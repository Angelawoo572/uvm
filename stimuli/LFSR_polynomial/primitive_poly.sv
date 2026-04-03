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

// from https://docs.amd.com/api/khub/documents/F9osNcU4E9VyJU6VdodOdA/content
module lfsr_poly_widthsel #(
    parameter int MAX_W = 64
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         enable,
    input  logic         seed_load,
    input  logic [6:0]   bitwidth,   // supported: 3..64
    input  logic [63:0]  seed,
    output logic [63:0]  state
);

    logic [63:0] next_state;
    logic [63:0] tap_mask;
    logic [63:0] active_mask;
    logic        feedback;
    logic        valid_width;
    logic        seed_is_zero_for_width;

    int i;

    // Low bitmask with 'bitwidth' ones
    function automatic logic [63:0] get_active_mask(input logic [6:0] w);
        logic [63:0] m;
        int k;
        begin
            m = '0;
            for (k = 0; k < 64; k++) begin
                if (k < w) m[k] = 1'b1;
            end
            return m;
        end
    endfunction

    // XAPP052 taps, converted to a mask of LOWER taps only.
    // The MSB tap (position n) is handled separately in feedback.
    function automatic logic [63:0] get_tap_mask(input logic [6:0] w);
        logic [63:0] m;
        begin
            m = '0;
            unique case (w)
                7'd3:  begin m[1]  = 1'b1; end                        // 3,2
                7'd4:  begin m[2]  = 1'b1; end                        // 4,3
                7'd5:  begin m[2]  = 1'b1; end                        // 5,3
                7'd6:  begin m[4]  = 1'b1; end                        // 6,5
                7'd7:  begin m[5]  = 1'b1; end                        // 7,6
                7'd8:  begin m[5]  = 1'b1; m[4] = 1'b1; m[3] = 1'b1; end // 8,6,5,4
                7'd9:  begin m[4]  = 1'b1; end                        // 9,5
                7'd10: begin m[6]  = 1'b1; end                        // 10,7
                7'd11: begin m[8]  = 1'b1; end                        // 11,9
                7'd12: begin m[5]  = 1'b1; m[3] = 1'b1; m[0] = 1'b1; end // 12,6,4,1
                7'd13: begin m[3]  = 1'b1; m[2] = 1'b1; m[0] = 1'b1; end // 13,4,3,1
                7'd14: begin m[4]  = 1'b1; m[2] = 1'b1; m[0] = 1'b1; end // 14,5,3,1
                7'd15: begin m[13] = 1'b1; end                        // 15,14
                7'd16: begin m[14] = 1'b1; m[12]=1'b1; m[3]=1'b1; end // 16,15,13,4
                7'd17: begin m[13] = 1'b1; end                        // 17,14
                7'd18: begin m[10] = 1'b1; end                        // 18,11
                7'd19: begin m[5]  = 1'b1; m[1]=1'b1; m[0]=1'b1; end // 19,6,2,1
                7'd20: begin m[16] = 1'b1; end                        // 20,17
                7'd21: begin m[18] = 1'b1; end                        // 21,19
                7'd22: begin m[20] = 1'b1; end                        // 22,21
                7'd23: begin m[17] = 1'b1; end                        // 23,18
                7'd24: begin m[22] = 1'b1; m[21]=1'b1; m[16]=1'b1; end // 24,23,22,17
                7'd25: begin m[21] = 1'b1; end                        // 25,22
                7'd26: begin m[5]  = 1'b1; m[1]=1'b1; m[0]=1'b1; end // 26,6,2,1
                7'd27: begin m[4]  = 1'b1; m[1]=1'b1; m[0]=1'b1; end // 27,5,2,1
                7'd28: begin m[24] = 1'b1; end                        // 28,25
                7'd29: begin m[26] = 1'b1; end                        // 29,27
                7'd30: begin m[5]  = 1'b1; m[3]=1'b1; m[0]=1'b1; end // 30,6,4,1
                7'd31: begin m[27] = 1'b1; end                        // 31,28
                7'd32: begin m[21] = 1'b1; m[1]=1'b1; m[0]=1'b1; end // 32,22,2,1
                7'd33: begin m[19] = 1'b1; end                        // 33,20
                7'd34: begin m[26] = 1'b1; m[1]=1'b1; m[0]=1'b1; end // 34,27,2,1
                7'd35: begin m[32] = 1'b1; end                        // 35,33
                7'd36: begin m[24] = 1'b1; end                        // 36,25
                7'd37: begin m[4]  = 1'b1; m[3]=1'b1; m[2]=1'b1; m[1]=1'b1; m[0]=1'b1; end // 37,5,4,3,2,1
                7'd38: begin m[5]  = 1'b1; m[4]=1'b1; m[0]=1'b1; end // 38,6,5,1
                7'd39: begin m[34] = 1'b1; end                        // 39,35
                7'd40: begin m[37] = 1'b1; m[20]=1'b1; m[18]=1'b1; end // 40,38,21,19
                7'd41: begin m[37] = 1'b1; end                        // 41,38
                7'd42: begin m[40] = 1'b1; m[19]=1'b1; m[18]=1'b1; end // 42,41,20,19
                7'd43: begin m[41] = 1'b1; m[37]=1'b1; m[36]=1'b1; end // 43,42,38,37
                7'd44: begin m[42] = 1'b1; m[17]=1'b1; m[16]=1'b1; end // 44,43,18,17
                7'd45: begin m[43] = 1'b1; m[41]=1'b1; m[40]=1'b1; end // 45,44,42,41
                7'd46: begin m[44] = 1'b1; m[25]=1'b1; m[24]=1'b1; end // 46,45,26,25
                7'd47: begin m[41] = 1'b1; end                        // 47,42
                7'd48: begin m[46] = 1'b1; m[20]=1'b1; m[19]=1'b1; end // 48,47,21,20
                7'd49: begin m[39] = 1'b1; end                        // 49,40
                7'd50: begin m[48] = 1'b1; m[23]=1'b1; m[22]=1'b1; end // 50,49,24,23
                7'd51: begin m[49] = 1'b1; m[35]=1'b1; m[34]=1'b1; end // 51,50,36,35
                7'd52: begin m[48] = 1'b1; end                        // 52,49
                7'd53: begin m[51] = 1'b1; m[37]=1'b1; m[36]=1'b1; end // 53,52,38,37
                7'd54: begin m[52] = 1'b1; m[17]=1'b1; m[16]=1'b1; end // 54,53,18,17
                7'd55: begin m[30] = 1'b1; end                        // 55,31
                7'd56: begin m[54] = 1'b1; m[34]=1'b1; m[33]=1'b1; end // 56,55,35,34
                7'd57: begin m[49] = 1'b1; end                        // 57,50
                7'd58: begin m[38] = 1'b1; end                        // 58,39
                7'd59: begin m[57] = 1'b1; m[37]=1'b1; m[36]=1'b1; end // 59,58,38,37
                7'd60: begin m[58] = 1'b1; end                        // 60,59
                7'd61: begin m[59] = 1'b1; m[45]=1'b1; m[44]=1'b1; end // 61,60,46,45
                7'd62: begin m[60] = 1'b1; m[5]=1'b1;  m[4]=1'b1; end // 62,61,6,5
                7'd63: begin m[61] = 1'b1; end                        // 63,62
                7'd64: begin m[62] = 1'b1; m[60]=1'b1; m[59]=1'b1; end // 64,63,61,60
                default: m = '0;
            endcase
            return m;
        end
    endfunction

    always_comb begin
        valid_width = (bitwidth >= 7'd3) && (bitwidth <= 7'd64);
        active_mask = get_active_mask(bitwidth);
        tap_mask    = get_tap_mask(bitwidth);

        feedback = 1'b0;
        next_state = '0;

        if (valid_width) begin
            // XOR version: same tap positions as XAPP052 XNOR table,
            // but the forbidden state becomes all-zeros instead of all-ones.
            feedback = state[bitwidth-1];
            for (i = 0; i < 64; i++) begin
                if (tap_mask[i]) feedback ^= state[i];
            end

            next_state[0] = feedback;
            for (i = 1; i < 64; i++) begin
                if (i < bitwidth)
                    next_state[i] = state[i-1];
                else
                    next_state[i] = 1'b0;
            end
        end
    end

    always_comb begin
        seed_is_zero_for_width = ((seed & active_mask) == 64'b0);
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= 64'b1;   // nonzero reset state
        end else if (seed_load) begin
            if (!valid_width || seed_is_zero_for_width)
                state <= 64'b1;
            else
                state <= (seed & active_mask);
        end else if (enable) begin
            if (!valid_width)
                state <= 64'b1;
            else if ((state & active_mask) == 64'b0)
                state <= 64'b1;
            else
                state <= next_state;
        end
    end

endmodule: lfsr_poly_widthsel

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

module lfsr_poly_widthsel_tb;
    logic        clk;
    logic        rst_n;
    logic        enable;
    logic        seed_load;
    logic [6:0]  bitwidth;
    logic [63:0] seed;
    logic [63:0] state;

    lfsr_poly_widthsel dut (
        .clk      (clk),
        .rst_n    (rst_n),
        .enable   (enable),
        .seed_load(seed_load),
        .bitwidth (bitwidth),
        .seed     (seed),
        .state    (state)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    task automatic reset_dut();
        begin
            rst_n      = 1'b0;
            enable     = 1'b0;
            seed_load  = 1'b0;
            bitwidth   = '0;
            seed       = '0;
            repeat (2) @(posedge clk);
            rst_n      = 1'b1;
            @(posedge clk);
        end
    endtask

    task automatic load_cfg(input logic [6:0] w, input logic [63:0] s);
        begin
            bitwidth  = w;
            seed      = s;
            seed_load = 1'b1;
            @(posedge clk);
            seed_load = 1'b0;
            @(posedge clk);
        end
    endtask

    function automatic logic [63:0] active_mask(input int w);
        logic [63:0] m;
        int i;
        begin
            m = '0;
            for (i = 0; i < 64; i++) begin
                if (i < w) m[i] = 1'b1;
            end
            return m;
        end
    endfunction

    function automatic longint unsigned expected_period(input int w);
        longint unsigned p;
        begin
            p = 64'd1;
            p = (p << w) - 1;
            return p;
        end
    endfunction

    task automatic test_zero_seed_redirect(input int w);
        logic [63:0] mask;
        begin
            $display("\n[ZERO] test width=%0d", w);
            reset_dut();
            load_cfg(w, 64'd0);

            mask = active_mask(w);

            if ((state & mask) == 64'd0) begin
                $error("[ZERO] FAIL width=%0d : state stayed zero in active bits", w);
                $finish;
            end
            else begin
                $display("[ZERO] PASS width=%0d : redirected to nonzero state 0x%0h", w, (state & mask));
            end
        end
    endtask

    task automatic test_repeatability(input int w, input logic [63:0] s);
        logic [63:0] seq1 [0:15];
        logic [63:0] seq2 [0:15];
        logic [63:0] mask;
        int i;
        begin
            $display("\n[REPEAT] test width=%0d", w);
            mask = active_mask(w);

            reset_dut();
            load_cfg(w, s);

            enable = 1'b1;
            for (i = 0; i < 16; i++) begin
                @(posedge clk);
                seq1[i] = state & mask;
            end
            enable = 1'b0;
            @(posedge clk);

            reset_dut();
            load_cfg(w, s);

            enable = 1'b1;
            for (i = 0; i < 16; i++) begin
                @(posedge clk);
                seq2[i] = state & mask;
            end
            enable = 1'b0;
            @(posedge clk);

            for (i = 0; i < 16; i++) begin
                if (seq1[i] !== seq2[i]) begin
                    $error("[REPEAT] FAIL width=%0d : mismatch at i=%0d seq1=0x%0h seq2=0x%0h",
                           w, i, seq1[i], seq2[i]);
                    $finish;
                end
            end

            $display("[REPEAT] PASS width=%0d", w);
        end
    endtask

    task automatic test_period_exhaustive(input int w, input logic [63:0] s);
        bit visited [0:(1<<16)-1];  // enough for w <= 16 in exhaustive mode
        logic [63:0] mask;
        logic [63:0] first_state;
        logic [63:0] curr_state;
        longint unsigned period;
        int i;

        begin
            if (w > 16) begin
                $display("\n[PERIOD] SKIP width=%0d : exhaustive check disabled for w>16", w);
                disable test_period_exhaustive;
            end

            $display("\n[PERIOD] exhaustive width=%0d", w);

            mask   = active_mask(w);
            period = expected_period(w);

            reset_dut();
            load_cfg(w, s);

            first_state = state & mask;

            if (first_state == 64'd0) begin
                $error("[PERIOD] FAIL width=%0d : initial state is zero", w);
                $finish;
            end

            for (i = 0; i < (1<<16); i++) begin
                visited[i] = 1'b0;
            end

            visited[int'(first_state)] = 1'b1;

            enable = 1'b1;
            for (i = 1; i <= period; i++) begin
                @(posedge clk);
                curr_state = state & mask;

                if (curr_state == 64'd0) begin
                    $error("[PERIOD] FAIL width=%0d : entered zero state at step=%0d", w, i);
                    $finish;
                end

                if (curr_state == first_state) begin
                    if (i != period) begin
                        $error("[PERIOD] FAIL width=%0d : returned early at step=%0d expected=%0d",
                               w, i, period);
                        $finish;
                    end
                    else begin
                        $display("[PERIOD] PASS width=%0d : period=%0d", w, period);
                    end
                end
                else begin
                    if (visited[int'(curr_state)]) begin
                        $error("[PERIOD] FAIL width=%0d : repeated state 0x%0h before full period at step=%0d",
                               w, curr_state, i);
                        $finish;
                    end
                    visited[int'(curr_state)] = 1'b1;
                end
            end

            enable = 1'b0;
            @(posedge clk);
        end
    endtask

    task automatic smoke_test_large_width(input int w, input logic [63:0] s, input int steps);
        logic [63:0] mask;
        logic [63:0] curr_state;
        int i;
        begin
            $display("\n[SMOKE] width=%0d steps=%0d", w, steps);

            mask = active_mask(w);

            reset_dut();
            load_cfg(w, s);

            if ((state & mask) == 64'd0) begin
                $error("[SMOKE] FAIL width=%0d : initial active state is zero", w);
                $finish;
            end

            enable = 1'b1;
            for (i = 0; i < steps; i++) begin
                @(posedge clk);
                curr_state = state & mask;
                if (curr_state == 64'd0) begin
                    $error("[SMOKE] FAIL width=%0d : zero state seen at i=%0d", w, i);
                    $finish;
                end
            end
            enable = 1'b0;
            @(posedge clk);

            $display("[SMOKE] PASS width=%0d", w);
        end
    endtask

    task automatic test_invalid_width(input int w);
        logic [63:0] prev;
        int i;
        begin
            $display("\n[INVALID] test width=%0d", w);

            reset_dut();
            load_cfg(w, 64'h1234);

            prev = state;

            enable = 1'b1;
            for (i = 0; i < 10; i++) begin
                @(posedge clk);

                if (state == 64'd0) begin
                    $error("[INVALID] FAIL width=%0d : entered zero state", w);
                    $finish;
                end

                if (state !== prev) begin
                    $display("[INVALID] INFO width=%0d : state changes (acceptable)", w);
                    disable fork;
                    break;
                end
            end

            enable = 1'b0;
            @(posedge clk);

            $display("[INVALID] PASS width=%0d", w);
        end
    endtask

    initial begin
        $display("==== lfsr_poly_widthsel_tb start ====");

        // zero-seed behavior
        test_zero_seed_redirect(3);
        test_zero_seed_redirect(8);
        test_zero_seed_redirect(16);

        // repeatability
        test_repeatability(8,  64'hA5);
        test_repeatability(16, 64'h1234);

        // exhaustive period checks for small widths
        test_period_exhaustive(3,  64'h1);     // expected 7
        test_period_exhaustive(4,  64'h1);     // expected 15
        test_period_exhaustive(8,  64'h1);     // expected 255
        test_period_exhaustive(12, 64'h1);     // expected 4095
        test_period_exhaustive(16, 64'h1);     // expected 65535

        // smoke checks for larger widths
        smoke_test_large_width(32, 64'h1, 2000);
        smoke_test_large_width(64, 64'h1, 2000);
        // invalid width tests
        test_invalid_width(2);
        test_invalid_width(65);

        $display("\nAll width-select LFSR tests PASSED.");
        $finish;
    end

endmodule: lfsr_poly_widthsel_tb