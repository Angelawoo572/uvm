`default_nettype none

// Method 1:
// Synthesizable RTL for: addr inside [A:3]
// Generalize it to addr inside [lo:hi].
// Intended constraint is exactly [1:3], tie lo=1, hi=3.

module method1_inside_range #(
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

endmodule: method1_inside_range

// ============================================================
// TB for method 1
// ============================================================
module tb_method1_inside_range;

    localparam int W = 4;

    logic         clk;
    logic         rst_n;
    logic         enable;
    logic [W-1:0] seed;
    logic         seed_load;
    logic [W-1:0] lo, hi;
    logic [W-1:0] addr;
    logic         valid;
    logic [W-1:0] diff;

    method1_inside_range #(.W(W)) dut (
        .clk(clk),
        .rst_n(rst_n),
        .enable(enable),
        .seed(seed),
        .seed_load(seed_load),
        .lo(lo),
        .hi(hi),
        .addr(addr),
        .valid(valid),
        .diff(diff)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 0;
        rst_n = 0;
        enable = 0;
        seed = 4'd5;
        seed_load = 0;
        lo = 4'd1;   // corresponds to [1:3]
        hi = 4'd3;

        #12;
        rst_n = 1;

        #10;
        seed_load = 1;
        #10;
        seed_load = 0;
        enable = 1;

        repeat (12) begin
            @(posedge clk);
            $display("[M1] t=%0t addr=%0d valid=%0b diff=%0d  range=[%0d:%0d]",
                     $time, addr, valid, diff, lo, hi);
        end

        $finish;
    end

endmodule: tb_method1_inside_range