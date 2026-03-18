This example contains a DUT with only 3 addresses that are R/W addresses. The addresses are:
```
  localparam MODE0_OFFSET = 4;
  localparam MODE1_OFFSET = 8;
  localparam MODE2_OFFSET = 12;
```

The UVM testbench will do a simple reset for a single clock cycle, followed by random writes to each of the registers. Testbench ends after 4 clock cycles.

The UVM testbench architecture contains: test, environment, agent, monitor, driver, coverage collector, and a top-level testbench that instantiates everything. 
All of these components are very simplified, this really is a simple basic testbench. 
The stimuli relies on a single request item and a couple of silly sequences. 
The coverage collector checks that every address is accessed and is also very simple.
