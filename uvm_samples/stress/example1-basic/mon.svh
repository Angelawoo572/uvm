class mon #(int DATA_WIDTH=32, int ADDR_WIDTH=16) extends uvm_monitor;
	`uvm_component_utils(mon)

	function new(string name="mon", uvm_component parent=null);
		super.new(name, parent);
	endfunction

	virtual itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH)) vif;
        uvm_analysis_port #(req_item) m_cov_port;

	virtual function void build_phase(uvm_phase phase);
		super.build_phase(phase);
	
		if (!uvm_config_db #(virtual itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH)))::get(null, "tb", "vif", vif))
			`uvm_fatal(get_type_name(), $sformatf("Virtual interface not found usign name"));
		`uvm_info (get_type_name (), $sformatf ("end of build phase"), UVM_NONE)

	endfunction

	virtual task run_phase(uvm_phase phase);
		super.run_phase(phase);
		// this task monitors the interface for a complete
		// transaction and writes into analysis port when complete
		forever begin
			@ (vif.mon_cb);
			if (vif.rstn) begin
				req_item req = req_item::type_id::create("item");
				req.rst_n = vif.rst_n;
				req.re = vif.re;
				req.we = vif.we;
				req.addr_i = vif.addr_i;
				req.data_i = vif.data_i;
				req.data_o = vif.data_o;
				m_cov_port.write(req);
			end
		end
	endtask

endclass
