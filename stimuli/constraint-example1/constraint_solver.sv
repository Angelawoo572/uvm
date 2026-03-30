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

    rst_n_assign_module rst_n_assign_module_solver (.lfsr_in(lfsr_output), .data(solver_output[1]));
    rst_n_assign_module rst_n_assign_module_solver_2 (.lfsr_in(lfsr_output), .data(solver_output[2]));
    addr_i_assign_module addr_i_assign_module_solver (.lfsr_in(lfsr_output), .data(solver_output[3]));
    we_assign_module we_assign_module_solver (.lfsr_in(lfsr_output), .data(solver_output[4]));
    re_assign_module re_assign_module_solver (.lfsr_in(lfsr_output), .data(solver_output[5]));
    rst_n_assign_module rst_n_assign_module_solver_6 (.lfsr_in(lfsr_output), .data(solver_output[6]));
    addr_i_assign_module addr_i_assign_module_solver_7 (.lfsr_in(lfsr_output), .data(solver_output[7]));
    we_assign_module we_assign_module_solver_8 (.lfsr_in(lfsr_output), .data(solver_output[8]));
    re_assign_module re_assign_module_solver_9 (.lfsr_in(lfsr_output), .data(solver_output[9]));
    rst_n_assign_module rst_n_assign_module_solver_10 (.lfsr_in(lfsr_output), .data(solver_output[10]));
    addr_i_assign_module addr_i_assign_module_solver_11 (.lfsr_in(lfsr_output), .data(solver_output[11]));
    we_assign_module we_assign_module_solver_12 (.lfsr_in(lfsr_output), .data(solver_output[12]));
    re_assign_module re_assign_module_solver_13 (.lfsr_in(lfsr_output), .data(solver_output[13]));

endmodule: constraint_solver

module rst_n_assign_module (
    input  logic [31:0] lfsr_in,
    output logic [31:0] data
);

    assign data = 1'b0;

endmodule

module addr_i_assign_module (
    input  logic [31:0] lfsr_in,
    output logic [31:0] data
);

    assign data = 4;

endmodule

module we_assign_module (
    input  logic [31:0] lfsr_in,
    output logic [31:0] data
);

    assign data = 1'b1;

endmodule

module re_assign_module (
    input  logic [31:0] lfsr_in,
    output logic [31:0] data
);

    assign data = 1'b0;

endmodule