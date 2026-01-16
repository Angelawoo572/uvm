//------------------------------------------------------------
//   Copyright 2010 Mentor Graphics Corporation
//   All Rights Reserved Worldwide
//
//   Licensed under the Apache License, Version 2.0 (the
//   "License"); you may not use this file except in
//   compliance with the License.  You may obtain a copy of
//   the License at
//
//       http://www.apache.org/licenses/LICENSE-2.0
//
//   Unless required by applicable law or agreed to in
//   writing, software distributed under the License is
//   distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
//   CONDITIONS OF ANY KIND, either express or implied.  See
//   the License for the specific language governing
//   permissions and limitations under the License.
//------------------------------------------------------------


// WISHBONE bus monitor
// Monitors slave read and write transactions and "packages" each
// transaction into a wb_txn and broadcasts the wb_txn
// Note only monitors slave 0 and slave 1 (see wishbone_bus_syscon_if)
//----------------------------------------------
class wb_bus_monitor extends uvm_monitor;
`uvm_component_utils(wb_bus_monitor)

  uvm_analysis_port #(wb_txn) wb_mon_ap;
  protected virtual wb_bus_monitor_bfm m_bfm;
  wb_config m_cfg;

  function new(string name, uvm_component parent);
   super.new(name,parent);
  endfunction

  function void build_phase(uvm_phase phase);
    wb_mon_ap = new("wb_mon_ap", this);
    if(m_cfg == null)
      if(!uvm_config_db #(wb_config)::get(this, "", "wb_config", m_cfg)) begin
        `uvm_fatal("build_phase", "Unable to find wb_config in the configuration database")
      end

    set_bfm();
  endfunction

  protected function void set_bfm();
    m_bfm = m_cfg.wb_mon_bfm; // set local virtual if property
    m_bfm.proxy = this;
  endfunction

  task run_phase(uvm_phase phase);
    m_bfm.run();
  endtask

  function void notify_transaction(wb_txn item);
    wb_mon_ap.write(item);
  endfunction : notify_transaction
endclass

