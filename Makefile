PYTHON  ?= python3
MAP     ?= maps/easy_1.txt
SOURCES  = main.py map_parser.py models.py pathfinder.py simulator.py

MYPY_FLAGS = --warn-return-any --warn-unused-ignores \
             --ignore-missing-imports --disallow-untyped-defs \
             --check-untyped-defs

.PHONY: install run debug clean lint lint-strict test help

help:
	@echo "make install      install the development dependencies"
	@echo "make run          run the simulation (MAP=maps/easy_1.txt)"
	@echo "make debug        run the simulation under pdb"
	@echo "make lint         run flake8 and mypy"
	@echo "make lint-strict  run flake8 and mypy --strict"
	@echo "make test         run the unit tests"
	@echo "make clean        remove caches and temporary files"

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) main.py $(MAP)

debug:
	$(PYTHON) -m pdb main.py $(MAP)

lint:
	flake8 .
	mypy . $(MYPY_FLAGS)

lint-strict:
	flake8 .
	mypy . --strict

test:
	$(PYTHON) -m pytest tests -q

clean:
	rm -rf __pycache__ tests/__pycache__ .mypy_cache .pytest_cache
	find . -name '*.pyc' -delete