.PHONY: lint lint-fix format format-check

lint:
	@ruff check .

lint-fix:
	@ruff check . --fix

format:
	@black .

format-check:
	@black --check .
