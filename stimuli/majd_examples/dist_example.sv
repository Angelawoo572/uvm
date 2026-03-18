// --- Generated Weighted Random Logic for 'slave_err' ---
// Input LFSR Width: 32 bits
module dist_example_slave_err(input logic [31:0] lfsr_in, output logic [31:0] slave_err);
logic [63:0] scaled_rand;

// Scaling: Map LFSR to [0 : 99]
assign scaled_rand = (lfsr_in * 100) >> 32;

always_comb begin
    case (scaled_rand) inside
        [0:19]: slave_err = 1;
        [20:99]: slave_err = 0;
        default: slave_err = '0; // Should not be reached
    endcase
end
endmodule