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

`ifndef MII_RX_DRIVER
`define MII_RX_DRIVER

// wishbone master point to point driver
//----------------------------------------------
class mii_rx_driver extends uvm_driver #(ethernet_txn,ethernet_txn);
`uvm_component_utils(mii_rx_driver)

  uvm_analysis_port #(ethernet_txn) mii_rx_drv_ap;

  mii_config m_cfg;
  virtual mii_rx_driver_bfm m_bfm;

  function new(string name, uvm_component parent);
   super.new(name,parent);
  endfunction

  function void build_phase(uvm_phase phase);
    mii_rx_drv_ap = new("mii_rx_drv_ap", this);
    if (m_cfg == null)
      if(!uvm_config_db #(mii_config)::get(this, "", "mii_config", m_cfg)) begin
        `uvm_fatal("build_phase", "unable to get mii_config from configuration database")
      end
    m_bfm   = m_cfg.mii_rx_drv_bfm;  // set to global virtual interface
  endfunction

  task run_phase(uvm_phase phase);
    ethernet_txn txn;
    m_bfm.init_mii_signals();
    forever begin
      seq_item_port.get(txn);  // get transaction
      m_bfm.send_frame(txn);
      seq_item_port.put(txn);  // send rsp transaction - note this is what was received
      mii_rx_drv_ap.write(txn); //broadcast transaction - This is the expected transaction
    end
  endtask

endclass
`endif
