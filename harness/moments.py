"""Upgrade-moment detector. Triggers are phone paid off, usage over the cap, and phone age.

Timing uses the sandbox upgrade rule (12+ months owned on a 24-month financing term), the
good-condition trade-in curve, and the remaining installment. Battery health and any
'wait for the next launch' language are labeled as modeled assumptions.
"""

from __future__ import annotations

from harness.config import (
    BATTERY_DROP_PER_MONTH,
    BATTERY_FLOOR,
    FINANCING_TERM_MONTHS,
    OLD_PHONE_MONTHS,
    TRADEIN_DROP_NOW_CENTS,
    TRADEIN_MAX_AGE,
    UPGRADE_MIN_AGE_MONTHS,
)
from harness.data import tradein_value_cents
from harness.console_offers import best_device_promo


def estimated_battery_pct(age_months: int) -> int:
    """No battery field exists. About 0.7 points per month, floored, and labeled as a model."""
    return max(BATTERY_FLOOR, round(100 - BATTERY_DROP_PER_MONTH * age_months))


def _line_triggers(line: dict) -> list[str]:
    triggers = []
    age = line.get("age_months")
    if age is None or line.get("device_sku") is None:
        if line.get("over_cap"):
            triggers.append("usage_over_cap")
        return triggers
    paid_off = (not line["byod"]) and int(line["financing_balance_cents"] or 0) == 0
    if paid_off and int(age) >= UPGRADE_MIN_AGE_MONTHS:
        triggers.append("paid_off")
    if int(age) >= OLD_PHONE_MONTHS:
        triggers.append("phone_age")
    if line.get("over_cap"):
        triggers.append("usage_over_cap")
    return triggers


def _priority(triggers: list[str], age: int | None) -> int:
    score = 0
    if "phone_age" in triggers and "paid_off" in triggers:
        score += 100
    elif "paid_off" in triggers:
        score += 70
    elif "phone_age" in triggers:
        score += 50
    if "usage_over_cap" in triggers:
        score += 40
    if age is not None and int(age) < UPGRADE_MIN_AGE_MONTHS:
        score -= 10
    return score


def _timing(line: dict, curves: dict) -> dict:
    age = int(line["age_months"])
    balance = 0 if line["byod"] else int(line["financing_balance_cents"] or 0)
    months_left = 0 if line["byod"] else int(line["financing_months_remaining"] or 0)
    value_now = tradein_value_cents(curves, line["device_sku"], age) if line.get("tradein_eligible") else None
    value_in_6 = (
        tradein_value_cents(curves, line["device_sku"], min(TRADEIN_MAX_AGE, age + 6))
        if line.get("tradein_eligible")
        else None
    )
    battery = estimated_battery_pct(age)
    base = {
        "age_months": age,
        "upgrade_eligible": age >= UPGRADE_MIN_AGE_MONTHS,
        "balance_cents": balance,
        "months_remaining": months_left,
        "tradein_value_cents": value_now,
        "tradein_value_in_6_cents": value_in_6,
        "battery_pct": battery,
        "battery_note": (
            f"Estimated battery health about {battery}% (modeled from phone age: "
            f"{BATTERY_DROP_PER_MONTH} points a month, floor {BATTERY_FLOOR}%)."
        ),
        "condition_note": "The trade-in curve is good condition. Fair and poor are not assumed.",
    }
    if age < UPGRADE_MIN_AGE_MONTHS:
        wait = UPGRADE_MIN_AGE_MONTHS - age
        base.update(
            {
                "when": "wait",
                "headline": (
                    f"Wait {wait} month{'s' if wait != 1 else ''} until the phone has been owned "
                    f"{UPGRADE_MIN_AGE_MONTHS} months. That is the sandbox upgrade rule "
                    f"(half of the {FINANCING_TERM_MONTHS}-month financing term)."
                ),
                "assumption": (
                    "This wait is the published sandbox rule, not a guess about the next phone. "
                    "The catalog has no future release dates."
                ),
            }
        )
        return base
    if balance > 0 and value_now is not None and value_now < balance:
        base.update(
            {
                "when": "wait",
                "headline": (
                    f"Wait. Trading this phone in today would charge the remaining "
                    f"${balance / 100:,.2f}, and the good-condition trade-in is "
                    f"${value_now / 100:,.2f}. {months_left} installment month"
                    f"{'s' if months_left != 1 else ''} remain."
                ),
                "assumption": (
                    "The payoff countdown comes from financing_months_remaining. "
                    "We are not waiting on a future launch; the sandbox has no future release dates."
                ),
            }
        )
        return base
    drop = (value_now - value_in_6) if value_now is not None and value_in_6 is not None else 0
    old = age >= OLD_PHONE_MONTHS
    if balance == 0 and (old or drop >= TRADEIN_DROP_NOW_CENTS):
        base.update(
            {
                "when": "now",
                "headline": (
                    "Upgrade now. The phone is paid off"
                    + (f" and {age} months old" if old else "")
                    + (
                        f". On the good-condition curve it loses ${drop / 100:,.2f} over the next 6 months."
                        if drop
                        else "."
                    )
                ),
                "assumption": (
                    "Now versus later uses the good-condition trade-in curve. "
                    "There is no future release date in the data, so this is not a launch-timed call."
                ),
            }
        )
        return base
    if balance == 0:
        base.update(
            {
                "when": "wait",
                "headline": (
                    f"Paid off, and upgrade-eligible, but the good-condition trade-in only moves "
                    f"${drop / 100:,.2f} over 6 months. Waiting is a modeled assumption."
                ),
                "assumption": (
                    "Modeled assumption: we wait because the curve is flat, not because a new phone "
                    "has a known release date. The sandbox does not include future release dates."
                ),
            }
        )
        return base
    # Balance is still positive, but the trade-in covers it. Charging the balance today is real.
    base.update(
        {
            "when": "now",
                "headline": (
                    f"Upgrade-eligible. Trading in today charges the remaining ${balance / 100:,.2f}. "
                    + (
                        "This phone is not marked trade-in eligible, so no curve value is quoted."
                        if value_now is None
                        else f"Good-condition trade-in value is ${value_now / 100:,.2f}."
                    )
                ),
            "assumption": (
                "The remaining balance is charged today if the phone is traded in. "
                "Any sense of waiting for a newer launch would be a modeled assumption; "
                "the catalog has no future release dates."
            ),
        }
    )
    return base


def detect_moment(account: dict, lines: list[dict], curves: dict, promos: list[dict], candidates: list[dict], device_names: dict[str, str]) -> dict | None:
    enriched = []
    for line in lines:
        cap = line.get("data_cap_gb")
        usage = line.get("usage_3m_gb")
        over = cap is not None and usage is not None and float(usage) > float(cap)
        item = dict(line)
        item["over_cap"] = bool(over)
        item["triggers"] = _line_triggers(item)
        if item["triggers"]:
            enriched.append(item)
    if not enriched:
        return None
    chosen = max(enriched, key=lambda line: _priority(line["triggers"], line.get("age_months")))
    if chosen.get("device_sku") is None or chosen.get("age_months") is None:
        return {
            "line_id": chosen["line_id"],
            "device_name": None,
            "triggers": chosen["triggers"],
            "when": "wait",
            "headline": (
                f"Usage on {chosen['member_label']} is over the plan cap "
                f"({float(chosen['usage_3m_gb']):.0f} GB vs {int(chosen['data_cap_gb'])} GB), "
                "and this line has no phone on the account to trade in."
            ),
            "assumption": "No device age, battery, or trade-in is invented for a line without a phone.",
            "other_lines": len(enriched) - 1,
            "promo": None,
            "net_cents": None,
        }
    timing = _timing(chosen, curves)
    ages = [int(line["age_months"]) for line in lines if line.get("age_months") is not None]
    oldest = max(ages) if ages else None
    plans = _unique_plans(lines)
    promo = None
    if timing["when"] == "now" and chosen.get("tradein_eligible") and chosen.get("device_sku"):
        promo = best_device_promo(
            account,
            promos,
            plans,
            n_lines=len(lines),
            oldest_age=oldest,
            line_age=int(chosen["age_months"]),
            candidates=candidates,
            device_names=device_names,
        )
    tradein = timing.get("tradein_value_cents") or 0
    balance = timing.get("balance_cents") or 0
    savings = promo["savings_cents"] if promo else 0
    # Sandbox cart totals do not subtract promo savings. We do.
    net = (tradein - balance + savings) if timing.get("tradein_value_cents") is not None else None
    return {
        "line_id": chosen["line_id"],
        "member_label": chosen["member_label"],
        "member_role": chosen["member_role"],
        "device_name": chosen["device_name"],
        "device_sku": chosen["device_sku"],
        "plan_name": chosen["plan_name"],
        "triggers": chosen["triggers"],
        "over_cap": chosen["over_cap"],
        "usage_3m_gb": chosen.get("usage_3m_gb"),
        "data_cap_gb": chosen.get("data_cap_gb"),
        "other_lines": len(enriched) - 1,
        "promo": promo,
        "net_cents": None if net is None else int(net),
        "stacked_promos": False,
        **timing,
    }


def _unique_plans(lines: list[dict]) -> list[dict]:
    seen = set()
    plans = []
    for line in lines:
        sku = line["plan_sku"]
        if sku in seen:
            continue
        seen.add(sku)
        plans.append(
            {
                "plan_family": line["plan_family"],
                "plan_variant": line["plan_variant"],
                "line_prices": line["line_prices"],
                "plan_eligibility": line["plan_eligibility"],
            }
        )
    return plans
