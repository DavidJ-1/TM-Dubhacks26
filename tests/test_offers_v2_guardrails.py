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
