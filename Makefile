PYTHON ?= python
UV ?= uv

.PHONY: install dev run test lint format validate metrics

install:
	$(UV) venv
	. .venv/bin/activate && $(UV) pip install -r requirements.txt

dev:
	. .venv/bin/activate && $(UV) pip install -e '.[dev]'

run:
	. .venv/bin/activate && $(UV) run uvicorn server.app:app --host 0.0.0.0 --port 8000

test:
	. .venv/bin/activate && pytest -q

lint:
	. .venv/bin/activate && ruff check .

format:
	. .venv/bin/activate && ruff format .

validate:
	. .venv/bin/activate && openenv validate

metrics:
	. .venv/bin/activate && $(PYTHON) scripts/generate_metrics_plot.py --tasks tasks.jsonl --log full_run.log --out assets/metrics.png --line-out assets/metrics_line.png --summary-out assets/metrics_summary.json
