# UVM -> RTL execution flow

## System overview
System generates 3 RTL blocks + an orchestrator block:
![System-overview](./images/system-overview.png)

The 4 RTL blocks connect as such:
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

