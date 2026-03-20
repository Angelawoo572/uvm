`default_nettype none
`include "../stimuli_fsm/seq_stim_if.svh"
/*
File 2 uses a shared reusable polynomial-based LFSR module (`lfsr_poly`).
The methods no longer implement their own LFSR logic; instead, they consume a
common LFSR output controlled by an enable signal.
This version is more modular and parameterizable than File 1.
*/

// ============================================================
// Shared polynomial LFSR
// Fibonacci, shift-left, insert feedback at LSB
//
// Example primitive-polynomial-based taps:
//   W=4  : x^4  + x   + 1
//   W=8  : x^8  + x^6 + x^5 + x + 1
//   W=16 : x^16 + x^5 + x^3 + x^2 + 1
//   W=20 : x^20 + x^3 + 1
//   W=32 : x^32 + x^22 + x^2 + x + 1
// ============================================================
module lfsr_poly #(
    parameter int W = 32
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         enable,
    input  logic         seed_load,
    input  logic [W-1:0] seed,
    output logic [W-1:0] state
);

    logic feedback;
    logic [W-1:0] next_state;

    always_comb begin
        unique case (W)
            4:  feedback = state[3]  ^ state[0];                         
            // x^4  + x + 1
            8:  feedback = state[7]  ^ state[5] ^ state[4] ^ state[0];  
            // x^8  + x^6 + x^5 + x + 1
            16: feedback = state[15] ^ state[4] ^ state[2] ^ state[1];  
            // x^16 + x^5 + x^3 + x^2 + 1
            20: feedback = state[19] ^ state[2];                         
            // x^20 + x^3 + 1
            32: feedback = state[31] ^ state[21] ^ state[1] ^ state[0]; 
            // x^32 + x^22 + x^2 + x + 1
            default: feedback = state[W-1] ^ state[0];
        endcase
    end

    assign next_state = {state[W-2:0], feedback};

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= 'h1; // avoid all-zero lock-up
        end else if (seed_load) begin
            state <= (seed == '0) ? 'h1 : seed;
        end else if (enable) begin
            state <= next_state;
        end
    end

endmodule : lfsr_poly

/*
*I use a shared polynomial-based LFSR as the internal candidate generator.
With a nonzero seed and primitive-polynomial taps, 
the internal LFSR state sequence is maximal-length.
Method 1 and Method 2 then filter that sequence according to range constraints,
while Method 3 maps the LFSR state into a legal enum subset.
Therefore, the internal generator is maximal-length, 
but the final constrained outputs are not themselves maximal-length sequences.
*/


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

    logic [DATA_W-1:0] lfsr_value;
    logic              lfsr_enable;
    logic [DATA_W-1:0] lo_reg, hi_reg;
    logic [DATA_W-1:0] candidate_reg;

    assign stim_if.req_ready   = (state == IDLE);
    assign stim_if.rsp_valid   = (state == RESP);
    assign stim_if.solved_data = candidate_reg;

    lfsr_poly #(
        .W(DATA_W)
    ) u_lfsr (
        .clk      (stim_if.clk),
        .rst_n    (stim_if.rst_n),
        .enable   (lfsr_enable),
        .seed_load(stim_if.req_seed_load),
        .seed     (stim_if.seed),
        .state    (lfsr_value)
    );

    function automatic logic in_range_inclusive(
        input logic [DATA_W-1:0] x,
        input logic [DATA_W-1:0] lo,
        input logic [DATA_W-1:0] hi
    );
        begin
            in_range_inclusive = (lo <= hi) && (x >= lo) && (x <= hi);
        end
    endfunction

    always_comb begin
        lfsr_enable = 1'b0;
        case (state)
            IDLE: begin
                if (stim_if.req_valid)
                    lfsr_enable = 1'b1;
            end
            SEARCH: begin
                lfsr_enable = 1'b1;
            end
            default: begin
                lfsr_enable = 1'b0;
            end
        endcase
    end

    always_ff @(posedge stim_if.clk or negedge stim_if.rst_n) begin
        if (!stim_if.rst_n) begin
            state         <= IDLE;
            lo_reg        <= '0;
            hi_reg        <= '0;
            candidate_reg <= '0;
        end else if (!stim_if.req_seed_load) begin
            case (state)
                IDLE: begin
                    if (stim_if.req_valid) begin
                        lo_reg <= stim_if.lower_bound;
                        hi_reg <= stim_if.upper_bound;
                        if (in_range_inclusive(lfsr_value, stim_if.lower_bound, stim_if.upper_bound)) begin
                            candidate_reg <= lfsr_value;
                            state         <= RESP;
                        end else begin
                            state         <= SEARCH;
                        end
                    end
                end

                SEARCH: begin
                    if (in_range_inclusive(lfsr_value, lo_reg, hi_reg)) begin
                        candidate_reg <= lfsr_value;
                        state         <= RESP;
                    end
                end

                RESP: begin
                    if (stim_if.rsp_ready) begin
                        state <= IDLE;
                    end
                end

                default: state <= IDLE;
            endcase
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

    logic [DATA_W-1:0] lfsr_value;
    logic              lfsr_enable;
    logic [DATA_W-1:0] lo_reg, hi_reg;
    logic [DATA_W-1:0] candidate_reg;

    assign stim_if.req_ready   = (state == IDLE);
    assign stim_if.rsp_valid   = (state == RESP);
    assign stim_if.solved_data = candidate_reg;

    lfsr_poly #(
        .W(DATA_W)
    ) u_lfsr (
        .clk      (stim_if.clk),
        .rst_n    (stim_if.rst_n),
        .enable   (lfsr_enable),
        .seed_load(stim_if.req_seed_load),
        .seed     (stim_if.seed),
        .state    (lfsr_value)
    );

    function automatic logic in_range_exclusive(
        input logic [DATA_W-1:0] x,
        input logic [DATA_W-1:0] lo,
        input logic [DATA_W-1:0] hi
    );
        begin
            in_range_exclusive = (hi > lo + 1'b1) && (x > lo) && (x < hi);
        end
    endfunction

    always_comb begin
        lfsr_enable = 1'b0;
        case (state)
            IDLE: begin
                if (stim_if.req_valid)
                    lfsr_enable = 1'b1;
            end
            SEARCH: begin
                lfsr_enable = 1'b1;
            end
            default: begin
                lfsr_enable = 1'b0;
            end
        endcase
    end

    always_ff @(posedge stim_if.clk or negedge stim_if.rst_n) begin
        if (!stim_if.rst_n) begin
            state         <= IDLE;
            lo_reg        <= '0;
            hi_reg        <= '0;
            candidate_reg <= '0;
        end else if (!stim_if.req_seed_load) begin
            case (state)
                IDLE: begin
                    if (stim_if.req_valid) begin
                        lo_reg <= stim_if.lower_bound;
                        hi_reg <= stim_if.upper_bound;
                        if (in_range_exclusive(lfsr_value, stim_if.lower_bound, stim_if.upper_bound)) begin
                            candidate_reg <= lfsr_value;
                            state         <= RESP;
                        end else begin
                            state         <= SEARCH;
                        end
                    end
                end

                SEARCH: begin
                    if (in_range_exclusive(lfsr_value, lo_reg, hi_reg)) begin
                        candidate_reg <= lfsr_value;
                        state         <= RESP;
                    end
                end

                RESP: begin
                    if (stim_if.rsp_ready) begin
                        state <= IDLE;
                    end
                end

                default: state <= IDLE;
            endcase
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

    logic [DATA_W-1:0] lfsr_value;
    logic              lfsr_enable;
    logic [DATA_W-1:0] candidate_reg;
    logic [1:0]        sel;
    addr_t             addr_enum;

    assign stim_if.req_ready   = (state == IDLE);
    assign stim_if.rsp_valid   = (state == RESP);
    assign stim_if.solved_data = candidate_reg;

    lfsr_poly #(
        .W(DATA_W)
    ) u_lfsr (
        .clk      (stim_if.clk),
        .rst_n    (stim_if.rst_n),
        .enable   (lfsr_enable),
        .seed_load(stim_if.req_seed_load),
        .seed     (stim_if.seed),
        .state    (lfsr_value)
    );

    always_comb begin
        sel = lfsr_value[1:0];
        unique case (sel)
            2'd0: addr_enum = RAM;
            2'd1: addr_enum = CPU;
            default: addr_enum = ROM; // 2 or 3 -> ROM
        endcase
    end

    always_comb begin
        lfsr_enable = 1'b0;
        if ((state == IDLE) && stim_if.req_valid)
            lfsr_enable = 1'b1;
    end

    always_ff @(posedge stim_if.clk or negedge stim_if.rst_n) begin
        if (!stim_if.rst_n) begin
            state         <= IDLE;
            candidate_reg <= '0;
        end else if (!stim_if.req_seed_load) begin
            case (state)
                IDLE: begin
                    if (stim_if.req_valid) begin
                        candidate_reg <= {{(DATA_W-8){1'b0}}, addr_enum};
                        state         <= RESP;
                    end
                end

                RESP: begin
                    if (stim_if.rsp_ready) begin
                        state <= IDLE;
                    end
                end

                default: state <= IDLE;
            endcase
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
        .clk  (clk),
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

        request_inclusive(32'd0,    32'd255);
        request_inclusive(32'd100,  32'd5000);
        request_inclusive(32'd1000, 32'd100000);
        request_inclusive(32'd1,    32'd3);

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
        .clk  (clk),
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

        request_exclusive(32'd0,     32'd10);
        request_exclusive(32'd100,   32'd5000);
        request_exclusive(32'd1234,  32'd5555);
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
        .clk  (clk),
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