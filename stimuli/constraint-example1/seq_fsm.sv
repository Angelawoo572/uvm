module seq_fsm (
    seq_stim_if.SEQ seq_if,
    logic start
);  
/*
  1) Load seed
  2) Request from stimuli_fsm using req_data_t 
  3) Wait for response from stimuli_fsm
  4) Repeat until all required data is received
  5) Send data to driver fsm
*/
    localparam DATA_W = seq_if.DATA_W;
    localparam NUM_CONSTRAINTS = seq_if.NUM_CONSTRAINTS;

    typedef enum logic [2:0] {
      IDLE,
      LOAD_SEED,
      REQ_ITEM,
      WAIT_RSP,
      SEND_TO_DRIVER
    } state_t;
    state_t state;
    localparam state_t SEED_LOAD = LOAD_SEED;

    data_to_driver_t data_to_driver [`NUM_SEQUENCES];
    req_data_t [3:0] req_data [`NUM_SEQUENCES];

    // Sequences
    // req_data[0]
    assign req_data[0][0] = {
      .constraint_id(1),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[0][1] = {
      .constraint_id(0),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[0][2] = {
      .constraint_id(0),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[0][3] = {
      .constraint_id(0),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    // req_data[1]
    assign req_data[1][0] = {
      .constraint_id(2),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[1][1] = {
      .constraint_id(3),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[1][2] = {
      .constraint_id(4),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[1][3] = {
      .constraint_id(5),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    // req_data[2]
    assign req_data[2][0] = {
      .constraint_id(2),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[2][1] = {
      .constraint_id(7),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[2][2] = {
      .constraint_id(4),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[2][3] = {
      .constraint_id(5),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    // req_data[3]
    assign req_data[3][0] = {
      .constraint_id(2),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[3][1] = {
      .constraint_id(11),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[3][2] = {
      .constraint_id(12),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    assign req_data[3][3] = {
      .constraint_id(13),
      .lower_bound(0),
      .upper_bound(32'hFFFF_FFFF)
    };

    // Loop counters
    int seq_idx;
    int item_idx;

    /*
    TODO: Implement FSM:
    1) IDLE: Implemented already
    2) LOAD_SEED: Do the same as load_seed task. seed is hardcoded in `SEED in constants.svh
    */
    // FSM
    always_ff @(posedge seq_if.clk, negedge seq_if.rst_n) begin
      // Default values:
      seq_if.req_seed_load <= '0;
      seq_if.req <= '0;
      seq_if.req_valid <= '0;
      seq_if.rsp_ready <= '0;

      if (!seq_if.rst_n) begin
          state <= IDLE;
          seq_idx <= '0;
          item_idx <= '0;
      end
      else begin
          case (state)
            IDLE: begin
              if (start)
                state <= SEED_LOAD;
            end

            SEED_LOAD: begin
              seq_if.req_seed_load <= 1'b1;
              seq_if.seed <= `SEED;
              state <= REQ_ITEM;
            end

            REQ_ITEM: begin
              if (seq_if.req_ready) begin
                seq_if.req_seed_load <= 1'b0;
                seq_if.req.lower_bound <= req_data[seq_idx][item_idx].lower_bound;
                seq_if.req.upper_bound <= req_data[seq_idx][item_idx].upper_bound;
                seq_if.req.constraint_id <= req_data[seq_idx][item_idx].constraint_id;
                seq_if.req_valid <= 1'b1;
                seq_if.rsp_ready <= 1'b1;
                state <= WAIT_RSP;
              end
            end

            WAIT_RSP: begin
              seq_if.req_valid <= 1'b0;
              seq_if.rsp_ready <= 1'b1;

              if (seq_if.rsp_valid) begin
                case (item_idx)
                  0: data_to_driver[seq_idx].rst_n <= seq_if.solved_data[0];
                  1: data_to_driver[seq_idx].addr_i <= seq_if.solved_data;
                  2: data_to_driver[seq_idx].we <= seq_if.solved_data[0];
                  3: data_to_driver[seq_idx].re <= seq_if.solved_data[0];
                  default: ;
                endcase

                seq_if.rsp_ready <= 1'b0;
                if (item_idx == 3) begin
                  item_idx <= 0;
                  state <= SEND_TO_DRIVER;
                end
                else begin
                  item_idx <= item_idx + 1;
                  state <= REQ_ITEM;
                end
              end
            end

            SEND_TO_DRIVER: begin
              if (seq_idx == (`NUM_SEQUENCES - 1)) begin
                state <= IDLE;
              end
              else begin
                seq_idx <= seq_idx + 1;
                item_idx <= 0;
                state <= REQ_ITEM;
              end
            end
          endcase
      end
    end



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
        seq_if.req.lower_bound <= lower_bound;
        seq_if.req.upper_bound <= upper_bound;
        seq_if.req.constraint_id <= constraint_id;
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