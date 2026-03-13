// Interfaces with orchestrator and monitor
// SAMPLE module, eventually want to generate this with a script
// start/done for control, valid/ready for data

module cov_fsm #(
    parameter WIDTH = 5
) (
    input logic clk,
    input logic rst,
    
    // cov module
    input logic cov_done,

    // orchestrator
    input logic start,
    input logic stop,
    output logic done,

    // monitor 
    input logic ready,
    output logic valid,
    input logic [WIDTH-1:0] data
);

    enum logic[1:0] {s_idle, s_run, s_done} state_n, state_p;

    always_comb begin
        state_n = state_p;
        case(state_p)
            s_idle: if (start) state_n = s_run;
            s_run: if (stop | cov_done) state_n = s_done;
            s_done: if (ready) state_n = s_idle;
        endcase
    end

    // status
    assign valid = (state_p == s_done);
    assign done = (state_p == s_done);

    always_ff @(posedge clk) begin
        if (reset) state_p = s_idle;
        else state_p = state_n;
    end

endmodule
