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
#         - inline randomize-with constraints in the form: constraints inline_N { ... }
#
# The output is an event trace that shows where sequence items are started and how they are used.
#
# To run:
#   python parse_seq.py <file.svh>


# -----------------------------
# Data model
# -----------------------------
@dataclass
class FlowEvent:
    kind: str              # "declare" | "create" | "start" | "randomize" | "finish" | "macro" | "call"
    handle: Optional[str]  # "req"
    handle_type: Optional[str]  # "apb_seq_item"
    text: str              # reconstructed statement / call text (single line)
    path: str = ""         # condition / loop context, e.g. "while() & if(cond)"
    constraint_text: Optional[str] = None


@dataclass
class SequenceFlow:
    seq_class: str                 # apb_seq
    item_type_param: Optional[str] # apb_seq_item (from uvm_sequence #(T))
    proc: str                      # "task body" / "function foo" / etc.
    events: List[FlowEvent] = field(default_factory=list)


# -----------------------------
# Path helpers
# -----------------------------
def _path_from_stack(cond_stack: List[str]) -> str:
    if not cond_stack:
        return ""
    return " & ".join(cond_stack)


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
    s = re.sub(r"(?m)^\s*//.*\n?", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_constraint_body(s: str) -> str:
    s = s.replace("\r\n", "\n")
    s = re.sub(r"(?m)^\s*//.*\n?", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*==\s*", " == ", s)
    s = re.sub(r"\s*!=\s*", " != ", s)
    s = re.sub(r"\s*>=\s*", " >= ", s)
    s = re.sub(r"\s*<=\s*", " <= ", s)
    s = re.sub(r"\s*&&\s*", " && ", s)
    s = re.sub(r"\s*\|\|\s*", " || ", s)
    s = re.sub(r"\s*:=\s*", " := ", s)

    # Avoid breaking slices / ranges like [7:4] or {[11:20]}
    s = re.sub(r"(?<!\[)\s*:\s*(?!\])", " : ", s)

    # Comparison operators after generic spacing cleanup
    s = re.sub(r"(?<![<>=!])\s*>\s*(?![=])", " > ", s)
    s = re.sub(r"(?<![<])\s*<\s*(?![=])", " < ", s)

    s = re.sub(r"(\d)\s+'([bodhBODH])", r"\1'\2", s)
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
    if not isinstance(node, dict):
        return None
    txt = node.get("text")
    if isinstance(txt, str):
        return txt
    return None


def _extract_randomize_with_constraint(inv: Dict[str, Any]) -> Optional[str]:
    """
    Search the invocation subtree for a randomize-with constraint block and
    return normalized contents without outer braces.
    """
    found_text: Optional[str] = None

    def walk(node: Any):
        nonlocal found_text
        if found_text is not None:
            return

        if isinstance(node, dict):
            kind = node.get("kind", "")

            # Prefer explicit "with" related nodes
            if "With" in kind or kind in {
                "ConstraintBlock",
                "ConstraintExpression",
                "ConstraintSet",
                "ConstraintBlockItem",
            }:
                txt = _minify_ws(_collect_tokens(node))
                if "{" in txt and "}" in txt:
                    found_text = txt
                    return

            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(inv)

    if not found_text:
        txt = _minify_ws(_collect_tokens(inv))
        m = re.search(r"\bwith\s*\{(.*)\}\s*$", txt)
        if m:
            found_text = "{" + m.group(1).strip() + "}"

    if not found_text:
        return None

    txt = found_text.strip()
    if txt.startswith("{") and txt.endswith("}"):
        txt = txt[1:-1].strip()
    else:
        m = re.search(r"\{(.*)\}", txt)
        if m:
            txt = m.group(1).strip()

    txt = _normalize_constraint_body(txt)
    if txt and not txt.endswith(";"):
        txt += ";"
    return txt or None

# -----------------------------
# Expression randomize walker
# -----------------------------
def _walk_expr_for_randomize(
    expr: Any,
    handle_types: Dict[str, str],
    events: List[FlowEvent],
    cond_stack: List[str],
) -> None:
    """
    Search an expression tree for randomize(...) or <handle>.randomize(...)
    and emit FlowEvents for them.
    """
    if isinstance(expr, dict):
        if expr.get("kind") == "InvocationExpression":
            call = _extract_invocation_name(expr)
            if call == "randomize":
                handle = _extract_randomize_handle_from_invocation(expr) or _extract_first_arg_identifier(expr)
                txt = _minify_ws(_collect_tokens(expr))
                constraint_text = _extract_randomize_with_constraint(expr)
                events.append(
                    FlowEvent(
                        kind="randomize",
                        handle=handle,
                        handle_type=handle_types.get(handle),
                        text=txt,
                        path=_path_from_stack(cond_stack),
                        constraint_text=constraint_text,
                    )
                )
        for v in expr.values():
            _walk_expr_for_randomize(v, handle_types, events, cond_stack)
    elif isinstance(expr, list):
        for x in expr:
            _walk_expr_for_randomize(x, handle_types, events, cond_stack)


# -----------------------------
# Helper: names and class-scope item handles
# -----------------------------
def _get_name_from_proto_name(node: Any) -> Optional[str]:
    """Handle both ScopedName and simple Identifier/IdentifierName."""
    if not isinstance(node, dict):
        return None
    k = node.get("kind")
    if k == "ScopedName":
        return None
    if k == "IdentifierName":
        return _get_identifier_from_identifiername(node)
    txt = node.get("text")
    if isinstance(txt, str):
        return txt
    return None


def _collect_class_item_handles(
    class_decl: Dict[str, Any],
    item_type: Optional[str],
) -> Dict[str, str]:
    """
    Look for DataDeclaration nodes at class scope whose type matches item_type.
    Returns { handle_name -> type_name }.
    We intentionally do NOT recurse into tasks/functions here.
    """
    handles: Dict[str, str] = {}

    def walk(node: Any):
        if isinstance(node, dict):
            k = node.get("kind")
            if k in ("TaskDeclaration", "FunctionDeclaration"):
                return

            if k == "DataDeclaration":
                ht = _extract_decl_handle_and_type(node)
                if ht:
                    handle, type_name = ht
                    if item_type is None or type_name == item_type:
                        handles.setdefault(handle, type_name)

            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(class_decl)
    return handles


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
# Macro detection
# -----------------------------
_UVM_MACROS = {
    "`uvm_do",
    "`uvm_do_with",
    "`uvm_do_on",
    "`uvm_do_on_with",
    "`uvm_do_pri",
    "`uvm_do_pri_with",
    "`uvm_do_on_pri",
    "`uvm_do_on_pri_with",
    "`uvm_create",
    "`uvm_create_on",
    "`uvm_send",
    "`uvm_send_pri",
    "`uvm_rand_send",
    "`uvm_rand_send_with",
    "`uvm_info",
    "`uvm_error",
    "`uvm_warning",
    "`uvm_fatal",
    "`uvm_object_utils",
}

def _macro_event_kind(macro: str) -> Optional[str]:
    if macro == "`uvm_do":
        return "DO"
    if macro == "`uvm_do_with":
        return "DO_WITH"
    return None

def _macro_uses_item_handle(macro: str) -> bool:
    return macro in {
        "`uvm_do",
        "`uvm_do_with",
        "`uvm_do_on",
        "`uvm_do_on_with",
        "`uvm_do_pri",
        "`uvm_do_pri_with",
        "`uvm_do_on_pri",
        "`uvm_do_on_pri_with",
        "`uvm_create",
        "`uvm_create_on",
        "`uvm_send",
        "`uvm_send_pri",
        "`uvm_rand_send",
        "`uvm_rand_send_with",
    }

def _extract_constraint_from_macro_args(macro: str, macro_args: List[str]) -> Optional[str]:
    if macro != "`uvm_do_with":
        return None
    if len(macro_args) < 2:
        return None

    txt = macro_args[1].strip()
    if txt.startswith("{") and txt.endswith("}"):
        txt = txt[1:-1].strip()

    txt = _normalize_constraint_body(txt)
    if txt and not txt.endswith(";"):
        txt += ";"
    return txt or None

def _token_text_list(tokens: Any) -> List[str]:
    out: List[str] = []
    if isinstance(tokens, list):
        for t in tokens:
            if isinstance(t, dict) and isinstance(t.get("text"), str):
                out.append(t["text"])
    return out


def _macro_arg_text(arg: Dict[str, Any]) -> str:
    if not isinstance(arg, dict):
        return ""
    toks = arg.get("tokens")
    return _minify_ws("".join(_token_text_list(toks)))


def _extract_first_identifier_from_macro_arg(arg: Dict[str, Any]) -> Optional[str]:
    if not isinstance(arg, dict):
        return None
    toks = arg.get("tokens")
    if not isinstance(toks, list):
        return None

    for t in toks:
        if isinstance(t, dict) and t.get("kind") == "Identifier":
            txt = t.get("text")
            if isinstance(txt, str):
                return txt
    return None


def _extract_macro_usage_info_from_trivia_item(triv: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Given one trivia item, if it is a MacroUsage directive, return:
      {
        "macro": "`uvm_create",
        "args": ["req"],
        "handle": "req",
        "raw": "`uvm_create(req)"
      }
    else return None.
    """
    if not isinstance(triv, dict):
        return None
    if triv.get("kind") != "Directive":
        return None

    syntax = triv.get("syntax")
    if not isinstance(syntax, dict):
        return None
    if syntax.get("kind") != "MacroUsage":
        return None

    directive = syntax.get("directive")
    if not isinstance(directive, dict):
        return None

    macro = directive.get("text")
    if not isinstance(macro, str):
        return None

    arg_list = syntax.get("args")
    macro_args: List[str] = []
    handle: Optional[str] = None

    if isinstance(arg_list, dict) and arg_list.get("kind") == "MacroActualArgumentList":
        args = arg_list.get("args")
        if isinstance(args, list):
            actual_args = [a for a in args if isinstance(a, dict) and a.get("kind") == "MacroActualArgument"]
            macro_args = [_macro_arg_text(a) for a in actual_args]

            if actual_args and _macro_uses_item_handle(macro):
                handle = _extract_first_identifier_from_macro_arg(actual_args[0])

    raw = macro
    if macro_args:
        raw += "(" + ", ".join(macro_args) + ")"

    return {
        "macro": macro,
        "args": macro_args,
        "handle": handle,
        "raw": raw,
    }



def _macro_implied_event_kinds(macro: str) -> List[str]:
    if macro in {"`uvm_create", "`uvm_create_on"}:
        return ["create"]

    if macro in {"`uvm_send", "`uvm_send_pri"}:
        return ["start", "finish"]

    if macro in {"`uvm_rand_send", "`uvm_rand_send_with"}:
        return ["randomize", "start", "finish"]

    if macro in {
        "`uvm_do",
        "`uvm_do_with",
        "`uvm_do_on",
        "`uvm_do_on_with",
        "`uvm_do_pri",
        "`uvm_do_pri_with",
        "`uvm_do_on_pri",
        "`uvm_do_on_pri_with",
    }:
        return ["create", "randomize", "start", "finish"]

    return []


def _emit_macros_from_child_trivia(
    node: Dict[str, Any],
    child_keys: List[str],
    handle_types: Dict[str, str],
    events: List[FlowEvent],
    cond_stack: List[str],
) -> None:
    if not isinstance(node, dict):
        return

    def handle_trivia_list(trivia: Any):
        if not isinstance(trivia, list):
            return

        for triv in trivia:
            info = _extract_macro_usage_info_from_trivia_item(triv)
            if not info:
                continue

            macro = info["macro"]
            if macro not in _UVM_MACROS:
                continue

            handle = info["handle"]
            raw = info["raw"]
            handle_type = handle_types.get(handle) if handle else None
            implied = _macro_implied_event_kinds(macro)
            macro_kind = _macro_event_kind(macro)

            if macro_kind is not None:
                events.append(
                    FlowEvent(
                        kind=macro_kind,
                        handle=handle,
                        handle_type=handle_type,
                        text=raw,
                        path=_path_from_stack(cond_stack),
                        constraint_text=_extract_constraint_from_macro_args(macro, info["args"]),
                    )
                )
            elif not implied:
                events.append(
                    FlowEvent(
                        kind="macro",
                        handle=handle,
                        handle_type=handle_type,
                        text=raw,
                        path=_path_from_stack(cond_stack),
                    )
                )
            else:
                for implied_kind in implied:
                    events.append(
                        FlowEvent(
                            kind=implied_kind,
                            handle=handle,
                            handle_type=handle_type,
                            text=f"{raw} [from {macro}]",
                            path=_path_from_stack(cond_stack),
                        )
                    )
    for key in child_keys:
        child = node.get(key)

        if isinstance(child, dict):
            handle_trivia_list(child.get("trivia"))

        elif isinstance(child, list):
            for elem in child:
                if isinstance(elem, dict):
                    handle_trivia_list(elem.get("trivia"))


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
# Procedural traversal
# -----------------------------
_START_CALLS = {"start_item", "send_request", "uvm_send", "send"}
_FINISH_CALLS = {"finish_item", "wait_for_item_done", "item_done"}
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


def _walk_procedural(
    node: Any,
    handle_types: Dict[str, str],
    events: List[FlowEvent],
    cond_stack: Optional[List[str]] = None,
) -> None:
    """
    Recursively walk any subtree that represents procedural code and emit FlowEvents.
    Now tracks branching via cond_stack (while/if contexts).
    """
    if cond_stack is None:
        cond_stack = []

    if isinstance(node, dict):
        kind = node.get("kind")

        if kind == "SequentialBlockStatement":
            _emit_macros_from_child_trivia(node, ["begin"], handle_types, events, cond_stack)
            for v in node.values():
                _walk_procedural(v, handle_types, events, cond_stack)
            _emit_macros_from_child_trivia(node, ["end"], handle_types, events, cond_stack)
            return

        if kind in ("TaskDeclaration", "FunctionDeclaration"):
            _emit_macros_from_child_trivia(node, ["prototype"], handle_types, events, cond_stack)

            for key, v in node.items():
                if key == "end":
                    continue
                _walk_procedural(v, handle_types, events, cond_stack)

            _emit_macros_from_child_trivia(node, ["end"], handle_types, events, cond_stack)
            return

        if kind == "LoopStatement":
            rw = node.get("repeatOrWhile")
            if isinstance(rw, dict) and rw.get("kind") == "WhileKeyword":
                cond_expr = node.get("expr")
                cond_txt = _minify_ws(_collect_tokens(cond_expr)) if cond_expr is not None else "<while-cond>"

                body = node.get("statement")
                if body is not None:
                    _walk_procedural(
                        body,
                        handle_types,
                        events,
                        cond_stack + [f"while({cond_txt})"],
                    )

                if cond_expr is not None:
                    _walk_expr_for_randomize(
                        cond_expr,
                        handle_types,
                        events,
                        cond_stack + [f"while({cond_txt})"],
                    )
                return

        if kind == "ConditionalStatement":
            _emit_macros_from_child_trivia(node, ["ifKeyword"], handle_types, events, cond_stack)
            predicate = node.get("predicate")
            cond_txt = _minify_ws(_collect_tokens(predicate)) if predicate is not None else "<if-cond>"

            if predicate is not None:
                _walk_expr_for_randomize(
                    predicate,
                    handle_types,
                    events,
                    cond_stack + [f"if({cond_txt})"],
                )

            then_stmt = node.get("statement")
            else_clause = node.get("elseClause")

            if then_stmt is not None:
                _walk_procedural(
                    then_stmt,
                    handle_types,
                    events,
                    cond_stack + [f"if({cond_txt})"],
                )

            if isinstance(else_clause, dict):
                else_stmt = else_clause.get("statement")
                if else_stmt is not None:
                    _walk_procedural(
                        else_stmt,
                        handle_types,
                        events,
                        cond_stack + [f"else({cond_txt})"],
                    )
            return

        if kind == "DataDeclaration":
            ht = _extract_decl_handle_and_type(node)
            if ht:
                handle, type_name = ht
                handle_types.setdefault(handle, type_name)
                events.append(
                    FlowEvent(
                        kind="declare",
                        handle=handle,
                        handle_type=type_name,
                        text=_statement_text(node),
                        path=_path_from_stack(cond_stack),
                    )
                )

        if kind == "ExpressionStatement":
            expr = node.get("expr")
            stmt_txt = _statement_text(node)

            if isinstance(expr, dict) and expr.get("kind") == "AssignmentExpression":
                left = expr.get("left")
                handle = _get_identifier_from_identifiername(left)
                right = expr.get("right")
                if isinstance(right, dict) and right.get("kind") == "InvocationExpression":
                    call = _extract_invocation_name(right)
                    if call == "create":
                        events.append(
                            FlowEvent(
                                kind="create",
                                handle=handle,
                                handle_type=handle_types.get(handle),
                                text=stmt_txt,
                                path=_path_from_stack(cond_stack),
                            )
                        )

            if isinstance(expr, dict) and expr.get("kind") == "InvocationExpression":
                call = _extract_invocation_name(expr)
                txt = stmt_txt

                if call in _START_CALLS:
                    handle = _extract_first_arg_identifier(expr)
                    events.append(
                        FlowEvent(
                            kind="start",
                            handle=handle,
                            handle_type=handle_types.get(handle),
                            text=txt,
                            path=_path_from_stack(cond_stack),
                        )
                    )
                elif call in _FINISH_CALLS:
                    handle = _extract_first_arg_identifier(expr)
                    events.append(
                        FlowEvent(
                            kind="finish",
                            handle=handle,
                            handle_type=handle_types.get(handle),
                            text=txt,
                            path=_path_from_stack(cond_stack),
                        )
                    )
                elif call in _RANDOMIZE_CALLS:
                    handle = _extract_first_arg_identifier(expr)
                    events.append(
                        FlowEvent(
                            kind="randomize",
                            handle=handle,
                            handle_type=handle_types.get(handle),
                            text=txt,
                            path=_path_from_stack(cond_stack),
                            constraint_text=_extract_randomize_with_constraint(expr),
                        )
                    )
                else:
                    events.append(
                        FlowEvent(
                            kind="call",
                            handle=None,
                            handle_type=None,
                            text=txt,
                            path=_path_from_stack(cond_stack),
                        )
                    )

            if expr is not None:
                _walk_expr_for_randomize(expr, handle_types, events, cond_stack)

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
                    events.append(
                        FlowEvent(
                            kind="randomize",
                            handle=handle,
                            handle_type=handle_types.get(handle),
                            text=txt,
                            path=_path_from_stack(cond_stack),
                            constraint_text=_extract_randomize_with_constraint(inv),
                        )
                    )

        for v in node.values():
            _walk_procedural(v, handle_types, events, cond_stack)

    elif isinstance(node, list):
        for i in node:
            _walk_procedural(i, handle_types, events, cond_stack)



# -----------------------------
# Entry point: extract flows
# -----------------------------
def extract_sequence_flows_from_file(filepath: str) -> List[SequenceFlow]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    seq_class_to_item = _find_sequence_classes(cst)
    flows: List[SequenceFlow] = []
    class_item_handles: Dict[str, Dict[str, str]] = {}

    def walk(x: Any, current_class: Optional[str] = None):
        if isinstance(x, dict):
            k = x.get("kind")

            if k == "ClassDeclaration":
                cls_name = _extract_simple_identifier_text(x.get("name"))

                if cls_name and cls_name in seq_class_to_item:
                    item_type = seq_class_to_item[cls_name]
                    class_item_handles[cls_name] = _collect_class_item_handles(x, item_type)

                for v in x.values():
                    walk(v, current_class=cls_name)
                return

            if k in ("TaskDeclaration", "FunctionDeclaration"):
                proto = x.get("prototype")
                if isinstance(proto, dict):
                    name_node = proto.get("name")

                    scoped = _extract_scoped_name_text(name_node)
                    seq_cls: Optional[str] = None
                    proc_name: Optional[str] = None

                    if scoped and "::" in scoped:
                        seq_cls, proc_name = [p.strip() for p in scoped.split("::", 1)]
                    else:
                        if current_class is not None:
                            seq_cls = current_class
                            proc_name = _get_name_from_proto_name(name_node)

                    if seq_cls and proc_name and seq_cls in seq_class_to_item:
                        handle_types: Dict[str, str] = dict(class_item_handles.get(seq_cls, {}))
                        events: List[FlowEvent] = []

                        for h, t in class_item_handles.get(seq_cls, {}).items():
                            events.append(
                                FlowEvent(
                                    kind="declare",
                                    handle=h,
                                    handle_type=t,
                                    text=f"{t} {h};",
                                    path="",
                                )
                            )

                        _walk_procedural(x, handle_types, events, cond_stack=[])

                        flows.append(
                            SequenceFlow(
                                seq_class=seq_cls,
                                item_type_param=seq_class_to_item.get(seq_cls),
                                proc=("task " if k == "TaskDeclaration" else "function ") + proc_name,
                                events=events,
                            )
                        )

            for v in x.values():
                walk(v, current_class=current_class)

        elif isinstance(x, list):
            for i in x:
                walk(i, current_class=current_class)

    walk(cst, current_class=None)
    return flows


def _extract_constraint_from_path(path: str) -> Optional[str]:
    """
    Extract inline randomize-with constraint text from a path string like:
      if(!req.randomize() with { rst_n==1; addr_i==MODE0_OFFSET; we==1; re==0;})
    """
    if not path:
        return None

    m = re.search(r"\bwith\s*\{(.*)\}\s*\)?\s*$", path)
    if not m:
        return None

    txt = m.group(1).strip()
    txt = _normalize_constraint_body(txt)
    if txt and not txt.endswith(";"):
        txt += ";"
    return txt or None
# -----------------------------
# Output formatting
# -----------------------------
def _format_flows(flows: List[SequenceFlow], include_calls: bool = False) -> str:
    lines: List[str] = []
    lines.append("Sequence Item Flow:")

    if not flows:
        lines.append("  <no sequence flows found>")
        return "\n".join(lines)

    flows_by_seq: Dict[str, List[SequenceFlow]] = {}
    for fl in flows:
        flows_by_seq.setdefault(fl.seq_class, []).append(fl)

    first = True
    for seq in sorted(flows_by_seq.keys()):
        if not first:
            lines.append("")   # <-- blank line separator
        first = False
        item = flows_by_seq[seq][0].item_type_param or "<unknown_item_type>"
        lines.append(f"  {seq} (uvm_sequence#({item}))")

        for fl in sorted(flows_by_seq[seq], key=lambda x: x.proc):
            lines.append(f"    {fl.proc}:")
            inline_idx = 0

            for e in fl.events:
                if not include_calls and e.kind in ("call",):
                    continue

                path_suffix = f"  [path: {e.path}]" if e.path else ""

                if e.handle:
                    t = f" type={e.handle_type}" if e.handle_type else ""
                    lines.append(f"      [{e.kind}] {e.handle}{t}: {e.text}{path_suffix}")
                else:
                    lines.append(f"      [{e.kind}] {e.text}{path_suffix}")

                if e.kind in ("randomize", "DO_WITH"):
                    constraint_text = e.constraint_text or _extract_constraint_from_path(e.path)
                    if constraint_text:
                        inline_idx += 1
                        lines.append(f"        constraints macro_inline_{inline_idx} {{ {constraint_text} }}")

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
    return f"{base}__seq_summary.txt"


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