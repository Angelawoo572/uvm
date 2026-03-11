/* @Brief Datapath/FSM for constraint solver. 
Solves constraints in two clock cycles. Outputs are registered*/
module stimuli_fsm (
    seq_stim_if.STIM stim_if
);
    localparam DATA_W = stim_if.DATA_W;
    localparam NUM_CONSTRAINTS = stim_if.NUM_CONSTRAINTS;

    // Bounded LFSR
    logic lfsr_enable, lfsr_seed_load, lfsr_valid;
    logic [DATA_W-1:0] lfsr_output;
    bounded_LFSR #(.W(DATA_W)) lfsr (
        .clk(stim_if.clk),
        .rst_n(stim_if.rst_n),
        .enable(lfsr_enable),
        .seed(stim_if.seed),
        .seed_load(lfsr_seed_load),
        .lo(stim_if.lower_bound),
        .hi(stim_if.upper_bound),
        .addr(lfsr_output),
        .valid(lfsr_valid),
        .diff()
    );

    // Connect lfsr_output to constraint solvers
    logic [DATA_W-1:0] solver_output [NUM_CONSTRAINTS];
    // TODO: implement constraint solvers here
    // e.g. constraint_id = 0: odd, 1: even
    assign solver_output[0] = {lfsr_output[DATA_W-1:1], 1'b1};
    assign solver_output[1] = {lfsr_output[DATA_W-1:1], 1'b0};

    // Register seed and bounds when request is valid
    logic lfsr_req_load;
    logic [$clog2(NUM_CONSTRAINTS)-1:0] registered_constraint_id;
    logic [DATA_W-1:0] registered_upper_bound, registered_lower_bound;

    always_ff @(posedge stim_if.clk) begin
        if (lfsr_req_load) begin
            registered_constraint_id <= stim_if.constraint_id;
            registered_upper_bound <= stim_if.upper_bound;
            registered_lower_bound <= stim_if.lower_bound;
        end
    end
    assign stim_if.solved_data = solver_output[registered_constraint_id];

    /* FSM
       Status points: lfsr_valid
       Control points: lfsr_enable
       Inputs: stim_if.req_valid, stim_if.rsp_ready, stim_if.req_seed_load
       Outputs: stim_if.req_ready, stim_if.rsp_valid */
    typedef enum logic [1:0] 
        {WAIT, SEED_LOAD, SOLVED} state_t;
    state_t state, nextState;

    always_ff @(posedge stim_if.clk, negedge stim_if.rst_n) begin
        if (!stim_if.rst_n)
            state <= WAIT;
        else 
            state <= nextState;
    end

    always_comb begin
        lfsr_enable = 0;
        lfsr_seed_load = 0;
        lfsr_req_load = 0;
        stim_if.req_ready = 0;
        stim_if.rsp_valid = 0;

        case (state)
            WAIT: begin
                if (stim_if.req_seed_load) begin
                    lfsr_seed_load = 1'b1;
                    nextState = SEED_LOAD;
                end
                else    
                    nextState = WAIT;
            end

            SEED_LOAD: begin
                stim_if.req_ready = 1'b1;
                if (stim_if.req_valid) begin
                    lfsr_enable = 1'b1;
                    lfsr_req_load = 1'b1;
                    nextState = SOLVED;
                end
                else
                    nextState = SEED_LOAD;
            end

            SOLVED: begin
                if (stim_if.rsp_ready) begin
                    if (lfsr_valid) begin
                        stim_if.rsp_valid = 1'b1;
                        nextState = SEED_LOAD;
                    end
                    else begin
                        lfsr_enable = 1'b1;
                        nextState = SOLVED;
                    end
                end
                else begin
                    if (lfsr_valid) 
                        nextState = SOLVED;
                    else begin
                        lfsr_enable = 1'b1;
                        nextState = SOLVED;
                    end
                end
            end
        endcase
    end

endmodule