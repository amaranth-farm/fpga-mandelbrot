#!/usr/bin/env python3

# this is a throwaway prototype
# so the code is highly experimental

import time
import struct
import usb
import code
import sys
import subprocess
import threading, queue

dev=usb.core.find(idVendor=0x1209, idProduct=0xDECA)

debug=False
if debug: print(dev)

scale = 8*8

def fix2float(fix):
    return fix/2**scale

def float2fix(f):
    return int(f*2**scale)

pixel_queue = queue.Queue()

def send_command(bytewidth, view, debug=False):
    tstart = time.perf_counter()
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
            while len(result) >= 6:
                packet, result = (result[:6], result[6:])
                assert packet[-1] == 0xa5
                pixel = struct.unpack("HHBx", bytes(packet))
                pixel_queue.put(pixel)
    except usb.USBError:
        print(f"Got {len(result)} bytes from USB")
    tusb = time.perf_counter()
    print(f"USB transfer+unpacking took: {tusb - tstart:0.4f} seconds")

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


default_view = FractalView(center_x=-0.75,    center_y=0,             radius=2.5,         max_iterations=170, width=1550, height=1080)
swirl        = FractalView(center_x=-0.74791, center_y=0.0888909763,  radius=6.9921e-5,   max_iterations=4096)

view = default_view

# the beautiful colors from the wikipedia
# mandelbrot page fractals
colortable = [
    [ 66,  30,  15],
    [ 25,   7,  26],
    [  9,   1,  47],
    [  4,   4,  73],
    [  0,   7, 100],
    [ 12,  44, 138],
    [ 24,  82, 177],
    [ 57, 125, 209],
    [134, 181, 229],
    [211, 236, 248],
    [241, 233, 191],
    [248, 201,  95],
    [255, 170,   0],
    [204, 128,   0],
    [153,  87,   0],
    [106,  52,   3],
]

from sys import argv
if __name__ == "__main__":
    if len(argv) > 1:
        if argv[1] == "debug":
            send_command(9, view, debug=True)
            code.interact(local=locals())
    else:
        tstart = time.perf_counter()

        usb_reader = lambda: send_command(9, view, debug=False)
        usb_thread = threading.Thread(target=usb_reader, daemon=True)
        usb_thread.start()

        import numpy as np
        from matplotlib.image import imsave

        p = np.zeros((view.height, view.width, 3))

        def unpacker():
            while True:
                pixel = pixel_queue.get()
                x     = pixel[0]
                y     = pixel[1]

                if x >= view.width:
                    print(f"rogue pixel: {str(pixel)}")
                    continue
                if y >= view.height:
                    print(f"rogue pixel: {str(pixel)}")
                    continue

                red, green, blue = colortable[pixel[2] & 0xf]
                maxed = pixel[2] >> 7
                if not maxed > 0:
                    p[y][x][0] = red   / 255.0
                    p[y][x][1] = green / 255.0
                    p[y][x][2] = blue  / 255.0

                pixel_queue.task_done()

        unpacker_thread = threading.Thread(target=unpacker, daemon=True)
        unpacker_thread.start()

        pixel_queue.join()
        usb_thread.join()

        pix_conv = time.perf_counter()
        outfilename = 'mandelbrot.png'
        imsave(outfilename, p)
        img_save = time.perf_counter()
        print(f"saving image took: {img_save - pix_conv:0.4f} seconds")
        openImage(outfilename)