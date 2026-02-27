module const_wrap_addr (
    input  logic [31:0] lfsr_in,
    output logic [31:0] addr
);

    assign addr[31:2] = lfsr_in[31:2];
    assign addr[1:0] = 2'h0;

endmodule