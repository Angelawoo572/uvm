`default_nettype none
`include "../stimuli_fsm/seq_stim_if.svh"

// ============================================================
// Method 1: inclusive range [lo:hi], LFSR-based search
// ============================================================
module stimuli_fsm_method1 #(
    parameter int DATA_W = 32,
    parameter int NUM_CONSTRAINTS = 8
) (
    seq_stim_if.STIM stim_if
);

    typedef enum logic [1:0] {
        IDLE   = 2'd0,
        SEARCH = 2'd1,
        RESP   = 2'd2
    } state_t;

    state_t state;

    logic [DATA_W-1:0] lfsr_state;
    logic [DATA_W-1:0] lo_reg, hi_reg;
    logic [DATA_W-1:0] candidate_reg;
    logic [DATA_W-1:0] lfsr_next;
    logic feedback;

    // 32-bit Fibonacci LFSR taps
    assign feedback  = lfsr_state[31] ^ lfsr_state[21] ^ lfsr_state[1] ^ lfsr_state[0];
    assign lfsr_next = {lfsr_state[30:0], feedback};

    assign stim_if.req_ready   = (state == IDLE);
    assign stim_if.rsp_valid   = (state == RESP);
    assign stim_if.solved_data = candidate_reg;

    function automatic logic in_range_inclusive(
        input logic [DATA_W-1:0] x,
        input logic [DATA_W-1:0] lo,
        input logic [DATA_W-1:0] hi
    );
        begin
            in_range_inclusive = (lo <= hi) && (x >= lo) && (x <= hi);
        end
    endfunction

    always_ff @(posedge stim_if.clk, negedge stim_if.rst_n) begin
        if (!stim_if.rst_n) begin
            state         <= IDLE;
            lfsr_state    <= 32'h1;
            lo_reg        <= '0;
            hi_reg        <= '0;
            candidate_reg <= '0;
        end else begin
            if (stim_if.req_seed_load) begin
                lfsr_state <= (stim_if.seed == '0) ? 32'h1 : stim_if.seed;
            end else begin
                case (state)
                    IDLE: begin
                        if (stim_if.req_valid) begin
                            lo_reg <= stim_if.lower_bound;
                            hi_reg <= stim_if.upper_bound;

                            lfsr_state <= lfsr_next;

                            if (in_range_inclusive(lfsr_next,
                                                   stim_if.lower_bound,
                                                   stim_if.upper_bound)) begin
                                candidate_reg <= lfsr_next;
                                state         <= RESP;
                            end else begin
                                state         <= SEARCH;
                            end
                        end
                    end

                    SEARCH: begin
                        lfsr_state <= lfsr_next;

                        if (in_range_inclusive(lfsr_next, lo_reg, hi_reg)) begin
                            candidate_reg <= lfsr_next;
                            state         <= RESP;
                        end
                    end

                    RESP: begin
                        if (stim_if.rsp_ready) begin
                            state <= IDLE;
                        end
                    end

                    default: begin
                        state <= IDLE;
                    end
                endcase
            end
        end
    end

endmodule : stimuli_fsm_method1


// ============================================================
// Method 2: exclusive range (lo, hi), LFSR-based search
// ============================================================
module stimuli_fsm_method2 #(
    parameter int DATA_W = 32,
    parameter int NUM_CONSTRAINTS = 8
) (
    seq_stim_if.STIM stim_if
);

    typedef enum logic [1:0] {
        IDLE   = 2'd0,
        SEARCH = 2'd1,
        RESP   = 2'd2
    } state_t;

    state_t state;

    logic [DATA_W-1:0] lfsr_state;
    logic [DATA_W-1:0] lo_reg, hi_reg;
    logic [DATA_W-1:0] candidate_reg;
    logic [DATA_W-1:0] lfsr_next;
    logic feedback;

    assign feedback  = lfsr_state[31] ^ lfsr_state[21] ^ lfsr_state[1] ^ lfsr_state[0];
    assign lfsr_next = {lfsr_state[30:0], feedback};

    assign stim_if.req_ready   = (state == IDLE);
    assign stim_if.rsp_valid   = (state == RESP);
    assign stim_if.solved_data = candidate_reg;

    function automatic logic in_range_exclusive(
        input logic [DATA_W-1:0] x,
        input logic [DATA_W-1:0] lo,
        input logic [DATA_W-1:0] hi
    );
        begin
            in_range_exclusive = (hi > lo + 1'b1) && (x > lo) && (x < hi);
        end
    endfunction

    always_ff @(posedge stim_if.clk, negedge stim_if.rst_n) begin
        if (!stim_if.rst_n) begin
            state         <= IDLE;
            lfsr_state    <= 32'h1;
            lo_reg        <= '0;
            hi_reg        <= '0;
            candidate_reg <= '0;
        end else begin
            if (stim_if.req_seed_load) begin
                lfsr_state <= (stim_if.seed == '0) ? 32'h1 : stim_if.seed;
            end else begin
                case (state)
                    IDLE: begin
                        if (stim_if.req_valid) begin
                            lo_reg <= stim_if.lower_bound;
                            hi_reg <= stim_if.upper_bound;

                            lfsr_state <= lfsr_next;

                            if (in_range_exclusive(lfsr_next,
                                                   stim_if.lower_bound,
                                                   stim_if.upper_bound)) begin
                                candidate_reg <= lfsr_next;
                                state         <= RESP;
                            end else begin
                                state         <= SEARCH;
                            end
                        end
                    end

                    SEARCH: begin
                        lfsr_state <= lfsr_next;

                        if (in_range_exclusive(lfsr_next, lo_reg, hi_reg)) begin
                            candidate_reg <= lfsr_next;
                            state         <= RESP;
                        end
                    end

                    RESP: begin
                        if (stim_if.rsp_ready) begin
                            state <= IDLE;
                        end
                    end

                    default: begin
                        state <= IDLE;
                    end
                endcase
            end
        end
    end

endmodule : stimuli_fsm_method2


// ============================================================
// Method 3: enum subset {RAM, CPU, ROM}, LFSR-driven mapping
// ============================================================
module stimuli_fsm_method3 #(
    parameter int DATA_W = 32,
    parameter int NUM_CONSTRAINTS = 8
) (
    seq_stim_if.STIM stim_if
);

    typedef enum logic [7:0] {
        RAM  = 8'd0,
        CPU  = 8'd1,
        ROM  = 8'd2,
        ROM2 = 8'd123,
        CPU2 = 8'd124
    } addr_t;

    typedef enum logic [1:0] {
        IDLE = 2'd0,
        RESP = 2'd1
    } state_t;

    state_t state;

    logic [31:0] lfsr_state;
    logic [31:0] lfsr_next;
    logic [31:0] candidate_reg;
    logic feedback;
    logic [1:0] sel;
    addr_t addr_enum;

    assign feedback  = lfsr_state[31] ^ lfsr_state[21] ^ lfsr_state[1] ^ lfsr_state[0];
    assign lfsr_next = {lfsr_state[30:0], feedback};

    always_comb begin
        sel = lfsr_next[1:0];
        unique case (sel)
            2'd0: addr_enum = RAM;
            2'd1: addr_enum = CPU;
            default: addr_enum = ROM; // 2 or 3 both map to ROM
        endcase
    end

    assign stim_if.req_ready   = (state == IDLE);
    assign stim_if.rsp_valid   = (state == RESP);
    assign stim_if.solved_data = candidate_reg;

    always_ff @(posedge stim_if.clk, negedge stim_if.rst_n) begin
        if (!stim_if.rst_n) begin
            state         <= IDLE;
            lfsr_state    <= 32'h1;
            candidate_reg <= 32'd0;
        end else begin
            if (stim_if.req_seed_load) begin
                lfsr_state <= (stim_if.seed == '0) ? 32'h1 : stim_if.seed;
            end else begin
                case (state)
                    IDLE: begin
                        if (stim_if.req_valid) begin
                            lfsr_state    <= lfsr_next;
                            candidate_reg <= {{(DATA_W-8){1'b0}}, addr_enum};
                            state         <= RESP;
                        end
                    end

                    RESP: begin
                        if (stim_if.rsp_ready) begin
                            state <= IDLE;
                        end
                    end

                    default: begin
                        state <= IDLE;
                    end
                endcase
            end
        end
    end

endmodule : stimuli_fsm_method3


// ============================================================
// TB for Method 1
// ============================================================
module tb_method1;

    localparam int DATA_W = 32;
    localparam int NUM_CONSTRAINTS = 8;

    logic clk, rst_n;

    seq_stim_if #(
        .DATA_W(DATA_W),
        .NUM_CONSTRAINTS(NUM_CONSTRAINTS)
    ) stim_if (
        .clk(clk),
        .rst_n(rst_n)
    );

    stimuli_fsm_method1 #(
        .DATA_W(DATA_W),
        .NUM_CONSTRAINTS(NUM_CONSTRAINTS)
    ) dut (
        .stim_if(stim_if)
    );

    always #5 clk = ~clk;

    task automatic reset_dut();
        begin
            rst_n = 1'b0;
            stim_if.seed          = '0;
            stim_if.lower_bound   = '0;
            stim_if.upper_bound   = '0;
            stim_if.constraint_id = '0;
            stim_if.req_seed_load = 1'b0;
            stim_if.req_valid     = 1'b0;
            stim_if.rsp_ready     = 1'b0;
            repeat (2) @(posedge clk);
            rst_n = 1'b1;
        end
    endtask

    task automatic load_seed(input logic [DATA_W-1:0] s);
        begin
            @(posedge clk);
            stim_if.seed          <= s;
            stim_if.req_seed_load <= 1'b1;
            @(posedge clk);
            stim_if.req_seed_load <= 1'b0;
        end
    endtask

    task automatic request_inclusive(
        input logic [DATA_W-1:0] lo,
        input logic [DATA_W-1:0] hi
    );
        begin
            wait (stim_if.req_ready);
            @(posedge clk);
            stim_if.lower_bound <= lo;
            stim_if.upper_bound <= hi;
            stim_if.req_valid   <= 1'b1;
            stim_if.rsp_ready   <= 1'b1;

            @(posedge clk);
            stim_if.req_valid <= 1'b0;

            wait (stim_if.rsp_valid);
            $display("[M1] solved_data=%0d range=[%0d:%0d]", stim_if.solved_data, lo, hi);

            if (!((stim_if.solved_data >= lo) && (stim_if.solved_data <= hi))) begin
                $display("ERROR: method1 output out of inclusive range");
                $finish;
            end

            @(posedge clk);
            stim_if.rsp_ready <= 1'b0;
        end
    endtask

    initial begin
        clk = 1'b0;
        reset_dut();
        load_seed(32'h0000_00A5);

        request_inclusive(32'd0, 32'd255);
        request_inclusive(32'd100, 32'd5000);
        request_inclusive(32'd1000, 32'd100000);
        request_inclusive(32'd1, 32'd3);

        #50;
        $display("tb_method1 PASSED");
        $finish;
    end

endmodule : tb_method1


// ============================================================
// TB for Method 2
// ============================================================
module tb_method2;

    localparam int DATA_W = 32;
    localparam int NUM_CONSTRAINTS = 8;

    logic clk, rst_n;

    seq_stim_if #(
        .DATA_W(DATA_W),
        .NUM_CONSTRAINTS(NUM_CONSTRAINTS)
    ) stim_if (
        .clk(clk),
        .rst_n(rst_n)
    );

    stimuli_fsm_method2 #(
        .DATA_W(DATA_W),
        .NUM_CONSTRAINTS(NUM_CONSTRAINTS)
    ) dut (
        .stim_if(stim_if)
    );

    always #5 clk = ~clk;

    task automatic reset_dut();
        begin
            rst_n = 1'b0;
            stim_if.seed          = '0;
            stim_if.lower_bound   = '0;
            stim_if.upper_bound   = '0;
            stim_if.constraint_id = '0;
            stim_if.req_seed_load = 1'b0;
            stim_if.req_valid     = 1'b0;
            stim_if.rsp_ready     = 1'b0;
            repeat (2) @(posedge clk);
            rst_n = 1'b1;
        end
    endtask

    task automatic load_seed(input logic [DATA_W-1:0] s);
        begin
            @(posedge clk);
            stim_if.seed          <= s;
            stim_if.req_seed_load <= 1'b1;
            @(posedge clk);
            stim_if.req_seed_load <= 1'b0;
        end
    endtask

    task automatic request_exclusive(
        input logic [DATA_W-1:0] lo,
        input logic [DATA_W-1:0] hi
    );
        begin
            wait (stim_if.req_ready);
            @(posedge clk);
            stim_if.lower_bound <= lo;
            stim_if.upper_bound <= hi;
            stim_if.req_valid   <= 1'b1;
            stim_if.rsp_ready   <= 1'b1;

            @(posedge clk);
            stim_if.req_valid <= 1'b0;

            wait (stim_if.rsp_valid);
            $display("[M2] solved_data=%0d constraint=(%0d,%0d)", stim_if.solved_data, lo, hi);

            if (!((stim_if.solved_data > lo) && (stim_if.solved_data < hi))) begin
                $display("ERROR: method2 output violates exclusive range");
                $finish;
            end

            @(posedge clk);
            stim_if.rsp_ready <= 1'b0;
        end
    endtask

    initial begin
        clk = 1'b0;
        reset_dut();
        load_seed(32'hACE1_1234);

        request_exclusive(32'd0, 32'd10);
        request_exclusive(32'd100, 32'd5000);
        request_exclusive(32'd1234, 32'd5555);
        request_exclusive(32'd10000, 32'd20000);

        #50;
        $display("tb_method2 PASSED");
        $finish;
    end

endmodule : tb_method2


// ============================================================
// TB for Method 3
// ============================================================
module tb_method3;

    localparam int DATA_W = 32;
    localparam int NUM_CONSTRAINTS = 8;

    logic clk, rst_n;

    seq_stim_if #(
        .DATA_W(DATA_W),
        .NUM_CONSTRAINTS(NUM_CONSTRAINTS)
    ) stim_if (
        .clk(clk),
        .rst_n(rst_n)
    );

    stimuli_fsm_method3 #(
        .DATA_W(DATA_W),
        .NUM_CONSTRAINTS(NUM_CONSTRAINTS)
    ) dut (
        .stim_if(stim_if)
    );

    always #5 clk = ~clk;

    function automatic string enum_name(input logic [31:0] x);
        begin
            case (x)
                32'd0:   enum_name = "RAM";
                32'd1:   enum_name = "CPU";
                32'd2:   enum_name = "ROM";
                32'd123: enum_name = "ROM2";
                32'd124: enum_name = "CPU2";
                default: enum_name = "UNKNOWN";
            endcase
        end
    endfunction

    task automatic reset_dut();
        begin
            rst_n = 1'b0;
            stim_if.seed          = '0;
            stim_if.lower_bound   = '0;
            stim_if.upper_bound   = '0;
            stim_if.constraint_id = '0;
            stim_if.req_seed_load = 1'b0;
            stim_if.req_valid     = 1'b0;
            stim_if.rsp_ready     = 1'b0;
            repeat (2) @(posedge clk);
            rst_n = 1'b1;
        end
    endtask

    task automatic load_seed(input logic [DATA_W-1:0] s);
        begin
            @(posedge clk);
            stim_if.seed          <= s;
            stim_if.req_seed_load <= 1'b1;
            @(posedge clk);
            stim_if.req_seed_load <= 1'b0;
        end
    endtask

    task automatic request_enum();
        begin
            wait (stim_if.req_ready);
            @(posedge clk);
            stim_if.req_valid <= 1'b1;
            stim_if.rsp_ready <= 1'b1;

            @(posedge clk);
            stim_if.req_valid <= 1'b0;

            wait (stim_if.rsp_valid);
            $display("[M3] solved_data=%0d (%s)", stim_if.solved_data, enum_name(stim_if.solved_data));

            if (!((stim_if.solved_data == 32'd0) ||
                  (stim_if.solved_data == 32'd1) ||
                  (stim_if.solved_data == 32'd2))) begin
                $display("ERROR: method3 output not in legal enum subset");
                $finish;
            end

            @(posedge clk);
            stim_if.rsp_ready <= 1'b0;
        end
    endtask

    initial begin
        clk = 1'b0;
        reset_dut();
        load_seed(32'h5A5A_00F1);

        repeat (8) begin
            request_enum();
        end

        #50;
        $display("tb_method3 PASSED");
        $finish;
    end

endmodule : tb_method3
