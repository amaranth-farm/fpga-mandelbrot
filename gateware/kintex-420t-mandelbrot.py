#!/usr/bin/env python3
#
# Copyright (c) 2021 Hans Baier <hansfbaier@gmail.com>
# SPDX-License-Identifier: CERN-OHL-W-2.0
import os
import code

from amaranth            import *
from amaranth.lib.fifo   import SyncFIFOBuffered
from amaranth.lib.cdc    import ResetSynchronizer
from amaranth.build      import *

from amaranth_boards.resources    import *
from amaranth_boards.hpc_xc7k420t import HPCStoreXC7K420TPlatform

from amlib.debug.ila     import StreamILA, ILACoreParameters
from amlib.stream        import connect_stream_to_fifo, connect_fifo_to_stream

from fractalmanager import FractalManager

from hspi import HSPITransmitter, HSPIReceiver

odd_pins  = list(range(1, 75, 2))
even_pins = list(range(2, 76, 2))

GND       = None
btb_odd   = [GND, None, None,
             GND, "HD12",   "HD13",  "HD14",  "HD15",
             GND, "HD16",   "HD17",  "HD18",  "HD19",
             GND, "HD20",   "HD21",  "HD22",  "HD23",
             GND, "HD24",   "HD25",  "HD26",  "HD27",
             GND, "HD28",   "HD29",  "HD30",  "HD31",
             GND, "LED1",   "LED2"]

btb_even  = [GND, "HD10", "HD11",
             GND, "HRCLK", "HRACT", "HRVLD", "HTRDY",
             GND, "HD0",     "HD1",   "HD2",   "HD3",
             GND, "HD4",     "HD5",   "HD6",   "HD7",
             GND, "HD8",     "HD9", "HTVLD", "HTREQ",
             GND, "HTACK", "HTCLK"]

even = list(zip(btb_even, even_pins))
odd  = list(zip(btb_odd,  odd_pins))

pinmap = dict(filter(lambda t: t[0] != None, even + odd))
hd_pins     = " ".join([f"BTB_0:{pinmap[pin]}" for pin in [f"HD{i}" for i in range(0, 32)]])
control_pin = lambda pin: "BTB_0:" + str(pinmap[pin])

#code.interact(local=locals())

class KintexMandelbrotPlatform(HPCStoreXC7K420TPlatform):
    def __init__(self, io_voltage="3.3V", toolchain="Vivado"):
        self.resources += [
            # HSPI
            Resource("hspi", 0,
                Subsignal("hd",        Pins(hd_pins, dir="io")),

                Subsignal("tx_ack",    Pins(control_pin('HTRDY'), dir="o")),
                Subsignal("tx_ready",  Pins(control_pin('HTACK'), dir="i")),

                Subsignal("tx_req",    Pins(control_pin('HRACT'), dir="o")),
                Subsignal("rx_act",    Pins(control_pin('HTREQ'), dir="i")),

                Subsignal("tx_valid",  Pins(control_pin('HRVLD'), dir="o")),
                Subsignal("rx_valid",  Pins(control_pin('HTVLD'), dir="i")),
                Attrs(IOSTANDARD="LVCMOS33")
            ),
            Resource("hspi-clocks", 0,
                Subsignal("tx_clk",    Pins(control_pin('HRCLK'), dir="o")),
                Subsignal("rx_clk",    Pins(control_pin('HTCLK'), dir="i")),
                Attrs(IOSTANDARD="LVCMOS33")
            ),
        ]
        super().__init__(io_voltage, toolchain)

    @property
    def file_templates(self):
        templates = super().file_templates
        templates["{{name}}.xdc"] += "\nset_property CLOCK_DEDICATED_ROUTE FALSE [get_nets pin_hspi-clocks_0__rx_clk/crg_hspi-clocks_0__rx_clk__i]"
        return templates

class Xilinx7SeriesClockDomainGenerator(Elaboratable):
    DUTY_CYCLE      = 0.5
    NO_PHASE_SHIFT  = 0

    def wire_up_reset(self, m, reset):
        m.submodules.reset_sync_sync = ResetSynchronizer(reset, domain="sync")
        m.submodules.reset_sync_hspi = ResetSynchronizer(reset, domain="hspi")

    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()

        # Create our domains
        m.domains.sync = ClockDomain("sync")
        m.domains.hspi = ClockDomain("hspi")

        clk         = platform.request(platform.default_clk)

        hspi_clocks = platform.request("hspi-clocks", 0)
        main_clock   = Signal()
        main_locked  = Signal()
        hspi_clock   = Signal()
        hspi_locked  = Signal()
        reset        = Signal()

        mainpll_feedback  = Signal()
        hspipll_feedback  = Signal()

        mainpll_led = platform.request("led", 0)
        hspipll_led = platform.request("led", 1)
        pol_led = platform.request("led", 2)

        m.submodules.mainpll = Instance("PLLE2_ADV",
            p_CLKIN1_PERIOD        = 10,
            p_BANDWIDTH            = "OPTIMIZED",
            p_COMPENSATION         = "ZHOLD",
            p_STARTUP_WAIT         = "FALSE",

            p_DIVCLK_DIVIDE        = 1,
            p_CLKFBOUT_MULT        = 12,
            p_CLKFBOUT_PHASE       = self.NO_PHASE_SHIFT,

            # 100MHz
            p_CLKOUT0_DIVIDE       = 12,
            p_CLKOUT0_PHASE        = self.NO_PHASE_SHIFT,
            p_CLKOUT0_DUTY_CYCLE   = self.DUTY_CYCLE,

            i_CLKFBIN              = mainpll_feedback,
            o_CLKFBOUT             = mainpll_feedback,
            i_CLKIN1               = clk,
            o_CLKOUT0              = main_clock,
            o_LOCKED               = main_locked,
        )

        m.submodules.hspipll = Instance("PLLE2_ADV",
            p_CLKIN1_PERIOD        = 10.416666666, # 96MHz
            p_BANDWIDTH            = "OPTIMIZED",
            p_COMPENSATION         = "ZHOLD",
            p_STARTUP_WAIT         = "FALSE",

            p_DIVCLK_DIVIDE        = 1,
            p_CLKFBOUT_MULT        = 12,
            p_CLKFBOUT_PHASE       = self.NO_PHASE_SHIFT,

            # 96MHz
            p_CLKOUT0_DIVIDE       = 12,
            p_CLKOUT0_PHASE        = self.NO_PHASE_SHIFT,
            p_CLKOUT0_DUTY_CYCLE   = self.DUTY_CYCLE,

            i_CLKFBIN              = hspipll_feedback,
            o_CLKFBOUT             = hspipll_feedback,
            i_CLKIN1               = hspi_clocks.rx_clk,
            o_CLKOUT0              = hspi_clock,
            o_LOCKED               = hspi_locked,
        )

        m.d.comb += [
            reset.eq(~(main_locked & hspi_locked)),
            ClockSignal("sync").eq(main_clock),
            ClockSignal("hspi").eq(hspi_clock),
            mainpll_led.eq(main_locked),
            hspipll_led.eq(hspi_locked),
            pol_led.eq(0),
        ]

        self.wire_up_reset(m, reset)

        return m

class MandelbrotAccelerator(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        m.submodules.crg = Xilinx7SeriesClockDomainGenerator()

        hspi_pads = platform.request("hspi", 0)

        m.submodules.hspi_tx      = hspi_tx       = HSPITransmitter(domain="hspi")
        m.submodules.hspi_rx      = hspi_rx       = HSPIReceiver(domain="hspi")
        m.submodules.output_fifo  = output_fifo   = DomainRenamer("hspi")(SyncFIFOBuffered(width=34, depth=4096))

        m.d.comb += [
            ## connect HSPI receiver
            *hspi_rx.connect_to_pads(hspi_pads),

            ## connect HSPI transmitter
            hspi_tx.user_id0_in.eq(0x3ABCDEF),
            hspi_tx.user_id1_in.eq(0x3456789),
            hspi_tx.tll_2b_in.eq(0b11),
            hspi_tx.sequence_nr_in.eq(hspi_rx.sequence_nr_out),

            *hspi_tx.connect_to_pads(hspi_pads),
            hspi_tx.send_ack.eq(0),

            *connect_stream_to_fifo(hspi_rx.stream_out, output_fifo, firstBit=-2, lastBit=-1),
            *connect_fifo_to_stream(output_fifo, hspi_tx.stream_in, firstBit=-2, lastBit=-1),
        ]

        return m

if __name__ == "__main__":
    top = MandelbrotAccelerator()
    KintexMandelbrotPlatform(toolchain="Vivado").build(top, do_program=False)
