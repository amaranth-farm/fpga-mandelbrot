import libusb, strutils
import std/random
import std/sugar
import system
import pkg/nint128
import struct
import sequtils

let debug = false

proc seq_hex*(s: seq[byte]): string =
    return "[" & join(collect(for e in s: e.toHex().toLowerAscii()), ", ") & "]"

proc printDevice*(device: ptr LibusbDevice) =
    # Print information about the given USB device
    var desc: LibusbDeviceDescriptor
    let r = libusbGetDeviceDescriptor(device, addr desc)
    if (r < 0):
        echo "Error: Failed to get device descriptor"
    else:
        var p = ""
        var path: array[8, uint8]
        let n = libusbGetPortNumbers(device, addr path[0], (cint)sizeof(path))
        if n > 0:
            p = " path: "
            p.add($path[0])
            for i in 1..<n:
                p.add(".")
                p.add($path[i])
        echo toHex(desc.idVendor, 4), ":", toHex(desc.idProduct, 4),
            " (bus ", libusbGetBusNumber(device),
            ", device ", libusbGetDeviceAddress(device), ")", p

proc bye*(devices: ptr LibusbDeviceArray, exitcode: int) =
    libusbFreeDeviceList(devices, 1)
    libusbExit(nil)
    quit(exitcode)

proc transfer(devHandle: ptr LibusbDeviceHandle, ep: char, data: ptr char, length: uint, timeout: uint): cint =
    var actualLength: cint
    let s = libusbBulkTransfer(devHandle, ep, data, (cint)length, addr actualLength, (cuint)timeout)

    case (LibusbError)s:
     of Libusberror.success:
        if debug:
            echo "transfer success"
        discard
     of Libusberror.timeout:
        if debug:
            echo "transfer timeout"
        discard
     else:
        stderr.write "USB transfer Error"

    return actualLength

proc receive(devHandle: ptr LibusbDeviceHandle, data: ptr byte, length: uint, timeout: uint): cint =
    return transfer(devHandle, (char)0x81, cast[ptr char](data), length, timeout)

proc send(devHandle: ptr LibusbDeviceHandle, data: ptr byte, length: uint, timeout: uint): cint =
    return transfer(devHandle, (char)0x1, cast[ptr char](data), length, timeout)

proc usb_init*(): (ptr LibusbDeviceHandle, ptr LibusbDeviceArray) =
    randomize()

    # initialize library
    let r = libusbInit(nil)

    if r < 0:
        echo "Error: Failed to initialize libusb"
        quit(-1)
    else:
        echo "Success: Initialized libusb"

        # detect available USB devices
        var devices: ptr LibusbDeviceArray = nil
        let cnt = libusbGetDeviceList(nil, addr devices)
        echo "Number of detected USB devices: ", cnt

        var device: ptr LibusbDevice = nil
        var descriptor: LibusbDeviceDescriptor

        # print device details
        for i in 0..<cnt:
            let d = devices[i]
            let r = libusbGetDeviceDescriptor(d, addr descriptor)
            if (r < 0):
                continue
            if ((descriptor.idVendor == 0x1209'i16) and (descriptor.idProduct == 0xdeca'i16)):
                stdout.write "Got device: "
                device = d
                printDevice(device)
                break

        if device == nil:
            echo "Unable to find device"
            bye(devices, -1)

        var devHandle: ptr LibusbDeviceHandle
        let r = libusbOpen(device, addr devHandle)
        if r < 0:
            echo "Could not open device: ", r
            bye(devices, -1)

        return (devHandle, devices)

proc send_request*(devHandle: ptr LibusbDeviceHandle, bytewidth: uint8,
                  width: uint16, height: uint16, max_iterations: uint32,
                  corner_x: UInt128, corner_y: UInt128, step: UInt128): iterator(): array[256, byte] {.thread.} =
    let
        command_header     = cast[seq[byte]](pack("HHI", width-1, height-1, max_iterations))
        corner_x_bytes     = corner_x.toBytesLE()[0..<bytewidth]
        corner_y_bytes     = corner_y.toBytesLE()[0..<bytewidth]
        step_bytes         = step.toBytesLE()[0..<bytewidth]

    var command: seq[byte] = concat(command_header, corner_x_bytes, corner_y_bytes, step_bytes, @[0xa5'u8])

    var r = send(devHandle, addr command[0], (uint)len(command), 100)

    if debug:
        echo "corner_x: ", $seq_hex(corner_x_bytes)
        echo "corner_y: ", $seq_hex(corner_y_bytes)
        echo "step: ", $seq_hex(step_bytes)
        echo $seq_hex(command)
        echo "request bytes sent: ", r

    let timeout = (uint)max(1, ((float32)max_iterations) / 1000.0)

    var data: array[256, byte]

    return iterator(): array[256, byte] =
        while true:
            r = receive(devHandle, addr data[0], 256, timeout)
            if r > 0:
                yield data
            else:
                break

let usb* {. global .} = usb_init()

# [0x73, 0x7,    0xd3, 0x7, 0xaa, 0x0, 0x0, 0x0,
# 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0xfe,
# 0x0, 0x60, 0x1b, 0xb1, 0x2e, 0x3d, 0xe6, 0xaf, 0xfe,
# 0x5c, 0xc3, 0xa4, 0xb1, 0xb9, 0xde, 0x55, 0x0, 0x0, 0xa5]

if debug:
    for i in send_request(usb[0], 9, 1024, 1024, 0xaa, u128("0xfe0000000000000000"), u128("0xfeafe63d2eb11b6000"), u128("0x55deb9b1a4c35c")):
        echo $seq_hex(@i)
    quit(0)