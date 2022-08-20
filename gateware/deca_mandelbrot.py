#!/usr/bin/env python3
#
# Copyright (c) 2021 Hans Baier <hansfbaier@gmail.com>
# SPDX-License-Identifier: CERN-OHL-W-2.0
import os

from amaranth            import *
from amaranth.lib.fifo   import AsyncFIFO

from amlib.debug.ila     import StreamILA, ILACoreParameters
from amlib.stream        import connect_stream_to_fifo, connect_fifo_to_stream
from amlib.io.led        import NumberToSevenSegmentHex
from amlib.io.max7219    import SerialLEDArray

from luna                import top_level_cli
from luna.usb2           import USBDevice, USBStreamInEndpoint, USBStreamOutEndpoint

from usb_protocol.types                       import USBRequestType, USBDirection, USBStandardRequests
from usb_protocol.emitters                    import DeviceDescriptorCollection

from luna.gateware.usb.usb2.device            import USBDevice
from luna.gateware.usb.usb2.endpoints.stream  import USBMultibyteStreamInEndpoint
from luna.gateware.usb.usb2.request           import USBRequestHandler, StallOnlyRequestHandler

from fractalmanager import FractalManager


class MandelbrotAccelerator(Elaboratable):
    MAX_PACKET_SIZE = 256
    USE_ILA = False
    ILA_MAX_PACKET_SIZE = 512

    def create_descriptors(self):
        """ Creates the descriptors that describe our audio topology. """

        descriptors = DeviceDescriptorCollection()

        with descriptors.DeviceDescriptor() as d:
            d.bcdUSB             = 2.00
            d.bDeviceClass       = 0xEF
            d.bDeviceSubclass    = 0x02
            d.bDeviceProtocol    = 0x01
            d.idVendor           = 0x1209
            d.idProduct          = 0xDECA

            d.iManufacturer      = "Hans Baier"
            d.iProduct           = "DECA-Mandelbrot"
            d.iSerialNumber      = "0815"
            d.bcdDevice          = 0.01

            d.bNumConfigurations = 1

        with descriptors.ConfigurationDescriptor() as configDescr:
            with configDescr.InterfaceDescriptor() as i:
                i.bInterfaceNumber = 0

                with i.EndpointDescriptor() as e:
                    e.bEndpointAddress = USBDirection.IN.to_endpoint_address(1) # EP 1 IN
                    e.wMaxPacketSize   = self.MAX_PACKET_SIZE

                with i.EndpointDescriptor() as e:
                    e.bEndpointAddress = USBDirection.OUT.to_endpoint_address(1) # EP 1 OUT
                    e.wMaxPacketSize   = self.MAX_PACKET_SIZE

            if self.USE_ILA:
                with configDescr.InterfaceDescriptor() as i:
                    i.bInterfaceNumber = 1

                    with i.EndpointDescriptor() as e:
                        e.bEndpointAddress = USBDirection.IN.to_endpoint_address(3) # EP 3 IN
                        e.wMaxPacketSize   = self.ILA_MAX_PACKET_SIZE

        return descriptors


    def elaborate(self, platform):
        m = Module()

        # Generate our domain clocks/resets.
        m.submodules.car = platform.clock_domain_generator()

        ulpi = platform.request(platform.default_usb_connection)
        m.submodules.usb = usb = USBDevice(bus=ulpi)

        # Add our standard control endpoint to the device.
        descriptors = self.create_descriptors()
        control_ep = usb.add_control_endpoint()
        control_ep.add_standard_request_handlers(descriptors, blacklist=[
            lambda setup:   (setup.type    == USBRequestType.STANDARD)
                          & (setup.request == USBStandardRequests.SET_INTERFACE)
        ])

        # Attach class-request handlers that stall any vendor or reserved requests,
        # as we don't have or need any.
        stall_condition = lambda setup : \
            (setup.type == USBRequestType.VENDOR) | \
            (setup.type == USBRequestType.RESERVED)
        control_ep.add_request_handler(StallOnlyRequestHandler(stall_condition))

        ep1_out = USBStreamOutEndpoint(
            endpoint_number=1, # EP 1 OUT
            max_packet_size=self.MAX_PACKET_SIZE)
        usb.add_endpoint(ep1_out)

        ep1_in = USBStreamInEndpoint(
            endpoint_number=1, # EP 1 IN
            max_packet_size=self.MAX_PACKET_SIZE)
        usb.add_endpoint(ep1_in)

        m.submodules.command_fifo = command_fifo = AsyncFIFO(width=8, depth=32, w_domain="usb", r_domain="fast")
        m.submodules.result_fifo  = result_fifo  = AsyncFIFO(width=8+2, depth=4*self.MAX_PACKET_SIZE, w_domain="fast", r_domain="usb")

        m.submodules.fractalmanager = fractalmanager = DomainRenamer("fast")(FractalManager(bitwidth=8*9, fraction_bits=8*8, no_cores=9))

        # wire up USB via FIFOs to fractalmanager
        m.d.comb += [
            connect_stream_to_fifo(ep1_out.stream, command_fifo),
            connect_fifo_to_stream(command_fifo, fractalmanager.command_stream_in),
            connect_stream_to_fifo(fractalmanager.pixel_stream_out, result_fifo),
            result_fifo.w_data[8].eq(fractalmanager.pixel_stream_out.first),
            result_fifo.w_data[9].eq(fractalmanager.pixel_stream_out.last),
            connect_fifo_to_stream(result_fifo, ep1_in.stream),
            ep1_in.stream.first.eq(result_fifo.r_data[8]),
            ep1_in.stream.last.eq(result_fifo.r_data[9]),
        ]

        # Connect our device as a high speed device
        m.d.comb += [
            usb.connect          .eq(1),
            usb.full_speed_only  .eq(0),
        ]

        if self.USE_ILA:
            usb_in_active = Signal()

            m.d.comb += [
                usb_in_active.eq(ep1_out.stream.ready & ep1_out.stream.valid)
            ]

            signals = [
                #ep1_out.stream.ready,
                #ep1_out.stream.valid,
                #ep1_out.stream.first,
                #ep1_out.stream.last,
                #ep1_out.stream.payload,
                #usb_in_active,
                result_fifo.r_level,
                ep1_in.stream.ready,
                ep1_in.stream.valid,
                ep1_in.stream.first,
                ep1_in.stream.last,
                ep1_in.stream.payload,
            ]

            signals_bits = sum([s.width for s in signals])
            depth = 1 * 8 * 1024 #int(33*8*1024/signals_bits)
            m.submodules.ila = ila = \
                StreamILA(
                    signals=signals,
                    sample_depth=depth,
                    domain="usb", o_domain="usb",
                    samples_pretrigger=128)

            stream_ep = USBMultibyteStreamInEndpoint(
                endpoint_number=3, # EP 3 IN
                max_packet_size=self.ILA_MAX_PACKET_SIZE,
                byte_width=ila.bytes_per_sample
            )
            usb.add_endpoint(stream_ep)

            m.d.comb += [
                stream_ep.stream.stream_eq(ila.stream),
                ila.trigger.eq(ep1_in.stream.first),
            ]

            ILACoreParameters(ila).pickle()

        leds = Cat([platform.request("led", i) for i in range(8)])
        m.d.comb += [
            leds[0].eq(usb.rx_activity_led),
            leds[1].eq(usb.tx_activity_led),
            leds[2].eq(usb.suspended),
            Cat(leds[3:6]).eq(fractalmanager.busy_out),
            leds[6].eq(result_fifo.r_en),
            leds[7].eq(result_fifo.r_rdy),
        ]

        spi = platform.request("spi")
        m.submodules.sevensegment = sevensegment = NumberToSevenSegmentHex(width=32)
        m.submodules.led_display = led_display = SerialLEDArray(divisor=8, init_delay=16e6)
        m.d.comb += [
            sevensegment.number_in.eq((fractalmanager.result_x_out << 16) | fractalmanager.result_y_out),
            sevensegment.dots_in.eq(fractalmanager.busy_out),
            *led_display.connect_to_resource(spi),
            Cat(led_display.digits_in).eq(sevensegment.seven_segment_out),
            led_display.valid_in.eq(1),
        ]

        return m

if __name__ == "__main__":
    os.environ["LUNA_PLATFORM"] = "arrow_deca:ArrowDECAPlatform"
    top_level_cli(MandelbrotAccelerator)