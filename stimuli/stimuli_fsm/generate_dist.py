import re

"""Parse a SystemVerilog dist constraint and emit combinational RTL."""


_DIST_RE = re.compile(r"(\w+)\s+dist\s*\{(.*)\}")
_RANGE_RE = re.compile(r"\[(\d+):(\d+)\]")


def _parse_dist_entries(body: str) -> list[dict[str, int]]:
    """Expand a dist body into a flat list of {val, weight} entries."""
    entries: list[dict[str, int]] = []
    terms = [term.strip() for term in body.split(",")]

    for term in terms:
        if not term:
            continue

        if ":=" in term:
            lhs, rhs = [part.strip() for part in term.split(":=", maxsplit=1)]
            operator = ":="
        elif ":/" in term:
            lhs, rhs = [part.strip() for part in term.split(":/", maxsplit=1)]
            operator = ":/"
        else:
            # Ignore malformed terms to preserve existing behavior.
            continue

        weight = int(rhs)
        range_match = _RANGE_RE.search(lhs)

        if not range_match:
            entries.append({"val": int(lhs), "weight": weight})
            continue

        lo = int(range_match.group(1))
        hi = int(range_match.group(2))
        count = hi - lo + 1

        if operator == ":=":
            # := means the provided weight applies to each value in the range.
            item_weight = weight
        else:
            # :/ splits a total weight across the range.
            item_weight = weight // count
            if item_weight == 0:
                item_weight = 1

        for value in range(lo, hi + 1):
            entries.append({"val": value, "weight": item_weight})

    return entries


def _build_case_items(map_table: list[dict[str, int]], var_name: str) -> list[str]:
    """Generate case items that map scaled random slots to output values."""
    lines: list[str] = []
    current_low = 0

    for item in map_table:
        weight = item["weight"]
        value = item["val"]
        range_high = current_low + weight - 1

        if weight > 0:
            if current_low == range_high:
                lines.append(f"        {current_low:<6}: {var_name} = {value};")
            else:
                lines.append(f"        [{current_low}:{range_high}]: {var_name} = {value};")

        current_low += weight

    return lines


def generate_dist(constraint_line: str, lfsr_width: int = 32, scaled_width: int = 64) -> str:
    """Generate a SystemVerilog module implementing weighted random dist behavior."""
    line = re.sub(r"//.*", "", constraint_line)
    match = _DIST_RE.search(line)

    if not match:
        return "// Error: Could not parse constraint format. Expected: 'var dist { ... };'"

    var_name = match.group(1)
    body = match.group(2)
    map_table = _parse_dist_entries(body)
    total_weight = sum(item["weight"] for item in map_table)

    rtl: list[str] = []
    rtl.append(f"// --- Generated Weighted Random Logic for '{var_name}' ---")
    rtl.append(f"// Input LFSR Width: {lfsr_width} bits")
    rtl.append(
        f"module {var_name}_dist_module (input logic [{lfsr_width-1}:0] lfsr_in, output logic [31:0] {var_name});"
    )
    rtl.append(f"logic [{scaled_width-1}:0] scaled_rand;")
    rtl.append("")
    rtl.append(f"// Scaling: Map LFSR to [0 : {total_weight-1}]")
    rtl.append(f"assign scaled_rand = (lfsr_in * {total_weight}) >> {lfsr_width};")
    rtl.append("")
    rtl.append("always_comb begin")
    rtl.append("    case (scaled_rand) inside")
    rtl.extend(_build_case_items(map_table, var_name))
    rtl.append(f"        default: {var_name} = '0; // Should not be reached")
    rtl.append("    endcase")
    rtl.append("end")
    rtl.append("endmodule")

    return "\n".join(rtl)