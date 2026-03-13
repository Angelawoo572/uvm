`default_nettype none
`include "../brendan_work/seq_stim_if.svh"
/*
 *The current M2 uses a seeded affine permutation over the legal interval.
  This gives a deterministic bounded traversal with a hard ceiling, 
  but its local numeric pattern can still look somewhat regular 
  because consecutive outputs differ by a constant stride modulo 
  the interval size.

  A future refinement would be to use 
  a stronger seeded permutation network instead of a simple affine mapping.
 */

module stimuli_fsm_method2 (
    seq_stim_if.STIM stim_if
);
    localparam int DATA_W = stim_if.DATA_W;
    localparam int GCD_ITERS = 2*DATA_W;
    localparam int STRIDE_SEARCH = 64;

    typedef enum logic [0:0] {IDLE, RESP} state_t;
    state_t state;

    logic [DATA_W-1:0] seed_reg;
    logic [DATA_W-1:0] lo_reg, hi_reg;
    logic [DATA_W-1:0] range_size;
    logic [DATA_W-1:0] idx;
    logic [DATA_W-1:0] offset;
    logic [DATA_W-1:0] stride;
    logic [DATA_W-1:0] perm_idx;

    function automatic logic [DATA_W-1:0] gcd_func(
        input logic [DATA_W-1:0] a,
        input logic [DATA_W-1:0] b
    );
        logic [DATA_W-1:0] x, y, t;
        int i;
        begin
            x = a;
            y = b;
            for (i = 0; i < GCD_ITERS; i++) begin
                if (y != 0) begin
                    t = x % y;
                    x = y;
                    y = t;
                end
            end
            gcd_func = x;
        end
    endfunction

    function automatic logic [DATA_W-1:0] choose_stride(
        input logic [DATA_W-1:0] seed_val,
        input logic [DATA_W-1:0] n
    );
        logic [DATA_W-1:0] cand;
        logic [DATA_W-1:0] best;
        logic found;
        int i;
        begin
            if (n <= 1) begin
                choose_stride = 0;
            end else begin
                best  = 1;
                found = 1'b0;
                for (i = 0; i < STRIDE_SEARCH; i++) begin
                    cand = 1 + ((seed_val + i) % (n - 1));
                    if (!found && (gcd_func(cand, n) == 1)) begin
                        best  = cand;
                        found = 1'b1;
                    end
                end
                choose_stride = best;
            end
        end
    endfunction

    // exclusive bounds: lower_bound < x < upper_bound
    assign range_size = (hi_reg > lo_reg + 1'b1) ? (hi_reg - lo_reg - 1'b1) : '0;

    always_comb begin
        if (range_size != 0)
            perm_idx = (offset + ((stride * idx) % range_size)) % range_size;
        else
            perm_idx = '0;
    end

    assign stim_if.solved_data = (lo_reg + 1'b1) + perm_idx;
    assign stim_if.req_ready   = (state == IDLE);
    assign stim_if.rsp_valid   = (state == RESP);

    always_ff @(posedge stim_if.clk or negedge stim_if.rst_n) begin
        if (!stim_if.rst_n) begin
            state    <= IDLE;
            seed_reg <= 'h1;
            lo_reg   <= '0;
            hi_reg   <= '0;
            idx      <= '0;
            offset   <= '0;
            stride   <= '0;
        end else begin
            case (state)
                IDLE: begin
                    if (stim_if.req_seed_load)
                        seed_reg <= (stim_if.seed == '0) ? 'h1 : stim_if.seed;

                    if (stim_if.req_valid) begin
                        lo_reg <= stim_if.lower_bound;
                        hi_reg <= stim_if.upper_bound;

                        if (stim_if.upper_bound > (stim_if.lower_bound + 1'b1)) begin
                            logic [DATA_W-1:0] n;
                            n = stim_if.upper_bound - stim_if.lower_bound - 1'b1;
                            offset <= seed_reg % n;
                            stride <= choose_stride(seed_reg, n);
                        end else begin
                            offset <= '0;
                            stride <= '0;
                        end

                        state <= RESP;
                    end
                end

                RESP: begin
                    if (stim_if.rsp_ready) begin
                        if (range_size != 0) begin
                            if (idx == range_size - 1'b1)
                                idx <= '0;
                            else
                                idx <= idx + 1'b1;
                        end
                        state <= IDLE;
                    end
                end
            endcase
        end
    end
endmodule : stimuli_fsm_method2


module tb_method2;
    localparam int DATA_W = 32;
    localparam int NUM_CONSTRAINTS = 4;

    logic clk, rst_n;
    seq_stim_if #(
        .DATA_W(DATA_W),
        .NUM_CONSTRAINTS(NUM_CONSTRAINTS)
    ) stim_if (
        .clk(clk),
        .rst_n(rst_n)
    );

    stimuli_fsm_method2 dut (.stim_if(stim_if));

    always #5 clk = ~clk;

    task automatic reset();
        rst_n = 0;
        stim_if.req_seed_load = 0;
        stim_if.req_valid     = 0;
        stim_if.rsp_ready     = 0;
        stim_if.seed          = '0;
        stim_if.lower_bound   = '0;
        stim_if.upper_bound   = '0;
        stim_if.constraint_id = 32'd2;
        repeat (2) @(posedge clk);
        rst_n = 1;
    endtask

    task automatic load_seed(input logic [DATA_W-1:0] s);
        @(posedge clk);
        stim_if.seed          <= s;
        stim_if.req_seed_load <= 1'b1;
        @(posedge clk);
        stim_if.req_seed_load <= 1'b0;
    endtask

    task automatic request_exclusive(
        input logic [DATA_W-1:0] lo,
        input logic [DATA_W-1:0] hi
    );
        wait(stim_if.req_ready);
        @(posedge clk);
        stim_if.lower_bound <= lo;
        stim_if.upper_bound <= hi;
        stim_if.req_valid   <= 1'b1;
        stim_if.rsp_ready   <= 1'b1;

        @(posedge clk);
        stim_if.req_valid <= 1'b0;

        wait(stim_if.rsp_valid);
        @(posedge clk);
        $display("[M2] solved_data=%0d constraint=(%0d,%0d)", stim_if.solved_data, lo, hi);
        if (!((stim_if.solved_data > lo) && (stim_if.solved_data < hi))) begin
            $display("ERROR: method2 output violates exclusive bounds");
            $finish;
        end
        stim_if.rsp_ready <= 1'b0;
    endtask

    initial begin
        clk = 0;
        reset();
        load_seed(32'hACE1);

        repeat (8) request_exclusive(32'd1234, 32'd5555);

        #20;
        $finish;
    end
endmodule : tb_method2
