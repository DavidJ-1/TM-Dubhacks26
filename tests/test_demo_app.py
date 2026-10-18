"""The judging demo keeps live screens on the console and badges the saved run."""

import ast
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / "app" / name).read_text()


def _function(name: str, function: str) -> str:
    source = _source(name)
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == function)
    return ast.get_source_segment(source, node) or ""


def test_make_run_starts_the_demo_and_keeps_the_other_app():
    makefile = (ROOT / "Makefile").read_text()
    assert "app/demo_app.py" in makefile
    assert "app/streamlit_app.py" in makefile
    assert "PORT ?= 8501" in makefile
    assert "UI_PORT ?= 8502" in makefile
    assert "--server.port $(PORT)" in makefile
    assert "--server.port $(UI_PORT)" in makefile
    assert "--server.port 8501" not in makefile
    assert "--server.port 8502" not in makefile


def test_make_dry_run_uses_the_port_variables():
    demo = subprocess.run(
        ["make", "-n", "run", "PORT=8601"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--server.port 8601" in demo.stdout
    ui = subprocess.run(
        ["make", "-n", "run-ui", "UI_PORT=8602"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--server.port 8602" in ui.stdout
    assert "--server.port 8501" not in ui.stdout


def test_demo_story_is_seven_screens_and_evidence_is_labeled():
    source = _source("demo_app.py")
    for label in (
        "1 · Landing",
        "2 · Who's at risk",
        "3 · Why this customer",
        "4 · What we do",
        "5 · Grow",
        "6 · Model evidence",
        "7 · Projections",
        "Model evidence (synthetic data)",
    ):
        assert label in source
    evidence = _function("demo_app.py", "evidence_page")
    assert "synthetic" in evidence.lower()
    assert "projections(" not in evidence
    assert "overview(" not in evidence
    landing = _function("demo_app.py", "landing_page")
    assert "get_console" not in landing


def test_strategy_chart_does_not_zoom_and_keeps_labels():
    import importlib.util
    import sys

    app_dir = str(ROOT / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    spec = importlib.util.spec_from_file_location("demo_app_under_test", ROOT / "app" / "demo_app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_app_under_test"] = module
    spec.loader.exec_module(module)
    compared = pd.read_csv(ROOT / "demo_data" / "comparison.csv")
    figure = module.strategy_figure(compared.loc[~compared["strategy"].astype(str).str.match(r"^\s*\d+[a-z]\.")])
    assert figure.layout.xaxis.fixedrange is True
    assert figure.layout.yaxis.fixedrange is True
    assert figure.layout.margin.l >= 140
    labels = list(figure.data[0].y)
    assert "3+ support calls" in labels
    assert all(len(str(label)) <= 24 for label in labels)
    assert "$-80K" in list(figure.layout.xaxis.ticktext)
    low, high = figure.layout.xaxis.range
    assert low > -200_000
    assert high < 120_000


def test_messages_are_at_the_top_and_the_banner_is_gone():
    demo = _source("demo_app.py")
    assert "def banner" not in demo
    assert "banner()" not in demo
    assert "Text messages" in demo
    assert "Send texts via ntfy" in demo
    assert "tm-dubhacks26-lf3reo19tv" in demo
    panel = _function("console_app.py", "text_we_would_send")
    assert "Text message we'd send" in panel
    assert "No message sent, here's why" in panel
    for name in ("action_page", "upgrades_page"):
        page = _function("console_app.py", name)
        assert "text_we_would_send" in page


def test_saved_opener_keeps_the_do_nothing_trap():
    offers = pd.read_csv(ROOT / "demo_data" / "offers.csv")
    row = offers.loc[offers["account_id"] == "ACC-PERSONA-24"].iloc[0]
    action = str(row.get("action_code") or row.get("action")).lower()
    assert "nothing" in action
