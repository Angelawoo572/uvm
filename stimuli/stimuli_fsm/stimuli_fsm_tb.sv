`default_nettype none

module stimuli_fsm_tb();
    localparam int DATA_W = 32;
    localparam int NUM_CONSTRAINTS = 4;
    logic clk, rst_n;
    seq_stim_if #(
        .DATA_W(DATA_W),
        .NUM_CONSTRAINTS(NUM_CONSTRAINTS)
    ) seq_stim_if_inst (
        .clk,
        .rst_n
    );

    stimuli_fsm stimuli_fsm_inst (
        .stim_if(seq_stim_if_inst)
    );

    task automatic reset();
        rst_n <= 0;
        @(posedge clk);
        @(posedge clk);
        rst_n <= 1'b1;
    endtask

    task automatic load_seed(bit [31:0] seed);
        seq_stim_if_inst.req_seed_load <= 1'b1;
        seq_stim_if_inst.seed <= seed;
        wait(seq_stim_if_inst.req_ready);
    endtask

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

    // initial begin
    //     $monitor(
    //         $time,,
    //         "state=%s, ", stimuli_fsm_inst.state.name(),
    //         "lfsr_valid=%b, ", stimuli_fsm_inst.lfsr_valid,
    //         "lfsr_output=%h, ", stimuli_fsm_inst.lfsr_output,
    //         "req_valid=%b, ", seq_stim_if_inst.req_valid,
    //         "req_ready=%b, ", seq_stim_if_inst.req_ready,
    //         "rsp_ready=%b, ", seq_stim_if_inst.rsp_ready,
    //         "rsp_valid=%b, ", seq_stim_if_inst.rsp_valid,
    //         "solved_data=%h, ", seq_stim_if_inst.solved_data
    //     );
    // end

    initial begin
        clk = 0;
        forever #5 clk <= ~clk;
    end
    
    // collection data
    bit [DATA_W-1:0] collected_data[NUM_CONSTRAINTS][$]; // queue per constraint_id

    // Add this always block to collect data
    always @(posedge clk) begin
        if (seq_stim_if_inst.rsp_valid === 1'b1) begin
            collected_data[seq_stim_if_inst.constraint_id].push_back(
                seq_stim_if_inst.solved_data
            );
        end
    end

    initial begin
        reset();
        load_seed(32'hF234567);
        repeat(10) // e.g. inside 32'h56789 and 32'hFAAFFA0
            request_data(2'b0, 32'h00056789, 32'hFAAFFA0);
        repeat(10) // e.g. addr < 32'hFFFF
            request_data(2'b0, 32'h0, 32'hFFFF);
        repeat(10) // e.g. addr > 32'h0000FFFF
            request_data(2'b0, 32'h0000FFFF, 32'hFFFFFFFF);
        repeat(20) // e.g. dist
            request_data(2'b1, 32'h0, 32'hFFFFFFFF);
        repeat(10) // e.g. parity
            request_data(2'd2, 32'h0, 32'hFFFFFFFF);
        repeat (10) // e.g. enum
            request_data(2'd3, 32'h0, 32'hFFFFFFFF);
        
        // Display collected results
        begin
            for (int cid = 0; cid < NUM_CONSTRAINTS; cid++) begin
                $display("\n=== Constraint ID %0d: %0d values collected ===", 
                        cid, collected_data[cid].size());
                foreach (collected_data[cid][i]) begin
                    $display("  [%0d] 0x%08h (%0d)", i, collected_data[cid][i], collected_data[cid][i]);
                end
            end
        end

        #1;
        $finish;
    end


endmodule: stimuli_fsm_tb