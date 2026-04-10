`default_nettype none
`include "constants.svh"

module top #(
    parameter int DATA_W = `DATA_W,
    parameter int NUM_CONSTRAINTS = `NUM_CONSTRAINTS
)(
    input logic clk,
    input logic rst_n,
    input logic start,
    itf.drv_cb vif
);
    seq_stim_if #(
        .DATA_W(DATA_W),
        .NUM_CONSTRAINTS(NUM_CONSTRAINTS)
    ) seq_stim_if_inst (
        .clk(clk),
        .rst_n(rst_n)
    );

    seq_drv_if seq_drv_if_inst (
        .clk(clk),
        .rst_n(rst_n)
    );

    stimuli_fsm stimuli_fsm_inst (
        .stim_if(seq_stim_if_inst)
    );

    seq_fsm seq_fsm_inst (
        .seq_if(seq_stim_if_inst),
        .seq_drv(seq_drv_if_inst),
        .start(start)
    );

    drv_fsm drv_fsm_inst (
        .clk(clk),
        .rst_n_sys(rst_n),
        .vif(vif),
        .seq_drv(seq_drv_if_inst)
    );

endmodule: top
