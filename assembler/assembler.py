import pyslang
from pyslang import SyntaxKind, SymbolKind

class HierarchyNode:
    """
    Represents a specific INSTANCE in the UVM hierarchy.
    (e.g., 'env' is an instance of type 'alu_env')
    """
    def __init__(self, name, type_name, parent=None):
        self.name = name            # Instance name (e.g., "agt")
        self.type_name = type_name  # Class type (e.g., "alu_agent")
        self.parent = parent
        self.children = []          # List of HierarchyNode
        self.configs = []           # Stores uvm_config_db::set calls found here

    def add_child(self, child_node):
        child_node.parent = self
        self.children.append(child_node)

    def print_tree(self, level=0):
        indent = "  " * level
        print(f"{indent}|- {self.name} : {self.type_name}")
        for config in self.configs:
            print(f"{indent}|  [Config Set] {config}")
        for child in self.children:
            child.print_tree(level + 1)


# --- Phase 1 ---
class UVMRegistry:
    def __init__(self):
        # Classification Buckets
        self.drivers = {}        # Name -> AST Node
        self.monitors = {}
        self.agents = {}
        self.envs = {}
        self.tests = {}
        self.seq_items = {}      # Data packets (Rule 5)

        # Format: { 'interface_name': { 'signals': [], 'modports': {} } }
        self.interfaces = {}

    def summary(self):
        print("--- Classification Summary ---")
        print(f"Drivers:    {list(self.drivers.keys())}")
        print(f"Monitors:   {list(self.monitors.keys())}")
        print(f"Agents:     {list(self.agents.keys())}")
        print(f"Envs:       {list(self.envs.keys())}")
        print(f"Tests:      {list(self.tests.keys())}")
        print(f"Seq Items:  {list(self.seq_items.keys())}")
        print(f"Interfaces: {list(self.interfaces.keys())}")
        print("------------------------------")

class Classifier:
    def __init__(self, tree):
        self.tree = tree
        self.registry = UVMRegistry()

    def run(self):
        # Start visiting from the root
        self._visit(self.tree.root)
        return self.registry

    def _visit(self, node):
        # 1. Check for Class Declarations (Drivers, Monitors, etc.)
        if node.kind == SyntaxKind.ClassDeclaration:
            self._classify_class(node)

        # 2. Check for Interface Declarations (Rule 2 Support)
        elif node.kind == SyntaxKind.InterfaceDeclaration:
            self._ingest_interface(node)

        # Recursively visit children
        if hasattr(node, 'members'):
            for child in node.members:
                self._visit(child)

    def _classify_class(self, node):
        """
        Inspects the 'extends' clause to determine the class role.
        """
        class_name = node.name.value

        # If there is no extends clause, we ignore it or treat as generic
        if node.extendsClause is None:
            return

        # Extract base class name.
        # Structure often: ClassDeclaration -> ExtendsClause -> Type (maybe parameterized)
        base_type = node.extendsClause.baseName

        # Extended class can be in this format `uvm_driver #(alu_item)`
        # Helper to dig out the raw identifier from potentially complex types
        base_name = self._get_type_name(base_type)

        # Apply Classification Logic
        if "uvm_driver" in base_name:
            self.registry.drivers[class_name] = node
        elif "uvm_monitor" in base_name or "monitor" in class_name.lower():
            self.registry.monitors[class_name] = node
        elif "uvm_agent" in base_name:
            self.registry.agents[class_name] = node
        elif "uvm_env" in base_name:
            self.registry.envs[class_name] = node
        elif "uvm_test" in base_name:
            self.registry.tests[class_name] = node
        elif "uvm_sequence_item" in base_name:
            self.registry.seq_items[class_name] = node

    def _ingest_interface(self, node):
        """
        Parses an interface to find signals and modports for later 'Port Explosion'.
        NOW COMPLETE: Extracting input/output directions from modports.
        """
        if_name = node.header.name.value
        # Structure:
        # {
        #   'signals': ['clk', 'rst_n', ...],
        #   'modports': {
        #       'tb': {'clk': 'input', 'rst_n': 'output'},
        #       'dut': {'clk': 'input', 'rst_n': 'input'}
        #   }
        # }
        self.registry.interfaces[if_name] = {'signals': [], 'modports': {}}

        # Walk interface members
        for member in node.members:
            # 1. Detect Signals (DataDeclaration) - same as before
            if member.kind == SyntaxKind.DataDeclaration:
                for decl in member.declarators:
                    sig_name = decl.name.value
                    self.registry.interfaces[if_name]['signals'].append(sig_name)

            # 2. Detect Modports (ModportDeclaration) - COMPLETED
            elif member.kind == SyntaxKind.ModportDeclaration:
                for item in member.items:
                    modport_name = item.name.value
                    # Initialize dictionary for this modport
                    self.registry.interfaces[if_name]['modports'][modport_name] = {}
                    # Track direction (default to inout if undefined, though usually explicit)
                    current_direction = "inout"

                    # Iterate through the ports in the modport list
                    for port in item.ports:
                        # Check if this port has an explicit direction (input/output/inout)
                        # pyslang AST: port.direction is a Token or None
                        if port.direction is not None:
                            current_direction = port.direction.valueText
                        # Get the signal name
                        port_name = port.name.value
                        # Store the mapping: Signal Name -> Direction
                        self.registry.interfaces[if_name]['modports'][modport_name][port_name] = current_direction

    def _ingest_interface(self, node):
        """
        Parses an interface to find signals and modports for later 'Port Explosion'.
        """
        if_name = node.header.name.value
        self.registry.interfaces[if_name] = {'signals': [], 'modports': {}}

        # Walk interface members
        for member in node.members:
            # Detect Signals (DataDeclaration)
            if member.kind == SyntaxKind.DataDeclaration:
                # Iterate variables in the declaration (e.g., logic a, b, c)
                for decl in member.declarators:
                    sig_name = decl.name.value
                    # Note: Getting the full type (logic [3:0]) requires deeper parsing
                    # For now, we store the name to prove we found it.
                    self.registry.interfaces[if_name]['signals'].append(sig_name)

            # Detect Modports
            elif member.kind == SyntaxKind.ModportDeclaration:
                for item in member.items:
                    modport_name = item.name.value
                    self.registry.interfaces[if_name]['modports'][modport_name] = []
                    # You would iterate item.ports here to get directions (input/output)

    def _get_type_name(self, type_node):
        """
        Robustly extracts the string name of a type, handling parameters.
        Example: uvm_driver#(alu_item) -> "uvm_driver"
        """
        # Case 1: Simple Identifier (uvm_test)
        if hasattr(type_node, 'identifier'):
            return type_node.identifier.value

        # Case 2: Parameterized Class (uvm_driver #(alu_item))
        # Structure: SpecializationExpression -> target (IdentifierName)
        if type_node.kind == SyntaxKind.ClassType: # Or similar depending on slang version
            if hasattr(type_node, 'target'):
                # Recurse or grab target
                return self._get_type_name(type_node.target)

        # Fallback: Convert the node to string via slang's text method
        # This returns "uvm_driver #(alu_item)", allowing us to substring search
        return str(type_node)


# --- Phase 2 ---
class Builder:
    """
    Performs 'Virtual Elaboration' by traversing build_phase() tasks.
    """
    def __init__(self, registry):
        self.registry = registry
        self.root_node = None

    def build(self, root_class_name):
        """
        Main entry point. Starts elaboration from the top Test class.
        """
        print(f"Starting Virtual Elaboration at root: {root_class_name}")
        self.root_node = HierarchyNode("uvm_test_top", root_class_name)

        # Recursive build
        self._elaborate_node(self.root_node)
        return self.root_node

    def _elaborate_node(self, current_node):
        """
        1. Look up the AST for the current node's type.
        2. Find its 'build_phase'.
        3. Scan for create() calls and config_db sets.
        4. Recurse for children.
        """
        # 1. Resolve Type to AST
        # Try to find the class definition in our registry (agents, envs, drivers, etc.)
        class_ast = self._find_ast_by_type(current_node.type_name)

        if not class_ast:
            # If not in registry, it's likely a library class (uvm_sequencer)
            # or we missed it. We stop recursing here.
            return

        # 2. Find build_phase
        build_phase = self._find_method(class_ast, "build_phase")
        if not build_phase:
            return

        # 3. Scan statements in build_phase
        # We need a visitor to look for Assignments and Function Calls
        self._scan_build_phase(build_phase, current_node, class_ast)

        # 4. Recurse (Depth-First)
        for child in current_node.children:
            self._elaborate_node(child)

    def _find_ast_by_type(self, type_name):
        # Search all buckets in the registry
        for bucket in [self.registry.tests, self.registry.envs,
                       self.registry.agents, self.registry.drivers,
                       self.registry.monitors]:
            if type_name in bucket:
                return bucket[type_name]
        return None

    def _find_method(self, class_node, method_name):
        for item in class_node.items:
            # Check if the node is any type of method/task/function
            if item.kind in [SyntaxKind.ClassMethodDeclaration,
                             SyntaxKind.TaskDeclaration,
                             SyntaxKind.FunctionDeclaration]:

                # 1. Unwrap the wrapper: if it's a ClassMethodDeclaration, get the inner declaration
                decl = item.declaration if item.kind == SyntaxKind.ClassMethodDeclaration else item

                # 2. Safely extract the name
                actual_name = None

                # Most slang versions store the name in the prototype
                if hasattr(decl, 'prototype') and hasattr(decl.prototype, 'name'):
                    name = decl.prototype.name
                    if name.kind == SyntaxKind.IdentifierName:
                        actual_name = name.identifier.valueText
                else:
                    raise RuntimeError('Unexpected: declaration do not have attr prototype or prototype does not have name')

                # 3. Check for a match
                if actual_name == method_name:
                    # Return the unwrapped declaration so the next step can access .items (the body)
                    return decl

        return None

    def _scan_build_phase(self, method_node, current_hierarchy_node, class_ast):
        """
        Scans the body of build_phase for:
        1. Factory Creation: var = type::type_id::create(...)
        2. Config DB: uvm_config_db#(...)::set(...)
        """
        if not method_node.items: return

        for item in method_node.items:
            # We are looking for ExpressionStatements
            if item.kind == SyntaxKind.ExpressionStatement:
                expr = item.expr

                # CASE A: Factory Creation (Assignment)
                # agt = alu_agent::type_id::create("agt", this);
                if expr.kind == SyntaxKind.AssignmentExpression:
                    self._handle_creation(expr, current_hierarchy_node, class_ast)

                # CASE B: Config DB Set (Void Call)
                # uvm_config_db#(...)::set(...)
                elif expr.kind == SyntaxKind.InvocationExpression:
                    self._handle_config_set(expr, current_hierarchy_node)

    def _handle_creation(self, assignment_expr, parent_node, class_ast):
        """
        Logic:
        1. Check if RHS is a call to 'create'.
        2. Get the LHS variable name (e.g., 'agt').
        3. Look up 'agt' in the Class Members to find its type ('alu_agent').
        """
        # Simplify: Convert entire RHS to string to check for "create"
        # In a robust compiler, we would check the CallExpression structure strictly.
        rhs_str = str(assignment_expr.right)

        if "create" in rhs_str and "type_id" in rhs_str:
            # 1. Identify Instance Name (LHS)
            # LHS might be 'agt' or 'this.agt'. keeping it simple:
            inst_var_name = str(assignment_expr.left).strip()

            # 2. Resolve Type from Class Member Declaration
            inst_type = self._lookup_member_type(class_ast, inst_var_name)

            if inst_type:
                # 3. Create Child Node
                # We use the variable name as the instance name for simplicity,
                # though strictly UVM uses the string arg in create("name").
                new_child = HierarchyNode(inst_var_name, inst_type)
                parent_node.add_child(new_child)
                # print(f"  [Build] Found child '{inst_var_name}' of type '{inst_type}' in {parent_node.type_name}")

    def _handle_config_set(self, call_expr, node):
        call_str = str(call_expr)
        if "uvm_config_db" in call_str and "set" in call_str:
            # Just storing the string representation for Phase 3 analysis
            # In Phase 3, you would parse the arguments: (cntxt, path, key, value)
            node.configs.append(call_str)

    def _lookup_member_type(self, class_ast, var_name):
        """
        Scans the class variables to find what type 'var_name' is.
        e.g., 'alu_agent agt;' -> returns 'alu_agent'
        """
        for item in class_ast.items:
            # Case 1: Direct Data Declaration
            if item.kind == SyntaxKind.ClassPropertyDeclaration:

                for decl in item.declaration.declarators:
                    if decl.name.valueText.strip() == var_name.strip():
                        return self._robust_type_name(item.declaration.type.name.identifier.valueText)
        return None

    def _robust_type_name(self, type_node):
        # Reuse logic from Phase 1 to get string name of type
        return str(type_node)


# --- Phase 3 ---
class RTLPort:
    def __init__(self, name, direction, width="1"):
        self.name = name
        self.direction = direction  # "input" or "output"
        self.width = width

    def __repr__(self):
        return f"{self.direction} logic [{self.width}:0] {self.name}"

class RTLModuleDefinition:
    """
    Represents the final Synthesized Module (e.g., 'module alu_driver_rtl ...')
    """
    def __init__(self, module_name):
        self.name = module_name
        self.ports = []      # List of RTLPort
        self.wires = []      # Internal wires for Containers
        self.instances = []  # Sub-modules instantiated here

    def add_port(self, name, direction, width="0"):
        # Helper to avoid duplicates
        self.ports.append(RTLPort(name, direction, width))

# --- Phase 3 Logic ---

class Connector:
    def __init__(self, registry, hierarchy_root):
        self.registry = registry
        self.root = hierarchy_root
        self.modules = {} # Map: UVM Class Name -> RTLModuleDefinition

    def run(self):
        print("Starting Phase 3: Connectivity Analysis...")

        # 1. Propagate Virtual Interfaces (Simulating config_db::set/get)
        # In a real tool, we trace 'set' calls. Here, we'll implement the logic
        # specifically for the 'tb_top' -> 'test' -> 'env' flow you provided.
        self._propagate_interfaces(self.root)

        # 2. Synthesize Leafs (Drivers/Monitors)
        self._synthesize_leafs(self.root)

        # 3. Synthesize Containers (Agents/Envs) - Wiring them together
        self._synthesize_containers(self.root)

        return self.modules

    def _propagate_interfaces(self, node, inherited_if=None):
        """
        Pushes interface info down the tree.
        Simplified: We assume 'alu_if' is passed down to everyone.
        """
        # In reality, we parse node.configs to find 'set' calls.
        # For this prototype, we assume the root passes 'alu_if' to children.
        current_if = inherited_if

        # Check if this node has a specific interface handle variable (e.g. 'vif')
        # We look at the class definition in the registry.
        class_node = self._find_ast_node(node.type_name)
        if class_node:
             # Find 'virtual alu_if.tb vif' member
             vif_info = self._find_virtual_interface_handle(class_node)
             if vif_info:
                 node.vif_def = vif_info # Store for Step 2
                 current_if = vif_info   # Pass down to children

        for child in node.children:
            self._propagate_interfaces(child, current_if)

    def _synthesize_leafs(self, node):
        # Recursively visit children first
        for child in node.children:
            self._synthesize_leafs(child)

        # Process only Leafs (Driver/Monitor)
        if node.type_name in self.registry.drivers or node.type_name in self.registry.monitors:
            print(f"  [Synth] Generating Leaf Ports for {node.name} ({node.type_name})")
            rtl_mod = RTLModuleDefinition(f"{node.type_name}_rtl")

            # A. Standard Ports
            rtl_mod.add_port("clk", "input")
            rtl_mod.add_port("rst_n", "input")

            # B. Explode Interface (Rule 2)
            if hasattr(node, 'vif_def'):
                self._explode_interface_ports(rtl_mod, node.vif_def)
            else:
                print(f"    WARNING: No virtual interface found for {node.name}")

            # C. Handshake Ports (Rule 5 & Handshake Refinement)
            if node.type_name in self.registry.drivers:
                self._add_stimuli_handshake_ports(rtl_mod)

            self.modules[node.type_name] = rtl_mod

    def _synthesize_containers(self, node):
        # Skip leafs
        if node.type_name in self.registry.drivers or node.type_name in self.registry.monitors:
            return

        # Recursively process children
        for child in node.children:
            self._synthesize_containers(child)

        # Now build THIS container module
        print(f"  [Synth] Generating Container Wiring for {node.name} ({node.type_name})")
        rtl_mod = RTLModuleDefinition(f"{node.type_name}_rtl")

        # Containers also need clk/rst to pass down
        rtl_mod.add_port("clk", "input")
        rtl_mod.add_port("rst_n", "input")

        # If this container (Agent) has a Driver and Sequencer, wire them
        self._analyze_connections(node, rtl_mod)

        self.modules[node.type_name] = rtl_mod

    # --- Helper Logic ---

    def _find_virtual_interface_handle(self, class_node):
        """
        Scans class members for 'virtual alu_if.tb vif;'
        Returns dict: {'if_name': 'alu_if', 'modport': 'tb', 'var_name': 'vif'}
        """
        # FIX 1: Iterate over .items instead of .members
        for item in class_node.items:

            # FIX 2: Check for the ClassPropertyDeclaration wrapper
            if item.kind == SyntaxKind.ClassPropertyDeclaration:

                # The actual declaration is inside the wrapper
                decl = item.declaration

                # We stringify the type to look for the "virtual" keyword
                # Slang often represents this as a VirtualInterfaceType node
                type_str = str(decl.type)

                if "virtual" in type_str and "interface" not in type_str:
                    # Extract "alu_if" and "tb"
                    # Format usually: virtual alu_if.tb
                    parts = type_str.replace("virtual", "").strip().split('.')
                    if len(parts) >= 1:
                        if_name = parts[0]
                        modport = parts[1] if len(parts) > 1 else None

                        # FIX 3: Safely extract the variable name from the declarators
                        # Assuming a single declaration like `virtual alu_if vif;`
                        if decl.declarators:
                            var_name = decl.declarators[0].name.valueText
                        else:
                            var_name = None

                        return {'if_name': if_name, 'modport': modport, 'var_name': var_name}
        return None

    def _explode_interface_ports(self, rtl_mod, vif_info):
        """
        Rule 2 Implementation:
        Look up interface definition -> Get Modport -> Create Ports
        """
        if_name = vif_info['if_name']
        modport_name = vif_info['modport']

        if if_name not in self.registry.interfaces:
            print(f"    ERROR: Interface '{if_name}' definition not found in registry.")
            return

        if_def = self.registry.interfaces[if_name]

        # 1. Get all signals defined in the interface
        # 2. Filter/Direct them based on Modport
        # Note: pyslang Modport parsing is complex.
        # For this prototype, we will infer direction from the UVM code context
        # Driver (tb modport) -> Outputs what DUT inputs.

        print(f"    Exploding {if_name}.{modport_name}...")

        # Hack/Heuristic for prototype:
        # If modport is 'tb': 'result'/'done' are INPUTS, others OUTPUTS
        # If modport is 'dut': 'result'/'done' are OUTPUTS, others INPUTS
        # In production, you MUST parse the `modport` AST node explicitly.

        all_signals = if_def['signals'] # ['rst_n', 'start', 'op', 'a', 'b', 'result', 'done']

        for sig in all_signals:
            port_name = f"vif_{sig}" # Prefix to avoid collision
            direction = "input" # Default

            if modport_name == "tb":
                # Driver Logic
                if sig in ["result", "done", "clk"]:
                    direction = "input"
                else:
                    direction = "output"
            elif modport_name == "dut":
                # Monitor Logic (Passive) - usually all inputs
                direction = "input"

            rtl_mod.add_port(port_name, direction, "0") # Width would be looked up from if_def

    def _add_stimuli_handshake_ports(self, rtl_mod):
        """
        匹配你朋友的 seq_stim_if.SEQ 端口方向
        """
        # Request (Driver -> Stimuli)
        rtl_mod.add_port("req_valid", "output")
        rtl_mod.add_port("req_ready", "input")
        rtl_mod.add_port("constraint_id", "output", "1") # 假设 4 个 constraint，位宽取决于你朋友的设定
        rtl_mod.add_port("lower_bound", "output", "31")
        rtl_mod.add_port("upper_bound", "output", "31")

        # Response (Stimuli -> Driver)
        rtl_mod.add_port("rsp_ready", "output")
        rtl_mod.add_port("rsp_valid", "input")
        rtl_mod.add_port("solved_data", "input", "31") # 32-bit flat data

    def _analyze_connections(self, container_node, rtl_mod):
        """
        Parses connect_phase to find wires.
        If we find Driver + Sequencer, we generate the connecting wires.
        """
        # Check children
        driver_inst = None
        sequencer_inst = None

        for child in container_node.children:
            if child.type_name in self.registry.drivers:
                driver_inst = child
            # In Phase 2 we saw 'sqr' has type 'uvm_sequencer #(alu_item)'
            if "uvm_sequencer" in child.type_name:
                sequencer_inst = child

        if driver_inst and sequencer_inst:
            print(f"    [Connect] Found Driver '{driver_inst.name}' <-> Sequencer '{sequencer_inst.name}'")
            # We don't parse the exact connect() string here because it's standard UVM.
            # We KNOW they must be connected via the handshake wires.

            # Define Wires
            rtl_mod.wires.append("wire w_valid;")
            rtl_mod.wires.append("wire w_ready;")
            rtl_mod.wires.append("wire [1:0] w_op;")
            rtl_mod.wires.append("wire [7:0] w_a, w_b;")

            # In Phase 5 (Assembly), these wires will be passed
            # to the Driver instance and the Stimuli Generator instance.

    def _find_ast_node(self, type_name):
        # Reuse lookup logic
        for bucket in [self.registry.drivers, self.registry.monitors,
                       self.registry.agents, self.registry.envs, self.registry.tests]:
            if type_name in bucket: return bucket[type_name]
        return None


# Part 4: --- FSM Data Structures ---
import pyslang
from pyslang import SyntaxKind

# --- FSM Data Structures ---

class FSMState:
    def __init__(self, name):
        self.name = name
        self.actions = []       # List of strings (e.g., "vif_start = 1'b1;")
        self.transitions = []   # List of tuples: (condition_str, target_state_obj)
        self.is_reset_state = False

    def add_action(self, action_str):
        self.actions.append(action_str)

    def add_transition(self, condition, target_state):
        self.transitions.append((condition, target_state))

    def __repr__(self):
        return self.name

class Synthesizer:
    def __init__(self, registry, rtl_modules):
        self.registry = registry
        self.rtl_modules = rtl_modules
        self.state_counter = 0

    def run(self, f):
        print("Starting Phase 4: Behavioral Synthesis...")
        for class_name, rtl_mod in self.rtl_modules.items():
            # Only synthesize drivers/monitors (Leafs)
            if class_name in self.registry.drivers:
                self._synthesize_driver_fsm(class_name, rtl_mod, f)
            # (Monitor synthesis is similar but simpler, skipped for brevity)

    def _synthesize_driver_fsm(self, class_name, rtl_mod, f):
        print(f"  [FSM] Synthesizing {class_name}...")

        # 1. Find run_phase using the hierarchy lookup
        run_phase = self._find_method_in_hierarchy(class_name, "run_phase")
        if not run_phase:
            print(f"    WARNING: No run_phase found for {class_name}")
            return

        # 2. Initialize FSM Slicing
        self.state_counter = 0
        start_state = self._create_state("S_RESET")
        start_state.is_reset_state = True

        entry_state = self._create_state("S_ENTRY")
        start_state.add_transition("default", entry_state)

        # 3. Run the Slicer (CFG Splitting)
        # Fix: 'run_phase' is a TaskDeclaration. Its contents are in '.items'
        active_state = entry_state
        if hasattr(run_phase, 'items'):
            for item in run_phase.items:
                active_state = self._slice_statement(item, active_state)

        # 4. Generate RTL Code
        self._emit_fsm_rtl(rtl_mod, start_state, f)

    # --- The Slicer (Core Logic) ---

    def _slice_block(self, statement_node, current_state):
        """
        Walks a block of statements. Appends actions to current_state.
        If a yield point is hit, creates a NEW state and returns it.
        """
        active_state = current_state

        # Handle Block (begin...end)
        if statement_node.kind == pyslang.BlockStatement:
            for item in statement_node.items:
                active_state = self._slice_statement(item, active_state)
            return active_state

        # Handle Single Statement
        else:
            return self._slice_statement(statement_node, active_state)

    def _slice_statement(self, stmt, current_state):
        # 0. Filter out UVM variable declarations and empty statements 
        # (Eliminates the "alu_item req;" leakage issue)
        if stmt.kind in [pyslang.SyntaxKind.DataDeclaration, 
                         pyslang.SyntaxKind.VariableDeclarationStatement, 
                         pyslang.SyntaxKind.EmptyStatement]:
            return current_state

        # 1. Expand Block Statements (begin ... end)
        if stmt.kind in [pyslang.SyntaxKind.SequentialBlockStatement, 
                         pyslang.SyntaxKind.StatementBlock]:
            active_state = current_state
            
            # Compatibility handling for different pyslang AST structure levels
            items = []
            if hasattr(stmt, 'items'): items = stmt.items
            elif hasattr(stmt, 'body') and hasattr(stmt.body, 'items'): items = stmt.body.items
            elif hasattr(stmt, 'block') and hasattr(stmt.block, 'items'): items = stmt.block.items
                
            for item in items:
                # Recursively process each item within the block
                active_state = self._slice_statement(item, active_state)
            return active_state

        # 2. Loop (forever)
        elif stmt.kind == pyslang.SyntaxKind.ForeverStatement:
            loop_head = self._create_state("S_LOOP_HEAD")
            current_state.add_transition("default", loop_head)
            
            # Slice the loop body
            loop_end = self._slice_statement(stmt.statement, loop_head)
            
            # Loop back transition
            loop_end.add_transition("default", loop_head)
            return self._create_state("S_UNREACHABLE")

        # 3. Handshake (get_next_item) -> Split into 3 states to match the Stimuli logic
        elif self._is_get_next_item(stmt):
            # State 1: S_REQ_ITEM (Initiate Request)
            req_state = self._create_state("S_REQ_ITEM")
            current_state.add_transition("default", req_state)
            
            req_state.add_action("req_valid = 1'b1;")
            req_state.add_action("rsp_ready = 1'b1;")
            req_state.add_action("constraint_id = 2'b0;") 
            req_state.add_action("lower_bound = 32'h0000_0000;")
            req_state.add_action("upper_bound = 32'hFFFF_FFFF;")
            
            # State 2: S_WAIT_RSP (Wait for Response)
            wait_rsp_state = self._create_state("S_WAIT_RSP")
            req_state.add_transition("!req_ready", req_state) # Loop if target is not ready
            req_state.add_transition("req_ready", wait_rsp_state)
            
            wait_rsp_state.add_action("req_valid = 1'b0;")
            wait_rsp_state.add_action("rsp_ready = 1'b1;")
            
            # State 3: S_GOT_ITEM (Fetch and Unpack Data)
            got_item_state = self._create_state("S_GOT_ITEM")
            wait_rsp_state.add_transition("!rsp_valid", wait_rsp_state) # Wait for computation completion
            wait_rsp_state.add_transition("rsp_valid", got_item_state)
            
            got_item_state.add_action("rsp_ready = 1'b0;")
            # Unpack flat data into internal registers (registers must be declared in the RTL emitter)
            got_item_state.add_action("next_req_op_reg = solved_data[17:16];")
            got_item_state.add_action("next_req_a_reg = solved_data[15:8];")
            got_item_state.add_action("next_req_b_reg = solved_data[7:0];")
            
            return got_item_state

        # 4. Do-While Loop (Wait for DUT completion)
        elif stmt.kind == pyslang.SyntaxKind.DoWhileStatement:
            wait_state = self._create_state("S_WAIT_DONE")
            current_state.add_transition("default", wait_state)
            
            # Extract condition (e.g., "!vif.done" -> "!vif_done")
            cond_str = str(stmt.condition).replace("vif.", "vif_").strip()
            next_state = self._create_state("S_AFTER_WAIT")
            
            # Per SV semantics: loop while condition is true, exit when false
            wait_state.add_transition(f"{cond_str}", wait_state)
            wait_state.add_transition(f"!({cond_str})", next_state)
            return next_state

        # 5. Timing Control (@posedge clk) -> Dynamically infer DRIVE_START and END
        elif stmt.kind == pyslang.SyntaxKind.TimingControlStatement or \
             (stmt.kind == pyslang.SyntaxKind.ExpressionStatement and "posedge" in str(stmt)):
            
            # Use a counter to precisely name the two clock edge wait states
            if not hasattr(self, 'posedge_count'): self.posedge_count = 0
            name = "S_DRIVE_START" if self.posedge_count == 0 else "S_DRIVE_END"
            self.posedge_count += 1
            
            next_state = self._create_state(name)
            current_state.add_transition("default", next_state) 
            return next_state

        # 6. Handshake (item_done)
        elif self._is_item_done(stmt):
            current_state.add_action("// seq_item_port.item_done() implied") 
            return current_state

        # 7. Standard Assignment Statements (Combinational Actions)
        else:
            code = str(stmt).strip()
            # Filter out inline comments and map variable names
            code = code.split("//")[0].strip()
            code = code.replace("vif.", "vif_").replace("req.", "req_").replace("<=", "=")
            
            if code and code != ';': # Ignore empty lines
                current_state.add_action(code)
            return current_state
    # --- Helpers ---

    def _create_state(self, base_name):
        exact_names = ["S_RESET", "S_ENTRY", "S_LOOP_HEAD", "S_REQ_ITEM", 
                       "S_WAIT_RSP", "S_GOT_ITEM", "S_DRIVE_START", 
                       "S_DRIVE_END", "S_WAIT_DONE"]
        
        if base_name in exact_names:
            name = base_name
        else:
            name = f"{base_name}_{self.state_counter}"
            self.state_counter += 1
            
        return FSMState(name)

    def _is_get_next_item(self, stmt):
        # Must be a standalone expression statement, not a Block containing it
        if stmt.kind != pyslang.SyntaxKind.ExpressionStatement: 
            return False
        return "get_next_item" in str(stmt)

    def _is_item_done(self, stmt):
        if stmt.kind != pyslang.SyntaxKind.ExpressionStatement: 
            return False
        return "item_done" in str(stmt)

    def _find_method_in_hierarchy(self, start_class_name, method_name):
        """
        Recursively searches up the inheritance chain using the unwrapped AST logic.
        """
        current_class_name = start_class_name

        while current_class_name:
            class_node = self._find_ast_node_in_registry(current_class_name)
            if not class_node:
                return None

            for item in class_node.items:
                if item.kind in [SyntaxKind.ClassMethodDeclaration,
                                 SyntaxKind.TaskDeclaration,
                                 SyntaxKind.FunctionDeclaration]:

                    # Unwrap the declaration
                    decl = item.declaration if item.kind == SyntaxKind.ClassMethodDeclaration else item

                    actual_name = None
                    if hasattr(decl, 'prototype') and hasattr(decl.prototype, 'name'):
                        name = decl.prototype.name
                        if name.kind == SyntaxKind.IdentifierName:
                            actual_name = name.identifier.valueText

                    if actual_name == method_name:
                        return decl # Found it!

            # Move up the hierarchy if not found
            current_class_name = self._get_base_class_name(class_node)

        return None

    def _get_base_class_name(self, class_node):
        if not class_node.baseClass: return None
        # Safely extract the parent class name
        return self._robust_type_name(class_node.baseClass.type)

    def _get_base_class_name(self, class_node):
        """
        Extracts the name of the parent class from the 'extends' clause.
        """
        if not class_node.baseClass:
            return None

        # Reuse your type name extractor from Phase 1
        # Assumes format: class Child extends Parent;
        return self._robust_type_name(class_node.baseClass.type)

    def _find_ast_node_in_registry(self, type_name):
        """
        Helper to look up any class type in the registry.
        """
        for bucket in [self.registry.drivers, self.registry.monitors,
                       self.registry.agents, self.registry.envs, self.registry.tests]:
            if type_name in bucket:
                return bucket[type_name]
        return None

    # ... inside Phase4Synthesizer class ...
    # Helper to clean up complex type names (e.g. "uvm_driver#(item)" -> "uvm_driver")
    def _robust_type_name(self, type_node):
         name = str(type_node)
         if "#" in name: # Remove parameterization for lookup
             return name.split("#")[0].strip()
         return name

    # --- RTL Emitter ---

    def _emit_fsm_rtl(self, rtl_mod, start_state, f):
        # Flatten Graph to list
        all_states = set()
        queue = [start_state]
        while queue:
            s = queue.pop(0)
            if s in all_states: continue
            all_states.add(s)
            for _, target in s.transitions:
                queue.append(target)

        state_list = list(all_states)
        state_enum_names = [s.name for s in state_list]

        print(f"\n  [Code Gen] Writing Logic for {rtl_mod.name}")

        # 1. State Enum
        f.write(f"    typedef enum logic [{len(state_list).bit_length()-1}:0] {{\n")
        f.write(f"      {', '.join(state_enum_names)}\n")
        f.write(f"    }} state_t;\n")
        f.write("    state_t state, next_state;\n")

        # 2. Sequential Block
        f.write("\n    always_ff @(posedge clk or negedge rst_n) begin\n")
        f.write(f"      if (!rst_n) state <= {start_state.name};\n")
        f.write("      else state <= next_state;\n")
        f.write("    end\n")

        # 3. Combinational Block
        f.write("\n    always_comb begin\n")
        f.write("      next_state = state;\n")
        f.write("      // Default Output assignments to 0 or hold\n")
        # (In a real tool, you'd track default values for all outputs)

        f.write("      case (state)\n")
        for s in state_list:
            f.write(f"        {s.name}: begin\n")
            # Actions
            for action in s.actions:
                f.write(f"          {action}\n")

            # Transitions
            if not s.transitions:
                pass # Terminal state
            elif len(s.transitions) == 1 and s.transitions[0][0] == "default":
                f.write(f"          next_state = {s.transitions[0][1].name};\n")
            else:
                # Priority Logic
                first = True
                for cond, target in s.transitions:
                    if cond == "default":
                        # Should be last
                        f.write(f"          else next_state = {target.name};\n")
                    else:
                        prefix = "if" if first else "else if"
                        f.write(f"          {prefix} ({cond}) next_state = {target.name};\n")
                        first = False
            f.write("        end\n")
        f.write("      endcase\n")
        f.write("    end\n")


# Part 5
class Assembler:
    def __init__(self, rtl_modules, hierarchy_root, registry):
        self.modules = rtl_modules
        self.root = hierarchy_root
        self.registry = registry

    def run(self, output_filename="uvm_synthesized.sv"):
        print(f"Starting Phase 5: Code Assembly into '{output_filename}'...")

        # Open the single file once
        with open(output_filename, "w") as f:
            f.write("// ====================================================\n")
            f.write("// Auto-Generated UVM to RTL Synthesis Output\n")
            f.write("// ====================================================\n\n")

            # 1. Write the Leaf Modules (Drivers/Monitors with FSMs)
            self._write_leaf_modules(f)

            # 2. Write the Container Modules (Agents/Envs/Test)
            self._write_container_modules(f)

            # 3. Write the Top-Level System Wrapper
            self._write_top_level_wrapper(f)

        print("Assembly complete.")

    def _write_leaf_modules(self, f):
        """
        Writes the driver and monitor modules to the shared file.
        """
        for mod_name, mod_def in self.modules.items():
            synthesizer = Synthesizer(registry, rtl_modules)

            if mod_name in self.registry.drivers:
                print(f"  [Write] Appending module {mod_def.name}...")

                f.write(f"// --- Leaf Module: {mod_def.name} ---\n")
                f.write(f"module {mod_def.name} (\n")
                self._write_ports(f, mod_def.ports)
                f.write(");\n\n")

                # FSM Code Injection Point
                synthesizer.run(f)
                # f.write("  // For now, generating placeholder logic\n")
                # f.write("  always_comb req_ready = 1'b1;\n\n")

                f.write("endmodule\n\n")

    def _write_container_modules(self, f):
        """
        Writes Agents, Envs, and Test modules to the shared file.
        """
        queue = [self.root]
        processed_types = set()

        while queue:
            node = queue.pop(0)

            if node.type_name not in processed_types and node.type_name not in self.registry.drivers:
                self._write_container_module(f, node)
                processed_types.add(node.type_name)

            for child in node.children:
                queue.append(child)

    def _write_container_module(self, f, node):
        mod_def = self.modules.get(node.type_name)
        if not mod_def: return

        print(f"  [Write] Appending module {mod_def.name}...")

        f.write(f"// --- Container Module: {mod_def.name} ---\n")
        f.write(f"module {mod_def.name} (\n")
        self._write_ports(f, mod_def.ports)
        f.write(");\n\n")

        # 1. Declare Internal Wires
        if mod_def.wires:
            for wire in mod_def.wires:
                f.write(f"  {wire}\n")
            f.write("\n")

        # 2. Instantiate Children
        for child in node.children:
            if "uvm_sequencer" in child.type_name:
                self._write_stimuli_generator_instantiation(f, child)
            else:
                self._write_child_instantiation(f, child)

        f.write("endmodule\n\n")

    def _write_child_instantiation(self, f, child_node):
        child_module_name = f"{child_node.type_name}_rtl"
        inst_name = f"u_{child_node.name}"

        f.write(f"  {child_module_name} {inst_name} (\n")
        f.write(f"    .clk(clk),\n")
        f.write(f"    .rst_n(rst_n),\n")
        f.write(f"    // Interface Pass-through\n")
        f.write(f"    .vif_start(vif_start),\n")
        f.write(f"    .vif_op(vif_op),\n")
        f.write(f"    .vif_done(vif_done),\n")

        if child_node.type_name in self.registry.drivers:
            f.write(f"    // Handshake Connections\n")
            f.write(f"    .req_valid(w_valid),\n")
            f.write(f"    .req_ready(w_ready),\n")
            f.write(f"    .req_op(w_op),\n")

        f.write(f"    .vif_result(vif_result)\n")
        f.write("  );\n\n")

    def _write_stimuli_generator_instantiation(self, f, node):
        f.write(f"  // Replaced uvm_sequencer '{node.name}' with Hardware Generator\n")
        f.write(f"  stim_gen_alu {node.name} (\n")
        f.write(f"    .clk(clk),\n")
        f.write(f"    .rst_n(rst_n),\n")
        f.write(f"    .req_valid(w_valid),\n")
        f.write(f"    .req_ready(w_ready),\n")
        f.write(f"    .req_op(w_op)\n")
        f.write("  );\n\n")

    def _write_top_level_wrapper(self, f):
        """
        Generates the final 'tb_top_synth' module.
        """
        print("  [Write] Appending tb_top_synth...")

        f.write("// --- Top-Level Wrapper: tb_top_synth ---\n")
        f.write("module tb_top_synth (\n")
        f.write("  input wire clk,\n")
        f.write("  input wire rst_n\n")
        f.write(");\n\n")

        f.write("  // 1. Wires to bridge Synthesized UVM <-> DUT\n")
        f.write("  wire start;\n")
        f.write("  wire [1:0] op;\n")
        f.write("  wire [7:0] a, b;\n")
        f.write("  wire [7:0] result;\n")
        f.write("  wire done;\n\n")

        f.write("  // 2. Instantiate the original DUT\n")
        f.write("  alu_dut dut (\n")
        f.write("    .clk(clk),\n")
        f.write("    .rst_n(rst_n),\n")
        f.write("    .start(start),\n")
        f.write("    .op(op),\n")
        f.write("    .a(a),\n")
        f.write("    .b(b),\n")
        f.write("    .result(result),\n")
        f.write("    .done(done)\n")
        f.write("  );\n\n")

        f.write("  // 3. Instantiate the Synthesized UVM Root (alu_test_rtl)\n")
        f.write("  alu_test_rtl uvm_top (\n")
        f.write("    .clk(clk),\n")
        f.write("    .rst_n(rst_n),\n")
        f.write("    .vif_start(start),\n")
        f.write("    .vif_op(op),\n")
        f.write("    .vif_a(a),\n")
        f.write("    .vif_b(b),\n")
        f.write("    .vif_result(result),\n")
        f.write("    .vif_done(done)\n")
        f.write("  );\n\n")

        f.write("endmodule\n")

    def _write_ports(self, f, ports):
        lines = []
        for p in ports:
            width_str = f"[{p.width}:0]" if p.width != "1" and p.width != "0" else ""
            lines.append(f"  {p.direction} logic {width_str} {p.name}")
        f.write(",\n".join(lines))
        f.write("\n")


# --- Execution ---

# Part 1
# 1. Create AST Tree (Using the file content you provided)
file_path = "alu_design_ver.sv"
tree = pyslang.SyntaxTree.fromFile(file_path)

# 2. Run Phase 1 Classifier
classifier = Classifier(tree)
registry = classifier.run()

# 3. Output Results
registry.summary()

# Part 2
builder = Builder(registry)

# 2. Run Virtual Elaboration
# We know 'alu_test' is the root because it extends uvm_test
root_type = list(registry.tests.keys())[0] # e.g., "alu_test"
hierarchy_root = builder.build(root_type)

# 3. Visualize
print("\n--- Virtual Elaboration Tree ---")
hierarchy_root.print_tree()


# Part 3
connector = Connector(registry, hierarchy_root)
rtl_modules = connector.run()

# Output Results
print("\n--- Synthesized RTL Interfaces ---")
for mod_name, mod_def in rtl_modules.items():
    print(f"Module: {mod_def.name}")
    for p in mod_def.ports:
        print(f"  {p}")
    if mod_def.wires:
        print(f"  Internal Wires: {len(mod_def.wires)} defined")

# Part 4 runs inside phase 5

# Part 5
assembler = Assembler(rtl_modules, hierarchy_root, registry)
assembler.run()
