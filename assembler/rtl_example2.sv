// ====================================================
// Auto-Generated Synthesizable UVM Testbench
// ====================================================

// --- Packed Struct Definitions ---
typedef struct packed {
  bit [ADDR_WIDTH-1:0] addr_i;
  bit we;
  bit re;
  bit [DATA_WIDTH-1:0] data_i;
  bit rst_n;
} req_item_s;

typedef struct packed {
  logic [DATA_WIDTH-1:0] data_o;
  logic [ARRAY_SIZE-1:0] valid;
} rsp_item_s;

typedef struct packed {
  req_item_s req;
  rsp_item_s rsp;
} full_item_s;

typedef struct packed {
  bit [ADDR_WIDTH-1:0] addr_i;
  bit we;
  bit re;
  bit [DATA_WIDTH-1:0] data_i;
  bit rst_n;
} reset_req_item_s;

interface itf #(
  parameter ADDR_WIDTH = 99,
  parameter DATA_WIDTH = 99,
  parameter ARRAY_SIZE = 99
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
  logic [ARRAY_SIZE-1:0] valid;

  // --- Modports ---
  modport drv_cb (
    input clk,
    output rst_n,
    output re,
    output we,
    output addr_i,
    output data_i,
    input data_o,
    input valid
  );

  modport mon_cb (
    input clk,
    input rst_n,
    input re,
    input we,
    input addr_i,
    input data_i,
    input data_o,
    input valid
  );

endinterface : itf

interface seq_drv_if (
  input logic clk,
  input logic rst_n
);

  // --- Internal Variables ---
  req_item_s req;
  logic req_valid;
  logic req_ready;
  logic rsp_valid;
  logic rsp_ready;

  // --- Modports ---
  modport SEQ (
    input clk,
    input rst_n,
    output req,
    output req_valid,
    output rsp_ready,
    input req_ready,
    input rsp_valid
  );

  modport DRV (
    input clk,
    input rst_n,
    input req,
    input req_valid,
    input rsp_ready,
    output req_ready,
    output rsp_valid
  );

endinterface : seq_drv_if

interface seq_stim_if #(
  parameter DATA_W = 32,
  parameter NUM_CONSTRAINTS = 8
) (
  input logic clk,
  input logic rst_n
);

  // --- Internal Variables ---
  logic [DATA_W-1:0] seed;
  logic req_seed_load;
  logic req_valid;
  logic req_ready;
  req_item_s req;
  logic rsp_valid;
  logic rsp_ready;

  // --- Modports ---
  modport STIM (
    input clk,
    input rst_n,
    input req,
    input seed,
    input req_seed_load,
    input req_valid,
    input rsp_ready,
    output req_ready,
    output solved_data,
    output rsp_valid
  );

  modport SEQ (
    input clk,
    input rst_n,
    input req_ready,
    input solved_data,
    input rsp_valid,
    output req,
    output seed,
    output req_seed_load,
    output req_valid,
    output rsp_ready
  );

endinterface : seq_stim_if

// --- Leaf Module: drv_rtl ---
module drv_rtl #(
  parameter int DATA_WIDTH = 32,
  parameter int ADDR_WIDTH = 16
) (
  itf.drv_cb vif,
  seq_drv_if.DRV seq_drv,
  input  logic      clk,
  input  logic      rst_n_sys
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
  seq_if.req_valid  = 1'b0;
  seq_if.rsp_ready  = 1'b0;

  case (state)
    S_RESET: next_state = S_REQ_ITEM;

    S_REQ_ITEM: begin
      seq_if.req_valid = 1'b1;
      if (seq_if.req_ready) next_state = S_WAIT_RSP;
    end

    S_WAIT_RSP: begin
      seq_if.rsp_ready = 1'b1;
      if (seq_if.rsp_valid) next_state = S_DRIVE;
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
      vif.addr_i <= seq_drv.req.addr_i;
      vif.data_i <= seq_drv.req.data_i;
      vif.re <= seq_drv.req.re;
      vif.we <= seq_drv.req.we;
      vif.rst_n <= seq_drv.req.rst_n;
      rsp <= seq_drv.rsp_item::type_id::create("rsp_item");
      rsp.data_o <= seq_drv.vif.data_o;
      rsp.valid <= seq_drv.vif.valid;
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
  seq_drv_if.DRV seq_drv,
  input  logic      clk,
  input  logic      rst_n_sys,
  output logic      mon_valid,
  output full_item_s item
);
  always_ff @(posedge clk or negedge rst_n_sys) begin
  if (!rst_n_sys) begin
    mon_valid <= 1'b0;
  end else begin
    mon_valid <= 1'b0; // Default to 0, pulses high on write()
    if (vif.rst_n) begin
    mon_valid <= 1'b1;
    end
  end
end

endmodule

// --- Container Module: example2_rtl ---
module example2_rtl #(
  parameter int DATA_WIDTH = 32,
  parameter int ADDR_WIDTH = 16
) (
  itf.drv_cb vif,
  seq_drv_if.DRV seq_drv,
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
  seq_drv_if.DRV seq_drv,
  input  logic      clk,
  input  logic      rst_n_sys,
  output logic      mon_valid,
  input  logic      req_seed_load_ext,
  input  logic      [31:0] seed_ext
);
  agt_rtl m_agt (
    .vif(vif.drv_cb),
    .seq_drv(vif.DRV),
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
  seq_drv_if.DRV seq_drv,
  input  logic      clk,
  input  logic      rst_n_sys,
  output logic      mon_valid,
  input  logic      req_seed_load_ext,
  input  logic      [31:0] seed_ext
);
  seq_stim_if #(.DATA_W(DATA_WIDTH)) stim_bus (.clk (clk), .rst_n (rst_n_sys));
  seq_drv_if drv_bus (.clk (clk), .rst_n (rst_n_sys));
  req_item_s w_req;

  drv_rtl m_drv (
    .vif(vif.drv_cb),
    .seq_drv(vif.DRV),
    .clk(clk),
    .rst_n_sys(rst_n_sys)
  );

  mon_rtl m_mon (
    .vif(vif.mon_cb),
    .seq_drv(vif.DRV),
    .clk(clk),
    .rst_n_sys(rst_n_sys),
    .mon_valid(mon_valid),
    .item(item)
  );


  seq_fsm u_seq_fsm (
    .seq_if  (stim_bus.SEQ),
    .seq_drv (drv_bus.SEQ),
    .start   (1'b1)
  );

  stimuli_fsm u_stimuli_fsm (
    .stim_if (stim_bus.STIM)
  );

  opcodes_cg cov (
    .clk   (clk), .rst_n (rst_n_sys)
    .sample (1'b1),
    .m_item(w_req),
    .collect_cov(),
    .m_item_addr_i_MODE0_cnt(),
    .m_item_addr_i_MODE1_cnt(),
    .m_item_addr_i_MODE2_cnt(),
    .m_item_addr_i_illegal_error()
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
  example2_rtl u_uvm_top (
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
