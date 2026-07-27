# Common tasks for RA / lab machines.
# Lab default: conda env from environment.yml.

.PHONY: setup check help

help:
	@echo "Targets:"
	@echo "  make setup  - create/update conda env hmet-preprocess"
	@echo "  make check  - run scripts/check_env.py (activate conda first)"

setup:
	./setup.sh

check:
	./setup.sh --check-only
