import re
from pathlib import Path

from generate_dist import generate_dist
from generate_assign import generate_assign
from generate_bit_assign import generate_bit_assign
from generate_bit_slice import generate_bit_slice

# TODO: have lfsr_width as input. then have generate churn out lower and upper bound for random variable
#       for compare/inside, have output be None and only give output and input. have main implemenet constraint_id
def _write_module_file(module_name: str, output: str, output_directory: str) -> None:
    """Create the output directory if needed, then write the generated module file."""
    out_dir = Path(output_directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_file = out_dir / f"{module_name}.sv"
    with open(output_file, "w") as f:
        f.write(output)


def generate_constraint(constraint_type: str, line: str, output_directory: str = "test", lfsr_width: int = 32) -> tuple[str, str]:
    """
    Generate constraint module based on the identified constraint type and the original line.
    The original line is needed to extract variable names, bounds, etc. for generating the module
    """
    op_type = [
        'dist',
        'inside',
        'compare',
        'parity',
        'bit-slice',
        'bit-assign',
        'assign'
    ]

    if constraint_type not in op_type:
        raise ValueError(f"Unsupported constraint type: {constraint_type}")
    
    match = re.search(r'{(.+)}', line)
    line = match.group(1).strip()
    print(constraint_type, "line: ", line)

    if constraint_type == 'dist':
        output = generate_dist(line, lfsr_width=lfsr_width)
        module_name = f"{line.split()[0]}_dist_module"
        _write_module_file(module_name, output, output_directory)
        return (module_name, output) # return variable name and generated module

    elif constraint_type == 'assign': 
        output = generate_assign(line, lfsr_width=lfsr_width)
        module_name = f"{line.split()[0]}_assign_module"
        _write_module_file(module_name, output, output_directory)
        return (module_name, output) # return variable name and generated module

    elif constraint_type == 'bit-assign':
        output = generate_bit_assign(line, lfsr_width=lfsr_width)
        var_name = line.split('[')[0].strip()
        module_name = f"{var_name}_bit_assign_module"
        _write_module_file(module_name, output, output_directory)
        return (module_name, output)

    elif constraint_type == 'bit-slice':
        output = generate_bit_slice(line, lfsr_width=lfsr_width)
        var_name = line.split('[')[0].strip()
        module_name = f"{var_name}_bit_slice_module"
        _write_module_file(module_name, output, output_directory)
        return (module_name, output)

    return ("", "")