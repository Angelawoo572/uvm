# UVM -> RTL execution flow

TODO:
- Sequences do not trigger sampling -> it is done by coverage collector that receives transactions from monitor
- Flow should include drivers and monitors (question: so we don't abstract it away?)
- SHould distinct betweeen sequence_item and sequence

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
Step 2: Seq 0 requests Stimuli
        │
        ├──→ Stimuli: Generates random values (5 cycles)
        │
Step 3: Seq 0 receives solved data
        │
        ├──→ Seq 0: Drives transaction to DUT through Orchestrator
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
Only **1 sequence** can drive the DUT at a time

The `token manager` and `DUT mux` within the orchestrator work as such:
```bash
┌───────────────────┐            
│   Orchestrator    │            
│  (Token manager)  │            
└───┬───────────────┘            
    │token_grant (one-hot)       
    ├────────────┐               
    │            │               
  ┌─▼───┐     ┌──▼──┐            
  │Seq 0│ ... │Seq n│            
  └─┬───┘     └────┬┘            
    └──────┬───────┘            
     ┌─────▼────────┐   
     │ Orchestrator │          
     │  (DUT mux)   │◄───────  token_grant    
     └─────┬────────┘              
           │                   
           ▼                     
          DUT                                                                     
```      

**Interface:**
```systemverilog
interface uvm_orchestrator_if #(
    parameter int NUM_SEQUENCES = 8,
    parameter int DUT_ADDR_W = 32,
    parameter int DUT_DATA_W = 32
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

    modport orchestrator (
        input  clk, rst_n,
        // Token manager
        output token_grant, 
        input  sequence_done,

        // DUT mux
        input seq_dut_addr, seq_dut_wdata, seq_dut_valid,
        output dut_addr, dut_wdata, dut_valid
    );
    // TODO: Note that dut can return data too, how do we connect this to coverage?

    modport sequence (
        input  clk, rst_n,
        // Token manager
        input  token_grant,
        output sequence_done,

        // DUT mux
        output seq_dut_addr, seq_data_wdata, seq_dut_valid
    );

endinterface
```

## Stimuli FSM (solver)
Effectively, the solver would have a bank of PRNGs. Once the Sequence FSM requests a constrained stimuli, the solver picks the PRNG which best suits the constraints and returns a `solved_data` value. I think some notion of a `constraint_id` which is pre-processed by the software would be great. (i.e. `constraint_id == 1` maps to a PRNG which solves for even random numbers between 12 and 256, etc.)

**Interface:**
```systemverilog
module uvm_stimuli #(
    parameter int NUM_CONSTRAINTS = 64,
    parameter int CONSTRAINT_ID_W = 8,
    parameter int SOLVED_DATA_W = 128,
    parameter int SEQ_ID_W = 8
)(
    input  logic clk, rst,

    // Request interface ===
    input  logic solve_req,
    input  logic [CONSTRAINT_ID_W-1:0] constraint_id,
    input  logic [SEQ_ID_W-1:0] sequence_id, // ID of sequence FSM

    // Response interface ===
    output logic solve_done,
    output logic [SEQ_ID_W-1:0] solved_data,

    // PRNG control ===
    input  logic [31:0] global_seed,
    input  logic seed_load,
    input  logic [2:0] seed_load,

    // Error messages? (i.e. solve_failed, timeout, etc.)
)
```

## Coverage FSM
Whenever the sequence executes a transaction, it can trigger a `cov_sample()` pulse to the coverage FSM which then takes a snapshot of inputs/outputs from the DUT interface.

**Workflow**:
I think Andrew has a great idea

## Sequence FSM
**State transitions:**
```bash
       [IDLE] 
          ↓                       
    Wait for token                
          ↓                       
   [REQ_RANDOM] ← Request solver  
          ↓                       
   [WAIT_SOLVE] ← Solver solving  
          ↓                       
    [DRIVE_DUT] ← Drive interface 
          ↓                       
   [SAMPLE_COV] ← Record result          
          ↓    (if sample_cov())  
       [DONE] 
```