#script written by S. Pagliarini on July 2022. works well in genus 18.10

# to modify this script, look for TODO markers

#TODO change this RTL path to point to the folder containing your design. the current structure works if *this* script is placed in your labN folder(s)
set RTL_PATH		"./"
set LIB_PATH 		"lib/"
set LEF_PATH		"lib/"
set TLEF_PATH		"lib/"


# TODO change my name to indicate which module is the top level. the default name here, "prime", corresponds to lab1 provided file
set DESIGN "dist_example_slave_err_mod"
#set DESIGN "fast_prime"

suppress_messages {LBR-30 LBR-31 LBR-40 LBR-41 LBR-72 LBR-77 LBR-162 PHYS-12 PHYS-13 PHYS-14 PHYS-15}

set_db lp_power_unit mW

# Baseline Libraries
set LIB_LIST {asap7sc7p5t_AO_LVT_TT_nldm_211120.lib asap7sc7p5t_INVBUF_LVT_TT_nldm_220122.lib asap7sc7p5t_OA_LVT_TT_nldm_211120.lib asap7sc7p5t_SEQ_LVT_TT_nldm_220123.lib asap7sc7p5t_SIMPLE_LVT_TT_nldm_211120.lib}
set LEF_LIST {asap7_tech_4x_201209.lef asap7sc7p5t_28_L_4x_220121a.lef}

# All HDL files, separated by spaces
set RTL_LIST {dist_example_slave_err_mod.sv}
#set RTL_LIST {fast_prime.v}

set_db init_lib_search_path "$LIB_PATH $LEF_PATH $TLEF_PATH"
set_db init_hdl_search_path $RTL_PATH 
set_db / .library "$LIB_LIST"
set_db lef_library "$LEF_LIST"

read_hdl ${RTL_LIST} -sv

# Elaborate the top level
elaborate $DESIGN

# the library uses picoseconds as time unit. this causes confusion because default unit in genus is ns
# TODO: change this number to change the clock period
set PERIOD 100000

#create_clock -name "clk" -period $PERIOD [get_ports clk]
#set_input_delay -clock clk 1 [all_inputs]
#set_output_delay -clock clk [expr $PERIOD/2] [all_outputs]

# GENERIC SYNTHESIS
syn_generic

# MAPPING
syn_map

# OPT
syn_opt

#TODO this will overwrite any previous netlist you might have. comment out if you don't want this behavior
#write_hdl > netlist.v

#TODO uncomment these lines to get reports directly on text files
# REPORTING (Timing, Area, Gates, Power)
#report timing > ./genus_timing.rep
report area   > ./genus_area.rep
#report gates  > ./genus_cell.rep
#report power  > ./genus_power.rep


