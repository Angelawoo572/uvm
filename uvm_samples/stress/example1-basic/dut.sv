module dut (itf myitf);

`include "constants.svh"

// aliases for clock and reset
logic clk, rst_n;
assign clk = myitf.clk;
assign rst_n = myitf.rst_n;

logic [DATA_WIDTH-1:0] mode0; // read and write register
logic [DATA_WIDTH-1:0] mode1; // read and write register
logic [DATA_WIDTH-1:0] mode2; // read and write register


always_ff @(posedge clk or negedge rst_n) begin
	if (rst_n == 1'b0) begin
		mode0 <= '0;
		mode1 <= '0;
		mode2 <= '0;
		myitf.data_o <= '0;
	end
	else begin
		if (myitf.re) begin
			case (myitf.addr_i)
				MODE0_OFFSET: myitf.data_o <= mode0;
				MODE1_OFFSET: myitf.data_o <= mode1;
				MODE2_OFFSET: myitf.data_o <= mode2;
				default: myitf.data_o <= '0;
			endcase
		end
		if (myitf.we) begin
			case (myitf.addr_i)
				MODE0_OFFSET: mode0 <= myitf.data_i;
				MODE1_OFFSET: mode1 <= myitf.data_i;
				MODE2_OFFSET: mode2 <= myitf.data_i;
				default: ;
			endcase
		end

	end
end

endmodule
