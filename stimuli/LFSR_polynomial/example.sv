`default_nettype none
function automatic logic feedback_fn (
    input logic [31:0] s,
    input int W
);
    case (W)
        4:  feedback_fn = s[3] ^ s[0];                     // x^4 + x + 1
        5:  feedback_fn = s[4] ^ s[2];                     // x^5 + x^3 + 1
        6:  feedback_fn = s[5] ^ s[4];                     // x^6 + x^5 + 1
        7:  feedback_fn = s[6] ^ s[5];                     // x^7 + x^6 + 1
        8:  feedback_fn = s[7] ^ s[5] ^ s[4] ^ s[3];       // x^8 + x^6 + x^5 + x^4 + 1
        16: feedback_fn = s[15] ^ s[13] ^ s[12] ^ s[10];
        default: feedback_fn = s[W-1] ^ s[1]; // fallback（不保证primitive）
    endcase
endfunction

