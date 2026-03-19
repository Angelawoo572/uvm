import re
import typer
import subprocess
from typing import Annotated

from identify import identify_constraint
from generate import generate_constraint

app = typer.Typer(add_completion=False)

# Assume input has been sanitized and only contains valid constraints in each line (one per line). 
# i.e. each line is a constraint or a comment (Comments start with //)
@app.command()
def main(
    input_filename: Annotated[str, typer.Argument(help="Input text file containing constraints. (Output of parser) E.g., 'constraints.txt',")], 
    output_directory: Annotated[str, typer.Argument(help="Output directory to save the generated stimuli_fsm RTL. E.g., 'output/'")]
) -> None:
    # Open and read file
    try:
        with open(input_filename, "r") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    # Parse file lines and save into content list (removes comments)
    content = []
    for line in lines:
        line = re.sub(r'//.*', '', line).strip() # remove comments
        if not line:
            continue # skip empty lines

        constraint_type = identify_constraint(line) # should return str
        # print(constraint_type)
        if not constraint_type:
            continue # skip lines without constraint

        content.append(generate_constraint(constraint_type, line, output_directory)) # content could be tuple 
                                                                   # ("module name", "module rtl", "lower_bound, upper_bound")
    if not content:
        print("No valid constraints found in the file.")
        return # skip if no constraints
    
    # List of files
    files_to_copy = [
        "seq_stim_if.svh",
        "stimuli_fsm.sv",
        "bounded_LFSR.sv"
    ]

    files_to_modify = [
        "constraint_solver.sv"
    ]
    return
    
    
if __name__ == "__main__":
    app()  
    # example:
    # python main.py main constraint.txt constraints_solver_ex1.sv