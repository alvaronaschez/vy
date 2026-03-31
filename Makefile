run:
	python main.py
activate:
	. .venv/bin/activate
debug:
	python -m pdb -p $(pgrep python)
format:
	black main.py
mypy:
	mypy --strict main.py
cloc:
	cloc main.py
doctest:
	python -m doctest main.py
