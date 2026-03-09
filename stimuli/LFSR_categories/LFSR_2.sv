`default_nettype none

// Method 2:
// Synthesizable RTL for:
//   addr > 1234
//   addr < 5555
module method2_numeric_bounds (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        enable,
    input  logic [15:0] seed,
    input  logic        seed_load,

    output logic [15:0] addr,
    output logic        valid
);

    logic [15:0] lfsr_state, lfsr_next;
    logic        feedback;

    // Example 16-bit LFSR taps
    assign feedback  = lfsr_state[15] ^ lfsr_state[13] ^ lfsr_state[12] ^ lfsr_state[10];
    assign lfsr_next = {lfsr_state[14:0], feedback};

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr_state <= 16'h1;
        end else if (seed_load) begin
            lfsr_state <= (seed == 16'h0) ? 16'h1 : seed;
        end else if (enable) begin
            lfsr_state <= lfsr_next;
        end
    end

    assign addr  = lfsr_state;
    assign valid = (addr > 16'd1234) && (addr < 16'd5555);

endmodule: method2_numeric_bounds

module tb_method2_numeric_bounds;

    logic        clk;
    logic        rst_n;
    logic        enable;
    logic [15:0] seed;
    logic        seed_load;
    logic [15:0] addr;
    logic        valid;

    method2_numeric_bounds dut (
        .clk(clk),
        .rst_n(rst_n),
        .enable(enable),
        .seed(seed),
        .seed_load(seed_load),
        .addr(addr),
        .valid(valid)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 0;
        rst_n = 0;
        enable = 0;
        seed = 16'hACE1;
        seed_load = 0;

        #12;
        rst_n = 1;

        #10;
        seed_load = 1;
        #10;
        seed_load = 0;
        enable = 1;

        repeat (20) begin
            @(posedge clk);
            $display("[M2] t=%0t addr=%0d valid=%0b", $time, addr, valid);
        end

        $finish;
    end

endmodule: tb_method2_numeric_bounds