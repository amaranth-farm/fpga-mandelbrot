from nmigen import *
from nmigen.build import Platform
from nmigen_library.test   import GatewareTestCase, sync_test_case
from nmigen_library.stream import StreamInterface


class Mandelcore(Elaboratable):
    def __init__(self):
        self.command_stream_in  = StreamInterface()
        self.pixel_stream_out   = StreamInterface()

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        return m


class Mandelbrot(Elaboratable):
    def __init__(self, *, bitwidth=128, fraction_bits=120, test=False):
        # Parameters
        self._bitwidth = bitwidth
        self._fraction_bits = fraction_bits
        self._test = test

        # Inputs
        self.cx_in             = Signal(signed(bitwidth))
        self.cy_in             = Signal(signed(bitwidth))
        self.start_in          = Signal()
        self.max_iterations_in = Signal(32)

        # Outputs
        self.busy_out          = Signal()
        self.escape_out        = Signal()
        self.maxed_out         = Signal()
        self.done_out          = Signal()
        self.iterations_out    = Signal(32)

        if test:
            self.x          = Signal.like(self.cx_in)
            self.y          = Signal.like(self.cy_in)
            self.xx_plus_yy = Signal.like(self.cy_in)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        bitwidth = self._bitwidth
        scale = self._fraction_bits
        test = self._test

        running   = Signal()
        iteration = Signal(34)

        # pipeline stages enable signals
        stage_enable = Signal(3)

        # pipeline stage 1
        two_xy_stage1 = Signal(signed(bitwidth))
        xx     = Signal(signed(bitwidth))
        yy     = Signal(signed(bitwidth))

        # pipeline stage 2
        xx_plus_yy    = Signal(signed(bitwidth))
        two_xy_stage2 = Signal(signed(bitwidth))

        # pipeline stage 3
        x             = Signal(signed(bitwidth))
        y             = Signal(signed(bitwidth))
        escape        = Signal()
        maxed_out     = Signal()

        four = Signal(signed(bitwidth))

        m.d.comb += [
            self.busy_out.eq(running),
            self.iterations_out.eq(iteration),
            self.escape_out.eq(escape),
            self.maxed_out.eq(maxed_out),
            four.eq(Const(4, signed(bitwidth)) << scale),
        ]

        if test:
            m.d.comb += [
                self.x.eq(x),
                self.y.eq(y),
                self.xx_plus_yy.eq(xx_plus_yy),
            ]

        with m.If(stage_enable[0]):
            m.d.sync += [
                # stage 1
                two_xy_stage1 .eq((x * y) >> (scale - 1)),
                xx            .eq((x * x) >> scale),
                yy            .eq((y * y) >> scale),
            ]

        with m.If(stage_enable[1]):
            m.d.sync += [
                # stage 2
                two_xy_stage2 .eq(two_xy_stage1),
                xx_plus_yy    .eq(xx + yy),
            ]

        with m.If(stage_enable[2]):
            m.d.sync += [
                # stage 3
                x             .eq(xx_plus_yy    + self.cx_in),
                y             .eq(two_xy_stage2 + self.cy_in),
                escape        .eq(xx_plus_yy > four),
                iteration     .eq(iteration + 1),
                maxed_out     .eq(iteration >= self.max_iterations_in),
            ]

        with m.FSM() as fsm:
            m.d.comb += running.eq(~fsm.ongoing("IDLE"))
            with m.State("IDLE"):
                with m.If(self.start_in):
                    m.d.sync += [
                        # stage 0
                        x             .eq(self.cx_in),
                        y             .eq(self.cy_in),
                        # stage 1
                        two_xy_stage1 .eq(0),
                        xx            .eq(0),
                        yy            .eq(0),
                        # stage 2
                        two_xy_stage2 .eq(0),
                        xx_plus_yy    .eq(0),

                        # non-pipelined
                        escape        .eq(0),
                        maxed_out     .eq(0),
                        iteration     .eq(0),
                    ]
                    m.next = "S1"

            with m.State("S1"):
                m.d.comb += stage_enable.eq(0b001)
                with m.If(escape | maxed_out):
                    m.d.comb += self.done_out.eq(1)
                    m.next = "IDLE"
                with m.Else():
                    m.next = "S2"

            with m.State("S2"):
                m.d.comb += stage_enable.eq(0b010)
                m.next = "S3"

            with m.State("S3"):
                m.d.comb += stage_enable.eq(0b100)
                m.next = "S1"

        return m

class MandelbrotTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = Mandelbrot
    FRAGMENT_ARGUMENTS = {'bitwidth': 64, 'fraction_bits': 56, 'test': True}

    def iterate_mandel(self, scale, dut, start_x, start_y, check=True):
        print("=================> mandel start")
        x = start_x
        y = start_y
        done = 0
        yield from self.advance_cycles(3)
        while done == 0:
            x = ((x * x) >> scale) + start_x
            y = ((x * y) >> (scale - 1)) + start_y
            dut_x = (yield dut.x)
            dut_y = (yield dut.y)
            print(f"dut_x: {hex(dut_x)} python x: {hex(x)} | dut_y: {hex(dut_y)} python y: {hex(y)}")
            if check:
                self.assertEqual(dut_x, x)
                self.assertEqual(dut_y, y)
            yield from self.advance_cycles(3)
            done = (yield dut.maxed_out) | (yield dut.escape_out)

        self.assertEqual(done, 1)


    @sync_test_case
    def test_basic(self):
        scale = self.FRAGMENT_ARGUMENTS['fraction_bits']
        dut = self.dut
        start_x = 1 << scale
        yield dut.cx_in.eq(start_x)
        yield dut.cy_in.eq(0)
        yield dut.max_iterations_in.eq(6)
        yield
        yield from self.pulse(dut.start_in)
        yield
        yield

        self.assertEqual((yield dut.x), start_x)
        yield from self.advance_cycles(3)

        # 1 * 1 + 1 = 2
        first_iter = start_x + start_x
        self.assertEqual((yield dut.x), first_iter)
        yield from self.advance_cycles(3)

        # 2 * 2 + 1 = 5
        second_iter = (first_iter * first_iter >> scale) + start_x
        self.assertEqual((yield dut.x), second_iter)
        self.assertGreater((yield dut.xx_plus_yy), 4 << scale)
        yield from self.advance_cycles(3)

        self.assertEqual((yield dut.escape_out), 1)

        start_x = 1 << (scale - 1)
        start_y = 0
        yield dut.cx_in.eq(start_x)
        yield dut.cy_in.eq(start_y)
        yield
        yield from self.pulse(dut.start_in)
        yield
        yield from self.iterate_mandel(scale, dut, start_x, start_y)

        yield
        yield

        start_x = 0
        start_y = 1 << (scale - 1)
        yield dut.cx_in.eq(start_x)
        yield dut.cy_in.eq(start_y)
        yield
        yield from self.pulse(dut.start_in)
        yield
        yield from self.iterate_mandel(scale, dut, start_x, start_y, check=False)

        yield
        yield

        start_x = 1 << (scale - 2)
        start_y = 1 << (scale - 3)
        yield dut.cx_in.eq(start_x)
        yield dut.cy_in.eq(start_y)
        yield
        yield from self.pulse(dut.start_in)
        yield
        yield from self.iterate_mandel(scale, dut, start_x, start_y, check=False)

