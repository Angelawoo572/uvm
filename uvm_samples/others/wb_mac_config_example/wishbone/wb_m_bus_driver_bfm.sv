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
interface wb_m_bus_driver_bfm (wishbone_bus_syscon_if wb_bus_if);

`include "uvm_macros.svh"
  import uvm_pkg::*;
  import wishbone_pkg::*;

  bit [2:0] m_id;  // Wishbone bus master ID

  function void set_m_id(bit[2:0] id);
    m_id = id;
  endfunction

  task wait_clock(int num = 1);
    repeat (num) @ (posedge wb_bus_if.clk);
  endtask
  
  //READ 1 or more cycles
  task wb_read_cycle(wb_txn req_txn);
    logic [31:0] temp_addr;
    temp_addr = req_txn.adr;
    for(int i = 0; i<req_txn.count; i++) begin
      if(wb_bus_if.rst) begin
        bus_reset();  // clear everything
        return; //exit if reset is asserted
      end
      wb_bus_if.m_addr[m_id] = temp_addr;
      wb_bus_if.m_we[m_id]  = 0;  // read
      wb_bus_if.m_sel[m_id] = req_txn.byte_sel;
      wb_bus_if.m_cyc[m_id] = 1;
      wb_bus_if.m_stb[m_id] = 1;
      @ (posedge wb_bus_if.clk)
      while (!(wb_bus_if.m_ack[m_id] & wb_bus_if.gnt[m_id])) @ (posedge wb_bus_if.clk);
      req_txn.data[i] = wb_bus_if.m_rdata;  // get data
      temp_addr =  temp_addr + 4;  // byte address so increment by 4 for word addr
    end
    wb_bus_if.m_cyc[m_id] = 0;
    wb_bus_if.m_stb[m_id] = 0;
  endtask

  //WRITE  1 or more write cycles
  task wb_write_cycle(wb_txn req_txn);
    for(int i = 0; i<req_txn.count; i++) begin
      if(wb_bus_if.rst) begin
        bus_reset();  // clear everything
        return; //exit if reset is asserted
      end
      wb_bus_if.m_wdata[m_id] = req_txn.data[i];
      wb_bus_if.m_addr[m_id] = req_txn.adr;
      wb_bus_if.m_we[m_id]  = 1;  //write
      wb_bus_if.m_sel[m_id] = req_txn.byte_sel;
      wb_bus_if.m_cyc[m_id] = 1;
      wb_bus_if.m_stb[m_id] = 1;
      @ (posedge wb_bus_if.clk)
      while (!(wb_bus_if.m_ack[m_id] & wb_bus_if.gnt[m_id])) @ (posedge wb_bus_if.clk);
      req_txn.adr =  req_txn.adr + 4;  // byte address so increment by 4 for word addr
    end
    wb_bus_if.m_cyc[m_id] = 0;
    wb_bus_if.m_stb[m_id] = 0;
  endtask

  task wb_irq(wb_txn req_txn);
    wait(wb_bus_if.irq);
    req_txn.data[0] = wb_bus_if.irq;
  endtask

  function void bus_reset();
    wb_bus_if.m_cyc[m_id] = 0;
    wb_bus_if.m_stb[m_id] = 0;
  endfunction

endinterface

