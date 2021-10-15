#!/bin/bash
export GENERATE_VCDS=0
python3 -m unittest mandelbrot.MandelbrotTest
python3 -m unittest fractalmanager.FractalManagerTest