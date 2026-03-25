import re

"""Generate SystemVerilog wrapper modules for single-bit constraints."""


_BIT_ASSIGN_RE = re.compile(
    r"^\s*(?P<var>\w+)\s*\[(?P<bit>\d+)\]\s*(?P<op>==|!=)\s*(?P<value>.+?)\s*;?\s*$"
)


def generate_bit_assign(constraint_line: str, lfsr_width: int = 32) -> str:
    """Generate a bit-assign module from an expression like `data[0] == 1'b1`."""
    line = re.sub(r"//.*", "", constraint_line).strip()
    match = _BIT_ASSIGN_RE.match(line)

    if not match:
        return "// Error: Could not parse bit-assign constraint. Expected: var[bit] == value"

    var_name = match.group("var")
    module_name = f"{var_name}_bit_assign_module"
    bit = int(match.group("bit"))
    op = match.group("op")
    value = match.group("value").strip()

    rtl: list[str] = []
    rtl.append(f"module {module_name} (")
    rtl.append(f"    input  logic [{lfsr_width-1}:0] lfsr_in,")
    rtl.append(f"    output logic [{lfsr_width-1}:0] data")
    rtl.append(");")
    rtl.append("")

    if bit < lfsr_width - 1:
        rtl.append(f"    assign data[{lfsr_width-1}:{bit+1}] = lfsr_in[{lfsr_width-1}:{bit+1}];")

    if op == "==":
        rtl.append(f"    assign data[{bit}] = {value};")
    else:
        rtl.append(
            f"    assign data[{bit}] = (lfsr_in[{bit}] == {value}) ? ~({value}) : lfsr_in[{bit}];"
        )

    if bit > 0:
        rtl.append(f"    assign data[{bit-1}:0] = lfsr_in[{bit-1}:0];")

    rtl.append("")
    rtl.append("endmodule")
    return "\n".join(rtl)
