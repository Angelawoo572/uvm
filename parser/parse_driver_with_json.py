import pyslang
import json
import argparse
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# High-Level Overview:
# This script analyzes a SystemVerilog (.sv / .svh) file containing UVM drivers and extracts the
# procedural flow of the run_phase task. It parses the file into a syntax tree with pyslang,
# converts that tree into CST JSON, then walks the JSON to:
#   1) Identify uvm_driver #(T) classes.
#   2) Find run_phase task declarations / definitions.
#   3) Recursively traverse procedural statements to detect:
#         - declarations
#         - sequencer handshakes (get_next_item / try_next_item / item_done / put_response)
#         - blocking and nonblocking assignments
#         - wait statements
#         - timing controls like @(posedge SFR.clk);
#         - branching / forever loop structure
#   4) Either:
#         - emit the original flat text summary with branch/loop paths, or
#         - emit a structured nested JSON tree preserving control-flow nesting.
#
# To run:
#   python parse_driver_with_json.py <file.sv>
#   python parse_driver_with_json.py <file.sv> --format json


# -----------------------------
# Data model
# -----------------------------
@dataclass
class DriverEvent:
    kind: str  # declare | seq_get | seq_done | assign | edge | wait | branch | loop
    text: str
    path: str = ""
    signal: Optional[str] = None
    edge: Optional[str] = None
    clock_expr: Optional[str] = None
    branch_cond: Optional[str] = None
    handle_type: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DriverFlow:
    driver_class: str
    item_type_param: Optional[str]
    proc: str
    events: List[DriverEvent] = field(default_factory=list)


# -----------------------------
# Path helpers
# -----------------------------
def _path_from_stack(cond_stack: List[str]) -> str:
    if not cond_stack:
        return ""
    return " & ".join(cond_stack)


# -----------------------------
# Token / text helpers
# -----------------------------
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


# -----------------------------
# Expression / type / predicate rendering
# -----------------------------
def _arg_list_to_text(arg_list: Any) -> str:
    if not isinstance(arg_list, dict):
        return ""

    params = arg_list.get("parameters")
    if not isinstance(params, list):
        return ""

    out: List[str] = []
    for p in params:
        if not isinstance(p, dict):
            continue
        if p.get("kind") == "Comma":
            continue
        expr = p.get("expr")
        out.append(_expr_to_text(expr))
    return ", ".join(x for x in out if x)


def _expr_to_text(node: Any) -> str:
    if not isinstance(node, dict):
        return ""

    kind = node.get("kind")

    if kind == "Identifier":
        return node.get("text", "")

    if kind == "IdentifierName":
        ident = node.get("identifier")
        return ident.get("text", "") if isinstance(ident, dict) else ""

    if kind == "MemberAccessExpression":
        left = _expr_to_text(node.get("value"))
        member = _expr_to_text(node.get("member"))
        return f"{left}.{member}".strip(".")

    if kind == "ElementSelectExpression":
        value = _expr_to_text(node.get("value"))
        selector = _expr_to_text(node.get("selector"))
        return f"{value}[{selector}]"

    if kind == "ClassName":
        ident = node.get("identifier")
        base = ident.get("text", "") if isinstance(ident, dict) else ""
        params = node.get("parameters")
        if isinstance(params, dict):
            plist = params.get("parameters")
            if isinstance(plist, list):
                parts: List[str] = []
                for p in plist:
                    if isinstance(p, dict) and p.get("kind") == "OrderedParamAssignment":
                        parts.append(_expr_to_text(p.get("expr")))
                if parts:
                    return f"{base}#({', '.join(parts)})"
        return base

    if kind == "ScopedName":
        left = _expr_to_text(node.get("left"))
        sep = node.get("separator", {}).get("text", "")
        right = _expr_to_text(node.get("right"))
        return f"{left}{sep}{right}"

    if kind == "SystemName":
        sid = node.get("systemIdentifier")
        return sid.get("text", "") if isinstance(sid, dict) else ""

    if kind == "SuperHandle":
        kw = node.get("keyword")
        return kw.get("text", "super") if isinstance(kw, dict) else "super"

    if kind == "ConstructorName":
        kw = node.get("keyword")
        return kw.get("text", "new") if isinstance(kw, dict) else "new"

    if kind == "IntegerLiteralExpression":
        lit = node.get("literal")
        return lit.get("text", "") if isinstance(lit, dict) else ""

    if kind == "StringLiteralExpression":
        lit = node.get("literal")
        return lit.get("text", "") if isinstance(lit, dict) else ""

    if kind == "NullLiteralExpression":
        lit = node.get("literal")
        return lit.get("text", "null") if isinstance(lit, dict) else "null"

    if kind == "SimplePropertyExpr":
        return _expr_to_text(node.get("expr"))

    if kind == "SimpleSequenceExpr":
        return _expr_to_text(node.get("expr"))

    if kind == "ConditionalPredicate":
        return _predicate_to_text(node)

    if kind == "ParenthesizedExpression":
        return f"({_expr_to_text(node.get('expr'))})"

    if kind == "ParenthesizedEventExpression":
        return f"({_expr_to_text(node.get('expr'))})"

    if kind == "SignalEventExpression":
        edge = node.get("edge", {}).get("text", "")
        expr = _expr_to_text(node.get("expr"))
        return f"{edge} {expr}".strip()

    if kind == "UnaryLogicalNotExpression":
        op = node.get("operatorToken", {}).get("text", "!")
        return f"{op}{_expr_to_text(node.get('operand'))}"

    if kind in (
        "EqualityExpression",
        "LogicalAndExpression",
        "LogicalOrExpression",
        "RelationalExpression",
        "AddExpression",
        "SubtractExpression",
        "MultiplyExpression",
    ):
        left = _expr_to_text(node.get("left"))
        op = node.get("operatorToken", {}).get("text", "")
        right = _expr_to_text(node.get("right"))
        return f"{left} {op} {right}".strip()

    if kind in ("AssignmentExpression", "NonblockingAssignmentExpression"):
        left = _expr_to_text(node.get("left"))
        op = node.get("operatorToken", {}).get("text", "=")
        right = _expr_to_text(node.get("right"))
        return f"{left} {op} {right}"

    if kind == "InvocationExpression":
        left = _expr_to_text(node.get("left"))
        args = _arg_list_to_text(node.get("arguments"))
        return f"{left}({args})"

    if kind == "NewClassExpression":
        scoped_new = _expr_to_text(node.get("scopedNew"))
        arg_list = _arg_list_to_text(node.get("argList"))
        return f"{scoped_new}({arg_list})"

    return _minify_ws(_collect_tokens(node))


def _type_to_text(node: Any) -> str:
    if not isinstance(node, dict):
        return ""

    kind = node.get("kind")

    if kind == "NamedType":
        return _expr_to_text(node.get("name"))

    if kind == "VirtualInterfaceType":
        name = _expr_to_text(node.get("name"))
        return f"virtual {name}".strip()

    if kind == "StringType":
        return node.get("keyword", {}).get("text", "string")

    if kind == "VoidType":
        return node.get("keyword", {}).get("text", "void")

    if kind == "ImplicitType":
        return ""

    return _minify_ws(_collect_tokens(node))


def _predicate_to_text(pred: Any) -> str:
    if not isinstance(pred, dict):
        return ""

    if pred.get("kind") == "ConditionalPredicate":
        conds = pred.get("conditions")
        if isinstance(conds, list):
            parts: List[str] = []
            for c in conds:
                if isinstance(c, dict):
                    expr = c.get("expr")
                    if expr is not None:
                        parts.append(_expr_to_text(expr))
            return ", ".join(p for p in parts if p)

    return _expr_to_text(pred)


# -----------------------------
# Identifier / prototype helpers
# -----------------------------
def _extract_simple_identifier_text(node: Any) -> Optional[str]:
    if not isinstance(node, dict):
        return None
    txt = node.get("text")
    return txt if isinstance(txt, str) else None


def _extract_scoped_name_text(node: Any) -> Optional[str]:
    if not isinstance(node, dict):
        return None
    if node.get("kind") != "ScopedName":
        return None
    return _expr_to_text(node)


def _get_name_from_proto_name(node: Any) -> Optional[str]:
    if not isinstance(node, dict):
        return None

    kind = node.get("kind")
    if kind == "ScopedName":
        return None
    if kind in ("IdentifierName", "ConstructorName"):
        return _expr_to_text(node)

    txt = node.get("text")
    return txt if isinstance(txt, str) else None


def _direction_to_text(direction: Any) -> str:
    if not isinstance(direction, dict):
        return ""
    txt = direction.get("text")
    if isinstance(txt, str) and txt:
        return txt
    kind = direction.get("kind", "")
    return kind.replace("Keyword", "").lower() if kind else ""


def _extract_default_value(node: Any) -> str:
    if not isinstance(node, dict):
        return ""

    for key in ("defaultValue", "initializer", "expr", "value"):
        val = node.get(key)
        txt = _expr_to_text(val)
        if txt:
            return txt
    return ""


def _extract_arg_from_port_node(port: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if not isinstance(port, dict) or port.get("kind") == "Comma":
        return out

    # Common pyslang shapes:
    #   FunctionPort / TaskPort:
    #       dataType -> NamedType / ...
    #       declarator -> Declarator(name=Identifier, initializer=...)
    #   FormalArgument / TfPortItem / PortDeclaration / AnsiPortDeclaration:
    #       type -> ...
    #       name / declarators / declarations / items
    direction_text = _direction_to_text(port.get("direction"))
    data_type = _type_to_text(port.get("dataType")) or _type_to_text(port.get("type"))

    # Exact FunctionPort / TaskPort structure.
    declarator = port.get("declarator")
    if isinstance(declarator, dict):
        name = _expr_to_text(declarator.get("name"))
        if name:
            arg: Dict[str, str] = {"name": name, "type": data_type or "<implicit>"}
            if direction_text:
                arg["direction"] = direction_text
            default_txt = _extract_default_value(declarator) or _extract_default_value(port)
            if default_txt:
                arg["default"] = default_txt
            out.append(arg)
            return out

    # Direct name on the port node.
    direct_name = _expr_to_text(port.get("name"))
    if direct_name:
        arg: Dict[str, str] = {"name": direct_name, "type": data_type or "<implicit>"}
        if direction_text:
            arg["direction"] = direction_text
        default_txt = _extract_default_value(port)
        if default_txt:
            arg["default"] = default_txt
        out.append(arg)
        return out

    # Multi-declarator fallbacks.
    for key in ("declarators", "declarations", "items", "ports"):
        vals = port.get(key)
        if not isinstance(vals, list):
            continue
        for item in vals:
            if not isinstance(item, dict) or item.get("kind") == "Comma":
                continue

            item_decl = item.get("declarator")
            name = ""
            if isinstance(item_decl, dict):
                name = _expr_to_text(item_decl.get("name"))
            if not name:
                name = _expr_to_text(item.get("name"))
            if not name:
                name = _expr_to_text(item.get("declarator"))
            if not name:
                continue

            arg = {
                "name": name,
                "type": data_type or _type_to_text(item.get("dataType")) or _type_to_text(item.get("type")) or "<implicit>",
            }
            if direction_text:
                arg["direction"] = direction_text
            default_txt = (
                _extract_default_value(item_decl) if isinstance(item_decl, dict) else ""
            ) or _extract_default_value(item)
            if default_txt:
                arg["default"] = default_txt
            out.append(arg)
        if out:
            return out

    return out


def _extract_task_args(proto: Dict[str, Any]) -> List[Dict[str, str]]:
    args_out: List[Dict[str, str]] = []

    def walk_ports(node: Any) -> None:
        nonlocal args_out
        if isinstance(node, list):
            for item in node:
                walk_ports(item)
            return
        if not isinstance(node, dict):
            return

        if node.get("kind") in (
            "FunctionPort",
            "TaskPort",
            "FormalArgument",
            "TfPortItem",
            "PortDeclaration",
            "AnsiPortDeclaration",
        ):
            args_out.extend(_extract_arg_from_port_node(node))
            return

        for key in ("ports", "items", "declarations", "declarators"):
            child = node.get(key)
            if isinstance(child, (list, dict)):
                walk_ports(child)

    # pyslang task / function prototypes often use portList rather than ports.
    for key in ("portList", "ports"):
        ports = proto.get(key)
        if isinstance(ports, (list, dict)):
            walk_ports(ports)
            if args_out:
                break

    # Fallback: some CST versions may store arguments directly on the prototype.
    if not args_out:
        walk_ports(proto)

    # Deduplicate while preserving order.
    deduped: List[Dict[str, str]] = []
    seen = set()
    for arg in args_out:
        key = (arg.get("name"), arg.get("type"), arg.get("direction"), arg.get("default"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(arg)
    return deduped


# -----------------------------
# Driver class discovery
# -----------------------------
def _extract_uvm_driver_param_from_classdecl(class_decl: Dict[str, Any]) -> Optional[str]:
    """
    For:
      class my_driver extends uvm_driver #(my_txn);
    extract "my_txn".
    """
    ext = class_decl.get("extendsClause")
    if not isinstance(ext, dict):
        return None

    base = ext.get("baseName")
    if not isinstance(base, dict):
        return None

    base_name = None
    if base.get("kind") == "ClassName":
        ident = base.get("identifier")
        if isinstance(ident, dict):
            base_name = ident.get("text")

    if base_name != "uvm_driver":
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
    txt = _expr_to_text(expr)
    return txt if txt else None


def _find_driver_classes(cst: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Returns { driver_class_name : item_type_param } for classes extending uvm_driver #(T)."""
    driver_class_to_item: Dict[str, Optional[str]] = {}

    def walk(x: Any):
        if isinstance(x, dict):
            if x.get("kind") == "ClassDeclaration":
                cls = _extract_simple_identifier_text(x.get("name"))
                if cls:
                    item_param = _extract_uvm_driver_param_from_classdecl(x)
                    if item_param is not None:
                        driver_class_to_item[cls] = item_param
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(cst)
    return driver_class_to_item


# -----------------------------
# Declarations
# -----------------------------
def _extract_decl_handle_and_type(data_decl: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    if data_decl.get("kind") != "DataDeclaration":
        return None

    type_name = _type_to_text(data_decl.get("type"))

    decls = data_decl.get("declarators")
    if not isinstance(decls, list) or not decls:
        return None

    d0 = decls[0]
    if not isinstance(d0, dict):
        return None

    handle = _expr_to_text(d0.get("name"))

    if handle and type_name:
        return handle, type_name
    return None


def _collect_class_handles(class_decl: Dict[str, Any]) -> Dict[str, str]:
    """
    Look for class-scope DataDeclaration nodes.
    Returns { handle_name -> type_name }.
    Does not recurse into methods.
    """
    handles: Dict[str, str] = {}

    def walk(node: Any):
        if isinstance(node, dict):
            k = node.get("kind")

            # Don't descend into methods
            if k in ("ClassMethodDeclaration", "TaskDeclaration", "FunctionDeclaration", "ClassMethodPrototype"):
                return

            if k == "ClassPropertyDeclaration":
                decl = node.get("declaration")
                if isinstance(decl, dict) and decl.get("kind") == "DataDeclaration":
                    ht = _extract_decl_handle_and_type(decl)
                    if ht:
                        handle, type_name = ht
                        handles.setdefault(handle, type_name)

            elif k == "DataDeclaration":
                ht = _extract_decl_handle_and_type(node)
                if ht:
                    handle, type_name = ht
                    handles.setdefault(handle, type_name)

            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(class_decl)
    return handles


# -----------------------------
# Call / assignment helpers
# -----------------------------
def _extract_invocation_name(inv: Dict[str, Any]) -> Optional[str]:
    left = inv.get("left")
    if not isinstance(left, dict):
        return None

    kind = left.get("kind")

    if kind == "IdentifierName":
        txt = _expr_to_text(left)
        return txt if txt else None

    if kind == "MemberAccessExpression":
        txt = _expr_to_text(left.get("member"))
        if txt:
            return txt
        full = _expr_to_text(left)
        return full.rsplit('.', 1)[-1] if full else None

    if kind == "ScopedName":
        txt = _expr_to_text(left.get("right"))
        if txt:
            return txt
        full = _expr_to_text(left)
        return full.rsplit('::', 1)[-1] if full else None

    if kind == "SystemName":
        txt = _expr_to_text(left)
        return txt if txt else None

    full = _expr_to_text(left)
    if full:
        if '.' in full:
            return full.rsplit('.', 1)[-1]
        if '::' in full:
            return full.rsplit('::', 1)[-1]
        return full

    return None


def _extract_first_arg_identifier(inv: Dict[str, Any]) -> Optional[str]:
    args = inv.get("arguments")
    if not isinstance(args, dict):
        return None

    params = args.get("parameters")
    if not isinstance(params, list):
        return None

    for p in params:
        if not isinstance(p, dict):
            continue
        if p.get("kind") == "Comma":
            continue
        expr = p.get("expr")
        txt = _expr_to_text(expr)
        return txt if txt else None

    return None


def _extract_assignment_sides(expr: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
    if expr.get("kind") not in ("AssignmentExpression", "NonblockingAssignmentExpression"):
        return None

    left = _expr_to_text(expr.get("left"))
    op = expr.get("operatorToken", {}).get("text", "=")
    right = _expr_to_text(expr.get("right"))
    return left, op, right


def _invocation_to_method_call(expr: Dict[str, Any]) -> Dict[str, Any]:
    left = expr.get("left")
    args = []
    arg_dict = expr.get("arguments")
    if isinstance(arg_dict, dict):
        params = arg_dict.get("parameters", [])
        for p in params:
            if isinstance(p, dict) and p.get("kind") != "Comma":
                args.append(_expr_to_text(p.get("expr")))

    if isinstance(left, dict) and left.get("kind") == "MemberAccessExpression":
        caller = _expr_to_text(left.get("value"))
        method = _expr_to_text(left.get("member"))
        if method:
            return {
                "type": "method_call",
                "caller": caller,
                "method": method,
                "arguments": args,
            }

    name = _expr_to_text(left)
    if name and "." in name:
        caller, method = name.rsplit('.', 1)
        return {
            "type": "method_call",
            "caller": caller,
            "method": method,
            "arguments": args,
        }

    return {
        "type": "function_call",
        "name": name,
        "arguments": args,
    }


# -----------------------------
# Timing / wait helpers
# -----------------------------
def _extract_wait_info(node: Dict[str, Any]) -> Optional[str]:
    if node.get("kind") != "WaitStatement":
        return None
    return _expr_to_text(node.get("expr"))


def _extract_event_control_info(timing_control: Any) -> Optional[Tuple[str, str]]:
    """
    For:
      TimingControlStatement
        timingControl: EventControlWithExpression
          expr: ParenthesizedEventExpression
            expr: SignalEventExpression
              edge: PosEdgeKeyword / NegEdgeKeyword
              expr: ScopedName(...)
    Return: (edge, signal_expr)
    """
    if not isinstance(timing_control, dict):
        return None

    if timing_control.get("kind") != "EventControlWithExpression":
        return None

    expr = timing_control.get("expr")
    if not isinstance(expr, dict) or expr.get("kind") != "ParenthesizedEventExpression":
        return None

    inner = expr.get("expr")
    if not isinstance(inner, dict) or inner.get("kind") != "SignalEventExpression":
        return None

    edge = inner.get("edge", {}).get("text", "")
    sig = _expr_to_text(inner.get("expr"))

    if edge and sig:
        return edge, sig
    return None


# -----------------------------
# Driver-specific call categories
# -----------------------------
_SEQ_GET_CALLS = {"get_next_item", "try_next_item", "get"}
_SEQ_DONE_CALLS = {"item_done"}
_SEQ_RSP_CALLS = {"put_response"}


# -----------------------------
# Recursive procedural traversal (legacy flat mode)
# -----------------------------
def _walk_driver_procedural(
    node: Any,
    handle_types: Dict[str, str],
    events: List[DriverEvent],
    cond_stack: Optional[List[str]] = None,
) -> None:
    if cond_stack is None:
        cond_stack = []

    if isinstance(node, dict):
        kind = node.get("kind")

        if kind == "SequentialBlockStatement":
            items = node.get("items")
            if isinstance(items, list):
                for item in items:
                    _walk_driver_procedural(item, handle_types, events, cond_stack)
            return

        if kind in ("TaskDeclaration", "FunctionDeclaration"):
            items = node.get("items")
            if isinstance(items, list):
                for item in items:
                    _walk_driver_procedural(item, handle_types, events, cond_stack)
            return

        if kind == "ForeverStatement":
            events.append(
                DriverEvent(
                    kind="loop",
                    text="forever",
                    path=_path_from_stack(cond_stack),
                )
            )
            body = node.get("statement")
            if body is not None:
                _walk_driver_procedural(body, handle_types, events, cond_stack + ["forever"])
            return

        if kind == "ConditionalStatement":
            predicate = node.get("predicate")
            cond_txt = _predicate_to_text(predicate) or "<if-cond>"

            events.append(
                DriverEvent(
                    kind="branch",
                    text=f"if ({cond_txt})",
                    branch_cond=cond_txt,
                    path=_path_from_stack(cond_stack),
                )
            )

            then_stmt = node.get("statement")
            if then_stmt is not None:
                _walk_driver_procedural(
                    then_stmt,
                    handle_types,
                    events,
                    cond_stack + [f"then[{cond_txt}]"],
                )

            else_clause = node.get("elseClause")
            if isinstance(else_clause, dict):
                events.append(
                    DriverEvent(
                        kind="branch",
                        text=f"else of if ({cond_txt})",
                        branch_cond=cond_txt,
                        path=_path_from_stack(cond_stack),
                    )
                )

                else_stmt = else_clause.get("clause")
                if else_stmt is not None:
                    _walk_driver_procedural(
                        else_stmt,
                        handle_types,
                        events,
                        cond_stack + [f"else[{cond_txt}]"],
                    )
            return

        if kind == "DataDeclaration":
            ht = _extract_decl_handle_and_type(node)
            if ht:
                handle, type_name = ht
                handle_types.setdefault(handle, type_name)
                events.append(
                    DriverEvent(
                        kind="declare",
                        text=f"{type_name} {handle};",
                        signal=handle,
                        handle_type=type_name,
                        path=_path_from_stack(cond_stack),
                    )
                )
            return

        if kind == "WaitStatement":
            cond = _extract_wait_info(node)
            cond_txt = cond if cond is not None else "<wait-cond>"
            events.append(
                DriverEvent(
                    kind="wait",
                    text=f"wait({cond_txt});",
                    branch_cond=cond,
                    path=_path_from_stack(cond_stack),
                )
            )
            return

        if kind == "TimingControlStatement":
            info = _extract_event_control_info(node.get("timingControl"))
            if info:
                edge, clkexpr = info
                events.append(
                    DriverEvent(
                        kind="edge",
                        text=f"@({edge} {clkexpr});",
                        edge=edge,
                        clock_expr=clkexpr,
                        path=_path_from_stack(cond_stack),
                    )
                )
            return

        if kind == "ExpressionStatement":
            expr = node.get("expr")
            if isinstance(expr, dict):
                expr_kind = expr.get("kind")

                if expr_kind in ("AssignmentExpression", "NonblockingAssignmentExpression"):
                    asn = _extract_assignment_sides(expr)
                    if asn:
                        left, op, right = asn
                        events.append(
                            DriverEvent(
                                kind="assign",
                                text=f"{left} {op} {right};",
                                signal=left,
                                path=_path_from_stack(cond_stack),
                                extra={"op": op, "rhs": right},
                            )
                        )
                    return

                if expr_kind == "InvocationExpression":
                    call = _extract_invocation_name(expr)
                    arg0 = _extract_first_arg_identifier(expr)

                    if call in _SEQ_GET_CALLS:
                        events.append(
                            DriverEvent(
                                kind="seq_get",
                                text=_expr_to_text(expr) + ";",
                                signal=arg0,
                                handle_type=handle_types.get(arg0),
                                path=_path_from_stack(cond_stack),
                                extra={"call": call},
                            )
                        )
                    elif call in _SEQ_DONE_CALLS:
                        events.append(
                            DriverEvent(
                                kind="seq_done",
                                text=_expr_to_text(expr) + ";",
                                path=_path_from_stack(cond_stack),
                                extra={"call": call},
                            )
                        )
                    elif call in _SEQ_RSP_CALLS:
                        events.append(
                            DriverEvent(
                                kind="seq_done",
                                text=_expr_to_text(expr) + ";",
                                signal=arg0,
                                handle_type=handle_types.get(arg0),
                                path=_path_from_stack(cond_stack),
                                extra={"call": call, "response": True},
                            )
                        )
                    return
            return

        for v in node.values():
            _walk_driver_procedural(v, handle_types, events, cond_stack)

    elif isinstance(node, list):
        for i in node:
            _walk_driver_procedural(i, handle_types, events, cond_stack)


# -----------------------------
# Recursive procedural traversal (nested JSON mode)
# -----------------------------
def _build_stmt_list(node: Any, handle_types: Dict[str, str]) -> List[Dict[str, Any]]:
    if not isinstance(node, dict):
        if isinstance(node, list):
            out: List[Dict[str, Any]] = []
            for item in node:
                out.extend(_build_stmt_list(item, handle_types))
            return out
        return []

    kind = node.get("kind")
    out: List[Dict[str, Any]] = []

    if kind == "SequentialBlockStatement":
        items = node.get("items", [])
        for item in items:
            out.extend(_build_stmt_list(item, handle_types))
        return out

    if kind in ("TaskDeclaration", "FunctionDeclaration"):
        items = node.get("items", [])
        for item in items:
            out.extend(_build_stmt_list(item, handle_types))
        return out

    if kind == "DataDeclaration":
        ht = _extract_decl_handle_and_type(node)
        if ht:
            name, data_type = ht
            handle_types.setdefault(name, data_type)
            out.append(
                {
                    "type": "variable_declaration",
                    "data_type": data_type,
                    "name": name,
                }
            )
        return out

    if kind == "ForeverStatement":
        body = node.get("statement")
        out.append(
            {
                "type": "loop",
                "loop_type": "forever",
                "children": _build_stmt_list(body, handle_types) if body else [],
            }
        )
        return out

    if kind == "ConditionalStatement":
        cond_txt = _predicate_to_text(node.get("predicate")) or "<if-cond>"
        then_stmt = node.get("statement")
        else_clause = node.get("elseClause")

        obj: Dict[str, Any] = {
            "type": "if_else" if isinstance(else_clause, dict) else "if",
            "condition": cond_txt,
            "true_branch": _build_stmt_list(then_stmt, handle_types) if then_stmt else [],
        }

        if isinstance(else_clause, dict):
            obj["false_branch"] = _build_stmt_list(else_clause.get("clause"), handle_types)

        out.append(obj)
        return out

    if kind == "WaitStatement":
        cond = _extract_wait_info(node) or "<wait-cond>"
        out.append(
            {
                "type": "wait_statement",
                "condition": cond,
            }
        )
        return out

    if kind == "TimingControlStatement":
        info = _extract_event_control_info(node.get("timingControl"))
        if info:
            edge, sig = info
            out.append(
                {
                    "type": "event_control",
                    "event": f"{edge} {sig}",
                }
            )
        return out

    if kind == "ExpressionStatement":
        expr = node.get("expr")
        if not isinstance(expr, dict):
            return out

        expr_kind = expr.get("kind")

        if expr_kind in ("AssignmentExpression", "NonblockingAssignmentExpression"):
            asn = _extract_assignment_sides(expr)
            if asn:
                lhs, op, rhs = asn
                out.append(
                    {
                        "type": "assignment",
                        "operator": op,
                        "lhs": lhs,
                        "rhs": rhs,
                    }
                )
            return out

        if expr_kind == "InvocationExpression":
            call_obj = _invocation_to_method_call(expr)
            call_name = _extract_invocation_name(expr)
            if call_name in _SEQ_GET_CALLS:
                call_obj["semantic_type"] = "seq_get"
            elif call_name in _SEQ_DONE_CALLS:
                call_obj["semantic_type"] = "seq_done"
            elif call_name in _SEQ_RSP_CALLS:
                call_obj["semantic_type"] = "seq_rsp"
            out.append(call_obj)
            return out

        return out

    for v in node.values():
        out.extend(_build_stmt_list(v, handle_types))

    return out


# -----------------------------
# Entry point: extract flows
# -----------------------------
def extract_driver_flows_from_file(filepath: str) -> List[DriverFlow]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    driver_class_to_item = _find_driver_classes(cst)
    flows: List[DriverFlow] = []
    class_handles: Dict[str, Dict[str, str]] = {}

    def walk(x: Any, current_class: Optional[str] = None):
        if isinstance(x, dict):
            k = x.get("kind")

            if k == "ClassDeclaration":
                cls_name = _extract_simple_identifier_text(x.get("name"))
                if cls_name and cls_name in driver_class_to_item:
                    class_handles[cls_name] = _collect_class_handles(x)

                for v in x.values():
                    walk(v, current_class=cls_name)
                return

            if k in ("TaskDeclaration", "FunctionDeclaration"):
                proto = x.get("prototype")
                if isinstance(proto, dict):
                    name_node = proto.get("name")

                    scoped = _extract_scoped_name_text(name_node)
                    drv_cls: Optional[str] = None
                    proc_name: Optional[str] = None

                    if scoped and "::" in scoped:
                        drv_cls, proc_name = [p.strip() for p in scoped.split("::", 1)]
                    else:
                        if current_class is not None:
                            drv_cls = current_class
                            proc_name = _get_name_from_proto_name(name_node)

                    if drv_cls and proc_name and drv_cls in driver_class_to_item and proc_name == "run_phase":
                        handle_types: Dict[str, str] = dict(class_handles.get(drv_cls, {}))
                        events: List[DriverEvent] = []

                        for h, t in class_handles.get(drv_cls, {}).items():
                            events.append(
                                DriverEvent(
                                    kind="declare",
                                    text=f"{t} {h};",
                                    signal=h,
                                    handle_type=t,
                                    path="",
                                )
                            )

                        _walk_driver_procedural(x, handle_types, events, cond_stack=[])

                        flows.append(
                            DriverFlow(
                                driver_class=drv_cls,
                                item_type_param=driver_class_to_item.get(drv_cls),
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


# -----------------------------
# Entry point: extract structured components
# -----------------------------
def extract_driver_components_from_file(filepath: str) -> List[Dict[str, Any]]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    driver_class_to_item = _find_driver_classes(cst)
    class_handles: Dict[str, Dict[str, str]] = {}
    components: Dict[str, Dict[str, Any]] = {}

    def ensure_component(class_name: str) -> Dict[str, Any]:
        if class_name not in components:
            members: List[Dict[str, Any]] = []
            for handle, type_name in class_handles.get(class_name, {}).items():
                if type_name.startswith("virtual "):
                    members.append(
                        {
                            "type": "virtual_interface",
                            "name": handle,
                            "interface_type": type_name.replace("virtual ", "", 1),
                        }
                    )
                else:
                    members.append(
                        {
                            "type": "variable",
                            "name": handle,
                            "data_type": type_name,
                        }
                    )

            components[class_name] = {
                "name": class_name,
                "base_type": "uvm_driver",
                "parameters": [driver_class_to_item.get(class_name)] if driver_class_to_item.get(class_name) else [],
                "members": members,
            }
        return components[class_name]

    def walk(x: Any, current_class: Optional[str] = None):
        if isinstance(x, dict):
            k = x.get("kind")

            if k == "ClassDeclaration":
                cls_name = _extract_simple_identifier_text(x.get("name"))
                if cls_name and cls_name in driver_class_to_item:
                    class_handles[cls_name] = _collect_class_handles(x)
                    ensure_component(cls_name)

                for v in x.values():
                    walk(v, current_class=cls_name)
                return

            if k in ("TaskDeclaration", "FunctionDeclaration"):
                proto = x.get("prototype")
                if isinstance(proto, dict):
                    name_node = proto.get("name")
                    scoped = _extract_scoped_name_text(name_node)
                    drv_cls: Optional[str] = None
                    proc_name: Optional[str] = None

                    if scoped and "::" in scoped:
                        drv_cls, proc_name = [p.strip() for p in scoped.split("::", 1)]
                    else:
                        if current_class is not None:
                            drv_cls = current_class
                            proc_name = _get_name_from_proto_name(name_node)

                    if drv_cls and proc_name and drv_cls in driver_class_to_item:
                        component = ensure_component(drv_cls)
                        handle_types: Dict[str, str] = dict(class_handles.get(drv_cls, {}))
                        task_entry = {
                            "type": "task" if k == "TaskDeclaration" else "function",
                            "name": proc_name,
                            "arguments": _extract_task_args(proto),
                            "body": _build_stmt_list(x, handle_types),
                        }

                        existing = None
                        for member in component["members"]:
                            if member.get("type") == task_entry["type"] and member.get("name") == task_entry["name"]:
                                existing = member
                                break

                        if existing is None:
                            component["members"].append(task_entry)
                        else:
                            if not existing.get("arguments") and task_entry.get("arguments"):
                                existing["arguments"] = task_entry["arguments"]
                            if (not existing.get("body")) and task_entry.get("body"):
                                existing["body"] = task_entry["body"]

            for v in x.values():
                walk(v, current_class=current_class)
        elif isinstance(x, list):
            for i in x:
                walk(i, current_class=current_class)

    walk(cst, current_class=None)
    return [{"component": comp} for _, comp in sorted(components.items())]


# -----------------------------
# Output formatting
# -----------------------------
def _format_flows(flows: List[DriverFlow]) -> str:
    lines: List[str] = []
    lines.append("Driver Flow:")

    if not flows:
        lines.append("  <no driver run_phase flows found>")
        return "\n".join(lines)

    flows_by_driver: Dict[str, List[DriverFlow]] = {}
    for fl in flows:
        flows_by_driver.setdefault(fl.driver_class, []).append(fl)

    for drv in sorted(flows_by_driver.keys()):
        item = flows_by_driver[drv][0].item_type_param or "<unknown_item_type>"
        lines.append(f"  {drv} (uvm_driver#({item}))")

        for fl in sorted(flows_by_driver[drv], key=lambda x: x.proc):
            lines.append(f"    {fl.proc}:")

            for e in fl.events:
                path_suffix = f"  [path: {e.path}]" if e.path else ""

                if e.kind == "edge":
                    clk = f" {e.clock_expr}" if e.clock_expr else ""
                    lines.append(f"      [{e.kind}] {e.edge}{clk}: {e.text}{path_suffix}")
                elif e.signal:
                    t = f" type={e.handle_type}" if e.handle_type else ""
                    lines.append(f"      [{e.kind}] {e.signal}{t}: {e.text}{path_suffix}")
                else:
                    lines.append(f"      [{e.kind}] {e.text}{path_suffix}")

    return "\n".join(lines)


def write_summary(out_file: str, flows: List[DriverFlow]) -> None:
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(_format_flows(flows))
        f.write("\n")


def write_json_output(out_file: str, components: List[Dict[str, Any]]) -> None:
    payload: Any
    if len(components) == 1:
        payload = components[0]
    else:
        payload = {"components": [entry["component"] for entry in components]}

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


# -----------------------------
# CLI
# -----------------------------
def default_out_path(input_file: str, output_format: str) -> str:
    base = os.path.splitext(os.path.basename(input_file))[0]
    suffix = ".json" if output_format == "json" else ".txt"
    stem_suffix = "_summary_json" if output_format == "json" else "_summary"
    return f"{base}{stem_suffix}{suffix}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="SystemVerilog file (.sv/.svh)")
    parser.add_argument("--out", default=None, help="Output file path")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format: original flat text summary or nested JSON",
    )
    args = parser.parse_args()

    out_file = args.out if args.out else default_out_path(args.file, args.format)

    if args.format == "json":
        components = extract_driver_components_from_file(args.file)
        write_json_output(out_file, components)
        print(f"Wrote driver JSON summary to {out_file}")
    else:
        flows = extract_driver_flows_from_file(args.file)
        write_summary(out_file, flows)
        print(f"Wrote driver flow summary to {out_file}")


if __name__ == "__main__":
    main()
