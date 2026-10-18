"""Checks on the precomputed live-events strip (data/live_events/live_events.csv, built by scripts/live_events.py).
Fast: reads the CSV only; the rescoring itself asserts book parity and step-0 parity when the script runs."""
from pathlib import Path
import re

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / "data/live_events/live_events.csv"
pytestmark = pytest.mark.skipif(not F.exists(), reason="live_events.csv not built")


def _load():
    return pd.read_csv(F).fillna("")


def test_one_customer_cumulative_steps():
    e = _load()
    assert e.account_id.nunique() == 1
    assert list(e.step) == list(range(len(e))) and 4 <= len(e) - 1 <= 5


def test_starts_where_the_book_says_and_flips_to_fix_first():
    e = _load()
    d = pd.read_csv(ROOT / "data/decisions/decisions.csv").set_index("account_id")
    acc = e.account_id[0]
    assert d.loc[acc, "decision"] == "silent" and e.pick[0] == "silent"
    assert d.loc[acc, "decision_reason"] == e.why[0]
    s0 = pd.read_csv(ROOT / "demo_data/churn_scores.csv").set_index("account_id").p_churn_90d[acc]
    assert abs(float(e.risk[0]) - s0) < 1e-4
    assert e.pick.iloc[-1] == "message" and e.pick_code.iloc[-1] in ("fix_first", "care_credit_fix_first")
    first_flip = int((e.pick != "silent").idxmax())
    assert first_flip >= 3


def test_on_screen_text_is_short_and_clean():
    e = _load()
    bad = re.compile(r"(?i)synthetic|simulated|account record|sandbox|_")
    for c in ("event_label", "event_line", "why", "reason_changed", "pick_label"):
        for s in e[c].astype(str):
            assert not bad.search(s), (c, s)
    for s in e.why:
        assert len(s.split()) <= 15, s
