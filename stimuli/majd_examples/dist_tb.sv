module tb();
    logic [31:0] lfsr_in, data3;
    
    dist_for_data3 dut (.*);

    initial begin 
        $monitor("%t input=%d output=%d %d", $time, lfsr_in, data3, dut.scaled_rand);
        
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100
        std::randomize(lfsr_in);
        #100

        #100 $finish;

    end
endmodule