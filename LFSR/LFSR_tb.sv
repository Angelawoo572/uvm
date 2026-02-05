`default_nettype none

module tb_bounded_lfsr;

  logic clk = 0;
  always #5 clk = ~clk;   // 100MHz
  logic rst_n;

  logic [15:0] seed_in;
  logic        seed_load;
  logic        enable;

  logic        cfg_mask_en;
  logic [7:0]  cfg_mask;
  logic [7:0]  cfg_fixed_bits;
  logic        cfg_pow2_range_en;
  logic [7:0]  cfg_L;
  logic [7:0]  cfg_pow2_mask;

  logic        c_range_en;
  logic [7:0]  cL, cH;
  logic        c_neq_en;
  logic [7:0]  cK;

  logic        out_valid;
  logic [7:0]  out_value;

  StimulusGlue dut (
    .clk(clk),
    .rst_n(rst_n),

    .seed_in(seed_in),
    .seed_load(seed_load),
    .enable(enable),

    .cfg_mask_en(cfg_mask_en),
    .cfg_mask(cfg_mask),
    .cfg_fixed_bits(cfg_fixed_bits),
    .cfg_pow2_range_en(cfg_pow2_range_en),
    .cfg_L(cfg_L),
    .cfg_pow2_mask(cfg_pow2_mask),

    .c_range_en(c_range_en),
    .cL(cL),
    .cH(cH),
    .c_neq_en(c_neq_en),
    .cK(cK),

    .out_valid(out_valid),
    .out_value(out_value)
  );

  initial begin
    // defaults
    rst_n = 0;
    seed_load = 0;
    enable = 0;

    cfg_mask_en = 0;
    cfg_pow2_range_en = 0;

    c_range_en = 0;
    c_neq_en   = 0;

    // reset
    #20;
    rst_n = 1;

    // load seed
    @(negedge clk);
    seed_in   = 16'hACE1;
    seed_load = 1;
    @(negedge clk);
    seed_load = 0;

    // enable generator
    enable = 1;

    // simple constraint: 3 <= x <= 7
    c_range_en = 1;
    cL = 8'd3;
    cH = 8'd7;

    // run for some cycles
    repeat (2000) begin
      @(posedge clk);
      $display("t=%0t  cand=%0d  valid=%0b",
               $time, out_value, out_valid);
    end

    $finish;
  end

endmodule: tb_bounded_lfsr