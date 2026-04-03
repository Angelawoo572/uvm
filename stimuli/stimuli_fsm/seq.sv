module seq #(

) (

);

    task automatic request_data(
        bit [$clog2(NUM_CONSTRAINTS)-1:0] constraint_id, 
        bit [DATA_W-1:0] lower_bound, upper_bound); 
        wait(seq_stim_if_inst.req_ready);

        seq_stim_if_inst.req_seed_load <= 1'b0;
        seq_stim_if_inst.lower_bound <= lower_bound;
        seq_stim_if_inst.upper_bound <= upper_bound;
        seq_stim_if_inst.constraint_id <= constraint_id;
        seq_stim_if_inst.req_valid <= 1'b1;
        seq_stim_if_inst.rsp_ready <= 1'b1;

        @(posedge clk);
        seq_stim_if_inst.req_valid <= 1'b0;
        seq_stim_if_inst.rsp_ready <= 1'b1;

        @(posedge clk);
        wait(seq_stim_if_inst.rsp_valid==1'b1);
        @(posedge clk);

        seq_stim_if_inst.rsp_ready <= 1'b0;
    endtask

endmodule: seq