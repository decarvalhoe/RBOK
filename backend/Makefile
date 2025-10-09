.PHONY: lint lint-fix format format-check

lint:
	@python3 -m ruff check .

lint-fix:
	@python3 -m ruff check . --fix

format:
	@python3 -m black .

format-check:
	@python3 -m black --check .
