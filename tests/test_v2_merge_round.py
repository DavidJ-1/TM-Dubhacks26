"""v2 merge round: kept value, port-out switch, forced fix-first, limited-time receipt, one decision. SYNTHETIC."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import offers as eng  # noqa: E402
import one_decision as od  # noqa: E402
import guardrail_join as gj  # noqa: E402

C = eng.CONFIG
OUT = Path(os.environ.get("TM_OUT_DIR", ROOT / "harness" / "out"))


def test_defaults():
    assert abs(C["KEPT_VALUE_MONTHS"] - 19.338) < 1e-9 and C["VALUE_HORIZON_MONTHS"] == 24
    assert C["PORT_OUT_CONTACT"] == "off" and C["PORT_OUT_SIGNAL_ORIGIN"] == "self_initiated"
    assert C["FIX_FIRST_FORCED_OPEN_TICKET"] is True


def test_port_out_modes(monkeypatch):
    for m, ok in (("off", False), ("self_initiated_only", True), ("all", True)):
        monkeypatch.setitem(C, "PORT_OUT_CONTACT", m)
        assert eng.port_out_allowed() is ok
    monkeypatch.setitem(C, "PORT_OUT_CONTACT", "self_initiated_only")
    monkeypatch.setitem(C, "PORT_OUT_SIGNAL_ORIGIN", "carrier_port_request")
    assert eng.port_out_allowed() is False          # FCC 2008: never on another carrier's port request
    monkeypatch.setitem(C, "PORT_OUT_CONTACT", "bogus")
    with pytest.raises(AssertionError):
        eng.port_out_allowed()


def _res(**ev):
    base = {a: {"eligible": False, "ev": 0.0} for a in eng.ACTIONS}
    for a, v in ev.items():
        base[a] = {"eligible": True, "ev": v}
    return base


def test_open_ticket_forces_fix_first():
    r = _res(perk_reminder=3.0, fix_first=-4.0, care_credit_fix_first=-6.0)
    assert eng.pick(r)[0] == "perk_reminder"
    a, ev, _, _ = eng.pick(r, open_ticket=True)
    assert a == "fix_first" and ev == -4.0 and eng.PICK_OVERRIDE[0] == "open_ticket"
    assert eng.pick(_res(care_credit_fix_first=5.0, fix_first=2.0), open_ticket=True)[0] == "care_credit_fix_first"


def test_receipt_limited_time(monkeypatch):
    monkeypatch.setattr(eng, "PLAN_STATUS", {"TMO-STUB-PLAN-ESSENTIALS-4LINE": "limited_time", "X": "current"})
    r = _res()
    r["variant_switch"] = {"eligible": True, "ev": 1.0, "save": 20.0, "skus": "TMO-STUB-PLAN-ESSENTIALS-4LINE"}
    it = eng.receipt_item(r)
    assert it["receipt_limited_time"] and "Limited-time plan" in it["receipt_reason"] and it["receipt_plan_end_date"] == ""
    r["variant_switch"]["skus"] = "X"
    assert not eng.receipt_item(r)["receipt_limited_time"]


def test_one_decision_toy(monkeypatch):
    o = pd.DataFrame({"account_id": ["A", "B", "C", "D", "E"],
                      "action_code": ["perk_reminder", "fix_first", "do_nothing", "do_nothing", "check_in"],
                      "expected_value": [2.0, 3.0, 0.0, 0.0, 1.0], "p_churn_90d": [.1] * 5,
                      "customer_value_usd": [1000.0] * 5, "pick_override": [""] * 5,
                      "already_leaving_save_attempt": [""] * 5})
    cands = pd.DataFrame({"account_id": ["A", "A", "B", "E"],
                          "action_code": ["perk_reminder", "care_credit", "fix_first", "check_in"],
                          "eligible": ["True"] * 4, "expected_value": [2.0, 1.5, 3.0, 1.0],
                          "save_rate": [.01, .02, .03, .01], "offer_cost": [.5, 25, 15, 2], "annoyance": [0, 1, 1, 1]})
    g = pd.DataFrame({"account_id": ["A", "B", "C", "D", "E"], "contact_ok": [False] * 5,
                      "block_reason": ["bill_change_no_fix"] * 2 + ["x"] * 3,
                      "blocking_bill_change": [True, True, False, False, False]})
    monkeypatch.setattr(od, "receipt_sets", lambda: {"strict": {"C"}, "lose_x": set(), "source": []})
    mom = pd.DataFrame({"account_id": ["E"], "decision": ["wait_until"], "wait_months": [1]})
    r = od.decide(o, cands, mom, g).set_index("account_id")
    assert r.loc["A", "final_action"] == "care_credit" and r.loc["A", "bill_rule_note"] == "swapped_to_offsetting_credit"
    assert r.loc["B", "final_action"] == "fix_first"          # fix-only callbacks pass the bill rule
    assert list(r.decision) == ["text_now", "text_now", "receipt_only", "silent", "wait_until 2026-11-01"]
    assert "tmm_contact_ok" in r.columns and "tmm_block_reason" in r.columns   # join point


@pytest.fixture(scope="module")
def offers():
    if not (OUT / "offers.csv").exists():
        pytest.skip("run harness/offers.py first")
    o = pd.read_csv(OUT / "offers.csv")
    if "in_headline" not in o:
        pytest.skip("offers.csv predates this round")
    return o


def test_port_out_never_in_headline(offers):
    f = pd.read_csv(OUT / "features.csv", usecols=["account_id", "port_out_inquiry"])
    po = offers.merge(f, on="account_id").query("port_out_inquiry == 1")
    assert not po.in_headline.astype(bool).any()
    if not eng.port_out_allowed():
        assert (po.action_code == "do_nothing").all() and (po.already_leaving_save_attempt.fillna("") == "").all()


def test_limited_time_receipts_are_4_line(offers):
    lim = offers[offers.receipt_limited_time.astype(bool)]
    assert lim.receipt_skus.str.contains("ESSENTIALS-4LINE").all()
    assert lim.receipt_reason.str.contains("Limited-time plan").all()


def test_decision_column_if_present(offers):
    if "decision" not in offers:
        pytest.skip("one_decision.py not run on this output")
    k = offers.decision.str.split(" ").str[0]
    assert set(k) <= {"text_now", "wait_until", "receipt_only", "silent"}
    assert (offers.loc[k == "silent", "final_action"] == "do_nothing").all()
