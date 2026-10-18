PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
DB := vendor/dubhacks/data/sandbox.db

.PHONY: run setup test

run: setup
	$(BIN)/streamlit run app/scroll_app.py --server.headless true --server.address 0.0.0.0 --server.port 8501

setup: $(BIN)/streamlit $(DB)

$(BIN)/streamlit: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

$(DB):
	git clone --depth 1 https://github.com/mageshkumarj/dubhacks vendor/dubhacks

test: setup
	DUBHACKS_DB=$(DB) $(BIN)/python -m pytest -q tests
