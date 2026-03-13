`default_nettype none

module method2_numeric_bounds #(
    parameter int W = 16,
    parameter logic [W-1:0] LO = 16'd1235,
    parameter logic [W-1:0] HI = 16'd5554
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         enable,
    input  logic [W-1:0] seed,
    input  logic         seed_load,

    output logic [W-1:0] addr,
    output logic         valid
);

    logic [W-1:0] range_size;
    logic [W-1:0] offset;
    logic [W-1:0] idx;
    logic [W-1:0] next_idx;

    assign range_size = HI - LO + 16'd1;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            idx    <= '0;
            offset <= '0;
        end else if (seed_load) begin
            idx    <= '0;
            offset <= seed % range_size;
        end else if (enable) begin
            if (idx == range_size - 16'd1)
                idx <= '0;
            else
                idx <= idx + 16'd1;
        end
    end

    always_comb begin
        next_idx = offset + idx;
        if (next_idx >= range_size)
            next_idx = next_idx - range_size;
        addr = LO + next_idx;
    end

    assign valid = 1'b1;

endmodule : method2_numeric_bounds


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

        repeat (12) begin
            @(posedge clk);
            $display("[M2] t=%0t addr=%0d valid=%0b", $time, addr, valid);
            if (!((addr > 16'd1234) && (addr < 16'd5555))) begin
                $display("ERROR: addr out of method2 bounds");
                $finish;
            end
        end

        $finish;
    end

endmodule : tb_method2_numeric_bounds