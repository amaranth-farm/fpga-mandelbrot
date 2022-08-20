import libusb, strutils
import std/random
import system
import pkg/nint128
import struct
import sequtils

proc printDevice(device: ptr LibusbDevice) =
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

proc bye(devices: ptr LibusbDeviceArray, exitcode: int) =
    libusbFreeDeviceList(devices, 1)
    libusbExit(nil)
    quit(exitcode)

proc transfer(devHandle: ptr LibusbDeviceHandle, ep: char, data: ptr char, length: uint): cint =
    var actualLength: cint
    let s = libusbBulkTransfer(devHandle, ep, data, (cint)length, addr actualLength, (cuint)1)

    case (LibusbError)s:
     of Libusberror.success:
        discard
     of Libusberror.timeout:
        discard # stdout.write "T"
     else:
        stdout.write "E"

    return actualLength

proc receive(devHandle: ptr LibusbDeviceHandle, data: ptr byte, length: uint): cint =
    return transfer(devHandle, (char)0x81, cast[ptr char](data), length)

proc send(devHandle: ptr LibusbDeviceHandle, data: ptr byte, length: uint): cint =
    return transfer(devHandle, (char)0x1, cast[ptr char](data), length)

proc usb_init(): (ptr LibusbDeviceHandle, ptr LibusbDeviceArray) =
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

var data: array[4000*4000, byte]

proc send_request(devHandle: ptr LibusbDeviceHandle, bytewidth: uint8, width: uint16, height: uint16, max_iterations: uint32, corner_x: UInt128, corner_y: UInt128, step: UInt128) =
    var
        command_header     = cast[seq[byte]](pack("HHI", width-1, height-1, max_iterations))
        corner_x_bytes     = corner_x.toBytesLE()[0..<bytewidth]
        corner_y_bytes     = corner_y.toBytesLE()[0..<bytewidth]
        step_bytes         = step.toBytesLE()[0..<bytewidth]
        command: seq[byte] = concat(command_header, corner_x_bytes, corner_y_bytes, step_bytes, @[0xa5'u8])

    var r = send(devHandle, addr command[0], (uint)len(command))

    echo $command
    echo r

    r = receive(devHandle, addr data[0], 1000)
    echo r


let usb = usb_init()


send_request(usb[0], 8, 1024, 1024, 1024, u128("0x998877665544332211"), u128("0x998877665544332211"), u128("0x998877665544332211"))
quit(0)