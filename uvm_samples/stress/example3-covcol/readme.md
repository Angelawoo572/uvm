This example contains a DUT with only 4 addresses that are R/W addresses. The addresses are:
```
  localparam MODE0_OFFSET = 4;
  localparam MODE1_OFFSET = 8;
  localparam MODE2_OFFSET = 12;
  localparam ARRAY_OFFSET = 16;
```

The last address, however, indexes into an array inside the DUT. The array has ARRAY_SIZE elements.

The UVM testbench architecture contains: test, environment, agent, monitor, driver, coverage collector, and a top-level testbench that instantiates everything. 
This examples focuses on coverage collection, so most of the differences appear in cov.svh
