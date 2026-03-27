module tb();

import uvm_pkg::*;
import stress_pkg::*;

`include "constants.svh"

bit clk;
initial begin
	clk = 0;
end

itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH), .ARRAY_SIZE(ARRAY_SIZE)) myitf(.clk(clk));
dut mydut(.myitf(myitf));

always begin
        #10;
        clk = !clk;
end

initial begin
	clk = 0;
	uvm_config_db#(virtual itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH), .ARRAY_SIZE(ARRAY_SIZE)) )::set(null, "tb", "vif", myitf);
    	run_test("example2");
end
endmodule


