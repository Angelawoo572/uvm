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

// wishbone master point to point driver
//----------------------------------------------
interface mii_rx_driver_bfm (mii_if m_v_miim_if);

`include "uvm_macros.svh"
  import uvm_pkg::*;
  import mac_mii_pkg::*;
  
  // task to send a frame to the MAC
  task send_frame(ethernet_txn txn);
    bit[31:0] crc32;
    crc32 = 32'hffffffff;  //init CRC
    `uvm_info("MII_RX_DRIVER_BFM", "Rx Preamble",UVM_LOW )
    for(int i=0; i< txn.preamble_len; i++)  begin  // Preamble
      @(posedge m_v_miim_if.mrx_clk)
        m_v_miim_if.MRxDV = 1;  //set valid data on mRx data
      m_v_miim_if.MRxD = txn.preamble_data[(i*4)+3-:4];
    end
    @(posedge m_v_miim_if.mrx_clk)
      `uvm_info("MII_RX_DRIVER_BFM", "Rx SFD",UVM_LOW )
    m_v_miim_if.MRxD = txn.sfd_data[3:0]; //Start Frame Delimiter
    @(posedge m_v_miim_if.mrx_clk)
      m_v_miim_if.MRxD = txn.sfd_data[7:4];

    `uvm_info("MII_RX_DRIVER_BFM", "Rx Dest MAC addr",UVM_LOW )
    for(int i=47; i>0; i-=8)  begin         // Dest_addr (Dest MAC addr)
      @(posedge m_v_miim_if.mrx_clk)
        m_v_miim_if.MRxD = txn.dest_addr[(i-4)-:4];    //low nibble
      crc32 = gen_crc(crc32,m_v_miim_if.MRxD);
      @(posedge m_v_miim_if.mrx_clk)
        m_v_miim_if.MRxD = txn.dest_addr[i-:4];        //high nibble
      crc32 = gen_crc(crc32,m_v_miim_if.MRxD);
    end

    `uvm_info("MII_RX_DRIVER_BFM", "Rx Source MAC addr",UVM_LOW )
    for(int i=47; i>0; i-=8)  begin         // srce_addr (Source MAC addr)
      @(posedge m_v_miim_if.mrx_clk)
        m_v_miim_if.MRxD = txn.srce_addr[(i-4)-:4];     //low nibble
      crc32 = gen_crc(crc32,m_v_miim_if.MRxD);
      @(posedge m_v_miim_if.mrx_clk)
        m_v_miim_if.MRxD = txn.srce_addr[i-:4];         //high nibble
      crc32 = gen_crc(crc32,m_v_miim_if.MRxD);
    end

    `uvm_info("MII_RX_DRIVER_BFM", "Rx length",UVM_LOW )
    for(int i=15; i>0; i-=8)  begin         // length
      @(posedge m_v_miim_if.mrx_clk)
        m_v_miim_if.MRxD = txn.payload_size[(i-4)-:4];     //low nibble
      crc32 = gen_crc(crc32,m_v_miim_if.MRxD);
      @(posedge m_v_miim_if.mrx_clk)
        m_v_miim_if.MRxD = txn.payload_size[i-:4];         //high nibble
      crc32 = gen_crc(crc32,m_v_miim_if.MRxD);
    end

    `uvm_info("MII_RX_DRIVER_BFM", "Rx Payload",UVM_LOW )
    for(int i=0; i<txn.payload_size; i++)  begin  // Payload
      @(posedge m_v_miim_if.mrx_clk)
        m_v_miim_if.MRxD = txn.payload[i][3:0];                //low nibble
      crc32 = gen_crc(crc32,m_v_miim_if.MRxD);
      @(posedge m_v_miim_if.mrx_clk)
        m_v_miim_if.MRxD = txn.payload[i][7:4];                //high nibble
      crc32 = gen_crc(crc32,m_v_miim_if.MRxD);
    end

    `uvm_info("MII_RX_DRIVER_BFM", "Rx CRC",UVM_LOW )
    //NOTE:  for crc to send invert the bits, swap the bit order within the nibble
    // and swap the nibble order within the byte
    crc32 = ~crc32;  //invert the bits
    for(int i=31; i>0; i-=8)  begin        // CRC
      @(posedge m_v_miim_if.mrx_clk)              //high nibble first instead of low
        m_v_miim_if.MRxD[3] = crc32[i-3];      //bit 0 of crc nibble to bit 3 on MRxD
      m_v_miim_if.MRxD[2] = crc32[i-2];
      m_v_miim_if.MRxD[1] = crc32[i-1];
      m_v_miim_if.MRxD[0] = crc32[i-0];      //bit 3 of crc nibble to bit 0 on MRxD
      @(posedge m_v_miim_if.mrx_clk)
        m_v_miim_if.MRxD[3] = crc32[(i-4)-3];            //low  nibble
      m_v_miim_if.MRxD[2] = crc32[(i-4)-2];
      m_v_miim_if.MRxD[1] = crc32[(i-4)-1];
      m_v_miim_if.MRxD[0] = crc32[(i-4)-0];
    end

    @(posedge m_v_miim_if.mrx_clk)
      m_v_miim_if.MRxDV = 0;  //clear valid data on mRx data
  endtask

  function void init_mii_signals();
    m_v_miim_if.MRxDV = 0;
    m_v_miim_if.MRxD = 0;
    m_v_miim_if.MRxErr = 0;
    m_v_miim_if.MColl = 0;
    m_v_miim_if.MCrs = 0;
    m_v_miim_if.Mdi_I = 0;
  endfunction

  function int gen_crc (int unsigned Crc, bit[3:0]nibble);
    int unsigned CrcNext;
    bit [3:0] Data ; //= nibble;
    Data[0] = nibble[3];
    Data[1] = nibble[2];
    Data[2] = nibble[1];
    Data[3] = nibble[0];
    CrcNext[0] = (Data[0] ^ Crc[28]);
    CrcNext[1] = (Data[1] ^ Data[0] ^ Crc[28] ^ Crc[29]);
    CrcNext[2] = (Data[2] ^ Data[1] ^ Data[0] ^ Crc[28] ^ Crc[29] ^
                  Crc[30]);
    CrcNext[3] = (Data[3] ^ Data[2] ^ Data[1] ^ Crc[29] ^ Crc[30] ^
                  Crc[31]);
    CrcNext[4] = ((Data[3] ^ Data[2] ^ Data[0] ^ Crc[28] ^ Crc[30] ^
                   Crc[31])) ^ Crc[0];
    CrcNext[5] = ((Data[3] ^ Data[1] ^ Data[0] ^ Crc[28] ^ Crc[29] ^
                   Crc[31])) ^ Crc[1];
    CrcNext[6] = ((Data[2] ^ Data[1] ^ Crc[29] ^ Crc[30])) ^ Crc[ 2];
    CrcNext[7] = ((Data[3] ^ Data[2] ^ Data[0] ^ Crc[28] ^ Crc[30] ^
                   Crc[31])) ^ Crc[3];
    CrcNext[8] = ((Data[3] ^ Data[1] ^ Data[0] ^ Crc[28] ^ Crc[29] ^
                   Crc[31])) ^ Crc[4];
    CrcNext[9] = ((Data[2] ^ Data[1] ^ Crc[29] ^ Crc[30])) ^ Crc[5];
    CrcNext[10] = ((Data[3] ^ Data[2] ^ Data[0] ^ Crc[28] ^ Crc[30] ^
                    Crc[31])) ^ Crc[6];
    CrcNext[11] = ((Data[3] ^ Data[1] ^ Data[0] ^ Crc[28] ^ Crc[29] ^
                    Crc[31])) ^ Crc[7];
    CrcNext[12] = ((Data[2] ^ Data[1] ^ Data[0] ^ Crc[28] ^ Crc[29] ^
                    Crc[30])) ^ Crc[8];
    CrcNext[13] = ((Data[3] ^ Data[2] ^ Data[1] ^ Crc[29] ^ Crc[30] ^
                    Crc[31])) ^ Crc[9];
    CrcNext[14] = ((Data[3] ^ Data[2] ^ Crc[30] ^ Crc[31])) ^ Crc[10];
    CrcNext[15] = ((Data[3] ^ Crc[31])) ^ Crc[11];
    CrcNext[16] = ((Data[0] ^ Crc[28])) ^ Crc[12];
    CrcNext[17] = ((Data[1] ^ Crc[29])) ^ Crc[13];
    CrcNext[18] = ((Data[2] ^ Crc[30])) ^ Crc[14];
    CrcNext[19] = ((Data[3] ^ Crc[31])) ^ Crc[15];
    CrcNext[20] = Crc[16];
    CrcNext[21] = Crc[17];
    CrcNext[22] = ((Data[0] ^ Crc[28])) ^ Crc[18];
    CrcNext[23] = ((Data[1] ^ Data[0] ^ Crc[29] ^ Crc[28])) ^ Crc[19];
    CrcNext[24] = ((Data[2] ^ Data[1] ^ Crc[30] ^ Crc[29])) ^ Crc[20];
    CrcNext[25] = ((Data[3] ^ Data[2] ^ Crc[31] ^ Crc[30])) ^ Crc[21];
    CrcNext[26] = ((Data[3] ^ Data[0] ^ Crc[31] ^ Crc[28])) ^ Crc[22];
    CrcNext[27] = ((Data[1] ^ Crc[29])) ^ Crc[23];
    CrcNext[28] = ((Data[2] ^ Crc[30])) ^ Crc[24];
    CrcNext[29] = ((Data[3] ^ Crc[31])) ^ Crc[25];
    CrcNext[30] = Crc[26];
    CrcNext[31] = Crc[27];
    return(CrcNext);
  endfunction
endinterface : mii_rx_driver_bfm

