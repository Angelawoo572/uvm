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

> Note: example1 and example2 share the same coverage module, so there is no `parse_2` target.

**Step 2: Generate synthesizable SystemVerilog**
```bash
make all
```
This runs `parsed_to_cov.py` then `gen_cov.py` in sequence.

**Or run scripts individually:**
```bash
python3 parsed_to_cov.py outputs/cov_parsed.json outputs/cov_usable.json outputs/constants.svh
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

## Generated Output Structure (example1)

Running on example1 produces four modules in `coverage.sv`:

- **`opcodes_cg`** — one module per covergroup; implements bin counters as `always_ff` arrays, updated via `case inside` on the coverpoint expression
- **`output_mod`** — serializes counter values into bytes selected by `signal_id` and `byte_ctr`, for transmission to the host
- **`cov_fsm`** — FSM that sequences the byte-serial output; coordinates with an external UART transmitter via `tx_ready` and `packet_done`
- **`cov`** — top-level module instantiating all of the above

`txuart.v` and `rxuart.v` are third-party UART modules included for pairing with `output_mod`/`cov_fsm` to send coverage data to the host. The host-side configuration is not yet complete.

The top-level `cov` module ports for example1:
- Inputs: `clk`, `rst`, `sample`, `m_item_addr_i` (32-bit), `sim_complete`, `tx_ready`, `packet_ready`, `packet_done`
- Outputs: per-bin counters (`opcodes_cg__MODE0_cnt`, etc.), `uart_out_cov_byte`, `done`, `signal_id`, `send_id`

## Assumptions

- All constants referenced in bin ranges (e.g. `MODE0_OFFSET`) must be resolvable as single values from `constants.svh`. Only integer literals and basic SV tick notation (`'h`, `'b`, `'d`) are supported.
- Signal widths for coverpoint expressions default to 32 bits, since elaboration-time width is not available from the CST.
- The `sample` input is externally controlled; the module does not generate its own sampling trigger.
- The generated `coverage.sv` currently uses a relative path for the `include` statement (`outputs/constants.svh`). This will be updated to reference the current directory only.

## Known Issues / Limitations

- **example3 fails with `ValueError: math domain error`** in `gen_cov.py`. Root cause: `parsed_to_cov.py` cannot evaluate arithmetic constant expressions (e.g. `ARRAY_OFFSET + ARRAY_SIZE - 1`), leaving a coverpoint with zero bins. `math.log2(0)` then raises the error. A temporary fix has been applied by hardcoding the value; a proper fix using a `generate` statement is planned.
- **Constant arithmetic expressions not supported:** `parsed_to_cov.py` only resolves single-value constants. Compound expressions produce a warning and resolve to 0.
- **Cross coverage:** `gen_cov.py` has partial cross coverage support; array flattening within crosses is noted as a TODO.
- **Host-side UART not yet configured:** `txuart.v`/`rxuart.v` are included but the full off-chip export path is not yet operational.