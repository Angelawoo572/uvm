xrun -elaborate -uvm itf.sv
xrun -elaborate -uvm stress.pkg.sv
xrun -elaborate -uvm dut.sv
xrun -uvm -gui -debug tb_dut.sv
