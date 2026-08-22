.PHONY: fmt lint test all

fmt:
	ruff check --select I --fix
	ruff format

lint:
	ruff check
	mypy


test:
	python3 -m pytest

all: fmt lint test
