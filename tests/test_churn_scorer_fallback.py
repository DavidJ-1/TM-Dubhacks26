"""Fresh-clone fallback: the churn scorer reads demo_data/ when harness/out has no inputs (synthetic data)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))


def test_scorer_falls_back_to_demo_data(tmp_path, monkeypatch):
    import churn_scorer as cs
    if not (cs.DEMO / "features.csv").exists():
        pytest.skip("demo_data/features.csv not present")
    monkeypatch.setattr(cs, "OUT", tmp_path / "empty_out")
    monkeypatch.setattr(cs, "_STATE", {})
    assert cs._input_dir() == cs.DEMO
    st = cs._load()
    assert st["model"] is not None and len(st["feats"]) > 0


def test_scorer_prefers_harness_out(tmp_path, monkeypatch):
    import churn_scorer as cs
    for f in ("features.csv", "labels.csv"):
        (tmp_path / f).write_text("account_id\n")
    monkeypatch.setattr(cs, "OUT", tmp_path)
    assert cs._input_dir() == tmp_path
