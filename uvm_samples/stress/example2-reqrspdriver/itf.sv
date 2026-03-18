interface itf (input bit clk);
	parameter ADDR_WIDTH = 99; // default value set to invalid to force overwriting at instance time 
	parameter DATA_WIDTH = 99; // default value set to invalid to force overwriting at instance time
	parameter ARRAY_SIZE = 99;
	bit rst_n; // active 0 asynchronous reset
	logic re; // active 1 read enable
	logic we; // active 1 write enable
	logic [ADDR_WIDTH-1:0] addr_i; // address input
	logic [DATA_WIDTH-1:0] data_i; // data input
	logic [DATA_WIDTH-1:0] data_o; // data input
	logic [ARRAY_SIZE-1:0] valid;

	// input means signal can only be sampled
	// output means signal can only be driven
	// inout means both
	clocking drv_cb @(posedge clk);
		default input #1step output #1;
		output rst_n, re, we, addr_i, data_i; 
		input data_o;
	endclocking

	clocking mon_cb @(posedge clk);
		default input #1step output #1;
		input rst_n, re, we, addr_i, data_i; 
		input data_o;
	endclocking
endinterface

