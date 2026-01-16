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

//  Top level module for a wishbone system with bus connection
// multiple masters and slaves
// Mike Baird
//----------------------------------------------
`timescale 1ns / 1ns

module top_mac_tb;
  import uvm_pkg::*;
  import tests_pkg::*;

   
  initial begin 
    run_test("test_mac_simple_duplex");  // create env and start running test
  end
  
endmodule
