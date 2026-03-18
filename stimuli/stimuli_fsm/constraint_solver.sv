`default_nettype none

module constraint_solver #(
    parameter int DATA_W = 32,
    parameter int NUM_CONSTRAINTS = 8
) (
    input  logic [DATA_W-1:0] lfsr_output,
    output logic [DATA_W-1:0] solver_output [NUM_CONSTRAINTS]
);  
    // immediate result
    assign solver_output[0] = lfsr_output;

    // TODO: Instantiate constraint solvers here

endmodule: constraint_solver

// TODO: Define constraint solvers here