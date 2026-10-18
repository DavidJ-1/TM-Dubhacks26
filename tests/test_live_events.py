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


def _open(step: int):
    """Scroll page on #02363 at one live tick, with the decision step of the walk-through open."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "scroll_app.py"))
    at.session_state["acc"] = "ACC-02363"
    at.session_state["customer_pick"] = "ACC-02363"
    at.session_state["seg"] = "ACC-02363"
    at.session_state["orbit_deal_quick"] = "ACC-02363"
    at.session_state["tick_ACC-02363"] = step
    at.session_state["orbit_step"] = 3
    at.session_state["orbit_last_acc"] = "ACC-02363"
    at = at.run(timeout=120)
    assert not at.exception
    return at


@pytest.mark.parametrize("step", range(5))
def test_live_tick_matches_across_the_page(step):
    import html
    import sys
    sys.path.insert(0, str(ROOT / "app"))
    import orbit_data as D

    facts = D.live_facts("ACC-02363", step)
    at = _open(step)
    text = html.unescape(" ".join(m.value for m in at.markdown))
    line = f"This step: {facts['line']}"
    # Walk-through, contact log, and deal example each carry the same line. The book row does too after tick 0.
    assert text.count(line) >= 3, text.count(line)
    assert f"o-tk-risk'>{facts['risk_txt'][:-1]}<small>%</small>" in text
    if facts["message"]:
        assert "Reach out in the app" in text
        assert text.count(facts["message"]) >= 3
        assert at.session_state["_phone_preview"] == facts["message"]
        assert "Picked:" in text and facts["action"] in text
    else:
        assert "No message sent, here's why" in text
        assert "Picked:" in text and "do nothing" in text.lower()
        assert at.session_state.get("_phone_preview", "") == ""
    for ev in facts["events"]:
        assert ev in text
    for ev in facts["later"]:
        assert ev not in text
    if facts["label"]:
        assert facts["label"] in text
    assert "o-hero-num'>184" in text
    assert "3,938" in text
    if step > 0:
        assert "This live what-if does not change them." in text
    else:
        assert "After event" not in text


def test_next_event_and_reset_follow_the_same_step():
    import html

    at = _open(0)
    at = next(b for b in at.button if b.label == "Next event →").click().run(timeout=120)
    assert not at.exception
    text = html.unescape(" ".join(m.value for m in at.markdown))
    assert "After event 1: Logged into the app" in text
    assert "Opened the app to check their usage." in text
    assert "This live what-if does not change them." in text
    assert "o-hero-num'>184" in text
    at = next(b for b in at.button if b.label == "Reset").click().run(timeout=120)
    assert not at.exception
    text = html.unescape(" ".join(m.value for m in at.markdown))
    assert "After event 1" not in text
    assert "o-hero-num'>184" in text
    assert at.session_state["tick_ACC-02363"] == 0


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
