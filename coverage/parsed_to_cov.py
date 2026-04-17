import json
import argparse
import re

# map constant names provided by constants.svh to values 
def build_constants_map(filepath):
    constants_map = {}
    
    # magic regex
    pattern = re.compile(r'(?:localparam|parameter)\s+(?:[\w\[\]:]+\s+)?(\w+)\s*=\s*([^;]+);')

    try:
        with open(filepath, 'r') as file:
            for line in file:
                # Strip out inline comments so they don't mess up parsing
                line = line.split('//')[0]
                
                match = pattern.search(line)
                if match:
                    name = match.group(1)
                    val_str = match.group(2).strip()

                    # Try to evaluate the value to an integer
                    try:
                        # Handles standard base-10 integers
                        constants_map[name] = int(val_str)
                        
                    except ValueError:
                        # Handles basic SystemVerilog tick notation (e.g., 32'hF, 'd12)
                        if "'" in val_str:
                            try:
                                _, base_and_val = val_str.split("'")
                                base = base_and_val[0].lower()
                                raw_val = base_and_val[1:].replace('_', '') # Strip underscores
                                
                                if base == 'h':
                                    constants_map[name] = int(raw_val, 16)
                                elif base == 'b':
                                    constants_map[name] = int(raw_val, 2)
                                elif base == 'd':
                                    constants_map[name] = int(raw_val, 10)
                                elif base == 'o':
                                    constants_map[name] = int(raw_val, 8)
                            except Exception:
                                print(f"Warning: Could not parse SV notation for {name}: {val_str}")
                        else:
                            print(f"Warning: Could not parse value for {name}: {val_str}")
                            
    except FileNotFoundError:
        print(f"Error: Could not find constants file at {filepath}")

    return constants_map

# returns value of constant
def resolve_constant(name):
    """Resolves a SystemVerilog constant name to an integer."""
    if name in CONSTANTS_MAP:
        return CONSTANTS_MAP[name]
    try:
        # Fallback in case 'left' or 'right' is already a raw integer string
        return int(name) 
    except ValueError:
        print(f"Warning: Could not resolve constant '{name}'")
        return 0

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

# Recursively reconstruct an expression like 'item.rsp.valid' from nested nodes.
def extract_expression(expr_node):
    if not expr_node:
        return ""
        
    kind = expr_node.get('kind')
    
    if kind == 'ScopedName':
        # Recursively extract the left side
        left = extract_expression(expr_node.get('left', {}))
        sep = "_" 
        # Recursively extract the right side
        right = extract_expression(expr_node.get('right', {}))
        
        return f"{left}{sep}{right}"
        
    elif kind == 'IdentifierName':
        return expr_node.get('identifier', {}).get('text', '')
        
    return ""

# Takes in a bin_node
def extract_bin(bin_node):
    bin_name = bin_node.get('name', {}).get('text', 'unknown_bin')
    initializer = bin_node.get('initializer', {})
    kind = initializer.get('kind')
    state_str = ""
    extracted_bins = []

    # Check if this is an array bin declaration (e.g., bins VALID[])
    is_array_bin = False
    size_node = bin_node.get('size')
    if size_node and size_node.get('kind') == "CoverageBinsArraySize":
        is_array_bin = True

    if kind == "ExpressionCoverageBinInitializer":
        state_str = resolve_constant(initializer.get('expr', '').get('identifier', {}).get('text', ''))
        extracted_bins.append({
            "reference": bin_name,
            "states": [state_str] if state_str else [] 
        })

    elif kind == "RangeCoverageBinInitializer":
        values = []
        valueRanges = initializer.get('ranges').get('valueRanges')
        
        for value in valueRanges:
            valueKind = value.get('kind', '')

            if valueKind == "IdentifierName":
                values.append(value.get('identifier', {}).get('text', ''))

            elif valueKind == "ValueRangeExpression":
                left = value.get('left', {}).get('identifier', {}).get('text', '')
                right = value.get('right', {}).get('identifier', {}).get('text', '')
                if is_array_bin:
                    start_val = resolve_constant(left)
                    end_val = resolve_constant(right)
                    
                    # Create an individual bin dict for each value in the range
                    for val in range(start_val, end_val + 1):
                        extracted_bins.append({
                            # SystemVerilog naturally names these bins with the index, e.g., VALID[10]
                            "reference": f"{bin_name}[{val}]", 
                            "states": [str(val)]
                        })
                    
                    # Return immediately since we've expanded the array
                    return extracted_bins
                else:
                    expression = f"[{left}:{right}]"
                    values.append(expression)

            elif valueKind == "IntegerVectorExpression":
                size = value.get('size', {}).get('text', '')
                base = value.get('base', {}).get('text', '')
                literal = value.get('value', {}).get('text', '')
                expression = "".join([size, base, literal])
                values.append(expression)

        if not is_array_bin:
            if len(values) > 1:
                state_str = "{" + ", ".join(values) + "}"
            else:
                state_str = "".join(values)
            
            extracted_bins.append({
                "reference": bin_name,
                "states": [state_str] if state_str else [] 
            })

    elif kind == "DefaultCoverageBinInitializer":
        extracted_bins.append({
            "reference": bin_name,
            "states": ["default"]
        })
    
    elif kind == "TransListCoverageBinInitializer":
        extracted_bins.append({
            "reference": bin_name,
            "states": ["NOT_SUPPORTED"]
        })
    
    return extracted_bins

def process_ast(ast):
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
            "sample_event": "manual", # AST doesn't explicitly link the sample event if called procedurally
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
                        "width": 32  # AST does not contain elaboration width data, defaulting to 32
                    }
                ],
                "bins": [],
                "illegal_bins": []
            }

            # 4. Find and process all Bins within this coverpoint
            bin_nodes = find_nodes(cp_node, 'CoverageBins')
            for bin_node in bin_nodes:
                bin_data = extract_bin(bin_node)
                coverpoint["bins"].extend(bin_data)

            covergroup["coverpoints"].append(coverpoint)

        output_model["covergroups"].append(covergroup)

    return output_model

def main():
    parser = argparse.ArgumentParser(description="Convert Parsed SV JSON to Coverage Schema JSON")
    parser.add_argument("input_file", help="Path to the parsed AST JSON (e.g. cov_parsed.json)")
    parser.add_argument("output_file", help="Path to the target output JSON (e.g. out_cov.json)")
    parser.add_argument("constants", type=str, help="Path to constants.svh")
    args = parser.parse_args()
    
    global CONSTANTS_MAP
    CONSTANTS_MAP = build_constants_map(args.constants)

    # Read the parsed AST
    with open(args.input_file, 'r') as f:
        ast_data = json.load(f)

    # Transform the AST to the target schema
    coverage_model = process_ast(ast_data)

    # Write out the result
    with open(args.output_file, 'w') as f:
        json.dump(coverage_model, f, indent=2)
    
    print(f"Successfully converted {args.input_file} to {args.output_file}")

if __name__ == "__main__":
    main()