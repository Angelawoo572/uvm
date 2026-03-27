class drv #(int DATA_WIDTH=32, int ADDR_WIDTH=16, int ARRAY_SIZE=8) extends uvm_driver #(req_item, rsp_item);
	`uvm_component_param_utils(drv#(DATA_WIDTH, ADDR_WIDTH, ARRAY_SIZE))

	function new(string name="drv", uvm_component parent);
		super.new(name, parent);
	endfunction: new	

	virtual itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH), .ARRAY_SIZE(ARRAY_SIZE)) vif;

	function void build_phase(uvm_phase phase);
		super.build_phase(phase);

		if (!uvm_config_db #(virtual itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH), .ARRAY_SIZE(ARRAY_SIZE)))::get(null, "tb", "vif", vif))
			`uvm_fatal(get_type_name(), $sformatf("Virtual interface not found"));
		`uvm_info (get_type_name (), $sformatf ("end of build phase"), UVM_NONE)
	endfunction: build_phase

	task run_phase(uvm_phase phase);
		req_item req; // to DUT
		rsp_item rsp; // from DUT

		@(vif.drv_cb); // checks for the clocking block event one time, to make sure everything after this is in sync with the clock

        	forever begin // because this is a forever loop, simulation can hang here very easily if the signaling is not in place
			seq_item_port.get_next_item(req);
			`uvm_info(get_type_name (), $sformatf ("driver acquired request..."), UVM_NONE)
			
			//@(vif.drv_cb); // checks for the clocking block event
			vif.drv_cb.addr_i <= req.addr_i; // then performs NBAs to keep the clocking block delays
			vif.drv_cb.data_i <= req.data_i;
			vif.drv_cb.re <= req.re;
			vif.drv_cb.we <= req.we;
			vif.drv_cb.rst_n <= req.rst_n;

			@(vif.drv_cb); // checks for the clocking block event		
			rsp = rsp_item::type_id::create("rsp_item");
			rsp.data_o = vif.drv_cb.data_o;
			rsp.valid = vif.drv_cb.valid;
			rsp.set_id_info(req);
			seq_item_port.item_done(rsp); // item done issued on rsp
			`uvm_info(get_type_name (), $sformatf ("... driver returned response"), UVM_NONE)
//			`uvm_info(get_type_name (), req.sprint(), UVM_NONE)
			//req.print();
			//rsp.print();
		end
	endtask: run_phase
endclass: drv

			
