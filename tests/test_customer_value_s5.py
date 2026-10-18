"""Golden tests from strategy/rubric/customer_value.md section 5 (tm-strategy's 12 engine rules + the R12 expected
answers for the 30 in-scope personas: next-best-moment, timekeeper, household). ALL NUMBERS SYNTHETIC.

Checks the engine's outputs in harness/out/offers.csv (+ line_tradein.csv for timekeepers, features.csv for account
facts). Run harness/offers.py first. Cases the current rules do not meet yet are xfail(strict=False) with a reason,
so the open work is visible; an XPASS means a rule landed and the xfail mark can be removed.
"""
from __future__ import annotations

import re
import os
from pathlib import Path

import pandas as pd
import pytest

OUT = Path(os.environ.get("TM_OUT_DIR", Path(__file__).resolve().parents[1] / "harness" / "out"))
UPSELLS = {"step_up", "family_upgrade", "device_upgrade", "home_internet_bundle"}
WAITS = {"wait_until_payoff", "wait_until_promo"}


@pytest.fixture(scope="module")
def out():
    if not (OUT / "offers.csv").exists():
        pytest.skip("run harness/offers.py first")
    o = pd.read_csv(OUT / "offers.csv").set_index("account_id")
    lt = pd.read_csv(OUT / "line_tradein.csv", keep_default_na=False) if (OUT / "line_tradein.csv").exists() else None
    f = pd.read_csv(OUT / "features.csv").set_index("account_id") if (OUT / "features.csv").exists() else None
    return o, lt, f


def _row(o, pid):
    return o.loc[f"ACC-PERSONA-{pid:02d}"]


def _lines(lt, pid):
    assert lt is not None, "no line_tradein.csv"
    return lt[lt.account_id == f"ACC-PERSONA-{pid:02d}"]


def _skus(r):
    return str(r.get("promo_skus", "")) if pd.notna(r.get("promo_skus")) else ""


# ---- R12 persona expectations: pid -> (expected answer from the rubric, check(o, lt) -> None or raises) ----------
def code_in(*codes):
    def chk(o, lt, pid):
        c = _row(o, pid)["action_code"]
        assert c in codes, f"action {c}, expected one of {codes}"
    return chk


def bill_shock_with_callback(o, lt, pid):
    r = _row(o, pid)
    assert r["action_code"] == "bill_shock_price_lock", r["action_code"]
    assert bool(r["also_fix_first"]) or re.search(r"(?i)call|callback", str(r["action_detail"]) + str(r["message_en"])), \
        "bill-shock relief without a callback for the open billing tickets"


def saver_or_review_saving(o, lt, pid):
    r = _row(o, pid)
    assert r["action_code"] in {"variant_switch", "right_size", "check_in"} and "SAVER" in _skus(r).upper(), \
        f"{r['action_code']} / {_skus(r)}: no Essentials Saver saving surfaced"


def step_up_to_more(o, lt, pid):
    r = _row(o, pid)
    assert r["action_code"] == "step_up" and "PLAN-MORE" in _skus(r), f"{r['action_code']} / {_skus(r)}"


def step_up_with_tradeoff(o, lt, pid):
    step_up_to_more(o, lt, pid)
    msg = str(_row(o, pid)["message_en"])
    assert re.search(r"(?i)\bor stay\b|slow|trade-?off|instead|keep your plan", msg), \
        "step-up text does not show the cheaper option / trade-off"


def no_upsell(o, lt, pid):
    c = _row(o, pid)["action_code"]
    assert c not in UPSELLS, f"upsell {c}"
    assert not re.search(r"(?i)school|graduat", str(_row(o, pid)["message_en"]))


def variant(o, lt, pid):
    assert _row(o, pid)["action_code"] == "variant_switch"


def wait_date(o, lt, pid):
    assert _row(o, pid)["action_code"] == "do_nothing"
    ls = _lines(lt, pid)
    assert len(ls) and ls["decision"].isin(WAITS).all() and (ls["wait_until"] != "").all(), \
        f"line decisions {sorted(set(ls['decision']))}"


def wait_together_feb_2027(o, lt, pid):
    assert _row(o, pid)["action_code"] in {"do_nothing", "device_upgrade", "family_upgrade"}
    ls = _lines(lt, pid)
    assert len(ls) == 2 and ls["decision"].isin(WAITS).all(), f"line decisions {sorted(set(ls['decision']))}"
    assert set(ls["wait_until"]) == {"2027-02-01"}, f"wait_until {sorted(set(ls['wait_until']))}"


def keep_no_rush(o, lt, pid):
    assert _row(o, pid)["action_code"] in {"do_nothing", "device_upgrade"}
    ls = _lines(lt, pid)
    assert len(ls) and ls["decision"].isin({"keep", "upgrade_now"}).all(), f"{sorted(set(ls['decision']))}"
    assert "delta_cents" in ls and "verdict_reason" in ls and ls["verdict_reason"].str.contains(r"\$").all(), \
        "no dollar comparison"


DO_NOTHING = code_in("do_nothing")
FIX_FIRST = code_in("fix_first", "care_credit_fix_first")
EXPECT = {
    2: ("do nothing", DO_NOTHING), 7: ("do nothing", DO_NOTHING), 10: ("do nothing", DO_NOTHING),
    24: ("do nothing", DO_NOTHING), 26: ("do nothing", DO_NOTHING), 35: ("do nothing", DO_NOTHING),
    4: ("fix-first (+ credit OK)", FIX_FIRST), 23: ("fix-first", FIX_FIRST), 27: ("fix-first", FIX_FIRST),
    21: ("check-in", code_in("check_in")),
    22: ("bill-shock relief + callback", bill_shock_with_callback),
    5: ("right-size", code_in("right_size")), 37: ("right-size (Essentials 4-Line, -$100/mo)", code_in("right_size")),
    8: ("Essentials Saver or plan-review saving", saver_or_review_saving),
    38: ("variant", variant), 39: ("variant", variant), 40: ("variant", variant),
    9: ("step-up to More", step_up_to_more), 19: ("step-up to More", step_up_to_more),
    25: ("step-up to More", step_up_to_more),
    6: ("step-up with the trade-off shown", step_up_with_tradeoff),
    28: ("no upsell", no_upsell),
    29: ("wait-until date", wait_date), 31: ("wait-until date", wait_date), 33: ("wait-until date", wait_date),
    34: ("wait until 2027-02, together", wait_together_feb_2027),
    3: ("keep / no rush with $ comparison", keep_no_rush), 30: ("keep / no rush with $ comparison", keep_no_rush),
    32: ("keep / no rush with $ comparison", keep_no_rush), 36: ("keep / no rush with $ comparison", keep_no_rush),
}
assert len(EXPECT) == 30

# Not met by the current rules. Batch 7 fixed 06, 08, 37, R1, R2, R3, R5/R6; R7 stays xfail.
XFAIL: dict[int, str] = {}   # 06, 08, 37 fixed in tm-offers batch 7 (marks removed)


@pytest.mark.parametrize("pid", [pytest.param(p, marks=pytest.mark.xfail(reason=XFAIL[p], strict=False))
                                 if p in XFAIL else p for p in sorted(EXPECT)], ids=lambda p: f"persona_{p:02d}")
def test_r12_persona(pid, out):
    o, lt, _ = out
    EXPECT[pid][1](o, lt, pid)


# ---- population-level rule checks (R1-R11) ------------------------------------------------------------------------
def test_r1_upsell_needs_a_usage_reason(out):
    o, _, f = out
    up = o[o.action_code.isin({"step_up", "family_upgrade"})]
    need = up["um_near_plan_limit"].astype(bool) | up["um_over_plan_cap"].astype(bool)
    if f is not None and "hotspot_gb_3m_avg" in f:
        need |= f["hotspot_gb_3m_avg"].reindex(up.index).fillna(0) > 0
    bad = up.index[~need].tolist()
    assert not bad, f"{len(bad)} upsells without a usage need, e.g. {bad[:5]}"
    assert not up["message_en"].str.contains(r"(?i)bill (?:went|has gone) up|grew \d+%").any()


def test_r2_no_step_up_to_beyond(out):
    o, _, _ = out
    bad = o[(o.action_code == "step_up") & o.promo_skus.fillna("").str.contains("BEYOND")]
    assert bad.empty, f"{len(bad)} More->Beyond step-ups (needs hotspot peak > 42 GB; none in the sandbox)"


def test_r3_no_forced_bundles(out):
    o, _, _ = out
    fu = o[o.action_code == "family_upgrade"]
    bundled = fu[fu.promo_skus.fillna("").str.contains("TRADEIN-ANY") & fu.promo_skus.fillna("").str.contains("PLAN-")
                 & ~(fu["um_near_plan_limit"].astype(bool) | fu["um_over_plan_cap"].astype(bool))]
    assert bundled.empty, f"{len(bundled)} family upgrades require a plan move without a need"


def test_r4_savings_ladder_saver_surfaced(out):
    o, _, _ = out
    assert o.promo_skus.fillna("").str.contains("ESSENTIALS-SAVER").any()


def test_r5_r6_port_out_floor(out):
    o, _, f = out
    if f is None:
        pytest.skip("no features.csv")
    po = f.index[f["port_out_inquiry"] == 1].intersection(o.index)
    shrug = o.loc[po][o.loc[po, "action_code"] == "do_nothing"].index.tolist()
    assert not shrug, f"{len(shrug)} port-out inquirers get do nothing, e.g. {shrug[:5]}"


@pytest.mark.xfail(reason="R7: no ticket_follow_up action yet", strict=False)
def test_r7_open_ticket_follow_up_exists(out):
    o, _, _ = out
    assert (o.action_code == "ticket_follow_up").any()


def test_r8_no_graduation_upsell_or_school_text(out):
    o, _, _ = out
    assert not o.message_en.fillna("").str.contains(r"(?i)\bschool|graduat").any()
    assert not o.message_es.fillna("").str.contains(r"(?i)escuela|gradua").any()
    assert _row(o, 28)["action_code"] not in UPSELLS


def test_r9_single_timekeeper_verdict(out):
    _, lt, _ = out
    assert lt is not None
    assert set(lt["decision"]) <= {"keep", "upgrade_now"} | WAITS
    assert ((lt["wait_until"] != "") == lt["decision"].isin(WAITS)).all()
    if "wait_verdict" in lt:
        assert (lt["wait_verdict"] == lt["decision"].map(lambda d: "wait" if d in WAITS else d)).all()


def test_r10_do_nothing_reason_is_true(out):
    o, _, f = out
    if f is None:
        pytest.skip("no features.csv")
    dn = o[(o.action_code == "do_nothing") & o.reason.fillna("").str.contains(r"(?i)happy and engaged")]
    ff = f.reindex(dn.index)
    bad = dn.index[(ff["unresolved_90d"].fillna(0) > 0) | (ff["port_out_inquiry"].fillna(0) == 1)
                   | (ff["n_lines_over_cap_3m"].fillna(0) > 0)].tolist()
    assert not bad, f"{len(bad)} false 'happy and engaged' reasons, e.g. {bad[:5]}"


def test_r11_guarantee_only_on_more_and_beyond(out):
    o, _, f = out
    if f is None:
        pytest.skip("no features.csv")
    g = o[o.message_en.fillna("").str.contains(r"(?i)guarantee")]
    fam = f["plan_family"].reindex(g.index)
    # the plan named in the text can be the target plan (variant/step-up), so allow More/Beyond targets too
    tgt = g.promo_skus.fillna("").str.contains("PLAN-MORE|PLAN-BEYOND")
    bad = g.index[~(fam.isin({"experience_more", "experience_beyond"}) | tgt)].tolist()
    assert not bad, f"{len(bad)} guarantee mentions outside More/Beyond, e.g. {bad[:5]}"
