# sv_to_json.py
import sys
import json
import pyslang

def main():
    if len(sys.argv) < 3:
        print("Usage: python sv_to_json.py <input.sv|svh> <output.json>")
        sys.exit(1)

    in_file = sys.argv[1]
    out_file = sys.argv[2]

    # Parse the SystemVerilog file into a SyntaxTree
    tree = pyslang.SyntaxTree.fromFile(in_file)

    # Convert to JSON string; use Full mode for max detail
    json_str = tree.to_json(pyslang.CSTJsonMode.Full)

    # pretty-print it
    data = json.loads(json_str)
    with open(out_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote CST JSON for {in_file} → {out_file}")

if __name__ == "__main__":
    main()
