# UVM -> RTL execution flow

## System overview
System generates **3 RTL blocks** (Sequence, Coverage and Stimuli FSMs)  + an **orchestrator block**:

![System-overview](./images/system-overview.png)

**Notes**: 
- Driver and Monitor are protocol-aware and may change between designs depending on the protocol.
- Coverage exports all bin/hit counts to the user; it does not decide when to stop.
- Transaction: the lowest level seq_item (maps to DUT-level signals)
- Bounded LFSR is used for all stimulus generation. The Seq FSM passes bounds and constraint IDs to the Stimuli FSM; per-constraint solver modules handle transformation.

## Execution overview
There will be 2 independent workflows:
1. Sequence -> Solver -> Driver interaction
```bash
Step 0: Load seed into Stimuli FSM
Step 1: Seq FSM executes this loop for its seq_items:
        - Determine next seq_item to execute based on conditional logic
        - Request stimulus data from Stimuli FSM for that seq_item
        - Issue transaction to Driver
        - Wait for driver to complete transaction
        - Repeat or finish when done
```
2. Coverage -> Monitor interaction
```bash
Step 1: Coverage FSM determines when to sample events
Step 2: If Coverage FSM decides to sample:
    - Sample transaction from Monitor's observed DUT signals
    - Coverage FSM updates counters/bins based on sampled transaction
Step 3: Repeat until test terminates
```

**Note**: Driver and Monitor should be protocol-aware

## Interface overview
There are 5 handshake protocols/interfaces required:
1. Orchestrator <-> Sequence FSM
2. Sequence FSM <-> Stimuli FSM
3. Orchestrator <-> Coverage FSM
4. Sequence FSM <-> Driver
5. Coverage FSM <-> Monitor

Across all interfaces:
- `ready` / `valid` for data transfter
- `start` / `done` for control

**Note**: Define handshake within the sequence FSM too? (between sequence <-> seq_item?) — TBD

#### Orchestrator <-> Sequence FSM
```systemverilog
interface orch_seq_if #(
    parameter int NUM_SEQUENCES = 8
) (
    input  logic clk, rst_n
);
    
    // Orchestrator -> Sequence
    logic                     start;

    // Sequence -> Orchestrator
    logic [NUM_SEQUENCES-1:0] done;
    logic [NUM_SEQUENCES-1:0] busy;

endinterface
```

#### Sequence FSM <-> Stimuli FSM
![Seq-Stimuli Interaction](./images/seq-stimuli.png)

Current implementation in `stimuli_fsm/seq_stim_if.svh`:

```systemverilog
interface seq_stim_if #(
    parameter DATA_W = 32,
    parameter NUM_CONSTRAINTS = 8
)(
    input  logic clk, rst_n
);
    // Request 
    logic [DATA_W-1:0] seed;
    logic [DATA_W-1:0] lower_bound, upper_bound;
    logic [$clog2(NUM_CONSTRAINTS)-1:0] constraint_id;  // some database of constraints
    logic       req_seed_load;
    logic       req_valid;
    logic       req_ready;

    // Response
    logic [DATA_W-1:0] solved_data;
    logic              rsp_valid;
    logic              rsp_ready;
    
    modport STIM (
        input clk, rst_n,

        // Request
        input seed, lower_bound, upper_bound,
        input constraint_id,
        input req_seed_load,
        output req_ready,
        input req_valid,

        // Response
        output solved_data,
        input rsp_ready,
        output rsp_valid
    );

    modport SEQ (
        input clk, rst_n,

        // Request
        output seed, lower_bound, upper_bound,
        output constraint_id,
        output req_seed_load
        input req_ready,
        output req_valid,

        // Response
        input solved_data,
        output rsp_ready,
        input rsp_valid
    );

endinterface
```

> **Note**: The assembler-generated `seq_stim_if` (in `rtl_example1.sv` / `rtl_example2.sv`) uses `req_item_s req` as the request signal (carrying the full seq_item struct), rather than separate `lower_bound`, `upper_bound`, and `constraint_id` signals.

#### Orchestrator <-> Coverage FSM
```systemverilog
interface orch_cov_if (
    input  logic clk, rst
);

    // Orchestrator -> Coverage
    logic enable;
    logic stop;

    // Coverage -> Orchestrator
    logic        done;
    logic [15:0] coverage_pct; // optional?

endinterface
```

#### Sequence FSM <-> Driver

**Note**: Driver uses a request/response mechanism. The seq_item is passed as a packed struct (`req_item_s`). Driver signals completion via `rsp_valid`/`rsp_ready`.

Current implementation in `stimuli/constraint-example1/seq_drv_if.svh`:

```systemverilog
interface seq_drv_if (
    input logic clk,
    input logic rst_n
);
    // Data from seq_fsm to drv
    req_item_s data_to_driver;

    // Handshake
    logic req_valid;
    logic req_ready;
    logic rsp_valid;
    logic rsp_ready;

    modport SEQ (
        input clk,
        input rst_n,

        output data_to_driver,
        output req_valid,
        input req_ready,

        input rsp_valid,
        output rsp_ready
    );

    modport DRV (
        input clk,
        input rst_n,

        input data_to_driver,
        input req_valid,
        output req_ready,

        output rsp_valid,
        input rsp_ready
    );

endinterface
```

> **Note**: The assembler-generated `seq_drv_if` (in `rtl_example1.sv` / `rtl_example2.sv`) uses `req_item_s req` instead of `req_item_s data_to_driver` as the signal name.

#### Coverage FSM <-> Monitor

**Note**: Coverage FSM samples data from the Monitor, not directly from DUT signals. The Monitor observes DUT outputs and forwards them to Coverage via this interface.

```systemverilog
interface cov_mon_if #(
    parameter MON_W = 64
)(
    input logic clk, rst_n
);

  // Monitor -> Coverage
  logic             sample_valid;
  logic [MON_W-1:0] sample_data;

  // Coverage -> Monitor
  logic sample_en;   // tells monitor to snapshot

endinterface
```