class env extends uvm_env;
        `uvm_component_utils (env)

	`include "constants.svh"

        agt #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH)) m_agt;

        function new (string name = "env", uvm_component parent = null);
                super.new (name, parent);
        endfunction

        virtual function void build_phase (uvm_phase phase);
                super.build_phase (phase);
                m_agt = agt #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH)) ::type_id::create ("m_agt", this);
        endfunction

        virtual function void connect_phase (uvm_phase phase);
                super.connect_phase(phase);
        endfunction
endclass

