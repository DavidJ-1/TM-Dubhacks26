"""Moment Replay (v2): dated moments, wait/act/silent decisions, live events, cap + budget optimizer. SYNTHETIC."""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import moment_replay as mr  # noqa: E402

AS_OF = date(2026, 10, 1)


def test_month_label_and_survival():
    assert mr.month_label(AS_OF, 2) == "Dec 2026" and mr.month_label(AS_OF, 4) == "Feb 2027"
    assert mr.survival(0.0, 3) == 1.0
    h = mr.monthly_hazard(0.27)
    assert abs((1 - h) ** 3 - 0.73) < 1e-9          # 90-day p -> constant monthly hazard (ASSUMPTION)
    assert mr.survival(0.27, 2) < 1


def _lines():
    return pd.DataFrame([
        {"line_id": "L1", "account_id": "A", "device_sku": "X", "device_purchase_date": "2025-12-15",
         "financing_months_remaining": 2, "monthly_installment_cents": 3000, "tradein_eligible": 1, "device_age_m": 10},
        {"line_id": "L2", "account_id": "A", "device_sku": None, "device_purchase_date": None,
         "financing_months_remaining": 0, "monthly_installment_cents": 0, "tradein_eligible": 0, "device_age_m": float("nan")},
    ])


def _promos():
    return pd.DataFrame({"min_tenure_months": [6.0, 36.0, None], "min_device_age_months": [None, None, 36.0]})


def test_moments_are_dated_from_own_fields():
    row = pd.Series({"tenure_months": 34})
    ev = mr.moments(row, _lines(), _promos(), 6)
    assert any(e["kind"] == "payoff" and e["field"] == "financing_months_remaining=2" for e in ev[2])
    assert any(e["kind"] == "device_age" and "reaches 12" in e["field"] for e in ev[2])   # 10 + 2 months
    assert any(e["kind"] == "tenure" and e["field"] == "tenure_months=34 (reaches 36)" for e in ev[2])


def test_row_as_of_moves_only_dated_fields():
    row = pd.Series({"tenure_months": 34, "max_financing_months_left": 2, "any_paid_off_device": False,
                     "n_upgrade_ready_lines": 0, "n_old_upgrade_lines": 0, "oldest_device_age_m": 10,
                     "contract_or_financing_months_remaining": 2, "bill_increase_pct": 0.3})
    r = mr.row_as_of(row, _lines(), 2)
    assert r["tenure_months"] == 36 and r["max_financing_months_left"] == 0 and r["any_paid_off_device"]
    assert r["n_upgrade_ready_lines"] == 1 and r["oldest_device_age_m"] == 12
    assert r["bill_increase_pct"] == 0.3   # held constant


def _opts():
    # account A: $25-credit option (EV 30) or a $0 alternative (EV 20); B: credit option EV 28; C: forced, EV -2
    return pd.DataFrame([
        {"account_id": "A", "week": 0, "action": "care_credit_fix_first", "ev": 30.0, "credit_usd": 25.0, "forced": False},
        {"account_id": "A", "week": 0, "action": "fix_first", "ev": 20.0, "credit_usd": 0.0, "forced": False},
        {"account_id": "B", "week": 0, "action": "care_credit", "ev": 28.0, "credit_usd": 25.0, "forced": False},
        {"account_id": "C", "week": 0, "action": "check_in", "ev": -2.0, "credit_usd": 0.0, "forced": True},
    ])


def test_solver_equals_greedy_on_contact_cap():
    o = _opts()
    for k in (1, 2):
        c = mr.schedule_compare(o, max_contacts=k)
        assert c["milp_ev"] == c["greedy_ev"], c
        assert c["max_per_account_milp"] == 1


def test_solver_beats_greedy_on_dollar_budget():
    c = mr.schedule_compare(_opts(), weekly_credit_budget=25.0)
    # greedy: A's credit option (30) then B doesn't fit -> 30 - 2; MILP: A fix_first (20) + B credit (28) - 2
    assert c["milp_ev"] == 46.0 and c["greedy_ev"] == 28.0


def test_forced_contact_always_scheduled():
    o = _opts()
    for x in (mr.solve_milp(o, max_contacts=1), mr.greedy(o, max_contacts=1)):
        assert x[3]


# ---- integration on the real engine (needs engine inputs in TM_OUT_DIR) ------------------------------------------
@pytest.fixture(scope="module")
def ctx():
    out = Path(os.environ.get("TM_OUT_DIR", ROOT / "harness" / "out"))
    if not (out / "churn_scores.csv").exists():
        pytest.skip("needs engine inputs in TM_OUT_DIR")
    return mr.load_context()


def _dec(ctx, pid):
    aid = f"ACC-PERSONA-{pid:02d}"
    return mr.decide(ctx.df.loc[aid], ctx.lines[ctx.lines.account_id == aid], ctx.promos, ctx.plans, ctx.as_of)


def test_personas_decisions_have_reasons(ctx):
    d4, d24 = _dec(ctx, 4), _dec(ctx, 24)
    assert d4["decision"] == "act_now" and d4["reason"].startswith("Act now")
    assert d24["decision"] == "stay_silent" and d24["reason"].startswith("Stay silent")


def test_wait_rows_carry_dated_field(ctx):
    dec = mr.replay(ctx, accounts=list(ctx.df.index[:400]))
    w = dec[dec.decision == "wait_until"]
    assert (w.dated_field != "").all() and w.reason.str.startswith("Wait until").all()
    assert set(dec.decision) <= {"act_now", "wait_until", "stay_silent"}


def test_apply_event_real_and_simulated(ctx):
    aid = "ACC-PERSONA-24"
    row, ln = ctx.df.loc[aid], ctx.lines[ctx.lines.account_id == aid]
    d = mr.apply_event(row, {"type": "unresolved_support", "category": "network"}, ln, ctx.promos, ctx.plans, ctx.as_of)
    assert d["event_source"] == "real sandbox field" and d["decision"] in {"act_now", "stay_silent", "wait_until"}
    s = mr.apply_event(row, {"type": "outage"}, ln, ctx.promos, ctx.plans, ctx.as_of)
    assert s["event_source"] == "simulated"
    with pytest.raises(ValueError):
        mr.apply_event(row, {"type": "made_up"}, ln, ctx.promos, ctx.plans, ctx.as_of)
