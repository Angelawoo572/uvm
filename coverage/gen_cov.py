import json
import argparse
import sys

# Supported features
# - fixed bins, illegal bins

# TODO features
# - ignored bins
# 

# TODO - update outputs correctly in cg

class VerilogModule:
    def __init__(self, name):
        self.name = name
        self.inputs = {}  # {name: width}
        self.outputs = {} # {name: width}
        self.body = []
        self.sub_modules = [] # List of tuples: (module_obj, instance_name)

    def add_input(self, name, width):
        self.inputs[name] = width

    def add_output(self, name, width):
        self.outputs[name] = width

    def add_line(self, line):
        self.body.append(line)

    def generate_sv(self):
        # Header
        lines = []
        lines.append(f"module {self.name} (")
        
        # Port list
        ports = []
        # Standardize Inputs
        for name, width in self.inputs.items():
            if width > 1:
                ports.append(f"    input logic [{width-1}:0] {name}")
            else:
                ports.append(f"    input logic {name}")
        
        # Standardize Outputs
        for name, width in self.outputs.items():
            if width > 1:
                ports.append(f"    output logic [{width-1}:0] {name}")
            else:
                ports.append(f"    output logic {name}")
                
        lines.append(",\n".join(ports))
        lines.append(");\n")

        # Body
        for line in self.body:
            lines.append(f"    {line}")
        
        # Submodule Instantiations
        if self.sub_modules:
            lines.append("")
            for sub_mod, instance_name in self.sub_modules:
                lines.append(f"    {sub_mod.name} {instance_name}_inst (")
                # Connect inputs - assumed pass-through by name
                connections = []
                for port in sub_mod.inputs:
                    connections.append(f"        .{port}({port})")
                
                # Connect outputs - wire to local output ports
                # We assume parent output naming convention matches child port mapping logic
                for port in sub_mod.outputs:
                    # In this hierarchy, we prefix child outputs with the instance name to create the parent output name
                    parent_port_name = f"{instance_name}_{port}"
                    connections.append(f"        .{port}({parent_port_name})")
                
                lines.append(",\n".join(connections))
                lines.append("    );")
                lines.append("")

        lines.append("endmodule\n")
        return "\n".join(lines)

#def generate_cross(cg_data, counter_width=4):

 #   return

def generate_coverpoint(cp_data, counter_width=4):
    ref = cp_data['reference']
    mod = VerilogModule(ref)
    refname = f"{cp_data.get('reference')}"
    # Inputs
    mod.add_input("clk", 1)
    mod.add_input("rst_n", 1)
    mod.add_input("sample", 1)
    
    for sig in cp_data['signals']:
        mod.add_input(sig['reference'], sig['width'])

    # Bins & Logic
    bins = cp_data.get('bins', [])
    illegal_bins = cp_data.get('illegal_bins', [])
    num_bins = len(bins)
    
    # Internal signals
    mod.add_line(f"// Bin Counters for {ref}")
    mod.add_line(f"logic [{counter_width-1}:0] {refname}_ctr_r [{num_bins-1}:0];")
    mod.add_line(f"logic [{counter_width-1}:0] {refname}_ctr_n [{num_bins-1}:0];")
    mod.add_line("")

    # Generate Outputs and map internal array to output ports
    for idx, b in enumerate(bins):
        bin_ref = b['reference']
        out_name = f"{refname}_{bin_ref}_cnt"
        mod.add_output(out_name, counter_width)
        mod.add_line(f"assign {out_name} = ctr_r[{idx}];")

    mod.add_output(f"{refname}_illegalError", 1)

    # Combinational Logic (Bin Mapping)
    mod.add_line("")
    mod.add_line("always_comb begin")
    mod.add_line("    // Default: Hold value, no error")
    mod.add_line(f"    {refname}_ctr_n = ctr_r;")
    mod.add_line(f"    {refname}_illegalError = 0;")
    mod.add_line("")
    mod.add_line(f"    case ({cp_data['expression']})")
    
    for idx, b in enumerate(bins):
        states = b['states']
        states_str = ", ".join(map(str, states))
        mod.add_line(f"        {states_str}: {refname}_ctr_n[{idx}] = {refname}_ctr_r[{idx}] + 1;")
    
    for b in illegal_bins:
        states = b['states']
        states_str = ", ".join(map(str, states))
        mod.add_line(f"        {states_str}: {refname}_illegalError = 1;")

    mod.add_line("        default: ; // No bin hit")
    mod.add_line("    endcase")
    mod.add_line("end")

    # Sequential Logic
    mod.add_line("")
    mod.add_line("always_ff @(posedge clk or negedge rst_n) begin")
    mod.add_line("    if (!rst_n) begin")
    for i in range(num_bins):
        mod.add_line(f"        {refname}_ctr_r[{i}] <= '0;")
    mod.add_line("    end else if (sample) begin")
    mod.add_line(f"        {refname}_ctr_r <= {refname}_ctr_n;")
    mod.add_line("    end")
    mod.add_line("end")

    return mod

def generate_covergroup(cg_data):
    ref = cg_data['reference']
    mod = VerilogModule(ref)
    
    # Standard Inputs
    mod.add_input("clk", 1)
    mod.add_input("rst_n", 1)
    mod.add_input("sample", 1) # Assumes external trigger logic determines 'sample' high

    # Process Children (Coverpoints)
    for cp_data in cg_data['coverpoints']:
        cp_mod = generate_coverpoint(cp_data)
        instance_name = f"{cp_data['reference']}_inst"

        # mod.sub_modules.append((cp_mod, instance_name))
        # append body lines to cg body
        for line in cp_mod.body:
            mod.add_line(line)

        # bubble up inputs (uniquify)
        for name, width in cp_mod.inputs.items():
            if name not in mod.inputs:
                mod.add_input(name, width)
        
        # bubble up outputs (prefix with instance name)
        for name, width in cp_mod.outputs.items():
            mod.add_output(f"{name}", width)

    return mod

def generate_coverage_model(model_data):
    ref = model_data.get('reference')
    mod = VerilogModule(ref)
    
    # Standard Inputs
    mod.add_input("clk", 1)
    mod.add_input("rst_n", 1)
    mod.add_input("sample", 1) 

    # Process Children (Covergroups)
    for cg_data in model_data['covergroups']:
        cg_mod = generate_covergroup(cg_data)
        instance_name = f"{cg_data['reference']}"
        mod.sub_modules.append((cg_mod, f"{instance_name}"))
        
        # bubble up inputs
        for name, width in cg_mod.inputs.items():
            if name not in mod.inputs:
                mod.add_input(name, width)
                
        # bubble up outputs
        for name, width in cg_mod.outputs.items():
            mod.add_output(f"{instance_name}_{name}", width)
            
    return mod

def collect_modules(mod, module_list):
    """Recursively collect all module objects to print them in order."""
    # We want children defined before parents in the file usually, 
    # but SystemVerilog doesn't strictly require it if unresolved types aren't used.
    # However, printing children first is good practice.
    for sub, _ in mod.sub_modules:
        collect_modules(sub, module_list)
    if mod not in module_list:
        module_list.append(mod)

def main():
    parser = argparse.ArgumentParser(description="Convert Coverage JSON to Synthesizable SystemVerilog")
    parser.add_argument("input_json", help="Path to the input JSON file")
    parser.add_argument("output_sv", help="Path to output SV file", default="coverage_model.sv")
    args = parser.parse_args()

    try:
        with open(args.input_json, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}")
        sys.exit(1)

    # Generate Model
    top_mod = generate_coverage_model(data)

    # Collect all modules (Leaf -> Root order)
    all_modules = []
    collect_modules(top_mod, all_modules)

    # Write to file
    with open(args.output_sv, 'w') as f:
        f.write("// Auto-generated SystemVerilog Coverage Model\n")
        f.write(f"// Generated from: {args.input_json}\n\n")
        
        for mod in all_modules:
            f.write(mod.generate_sv())
            f.write("\n")
            
    print(f"Successfully generated {args.output_sv}")

if __name__ == "__main__":
    main()