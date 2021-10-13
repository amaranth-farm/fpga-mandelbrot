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

def fix2float(fix):
    return fix/2**scale

def float2fix(f):
    return int(f*2**scale)

def send_command(bytewidth, view, debug=False):
    command_bytes = struct.pack("HHI", view.width-1, view.height-1, view.max_iterations)
    command_bytes += view.corner_x.to_bytes(bytewidth, byteorder='little', signed=True)
    command_bytes += view.corner_y.to_bytes(bytewidth, byteorder='little', signed=True)
    command_bytes += view.step    .to_bytes(bytewidth, byteorder='little', signed=True)
    command_bytes += bytes([0xa5])
    if debug: print(f"command: {[hex(b) for b in command_bytes]}")

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

class FractalView():
    def __init__(self, *, center_x, center_y, radius, width=1920, height=1080, max_iterations=256) -> None:
        radius_pixels = min(width, height) / 2
        step = radius / radius_pixels / 2

        self.step = float2fix(step)
        self.corner_x = corner_x = float2fix(center_x - (width/2)  * step)
        self.corner_y = corner_y = float2fix(center_y - (height/2) * step)
        self.width  = width
        self.height = height
        self.max_iterations = max_iterations
        if debug:
            print(f"left_corner_x: {corner_x/2**scale} corner_y: {corner_y/2**scale}, step: {self.step/2**scale}")
            print(f"right_corner_x: {(corner_x + width*self.step)/2**scale} upper_corner_y: {(corner_y + height*self.step)/2**scale}")


default_view = FractalView(center_x=-0.75,    center_y=0,             radius=2.5,         max_iterations=170)
swirl        = FractalView(center_x=-0.74791, center_y=0.0888909763, radius=6.9921e-5,   max_iterations=4096)

view = default_view

from sys import argv
if __name__ == "__main__":
    if len(argv) > 1:
        if argv[1] == "plot":
            p = send_command(9, view, debug=False)
            r = [e for e in p if e[3] & 0x1 > 0]
            x = [fix2float(view.corner_x) + fix2float(view.step) * e[0] for e in r]
            y = [fix2float(view.corner_y) + fix2float(view.step) * e[1] for e in r]

            coords = list(zip(x, y))
            print(coords)

            import matplotlib.pyplot as plt
            plt.scatter(x, y, c ="black")

            # To show the plot
            plt.show()

        if argv[1] == "debug":
            send_command(9, view, debug=True)
            code.interact(local=locals())
    else:
        tstart = time.perf_counter()
        pixels = send_command(9, view, debug=False)
        tusb = time.perf_counter()
        print(f"USB transfer took: {tusb - tstart:0.4f} seconds")

        import numpy as np
        from matplotlib.image import imsave

        p = np.zeros((view.height, view.width, 3))

        for pixel in pixels:
            x     = pixel[0]
            y     = pixel[1]
            red   = pixel[2] / 255.0
            green = pixel[3] / 255.0
            blue  = pixel[4] / 255.0

            if x >= view.width:
                print(f"rogue pixel: {str(pixel)}")
                continue
            if y >= view.height:
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