typedef struct {
  bit [$clog2(`NUM_CONSTRAINTS)-1:0] constraint_id;
  bit [`DATA_W-1:0] lower_bound;
  bit [`DATA_W-1:0] upper_bound;
} req_data_t;