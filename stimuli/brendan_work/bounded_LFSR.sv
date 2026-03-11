`default_nettype none

module bounded_LFSR #(
    parameter int W = 4
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         enable,
    input  logic [W-1:0] seed,
    input  logic         seed_load,

    input  logic [W-1:0] lo,
    input  logic [W-1:0] hi,

    output logic [W-1:0] addr,
    output logic         valid,
    output logic [W-1:0] diff
);

    logic [W-1:0] lfsr_state, lfsr_next;
    logic         feedback;

    // Simple LFSR taps for small demo widths
    assign feedback  = lfsr_state[W-1] ^ lfsr_state[1];
    assign lfsr_next = {lfsr_state[W-2:0], feedback};

    // Sequential candidate generator
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr_state <= 'h1;
        end else if (seed_load) begin
            lfsr_state <= (seed == '0) ? 'h1 : seed;
        end else if (enable) begin
            lfsr_state <= lfsr_next;
        end
    end

    // Candidate value
    assign addr = lfsr_state;

    // Constraint check: addr inside [lo:hi]
    assign valid = (addr >= lo) && (addr <= hi);

    // Whiteboard had: B - A = diff
    assign diff = addr - lo;

endmodule: bounded_LFSR