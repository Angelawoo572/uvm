all:
	python3 parsed_to_cov.py cov_parsed.json constants.svh cov_usable.json
	python3 gen_cov.py cov_usable.json coverage.sv

clean:
	rm cov_usable.json
	rm coverage.sv