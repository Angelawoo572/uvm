class cov extends uvm_subscriber #(full_item);
	`uvm_component_utils(cov)

	`include "constants.svh"

	// handle for the item received from the monitor
	full_item m_item;

	// Covergroup for the addresses
	covergroup opcodes_cg;
		option.per_instance = 1 ;
		coverpoint full_item.addr_i {
			bins MODE0 = MODE0_OFFSET;
			bins MODE1 = MODE1_OFFSET;
			bins MODE2 = MODE2_OFFSET;
		}
	endgroup


	function new(string name, uvm_component parent);
		super.new(name, parent);
		opcodes_cg = new();
	endfunction

	function void write(full_item t); // must be named "t", because write() is a pure function that already has t name
		this.m_item = t;
		opcodes_cg.sample(); // sample could be conditional
	endfunction
endclass

