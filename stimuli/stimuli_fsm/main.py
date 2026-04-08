import re
import os
from pathlib import Path
import typer
import subprocess
from typing import Annotated

from identify import identify_constraint
from generate import generate_constraint

app = typer.Typer(add_completion=False)


def _copy_file_with_subprocess(src: Path, dst: Path) -> None:
    """Copy a file using subprocess to keep behavior explicit in the workflow."""
    if not src.exists():
        raise FileNotFoundError(f"Template file not found: {src}")

    if src.resolve() == dst.resolve():
        return

    if dst.parent:
        dst.parent.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Copy-Item -LiteralPath '{src}' -Destination '{dst}' -Force",
            ],
            check=True,
        )
    else:
        subprocess.run(["cp", str(src), str(dst)], check=True)

# Assume input has been sanitized and only contains valid constraints in each line (one per line). 
# i.e. each line is a constraint or a comment (Comments start with //)
@app.command()
def main(
    input_filename: Annotated[str, typer.Argument(help="Input text file containing constraints. (Output of parser) E.g., 'constraints.txt',")], 
    output_directory: Annotated[str, typer.Argument(help="Output directory to save the generated stimuli_fsm RTL. E.g., 'output/'"),],
    lfsr_width: Annotated[int, typer.Option(help="Width of the LFSR input for generated modules. Default is 32.")] = 32
) -> None:
    script_dir = Path(__file__).resolve().parent
    out_dir = Path(output_directory)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Open and read file
    try:
        with open(input_filename, "r") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    # List of files
    files_to_copy = [
        "seq_stim_if.svh",
        "stimuli_fsm.sv",
        "bounded_LFSR.sv",
        "seq_fsm.sv"
    ]

    files_to_modify = [
        "constraint_solver.sv"
    ]

    try:
        for file_name in files_to_copy + files_to_modify:
            _copy_file_with_subprocess(script_dir / file_name, out_dir / file_name)
    except Exception as e:
        print(f"Error copying template files: {e}")
        return

    # Parse file lines and save into content list (removes comments)
    records = []
    next_solver_constraint_id = 1
    passthrough_alias_counter = 0
    for line in lines:
        line = re.sub(r'//.*', '', line).strip() # remove comments
        if not line:
            continue # skip empty lines

        constraint_type = identify_constraint(line) # should return str
        if not constraint_type:
            continue # skip lines without constraint

        module_name, output, lower_bound, upper_bound = generate_constraint(
            constraint_type,
            line,
            output_directory,
            lfsr_width
        )

        if module_name and output:
            solver_constraint_id = next_solver_constraint_id
            db_constraint_id = str(solver_constraint_id)
            next_solver_constraint_id += 1
            passthrough_assign = False
        elif constraint_type in {"inside", "compare"}:
            # inside/compare map directly to solver_output[0].
            solver_constraint_id = 0
            passthrough_alias_counter += 1
            db_constraint_id = f"0.{passthrough_alias_counter}"
            passthrough_assign = False
        else:
            # Preserve pass-through behavior for constraint types that do not
            # emit standalone solver modules.
            solver_constraint_id = next_solver_constraint_id
            db_constraint_id = str(solver_constraint_id)
            next_solver_constraint_id += 1
            passthrough_assign = True

        records.append(
            {
                "solver_constraint_id": solver_constraint_id,
                "db_constraint_id": db_constraint_id,
                "constraint_type": constraint_type,
                "constraint_text": line,
                "module_name": module_name,
                "output": output,
                "passthrough_assign": passthrough_assign,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
            }
        )

    if not records:
        print("No valid constraints found in the file.")

    # Update the copied constraint_solver.sv TODO blocks.
    solver_file = out_dir / "constraint_solver.sv"
    try:
        solver_template = solver_file.read_text()
    except Exception as e:
        print(f"Error reading copied constraint solver file: {e}")
        return

    instance_lines = []
    module_blocks = []
    emitted_module_defs = set()
    used_instance_names = set()

    for record in records:
        idx = record["solver_constraint_id"]
        module_name = record["module_name"]
        output = record["output"]

        if module_name and output:
            instance_name = f"{module_name}_solver"
            if instance_name in used_instance_names:
                instance_name = f"{module_name}_solver_{idx}"
            used_instance_names.add(instance_name)

            instance_lines.append(
                f"    {module_name} {instance_name} (.lfsr_in(lfsr_output), .data(solver_output[{idx}]));"
            )

            if module_name not in emitted_module_defs:
                emitted_module_defs.add(module_name)
                module_blocks.append(output.strip())
        elif record["passthrough_assign"]:
            instance_lines.append(f"    assign solver_output[{idx}] = lfsr_output;")

    instance_block = "\n".join(instance_lines) if instance_lines else "    // No generated constraints"
    modules_block = "\n\n".join(module_blocks) if module_blocks else "// No generated solver modules"

    instantiate_marker = "    // TODO: Instantiate constraint solvers here"
    if instantiate_marker in solver_template:
        solver_template = solver_template.replace(instantiate_marker, instance_block)
    elif "// TODO: Instantiate constraint solvers here" in solver_template:
        solver_template = solver_template.replace("// TODO: Instantiate constraint solvers here", instance_block)
    else:
        print("Warning: First TODO marker not found in constraint_solver.sv")

    define_marker = "// TODO: Define constraint solvers here"
    if define_marker in solver_template:
        solver_template = solver_template.replace(define_marker, modules_block)
    else:
        print("Warning: Second TODO marker not found in constraint_solver.sv")

    try:
        solver_file.write_text(solver_template)
    except Exception as e:
        print(f"Error writing updated constraint solver file: {e}")
        return

    # Emit constraints database for traceability.
    max_val = (1 << lfsr_width) - 1
    db_lines = [
        "# constraint_id|constraint_type|constraint|module_name|lower_bound|upper_bound",
        f"0|reserved|solver_output[0] = lfsr_output|N/A|0|{max_val}",
    ]

    for record in records:
        db_lines.append(
            "|".join(
                [
                    str(record["db_constraint_id"]),
                    str(record["constraint_type"]),
                    str(record["constraint_text"]),
                    str(record["module_name"] if record["module_name"] else "N/A"),
                    str(record["lower_bound"]),
                    str(record["upper_bound"]),
                ]
            )
        )

    try:
        (out_dir / "constraints.db").write_text("\n".join(db_lines) + "\n")
    except Exception as e:
        print(f"Error writing constraints.db: {e}")
        return

    print(f"Generated outputs in: {out_dir}")
    print(f"Updated solver file: {solver_file}")
    print(f"Constraint mapping file: {out_dir / 'constraints.db'}")
    
    
if __name__ == "__main__":
    app()  
    # example:
    # python main.py main constraint.txt constraints_solver_ex1.sv