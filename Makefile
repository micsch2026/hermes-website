# Hermes-Site — Pflicht-Checks mit EINEM kanonischen Kommando: make test
#
# Bündelt die projekteigenen Suiten:
#   tests/test_*.py            — Python-Checks (Overview-Builder, Seiten, ...)
#   tests/verify_overview_charts.js — Node-vm-Harness der Kommandocenter-Charts
#   tests/verify_radar.js      — Node-DOM-Stub-Harness des Rotations-Radars v2
#   tests/verify_bot_curves.js — Node-Chart-Harness der Echtgeld-Konto-Kurven
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
	if [ -f tests/verify_radar.js ]; then \
	  echo "== tests/verify_radar.js"; \
	  $(NODE) tests/verify_radar.js || fail=1; \
	fi; \
	if [ -f tests/verify_llm_chart.js ]; then \
	  echo "== tests/verify_llm_chart.js"; \
	  $(NODE) tests/verify_llm_chart.js || fail=1; \
	fi; \
	if [ -f tests/verify_bot_curves.js ]; then \
	  echo "== tests/verify_bot_curves.js"; \
	  $(NODE) tests/verify_bot_curves.js || fail=1; \
	fi; \
	if [ $$fail -eq 0 ]; then echo "SITE TESTS OK"; else echo "SITE TESTS FAILED"; exit 1; fi

.PHONY: test
