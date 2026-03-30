xrun -elaborate -uvm itf.sv 
xrun -elaborate -uvm stress.pkg.sv -coverage all
xrun -elaborate -uvm dut.sv
xrun -uvm tb_dut.sv -coverage all -covoverwrite -cov_cgsample -covdut dut
