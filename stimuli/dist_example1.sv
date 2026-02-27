// --- Generated Weighted Random Logic for 'data3' ---
// Input LFSR Width: 32 bits
module dist_for_data3(input logic [31:0] lfsr_in, output logic [31:0] data3);
logic [63:0] scaled_rand;

// Scaling: Map LFSR to [0 : 29]
assign scaled_rand = (lfsr_in * 30) >> 32;

always_comb begin
    case (scaled_rand) inside
        [0:9]: data3 = 0;
        [10:11]: data3 = 1;
        [12:13]: data3 = 2;
        [14:15]: data3 = 3;
        [16:17]: data3 = 4;
        [18:19]: data3 = 5;
        [20:29]: data3 = 100;
        default: data3 = '0; // Should not be reached
    endcase
end
endmodule 
// if lfsr == 2 bits and 1 := 10 2 := 10 3:= 10
// lfsr_in = 0 --> 0
// lfsr_in = 1 --> 30 1E 0001 1110 / 4 --> 0000 0111 (7)
// lfsr_in = 2 --> 60 111100 / 4 --> 0000 1111 (15)
// lfsr_in = 3 --> 90 1011010 / 4 --> 0001 0110 (22)
// --> number of RNGs not divisble by number of values
// mod operation
// lfsr_in % 3

// data3 dist { 0 := 10, [1:5] :/ 10, 100 := 10};

// total weight 15
// two issues:
// 1. product could be huge depending on weight
// 2. some values are biased 
