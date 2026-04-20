# Parser Module

Converts UVM SystemVerilog source files into structured JSON for use by the assembler and coverage modules.

## Scripts

**`sv_to_json.py`** — generates a raw Concrete Syntax Tree (CST) JSON from any `.sv`/`.svh` file. This is the base layer all other parsers build on.

**`parse_driver_with_json.py`** — extracts `run_phase` flow from classes extending `uvm_driver #(T)`: sequencer handshakes, signal assignments, clock edges, and branch/loop structure.

**`parse_monitor_with_json.py`** — extracts `build_phase` and `run_phase` from classes extending `uvm_monitor`: config_db gets, interface sampling, and analysis port writes.

**`parse_seq_item_with_json.py`** — extracts field declarations (with rand qualifier) and constraint blocks from classes extending `uvm_sequence_item`.

**`parse_seq_with_json.py`** — extracts the `body` task flow from classes extending `uvm_sequence #(T)`: create, randomize, start_item, finish_item, and UVM macros (`uvm_do`, `uvm_do_with`, etc.).

**`constraint_preprocessor.py`** — extracts and normalizes rand variable constraints into numeric bounds (`original_min`, `original_max`, `FIXED_MASK`, `FIXED_VAL`) for use by the stimuli constraint solver. Intended input is a sequence item file with constraints of the form `inside {[A:B]}`, `<`/`<=`/`>`/`>=`, or bit-slice `==`.

> `parse_drivers.py`, `parse_seq.py`, `parse_seq_item.py` are earlier versions also in active use. The `_with_json.py` versions add JSON output support and are used by the assembler pipeline; the non-json versions are used separately by other team members.

## Setup

From the repo root:
```bash
uv sync
```

## How to Run

All scripts are run from the `parser/` directory with `uv run`.

```bash
# CST JSON (required input for downstream tools)
uv run sv_to_json.py <input.svh> <output.json>

# Component parsers — text output by default, add --format json for JSON
uv run parse_driver_with_json.py <file.svh>
uv run parse_monitor_with_json.py <file.svh>
uv run parse_seq_item_with_json.py <file.svh>
uv run parse_seq_with_json.py <file.svh>

# Constraint bounds extraction
uv run constraint_preprocessor.py <file.svh>
uv run constraint_preprocessor.py <file.svh> --out result.txt
```

All parsers default to writing output next to the input file with a descriptive suffix (e.g., `stress.pkg_seq_item_summary.txt`). Use `--out` to override.

## Inputs and Outputs

| Script | Input | Output |
|--------|-------|--------|
| `sv_to_json.py` | `.sv` / `.svh` | CST JSON |
| `parse_driver_with_json.py` | `.sv` / `.svh` | `_summary.txt` or `_summary_json.json` |
| `parse_monitor_with_json.py` | `.sv` / `.svh` | `_monitor_summary.txt` or `.json` |
| `parse_seq_item_with_json.py` | `.sv` / `.svh` | `_seq_item_summary.txt` or `.json` |
| `parse_seq_with_json.py` | `.sv` / `.svh` | `__seq_summary.txt` or `.json` |
| `constraint_preprocessor.py` | `.sv` / `.svh` | `_constraint_summary.txt` |

## Assumptions

- Input files follow UVM coding conventions. Parsers identify components by base class name (`uvm_driver`, `uvm_monitor`, `uvm_sequence`, `uvm_sequence_item`) — they are not general-purpose SV parsers.
- Both the class declaration and any out-of-class method definitions (e.g., `task sfr_driver::run_phase(...)`) must be in the same input file. Confirmed by author: each component-specific parser requires this.
- Only locally declared fields and constraints are extracted; inherited members are not expanded.
- `pyslang` will emit diagnostics when UVM base class symbols are not in scope (common when parsing a single package file without the full UVM library). These are safely ignored — parsing still completes.

## Observed Limitations

- `constraint_preprocessor.py` does not support inline `with { ... }` randomize constraints, so running it on `stress.pkg.sv` produces no output. It is intended for standalone constraint blocks using `inside`, `<`/`<=`/`>`/`>=`, or bit-slice `==` syntax.
- `parse_drivers.py` and `parse_driver_with_json.py` both default to writing `<basename>_summary.txt`, so running both on the same file overwrites the earlier output.
- Diagnostics from `parse_seq_item_with_json.py` print as `<pyslang.pyslang.Diagnostic object>` rather than a human-readable message.