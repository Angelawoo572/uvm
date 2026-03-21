import re

"""Parse SystemVerilog inside constraints and extract numeric bounds."""


_INSIDE_RE = re.compile(
    r"^\s*(?P<var>\w+)\s+inside\s*\{\s*\[\s*(?P<lo>[^:\]]+)\s*:\s*(?P<hi>[^\]]+)\s*\]\s*\}\s*$"
)


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


def generate_inside(constraint_line: str, lfsr_width: int = 32) -> tuple[int, int]:
    """Extract [lower_bound, upper_bound] from `var inside {[lo:hi]}` and clamp to LFSR width."""
    line = re.sub(r"//.*", "", constraint_line).strip()
    match = _INSIDE_RE.match(line)

    if not match:
        raise ValueError(f"Could not parse inside constraint body: {line}")

    lo = _parse_sv_int(match.group("lo"))
    hi = _parse_sv_int(match.group("hi"))
    lower_bound = min(lo, hi)
    upper_bound = max(lo, hi)

    max_value = _max_lfsr_value(lfsr_width)
    lower_bound = max(0, lower_bound)
    upper_bound = min(max_value, upper_bound)
    return lower_bound, upper_bound
