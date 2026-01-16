QUESTA_HOME ?= $(dir $(shell which vsim))/..
UVM_HOME ?= $(QUESTA_HOME)/verilog_src/uvm-1.1
UVM_SRC = $(UVM_HOME)/src
UVM_REG_HOME = ./uvm/src/uvm_register-2.0/src

WB_SRCS = ./wishbone
SEQUENCES_SRCS = ./sequences
MII_SRCS = ./mac_mii
TEST_SRCS = ./tests
ETH_SRCS = ./eth
ENV_SRCS = ./env
TOP_SRCS = ./top_modules

WB_BUS_SOURCES =  \
        $(WB_SRCS)/wb_slave_mem.sv \
        $(WB_SRCS)/wishbone_bus_syscon_if.sv  \
        $(TOP_SRCS)/test_params_pkg.sv \
        $(MII_SRCS)/mii_if.sv \
        $(MII_SRCS)/mac_mii_protocol_module.sv \
        $(ETH_SRCS)/wb_register_pkg.sv \
        $(ETH_SRCS)/mac_info_pkg.sv  \
        $(WB_SRCS)/wishbone_pkg.sv \
        $(WB_SRCS)/wb_m_bus_driver_bfm.sv \
        $(WB_SRCS)/wb_bus_monitor_bfm.sv \
        $(MII_SRCS)/mac_mii_pkg.sv \
        $(MII_SRCS)/mii_rx_driver_bfm.sv \
        $(MII_SRCS)/mii_tx_driver_bfm.sv \
        $(SEQUENCES_SRCS)/sequences_pkg.sv \
        $(ENV_SRCS)/env_pkg.sv \
        $(TEST_SRCS)/tests_pkg.sv \
        $(TOP_SRCS)/top_mac_hdl.sv \
        $(TOP_SRCS)/top_mac_tb.sv

MAC_SRC_DIR = ./mac_core
MAC_SRCS = $(MAC_SRC_DIR)/eth_top.v

normal: clean cmp sim

gui: clean cmp
	vsim +nowarnTSCALE -voptargs="+acc" top_mac_hdl top_mac_tb -suppress 3829 -suppress 8887

sim: 
	vsim +nowarnTSCALE -c top_mac_hdl top_mac_tb -suppress 3829 -do "run -all" -suppress 8887
	@echo " " 
	@echo "---- To verify your output is correct scroll up the output to above"
	@echo "---- the report summary and look for the following lines:"
	@echo " " 
	@echo " Number of Ethernet transactions sent (Tx) by the MAC: 3      " 
	@echo " Number of Ethernet transactions received (Rx) by the MAC: 4  "
	@echo " Number of Tx Errors: 0                                       "
	@echo " Number of Rx Errors: 0                                       "
	@echo " "
	@echo " Number of Wishbone 0 Slave Memory write transactions: 134    "
	@echo " Number of Wishbone 0 Slave Memory read  transactions: 135    "
	@echo " Number of Wishbone 0 Non-Slave Memory write cycles: 33       "
	@echo " Number of Wishbone 0 Non-Slave Memory read cycles: 22        "
	@echo " Wishbone 0 Slave Memory read error count: 0                  "
	@echo " "

bus: clean cmp
	vsim +nowarnTSCALE -c top_mac_hdl top_mac_tb -suppress 3829 -do "run -all"

debug: clean cmp
	vsim +nowarnTSCALE -gui -voptargs="+acc" top_mac_hdl top_mac_tb -suppress 3829 -UVMdebug

uvm_cmp: 
	test -e work || vlib work
	vlog +incdir+$(UVM_SRC) +incdir+$(UVM_REG_HOME) $(UVM_REG_HOME)/uvm_register_pkg.sv

qvl_cmp:
	vlog -novopt -sv -mfcu +define+QVL_ASSERT_ON+QVL_COVER_ON $(QUESTA_HOME)/qvl_src/qvl_monitors/gigabit_ethernet/qvl_gigabit_ethernet_mii_monitor.sv \
           -y $(QUESTA_HOME)/verilog_src/std_ovl -y $(QUESTA_HOME)/qvl_src/qvl_monitors/gigabit_ethernet +incdir+$(QUESTA_HOME)/verilog_src/std_ovl \
           +incdir+$(QUESTA_HOME)/qvl_src/qvl_monitors/gigabit_ethernet +incdir+$(QUESTA_HOME)/qvl_src/qvl_checkers +libext+.sv

cmp: clean uvm_cmp sv_bus_cmp

sv_bus_cmp: 
	test -e work || vlib work
	vlog +incdir+$(MAC_SRC_DIR) -y $(MAC_SRC_DIR) +libext+.v $(MAC_SRCS)
	vlog -suppress 2223 -suppress 2181  $(WB_BUS_SOURCES) \
	+incdir+$(WB_SRCS) \
	+incdir+$(ETH_SRCS) \
	+incdir+$(ANALYSIS_SRCS) \
	+incdir+$(WB_MII_SRCS) \
	+incdir+$(SEQUENCES_SRCS) \
	+incdir+$(MII_SRCS) \
	+incdir+$(TEST_SRCS) \
	+incdir+$(ENV_SRCS) \
	+incdir+$(UVM_REG_HOME) \
	+incdir+$(UVM_SRC)

tarball: clean tar

tar:
	@rm -f EF_wb_mac_config_vif_pm.tar; \
	rm -f EF_wb_mac_config_vif_pm.tar.gz ; \
	cd .. ; \
	tar -zcf EF_wb_mac_config_vif_pm/EF_wb_mac_config_vif_pm.tgz \
	EF_wb_mac_config_vif_pm/env \
	EF_wb_mac_config_vif_pm/eth \
	EF_wb_mac_config_vif_pm/mac_core \
	EF_wb_mac_config_vif_pm/mac_mii \
	EF_wb_mac_config_vif_pm/Makefile \
	EF_wb_mac_config_vif_pm/uvm \
	EF_wb_mac_config_vif_pm/README.txt \
	EF_wb_mac_config_vif_pm/sequences \
	EF_wb_mac_config_vif_pm/tests \
	EF_wb_mac_config_vif_pm/top_modules \
	EF_wb_mac_config_vif_pm/wishbone ;\
	cd EF_wb_mac_config_vif_pm; 

clean: .FRC
	rm -rf  *.tmp  *.log  log transcript work *.wlf vsim.fcdb *.vstf
	find . -name "*~"
        
.FRC:
