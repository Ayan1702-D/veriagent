.PHONY: dev test lint eval

PYTHON ?= python3

dev:
	cd backend && uvicorn veriagent.main:app --reload --host 0.0.0.0 --port 8000

test:
	cd backend && pytest

lint:
	cd backend && ruff check src tests eval && ruff format --check src tests eval && mypy

eval:
	cd backend && $(PYTHON) -m eval.run_eval