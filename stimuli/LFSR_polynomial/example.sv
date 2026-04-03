`default_nettype none
`include "../stimuli_fsm/seq_stim_if.svh"
module lfsr_poly_fixed #(
    parameter int W = 8
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
    // Return LOWER tap mask only.
    // MSB tap is always implicit in this Fibonacci XOR form.
    // Bit i of the returned mask corresponds to state[i].
    function automatic logic [W-1:0] get_tap_mask();
        logic [W-1:0] m;
        begin
            m = '0;
            unique case (W)
                3:  begin m[1]  = 1'b1; end                                  // 3,2
                4:  begin m[2]  = 1'b1; end                                  // 4,3
                5:  begin m[2]  = 1'b1; end                                  // 5,3
                6:  begin m[4]  = 1'b1; end                                  // 6,5
                7:  begin m[5]  = 1'b1; end                                  // 7,6
                8:  begin m[5]  = 1'b1; m[4] = 1'b1; m[3] = 1'b1; end        // 8,6,5,4
                9:  begin m[4]  = 1'b1; end                                  // 9,5
                10: begin m[6]  = 1'b1; end                                  // 10,7
                11: begin m[8]  = 1'b1; end                                  // 11,9
                12: begin m[5]  = 1'b1; m[3] = 1'b1; m[0] = 1'b1; end        // 12,6,4,1
                13: begin m[3]  = 1'b1; m[2] = 1'b1; m[0] = 1'b1; end        // 13,4,3,1
                14: begin m[4]  = 1'b1; m[2] = 1'b1; m[0] = 1'b1; end        // 14,5,3,1
                15: begin m[13] = 1'b1; end                                  // 15,14
                16: begin m[14] = 1'b1; m[12] = 1'b1; m[3] = 1'b1; end       // 16,15,13,4
                17: begin m[13] = 1'b1; end                                  // 17,14
                18: begin m[10] = 1'b1; end                                  // 18,11
                19: begin m[5]  = 1'b1; m[1] = 1'b1; m[0] = 1'b1; end        // 19,6,2,1
                20: begin m[16] = 1'b1; end                                  // 20,17
                21: begin m[18] = 1'b1; end                                  // 21,19
                22: begin m[20] = 1'b1; end                                  // 22,21
                23: begin m[17] = 1'b1; end                                  // 23,18
                24: begin m[22] = 1'b1; m[21] = 1'b1; m[16] = 1'b1; end      // 24,23,22,17
                25: begin m[21] = 1'b1; end                                  // 25,22
                26: begin m[5]  = 1'b1; m[1] = 1'b1; m[0] = 1'b1; end        // 26,6,2,1
                27: begin m[4]  = 1'b1; m[1] = 1'b1; m[0] = 1'b1; end        // 27,5,2,1
                28: begin m[24] = 1'b1; end                                  // 28,25
                29: begin m[26] = 1'b1; end                                  // 29,27
                30: begin m[5]  = 1'b1; m[3] = 1'b1; m[0] = 1'b1; end        // 30,6,4,1
                31: begin m[27] = 1'b1; end                                  // 31,28
                32: begin m[21] = 1'b1; m[1] = 1'b1; m[0] = 1'b1; end        // 32,22,2,1
                33: begin m[19] = 1'b1; end                                  // 33,20
                34: begin m[26] = 1'b1; m[1] = 1'b1; m[0] = 1'b1; end        // 34,27,2,1
                35: begin m[32] = 1'b1; end                                  // 35,33
                36: begin m[24] = 1'b1; end                                  // 36,25
                37: begin m[4]  = 1'b1; m[3] = 1'b1; m[2] = 1'b1;
                          m[1]  = 1'b1; m[0] = 1'b1; end                     // 37,5,4,3,2,1
                38: begin m[5]  = 1'b1; m[4] = 1'b1; m[0] = 1'b1; end        // 38,6,5,1
                39: begin m[34] = 1'b1; end                                  // 39,35
                40: begin m[37] = 1'b1; m[20] = 1'b1; m[18] = 1'b1; end      // 40,38,21,19
                41: begin m[37] = 1'b1; end                                  // 41,38
                42: begin m[40] = 1'b1; m[19] = 1'b1; m[18] = 1'b1; end      // 42,41,20,19
                43: begin m[41] = 1'b1; m[37] = 1'b1; m[36] = 1'b1; end      // 43,42,38,37
                44: begin m[42] = 1'b1; m[17] = 1'b1; m[16] = 1'b1; end      // 44,43,18,17
                45: begin m[43] = 1'b1; m[41] = 1'b1; m[40] = 1'b1; end      // 45,44,42,41
                46: begin m[44] = 1'b1; m[25] = 1'b1; m[24] = 1'b1; end      // 46,45,26,25
                47: begin m[41] = 1'b1; end                                  // 47,42
                48: begin m[46] = 1'b1; m[20] = 1'b1; m[19] = 1'b1; end      // 48,47,21,20
                49: begin m[39] = 1'b1; end                                  // 49,40
                50: begin m[48] = 1'b1; m[23] = 1'b1; m[22] = 1'b1; end      // 50,49,24,23
                51: begin m[49] = 1'b1; m[35] = 1'b1; m[34] = 1'b1; end      // 51,50,36,35
                52: begin m[48] = 1'b1; end                                  // 52,49
                53: begin m[51] = 1'b1; m[37] = 1'b1; m[36] = 1'b1; end      // 53,52,38,37
                54: begin m[52] = 1'b1; m[17] = 1'b1; m[16] = 1'b1; end      // 54,53,18,17
                55: begin m[30] = 1'b1; end                                  // 55,31
                56: begin m[54] = 1'b1; m[34] = 1'b1; m[33] = 1'b1; end      // 56,55,35,34
                57: begin m[49] = 1'b1; end                                  // 57,50
                58: begin m[38] = 1'b1; end                                  // 58,39
                59: begin m[57] = 1'b1; m[37] = 1'b1; m[36] = 1'b1; end      // 59,58,38,37
                60: begin m[58] = 1'b1; end                                  // 60,59
                61: begin m[59] = 1'b1; m[45] = 1'b1; m[44] = 1'b1; end      // 61,60,46,45
                62: begin m[60] = 1'b1; m[5]  = 1'b1; m[4]  = 1'b1; end      // 62,61,6,5
                63: begin m[61] = 1'b1; end                                  // 63,62
                64: begin m[62] = 1'b1; m[60] = 1'b1; m[59] = 1'b1; end      // 64,63,61,60
                default: m = '0;
            endcase
            return m;
        end
    endfunction

    localparam logic [W-1:0] TAP_MASK = get_tap_mask();
    localparam logic [W-1:0] DEFAULT_SEED = {{(W-1){1'b0}}, 1'b1};

    always_comb begin
        feedback = state[W-1];
        for (i = 0; i < W-1; i++) begin
            if (TAP_MASK[i]) feedback ^= state[i];
        end
        next_state = {state[W-2:0], feedback};
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= DEFAULT_SEED;
        end else if (seed_load) begin
            if (seed == '0)
                state <= DEFAULT_SEED;
            else
                state <= seed;
        end else if (enable) begin
            if (state == '0)
                state <= DEFAULT_SEED;
            else
                state <= next_state;
        end
    end

    initial begin
        if (W < 3 || W > 64)
            $error("lfsr_poly_fixed: unsupported W=%0d (supported 3..64)", W);
        if (TAP_MASK == '0)
            $error("lfsr_poly_fixed: no tap mask defined for W=%0d", W);
    end

endmodule : lfsr_poly_fixed

module lfsr_poly_fixed_tb;
    localparam int W = 16;
    localparam longint unsigned EXPECTED_PERIOD = (64'd1 << W) - 1;

    logic         clk;
    logic         rst_n;
    logic         enable;
    logic         seed_load;
    logic [W-1:0] seed;
    logic [W-1:0] state;

    lfsr_poly_fixed #(
        .W(W)
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

    task automatic reset_dut();
        begin
            rst_n     = 1'b0;
            enable    = 1'b0;
            seed_load = 1'b0;
            seed      = '0;
            repeat (2) @(posedge clk);
            rst_n     = 1'b1;
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

    task automatic test_zero_seed_redirect();
        begin
            $display("\n[ZERO] W=%0d", W);
            reset_dut();
            load_seed('0);

            if (state == '0) begin
                $error("[ZERO] FAIL: state remained zero");
                $finish;
            end

            $display("[ZERO] PASS: redirected to 0x%0h", state);
        end
    endtask

    task automatic test_repeatability();
        logic [W-1:0] seq1 [0:15];
        logic [W-1:0] seq2 [0:15];
        int i;
        begin
            $display("\n[REPEAT] W=%0d", W);

            reset_dut();
            load_seed({{(W-8){1'b0}}, 8'hA5});

            enable = 1'b1;
            for (i = 0; i < 16; i++) begin
                @(posedge clk);
                seq1[i] = state;
            end
            enable = 1'b0;
            @(posedge clk);

            reset_dut();
            load_seed({{(W-8){1'b0}}, 8'hA5});

            enable = 1'b1;
            for (i = 0; i < 16; i++) begin
                @(posedge clk);
                seq2[i] = state;
            end
            enable = 1'b0;
            @(posedge clk);

            for (i = 0; i < 16; i++) begin
                if (seq1[i] !== seq2[i]) begin
                    $error("[REPEAT] FAIL: mismatch at i=%0d", i);
                    $finish;
                end
            end

            $display("[REPEAT] PASS");
        end
    endtask

    task automatic test_period_exhaustive();
        bit visited [0:(1<<16)-1];
        logic [W-1:0] first_state;
        int i;
        begin
            if (W > 16) begin
                $display("\n[PERIOD] SKIP exhaustive for W=%0d", W);
                disable test_period_exhaustive;
            end

            $display("\n[PERIOD] exhaustive W=%0d", W);

            reset_dut();
            load_seed('d1);

            first_state = state;

            if (first_state == '0) begin
                $error("[PERIOD] FAIL: initial state is zero");
                $finish;
            end

            for (i = 0; i < (1<<16); i++) visited[i] = 1'b0;
            visited[int'(first_state)] = 1'b1;

            enable = 1'b1;
            for (i = 1; i <= EXPECTED_PERIOD; i++) begin
                @(posedge clk);

                if (state == '0) begin
                    $error("[PERIOD] FAIL: entered zero state at step %0d", i);
                    $finish;
                end

                if (state == first_state) begin
                    if (i != EXPECTED_PERIOD) begin
                        $error("[PERIOD] FAIL: returned early at step %0d expected %0d", i, EXPECTED_PERIOD);
                        $finish;
                    end else begin
                        $display("[PERIOD] PASS: period=%0d", EXPECTED_PERIOD);
                    end
                end else begin
                    if (visited[int'(state)]) begin
                        $error("[PERIOD] FAIL: repeated state 0x%0h early at step %0d", state, i);
                        $finish;
                    end
                    visited[int'(state)] = 1'b1;
                end
            end

            enable = 1'b0;
            @(posedge clk);
        end
    endtask

    task automatic smoke_test_large();
        int i;
        begin
            if (W <= 16) disable smoke_test_large;

            $display("\n[SMOKE] W=%0d", W);

            reset_dut();
            load_seed('d1);

            if (state == '0) begin
                $error("[SMOKE] FAIL: initial state is zero");
                $finish;
            end

            enable = 1'b1;
            for (i = 0; i < 2000; i++) begin
                @(posedge clk);
                if (state == '0) begin
                    $error("[SMOKE] FAIL: zero state seen at step %0d", i);
                    $finish;
                end
            end
            enable = 1'b0;
            @(posedge clk);

            $display("[SMOKE] PASS");
        end
    endtask

    initial begin
        $display("==== lfsr_poly_fixed_tb start (W=%0d) ====", W);

        test_zero_seed_redirect();
        test_repeatability();
        test_period_exhaustive();
        smoke_test_large();

        $display("\nAll fixed-width LFSR tests PASSED.");
        $finish;
    end

endmodule: lfsr_poly_fixed_tb