`default_nettype none

interface seq_stim_if #(
    parameter DATA_W = 32,
    parameter NUM_CONSTRAINTS = 8
)(
    input  logic clk, rst_n
);
    // Request 
    logic [DATA_W-1:0] seed;
    logic [DATA_W-1:0] lower_bound, upper_bound;
    logic [$clog2(NUM_CONSTRAINTS)-1:0] constraint_id;  // some database of constraints
    logic       req_seed_load;
    logic       req_valid;
    logic       req_ready;

    // Response
    logic [DATA_W-1:0] solved_data;
    logic              rsp_valid;
    logic              rsp_ready;
    
    modport STIM (
        input clk, rst_n,

        // Request
        input seed, lower_bound, upper_bound,
        input constraint_id,
        input req_seed_load,
        output req_ready,
        input req_valid,

        // Response
        output solved_data,
        input rsp_ready,
        output rsp_valid
    );

    modport SEQ (
        input clk, rst_n,

        // Request
        output seed, lower_bound, upper_bound,
        output constraint_id,
        output req_seed_load,
        input req_ready,
        output req_valid,

        // Response
        input solved_data,
        output rsp_ready,
        input rsp_valid
    );

endinterface
