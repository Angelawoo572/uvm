import json
import argparse
import sys
import math
import itertools

# Supported features
# - fixed bins, illegal bins

# TODO features
# - ignored bins
# - flatten array in cross coverage

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
                    # Do not prefix for the FSM module
                    if instance_name == "cov_fsm_inst":
                        parent_port_name = f"{port}"
                    else:
                        parent_port_name = f"{instance_name}_{port}"
                    connections.append(f"        .{port}({parent_port_name})")
                
                lines.append(",\n".join(connections))
                lines.append("    );")
                lines.append("")

        lines.append("endmodule\n")
        return "\n".join(lines)

# computes the bins of interest given a set of coverpoints
def prune_cross_bins():
    return

# Returns reference to all cp in cross
def get_covp(cross_data, cg_data):
    saved_covp = []
    for covp in cross_data['coverpoints']:
        cur = next(
            (cp for cp in cg_data['coverpoints'] if cp.get("reference") == covp), 
            None
        )
        if (cur == None):
            print("No matching coverpoint found")
        saved_covp.append(cur)
    return saved_covp

def gen_hierarchy_cross(ref, mod, saved_covp, counter_width=16):
    # Internal signals
    # Create an index for each cross point
    signal = ""
    covp_index = ""
    for covp in saved_covp:
        num_bins = len(covp.get('bins'))
        bin_width = math.ceil(math.log2(num_bins))
        signal += f"[{bin_width-1}:0]"
        covp_index += f"[{covp.get('reference')}]"
    mod.add_line(f"// Bin Counters for {ref}")
    mod.add_line(f"logic [{counter_width-1}:0] {ref}_ctr_r {signal}")
    mod.add_line(f"logic [{counter_width-1}:0] {ref}_ctr_n {signal}")
    mod.add_line(f"logic {ref}_illegal_error")

    # Assign outputs
    for idx, covp in enumerate(saved_covp):
        for idy, bin in enumerate(covp.get('bins')):
            out_name = f"{ref}_{idx}{idy}_cnt"
            mod.add_line(f"assign {out_name} = {ref}_ctr_r[{idx}][{idy}]")
            mod.add_output(out_name, counter_width)

    # Combinational Logic (Bin Mapping)
    mod.add_line("")
    mod.add_line("always_comb begin")
    mod.add_line("    // Default: Hold value, no error")
    mod.add_line(f"    {ref}_ctr_n = {ref}_ctr_r;")
    mod.add_line(f"    {ref}_illegal_error = 0;")
    mod.add_line("")
    mod.add_line(f"    if (sample) {ref}_ctr_n{covp_index} = {ref}_ctr_r{covp_index} + 1;")
    mod.add_line("end")

    # Sequential Logic
    mod.add_line("")
    mod.add_line("always_ff @(posedge clk or negedge rst) begin")
    mod.add_line("    if (!rst) begin")
    mod.add_line(f"        {ref}_ctr_r <= '0;")
    mod.add_line("    end else if (sample) begin")
    mod.add_line(f"        {ref}_ctr_r <= {ref}_ctr_n;")
    mod.add_line("    end")
    mod.add_line("end")

def gen_flat_cross(ref, mod, saved_covp, counter_width=16):
    # Calculate the total number of bins by multiplying the lengths of all bins
    bin_counts = [len(covp.get('bins')) for covp in saved_covp]
    total_bins = math.prod(bin_counts) if bin_counts else 0
    
    # Generate the concatenated signal string, e.g., "{cp1_idx_index, cp2_idx_index}"
    covp_refs = [f"{covp.get('reference')}_index" for covp in saved_covp]
    concat_sig = "{" + ", ".join(covp_refs) + "}"
    
    # Internal signals (Flattened unpacked arrays)
    mod.add_line(f"// Flattened Bin Counters for {ref}")
    mod.add_line(f"logic [{counter_width-1}:0] {ref}_ctr_r [0:{total_bins-1}];")
    mod.add_line(f"logic [{counter_width-1}:0] {ref}_ctr_n [0:{total_bins-1}];")
    mod.add_line(f"logic {ref}_illegal_error;")

    # Generate all index combinations
    ranges = [range(n) for n in bin_counts]
    all_combinations = list(itertools.product(*ranges))

    # Assign outputs mapped from the flat array
    mod.add_line("")
    for flat_idx, combo in enumerate(all_combinations):
        # Create a string of the indices like "01"
        combo_str = "".join(map(str, combo))
        out_name = f"{ref}_{combo_str}_cnt"
        mod.add_line(f"assign {out_name} = {ref}_ctr_r[{flat_idx}];")
        mod.add_output(out_name, counter_width)

    # Combinational Logic (Bin Mapping via Case Statement)
    mod.add_line("")
    mod.add_line("always_comb begin")
    mod.add_line("    // Default: Hold all values, no error")
    mod.add_line(f"    {ref}_ctr_n = {ref}_ctr_r; // Bulk unpacked array assignment")
    mod.add_line(f"    {ref}_illegal_error = 0;")
    mod.add_line("")
    mod.add_line(f"    if (sample) begin")
    mod.add_line(f"        case ({concat_sig})")
    
    for flat_idx, combo in enumerate(all_combinations):
        # Build the bit-width specific case condition (e.g., {2'd0, 2'd1})
        case_cond_parts = []
        for cp_idx, val in enumerate(combo):
            num_bins = len(saved_covp[cp_idx].get('bins'))
            # Ensure bin_width is at least 1, even if num_bins is 1
            bin_width = max(1, math.ceil(math.log2(num_bins))) 
            case_cond_parts.append(f"{bin_width}'d{val}")
        
        case_cond_str = "{" + ", ".join(case_cond_parts) + "}"
        mod.add_line(f"            {case_cond_str}: {ref}_ctr_n[{flat_idx}] = {ref}_ctr_r[{flat_idx}] + 1;")
        
    mod.add_line("            default: begin")
    mod.add_line(f"                {ref}_illegal_error = 1;")
    mod.add_line("            end")
    mod.add_line("        endcase")
    mod.add_line("    end")
    mod.add_line("end")

    # Sequential Logic
    mod.add_line("")
    mod.add_line("always_ff @(posedge clk or negedge rst) begin")
    mod.add_line("    if (!rst) begin")
    mod.add_line(f"        {ref}_ctr_r <= '{{default:0}};")
    mod.add_line("    end else if (sample) begin")
    mod.add_line(f"        {ref}_ctr_r <= {ref}_ctr_n;")
    mod.add_line("    end")
    mod.add_line("end")

# creates code for cross coverage
# lives within a covergroup
def generate_cross(cross_data, cg_data, counter_width=16):
    ref = cross_data['reference']
    mod = VerilogModule(ref)

    # Name and header
    mod.add_line("")
    mod.add_line(f"// Cross coverage {ref}")

    # Get reference to coverpoints
    saved_covp = get_covp(cross_data, cg_data)

    # gen_hierarchy_cross(ref, mod, saved_covp)
    gen_flat_cross(ref, mod, saved_covp)

    return mod

def generate_coverpoint(cp_data, counter_width=16):
    ref = cp_data['reference']
    mod = VerilogModule(ref)
    # Inputs
    mod.add_input("clk", 1)
    mod.add_input("rst", 1)
    mod.add_input("sample", 1)
    
    for sig in cp_data['signals']:
        mod.add_input(sig['reference'], sig['width'])

    # Bins & Logic
    bins = cp_data.get('bins', [])
    illegal_bins = cp_data.get('illegal_bins', [])
    num_bins = len(bins)
    
    # Internal signals
    bin_width = math.ceil(math.log2(num_bins))
    mod.add_line(f"// Bin Counters for {ref}")
    mod.add_line(f"logic [{counter_width-1}:0] {ref}_ctr_r [{num_bins-1}:0];")
    mod.add_line(f"logic [{counter_width-1}:0] {ref}_ctr_n [{num_bins-1}:0];")
    mod.add_line(f"logic [{bin_width-1}:0] {ref}_index;")
    mod.add_line("")

    # Generate Outputs and map internal array to output ports
    for idx, b in enumerate(bins):
        bin_ref = b['reference']
        out_name = f"{ref}_{bin_ref}_cnt"
        mod.add_output(out_name, counter_width)
        mod.add_line(f"assign {out_name} = {ref}_ctr_r[{idx}];")

    mod.add_output(f"{ref}_illegal_error", 1)

    # Combinational Logic (Bin Mapping)
    mod.add_line("")
    mod.add_line("always_comb begin")
    mod.add_line("    // Default: Hold value, no error")
    mod.add_line(f"    {ref}_ctr_n = {ref}_ctr_r;")
    mod.add_line(f"    {ref}_illegal_error = 0;")
    mod.add_line("")
    mod.add_line(f"    case ({cp_data['expression']})")
    
    for idx, b in enumerate(bins):
        states = b['states']
        states_str = ", ".join(map(str, states))
        mod.add_line(f"        {states_str}: begin {ref}_ctr_n[{idx}] = {ref}_ctr_r[{idx}] + 1;")
        mod.add_line(f"        {ref}_index = {idx};")
        mod.add_line(f"        end")
    
    for b in illegal_bins:
        states = b['states']
        states_str = ", ".join(map(str, states))
        mod.add_line(f"        {states_str}: {ref}_illegal_error = 1;")

    mod.add_line("        default: ; // No bin hit")
    mod.add_line("    endcase")
    mod.add_line("end")

    # Sequential Logic
    mod.add_line("")
    mod.add_line("always_ff @(posedge clk or negedge rst) begin")
    mod.add_line("    if (!rst) begin")
    for i in range(num_bins):
        mod.add_line(f"        {ref}_ctr_r[{i}] <= '0;")
    mod.add_line("    end else if (sample) begin")
    mod.add_line(f"        {ref}_ctr_r <= {ref}_ctr_n;")
    mod.add_line("    end")
    mod.add_line("end")

    return mod

def generate_covergroup(cg_data):
    ref = cg_data['reference']
    mod = VerilogModule(ref)
    
    # Standard Inputs
    mod.add_input("clk", 1)
    mod.add_input("rst", 1)
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

    # Process crosses
    for cross in cg_data['crosses']:
        cross_mod = generate_cross(cross, cg_data)

        for line in cross_mod.body:
            mod.add_line(line)

        # bubble up outputs (prefix with instance name)
        for name, width in cross_mod.outputs.items():
            mod.add_output(f"{name}", width)

    return mod

def generate_coverage_model(model_data):
    ref = model_data.get('reference')
    mod = VerilogModule(ref)
    
    # Standard Inputs
    mod.add_input("clk", 1)
    mod.add_input("rst", 1)
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

# creates a table that maps a code to signal name and width
def gen_output_table(top_mod):
    output_table = {}

    for idx, sub_mod in enumerate(top_mod.sub_modules):
        for idy, key in enumerate(top_mod.outputs.keys()):
            id = idx * len(top_mod.sub_modules) + idy
            output_table[id] = {"name": key, "width": top_mod.outputs[key], "cg_id": idx}
    
    return output_table

# gets id of signal given name, returns -1 on failure
def get_id(signal_name, output_table):
    for id in output_table.keys():
        if output_table[id].get("name") == signal_name:
            return id
    return -1 

# creates output logic for a single covergroup
def gen_output_cg(cg, output_table):
    mod = VerilogModule("output_mod")
    signal_id_bits = math.ceil(math.log2(len(output_table)))
    mod.add_input("signal_id", signal_id_bits)
    mod.add_output("byte_done", 1)
    mod.add_output(f"{cg.name}_byte", 8)

    # byte_counter, tracks which byte of output signal is transmitted
    max_output_width = 0
    for key in cg.outputs.keys():
        if cg.outputs[key] > max_output_width:
            max_output_width = cg.outputs[key]
    byte_ctr_bits = math.ceil(math.log2(max_output_width / 8))
    mod.add_input("byte_ctr", byte_ctr_bits)
    mod.add_line(f"logic[{byte_ctr_bits-1}:0] byte_ctr;")

    # create mux for each output signal
    for output in cg.outputs.keys():
        width = cg.outputs[key]
        mod.add_input(output, width)
        mod.add_line(f"logic[7:0] {output}_byte;")
        mod.add_line(f"logic {output}_done;")
        mod.add_line("")
        mod.add_line("always_comb begin")            
        mod.add_line(f"    {output}_byte = '0;")
        mod.add_line("    case(byte_ctr)")
        for x in range(byte_ctr_bits + 1):
            # make a new case for each packet in output
            if (x * 8 < width):
                end_bit = x * 8 + 7 if (x * 8 + 7 < width) \
                    else x * 8 + width % 8 - 1
                mod.add_line(f"        {x}: {output}_byte[{end_bit % 8}:0] = " +
                             f"{output}[{end_bit}:{x * 8}];")
        mod.add_line(f"    default: {output}_byte = '0;")
        mod.add_line(f"    endcase")
        mod.add_line("end")
        id = get_id(output, output_table)
        # done signal asserted in same cycle that last packet is sent
        byte_num = math.ceil(width / 8)
        mod.add_line(f"assign {output}_done = " + 
                     f"(signal_id == {id}) & (byte_ctr == {byte_num - 1});")
        mod.add_line("")
    
    # mux output signal to generate cg_byte
    mod.add_line("always_comb begin")
    mod.add_line(    "case(signal_id)")
    for output in cg.outputs.keys():
        id = get_id(output, output_table)
        mod.add_line(f"        {id}: {cg.name}_byte = {output}_byte;")
    mod.add_line(f"        default: {cg.name}_byte = '0;")
    mod.add_line(    "endcase")
    mod.add_line("end")

    # assert done signal if any packet is done sending
    or_logic = " |\n        ".join(f"{output}_done" for output in cg.outputs.keys())
    mod.add_line(f"assign byte_done = {or_logic};")
    return mod

# generates the FSM to orchestrate UART transmission of coverage data
def gen_cov_fsm(cg, output_table):
    mod = VerilogModule("cov_fsm")
    
    # Dynamically calculate parameterized widths
    signal_count = len(output_table)
    signal_id_bits = max(1, math.ceil(math.log2(signal_count)))
    
    max_output_width = 0
    for key in cg.outputs.keys():
        if cg.outputs[key] > max_output_width:
            max_output_width = cg.outputs[key]
    
    # Calculate byte_ctr_bits, ensuring it is at least 1 bit wide (logic[0:0])
    byte_ctr_bits = max(1, math.ceil(math.log2(max_output_width / 8)))

    # Add inputs
    mod.add_input("clk", 1)
    mod.add_input("rst", 1)
    mod.add_input("sim_complete", 1)
    mod.add_input("tx_ready", 1)
    mod.add_input("packet_ready", 1)
    mod.add_input("packet_done", 1)

    # Add outputs
    mod.add_output("done", 1)
    mod.add_output("byte_ctr", byte_ctr_bits)
    mod.add_output("signal_id", signal_id_bits)
    mod.add_output("send_id", 1)

    # State definitions and local parameters
    mod.add_line("enum logic[1:0] {s_idle, s_send_id, s_packet} state_n, state_p;")
    mod.add_line(f"localparam SIGNAL_COUNT = {signal_count};")
    mod.add_line("")
    
    # Next state logic
    mod.add_line("always_comb begin")
    mod.add_line("    state_n = state_p;")
    mod.add_line("    case(state_p)")
    mod.add_line("        s_idle: if (sim_complete & tx_ready) state_n = s_send_id;")
    mod.add_line("        s_send_id: if (tx_ready) state_n = s_packet;")
    mod.add_line("        s_packet: begin ")
    mod.add_line("            if (signal_id == (SIGNAL_COUNT-1) & tx_ready) state_n = s_idle;")
    mod.add_line("            else if (tx_ready & packet_done) state_n = s_send_id;")
    mod.add_line("        end")
    mod.add_line("    endcase")
    mod.add_line("end")
    mod.add_line("")
    
    # Counters logic
    mod.add_line(f"logic[{signal_id_bits-1}:0] signal_id_n;")
    mod.add_line(f"logic[{byte_ctr_bits-1}:0] byte_ctr_n;")
    mod.add_line("always_comb begin")
    mod.add_line("    signal_id_n = signal_id;")
    mod.add_line("    byte_ctr_n = byte_ctr;")
    mod.add_line("    if (state_p == s_packet & tx_ready) begin")
    mod.add_line("        byte_ctr_n = byte_ctr + 1;")
    mod.add_line("    end")
    mod.add_line("    if (state_p == s_packet & state_n == s_send_id) begin")
    mod.add_line("        signal_id_n = signal_id + 1;")
    mod.add_line("    end")
    mod.add_line("    if (state_p != s_packet) begin")
    mod.add_line("        byte_ctr_n = '0;")
    mod.add_line("    end")
    mod.add_line("end")
    mod.add_line("")
    
    # Status assignments
    mod.add_line("assign done = (state_p == s_packet & state_n == s_idle);")
    mod.add_line("assign send_id = (state_p == s_send_id);")
    mod.add_line("")
    
    # Sequential logic
    mod.add_line("always_ff @(posedge clk) begin")
    mod.add_line("    if (rst) begin ")
    mod.add_line("        state_p <= s_idle;")
    mod.add_line("        byte_ctr <= '0;")
    mod.add_line("        signal_id <= '0;")
    mod.add_line("    end")
    mod.add_line("    else begin")
    mod.add_line("        state_p <= state_n;")
    mod.add_line("        byte_ctr <= byte_ctr_n;")
    mod.add_line("        signal_id <= signal_id_n;")
    mod.add_line("    end")
    mod.add_line("end")

    return mod

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

    # Add uart module
    output_table = gen_output_table(top_mod)
    fsm_mod = gen_cov_fsm(top_mod, output_table)
    output_mod = gen_output_cg(top_mod, output_table)

    top_mod.sub_modules.append((output_mod, "uart_out"))
    top_mod.sub_modules.append((fsm_mod, "cov_fsm_inst"))

    collect_modules(top_mod, all_modules)

    # bubble up inputs and outputs for uart
    for name, width in output_mod.outputs.items():
        if name not in top_mod.outputs:
            top_mod.add_output(f"uart_out_{name}", width)

    # bubble up inputs and outputs for cov_fsm
    for name, width in fsm_mod.outputs.items():
        if name not in top_mod.outputs:
            top_mod.add_output(f"{name}", width)
    for name, width in fsm_mod.inputs.items():
        if name not in top_mod.inputs:
            top_mod.add_input(f"{name}", width)

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