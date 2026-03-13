`default_nettype none
`include "../brendan_work/seq_stim_if.svh"
/*
 * M1 handles general interval constraints of the form addr inside [lo:hi].
   It generates values directly inside the legal interval in a seed-dependent 
    bounded traversal order.
   The original whiteboard example can be viewed as a small instance 
   such as [1:8], which is a better demonstration case 
   because the larger domain makes the pseudo-random traversal more visible.
 */

module stimuli_fsm_method1 (
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

    assign range_size = (hi_reg >= lo_reg) ? (hi_reg - lo_reg + 1'b1) : '0;

    always_comb begin
        if (range_size != 0)
            perm_idx = (offset + ((stride * idx) % range_size)) % range_size;
        else
            perm_idx = '0;
    end

    assign stim_if.solved_data = lo_reg + perm_idx;
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

                        if (stim_if.upper_bound >= stim_if.lower_bound) begin
                            logic [DATA_W-1:0] n;
                            n = stim_if.upper_bound - stim_if.lower_bound + 1'b1;
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
endmodule : stimuli_fsm_method1

module tb_method1;
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

    stimuli_fsm_method1 dut (.stim_if(stim_if));

    always #5 clk = ~clk;

    task automatic reset();
        rst_n = 0;
        stim_if.req_seed_load = 0;
        stim_if.req_valid     = 0;
        stim_if.rsp_ready     = 0;
        stim_if.seed          = '0;
        stim_if.lower_bound   = '0;
        stim_if.upper_bound   = '0;
        stim_if.constraint_id = 32'd1;
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

    task automatic request_range(
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
        $display("[M1] solved_data=%0d range=[%0d:%0d]", stim_if.solved_data, lo, hi);
        if (!((stim_if.solved_data >= lo) && (stim_if.solved_data <= hi))) begin
            $display("ERROR: method1 output out of range");
            $finish;
        end
        stim_if.rsp_ready <= 1'b0;
    endtask

    initial begin
        clk = 0;
        reset();
        load_seed(32'd5);

        repeat (8) request_range(32'd1, 32'd8);

        #20;
        $finish;
    end
endmodule : tb_method1
