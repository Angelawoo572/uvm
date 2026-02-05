# UVM -> RTL execution flow

## System overview
System generates **3 RTL blocks** + an **orchestrator block**:
![System-overview](./images/system-overview.png)

The **4 RTL blocks** connect as such:
![Lower-level-system-overview](./images/system-overview-1.png)

## Execution flow
```bash
Step 1: Orchestrator grants TOKEN to Sequence 0
        │
        ├──→ Seq 0: "I need random data"
        │
Step 2: Seq 0 requests Solver
        │
        ├──→ Solver: Generates random values (5 cycles)
        │
Step 3: Seq 0 receives solved data
        │
        ├──→ Seq 0: Drives transaction to DUT
        │
Step 4: DUT accepts transaction
        │
        ├──→ Seq 0: Triggers Coverage sampling
        │
Step 5: Seq 0 done, releases TOKEN
        │
        └──→ Orchestrator grants TOKEN to Sequence 1
        
        [Repeat for all sequences...]
```

## Orchestrator
Only **1 sequence** can drive **1 DUT** at a time.

The `token manager` and `DUT mux` work as such:
```bash
┌───────────────────┐            
│ Top Orchestrator  │            
│  (Token manager)  │            
└───┬───────────────┘            
    │token_grant (one-hot)       
    ├────────────┐               
    │            │               
  ┌─▼───┐     ┌──▼──┐            
  │Seq 0│ ... │Seq n│            
  └─┬───┘     └────┬┘            
    └──────┬───────┘            
     ┌─────▼─────┐              
     │  DUT mux  │◄───────  token_grant    
     └─────┬─────┘              
           │                   
           ▼                     
          DUT                                                                     
```      

**Interface:**
```systemverilog
interface uvm_orchestrator_if #(
    parameter int NUM_SEQUENCES = 8
)(
    input  logic clk,
    input  logic rst_n
);
    // Token Manager ===
    logic [NUM_SEQUENCES-1:0] token_grant;          // One-hot: controls which seq drives DUT
    logic [NUM_SEQUENCES-1:0] sequence_done;        // Seq asserts when finished

    // DUT Mux ===
    // DUT Mux -> DUT
    logic [DUT_ADDR_W-1:0]    dut_addr;             // muxed from seq_dut_addr
    logic [DUT_DATA_W-1:0]    dut_wdata;            // muxed from seq_dut_wdata
    logic                     dut_valid;            // muxed from seq_dut_valid

    // Sequence -> DUT Mux
    logic [DUT_ADDR_W-1:0]    seq_dut_addr  [NUM_SEQUENCES]; 
    logic [DUT_DATA_W-1:0]    seq_dut_wdata [NUM_SEQUENCES];
    logic [NUM_SEQUENCES-1:0] seq_dut_valid;

endinterface
```
TODO: Add modports

## Sequence FSM