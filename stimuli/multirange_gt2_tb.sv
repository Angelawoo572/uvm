`timescale 1ps/1ps

module multirange_tb();

    localparam WIDTH = 32;

    logic [WIDTH-1:0] lfsr_in;
    logic [WIDTH-1:0] result;

    multirange_solver #(
    .WIDTH(32),
    .N_REGIONS(3)
    ) u_solver (
    .lfsr_in    (lfsr_in),
    .min_bounds ('{32'd0,  32'd50, 32'd90}),
    .max_bounds ('{32'd10, 32'd60, 32'd100}),
    .result     (result)
    );

    initial begin
        lfsr_in = $urandom;
        
        #1 $display("result is %d", result);
        #1 $finish;
        
    end


endmodule