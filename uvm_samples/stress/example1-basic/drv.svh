class drv #(int DATA_WIDTH=32, int ADDR_WIDTH=16) extends uvm_driver;
	`uvm_component_param_utils(drv#(DATA_WIDTH, ADDR_WIDTH))

	function new(string name="drv", uvm_component parent);
		super.new(name, parent);
	endfunction: new	

	virtual itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH)) vif;

	function void build_phase(uvm_phase phase);
		super.build_phase(phase);

		if (!uvm_config_db #(virtual itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH)))::get(null, "tb", "vif", vif))
			`uvm_fatal(get_type_name(), $sformatf("Virtual interface not found"));
		`uvm_info (get_type_name (), $sformatf ("end of build phase"), UVM_NONE)
	endfunction: build_phase

	task run_phase(uvm_phase phase);
		req_item req; // to DUT

        	forever begin // because this is a forever loop, simulation can hang here very easily if the signaling is not in place
			seq_item_port.get_next_item(req);
	    
			@(vif.drv_cb); // checks for the clocking block event
			vif.drv_cb.addr_i <= req.addr_i; // then performs NBAs to keep the clocking block delays
			vif.drv_cb.data_i <= req.data_i;
			vif.drv_cb.re <= req.re;
			vif.drv_cb.we <= req.we;
			vif.drv_cb.rst_n <= req.rst_n;

			seq_item_port.item_done(); // when there is no response, this is how item done looks like
		end
	endtask: run_phase
endclass: drv

			
