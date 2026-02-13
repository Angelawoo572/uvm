import re
"""
Parses a SystemVerilog dist constraint and generates RTL
"""
def parse_and_generate_sv(constraint_line, lfsr_width=32, scaled_width=64):
    
    # 1. Clean up the input string
    # Remove comments (// ...)
    line = re.sub(r'//.*', '', constraint_line)
    # Extract variable name and the content inside {}
    match = re.search(r'(\w+)\s+dist\s*\{(.*)\}', line)
    
    if not match:
        return "// Error: Could not parse constraint format. Expected: 'var dist { ... };'"
    
    var_name = match.group(1)
    body = match.group(2)
    
    # 2. Parse the distribution list
    # Split by commas to get individual terms
    terms = [t.strip() for t in body.split(',')]
    
    map_table = [] # Stores tuples of (output_value, weight)
    
    for term in terms:
        if not term: continue
        
        # Determine operator type
        if ':=' in term:
            parts = term.split(':=')
            operator = ':='
        elif ':/' in term:
            parts = term.split(':/')
            operator = ':/'
        else:
            continue # Malformed term
            
        lhs = parts[0].strip()
        weight_str = parts[1].strip()
        weight = int(weight_str)
        
        # Check if LHS is a range [lo:hi] or single value
        range_match = re.search(r'\[(\d+):(\d+)\]', lhs)
        
        if range_match:
            lo = int(range_match.group(1))
            hi = int(range_match.group(2))
            count = hi - lo + 1
            
            if operator == ':=':
                # Weight applies to EACH item
                item_weight = weight
            else: # operator == ':/'
                # Weight is distributed (split) among items
                # integer division
                item_weight = weight // count
                if item_weight == 0: item_weight = 1 # Safety floor
                
            for val in range(lo, hi + 1):
                map_table.append({'val': val, 'weight': item_weight})
        else:
            # Single value
            val = int(lhs)
            map_table.append({'val': val, 'weight': weight})

    # 3. Calculate Cumulative Ranges
    # We map "slots" of probability to output values
    total_weight = sum(item['weight'] for item in map_table)
    
    # 4. Generate RTL
    rtl = []
    rtl.append(f"// --- Generated Weighted Random Logic for '{var_name}' ---")
    # rtl.append(f"// Total Weight Sum: {total_weight}")
    rtl.append(f"// Input LFSR Width: {lfsr_width} bits")
    
    # Variable declarations
    # rtl.append(f"logic [{lfsr_width-1}:0] product_high;")
    rtl.append(f"module dist_for_{var_name}(input logic [{lfsr_width-1}:0] lfsr_in, output logic [31:0] {var_name});")
    rtl.append(f"logic [{scaled_width-1}:0] scaled_rand;")
    # rtl.append(f"logic [31:0] {var_name};") 
    rtl.append("")
    
    # Scaling Logic
    # We use the standard scaling: (LFSR * TOTAL_WEIGHT) >> LFSR_WIDTH
    # This maps the 0..2^N-1 range to 0..TOTAL_WEIGHT-1
    rtl.append(f"// Scaling: Map LFSR to [0 : {total_weight-1}]")
    rtl.append(f"assign scaled_rand = (lfsr_in * {total_weight}) >> {lfsr_width};")
    # rtl.append(f"assign scaled_rand = product_high;")
    rtl.append("")
    
    # Case Statement
    rtl.append(f"always_comb begin")
    rtl.append(f"    case (scaled_rand) inside")
    
    current_low = 0
    for item in map_table:
        w = item['weight']
        val = item['val']
        
        # Calculate the range [low : high] for this value
        # SV syntax is inclusive [lo:hi]
        range_high = current_low + w - 1
        
        if w > 0:
            if current_low == range_high:
                # Single point
                rtl.append(f"        {current_low:<6}: {var_name} = {val};")
            else:
                # Range
                rtl.append(f"        [{current_low}:{range_high}]: {var_name} = {val};")
        
        current_low += w
        
    rtl.append(f"        default: {var_name} = '0; // Should not be reached")
    rtl.append(f"    endcase")
    rtl.append(f"end")
    rtl.append(f"endmodule")
    
    return "\n".join(rtl)

def write_to_file(filename, content):
    """Writes the content string to a file."""
    try:
        with open(filename, "w") as f:
            f.write(content)
        print(f"Successfully wrote to {filename}")
    except IOError as e:
        print(f"Error writing file: {e}")

# --- Test with your specific example ---
input_str = "data3 dist { 0 := 10, [1:5] :/ 10, 100 := 10};"
generated_rtl = parse_and_generate_sv(input_str, lfsr_width=32)

# Define output filename
output_filename = "dist_example1.sv"

# Write to file
write_to_file(output_filename, generated_rtl)