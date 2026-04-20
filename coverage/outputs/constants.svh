// widths for the ports of the design
localparam ADDR_WIDTH = 16;
localparam DATA_WIDTH = 32;

// number of elements in the array that serves as storage
localparam ARRAY_SIZE = 8;

// addresses (offsets) for the locations to which you can read or write
localparam MODE0_OFFSET = 4;
localparam MODE1_OFFSET = 8;
localparam MODE2_OFFSET = 12;
localparam ARRAY_OFFSET = 16;
localparam ARRAY_OFFSET_CEILING = ARRAY_OFFSET + ARRAY_SIZE -1;

localparam [DATA_WIDTH-1:0] MODE0_TYPE1 = 55;
localparam [DATA_WIDTH-1:0] MODE0_TYPE2 = 111;

localparam [DATA_WIDTH-1:0] MODE1_HIGH = '1;
localparam [DATA_WIDTH-1:0] MODE1_LOW = '0;

localparam [DATA_WIDTH-1:0] MODE2_SHORT = DATA_WIDTH'('hA);
localparam [DATA_WIDTH-1:0] MODE2_LONG = DATA_WIDTH'('hF);
localparam [DATA_WIDTH-1:0] MODE2_AVERAGE = DATA_WIDTH'('hC);
