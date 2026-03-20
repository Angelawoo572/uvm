`default_nettype none
`include "../stimuli_fsm/seq_stim_if.svh"

module stimuli_fsm_method1 (
    seq_stim_if.STIM stim_if
);
    localparam int DATA_W = stim_if.DATA_W;

    typedef enum logic [0:0] {IDLE, RESP} state_t;
    state_t state;

    logic [DATA_W-1:0] seed_reg;
    logic [DATA_W-1:0] lo_reg, hi_reg;
    logic [DATA_W-1:0] range_size;
    logic [DATA_W-1:0] idx, offset;
    logic [DATA_W-1:0] perm_idx;

    assign range_size = (hi_reg >= lo_reg) ? (hi_reg - lo_reg + 1'b1) : '0;

    always_comb begin
        perm_idx = idx + offset;
        if ((range_size != '0) && (perm_idx >= range_size))
            perm_idx = perm_idx - range_size;
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
        end else begin
            case (state)
                IDLE: begin
                    if (stim_if.req_seed_load) begin
                        seed_reg <= (stim_if.seed == '0) ? 'h1 : stim_if.seed;
                    end
                    if (stim_if.req_valid) begin
                        lo_reg <= stim_if.lower_bound;
                        hi_reg <= stim_if.upper_bound;
                        idx    <= idx; // hold until response consumed
                        if (stim_if.upper_bound >= stim_if.lower_bound)
                            offset <= ((stim_if.seed == '0) ? 'h1 : stim_if.seed) %
                                      (stim_if.upper_bound - stim_if.lower_bound + 1'b1);
                        else
                            offset <= '0;
                        state <= RESP;
                    end
                end

                RESP: begin
                    if (stim_if.rsp_ready) begin
                        if ((hi_reg >= lo_reg) && (range_size != '0)) begin
                            if (idx == (range_size - 1'b1))
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
endmodule: stimuli_fsm_method1

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
        stim_if.constraint_id = '0;
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

        repeat (8) request_range(32'd1, 32'd3);

        #20;
        $finish;
    end
endmodule: tb_method1