# Stimuli Generation 

## The 5 Basic Types:
1. Bounded range:
```
constraint page_size { transfer_size inside {[1:1024]}; }
```
2. Semi-bounded range:
```
constraint within_upper { start_addr > 32'h0100_0000; }
```
```
constraint within_lower { start_addr < 32'h0104_0000; }
```
3. Enum types:
```
constraint imm_val_c { instr_name inside {C_SRAI, C_SRLI, C_SLLI}; }
```
4. Distribution:
```
constraint type_dist { packet_type dist { [1:3] := 10, 4 := 10, 5 := 1, [10:15] :/ 60 }; }
```
5. Bit assignment:
```
constraint addr_c { start_addr[1:0] == 0; }
```
### Stress Tests
1. Non-power of 2 ranges:
```
constraint len_c { char_len inside {0, 1, [31:33], [63:65], 126, 127}; }
```

## Composite/Second-order Types: 
1. Bit assignment + another basic type:
```
constraint within_range { 
    start_addr < 32'h0104_0000;
    start_addr > 32'h0100_0000; // start_addr inside {[a:b]};
    start_addr[1:0] == 0; // 100
}
```
```
constraint target_bank_c {
    addr inside {[32'h8000_0000 : 32'hBFFF_FFFF]}; 
    addr[2:0] == 3'b000; 
    addr[9:8] == 2'b10; 
}
```
Solver logic ideas:
```
1. Parser does some pre-processing
    - Extract number of constraints applied to every rand variable
    - Find number of bits not constrained/assigned

- New bound = [min >> short_bit : max >> short_bit] --> (output << short_bit || short_val) // in this case short_bit = 2, short_val == 2'b0
- Provide error handling for when no solution is found
```
2. Ordered constraints:
```
constraint within_range { 
    start_addr < (32'h0104_0000 - block_size*4);
    solve start_addr before block_size;
}
```
```
constraint c_mux_select { 
    solve opcode before mux_select;
    if (opcode == `MD_OP_REM) (mux_select == `MD_OUT_REM);
}
```
Solver logic ideas:
```
- Parser generates rand variable priority database:
    - Uses keywords solve ... before ... to assign relative priorities
- Seq <-> seq_item FSM reads from priority database to decide which variable to solve for next
- Seq <-> stim FSM should provide additional inputs (e.g. block_size, opcode) to solver module
```

3. Two rand variables:
```
constraint size_c { tkeep.size() == tdata.size(); }
```
```
constraint valid_reg_c { fwd_addr_reg != bw_addr_reg; }
```
```
constraint addr_valid { start_addr < end_addr; }
```

---

## Directory Structure

```
stimuli/
├── stimuli_fsm/          — core FSM hardware + Python RTL generation tools
├── constraint-example1/  — integration example connecting seq_fsm, stimuli_fsm, and drv_fsm
├── majd_examples/        — reference solver examples (dist, bit-assign)
├── find_range.py         — constraint region extractor (standalone)
├── multirange.sv         — two-region combinational solver
├── multirange_gt2.sv     — N-region generalized solver
├── composite1.sv         — composite constraint solver prototype
└── genus_*.rep           — synthesis area reports for multirange solvers
```

## stimuli_fsm — Core Flow

### Overview

The `stimuli_fsm/` directory contains the main RTL generation pipeline. Given a text file of SV-style constraint declarations, `main.py` generates a ready-to-compile set of SystemVerilog files.

```
constraints.txt  →  [main.py]  →  constraint_solver.sv  (generated: solver modules populated)
                              →  constraints.db          (generated: constraint ID mapping)
                              →  stimuli_fsm.sv          (copied from stimuli_fsm/ templates)
                              →  bounded_LFSR.sv         (copied from stimuli_fsm/ templates)
                              →  seq_fsm.sv              (copied from stimuli_fsm/ templates)
                              →  seq_stim_if.svh         (copied from stimuli_fsm/ templates)
```

### How to Run

```bash
cd stimuli/stimuli_fsm
uv run main.py <constraints.txt> <output_directory/>
```

Example:
```bash
uv run main.py constraints.txt test_output/
```

Output files appear in `test_output/`. The `constraint_solver.sv` template is populated with instantiations and module definitions for each constraint. A `constraints.db` file maps each constraint to its `solver_output[N]` index, type, bounds, and generated module name.

> Note: `constraints.txt` is generated from parser output — use `parse_seq_item_with_json.py` for standalone constraint blocks, or `parse_seq_with_json.py` for inline randomize constraints. See the `parser/` README for usage.

### Constraint Types Supported by main.py

`identify.py` classifies each constraint line into one of 7 types. Verified by running all types against the classifier:

| Type | Example | Solver output |
|------|---------|---------------|
| `inside` | `addr inside {[11:20]}` | bounds `(11, 20)` passed to LFSR, no module generated |
| `compare` | `addr > 4'h4 && addr < 4'hC` | bounds `(5, 11)` passed to LFSR, no module generated |
| `assign` | `rst_n == 1'b0` | generates `rst_n_assign_module` |
| `bit-assign` | `data[0] == 1'b1` | generates `data_bit_assign_module` |
| `bit-slice` | `data[7:4] != 4'b1111` | generates `data_bit_slice_module` |
| `dist` | `payload dist { 0 := 5, 1 := 95 }` | generates `payload_dist_module` |
| `parity` | `parity == (^data)` | identified but no module generated — passes through `lfsr_output` |

### Simulating stimuli_fsm

Compile and run from `stimuli_fsm/`:

```bash
vcs -full64 -sverilog +v2k +incdir+. \
  seq_stim_if.svh \
  stimuli_fsm_tb.sv \
  stimuli_fsm.sv \
  seq_fsm.sv \
  constraint_solver.sv \
  bounded_LFSR.sv

./simv
```

Observed results with the default `constraint_solver.sv` (only `solver_output[0]` implemented):

- Constraint ID 0: 30 nonzero values collected, spanning the three requested ranges
- Constraint IDs 1, 2, 3: all zeros — solver outputs not yet implemented

### Assumptions

- Input constraints must be one per line in SV constraint block syntax.
- `inside` and `compare` constraints map to `solver_output[0]` (bounded LFSR pass-through) with the extracted bounds as `lower_bound`/`upper_bound`.
- All other types generate standalone combinational modules instantiated in `constraint_solver.sv`.
- Default LFSR width is 32 bits; override with `--lfsr-width` option.
- Seed must be nonzero; a zero seed is redirected to `32'h1` internally.

## constraint-example1

An integration example connecting `seq_fsm`, `stimuli_fsm`, `drv_fsm`, and `constraint_solver` for the example1-basic UVM stress test. Contains a pre-populated `constraint_solver.sv` and a `constraints.db` mapping 13 constraint IDs derived from the example1-basic sequences.

### Known Issue — Does Not Compile

Compiling with VCS produces the following errors:

```
Error: req_data_t is unknown in seq_stim_if.svh line 10
Error: `NUM_CONSTRAINTS undefined in req_data.svh line 2
```

Root cause: `seq_stim_if.svh` uses `req_data_t` which is defined in `req_data.svh`, and `req_data.svh` uses `` `NUM_CONSTRAINTS `` which is defined in `constants.svh`. The correct include order has not been established. *(Need to confirm with author: is there a correct compile order or build script?)*

## find_range.py

Standalone Python script that parses SV constraint blocks and computes valid numeric regions per variable. Supports `inside`, relational operators (`>=`, `<=`, `>`, `<`, `==`), logical `&&`/`||`, negated `inside`, and intersection of multiple constraints on the same variable.

```bash
cd stimuli
uv run find_range.py   # runs built-in self-test
```

Self-test passes for all included examples. Output format:

```
Variable : addr
  Regions : 2
  Region 1: min=0    max=15
  Region 2: min=32   max=63
```

*(Need to confirm with author: is find_range.py intended to feed into composite1.sv / constraint_solver.sv, or is it standalone?)*

## multirange.sv / multirange_gt2.sv

Combinational RTL solvers that map an LFSR input to a value within a union of legal ranges, proportional to each region's span.

- `multirange.sv` — two fixed regions (`min0/max0`, `min1/max1`)
- `multirange_gt2.sv` — parameterized N regions (`N_REGIONS`, arrays of `min_bounds`/`max_bounds`)

Synthesis reports (`genus_*.rep`) using ASAP7 standard cells show:
- `multirange.sv`: 3021 cells, total area 8281.593
- `multirange_gt2.sv`: 3786 cells, total area 10262.401

*(Need to confirm with author: relationship to bounded_LFSR and main stimuli_fsm flow.)*

## Known Issues / Limitations

- **`constraint-example1` does not compile** — include order issue, see above.
- **Parity constraints not solved** — `identify.py` identifies parity constraints but solving them is out of scope by design; the output passes through raw `lfsr_output`.
- **`constraint_solver.sv` default is a stub** — only `solver_output[0]` is wired; all other IDs return 0 until the user populates the solver or runs `main.py`.
- **`inside`/`compare` bounds not automatically wired** — these constraint types return bounds via `constraints.db` but do not auto-configure the LFSR `lower_bound`/`upper_bound` ports; the user must wire these manually.