.PHONY: install run dev test seed clean

install:
	pip install -r requirements.txt

run:
	uvicorn encounter.main:app --host 0.0.0.0 --port 8000

dev:
	uvicorn encounter.main:app --reload --port 8000

test:
	pytest -q

seed:
	python -m encounter.seed

clean:
	rm -rf var .pytest_cache __pycache__ encounter/__pycache__
