`default_nettype none

// Combinational next-state function for a Fibonacci LFSR
module LFSRNext #(
    parameter int W = 16,
    parameter logic [W-1:0] TAPS_MASK = 16'hB400  
    // example (x^16 + x^14 + x^13 + x^11 + 1)
) (
    input  logic [W-1:0] state,
    output logic [W-1:0] next
);
    logic feedback;
    // XOR of tapped bits
    assign feedback = ^(state & TAPS_MASK);
    // Shift and insert feedback 
    // (choose direction & convention and keep consistent)
    assign next = {state[W-2:0], feedback};
endmodule: LFSRNext


// Sequential candidate generator: 1 candidate per cycle
//     - seed-stable
//     - bounded transform (mask/fixed, optional pow2-range)
module BoundedLFSRCandidateGen #(
    parameter int SEED_W = 16,
    parameter int OUT_W  = 8,
    parameter logic [SEED_W-1:0] TAPS_MASK    = 16'hB400,
    parameter logic [SEED_W-1:0] DEFAULT_SEED = 16'h0001
) (
    input  logic                 clk,
    input  logic                 rst_n,

    input  logic [SEED_W-1:0]    seed_in,
    input  logic                 seed_load,

    input  logic                 enable,     // advance LFSR when 1

    // Bounding config (MVP)
    input  logic                 cfg_mask_en,
    input  logic [OUT_W-1:0]     cfg_mask,
    input  logic [OUT_W-1:0]     cfg_fixed_bits,

    input  logic                 cfg_pow2_range_en,
    input  logic [OUT_W-1:0]     cfg_L,
    input  logic [OUT_W-1:0]     cfg_pow2_mask,  // should be (2^k - 1)

    output logic [OUT_W-1:0]     candidate,
    output logic [SEED_W-1:0]    dbg_state
);

    logic [SEED_W-1:0] lfsr_state, lfsr_next;
    logic [OUT_W-1:0]  cand_pre, cand_bounded;

    // next-state combinational
    LFSRNext #(.W(SEED_W), .TAPS_MASK(TAPS_MASK)) u_next (
        .state(lfsr_state),
        .next (lfsr_next)
    );

    // seed sanitize
    function automatic logic [SEED_W-1:0] sanitize_seed(
        input logic [SEED_W-1:0] s
        );
        if (s == '0) sanitize_seed = DEFAULT_SEED;
        else         sanitize_seed = s;
    endfunction

    // sequential state update
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr_state <= DEFAULT_SEED;
        end else if (seed_load) begin
            lfsr_state <= sanitize_seed(seed_in);
        end else if (enable) begin
            lfsr_state <= lfsr_next;
        end
    end

    // candidate extraction: choose a consistent slice
    assign cand_pre = lfsr_state[OUT_W-1:0];

    // bounding transform (pure combinational)
    always_comb begin
        cand_bounded = cand_pre;

        // mask/fixed bits
        if (cfg_mask_en) begin
            cand_bounded = (cand_bounded & cfg_mask) | cfg_fixed_bits;
        end

        // pow2 range: L + (x & (2^k-1))
        if (cfg_pow2_range_en) begin
            cand_bounded = cfg_L + (cand_bounded & cfg_pow2_mask);
        end
    end

    assign candidate = cand_bounded;
    assign dbg_state = lfsr_state;

endmodule: BoundedLFSRCandidateGen


// Example combinational constraint checker (placeholder)
//     Others can replace this with a generated checker from IR.
module ConstraintCheckSimple #(
    parameter int W = 8
) (
    input  logic [W-1:0] x,

    input  logic         range_en,
    input  logic [W-1:0] L,
    input  logic [W-1:0] H,

    input  logic         neq_en,
    input  logic [W-1:0] K,

    output logic         ok
);
    logic ok_range, ok_neq;

    assign ok_range = (!range_en) || ((x >= L) && (x <= H));
    assign ok_neq   = (!neq_en)   || (x != K);

    assign ok = ok_range & ok_neq;
endmodule: ConstraintCheckSimple


// Glue: candidate -> combinational check -> valid/value
//     "invalid" simply means valid=0 for that cycle.
module StimulusGlue #(
    parameter int SEED_W = 16,
    parameter int OUT_W  = 8,
    parameter logic [SEED_W-1:0] TAPS_MASK    = 16'hB400,
    parameter logic [SEED_W-1:0] DEFAULT_SEED = 16'h0001
) (
    input  logic                 clk,
    input  logic                 rst_n,

    input  logic [SEED_W-1:0]    seed_in,
    input  logic                 seed_load,
    input  logic                 enable,

    // bounding cfg
    input  logic                 cfg_mask_en,
    input  logic [OUT_W-1:0]     cfg_mask,
    input  logic [OUT_W-1:0]     cfg_fixed_bits,
    input  logic                 cfg_pow2_range_en,
    input  logic [OUT_W-1:0]     cfg_L,
    input  logic [OUT_W-1:0]     cfg_pow2_mask,

    // constraint cfg (example)
    input  logic                 c_range_en,
    input  logic [OUT_W-1:0]     cL,
    input  logic [OUT_W-1:0]     cH,
    input  logic                 c_neq_en,
    input  logic [OUT_W-1:0]     cK,

    output logic                 out_valid,
    output logic [OUT_W-1:0]     out_value
);
    logic [OUT_W-1:0] cand;
    logic ok;

    BoundedLFSRCandidateGen #(
        .SEED_W(SEED_W),
        .OUT_W (OUT_W),
        .TAPS_MASK(TAPS_MASK),
        .DEFAULT_SEED(DEFAULT_SEED)
    ) u_gen (
        .clk(clk), .rst_n(rst_n),
        .seed_in(seed_in), .seed_load(seed_load),
        .enable(enable),
        .cfg_mask_en(cfg_mask_en),
        .cfg_mask(cfg_mask),
        .cfg_fixed_bits(cfg_fixed_bits),
        .cfg_pow2_range_en(cfg_pow2_range_en),
        .cfg_L(cfg_L),
        .cfg_pow2_mask(cfg_pow2_mask),
        .candidate(cand),
        .dbg_state()
    );

    ConstraintCheckSimple #(.W(OUT_W)) u_chk (
        .x(cand),
        .range_en(c_range_en),
        .L(cL), .H(cH),
        .neq_en(c_neq_en),
        .K(cK),
        .ok(ok)
    );

    // combinational solver semantics:
    // in this cycle: cand is either accepted (valid=1) or ignored (valid=0)
    assign out_valid = ok;
    assign out_value = cand;

endmodule