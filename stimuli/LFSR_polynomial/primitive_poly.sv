`default_nettype none
`include "../stimuli_fsm/seq_stim_if.svh"

// Generic polynomial-parameterized Fibonacci XOR LFSR
//   - No hardcoded tap table inside the LFSR module
//   - Maximal-length behavior IF caller supplies a primitive polynomial
//   - Never allow all-zero state (XOR-LFSR lock-up state)
//
// Polynomial encoding:
//   POLY[i] corresponds to coefficient of x^i, for i = 1..W
//   Expected:
//      POLY[W] = 1   (highest-order term x^W)
//      POLY[1] = 1   (constant/feedback connectivity side)
//   Example meaning:
//      x^8 + x^6 + x^5 + x + 1
//   can be encoded by setting POLY[8], POLY[6], POLY[5], POLY[1] = 1

//   - This module itself does NOT prove primitiveness.
//   - It assumes the supplied POLY is primitive for width W.
//   - With nonzero seed + primitive POLY, the internal state cycle is 2^W - 1.
module lfsr_poly #(
    parameter int W = 32,
    parameter logic [W:1] POLY = '0,
    parameter logic [W-1:0] DEFAULT_SEED = {{(W-1){1'b0}}, 1'b1}
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         enable,
    input  logic         seed_load,
    input  logic [W-1:0] seed,
    output logic [W-1:0] state
);

    logic [W-1:0] next_state;
    logic         feedback;
    int           i;

    // Feedback computation
    //
    // We use the current state bits selected by POLY[1:W].
    // The exact sequence depends on the chosen representation,
    // but once a primitive polynomial is used consistently,
    // the internal state sequence is maximal-length.
    always_comb begin
    // MSB always participates for this Fibonacci form
        feedback = state[W-1];

        for (i = 1; i < W; i++) begin
            if (POLY[i]) begin
                feedback ^= state[i-1];
            end
        end

        next_state = {state[W-2:0], feedback};
    end

    // State register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            if (DEFAULT_SEED == '0)
                state <= {{(W-1){1'b0}}, 1'b1};
            else
                state <= DEFAULT_SEED;
        end
        else if (seed_load) begin
            if (seed == '0)
                state <= (DEFAULT_SEED == '0) ? {{(W-1){1'b0}}, 1'b1}
                                              : DEFAULT_SEED;
            else
                state <= seed;
        end
        else if (enable) begin
            // extra protection in case state is somehow corrupted to zero
            if (state == '0)
                state <= (DEFAULT_SEED == '0) ? {{(W-1){1'b0}}, 1'b1}
                                              : DEFAULT_SEED;
            else
                state <= next_state;
        end
    end
    // Structural sanity checks
    initial begin
        if (W < 2) begin
            $error("lfsr_poly: W must be >= 2");
        end
        if (POLY == '0) begin
            $warning("lfsr_poly: POLY is all-zero. Maximal-length is impossible unless caller overrides POLY.");
        end
        if (POLY[W] !== 1'b1) begin
            $warning("lfsr_poly: POLY[W] should normally be 1 for a degree-W polynomial.");
        end
    end

endmodule : lfsr_poly

module lfsr_poly_tb;

    // Choose a small width for exhaustive simulation proof.
    // W=8 is practical: period should be 255.
    localparam int W = 8;
    localparam int EXPECTED_PERIOD = (1 << W) - 1;

    // Supply a primitive polynomial externally.

    // For the generic POLY-parameterized version we discussed:
    // Example primitive poly for W=8:
    //   x^8 + x^6 + x^5 + x + 1
    //
    // Keep this consistent with your lfsr_poly's feedback convention.
    localparam logic [W:1] POLY = 8'b1000_1110;;

    localparam logic [W-1:0] DEFAULT_SEED = 8'h01;

    logic clk;
    logic rst_n;
    logic enable;
    logic seed_load;
    logic [W-1:0] seed;
    logic [W-1:0] state;

    lfsr_poly #(
        .W(W),
        .POLY(POLY),
        .DEFAULT_SEED(DEFAULT_SEED)
    ) dut (
        .clk      (clk),
        .rst_n    (rst_n),
        .enable   (enable),
        .seed_load(seed_load),
        .seed     (seed),
        .state    (state)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    // Helpers
    task automatic reset_dut();
        begin
            rst_n      = 1'b0;
            enable     = 1'b0;
            seed_load  = 1'b0;
            seed       = '0;
            repeat (2) @(posedge clk);
            rst_n      = 1'b1;
            @(posedge clk);
        end
    endtask

    task automatic load_seed(input logic [W-1:0] s);
        begin
            seed      = s;
            seed_load = 1'b1;
            @(posedge clk);
            seed_load = 1'b0;
            @(posedge clk);
        end
    endtask

    task automatic step_n(input int n);
        int i;
        begin
            enable = 1'b1;
            for (i = 0; i < n; i++) begin
                @(posedge clk);
            end
            enable = 1'b0;
            @(posedge clk);
        end
    endtask

    // Test 1: zero-state protection
    // XOR-LFSR must never remain in all-zero state.
    task automatic test_zero_seed_protection();
        begin
            $display("\n[TEST1] zero-seed protection");
            reset_dut();

            load_seed('0);

            if (state == '0) begin
                $error("[TEST1] FAIL: state remained all-zero after loading zero seed");
                $finish;
            end
            else begin
                $display("[TEST1] PASS: zero seed redirected to nonzero state = 0x%0h", state);
            end
        end
    endtask

    // Test 2: repeatability
    // Same seed must produce same sequence.
    task automatic test_repeatability();
        logic [W-1:0] seq1 [0:15];
        logic [W-1:0] seq2 [0:15];
        int i;
        begin
            $display("\n[TEST2] repeatability");

            reset_dut();
            load_seed(8'hA5);

            enable = 1'b1;
            for (i = 0; i < 16; i++) begin
                @(posedge clk);
                seq1[i] = state;
            end
            enable = 1'b0;
            @(posedge clk);

            reset_dut();
            load_seed(8'hA5);

            enable = 1'b1;
            for (i = 0; i < 16; i++) begin
                @(posedge clk);
                seq2[i] = state;
            end
            enable = 1'b0;
            @(posedge clk);

            for (i = 0; i < 16; i++) begin
                if (seq1[i] !== seq2[i]) begin
                    $error("[TEST2] FAIL: mismatch at i=%0d seq1=0x%0h seq2=0x%0h",
                           i, seq1[i], seq2[i]);
                    $finish;
                end
            end

            $display("[TEST2] PASS: same seed reproduced identical sequence");
        end
    endtask

    // Test 3: maximal-length period check (exhaustive for small W)
    // check:
    //   1) no zero state appears
    //   2) no repeated state appears before returning to first state
    //   3) return occurs exactly after 2^W - 1 steps
    task automatic test_period();
        bit visited [0:EXPECTED_PERIOD]; // enough for indices 0..255 when W=8
        logic [W-1:0] first_state;
        int step_count;
        int idx;
        begin
            $display("\n[TEST3] exhaustive period check for W=%0d", W);

            reset_dut();
            load_seed(DEFAULT_SEED);

            first_state = state;

            if (first_state == '0) begin
                $error("[TEST3] FAIL: first_state is zero");
                $finish;
            end

            // clear visited table
            for (idx = 0; idx <= EXPECTED_PERIOD; idx++) begin
                visited[idx] = 1'b0;
            end

            // mark initial state
            visited[first_state] = 1'b1;
            step_count = 0;

            enable = 1'b1;
            forever begin
                @(posedge clk);
                step_count++;

                if (state == '0) begin
                    $error("[TEST3] FAIL: entered all-zero lockup state at step %0d", step_count);
                    $finish;
                end

                if (state == first_state) begin
                    if (step_count != EXPECTED_PERIOD) begin
                        $error("[TEST3] FAIL: returned to first state too early/late. step_count=%0d expected=%0d",
                               step_count, EXPECTED_PERIOD);
                        $finish;
                    end
                    else begin
                        $display("[TEST3] PASS: period = %0d = 2^W - 1", step_count);
                        disable fork;
                        break;
                    end
                end

                if (visited[state]) begin
                    $error("[TEST3] FAIL: repeated non-initial state 0x%0h before full period, step=%0d",
                           state, step_count);
                    $finish;
                end

                visited[state] = 1'b1;
            end

            enable = 1'b0;
            @(posedge clk);
        end
    endtask

    initial begin
        $display("==== lfsr_poly_tb start ====");

        test_zero_seed_protection();
        test_repeatability();
        test_period();

        $display("\nAll LFSR tests PASSED.");
        $finish;
    end

endmodule: lfsr_poly_tb