"""tm-offers lane (Model B): deterministic expected-value offer chooser with "do nothing" allowed to win.

    EV(action) = p_churn_90d x save_rate x customer_value  (+ p_accept x upsell_gain, upsell actions only)
                 - expected_offer_cost - annoyance

"do nothing" has EV = 0 and wins whenever every other eligible action is below 0.

Inputs (all in harness/out/ unless overridden):
  churn_scores.csv  from tm-churn (Model A). If missing, mock_churn_scores.csv is generated from the
                    sandbox with the same columns and used instead (switch: CHURN_SOURCE below).
  features.csv      from tm-data (account-level). When present its columns override the sandbox-derived
                    facts for detectors and eligibility; per-line facts it lacks (per-line peak usage and
                    hotspot, paid-off/upgrade-ready lines, network-unresolved count) come from the sandbox.
  sandbox.db        judge sandbox, opened READ-ONLY (promotions, plans, devices, lines, usage, billing ...).
Output:
  offers.csv            chosen action per account: account_id, action, expected_value, reason, runner-up,
                        upgrade-moment flags, per-action EVs.
  offer_candidates.csv  one row per account x action (incl. do nothing and ineligible ones), is_chosen.

ALL CUSTOMERS AND ALL NUMBERS ARE SYNTHETIC / SIMULATED. Nothing here is a real T-Mobile offer.
Run:  python harness/offers.py      (from the repo root or from harness/)
"""

from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offer_detectors as det  # noqa: E402
import offer_messages as om  # noqa: E402

OUT_DIR = Path(os.environ.get("TM_OUT_DIR", HERE / "out"))

# =============================================================================================
# CONFIG: ALL ASSUMPTIONS LIVE HERE. EVERY VALUE IS SYNTHETIC (a judgement call, not fitted on
# real outcomes). Promo amounts and eligibility come from the sandbox promotions table instead.
# =============================================================================================
CONFIG = {
    # --- switches
    "CHURN_SOURCE": "auto",          # "auto": real out/churn_scores.csv if present, else mock; "real"; "mock"
    "ENABLE_RIGHT_SIZE": True,       # OPEN SCOPE QUESTION: right-sizing gives revenue away. Toggle off here
                                     # (or env TM_ENABLE_RIGHT_SIZE=0).
    "STRICT_PROMO_RULES": False,     # True: keep-your-phone only per the literal sandbox rule (new line + port-in
                                     # + BYOD + Saver), which no existing customer meets. False: adapted retention
                                     # version using the same $20/mo value (see KYP_* below).

    # --- customer value (synthetic)
    "VALUE_HORIZON_MONTHS": 24,      # how many months of service margin a save is worth
    "SERVICE_MARGIN": 0.50,          # share of monthly service revenue (bill minus device installments) kept

    # --- base save rates: P(customer stays | they would have churned, we take the action). Synthetic.
    #     Each action has a rate when it addresses the customer's churn driver and a lower "off-target" rate.
    "SAVE_RATE": {
        "care_credit":      {"on_target": 0.25, "off_target": 0.05},  # billing / service pain
        "loyalty_credit":   {"on_target": 0.12, "off_target": 0.05},  # price / competitor shopping
        "keep_your_phone":  {"on_target": 0.20, "off_target": 0.05},  # price, phone paid off (free to leave)
        "right_size":       {"on_target": 0.30, "off_target": 0.10},  # overpaying / bill shock
        "step_up":          {"on_target": 0.15, "off_target": 0.03},  # plan too small / life event
        "device_upgrade":   {"on_target": 0.22, "off_target": 0.06},  # old or paid-off phone / device issues
        "variant_switch":   {"on_target": 0.30, "off_target": 0.10},  # same plan for less
        "family_upgrade":   {"on_target": 0.18, "off_target": 0.05},  # outgrowing / old phones on a family plan
        "bill_shock_price_lock": {"on_target": 0.30, "off_target": 0.08},  # promo-end bill shock on More/Beyond
        "check_in":         {"on_target": 0.12, "off_target": 0.04},  # shopping / port-out / went quiet
        "perk_reminder":    {"on_target": 0.08, "off_target": 0.03},  # streams a lot, perk unused
        "home_internet_bundle": {"on_target": 0.03, "off_target": 0.03},  # bundles are stickier
        "fix_first":        {"on_target": 0.35, "off_target": 0.04,   # network / unresolved service issue
                             "billing_only": 0.15},                   # a callback can explain a price rise,
                                                                      # not undo it
    },
    # combined "$25 care credit + fix-first callback" (plan doc demo: "the $25 care credit plus a network fix").
    # Save rate = 1 - (1 - fix_first rate) x (1 - credit increment). The credit only adds its on-target rate
    # when there is billing pain (a credit doesn't fix coverage); otherwise it adds the off-target rate.
    "COMBO_ANNOYANCE": 5.0,
    # --- bill-shock guardrail (nextbest ladder rule in the plan doc: "no upsell after bill shock")
    "UPSELL_BLOCK_DAYS_AFTER_BILL_SHOCK": 90,   # step-up / device upgrade are INELIGIBLE this many days after a
                                                # promo expired or the bill jumped (>= 15%, not a new phone)
    "BILL_SHOCK_RELIEF_OVERRIDE": True,         # OPEN DECISION (David). One switch for the override below.
                                                # Env TM_BILL_SHOCK_RELIEF_OVERRIDE=0 to turn it off.
    "BILL_SHOCK_RELIEF": {                      # POLICY OVERRIDE, not a sandbox rule: in that same window the
        "enabled": True,                        # care credit's 3-contact minimum is relaxed so bill-shocked
        "care_credit_min_contacts": 1,          # customers who did reach out can get it (tenure >= 6 still applies)
        "credit_save_boost": 0.05,              # credits directly offset the price rise: +5 pts save rate
    },
    # --- probability the customer takes the offer (only matters for upsell gain / conditional costs)
    "P_ACCEPT": {"right_size": 0.45, "variant_switch": 0.70, "step_up": 0.25, "device_upgrade": 0.15,
                 "family_upgrade": 0.20, "home_internet_bundle": 0.04},
    # --- annoyance: dollar-equivalent cost of contacting (agent time, message fatigue, sleeping-dog risk)
    "ANNOYANCE": {
        "care_credit": 3.0, "loyalty_credit": 3.0, "keep_your_phone": 3.0, "right_size": 2.0,
        "step_up": 5.0, "device_upgrade": 6.0, "fix_first": 4.0, "variant_switch": 2.0,
        "family_upgrade": 6.0, "bill_shock_price_lock": 3.0, "check_in": 2.0, "perk_reminder": 2.0,
        "home_internet_bundle": 6.0,
    },
    "UPSELL_AFTER_PAIN_PENALTY": 25.0,   # extra annoyance for upsells right after bill shock / unresolved issues
    # --- costs not in the sandbox (synthetic)
    "FIX_FIRST_CALLBACK_COST": 15.0,     # agent callback + ticket escalation, $
    "LOYALTY_CREDIT_MONTHS": 12,         # open-ended $/mo credit valued over 12 months (sandbox API uses 12 too)
    "KYP_MONTHS": 6,                     # adapted keep-your-phone credit length (real promo pays 36 months
                                         # on a NEW line; we cap the retention version at 6 months)
    "RIGHT_SIZE_REVENUE_MONTHS": 12,     # months of lost revenue counted as the cost of a right-size
    "RIGHT_SIZE_MIN_SAVINGS": 10.0,      # $/mo; smaller savings aren't worth a message
    "RIGHT_SIZE_CAP_HEADROOM": 0.70,     # target plan cap must be >= heaviest line's recent peak / 0.70
    "STEP_UP_MARGIN": 0.80,              # share of incremental plan revenue that is margin
    "DEVICE_UPGRADE_MARGIN": 80.0,       # $ margin on a device sale + new 24-month financing (synthetic)
    # --- batch 4/5 (tm-strategy proposals + prompt-fit audit). All synthetic.
    "ENRICHMENT_IN_DECISIONS": False,   # PERMANENTLY OFF (tm-strategy A/B, strategy/ab_enrichment/RESULTS.md):
                                        # simulated enrichment (job change, income, kid age band, likely_kid_flag)
                                        # never feeds eligibility, p_accept, EV or text; listed in `drivers` only,
                                        # tagged enrichment(simulated)[not used]. There is no code path that reads it.
    "AFFORDABILITY_MAX_BILL_INCREASE": 0.25,  # upsell blocked if the plan increase > 25% of the current bill
                                              # (synthetic threshold; never income)
    "AFFORDABILITY_MAX_BILL_INCREASE_OVER_CAP": 0.40,  # ... 40% when a line is already over its data cap
                                                       # (they are already throttled / paying for overage)
    "FAMILY_UPGRADE_ENDING_MONTHS": 2,
    "UPGRADE_GATE": True,               # device / family upgrade only for accounts in the top 15% of tm-bench's
                                        # NO-INCOME upgrade model (upgrade_gate.py). Env TM_UPGRADE_GATE=0 to drop.  # promo / financing ending within this many months = upgrade moment
    "MIN_CREDIT_P_CHURN": 0.05,         # guardrail: no bill/goodwill credit below 5% 90-day risk
    "CUSTOMER_BENEFIT_WEIGHT": 0.5,     # customer-first actions: $ of customer savings counted as trust value.
                                        # EV += W*savings*12*p_accept ; lost margin counted x (1-W)
    "SAME_COVERAGE_RULE": True,         # an eligible same-features cheaper variant (55+/partner/community/4-line)
                                        # beats do-nothing, upsells, check-ins and cross-sells (restraint =
                                        # no upsell, not hiding savings). Problem-solving actions still win.
    "LOCK_CUT": 0.50,                   # hazard cut while new promo credits / financing are paying out
    "CHECK_IN_COST": 2.0,               # $ (message + light agent follow-up)
    "PERK_MIN_STREAMING_HOURS": 20.0,   # streaming_hours_3m_avg that makes an unused perk relevant
    "HINT_MARGIN": 0.30,                # share of Home Internet revenue that is margin
    "QUIET_APP_SESSIONS": 3,            # app_sessions_30d at or below = went quiet
    # --- mock churn model (used only when real churn_scores.csv is missing)
    "MOCK_MEAN_MONTHLY_HAZARD": 0.0099,  # calibrate mock to 0.99%/month like tm-data's synthetic labels
}
if os.environ.get("TM_BILL_SHOCK_RELIEF_OVERRIDE") is not None:
    CONFIG["BILL_SHOCK_RELIEF_OVERRIDE"] = os.environ["TM_BILL_SHOCK_RELIEF_OVERRIDE"] not in ("0", "false", "False", "")
if os.environ.get("TM_UPGRADE_GATE") is not None:
    CONFIG["UPGRADE_GATE"] = os.environ["TM_UPGRADE_GATE"] not in ("0", "false", "False", "")
if os.environ.get("TM_ENABLE_RIGHT_SIZE") is not None:
    CONFIG["ENABLE_RIGHT_SIZE"] = os.environ["TM_ENABLE_RIGHT_SIZE"] not in ("0", "false", "False", "")

ACTIONS = ["do_nothing", "care_credit", "loyalty_credit", "keep_your_phone", "variant_switch", "right_size",
           "step_up", "family_upgrade", "device_upgrade", "fix_first", "care_credit_fix_first",
           "bill_shock_price_lock", "check_in", "perk_reminder", "home_internet_bundle"]
ACTION_LABEL = {
    "do_nothing": "do nothing", "care_credit": "$25 care credit", "loyalty_credit": "loyalty credit",
    "keep_your_phone": "keep-your-phone credit", "variant_switch": "switch to discount plan variant",
    "right_size": "right-size plan", "step_up": "step-up plan", "family_upgrade": "family upgrade",
    "device_upgrade": "device upgrade", "fix_first": "fix-first callback",
    "care_credit_fix_first": "$25 care credit + fix-first callback",
    "bill_shock_price_lock": "bill-shock relief ($25 credit, price-guarantee fact)",
    "check_in": "check-in / plan review", "perk_reminder": "perk reminder",
    "home_internet_bundle": "Home Internet bundle",
}
SEGMENT = {  # offer segment shown on the card (customer type stays in features.csv `segment`)
    "do_nothing": "leave alone", "fix_first": "fix first", "care_credit_fix_first": "fix first + goodwill",
    "care_credit": "goodwill credit", "bill_shock_price_lock": "bill-shock relief",
    "loyalty_credit": "loyalty thank-you", "keep_your_phone": "keep your phone",
    "variant_switch": "save money (same plan, discount variant)", "right_size": "save money (right-size)",
    "step_up": "better-fitting plan (step-up)", "family_upgrade": "family upgrade",
    "device_upgrade": "device upgrade", "check_in": "check-in", "perk_reminder": "perk reminder",
    "home_internet_bundle": "bundle",
}
PROMO_FOR_ACTION = {
    "care_credit": "PROMO-STUB-CARE-CREDIT", "loyalty_credit": "PROMO-STUB-LOYALTY-CREDIT",
    "keep_your_phone": "PROMO-STUB-KEEP-YOUR-PHONE",
}
UPSELLS = ("step_up", "family_upgrade", "device_upgrade", "home_internet_bundle")
CREDIT_ACTIONS = ("care_credit", "loyalty_credit", "keep_your_phone", "care_credit_fix_first",
                  "bill_shock_price_lock")
PROBLEM_ACTIONS = ("fix_first", "care_credit_fix_first", "care_credit", "bill_shock_price_lock")

# =============================================================================================
# Churn scores: real (tm-churn) or mock
# =============================================================================================
CHURN_COLS = ["account_id", "p_churn_90d", "risk_rank", "risk_reason_1", "risk_reason_2", "risk_reason_3",
              "stay_reason_1", "stay_reason_2", "stay_reason_3"]


def make_mock_churn_scores(f: pd.DataFrame) -> pd.DataFrame:
    """SYNTHETIC mock of Model A's output, built from sandbox fields. Replaced automatically by the real file.

    Uses the sandbox toy-model drivers, but counts unresolved / negative contacts rather than raw contacts
    (so a happy frequent caller is not flagged), then calibrates the intercept so the mean monthly hazard is
    0.99% (90-day p = 1 - (1 - h)^3).
    """
    terms = pd.DataFrame({
        "unresolved support contacts": 0.55 * f["unresolved_90d"],
        "unhappy support contacts": 0.30 * f["neg_contacts_90d"],
        "bill went up": 4.0 * f["bill_increase_pct"],
        "researching other carriers": 2.2 * f["competitor_research_score"],
        "asked about porting out": 1.8 * f["port_out_inquiry"],
        "asked about cancelling": 0.8 * f["cancel_inquiry_90d"],
        "plan doesn't fit usage": 0.7 * f["plan_misfit_share"].fillna(0),
        "app use dropped": 0.15 * (8 - f["app_sessions_30d"].clip(upper=8)),
    })
    stay = pd.DataFrame({
        "long tenure": 0.012 * f["tenure_months"].clip(upper=120),
        "uses the app a lot": 0.03 * (f["app_sessions_30d"] - 8).clip(lower=0),
        "bundled with Home Internet": 0.5 * f["has_home_internet"].astype(float),
        "phone financing keeps them": 0.4 * (f["max_financing_months_left"].fillna(0) >= 6),
        "happy with support": 0.6 * (f["avg_sentiment_90d"] > 0.2),
        "on AutoPay": 0.2 * f["autopay"],
    })
    score = terms.sum(axis=1) - stay.sum(axis=1)
    target = 1 - (1 - CONFIG["MOCK_MEAN_MONTHLY_HAZARD"]) ** 3
    lo, hi = -15.0, 5.0
    for _ in range(80):  # bisection on the intercept
        b0 = (lo + hi) / 2
        mean = (1 / (1 + np.exp(-(b0 + score)))).mean()
        lo, hi = (b0, hi) if mean < target else (lo, b0)
    p = 1 / (1 + np.exp(-(b0 + score)))

    def top(df, k):
        out = []
        for _, row in df.iterrows():
            r = row[row > 0.05].sort_values(ascending=False).index.tolist()[:k]
            out.append(r + [""] * (k - len(r)))
        return out

    risk, stays = top(terms, 3), top(stay, 3)
    mock = pd.DataFrame({"account_id": f["account_id"], "p_churn_90d": p.round(4)})
    mock["risk_rank"] = mock["p_churn_90d"].rank(ascending=False, method="first").astype(int)
    for i in range(3):
        mock[f"risk_reason_{i+1}"] = [r[i] for r in risk]
        mock[f"stay_reason_{i+1}"] = [s[i] for s in stays]
    return mock[CHURN_COLS]


def load_churn_scores(f: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    real = OUT_DIR / "churn_scores.csv"
    src = CONFIG["CHURN_SOURCE"]
    if src == "real" or (src == "auto" and real.exists()):
        cs = pd.read_csv(real)
        missing = [c for c in ["account_id", "p_churn_90d"] if c not in cs.columns]
        if missing:
            raise ValueError(f"{real} is missing columns {missing}")
        for c in CHURN_COLS:
            if c not in cs.columns:
                cs[c] = ""
        return cs[CHURN_COLS], f"real ({real})"
    if src != "mock" and os.environ.get("TM_ALLOW_MOCK_SCORES") != "1":
        raise FileNotFoundError(
            f"Real churn scores not found at {real}. Run tm-churn's Model A (harness/churn_model.py) first, or set "
            "TM_ALLOW_MOCK_SCORES=1 to use clearly-labelled mock scores.")
    mock = make_mock_churn_scores(f)
    mock.to_csv(OUT_DIR / "mock_churn_scores.csv", index=False)
    return mock, f"mock ({OUT_DIR / 'mock_churn_scores.csv'})"


# =============================================================================================
# Catalog helpers: right-size and step-up searches over the sandbox plans table
# =============================================================================================
def _plan_allowed(plan: pd.Series, n_lines: int, discount_group) -> bool:
    if pd.notna(plan["eligibility"]) and plan["eligibility"] != discount_group:
        return False
    if n_lines < plan["min_lines"] or (pd.notna(plan["max_lines"]) and n_lines > plan["max_lines"]):
        return False
    return True


def _fits_usage(plan: pd.Series, row: pd.Series) -> bool:
    peak = row["max_line_data_peak_gb"] if pd.notna(row["max_line_data_peak_gb"]) else 0
    if pd.notna(plan["data_cap_gb"]) and peak > CONFIG["RIGHT_SIZE_CAP_HEADROOM"] * plan["data_cap_gb"]:
        return False
    hs = row["max_line_hotspot_gb"] if pd.notna(row["max_line_hotspot_gb"]) else 0
    if hs > 0.5 and plan["hotspot_high_speed_gb"] < 1.5 * hs:
        return False
    return True


def _price(p: pd.Series, n: int) -> int:
    return det.plan_price_cents(p["line_prices"], p["extra_line_cents"], n)


def variant_option(row: pd.Series, plans: pd.DataFrame):
    """Same family + same features, cheaper: a discount variant the account qualifies for per the sandbox
    (plans.eligibility == accounts.discount_group: 55+/partner/community) or the Essentials 4 Line Offer
    (4+ lines). Never Military / First Responder (not in the sandbox). Returns (plan, $save/mo) or None."""
    cur = plans.set_index("sku").loc[row["plan_sku"]]
    if cur["variant"] != "standard":
        return None
    best = None
    for _, p in plans.iterrows():
        if p["sku"] == row["plan_sku"] or p["family"] != cur["family"] or p["variant"] in ("standard", "saver"):
            continue
        if not _plan_allowed(p, row["n_lines"], row["discount_group"]) or not _fits_usage(p, row):
            continue
        save = (row["plan_price_cents"] - _price(p, row["n_lines"])) / 100
        if save >= CONFIG["RIGHT_SIZE_MIN_SAVINGS"] and (best is None or save > best[1]):
            best = (p, save)
    return best


def right_size_option(row: pd.Series, plans: pd.DataFrame):
    """Move DOWN to a cheaper plan that still fits every line's usage (saves >= RIGHT_SIZE_MIN_SAVINGS/mo).

      - 'low_use': sandbox misfit rule (every line < 5 GB on a premium plan) -> any cheaper plan that fits;
      - 'beyond_down': Experience Beyond where every line averages < 15 GB and < 2 GB hotspot, no connected
        lines -> Experience More (same variant group). The customer gives up hotspot / perks; the text says so.
    Same-family discount variants are variant_option(), not this. Returns (plan, $save/mo, kind) or None.
    """
    cur = plans.set_index("sku").loc[row["plan_sku"]]
    low_use = bool(row["all_low_use_premium_any"])
    beyond_down = bool(cur["family"] == "experience_beyond"
                       and (row["max_line_data_gb"] if pd.notna(row["max_line_data_gb"]) else 0) < 15
                       and (row["max_line_hotspot_gb"] if pd.notna(row["max_line_hotspot_gb"]) else 0) < 2
                       and (row.get("n_connected_lines", 0) or 0) == 0
                       and not (row.get("has_streaming_addon", 0) or 0)      # uses Beyond's streaming perks
                       and not bool(row.get("has_home_internet", False)))   # bundled household: leave alone
    if not (low_use or beyond_down):
        return None
    best = None
    for _, p in plans.iterrows():
        if FAMILY_RANK[p["family"]] >= FAMILY_RANK[cur["family"]]:
            continue
        if not _plan_allowed(p, row["n_lines"], row["discount_group"]) or not _fits_usage(p, row):
            continue
        if not low_use and p["family"] != "experience_more":
            continue
        save = (row["plan_price_cents"] - _price(p, row["n_lines"])) / 100
        if save >= CONFIG["RIGHT_SIZE_MIN_SAVINGS"] and (best is None or save > best[1]):
            best = (p, save, "low_use" if low_use else "beyond_down")
    return best


FAMILY_RANK = {"essentials": 0, "experience_more": 1, "experience_beyond": 2}


def step_up_option(row: pd.Series, plans: pd.DataFrame):
    """Cheapest allowed plan one step up, when the household is outgrowing its plan or a life event hits."""
    outgrowing = bool(row["um_near_plan_limit"] or row["um_over_plan_cap"] or row["um_usage_growth"]
                      or (row["plan_family"] == "essentials" and (row["max_line_hotspot_gb"] or 0) > 0.5)
                      or (row["plan_family"] == "experience_more" and (row["max_line_hotspot_gb"] or 0) > 45))
    grad = False  # graduation is an inferred life event (student + tenure heuristic): not an upsell trigger
    if not (outgrowing or grad):
        return None
    cur_rank = FAMILY_RANK[row["plan_family"]]
    cands = []
    for _, p in plans.iterrows():
        if not _plan_allowed(p, row["n_lines"], row["discount_group"]):
            continue
        price = det.plan_price_cents(p["line_prices"], p["extra_line_cents"], row["n_lines"])
        delta = (price - row["plan_price_cents"]) / 100
        r = FAMILY_RANK[p["family"]]
        if outgrowing and r == cur_rank + 1 and delta > 0:
            cands.append((p, delta))
        elif grad and not outgrowing and r == cur_rank and p["variant"] == "standard" and delta > 0:
            cands.append((p, delta))  # Saver -> standard Essentials (more lines, no 2-line limit)
    if not cands:
        return None
    return min(cands, key=lambda c: c[1])


# =============================================================================================
# Eligibility per sandbox promotions rules (mirrors api/services/promotions.py for an existing account,
# no cart) plus action-specific preconditions.
# =============================================================================================
def promo_rule_ok(promo: pd.Series, row: pd.Series) -> tuple[bool, str]:
    why = []
    if pd.notna(promo["min_tenure_months"]) and row["tenure_months"] < promo["min_tenure_months"]:
        why.append(f"needs {int(promo['min_tenure_months'])}+ months tenure (has {row['tenure_months']})")
    if pd.notna(promo["min_support_contacts_90d"]) and row["support_90d"] < promo["min_support_contacts_90d"]:
        why.append(f"needs {int(promo['min_support_contacts_90d'])}+ support contacts in 90 days "
                   f"(has {row['support_90d']})")
    if pd.notna(promo["credit_tiers"]) and row["credit_tier"] not in str(promo["credit_tiers"]).split(","):
        why.append(f"credit tier {row['credit_tier']} not allowed")
    if pd.notna(promo["discount_groups"]) and row["discount_group"] not in str(promo["discount_groups"]).split(","):
        why.append("discount group not allowed")
    if pd.notna(promo["min_device_age_months"]) and (row["oldest_device_age_m"] or 0) < promo["min_device_age_months"]:
        why.append(f"needs a phone owned {int(promo['min_device_age_months'])}+ months")
    return (not why), "; ".join(why)


SHOP_REASON = re.compile(r"port|carrier|compet|shopping", re.I)


def drivers(row: pd.Series) -> dict:
    """Which churn drivers are present (synthetic thresholds on real sandbox fields)."""
    d = {
        "billing_pain": bool(row["um_promo_expired"] or row["bill_increase_pct"] >= 0.10 or row["billing_90d"] >= 1),
        "service_pain": bool(row["unresolved_90d"] >= 1 or row["network_90d"] >= 2 or row["neg_contacts_90d"] >= 2),
        "network_pain": bool(row["network_90d"] >= 1 and (row["network_unresolved_90d"] >= 1 or row["network_90d"] >= 2)),
        "unresolved": bool(row["unresolved_90d"] >= 1),
        "shopping": bool(row["competitor_research_score"] >= 0.6 or row["port_out_inquiry"] == 1
                         or row["cancel_inquiry_90d"] >= 1),
        "quiet": bool(row["app_sessions_30d"] <= CONFIG["QUIET_APP_SESSIONS"]),
        "device_pain": bool(row["device_90d"] >= 1 or row["um_old_device"]),
        "overpay": bool(row["um_plan_overpay"]),
        "outgrowing": bool(row["um_near_plan_limit"] or row["um_over_plan_cap"] or row["um_usage_growth"]),
        "life_event": bool(row["um_student_graduating"]),
        "free_to_leave": bool(row["max_financing_months_left"] == 0 and row["n_lines"] > 0),
        "bill_shock_recent": bool(pd.notna(row["days_since_bill_shock"])
                                  and row["days_since_bill_shock"] <= CONFIG["UPSELL_BLOCK_DAYS_AFTER_BILL_SHOCK"]),
        "fixable_unresolved": bool(row["unresolved_90d"] > 0
                                   and (row["network_90d"] > 0 or row["device_90d"] > 0)),
        "streaming": bool((row.get("streaming_hours_3m_avg", 0) or 0) >= CONFIG["PERK_MIN_STREAMING_HOURS"]
                          and not (row.get("has_streaming_addon", 0) or 0)),
        "kid_line": bool((row.get("n_kid_lines", 0) or 0) > 0),   # REAL: lines.member_role child/teen
    }
    # shopping as the TOP driver only matters for an at-risk account: port-out inquiry, or Model A's #1 reason is
    # shopping AND risk >= MIN_CREDIT_P_CHURN (Model A names "shopping" #1 even at <1% risk)
    d["top_driver_shopping"] = bool(row["port_out_inquiry"] == 1 or (
        SHOP_REASON.search(str(row.get("risk_reason_1", "") or ""))
        and row["p_churn_90d"] >= CONFIG["MIN_CREDIT_P_CHURN"]))
    return d


ON_TARGET = {  # action -> drivers it addresses
    "care_credit": ["billing_pain", "service_pain"],
    "loyalty_credit": ["shopping", "billing_pain"],
    "keep_your_phone": ["billing_pain", "shopping"],
    "variant_switch": ["overpay", "billing_pain"],
    "right_size": ["overpay", "billing_pain"],
    "step_up": ["outgrowing", "life_event"],
    "family_upgrade": ["outgrowing", "device_pain", "free_to_leave"],
    "device_upgrade": ["device_pain", "free_to_leave"],
    "fix_first": ["network_pain", "fixable_unresolved"],
    "bill_shock_price_lock": ["billing_pain"],
    "check_in": ["shopping", "quiet"],
    "perk_reminder": ["streaming"],
    "home_internet_bundle": [],
}


def lock_value(p90: float, lock_months: float, existing_months: float, monthly_margin: float,
               p_accept: float) -> float:
    """Retention value of NEW lock-in (promo credits / financing paying out). SYNTHETIC.

    Spec formula p_accept*[(1-h(1-cut))^L - (1-h)^L]*margin*24 multiplies the survival gap AT month L by 24
    full months of margin (and L=36 runs past the 24-month horizon), so it overstates. Corrected: sum the
    monthly survival gap over the value horizon, with the cut active only for months beyond the lock the
    customer already has (existing financing / promo months), i.e. no double count with current lock-in.
    h = monthly hazard from p_churn_90d."""
    if lock_months <= 0 or p_accept <= 0:
        return 0.0
    h = 1 - (1 - min(max(p90, 0.0), 0.999)) ** (1 / 3)
    hc = h * (1 - CONFIG["LOCK_CUT"])
    H = CONFIG["VALUE_HORIZON_MONTHS"]
    m = max(0.0, float(existing_months or 0))
    gap, s_new, s_base = 0.0, 1.0, 1.0
    for t in range(1, H + 1):
        s_base *= (1 - h)
        s_new *= (1 - hc) if (m < t <= lock_months) else (1 - h)
        gap += s_new - s_base
    return p_accept * gap * monthly_margin


def evaluate_account(row: pd.Series, promos: pd.DataFrame, plans: pd.DataFrame) -> dict:
    C = CONFIG
    d = drivers(row)
    p = float(row["p_churn_90d"])
    margin_mo = row["service_revenue_cents"] / 100 * C["SERVICE_MARGIN"]
    value = margin_mo * C["VALUE_HORIZON_MONTHS"]
    W = C["CUSTOMER_BENEFIT_WEIGHT"]
    plan_idx = plans.set_index("sku")
    cur_plan = plan_idx.loc[row["plan_sku"]]
    guarantee = int(cur_plan["price_guarantee_years"]) if pd.notna(cur_plan["price_guarantee_years"]) else 0
    existing_lock = row.get("contract_or_financing_months_remaining", row["max_financing_months_left"]) or 0
    res: dict[str, dict] = {"do_nothing": {"ev": 0.0, "eligible": True, "detail": "", "save_rate": 0.0,
                                           "cost": 0.0, "annoyance": 0.0, "gain": 0.0, "save_value": 0.0,
                                           "customer_benefit": 0.0, "lock_value": 0.0, "skus": "",
                                           "lock_in_months": 0}}
    relief = C["BILL_SHOCK_RELIEF"]
    shock_relief = d["bill_shock_recent"] and relief["enabled"] and C["BILL_SHOCK_RELIEF_OVERRIDE"]

    def pa(action):
        return C["P_ACCEPT"].get(action, 0.0)

    def sr(action):
        if action == "care_credit_fix_first":
            fix = sr("fix_first")
            cc = C["SAVE_RATE"]["care_credit"]
            inc = cc["on_target"] if d["billing_pain"] else cc["off_target"]
            if shock_relief:
                inc += relief["credit_save_boost"]
            return round(1 - (1 - fix) * (1 - inc), 4)
        rates = C["SAVE_RATE"][action]
        if any(d[k] for k in ON_TARGET[action]):
            r = rates["on_target"]
        elif action == "fix_first" and d["unresolved"]:
            r = rates["billing_only"]
        else:
            r = rates["off_target"]
        if action in ("care_credit", "loyalty_credit", "keep_your_phone") and shock_relief:
            r += relief["credit_save_boost"]
        return r

    def add(action, eligible, cost, gain=0.0, detail="", why_not="", benefit=0.0, lock=0.0, lock_gross=0.0,
            skus="", lock_months=0):
        f_ann = C["COMBO_ANNOYANCE"] if action == "care_credit_fix_first" else C["ANNOYANCE"][action]
        base = {"forced_save_rate": sr(action), "forced_cost": cost, "forced_annoyance": f_ann,
                "forced_gain": gain, "skus": skus, "lock_in_months": lock_months}
        if not eligible:
            res[action] = {"ev": None, "eligible": False, "detail": why_not, "save_rate": None, "cost": None,
                           "annoyance": None, "customer_benefit": None, "lock_value": None, **base}
            return
        ann = f_ann
        sv = p * sr(action) * value
        ev = sv + gain + benefit + lock - cost - ann
        res[action] = {"ev": round(ev, 2), "eligible": True, "detail": detail, "save_rate": sr(action),
                       "cost": round(cost, 2), "annoyance": round(ann, 2), "gain": round(gain, 2),
                       "save_value": round(sv, 2), "customer_benefit": round(benefit, 2),
                       "lock_value": round(lock, 2), "ev_gross_lock": round(ev - lock + lock_gross, 2), **base}

    credit_block = (f"guardrail: no bill credits below {C['MIN_CREDIT_P_CHURN']:.0%} churn risk "
                    f"(this account {p:.1%})") if p < C["MIN_CREDIT_P_CHURN"] else ""

    # ---- $25 care credit: PROMO-STUB-CARE-CREDIT (tenure >= 6, >= 3 support contacts in 90d), $25 x 1
    pr = promos.loc["PROMO-STUB-CARE-CREDIT"]
    ok, why = promo_rule_ok(pr, row)
    cc_detail = "$25 one-time goodwill credit"
    if not ok and shock_relief:
        relaxed = pr.copy()
        relaxed["min_support_contacts_90d"] = relief["care_credit_min_contacts"]
        if promo_rule_ok(relaxed, row)[0]:
            ok, cc_detail = True, ("$25 goodwill credit via bill-shock relief override "
                                   f"(sandbox rule needs {int(pr['min_support_contacts_90d'])}+ contacts)")
    care_cost = pr["value_cents"] / 100 * (pr["payout_months"] or 1)
    care_rule_ok = ok
    # bill-shock relief replaces the standalone credit on More/Beyond (it IS the credit plus the explanation)
    lock_ok = bool(d["bill_shock_recent"] and guarantee >= 5 and care_rule_ok and not credit_block)
    add("care_credit", ok and not credit_block and not lock_ok, care_cost, detail=cc_detail,
        why_not=why or credit_block or "replaced by bill-shock relief (same $25 credit plus the explanation)",
        skus="PROMO-STUB-CARE-CREDIT")
    care_ok = ok and not credit_block

    # ---- loyalty credit: PROMO-STUB-LOYALTY-CREDIT (tenure >= 36), $5/mo valued over 12 months
    pl = promos.loc["PROMO-STUB-LOYALTY-CREDIT"]
    ok, why = promo_rule_ok(pl, row)
    loy_mo = pl["value_cents"] / 100
    add("loyalty_credit", ok and not credit_block, loy_mo * C["LOYALTY_CREDIT_MONTHS"],
        detail=f"${loy_mo:.0f}/mo loyalty credit", why_not=why or credit_block, skus="PROMO-STUB-LOYALTY-CREDIT")

    # ---- keep-your-phone (adapted; real promo needs a new ported-in BYOD Saver line)
    pk = promos.loc["PROMO-STUB-KEEP-YOUR-PHONE"]
    mo = pk["value_cents"] / 100
    if C["STRICT_PROMO_RULES"]:
        add("keep_your_phone", False, 0, why_not="sandbox rule needs a new ported-in BYOD line on Essentials Saver")
    else:
        ok = bool(d["free_to_leave"] and (row["any_paid_off_device"] or row["n_byod"] > 0))
        add("keep_your_phone", ok and not credit_block, mo * C["KYP_MONTHS"],
            detail=f"${mo:.0f}/mo for {C['KYP_MONTHS']} months to keep a paid-off phone (adapted)",
            why_not=("still paying off a phone" if not ok else credit_block), skus="PROMO-STUB-KEEP-YOUR-PHONE")

    # ---- customer-first: discount variant (same features) and right-size down
    vs = variant_option(row, plans) if C["ENABLE_RIGHT_SIZE"] else None
    if vs is not None:
        plan, save = vs
        pav = pa("variant_switch")
        add("variant_switch", True, save * C["RIGHT_SIZE_REVENUE_MONTHS"] * pav * (1 - W),
            benefit=W * save * 12 * pav, detail=f"move to {plan['name']} (same features, saves ${save:.0f}/mo)",
            skus=plan["sku"])
        res["variant_switch"].update(plan_name=plan["name"], plan_sku=plan["sku"], save=save)
    else:
        add("variant_switch", False, 0, why_not="disabled by ENABLE_RIGHT_SIZE" if not C["ENABLE_RIGHT_SIZE"]
            else "no cheaper discount variant / 4-line offer they qualify for")
    rs = right_size_option(row, plans) if C["ENABLE_RIGHT_SIZE"] else None
    if rs is not None:
        plan, save, kind = rs
        par = pa("right_size")
        add("right_size", True, save * C["RIGHT_SIZE_REVENUE_MONTHS"] * par * (1 - W),
            benefit=W * save * 12 * par, detail=f"move to {plan['name']} (saves ${save:.0f}/mo; {kind})",
            skus=plan["sku"])
        res["right_size"].update(plan_name=plan["name"], plan_sku=plan["sku"], save=save, kind=kind)
    else:
        add("right_size", False, 0, why_not="disabled by ENABLE_RIGHT_SIZE" if not C["ENABLE_RIGHT_SIZE"]
            else "no cheaper plan fits their usage (or not a light user)")

    # ---- upsell guardrails
    blocks = []
    if d["bill_shock_recent"]:
        blocks.append(f"bill-shock guardrail (bill rose {int(row['days_since_bill_shock'])} days ago, "
                      f"window {C['UPSELL_BLOCK_DAYS_AFTER_BILL_SHOCK']} days)")
    if d["unresolved"]:
        blocks.append("open support issue")
    if vs is not None:
        blocks.append("a cheaper eligible version of their plan exists")
    if d["top_driver_shopping"]:
        blocks.append("top driver is shopping / port-out")
    upsell_block = "blocked: " + "; ".join(blocks) if blocks else ""

    # ---- step-up
    su = step_up_option(row, plans)
    bill = max(float(row["last_bill_cents"] or 0) / 100, 1.0)

    def afford_block(delta):
        lim = C["AFFORDABILITY_MAX_BILL_INCREASE_OVER_CAP"] if row["um_over_plan_cap"] \
            else C["AFFORDABILITY_MAX_BILL_INCREASE"]
        return (f"blocked: affordability (+${delta:.0f}/mo is {delta / bill:.0%} of the ${bill:.0f} bill, "
                f"limit {lim:.0%})") if delta / bill > lim else ""
    if su is not None and (upsell_block or afford_block(su[1])):
        add("step_up", False, 0, why_not=upsell_block or afford_block(su[1]))
    elif su is not None:
        plan, delta = su
        gain = pa("step_up") * delta * C["STEP_UP_MARGIN"] * C["VALUE_HORIZON_MONTHS"] * (1 - p)
        add("step_up", True, 0.0, gain=gain, detail=f"move to {plan['name']} (+${delta:.0f}/mo)", skus=plan["sku"])
        res["step_up"].update(plan_name=plan["name"], plan_sku=plan["sku"], delta=delta)
    else:
        add("step_up", False, 0, why_not="not outgrowing the plan and no life event")

    # ---- family upgrade: one plan up + TRADEIN-ANY per paid-off phone; real kid lines; not a discount
    anyt = promos.loc["PROMO-STUB-TRADEIN-ANY"]
    # real fields only: phones with trade-in value left after the balance (or paid off) + a real moment
    end_m = C["FAMILY_UPGRADE_ENDING_MONTHS"]
    promo_m = row.get("promo_months_remaining", 0) or 0
    fin_m = row.get("contract_or_financing_months_remaining", 0) or 0
    moment = bool(row["um_old_device"] or row["um_near_plan_limit"] or row["installment_ended_recent"]
                  or 0 < promo_m <= end_m or 0 < fin_m <= end_m)
    n_trade = int(row.get("n_tradein_value_lines", 0) or 0)
    tier_ok, tier_why = promo_rule_ok(anyt, row)
    fam_ready = bool(n_trade > 0 and moment and tier_ok)
    gate_ok = bool(row.get("in_top15", True))
    gate_why = f"upgrade gate: not in the no-income upgrade model's top 15% (pct {row.get('upgrade_pct', float('nan')):.0f})"
    fam_ok = bool(gate_ok and row.get("is_family_plan", 0) and row["n_lines"] >= 2 and d["kid_line"]
                  and row["plan_family"] in ("essentials", "experience_more") and fam_ready)
    fu_plan = None
    if fam_ok:
        nxt = FAMILY_RANK[row["plan_family"]] + 1
        opts = [(pp, (_price(pp, row["n_lines"]) - row["plan_price_cents"]) / 100) for _, pp in plans.iterrows()
                if FAMILY_RANK[pp["family"]] == nxt and _plan_allowed(pp, row["n_lines"], row["discount_group"])
                and pp["variant"] in ("standard", cur_plan["variant"])]
        opts = [o for o in opts if o[1] > 0]
        fu_plan = min(opts, key=lambda o: o[1]) if opts else None
    if fam_ok and fu_plan is not None and (upsell_block or afford_block(fu_plan[1])):
        add("family_upgrade", False, 0, why_not=upsell_block or afford_block(fu_plan[1]))
    elif fam_ok and fu_plan is not None:
        plan, delta = fu_plan
        n_dev = int(min(n_trade, anyt["max_units"] if pd.notna(anyt["max_units"]) else 4))
        credit = anyt["value_cents"] / 100
        L = int(anyt["payout_months"])
        paf = pa("family_upgrade")
        gain = paf * (delta * C["STEP_UP_MARGIN"] * C["VALUE_HORIZON_MONTHS"] * (1 - p)
                      + C["DEVICE_UPGRADE_MARGIN"] * n_dev)
        lv = lock_value(p, L, existing_lock, margin_mo, paf)
        lg = lock_value(p, L, 0, margin_mo, paf)
        add("family_upgrade", True, paf * credit * n_dev, gain=gain, lock=lv, lock_gross=lg,
            detail=f"move to {plan['name']} (+${delta:.0f}/mo) + {anyt['name']} ${credit:.0f} x {n_dev} phone(s)",
            skus=f"{plan['sku']};{anyt['sku']}", lock_months=L)
        res["family_upgrade"].update(plan_name=plan["name"], plan_sku=plan["sku"], delta=delta, credit=credit,
                                     n_dev=n_dev, payout=L)
    else:
        why = (gate_why if not gate_ok else "not a family plan" if not row.get("is_family_plan", 0) else
               "no child/teen line (lines.member_role)" if not d["kid_line"] else
               "already on the top plan family" if row["plan_family"] not in ("essentials", "experience_more") else
               f"trade-in credit tier rule: {tier_why}" if not tier_ok else
               "no trade-in phone with value left after its balance" if n_trade == 0 else
               "no upgrade moment (old phone, near data limit, payoff / promo ending)" if not fam_ready else
               "no allowed next plan")
        add("family_upgrade", False, 0, why_not=why)

    # ---- device upgrade (paid-off, trade-in eligible, 12+ months); lock-in = promo payout months
    if row["n_upgrade_ready_lines"] > 0 and not gate_ok:
        add("device_upgrade", False, 0, why_not=gate_why)
    elif row["n_upgrade_ready_lines"] > 0 and upsell_block:
        add("device_upgrade", False, 0, why_not=upsell_block)
    elif row["n_upgrade_ready_lines"] > 0:
        options = []
        old = promos.loc["PROMO-STUB-OLD-PHONE-UPGRADE"]
        if row["n_old_upgrade_lines"] > 0 and promo_rule_ok(old, row)[0]:
            options.append(old)
        if row["plan_family"] in str(anyt["plan_families"]).split(","):
            options.append(anyt)
        best = max(options, key=lambda r: r["value_cents"])
        credit = best["value_cents"] / 100
        pad = pa("device_upgrade")
        L = int(best["payout_months"]) if pd.notna(best["payout_months"]) else 0
        add("device_upgrade", True, pad * credit, gain=pad * C["DEVICE_UPGRADE_MARGIN"],
            lock=lock_value(p, L, existing_lock, margin_mo, pad), lock_gross=lock_value(p, L, 0, margin_mo, pad),
            detail=f"upgrade with {best['name']} (${credit:.0f})", skus=best["sku"], lock_months=L)
        res["device_upgrade"]["promo"] = best["sku"]
    else:
        add("device_upgrade", False, 0, why_not="no paid-off, trade-in-eligible phone owned 12+ months")

    # ---- fix-first callback
    ok = bool(d["unresolved"] or d["network_pain"])
    add("fix_first", ok, C["FIX_FIRST_CALLBACK_COST"], detail="agent callback to fix the open issue",
        why_not="no open or network issue")
    fix_ok = ok
    add("care_credit_fix_first", care_ok and fix_ok, care_cost + C["FIX_FIRST_CALLBACK_COST"],
        detail="$25 goodwill credit plus an agent callback to fix the issue",
        why_not=credit_block or "needs both the care credit and a fix-first issue", skus="PROMO-STUB-CARE-CREDIT")

    # ---- bill-shock relief: More/Beyond only; $25 care credit (+ $5/mo loyalty at 36+ months); the 5-year
    #      guarantee is stated as a FACT, never as a new lock -> lock_in 0
    with_loyalty = bool(row["tenure_months"] >= (pl["min_tenure_months"] or 36))
    cost = care_cost + (loy_mo * C["LOYALTY_CREDIT_MONTHS"] if with_loyalty else 0)
    why = ("no bill shock in the last 90 days" if not d["bill_shock_recent"] else
           "Essentials has no price guarantee: credits / right-size instead" if guarantee < 5 else
           credit_block or "care-credit rule not met")
    add("bill_shock_price_lock", lock_ok, cost,
        detail="explain the promo end + $25 credit" + (" + $5/mo loyalty" if with_loyalty else "")
               + f"; {cur_plan['name']} price guaranteed {guarantee} years (fact)",
        why_not=why, skus="PROMO-STUB-CARE-CREDIT" + (";PROMO-STUB-LOYALTY-CREDIT" if with_loyalty else "")
                          + f";{row['plan_sku']}")
    if lock_ok:
        res["bill_shock_price_lock"].update(with_loyalty=with_loyalty, guarantee=guarantee)

    # ---- check-in / plan review (no $): shopping, port-out or went quiet, nothing open
    ok = bool((d["shopping"] or d["quiet"]) and not d["unresolved"])
    add("check_in", ok, C["CHECK_IN_COST"], detail="plan review, no offer" +
        (f"; {cur_plan['name']} price guarantee stated as a fact" if guarantee >= 5 else ""),
        why_not="open support issue (fix first)" if d["unresolved"] else "no shopping / port-out / quiet signal",
        skus=row["plan_sku"] if guarantee >= 5 else "")
    # ---- perk reminder (no $, no brand names)
    ok = bool(d["streaming"] and isinstance(cur_plan["perks"], str) and "streaming-video-ads" in cur_plan["perks"]
              and p >= C["MIN_CREDIT_P_CHURN"])
    add("perk_reminder", ok, 0.0, detail="remind them their plan includes a streaming video perk",
        why_not="no unused streaming perk / risk below 5%", skus=row["plan_sku"])
    # ---- Home Internet bundle (BUNDLE-HINT $15/mo with Home Internet Basic)
    hint = promos.loc["PROMO-STUB-BUNDLE-HINT"]
    ok = bool(not row["has_home_internet"] and row["n_lines"] >= 2)
    if ok and upsell_block:
        add("home_internet_bundle", False, 0, why_not=upsell_block)
    elif ok:
        pah = pa("home_internet_bundle")
        hb, hc = 50.0, hint["value_cents"] / 100
        add("home_internet_bundle", True, pah * hc * 12, gain=pah * (hb - hc) * C["HINT_MARGIN"] * C["VALUE_HORIZON_MONTHS"],
            detail=f"Home Internet Basic ${hb:.0f}/mo with ${hc:.0f}/mo bundle credit",
            skus="TMO-STUB-ADD-HINT-BASIC;PROMO-STUB-BUNDLE-HINT")
    else:
        add("home_internet_bundle", False, 0, why_not="already has Home Internet or single line")
    return {"res": res, "drivers": d, "value": value}


def driver_list(row: pd.Series, d: dict) -> str:
    """`group:signal` list (commerce / customer / live / enrichment(simulated))."""
    out = []
    if d["bill_shock_recent"]:
        out.append("live:bill_shock_promo_expired" if row["um_promo_expired"] else "live:bill_jump")
    if d["unresolved"]:
        out.append("live:unresolved_support")
    if row["network_90d"] >= 1:
        out.append("live:network_complaints")
    if row["port_out_inquiry"] == 1:
        out.append("live:port_out_inquiry")
    if row["competitor_research_score"] >= 0.6:
        out.append("live:competitor_research")
    if d["quiet"]:
        out.append("live:app_use_dropped")
    if row["um_near_plan_limit"]:
        out.append("live:near_data_cap")
    if row["um_usage_growth"]:
        out.append("live:usage_growth")
    if row["any_paid_off_device"]:
        out.append("commerce:device_paid_off")
    if row["um_old_device"]:
        out.append("commerce:old_device")
    if (row["max_financing_months_left"] or 0) > 0:
        out.append(f"commerce:financing_{int(row['max_financing_months_left'])}m_left")
    if row["all_low_use_premium_any"]:
        out.append("commerce:premium_plan_light_use")
    if row.get("_variant_ok"):
        out.append("commerce:cheaper_variant_eligible")
    out.append(f"customer:tenure_{int(row['tenure_months'])}m")
    out.append(f"customer:lines_{int(row['n_lines'])}")
    if d.get("kid_line") and (row.get("n_kid_lines", 0) or 0) > 0:
        out.append("customer:kid_line")
    if isinstance(row["discount_group"], str) and row["discount_group"]:
        out.append(f"customer:discount_group_{row['discount_group']}")
    tag = "enrichment(simulated)[not used]"
    if row.get("recent_job_change", 0) == 1:
        out.append(f"{tag}:job_change_90d")
    if isinstance(row.get("income_band"), str) and row.get("income_band"):
        out.append(f"{tag}:income_band_{row['income_band']}")
    if isinstance(row.get("kid_age_band"), str) and row.get("kid_age_band") not in ("", "none"):
        out.append(f"{tag}:kid_age_band_{row['kid_age_band']}")
    return ";".join(out)


def _pct(row):
    pv = row["p_churn_90d"] * 100
    return f"{pv:.1f}%" if pv >= 1 else f"{pv:.2f}%"


def why_this_offer(action: str, row: pd.Series, ev: dict) -> str:
    """One customer-facing sentence (operator math goes in `reason`)."""
    d, r = ev["drivers"], ev["res"]
    if action == "do_nothing":
        if row["unresolved_90d"] > 0:
            return "Open issue being handled; no offer until it's resolved."
        if row["app_sessions_30d"] >= 10 or row["avg_sentiment_90d"] > 0.2:
            return "They're happy and engaged, so there's no need to interrupt."
        if row["max_financing_months_left"] > 0 and (row["um_payoff_soon"] or row["um_old_device"]):
            return "Their phone is still being paid off, so the honest advice is to wait; we won't push an upgrade."
        if row["p_churn_90d"] >= 0.05:
            return "Nothing we could offer right now would genuinely help, so we'll hold off and keep listening."
        return "Their plan fits how they use it and nothing is wrong, so we won't bother them."
    m = {
        "fix_first": "Something is still broken for them, so we fix it first instead of offering a discount.",
        "care_credit_fix_first": "We fix what's broken first and add a $25 goodwill credit for the trouble.",
        "care_credit": "They've had a rough stretch with us, so a one-time $25 credit says sorry.",
        "bill_shock_price_lock": "Their bill rose because a promo ended, so we explain it, add $25, and remind them their plan price is guaranteed.",
        "loyalty_credit": "They've been with us a long time, so a small monthly thank-you credit.",
        "keep_your_phone": "Their phone is paid off, so a monthly credit to keep using it.",
        "variant_switch": f"They qualify for the same plan for ${r['variant_switch'].get('save', 0):.0f}/month less, so we tell them.",
        "right_size": f"They pay for more than they use; a plan that fits saves them ${r['right_size'].get('save', 0):.0f}/month.",
        "step_up": "Their usage has outgrown the plan, so a plan that fits avoids slowdowns and surprise costs."
                   if d["outgrowing"] else "Their plan setup is about to change, so a plan that lets them add lines is timely.",
        "family_upgrade": "A better plan for the whole family plus trade-in credit on phones that are ready to go.",
        "device_upgrade": "Their phone is paid off and ready to trade in, so a real trade-in credit makes upgrading worth it.",
        "check_in": "A long-time customer has gone quiet, so a no-strings plan check-in.",
        "perk_reminder": "They stream a lot and haven't used a perk their plan already includes.",
        "home_internet_bundle": "Adding Home Internet to their phone lines comes with a monthly bundle credit.",
    }
    return m.get(action, "")


def reason_text(action: str, row: pd.Series, ev: dict, best_other: tuple | None) -> str:
    """Operator line with the math (synthetic)."""
    d, r = ev["drivers"], ev["res"]
    pct = _pct(row)
    if action == "do_nothing":
        if best_other is None:
            return f"Simulated churn risk {pct}; no eligible action applies. EV 0."
        return (f"Simulated churn risk {pct}; best eligible option ({ACTION_LABEL[best_other[0]]}) has EV "
                f"${best_other[1]:.2f} < 0, so restraint (EV 0).")
    v = r[action]
    parts = [f"save value ${v['save_value']:.2f}"]
    if v.get("gain"):
        parts.append(f"upsell ${v['gain']:.2f}")
    if v.get("customer_benefit"):
        parts.append(f"customer benefit ${v['customer_benefit']:.2f}")
    if v.get("lock_value"):
        parts.append(f"lock-in ${v['lock_value']:.2f}")
    return (f"Risk {pct}; {v['detail']}. EV = {' + '.join(parts)} - cost ${v['cost']:.2f} - annoyance "
            f"${v['annoyance']:.2f} = ${v['ev']:.2f} (synthetic).")


def candidate_reason(a: str, v: dict, chosen: str) -> str:
    if not v["eligible"]:
        return f"Not eligible: {v['detail']}."
    if a == "do_nothing":
        return "Baseline: no contact, no cost (EV 0)."
    parts = f"save value ${v['save_value']:.2f}"
    if v.get("gain"):
        parts += f" + upsell ${v['gain']:.2f}"
    if v.get("customer_benefit"):
        parts += f" + customer benefit ${v['customer_benefit']:.2f}"
    if v.get("lock_value"):
        parts += f" + lock-in ${v['lock_value']:.2f}"
    tail = "chosen" if a == chosen else ("below zero" if v["ev"] < 0 else "lower EV than the chosen action")
    return f"Eligible ({v['detail']}): {parts} - cost ${v['cost']:.2f} - annoyance ${v['annoyance']:.2f}; {tail}."


DETAILS: dict[str, dict] = {}  # account_id -> evaluate_account() output from the last run (used by uplift.py)


def pick(res: dict, key: str = "ev", exclude: tuple = ()) -> tuple[str, float, tuple | None, tuple | None]:
    """Chooser: best eligible EV > 0 else do nothing; then the same-coverage rule. Returns
    (action, ev, runner_up, best_other)."""
    scored = sorted(((a, v[key]) for a, v in res.items()
                     if v["eligible"] and a != "do_nothing" and a not in exclude),
                    key=lambda t: (-t[1], ACTIONS.index(t[0])))
    best_other = scored[0] if scored else None
    if best_other and best_other[1] > 0:
        action, evv = best_other
    else:
        action, evv = "do_nothing", 0.0
    vs = res.get("variant_switch", {})
    if (CONFIG["SAME_COVERAGE_RULE"] and vs.get("eligible") and "variant_switch" not in exclude
            and action not in PROBLEM_ACTIONS and action not in ("variant_switch", "right_size")):
        action, evv = "variant_switch", vs[key]
    rest = [s for s in scored if s[0] != action]
    runner = ("do_nothing", 0.0) if action != "do_nothing" and (not rest or rest[0][1] < 0) else \
        (rest[0] if rest else None)
    return action, evv, runner, best_other


def choose(df: pd.DataFrame, promos: pd.DataFrame, plans: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, cands = [], []
    DETAILS.clear()
    for _, row in df.iterrows():
        ev = evaluate_account(row, promos, plans)
        DETAILS[row["account_id"]] = ev
        res = ev["res"]
        action, evv, runner, best_other = pick(res)
        # balance-netting check: winner if lock-in were NOT netted against existing financing
        gross_res = {a: ({**v, "ev": v.get("ev_gross_lock", v["ev"])} if v["eligible"] else v) for a, v in res.items()}
        gross_action = pick(gross_res)[0]
        row = row.copy()
        row["_variant_ok"] = res["variant_switch"]["eligible"]
        out = {
            "account_id": row["account_id"], "action": ACTION_LABEL[action], "action_code": action,
            "expected_value": round(evv, 2), "reason": reason_text(action, row, ev, best_other),
            "segment": SEGMENT[action], "why_this_offer": why_this_offer(action, row, ev),
            "lock_in_months": int(res[action].get("lock_in_months", 0) or 0) if res[action]["eligible"] else 0,
            "drivers": driver_list(row, ev["drivers"]),
            "promo_skus": res[action].get("skus", "") if action != "do_nothing" else "",
            "action_detail": res[action]["detail"],
            "runner_up_action": ACTION_LABEL[runner[0]] if runner else "",
            "runner_up_ev": round(runner[1], 2) if runner else np.nan,
            "p_churn_90d": row["p_churn_90d"], "risk_rank": row["risk_rank"],
            "customer_value_usd": round(ev["value"], 2),
            "also_fix_first": bool(action not in ("fix_first", "care_credit_fix_first", "do_nothing")
                                   and res["fix_first"]["eligible"]),
            "bill_shock_recent": ev["drivers"]["bill_shock_recent"],
            "days_since_bill_shock": row["days_since_bill_shock"],
            "eligible_actions": ";".join(a for a in ACTIONS if res[a]["eligible"]),
            "action_if_lock_not_netted": gross_action,
        }
        for a in ACTIONS[1:]:
            out[f"ev_{a}"] = res[a]["ev"]
        rows.append(out)
        ranked = sorted(ACTIONS, key=lambda a: (not res[a]["eligible"],
                                                -(res[a]["ev"] if res[a]["eligible"] else 0), ACTIONS.index(a)))
        for rank, a in enumerate(ranked, 1):
            v = res[a]
            cands.append({
                "account_id": row["account_id"], "action": ACTION_LABEL[a], "action_code": a,
                "eligible": bool(v["eligible"]), "rank": rank if v["eligible"] else np.nan,
                "expected_value": v["ev"], "offer_cost": v["cost"], "save_rate": v["save_rate"],
                "annoyance": v["annoyance"], "save_value": v.get("save_value"), "upsell_gain": v.get("gain"),
                "customer_benefit": v.get("customer_benefit"), "lock_value": v.get("lock_value"),
                "lock_in_months": v.get("lock_in_months", 0), "promo_skus": v.get("skus", ""),
                "blocked_or_ineligible_reason": "" if v["eligible"] else v["detail"],
                "reason": out["reason"] if a == action else candidate_reason(a, v, action),
                "is_chosen": a == action,
            })
    return pd.DataFrame(rows), pd.DataFrame(cands)


def main() -> pd.DataFrame:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = det.connect_ro()
    cat = det.load_catalog(conn)
    facts = det.build_account_facts(conn)

    facts, feat_note = det.apply_features_csv(facts, OUT_DIR / "features.csv")
    print(f"features: {feat_note}")
    facts, enr_note = det.apply_enrichment(facts, OUT_DIR / "enrichment.csv")
    print(f"household/enrichment: {enr_note}; ENRICHMENT_IN_DECISIONS={CONFIG['ENRICHMENT_IN_DECISIONS']}")
    churn, source = load_churn_scores(facts)
    df = facts.merge(churn, on="account_id", how="left")
    if df["p_churn_90d"].isna().any():
        n = int(df["p_churn_90d"].isna().sum())
        print(f"WARNING: {n} accounts missing p_churn_90d; filled with the median")
        df["p_churn_90d"] = df["p_churn_90d"].fillna(df["p_churn_90d"].median())
    print(f"churn scores: {source}")

    plans = cat["plans"]
    df["all_low_use_premium_any"] = df["um_plan_overpay"]  # sandbox misfit rule (all lines < 5 GB on premium)
    df["um_plan_overpay"] = [bool(r["um_plan_overpay"] or right_size_option(r, plans) is not None
                                  or variant_option(r, plans) is not None) for _, r in df.iterrows()]
    df["upgrade_moment"] = df[det.UPGRADE_MOMENT_COLS].any(axis=1)
    # upgrade gate: tm-bench NO-INCOME upgrade model, top 15% (upgrade_gate.py); detectors AND gate
    import upgrade_gate as ug
    gs = ug.load() if CONFIG["UPGRADE_GATE"] else None
    if gs is not None:
        df = df.merge(gs[["account_id", "upgrade_pct", "in_top15"]], on="account_id", how="left")
        df["in_top15"] = df["in_top15"].fillna(False).astype(bool)
        print(f"upgrade gate: {int(df.in_top15.sum())} accounts in the no-income model's top 15%")
    else:
        df["upgrade_pct"], df["in_top15"] = np.nan, True
    df["upgrade_candidate"] = df["upgrade_moment"] & df["in_top15"]
    # timekeeper now-vs-wait per line (also feeds family_upgrade: phones with trade-in value after balance)
    lt = det.build_line_tradein(conn, cat["promotions"], df.set_index("account_id")["plan_family"])
    lt.to_csv(OUT_DIR / "line_tradein.csv", index=False)
    tv = lt[(lt["net_now_cents"] > 0) | ((lt["financing_balance_cents"] == 0) & (lt["tradein_value_now_cents"] > 0))]
    df["n_tradein_value_lines"] = df["account_id"].map(tv.groupby("account_id").size()).fillna(0).astype(int)

    offers, cands = choose(df, cat["promotions"], plans)
    fx = df.set_index("account_id")
    for lang in ("en", "es"):
        offers[f"message_{lang}"] = [
            om.build_message(fx.loc[a], code, DETAILS[a]["res"], cat["promotions"], plans, lang)
            for a, code in zip(offers["account_id"], offers["action_code"])]
    offers["message_status"] = np.where(
        offers["action_code"] == "keep_your_phone", "suppressed_adapted_promo",
        np.where(offers["action_code"] == "do_nothing", "no_contact", "ok"))
    val = om.validate_messages(offers, df, cat["promotions"], plans, cat.get("addons"))
    val.to_csv(OUT_DIR / "message_validation.csv", index=False)
    print(f"messages: {int(val.passed.sum())}/{len(val)} accounts pass the validator "
          f"({int((offers.message_en != '').sum())} with a message)")
    offers = offers.merge(df[["account_id", "upgrade_moment", "upgrade_pct", "upgrade_candidate"]
                             + det.UPGRADE_MOMENT_COLS], on="account_id")
    offers["churn_source"] = "real" if source.startswith("real") else "mock"
    offers["enrichment_in_decisions"] = CONFIG["ENRICHMENT_IN_DECISIONS"]
    offers["data_note"] = "synthetic/simulated"
    first = ["account_id", "action", "expected_value", "reason", "segment", "why_this_offer", "lock_in_months",
             "drivers", "promo_skus", "runner_up_action", "runner_up_ev",
             "upgrade_moment"] + det.UPGRADE_MOMENT_COLS + ["message_en", "message_es"]
    offers = offers[first + [c for c in offers.columns if c not in first]].sort_values("risk_rank")
    offers.to_csv(OUT_DIR / "offers.csv", index=False)
    cands["data_note"] = "synthetic/simulated"
    chosen = cands[cands.is_chosen].set_index("account_id")["action"]
    assert chosen.index.is_unique and len(chosen) == len(offers), "candidates: not exactly one chosen per account"
    assert (chosen.reindex(offers["account_id"]).values == offers["action"].values).all(), "candidates != offers"
    cands.to_csv(OUT_DIR / "offer_candidates.csv", index=False)
    return offers


if __name__ == "__main__":
    o = main()
    print(f"wrote {OUT_DIR / 'offers.csv'} ({len(o)} rows). ALL NUMBERS SYNTHETIC.")
    print(o["action"].value_counts().to_string())
