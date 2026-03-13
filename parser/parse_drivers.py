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
#   4) Annotate each event with a path describing its branch / loop context.
#
#
# To run:
#   python parse_driver.py <file.sv>


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
# Call / assignment helpers (note: we do NOT emit generic calls)
# -----------------------------
def _extract_invocation_name(inv: Dict[str, Any]) -> Optional[str]:
    left = inv.get("left")
    if not isinstance(left, dict):
        return None

    kind = left.get("kind")

    if kind == "IdentifierName":
        txt = _expr_to_text(left)
        return txt if txt else None

    if kind == "ScopedName":
        txt = _expr_to_text(left.get("right"))
        return txt if txt else None

    if kind == "SystemName":
        txt = _expr_to_text(left)
        return txt if txt else None

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
_SEQ_RSP_CALLS = {"put_response"}  # currently treated as a "meaningful" driver event


# -----------------------------
# Recursive procedural traversal
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

        # Sequential block
        if kind == "SequentialBlockStatement":
            items = node.get("items")
            if isinstance(items, list):
                for item in items:
                    _walk_driver_procedural(item, handle_types, events, cond_stack)
            return

        # Task / function declaration (walk items)
        if kind in ("TaskDeclaration", "FunctionDeclaration"):
            items = node.get("items")
            if isinstance(items, list):
                for item in items:
                    _walk_driver_procedural(item, handle_types, events, cond_stack)
            return

        # Forever loop
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

        # Conditional
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

                else_stmt = else_clause.get("clause")  # NOTE: pyslang uses "clause"
                if else_stmt is not None:
                    _walk_driver_procedural(
                        else_stmt,
                        handle_types,
                        events,
                        cond_stack + [f"else[{cond_txt}]"],
                    )
            return

        # Declaration
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

        # Wait statement
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

        # Timing control statement (e.g. @(posedge clk);)
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
            # If it's some other timing control we don't recognize, we ignore it for now.
            return

        # Expression statement
        if kind == "ExpressionStatement":
            expr = node.get("expr")
            if isinstance(expr, dict):
                expr_kind = expr.get("kind")

                # Assignment / nonblocking assignment
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

                # Invocation (only emit if it's meaningful)
                if expr_kind == "InvocationExpression":
                    call = _extract_invocation_name(expr)
                    arg0 = _extract_first_arg_identifier(expr)

                    # Special: sequencer handshake calls
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
                        # Keep as a meaningful event for now (still not "generic call")
                        events.append(
                            DriverEvent(
                                kind="seq_done",  # optional: you can change to "seq_rsp" if you want later
                                text=_expr_to_text(expr) + ";",
                                signal=arg0,
                                handle_type=handle_types.get(arg0),
                                path=_path_from_stack(cond_stack),
                                extra={"call": call, "response": True},
                            )
                        )
                    # else: ignore generic calls
                    return

            # Unknown expression statement: ignore
            return

        # Default recursion
        for v in node.values():
            _walk_driver_procedural(v, handle_types, events, cond_stack)

    elif isinstance(node, list):
        for i in node:
            _walk_driver_procedural(i, handle_types, events, cond_stack)


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

                        # Emit synthetic declare events for class-level handles
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
    args = parser.parse_args()

    flows = extract_driver_flows_from_file(args.file)

    out_file = args.out if args.out else default_out_path(args.file)
    write_summary(out_file, flows)
    print(f"Wrote driver flow summary to {out_file}")


if __name__ == "__main__":
    main()