# Package

version       = "0.1.0"
author        = "Hans Baier"
description   = "Mandelbrot client for kintex-mandelbrot"
license       = "MIT"
srcDir        = "src"
bin           = @["fpgamandelbrot"]
backend       = "cpp"


# Dependencies

requires "nim >= 1.6.6"
requires "nimgl >= 0.3.6"
requires "byteutils"
requires "imgui"
requires "libusb"
requires "nint128"
requires "struct"