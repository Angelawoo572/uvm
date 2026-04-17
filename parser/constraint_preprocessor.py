# =============================================================================
# Constraint Preprocessor for UVM Sequence Items
# =============================================================================
#
# Parses SystemVerilog (.sv/.svh) files using pyslang and extracts constraints
# on rand variables into a normalized form for RTL use.
#
# Supported:
#   - Range:       var inside {[A:B]}
#   - Relational:  var <, <=, >, >= value
#   - Bit fixes:   var[msb:lsb] == value, var[bit] == value
#
# Output per variable:
#   - original_min / original_max
#   - FIXED_MASK / FIXED_VAL
#     where: (value & FIXED_MASK) == FIXED_VAL
#
# Notes:
#   - Only simple single-variable constraints are supported
#   - No complex expressions or satisfiability checks
#
# Usage:
#   python constraint_preprocessor.py <file.svh>
#   python constraint_preprocessor.py <file.svh> --out result.txt

import pyslang
import json
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
import os
import argparse
import re


# -----------------------------
# Data model
# -----------------------------
@dataclass
class FieldInfo:
    name: str
    sv_type: str
    rand_mode: str


@dataclass
class ClassDeclInfo:
    name: str
    kind: str
    base_name: Optional[str]


@dataclass
class AggregatedConstraint:
    var_name: str
    original_min: Optional[int] = None
    original_max: Optional[int] = None
    fixed_mask: int = 0
    fixed_val: int = 0
    sources: List[str] = field(default_factory=list)


IGNORED_FIELD_NAMES = {"name", "this", "state", "seed", "on_ff"}


# -----------------------------
# Generic JSON helpers
# -----------------------------
def _extract_identifier_text(name_node: Any) -> Optional[str]:
    if not isinstance(name_node, dict):
        return None

    txt = name_node.get("text")
    if isinstance(txt, str):
        return txt

    ident = name_node.get("identifier")
    if isinstance(ident, dict):
        txt = ident.get("text")
        if isinstance(txt, str):
            return txt

    val = name_node.get("value")
    if isinstance(val, str):
        return val

    return None


def _extract_text(node: Any) -> str:
    parts: List[str] = []

    def walk(x: Any):
        if isinstance(x, dict):
            if "text" in x and isinstance(x["text"], str):
                parts.append(x["text"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(node)
    return "".join(parts).strip()


# -----------------------------
# Class classification
# -----------------------------
def classify_from_base_text(base_text: str) -> str:
    t = base_text.replace(" ", "")
    if "uvm_sequence_item" in t:
        return "seq_item"
    if "uvm_sequence" in t:
        return "sequence"
    return "other"


def extract_class_decls_from_json(filepath: str) -> Dict[str, ClassDeclInfo]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    class_map: Dict[str, ClassDeclInfo] = {}

    def walk(node: Any):
        if isinstance(node, dict):
            if node.get("kind") == "ClassDeclaration":
                name = _extract_identifier_text(node.get("name")) or "<unknown_class>"
                ext = node.get("extendsClause")
                base_name = None

                if isinstance(ext, dict):
                    base_name = _extract_text(ext.get("baseName"))

                kind = classify_from_base_text(base_name or "")
                class_map[name] = ClassDeclInfo(
                    name=name,
                    kind=kind,
                    base_name=base_name
                )

            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(cst)

    changed = True
    while changed:
        changed = False
        for ci in class_map.values():
            if ci.kind != "other" or not ci.base_name:
                continue

            if ci.base_name in class_map:
                parent_kind = class_map[ci.base_name].kind
                if parent_kind in {"seq_item", "sequence"}:
                    ci.kind = parent_kind
                    changed = True

    return class_map


# -----------------------------
# Field extraction from JSON
# -----------------------------
def _has_rand_qualifier(qualifiers: Any) -> bool:
    if not isinstance(qualifiers, list):
        return False
    for q in qualifiers:
        if isinstance(q, dict) and q.get("kind") == "RandKeyword":
            return True
    return False


def _extract_type_text(type_node: Any) -> str:
    text = _extract_text(type_node)
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else "<unknown_type>"


def extract_fields_from_json(filepath: str,
                             class_decl_map: Dict[str, ClassDeclInfo]) -> Dict[str, List[FieldInfo]]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    fields_by_class: Dict[str, List[FieldInfo]] = {}

    def add_field(class_name: str, finfo: FieldInfo):
        fields_by_class.setdefault(class_name, []).append(finfo)

    def walk_class_items(items: Any, class_name: str):
        if not isinstance(items, list):
            return

        for item in items:
            if not isinstance(item, dict):
                continue

            if item.get("kind") != "ClassPropertyDeclaration":
                continue

            qualifiers = item.get("qualifiers", [])
            rand_mode = "Rand" if _has_rand_qualifier(qualifiers) else "None_"

            decl = item.get("declaration")
            if not isinstance(decl, dict):
                continue
            if decl.get("kind") != "DataDeclaration":
                continue

            type_node = decl.get("type")
            sv_type = _extract_type_text(type_node)

            declarators = decl.get("declarators", [])
            for d in declarators:
                if not isinstance(d, dict):
                    continue
                if d.get("kind") != "Declarator":
                    continue

                name = _extract_identifier_text(d.get("name"))
                if not name:
                    continue
                if name in IGNORED_FIELD_NAMES:
                    continue

                add_field(class_name, FieldInfo(
                    name=name,
                    sv_type=sv_type,
                    rand_mode=rand_mode
                ))

    def walk(node: Any):
        if isinstance(node, dict):
            if node.get("kind") == "ClassDeclaration":
                class_name = _extract_identifier_text(node.get("name")) or "<unknown_class>"
                decl_info = class_decl_map.get(class_name)

                if decl_info and decl_info.kind == "seq_item":
                    items = node.get("items")
                    walk_class_items(items, class_name)

            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(cst)
    return fields_by_class


# -----------------------------
# Integer / expression helpers
# -----------------------------
def parse_integer_expr(node: Any) -> Optional[int]:
    if not isinstance(node, dict):
        return None

    kind = node.get("kind")

    if kind == "IntegerLiteralExpression":
        lit = node.get("literal", {})
        txt = lit.get("text")
        if isinstance(txt, str) and txt.isdigit():
            return int(txt)

    if kind == "IntegerLiteral":
        txt = node.get("text")
        if isinstance(txt, str) and txt.isdigit():
            return int(txt)

    if kind == "IntegerVectorExpression":
        base = node.get("base", {}).get("text", "")
        value = node.get("value", {}).get("text", "")

        if not isinstance(base, str) or not isinstance(value, str):
            return None

        digits = value.replace("_", "")
        if any(c in digits.lower() for c in "xz"):
            return None

        base_map = {"'b": 2, "'o": 8, "'d": 10, "'h": 16}
        if base not in base_map:
            return None

        return int(digits, base_map[base])

    return None


def extract_identifier_name(node: Any) -> Optional[str]:
    if not isinstance(node, dict):
        return None

    kind = node.get("kind")

    if kind == "IdentifierName":
        ident = node.get("identifier", {})
        return ident.get("text")

    if kind == "IdentifierSelectName":
        ident = node.get("identifier", {})
        return ident.get("text")

    if kind == "Identifier":
        return node.get("text")

    return None


def get_or_create(summary: Dict[str, AggregatedConstraint], var_name: str) -> AggregatedConstraint:
    if var_name not in summary:
        summary[var_name] = AggregatedConstraint(var_name=var_name)
    return summary[var_name]


def update_min(ac: AggregatedConstraint, value: int):
    if ac.original_min is None or value > ac.original_min:
        ac.original_min = value


def update_max(ac: AggregatedConstraint, value: int):
    if ac.original_max is None or value < ac.original_max:
        ac.original_max = value


def add_source(ac: AggregatedConstraint, constraint_name: str):
    if constraint_name not in ac.sources:
        ac.sources.append(constraint_name)


def apply_fixed_slice(ac: AggregatedConstraint, msb: int, lsb: int, value: int):
    width = msb - lsb + 1
    raw_mask = (1 << width) - 1
    mask = raw_mask << lsb
    shifted_val = (value & raw_mask) << lsb

    overlap = ac.fixed_mask & mask
    if overlap:
        existing_bits = ac.fixed_val & overlap
        incoming_bits = shifted_val & overlap
        if existing_bits != incoming_bits:
            raise ValueError(
                f"Conflicting fixed assignments on {ac.var_name}: "
                f"existing=0x{existing_bits:08x}, incoming=0x{incoming_bits:08x}"
            )

    ac.fixed_mask |= mask
    ac.fixed_val = (ac.fixed_val & ~mask) | shifted_val


def format_hex32(value: Optional[int]) -> str:
    if value is None:
        return "None"
    return f"32'h{value & 0xFFFFFFFF:08X}"


# -----------------------------
# Select extraction
# -----------------------------
def extract_select_info(left: Any) -> Optional[Tuple[str, int, int]]:
    if not isinstance(left, dict):
        return None

    if left.get("kind") != "IdentifierSelectName":
        return None

    var_name = extract_identifier_name(left)
    if var_name is None:
        return None

    selectors = left.get("selectors", [])
    if len(selectors) != 1:
        return None

    sel = selectors[0]
    if not isinstance(sel, dict) or sel.get("kind") != "ElementSelect":
        return None

    selector = sel.get("selector")
    if not isinstance(selector, dict):
        return None

    selector_kind = selector.get("kind")

    # Case 1: addr[9:8]
    if selector_kind == "SimpleRangeSelect":
        msb = parse_integer_expr(selector.get("left"))
        lsb = parse_integer_expr(selector.get("right"))
        if msb is None or lsb is None:
            return None
        return var_name, max(msb, lsb), min(msb, lsb)

    # Case 2: addr[7]
    if selector_kind == "BitSelect":
        bit = parse_integer_expr(selector.get("expr"))
        if bit is None:
            return None
        return var_name, bit, bit

    # Fallback in case pyslang emits a direct literal-like selector
    bit = parse_integer_expr(selector)
    if bit is not None:
        return var_name, bit, bit

    return None


# -----------------------------
# Constraint expression handlers
# -----------------------------
def handle_inside_expression(expr: Any,
                             summary: Dict[str, AggregatedConstraint],
                             constraint_name: str,
                             rand_fields: Set[str]) -> None:
    if not isinstance(expr, dict):
        return
    if expr.get("kind") != "InsideExpression":
        return

    var_name = extract_identifier_name(expr.get("expr"))
    if var_name not in rand_fields:
        return

    ranges = expr.get("ranges", {})
    value_ranges = ranges.get("valueRanges", [])
    if len(value_ranges) != 1:
        return

    vr = value_ranges[0]
    if not isinstance(vr, dict):
        return
    if vr.get("kind") != "ValueRangeExpression":
        return

    lo = parse_integer_expr(vr.get("left"))
    hi = parse_integer_expr(vr.get("right"))

    if lo is None or hi is None:
        return

    ac = get_or_create(summary, var_name)
    update_min(ac, lo)
    update_max(ac, hi)
    add_source(ac, constraint_name)


def handle_equality_expression(expr: Any,
                               summary: Dict[str, AggregatedConstraint],
                               constraint_name: str,
                               rand_fields: Set[str]) -> None:
    if not isinstance(expr, dict):
        return
    if expr.get("kind") != "EqualityExpression":
        return

    left = expr.get("left")
    right = expr.get("right")

    sel_info = extract_select_info(left)
    if sel_info is None:
        return

    var_name, msb, lsb = sel_info
    if var_name not in rand_fields:
        return

    rhs = parse_integer_expr(right)
    if rhs is None:
        return

    ac = get_or_create(summary, var_name)
    apply_fixed_slice(ac, msb, lsb, rhs)
    add_source(ac, constraint_name)


def _get_binary_operator_kind(expr: Any) -> Optional[str]:
    if not isinstance(expr, dict):
        return None

    kind = expr.get("kind")
    if isinstance(kind, str) and kind in {
        "LessThanExpression",
        "LessThanEqualExpression",
        "GreaterThanExpression",
        "GreaterThanEqualExpression",
    }:
        return kind

    tok = expr.get("operatorToken")
    if isinstance(tok, dict):
        tok_kind = tok.get("kind")
        tok_text = tok.get("text")
        if tok_kind in {
            "LessThan",
            "LessThanEquals",
            "GreaterThan",
            "GreaterThanEquals",
        }:
            return tok_kind
        if tok_text == "<":
            return "LessThan"
        if tok_text == "<=":
            return "LessThanEquals"
        if tok_text == ">":
            return "GreaterThan"
        if tok_text == ">=":
            return "GreaterThanEquals"

    return None


def handle_relational_expression(expr: Any,
                                 summary: Dict[str, AggregatedConstraint],
                                 constraint_name: str,
                                 rand_fields: Set[str]) -> None:
    if not isinstance(expr, dict):
        return

    op_kind = _get_binary_operator_kind(expr)
    if op_kind is None:
        return

    left = expr.get("left")
    right = expr.get("right")

    var_name = extract_identifier_name(left)
    if var_name not in rand_fields:
        return

    rhs = parse_integer_expr(right)
    if rhs is None:
        return

    ac = get_or_create(summary, var_name)

    if op_kind in {"LessThanExpression", "LessThan"}:
        update_max(ac, rhs - 1)
    elif op_kind in {"LessThanEqualExpression", "LessThanEquals"}:
        update_max(ac, rhs)
    elif op_kind in {"GreaterThanExpression", "GreaterThan"}:
        update_min(ac, rhs + 1)
    elif op_kind in {"GreaterThanEqualExpression", "GreaterThanEquals"}:
        update_min(ac, rhs)

    add_source(ac, constraint_name)


def analyze_expression_constraint(item: Any,
                                  summary: Dict[str, AggregatedConstraint],
                                  constraint_name: str,
                                  rand_fields: Set[str]) -> None:
    if not isinstance(item, dict):
        return
    if item.get("kind") != "ExpressionConstraint":
        return

    expr = item.get("expr", {})
    if not isinstance(expr, dict):
        return

    expr_kind = expr.get("kind")

    if expr_kind == "InsideExpression":
        handle_inside_expression(expr, summary, constraint_name, rand_fields)
        return

    if expr_kind == "EqualityExpression":
        handle_equality_expression(expr, summary, constraint_name, rand_fields)
        return

    handle_relational_expression(expr, summary, constraint_name, rand_fields)


# -----------------------------
# Main extraction pass
# -----------------------------
def extract_constraint_inputs_from_json(filepath: str) -> Dict[str, Dict[str, AggregatedConstraint]]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    class_decl_map = extract_class_decls_from_json(filepath)
    fields_by_class = extract_fields_from_json(filepath, class_decl_map)

    rand_fields_by_class: Dict[str, Set[str]] = {}
    for class_name, fields in fields_by_class.items():
        rand_fields_by_class[class_name] = {
            f.name for f in fields if f.rand_mode == "Rand"
        }

    results: Dict[str, Dict[str, AggregatedConstraint]] = {}

    def walk(node: Any):
        if isinstance(node, dict):
            if node.get("kind") == "ClassDeclaration":
                class_name = _extract_identifier_text(node.get("name")) or "<unknown_class>"
                decl = class_decl_map.get(class_name)

                if decl and decl.kind == "seq_item":
                    results.setdefault(class_name, {})
                    rand_fields = rand_fields_by_class.get(class_name, set())

                    for item in node.get("items", []):
                        if not isinstance(item, dict):
                            continue
                        if item.get("kind") != "ConstraintDeclaration":
                            continue

                        constraint_name = _extract_identifier_text(item.get("name")) or "<unknown_constraint>"
                        block = item.get("block", {})
                        if not isinstance(block, dict):
                            continue
                        if block.get("kind") != "ConstraintBlock":
                            continue

                        for citem in block.get("items", []):
                            analyze_expression_constraint(
                                citem,
                                results[class_name],
                                constraint_name,
                                rand_fields
                            )

            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(cst)
    return results


# -----------------------------
# Output formatting
# -----------------------------
def format_results(results: Dict[str, Dict[str, AggregatedConstraint]]) -> str:
    lines: List[str] = []

    for class_name in sorted(results.keys()):
        lines.append(f"Class: {class_name}")

        var_map = results[class_name]
        if not var_map:
            lines.append("  <no supported aggregated constraints found>")
            lines.append("")
            continue

        for var_name in sorted(var_map.keys()):
            ac = var_map[var_name]
            lines.append(f"  Variable: {var_name}")
            lines.append(f"    original_min: {format_hex32(ac.original_min)}")
            lines.append(f"    original_max: {format_hex32(ac.original_max)}")
            lines.append(f"    FIXED_MASK : {format_hex32(ac.fixed_mask)}")
            lines.append(f"    FIXED_VAL  : {format_hex32(ac.fixed_val)}")

            if ac.sources:
                lines.append(f"    sources    : {', '.join(ac.sources)}")

        lines.append("")

    return "\n".join(lines)


def default_out_path(input_file: str) -> str:
    base = os.path.splitext(os.path.basename(input_file))[0]
    return f"{base}_constraint_summary.txt"


def write_output(results: Dict[str, Dict[str, AggregatedConstraint]], out_file: str) -> None:
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(format_results(results))


# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="SystemVerilog file (.sv/.svh)")
    parser.add_argument("--out", default=None, help="Optional output text file")
    args = parser.parse_args()

    results = extract_constraint_inputs_from_json(args.file)

    if args.out:
        write_output(results, args.out)
        print(f"Wrote output to {args.out}")
    else:
        print(format_results(results))


if __name__ == "__main__":
    main()