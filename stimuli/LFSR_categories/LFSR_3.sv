`default_nettype none

module method3_enum_range (
    input  logic clk,
    input  logic rst_n,
    input  logic enable,
    input  logic [7:0] seed,
    input  logic seed_load,

    output logic [7:0] addr_code,
    output logic       valid
);

    typedef enum logic [7:0] {
        RAM  = 8'd0,
        CPU  = 8'd1,
        ROM  = 8'd2,
        ROM2 = 8'd123,
        CPU2 = 8'd124
    } addr_t;

    logic [1:0] idx;
    logic [1:0] offset;
    logic [1:0] sel;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            idx    <= 2'd0;
            offset <= 2'd0;
        end else if (seed_load) begin
            idx    <= 2'd0;
            offset <= seed % 3;
        end else if (enable) begin
            if (idx == 2'd2)
                idx <= 2'd0;
            else
                idx <= idx + 2'd1;
        end
    end

    always_comb begin
        sel = idx + offset;
        if (sel >= 3)
            sel = sel - 3;

        unique case (sel)
            2'd0: addr_code = RAM;
            2'd1: addr_code = CPU;
            default: addr_code = ROM;
        endcase
    end

    assign valid = 1'b1;

endmodule : method3_enum_range


module tb_method3_enum_range;

    logic clk;
    logic rst_n;
    logic enable;
    logic [7:0] seed;
    logic seed_load;
    logic [7:0] addr_code;
    logic valid;

    method3_enum_range dut (
        .clk(clk),
        .rst_n(rst_n),
        .enable(enable),
        .seed(seed),
        .seed_load(seed_load),
        .addr_code(addr_code),
        .valid(valid)
    );

    always #5 clk = ~clk;

    function automatic string enum_name(input logic [7:0] x);
        case (x)
            8'd0:   enum_name = "RAM";
            8'd1:   enum_name = "CPU";
            8'd2:   enum_name = "ROM";
            8'd123: enum_name = "ROM2";
            8'd124: enum_name = "CPU2";
            default: enum_name = "UNKNOWN";
        endcase
    endfunction

    initial begin
        clk = 0;
        rst_n = 0;
        enable = 0;
        seed = 8'h5A;
        seed_load = 0;

        #12;
        rst_n = 1;

        #10;
        seed_load = 1;
        #10;
        seed_load = 0;
        enable = 1;

        repeat (10) begin
            @(posedge clk);
            $display("[M3] t=%0t addr_code=%0d (%s) valid=%0b",
                     $time, addr_code, enum_name(addr_code), valid);
            if (!((addr_code == 8'd0) || (addr_code == 8'd1) || (addr_code == 8'd2))) begin
                $display("ERROR: addr_code not in legal enum subset");
                $finish;
            end
        end

        $finish;
    end

endmodule : tb_method3_enum_range