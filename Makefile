PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
DB := vendor/dubhacks/data/sandbox.db

.PHONY: run run-ui setup test life-signals

run: setup
	$(BIN)/streamlit run app/console_app.py --server.headless true --server.address 0.0.0.0 --server.port 8501

run-ui: setup
	$(BIN)/streamlit run app/streamlit_app.py --server.headless true --server.address 0.0.0.0 --server.port 8501

setup: $(BIN)/streamlit $(DB)

$(BIN)/streamlit: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

$(DB):
	git clone --depth 1 https://github.com/mageshkumarj/dubhacks vendor/dubhacks

test: setup
	DUBHACKS_DB=$(DB) $(BIN)/python -m pytest -q tests

life-signals: setup
	DUBHACKS_DB=$(DB) $(BIN)/python -m harness.upsell.signals
