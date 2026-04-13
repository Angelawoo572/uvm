# Stimuli Generation 

## The 5 Basic Types:
1. Bounded range:
```
constraint page_size { transfer_size inside {[1:1024]}; }
```
2. Semi-bounded range:
```
constraint within_upper { start_addr > 32'h0100_0000; }
```
```
constraint within_lower { start_addr < 32'h0104_0000; }
```
3. Enum types:
```
constraint imm_val_c { instr_name inside {C_SRAI, C_SRLI, C_SLLI}; }
```
4. Distribution:
```
constraint type_dist { packet_type dist { [1:3] := 10, 4 := 10, 5 := 1, [10:15] :/ 60 }; }
```
5. Bit assignment:
```
constraint addr_c { start_addr[1:0] == 0; }
```
### Stress Tests
1. Non-power of 2 ranges:
```
constraint len_c { char_len inside {0, 1, [31:33], [63:65], 126, 127}; }
```

## Composite/Second-order Types: 
1. Bit assignment + another basic type:
```
constraint within_range { 
    start_addr < 32'h0104_0000;
    start_addr > 32'h0100_0000; // start_addr inside {[a:b]};
    start_addr[1:0] == 0; // 100
}
```
```
constraint target_bank_c {
    addr inside {[32'h8000_0000 : 32'hBFFF_FFFF]}; 
    addr[2:0] == 3'b000; 
    addr[9:8] == 2'b10; 
}
```
Solver logic ideas:
```
1. Parser does some pre-processing
    - Extract number of constraints applied to every rand variable
    - Find number of bits not constrained/assigned

- New bound = [min >> short_bit : max >> short_bit] --> (output << short_bit || short_val) // in this case short_bit = 2, short_val == 2'b0
- Provide error handling for when no solution is found
```
2. Ordered constraints:
```
constraint within_range { 
    start_addr < (32'h0104_0000 - block_size*4);
    solve start_addr before block_size;
}
```
```
constraint c_mux_select { 
    solve opcode before mux_select;
    if (opcode == `MD_OP_REM) (mux_select == `MD_OUT_REM);
}
```
Solver logic ideas:
```
- Parser generates rand variable priority database:
    - Uses keywords solve ... before ... to assign relative priorities
- Seq <-> seq_item FSM reads from priority database to decide which variable to solve for next
- Seq <-> stim FSM should provide additional inputs (e.g. block_size, opcode) to solver module
```

3. Two rand variables:
```
constraint size_c { tkeep.size() == tdata.size(); }
```
```
constraint valid_reg_c { fwd_addr_reg != bw_addr_reg; }
```
```
constraint addr_valid { start_addr < end_addr; }
```