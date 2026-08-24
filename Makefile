.PHONY: fmt lint all

all: fmt lint

fmt:
	ruff check --select I --fix
	ruff format

lint:
	ruff check
	mypy
