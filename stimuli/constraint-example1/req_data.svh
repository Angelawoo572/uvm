typedef struct packed {
  bit [$clog2(`NUM_CONSTRAINTS)-1:0] constraint_id;
  bit [`DATA_W-1:0] lower_bound;
  bit [`DATA_W-1:0] upper_bound;
} req_data_t; // stimuli_fsm to seq_fsm

// cu
typedef struct packed {
  bit rst_n;
  bit [`DATA_W-1:0] addr_i;
  bit we;
  bit re;
} data_to_driver_t; // seq_fsm to driver_fsm

// new 
typedef struct packed {
  bit [ADDR_WIDTH-1:0] addr_i;
  bit we;
  bit re;
  bit [DATA_WIDTH-1:0] data_i;
  logic [DATA_WIDTH-1:0] data_o;
  bit rst_n;
} req_item_s;