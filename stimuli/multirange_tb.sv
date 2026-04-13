`timescale 1ps/1ps
module multirange_tb();

    localparam WIDTH = 32;

    logic [WIDTH-1:0] lfsr_in;
    logic [WIDTH-1:0] min0;
    logic [WIDTH-1:0] max0;
    logic [WIDTH-1:0] min1;
    logic [WIDTH-1:0] max1;
    logic [WIDTH-1:0] result;

    multirange_solver dut (.*);

    initial begin
        lfsr_in = $urandom;
        min0 = 32'd0;
        max0 = 32'd15;
        min1 = 32'd32;
        max1 = 32'd63;
        
        #1 $display("result is %d", result);
        #1 $finish;
        
    end


endmodule