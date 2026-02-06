`timescale 1ns / 1ps

module tb_alu_coverage;

    // -------------------------------------------------------------------------
    // 1. Signal Declarations
    // -------------------------------------------------------------------------
    logic clk;
    logic rst_n;
    logic sample;
    logic [7:0] a;
    logic [7:0] b;

    // Outputs from the DUT (Device Under Test)
    logic [31:0] zero_cnt;
    logic [31:0] nonzero_cnt;

    // -------------------------------------------------------------------------
    // 2. DUT Instantiation
    // -------------------------------------------------------------------------
    alu_coverage_model dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample(sample),
        .a(a),
        .b(b),
        // Connect outputs
        // Note: These names match the generated top-level module output ports
        .cg_add_inst_cp_add_inst_zero_cnt(zero_cnt),
        .cg_add_inst_cp_add_inst_nonzero_cnt(nonzero_cnt)
    );

    // -------------------------------------------------------------------------
    // 3. Clock Generation
    // -------------------------------------------------------------------------
    initial begin
        clk = 0;
        forever #5 clk = ~clk; // 10ns period
    end

    // -------------------------------------------------------------------------
    // 4. Test Procedures
    // -------------------------------------------------------------------------
    initial begin
        // --- Initialization ---
        $display("Starting Testbench...");
        $dumpfile("dump.vcd"); $dumpvars;
        rst_n = 0;
        sample = 0;
        a = 0;
        b = 0;

        // Apply Reset
        repeat (2) @(posedge clk);
        rst_n = 1;
        $display("Reset released.");

        // --- Test Case 1: Hit 'zero' bin ---
        // Expression is (a[7:6] & b[7:6])
        // To get 0: Let a[7:6] = 00, b[7:6] = 00 -> 0 & 0 = 0
        $display("Test 1: Targeting 'zero' bin...");
        @(posedge clk);
        a = 8'b0000_0000; 
        b = 8'b0000_0000;
        sample = 1;       // Trigger sample
        @(posedge clk);
        sample = 0;       // De-assert sample
        
        // Wait for update (counters update on posedge when sample is high)
        @(negedge clk); 
        if (zero_cnt !== 1) $error("Test 1 Failed: zero_cnt should be 1, got %0d", zero_cnt);
        if (nonzero_cnt !== 0) $error("Test 1 Failed: nonzero_cnt should be 0, got %0d", nonzero_cnt);


        // --- Test Case 2: Hit 'nonzero' bin ---
        // To get 1: Let a[7:6] = 01 (0x40), b[7:6] = 01 (0x40) -> 1 & 1 = 1
        $display("Test 2: Targeting 'nonzero' bin (value 1)...");
        @(posedge clk);
        a = 8'b0100_0000; // Bits 7:6 are '01'
        b = 8'b0100_0000; // Bits 7:6 are '01'
        sample = 1;
        @(posedge clk);
        sample = 0;

        @(negedge clk);
        if (zero_cnt !== 1) $error("Test 2 Failed: zero_cnt should remain 1, got %0d", zero_cnt);
        if (nonzero_cnt !== 1) $error("Test 2 Failed: nonzero_cnt should be 1, got %0d", nonzero_cnt);


        // --- Test Case 3: Hit 'nonzero' bin again (different value) ---
        // To get 3: Let a[7:6] = 11 (0xC0), b[7:6] = 11 (0xC0) -> 3 & 3 = 3
        $display("Test 3: Targeting 'nonzero' bin (value 3)...");
        @(posedge clk);
        a = 8'b1100_0000; 
        b = 8'b1100_0000;
        sample = 1;
        @(posedge clk);
        sample = 0;

        @(negedge clk);
        if (nonzero_cnt !== 2) $error("Test 3 Failed: nonzero_cnt should be 2, got %0d", nonzero_cnt);


        // --- Test Case 4: No Sample Trigger ---
        // Change inputs but keep sample low. Counters should NOT change.
        $display("Test 4: Changing inputs without sample trigger...");
        @(posedge clk);
        a = 8'b0000_0000; // Would hit zero bin if sampled
        b = 8'b0000_0000;
        sample = 0;       // DO NOT SAMPLE
        @(posedge clk);
        
        @(negedge clk);
        if (zero_cnt !== 1) $error("Test 4 Failed: zero_cnt changed without sample signal!");


        // --- Test Case 5: Reset Check ---
        $display("Test 5: Asserting Reset...");
        rst_n = 0;
        @(posedge clk);
        rst_n = 1;
        @(negedge clk);
        if (zero_cnt !== 0 || nonzero_cnt !== 0) $error("Test 5 Failed: Counters did not clear on reset");

        $display("All tests completed.");
        $finish;
    end

endmodule