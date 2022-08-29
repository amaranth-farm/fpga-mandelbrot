# FPGA Mandelbrot
FPGA boards as mandelbrot accelerators.
This is a hobby project to explore parallel computation/pipelining
on a FPGA.

## Supported Boards
* The Terasic DECA board over high speed USB2

## Current Status
* Terasic DECA board working: nine 72 bit fixed point mandelbrot cores run at 60 MHz over high speed USB2
* basic interactive Gtk app written in python works
* imgui based app written in Nim works
* produces beautiful images:
![image](https://user-images.githubusercontent.com/148607/137055848-e216424f-0ad3-4c40-96b1-d512d16e04b4.png)

## How to build
```bash
$ ./initialize-python-environment.sh
$ . ./venv/bin/activate
$ python3 gateware/deca_mandelbrot.py --keep
```

## How to run the testbench
```bash
$ cd gateware/
$ ./run-tests.sh
```
If you want to generate .vcd traces please set the `GENERATE_VCDS` variable in the file to `1`


