module dut (itf myitf);

`include "constants.svh"

// aliases for clock and reset
logic clk, rst_n;
assign clk = myitf.clk;
assign rst_n = myitf.rst_n;

logic [DATA_WIDTH-1:0] mode0; // read and write register
logic [DATA_WIDTH-1:0] mode1; // read and write register
logic [DATA_WIDTH-1:0] mode2; // read and write register
logic [DATA_WIDTH-1:0] storage [0:ARRAY_SIZE-1];
//logic [ARRAY_SIZE-1:0] valid; // part of itf

always_ff @(posedge clk or negedge rst_n) begin
	if (rst_n == 1'b0) begin
		mode0 <= '0;
		mode1 <= '0;
		mode2 <= '0;
		myitf.data_o <= '0;
		myitf.valid <= '0;
	end
	else begin
		if (myitf.re) begin
			unique case (myitf.addr_i) inside
				MODE0_OFFSET: myitf.data_o <= mode0;
				MODE1_OFFSET: myitf.data_o <= mode1;
				MODE2_OFFSET: myitf.data_o <= mode2;
				[ARRAY_OFFSET:ARRAY_OFFSET_CEILING]: begin 
					logic [$clog2(ARRAY_SIZE):0] address_for_storage;
					address_for_storage = myitf.addr_i - ARRAY_OFFSET;
					myitf.data_o <= storage[address_for_storage];
				end
				default: myitf.data_o <= '0;
			endcase
		end
		if (myitf.we) begin
			unique case (myitf.addr_i) inside
				MODE0_OFFSET: mode0 <= myitf.data_i;
				MODE1_OFFSET: mode1 <= myitf.data_i;
				MODE2_OFFSET: mode2 <= myitf.data_i;
				[ARRAY_OFFSET:ARRAY_OFFSET_CEILING]: begin 
					logic [$clog2(ARRAY_SIZE):0] address_for_storage;
					address_for_storage = myitf.addr_i - ARRAY_OFFSET;
					storage[address_for_storage] <= myitf.data_i;
					myitf.valid[address_for_storage] <= 1'b1;
				end
				default: ;
			endcase
		end

	end
end

endmodule
