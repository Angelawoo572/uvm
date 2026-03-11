`default_nettype none

module constraint_solver #(
    parameter int DATA_W = 32,
    parameter int NUM_CONSTRAINTS = 8
) (
    input  logic [DATA_W-1:0] lfsr_output,
    output logic [DATA_W-1:0] solver_output [NUM_CONSTRAINTS]
);
     // e.g. constraint_id = 0: odd, 1: even
    assign solver_output[0] = {lfsr_output[DATA_W-1:1], 1'b1};
    assign solver_output[1] = {lfsr_output[DATA_W-1:1], 1'b0};
endmodule: constraint_solver