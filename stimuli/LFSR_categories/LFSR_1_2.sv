`default_nettype none

// (SEQ ITEM) basic item
// basic item only have rand addr
class basic_item;
  rand int addr;
  function new(string name="basic_item");
  endfunction
endclass

// (SEQ ITEM) tem-level constraints
// CONSTRAINT: addr > 1234, addr < 5555
class constrained_item extends basic_item;
  // Equivalent to: 1234 < addr < 5555
  constraint c_addr_bounds {
    addr > 1234;
    addr < 5555;
  }
  function new(string name="constrained_item");
    super.new(name);
  endfunction
endclass

// Part 1  model as a task
// randomize B with {addr inside [A:3]}
task automatic do_part1_inline_constraint();
  basic_item A;
  basic_item B;
  int diff;

  int A_low;   // for [A:3] lower bound
  int A_high;  // upper bound

  A = new("A");
  B = new("B");

  // A_low=1, A_high=3 match [1:3]
  A_low  = 1;
  A_high = 3;

  // Randomize A without constraints (basic)
  assert(A.randomize()) else $fatal(1, "A.randomize failed");

  // inline constraint on B
  // option 1: fixed [1:3]
  // assert(B.randomize() with { addr inside {[1:3]}; });
  // option 2: [A:3]
  assert(B.randomize() with { addr inside {[A_low:A_high]}; })
    else $fatal(1, "B.randomize with inline constraint failed");

  diff = B.addr - A.addr;

  $display("\n=== Part (1) Inline constraint ===");
  $display("A.addr = %0d", A.addr);
  $display("B.addr = %0d  (must be in [%0d:%0d])", B.addr, A_low, A_high);
  $display("diff = B - A = %0d", diff);

  // sanity check
  if (!(B.addr >= A_low && B.addr <= A_high))
    $fatal(1, "Part (1) FAILED: B.addr not in range");
endtask


// Part 2 test: item-level constraints always active
task automatic do_part2_item_constraints();
  constrained_item C;

  C = new("C");

  // Part (2): randomize should ALWAYS obey the class constraint
  assert(C.randomize()) else $fatal(1, "C.randomize failed");

  $display("\n=== Part (2) Item-level constraints ===");
  $display("C.addr = %0d  (must satisfy 1234 < addr < 5555)", C.addr);

  if (!(C.addr > 1234 && C.addr < 5555))
    $fatal(1, "Part (2) FAILED: C.addr out of bounds");
endtask

// Top TB
module tb;
  initial begin
    // Run Part (1)
    do_part1_inline_constraint();

    // Run Part (2)
    do_part2_item_constraints();

    $display("\nALL DONE");
    $finish;
  end
endmodule: tb
