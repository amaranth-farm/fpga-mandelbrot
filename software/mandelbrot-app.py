#!/usr/bin/env python3

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

def send_command(bytewidth, view, iterations=10000, debug=False):
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
            r = dev.read(0x81, 256, timeout=max(10, iterations//1000))
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

        self.radius = radius
        self.center_x = center_x
        self.center_y = center_y
        self.step = float2fix(step)
        self.corner_x = float2fix(center_x - (width/2)  * step)
        self.corner_y = float2fix(center_y - (height/2) * step)
        self.width  = width
        self.height = height
        self.max_iterations = max_iterations

    def update_size(self, width, height, iterations):
        self.update(center_x=self.center_x, center_y=self.center_y, radius=self.radius, width=width, height=height, max_iterations=iterations)

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

    def get_lower_left_corner(self):
        return (fix2float(self.corner_x), fix2float(self.corner_y))

    def get_upper_right_corner(self):
        x = fix2float(self.corner_x) + self.width  * fix2float(self.step)
        y = fix2float(self.corner_y) + self.height * fix2float(self.step)
        return (x, y)


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

colortable_float = [[i[0] / 255.0, i[1] / 255.0, i[2] / 255.0] for i in colortable]

def gtk_gui(orbits=False):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository           import GLib, Gtk, Gdk
    from gi.repository.Gtk       import DrawingArea
    from gi.repository.GdkPixbuf import Pixbuf, Colorspace
    import cairo

    class GuiHandler:
        pixbuf = None
        builder = None
        canvas  = None

        width  = 0
        weight = 0

        drawing = False
        view = default_view

        def __init__(self, builder) -> None:
            self.builder = builder
            self.pixels = None
            centerx_widget    = builder.get_object("center_x")
            centery_widget    = builder.get_object("center_y")
            radius_widget     = builder.get_object("radius")
            iterations_widget = builder.get_object("iterations")
            zero_y            = builder.get_object("zero_y")

            center_x, center_y = view.get_center()
            radius             = view.get_radius()
            iterations         = view.max_iterations

            centerx_widget   .set_text(str(center_x))
            centery_widget   .set_text(str(center_y))
            radius_widget    .set_text(str(radius))
            iterations_widget.set_text(str(iterations))

            self.updateImageBufferIfNeeded()

        def painter(self):
            drawing_start = time.perf_counter()
            try:
                channels  = 3
                rowstride = self.width * channels
                pixel_count = 0
                while True:
                    # get() will exit this thread if the
                    # queue is empty
                    pixel = pixel_queue.get()
                    pixel_count += 1

                    x     = pixel[0]
                    y     = self.view.height - pixel[1]

                    red, green, blue = colortable[pixel[2] & 0xf]
                    maxed = pixel[2] >> 7

                    pixel_index = y * rowstride + x * channels

                    if maxed:
                        red = green = blue = 0

                    if pixel_index + 2 < len(self.pixels):
                        self.pixels[pixel_index]     = red
                        self.pixels[pixel_index + 1] = green
                        self.pixels[pixel_index + 2] = blue

                    if pixel_count % (2 * self.width) == 0:
                        GLib.idle_add(self.canvas.queue_draw)

                    pixel_queue.task_done()

            finally:
                now = time.perf_counter()
                print(f"drawing took: {now - drawing_start:0.4f} seconds")

        def onDestroy(self, *args):
            Gtk.main_quit()

        def updateImageBufferIfNeeded(self):
            self.canvas = canvas = builder.get_object("canvas")
            width  = canvas.get_allocated_size().allocation.width
            height = canvas.get_allocated_size().allocation.height
            if (self.pixbuf is None or self.width != width or self.height != height) and width > 0 and height > 0:
                print(f"w {width} h {height}")
                self.pixels = bytearray((height + 1) * 3 * width)
                self.width, self.height = width, height

        def getViewParameterWidgets(self):
            center_x   = builder.get_object("center_x")
            center_y   = builder.get_object("center_y")
            radius     = builder.get_object("radius")
            return [center_x, center_y, radius]

        def getViewParameters(self):
            getValue = lambda w: float(w.get_text())
            return map(getValue, self.getViewParameterWidgets())

        def onUpdateButtonPress(self, button):
            self.updateImageBufferIfNeeded()

            center_x, center_y, radius = self.getViewParameters()
            iterations = int  (builder.get_object("iterations").get_text())

            self.view.update(center_x=center_x, center_y=center_y, radius=radius, width=self.width, height=self.height, max_iterations=iterations)
            print(self.view.to_string())

            # clear out image
            for i in range(len(self.pixels)):
                self.pixels[i] = 0

            view        = self.view
            view.width  = self.width
            view.height = self.height
            usb_reader = lambda: send_command(9, view, view.max_iterations, debug=False)
            usb_thread = threading.Thread(target=usb_reader, daemon=True)
            usb_thread.start()

            painter_thread = threading.Thread(target=lambda: self.painter(), daemon=True)
            painter_thread.start()

        def onCanvasButtonPress(self, canvas, event):
            step = fix2float(self.view.step)
            x = fix2float(self.view.corner_x) + (event.x * step)
            y = fix2float(self.view.corner_y) + ((self.view.height - event.y) * step)
            center_x, center_y, _ = self.getViewParameterWidgets()
            center_x.set_text(str(x))
            center_y.set_text(str(y))

        crosshairs = None

        def onCanvasMotion(self, canvas, event):
            step = fix2float(self.view.step)
            x = fix2float(self.view.corner_x) + (event.x * step)
            y = fix2float(self.view.corner_y) + ((self.view.height - event.y) * step)
            self.crosshairs = [(event.x, event.y), (x,y)]
            canvas.queue_draw()

        def onDraw(self, canvas: DrawingArea, cr: cairo.Context):
            if not self.pixels is None:
                pixbuf = Pixbuf.new_from_data(bytes(self.pixels), Colorspace.RGB, False, 8, self.width, self.height + 1, self.width * 3)
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
            if not self.crosshairs is None:
                x, y = self.crosshairs[0]
                cr.set_source_rgb(1, 1, 1)
                cr.set_line_width(1)
                cr.move_to(x, 0)
                cr.line_to(x, self.view.height)
                cr.move_to(0, y)
                cr.line_to(self.view.width, y)
                cr.stroke()

                cr.set_font_size(20)
                cr.move_to(20, 20)
                cr.show_text(f"x: {str(self.crosshairs[1][0])}")
                cr.move_to(20, 40)
                cr.show_text(f"y: {str(self.crosshairs[1][1])}")


    builder = Gtk.Builder()
    builder.add_from_file("mandelbrot-client-gui.ui")
    handler = GuiHandler(builder)
    builder.connect_signals(handler)

    window = builder.get_object("window")
    window.connect("destroy", Gtk.main_quit)
    window.show_all()

    Gtk.main()

from sys import argv
if __name__ == "__main__":
    if len(argv) > 1:
        if argv[1] == "debug":
            send_command(9, view, debug=True)

        elif argv[1] == "png":
            tstart = time.perf_counter()

            if len(argv) >= 4:
                width  = int(argv[2])
                height = int(argv[3])
                if (len(argv) == 5):
                    iterations = int(argv[4])
                    view.update_size(width, height, iterations)
                else:
                    view.update_size(width, height, 170)

            print("Rendering view to PNG:")
            lower_left = view.get_lower_left_corner()
            print(f"lower left corner: x: {lower_left[0]} y: {lower_left[1]}")
            upper_right = view.get_upper_right_corner()
            print(f"upper right corner: x: {upper_right[0]} y: {upper_right[1]}")
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

                    red, green, blue = colortable_float[pixel[2] & 0xf]
                    maxed = pixel[2] >> 7
                    if not maxed:
                        p[y][x][0] = red
                        p[y][x][1] = green
                        p[y][x][2] = blue

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

        elif argv[1] == "orbits":
            gtk_gui(orbits=True)

    else:
        gtk_gui()