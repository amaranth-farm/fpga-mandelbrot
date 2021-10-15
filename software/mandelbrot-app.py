#!/usr/bin/env python3

# this is a throwaway prototype
# so the code is highly experimental and sketchy

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
        tusb = time.perf_counter()
        print(f"USB transfer+unpacking took: {tusb - tstart:0.4f} seconds")

def openImage(path):
    imageViewerFromCommandLine = {'linux':'xdg-open',
                                  'win32':'explorer',
                                  'darwin':'open'}[sys.platform]
    subprocess.run([imageViewerFromCommandLine, path])

class FractalView():
    def __init__(self, *, center_x, center_y, radius, width, height, max_iterations=256) -> None:
        self.update(center_x=center_x, center_y=center_y, radius=radius, width=width, height=height, max_iterations=max_iterations)

    def update(self, *, center_x, center_y, radius, width, height, max_iterations=256) -> None:
        radius_pixels = min(width, height) / 2
        step = radius / radius_pixels

        self.step = float2fix(step)
        self.corner_x = float2fix(center_x - (width/2)  * step)
        self.corner_y = float2fix(center_y - (height/2) * step)
        self.width  = width
        self.height = height
        self.max_iterations = max_iterations

    def get_center(self):
        center_x = fix2float(self.corner_x) + fix2float(self.step) * (self.width  / 2)
        center_y = fix2float(self.corner_y) + fix2float(self.step) * (self.height / 2)
        return [center_x, center_y]

    def get_radius(self):
        radius_pixels = min(self.width, self.height) / 2
        return fix2float(self.step) * radius_pixels

    def to_string(self):
        x, y = self.get_center()
        return f"center_x: {x}, center_y: {y}, radius: {self.get_radius()}"

default_view = FractalView(center_x=-0.75,    center_y=0,             radius=1.25,        max_iterations=170,  width=1550, height=1080)
swirl        = FractalView(center_x=-0.74791, center_y=0.0888909763,  radius=6.9921e-5,   max_iterations=4096, width=1550, height=1080)

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

        if argv[1] == "gui":
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository     import GLib, Gtk, Gdk
            from gi.repository.Gtk import DrawingArea
            import cairo

            class GuiHandler:
                surface = None
                builder = None
                canvas  = None

                width  = 0
                weight = 0

                drawing = False
                view = default_view

                def __init__(self, builder) -> None:
                    self.builder = builder
                    centerx_widget    = builder.get_object("center_x")
                    centery_widget    = builder.get_object("center_y")
                    radius_widget     = builder.get_object("radius")
                    iterations_widget = builder.get_object("iterations")

                    center_x, center_y = view.get_center()
                    radius             = view.get_radius()
                    iterations         = view.max_iterations

                    centerx_widget   .set_text(str(center_x))
                    centery_widget   .set_text(str(center_y))
                    radius_widget    .set_text(str(radius))
                    iterations_widget.set_text(str(iterations))

                    self.updateImageSurfaceIfNeeded()

                def painter(self):
                    drawing_start = time.perf_counter()
                    try:
                        cr = cairo.Context(self.surface)
                        pixel_count = 0
                        while True:
                            # get() will exit this thread if the
                            # queue is empty
                            pixel = pixel_queue.get()
                            pixel_count += 1

                            x     = pixel[0]
                            y     = pixel[1]

                            red, green, blue = colortable[pixel[2] & 0xf]
                            red   /= 255.0
                            green /= 255.0
                            blue  /= 255.0

                            maxed = pixel[2] >> 7

                            def draw_pixel():
                                if not maxed:
                                    cr.set_source_rgb(red, green, blue)
                                else:
                                    cr.set_source_rgb(0, 0, 0)

                                cr.rectangle(x, y, 1.5, 1.5)
                                cr.fill()
                                self.surface.mark_dirty_rectangle(x, y, 1, 1)
                                if pixel_count % 500 == 0:
                                    self.canvas.queue_draw()

                                return False

                            Gdk.threads_enter()
                            draw_pixel()
                            Gdk.threads_leave()
                            pixel_queue.task_done()

                    finally:
                        now = time.perf_counter()
                        print(f"drawing took: {now - drawing_start:0.4f} seconds")

                def onDestroy(self, *args):
                    Gtk.main_quit()

                def updateImageSurfaceIfNeeded(self):
                    self.canvas = canvas = builder.get_object("canvas")
                    width  = canvas.get_allocated_size().allocation.width
                    height = canvas.get_allocated_size().allocation.height
                    if self.surface is None or self.width != width or self.height != height:
                        self.surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
                        self.width, self.height = width, height

                def onButtonPressed(self, button):
                    self.updateImageSurfaceIfNeeded()

                    center_x   = float(builder.get_object("center_x").get_text())
                    center_y   = float(builder.get_object("center_y").get_text())
                    radius     = float(builder.get_object("radius").get_text())
                    iterations = int  (builder.get_object("iterations").get_text())

                    self.view.update(center_x=center_x, center_y=center_y, radius=radius, width=self.width, height=self.height, max_iterations=iterations)
                    print(self.view.to_string())

                    cr = cairo.Context(self.surface)
                    cr.set_source_rgb(0, 0, 0)
                    cr.rectangle(0, 0, self.width, self.height)
                    cr.fill()

                    view = self.view
                    view.width  = self.width
                    view.height = self.height
                    usb_reader = lambda: send_command(9, view, debug=False)
                    usb_thread = threading.Thread(target=usb_reader, daemon=True)
                    usb_thread.start()

                    painter_thread = threading.Thread(target=lambda: self.painter(), daemon=True)
                    painter_thread.start()

                def onDraw(self, canvas: DrawingArea, cr: cairo.Context):
                    cr.set_source_surface(self.surface, 0, 0)
                    cr.paint()

            builder = Gtk.Builder()
            builder.add_from_file("mandelbrot-client-gui.glade")
            handler = GuiHandler(builder)
            builder.connect_signals(handler)

            window = builder.get_object("window")
            window.connect("destroy", Gtk.main_quit)
            window.show_all()

            Gdk.threads_init()
            Gtk.main()
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
                if not maxed:
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