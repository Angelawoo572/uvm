class req_item extends uvm_sequence_item;
	`uvm_object_utils(req_item)

	`include "constants.svh"

	// inputs to the DUT
	rand bit [ADDR_WIDTH-1:0] addr_i;
	rand bit we;
	rand bit re;
	rand bit [DATA_WIDTH-1:0] data_i;
	logic [DATA_WIDTH-1:0] data_o;
	rand bit rst_n = 1; 
	
	function new(string name = "req_item");
		super.new(name);
	endfunction: new
endclass: req_item

class reset_req_item extends req_item;
	`uvm_object_utils(reset_req_item)
		
	function new(string name = "reset_req_item");
		super.new(name);
	endfunction: new

	constraint force_rst { rst_n == 1'b0;}
endclass: reset_req_item

class config_seq extends uvm_sequence#(req_item);
        `uvm_object_utils(config_seq)

        function new(string name = "config_seq");
                super.new(name);
        endfunction: new

        req_item req;

        virtual task body();
		req = req_item::type_id::create("req");
		start_item(req);
		if (!req.randomize() with {rst_n==1; addr_i==MODE0_OFFSET; we==1; re==0;}) begin `uvm_error(get_type_name, "Failed to randomize sequence item") end
		finish_item(req);

		req = req_item::type_id::create("req");
		start_item(req);
		if (!req.randomize() with {rst_n==1; addr_i==MODE1_OFFSET; we==1; re==0;}) begin `uvm_error(get_type_name, "Failed to randomize sequence item") end
		finish_item(req);

		req = req_item::type_id::create("req");
		start_item(req);
		if (!req.randomize() with {rst_n==1; addr_i==MODE2_OFFSET; we==1; re==0;}) begin `uvm_error(get_type_name, "Failed to randomize sequence item") end
		finish_item(req);
        endtask
endclass: config_seq

class reset_then_config_vseq extends uvm_sequence#(req_item);
	`uvm_object_utils(reset_then_config_vseq)

        function new(string name = "reset_then_config_vseq");
                super.new(name);
        endfunction: new

	reset_req_item rst;
        config_seq cfg;

        virtual task body();
		`uvm_do(rst)
		`uvm_do(cfg)
	endtask
endclass: reset_then_config_vseq
	


