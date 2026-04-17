all:
	python3 parsed_to_cov.py outputs/cov_parsed.json outputs/cov_usable.json outputs/constants.svh
	python3 gen_cov.py outputs/cov_usable.json outputs/coverage.sv outputs/constants.svh

debug:
	python3 -m pdb gen_cov.py outputs/cov_usable.json outputs/coverage.sv

parse_1:
	python ../parser/sv_to_json.py ../uvm_samples/stress/example1-basic/cov.svh outputs/cov_parsed.json
	cp ../uvm_samples/stress/example1-basic/constants.svh outputs/constants.svh

parse_3:
	python ../parser/sv_to_json.py ../uvm_samples/stress/example3-covcol/cov.svh outputs/cov_parsed.json
	cp ../uvm_samples/stress/example3-covcol/constants.svh outputs/constants.svh

clean:
	rm outputs/cov_usable.json
	rm outputs/coverage.sv