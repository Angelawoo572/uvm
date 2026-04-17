import pyslang
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
import os
import argparse
import re

# High-Level Overview:
# This script analyzes a SystemVerilog (.sv / .svh) file containing UVM classes.
# It focuses ONLY on sequence-item classes (classes derived from uvm_sequence_item),
# even if the file also contains sequence classes.
#
# It uses the CST JSON to:
#   1. identify which classes are sequence items vs sequences / other classes
#   2. extract class parameters / base class info
#   3. extract locally declared fields in each sequence-item class
#   4. extract local constraints declared in each sequence-item class
#   5. optionally emit either text summary output or JSON output
#
# Notes:
# - This parser is focused on sequence-item information only.
# - It intentionally ignores sequence classes such as classes extending uvm_sequence.
# - For now, fields / constraints are LOCAL to the given class. Inherited fields are not expanded.
#
# TO RUN:
#   python parse_seq_item_with_json.py <file.svh>
#   python parse_seq_item_with_json.py <file.svh> --format json
#   python parse_seq_item_with_json.py <file.svh> --format json --pretty


# -----------------------------
# Data model
# -----------------------------
@dataclass
class FieldInfo:
    name: str
    sv_type: str
    rand_mode: str
    default: Optional[str] = None
    is_local: bool = True


@dataclass
class ConstraintInfo:
    name: str
    text: str
    is_local: bool = True


@dataclass
class SeqItemInfo:
    name: str
    kind: str = "other"
    base_name: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    fields: List[FieldInfo] = field(default_factory=list)
    constraints: List[ConstraintInfo] = field(default_factory=list)


@dataclass
class ClassDeclInfo:
    name: str
    kind: str
    base_name: Optional[str]
    parameters: List[str] = field(default_factory=list)


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

    name = name_node.get("name")
    if isinstance(name, dict):
        return _extract_identifier_text(name)

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



def _collect_tokens(node: Any) -> str:
    out: List[str] = []

    def walk(x: Any):
        if isinstance(x, dict):
            if "text" in x and isinstance(x["text"], str):
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



def _normalize_inline_text(s: str) -> str:
    s = s.replace("\r\n", "\n")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([\)\]\}\;,])", r"\1", s)
    s = re.sub(r"([\(\[\{])\s+", r"\1", s)
    s = re.sub(r"\s*::\s*", "::", s)
    s = re.sub(r"\s*#\s*", " # ", s)
    s = re.sub(r"\s*=\s*", " = ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s



def _normalize_constraint_text(s: str) -> str:
    s = s.replace("\r\n", "\n")
    s = re.sub(r"(?m)^\s*//.*\n?", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([\)\]\}])", r"\1", s)
    s = re.sub(r"\s+([;,])", r"\1", s)
    s = re.sub(r"\s+\{", " {", s)

    s = re.sub(r"\s*=\s*=\s*", " == ", s)
    s = re.sub(r"\s*!\s*=\s*", " != ", s)
    s = re.sub(r"\s*<\s*=\s*", " <= ", s)
    s = re.sub(r"\s*>\s*=\s*", " >= ", s)

    s = re.sub(r"(\d)\s+'([bodhBODH])", r"\1'\2", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s



def _extract_type_text(type_node: Any) -> str:
    text = _extract_text(type_node)
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else "<unknown_type>"



def _extract_initializer_text(declarator_node: Any) -> Optional[str]:
    if not isinstance(declarator_node, dict):
        return None

    init = declarator_node.get("initializer")
    if init is None:
        return None

    txt = _extract_text(init)
    if not txt:
        return None

    txt = _normalize_inline_text(txt)
    if txt.startswith("="):
        txt = txt[1:].strip()
    return txt or None



def _extract_parameter_list_text(param_port_list: Any) -> List[str]:
    params: List[str] = []
    if not isinstance(param_port_list, dict):
        return params

    decls = param_port_list.get("declarations", [])
    if not isinstance(decls, list):
        return params

    for decl in decls:
        if not isinstance(decl, dict):
            continue

        # Typical shape: ParameterDeclaration with type + declarators
        type_text = _extract_type_text(decl.get("type"))
        declarators = decl.get("declarators", [])
        if isinstance(declarators, list) and declarators:
            for d in declarators:
                if not isinstance(d, dict):
                    continue
                name = _extract_identifier_text(d.get("name"))
                if not name:
                    continue
                init = _extract_initializer_text(d)
                if init is not None:
                    params.append(f"{type_text} {name}={init}")
                else:
                    params.append(f"{type_text} {name}")
            continue

        # Fallback for odd CST shapes
        txt = _normalize_inline_text(_collect_tokens(decl))
        if txt:
            params.append(txt)

    return params


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
                    base_name = _normalize_inline_text(_extract_text(ext.get("baseName")))

                params = _extract_parameter_list_text(node.get("parameters"))
                kind = classify_from_base_text(base_name or "")
                class_map[name] = ClassDeclInfo(
                    name=name,
                    kind=kind,
                    base_name=base_name,
                    parameters=params,
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

                default = _extract_initializer_text(d)
                add_field(class_name, FieldInfo(
                    name=name,
                    sv_type=sv_type,
                    rand_mode=rand_mode,
                    default=default,
                    is_local=True,
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

def extract_constraints_from_json(filepath: str,
                                  class_decl_map: Dict[str, ClassDeclInfo]) -> Dict[str, List[ConstraintInfo]]:
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
                add_constraint(class_name, ConstraintInfo(name=cname, text=text, is_local=True))

            for v in node.values():
                walk_class_items(v, class_name)

        elif isinstance(node, list):
            for i in node:
                walk_class_items(i, class_name)

    def walk(node: Any):
        if isinstance(node, dict):
            if node.get("kind") == "ClassDeclaration":
                class_name = _extract_identifier_text(node.get("name")) or "<unknown_class>"
                decl_info = class_decl_map.get(class_name)
                if decl_info and decl_info.kind == "seq_item":
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



def collect_seq_items(filepath: str, show_diagnostics: bool = True) -> List[SeqItemInfo]:
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
    constraints_by_class = extract_constraints_from_json(filepath, class_decl_map)

    items: List[SeqItemInfo] = []
    for class_name in sorted(class_decl_map.keys()):
        decl = class_decl_map[class_name]
        if decl.kind != "seq_item":
            continue

        ci = SeqItemInfo(
            name=class_name,
            kind=decl.kind,
            base_name=decl.base_name,
            parameters=decl.parameters,
            fields=fields_by_class.get(class_name, []),
            constraints=constraints_by_class.get(class_name, []),
        )
        items.append(ci)

    return items


# -----------------------------
# Formatting helpers
# -----------------------------

def dedupe_fields(fields: List[FieldInfo]) -> List[FieldInfo]:
    seen = set()
    out: List[FieldInfo] = []
    for f in fields:
        key = (f.name, f.sv_type, f.rand_mode, f.default, f.is_local)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out



def dedupe_constraints(constraints: List[ConstraintInfo]) -> List[ConstraintInfo]:
    seen = set()
    out: List[ConstraintInfo] = []
    for c in constraints:
        key = (c.name, c.text, c.is_local)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out



def format_seq_item_info(ci: SeqItemInfo) -> str:
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
    return "\n".join(lines)



def write_summary(items: List[SeqItemInfo], out_file: str) -> None:
    with open(out_file, "w", encoding="utf-8") as f:
        for ci in items:
            f.write(format_seq_item_info(ci))
            f.write("\n")



def seq_items_to_json_dict(items: List[SeqItemInfo]) -> Dict[str, Any]:
    out_items: List[Dict[str, Any]] = []
    for ci in items:
        out_items.append({
            "name": ci.name,
            "kind": ci.kind,
            "base_name": ci.base_name,
            "parameters": ci.parameters,
            "fields": [asdict(f) for f in dedupe_fields(ci.fields)],
            "constraints": [asdict(c) for c in dedupe_constraints(ci.constraints)],
        })

    return {
        "sequence_items": out_items
    }


# -----------------------------
# CLI
# -----------------------------

def default_out_path(input_file: str, out_format: str) -> str:
    base = os.path.splitext(os.path.basename(input_file))[0]
    ext = "json" if out_format == "json" else "txt"
    return f"{base}_seq_item_summary.{ext}"



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="SystemVerilog file (.sv/.svh)")
    parser.add_argument("--out", default=None, help="Output file path")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument("--no-diags", action="store_true", help="Do not print diagnostics")
    args = parser.parse_args()

    items = collect_seq_items(args.file, show_diagnostics=not args.no_diags)

    if not items:
        if args.format == "json":
            payload = {"sequence_items": []}
            rendered = json.dumps(payload, indent=2 if args.pretty else None)
            if args.out:
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write(rendered)
                print(f"Wrote JSON to {args.out}")
            else:
                print(rendered)
        else:
            print("No sequence-item classes found in file.")
        return

    out_file = args.out if args.out else default_out_path(args.file, args.format)

    if args.format == "json":
        payload = seq_items_to_json_dict(items)
        rendered = json.dumps(payload, indent=2 if args.pretty else None)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"Wrote JSON to {out_file}")
    else:
        write_summary(items, out_file)
        print(f"Wrote summary to {out_file}")


if __name__ == "__main__":
    main()
