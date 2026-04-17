import pyslang
import json
import argparse
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

# High-Level Overview:
# This script analyzes a SystemVerilog (.sv / .svh) file containing UVM sequences and extracts the
# procedural flow of sequence items. It parses the file into a syntax tree with pyslang, converts
# that tree into CST JSON, and walks the JSON to:
#   1) Identify uvm_sequence #(T) classes.
#   2) Find procedural blocks, especially body().
#   3) Extract ordered events: declarations, creates, starts, randomize calls, finishes, macros, calls.
#   4) Preserve paths / conditional context.
#   5) Preserve inline constraints from randomize-with and `uvm_do_with.
#
# It supports both text and JSON output. The JSON is designed so that everything visible in the
# text summary is also present structurally in the JSON.
#
# TO RUN:
#   python parse_seq_with_json.py <file.svh>
#   python parse_seq_with_json.py <file.svh> --format json


@dataclass
class FlowEvent:
    kind: str
    handle: Optional[str]
    handle_type: Optional[str]
    text: str
    path: str = ""
    constraint_text: Optional[str] = None


@dataclass
class SequenceFlow:
    seq_class: str
    item_type_param: Optional[str]
    proc: str
    events: List[FlowEvent] = field(default_factory=list)


def _path_from_stack(cond_stack: List[str]) -> str:
    return " & ".join(cond_stack) if cond_stack else ""


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


def _minify_ws(s: str) -> str:
    s = s.replace("\r\n", "\n")
    s = re.sub(r"(?m)^\s*//.*\n?", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_constraint_body(s: str) -> str:
    s = s.replace("\r\n", "\n")
    s = re.sub(r"(?m)^\s*//.*\n?", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*=\s*=\s*", " == ", s)
    s = re.sub(r"\s*!\s*=\s*", " != ", s)
    s = re.sub(r"\s*>\s*=\s*", " >= ", s)
    s = re.sub(r"\s*<\s*=\s*", " <= ", s)
    s = re.sub(r"\s*&&\s*", " && ", s)
    s = re.sub(r"\s*\|\|\s*", " || ", s)
    s = re.sub(r"\s*:=\s*", " := ", s)
    s = re.sub(r"(?<!\[)\s*:\s*(?!\])", " : ", s)
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
    if not isinstance(node, dict) or node.get("kind") != "ScopedName":
        return None
    return _minify_ws(_collect_tokens(node))


def _extract_simple_identifier_text(node: Any) -> Optional[str]:
    if not isinstance(node, dict):
        return None
    txt = node.get("text")
    return txt if isinstance(txt, str) else None


def _extract_randomize_with_constraint(inv: Dict[str, Any]) -> Optional[str]:
    found_text: Optional[str] = None

    def walk(node: Any):
        nonlocal found_text
        if found_text is not None:
            return
        if isinstance(node, dict):
            kind = node.get("kind", "")
            if "With" in kind or kind in {"ConstraintBlock", "ConstraintExpression", "ConstraintSet", "ConstraintBlockItem"}:
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


def _walk_expr_for_randomize(expr: Any, handle_types: Dict[str, str], events: List[FlowEvent], cond_stack: List[str]) -> None:
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


def _get_name_from_proto_name(node: Any) -> Optional[str]:
    if not isinstance(node, dict):
        return None
    k = node.get("kind")
    if k == "ScopedName":
        return None
    if k == "IdentifierName":
        return _get_identifier_from_identifiername(node)
    txt = node.get("text")
    return txt if isinstance(txt, str) else None


def _collect_class_item_handles(class_decl: Dict[str, Any], item_type: Optional[str]) -> Dict[str, str]:
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


def _extract_uvm_sequence_param_from_classdecl(class_decl: Dict[str, Any]) -> Optional[str]:
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


_UVM_MACROS = {
    "`uvm_do", "`uvm_do_with", "`uvm_do_on", "`uvm_do_on_with", "`uvm_do_pri", "`uvm_do_pri_with",
    "`uvm_do_on_pri", "`uvm_do_on_pri_with", "`uvm_create", "`uvm_create_on", "`uvm_send", "`uvm_send_pri",
    "`uvm_rand_send", "`uvm_rand_send_with", "`uvm_info", "`uvm_error", "`uvm_warning", "`uvm_fatal",
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
        "`uvm_do", "`uvm_do_with", "`uvm_do_on", "`uvm_do_on_with", "`uvm_do_pri", "`uvm_do_pri_with",
        "`uvm_do_on_pri", "`uvm_do_on_pri_with", "`uvm_create", "`uvm_create_on", "`uvm_send", "`uvm_send_pri",
        "`uvm_rand_send", "`uvm_rand_send_with",
    }


def _extract_constraint_from_macro_args(macro: str, macro_args: List[str]) -> Optional[str]:
    if macro != "`uvm_do_with" or len(macro_args) < 2:
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
    if not isinstance(triv, dict) or triv.get("kind") != "Directive":
        return None
    syntax = triv.get("syntax")
    if not isinstance(syntax, dict) or syntax.get("kind") != "MacroUsage":
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
    return {"macro": macro, "args": macro_args, "handle": handle, "raw": raw}


def _macro_implied_event_kinds(macro: str) -> List[str]:
    if macro in {"`uvm_create", "`uvm_create_on"}:
        return ["create"]
    if macro in {"`uvm_send", "`uvm_send_pri"}:
        return ["start", "finish"]
    if macro in {"`uvm_rand_send", "`uvm_rand_send_with"}:
        return ["randomize", "start", "finish"]
    if macro in {
        "`uvm_do", "`uvm_do_with", "`uvm_do_on", "`uvm_do_on_with", "`uvm_do_pri", "`uvm_do_pri_with",
        "`uvm_do_on_pri", "`uvm_do_on_pri_with",
    }:
        return ["create", "randomize", "start", "finish"]
    return []


def _emit_macros_from_child_trivia(node: Dict[str, Any], child_keys: List[str], handle_types: Dict[str, str], events: List[FlowEvent], cond_stack: List[str]) -> None:
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
                events.append(FlowEvent(kind=macro_kind, handle=handle, handle_type=handle_type, text=raw,
                                        path=_path_from_stack(cond_stack),
                                        constraint_text=_extract_constraint_from_macro_args(macro, info["args"])))
            elif not implied:
                events.append(FlowEvent(kind="macro", handle=handle, handle_type=handle_type, text=raw,
                                        path=_path_from_stack(cond_stack)))
            else:
                for implied_kind in implied:
                    events.append(FlowEvent(kind=implied_kind, handle=handle, handle_type=handle_type,
                                            text=f"{raw} [from {macro}]", path=_path_from_stack(cond_stack)))

    for key in child_keys:
        child = node.get(key)
        if isinstance(child, dict):
            handle_trivia_list(child.get("trivia"))
        elif isinstance(child, list):
            for elem in child:
                if isinstance(elem, dict):
                    handle_trivia_list(elem.get("trivia"))


def _extract_invocation_name(inv: Dict[str, Any]) -> Optional[str]:
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
    left = inv.get("left")
    if not isinstance(left, dict) or left.get("kind") != "ScopedName":
        return None
    base = left.get("left")
    return _get_identifier_from_identifiername(base)


def _statement_text(node: Any) -> str:
    return _minify_ws(_collect_tokens(node))


_START_CALLS = {"start_item", "send_request", "uvm_send", "send"}
_FINISH_CALLS = {"finish_item", "wait_for_item_done", "item_done"}
_RANDOMIZE_CALLS = {"randomize"}


def _extract_decl_handle_and_type(data_decl: Dict[str, Any]) -> Optional[Tuple[str, str]]:
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
    handle = _extract_simple_identifier_text(d0.get("name"))
    if handle and type_name:
        return handle, type_name
    return None


def _walk_procedural(node: Any, handle_types: Dict[str, str], events: List[FlowEvent], cond_stack: Optional[List[str]] = None) -> None:
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
                    _walk_procedural(body, handle_types, events, cond_stack + [f"while({cond_txt})"])
                if cond_expr is not None:
                    _walk_expr_for_randomize(cond_expr, handle_types, events, cond_stack + [f"while({cond_txt})"])
                return

        if kind == "ConditionalStatement":
            _emit_macros_from_child_trivia(node, ["ifKeyword"], handle_types, events, cond_stack)
            predicate = node.get("predicate")
            cond_txt = _minify_ws(_collect_tokens(predicate)) if predicate is not None else "<if-cond>"
            if predicate is not None:
                _walk_expr_for_randomize(predicate, handle_types, events, cond_stack + [f"if({cond_txt})"])
            then_stmt = node.get("statement")
            else_clause = node.get("elseClause")
            if then_stmt is not None:
                _walk_procedural(then_stmt, handle_types, events, cond_stack + [f"if({cond_txt})"])
            if isinstance(else_clause, dict):
                else_stmt = else_clause.get("statement")
                if else_stmt is not None:
                    _walk_procedural(else_stmt, handle_types, events, cond_stack + [f"else({cond_txt})"])
            return

        if kind == "DataDeclaration":
            ht = _extract_decl_handle_and_type(node)
            if ht:
                handle, type_name = ht
                handle_types.setdefault(handle, type_name)
                events.append(FlowEvent(kind="declare", handle=handle, handle_type=type_name,
                                        text=_statement_text(node), path=_path_from_stack(cond_stack)))

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
                        events.append(FlowEvent(kind="create", handle=handle, handle_type=handle_types.get(handle),
                                                text=stmt_txt, path=_path_from_stack(cond_stack)))

            if isinstance(expr, dict) and expr.get("kind") == "InvocationExpression":
                call = _extract_invocation_name(expr)
                txt = stmt_txt
                if call in _START_CALLS:
                    handle = _extract_first_arg_identifier(expr)
                    events.append(FlowEvent(kind="start", handle=handle, handle_type=handle_types.get(handle),
                                            text=txt, path=_path_from_stack(cond_stack)))
                elif call in _FINISH_CALLS:
                    handle = _extract_first_arg_identifier(expr)
                    events.append(FlowEvent(kind="finish", handle=handle, handle_type=handle_types.get(handle),
                                            text=txt, path=_path_from_stack(cond_stack)))
                elif call in _RANDOMIZE_CALLS:
                    handle = _extract_first_arg_identifier(expr)
                    events.append(FlowEvent(kind="randomize", handle=handle, handle_type=handle_types.get(handle),
                                            text=txt, path=_path_from_stack(cond_stack),
                                            constraint_text=_extract_randomize_with_constraint(expr)))
                else:
                    events.append(FlowEvent(kind="call", handle=None, handle_type=None,
                                            text=txt, path=_path_from_stack(cond_stack)))
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
                    events.append(FlowEvent(kind="randomize", handle=handle, handle_type=handle_types.get(handle),
                                            text=txt, path=_path_from_stack(cond_stack),
                                            constraint_text=_extract_randomize_with_constraint(inv)))

        for v in node.values():
            _walk_procedural(v, handle_types, events, cond_stack)

    elif isinstance(node, list):
        for i in node:
            _walk_procedural(i, handle_types, events, cond_stack)


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
                            events.append(FlowEvent(kind="declare", handle=h, handle_type=t, text=f"{t} {h};", path=""))
                        _walk_procedural(x, handle_types, events, cond_stack=[])
                        flows.append(SequenceFlow(seq_class=seq_cls, item_type_param=seq_class_to_item.get(seq_cls),
                                                  proc=("task " if k == "TaskDeclaration" else "function ") + proc_name,
                                                  events=events))
            for v in x.values():
                walk(v, current_class=current_class)
        elif isinstance(x, list):
            for i in x:
                walk(i, current_class=current_class)

    walk(cst, current_class=None)
    return flows


def _extract_constraint_from_path(path: str) -> Optional[str]:
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


def _format_flows(flows: List[SequenceFlow], include_calls: bool = False) -> str:
    lines: List[str] = ["Sequence Item Flow:"]
    if not flows:
        lines.append("  <no sequence flows found>")
        return "\n".join(lines)

    flows_by_seq: Dict[str, List[SequenceFlow]] = {}
    for fl in flows:
        flows_by_seq.setdefault(fl.seq_class, []).append(fl)

    first = True
    for seq in sorted(flows_by_seq.keys()):
        if not first:
            lines.append("")
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


def _flows_to_json_dict(flows: List[SequenceFlow], include_calls: bool = False) -> Dict[str, Any]:
    grouped: Dict[str, Dict[str, Any]] = {}

    for fl in flows:
        seq_entry = grouped.setdefault(fl.seq_class, {
            "name": fl.seq_class,
            "base_type": "uvm_sequence",
            "item_type_param": fl.item_type_param,
            "procedures": [],
        })

        proc_entry: Dict[str, Any] = {
            "proc": fl.proc,
            "events": [],
        }

        inline_idx = 0
        for e in fl.events:
            if not include_calls and e.kind == "call":
                continue
            constraint_text = e.constraint_text
            if e.kind in ("randomize", "DO_WITH") and not constraint_text:
                constraint_text = _extract_constraint_from_path(e.path)

            event_obj: Dict[str, Any] = {
                "kind": e.kind,
                "handle": e.handle,
                "handle_type": e.handle_type,
                "text": e.text,
                "path": e.path,
                "constraint_text": constraint_text,
            }

            if constraint_text:
                inline_idx += 1
                event_obj["inline_constraint_name"] = f"macro_inline_{inline_idx}"

            proc_entry["events"].append(event_obj)

        seq_entry["procedures"].append(proc_entry)

    sequences = [grouped[name] for name in sorted(grouped.keys())]
    for seq in sequences:
        seq["procedures"] = sorted(seq["procedures"], key=lambda p: p["proc"])
    return {"sequences": sequences}


def write_summary(out_file: str, flows: List[SequenceFlow], include_calls: bool = False) -> None:
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(_format_flows(flows, include_calls=include_calls))
        f.write("\n")


def write_json(out_file: str, flows: List[SequenceFlow], include_calls: bool = False, pretty: bool = True) -> None:
    payload = _flows_to_json_dict(flows, include_calls=include_calls)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2 if pretty else None)
        f.write("\n")


def default_out_path(input_file: str, fmt: str) -> str:
    base = os.path.splitext(os.path.basename(input_file))[0]
    return f"{base}__seq_summary.{ 'json' if fmt == 'json' else 'txt' }"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="SystemVerilog file (.sv/.svh)")
    parser.add_argument("--out", default=None, help="Output file path")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--include-calls", action="store_true",
                        help="Include non-flow calls (everything that isn't declare/create/start/randomize/finish/macro)")
    args = parser.parse_args()

    flows = extract_sequence_flows_from_file(args.file)
    out_file = args.out if args.out else default_out_path(args.file, args.format)

    if args.format == "json":
        write_json(out_file, flows, include_calls=args.include_calls, pretty=args.pretty or True)
    else:
        write_summary(out_file, flows, include_calls=args.include_calls)

    print(f"Wrote {args.format} summary to {out_file}")


if __name__ == "__main__":
    main()
