class req_item extends uvm_sequence_item;
	`include "constants.svh"

	// inputs to the DUT
	rand bit [ADDR_WIDTH-1:0] addr_i;
	rand bit we;
	rand bit re;
	rand bit [DATA_WIDTH-1:0] data_i;
	rand bit rst_n = 1; 
	
	function new(string name = "req_item");
		super.new(name);
	endfunction: new

	`uvm_object_utils_begin(req_item)
		`uvm_field_int(addr_i,UVM_ALL_ON)
		`uvm_field_int(we,UVM_ALL_ON)
		`uvm_field_int(re,UVM_ALL_ON)
		`uvm_field_int(data_i,UVM_ALL_ON)
	`uvm_object_utils_end

endclass: req_item

class rsp_item extends uvm_sequence_item;
	`include "constants.svh"

	// outputs from the DUT
	logic [DATA_WIDTH-1:0] data_o;
	logic [ARRAY_SIZE-1:0] valid;
	
	function new(string name = "rsp_item");
		super.new(name);
	endfunction: new

	`uvm_object_utils_begin(rsp_item)
		`uvm_field_int(data_o,UVM_ALL_ON)
		`uvm_field_int(valid,UVM_ALL_ON)
	`uvm_object_utils_end

endclass: rsp_item

class full_item extends uvm_sequence_item;
	`uvm_object_utils(full_item)

	req_item req;
	rsp_item rsp;

	function new(string name = "full_item");
		super.new(name);
	endfunction: new
endclass: full_item

class reset_req_item extends req_item;
	`uvm_object_utils(reset_req_item)
		
	function new(string name = "reset_req_item");
		super.new(name);
	endfunction: new

	constraint force_rst { rst_n == 1'b0;}
endclass: reset_req_item

// items are above this line, sequences are below
class config_seq extends uvm_sequence;
        `uvm_object_utils(config_seq)

        function new(string name = "config_seq");
                super.new(name);
        endfunction: new

        req_item req;

        virtual task body();
		req = req_item::type_id::create("req");
		start_item(req);
		if (!req.randomize() with {rst_n==1; addr_i==MODE0_OFFSET; we==1; re==0; data_i== MODE0_TYPE1;}) begin `uvm_error(get_type_name, "Failed to randomize sequence item") end
		finish_item(req);

		req = req_item::type_id::create("req");
		start_item(req);
		if (!req.randomize() with {rst_n==1; addr_i==MODE1_OFFSET; we==1; re==0; data_i==MODE1_HIGH;}) begin `uvm_error(get_type_name, "Failed to randomize sequence item") end
		finish_item(req);

		req = req_item::type_id::create("req");
		start_item(req);
		if (!req.randomize() with {rst_n==1; addr_i==MODE2_OFFSET; we==1; re==0; data_i==MODE2_SHORT;}) begin `uvm_error(get_type_name, "Failed to randomize sequence item") end
		finish_item(req);
        endtask
endclass: config_seq

class change_mode_seq extends uvm_sequence #(req_item, rsp_item); // specialization is needed for this case
        `uvm_object_utils(change_mode_seq)
	`include "constants.svh"	

        function new(string name = "change_mode_seq");
                super.new(name);
        endfunction: new

        req_item req;
	rsp_item rsp;
	bit [DATA_WIDTH-1:0] newmode = 99; // invalid

        virtual task body();
		req = req_item::type_id::create("req");
		start_item(req);
		if (!req.randomize() with {rst_n==1; addr_i==MODE0_OFFSET; we==0; re==1;}) begin `uvm_error(get_type_name, "Failed to randomize sequence item") end
		finish_item(req);
		get_response(rsp); // get response associated with the read request
		
		if (rsp.data_o == MODE0_TYPE1) newmode = MODE0_TYPE2;
		if (rsp.data_o == MODE0_TYPE2) newmode = MODE0_TYPE1;

		req = req_item::type_id::create("req");
		start_item(req);
		if (!req.randomize() with {rst_n==1; addr_i==MODE0_OFFSET; we==1; re==0; data_i==newmode;}) begin `uvm_error(get_type_name, "Failed to randomize sequence item") end
		finish_item(req);

	endtask
endclass: change_mode_seq

class reset_then_config_vseq extends uvm_sequence;
	`uvm_object_utils(reset_then_config_vseq)

        function new(string name = "reset_then_config_vseq");
                super.new(name);
        endfunction: new

	reset_req_item rst;
        config_seq cfg;
	change_mode_seq change;

        virtual task body();
		`uvm_do(rst)
		`uvm_do(cfg)
		`uvm_do(change)
		`uvm_do(change)
		`uvm_do(change)
		`uvm_do(change)
	endtask
endclass: reset_then_config_vseq
	


