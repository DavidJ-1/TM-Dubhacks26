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
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offer_detectors as det  # noqa: E402

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
    "BILL_SHOCK_RELIEF": {                      # POLICY OVERRIDE, not a sandbox rule: in that same window the
        "enabled": True,                        # care credit's 3-contact minimum is relaxed so bill-shocked
        "care_credit_min_contacts": 1,          # customers who did reach out can get it (tenure >= 6 still applies)
        "credit_save_boost": 0.05,              # credits directly offset the price rise: +5 pts save rate
    },
    # --- probability the customer takes the offer (only matters for upsell gain / conditional costs)
    "P_ACCEPT": {"right_size": 0.60, "step_up": 0.25, "device_upgrade": 0.15},
    # --- annoyance: dollar-equivalent cost of contacting (agent time, message fatigue, sleeping-dog risk)
    "ANNOYANCE": {
        "care_credit": 3.0, "loyalty_credit": 3.0, "keep_your_phone": 3.0, "right_size": 2.0,
        "step_up": 5.0, "device_upgrade": 6.0, "fix_first": 4.0,
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
    # --- mock churn model (used only when real churn_scores.csv is missing)
    "MOCK_MEAN_MONTHLY_HAZARD": 0.0099,  # calibrate mock to 0.99%/month like tm-data's synthetic labels
}
if os.environ.get("TM_ENABLE_RIGHT_SIZE") is not None:
    CONFIG["ENABLE_RIGHT_SIZE"] = os.environ["TM_ENABLE_RIGHT_SIZE"] not in ("0", "false", "False", "")

ACTIONS = ["do_nothing", "care_credit", "loyalty_credit", "keep_your_phone", "right_size", "step_up",
           "device_upgrade", "fix_first", "care_credit_fix_first"]
ACTION_LABEL = {
    "do_nothing": "do nothing", "care_credit": "$25 care credit", "loyalty_credit": "loyalty credit",
    "keep_your_phone": "keep-your-phone credit", "right_size": "right-size plan", "step_up": "step-up plan",
    "device_upgrade": "device upgrade", "fix_first": "fix-first callback",
    "care_credit_fix_first": "$25 care credit + fix-first callback",
}
PROMO_FOR_ACTION = {
    "care_credit": "PROMO-STUB-CARE-CREDIT", "loyalty_credit": "PROMO-STUB-LOYALTY-CREDIT",
    "keep_your_phone": "PROMO-STUB-KEEP-YOUR-PHONE",
}

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


def right_size_option(row: pd.Series, plans: pd.DataFrame):
    """Cheapest allowed plan that still fits every line's usage and saves >= RIGHT_SIZE_MIN_SAVINGS/mo.

    Gated so we don't push every premium household down to Essentials:
      - households flagged by the sandbox's own misfit rule (every line < 5 GB on a premium plan) may move to
        any cheaper plan that fits;
      - everyone else may only move to a cheaper variant of the SAME family (e.g. a partner / community / 55+
        discount variant they qualify for, or the 4 Line Offer), keeping the same benefits.
    """
    best = None
    low_use = bool(row["all_low_use_premium_any"])
    cur = plans.set_index("sku").loc[row["plan_sku"]]
    for _, p in plans.iterrows():
        if p["sku"] == row["plan_sku"] or not _plan_allowed(p, row["n_lines"], row["discount_group"]):
            continue
        if not low_use and (p["family"] != cur["family"] or p["tier"] != cur["tier"]):
            continue  # same family AND same tier only (no Essentials -> Saver downgrade unless misfit)
        if not _fits_usage(p, row):
            continue
        price = det.plan_price_cents(p["line_prices"], p["extra_line_cents"], row["n_lines"])
        save = (row["plan_price_cents"] - price) / 100
        if save >= CONFIG["RIGHT_SIZE_MIN_SAVINGS"] and (best is None or save > best[1]):
            best = (p, save)
    return best


FAMILY_RANK = {"essentials": 0, "experience_more": 1, "experience_beyond": 2}


def step_up_option(row: pd.Series, plans: pd.DataFrame):
    """Cheapest allowed plan one step up, when the household is outgrowing its plan or a life event hits."""
    outgrowing = bool(row["um_near_plan_limit"] or row["um_over_plan_cap"] or row["um_usage_growth"]
                      or (row["plan_family"] == "essentials" and (row["max_line_hotspot_gb"] or 0) > 0.5)
                      or (row["plan_family"] == "experience_more" and (row["max_line_hotspot_gb"] or 0) > 45))
    grad = bool(row["um_student_graduating"])
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


def drivers(row: pd.Series) -> dict:
    """Which churn drivers are present (synthetic thresholds on real sandbox fields)."""
    return {
        "billing_pain": bool(row["um_promo_expired"] or row["bill_increase_pct"] >= 0.10 or row["billing_90d"] >= 1),
        "service_pain": bool(row["unresolved_90d"] >= 1 or row["network_90d"] >= 2 or row["neg_contacts_90d"] >= 2),
        "network_pain": bool(row["network_90d"] >= 1 and (row["network_unresolved_90d"] >= 1 or row["network_90d"] >= 2)),
        "unresolved": bool(row["unresolved_90d"] >= 1),
        "shopping": bool(row["competitor_research_score"] >= 0.6 or row["port_out_inquiry"] == 1
                         or row["cancel_inquiry_90d"] >= 1),
        "device_pain": bool(row["device_90d"] >= 1 or row["um_old_device"]),
        "overpay": bool(row["um_plan_overpay"]),
        "outgrowing": bool(row["um_near_plan_limit"] or row["um_over_plan_cap"] or row["um_usage_growth"]),
        "life_event": bool(row["um_student_graduating"]),
        "free_to_leave": bool(row["max_financing_months_left"] == 0 and row["n_lines"] > 0),
        "bill_shock_recent": bool(pd.notna(row["days_since_bill_shock"])
                                  and row["days_since_bill_shock"] <= CONFIG["UPSELL_BLOCK_DAYS_AFTER_BILL_SHOCK"]),
        # unresolved contacts about something a callback can actually fix (not only billing)
        "fixable_unresolved": bool(row["unresolved_90d"] > 0
                                   and (row["unresolved_90d"] > row["billing_90d"] or row["network_90d"] > 0
                                        or row["device_90d"] > 0)),
    }


ON_TARGET = {  # action -> drivers it addresses
    "care_credit": ["billing_pain", "service_pain"],
    "loyalty_credit": ["shopping", "billing_pain"],
    "keep_your_phone": ["billing_pain", "shopping"],
    "right_size": ["overpay", "billing_pain"],
    "step_up": ["outgrowing", "life_event"],
    "device_upgrade": ["device_pain", "free_to_leave"],
    "fix_first": ["network_pain", "fixable_unresolved"],
}
CREDIT_ACTIONS = ("care_credit", "loyalty_credit", "keep_your_phone")


def evaluate_account(row: pd.Series, promos: pd.DataFrame, plans: pd.DataFrame) -> dict:
    C = CONFIG
    d = drivers(row)
    p = float(row["p_churn_90d"])
    value = row["service_revenue_cents"] / 100 * C["SERVICE_MARGIN"] * C["VALUE_HORIZON_MONTHS"]
    pain = d["billing_pain"] or d["unresolved"]
    res: dict[str, dict] = {"do_nothing": {"ev": 0.0, "eligible": True, "detail": "", "save_rate": 0.0,
                                           "cost": 0.0, "annoyance": 0.0, "gain": 0.0, "save_value": 0.0}}

    relief = C["BILL_SHOCK_RELIEF"]
    shock_relief = d["bill_shock_recent"] and relief["enabled"]

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
        if action in CREDIT_ACTIONS and shock_relief:
            r += relief["credit_save_boost"]
        return r

    def add(action, eligible, cost, gain=0.0, detail="", why_not=""):
        if not eligible:
            res[action] = {"ev": None, "eligible": False, "detail": why_not,
                           "save_rate": None, "cost": None, "annoyance": None}
            return
        ann = C["COMBO_ANNOYANCE"] if action == "care_credit_fix_first" else C["ANNOYANCE"][action]
        if action in ("step_up", "device_upgrade") and pain:
            ann += C["UPSELL_AFTER_PAIN_PENALTY"]
        ev = p * sr(action) * value + gain - cost - ann
        res[action] = {"ev": round(ev, 2), "eligible": True, "detail": detail, "save_rate": sr(action),
                       "cost": round(cost, 2), "annoyance": round(ann, 2), "gain": round(gain, 2),
                       "save_value": round(p * sr(action) * value, 2)}

    # $25 care credit: PROMO-STUB-CARE-CREDIT (tenure >= 6, >= 3 support contacts in 90d), $25 x 1 month
    pr = promos.loc["PROMO-STUB-CARE-CREDIT"]
    ok, why = promo_rule_ok(pr, row)
    cc_detail = "$25 one-time goodwill credit"
    if not ok and shock_relief:
        relaxed = pr.copy()
        relaxed["min_support_contacts_90d"] = relief["care_credit_min_contacts"]
        ok2, _ = promo_rule_ok(relaxed, row)
        if ok2:
            ok, cc_detail = True, ("$25 goodwill credit via bill-shock relief override "
                                   f"(sandbox rule needs {int(pr['min_support_contacts_90d'])}+ contacts)")
    care_cost = pr["value_cents"] / 100 * (pr["payout_months"] or 1)
    add("care_credit", ok, care_cost, detail=cc_detail, why_not=why)
    care_ok = ok

    # loyalty credit: PROMO-STUB-LOYALTY-CREDIT (tenure >= 36), $5/mo ongoing valued over 12 months
    pr = promos.loc["PROMO-STUB-LOYALTY-CREDIT"]
    ok, why = promo_rule_ok(pr, row)
    mo = pr["value_cents"] / 100
    add("loyalty_credit", ok, mo * C["LOYALTY_CREDIT_MONTHS"],
        detail=f"${mo:.0f}/mo loyalty credit", why_not=why)

    # keep-your-phone: PROMO-STUB-KEEP-YOUR-PHONE is $20/mo but only for a NEW ported-in BYOD Saver line.
    pr = promos.loc["PROMO-STUB-KEEP-YOUR-PHONE"]
    mo = pr["value_cents"] / 100
    if C["STRICT_PROMO_RULES"]:
        add("keep_your_phone", False, 0, why_not="sandbox rule needs a new ported-in BYOD line on Essentials Saver")
    else:
        ok = bool(d["free_to_leave"] and (row["any_paid_off_device"] or row["n_byod"] > 0))
        add("keep_your_phone", ok, mo * C["KYP_MONTHS"],
            detail=f"${mo:.0f}/mo for {C['KYP_MONTHS']} months to keep a paid-off phone (adapted)",
            why_not="still paying off a phone" if not ok else "")

    # right-size plan (flagged scope question)
    rs = right_size_option(row, plans) if C["ENABLE_RIGHT_SIZE"] else None
    if rs is not None:
        plan, save = rs
        add("right_size", True, save * C["RIGHT_SIZE_REVENUE_MONTHS"] * C["P_ACCEPT"]["right_size"],
            detail=f"move to {plan['name']} (saves ${save:.0f}/mo)")
        res["right_size"]["plan_name"], res["right_size"]["save"] = plan["name"], save
    else:
        add("right_size", False, 0, why_not="disabled by ENABLE_RIGHT_SIZE" if not C["ENABLE_RIGHT_SIZE"]
            else "no cheaper allowed plan fits their usage")

    # step-up plan
    su = step_up_option(row, plans)
    shock_block = (f"blocked by bill-shock guardrail (bill rose {int(row['days_since_bill_shock'])} days ago, "
                   f"window {C['UPSELL_BLOCK_DAYS_AFTER_BILL_SHOCK']} days)") if d["bill_shock_recent"] else ""
    if su is not None and shock_block:
        add("step_up", False, 0, why_not=shock_block)
    elif su is not None:
        plan, delta = su
        gain = C["P_ACCEPT"]["step_up"] * delta * C["STEP_UP_MARGIN"] * C["VALUE_HORIZON_MONTHS"] * (1 - p)
        add("step_up", True, 0.0, gain=gain, detail=f"move to {plan['name']} (+${delta:.0f}/mo)")
        res["step_up"]["plan_name"], res["step_up"]["delta"] = plan["name"], delta
    else:
        add("step_up", False, 0, why_not="not outgrowing the plan and no life event")

    # device upgrade: a line that is upgrade-eligible per sandbox stub rule (owned 12+ months, trade-in
    # eligible) and paid off. Credit = best real promo it meets: OLD-PHONE-UPGRADE ($150, phone 36+ months,
    # trade-in) or TRADEIN-ANY ($200, any trade-in, Essentials/More/Beyond). Credit only paid if accepted.
    if row["n_upgrade_ready_lines"] > 0 and shock_block:
        add("device_upgrade", False, 0, why_not=shock_block)
    elif row["n_upgrade_ready_lines"] > 0:
        options = []
        old = promos.loc["PROMO-STUB-OLD-PHONE-UPGRADE"]
        if row["n_old_upgrade_lines"] > 0 and promo_rule_ok(old, row)[0]:
            options.append(old)
        anyt = promos.loc["PROMO-STUB-TRADEIN-ANY"]
        if row["plan_family"] in str(anyt["plan_families"]).split(","):
            options.append(anyt)
        best = max(options, key=lambda r: r["value_cents"])
        credit = best["value_cents"] / 100
        pa = C["P_ACCEPT"]["device_upgrade"]
        add("device_upgrade", True, pa * credit, gain=pa * C["DEVICE_UPGRADE_MARGIN"],
            detail=f"upgrade with {best['name']} (${credit:.0f})")
        res["device_upgrade"]["promo"] = best["sku"]
    else:
        add("device_upgrade", False, 0, why_not="no paid-off, trade-in-eligible phone owned 12+ months")

    # fix-first callback: unresolved contacts or repeated network complaints; no discount
    ok = bool(d["unresolved"] or d["network_pain"])
    add("fix_first", ok, C["FIX_FIRST_CALLBACK_COST"], detail="agent callback to fix the open issue",
        why_not="no open or network issue")
    fix_ok = ok

    # combined: care credit + fix-first callback (both must be eligible on their own)
    add("care_credit_fix_first", care_ok and fix_ok, care_cost + C["FIX_FIRST_CALLBACK_COST"],
        detail="$25 goodwill credit plus an agent callback to fix the issue",
        why_not="needs both the care credit and a fix-first issue")

    return {"res": res, "drivers": d, "value": value}


def reason_text(action: str, row: pd.Series, ev: dict, best_other: tuple | None) -> str:
    d, r = ev["drivers"], ev["res"]
    pv = row["p_churn_90d"] * 100
    pct = f"{pv:.1f}%" if pv >= 1 else f"{pv:.2f}%"
    if action == "do_nothing":
        if best_other is None:
            return f"Simulated churn risk is {pct} and no eligible offer applies, so we leave them alone."
        return (f"Simulated churn risk is {pct}, so even the best option ({ACTION_LABEL[best_other[0]]}) "
                f"costs more than it saves; we leave them alone.")
    if action == "fix_first":
        if d["network_pain"]:
            return (f"They've logged {row['network_90d']} network complaints in 90 days, so an agent callback "
                    "to fix coverage beats a discount.")
        if row["billing_90d"] >= 1 and d["billing_pain"]:
            bump = f" after their bill rose {row['bill_increase_pct']*100:.0f}%" if row["bill_increase_pct"] >= 0.05 else ""
            return (f"Their billing questions{bump} are still unresolved, so an agent callback to fix the bill "
                    "beats a discount they don't qualify for yet.")
        return (f"They have {row['unresolved_90d']} unresolved support contacts, so an agent callback to fix the "
                "problem beats a discount.")
    if action == "care_credit_fix_first":
        issue = f"{int(row['network_90d'])} network complaints" if d["network_pain"] else "unresolved support issues"
        if row["um_promo_expired"]:
            price = " and a bill that jumped after a promo ended"
        elif d["billing_pain"]:
            price = " and billing frustration"
        else:
            price = ""
        return f"They have {issue}{price}, so we fix the problem first and add a $25 goodwill credit."
    if action == "care_credit" and d["bill_shock_recent"]:
        return (f"Their bill went up {row['bill_increase_pct']*100:.0f}% after a promo ended and they reached out, "
                "so a $25 goodwill credit (not an upsell) is the best value.")
    if action == "care_credit":
        why = "their bill jumped after a promo ended" if d["billing_pain"] else "they've had a rough run with support"
        return f"They've contacted us {int(row['support_90d'])} times in 90 days and {why}, so a $25 goodwill credit is the best value."
    if action == "loyalty_credit":
        return f"After {int(row['tenure_months'])} months with us they're showing signs of shopping around, so a $5/mo loyalty credit is the best value."
    if action == "keep_your_phone":
        return "Their phone is paid off, so nothing keeps them here; a monthly credit to keep their phone is the best value."
    if action == "right_size":
        return f"They're paying for more plan than they use; moving to {r['right_size']['plan_name']} saves ${r['right_size']['save']:.0f}/mo and lowers their risk."
    if action == "step_up":
        why = "they're graduating and will lose the student setup" if d["life_event"] and not d["outgrowing"] \
            else "their usage is outgrowing their plan"
        return f"{why[0].upper() + why[1:]}, so {r['step_up']['plan_name']} is a timely step-up."
    if action == "device_upgrade":
        return "Their phone is paid off and old enough to trade in, so an upgrade with a real trade-in credit is the best value."
    return ""


def candidate_reason(a: str, v: dict, chosen: str) -> str:
    if not v["eligible"]:
        return f"Not eligible: {v['detail']}."
    if a == "do_nothing":
        return "Baseline: no contact, no cost (EV 0)."
    parts = f"save value ${v['save_value']:.2f}"
    if v.get("gain"):
        parts += f" + upsell ${v['gain']:.2f}"
    tail = "chosen" if a == chosen else ("below zero" if v["ev"] < 0 else "lower EV than the chosen action")
    return f"Eligible ({v['detail']}): {parts} - cost ${v['cost']:.2f} - annoyance ${v['annoyance']:.2f}; {tail}."


def choose(df: pd.DataFrame, promos: pd.DataFrame, plans: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, cands = [], []
    for _, row in df.iterrows():
        ev = evaluate_account(row, promos, plans)
        res = ev["res"]
        scored = sorted(((a, v["ev"]) for a, v in res.items() if v["eligible"] and a != "do_nothing"),
                        key=lambda t: (-t[1], ACTIONS.index(t[0])))
        best_other = scored[0] if scored else None
        if best_other and best_other[1] > 0:
            action, evv = best_other
            runner = ("do_nothing", 0.0) if len(scored) < 2 or scored[1][1] < 0 else scored[1]
        else:
            action, evv, runner = "do_nothing", 0.0, best_other
        out = {
            "account_id": row["account_id"], "action": ACTION_LABEL[action], "action_code": action,
            "expected_value": round(evv, 2), "reason": reason_text(action, row, ev, best_other),
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
        }
        for a in ACTIONS[1:]:
            out[f"ev_{a}"] = res[a]["ev"]
        rows.append(out)
        for a in ACTIONS:
            v = res[a]
            cands.append({
                "account_id": row["account_id"], "action": ACTION_LABEL[a], "eligible": bool(v["eligible"]),
                "expected_value": v["ev"], "offer_cost": v["cost"], "save_rate": v["save_rate"],
                "annoyance": v["annoyance"],
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
    churn, source = load_churn_scores(facts)
    df = facts.merge(churn, on="account_id", how="left")
    if df["p_churn_90d"].isna().any():
        n = int(df["p_churn_90d"].isna().sum())
        print(f"WARNING: {n} accounts missing p_churn_90d; filled with the median")
        df["p_churn_90d"] = df["p_churn_90d"].fillna(df["p_churn_90d"].median())
    print(f"churn scores: {source}")

    # finalise um_plan_overpay: sandbox misfit rule OR a cheaper plan fits (search runs regardless of flag)
    plans = cat["plans"]
    df["all_low_use_premium_any"] = df["um_plan_overpay"]  # sandbox misfit rule (all lines < 5 GB on premium)
    df["um_plan_overpay"] = [bool(r["um_plan_overpay"] or right_size_option(r, plans) is not None)
                             for _, r in df.iterrows()]
    df["upgrade_moment"] = df[det.UPGRADE_MOMENT_COLS].any(axis=1)

    offers, cands = choose(df, cat["promotions"], plans)
    offers = offers.merge(df[["account_id", "upgrade_moment"] + det.UPGRADE_MOMENT_COLS], on="account_id")
    offers["churn_source"] = "real" if source.startswith("real") else "mock"
    offers["data_note"] = "synthetic/simulated"
    first = ["account_id", "action", "expected_value", "reason", "runner_up_action", "runner_up_ev",
             "upgrade_moment"] + det.UPGRADE_MOMENT_COLS
    offers = offers[first + [c for c in offers.columns if c not in first]].sort_values("risk_rank")
    offers.to_csv(OUT_DIR / "offers.csv", index=False)
    cands["data_note"] = "synthetic/simulated"
    # integrity: exactly one chosen per account, matching offers.csv
    chosen = cands[cands.is_chosen].set_index("account_id")["action"]
    assert chosen.index.is_unique and len(chosen) == len(offers), "candidates: not exactly one chosen per account"
    assert (chosen.reindex(offers["account_id"]).values == offers["action"].values).all(), "candidates != offers"
    cands.to_csv(OUT_DIR / "offer_candidates.csv", index=False)
    return offers


if __name__ == "__main__":
    o = main()
    print(f"wrote {OUT_DIR / 'offers.csv'} ({len(o)} rows). ALL NUMBERS SYNTHETIC.")
    print(o["action"].value_counts().to_string())
