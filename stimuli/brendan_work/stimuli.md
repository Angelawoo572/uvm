**Constraints to solve for:**
1. inside
- Bounded LFSR only

2. addr > a, addr < b
- Bounded LFSR 
- LFSR should pick range proportional to size: 

**example:**
For $addr < 5, addr > 12$ in `bit [3:0]`
$$addr \in [0, 4] \cup [13, 15]$$
$$|addr| = 8$$
Use Bounded LFSR from `0` to `7`
``` 
assign addr = lfsr_out ? lfsr_out <= 4 : lfsr_out + 8;
```

3. enum types
- Bounded LFSR only
- Parser resolves enum to integer set of valid values

4. dist
- Bounded LFSR
- Constraint solver: weight table 

5. bit-wise constraint (e.g. parity)
- Bounded LFSR
- Mask `bit [1:0]` depending on constraint

## Regex matching of constraints
1. Assign
```
# Regex to capture: variable, [msb:lsb], and the value
# Example: constraint align_32 {addr[1:0] == 0;}
pattern = r"constraint\s+\w+\s*\{(\w+)(?:\[(\d+):(\d+)\])?\s*==\s*([^;]+);?\s*\}"
match = re.search(pattern, constraint_line)
```

2. dist
```
# 1. Clean up the input string
# Remove comments (// ...)
line = re.sub(r'//.*', '', constraint_line)
# Extract variable name and the content inside {}
match = re.search(r'(\w+)\s+dist\s*\{(.*)\}', line)
```
