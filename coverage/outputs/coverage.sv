// Auto-generated SystemVerilog Coverage Model
// Generated from: outputs/cov_usable.json
`include outputs/constants.svh

module opcodes_cg (
    input logic [0:0] clk,
    input logic [0:0] rst,
    input logic [0:0] sample,
    input logic [31:0] m_item_addr_i,
    output logic [15:0] _MODE0_cnt,
    output logic [15:0] _MODE1_cnt,
    output logic [15:0] _MODE2_cnt,
    output logic _illegal_error
);

    // Bin Counters for 
    logic [15:0] _ctr_r [2:0];
    logic [15:0] _ctr_n [2:0];
    logic [1:0] _index;
    
    assign _MODE0_cnt = _ctr_r[0];
    assign _MODE1_cnt = _ctr_r[1];
    assign _MODE2_cnt = _ctr_r[2];
    
    always_comb begin
        // Default: Hold value, no error
        _ctr_n = _ctr_r;
        _illegal_error = 0;
    
        case (m_item_addr_i) inside
            MODE0_OFFSET: begin _ctr_n[0] = _ctr_r[0] + 1;
            _index = 0;
            end
            MODE1_OFFSET: begin _ctr_n[1] = _ctr_r[1] + 1;
            _index = 1;
            end
            MODE2_OFFSET: begin _ctr_n[2] = _ctr_r[2] + 1;
            _index = 2;
            end
            default: ; // No bin hit
        endcase
    end
    
    always_ff @(posedge clk or negedge rst) begin
        if (!rst) begin
            _ctr_r[0] <= '0;
            _ctr_r[1] <= '0;
            _ctr_r[2] <= '0;
        end else if (sample) begin
            _ctr_r <= _ctr_n;
        end
    end
endmodule

module output_mod (
    input logic [1:0] signal_id,
    input logic [0:0] byte_ctr,
    input logic [15:0] opcodes_cg__MODE0_cnt,
    input logic [15:0] opcodes_cg__MODE1_cnt,
    input logic [15:0] opcodes_cg__MODE2_cnt,
    input logic [0:0] opcodes_cg__illegal_error,
    output logic byte_done,
    output logic [7:0] cov_byte
);

    logic[7:0] opcodes_cg__MODE0_cnt_byte;
    logic opcodes_cg__MODE0_cnt_done;
    
    always_comb begin
        opcodes_cg__MODE0_cnt_byte = '0;
        case(byte_ctr)
            0: opcodes_cg__MODE0_cnt_byte[7:0] = opcodes_cg__MODE0_cnt[7:0];
            1: opcodes_cg__MODE0_cnt_byte[7:0] = opcodes_cg__MODE0_cnt[15:8];
        default: opcodes_cg__MODE0_cnt_byte = '0;
        endcase
    end
    assign opcodes_cg__MODE0_cnt_done = (signal_id == 0) & (byte_ctr == 1);
    
    logic[7:0] opcodes_cg__MODE1_cnt_byte;
    logic opcodes_cg__MODE1_cnt_done;
    
    always_comb begin
        opcodes_cg__MODE1_cnt_byte = '0;
        case(byte_ctr)
            0: opcodes_cg__MODE1_cnt_byte[7:0] = opcodes_cg__MODE1_cnt[7:0];
            1: opcodes_cg__MODE1_cnt_byte[7:0] = opcodes_cg__MODE1_cnt[15:8];
        default: opcodes_cg__MODE1_cnt_byte = '0;
        endcase
    end
    assign opcodes_cg__MODE1_cnt_done = (signal_id == 1) & (byte_ctr == 1);
    
    logic[7:0] opcodes_cg__MODE2_cnt_byte;
    logic opcodes_cg__MODE2_cnt_done;
    
    always_comb begin
        opcodes_cg__MODE2_cnt_byte = '0;
        case(byte_ctr)
            0: opcodes_cg__MODE2_cnt_byte[7:0] = opcodes_cg__MODE2_cnt[7:0];
            1: opcodes_cg__MODE2_cnt_byte[7:0] = opcodes_cg__MODE2_cnt[15:8];
        default: opcodes_cg__MODE2_cnt_byte = '0;
        endcase
    end
    assign opcodes_cg__MODE2_cnt_done = (signal_id == 2) & (byte_ctr == 1);
    
    logic[7:0] opcodes_cg__illegal_error_byte;
    logic opcodes_cg__illegal_error_done;
    
    always_comb begin
        opcodes_cg__illegal_error_byte = '0;
        case(byte_ctr)
            0: opcodes_cg__illegal_error_byte[0:0] = opcodes_cg__illegal_error[0:0];
        default: opcodes_cg__illegal_error_byte = '0;
        endcase
    end
    assign opcodes_cg__illegal_error_done = (signal_id == 3) & (byte_ctr == 0);
    
    always_comb begin
    case(signal_id)
            0: cov_byte = opcodes_cg__MODE0_cnt_byte;
            1: cov_byte = opcodes_cg__MODE1_cnt_byte;
            2: cov_byte = opcodes_cg__MODE2_cnt_byte;
            3: cov_byte = opcodes_cg__illegal_error_byte;
            default: cov_byte = '0;
    endcase
    end
    assign byte_done = opcodes_cg__MODE0_cnt_done |
        opcodes_cg__MODE1_cnt_done |
        opcodes_cg__MODE2_cnt_done |
        opcodes_cg__illegal_error_done;
endmodule

module cov_fsm (
    input logic [0:0] clk,
    input logic [0:0] rst,
    input logic [0:0] sim_complete,
    input logic [0:0] tx_ready,
    input logic [0:0] packet_ready,
    input logic [0:0] packet_done,
    output logic done,
    output logic byte_ctr,
    output logic [1:0] signal_id,
    output logic send_id
);

    enum logic[1:0] {s_idle, s_send_id, s_packet} state_n, state_p;
    localparam SIGNAL_COUNT = 4;
    
    always_comb begin
        state_n = state_p;
        case(state_p)
            s_idle: if (sim_complete & tx_ready) state_n = s_send_id;
            s_send_id: if (tx_ready) state_n = s_packet;
            s_packet: begin 
                if (signal_id == (SIGNAL_COUNT-1) & tx_ready) state_n = s_idle;
                else if (tx_ready & packet_done) state_n = s_send_id;
            end
        endcase
    end
    
    logic[1:0] signal_id_n;
    logic[0:0] byte_ctr_n;
    always_comb begin
        signal_id_n = signal_id;
        byte_ctr_n = byte_ctr;
        if (state_p == s_packet & tx_ready) begin
            byte_ctr_n = byte_ctr + 1;
        end
        if (state_p == s_packet & state_n == s_send_id) begin
            signal_id_n = signal_id + 1;
        end
        if (state_p != s_packet) begin
            byte_ctr_n = '0;
        end
    end
    
    assign done = (state_p == s_packet & state_n == s_idle);
    assign send_id = (state_p == s_send_id);
    
    always_ff @(posedge clk) begin
        if (rst) begin 
            state_p <= s_idle;
            byte_ctr <= '0;
            signal_id <= '0;
        end
        else begin
            state_p <= state_n;
            byte_ctr <= byte_ctr_n;
            signal_id <= signal_id_n;
        end
    end
endmodule

module cov (
    input logic [0:0] clk,
    input logic [0:0] rst,
    input logic [0:0] sample,
    input logic [31:0] m_item_addr_i,
    input logic [0:0] sim_complete,
    input logic [0:0] tx_ready,
    input logic [0:0] packet_ready,
    input logic [0:0] packet_done,
    output logic [15:0] opcodes_cg__MODE0_cnt,
    output logic [15:0] opcodes_cg__MODE1_cnt,
    output logic [15:0] opcodes_cg__MODE2_cnt,
    output logic opcodes_cg__illegal_error,
    output logic uart_out_byte_done,
    output logic [7:0] uart_out_cov_byte,
    output logic done,
    output logic byte_ctr,
    output logic [1:0] signal_id,
    output logic send_id
);


    opcodes_cg opcodes_cg_inst (
        .clk(clk),
        .rst(rst),
        .sample(sample),
        .m_item_addr_i(m_item_addr_i),
        ._MODE0_cnt(opcodes_cg__MODE0_cnt),
        ._MODE1_cnt(opcodes_cg__MODE1_cnt),
        ._MODE2_cnt(opcodes_cg__MODE2_cnt),
        ._illegal_error(opcodes_cg__illegal_error)
    );

    output_mod uart_out_inst (
        .signal_id(signal_id),
        .byte_ctr(byte_ctr),
        .opcodes_cg__MODE0_cnt(opcodes_cg__MODE0_cnt),
        .opcodes_cg__MODE1_cnt(opcodes_cg__MODE1_cnt),
        .opcodes_cg__MODE2_cnt(opcodes_cg__MODE2_cnt),
        .opcodes_cg__illegal_error(opcodes_cg__illegal_error),
        .byte_done(uart_out_byte_done),
        .cov_byte(uart_out_cov_byte)
    );

    cov_fsm cov_fsm_inst_inst (
        .clk(clk),
        .rst(rst),
        .sim_complete(sim_complete),
        .tx_ready(tx_ready),
        .packet_ready(packet_ready),
        .packet_done(packet_done),
        .done(done),
        .byte_ctr(byte_ctr),
        .signal_id(signal_id),
        .send_id(send_id)
    );

endmodule

