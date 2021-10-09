from nmigen import *
from nmigen.build import Platform
from nmigen_library.test   import GatewareTestCase, sync_test_case

# work around https://github.com/nmigen/nmigen/pull/640

class PriorityEncoder(Elaboratable):
    """Priority encode requests to binary.

    If any bit in ``i`` is asserted, ``n`` is low and ``o`` indicates the least significant
    asserted bit.
    Otherwise, ``n`` is high and ``o`` is ``0``.

    Parameters
    ----------
    width : int
        Bit width of the input.

    Attributes
    ----------
    i : Signal(width), in
        Input requests.
    o : Signal(range(width)), out
        Encoded binary.
    n : Signal, out
        Invalid: no input bits are asserted.
    """
    def __init__(self, width):
        self.width = width

        self.i = Signal(width)
        self.o = Signal(range(width))
        self.n = Signal()

    def elaborate(self, platform):
        m = Module()
        for j in range(self.width):
            with m.If(self.i[j]):
                m.d.comb += self.o.eq(j)
        m.d.comb += self.n.eq(self.i == 0)
        return m

class TestHarness(Elaboratable):
    def __init__(self, width):
        self.width = width
        self.i = Signal(width)
        self.o = Signal(range(width))
        self.n = Signal()

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        m.submodules.encoder = encoder = PriorityEncoder(self.width)

        m.d.sync += [
            encoder.i.eq(self.i)
        ]

        m.d.comb += [
            self.o.eq(encoder.o),
            self.n.eq(encoder.n),
        ]

        return m

class PriorityEncoderTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = TestHarness
    FRAGMENT_ARGUMENTS = {'width': 3}

    @sync_test_case
    def test_basic(self):
        dut = self.dut
        for i in range(8):
            yield dut.i.eq(i)
            yield

        yield from self.advance_cycles(3)
