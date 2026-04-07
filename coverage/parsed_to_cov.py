import json
import argparse

import re

def load_constants(filepath):
    constants = {}
    # Regex explanation:
    # localparam \s+       : matches 'localparam' followed by spaces
    # ([A-Za-z0-9_]+)      : Group 1 - matches the constant name (e.g., MODE0_OFFSET)
    # \s*=\s* : matches '=' surrounded by optional spaces
    # ([^;]+)              : Group 2 - matches everything up to the ';' (the value)
    pattern = re.compile(r'localparam\s+([A-Za-z0-9_]+)\s*=\s*([^;]+);')
    
    with open(filepath, 'r') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                name = match.group(1)
                value_str = match.group(2).strip()
                
                # Try to convert to an integer
                try:
                    # Handles standard base-10 integers
                    constants[name] = int(value_str)
                except ValueError:
                    # If it's a complex string or Verilog hex (e.g., 32'h4), 
                    # keep it as a string or add custom parsing here.
                    constants[name] = value_str
                    
    return constants

def find_nodes(node, kind):
    """Recursively search the AST for nodes of a specific 'kind'."""
    found = []
    if isinstance(node, dict):
        if node.get('kind') == kind:
            found.append(node)
        for key, value in node.items():
            found.extend(find_nodes(value, kind))
    elif isinstance(node, list):
        for item in node:
            found.extend(find_nodes(item, kind))
    return found

def extract_expression(expr_node):
    """Reconstruct an expression like 'm_item.addr_i' from a ScopedName node."""
    if not expr_node:
        return ""
    if expr_node.get('kind') == 'ScopedName':
        # Safely extract left, separator, and right text
        left = expr_node.get('left', {}).get('identifier', {}).get('text', '')
        sep = expr_node.get('separator', {}).get('text', '')
        right = expr_node.get('right', {}).get('identifier', {}).get('text', '')
        sep = "_"
        return f"{left}{sep}{right}"
    elif expr_node.get('kind') == 'IdentifierName':
        return expr_node.get('identifier', {}).get('text', '')
    return ""

def process_ast(ast, sv_constants): # <-- 1. Add sv_constants here
    """Processes the parsed SV AST and returns a dictionary matching cov.json schema."""
    output_model = {
        "reference": "",
        "covergroups": []
    }

    # 1. Find the top-level class name for the reference
    class_nodes = find_nodes(ast, 'ClassDeclaration')
    if class_nodes:
        output_model["reference"] = class_nodes[0].get('name', {}).get('text', 'unknown_class')

    # 2. Find and process all Covergroups
    cg_nodes = find_nodes(ast, 'CovergroupDeclaration')
    for cg_node in cg_nodes:
        cg_name = cg_node.get('name', {}).get('text', 'unknown_cg')
        
        covergroup = {
            "reference": cg_name,
            "sample_event": "manual", 
            "coverpoints": [],
            "crosses": []
        }

        # 3. Find and process all Coverpoints within this covergroup
        cp_nodes = find_nodes(cg_node, 'Coverpoint')
        for cp_node in cp_nodes:
            expr_str = extract_expression(cp_node.get('expr'))
            
            coverpoint = {
                "reference": expr_str,
                "expression": expr_str,
                "signals": [
                    {
                        "reference": expr_str,
                        "width": 32  
                    }
                ],
                "bins": [],
                "illegal_bins": []
            }

            # 4. Find and process all Bins within this coverpoint
            bin_nodes = find_nodes(cp_node, 'CoverageBins')
            for bin_node in bin_nodes:
                bin_name = bin_node.get('name', {}).get('text', 'unknown_bin')
                
                resolved_states = []
                
                # Find the nodes that contain the actual bin values/macros.
                # (You might need to adjust 'IdentifierName' based on your AST)
                value_nodes = find_nodes(bin_node, 'IdentifierName') 
                
                for v_node in value_nodes:
                    val_str = v_node.get('identifier', {}).get('text', '')
                    
                    # Check if the string matches a constant from constants.svh
                    if val_str in sv_constants:
                        resolved_states.append(sv_constants[val_str])
                    else:
                        # Fallback: if it's just a raw number (like "4"), convert it
                        try:
                            resolved_states.append(int(val_str))
                        except ValueError:
                            # It's a string we don't recognize, just skip or append it as-is
                            pass 
                # =========================================================

                bin_data = {
                    "reference": bin_name,
                    "states": resolved_states
                }
                coverpoint["bins"].append(bin_data)

            covergroup["coverpoints"].append(coverpoint)

        output_model["covergroups"].append(covergroup)

    return output_model

def main():
    parser = argparse.ArgumentParser(description="Convert Parsed SV JSON to Coverage Schema JSON")
    parser.add_argument("input_file", help="Path to the parsed AST JSON (e.g. cov_parsed.json)")
    parser.add_argument("constants", help="Path to constants.svh file")   
    parser.add_argument("output_file", help="Path to the target output JSON (e.g. out_cov.json)")
    
    args = parser.parse_args()
    sv_constants = load_constants(args.constants)
    # Read the parsed AST
    with open(args.input_file, 'r') as f:
        ast_data = json.load(f)

    # Transform the AST to the target schema
    coverage_model = process_ast(ast_data, sv_constants)

    # Write out the result
    with open(args.output_file, 'w') as f:
        json.dump(coverage_model, f, indent=2)
    
    print(f"Successfully converted {args.input_file} to {args.output_file}")

if __name__ == "__main__":
    main()