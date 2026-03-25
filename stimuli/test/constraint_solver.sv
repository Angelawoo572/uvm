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
    payload_dist_module payload_dist_module_solver (.lfsr_in(lfsr_output), .data(solver_output[2]));
    data_dist_module data_dist_module_solver (.lfsr_in(lfsr_output), .data(solver_output[3]));
    assign solver_output[4] = lfsr_output;
    data_bit_assign_module data_bit_assign_module_solver (.lfsr_in(lfsr_output), .data(solver_output[5]));
    data_bit_slice_module data_bit_slice_module_solver (.lfsr_in(lfsr_output), .data(solver_output[6]));

endmodule: constraint_solver

module rst_n_assign_module (
    input  logic [31:0] lfsr_in,
    output logic [31:0] data
);

    assign data = 1'b0;

endmodule

// --- Generated Weighted Random Logic for 'payload' ---
// Input LFSR Width: 32 bits
module payload_dist_module (input logic [31:0] lfsr_in, output logic [31:0] data);
logic [63:0] scaled_rand;

// Scaling: Map LFSR to [0 : 99]
assign scaled_rand = (lfsr_in * 100) >> 32;

always_comb begin
    case (scaled_rand) inside
        [0:4]: data = 0;
        [5:99]: data = 1;
        default: data = '0; // Should not be reached
    endcase
end
endmodule

// --- Generated Weighted Random Logic for 'data' ---
// Input LFSR Width: 32 bits
module data_dist_module (input logic [31:0] lfsr_in, output logic [31:0] data);
logic [63:0] scaled_rand;

// Scaling: Map LFSR to [0 : 99]
assign scaled_rand = (lfsr_in * 100) >> 32;

always_comb begin
    case (scaled_rand) inside
        [0:9]: data = 0;
        [10:89]: data = 20;
        [90:99]: data = 12;
        default: data = '0; // Should not be reached
    endcase
end
endmodule

module data_bit_assign_module (
    input  logic [31:0] lfsr_in,
    output logic [31:0] data
);

    assign data[31:1] = lfsr_in[31:1];
    assign data[0] = 1'b1;

endmodule

module data_bit_slice_module (
    input  logic [31:0] lfsr_in,
    output logic [31:0] data
);

    assign data[31:8] = lfsr_in[31:8];
    assign data[7:4] = (lfsr_in[7:4] == 4'b1111) ? (lfsr_in[7:4] ^ {{3{1'b0}},1'b1}) : lfsr_in[7:4];
    assign data[3:0] = lfsr_in[3:0];

endmodule