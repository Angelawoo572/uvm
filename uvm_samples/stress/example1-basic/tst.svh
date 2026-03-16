class example1basic extends uvm_test;
        `uvm_component_utils (example1basic)

        function new (string name = "example1basic", uvm_component parent = null);
                super.new (name, parent);
        endfunction

        env m_env;

        virtual function void build_phase (uvm_phase phase);
                super.build_phase (phase);
                m_env  = env::type_id::create ("m_env", this);
                `uvm_info (get_type_name (), $sformatf ("build phase"), UVM_NONE)
        endfunction

        virtual task run_phase (uvm_phase phase);
                config_seq m_seq = config_seq::type_id::create ("m_seq");

                super.run_phase(phase);

                phase.raise_objection (this);
                m_seq.start(m_env.m_agt.m_sqr);
                phase.drop_objection (this);
        endtask
endclass

