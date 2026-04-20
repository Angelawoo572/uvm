# Coverage Module

Translates SystemVerilog functional coverage definitions into synthesizable SystemVerilog hardware that counts bin hits and exports coverage data.

## Pipeline

```
cov.svh + constants.svh
    → [sv_to_json.py]     → outputs/cov_parsed.json   (CST JSON)
    → [parsed_to_cov.py]  → outputs/cov_usable.json   (coverage IR)
    → [gen_cov.py]        → outputs/coverage.sv        (synthesizable SV)
```

## How to Run

All commands are run from the `coverage/` directory.

**Step 1: Parse a coverage source file**
```bash
make parse_1   # uses uvm_samples/stress/example1-basic/cov.svh
make parse_3   # uses uvm_samples/stress/example3-covcol/cov.svh
```
This runs `sv_to_json.py` on the coverage source and copies `constants.svh` into `outputs/`.

**Step 2: Generate synthesizable SystemVerilog**
```bash
make all
```
This runs `parsed_to_cov.py` then `gen_cov.py` in sequence.

**Or run scripts individually:**
```bash
# Step 2a: convert CST JSON to coverage IR
python3 parsed_to_cov.py outputs/cov_parsed.json outputs/cov_usable.json outputs/constants.svh

# Step 2b: generate coverage SV
python3 gen_cov.py outputs/cov_usable.json outputs/coverage.sv outputs/constants.svh
```

## Inputs and Outputs

| File | Description |
|------|-------------|
| `cov.svh` | Input: SystemVerilog coverage source (covergroups, coverpoints, bins) |
| `constants.svh` | Input: parameter definitions referenced by bin ranges |
| `outputs/cov_parsed.json` | Intermediate: raw CST JSON from `sv_to_json.py` |
| `outputs/cov_usable.json` | Intermediate: normalized coverage IR used by `gen_cov.py` |
| `outputs/coverage.sv` | Output: synthesizable SystemVerilog coverage model |

`cov.json` in this directory is a JSON schema specification for the coverage IR format — it is not an input to any script.

## Generated Output Structure (example1-basic)

Running on example1-basic produces the following modules in `coverage.sv`:

- **`opcodes_cg`** — one module per covergroup; implements bin counters as `always_ff` arrays, updated via `case inside` on the coverpoint expression
- **`output_mod`** — serializes counter values into bytes, selected by `signal_id` and `byte_ctr`; intended for off-chip data export
- **`cov_fsm`** — FSM that sequences the byte-serial output; coordinates with an external UART transmitter (`tx_ready`, `packet_done`)
- **`cov`** — top-level module instantiating all of the above

The top-level `cov` module ports for example1-basic:
- Inputs: `clk`, `rst`, `sample`, `m_item_addr_i` (32-bit), `sim_complete`, `tx_ready`, `packet_ready`, `packet_done`
- Outputs: per-bin counters (`opcodes_cg__MODE0_cnt`, etc.), `uart_out_cov_byte`, `done`, `signal_id`, `send_id`

`rxuart.v` and `txuart.v` are third-party UART modules included for reference to pair with `output_mod`/`cov_fsm` for off-chip export. *(Need to confirm with author.)*

## Assumptions

- All constants referenced in bin ranges (e.g. `MODE0_OFFSET`) must be resolvable from `constants.svh`. Only integer literals and basic SV tick notation (`'h`, `'b`, `'d`) are supported — arithmetic expressions are not evaluated.
- Signal widths for coverpoint expressions default to 32 bits, since width information is not available from the CST without full elaboration.
- The `sample` input is assumed to be externally controlled; the module does not generate its own sampling trigger.
- The generated `coverage.sv` uses `` `include outputs/constants.svh `` with a relative path, so it must be compiled from the `coverage/` directory or the include path must be adjusted.

## Known Issues / Limitations

- **example3 fails with `ValueError: math domain error`** during `gen_cov.py`. The cause is a coverpoint with zero regular bins (only illegal bins), which causes `math.log2(0)` to fail. Confirmed root cause: `parsed_to_cov.py` cannot resolve `ARRAY_OFFSET_CEILING = ARRAY_OFFSET + ARRAY_SIZE - 1` because constant arithmetic expressions are not supported, leaving bin ranges empty.
- **Constant expression resolution:** `parsed_to_cov.py` only resolves single-value constants. Expressions like `ARRAY_OFFSET + ARRAY_SIZE - 1` produce a warning and resolve to 0.
- **Coverpoint reference name empty:** In the generated output for example1, the coverpoint `reference` field is empty (producing port names like `_MODE0_cnt` instead of `cp_addr_MODE0_cnt`). This appears to be a parsing issue in `parsed_to_cov.py` when the coverpoint label is defined using a named label syntax.
- **Cross coverage:** `gen_cov.py` has partial cross coverage support but the flatten implementation (`gen_flat_cross`) is noted as a TODO for array flattening.
- **`make debug` target:** runs `gen_cov.py` under `pdb` directly on `outputs/cov_usable.json` without re-parsing — useful for debugging generation issues independently of parsing.