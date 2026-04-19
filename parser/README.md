# Parser Module

Parses UVM SystemVerilog (`.sv`/`.svh`) files into structured JSON or text summaries for use by the assembler, coverage, and stimuli modules.

**Setup:** `uv sync` from repo root (requires `pyslang >= 10.0.0`).

---

## Scripts

### `sv_to_json.py` — Raw CST export
```bash
uv run python parser/sv_to_json.py <input.svh> <output.json>
```
Outputs a full Concrete Syntax Tree (CST) JSON. Use this to inspect the tree; not required before running other scripts (they call pyslang internally).

---

### `parse_seq_item_with_json.py` — Sequence item fields and constraints
```bash
uv run python parser/parse_seq_item_with_json.py <file.svh> [--format json] [--pretty] [--no-diags]
```
**Output:** fields (`name`, `sv_type`, `rand_mode`) and constraint text for each `uvm_sequence_item` subclass.  
**Default output file:** `<input>_seq_item_summary.txt` (or `.json`)

**Assumptions / Limitations:**
- Detects seq_item classes by `extends uvm_sequence_item` (direct or through inheritance chain)
- Fields named `name`, `this`, `state`, `seed`, `on_ff` are ignored
- Only locally declared fields are extracted — inherited fields are not included
- Constraint text is reconstructed from CST tokens; formatting may differ from source

> `parse_seq_item.py` appears to be an older text-only version of this script. *(Confirm with author: deprecated?)*

---

### `parse_seq_with_json.py` — Sequence body flow
```bash
uv run python parser/parse_seq_with_json.py <file.svh> [--format json] [--include-calls]
```
**Output:** ordered event list (`declare`, `create`, `randomize`, `start`, `finish`, macro events) for each `uvm_sequence #(T)` subclass.  
**Default output file:** `<input>__seq_summary.txt` (or `.json`)

**Assumptions / Limitations:**
- Detects sequence classes by `extends uvm_sequence #(T)`; uses `T` to identify relevant handles
- Inline `randomize() with { ... }` constraints are extracted and shown separately
- `if/else` and `while` context is tracked per event via a path field
- Generic calls omitted by default; use `--include-calls` to include

> `parse_seq.py` appears to be an older text-only version. *(Confirm with author: deprecated?)*

---

### `parse_driver_with_json.py` — Driver run_phase flow
```bash
uv run python parser/parse_driver_with_json.py <file.svh> [--format json]
```
**Output:** event trace of `run_phase` for each `uvm_driver #(T)` subclass.  
**Default output file:** `<input>_summary.txt` (or `<input>_summary_json.json`)

**Event kinds:** `declare`, `seq_get` (`get_next_item`/`try_next_item`/`get`), `seq_done` (`item_done`/`put_response`), `assign`, `edge`, `wait`, `branch`, `loop`

**Assumptions / Limitations:**
- Only `run_phase` is extracted
- Class-level fields are emitted as `declare` events at the top
- Timing controls other than `@(posedge/negedge <signal>)` are silently skipped
- Generic calls not in the sequencer handshake list are not emitted

> `parse_drivers.py` appears to be an older version (missing `MemberAccessExpression` handling in call resolution). *(Confirm with author: deprecated?)*

---

### `parse_monitor_with_json.py` — Monitor phase flows
```bash
uv run python parser/parse_monitor_with_json.py <file.svh> [--format json]
```
**Output:** event trace for `build_phase` and `run_phase` of each `uvm_monitor` subclass.  
**Default output file:** `<input>_monitor_summary.txt` (or `<input>_monitor_summary_json.json`)

**Assumptions / Limitations:**
- Only classes directly `extends uvm_monitor` are detected (no inheritance chain resolution)
- Supports `@(vif.mon_cb)` style timing controls in addition to `@(posedge clk)`
- UVM macros inside `EmptyStatement` nodes are captured via trivia inspection

> No `parse_monitor.py` (non-JSON version) found. *(Confirm with author: was one planned?)*

---

### `constraint_preprocessor.py` — Constraint value ranges
```bash
uv run python parser/constraint_preprocessor.py <file.svh> [--out result.txt]
```
**Output:** per `rand` variable in each `uvm_sequence_item` subclass:
- `original_min` / `original_max` — from `inside {[A:B]}` or relational constraints
- `FIXED_MASK` / `FIXED_VAL` — from `var[msb:lsb] == value` bit-fix constraints

**Supported constraint forms:** `inside {[A:B]}`, `< <= > >=`, `var[msb:lsb] == value`

**Limitations:**
- Symbolic constants (e.g. `MODE0_OFFSET`) in ranges cannot be resolved — only integer literals
- Cross-variable constraints are skipped
- Conflicting fixed-bit assignments on the same variable raise `ValueError`

> Intended output destination (assembler vs stimuli) unclear from code alone. *(Confirm with author)*

---

## General Limitations

- Not a full SV compiler — relies on UVM coding conventions; unrecognized constructs are silently skipped
- Files with missing includes or macros will produce pyslang diagnostics; scripts continue but output may be incomplete
- CST JSON structure is `pyslang`-version-dependent; scripts target `pyslang >= 10.0.0`