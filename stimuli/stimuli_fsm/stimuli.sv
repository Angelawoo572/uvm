/* @Brief Datapath/FSM for constraint solver. 
Solves constraints in one clock cycle. Outputs are registered*/
module stimuli_fsm (
    seq_stim_if.STIM stim_if
);
    localparam DATA_W = stim_if.DATA_W;
    localparam NUM_CONSTRAINTS = stim_if.NUM_CONSTRAINTS;

    /*  Bounded LFSR:
        Input: seed, lower_bound, upper_bound
        Output: lfsr_output */
    logic [DATA_W-1:0] lfsr_output;
    // TODO: instantiate bounded lfsr

    // Connect lfsr_output to constraint solvers
    logic [DATA_W-1:0] solver_output [NUM_CONSTRAINTS];

    // Mux constraint solvers to solved_data using constraint_id
    logic [$clog2(NUM_CONSTRAINTS)-1:0] registered_constraint_id;
    always_ff @(posedge clock) begin
        registered_constraint_id <= stim_if.constraint_id;
        stim_if.solved_data <= solver_output[registered_constraint_id];
    end


endmodule