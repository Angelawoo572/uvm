class agt #(int DATA_WIDTH=32, int ADDR_WIDTH=16, int ARRAY_SIZE=8) extends uvm_agent;
	`uvm_component_param_utils(agt#(DATA_WIDTH, ADDR_WIDTH, ARRAY_SIZE))
	
	drv #(DATA_WIDTH, ADDR_WIDTH, ARRAY_SIZE) m_drv;
	mon #(DATA_WIDTH, ADDR_WIDTH, ARRAY_SIZE) m_mon;
	uvm_sequencer #(req_item, rsp_item) m_sqr;
	cov m_cov;

	function new(string name="agt", uvm_component parent);
		super.new(name, parent);
	endfunction: new

	function void build_phase(uvm_phase phase);
		super.build_phase(phase);
		m_drv = drv #(DATA_WIDTH, ADDR_WIDTH, ARRAY_SIZE)::type_id::create("m_drv", this);
		m_mon = mon #(DATA_WIDTH, ADDR_WIDTH, ARRAY_SIZE)::type_id::create("m_mon", this);
		m_sqr = uvm_sequencer #(req_item, rsp_item)::type_id::create("m_sqr", this);
		m_cov = cov::type_id::create("m_cov", this);

		`uvm_info (get_type_name(), $sformatf ("end of build phase"), UVM_NONE)
	endfunction: build_phase

	function void connect_phase(uvm_phase phase);
		m_drv.seq_item_port.connect(m_sqr.seq_item_export);
		m_mon.m_cov_port.connect(m_cov.analysis_export);
		`uvm_info (get_type_name(), $sformatf ("end of connect phase"), UVM_NONE)
	endfunction: connect_phase
endclass: agt
