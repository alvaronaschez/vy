run:
	python main.py
activate:
	. .venv/bin/activate
debug:
	python -m pdb -p $(pgrep python)
format:
	isort main.py text.py
	black main.py text.py
mypy:
	mypy --strict main.py
cloc:
	cloc main.py
doctest:
	python -m doctest vy.py
