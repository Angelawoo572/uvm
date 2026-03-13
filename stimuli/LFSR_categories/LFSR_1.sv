`default_nettype none

module method1_inside_range #(
    parameter int W = 8
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

    logic [W-1:0] range_size;
    logic [W-1:0] offset;
    logic [W-1:0] idx;
    logic [W-1:0] next_idx;
    logic         bounds_ok;

    assign bounds_ok  = (hi >= lo);
    assign range_size = bounds_ok ? (hi - lo + {{(W-1){1'b0}},1'b1}) : '0;

    // idx is the position inside the legal domain [0 : range_size-1]
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            idx    <= '0;
            offset <= '0;
        end else if (seed_load) begin
            idx    <= '0;
            if (bounds_ok && (range_size != '0))
                offset <= seed % range_size;
            else
                offset <= '0;
        end else if (enable && bounds_ok && (range_size != '0)) begin
            if (idx == (range_size - {{(W-1){1'b0}},1'b1}))
                idx <= '0;
            else
                idx <= idx + {{(W-1){1'b0}},1'b1};
        end
    end

    // addr = lo + ((offset + idx) mod range_size)
    always_comb begin
        next_idx = offset + idx;
        if (bounds_ok && (range_size != '0) && (next_idx >= range_size))
            next_idx = next_idx - range_size;
        addr = lo + next_idx;
    end

    assign valid = bounds_ok && (range_size != '0);
    assign diff  = addr - lo;

endmodule : method1_inside_range


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
        lo = 4'd1;   // [1:3]
        hi = 4'd3;

        #12;
        rst_n = 1;

        #10;
        seed_load = 1;
        #10;
        seed_load = 0;
        enable = 1;

        repeat (10) begin
            @(posedge clk);
            $display("[M1] t=%0t addr=%0d valid=%0b diff=%0d range=[%0d:%0d]",
                     $time, addr, valid, diff, lo, hi);
            if (valid && !((addr >= lo) && (addr <= hi))) begin
                $display("ERROR: addr out of range");
                $finish;
            end
        end

        $finish;
    end

endmodule : tb_method1_inside_range