module multirange_solver #(
    parameter WIDTH = 32
)(
    input  logic [WIDTH-1:0] lfsr_in,
    // Region 0 Bounds
    input  logic [WIDTH-1:0] min0,
    input  logic [WIDTH-1:0] max0,
    // Region 1 Bounds
    input  logic [WIDTH-1:0] min1,
    input  logic [WIDTH-1:0] max1,
    
    output logic [WIDTH-1:0] result
);

    logic [WIDTH:0]   span0, span1;
    logic [WIDTH:0]   total_span;
    logic [63:0]      scaled_rand;
    logic [WIDTH-1:0] r;

    always_comb begin
        // 1. Calculate the weight of each region
        span0 = (max0 - min0) + 1'b1;
        span1 = (max1 - min1) + 1'b1;
        total_span = span0 + span1;

        // 2. Scale LFSR to [0 : total_span-1]
        scaled_rand = (64'(lfsr_in) * total_span) >> 32;
        r = scaled_rand[WIDTH-1:0];

        // 3. Region Selection Logic
        if (r < span0) begin
            // We landed in the first region
            result = min0 + r;
        end else begin
            // We landed in the second region
            // Subtract the first span to find the local offset for region 1
            result = min1 + (r - span0[WIDTH-1:0]);
        end
    end

endmodule