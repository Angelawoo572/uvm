from sympy import re

import typer
from typing import Annotated

from identify import identify_constraint
from generate import generate_constraint

app = typer.Typer(add_completion=False)

@app.command()
def one_line(
    input_filename: Annotated[str, typer.Argument(help="Input SystemVerilog file containing constraints. E.g., 'constraints.sv'")], 
    output_filename: Annotated[str, typer.Argument(help="Output file for generated constraints")]
) -> None:
    try:
        with open(input_filename, "r") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    content = []
    line = lines[0] if lines else ""
    # Remove comments
    line = re.sub(r'//.*', '', line).strip()
    constraint_type = identify_constraint(line)
    if not constraint_type:
        print("No valid constraint found in the first line.")
        return
    content.append(generate_constraint(constraint_type, line))
    
    try:
        with open(output_filename, "w") as f:
            f.write("\n".join(content))
        print(f"Successfully wrote to {output_filename}")
    except Exception as e:
        print(f"Error writing file: {e}")

@app.command()
def main(
    input_filename: Annotated[str, typer.Argument(help="Input SystemVerilog file containing constraints. E.g., 'constraints.sv'")], 
    output_filename: Annotated[str, typer.Argument(help="Output file for generated constraints")]
) -> None:
    try:
        with open(input_filename, "r") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    content = []
    for line in lines:
        line = re.sub(r'//.*', '', line).strip() # remove comments
        constraint_type = identify_constraint(line)
        if not constraint_type:
            continue # skip lines without constraint
        content.append(generate_constraint(constraint_type, line))
    
    try:
        with open(output_filename, "w") as f:
            f.write("\n".join(content))
        print(f"Successfully wrote to {output_filename}")
    except Exception as e:
        print(f"Error writing file: {e}")
    
if __name__ == "__main__":
    app()  
    # example:
    # python main.py one-line constraints.sv constraints_rtl.sv
    # python main.py main constraint.sv constraint_rtl.sv