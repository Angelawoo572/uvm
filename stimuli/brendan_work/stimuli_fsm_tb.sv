`default_nettype none

module stimuli_fsm_tb();
    logic clk, rst_n;
    seq_stim_if #(
        .DATA_W(8),
        .NUM_CONSTRAINTS(2)
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

    // TO fix: FSM immediately asserts req_ready, but requries additional cycle to load seed
    task automatic get_data(); // constraint_id = 0
        seq_stim_if_inst.req_seed_load <= 1'b1;
        seq_stim_if_inst.seed <= 8'h10;

        wait(seq_stim_if_inst.req_ready);

        seq_stim_if_inst.req_seed_load <= 1'b0;
        seq_stim_if_inst.lower_bound <= 8'h0;
        seq_stim_if_inst.upper_bound <= 8'h12;
        seq_stim_if_inst.constraint_id <= 1'b0;
        seq_stim_if_inst.req_valid <= 1'b1;
        seq_stim_if_inst.rsp_ready <= 1'b1;

        @(posedge clk);
        seq_stim_if_inst.req_valid <= 1'b0;
        seq_stim_if_inst.rsp_ready <= 1'b1;

        @(posedge clk);
        wait(seq_stim_if_inst.rsp_valid==1'b1);
        @(posedge clk);
        seq_stim_if_inst.rsp_ready <= 1'b0;

        wait(seq_stim_if_inst.req_ready);

        seq_stim_if_inst.lower_bound <= 8'h20;
        seq_stim_if_inst.upper_bound <= 8'h30;
        seq_stim_if_inst.constraint_id <= 1'b1;
        seq_stim_if_inst.req_valid <= 1'b1;

        @(posedge clk);
        seq_stim_if_inst.req_valid <= 1'b0;
        seq_stim_if_inst.rsp_ready <= 1'b1;

        @(posedge clk);
        wait(seq_stim_if_inst.rsp_valid);
        @(posedge clk);
        seq_stim_if_inst.rsp_ready <= 1'b0;
    endtask

    initial begin
        $monitor(
            $time,,
            "state=%s, ", stimuli_fsm_inst.state.name(),
            "lfsr_valid=%b, ", stimuli_fsm_inst.lfsr_valid,
            "lfsr_output=%h, ", stimuli_fsm_inst.lfsr_output,
            "req_valid=%b, ", seq_stim_if_inst.req_valid,
            "req_ready=%b, ", seq_stim_if_inst.req_ready,
            "rsp_ready=%b, ", seq_stim_if_inst.rsp_ready,
            "rsp_valid=%b, ", seq_stim_if_inst.rsp_valid,
            "solved_data=%h, ", seq_stim_if_inst.solved_data
        );
    end
    initial begin
        clk = 0;
        forever #5 clk <= ~clk;
    end

    initial begin
        reset();
        get_data();
        #1;
        $finish;
    end
endmodule: stimuli_fsm_tb