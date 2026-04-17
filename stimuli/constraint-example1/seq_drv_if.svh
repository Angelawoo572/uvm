`default_nettype none

interface seq_drv_if (
    input logic clk,
    input logic rst_n
);
    // Data from seq_fsm to drv
    req_item_s data_to_driver;

    // Handshake
    logic req_valid;
    logic req_ready;
    logic rsp_valid;
    logic rsp_ready;

    modport SEQ (
        input clk,
        input rst_n,

        output data_to_driver,
        output req_valid,
        input req_ready,

        input rsp_valid,
        output rsp_ready
    );

    modport DRV (
        input clk,
        input rst_n,

        input data_to_driver,
        input req_valid,
        output req_ready,

        output rsp_valid,
        input rsp_ready
    );

endinterface
