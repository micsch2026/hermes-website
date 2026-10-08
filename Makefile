# Hermes-Site — Pflicht-Checks mit EINEM kanonischen Kommando: make test
#
# Bündelt die projekteigenen Suiten:
#   tests/test_*.py            — Python-Checks (Overview-Builder, Seiten, ...)
#   tests/verify_overview_charts.js — Node-vm-Harness der Kommandocenter-Charts
#
# Konvention (Skill hermes-site-management): Neue Seiten/Builder bekommen eine
# tests/test_<name>_*.py-Suite; damit laufen sie hier automatisch mit.

PY   ?= /usr/bin/python3
NODE ?= node

test:
	@fail=0; \
	for t in tests/test_*.py; do \
	  echo "== $$t"; \
	  $(PY) $$t || fail=1; \
	done; \
	if [ -f tests/verify_overview_charts.js ]; then \
	  echo "== tests/verify_overview_charts.js"; \
	  $(NODE) tests/verify_overview_charts.js || fail=1; \
	fi; \
	if [ $$fail -eq 0 ]; then echo "SITE TESTS OK"; else echo "SITE TESTS FAILED"; exit 1; fi

.PHONY: test
