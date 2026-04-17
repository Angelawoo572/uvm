import pyslang
import json
import argparse
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# High-Level Overview:
# This script analyzes a SystemVerilog (.sv / .svh) file containing UVM monitors and extracts the
# procedural flow of the build_phase and run_phase methods. It parses the file into a syntax tree
# with pyslang, converts that tree into CST JSON, then walks the JSON to:
#   1) Identify classes extending uvm_monitor.
#   2) Find build_phase / run_phase task or function declarations / definitions.
#   3) Recursively traverse procedural statements to detect:
#         - declarations
#         - config_db gets
#         - factory creates / constructor calls
#         - analysis port writes
#         - blocking and nonblocking assignments
#         - wait statements
#         - timing controls like @(posedge clk) or @(vif.mon_cb)
#         - branching / forever loop structure
#   4) Either:
#         - emit a flat text summary with branch/loop paths, or
#         - emit a structured nested JSON tree preserving control-flow nesting.
#
# To run:
#   python parse_monitor_with_json.py <file.sv>
#   python parse_monitor_with_json.py <file.sv> --format json


# -----------------------------
# Data model
# -----------------------------
@dataclass
class MonitorEvent:
    kind: str  # declare | assign | edge | wait | branch | loop | call
    text: str
    path: str = ""
    signal: Optional[str] = None
    edge: Optional[str] = None
    clock_expr: Optional[str] = None
    branch_cond: Optional[str] = None
    handle_type: Optional[str] = None
    semantic_type: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitorFlow:
    monitor_class: str
    proc: str
    events: List[MonitorEvent] = field(default_factory=list)


MONITOR_PHASE_PROCS = {"build_phase", "run_phase"}


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
                    if isinstance(p, dict) and p.get("kind") in ("OrderedParamAssignment", "NamedParamAssignment"):
                        expr = p.get("expr")
                        if expr is not None:
                            parts.append(_expr_to_text(expr))
                        else:
                            parts.append(_minify_ws(_collect_tokens(p)))
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
        # Keep interface parameters, e.g.
        # virtual itf #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH))
        txt = _minify_ws(_collect_tokens(node))
        return txt if txt else "virtual " + _expr_to_text(node.get("name"))

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
        txt = _expr_to_text(node.get("right"))
        return txt if txt else None

    txt = _expr_to_text(node)
    return txt if txt else None


def _direction_to_text(direction: Any) -> str:
    if isinstance(direction, dict):
        txt = direction.get("text")
        if isinstance(txt, str):
            return txt
    if isinstance(direction, str):
        return direction
    return ""


def _extract_default_value(node: Any) -> str:
    if not isinstance(node, dict):
        return ""

    init = node.get("initializer")
    if isinstance(init, dict):
        expr = init.get("expr") if init.get("kind") == "EqualsValueClause" else None
        txt = _expr_to_text(expr if isinstance(expr, dict) else init)
        if txt:
            return txt

    for key in ("default", "expr"):
        val = node.get(key)
        if isinstance(val, dict):
            txt = _expr_to_text(val)
            if txt:
                return txt
    return ""


def _extract_arg_from_port_node(port: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []

    data_type = _type_to_text(port.get("type") or port.get("dataType"))
    direction_text = _direction_to_text(port.get("direction"))

    direct_name = _expr_to_text(port.get("name"))
    if not direct_name and isinstance(port.get("declarator"), dict):
        direct_name = _expr_to_text(port["declarator"].get("name"))
    if direct_name:
        arg: Dict[str, str] = {"name": direct_name, "type": data_type or "<implicit>"}
        if direction_text:
            arg["direction"] = direction_text
        default_txt = _extract_default_value(port.get("declarator")) if isinstance(port.get("declarator"), dict) else ""
        if not default_txt:
            default_txt = _extract_default_value(port)
        if default_txt:
            arg["default"] = default_txt
        out.append(arg)
        return out

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

    for key in ("portList", "ports"):
        ports = proto.get(key)
        if isinstance(ports, (list, dict)):
            walk_ports(ports)
            if args_out:
                break

    if not args_out:
        walk_ports(proto)

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
# Monitor class discovery
# -----------------------------
def _extract_monitor_class_parameters(class_decl: Dict[str, Any]) -> List[str]:
    params_node = class_decl.get("parameters")
    if not isinstance(params_node, dict):
        return []

    params = params_node.get("declarations") or params_node.get("parameters")
    if not isinstance(params, list):
        return []

    out: List[str] = []
    for p in params:
        if not isinstance(p, dict) or p.get("kind") == "Comma":
            continue
        if p.get("kind") == "ParameterDeclaration":
            ptype = _type_to_text(p.get("type"))
            decls = p.get("declarators")
            if isinstance(decls, list):
                for d in decls:
                    if not isinstance(d, dict) or d.get("kind") == "Comma":
                        continue
                    name = _expr_to_text(d.get("name"))
                    init = _extract_default_value(d)
                    txt = f"{ptype} {name}".strip()
                    if init:
                        txt += f"={init}"
                    if txt:
                        out.append(txt)
                continue
        txt = _minify_ws(_collect_tokens(p))
        if txt:
            out.append(txt)
    return out


def _is_uvm_monitor_class(class_decl: Dict[str, Any]) -> bool:
    ext = class_decl.get("extendsClause")
    if not isinstance(ext, dict):
        return False

    base = ext.get("baseName")
    if not isinstance(base, dict):
        return False

    # pyslang may encode the extends target as IdentifierName, ClassName,
    # or other name-like nodes depending on context / version.
    base_name = _expr_to_text(base)
    if not base_name:
        return False

    # Be tolerant of parameterization or extra qualification.
    return base_name.split("#", 1)[0].strip() == "uvm_monitor"


def _find_monitor_classes(cst: Dict[str, Any]) -> Dict[str, List[str]]:
    """Returns { monitor_class_name : [class parameter text, ...] } for classes extending uvm_monitor."""
    monitor_class_to_params: Dict[str, List[str]] = {}

    def walk(x: Any):
        if isinstance(x, dict):
            if x.get("kind") == "ClassDeclaration":
                cls = _extract_simple_identifier_text(x.get("name"))
                if cls and _is_uvm_monitor_class(x):
                    monitor_class_to_params[cls] = _extract_monitor_class_parameters(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(cst)
    return monitor_class_to_params


# -----------------------------
# Declarations
# -----------------------------
def _extract_declarator_name_and_initializer(declarator: Any) -> Tuple[str, str]:
    if not isinstance(declarator, dict):
        return "", ""

    name = _expr_to_text(declarator.get("name"))
    init = _extract_default_value(declarator)
    return name, init


def _extract_decl_entries(data_decl: Dict[str, Any]) -> List[Dict[str, str]]:
    if data_decl.get("kind") != "DataDeclaration":
        return []

    type_name = _type_to_text(data_decl.get("type"))
    decls = data_decl.get("declarators")
    if not isinstance(decls, list) or not decls:
        return []

    out: List[Dict[str, str]] = []
    for d in decls:
        if not isinstance(d, dict) or d.get("kind") == "Comma":
            continue
        handle, init = _extract_declarator_name_and_initializer(d)
        if handle:
            entry = {"name": handle, "type": type_name}
            if init:
                entry["initializer"] = init
            out.append(entry)
    return out


def _collect_class_handles(class_decl: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """
    Look for class-scope DataDeclaration nodes.
    Returns { handle_name -> {"type": type_name, "initializer": ...?} }.
    Does not recurse into methods.
    """
    handles: Dict[str, Dict[str, str]] = {}

    def walk(node: Any):
        if isinstance(node, dict):
            k = node.get("kind")

            if k in ("ClassMethodDeclaration", "TaskDeclaration", "FunctionDeclaration", "ClassMethodPrototype"):
                return

            if k == "ClassPropertyDeclaration":
                decl = node.get("declaration")
                if isinstance(decl, dict) and decl.get("kind") == "DataDeclaration":
                    for entry in _extract_decl_entries(decl):
                        handles.setdefault(entry["name"], entry)

            elif k == "DataDeclaration":
                for entry in _extract_decl_entries(node):
                    handles.setdefault(entry["name"], entry)

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



def _macro_usage_to_stmt(macro_usage: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(macro_usage, dict) or macro_usage.get("kind") != "MacroUsage":
        return None

    directive = macro_usage.get("directive")
    name = directive.get("text", "") if isinstance(directive, dict) else ""
    args_node = macro_usage.get("args")
    args: List[str] = []
    if isinstance(args_node, dict):
        for a in args_node.get("args", []):
            if isinstance(a, dict) and a.get("kind") != "Comma":
                txt = _minify_ws(_collect_tokens(a))
                if txt:
                    args.append(txt)

    stmt: Dict[str, Any] = {"type": "function_call", "name": name, "arguments": args}
    lname = name.lower()
    if "uvm_fatal" in lname:
        stmt["semantic_type"] = "uvm_fatal"
    elif "uvm_error" in lname:
        stmt["semantic_type"] = "uvm_error"
    elif "uvm_warning" in lname:
        stmt["semantic_type"] = "uvm_warning"
    elif "uvm_info" in lname:
        stmt["semantic_type"] = "uvm_info"
    return stmt


def _collect_macro_stmts(node: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()

    def walk(x: Any):
        if isinstance(x, dict):
            for v in x.values():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and item.get("kind") == "Directive":
                            syntax = item.get("syntax")
                            stmt = _macro_usage_to_stmt(syntax) if isinstance(syntax, dict) else None
                            if stmt is not None:
                                sig = (stmt.get("name"), tuple(stmt.get("arguments", [])))
                                if sig not in seen:
                                    seen.add(sig)
                                    out.append(stmt)
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(node)
    return out

def _classify_monitor_invocation(expr: Dict[str, Any]) -> Dict[str, Any]:
    call_obj = _invocation_to_method_call(expr)
    full_txt = _expr_to_text(expr)
    call_name = _extract_invocation_name(expr) or ""

    if "uvm_config_db" in full_txt and "::get" in full_txt:
        call_obj["semantic_type"] = "config_db_get"
        return call_obj

    if "type_id::create" in full_txt:
        call_obj["semantic_type"] = "factory_create"
        return call_obj

    if call_name == "write":
        call_obj["semantic_type"] = "analysis_write"
        return call_obj

    if call_name == "new":
        call_obj["semantic_type"] = "constructor_call"
        return call_obj

    if "uvm_fatal" in full_txt or "`uvm_fatal" in full_txt:
        call_obj["semantic_type"] = "uvm_fatal"
        return call_obj

    if "uvm_error" in full_txt or "`uvm_error" in full_txt:
        call_obj["semantic_type"] = "uvm_error"
        return call_obj

    if "uvm_warning" in full_txt or "`uvm_warning" in full_txt:
        call_obj["semantic_type"] = "uvm_warning"
        return call_obj

    if "uvm_info" in full_txt or "`uvm_info" in full_txt:
        call_obj["semantic_type"] = "uvm_info"
        return call_obj

    return call_obj


def _classify_assignment(lhs: str, rhs: str, op: str = "=") -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "type": "assignment",
        "operator": op,
        "lhs": lhs,
        "rhs": rhs,
    }

    if rhs.startswith("vif.") or rhs.startswith("this.vif.") or ".vif." in rhs:
        entry["semantic_type"] = "sample_from_interface"
    elif rhs.startswith("new(") or rhs == "new" or ".new(" in rhs:
        entry["semantic_type"] = "constructor_call"
    elif "type_id::create" in rhs:
        entry["semantic_type"] = "factory_create"

    return entry


# -----------------------------
# Timing / wait helpers
# -----------------------------
def _extract_wait_info(node: Dict[str, Any]) -> Optional[str]:
    if node.get("kind") != "WaitStatement":
        return None
    return _expr_to_text(node.get("expr"))


def _extract_event_control_info(timing_control: Any) -> Optional[Tuple[str, str]]:
    """
    Handles:
      @(posedge clk)
      @(negedge clk)
      @(vif.mon_cb)
    Return: (edge_or_empty, signal_expr)
    """
    if not isinstance(timing_control, dict):
        return None

    kind = timing_control.get("kind")
    if kind != "EventControlWithExpression":
        return None

    expr = timing_control.get("expr")
    if not isinstance(expr, dict):
        return None

    if expr.get("kind") == "ParenthesizedEventExpression":
        inner = expr.get("expr")
        if not isinstance(inner, dict):
            return None

        if inner.get("kind") == "SignalEventExpression":
            edge = inner.get("edge", {}).get("text", "")
            sig = _expr_to_text(inner.get("expr"))
            if sig:
                return edge, sig

        inner_txt = _expr_to_text(inner)
        if inner_txt:
            return "", inner_txt

    txt = _expr_to_text(expr)
    if txt:
        txt = txt.strip()
        if txt.startswith("(") and txt.endswith(")"):
            txt = txt[1:-1].strip()
        return "", txt

    return None


# -----------------------------
# Recursive procedural traversal (legacy flat mode)
# -----------------------------
def _walk_monitor_procedural(
    node: Any,
    handle_types: Dict[str, str],
    events: List[MonitorEvent],
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
                    _walk_monitor_procedural(item, handle_types, events, cond_stack)
            return

        if kind in ("TaskDeclaration", "FunctionDeclaration"):
            items = node.get("items")
            if isinstance(items, list):
                for item in items:
                    _walk_monitor_procedural(item, handle_types, events, cond_stack)
            return

        if kind == "ForeverStatement":
            events.append(
                MonitorEvent(
                    kind="loop",
                    text="forever",
                    path=_path_from_stack(cond_stack),
                )
            )
            body = node.get("statement")
            if body is not None:
                _walk_monitor_procedural(body, handle_types, events, cond_stack + ["forever"])
            return

        if kind == "ConditionalStatement":
            predicate = node.get("predicate")
            cond_txt = _predicate_to_text(predicate) or "<if-cond>"

            events.append(
                MonitorEvent(
                    kind="branch",
                    text=f"if ({cond_txt})",
                    branch_cond=cond_txt,
                    path=_path_from_stack(cond_stack),
                )
            )

            then_stmt = node.get("statement")
            if then_stmt is not None:
                _walk_monitor_procedural(
                    then_stmt,
                    handle_types,
                    events,
                    cond_stack + [f"then[{cond_txt}]"],
                )

            else_clause = node.get("elseClause")
            if isinstance(else_clause, dict):
                events.append(
                    MonitorEvent(
                        kind="branch",
                        text=f"else of if ({cond_txt})",
                        branch_cond=cond_txt,
                        path=_path_from_stack(cond_stack),
                    )
                )

                else_stmt = else_clause.get("clause")
                if else_stmt is not None:
                    _walk_monitor_procedural(
                        else_stmt,
                        handle_types,
                        events,
                        cond_stack + [f"else[{cond_txt}]"],
                    )
            return

        if kind == "DataDeclaration":
            entries = _extract_decl_entries(node)
            for entry in entries:
                handle = entry["name"]
                type_name = entry.get("type", "")
                handle_types.setdefault(handle, type_name)
                text = f"{type_name} {handle}".strip()
                if entry.get("initializer"):
                    text += f" = {entry['initializer']}"
                text += ";"
                events.append(
                    MonitorEvent(
                        kind="declare",
                        text=text,
                        signal=handle,
                        handle_type=type_name,
                        path=_path_from_stack(cond_stack),
                        semantic_type=(
                            "factory_create" if "type_id::create" in entry.get("initializer", "") else None
                        ),
                        extra={"initializer": entry.get("initializer", "")},
                    )
                )
            return

        if kind == "WaitStatement":
            cond = _extract_wait_info(node)
            cond_txt = cond if cond is not None else "<wait-cond>"
            events.append(
                MonitorEvent(
                    kind="wait",
                    text=f"wait({cond_txt});",
                    branch_cond=cond,
                    path=_path_from_stack(cond_stack),
                )
            )
            return

        if kind == "EmptyStatement":
            for stmt in _collect_macro_stmts(node):
                events.append(
                    MonitorEvent(
                        kind="call",
                        text=f"{stmt.get('name')}({', '.join(stmt.get('arguments', []))});",
                        path=_path_from_stack(cond_stack),
                        semantic_type=stmt.get("semantic_type"),
                        extra=stmt,
                    )
                )
            return

        if kind == "TimingControlStatement":
            info = _extract_event_control_info(node.get("timingControl"))
            if info:
                edge, clkexpr = info
                evt_txt = f"@({(edge + ' ') if edge else ''}{clkexpr});"
                events.append(
                    MonitorEvent(
                        kind="edge",
                        text=evt_txt,
                        edge=edge or None,
                        clock_expr=clkexpr,
                        path=_path_from_stack(cond_stack),
                    )
                )
            return

        if kind == "ExpressionStatement":
            for stmt in _collect_macro_stmts(node):
                events.append(
                    MonitorEvent(
                        kind="call",
                        text=f"{stmt.get('name')}({', '.join(stmt.get('arguments', []))});",
                        path=_path_from_stack(cond_stack),
                        semantic_type=stmt.get("semantic_type"),
                        extra=stmt,
                    )
                )
            expr = node.get("expr")
            if isinstance(expr, dict):
                expr_kind = expr.get("kind")

                if expr_kind in ("AssignmentExpression", "NonblockingAssignmentExpression"):
                    asn = _extract_assignment_sides(expr)
                    if asn:
                        left, op, right = asn
                        semantic_type = None
                        if right.startswith("vif.") or right.startswith("this.vif.") or ".vif." in right:
                            semantic_type = "sample_from_interface"
                        elif right.startswith("new(") or ".new(" in right:
                            semantic_type = "constructor_call"
                        elif "type_id::create" in right:
                            semantic_type = "factory_create"
                        events.append(
                            MonitorEvent(
                                kind="assign",
                                text=f"{left} {op} {right};",
                                signal=left,
                                path=_path_from_stack(cond_stack),
                                semantic_type=semantic_type,
                                extra={"op": op, "rhs": right},
                            )
                        )
                    return

                if expr_kind == "InvocationExpression":
                    call_obj = _classify_monitor_invocation(expr)
                    events.append(
                        MonitorEvent(
                            kind="call",
                            text=_expr_to_text(expr) + ";",
                            signal=_extract_first_arg_identifier(expr),
                            path=_path_from_stack(cond_stack),
                            semantic_type=call_obj.get("semantic_type"),
                            extra=call_obj,
                        )
                    )
                    return
            return

        for v in node.values():
            _walk_monitor_procedural(v, handle_types, events, cond_stack)

    elif isinstance(node, list):
        for i in node:
            _walk_monitor_procedural(i, handle_types, events, cond_stack)


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
        entries = _extract_decl_entries(node)
        for entry in entries:
            name = entry["name"]
            data_type = entry.get("type", "")
            handle_types.setdefault(name, data_type)
            obj: Dict[str, Any] = {
                "type": "variable_declaration",
                "data_type": data_type,
                "name": name,
            }
            init = entry.get("initializer")
            if init:
                obj["initializer"] = init
                if "type_id::create" in init:
                    obj["semantic_type"] = "factory_create"
                elif init.startswith("new(") or ".new(" in init:
                    obj["semantic_type"] = "constructor_call"
            out.append(obj)
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

    if kind == "EmptyStatement":
        out.extend(_collect_macro_stmts(node))
        return out

    if kind == "TimingControlStatement":
        info = _extract_event_control_info(node.get("timingControl"))
        if info:
            edge, sig = info
            obj: Dict[str, Any] = {
                "type": "event_control",
                "event": sig,
            }
            if edge:
                obj["edge"] = edge
            out.append(obj)
        return out

    if kind == "ExpressionStatement":
        out.extend(_collect_macro_stmts(node))
        expr = node.get("expr")
        if not isinstance(expr, dict):
            return out

        expr_kind = expr.get("kind")

        if expr_kind in ("AssignmentExpression", "NonblockingAssignmentExpression"):
            asn = _extract_assignment_sides(expr)
            if asn:
                lhs, op, rhs = asn
                out.append(_classify_assignment(lhs, rhs, op))
            return out

        if expr_kind == "InvocationExpression":
            out.append(_classify_monitor_invocation(expr))
            return out

        return out

    for v in node.values():
        out.extend(_build_stmt_list(v, handle_types))

    return out


# -----------------------------
# Entry point: extract flows
# -----------------------------
def extract_monitor_flows_from_file(filepath: str) -> List[MonitorFlow]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    monitor_class_to_params = _find_monitor_classes(cst)
    flows: List[MonitorFlow] = []
    class_handles: Dict[str, Dict[str, Dict[str, str]]] = {}

    def walk(x: Any, current_class: Optional[str] = None):
        if isinstance(x, dict):
            k = x.get("kind")

            if k == "ClassDeclaration":
                cls_name = _extract_simple_identifier_text(x.get("name"))
                if cls_name and cls_name in monitor_class_to_params:
                    class_handles[cls_name] = _collect_class_handles(x)

                for v in x.values():
                    walk(v, current_class=cls_name)
                return

            if k in ("TaskDeclaration", "FunctionDeclaration"):
                proto = x.get("prototype")
                if isinstance(proto, dict):
                    name_node = proto.get("name")

                    scoped = _extract_scoped_name_text(name_node)
                    mon_cls: Optional[str] = None
                    proc_name: Optional[str] = None

                    if scoped and "::" in scoped:
                        mon_cls, proc_name = [p.strip() for p in scoped.split("::", 1)]
                    else:
                        if current_class is not None:
                            mon_cls = current_class
                            proc_name = _get_name_from_proto_name(name_node)

                    if mon_cls and proc_name and mon_cls in monitor_class_to_params and proc_name in MONITOR_PHASE_PROCS:
                        handle_types: Dict[str, str] = {
                            h: d.get("type", "") for h, d in class_handles.get(mon_cls, {}).items()
                        }
                        events: List[MonitorEvent] = []

                        for h, d in class_handles.get(mon_cls, {}).items():
                            t = d.get("type", "")
                            init = d.get("initializer", "")
                            text = f"{t} {h}".strip()
                            if init:
                                text += f" = {init}"
                            text += ";"
                            events.append(
                                MonitorEvent(
                                    kind="declare",
                                    text=text,
                                    signal=h,
                                    handle_type=t,
                                    path="",
                                    semantic_type=(
                                        "factory_create" if "type_id::create" in init else None
                                    ),
                                )
                            )

                        _walk_monitor_procedural(x, handle_types, events, cond_stack=[])

                        flows.append(
                            MonitorFlow(
                                monitor_class=mon_cls,
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
def extract_monitor_components_from_file(filepath: str) -> List[Dict[str, Any]]:
    tree = pyslang.SyntaxTree.fromFile(filepath)
    cst = json.loads(tree.to_json())

    monitor_class_to_params = _find_monitor_classes(cst)
    class_handles: Dict[str, Dict[str, Dict[str, str]]] = {}
    components: Dict[str, Dict[str, Any]] = {}

    def ensure_component(class_name: str) -> Dict[str, Any]:
        if class_name not in components:
            members: List[Dict[str, Any]] = []
            for handle, decl in class_handles.get(class_name, {}).items():
                type_name = decl.get("type", "")
                member: Dict[str, Any]
                if type_name.startswith("virtual "):
                    member = {
                        "type": "virtual_interface",
                        "name": handle,
                        "interface_type": type_name.replace("virtual ", "", 1),
                    }
                else:
                    member = {
                        "type": "variable",
                        "name": handle,
                        "data_type": type_name,
                    }
                if decl.get("initializer"):
                    member["initializer"] = decl["initializer"]
                members.append(member)

            components[class_name] = {
                "name": class_name,
                "base_type": "uvm_monitor",
                "parameters": monitor_class_to_params.get(class_name, []),
                "members": members,
            }
        return components[class_name]

    def walk(x: Any, current_class: Optional[str] = None):
        if isinstance(x, dict):
            k = x.get("kind")

            if k == "ClassDeclaration":
                cls_name = _extract_simple_identifier_text(x.get("name"))
                if cls_name and cls_name in monitor_class_to_params:
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
                    mon_cls: Optional[str] = None
                    proc_name: Optional[str] = None

                    if scoped and "::" in scoped:
                        mon_cls, proc_name = [p.strip() for p in scoped.split("::", 1)]
                    else:
                        if current_class is not None:
                            mon_cls = current_class
                            proc_name = _get_name_from_proto_name(name_node)

                    if mon_cls and proc_name and mon_cls in monitor_class_to_params:
                        component = ensure_component(mon_cls)
                        handle_types: Dict[str, str] = {
                            h: d.get("type", "") for h, d in class_handles.get(mon_cls, {}).items()
                        }
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
def _format_flows(flows: List[MonitorFlow]) -> str:
    lines: List[str] = []
    lines.append("Monitor Flow:")

    if not flows:
        lines.append("  <no monitor build_phase/run_phase flows found>")
        return "\n".join(lines)

    flows_by_monitor: Dict[str, List[MonitorFlow]] = {}
    for fl in flows:
        flows_by_monitor.setdefault(fl.monitor_class, []).append(fl)

    for mon in sorted(flows_by_monitor.keys()):
        lines.append(f"  {mon} (uvm_monitor)")

        for fl in sorted(flows_by_monitor[mon], key=lambda x: x.proc):
            lines.append(f"    {fl.proc}:")

            for e in fl.events:
                path_suffix = f"  [path: {e.path}]" if e.path else ""
                semantic_suffix = f"  [semantic: {e.semantic_type}]" if e.semantic_type else ""

                if e.kind == "edge":
                    edge_prefix = f"{e.edge} " if e.edge else ""
                    clk = f"{edge_prefix}{e.clock_expr}" if e.clock_expr else ""
                    lines.append(f"      [{e.kind}] {clk}: {e.text}{semantic_suffix}{path_suffix}")
                elif e.signal:
                    t = f" type={e.handle_type}" if e.handle_type else ""
                    lines.append(f"      [{e.kind}] {e.signal}{t}: {e.text}{semantic_suffix}{path_suffix}")
                else:
                    lines.append(f"      [{e.kind}] {e.text}{semantic_suffix}{path_suffix}")

    return "\n".join(lines)


def write_summary(out_file: str, flows: List[MonitorFlow]) -> None:
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
    stem_suffix = "_monitor_summary_json" if output_format == "json" else "_monitor_summary"
    return f"{base}{stem_suffix}{suffix}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="SystemVerilog file (.sv/.svh)")
    parser.add_argument("--out", default=None, help="Output file path")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format: flat text summary or nested JSON",
    )
    args = parser.parse_args()

    out_file = args.out if args.out else default_out_path(args.file, args.format)

    if args.format == "json":
        components = extract_monitor_components_from_file(args.file)
        write_json_output(out_file, components)
        print(f"Wrote monitor JSON summary to {out_file}")
    else:
        flows = extract_monitor_flows_from_file(args.file)
        write_summary(out_file, flows)
        print(f"Wrote monitor flow summary to {out_file}")


if __name__ == "__main__":
    main()
