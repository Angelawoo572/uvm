import pyslang
import json
import argparse
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# High-Level Overview:
# This script analyzes a SystemVerilog (.sv / .svh) file containing UVM sequences and extracts the
# procedural "flow" of sequence items. It parses the file into a syntax tree with pyslang, converts
# that tree into CST JSON, then walks the JSON to:
#   1) Identify uvm_sequence #(T) classes (sequence class + sequence item type parameter).
#   2) Find procedural blocks (tasks/functions), especially <seq>::body, and recursively traverse
#      all nested statements (ifs/loops/begin-end/fork-join) to detect:
#         - handle declarations (type + handle)
#         - handle assignments created via type_id::create
#         - start points (start_item(handle), send_request(handle), etc.)
#         - randomization calls (handle.randomize(), randomize(handle))
#         - finish points (finish_item(handle), wait_for_item_done(), etc.)
#         - macro shorthands (`uvm_do / `uvm_create / `uvm_send) via token inspection
# The output is an event trace that shows where sequence items are started and how they are used.
#
# To run:
#   python parse_sequences.py <file.svh>


# -----------------------------
# Data model
# -----------------------------
@dataclass
class FlowEvent:
    kind: str              # "declare" | "create" | "start" | "randomize" | "finish" | "macro" | "call"
    handle: Optional[str]  # "req"
    handle_type: Optional[str]  # "apb_seq_item"
    text: str              # reconstructed statement / call text (single line)


@dataclass
class SequenceFlow:
    seq_class: str                 # apb_seq
    item_type_param: Optional[str] # apb_seq_item (from uvm_sequence #(T))
    proc: str                      # "task body" / "function foo" / etc.
    events: List[FlowEvent] = field(default_factory=list)


# -----------------------------
# CST JSON token helpers
# -----------------------------
def _collect_tokens(node: Any) -> str:
    """Reconstruct token text in JSON order, including trivia."""
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


def _minify_ws(s: str) -> str:
    """One-line, stable rendering for statements."""
    s = s.replace("\r\n", "\n")
    s = re.sub(r"(?m)^\s*//.*\n?", "", s)     # drop full-line comments
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _get_identifier_from_identifiername(node: Any) -> Optional[str]:
    if not isinstance(node, dict):
        return None
    if node.get("kind") == "IdentifierName":
        ident = node.get("identifier")
        if isinstance(ident, dict) and isinstance(ident.get("text"), str):
            return ident["text"]
    return None


def _extract_scoped_name_text(node: Any) -> Optional[str]:
    if not isinstance(node, dict):
        return None
    if node.get("kind") != "ScopedName":
        return None
    return _minify_ws(_collect_tokens(node))


def _extract_simple_identifier_text(node: Any) -> Optional[str]:
    # For nodes like {"kind":"Identifier", "text":"apb_seq"}
    if not isinstance(node, dict):
        return None
    txt = node.get("text")
    if isinstance(txt, str):
        return txt
    return None


# -----------------------------
# Sequence class discovery
# -----------------------------
def _extract_uvm_sequence_param_from_classdecl(class_decl: Dict[str, Any]) -> Optional[str]:
    """
    For:
      class apb_seq extends uvm_sequence #(apb_seq_item);
    extract "apb_seq_item".
    """
    ext = class_decl.get("extendsClause")
    if not isinstance(ext, dict):
        return None
    base = ext.get("baseName")
    if not isinstance(base, dict):
        return None

    ident = base.get("identifier")
    base_name = ident.get("text") if isinstance(ident, dict) and isinstance(ident.get("text"), str) else None
    if base_name != "uvm_sequence":
        return None

    params = base.get("parameters")
    if not isinstance(params, dict):
        return None
    plist = params.get("parameters")
    if not isinstance(plist, list) or not plist:
        return None

    p0 = plist[0]
    if not isinstance(p0, dict):
        return None
    expr = p0.get("expr")
    return _get_identifier_from_identifiername(expr)


def _find_sequence_classes(cst: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Returns { seq_class_name : item_type_param } for classes extending uvm_sequence #(T)."""
    seq_class_to_item: Dict[str, Optional[str]] = {}

    def walk(x: Any):
        if isinstance(x, dict):
            if x.get("kind") == "ClassDeclaration":
                cls = _extract_simple_identifier_text(x.get("name"))
                if cls:
                    item_param = _extract_uvm_sequence_param_from_classdecl(x)
                    if item_param is not None:
                        seq_class_to_item[cls] = item_param
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(cst)
    return seq_class_to_item


# -----------------------------
# Macro detection (uvm_do / uvm_create / uvm_send)
# -----------------------------
_UVM_MACROS = {"`uvm_do", "`uvm_do_with", "`uvm_create", "`uvm_send", "`uvm_rand_send", "`uvm_rand_send_with"}
# https://verificationacademy.com/verification-methodology-reference/uvm/docs_1.1b/html/files/macros/uvm_sequence_defines-svh.html

def _find_macro_usages(node: Any) -> List[str]:
    """
    Return a list of macro directive texts found in a subtree, e.g. "`uvm_do".
    """
    found: List[str] = []

    def walk(x: Any):
        if isinstance(x, dict):
            # Slang JSON often represents macro usage under trivia kind "Directive" with a nested MacroUsage.
            if x.get("kind") == "Directive":
                txt = x.get("text")
                if isinstance(txt, str) and txt in _UVM_MACROS:
                    found.append(txt)
            # Also sometimes the directive is under "directive": {"kind":"Directive","text":"`uvm_do"}
            d = x.get("directive")
            if isinstance(d, dict):
                txt = d.get("text")
                if isinstance(txt, str) and txt in _UVM_MACROS:
                    found.append(txt)

            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(node)
    return found


# -----------------------------
# Call and handle extraction helpers
# -----------------------------
def _extract_invocation_name(inv: Dict[str, Any]) -> Optional[str]:
    """
    InvocationExpression.left can be:
      - IdentifierName(start_item)
      - ScopedName(req.randomize)  -> return "randomize"
      - ScopedName(apb_seq_item::type_id::create) -> return "create" (rightmost)
    """
    left = inv.get("left")
    if not isinstance(left, dict):
        return None

    k = left.get("kind")
    if k == "IdentifierName":
        return _get_identifier_from_identifiername(left)

    if k == "ScopedName":
        right = left.get("right")
        if isinstance(right, dict) and right.get("kind") == "IdentifierName":
            return _get_identifier_from_identifiername(right)

    return None


def _extract_first_arg_identifier(inv: Dict[str, Any]) -> Optional[str]:
    """Extract identifier of first argument (e.g. start_item(req) -> 'req')."""
    args = inv.get("arguments")
    if not isinstance(args, dict):
        return None
    params = args.get("parameters")
    if not isinstance(params, list) or not params:
        return None

    p0 = params[0]
    if not isinstance(p0, dict):
        return None
    expr = p0.get("expr")

    found: Optional[str] = None

    def walk(x: Any):
        nonlocal found
        if found is not None:
            return
        if isinstance(x, dict):
            if x.get("kind") == "IdentifierName":
                ident = _get_identifier_from_identifiername(x)
                if ident:
                    found = ident
                    return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(expr)
    return found


def _extract_randomize_handle_from_invocation(inv: Dict[str, Any]) -> Optional[str]:
    """For req.randomize(), InvocationExpression.left is ScopedName(left=req, right=randomize)."""
    left = inv.get("left")
    if not isinstance(left, dict):
        return None
    if left.get("kind") != "ScopedName":
        return None
    base = left.get("left")
    return _get_identifier_from_identifiername(base)


def _statement_text(node: Any) -> str:
    return _minify_ws(_collect_tokens(node))


# -----------------------------
# Recursive procedural traversal
# -----------------------------
_START_CALLS = {"start_item", "send_request", "uvm_send", "send"}
_FINISH_CALLS = {"finish_item", "wait_for_item_done", "item_done"}
# "randomize" is handled specially because it can be method-call or function-call.
_RANDOMIZE_CALLS = {"randomize"}


def _extract_decl_handle_and_type(data_decl: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """
    DataDeclaration:
      type: NamedType -> IdentifierName.identifier.text = "apb_seq_item"
      declarators[0].name.text = "req"
    Return (handle, type_name)
    """
    if data_decl.get("kind") != "DataDeclaration":
        return None

    t = data_decl.get("type")
    type_name: Optional[str] = None
    if isinstance(t, dict) and t.get("kind") == "NamedType":
        nm = t.get("name")
        type_name = _get_identifier_from_identifiername(nm)

    decls = data_decl.get("declarators")
    if not isinstance(decls, list) or not decls:
        return None

    d0 = decls[0]
    if not isinstance(d0, dict):
        return None

    h = d0.get("name")
    handle = _extract_simple_identifier_text(h)

    if handle and type_name:
        return (handle, type_name)
    return None


def _walk_procedural(node: Any, handle_types: Dict[str, str], events: List[FlowEvent]) -> None:
    """
    Recursively walk any subtree that represents procedural code and emit FlowEvents.
    This does not try to build full control-flow; it emits events in traversal order.
    """
    if isinstance(node, dict):
        kind = node.get("kind")

        # Handle declarations: apb_seq_item req;
        if kind == "DataDeclaration":
            ht = _extract_decl_handle_and_type(node)
            if ht:
                handle, type_name = ht
                handle_types.setdefault(handle, type_name)
                events.append(FlowEvent(kind="declare", handle=handle, handle_type=type_name, text=_statement_text(node)))

        # Expression statements and their inner calls
        if kind == "ExpressionStatement":
            expr = node.get("expr")
            if isinstance(expr, dict):
                # Assignment create: req = T::type_id::create(...)
                if expr.get("kind") == "AssignmentExpression":
                    left = expr.get("left")
                    handle = _get_identifier_from_identifiername(left)
                    right = expr.get("right")
                    if isinstance(right, dict) and right.get("kind") == "InvocationExpression":
                        call = _extract_invocation_name(right)
                        if call == "create":
                            # best-effort type inference from RHS text (if we don't have it yet)
                            txt = _statement_text(node)
                            events.append(FlowEvent(
                                kind="create",
                                handle=handle,
                                handle_type=handle_types.get(handle),
                                text=txt
                            ))
                # Direct call statement: start_item(req); finish_item(req); etc.
                if expr.get("kind") == "InvocationExpression":
                    call = _extract_invocation_name(expr)
                    txt = _statement_text(node)

                    if call in _START_CALLS:
                        handle = _extract_first_arg_identifier(expr)
                        events.append(FlowEvent(
                            kind="start",
                            handle=handle,
                            handle_type=handle_types.get(handle),
                            text=txt
                        ))
                    elif call in _FINISH_CALLS:
                        handle = _extract_first_arg_identifier(expr)
                        events.append(FlowEvent(
                            kind="finish",
                            handle=handle,
                            handle_type=handle_types.get(handle),
                            text=txt
                        ))
                    elif call in _RANDOMIZE_CALLS:
                        # randomize(handle) form
                        handle = _extract_first_arg_identifier(expr)
                        events.append(FlowEvent(
                            kind="randomize",
                            handle=handle,
                            handle_type=handle_types.get(handle),
                            text=txt
                        ))
                    else:
                        events.append(FlowEvent(kind="call", handle=None, handle_type=None, text=txt))

        # assert(...) often wraps randomize
        if kind == "ImmediateAssertStatement":
            txt = _statement_text(node)

            inv: Optional[Dict[str, Any]] = None

            def find_inv(x: Any):
                nonlocal inv
                if inv is not None:
                    return
                if isinstance(x, dict):
                    if x.get("kind") == "InvocationExpression":
                        inv = x
                        return
                    for v in x.values():
                        find_inv(v)
                elif isinstance(x, list):
                    for i in x:
                        find_inv(i)

            find_inv(node.get("expr"))

            if isinstance(inv, dict):
                call = _extract_invocation_name(inv)
                if call == "randomize":
                    handle = _extract_randomize_handle_from_invocation(inv) or _extract_first_arg_identifier(inv)
                    events.append(FlowEvent(
                        kind="randomize",
                        handle=handle,
                        handle_type=handle_types.get(handle),
                        text=txt
                    ))

        # Macro usage inside this subtree
        macros = _find_macro_usages(node)
        for m in macros:
            events.append(FlowEvent(kind="macro", handle=None, handle_type=None, text=m))

        # Recurse
        for v in node.values():
            _walk_procedural(v, handle_types, events)

    elif isinstance(node, list):
        for i in node:
            _walk_procedural(i, handle_types, events)


# -----------------------------
# Entry point: extract flows
# -----------------------------
def extract_sequence_flows_from_file(filepath: str) -> List[SequenceFlow]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    seq_class_to_item = _find_sequence_classes(cst)
    flows: List[SequenceFlow] = []

    def walk(x: Any):
        if isinstance(x, dict):
            k = x.get("kind")

            # TaskDeclaration and FunctionDeclaration are both interesting.
            if k in ("TaskDeclaration", "FunctionDeclaration"):
                proto = x.get("prototype")
                if isinstance(proto, dict):
                    name_node = proto.get("name")

                    # We primarily care about scoped procedures like apb_seq::body
                    scoped = _extract_scoped_name_text(name_node)
                    if scoped and "::" in scoped:
                        seq_cls, proc_name = [p.strip() for p in scoped.split("::", 1)]
                        if seq_cls in seq_class_to_item:
                            handle_types: Dict[str, str] = {}
                            events: List[FlowEvent] = []

                            # Walk entire declaration subtree to catch nested begin/if/for/fork
                            _walk_procedural(x, handle_types, events)

                            flows.append(SequenceFlow(
                                seq_class=seq_cls,
                                item_type_param=seq_class_to_item.get(seq_cls),
                                proc=("task " if k == "TaskDeclaration" else "function ") + proc_name,
                                events=events
                            ))

            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(cst)
    return flows


# -----------------------------
# Output formatting
# -----------------------------
def _format_flows(flows: List[SequenceFlow], include_calls: bool = False) -> str:
    lines: List[str] = []
    lines.append("Sequence Item Flow:")

    if not flows:
        lines.append("  <no sequence flows found>")
        return "\n".join(lines)

    # Group by sequence class
    flows_by_seq: Dict[str, List[SequenceFlow]] = {}
    for fl in flows:
        flows_by_seq.setdefault(fl.seq_class, []).append(fl)

    for seq in sorted(flows_by_seq.keys()):
        item = flows_by_seq[seq][0].item_type_param or "<unknown_item_type>"
        lines.append(f"  {seq} (uvm_sequence#({item}))")

        for fl in sorted(flows_by_seq[seq], key=lambda x: x.proc):
            lines.append(f"    {fl.proc}:")

            for e in fl.events:
                if not include_calls and e.kind in ("call",):
                    continue

                if e.kind == "macro":
                    lines.append(f"      [macro] {e.text}")
                    continue

                if e.handle:
                    t = f" type={e.handle_type}" if e.handle_type else ""
                    lines.append(f"      [{e.kind}] {e.handle}{t}: {e.text}")
                else:
                    lines.append(f"      [{e.kind}] {e.text}")

    return "\n".join(lines)


def write_summary(out_file: str, flows: List[SequenceFlow], include_calls: bool = False) -> None:
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(_format_flows(flows, include_calls=include_calls))
        f.write("\n")


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
    parser.add_argument(
        "--include-calls",
        action="store_true",
        help="Include non-flow calls (everything that isn't declare/create/start/randomize/finish/macro)",
    )
    args = parser.parse_args()

    flows = extract_sequence_flows_from_file(args.file)

    out_file = args.out if args.out else default_out_path(args.file)
    write_summary(out_file, flows, include_calls=args.include_calls)
    print(f"Wrote flow summary to {out_file}")


if __name__ == "__main__":
    main()
