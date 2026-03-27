class mon #(int DATA_WIDTH=32, int ADDR_WIDTH=16, int ARRAY_SIZE=8) extends uvm_monitor;
	`uvm_component_param_utils(mon#(DATA_WIDTH, ADDR_WIDTH, ARRAY_SIZE))
	
	function new(string name="mon", uvm_component parent=null);
		super.new(name, parent);
	endfunction : new

	virtual itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH), .ARRAY_SIZE(ARRAY_SIZE)) vif;
        uvm_analysis_port #(full_item) m_cov_port;

	virtual function void build_phase(uvm_phase phase);
		super.build_phase(phase);
	
		if (!uvm_config_db #(virtual itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH), .ARRAY_SIZE(ARRAY_SIZE)))::get(null, "tb", "vif", vif))
			`uvm_fatal(get_type_name(), $sformatf("Virtual interface not found usign name"));
		`uvm_info (get_type_name (), $sformatf ("end of build phase"), UVM_NONE)
		 m_cov_port = new ("m_cov_port", this);
	endfunction

	virtual task run_phase(uvm_phase phase);
		super.run_phase(phase);
		// this task monitors the interface for a complete
		// transaction and writes into analysis port when complete
		forever begin
			@ (vif.mon_cb);
			if (vif.mon_cb.rst_n) begin // not under reset
				full_item item = full_item::type_id::create("full");
				req_item req = req_item::type_id::create("full.req");
				rsp_item rsp = rsp_item::type_id::create("full.rsp");

				req.addr_i = vif.mon_cb.addr_i;
				req.we = vif.mon_cb.we;
				req.re = vif.mon_cb.re;
				req.rst_n = vif.mon_cb.rst_n;
				req.data_i = vif.mon_cb.data_i;

				rsp.data_o = vif.mon_cb.data_o;
				rsp.valid = vif.mon_cb.valid;

				item.req = req;
				item.rsp = rsp;

				m_cov_port.write(item);
			end

		end
	endtask

endclass
