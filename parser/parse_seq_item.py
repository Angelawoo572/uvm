import pyslang
import json
from typing import Union, List, Dict, Any, Optional
from dataclasses import dataclass, field
import os
import argparse
import re

# High-Level Overview:
# This script analyzes a SystemVerilog (.sv / .svh) file containing UVM sequence items.
# The file is first parsed into a syntax tree using pyslang, then added to a Compilation
# object where slang resolves classes, variables, and types into semantic symbols.
# By walking the compilation with a visitor, the script detects when a class is
# encountered and records each variable (VariableSymbol) associated with that class,
# including its type and whether it is declared as rand.
#
# Constraints are extracted separately using the CST JSON representation of the syntax
# tree. The script locates ConstraintDeclaration nodes and reconstructs clean,
# human-readable constraint text directly from the JSON token structure. This avoids
# relying on semantic resolution of constraint bodies, which may fail when UVM macros
# or base classes are undefined.
#
# The final result is a structured summary of each class, including its fields and
# fully reconstructed constraint blocks.
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
    fields: List[FieldInfo] = field(default_factory=list)
    constraints: List[ConstraintInfo] = field(default_factory=list)


# -----------------------------
# Semantic extraction for fields
# -----------------------------
class ClassCollector:
    """
    Collect fields using Compilation semantic symbols.
    Keeps your simple 'current_class' heuristic.
    """
    def __init__(self):
        self._classes: Dict[str, ClassInfo] = {}
        self._current_class: Optional[str] = None

    def _ensure(self, class_name: str) -> ClassInfo:
        if class_name not in self._classes:
            self._classes[class_name] = ClassInfo(name=class_name)
        return self._classes[class_name]

    def __call__(self, obj: Union[pyslang.Token, pyslang.SyntaxNode]):
        if isinstance(obj, pyslang.ClassType):
            self._current_class = obj.name
            self._ensure(obj.name)
            return

        if self._current_class is None:
            return

        if isinstance(obj, pyslang.VariableSymbol):
            rand_mode = getattr(obj, "randMode", None)
            rand_name = rand_mode.name if rand_mode is not None else "None"
            ci = self._ensure(self._current_class)
            ci.fields.append(FieldInfo(name=obj.name,
                                       sv_type=str(obj.type),
                                       rand_mode=rand_name))

    def results(self) -> List[ClassInfo]:
        return [self._classes[k] for k in sorted(self._classes.keys())]


# -----------------------------
# Compilation
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

    collector = ClassCollector()
    comp.getRoot().visit(collector)
    return collector.results()


# -----------------------------
# JSON-only constraint extraction
# -----------------------------
def _extract_identifier_text(name_node: Any) -> Optional[str]:
    if not isinstance(name_node, dict):
        return None
    ident = name_node.get("identifier")
    if isinstance(ident, dict):
        txt = ident.get("text")
        if isinstance(txt, str):
            return txt
    val = name_node.get("value")
    if isinstance(val, str):
        return val
    return None


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

                # Skip banner comments attached to 'constraint' keyword
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


def _normalize_constraint_text(s: str) -> str:
    # Normalize line endings
    s = s.replace("\r\n", "\n")

    # Remove full-line // comments (banner lines)
    s = re.sub(r"(?m)^\s*//.*\n?", "", s)

    # Collapse ALL whitespace (including newlines) into single spaces
    s = re.sub(r"\s+", " ", s).strip()

    # No space right before ')' or ']' or '}'
    s = re.sub(r"\s+([\)\]\}])", r"\1", s)

    # No space before semicolons / commas
    s = re.sub(r"\s+([;,])", r"\1", s)

    # Make brace spacing consistent: "name {" not "name  {"
    s = re.sub(r"\s+\{", " {", s)

    # Fix double equals spacing: "==" with single spaces around
    s = re.sub(r"\s*==\s*", " == ", s)

    # Collapse again in case punctuation fixes created doubles
    s = re.sub(r"\s+", " ", s).strip()

    return s



def extract_constraints_from_json(filepath: str) -> List[ConstraintInfo]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    constraints: List[ConstraintInfo] = []

    def walk(x: Any):
        if isinstance(x, dict):
            if x.get("kind") == "ConstraintDeclaration":
                cname = _extract_identifier_text(x.get("name")) or "<unknown_constraint>"

                kw = x.get("keyword")
                nm = x.get("name")
                blk = x.get("block")

                parts: List[str] = []

                if isinstance(kw, dict) and isinstance(kw.get("text"), str):
                    parts.append(kw["text"])

                if nm is not None:
                    parts.append(_collect_tokens(nm))

                if blk is not None:
                    parts.append(_collect_tokens(blk))

                text = "".join(parts)
                text = _normalize_constraint_text(text)

                constraints.append(ConstraintInfo(name=cname, text=text))

            for v in x.values():
                walk(v)

        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(cst)
    return constraints


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
            lines.append(f"  {f.name:12s} : {f.sv_type:20s} rand_mode={f.rand_mode}")
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
    return f"{base}_summary.txt"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="SystemVerilog file (.sv/.svh)")
    parser.add_argument("--out", default=None, help="Output text file path")
    parser.add_argument("--no-diags", action="store_true", help="Do not print diagnostics")
    args = parser.parse_args()

    classes = collect_classes(args.file, show_diagnostics=not args.no_diags)

    if not classes:
        print("No classes found in file.")
        return

    constraints = extract_constraints_from_json(args.file)

    # Attach constraints to classes (usually 1 per file)
    if len(classes) == 1:
        classes[0].constraints.extend(constraints)
    else:
        for ci in classes:
            ci.constraints.extend(constraints)

    out_file = args.out if args.out else default_out_path(args.file)
    write_summary(classes, out_file)
    print(f"Wrote summary to {out_file}")


if __name__ == "__main__":
    main()
