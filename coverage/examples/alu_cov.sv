// Auto-generated SystemVerilog Coverage Model
// Generated from: example.json

module cp_add (
    input logic clk,
    input logic rst_n,
    input logic sample,
    input logic [7:0] a,
    input logic [7:0] b,
    output logic [31:0] zero_cnt,
    output logic [31:0] nonzero_cnt
);

    // Bin Counters for cp_add
    logic [31:0] ctr_r [1:0];
    logic [31:0] ctr_n [1:0];
    
    assign zero_cnt = ctr_r[0];
    assign nonzero_cnt = ctr_r[1];
    
    always_comb begin
        // Default: Hold value
        ctr_n = ctr_r;
    
        case ((a[7:6] & b[7:6]))
            0: ctr_n[0] = ctr_r[0] + 1;
            1, 2, 3: ctr_n[1] = ctr_r[1] + 1;
            default: ; // No bin hit
        endcase
    end
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ctr_r[0] <= '0;
            ctr_r[1] <= '0;
        end else if (sample) begin
            ctr_r <= ctr_n;
        end
    end
endmodule

module cg_add (
    input logic clk,
    input logic rst_n,
    input logic sample,
    input logic [7:0] a,
    input logic [7:0] b,
    output logic [31:0] cp_add_inst_zero_cnt,
    output logic [31:0] cp_add_inst_nonzero_cnt
);


    cp_add cp_add_inst (
        .clk(clk),
        .rst_n(rst_n),
        .sample(sample),
        .a(a),
        .b(b),
        .zero_cnt(cp_add_inst_zero_cnt),
        .nonzero_cnt(cp_add_inst_nonzero_cnt)
    );

endmodule

module alu_coverage_model (
    input logic clk,
    input logic rst_n,
    input logic sample,
    input logic [7:0] a,
    input logic [7:0] b,
    output logic [31:0] cg_add_inst_cp_add_inst_zero_cnt,
    output logic [31:0] cg_add_inst_cp_add_inst_nonzero_cnt
);


    cg_add cg_add_inst (
        .clk(clk),
        .rst_n(rst_n),
        .sample(sample),
        .a(a),
        .b(b),
        .cp_add_inst_zero_cnt(cg_add_inst_cp_add_inst_zero_cnt),
        .cp_add_inst_nonzero_cnt(cg_add_inst_cp_add_inst_nonzero_cnt)
    );

endmodule

