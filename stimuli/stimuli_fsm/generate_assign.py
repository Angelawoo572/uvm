import re

"""Generate SystemVerilog wrapper modules for simple equality constraints."""


_ASSIGN_RE = re.compile(
    r"^\s*(?P<var>\w+)\s*(?:\[(?P<msb>\d+):(?P<lsb>\d+)\])?\s*==\s*(?P<value>.+?)\s*;?\s*$"
)


def generate_assign(constraint_line: str, total_width: int = 32) -> str:
    """Generate an assign module from an expression like `addr[1:0] == 2'h0`."""
    line = re.sub(r"//.*", "", constraint_line).strip()
    match = _ASSIGN_RE.match(line)

    if not match:
        return "// Error: Could not parse assign constraint. Expected: var[msb:lsb] == value"

    var_name = match.group("var")
    module_name = f"{var_name}_assign_module"
    msb_str = match.group("msb")
    lsb_str = match.group("lsb")
    value = match.group("value").strip()

    rtl: list[str] = []
    rtl.append(f"module {module_name} (")
    rtl.append(f"    input  logic [{total_width-1}:0] lfsr_in,")
    rtl.append(f"    output logic [{total_width-1}:0] {var_name}")
    rtl.append(");")
    rtl.append("")

    if msb_str is not None and lsb_str is not None:
        msb = int(msb_str)
        lsb = int(lsb_str)
        if msb < lsb:
            msb, lsb = lsb, msb

        # Keep unconstrained bits random and constrain only the selected slice.
        if msb < total_width - 1:
            rtl.append(
                f"    assign {var_name}[{total_width-1}:{msb+1}] = lfsr_in[{total_width-1}:{msb+1}];"
            )

        rtl.append(f"    assign {var_name}[{msb}:{lsb}] = {value};")

        if lsb > 0:
            rtl.append(f"    assign {var_name}[{lsb-1}:0] = lfsr_in[{lsb-1}:0];")
    else:
        rtl.append(f"    assign {var_name} = {value};")

    rtl.append("")
    rtl.append("endmodule")
    return "\n".join(rtl)




      