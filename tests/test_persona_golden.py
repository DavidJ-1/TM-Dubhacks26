"""Persona golden tests for Model B (tm-offers): one test per sandbox persona (42 customer personas).

Each persona's expected DIRECTION comes from its sandbox `personas.scenario` + `primary_theme`, the prompt-fit
audit (strategy/research/prompt_fit_audit.md) and tm-strategy's golden list (handoff/tm-offers-proposals.txt).
Cart-whisperer / matchmaker personas are out of our scope: the test is only "no unprompted discount / credit".
Timekeeper personas also check out/line_tradein.csv (now-vs-wait). Reads harness/out/ (run harness/offers.py
first). ALL NUMBERS SYNTHETIC.
"""
from __future__ import annotations

import os
from pathlib import Path

import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import offers as _eng  # noqa: E402  (CONFIG only)

# v2: with the Ascarza et al. 2016 plan-fit backfire ON (default), an unprompted right-size never beats silence
# (its net save rate is negative), so the right-size personas (05, 37) deliberately become do-nothing with the
# "plan_fit_held" reason. With RIGHT_SIZE_BACKFIRE off they must still be right-size.
BACKFIRE_ON = _eng.right_size_backfire_rel() > 0
RS_OR_HELD = {"right_size", "do_nothing"} if BACKFIRE_ON else {"right_size"}
# v2 spec: plan moves are receipt-only (no SMS); a persona expecting a plan move passes when the move is on the
# receipt (receipt_action / receipt_skus) and the text action is not a plan move.
RECEIPT = bool(_eng.CONFIG.get("PLAN_MOVES_RECEIPT_ONLY"))
PLAN_MOVES = {"variant_switch", "right_size"}
# v2: at the field save rate (FIELD_SAVE_RATE 0.10 < base anchor) a $15 fix-first callback / $25 relief no longer
# pays for personas 22 and 27 (open ticket); fix-first is not a forced rule in the engine, so they go silent.
# Deliberate, flagged for David. With the base table (FIELD_SAVE_RATE == anchor) they must act.
FIELD_LOW = _eng.CONFIG["FIELD_SAVE_RATE"] < _eng.CONFIG["SAVE_RATE_ANCHOR"]
FIELD_SENSITIVE = {22, 27}
# v2 (merge round): three more deliberate switches, each with its own allowance below.
#   PORT_OUT_CONTACT=off (default, pending David): persona 21 (port-out inquiry) gets no outreach -> do_nothing.
#   FIX_FIRST_FORCED_OPEN_TICKET (Grok Bot's call): an open ticket forces fix-first -> persona 22 gets fix_first.
#   KEPT_VALUE_MONTHS 19.338 (~$1,478 survival-discounted): persona 04's $25 credit no longer adds enough on top of
#   the fix-first callback, so fix_first alone may win.
PO_OFF = not _eng.port_out_allowed()
FF_FORCED = bool(_eng.CONFIG.get("FIX_FIRST_FORCED_OPEN_TICKET"))
VALUE_DISC = _eng.CONFIG.get("KEPT_VALUE_MONTHS", 24) < _eng.CONFIG["VALUE_HORIZON_MONTHS"]
V2_EXTRA = {21: {"do_nothing"} if PO_OFF else set(), 22: {"fix_first"} if FF_FORCED else set(),
            4: {"fix_first"} if VALUE_DISC else set()}
OUT = Path(os.environ.get("TM_OUT_DIR", ROOT / "harness" / "out"))   # scratch runs: TM_OUT_DIR
DEMO = ROOT / "demo_data"   # tracked copies; used when harness/out has not been generated (fresh clone)
CREDITS = {"care_credit", "loyalty_credit", "keep_your_phone", "care_credit_fix_first", "bill_shock_price_lock"}
UPSELLS = {"step_up", "family_upgrade", "device_upgrade", "home_internet_bundle"}
ALL = {"do_nothing", "care_credit", "loyalty_credit", "keep_your_phone", "variant_switch", "right_size", "step_up",
       "family_upgrade", "device_upgrade", "fix_first", "care_credit_fix_first", "bill_shock_price_lock",
       "check_in", "perk_reminder", "home_internet_bundle"}
NO_DISCOUNT = ALL - CREDITS
QUIET = {"do_nothing", "check_in", "variant_switch", "right_size"}

# persona -> (direction, allowed action codes, extra check or None)
#   extra: ("line", decisions)  = every line's line_tradein decision in that set
#          ("sku", sku)          = promo_skus contains sku
#          ("no_text", regex)    = message_en does not match
EXPECT = {
    1: ("matchmaker, budget student: no unprompted discount or upsell", QUIET, None),
    2: ("household, 5 lines on unlimited: plan fit or leave alone, no credit", QUIET, None),
    3: ("timekeeper, paid-off 3+ yr phone: upgrade-now math, no push", {"do_nothing", "device_upgrade"}, ("line", {"upgrade_now"})),
    4: ("NBM bill jump + calls: fix + credit", {"care_credit_fix_first"}, None),
    5: ("household on premium plan barely used: right-size (v2: held, backfire)", RS_OR_HELD, None),
    6: ("household SMB, heavy line over cap: step-up", {"step_up"}, None),
    7: ("timekeeper, upgraded 3 months ago: keep (corrected wait math)", {"do_nothing"}, ("line", {"keep"})),
    8: ("household retired light users: cheaper fit or leave alone", QUIET, None),
    9: ("matchmaker power user on capped plan: step-up", {"step_up"}, None),
    10: ("NBM loyal bundled family: do nothing", {"do_nothing"}, None),
    11: ("cart: no unprompted discount", NO_DISCOUNT, None),
    12: ("cart: no unprompted discount", NO_DISCOUNT, None),
    13: ("cart: no unprompted discount", NO_DISCOUNT, None),
    14: ("cart: no unprompted discount", NO_DISCOUNT, None),
    15: ("cart: no unprompted discount", NO_DISCOUNT, None),
    16: ("cart: no unprompted discount", NO_DISCOUNT, None),
    17: ("cart: no unprompted discount", NO_DISCOUNT, None),
    18: ("cart: no unprompted discount", NO_DISCOUNT, None),
    19: ("matchmaker, video outgrew basic plan: step-up", {"step_up"}, None),
    20: ("matchmaker, wants watch + home internet: bundle / step-up / leave alone",
         {"home_internet_bundle", "step_up", "do_nothing"}, None),
    21: ("NBM quiet long-timer, port-out inquiry: check-in", {"check_in"}, None),
    22: ("NBM promo-ended bill shock: relief, no upsell", {"bill_shock_price_lock", "care_credit"}, None),
    23: ("NBM coverage complaints: fix first, no discount", {"fix_first"}, None),
    24: ("NBM happy frequent caller: do nothing", {"do_nothing"}, None),
    25: ("NBM outgrowing plan: step-up", {"step_up"}, None),
    26: ("NBM loyal family casually comparing: restraint / light touch", {"do_nothing", "check_in"}, None),
    27: ("NBM locked in, unhappy: fix, not a discount", {"fix_first"}, None),
    28: ("NBM student: do nothing (graduation is an inference; enrichment off), never school in text",
         {"do_nothing"}, ("no_text", r"(?i)school|graduat")),
    29: ("timekeeper, 4 payments left: wait", {"do_nothing"}, ("line", {"wait_until_payoff"})),
    30: ("timekeeper, 4-yr phone losing value: upgrade-now math", {"do_nothing", "device_upgrade"}, ("line", {"upgrade_now"})),
    31: ("timekeeper, year-old flagship, a year of payments: wait", {"do_nothing"}, ("line", {"wait_until_payoff"})),
    32: ("timekeeper, 2-yr paid-off flagship: keep (corrected wait math)", {"do_nothing", "device_upgrade"}, ("line", {"keep"})),
    33: ("timekeeper, foldable with payments left: wait", {"do_nothing"}, ("line", {"wait_until_payoff"})),
    34: ("timekeeper, two phones due together: wait for the promo", {"do_nothing", "device_upgrade", "family_upgrade"},
         ("line", {"wait_until_promo"})),
    35: ("timekeeper, year-old budget phone paid off: keep", {"do_nothing"}, ("line", {"keep"})),
    36: ("timekeeper, 5-yr phone, light user: nothing to wait for", {"do_nothing", "device_upgrade"}, ("line", {"upgrade_now", "keep"})),
    37: ("household family of 4 on unlimited, light use: cheaper fit (v2: held, backfire)",
         RS_OR_HELD | {"variant_switch"}, None),
    38: ("household 55+ couple: variant to More 55+", {"variant_switch"}, ("sku", "TMO-STUB-PLAN-MORE-55")),
    39: ("household 5 lines on entry plan: many-line offer", {"variant_switch", "right_size"}, None),
    40: ("household partner-eligible: variant to Beyond Partner", {"variant_switch"}, ("sku", "TMO-STUB-PLAN-BEYOND-PARTNER")),
    41: ("household split accounts: out of scope, no upsell / credit", QUIET, None),
    42: ("household split accounts: out of scope, no upsell / credit", QUIET, None),
}


def check(pid: int, offers: pd.DataFrame, lt: pd.DataFrame | None) -> tuple[bool, str]:
    """Pure check, usable on any offers.csv (before/after comparisons)."""
    acc = f"ACC-PERSONA-{pid:02d}"
    direction, allowed, extra = EXPECT[pid]
    allowed = set(allowed) | V2_EXTRA.get(pid, set())
    r = offers.set_index("account_id").loc[acc]
    code = r["action_code"]
    via_receipt = bool(RECEIPT and code not in PLAN_MOVES and str(r.get("receipt_action", "")) in allowed
                       and str(r.get("receipt_action", "")) in PLAN_MOVES)
    if code not in allowed and not via_receipt:
        if FIELD_LOW and pid in FIELD_SENSITIVE and code == "do_nothing":
            return True, "do_nothing (field save rate; flagged)"
        return False, f"{code} not in {sorted(allowed)}"
    if extra:
        kind, arg = extra
        skus = str(r.get("receipt_skus", "")) if via_receipt else str(r.get("promo_skus", ""))
        if kind == "sku" and arg not in skus:
            return False, f"promo_skus {r.get('promo_skus')} lacks {arg}"
        if kind == "no_text":
            import re
            if re.search(arg, str(r.get("message_en", "")) or ""):
                return False, "message mentions an inferred life detail"
        if kind == "line":
            if lt is None:
                return False, "no line_tradein.csv"
            dec = set(lt.loc[lt.account_id == acc, "decision"])
            if not dec or not dec <= arg:
                return False, f"line decisions {sorted(dec)} not in {sorted(arg)}"
    return True, code


def _src() -> Path:
    if (OUT / "offers.csv").exists():
        return OUT
    if (DEMO / "offers.csv").exists():
        return DEMO
    pytest.skip("run harness/offers.py first (no harness/out or demo_data offers.csv)")


def _cands(base: Path) -> pd.DataFrame | None:
    for n in ("offer_candidates.csv", "offer_candidates.csv.gz"):
        if (base / n).exists():
            return pd.read_csv(base / n)
    return None


@pytest.fixture(scope="module")
def outputs():
    base = _src()
    lt = pd.read_csv(base / "line_tradein.csv") if (base / "line_tradein.csv").exists() else None
    return pd.read_csv(base / "offers.csv"), lt


@pytest.mark.parametrize("pid", sorted(EXPECT), ids=lambda p: f"persona_{p:02d}")
def test_persona_direction(pid, outputs):
    ok, msg = check(pid, *outputs)
    assert ok, f"persona {pid:02d} ({EXPECT[pid][0]}): {msg}"


# ---- batch 7: deterministic pins (exact action + skus) for personas whose pick must not drift ---------------------
PINS = {
    38: ("variant_switch", "TMO-STUB-PLAN-MORE-55"),   # only $3.10 above do nothing: pin it
    28: ("do_nothing", ""), 10: ("do_nothing", ""),
    6: ("step_up", "TMO-STUB-PLAN-MORE"), 19: ("step_up", "TMO-STUB-PLAN-MORE"),
    21: ("check_in", None), 4: ("care_credit_fix_first", "PROMO-STUB-CARE-CREDIT"),
    37: ("right_size", "TMO-STUB-PLAN-ESSENTIALS-4LINE"),   # v2: do_nothing when held for backfire (see below)
    24: ("do_nothing", ""),
}


@pytest.mark.parametrize("pid", sorted(PINS), ids=lambda p: f"pin_{p:02d}")
def test_persona_pin(pid, outputs):
    o = outputs[0].set_index("account_id").loc[f"ACC-PERSONA-{pid:02d}"]
    code, sku = PINS[pid]
    if o["action_code"] in V2_EXTRA.get(pid, set()):
        code, sku = o["action_code"], None   # deliberate v2 switch (see V2_EXTRA)
    if pid == 37 and BACKFIRE_ON and o.get("do_nothing_reason") == "plan_fit_held":
        code, sku = "do_nothing", ""   # v2: right-size held (Ascarza 2016 backfire); frozen demo_data still pins right_size
    if RECEIPT and code in PLAN_MOVES and "receipt_action" in o and o["action_code"] not in PLAN_MOVES:
        assert o["receipt_action"] == code, f"persona {pid:02d}: receipt {o['receipt_action']} != {code}"
        if sku:
            assert sku in str(o["receipt_skus"]).split(";"), f"persona {pid:02d}: receipt_skus {o['receipt_skus']!r}"
        return
    assert o["action_code"] == code, f"persona {pid:02d}: {o['action_code']} != {code}"
    if sku is not None:
        got = o["promo_skus"] if isinstance(o["promo_skus"], str) else ""
        assert (sku in got.split(";")) if sku else got == "", f"persona {pid:02d}: promo_skus {got!r}"


def test_persona_38_saves_40_a_month():
    c = _cands(_src())
    if c is None or "customer_monthly_delta" not in c:
        pytest.skip("no offer_candidates with customer_monthly_delta")
    r = c[(c.account_id == "ACC-PERSONA-38") & (c.action_code == "variant_switch")].iloc[0]
    o = pd.read_csv(_src() / "offers.csv").set_index("account_id").loc["ACC-PERSONA-38"]
    if RECEIPT and "receipt_action" in o:   # v2: receipt-only plan move, still computed in the candidates
        assert o["receipt_action"] == "variant_switch" and abs(o["receipt_monthly_saving"] - 40) < 1e-6
        assert bool(r["eligible"]) and abs(r["customer_monthly_delta"] + 40) < 1e-6
        return
    assert bool(r["is_chosen"]) and abs(r["customer_monthly_delta"] + 40) < 1e-6


def test_text_fixes_post_freeze(outputs):
    """check-in fits one SMS; right-size es keeps an opt-out; '5 lines qualify for 4 Line' states the real rule."""
    o = outputs[0]
    ci = o[o.action_code == "check_in"]
    assert (ci.message_en.str.len() <= 160).all() and (ci.message_es.str.len() <= 160).all()
    rs = o[o.action_code == "right_size"]
    assert rs.message_es.str.contains("o ignore este mensaje").all()
    four = o[(o.action_code == "variant_switch") & o.message_en.fillna("").str.contains("4 Line Offer")]
    odd = four[~four.message_en.str.contains(r"your 4 lines qualify")]
    assert odd.message_en.str.contains(r"qualify for our Essentials 4 Line Offer 2\.0 \(4 or more lines\)").all()
    assert odd.message_es.str.contains(r"\(4 o más líneas\)").all()
    p39 = o.set_index("account_id").loc["ACC-PERSONA-39"]
    if p39["action_code"] == "variant_switch":
        assert "(4 or more lines)" in p39["message_en"] and "(4 o más líneas)" in p39["message_es"]


def test_persona_24_reason_from_real_fields(outputs):
    o = outputs[0].set_index("account_id").loc["ACC-PERSONA-24"]
    assert o["why_this_offer"].startswith("Happy customer:"), o["why_this_offer"]
    assert "resolved" in o["why_this_offer"] and "no port-out inquiry" in o["why_this_offer"]
    assert "happy and engaged" not in str(o["why_this_offer"])


def test_wait_personas_reason_matches_verdict(outputs):
    o = outputs[0].set_index("account_id")
    for pid in (29, 31, 33):
        w = o.loc[f"ACC-PERSONA-{pid:02d}", "why_this_offer"]
        assert "wait" in w and "happy" not in w.lower(), f"persona {pid}: {w}"


def test_open_ticket_wording(outputs):
    o = outputs[0]
    if "do_nothing_reason" not in o:
        pytest.skip("older offers.csv")
    t = o[o.do_nothing_reason == "open_ticket"]
    if FF_FORCED:   # v2: an open ticket forces fix-first, so silence with an open ticket only if fix-first is ineligible
        assert (o.loc[o.pick_override.fillna("") == "open_ticket", "action_code"]
                .isin(["fix_first", "care_credit_fix_first"])).all()
        return
    assert len(t) and (t.why_this_offer == "Open ticket with support; no marketing until it's closed.").all()


# ---- batch 7: live-toggle API (offer_api.choose_offer) on persona 21 -----------------------------------------------
@pytest.fixture(scope="module")
def api():
    import sys
    sys.path.insert(0, str(ROOT / "harness"))
    try:
        import offer_api
        offer_api.prepared_row("ACC-PERSONA-21")
    except Exception as e:  # no sandbox DB on this machine
        pytest.skip(f"offer_api unavailable: {e}")
    return offer_api


def test_api_persona_21_port_out_off_still_check_in(api):
    row = api.prepared_row("ACC-PERSONA-21")
    row["port_out_inquiry"] = 0
    got = api.choose_offer(row, p_churn=0.035)["action_code"]
    # v2: at FIELD_SAVE_RATE 0.10 a no-offer check-in at 3.5% risk no longer pays once port-out is off
    assert got in ({"check_in", "do_nothing"} if FIELD_LOW else {"check_in"}), got


def test_api_persona_21_port_out_and_shopping_off_do_nothing(api):
    row = api.prepared_row("ACC-PERSONA-21")
    row["port_out_inquiry"] = 0
    row["competitor_research_score"] = 0.0
    assert api.choose_offer(row, p_churn=0.017)["action_code"] == "do_nothing"


def test_api_matches_offers_csv(api, outputs):
    o = outputs[0].set_index("account_id")
    if RECEIPT and "receipt_action" not in o:
        pytest.skip("offers.csv predates v2 (frozen demo_data copy); regenerate with harness/offers.py")
    for pid in (38, 21, 24, 4):
        acc = f"ACC-PERSONA-{pid:02d}"
        got = api.choose_offer(api.prepared_row(acc))["action_code"]
        assert got == o.loc[acc, "action_code"], f"{acc}: api {got} vs offers.csv {o.loc[acc, 'action_code']}"


def test_api_persona_21_toggled_reason_low_risk(api):
    row = api.prepared_row("ACC-PERSONA-21")
    row["port_out_inquiry"] = 0
    row["competitor_research_score"] = 0.0
    out = api.choose_offer(row, p_churn=0.017)
    assert out["why_this_offer"].startswith("Risk is low") and "nothing needs fixing" in out["why_this_offer"], \
        out["why_this_offer"]


def test_v2_right_size_personas_held_for_backfire(outputs):
    """v2: plan-fit personas 05 / 08 / 37 are held with the honest backfire reason, and the saving is still computed."""
    if not BACKFIRE_ON:
        pytest.skip("RIGHT_SIZE_BACKFIRE off")
    o = outputs[0].set_index("account_id")
    if "do_nothing_reason" not in o or not (o["do_nothing_reason"] == "plan_fit_held").any():
        pytest.skip("outputs predate v2 (e.g. the frozen demo_data copy); regenerate with harness/offers.py")
    c = _cands(_src())
    for pid in (5, 8, 37):
        r = o.loc[f"ACC-PERSONA-{pid:02d}"]
        assert r["action_code"] == "do_nothing" and r["do_nothing_reason"] == "plan_fit_held", (pid, r["action_code"])
        assert "6% to 10%" in r["why_this_offer"]
        if c is not None:
            rs = c[(c.account_id == f"ACC-PERSONA-{pid:02d}") & (c.action_code == "right_size")].iloc[0]
            assert bool(rs["eligible"]) and rs["expected_value"] < 0
