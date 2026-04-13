"""
SystemVerilog Constraint Region Extractor
==========================================
Parses SV constraint blocks and resolves the final valid regions
(min/max pairs) for each constrained variable, accounting for:
  - Relational operators  (>=, <=, >, <, ==)
  - Logical AND/OR         (&&, ||)
  - inside {[lo:hi], ...}  ranges
  - Negated inside         !(var inside {[lo:hi]})
  - Multiple constraints   that all apply to the same variable 

Usage (library):
    from sv_constraint_parser import parse_sv_constraints
    results = parse_sv_constraints(sv_source_text)
    # results = { 'addr': [Interval(0,15), Interval(32,63)], ... }
"""

import re
import sys

INT_MAX = 2**63 - 1
INT_MIN = -(2**63)


# ---------------------------------------------------------------------------
# Interval primitives
# ---------------------------------------------------------------------------

class Interval:
    __slots__ = ('lo', 'hi')

    def __init__(self, lo: int, hi: int):
        self.lo = lo
        self.hi = hi

    def is_valid(self) -> bool:
        return self.lo <= self.hi

    def intersect(self, other):
        lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
        return Interval(lo, hi) if lo <= hi else None

    def subtract(self, other):
        """Return self minus other (a hole-punch)."""
        if other.lo > self.hi or other.hi < self.lo:
            return [Interval(self.lo, self.hi)]
        result = []
        if self.lo < other.lo:
            result.append(Interval(self.lo, other.lo - 1))
        if self.hi > other.hi:
            result.append(Interval(other.hi + 1, self.hi))
        return result

    def __repr__(self):
        lo = self.lo if self.lo != INT_MIN else "-inf"
        hi = self.hi if self.hi != INT_MAX else "+inf"
        return f"[{lo}, {hi}]"


def union_ivs(ivs):
    valid = [iv for iv in ivs if iv.is_valid()]
    if not valid:
        return []
    s = sorted(valid, key=lambda x: x.lo)
    m = [Interval(s[0].lo, s[0].hi)]
    for iv in s[1:]:
        if iv.lo <= m[-1].hi + 1:
            m[-1].hi = max(m[-1].hi, iv.hi)
        else:
            m.append(Interval(iv.lo, iv.hi))
    return m


def intersect_sets(sets):
    """AND of multiple interval sets."""
    if not sets:
        return []
    result = sets[0]
    for other in sets[1:]:
        new = []
        for a in result:
            for b in other:
                iv = a.intersect(b)
                if iv:
                    new.append(iv)
        result = union_ivs(new)
    return result


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def strip_comments(text: str) -> str:
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    return text


def split_on_sep(expr: str, sep: str):
    """Split expr on sep, but only at paren/brace depth 0."""
    parts, cur, depth, i = [], [], 0, 0
    while i < len(expr):
        c = expr[i]
        if c in '({':
            depth += 1; cur.append(c)
        elif c in ')}':
            depth -= 1; cur.append(c)
        elif expr[i:i+len(sep)] == sep and depth == 0:
            parts.append(''.join(cur)); cur = []; i += len(sep); continue
        else:
            cur.append(c)
        i += 1
    parts.append(''.join(cur))
    return parts


def is_balanced(expr: str) -> bool:
    depth = 0
    for c in expr:
        if c in '({':
            depth += 1
        elif c in ')}':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def strip_outer_parens(expr: str) -> str:
    """Remove exactly one layer of balanced outer parens, if present."""
    expr = expr.strip()
    if expr.startswith('(') and expr.endswith(')') and is_balanced(expr[1:-1]):
        return expr[1:-1].strip()
    return expr


# ---------------------------------------------------------------------------
# inside-set parser
# ---------------------------------------------------------------------------

def parse_inside_set(body: str):
    ivs = []
    for m in re.finditer(r'\[\s*(-?\d+)\s*:\s*(-?\d+)\s*\]', body):
        ivs.append(Interval(int(m.group(1)), int(m.group(2))))
    cleaned = re.sub(r'\[[^\]]*\]', '', body)
    for m in re.finditer(r'\b(-?\d+)\b', cleaned):
        v = int(m.group(1))
        ivs.append(Interval(v, v))
    return union_ivs(ivs)


# ---------------------------------------------------------------------------
# Expression evaluator  (iterative, no mutual recursion)
# ---------------------------------------------------------------------------

# We parse the expression as:
#   expr   = and_expr  ( '||' and_expr )*
#   and_expr = atom   ( '&&' atom )*
#   atom   = '(' expr ')' | simple
#
# We implement this by splitting top-level OR first, then top-level AND
# inside each OR-branch, then recursing only when we encounter parens.

def eval_expr(var: str, expr: str):
    """
    Evaluate expression `expr` for variable `var`.
    Returns list[Interval] satisfying the expression.
    Top-level entry; handles OR (||) at the lowest precedence.
    """
    expr = expr.strip()

    # Top-level OR
    or_parts = split_on_sep(expr, '||')
    if len(or_parts) > 1:
        ivs = []
        for p in or_parts:
            ivs.extend(eval_and(var, p.strip()))
        return union_ivs(ivs)

    # No top-level OR — handle as AND
    return eval_and(var, expr)


def eval_and(var: str, expr: str):
    """Handle top-level AND (&&)."""
    expr = expr.strip()
    and_parts = split_on_sep(expr, '&&')
    if len(and_parts) > 1:
        sets = [eval_paren_or_simple(var, p.strip()) for p in and_parts]
        return intersect_sets(sets)
    return eval_paren_or_simple(var, expr)


def eval_paren_or_simple(var: str, expr: str):
    """
    If expr is wrapped in parens that contain compound operators,
    recurse via eval_expr.  Otherwise call eval_simple.
    """
    expr = expr.strip()
    # If it starts with '(' and ends with ')' and the interior is balanced,
    # strip one layer then re-dispatch through eval_expr.
    inner = strip_outer_parens(expr)
    if inner != expr:
        # Something was stripped; recurse
        return eval_expr(var, inner)
    # No outer parens — evaluate as a leaf
    return eval_simple(var, expr)


REL_OPS = [
    (r'>=', lambda v: Interval(v,     INT_MAX)),
    (r'<=', lambda v: Interval(INT_MIN, v    )),
    (r'>',  lambda v: Interval(v + 1,  INT_MAX)),
    (r'<',  lambda v: Interval(INT_MIN, v - 1)),
    (r'==', lambda v: Interval(v,       v    )),
]
REV_OP = {'>=': '<=', '<=': '>=', '>': '<', '<': '>'}


def eval_simple(var: str, expr: str):
    """Evaluate a leaf (non-compound) expression."""
    expr = expr.strip()

    # !(var inside { ... })
    m = re.match(
        r'!\s*\(\s*' + re.escape(var) + r'\s+inside\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}\s*\)',
        expr
    )
    if m:
        excluded = parse_inside_set(m.group(1))
        result = [Interval(INT_MIN, INT_MAX)]
        for e in excluded:
            new = []
            for iv in result:
                new.extend(iv.subtract(e))
            result = new
        return union_ivs(result)

    # var inside { ... }
    m = re.match(
        re.escape(var) + r'\s+inside\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
        expr
    )
    if m:
        return parse_inside_set(m.group(1))

    # Relational
    for op_str, builder in REL_OPS:
        # var OP number
        m = re.match(re.escape(var) + r'\s*' + re.escape(op_str) + r'\s*(-?\d+)', expr)
        if m:
            return [builder(int(m.group(1)))]
        # number OP var → reverse operator
        rev = REV_OP.get(op_str)
        if rev:
            rev_builder = dict(REL_OPS).get(rev)
            m = re.match(r'(-?\d+)\s*' + re.escape(op_str) + r'\s*' + re.escape(var), expr)
            if m and rev_builder:
                return [rev_builder(int(m.group(1)))]

    # Could not parse — return unconstrained
    return [Interval(INT_MIN, INT_MAX)]


# ---------------------------------------------------------------------------
# Constraint block extractor (nested-brace-aware)
# ---------------------------------------------------------------------------

SV_KEYWORDS = {
    'inside', 'if', 'else', 'foreach', 'soft', 'unique', 'dist',
    'with', 'and', 'or', 'not', 'constraint', 'rand', 'randc',
    'bit', 'int', 'logic', 'byte', 'integer', 'shortint', 'longint',
    'string', 'void'
}


def extract_constraint_bodies(sv_text: str):
    """
    Yield (constraint_name, body_string) pairs.
    Body is everything between the outermost { } of each constraint block,
    correctly handling nested braces (inside sets, etc.).
    """
    sv_text = strip_comments(sv_text)
    for hdr in re.finditer(r'\bconstraint\s+(\w+)\s*\{', sv_text):
        name = hdr.group(1)
        start = hdr.end()
        depth, i = 1, start
        while i < len(sv_text) and depth > 0:
            if sv_text[i] == '{':
                depth += 1
            elif sv_text[i] == '}':
                depth -= 1
            i += 1
        body = sv_text[start:i-1].strip()
        yield name, body


def variables_in_body(body: str):
    """
    Return set of identifiers that appear with a constraint operator.
    """
    found = set()
    # var OP ...
    for m in re.finditer(
        r'\b([a-zA-Z_]\w*)\b\s*(?:>=|<=|>(?!=)|<(?!=)|==|!=|inside\b)', body
    ):
        name = m.group(1)
        if name not in SV_KEYWORDS:
            found.add(name)
    # number OP var
    for m in re.finditer(
        r'\b\d+\s*(?:>=|<=|>(?!=)|<(?!=)|==)\s*([a-zA-Z_]\w*)\b', body
    ):
        name = m.group(1)
        if name not in SV_KEYWORDS:
            found.add(name)
    # !(var inside {})
    for m in re.finditer(r'!\s*\(\s*([a-zA-Z_]\w*)\s+inside\b', body):
        name = m.group(1)
        if name not in SV_KEYWORDS:
            found.add(name)
    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_sv_constraints(sv_text: str) -> dict:
    """
    Parse SystemVerilog constraint blocks.

    Returns
    -------
    dict mapping variable name → list[Interval]
        Each Interval has .lo and .hi (INT_MIN / INT_MAX for unbounded).
        Multiple constraints on the same variable are intersected (ANDed).
    """
    # Collect per-variable list of constraint body strings
    var_exprs: dict[str, list[str]] = {}
    for _name, body in extract_constraint_bodies(sv_text):
        body_clean = body.rstrip(';').strip()
        for var in variables_in_body(body_clean):
            var_exprs.setdefault(var, []).append(body_clean)

    results = {}
    for var, exprs in var_exprs.items():
        # Each constraint block contributes one interval-set; AND them together.
        per = [eval_expr(var, e) for e in exprs]
        per = [s for s in per if s]   # drop empty
        regions = intersect_sets(per) if per else []
        if regions:
            results[var] = regions
    return results


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def print_regions(results: dict) -> None:
    ld = lambda v: str(v) if v != INT_MIN else "-inf"
    hd = lambda v: str(v) if v != INT_MAX else "+inf"
    for var, regions in sorted(results.items()):
        print(f"\nVariable : {var}")
        print(f"  Regions : {len(regions)}")
        for i, iv in enumerate(regions, 1):
            print(f"  Region {i}: min={ld(iv.lo):<14}  max={hd(iv.hi)}")


# ---------------------------------------------------------------------------
# Demo / self-test
# ---------------------------------------------------------------------------

SAMPLE_SV = """
constraint disjoint_ranges {
    (val >= 0 && val <= 10) || (val >= 90 && val <= 100);
}

constraint range_limit {
    addr inside {[0:63]};
}

constraint exclude_reserved {
    !(addr inside {[16:31]});
}

constraint iter_count_c {
    iteration_count inside {[1:10]};
}

constraint iter_count_short_c {
    iteration_count < 5;
}
"""

EXPECTED = {
    'val':             [(0, 10), (90, 100)],
    'addr':            [(0, 15), (32, 63)],
    'iteration_count': [(1, 4)],
}

if __name__ == "__main__":
    results = parse_sv_constraints(SAMPLE_SV)
    print_regions(results)

    print()
    print("=" * 52)
    print("Machine-readable  { var: [(lo, hi), ...] }")
    print("=" * 52)
    for var, regions in sorted(results.items()):
        pairs = [
            (iv.lo if iv.lo != INT_MIN else None,
             iv.hi if iv.hi != INT_MAX else None)
            for iv in regions
        ]
        print(f"  {var}: {pairs}")

    # Self-test
    print()
    print("Self-test ...")
    ok = True
    for var, expected_pairs in EXPECTED.items():
        actual = [(iv.lo, iv.hi) for iv in results.get(var, [])]
        if actual == expected_pairs:
            print(f"  PASS  {var}: {actual}")
        else:
            print(f"  FAIL  {var}: expected {expected_pairs}, got {actual}")
            ok = False
    sys.exit(0 if ok else 1)