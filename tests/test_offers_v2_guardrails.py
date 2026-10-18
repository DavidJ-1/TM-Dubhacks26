"""v2 (tm-offers #3): honest upsell acceptance, upsell risk guardrail, right-size backfire. ALL NUMBERS SYNTHETIC.

Function checks run without outputs; population checks read TM_OUT_DIR (or harness/out) after harness/offers.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import offers as eng  # noqa: E402

OUT = Path(os.environ.get("TM_OUT_DIR", ROOT / "harness" / "out"))
UPSELLS = {"step_up", "family_upgrade", "device_upgrade", "home_internet_bundle"}


# ---- config / functions ----------------------------------------------------------------------------------------
def test_upsell_acceptance_at_or_below_cited_ceiling():
    # AT&T 3.0-4.7%/quarter, Verizon 2.6% (2Q26): overall upgrade rates incl. organic = ceiling
    for a in ("step_up", "device_upgrade", "family_upgrade"):
        assert eng.CONFIG["P_ACCEPT"][a] <= 0.047, a


def test_guardrail_flag_default_on():
    assert eng.CONFIG["UPSELL_RISK_GUARDRAIL"] is True


def test_guard_reason_plain_language(monkeypatch):
    row = pd.Series({"top_churn_decile": True, "support_90d": 4})
    why = eng.upsell_risk_guard_reason(row)
    assert why.startswith("upsell guardrail:") and "highest-risk 10%" in why and "4 times in 90 days" in why
    assert eng.upsell_risk_guard_reason(pd.Series({"top_churn_decile": False, "support_90d": 2})) == ""
    assert "support" in eng.upsell_risk_guard_reason(pd.Series({"top_churn_decile": False, "support_90d": 3}))
    monkeypatch.setitem(eng.CONFIG, "UPSELL_RISK_GUARDRAIL", False)
    assert eng.upsell_risk_guard_reason(row) == ""


def test_backfire_relative_factor_from_6_to_10(monkeypatch):
    assert abs(eng.right_size_backfire_rel() - (0.10 / 0.06 - 1)) < 1e-9
    monkeypatch.setitem(eng.CONFIG, "RIGHT_SIZE_BACKFIRE", {**eng.CONFIG["RIGHT_SIZE_BACKFIRE"], "enabled": False})
    assert eng.right_size_backfire_rel() == 0.0


def test_usage_unstable_reason():
    assert "swings" in eng.usage_unstable_reason(pd.Series({"usage_cv": 0.40, "usage_trend_ratio": 1.0}))
    assert "falling" in eng.usage_unstable_reason(pd.Series({"usage_cv": 0.10, "usage_trend_ratio": 0.6}))
    assert eng.usage_unstable_reason(pd.Series({"usage_cv": 0.10, "usage_trend_ratio": 1.0})) == ""
    assert eng.usage_unstable_reason(pd.Series({"usage_cv": float("nan"), "usage_trend_ratio": float("nan")})) == ""


def test_forced_rules_untouched():
    C = eng.CONFIG
    assert C["SAME_COVERAGE_RULE"] and C["PORT_OUT_ALWAYS_CONTACT"] and C["BILL_SHOCK_RELIEF_OVERRIDE"]


# ---- population checks on the engine's outputs -----------------------------------------------------------------
@pytest.fixture(scope="module")
def run():
    if not (OUT / "offers.csv").exists():
        pytest.skip("run harness/offers.py first")
    o = pd.read_csv(OUT / "offers.csv")
    cn = next((OUT / n for n in ("offer_candidates.csv", "offer_candidates.csv.gz") if (OUT / n).exists()), None)
    c = pd.read_csv(cn) if cn else None
    f = pd.read_csv(OUT / "features.csv") if (OUT / "features.csv").exists() else None
    return o, c, f


def _guarded(o, f):
    k = int(round(eng.CONFIG["UPSELL_GUARD_TOP_RISK_SHARE"] * len(o)))
    top = set(o.sort_values(["p_churn_90d", "account_id"], ascending=[False, True]).account_id.head(k))
    sup = set(f.loc[f.support_90d.fillna(0) >= eng.CONFIG["UPSELL_GUARD_MIN_SUPPORT_90D"], "account_id"]) \
        if f is not None else set()
    return top | sup


def test_no_upsell_chosen_for_guarded(run):
    o, _, f = run
    g = _guarded(o, f)
    bad = o[o.account_id.isin(g) & o.action_code.isin(UPSELLS)]
    assert bad.empty, f"{len(bad)} upsells to top-decile / 3+ support accounts, e.g. {bad.account_id.head().tolist()}"


def test_no_upsell_even_eligible_for_guarded(run):
    o, c, f = run
    if c is None:
        pytest.skip("no offer_candidates")
    g = _guarded(o, f)
    up = c[c.account_id.isin(g) & c.action_code.isin(UPSELLS)]
    assert not up.eligible.astype(str).eq("True").any()
    assert up.blocked_or_ineligible_reason.fillna("").str.contains("upsell guardrail").any()


def test_right_size_net_save_rate_includes_backfire(run):
    _, c, _ = run
    if c is None or eng.right_size_backfire_rel() == 0:
        pytest.skip("no candidates / backfire off")
    rs = c[(c.action_code == "right_size") & (c.eligible.astype(str) == "True")]
    assert len(rs) and (rs.save_rate < 0).all()


def test_right_size_excludes_volatile_or_declining(run):
    _, c, _ = run
    if c is None:
        pytest.skip("no offer_candidates")
    blk = c[(c.action_code == "right_size") & c.blocked_or_ineligible_reason.fillna("").str.contains("backfire guardrail")]
    assert (blk.eligible.astype(str) == "False").all()


# ---- v2: field save rate, profit gate, receipt-only plan moves, perk reminder -----------------------------------
def test_field_save_rate_scales_base_table_preserving_ratios():
    C = eng.CONFIG
    k = C["FIELD_SAVE_RATE"] / C["SAVE_RATE_ANCHOR"]
    for a, d in C["SAVE_RATE_BASE"].items():
        if a in C.get("SAVE_RATE_ABSOLUTE", {}):
            continue
        for t, v in d.items():
            assert abs(C["SAVE_RATE"][a][t] - v * k) < 1e-6, (a, t)
    assert C["SAVE_RATE"]["perk_reminder"] == {"on_target": 0.02, "off_target": 0.01}
    assert C["PERK_REMINDER_COST"] == 0.50


def test_apply_field_save_rate_roundtrip():
    old = eng.CONFIG["FIELD_SAVE_RATE"]
    try:
        eng.apply_field_save_rate(0.22)
        assert abs(eng.CONFIG["SAVE_RATE"]["fix_first"]["on_target"] - 0.35 * 0.22 / 0.45) < 1e-6
    finally:
        eng.apply_field_save_rate(old)


def test_no_nonforced_contact_with_nonpositive_ev(run):
    o, _, _ = run
    c = o[o.action_code != "do_nothing"]
    bad = c[(c.expected_value <= 0) & c.pick_override.isna()]
    assert bad.empty, f"{len(bad)} non-forced contacts with EV <= 0"


def test_plan_moves_receipt_only(run):
    o, _, _ = run
    if not eng.CONFIG["PLAN_MOVES_RECEIPT_ONLY"] or "receipt_action" not in o:
        pytest.skip("receipt-only off / old outputs")
    assert not o.action_code.isin(["variant_switch", "right_size"]).any()
    assert set(o.receipt_action.dropna()) <= {"variant_switch", "right_size"}
    assert (o.loc[o.action_code == "do_nothing", "channel"] == "none").all()
    assert (o.loc[o.action_code != "do_nothing", "channel"] == "sms").all()
    assert (o.loc[o.action_code == "do_nothing", "message_en"].fillna("") == "").all()
