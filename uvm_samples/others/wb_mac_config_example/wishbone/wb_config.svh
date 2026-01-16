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

`ifndef WB_CONFIG
`define WB_CONFIG

// configuration container class
class wb_config extends uvm_object;
  `uvm_object_utils( wb_config );

  virtual wb_m_bus_driver_bfm  wb_drv_bfm;
  virtual wb_bus_monitor_bfm   wb_mon_bfm;

  int m_wb_id;                       // Wishbone bus ID
  int m_wb_master_id;                // Wishbone bus master id for wishone agent
  int m_mac_id;                      // id of MAC WB master
  int unsigned m_mac_wb_base_addr;   // Wishbone base address of MAC
  bit [47:0]   m_mac_eth_addr;       // Ethernet address of MAC
  bit [47:0]   m_tb_eth_addr;        // Ethernet address of testbench for sends/receives
  int m_mem_slave_size;              // Size of slave memory in bytes
  int unsigned m_s_mem_wb_base_addr; // base address of wb memory for MAC frame buffers
  int m_mem_slave_wb_id;             // Wishbone ID of slave memory
  int m_wb_verbosity;                // verbosity level for wishbone messages


  function new( string name = "" );
    super.new( name );
  endfunction

  //
  // Task: wait_for_clock
  //
  // This method waits for n clock cycles. 
  task wait_for_clock( int n = 1 );
    wb_mon_bfm.wait_clock(n);
  endtask
  
  //
  // Task: wait_for_reset
  //
  // This method waits for the end of reset. 
  event wait_for_reset_event;
  bit   wait_for_reset_called = 0;
  
  task wait_for_reset();
    if (!wait_for_reset_called) begin
      wait_for_reset_called = 1;
      wb_mon_bfm.wait_for_reset();
      -> wait_for_reset_event;
      wait_for_reset_called = 0;
    end else begin
      @(wait_for_reset_event);
    end
  endtask : wait_for_reset

endclass

`endif
