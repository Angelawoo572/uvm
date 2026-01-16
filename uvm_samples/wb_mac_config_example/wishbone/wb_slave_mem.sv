/////////////////////////////////////////////////////////////////////
////                                                             ////
////  WISHBONE Slave Model                                       ////
////                                                             ////
////                                                             ////
////  Author: Rudolf Usselmann                                   ////
////          rudi@asics.ws                                      ////
////                                                             ////
////                                                             ////
////  Downloaded from: http://www.opencores.org/cores/wb_conmax/ ////
////                                                             ////
/////////////////////////////////////////////////////////////////////
////                                                             ////
//// Copyright (C) 2000-2002 Rudolf Usselmann                    ////
////                         www.asics.ws                        ////
////                         rudi@asics.ws                       ////
////                                                             ////
//// This source file may be used and distributed without        ////
//// restriction provided that this copyright statement is not   ////
//// removed from the file and that any derivative work contains ////
//// the original copyright notice and the associated disclaimer.////
////                                                             ////
////     THIS SOFTWARE IS PROVIDED ``AS IS'' AND WITHOUT ANY     ////
//// EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED   ////
//// TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS   ////
//// FOR A PARTICULAR PURPOSE. IN NO EVENT SHALL THE AUTHOR      ////
//// OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,         ////
//// INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES    ////
//// (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE   ////
//// GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR        ////
//// BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF  ////
//// LIABILITY, WHETHER IN  CONTRACT, STRICT LIABILITY, OR TORT  ////
//// (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT  ////
//// OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE         ////
//// POSSIBILITY OF SUCH DAMAGE.                                 ////
////                                                             ////
/////////////////////////////////////////////////////////////////////

//`include "wb_model_defines.v"
//import uvm_pkg::*;
  `include "uvm_macros.svh"

module wb_slave_mem #(parameter MEM_SIZE = 13)
                     (clk, rst, adr, din, dout, cyc, stb, sel, we, ack, err, rty);

input		clk, rst;
input	[31:0]	adr, din;
output	[31:0]	dout;
input		cyc, stb;
input	[3:0]	sel;
input		we;
output		ack, err, rty;

////////////////////////////////////////////////////////////////////
//
// Local Wires
//
import uvm_pkg::*;

//parameter	MEM_SIZE = 13;
parameter	sz = (1<<MEM_SIZE)-1;

reg	[31:0]	mem[sz:0];
wire		mem_re, mem_we;
wire	[31:0]	tmp;
reg	[31:0]	dout, tmp2;

reg		err, rty;
reg	[31:0]	del_ack;
reg	[5:0]	delay;

////////////////////////////////////////////////////////////////////
//
// Memory Logic
//

initial
   begin
	delay = 0;
	err = 0;
	rty = 0;
	#2;
        `uvm_info("WB_MEM_SLAVE",
                        $sformatf("Memory Size %0d address lines %0d words", MEM_SIZE, sz+1) ,UVM_LOW )
//	$display("\nINFO: WISHBONE MEMORY MODEL INSTANTIATED (%m)");
//	$display("      Memory Size %0d address lines %0d words\n",
//	MEM_SIZE, sz+1);
   end

assign mem_re = cyc & stb & !we;
assign mem_we = cyc & stb &  we;

assign	tmp = mem[adr[MEM_SIZE+1:2]];

always @(sel or tmp or mem_re or ack)
	if(mem_re & ack)
	   begin
		dout[31:24] <= sel[3] ? tmp[31:24] : 8'hxx;
		dout[23:16] <= sel[2] ? tmp[23:16] : 8'hxx;
		dout[15:08] <= sel[1] ? tmp[15:08] : 8'hxx;
		dout[07:00] <= sel[0] ? tmp[07:00] : 8'hxx;
	   end
	else	dout <= 32'hzzzz_zzzz;


always @(sel or tmp or din)
   begin
	tmp2[31:24] = !sel[3] ? tmp[31:24] : din[31:24];
	tmp2[23:16] = !sel[2] ? tmp[23:16] : din[23:16];
	tmp2[15:08] = !sel[1] ? tmp[15:08] : din[15:08];
	tmp2[07:00] = !sel[0] ? tmp[07:00] : din[07:00];
   end

always @(posedge clk)
	if(mem_we)	mem[adr[MEM_SIZE+1:2]] <= tmp2;

always @(posedge clk)
	del_ack = ack ? 0 : {del_ack[30:0], (mem_re | mem_we)};

assign	ack = cyc & ((delay==0) ? (mem_re | mem_we) : del_ack[delay-1]);

task fill_mem;
input		mode;

integer		n, mode;

begin

for(n=0;n<(sz+1);n=n+1)
   begin
	case(mode)
	   0:	mem[n] = { ~n[15:0], n[15:0] };
	   1:	mem[n] = $random;
	endcase
   end

end
endtask

endmodule
