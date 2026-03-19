import re

def identify_constraint(line: str) -> str:
    """
    Categorize constraint lines into groups:
    - 'inside': constraints using 'inside' keyword
    - 'assign': direct equality assignments (simple values or enums)
    - 'bit-assign': single-bit assignments (e.g., addr[0] == 1)
    - 'bit-slice': range assignments (e.g., addr[1:5] == 3)
    - 'dist': constraints using 'dist' keyword
    - 'parity': XOR/parity constraints or bit operations
    - 'compare': inequality comparisons

    Returns:
        - str: constraint type
    """    
    # Remove constraint name and braces
    match = re.search(r'{(.+)}', line)
    if not match:
        return None
    
    constraint_body = match.group(1).strip()
    # print(constraint_body)
    
    # Check for 'dist' keyword
    if 'dist' in constraint_body:
        return 'dist'
    
    # Check for 'inside' keyword
    if 'inside' in constraint_body:
        return 'inside'
    
    # Check for compare
    if any(op in constraint_body for op in ['>', '>=', '<', '<=']):
        return 'compare'
    
    # Check for bit-wise operations (XOR, ^) or parity
    if '^' in constraint_body:
        return 'parity'
    
    # Check for bit-slice assignment (e.g., data[7:4], addr[1:0])
    if re.search(r'\w+\[\d+:\d+\]\s*[!=<>]', constraint_body):
        return 'bit-slice'
    
    # Check for bit indexing (e.g., data[0], data[7:4])
    if re.search(r'\w+\[\d+\]\s*(==|!=|<=|>=|<|>)', constraint_body):
        return 'bit-assign'
    
    # Default: simple equality assignment
    if '==' in constraint_body or '!=' in constraint_body:
        return 'assign'
    
    return None

"""
uv run .\stimuli_fsm\main.py .\stimuli_fsm\constraints.txt test/
rst_n == 1'b0
addr inside {[11:20]}
addr > 4'h4 && addr < 4'hC
addr_bus > 8'h20 && addr_bus < 8'h80
state inside {IDLE, FETCH, EXECUTE, WRITE}
payload dist { 0 := 5, 1 := 95 }
data dist { 8'h00 := 10, [8'h01:8'h7F] := 80, 8'hFF := 10 }
parity == (^data)
data[0] == 1'b1
data[7:4] != 4'b1111
"""