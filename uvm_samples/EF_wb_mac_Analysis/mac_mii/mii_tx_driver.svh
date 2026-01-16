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

`ifndef MII_TX_DRIVER
`define MII_TX_DRIVER

// wishbone master point to point driver
//----------------------------------------------
class mii_tx_driver extends uvm_driver #(ethernet_txn,ethernet_txn);
`uvm_component_utils(mii_tx_driver)

  uvm_analysis_port #(ethernet_txn) mii_tx_drv_ap;

   mii_config m_cfg;
   virtual mii_tx_driver_bfm m_bfm;

  function new(string name, uvm_component parent);
   super.new(name,parent);
  endfunction

  function void build_phase(uvm_phase phase);
    mii_tx_drv_ap = new("mii_tx_drv_ap", this);
    if (m_cfg == null)
      if(!uvm_config_db #(mii_config)::get(this, "", "mii_config", m_cfg)) begin
        `uvm_fatal("build_phase", "unable to get mii_config from configuration database")
      end
    m_bfm   = m_cfg.MII_tx_drv_bfm;  // set to global virtual interface
  endfunction

  task run_phase(uvm_phase phase);
    ethernet_txn txn;
    ethernet_txn sb_txn;
    forever begin
      seq_item_port.get(txn);       // get transaction
      m_bfm.get_frame(txn);         // receive txn from MAC
      $cast(sb_txn, txn.clone());   // make a copy of the txn
      mii_tx_drv_ap.write(sb_txn);  // broadcast received txn
      seq_item_port.put(txn);    // return transaction
    end
  endtask

endclass
`endif
