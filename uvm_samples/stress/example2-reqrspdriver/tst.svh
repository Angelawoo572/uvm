class example2 extends uvm_test;
        `uvm_component_utils (example2)

        function new (string name = "example2", uvm_component parent = null);
                super.new (name, parent);
        endfunction

        env m_env;

        virtual function void build_phase (uvm_phase phase);
                super.build_phase (phase);
                m_env  = env::type_id::create ("m_env", this);
                `uvm_info (get_type_name (), $sformatf ("build phase"), UVM_NONE)
        endfunction

        virtual task run_phase (uvm_phase phase);
                reset_then_config_vseq m_seq = reset_then_config_vseq::type_id::create ("m_seq");

                phase.phase_done.set_drain_time(this, 20ns); // this makes sure simulation keeps running for another 20 time units past the last sequence
		
                super.run_phase(phase);

                phase.raise_objection (this);
                m_seq.start(m_env.m_agt.m_sqr);
                phase.drop_objection (this);
        endtask
endclass : example2

