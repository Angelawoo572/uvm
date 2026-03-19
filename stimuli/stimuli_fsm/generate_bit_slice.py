import re

"""Generate SystemVerilog wrapper modules for bit-slice constraints."""


_BIT_SLICE_RE = re.compile(
    r"^\s*(?P<var>\w+)\s*\[(?P<msb>\d+):(?P<lsb>\d+)\]\s*(?P<op>==|!=)\s*(?P<value>.+?)\s*;?\s*$"
)


def generate_bit_slice(constraint_line: str, lfsr_width: int = 32) -> str:
    """Generate a bit-slice module from an expression like `data[7:4] != 4'b1111`."""
    line = re.sub(r"//.*", "", constraint_line).strip()
    match = _BIT_SLICE_RE.match(line)

    if not match:
        return "// Error: Could not parse bit-slice constraint. Expected: var[msb:lsb] == value"

    var_name = match.group("var")
    module_name = f"{var_name}_bit_slice_module"
    msb = int(match.group("msb"))
    lsb = int(match.group("lsb"))
    op = match.group("op")
    value = match.group("value").strip()

    if msb < lsb:
        msb, lsb = lsb, msb

    width = msb - lsb + 1
    neq_fix_mask = f"{{{{{width-1}{{1'b0}}}},1'b1}}" if width > 1 else "1'b1"

    rtl: list[str] = []
    rtl.append(f"module {module_name} (")
    rtl.append(f"    input  logic [{lfsr_width-1}:0] lfsr_in,")
    rtl.append(f"    output logic [{lfsr_width-1}:0] {var_name}")
    rtl.append(");")
    rtl.append("")

    if msb < lfsr_width - 1:
        rtl.append(f"    assign {var_name}[{lfsr_width-1}:{msb+1}] = lfsr_in[{lfsr_width-1}:{msb+1}];")

    if op == "==":
        rtl.append(f"    assign {var_name}[{msb}:{lsb}] = {value};")
    else:
        rtl.append(
            f"    assign {var_name}[{msb}:{lsb}] = (lfsr_in[{msb}:{lsb}] == {value}) ? (lfsr_in[{msb}:{lsb}] ^ {neq_fix_mask}) : lfsr_in[{msb}:{lsb}];"
        )

    if lsb > 0:
        rtl.append(f"    assign {var_name}[{lsb-1}:0] = lfsr_in[{lsb-1}:0];")

    rtl.append("")
    rtl.append("endmodule")
    return "\n".join(rtl)
