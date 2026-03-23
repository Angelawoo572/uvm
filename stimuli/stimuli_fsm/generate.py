import re

from generate_compare import generate_compare
from generate_inside import generate_inside
from generate_dist import generate_dist
from generate_assign import generate_assign
from generate_bit_assign import generate_bit_assign
from generate_bit_slice import generate_bit_slice

def generate_constraint(constraint_type: str, line: str, output_directory: str = "test", lfsr_width: int = 32) -> tuple:
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

    default_lower_bound = 0
    default_upper_bound = (1 << lfsr_width) - 1
    
    match = re.search(r'{(.+)}', line)
    line = match.group(1).strip()
    
    if constraint_type == 'inside':
        lower_bound, upper_bound = generate_inside(line, lfsr_width=lfsr_width)
        return (None, None, lower_bound, upper_bound) # return None for module name and module content since we don't need to generate a module for inside constraint. We will implement the inside constraint in the main stimuli_fsm module. We only need to return the lower and upper bound for the inside constraint.
    
    elif constraint_type == 'compare':
        lower_bound, upper_bound = generate_compare(line, lfsr_width=lfsr_width)
        return (None, None, lower_bound, upper_bound)
    
    elif constraint_type == 'dist':
        output = generate_dist(line, lfsr_width=lfsr_width)
        module_name = f"{line.split()[0]}_dist_module"
        return (module_name, output, default_lower_bound, default_upper_bound)

    elif constraint_type == 'assign': 
        output = generate_assign(line, lfsr_width=lfsr_width)
        module_name = f"{line.split()[0]}_assign_module"
        return (module_name, output, default_lower_bound, default_upper_bound)

    elif constraint_type == 'bit-assign':
        output = generate_bit_assign(line, lfsr_width=lfsr_width)
        var_name = line.split('[')[0].strip()
        module_name = f"{var_name}_bit_assign_module"
        return (module_name, output, default_lower_bound, default_upper_bound)

    elif constraint_type == 'bit-slice':
        output = generate_bit_slice(line, lfsr_width=lfsr_width)
        var_name = line.split('[')[0].strip()
        module_name = f"{var_name}_bit_slice_module"
        return (module_name, output, default_lower_bound, default_upper_bound)
    
    return ("", "", default_lower_bound, default_upper_bound)