# Simulator
XRUN = xrun

# Flags
UVM_FLAGS = -uvm
COV_FLAGS = -coverage all
RUN_FLAGS = -coverage all -covoverwrite -cov_cgsample -covdut dut
GUI_FLAGS = -gui -debug

# Stamp files (used to track completion)
ITF_STAMP    = .itf.elab
STRESS_STAMP = .stress.elab
DUT_STAMP    = .dut.elab

# Default target
all: run

# -----------------------------
# Elaboration steps (incremental)
# -----------------------------

$(ITF_STAMP): itf.sv
	$(XRUN) -elaborate $(UVM_FLAGS) $<
	touch $@

$(STRESS_STAMP): stress.pkg.sv
	$(XRUN) -elaborate $(UVM_FLAGS) $(COV_FLAGS) $<
	touch $@

$(DUT_STAMP): dut.sv
	$(XRUN) -elaborate $(UVM_FLAGS) $<
	touch $@

# -----------------------------

run: $(ITF_STAMP) $(STRESS_STAMP) $(DUT_STAMP) tb_dut.sv
	$(XRUN) $(UVM_FLAGS) tb_dut.sv $(RUN_FLAGS) || true

# -----------------------------

gui: $(ITF_STAMP) $(STRESS_STAMP) $(DUT_STAMP) tb_dut.sv
	$(XRUN) $(UVM_FLAGS) tb_dut.sv $(RUN_FLAGS) $(GUI_FLAGS)

# -----------------------------

clean:
	rm -rf *.elab .*.elab xrun.* xcelium.d waves.shm *.log *.key

.PHONY: all run gui clean
