#!/usr/bin/env python3
#%%
import struct
import usb

dev=usb.core.find(idVendor=0x1209, idProduct=0xDECA)
print(dev)

import struct
import time

scale = 8*8

def send_command(bytewidth, no_pixels_x, no_pixels_y, max_iterations, bottom_left_corner_x, bottom_left_corner_y, step):
    command_bytes = struct.pack("HHI", no_pixels_x, no_pixels_y, max_iterations)

    command_bytes += bottom_left_corner_x.to_bytes(bytewidth, byteorder='little', signed=True)
    command_bytes += bottom_left_corner_y.to_bytes(bytewidth, byteorder='little', signed=True)
    command_bytes += step.to_bytes(bytewidth, byteorder='little', signed=True)
    command_bytes += bytes([0xa5])
    print(f"command: {str(bytes(command_bytes))}")

    dev.write(0x01, command_bytes)

    time.sleep(0.2)

    result = []
    try:
        while True:
            print("read")
            r = dev.read(0x81, 256, timeout=200)
            print("Got: "+ str(len(r)))
            print(str(r))
            result += r
    except usb.USBError:
        print(f"Got Total: {len(result)}")

    if len(result) > 0:
        first_separator_index = result.index(0xa5)
        if first_separator_index != 9:
            print(f"Chop until index {first_separator_index}")
            result = result[first_separator_index+1:]
        pixels = [struct.unpack("HHIBx", bytes(p)) for p in [result[i:i+10] for i in range(0, len(result), 10)] if len(p) == 10]
        for pixel in pixels:
            print(f"x: {pixel[0]} y: {pixel[1]} iterations: {pixel[2]}\t escape: {pixel[3] >> 4} maxed: {pixel[3] & 0xf}")

        print(f"Total number of pixels: {len(pixels)}")

corner_x = -2 << scale
corner_y = 1
step = 1 << (scale - 3)

#send_command(9, 1920, 1080, 256, corner_x, corner_y, step)
send_command(9, 4, 4, 256, corner_x, corner_y, step)


# %%
