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
interface wb_bus_monitor_bfm (wishbone_bus_syscon_if wb_bus_if);

  import wishbone_pkg::*;
  
  //------------------------------------------
  // Data Members
  //------------------------------------------
  wb_bus_monitor proxy;


  //------------------------------------------
  // Methods
  //------------------------------------------

  //
  // Task: wait_for_clock
  //
  // This method waits for n clock cycles. 
  task automatic wait_clock(int num = 1);
    repeat (num) @ (posedge wb_bus_if.clk);
  endtask : wait_clock

  //
  // Task: wait_for_reset
  //
  // This method waits for the end of reset. 
  task wait_for_reset();
    // Wait for reset to end
    @(negedge wb_bus_if.rst);
  endtask : wait_for_reset
  
  task run();
    wb_txn txn;

    forever @ (posedge wb_bus_if.clk)
      if(wb_bus_if.s_cyc) begin // Is there a valid wb cycle?
        txn = wb_txn::type_id::create("txn"); // create a new wb_txn
        txn.adr = wb_bus_if.s_addr; // get address
        txn.count = 1;  // set count to one read or write
        if(wb_bus_if.s_we)  begin // is it a write?
          txn.data[0] = wb_bus_if.s_wdata;  // get data
          txn.txn_type = WRITE; // set op type
          while (!(wb_bus_if.s_ack[0] | wb_bus_if.s_ack[1]|wb_bus_if.s_ack[2]))
            @ (posedge wb_bus_if.clk); // wait for cycle to end
        end
        else begin
          txn.txn_type = READ; // set op type
          case (1) //Nope its a read, get data from correct slave
            wb_bus_if.s_stb[0]:  begin
              while (!(wb_bus_if.s_ack[0])) @ (posedge wb_bus_if.clk); // wait for ack
              txn.data[0] = wb_bus_if.s_rdata[0];  // get data
            end
            wb_bus_if.s_stb[1]:  begin
              while (!(wb_bus_if.s_ack[1])) @ (posedge wb_bus_if.clk); // wait for ack
              txn.data[0] = wb_bus_if.s_rdata[1];  // get data
            end
          endcase
        end // else: !if(wb_bus_if.s_we)
        proxy.notify_transaction(txn); // broadcast the wb_txn: wb_mon_ap.write(txn)
      end
  endtask
endinterface

