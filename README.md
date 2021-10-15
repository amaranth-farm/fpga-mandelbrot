# deca-mandelbrot
The Terasic DECA board as a mandelbrot accelerator.
This is a hobby project to explore parallel computation/pipelining
on a FPGA.

## current status
* working: nine 72 bit fixed point mandelbrot cores run at 60 MHz
* still needs improvement: better resource usage, pipelining, more efficient USB data transfer
* very rough client app with hardwired parameters
* produces beautiful images:
![image](https://user-images.githubusercontent.com/148607/137055848-e216424f-0ad3-4c40-96b1-d512d16e04b4.png)

## how to build
```bash
$ ./initialize-python-environment.sh
$ . ./venv/bin/activate
$ python3 gateware/deca_mandelbrot.py --keep
```

## how to run the testbench
```bash
$ cd gateware/
$ ./run-tests.sh
```
If you want to generate .vcd traces please set the `GENERATE_VCDS` variable in the file to `1`


