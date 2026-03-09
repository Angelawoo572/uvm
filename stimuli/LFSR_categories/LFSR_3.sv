`default_nettype none

// Method 3:
// Synthesizable RTL for enum-valued address with constraint:
//   addr inside [RAM:ROM]
// We implement that as:
//   valid = (addr_code >= RAM) && (addr_code <= ROM)
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

    logic [7:0] lfsr_state, lfsr_next;
    logic       feedback;
    addr_t      addr_enum;

    assign feedback  = lfsr_state[7] ^ lfsr_state[5] ^ lfsr_state[4] ^ lfsr_state[3];
    assign lfsr_next = {lfsr_state[6:0], feedback};

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr_state <= 8'h1;
        end else if (seed_load) begin
            lfsr_state <= (seed == 8'h00) ? 8'h1 : seed;
        end else if (enable) begin
            lfsr_state <= lfsr_next;
        end
    end

    // Map raw LFSR output into one of the enum values
    always_comb begin
        unique case (lfsr_state[2:0])
            3'd0: addr_enum = RAM;
            3'd1: addr_enum = CPU;
            3'd2: addr_enum = ROM;
            3'd3: addr_enum = ROM2;
            default: addr_enum = CPU2;
        endcase
    end

    assign addr_code = addr_enum;

    // Equivalent hardware form of: addr inside [RAM:ROM]
    assign valid = (addr_enum >= RAM) && (addr_enum <= ROM);

endmodule: method3_enum_range

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

        repeat (16) begin
            @(posedge clk);
            $display("[M3] t=%0t addr_code=%0d (%s) valid=%0b",
                     $time, addr_code, enum_name(addr_code), valid);
        end

        $finish;
    end

endmodule: tb_method3_enum_range
