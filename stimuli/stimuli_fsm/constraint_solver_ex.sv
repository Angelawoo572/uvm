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

    // e.g. dist (20% error rate) (dist example)
    dist_example_slave_err dist_example (
        .lfsr_in(lfsr_output),
        .slave_err(solver_output[1]) 
    );

    // e.g. bit assign example (parity example?)
    const_wrap_addr const_wrap (
        .lfsr_in(lfsr_output),
        .addr(solver_output[2])
    );

    // e.g. enum (enum example)
    enum_example enum_example (
        .lfsr_in(lfsr_output),
        .enum_out(solver_output[3])
    );

    // e.g. comp

endmodule: constraint_solver

// dist_example
module dist_example_slave_err(input logic [31:0] lfsr_in, output logic [31:0] slave_err);
logic [63:0] scaled_rand;

// Scaling: Map LFSR to [0 : 99]
assign scaled_rand = lfsr_in % 100;

always_comb begin
    case (scaled_rand) inside
        [0:19]: slave_err = 1;
        [20:99]: slave_err = 0;
        default: slave_err = '0; // Should not be reached
    endcase
end
endmodule

// bit assign example
module const_wrap_addr (
    input  logic [31:0] lfsr_in,
    output logic [31:0] addr
);

    assign addr[31:2] = lfsr_in[31:2];
    assign addr[1:0] = 2'h0;

endmodule

module enum_example (
    input  logic [31:0] lfsr_in,
    output logic [31:0] enum_out
);
    typedef enum logic [7:0] {
        RAM  = 8'd0,
        CPU  = 8'd1,
        ROM  = 8'd2,
        ROM2 = 8'd123,
        CPU2 = 8'd124
    } addr_t;
    addr_t addr_enum;

    always_comb begin
        unique case (lfsr_in % 5)
            0: addr_enum = RAM;
            1: addr_enum = CPU;
            2: addr_enum = ROM;
            3: addr_enum = ROM2;
            4: addr_enum = CPU2;
        endcase
    end

    assign enum_out = addr_enum;
endmodule