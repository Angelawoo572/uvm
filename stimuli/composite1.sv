/**
@input: original_min, original_max, fixed_mask = ...0000_0011_0000_0111, fixed_val = ...0000_0010_0000_0000 
**/
function automatic logic [31:0] gen_bound(logic [31:0] val, logic [31:0] mask);
    logic [31:0] res = '0;
    integer shift = 0;
    for (integer i = 0; i < 32; i++) begin
        if (mask[i]) begin
            res[shift] = val[i];
            shift++;
        end
    end
    return res;
endfunction


function automatic logic [31:0] pack_bits(logic [31:0] val, logic [31:0] mask);
    logic [31:0] res = '0;
    integer shift = 0;
    for (integer i = 0; i < 32; i++) begin
        if (mask[i]) begin
            res[i] = val[shift];
            shift++;
        end else begin
            res[i] = 1'b0; 
        end
    end
    return res;
endfunction

module rtl_constraint_solver (
    input  logic [31:0] original_min,
    input  logic [31:0] original_max,
    input  logic [31:0] in_rand,     
    output logic [31:0] out);

    localparam logic [31:0] FIXED_MASK = 32'h0000_0307; // ...0000_0011_0000_0111
    localparam logic [31:0] FIXED_VAL  = 32'h0000_0200; // ...0000_0010_0000_0000 
    localparam logic [31:0] FREE_MASK  = ~FIXED_MASK;

    logic [31:0] compact_min, compact_max;
    logic [31:0] test_min_val, test_max_val;
    logic [31:0] range_size, compact_rand;

    always_comb begin
        // find new bounds
        compact_min = pext(original_min, FREE_MASK);
        compact_max = pext(original_max, FREE_MASK);

        test_min_val = pdep(compact_min, FREE_MASK) | FIXED_VAL;
        if (test_min_val < original_min) begin
            compact_min = compact_min + 1;
        end

        test_max_val = pdep(compact_max, FREE_MASK) | FIXED_VAL;
        if (test_max_val > original_max) begin
            compact_max = compact_max - 1;
        end

        // scale in_rand to fit bounds
        range_size   = (compact_max - compact_min) + 1;
        compact_rand = compact_min + (in_rand % range_size);

        // expand random val and combine with fixed vals
        out = pdep(compact_rand, FREE_MASK) | FIXED_VAL;
    end

endmodule