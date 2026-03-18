xrun -elaborate itf.sv
xrun -elaborate -uvm stress.pkg.sv
xrun -elaborate dut.sv
xrun -uvm -gui -debug tb_dut.sv
