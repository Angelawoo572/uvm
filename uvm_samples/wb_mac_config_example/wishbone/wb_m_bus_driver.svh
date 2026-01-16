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

// WISHBONE master driver
//----------------------------------------------
class wb_m_bus_driver extends uvm_driver  #(wb_txn, wb_txn);
`uvm_component_utils(wb_m_bus_driver)

  uvm_analysis_port #(wb_txn) wb_drv_ap;
  protected virtual wb_m_bus_driver_bfm  m_bfm;  // Virtual Interface
  wb_config m_cfg;


  function new(string name, uvm_component parent);
   super.new(name,parent);
  endfunction

  function void build_phase(uvm_phase phase);
    if(m_cfg == null)
      if(!uvm_config_db #(wb_config)::get(this, "", "wb_config", m_cfg)) begin
        `uvm_fatal("build_phase", "Unable to find wb_config in the configuration database")
      end
    m_bfm = m_cfg.wb_drv_bfm; // set local virtual if property
    m_bfm.set_m_id(m_cfg.m_wb_master_id);
    
    wb_drv_ap = new("wb_drv_ap", this);
  endfunction

  function void end_of_elaboration();
    set_report_verbosity_level(m_cfg.m_wb_verbosity);
  endfunction

  task run_phase(uvm_phase phase);
    wb_txn req_txn;
    forever begin
      seq_item_port.get(req_txn);  // get transaction
      //m_bfm.wait_clock();  // sync to clock edge
      case(req_txn.txn_type)  //what type of transaction?
        NONE: `uvm_info($sformatf("WB_M_DRVR_%0d",m_cfg.m_wb_master_id),
                              $sformatf("wb_txn %0d the wb_txn_type was type NONE",
                              req_txn.get_transaction_id()),UVM_LOW )
        WRITE: wb_write_cycle(req_txn);
        READ:  wb_read_cycle(req_txn);
        RMW:  wb_rmw_cycle(req_txn);
        WAIT_IRQ: fork wb_irq(req_txn); join_none
        default: `uvm_error($sformatf("WB_M_DRVR_%0d",m_cfg.m_wb_master_id),
                                  $sformatf("wb_txn %0d the wb_txn_type was type illegal",
                                  req_txn.get_transaction_id()) )
      endcase
    end
  endtask

  //READ 1 or more cycles
  virtual task wb_read_cycle(wb_txn req_txn);
    m_bfm.wb_read_cycle(req_txn);
    seq_item_port.put(req_txn);  // send rsp object back to sequence
    wb_drv_ap.write(req_txn);  //broadcast read transaction with results
  endtask

  //WRITE  1 or more write cycles
  virtual task wb_write_cycle(ref wb_txn req_txn);
    wb_txn orig_req_txn;
    $cast(orig_req_txn, req_txn.clone());  //save off copy of original req transaction
    m_bfm.wb_write_cycle(req_txn);
    `uvm_info($sformatf("WB_M_DRVR_%0d",m_cfg.m_wb_master_id),
                    $sformatf("req_txn: %s",orig_req_txn.convert2string()),
                    351 )
    wb_drv_ap.write(orig_req_txn);  //broadcast orignal transaction
  endtask

  //RMW ( read-modify_write)
  virtual task wb_rmw_cycle(ref wb_txn req_txn);
    `uvm_info($sformatf("WB_M_DRVR_%0d",m_cfg.m_wb_master_id),
                    "Wishbone RMW instruction not implemented yet",UVM_LOW )
  endtask

  virtual task wb_irq(wb_txn req_txn);
    m_bfm.wb_irq(req_txn);
    seq_item_port.put(req_txn);  // send rsp object back to sequence
  endtask

endclass

