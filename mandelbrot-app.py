#!/usr/bin/env python3

# this is a throwaway prototype
# so the code is highly experimental

import time
import struct
import usb
import code
import sys
import subprocess

dev=usb.core.find(idVendor=0x1209, idProduct=0xDECA)

debug=False
if debug: print(dev)

scale = 8*8


def send_command(bytewidth, no_pixels_x, no_pixels_y, max_iterations, bottom_left_corner_x, bottom_left_corner_y, step, debug=False):
    command_bytes = struct.pack("HHI", no_pixels_x, no_pixels_y, max_iterations)

    command_bytes += bottom_left_corner_x.to_bytes(bytewidth, byteorder='little', signed=True)
    command_bytes += bottom_left_corner_y.to_bytes(bytewidth, byteorder='little', signed=True)
    command_bytes += step.to_bytes(bytewidth, byteorder='little', signed=True)
    command_bytes += bytes([0xa5])
    if debug: print(f"command: {str(bytes(command_bytes))}")

    dev.write(0x01, command_bytes)

    time.sleep(0.05)

    result = []
    try:
        while True:
            if debug: print("read")
            r = dev.read(0x81, 256, timeout=10)
            if debug: print("Got: "+ str(len(r)))
            if debug: print(str(r))
            result += r
    except usb.USBError:
        print(f"Got {len(result)} bytes from USB")

    if len(result) > 0:
        first_separator_index = result.index(0xa5)
        if first_separator_index != 7:
            print(f"Warning: Chop until index {first_separator_index}")
            result = result[first_separator_index+1:]
        pixels = [struct.unpack("HHBBBx", bytes(p)) for p in [result[i:i+8] for i in range(0, len(result), 8)] if len(p) == 8]
        for pixel in pixels:
            if debug: print(f"x: {pixel[0]} y: {pixel[1]} R: {pixel[2]} G: {pixel[3]} B: {pixel[4]}")

        print(f"Total number of pixels: {len(pixels)}")

        return pixels

def openImage(path):
    imageViewerFromCommandLine = {'linux':'xdg-open',
                                  'win32':'explorer',
                                  'darwin':'open'}[sys.platform]
    subprocess.run([imageViewerFromCommandLine, path])

corner_x = -2 << scale
corner_y = -5 << (scale - 2)
step = 1 << (scale - 9)

image_width  =  1920 # 256+128
image_height =  1300 # 256+64

def fix2float(fix):
    return fix/2**scale

print(f"left_corner_x: {corner_x/2**scale} corner_y: {corner_y/2**scale}, step: {step/2**scale}")
print(f"right_corner_x: {(corner_x + image_width*step)/2**scale} upper_corner_y: {(corner_y + image_height*step)/2**scale}")

from sys import argv
if __name__ == "__main__":
    if len(argv) > 1:
        if argv[1] == "plot":
            p = send_command(9, image_width, image_height, 256, corner_x, corner_y, step, debug=False)
            r = [e for e in p if e[3] & 0x1 > 0]
            x = [fix2float(corner_x) + fix2float(step) * e[0] for e in r]
            y = [fix2float(corner_y) + fix2float(step) * e[1] for e in r]

            coords = list(zip(x, y))
            print(coords)

            import matplotlib.pyplot as plt
            plt.scatter(x, y, c ="black")

            # To show the plot
            plt.show()
            code.interact(local=locals())

        if argv[1] == "debug":
            send_command(9, image_width, image_height, 255, corner_x, corner_y, step, debug=True)
            code.interact(local=locals())
    else:
        tstart = time.perf_counter()
        pixels = send_command(9, image_width - 1, image_height - 1, 255, corner_x, corner_y, step)
        tusb = time.perf_counter()
        print(f"USB transfer took: {tusb - tstart:0.4f} seconds")

        import numpy as np
        from matplotlib.image import imsave

        p = np.zeros((image_height, image_width, 3))

        for pixel in pixels:
            x     = pixel[0]
            y     = pixel[1]
            red   = pixel[2] / 255.0
            green = pixel[3] / 255.0
            blue  = pixel[4] / 255.0

            if x >= image_width:
                print(f"rogue pixel: {str(pixel)}")
                continue
            if y >= image_height:
                print(f"rogue pixel: {str(pixel)}")
                continue

            p[y][x][0] = red
            p[y][x][1] = green
            p[y][x][2] = blue

        pixels = []

        pix_conv = time.perf_counter()
        print(f"converting pixels took: {pix_conv - tusb:0.4f} seconds")

        outfilename = 'mandelbrot.png'
        imsave(outfilename, p)
        img_save = time.perf_counter()
        print(f"saving image took: {img_save - pix_conv:0.4f} seconds")
        openImage(outfilename)