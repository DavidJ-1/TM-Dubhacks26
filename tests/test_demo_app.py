"""The judging demo keeps live screens on the console and badges the saved run."""

import ast
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


def test_saved_opener_keeps_the_do_nothing_trap():
    offers = pd.read_csv(ROOT / "demo_data" / "offers.csv")
    row = offers.loc[offers["account_id"] == "ACC-PERSONA-24"].iloc[0]
    action = str(row.get("action_code") or row.get("action")).lower()
    assert "nothing" in action
