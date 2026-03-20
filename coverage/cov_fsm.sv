// Interfaces with orchestrator and monitor
// SAMPLE module, eventually want to generate this with a script
// start/done for control, valid/ready for data

/*  Questions
    Does this FSM need to talk with the sequencer for procedural sampling?
    Otherwise cov needs some notion of ordering/sequencing
    sample_data could be many different signals
    TODO:
    how to output data to user
    implement both tables for cross coverage and then synthesize and compare(!)
    update top level block diagram
*/

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
    input logic [WIDTH-1:0] data // TODO parameterize
);

    // instantiate coverage module...
    // module X_coverage_module X (ports)

    txuart tx (
		// {{{
		.i_clk, 
        .i_reset,
		.i_setup(i_setup),
		.i_break,
		.i_wr,
		.i_data,
		// Hardware flow control Ready-To-Send bit.  Set this to one to
		// use the core without flow control.  (A more appropriate name
		// would be the Ready-To-Receive bit ...)
		.i_cts_n,
		// And the UART input line itself
		.o_uart_tx,
		// A line to tell others when we are ready to accept data.  If
		// (i_wr)&&(!o_busy) is ever true, then the core has accepted a
		// byte for transmission.
		._busy
		// }}}
	);

    // configuration bits
    logic [31:0] i_setup;
    logic flow_control = 2'b00;
    logic data_bits = 2'b00;
    logic stop_bits = 1'b0;
    logic parity_bits = 3'b000;
    logic baud = 24'd5208; // 9600 baud, 50MHz / 9600
    assign i_setup = {flow_control, data_bits, stop_bits, parity, baud};

    enum logic[1:0] {s_idle, s_run, s_done, s_sending} state_n, state_p;

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

    // pseudo code for sending data out
    // packet structure - <signal_name> <data> <EOL>
    // all signals are 1 dimensional
    for output in coverage {
        if (o_uart_tx) {
            send_data();
        }
    }

endmodule
