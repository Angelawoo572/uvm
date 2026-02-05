# UVM -> RTL Execution Model

## 1. Architectural Overview
* Note: Stimuli and Solver may be used interchangeably

### 1.1 Schematics
![Improved schematic](./images/improved-schematic.png)


#### Principles:
- Sequence-centric design: Each sequence-item = independent FSM
- Shared solver: Simuli FSM has a bank of PRNGs which run independently from whole system
- Token-based arbitration: Some concept of a global token where only one sequence drives DUT at a time
- Hierarchical control: 
```bash
top
├───coverage (FSM)
└───sequences (FSM)
    └───stimuli (FSM)
            └───solvers (FSM)
```

### 1.2 Concept of time
**Core principle**: One UVM execution step = One RTL clock cycle

| UVM Construct | RTL Timing | Notes |
| --- | --- | --- |
|`randomize()`|Multi-cycle handshake: Seq -> Stimuli FSM, wait N cycles | Stimuli may take 1-10 cycles depending on constraint complexity |
|`sample()` | 1-cycle pulse to Coverage FSM | |
|`wait(cond)` | Poll each cycle until cond=1 | Seq FSM stays in WAIT state |
|`@(posedge clock)`|1-cycle dealy in sequence FSM | Could stall at explicit WAIT_CLK state |

**Main note:**
- Sequence FSMs advance one per clock cycle
- Stimuli FSM operates asynchronously with wait state (multi-cycle operations)
- Coverage FSM samples on explicit pulse from active sequence
- All modules synchronized to single global clock


### Notes
- Some key ideas of monitors/drivers/sequencers
- Label signals in between them
- Improve diagram with specific signals