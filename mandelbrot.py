from nmigen import *
from nmigen.build import Platform
from nmigen_library.test   import GatewareTestCase, sync_test_case

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
        self.result_read_in    = Signal()

        # Outputs
        self.busy_out          = Signal()
        self.escape_out        = Signal()
        self.maxed_out         = Signal()
        self.done_out          = Signal()
        self.result_ready_out  = Signal()
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
        iteration = Signal(32)

        # pipeline stages enable signals
        stage_enable = Signal(5)

        # pipeline stage 1
        two_xy = Signal(signed(bitwidth))
        xx     = Signal(signed(bitwidth))
        yy     = Signal(signed(bitwidth))

        # pipeline stage 2
        xx_plus_yy    = Signal(signed(bitwidth))
        xx_minus_yy   = Signal(signed(bitwidth))

        # pipeline stage 3
        x             = Signal(signed(bitwidth))
        x             = Signal(signed(bitwidth))
        y             = Signal(signed(bitwidth))
        escape        = Signal()
        maxed_out     = Signal()
        result_read   = Signal(reset=1)

        four = Signal(signed(bitwidth))

        with m.If(self.result_read_in):
            m.d.sync += [
                result_read.eq(1),
                self.result_ready_out.eq(0),
                maxed_out.eq(0),
                escape.eq(0),
                iteration.eq(0)
            ]

        m.d.comb += [
            self.busy_out.eq(running | ~result_read),
            self.iterations_out.eq(iteration),
            self.escape_out.eq(escape),
            self.maxed_out.eq(maxed_out),
            four.eq(Const(4, signed(bitwidth)) << scale),
        ]

        # instantiate a multiplier for reuse
        # the product has one bit more than necessary
        # because we want to preserve the bit of precision
        # for the factor 2xy
        factor1           = Signal(bitwidth)
        factor2           = Signal(bitwidth)
        two_times_product = Signal(bitwidth)

        m.d.comb += two_times_product.eq((factor1 * factor2) >> (scale - 1))

        if test:
            m.d.comb += [
                self.x.eq(x),
                self.y.eq(y),
                self.xx_plus_yy.eq(xx_plus_yy),
            ]

        # processing pipleline
        # here still used in a sequential manner
        # to be made fully pipelined later
        with m.If(stage_enable[0]):
            # stage 0
            m.d.comb += [
                factor1.eq(x),
                factor2.eq(x),
            ]
            m.d.sync += [
                xx.eq(two_times_product >> 1),
            ]

        with m.If(stage_enable[1]):
            # stage 1
            m.d.comb += [
                factor1.eq(y),
                factor2.eq(y),
            ]
            m.d.sync += [
                yy.eq(two_times_product >> 1),
            ]

        with m.If(stage_enable[2]):
            # stage 2
            m.d.comb += [
                factor1.eq(x),
                factor2.eq(y),
            ]
            m.d.sync += [
                two_xy.eq(two_times_product),
            ]

        with m.If(stage_enable[3]):
            # stage 3
            m.d.sync += [
                xx_plus_yy    .eq(xx + yy),
                xx_minus_yy   .eq(xx - yy),
            ]

        with m.If(stage_enable[4]):
            # stage 4
            m.d.sync += [
                x             .eq(xx_minus_yy   + self.cx_in),
                y             .eq(two_xy        + self.cy_in),
                escape        .eq(xx_plus_yy > four),
                iteration     .eq(iteration + 1),
                maxed_out     .eq(iteration >= self.max_iterations_in),
            ]

        with m.FSM() as fsm:
            m.d.comb += running.eq(~fsm.ongoing("IDLE"))
            with m.State("IDLE"):
                with m.If(self.start_in):
                    m.d.sync += [
                        x             .eq(self.cx_in),
                        y             .eq(self.cy_in),
                        two_xy        .eq(0),
                        xx            .eq(0),
                        yy            .eq(0),
                        xx_plus_yy    .eq(0),

                        escape                .eq(0),
                        maxed_out             .eq(0),
                        iteration             .eq(0),
                        self.result_ready_out .eq(0),
                        result_read           .eq(0),
                    ]
                    m.next = "S0"

            with m.State("S0"):
                m.d.comb += stage_enable.eq(1)
                with m.If(escape | maxed_out):
                    m.d.comb += self.done_out.eq(1)
                    m.d.sync += self.result_ready_out.eq(1)
                    m.next = "IDLE"
                with m.Else():
                    m.next = "S1"

            with m.State("S1"):
                m.d.comb += stage_enable.eq(1 << 1)
                m.next = "S2"

            with m.State("S2"):
                m.d.comb += stage_enable.eq(1 << 2)
                m.next = "S3"

            with m.State("S3"):
                m.d.comb += stage_enable.eq(1 << 3)
                m.next = "S4"

            with m.State("S4"):
                m.d.comb += stage_enable.eq(1 << 4)
                m.next = "S0"

        return m

class MandelbrotTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = Mandelbrot
    FRAGMENT_ARGUMENTS = {'bitwidth': 64, 'fraction_bits': 56, 'test': True}

    def iterate_mandel(self, scale, dut, start_x, start_y, check=True):
        print("=================> mandel start")
        x = start_x
        y = start_y
        done = 0
        yield from self.advance_cycles(5)
        while done == 0:
            x = ((x * x) >> scale) - ((y * y) >> scale) + start_x
            y = ((x * y) >> (scale - 1)) + start_y
            dut_x = (yield dut.x)
            dut_y = (yield dut.y)
            print(f"dut_x: {hex(dut_x)} python x: {hex(x)} | dut_y: {hex(dut_y)} python y: {hex(y)}")
            if check:
                self.assertEqual(dut_x, x)
                self.assertEqual(dut_y, y)
            yield from self.advance_cycles(5)
            done = (yield dut.maxed_out) | (yield dut.escape_out)

        self.assertEqual(done, 1)
        yield dut.result_read_in.eq(1)
        yield
        yield dut.result_read_in.eq(0)
        yield


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
        yield from self.advance_cycles(5)

        # 1 * 1 + 1 = 2
        first_iter = start_x + start_x
        self.assertEqual((yield dut.x), first_iter)
        yield from self.advance_cycles(5)

        # 2 * 2 + 1 = 5
        second_iter = (first_iter * first_iter >> scale) + start_x
        self.assertEqual((yield dut.x), second_iter)
        yield
        yield
        self.assertGreater((yield dut.xx_plus_yy), 4 << scale)
        yield from self.advance_cycles(5)

        self.assertEqual((yield dut.escape_out), 1)

        yield dut.result_read_in.eq(1)
        yield
        yield dut.result_read_in.eq(0)
        yield

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
        yield
        self.assertEqual((yield dut.result_ready_out), 0)
        yield
