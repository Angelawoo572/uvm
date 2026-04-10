import json
import os
import glob
import re

class HierarchyNode:
    def __init__(self, name, type_name, parent=None):
        self.name = name            
        self.type_name = type_name  
        self.parent = parent
        self.children = []          
        self.configs = []           

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

import json

# --- Phase 1: Classification ---
class UVMRegistry:
    def __init__(self):
        self.drivers = {}        
        self.monitors = {}
        self.agents = {}
        self.envs = {}
        self.tests = {}
        self.seq_items = {}      
        self.structs = {}        # Holds the flattened packed structs
        self.interfaces = {}     

    def summary(self):
        print("--- Classification Summary ---")
        print(f"Drivers:    {list(self.drivers.keys())}")
        print(f"Monitors:   {list(self.monitors.keys())}")
        print(f"Agents:     {list(self.agents.keys())}")
        print(f"Envs:       {list(self.envs.keys())}")
        print(f"Tests:      {list(self.tests.keys())}")
        print(f"Seq Items:  {list(self.seq_items.keys())}")
        print(f"Structs:    {list(self.structs.keys())}")
        print()
        for key, value in self.structs.items():
            print(f"{key}: {value}")
        print("------------------------------")


class Classifier:
    def __init__(self, json_data_list):
        self.json_data_list = json_data_list
        self.registry = UVMRegistry()
        self._unclassified_classes = {} # Temp storage for Pass 1

    def run(self):
        # PASS 1: Read all JSON nodes and categorize what we can immediately
        for data in self.json_data_list:
            # Handle the new format: {"components": [...]}
            components = data.get("components", [])
            # Fallback for old format: {"component": {...}}
            if not components and "component" in data:
                components = [data["component"]]
                
            for comp in components:
                self._classify_class(comp)

            # Interface ingestion
            if "interface" in data:
                self._ingest_interface(data["interface"])

        # PASS 2: Resolve inheritance and build packed structs
        self._resolve_structs()
        
        return self.registry

    def _classify_class(self, comp_dict):
        class_name = comp_dict.get("name")
        base_type = comp_dict.get("base_type", "")

        if not base_type: 
            return

        # Immediate classification for core UVM types
        if "uvm_driver" in base_type:
            self.registry.drivers[class_name] = comp_dict
        elif "uvm_monitor" in base_type or "monitor" in class_name.lower():
            self.registry.monitors[class_name] = comp_dict
        elif "uvm_agent" in base_type:
            self.registry.agents[class_name] = comp_dict
        elif "uvm_env" in base_type:
            self.registry.envs[class_name] = comp_dict
        elif "uvm_test" in base_type:
            self.registry.tests[class_name] = comp_dict
        elif "uvm_sequence_item" in base_type:
            self.registry.seq_items[class_name] = comp_dict
        elif "interface" in base_type:
            self.registry.interface = comp_dict
        else:
            # It might be a custom type extending another custom type (e.g., reset_req_item extends req_item)
            # Store it temporarily. We will resolve it in Pass 2.
            self._unclassified_classes[class_name] = comp_dict

    def _resolve_structs(self):
        """
        Pass 2: Figures out which unclassified classes are actually sequence items,
        and flattens their variable declarations into struct fields.
        """
        # 1. Identify all subclasses of known sequence items iteratively
        changed = True
        while changed:
            changed = False
            for cname, cdict in list(self._unclassified_classes.items()):
                btype = cdict.get("base_type")
                if btype in self.registry.seq_items:
                    # Found a child of a sequence item (e.g., reset_req_item)
                    self.registry.seq_items[cname] = cdict
                    del self._unclassified_classes[cname]
                    changed = True
                    
        # 2. Build the flattened structs for every identified sequence item
        for sname in self.registry.seq_items:
            fields = self._get_inherited_fields(sname)
            
            # Only generate a struct if there are actual variables to pack
            if fields:
                struct_name = f"{sname}_s"
                self.registry.structs[struct_name] = {
                    "name": struct_name,
                    "fields": fields
                }

    def _get_inherited_fields(self, class_name):
        """
        Recursively climbs the inheritance tree to gather all variable declarations.
        """
        if class_name not in self.registry.seq_items:
            return []
            
        cdict = self.registry.seq_items[class_name]
        btype = cdict.get("base_type")
        
        fields = []
        
        # 1. Get parent's fields first (so they appear first in the packed struct)
        if btype and btype != "uvm_sequence_item":
            fields.extend(self._get_inherited_fields(btype))
            
        # 2. Get this class's own fields
        for member in cdict.get("members", []):
            if member.get("type") == "variable_declaration":
                
                # Check for nested sequence items (like full_item having req_item and rsp_item)
                data_type = member.get("data_type")
                
                # If the variable type is another known sequence item, map it to its struct type
                if data_type in self.registry.seq_items:
                    mapped_type = f"{data_type}_s"
                else:
                    mapped_type = data_type
                
                fields.append({
                    "name": member.get("name"),
                    "data_type": mapped_type,
                    "original_line": member.get("original_line", "")
                })
                
        return fields

    def _ingest_interface(self, interface_dict):
        if_name = interface_dict.get("name")
        self.registry.interfaces[if_name] = {
            'signals': [], 'modports': {}, 
            'original_line': interface_dict.get("original_line", "")
        }

        for member in interface_dict.get("members", []):
            if member.get("type") == "variable_declaration":
                self.registry.interfaces[if_name]['signals'].append(member)
            elif member.get("type") == "clocking_block":
                cb_name = member.get("name") 
                self.registry.interfaces[if_name]['modports'][cb_name] = {
                    "name": cb_name, "converted_from": "clocking_block",
                    "signals": member.get("signals", []),
                    "original_line": member.get("original_line", "")
                }
            elif member.get("type") == "modport":
                self.registry.interfaces[if_name]['modports'][member.get("name")] = member

# --- Phase 2: Virtual Elaboration ---
class Builder:
    def __init__(self, registry):
        self.registry = registry
        self.root_node = None

    def build(self, root_class_name):
        print(f"Starting Virtual Elaboration at root: {root_class_name}")
        self.root_node = HierarchyNode("uvm_test_top", root_class_name)
        self._elaborate_node(self.root_node)
        return self.root_node

    def _elaborate_node(self, current_node):
        class_dict = self._find_ast_by_type(current_node.type_name)
        if not class_dict: return
        build_phase = self._find_method(class_dict, "build_phase")
        if not build_phase: return

        self._scan_build_phase(build_phase, current_node, class_dict)
        for child in current_node.children:
            self._elaborate_node(child)

    def _find_ast_by_type(self, type_name):
        for bucket in [self.registry.tests, self.registry.envs,
                       self.registry.agents, self.registry.drivers, self.registry.monitors]:
            if type_name in bucket: return bucket[type_name]
        return None

    def _find_method(self, class_dict, method_name):
        for member in class_dict.get("members", []):
            if member.get("type") in ["function", "task"] and member.get("name") == method_name:
                return member
        return None

    def _scan_build_phase(self, method_dict, current_hierarchy_node, class_dict):
        children = method_dict.get("children", [])
        for statement in children:
            if statement.get("type") == "assignment":
                rhs_str = statement.get("rhs", "")
                if "create" in rhs_str and "type_id" in rhs_str:
                    inst_var_name = statement.get("lhs", "").strip()
                    inst_type = self._lookup_member_type(class_dict, inst_var_name)
                    if inst_type:
                        new_child = HierarchyNode(inst_var_name, inst_type)
                        current_hierarchy_node.add_child(new_child)

            elif statement.get("type") == "method_call":
                method = statement.get("method", "")
                caller = statement.get("caller", "")
                if "set" in method and "uvm_config_db" in caller:
                    current_hierarchy_node.configs.append(str(statement))

    def _lookup_member_type(self, class_dict, var_name):
        for member in class_dict.get("members", []):
            if member.get("type") == "variable_declaration" and member.get("name") == var_name:
                return member.get("data_type")
        return None

# --- Phase 3 RTL Data Structure ---
class RTLModuleDefinition:
    def __init__(self, name):
        self.name = name
        self.parameters = [] 
        self.ports = []
        self.interface_ports = [] 
        self.wires = []

    def add_parameter(self, param_type, name, default_val):
        self.parameters.append({"type": param_type, "name": name, "default": default_val})

    # UPDATED: Added data_type with "logic" as default
    def add_port(self, name, direction, width="", data_type="logic"):
        if not any(p["name"] == name for p in self.ports):
            self.ports.append({
                "name": name, 
                "direction": direction, 
                "width": width, 
                "data_type": data_type # NEW
            })

    def add_interface_port(self, if_name, modport, port_name):
        if not any(p["name"] == port_name for p in self.interface_ports):
            self.interface_ports.append({"if_name": if_name, "modport": modport, "name": port_name})

# --- Phase 3: Netlist Building ---
class NetlistBuilder:
    def __init__(self, registry, hierarchy_root):
        self.registry = registry
        self.root = hierarchy_root
        self.modules = {} 
        # Removed self.virtual_config_db entirely

    def run(self):
        print("Starting Phase 3: Netlist Building...")
        # config_db resolution is completely removed!
        self._synthesize_leafs(self.root)
        self._synthesize_containers(self.root)
        return self.modules
    
    def _synthesize_leafs(self, node):
        for child in node.children:
            self._synthesize_leafs(child)

        if node.type_name in self.registry.drivers or node.type_name in self.registry.monitors:
            rtl_mod = RTLModuleDefinition(f"{node.type_name}_rtl")
            rtl_mod.add_parameter("int", "DATA_WIDTH", "32")
            rtl_mod.add_parameter("int", "ADDR_WIDTH", "16")
            rtl_mod.add_port("clk", "input")
            rtl_mod.add_port("rst_n_sys", "input") 

            class_dict = self._find_class_dict(node.type_name)
            vif_info = None
            
            if class_dict:
                for member in class_dict.get("members", []):
                    if member.get("type") == "virtual_interface":
                        raw_if_type = member.get("interface_type", "alu_if")
                        var_name = member.get("name", "vif")
                        
                        parts = raw_if_type.split('.')
                        if_name = parts[0]
                        modport = parts[1] if len(parts) > 1 else ("drv_cb" if node.type_name in self.registry.drivers else "mon_cb")
                        
                        vif_info = {'if_name': if_name, 'modport': modport, 'var_name': var_name}
                        break
            
            if not vif_info:
                modport = "drv_cb" if node.type_name in self.registry.drivers else "mon_cb"
                vif_info = {'if_name': 'alu_if', 'modport': modport, 'var_name': 'vif'}
            
            node.vif_def = vif_info
            rtl_mod.add_interface_port(node.vif_def['if_name'], node.vif_def['modport'], node.vif_def['var_name'])

            # Pass the class_dict to the port generators so they can scan the AST
            if node.type_name in self.registry.drivers:
                self._add_stimuli_handshake_ports(rtl_mod, class_dict)
            elif node.type_name in self.registry.monitors:
                self._add_monitor_ports(rtl_mod, class_dict)

            self.modules[node.type_name] = rtl_mod

    def _synthesize_containers(self, node):
        if node.type_name in self.registry.drivers or node.type_name in self.registry.monitors:
            return

        for child in node.children:
            self._synthesize_containers(child)

        rtl_mod = RTLModuleDefinition(f"{node.type_name}_rtl")
        rtl_mod.add_parameter("int", "DATA_WIDTH", "32")
        rtl_mod.add_parameter("int", "ADDR_WIDTH", "16")

        rtl_mod.add_port("clk", "input")
        rtl_mod.add_port("rst_n_sys", "input")

        descendant_driver = self._find_descendant_by_bucket(node, self.registry.drivers)
        descendant_mon = self._find_descendant_by_bucket(node, self.registry.monitors)
        
        if descendant_driver and descendant_driver.type_name in self.modules:
            self._bubble_ports(rtl_mod, self.modules[descendant_driver.type_name])
        
        if descendant_mon and descendant_mon.type_name in self.modules:
            self._bubble_ports(rtl_mod, self.modules[descendant_mon.type_name])

        if "agent" not in node.type_name.lower(): 
            rtl_mod.add_port("req_seed_load_ext", "input")
            rtl_mod.add_port("seed_ext", "input", "31")

        self._analyze_connections(node, rtl_mod)
        self.modules[node.type_name] = rtl_mod
    
    def _find_descendant_by_bucket(self, node, registry_bucket):
        for child in node.children:
            if child.type_name in registry_bucket: return child
            found = self._find_descendant_by_bucket(child, registry_bucket)
            if found: return found
        return None
    
    def _bubble_ports(self, container_rtl, leaf_rtl):
        for port in leaf_rtl.ports:
            # Bubbles up the mon_out struct automatically via "mon_" prefix match
            if port["name"].startswith("mon_") or "seed" in port["name"]:
                container_rtl.add_port(port["name"], port["direction"], port["width"], port.get("data_type", "logic"))
        
        for if_port in leaf_rtl.interface_ports:
            container_rtl.add_interface_port(if_port["if_name"], if_port["modport"], if_port["name"])

    def _add_stimuli_handshake_ports(self, rtl_mod, class_dict):
        # 1. Base protocol ports
        rtl_mod.add_port("req_valid", "output")
        rtl_mod.add_port("req_ready", "input")
        rtl_mod.add_port("lower_bound", "output", "31")
        rtl_mod.add_port("upper_bound", "output", "31")
        rtl_mod.add_port("rsp_ready", "output")
        rtl_mod.add_port("rsp_valid", "input")

        run_phase = self._find_method(class_dict, "run_phase")
        if not run_phase: return

        # Helper to lookup a variable's data_type
        def get_var_type(var_name):
            # Check local run_phase variables
            for stmt in run_phase.get("children", []):
                if stmt.get("type") == "variable_declaration" and stmt.get("name") == var_name:
                    return stmt.get("data_type")
            # Check global class members
            for member in class_dict.get("members", []):
                if member.get("type") == "variable_declaration" and member.get("name") == var_name:
                    return member.get("data_type")
            return None

        # 2. Recursively scan the run_phase AST for get_next_item and item_done
        def scan_children(statements):
            print("called")
            for stmt in statements:
                if stmt.get("type") == "method_call":
                    method = stmt.get("method", "")
                    args = stmt.get("arguments", [])
                    
                    if "get_next_item" in method and args:
                        var_name = args[0]
                        v_type = get_var_type(var_name)
                        if v_type:
                            rtl_mod.add_port(var_name, "input", data_type=f"{v_type}_s")
                            
                    elif "item_done" in method and args:
                        var_name = args[0]
                        v_type = get_var_type(var_name)
                        if v_type:
                            rtl_mod.add_port(var_name, "output", data_type=f"{v_type}_s")
                
                # Recurse into nested blocks (e.g., forever loops, ifs)
                if "children" in stmt:
                    scan_children(stmt["children"])

        scan_children(run_phase.get("children", []))

    def _add_monitor_ports(self, rtl_mod, class_dict):
        rtl_mod.add_port("mon_valid", "output")
        
        # We need to find the variable that holds the sequence item
        target_var = "mon_out" # Fallbacks
        target_type = "logic"
        
        # Helper to find any variable whose type matches a known sequence item
        def find_seq_item_var(statements):
            for stmt in statements:
                if stmt.get("type") == "variable_declaration":
                    if stmt.get("data_type") in self.registry.seq_items:
                        return stmt.get("name"), stmt.get("data_type")
                elif stmt.get("type") == "loop":
                    return find_seq_item_var(stmt.get("children"))
                elif stmt.get("type") == "if":
                    name, dtype = find_seq_item_var(stmt.get("true_branch"))
                    if "false_branch" in stmt:
                        name, dtype = find_seq_item_var(stmt.get("false_branch"))
                    return name, dtype
            return None, None

        # 1. Check class members
        name, dtype = find_seq_item_var(class_dict.get("members", []))
        
        # 2. Check local variables in run_phase if not found in members
        if not name:
            run_phase = self._find_method(class_dict, "run_phase")
            if run_phase:
                name, dtype = find_seq_item_var(run_phase.get("children", []))
                
        # 3. Add the port using the dynamically discovered names
        if name and dtype:
            target_var = name
            target_type = f"{dtype}_s"
            
        rtl_mod.add_port(target_var, "output", data_type=target_type)

    def _analyze_connections(self, container_node, rtl_mod):
        driver_inst = None
        sequencer_inst = None

        for child in container_node.children:
            if child.type_name in self.registry.drivers:
                driver_inst = child
            if "uvm_sequencer" in child.type_name:
                sequencer_inst = child

        if driver_inst and sequencer_inst:
            rtl_mod.wires.append("wire w_valid;")
            rtl_mod.wires.append("wire w_ready;")
            
            # Look at the synthesized driver to declare the matching internal structs
            driver_rtl = self.modules.get(driver_inst.type_name)
            if driver_rtl:
                for port in driver_rtl.ports:
                    # If it is a struct port (not logic), create a matching internal wire
                    if port.get("data_type", "logic") != "logic" and port.get("data_type", "").endswith("_s"):
                        rtl_mod.wires.append(f"{port['data_type']} w_{port['name']};")
    
    def _find_class_dict(self, type_name):
        for bucket in [self.registry.drivers, self.registry.monitors,
                       self.registry.agents, self.registry.envs, self.registry.tests]:
            if type_name in bucket: 
                return bucket[type_name]
        return None
    
    def _find_method(self, class_dict, method_name):
        """
        Searches the members of a JSON class dictionary for a specific task or function.
        """
        if not class_dict:
            return None
            
        for member in class_dict.get("members", []):
            # Check if the member is a task or function and matches the requested name
            if member.get("type") in ["task", "function"] and member.get("name") == method_name:
                return member
                
        return None
    

import re

class BehavioralSynthesizer:
    """
    Phase 4: Scans the run_phase of Drivers and Monitors to build hardware behaviors.
    Detects sequence item usage to automatically generate struct ports and handshakes.
    """
    def __init__(self, registry, modules):
        self.registry = registry
        self.modules = modules

    def run(self):
        print("Starting Phase 4: Behavioral Synthesis...")
        
        for name, rtl_mod in self.modules.items():
            if name in self.registry.drivers:
                self._synthesize_driver(name, rtl_mod)
            elif name in self.registry.monitors:
                self._synthesize_monitor(name, rtl_mod)
                
        return self.modules

    def _find_method_in_hierarchy(self, class_dict, method_name):
        for member in class_dict.get("members", []):
            if member.get("type") in ["task", "function"] and member.get("name") == method_name:
                return member
        return None

    # ==========================================
    # Driver Synthesis
    # ==========================================
    def _synthesize_driver(self, name, rtl_mod):
        print(f"  [Synth FSM] Building Driver logic for: {name}")
        class_dict = self.registry.drivers.get(name)
        run_phase = self._find_method_in_hierarchy(class_dict, "run_phase")
        if not run_phase:
            return

        # 1. Scan for the transaction variable (e.g., req_item req;)
        req_type = None
        req_var = None
        has_get_next_item = False
        has_item_done = False

        for stmt in run_phase.get("children", []):
            req_type, req_var = self._find_variable_declaration(stmt)
            if req_type:
                break # Found the main transaction item

        # Hack for Python 3 scoping in nested functions
        has_get_next_item = True 
        has_item_done = True 

        # 2. Extract behavior lines (No variable replacement needed, using AST)
        drive_lines = self._extract_behavior_lines(run_phase.get("children", []))

        # 3. Emit Driver RTL
        self._emit_driver_rtl(rtl_mod, drive_lines, has_item_done)

    def _emit_driver_rtl(self, rtl_mod, drive_lines, has_item_done):
        # Enum Definition
        enum_def = """
typedef enum logic [2:0] {
  S_RESET, 
  S_REQ_ITEM, 
  S_WAIT_RSP, 
  S_DRIVE,
  S_RESPOND
} state_t;

state_t state, next_state;"""
        rtl_mod.wires.append(enum_def)

        # Combinational FSM Logic
        comb_logic = """
always_comb begin
  // Default assignments
  next_state = state;
  req_valid  = 1'b0;
  rsp_ready  = 1'b0;

  case (state)
    S_RESET: next_state = S_REQ_ITEM;

    S_REQ_ITEM: begin
      req_valid = 1'b1;
      if (req_ready) next_state = S_WAIT_RSP;
    end

    S_WAIT_RSP: begin
      rsp_ready = 1'b1;
      if (rsp_valid) next_state = S_DRIVE;
    end

    S_DRIVE: begin
      next_state = S_REQ_ITEM; 
    end

    default: next_state = S_RESET;
  endcase
end"""
        rtl_mod.wires.append(comb_logic)

        # Sequential Logic (Data Capture & Drive)
        # Note: The temp <= req logic has been completely removed
        ff_logic = [
            "always_ff @(posedge clk or negedge rst_n_sys) begin",
            "  if (!rst_n_sys) begin",
            "    state <= S_RESET;",
            "  end else begin",
            "    state <= next_state;",
            "    ",
            "    if (state == S_DRIVE) begin"
        ]
        
        # Inject the extracted lines synthesized from JSON
        for line in drive_lines:
            ff_logic.append(f"      {line}")
            
        ff_logic.append("    end")
        ff_logic.append("  end")
        ff_logic.append("end")

        rtl_mod.wires.append("\n".join(ff_logic))

    # ==========================================
    # Monitor Synthesis
    # ==========================================
    def _synthesize_monitor(self, name, rtl_mod):
        print(f"  [Synth FSM] Building Monitor logic for: {name}")
        class_dict = self.registry.monitors.get(name)
        run_phase = self._find_method_in_hierarchy(class_dict, "run_phase")
        if not run_phase:
            return

        mon_type = None
        mon_var = None

        # Find the sequence item variable (e.g., 'req')
        for stmt in run_phase.get("children", []):
            mon_type, mon_var = self._find_variable_declaration(stmt)
            if mon_type:
                break

        # Extract Lines (Pass a flag so the extractor knows we are in a monitor)
        capture_lines = self._extract_behavior_lines(run_phase.get("children", []), is_monitor=True)

        # Emit Monitor RTL
        ff_logic = [
            "always_ff @(posedge clk or negedge rst_n_sys) begin",
            "  if (!rst_n_sys) begin",
            "    mon_valid <= 1'b0;"
        ]
        
        # Dynamically reset the struct port
        if mon_var:
            ff_logic.append(f"    {mon_var} <= '0;")
            
        ff_logic.extend([
            "  end else begin",
            "    mon_valid <= 1'b0; // Default to 0, pulses high on write()"
        ])

        # Inject the lines extracted from the AST
        for line in capture_lines:
            ff_logic.append(f"    {line}")

        ff_logic.append("  end")
        ff_logic.append("end")

        rtl_mod.wires.append("\n".join(ff_logic))

    # ==========================================
    # AST Traversal Helpers
    # ==========================================
    def _find_variable_declaration(self, stmt):
        if stmt.get("type") == "variable_declaration":
            if "req" in stmt.get("name") or "item" in stmt.get("name"):
                return stmt.get("data_type"), stmt.get("name")
        
        for child in stmt.get("children", []):
            t, v = self._find_variable_declaration(child)
            if t: return t, v
            
        return None, None

    def _has_method_call(self, stmt, target_method):
        if stmt.get("type") == "method_call" and target_method in stmt.get("method", ""):
            return True
        for child in stmt.get("children", []):
            if self._has_method_call(child, target_method):
                return True
        return False

    def _extract_behavior_lines(self, statements, is_monitor=False):
        """
        Recursively finds assignment and if statements.
        Builds the SV code directly from the JSON AST elements.
        Removes clocking block references (.drv_cb, .mon_cb).
        """
        lines = []
        for stmt in statements:
            stype = stmt.get("type")
            
            if stype == "assignment":
                lhs = stmt.get("lhs", "")
                rhs = stmt.get("rhs", "")
                
                # Strip out .drv_cb and .mon_cb
                lhs = re.sub(r'\.(drv_cb|mon_cb)', '', lhs)
                rhs = re.sub(r'\.(drv_cb|mon_cb)', '', rhs)
                
                # Force non-blocking assignment (<=) since this goes in an always_ff block
                lines.append(f"{lhs} <= {rhs};")
                
            elif stype == "if":
                cond = stmt.get("condition", "")
                # Strip out .drv_cb and .mon_cb from conditions
                cond = re.sub(r'\.(drv_cb|mon_cb)', '', cond)
                
                lines.append(f"if ({cond}) begin")
                if "true_branch" in stmt:
                    lines.extend(self._extract_behavior_lines(stmt.get("true_branch", []), is_monitor))
                elif "false_branch" in stmt:
                    lines.extend(self._extract_behavior_lines(stmt.get("false_branch", []), is_monitor))
                lines.append("end")
                
            elif stype == "loop":
                # Flatten loops out since they are handled by the always_ff boundary
                lines.extend(self._extract_behavior_lines(stmt.get("children", []), is_monitor))
                
            elif stype == "method_call":
                method = stmt.get("method", "")
                # Translate the software 'write' call into a hardware 'valid' pulse
                if is_monitor and "write" in method:
                    lines.append("mon_valid <= 1'b1;")
                
        return lines
    


class CodeAssembler:
    """
    Phase 5: Reads the drafted RTL modules and the UVM hierarchy tree,
    and writes out the final synthesizable SystemVerilog file.
    """
    def __init__(self, registry, hierarchy_root, modules, output_file="assembler_output_rtl.sv"):
        self.registry = registry
        self.root = hierarchy_root
        self.modules = modules
        self.output_file = output_file

    def run(self):
        print(f"--- Starting Phase 5: Code Assembly ---")
        
        with open(self.output_file, 'w') as f:
            f.write("// ====================================================\n")
            f.write("// Auto-Generated Synthesizable UVM Testbench\n")
            f.write("// ====================================================\n\n")

            self._write_interface_rtl(f, self.registry.interface)

            # 1. Write the Packed Structs (from Phase 1)
            self._write_structs(f)

            # 2. Write Leaf Modules (Drivers & Monitors)
            self._write_leaf_modules(f)

            # 3. Write Container Modules (Agents, Envs, Tests) via BFS
            self._write_container_modules(f)

            # 4. Write Top-Level Wrapper
            self._write_top_level(f)
            
        print(f"Success! SystemVerilog written to {self.output_file}")
    
    # ==========================================
    # STEP 1: Interface definition
    # ==========================================
    def _write_interface_rtl(self, f, itf_json):
        """
        Parses the itf.json dictionary and generates a synthesizable 
        SystemVerilog interface, converting clocking blocks to modports.
        """
        comp = itf_json
        name = comp.get("name", "itf")
        
        print(f"  [Assemble] Writing Interface: {name}")
        
        # 1. Format Parameters
        params = comp.get("parameters", [])
        param_strs = []
        for p in params:
            param_strs.append(f"  parameter {p['name']} = {p['default']}")
        joined_params = ',\n'.join(param_strs)
        param_block = f" #(\n{joined_params}\n)" if param_strs else ""
        
        # 2. Format Ports
        ports = comp.get("ports", [])
        port_strs = []
        for p in ports:
            port_strs.append(f"  {p['direction']} {p['type']} {p['name']}")
        joined_params2 = ',\n'.join(port_strs)
        port_block = f" (\n{joined_params2}\n);"
        
        # Write Header
        f.write(f"interface {name}{param_block}{port_block}\n\n")
        f.write("  // --- Internal Variables ---\n")
        
        # 3. Format Variable Declarations
        members = comp.get("members", [])
        for m in members:
            if m.get("type") == "variable_declaration":
                f.write(f"  {m['data_type']} {m['name']};\n")
                
        f.write("\n  // --- Modports (Converted from Clocking Blocks) ---\n")
        
        # 4. Transform Clocking Blocks to Modports
        for m in members:
            if m.get("type") == "clocking_block":
                cb_name = m.get("name")
                
                # It is standard practice to include the interface clock as an input in the modport
                modport_signals = ["input clk"] 
                
                # Dig into the children to find 'clocking_signals'
                for child in m.get("children", []):
                    if child.get("type") == "clocking_signals":
                        direction = child.get("direction")
                        for sig in child.get("signals", []):
                            # Map the direction directly from the clocking_signals block
                            modport_signals.append(f"{direction} {sig}")
                
                # Format with newlines for clean SV code
                formatted_sigs = ",\n    ".join(modport_signals)
                f.write(f"  modport {cb_name} (\n    {formatted_sigs}\n  );\n\n")
                
        f.write(f"endinterface : {name}\n\n")

    # ==========================================
    # STEP 1: Packed Structs
    # ==========================================
    def _write_structs(self, f):
        print("  [Assemble] Writing Packed Structs...")
        if not self.registry.structs:
            return

        f.write("// --- Packed Struct Definitions ---\n")
        for s_name, s_dict in self.registry.structs.items():
            f.write(f"typedef struct packed {{\n")
            for field in s_dict.get("fields", []):
                # E.g., "  logic [31:0] data_i;"
                f.write(f"  {field['data_type']} {field['name']};\n")
            f.write(f"}} {s_name};\n\n")

    # ==========================================
    # STEP 2: Leaf Modules
    # ==========================================
    def _write_leaf_modules(self, f):
        print("  [Assemble] Writing Leaf Modules...")
        for name, rtl_mod in self.modules.items():
            if name in self.registry.drivers or name in self.registry.monitors:
                f.write(f"// --- Leaf Module: {name}_rtl ---\n")
                self._write_module_header(f, rtl_mod)
                self._write_module_body(f, rtl_mod)
                f.write("endmodule\n\n")

    # ==========================================
    # STEP 3: Container Modules (BFS Traversal)
    # ==========================================
    def _write_container_modules(self, f):
        print("  [Assemble] Writing Container Modules...")
        
        queue = [self.root]
        visited_types = set() # Track by type to avoid duplicate module definitions

        while queue:
            node = queue.pop(0)

            is_leaf = node.type_name in self.registry.drivers or node.type_name in self.registry.monitors
            
            # If it's a container we haven't written yet
            if not is_leaf and node.type_name not in visited_types:
                visited_types.add(node.type_name)
                
                if node.type_name in self.modules:
                    rtl_mod = self.modules[node.type_name]

                    if ((not "uvm_sequencer" in node.type_name) and (not "cov" in node.type_name)):
                        f.write(f"// --- Container Module: {node.type_name}_rtl ---\n")
                        self._write_module_header(f, rtl_mod)
                        self._write_module_body(f, rtl_mod) # Writes internal wires
                        
                        # Instantiate children inside this container
                        for child in node.children:
                            if "uvm_sequencer" in child.type_name:
                                self._insert_stimuli_fsm(f, child)
                            else:
                                self._instantiate_child(f, child)

                        f.write("endmodule\n\n")

            # Add children to Queue
            for child in node.children:
                queue.append(child)

    # ==========================================
    # STEP 4: Top-Level Wrapper
    # ==========================================
    def _write_top_level(self, f):
        print("  [Assemble] Writing Top-Level Wrapper...")
        root_rtl_name = f"{self.root.type_name}_rtl"
        
        f.write("// --- Top-Level Wrapper: tb_synth ---\n")
        f.write("module tb_synth;\n")
        f.write("  logic clk;\n")
        f.write("  logic rst_n_sys;\n\n")
        
        f.write("  // Top-level extensions & monitor signals\n")
        f.write("  logic        req_seed_load_ext;\n")
        f.write("  logic [31:0] seed_ext;\n")
        f.write("  logic        mon_valid;\n")
        
        # Look up the struct type for mon_out if it exists
        mon_struct = "mon_data" # Fallback
        for mod in self.modules.values():
            for port in mod.ports:
                if port["name"] == "mon_out":
                    mon_struct = port.get("data_type", "mon_data")
        f.write(f"  {mon_struct} mon_out;\n\n")

        f.write("  // Clock generation\n")
        f.write("  initial begin\n")
        f.write("    clk = 0;\n")
        f.write("    forever #10 clk = ~clk;\n")
        f.write("  end\n\n")

        f.write("  // DUT Instance (Assuming standard hookups to vif)\n")
        f.write("  dut u_dut (\n")
        f.write("    .clk    (clk),\n")
        f.write("    .rst_n  (vif_inst.rst_n),\n")
        f.write("    .re     (vif_inst.re),\n")
        f.write("    .we     (vif_inst.we),\n")
        f.write("    .addr_i (vif_inst.addr_i),\n")
        f.write("    .data_i (vif_inst.data_i),\n")
        f.write("    .data_o (vif_inst.data_o)\n")
        f.write("  );\n\n")
        
        f.write(f"  // UVM Synthesized Hierarchy Root\n")
        f.write(f"  {root_rtl_name} u_uvm_top (\n")
        f.write("    .clk               (clk),\n")
        f.write("    .rst_n_sys         (rst_n_sys),\n")
        f.write("    .vif               (vif_inst),\n")
        f.write("    .req_seed_load_ext (req_seed_load_ext),\n")
        f.write("    .seed_ext          (seed_ext),\n")
        f.write("    .mon_valid         (mon_valid),\n")
        f.write("    .mon_out           (mon_out)\n")
        f.write("  );\n\n")

        f.write("  // System Reset Init\n")
        f.write("  initial begin\n")
        f.write("    rst_n_sys = 1'b0;\n")
        f.write("    req_seed_load_ext = 1'b0;\n")
        f.write("    seed_ext = 32'h0;\n")
        f.write("    repeat(5) @(posedge clk);\n")
        f.write("    rst_n_sys = 1'b1;\n")
        f.write("  end\n\n")
        f.write("endmodule\n")

    # ==========================================
    # Formatting Helpers
    # ==========================================
    def _write_module_header(self, f, rtl_mod):
        # 1. Module Name and Parameters
        f.write(f"module {rtl_mod.name} ")
        if rtl_mod.parameters:
            f.write("#(\n")
            for i, param in enumerate(rtl_mod.parameters):
                comma = "," if i < len(rtl_mod.parameters) - 1 else ""
                f.write(f"  parameter {param['type']} {param['name']} = {param['default']}{comma}\n")
            f.write(") ")
        f.write("(\n")

        # 2. Interface Ports (e.g., alu_if.drv_cb vif)
        total_ports = len(rtl_mod.interface_ports) + len(rtl_mod.ports)
        port_index = 0

        for ip in rtl_mod.interface_ports:
            comma = "," if port_index < total_ports - 1 else ""
            modport_str = f".{ip['modport']} " if ip['modport'] else " "
            f.write(f"  {ip['if_name']}{modport_str}{ip['name']}{comma}\n")
            port_index += 1

        # 3. Standard Ports
        for p in rtl_mod.ports:
            comma = "," if port_index < total_ports - 1 else ""
            width_str = f"[{p['width']}:0] " if p['width'] and p['width'] != "0" else ""
            data_type = p.get('data_type', 'logic')
            
            # Formatting nicely (e.g., "input  req_item_s  req")
            f.write(f"  {p['direction']:<6} {data_type:<10} {width_str}{p['name']}{comma}\n")
            port_index += 1

        f.write(");\n")

    def _write_module_body(self, f, rtl_mod):
        if not rtl_mod.wires:
            return
        for line in rtl_mod.wires:
            f.write(f"  {line}\n")
        f.write("\n")

    def _insert_stimuli_fsm(self, f, child_node):
        f.write(f"  // --- Stimuli Generator (Replaces {child_node.name}) ---\n")
        f.write("  stimuli_fsm_wide sqr_fsm (\n")
        f.write("    .clk(clk), .rst_n(rst_n_sys), .seed(seed_ext),\n")
        f.write("    .req_seed_load(req_seed_load_ext),\n")
        f.write("    .req_valid(w_valid), .req_ready(w_ready),\n")
        f.write("    .req(w_req), .rsp_valid(w_rsp_valid), .rsp_ready(w_rsp_ready)\n")
        f.write("  );\n\n")

    def _instantiate_child(self, f, child_node):
        child_rtl_name = f"{child_node.type_name}_rtl"
        inst_name = child_node.name
        
        # Simple heuristic: If it's a top-level container (Env/Test), use (.*)
        if "env" in child_rtl_name.lower() or "test" in child_rtl_name.lower():
            f.write(f"  {child_rtl_name} {inst_name} (.*);\n\n")
            return

        # Otherwise, map the ports specifically (for Agents -> Drv/Mon)
        f.write(f"  {child_rtl_name} {inst_name} (\n")
        
        if child_node.type_name in self.modules:
            child_mod = self.modules[child_node.type_name]
            total_ports = len(child_mod.interface_ports) + len(child_mod.ports)
            port_index = 0

            # Map Interface Ports
            for ip in child_mod.interface_ports:
                comma = "," if port_index < total_ports - 1 else ""
                # Map parent 'vif' to child 'vif.drv_cb'
                modport_str = f".{ip['modport']}" if ip['modport'] else ""
                f.write(f"    .{ip['name']}(vif{modport_str}){comma}\n")
                port_index += 1

            # Map Standard Ports
            for p in child_mod.ports:
                comma = "," if port_index < total_ports - 1 else ""
                port_name = p['name']
                
                # Map the driver handshake ports to the agent's internal wires
                if port_name in ["req_valid", "req_ready", "rsp_valid", "rsp_ready"]:
                    wire_map = port_name.replace("req_", "w_").replace("rsp_", "w_rsp_")
                    f.write(f"    .{port_name}({wire_map}){comma}\n")
                elif port_name == "req":
                    f.write(f"    .{port_name}(w_req){comma}\n")
                else:
                    # Pass-through generic ports (clk, rst_n_sys, etc.)
                    f.write(f"    .{port_name}({port_name}){comma}\n")
                port_index += 1
                
        f.write("  );\n\n")

# ==========================================
# TEST EXECUTION
# ==========================================
if __name__ == "__main__":
    json_dir = "./stress_example1_parsed/"
    loaded_json_data = []
    
    if os.path.exists(json_dir):
        for file_path in glob.glob(os.path.join(json_dir, "*.json")):
            try:
                with open(file_path, 'r') as f:
                    loaded_json_data.append(json.load(f))
            except json.JSONDecodeError: pass

    if loaded_json_data:
        classifier = Classifier(loaded_json_data)
        registry = classifier.run()
        registry.summary()

        builder = Builder(registry)
        if registry.tests:
            root_type = list(registry.tests.keys())[0] 
            hierarchy_root = builder.build(root_type)
            hierarchy_root.print_tree()

            netlist_builder = NetlistBuilder(registry, hierarchy_root)
            generated_modules = netlist_builder.run()

            print("\n--- Generated RTL Modules ---")
            for mod_name, rtl_mod in generated_modules.items():
                print(f"\nModule Name: {rtl_mod.name}")
                
                print("  Standard Ports:")
                for port in rtl_mod.ports:
                    # UPDATED: Print data_type string instead of assuming "logic"
                    width_str = f"[{port['width']}:0] " if port['width'] and port['width'] != "0" else ""
                    dt = port.get("data_type", "logic")
                    print(f"    {port['direction']:<6} {dt:<10} {width_str}{port['name']}")
                
                print("  Interface Ports:")
                if not rtl_mod.interface_ports:
                    print("    (No interface ports defined)")
                for ip in rtl_mod.interface_ports:
                    modport_str = f".{ip['modport']}" if ip['modport'] else ""
                    print(f"    {ip['if_name']}{modport_str} {ip['name']}")
                
                print("  Wires:")
                if not rtl_mod.wires:
                    print("    (No internal wires defined)")
                for wire in rtl_mod.wires:
                    print(f"    {wire}")

            fsm_synthesizer = BehavioralSynthesizer(registry, generated_modules)
            fsm_modules = fsm_synthesizer.run()

            print("\n" + "="*40)
            print(" PHASE 5: Code Assembly")
            print("="*40)
            
            assembler = CodeAssembler(registry, hierarchy_root, fsm_modules, "assembler_output_rtl.sv")
            assembler.run()