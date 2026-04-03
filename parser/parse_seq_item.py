import pyslang
import json
from typing import Union, List, Dict, Any, Optional
from dataclasses import dataclass, field
import os
import argparse
import re

# High-Level Overview:
# This script analyzes a SystemVerilog (.sv / .svh) file containing UVM sequence items.
# It uses the CST JSON to:
#   1. identify which classes are sequence items vs sequences
#   2. extract locally declared fields
#   3. extract class-local constraints
#
# This is more robust than relying entirely on semantic resolution when UVM base
# classes or included constants are not fully in scope.
#
# The final result is a structured summary of each sequence-item class, including:
#   - declared fields
#   - reconstructed constraint blocks
#
# TO RUN:
#   python parse_seq_item.py <file.svh>


# -----------------------------
# Data model
# -----------------------------
@dataclass
class FieldInfo:
    name: str
    sv_type: str
    rand_mode: str


@dataclass
class ConstraintInfo:
    name: str
    text: str


@dataclass
class ClassInfo:
    name: str
    kind: str = "other"
    base_name: Optional[str] = None
    fields: List[FieldInfo] = field(default_factory=list)
    constraints: List[ConstraintInfo] = field(default_factory=list)


@dataclass
class ClassDeclInfo:
    name: str
    kind: str
    base_name: Optional[str]


IGNORED_FIELD_NAMES = {"name", "this", "state", "seed", "on_ff"}


# -----------------------------
# Generic JSON helpers
# -----------------------------
def _extract_identifier_text(name_node: Any) -> Optional[str]:
    if not isinstance(name_node, dict):
        return None

    # Case 1: direct identifier node
    txt = name_node.get("text")
    if isinstance(txt, str):
        return txt

    # Case 2: wrapper with nested identifier
    ident = name_node.get("identifier")
    if isinstance(ident, dict):
        txt = ident.get("text")
        if isinstance(txt, str):
            return txt

    # Case 3: wrapper with plain value
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


def _collect_tokens(node: Any, skip_keyword_trivia: bool = False) -> str:
    """
    Reconstruct token text in JSON order.
    If skip_keyword_trivia=True, skip trivia on ConstraintKeyword token.
    """
    out: List[str] = []

    def walk(x: Any):
        if isinstance(x, dict):
            if "text" in x and isinstance(x["text"], str):
                kind = x.get("kind")

                if skip_keyword_trivia and kind == "ConstraintKeyword":
                    out.append(x["text"])
                else:
                    trivia = x.get("trivia")
                    if isinstance(trivia, list):
                        for t in trivia:
                            if isinstance(t, dict) and isinstance(t.get("text"), str):
                                out.append(t["text"])
                    out.append(x["text"])

            for v in x.values():
                walk(v)

        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(node)
    return "".join(out)


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

    # Propagate classification through user-defined inheritance
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
# Constraint extraction from JSON
# -----------------------------
def _normalize_constraint_text(s: str) -> str:
    s = s.replace("\r\n", "\n")
    s = re.sub(r"(?m)^\s*//.*\n?", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([\)\]\}])", r"\1", s)
    s = re.sub(r"\s+([;,])", r"\1", s)
    s = re.sub(r"\s+\{", " {", s)
    s = re.sub(r"\s*==\s*", " == ", s)
    s = re.sub(r"(\d)\s+'([bodhBODH])", r"\1'\2", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_constraints_from_json(filepath: str) -> Dict[str, List[ConstraintInfo]]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    constraints_by_class: Dict[str, List[ConstraintInfo]] = {}

    def add_constraint(class_name: str, cinfo: ConstraintInfo):
        constraints_by_class.setdefault(class_name, []).append(cinfo)

    def walk_class_items(node: Any, class_name: str):
        if isinstance(node, dict):
            if node.get("kind") == "ConstraintDeclaration":
                cname = _extract_identifier_text(node.get("name")) or "<unknown_constraint>"

                kw = node.get("keyword")
                nm = node.get("name")
                blk = node.get("block")

                parts: List[str] = []
                if isinstance(kw, dict) and isinstance(kw.get("text"), str):
                    parts.append(kw["text"])
                if nm is not None:
                    parts.append(_collect_tokens(nm))
                if blk is not None:
                    parts.append(_collect_tokens(blk))

                text = _normalize_constraint_text("".join(parts))
                add_constraint(class_name, ConstraintInfo(name=cname, text=text))

            for v in node.values():
                walk_class_items(v, class_name)

        elif isinstance(node, list):
            for i in node:
                walk_class_items(i, class_name)

    def walk(node: Any):
        if isinstance(node, dict):
            if node.get("kind") == "ClassDeclaration":
                class_name = _extract_identifier_text(node.get("name")) or "<unknown_class>"
                items = node.get("items")
                if items is not None:
                    walk_class_items(items, class_name)

            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(cst)
    return constraints_by_class


# -----------------------------
# Compilation / collection
# -----------------------------
def compile_file(filepath: str) -> pyslang.Compilation:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    comp = pyslang.Compilation()
    comp.addSyntaxTree(tree)
    return comp


def collect_classes(filepath: str, show_diagnostics: bool = True) -> List[ClassInfo]:
    comp = compile_file(filepath)

    if show_diagnostics:
        diags = comp.getAllDiagnostics()
        if diags:
            print("Diagnostics from slang:")
            for d in diags:
                print(" ", d)
            print(" (Ignoring diagnostics and continuing)\n")

    class_decl_map = extract_class_decls_from_json(filepath)
    fields_by_class = extract_fields_from_json(filepath, class_decl_map)

    classes: List[ClassInfo] = []
    for class_name in sorted(class_decl_map.keys()):
        decl = class_decl_map[class_name]
        if decl.kind != "seq_item":
            continue

        ci = ClassInfo(
            name=class_name,
            kind=decl.kind,
            base_name=decl.base_name,
            fields=fields_by_class.get(class_name, []),
            constraints=[]
        )
        classes.append(ci)

    return classes


# -----------------------------
# Formatting helpers
# -----------------------------
def dedupe_fields(fields: List[FieldInfo]) -> List[FieldInfo]:
    seen = set()
    out: List[FieldInfo] = []
    for f in fields:
        key = (f.name, f.sv_type, f.rand_mode)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def dedupe_constraints(constraints: List[ConstraintInfo]) -> List[ConstraintInfo]:
    seen = set()
    out: List[ConstraintInfo] = []
    for c in constraints:
        key = (c.name, c.text)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def format_class_info(ci: ClassInfo) -> str:
    fields = dedupe_fields(ci.fields)
    constraints = dedupe_constraints(ci.constraints)

    lines: List[str] = []
    lines.append(f"Class: {ci.name}")
    lines.append("")

    lines.append("Fields:")
    if fields:
        for f in fields:
            lines.append(f"  {f.name:12s} : {f.sv_type:24s} rand_mode={f.rand_mode}")
    else:
        lines.append("  <no fields found>")

    lines.append("")
    lines.append("Constraints:")
    if constraints:
        for c in constraints:
            lines.append(f"  {c.name}")
            body = c.text.replace("\n", "\n    ")
            lines.append(f"    {body}")
    else:
        lines.append("  <no constraints found>")

    lines.append("")
    lines.append("")
    return "\n".join(lines)


def write_summary(classes: List[ClassInfo], out_file: str) -> None:
    with open(out_file, "w", encoding="utf-8") as f:
        for ci in classes:
            f.write(format_class_info(ci))


# -----------------------------
# CLI
# -----------------------------
def default_out_path(input_file: str) -> str:
    base = os.path.splitext(os.path.basename(input_file))[0]
    return f"{base}_item_summary.txt"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="SystemVerilog file (.sv/.svh)")
    parser.add_argument("--out", default=None, help="Output text file path")
    parser.add_argument("--no-diags", action="store_true", help="Do not print diagnostics")
    args = parser.parse_args()

    classes = collect_classes(args.file, show_diagnostics=not args.no_diags)

    if not classes:
        print("No sequence-item classes found in file.")
        return

    constraints_by_class = extract_constraints_from_json(args.file)

    for ci in classes:
        ci.constraints.extend(constraints_by_class.get(ci.name, []))

    out_file = args.out if args.out else default_out_path(args.file)
    write_summary(classes, out_file)
    print(f"Wrote summary to {out_file}")


if __name__ == "__main__":
    main()