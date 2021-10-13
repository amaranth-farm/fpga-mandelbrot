from nmigen import *
from nmigen.build      import Platform
from nmigen.lib.coding import PriorityEncoder

from nmigen_library.test   import GatewareTestCase, sync_test_case
from nmigen_library.stream import StreamInterface

from mandelbrot import Mandelbrot

class FractalManager(Elaboratable):
    def __init__(self, *, bitwidth, fraction_bits, no_cores, test=False):
        # Parameters
        assert bitwidth % 8 == 0, "bitwidth must be a multiple of 8"
        self._bitwidth = bitwidth
        self._no_cores = no_cores
        self._fraction_bits = fraction_bits
        self._test = test

        # I/O
        self.command_stream_in  = StreamInterface(name="command_stream")
        self.pixel_stream_out   = StreamInterface(name="pixel_stream")
        self.busy               = Signal(no_cores)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        bitwidth  = self._bitwidth
        bytewidth = bitwidth // 8
        stream_in = self.command_stream_in
        no_cores = self._no_cores

        no_pixels_x    = Signal(16)
        no_pixels_y    = Signal(16)
        max_iterations = Signal(32)

        bottom_left_corner_x = Signal(signed(bitwidth))
        bottom_left_corner_y = Signal(signed(bitwidth))
        step                 = Signal(signed(bitwidth))

        current_x = Signal.like(bottom_left_corner_x)
        current_y = Signal.like(bottom_left_corner_y)
        current_pixel_x = Signal.like(no_pixels_x)
        current_pixel_y = Signal.like(no_pixels_y)

        bytepos          = Signal(16)
        command_complete = Signal()

        ready = Signal()
        m.d.comb += stream_in.ready.eq(ready)

        # read command
        with m.If(stream_in.valid & ready & ~command_complete):
            m.d.sync += bytepos.eq(bytepos + 1)

            with m.Switch(bytepos):
                with m.Case(0):
                    m.d.sync += no_pixels_x[:8].eq(stream_in.payload)
                with m.Case(1):
                    m.d.sync += no_pixels_x[8:].eq(stream_in.payload)

                with m.Case(2):
                    m.d.sync += no_pixels_y[:8].eq(stream_in.payload)
                with m.Case(3):
                    m.d.sync += no_pixels_y[8:].eq(stream_in.payload)

                for b in range(4):
                    with m.Case(4 + b):
                        m.d.sync += max_iterations[b*8:(b*8+8)].eq(stream_in.payload),

                for b in range(bytewidth):
                    with m.Case(8 + b):
                        m.d.sync += bottom_left_corner_x[b*8:(b*8+8)].eq(stream_in.payload),

                for b in range(bytewidth):
                    with m.Case(8 + bytewidth + b):
                        m.d.sync += bottom_left_corner_y[b*8:(b*8+8)].eq(stream_in.payload),

                for b in range(bytewidth):
                    with m.Case(8 + 2*bytewidth + b):
                        m.d.sync += step[b*8:(b*8+8)].eq(stream_in.payload),

                with m.Default():
                    m.d.sync += bytepos.eq(0)
                    with m.If(stream_in.payload == 0xa5):
                        m.d.sync += [
                            command_complete.eq(1),
                            current_x.eq(bottom_left_corner_x),
                            current_y.eq(bottom_left_corner_y),
                            current_pixel_x.eq(0),
                            current_pixel_y.eq(0),
                        ]
                    with m.Else():
                        m.d.sync += [
                            bottom_left_corner_x.eq(0),
                            bottom_left_corner_y.eq(0),
                            step.eq(0),
                            max_iterations.eq(64),
                        ]

        # instantiate cores
        cores    = []
        # core scheduler signals
        idle     = Array([Signal(                  name=f"idle_{n}")   for n in range(no_cores)])
        start    = Array([Signal(                  name=f"start_{n}")  for n in range(no_cores)])
        xs       = Array([Signal(signed(bitwidth), name=f"x_{n}")      for n in range(no_cores)])
        ys       = Array([Signal(signed(bitwidth), name=f"y_{n}")      for n in range(no_cores)])
        pixel_x = Array([Signal(signed(bitwidth),  name=f"pixelx_{n}") for n in range(no_cores)])
        pixel_y = Array([Signal(signed(bitwidth),  name=f"pixely_{n}") for n in range(no_cores)])

        m.d.comb += self.busy.eq(~Cat(idle))

        # result collector signals
        done       = Array([Signal(    name=f"done_{n}")    for n in range(no_cores)])
        collect    = Array([Signal(    name=f"collect_{n}") for n in range(no_cores)])
        maxed      = Array([Signal(    name=f"maxed_{n}")   for n in range(no_cores)])
        escape     = Array([Signal(    name=f"escape_{n}")  for n in range(no_cores)])
        iterations = Array([Signal(32, name=f"done_{n}")    for n in range(no_cores)])


        for c in range(no_cores):
            core = Mandelbrot(bitwidth=bitwidth, fraction_bits=self._fraction_bits, test=self._test)
            cores.append(core)
            m.submodules[f"core_{c}"] = core
            m.d.comb += [
                idle[c].eq(~core.busy_out),
                core.start_in.eq(start[c]),
                done[c].eq(core.result_ready_out),
                maxed[c].eq(core.maxed_out),
                escape[c].eq(core.escape_out),
                core.result_read_in.eq(collect[c]),
                iterations[c].eq(core.iterations_out),
                core.cx_in.eq(xs[c]),
                core.cy_in.eq(ys[c]),
                core.max_iterations_in.eq(max_iterations),
            ]

        # next core scheduler
        next_core       = Signal(range(no_cores))
        next_core_ready = Signal()
        current_core    = Signal.like(next_core)

        m.submodules.next_core_scheduler = next_core_scheduler = PriorityEncoder(no_cores)
        m.d.comb += [
            next_core_scheduler.i.eq(Cat(idle)),
            next_core.eq(next_core_scheduler.o),
            next_core_ready.eq(~next_core_scheduler.n),
        ]

        # result scheduler
        next_result_ready = Signal()
        next_result       = Signal(range(no_cores))
        current_result    = Signal.like(next_result)

        m.submodules.result_scheduler = result_scheduler = PriorityEncoder(no_cores)
        m.d.comb += [
            result_scheduler.i.eq(Cat(done)),
            next_result.eq(result_scheduler.o),
            next_result_ready.eq(~result_scheduler.n),
        ]


        # core scheduler FSM
        with m.FSM(name="scheduler") as fsm:
            m.d.comb += ready.eq(fsm.ongoing("IDLE"))
            with m.State("IDLE"):
                with m.If(command_complete):
                    m.d.comb += Cat(collect).eq(2**no_cores - 1)
                    m.d.sync += command_complete.eq(0)
                    m.next = "PICK"

            with m.State("PICK"):
                with m.If(  (current_pixel_x == no_pixels_x)
                          & (current_pixel_y == no_pixels_y)):
                    m.d.sync += [
                        current_pixel_x.eq(0),
                        current_pixel_y.eq(0),
                    ]
                    m.next = "IDLE"

                with m.Elif(next_core_ready):
                    m.d.sync += current_core.eq(next_core)
                    m.next = "SCHEDULE"

            with m.State("SCHEDULE"):
                m.d.sync += [
                    xs[current_core].eq(current_x),
                    ys[current_core].eq(current_y),
                    pixel_x[current_core].eq(current_pixel_x),
                    pixel_y[current_core].eq(current_pixel_y),
                ]

                with m.If(current_pixel_x < no_pixels_x):
                    m.d.sync += [
                        current_x.eq(current_x + step),
                        current_pixel_x.eq(current_pixel_x + 1),
                    ]
                with m.Else():
                    m.d.sync += [
                        current_x.eq(bottom_left_corner_x),
                        current_pixel_x.eq(0),
                        current_y.eq(current_y + step),
                        current_pixel_y.eq(current_pixel_y + 1),
                    ]

                m.next = "TRIGGER"

            with m.State("TRIGGER"):
                m.d.comb += start[current_core].eq(1)
                m.next = "PICK"


        pixel_out = self.pixel_stream_out
        result_iterations = Signal(32)
        result_color      = Signal(24)
        result_pixel_x    = Signal(16)
        result_pixel_y    = Signal(16)
        result_escape     = Signal()
        result_maxed      = Signal()
        send_byte         = Signal(8)
        first_result_sent = Signal()

        #
        ## convert iterations into color, using
        # the beautiful colors from the wikipedia mandelbrot images
        colortable = [
            [ 66,  30,  15],
            [ 25,   7,  26],
            [  9,   1,  47],
            [  4,   4,  73],
            [  0,   7, 100],
            [ 12,  44, 138],
            [ 24,  82, 177],
            [ 57, 125, 209],
            [134, 181, 229],
            [211, 236, 248],
            [241, 233, 191],
            [248, 201,  95],
            [255, 170,   0],
            [204, 128,   0],
            [153,  87,   0],
            [106,  52,   3],
        ]

        with m.If(result_escape):
            with m.Switch(result_iterations[0:4]):
                for i in range(16):
                    with m.Case(i):
                        m.d.comb += [
                            result_color[0:8]  .eq(colortable[i][0]),
                            result_color[8:16] .eq(colortable[i][1]),
                            result_color[16:24].eq(colortable[i][2]),
                        ]
        with m.Else():
            m.d.comb += result_color.eq(0)

        # result collector FSM
        with m.FSM(name="result_collector") as fsm:
            with m.State("WAIT"):
                with m.If(next_result_ready):
                    m.d.sync += current_result.eq(next_result)
                    m.next = "COLLECT"

            with m.State("COLLECT"):
                m.d.sync += [
                    result_iterations.eq(iterations [current_result]),
                    result_maxed     .eq(maxed      [current_result]),
                    result_escape    .eq(escape     [current_result]),
                    result_pixel_x   .eq(pixel_x    [current_result]),
                    result_pixel_y   .eq(pixel_y    [current_result]),
                    send_byte.eq(0),
                ]
                m.d.comb += collect[current_result].eq(1)
                m.next = "SEND"

            with m.State("SEND"):
                with m.If(pixel_out.ready):
                    m.d.sync += send_byte.eq(send_byte + 1)
                    m.d.comb += pixel_out.valid.eq(1)

                    with m.Switch(send_byte):
                        with m.Case(0):
                            m.d.comb += pixel_out.payload.eq(result_pixel_x[0:8])
                            # mark first result byte
                            with m.If(~first_result_sent):
                                m.d.comb += pixel_out.first.eq(1)
                                m.d.sync += first_result_sent.eq(1)
                        with m.Case(1):
                            m.d.comb +=  pixel_out.payload.eq(result_pixel_x[8:16])
                        with m.Case(2):
                            m.d.comb +=  pixel_out.payload.eq(result_pixel_y[0:8])
                        with m.Case(3):
                            m.d.comb +=  pixel_out.payload.eq(result_pixel_y[8:16])
                        with m.Case(4):
                            m.d.comb +=  pixel_out.payload.eq(result_color[0:8])
                        with m.Case(5):
                            m.d.comb +=  pixel_out.payload.eq(result_color[8:16])
                        with m.Case(6):
                            m.d.comb +=  pixel_out.payload.eq(result_color[16:24])
                        with m.Default():
                            # separator
                            m.d.comb +=  pixel_out.payload.eq(0xa5)
                            # mark last result byte
                            with m.If(Cat(idle) == Repl(Const(1, 1), no_cores)):
                                m.d.comb += pixel_out.last.eq(1)
                                m.d.sync += first_result_sent.eq(0)
                            m.next = "WAIT"

        return m

class FractalManagerTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = FractalManager
    FRAGMENT_ARGUMENTS = {'bitwidth': 64, 'fraction_bits': 56, 'no_cores':2, 'test': True}

    @sync_test_case
    def test_basic(self):
        scale = self.FRAGMENT_ARGUMENTS['fraction_bits']
        bitwidth = self.FRAGMENT_ARGUMENTS['bitwidth']
        bytewidth = bitwidth // 8
        dut = self.dut
        command_stream = dut.command_stream_in
        result_stream = dut.pixel_stream_out
        corner_x = -3 << (scale - 1)
        corner_y = 0
        step = 1 << (scale - 2)

        yield from self.advance_cycles(5)
        yield command_stream.valid.eq(1)
        yield result_stream.ready.eq(1)

        # send 0x0010 twice to calculate 4x4 pixels
        for _ in range(2):
            yield command_stream.payload.eq(4)
            yield
            yield command_stream.payload.eq(0)
            yield

        # max iterations
        max_iterations = 63
        for b in range(4):
            yield command_stream.payload.eq(max_iterations >> (8 * b))
            yield

        # send corner_x
        for i in  range(bytewidth):
            yield command_stream.payload.eq(0xff & (corner_x >> (i * 8)))
            yield

        # send corner_y
        for i in  range(bytewidth):
            yield command_stream.payload.eq(0xff & (corner_y >> (i * 8)))
            yield

        # send step
        for i in  range(bytewidth):
            yield command_stream.payload.eq(0xff & (step >> (i * 8)))
            yield

        yield command_stream.payload.eq(0xa5)
        yield

        yield command_stream.valid.eq(0)

        yield from self.advance_cycles(2500)