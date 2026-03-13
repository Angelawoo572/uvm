`default_nettype none
`include "../brendan_work/seq_stim_if.svh"
/*
Method 3 now implements a seed-selected permutation 
over the legal enum subset [RAM:ROM].
*/

module stimuli_fsm_method3 (
    seq_stim_if.STIM stim_if
);
    typedef enum logic [31:0] {
        RAM  = 32'd0,
        CPU  = 32'd1,
        ROM  = 32'd2,
        ROM2 = 32'd123,
        CPU2 = 32'd124
    } addr_t;

    typedef enum logic [0:0] {IDLE, RESP} state_t;
    state_t state;

    logic [31:0] seed_reg;
    logic [1:0]  idx;
    logic [2:0]  perm_sel;
    addr_t       addr_enum;

    always_comb begin
        unique case (perm_sel)
            3'd0: begin
                unique case (idx)
                    2'd0: addr_enum = RAM;
                    2'd1: addr_enum = CPU;
                    default: addr_enum = ROM;
                endcase
            end
            3'd1: begin
                unique case (idx)
                    2'd0: addr_enum = RAM;
                    2'd1: addr_enum = ROM;
                    default: addr_enum = CPU;
                endcase
            end
            3'd2: begin
                unique case (idx)
                    2'd0: addr_enum = CPU;
                    2'd1: addr_enum = RAM;
                    default: addr_enum = ROM;
                endcase
            end
            3'd3: begin
                unique case (idx)
                    2'd0: addr_enum = CPU;
                    2'd1: addr_enum = ROM;
                    default: addr_enum = RAM;
                endcase
            end
            3'd4: begin
                unique case (idx)
                    2'd0: addr_enum = ROM;
                    2'd1: addr_enum = RAM;
                    default: addr_enum = CPU;
                endcase
            end
            default: begin
                unique case (idx)
                    2'd0: addr_enum = ROM;
                    2'd1: addr_enum = CPU;
                    default: addr_enum = RAM;
                endcase
            end
        endcase
    end

    assign stim_if.solved_data = addr_enum;
    assign stim_if.req_ready   = (state == IDLE);
    assign stim_if.rsp_valid   = (state == RESP);

    always_ff @(posedge stim_if.clk or negedge stim_if.rst_n) begin
        if (!stim_if.rst_n) begin
            state    <= IDLE;
            seed_reg <= 32'h1;
            idx      <= 2'd0;
            perm_sel <= 3'd0;
        end else begin
            case (state)
                IDLE: begin
                    if (stim_if.req_seed_load)
                        seed_reg <= (stim_if.seed == '0) ? 32'h1 : stim_if.seed;

                    if (stim_if.req_valid) begin
                        perm_sel <= seed_reg % 6;
                        state    <= RESP;
                    end
                end

                RESP: begin
                    if (stim_if.rsp_ready) begin
                        if (idx == 2'd2)
                            idx <= 2'd0;
                        else
                            idx <= idx + 2'd1;
                        state <= IDLE;
                    end
                end
            endcase
        end
    end
endmodule : stimuli_fsm_method3


module tb_method3;
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

    stimuli_fsm_method3 dut (.stim_if(stim_if));

    always #5 clk = ~clk;

    function automatic string enum_name(input logic [31:0] x);
        case (x)
            32'd0:   enum_name = "RAM";
            32'd1:   enum_name = "CPU";
            32'd2:   enum_name = "ROM";
            32'd123: enum_name = "ROM2";
            32'd124: enum_name = "CPU2";
            default: enum_name = "UNKNOWN";
        endcase
    endfunction

    task automatic reset();
        rst_n = 0;
        stim_if.req_seed_load = 0;
        stim_if.req_valid     = 0;
        stim_if.rsp_ready     = 0;
        stim_if.seed          = '0;
        stim_if.lower_bound   = '0;
        stim_if.upper_bound   = '0;
        stim_if.constraint_id = 32'd3;
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

    task automatic request_enum_once(output logic [31:0] out_val);
        wait(stim_if.req_ready);
        @(posedge clk);
        stim_if.req_valid <= 1'b1;
        stim_if.rsp_ready <= 1'b1;

        @(posedge clk);
        stim_if.req_valid <= 1'b0;

        wait(stim_if.rsp_valid);
        @(posedge clk);
        out_val = stim_if.solved_data;
        $display("[M3] solved_data=%0d (%s)", out_val, enum_name(out_val));

        if (!((out_val == 32'd0) ||
              (out_val == 32'd1) ||
              (out_val == 32'd2))) begin
            $display("ERROR: method3 output not in legal enum subset");
            $finish;
        end

        stim_if.rsp_ready <= 1'b0;
    endtask

    task automatic run_seed(input logic [31:0] s);
        logic [31:0] a, b, c;
        $display("\n---- seed = %0d ----", s);
        load_seed(s);
        request_enum_once(a);
        request_enum_once(b);
        request_enum_once(c);
        $display("Permutation for seed %0d: %s -> %s -> %s",
                 s, enum_name(a), enum_name(b), enum_name(c));
    endtask

    initial begin
        clk = 0;
        reset();

        run_seed(32'd0);
        run_seed(32'd1);
        run_seed(32'd2);
        run_seed(32'd3);
        run_seed(32'd4);
        run_seed(32'd5);

        #20;
        $finish;
    end
endmodule: tb_method3
