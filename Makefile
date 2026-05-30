run:
	python main2.py
activate:
	. .venv/bin/activate
debug:
	python -m pdb -p $(pgrep python)
format:
	isort main2.py text.py
	black main2.py text.py
mypy:
	mypy --strict main2.py
cloc:
	cloc main2.py
doctest:
	python -m doctest main2.py
