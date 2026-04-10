// ====================================================
// Auto-Generated Synthesizable UVM Testbench
// ====================================================

interface itf #(
  parameter ADDR_WIDTH = 99,
  parameter DATA_WIDTH = 99
) (
  input bit clk
);

  // --- Internal Variables ---
  bit rst_n;
  logic re;
  logic we;
  logic [ADDR_WIDTH-1:0] addr_i;
  logic [DATA_WIDTH-1:0] data_i;
  logic [DATA_WIDTH-1:0] data_o;

  // --- Modports (Converted from Clocking Blocks) ---
  modport drv_cb (
    input clk,
    output rst_n,
    output re,
    output we,
    output addr_i,
    output data_i,
    input data_o
  );

  modport mon_cb (
    input clk,
    input rst_n,
    input re,
    input we,
    input addr_i,
    input data_i,
    input data_o
  );

endinterface : itf

// --- Packed Struct Definitions ---
typedef struct packed {
  bit [ADDR_WIDTH-1:0] addr_i;
  bit we;
  bit re;
  bit [DATA_WIDTH-1:0] data_i;
  logic [DATA_WIDTH-1:0] data_o;
  bit rst_n;
} req_item_s;

typedef struct packed {
  bit [ADDR_WIDTH-1:0] addr_i;
  bit we;
  bit re;
  bit [DATA_WIDTH-1:0] data_i;
  logic [DATA_WIDTH-1:0] data_o;
  bit rst_n;
} reset_req_item_s;

// --- Leaf Module: drv_rtl ---
module drv_rtl #(
  parameter int DATA_WIDTH = 32,
  parameter int ADDR_WIDTH = 16
) (
  itf.drv_cb vif,
  input  logic      clk,
  input  logic      rst_n_sys,
  output logic      req_valid,
  input  logic      req_ready,
  output logic      [31:0] lower_bound,
  output logic      [31:0] upper_bound,
  output logic      rsp_ready,
  input  logic      rsp_valid,
  input  req_item_s req
);
  
typedef enum logic [2:0] {
  S_RESET, 
  S_REQ_ITEM, 
  S_WAIT_RSP, 
  S_DRIVE,
  S_RESPOND
} state_t;

state_t state, next_state;
  
always_comb begin
  // Default assignments
  next_state = state;
  req_valid  = 1'b0;
  rsp_ready  = 1'b0;

  case (state)
    S_RESET: next_state = S_REQ_ITEM;

    S_REQ_ITEM: begin
      req_valid = 1'b1;
      if (req_ready) next_state = S_WAIT_RSP;
    end

    S_WAIT_RSP: begin
      rsp_ready = 1'b1;
      if (rsp_valid) next_state = S_DRIVE;
    end

    S_DRIVE: begin
      next_state = S_REQ_ITEM; 
    end

    default: next_state = S_RESET;
  endcase
end
  always_ff @(posedge clk or negedge rst_n_sys) begin
  if (!rst_n_sys) begin
    state <= S_RESET;
  end else begin
    state <= next_state;
    
    if (state == S_DRIVE) begin
      vif.addr_i <= req.addr_i;
      vif.data_i <= req.data_i;
      vif.re <= req.re;
      vif.we <= req.we;
      vif.rst_n <= req.rst_n;
    end
  end
end

endmodule

// --- Leaf Module: mon_rtl ---
module mon_rtl #(
  parameter int DATA_WIDTH = 32,
  parameter int ADDR_WIDTH = 16
) (
  itf.mon_cb vif,
  input  logic      clk,
  input  logic      rst_n_sys,
  output logic      mon_valid,
  output req_item_s req
);
  always_ff @(posedge clk or negedge rst_n_sys) begin
  if (!rst_n_sys) begin
    mon_valid <= 1'b0;
  end else begin
    mon_valid <= 1'b0; // Default to 0, pulses high on write()
    if (vif.rst_n) begin
    req.rst_n <= vif.rst_n;
    req.re <= vif.re;
    req.we <= vif.we;
    req.addr_i <= vif.addr_i;
    req.data_i <= vif.data_i;
    req.data_o <= vif.data_o;
    mon_valid <= 1'b1;
    end
  end
end

endmodule

// --- Container Module: example1basic_rtl ---
module example1basic_rtl #(
  parameter int DATA_WIDTH = 32,
  parameter int ADDR_WIDTH = 16
) (
  itf.drv_cb vif,
  input  logic      clk,
  input  logic      rst_n_sys,
  output logic      mon_valid,
  input  logic      req_seed_load_ext,
  input  logic      [31:0] seed_ext
);
  env_rtl m_env (.*);

endmodule

// --- Container Module: env_rtl ---
module env_rtl #(
  parameter int DATA_WIDTH = 32,
  parameter int ADDR_WIDTH = 16
) (
  itf.drv_cb vif,
  input  logic      clk,
  input  logic      rst_n_sys,
  output logic      mon_valid,
  input  logic      req_seed_load_ext,
  input  logic      [31:0] seed_ext
);
  agt_rtl m_agt (
    .vif(vif.drv_cb),
    .clk(clk),
    .rst_n_sys(rst_n_sys),
    .mon_valid(mon_valid),
    .req_seed_load_ext(req_seed_load_ext),
    .seed_ext(seed_ext)
  );

endmodule

// --- Container Module: agt_rtl ---
module agt_rtl #(
  parameter int DATA_WIDTH = 32,
  parameter int ADDR_WIDTH = 16
) (
  itf.drv_cb vif,
  input  logic      clk,
  input  logic      rst_n_sys,
  output logic      mon_valid,
  input  logic      req_seed_load_ext,
  input  logic      [31:0] seed_ext
);
  wire w_valid;
  wire w_ready;
  req_item_s w_req;

  drv_rtl m_drv (
    .vif(vif.drv_cb),
    .clk(clk),
    .rst_n_sys(rst_n_sys),
    .req_valid(w_valid),
    .req_ready(w_ready),
    .lower_bound(lower_bound),
    .upper_bound(upper_bound),
    .rsp_ready(w_rsp_ready),
    .rsp_valid(w_rsp_valid),
    .req(w_req)
  );

  mon_rtl m_mon (
    .vif(vif.mon_cb),
    .clk(clk),
    .rst_n_sys(rst_n_sys),
    .mon_valid(mon_valid),
    .req(w_req)
  );

  // --- Stimuli Generator (Replaces m_sqr) ---
  stimuli_fsm_wide sqr_fsm (
    .clk(clk), .rst_n(rst_n_sys), .seed(seed_ext),
    .req_seed_load(req_seed_load_ext),
    .req_valid(w_valid), .req_ready(w_ready),
    .req(w_req), .rsp_valid(w_rsp_valid), .rsp_ready(w_rsp_ready)
  );

  cov_rtl m_cov (
    .clk(clk),
    .rst_n_sys(rst_n_sys),
    .req_seed_load_ext(req_seed_load_ext),
    .seed_ext(seed_ext)
  );

endmodule

// --- Top-Level Wrapper: tb_synth ---
module tb_synth;
  logic clk;
  logic rst_n_sys;

  // Top-level extensions & monitor signals
  logic        req_seed_load_ext;
  logic [31:0] seed_ext;
  logic        mon_valid;
  mon_data mon_out;

  // Clock generation
  initial begin
    clk = 0;
    forever #10 clk = ~clk;
  end

  // DUT Instance (Assuming standard hookups to vif)
  dut u_dut (
    .clk    (clk),
    .rst_n  (vif_inst.rst_n),
    .re     (vif_inst.re),
    .we     (vif_inst.we),
    .addr_i (vif_inst.addr_i),
    .data_i (vif_inst.data_i),
    .data_o (vif_inst.data_o)
  );

  // UVM Synthesized Hierarchy Root
  example1basic_rtl u_uvm_top (
    .clk               (clk),
    .rst_n_sys         (rst_n_sys),
    .vif               (vif_inst),
    .req_seed_load_ext (req_seed_load_ext),
    .seed_ext          (seed_ext),
    .mon_valid         (mon_valid),
    .mon_out           (mon_out)
  );

  // System Reset Init
  initial begin
    rst_n_sys = 1'b0;
    req_seed_load_ext = 1'b0;
    seed_ext = 32'h0;
    repeat(5) @(posedge clk);
    rst_n_sys = 1'b1;
  end

endmodule
