.PHONY: check validate export test compile

check: compile validate test export

compile:
	python -m compileall scripts tests web db migrations

validate:
	python scripts/validate_catalog.py

export:
	python scripts/export_markdown.py

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
