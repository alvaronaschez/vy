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
	mypy --strict main.py text.py
cloc:
	cloc main.py text.py
doctest:
	python -m doctest main2.py
