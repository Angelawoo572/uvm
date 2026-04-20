module seq_fsm (
    seq_stim_if.SEQ seq_if
);  
    localparam DATA_W = seq_if.DATA_W;
    localparam NUM_CONSTRAINTS = seq_if.NUM_CONSTRAINTS;

    task automatic load_seed(bit [31:0] seed);
        seq_if.req_seed_load <= 1'b1;
        seq_if.seed <= seed;
        wait(seq_if.req_ready);
    endtask

    task automatic request_data(
        bit [$clog2(NUM_CONSTRAINTS)-1:0] constraint_id, 
        bit [DATA_W-1:0] lower_bound, upper_bound); 
        wait(seq_if.req_ready);

        seq_if.req_seed_load <= 1'b0;
        seq_if.lower_bound <= lower_bound;
        seq_if.upper_bound <= upper_bound;
        seq_if.constraint_id <= constraint_id;
        seq_if.req_valid <= 1'b1;
        seq_if.rsp_ready <= 1'b1;

        @(posedge seq_if.clk);
        seq_if.req_valid <= 1'b0;
        seq_if.rsp_ready <= 1'b1;

        @(posedge seq_if.clk);
        wait(seq_if.rsp_valid==1'b1);
        @(posedge seq_if.clk);

        seq_if.rsp_ready <= 1'b0;
    endtask

endmodule: seq_fsm