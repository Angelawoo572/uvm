module multirange_solver #(
    parameter int WIDTH    = 32,
    parameter int N_REGIONS = 4
)(
    input  logic [WIDTH-1:0] lfsr_in,
    input  logic [WIDTH-1:0] min_bounds [N_REGIONS],
    input  logic [WIDTH-1:0] max_bounds [N_REGIONS],
    output logic [WIDTH-1:0] result
);
    logic [WIDTH:0]  spans      [N_REGIONS];
    logic [WIDTH+$clog2(N_REGIONS)-1:0] total_span;
    logic [63:0]     scaled_rand;
    logic [WIDTH+$clog2(N_REGIONS)-1:0] r;
    logic [WIDTH+$clog2(N_REGIONS)-1:0] cumulative [N_REGIONS+1];

    always_comb begin
        // 1. Calculate spans and total
        // $display("%d %d %d", min_bounds[0], min_bounds[1], min_bounds[2]);
        total_span = '0;
        for (int i = 0; i < N_REGIONS; i++) begin
            spans[i]   = (max_bounds[i] - min_bounds[i]) + 1;
            total_span += spans[i];
        end

        // 2. Build cumulative span boundaries
        //    cumulative[i] = sum of spans[0..i-1]
        //    so region i occupies [cumulative[i], cumulative[i+1])
        cumulative[0] = '0;
        for (int i = 0; i < N_REGIONS; i++)
            cumulative[i+1] = cumulative[i] + spans[i];
        // $display("%d %d %d", cumulative[0], cumulative[1], cumulative[2]);
        // 3. Scale LFSR to [0 : total_span-1]
        scaled_rand = (64'(lfsr_in) * 64'(total_span)) >> 32;
        r = scaled_rand[WIDTH+$clog2(N_REGIONS)-1:0];
        
        // $display("%d %d", scaled_rand, r);
        // 4. Walk cumulative boundaries to find which region r fell into
        result = min_bounds[0] + r[WIDTH-1:0];  // default (also covers region 0)
        for (int i = 0; i < N_REGIONS; i++) begin
            if (r >= cumulative[i])
                result = min_bounds[i] + (r - cumulative[i]);
        end
    end
endmodule