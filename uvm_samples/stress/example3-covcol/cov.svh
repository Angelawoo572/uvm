// example of a cg outside the class, this allows for it to become a data type
// that can be instantiated (with any name) many times

`include "constants.svh"

covergroup addr_cg (ref bit [ADDR_WIDTH-1:0] addr);
	option.per_instance = 1 ;
	cp_addr : coverpoint addr {
		bins MODE0 = {MODE0_OFFSET};
		bins MODE1 = {MODE1_OFFSET};
		bins MODE2 = {MODE2_OFFSET};
		bins ARRAY = {[ARRAY_OFFSET:ARRAY_OFFSET_CEILING]};
		bins other_addresses = default; // any other address
	}
endgroup

class cov extends uvm_subscriber #(full_item);
	`uvm_component_utils(cov)

	`include "constants.svh"

	// handle for the item received from the monitor
	full_item item;
	// handle for the address
	bit [ADDR_WIDTH-1:0] local_addr;

	// Covergroup for the addresses
	addr_cg writes, reads;

	covergroup array_cg ();
		option.per_instance = 0 ;
		cp_addr : coverpoint item.req.addr_i { // coverpoint points to a hierarchical variable
			bins VALID[] = {[ARRAY_OFFSET:ARRAY_OFFSET_CEILING]}; // array style declaration of bins, i.e., 1 bin per value in the range
			illegal_bins outside_range = default; // any other address is illegal
	}
	endgroup

	covergroup valid_cg();
		cp_valid: coverpoint item.rsp.valid {
			wildcard bins bit0 = { 8'b???????1 };
			wildcard bins bit1 = { 8'b??????1? };
			wildcard bins bit2 = { 8'b?????1?? };
			wildcard bins bit3 = { 8'b????1??? };
			wildcard bins bit4 = { 8'b???1???? };
			wildcard bins bit5 = { 8'b??1????? };
			wildcard bins bit6 = { 8'b?1?????? };
			wildcard bins bit7 = { 8'b1??????? };
		}
		cp_range: coverpoint item.rsp.data_o {
			bins split[2] = {[0:$]};
		}
	endgroup

	covergroup mode2_cg with function sample(logic [DATA_WIDTH-1:0] datai);
		// option per instance is ommited, this means default of
		// 0 should be assumed
		cp_data : coverpoint datai {
			bins short = {MODE2_SHORT};
			bins long = {MODE2_LONG};
			bins average = {MODE2_AVERAGE};
			bins otherstuff = default; // catches any other value, puts them in here
		}
	endgroup

	covergroup cross_cg();
		cp_we: coverpoint item.req.we {
			bins is_write = {1};
			ignore_bins otherwise = {0};
		}
		cp_re: coverpoint item.req.re {
			bins is_not_read = {0};
			ignore_bins otherwise = {1};
		}
		cp_addr : coverpoint item.req.addr_i {
			bins ANY_ARRAY_ADDR = {[ARRAY_OFFSET:ARRAY_OFFSET_CEILING]};
		}
		is_write_to_array: cross cp_we, cp_re, cp_addr;
	endgroup

	covergroup burst_cg();
		option.at_least = 3;
		cp_addr : coverpoint item.req.addr_i {
			bins ordered = (ARRAY_OFFSET => ARRAY_OFFSET+1 => ARRAY_OFFSET+2 => ARRAY_OFFSET+3);
		}
	endgroup

	function new(string name, uvm_component parent);
		super.new(name, parent);
		writes = new(local_addr);
		reads = new(local_addr);
		array_cg = new();
		mode2_cg = new();
		cross_cg = new();
		burst_cg = new();
		valid_cg = new();
	endfunction

	function void write(full_item t); // must be named "t", because write() is a pure function that already has t name
		this.item = t;
		//cast(this.item, t.clone());
		local_addr = item.req.addr_i;

		item.req.print();
		item.rsp.print();

		if (item.req.we) // is a write
			writes.sample(); 
		if (item.req.re) // is a read
			reads.sample(); 

		array_cg.sample(); // because array_cg is declared inside the class, it becomes an instance
		cross_cg.sample();
		burst_cg.sample();
		valid_cg.sample();

		if (item.req.re) begin // is a read...
			if (item.req.addr_i == MODE2_OFFSET) begin // ... to MODE2 register
				mode2_cg.sample(item.rsp.data_o);
				$display("%b %b ", item.rsp.data_o, MODE2_SHORT);
			end
		end


	endfunction
endclass

