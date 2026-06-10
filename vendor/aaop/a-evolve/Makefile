.PHONY: install test lint fmt

install:
	pip install -e ".[all,dev]"

test:
	pytest tests/ -v

lint:
	ruff check agent_evolve/

fmt:
	ruff format agent_evolve/
