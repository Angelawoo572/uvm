`default_nettype none

// --- Leaf Module: drv_rtl ---
module drv_rtl #(
  parameter int DATA_WIDTH = 32,
  parameter int ADDR_WIDTH = 16
)(
  input  logic clk,
  input  logic rst_n_sys,
  
  itf.drv_cb vif,

  output logic      req_valid,
  input  logic      req_ready,
  output logic      rsp_ready,
  input  logic      rsp_valid,
  input  data_to_driver_t   req
);
    typedef enum logic [2:0] {
      S_RESET, 
      S_REQ_ITEM, 
      S_WAIT_RSP, 
      S_DRIVE
    } state_t;
    
    state_t state, next_state;
    data_to_driver_t temp;
    always_ff @(posedge clk or negedge rst_n_sys) begin
      if (!rst_n_sys) begin
        state <= S_RESET;
      end else begin
        state <= next_state;
        if (state == S_WAIT_RSP && rsp_valid) begin
          temp <= req; 
        end
        if (state == S_DRIVE) begin
          vif.rst_n <= temp.rst_n;
          vif.addr_i <= temp.addr_i;
          vif.we <= temp.we;
          vif.re <= temp.re;
        end
      end
    end

    always_comb begin
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
endmodule