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


def test_event_labels_fit_on_one_line():
    e = _load()
    labels = [s for s in e.event_label.astype(str) if s]
    assert labels[-1] == "Asked to move their number"
    for s in labels:
        assert "\n" not in s and len(s) <= 27, s


def test_on_screen_text_is_short_and_clean():
    e = _load()
    bad = re.compile(r"(?i)synthetic|simulated|account record|sandbox|_")
    for c in ("event_label", "event_line", "why", "reason_changed", "pick_label"):
        for s in e[c].astype(str):
            assert not bad.search(s), (c, s)
    for s in e.why:
        assert len(s.split()) <= 15, s


def test_other_customers_are_told_the_rail_switches():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "scroll_app.py")).run(timeout=90)
    assert not at.exception
    labels = [b.label for b in at.button]
    assert "Next event → switches to customer #02363" in labels
    assert "Next event →" not in labels
    text = " ".join(m.value for m in at.markdown)
    assert "Live events demo follows customer #02363" in text
    at = next(b for b in at.button if b.label.startswith("Next event → switches")).click().run(timeout=90)
    assert not at.exception
    assert at.session_state["acc"] == "ACC-02363"
    assert any("Now showing #02363 for live events" in t.value for t in at.toast)
    labels = [b.label for b in at.button]
    assert "Next event →" in labels
    assert not any(x.startswith("Next event → switches") for x in labels)
