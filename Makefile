.PHONY: check validate export test compile

check: compile validate test export

compile:
	python -m compileall scripts tests web

validate:
	python scripts/validate_catalog.py

export:
	python scripts/export_markdown.py

test:
	python -m pytest -q
