import re

"""Parse SystemVerilog compare constraints and extract numeric bounds."""


_COMPARE_CLAUSE_RE = re.compile(r"^\s*(?P<var>\w+)\s*(?P<op>>=|<=|>|<)\s*(?P<value>.+?)\s*$")


def _max_lfsr_value(lfsr_width: int) -> int:
    return (1 << lfsr_width) - 1


def _parse_sv_int(value: str) -> int:
    """Parse decimal and common SystemVerilog integer literals (e.g. 4'hC, 8'd10)."""
    token = value.strip().rstrip(";")

    sv_match = re.fullmatch(
        r"(?:(?P<width>\d+)')?(?P<base>[sS]?[dDhHbBoO])(?P<digits>[0-9a-fA-F_xXzZ?]+)",
        token,
    )
    if sv_match:
        base = sv_match.group("base").lower()[-1]
        base_map = {"d": 10, "h": 16, "b": 2, "o": 8}
        digits = sv_match.group("digits").replace("_", "")
        # Treat unknown bits as zero for bound computation.
        digits = re.sub(r"[xXzZ?]", "0", digits)
        return int(digits, base_map[base])

    return int(token, 10)


def generate_compare(constraint_line: str, lfsr_width: int = 32) -> tuple[int, int]:
    """Extract [lower_bound, upper_bound] from compare clauses and clamp to LFSR width."""
    line = re.sub(r"//.*", "", constraint_line).strip()

    max_value = _max_lfsr_value(lfsr_width)
    lower_bound = 0
    upper_bound = max_value
    var_name = None

    for clause in [part.strip() for part in line.split("&&") if part.strip()]:
        match = _COMPARE_CLAUSE_RE.match(clause)
        if not match:
            raise ValueError(f"Could not parse compare clause: {clause}")

        if var_name is None:
            var_name = match.group("var")
        elif match.group("var") != var_name:
            raise ValueError(f"Compare constraint mixes variables: {line}")

        op = match.group("op")
        value = _parse_sv_int(match.group("value"))

        if op == ">":
            lower_bound = max(lower_bound, value + 1)
        elif op == ">=":
            lower_bound = max(lower_bound, value)
        elif op == "<":
            upper_bound = min(upper_bound, value - 1)
        elif op == "<=":
            upper_bound = min(upper_bound, value)

    lower_bound = max(0, lower_bound)
    upper_bound = min(max_value, upper_bound)

    if lower_bound > upper_bound:
        raise ValueError(f"Unsatisfiable compare constraint: {line}")

    return lower_bound, upper_bound
