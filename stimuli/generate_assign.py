import re

def generate_constrained_module(constraint_line, total_width=32):
    # Regex to capture: variable, [msb:lsb], and the value
    # Example: constraint align_32 {addr[1:0] == 0;}
    pattern = r"constraint\s+\w+\s*\{(\w+)(?:\[(\d+):(\d+)\])?\s*==\s*([^;]+);?\s*\}"
    match = re.search(pattern, constraint_line)
    
    if not match:
        return "// Error: Could not parse constraint format."

    var_name = match.group(1)
    msb_str  = match.group(2)
    lsb_str  = match.group(3)
    val_raw  = match.group(4).strip()

    rtl = []
    rtl.append(f"module const_wrap_{var_name} (")
    rtl.append(f"    input  logic [{total_width-1}:0] lfsr_in,")
    rtl.append(f"    output logic [{total_width-1}:0] {var_name}")
    rtl.append(f");")
    rtl.append("")

    # Case 1: Specific bit range is constrained (e.g., addr[1:0])
    if msb_str and lsb_str:
        msb, lsb = int(msb_str), int(lsb_str)
        width = msb - lsb + 1
        
        # 1. Pass-through upper bits
        if msb < total_width - 1:
            rtl.append(f"    assign {var_name}[{total_width-1}:{msb+1}] = lfsr_in[{total_width-1}:{msb+1}];")
        
        # 2. Assign constrained bits
        # Formatting '0' to '2'b0' etc.
        val = f"{width}'h{int(val_raw, 0):x}" if val_raw.isnumeric() or 'h' in val_raw else val_raw
        rtl.append(f"    assign {var_name}[{msb}:{lsb}] = {val};")
        
        # 3. Pass-through lower bits
        if lsb > 0:
            rtl.append(f"    assign {var_name}[{lsb-1}:0] = lfsr_in[{lsb-1}:0];")
            
    # Case 2: Entire variable is constrained (e.g., lcr == 8'h3f)
    else:
        rtl.append(f"    assign {var_name} = {val_raw};")

    rtl.append("")
    rtl.append("endmodule")
    return "\n".join(rtl)

# --- Test ---
input_str = "constraint align_32 {addr[1:0] == 0;}"
output_lines = generate_constrained_module(input_str)

def write_to_file(filename, content):
    """Writes the content string to a file."""
    try:
        with open(filename, "w") as f:
            for i in content:
                f.write(i)
        print(f"Successfully wrote to {filename}")
    except IOError as e:
        print(f"Error writing file: {e}")

print("// --- Write RTL to file---")
output_filename = "bit_assign_example1.sv"

# Write to file
write_to_file(output_filename, output_lines)




      