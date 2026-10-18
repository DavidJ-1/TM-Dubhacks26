"""Persona golden tests for Model B (tm-offers): one test per sandbox persona (42 customer personas).

Each persona's expected DIRECTION comes from its sandbox `personas.scenario` + `primary_theme`, the prompt-fit
audit (strategy/research/prompt_fit_audit.md) and tm-strategy's golden list (handoff/tm-offers-proposals.txt).
Cart-whisperer / matchmaker personas are out of our scope: the test is only "no unprompted discount / credit".
Timekeeper personas also check out/line_tradein.csv (now-vs-wait). Reads harness/out/ (run harness/offers.py
first). ALL NUMBERS SYNTHETIC.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

OUT = Path(__file__).resolve().parents[1] / "harness" / "out"
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
    5: ("household on premium plan barely used: right-size", {"right_size"}, None),
    6: ("household SMB, heavy line over cap: step-up", {"step_up"}, None),
    7: ("timekeeper, upgraded 3 months ago: wait", {"do_nothing"}, ("line", {"wait_until_payoff"})),
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
    32: ("timekeeper, 2-yr paid-off flagship: upgrade-now math", {"do_nothing", "device_upgrade"}, ("line", {"upgrade_now"})),
    33: ("timekeeper, foldable with payments left: wait", {"do_nothing"}, ("line", {"wait_until_payoff"})),
    34: ("timekeeper, two phones due together", {"do_nothing", "device_upgrade", "family_upgrade"}, ("line", {"upgrade_now"})),
    35: ("timekeeper, year-old budget phone paid off: keep", {"do_nothing"}, ("line", {"keep"})),
    36: ("timekeeper, 5-yr phone, light user: nothing to wait for", {"do_nothing", "device_upgrade"}, ("line", {"upgrade_now", "keep"})),
    37: ("household family of 4 on unlimited, light use: cheaper fit", {"right_size", "variant_switch"}, None),
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
    r = offers.set_index("account_id").loc[acc]
    code = r["action_code"]
    if code not in allowed:
        return False, f"{code} not in {sorted(allowed)}"
    if extra:
        kind, arg = extra
        if kind == "sku" and arg not in str(r.get("promo_skus", "")):
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


@pytest.fixture(scope="module")
def outputs():
    if not (OUT / "offers.csv").exists():
        pytest.skip("run harness/offers.py first")
    lt = pd.read_csv(OUT / "line_tradein.csv") if (OUT / "line_tradein.csv").exists() else None
    return pd.read_csv(OUT / "offers.csv"), lt


@pytest.mark.parametrize("pid", sorted(EXPECT), ids=lambda p: f"persona_{p:02d}")
def test_persona_direction(pid, outputs):
    ok, msg = check(pid, *outputs)
    assert ok, f"persona {pid:02d} ({EXPECT[pid][0]}): {msg}"
