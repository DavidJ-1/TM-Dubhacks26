"""If-then playbook. First matching rule in rules.RULES wins. Exactly one action."""

from __future__ import annotations

from harness.config import RETENTION_SKUS, UPGRADE_MIN_AGE_MONTHS
from harness.console_offers import eligibility_reasons, empty_cart_facts, is_device_promo, savings_cents
from harness.moments import detect_moment
from harness.playbook.rules import (
    ASSUMPTION_CREDIT_CENTS,
    BILL_JUMP_PCT,
    CAP_RATIO,
    DO_NOTHING_ACCOUNTS,
    RULES,
    TEMPLATES,
    UPGRADE_PUSH_BLOCKED,
)

HIGH_RISK = frozenset({"top_10", "mid_10_30"})


def decide(ctx: dict) -> dict:
    """Return one action for one account. ctx carries sandbox facts, not a second model."""
    matched = None
    for rule in RULES:
        hit = _CHECKS[rule["id"]](ctx)
        if hit is None:
            continue
        matched = _finish(rule, hit, ctx)
        break
    if matched is None:
        matched = _finish(RULES[-1], _do_nothing(ctx), ctx)
    if ctx["account"]["account_id"] in DO_NOTHING_ACCOUNTS and matched["action"] != "DO NOTHING":
        trapped = _finish(RULES[-1], _do_nothing(ctx), ctx)
        trapped["rejected"] = (
            "Happy-caller trap: this account stays do nothing. "
            "Resolved support contacts are not treated as an unresolved issue."
        )
        trapped["trigger"] = "Happy frequent caller"
        matched = trapped
    if ctx["account"]["account_id"] in UPGRADE_PUSH_BLOCKED and matched.get("upgrade_outcome") == "now":
        matched = _block_upgrade_push(matched)
    matched["promo_skus"] = [sku for sku in matched["promo_skus"] if sku][:1]
    matched["stacked_promos"] = False
    return matched


def _finish(rule: dict, hit: dict, ctx: dict) -> dict:
    account = ctx["account"]
    offer_line = hit.get("offer_line") or hit.get("offer_name") or "No offer."
    template = TEMPLATES[hit.get("template") or rule["template"]]
    channel = hit.get("channel") or (
        "none" if rule["channel"] == "none" else (account.get("contact_preference") or "app")
    )
    if rule["channel"] not in {"account contact preference", "none"}:
        channel = rule["channel"]
    reasons = list(hit.get("reasons") or [])[:3]
    while len(reasons) < 3:
        reasons.append({"text": "", "source": ""})
    return {
        "rule_id": rule["id"],
        "action": hit.get("action") or rule["action"],
        "trigger": hit.get("trigger") or rule["when"],
        "offer_name": hit.get("offer_name") or "None",
        "offer_sku": hit.get("offer_sku"),
        "offer_cents": hit.get("offer_cents"),
        "offer_is_assumption": bool(hit.get("offer_is_assumption")),
        "promo_skus": list(hit.get("promo_skus") or []),
        "stacked_promos": False,
        "channel": channel,
        "why": hit.get("why") or rule["when"],
        "rejected": hit.get("rejected") or "No later rule was reached.",
        "reasons": reasons,
        "upgrade_outcome": hit.get("upgrade_outcome"),
        "assumption_note": hit.get("assumption_note") or "",
        "message_en": template["en"].format(offer_line=offer_line),
        "message_es": template["es"].format(offer_line=offer_line),
    }


def _reason(text: str, source: str) -> dict:
    return {"text": text, "source": source}


def _plans_on_account(lines: list[dict]) -> list[dict]:
    seen = set()
    plans = []
    for line in lines:
        if line["plan_sku"] in seen:
            continue
        seen.add(line["plan_sku"])
        plans.append(
            {
                "plan_family": line["plan_family"],
                "plan_variant": line["plan_variant"],
                "line_prices": line["line_prices"],
                "plan_eligibility": line["plan_eligibility"],
            }
        )
    return plans


def _oldest(lines: list[dict]) -> int | None:
    ages = [int(line["age_months"]) for line in lines if line.get("age_months") is not None]
    return max(ages) if ages else None


def _first_price(line_prices: str) -> int:
    return int(str(line_prices).split(",")[0])


def _plan_allowed(plan: dict, account: dict, n_lines: int) -> bool:
    needed = plan.get("eligibility") or plan.get("plan_eligibility")
    if needed and account.get("discount_group") != needed:
        return False
    minimum = int(plan["min_lines"]) if plan.get("min_lines") else 1
    maximum = int(plan["max_lines"]) if plan.get("max_lines") else None
    if n_lines < minimum:
        return False
    if maximum is not None and n_lines > maximum:
        return False
    return True


def _current_price(lines: list[dict]) -> int | None:
    if not lines:
        return None
    return _first_price(lines[0]["line_prices"])


def _eligible_promos(ctx: dict, skus: set[str] | None, *, allow_device: bool) -> list[dict]:
    account = ctx["account"]
    lines = ctx["lines"]
    facts = empty_cart_facts(account, _plans_on_account(lines), len(lines), _oldest(lines))
    found = []
    for promo in ctx["promos"]:
        if skus is not None and promo["sku"] not in skus:
            continue
        if promo.get("requires_port_in"):
            continue
        if not allow_device and is_device_promo(promo):
            continue
        reasons = eligibility_reasons(promo, facts, ctx.get("device_names") or {})
        if reasons:
            continue
        found.append(
            {
                "sku": promo["sku"],
                "name": promo["name"],
                "savings_cents": int(savings_cents(promo, facts)),
                "device": is_device_promo(promo),
            }
        )
    found.sort(key=lambda item: item["savings_cents"], reverse=True)
    return found


def _fix_first(ctx: dict) -> dict | None:
    unresolved = int(ctx.get("unresolved_90d") or 0)
    if unresolved < 1:
        return None
    return {
        "trigger": f"{unresolved} unresolved support contact(s) in 90 days",
        "offer_name": "None",
        "offer_line": "No offer.",
        "why": "An open support issue comes before any promo or upgrade.",
        "rejected": "A retention promo was not considered. Fix the issue first.",
        "reasons": [
            _reason(f"{unresolved} support contact(s) are still unresolved in the last 90 days.", "support"),
            _reason("No promotion is attached to a fix-first message.", "promotions"),
            _reason(f"Model A risk band is {ctx['risk_band']}.", "context"),
        ],
    }


def _retention(ctx: dict) -> dict | None:
    account = ctx["account"]
    port_out = int(account.get("port_out_inquiry") or 0) == 1
    high_value = ctx["value_band"] == "high"
    if not (port_out or (ctx["risk_band"] in HIGH_RISK and high_value)):
        return None
    eligible = _eligible_promos(ctx, set(RETENTION_SKUS), allow_device=True)
    low_risk = ctx["risk_band"] == "rest"
    if low_risk:
        return {
            "trigger": "Port-out inquiry in the low-risk band",
            "offer_name": "None",
            "offer_line": "No discount. Low risk never gets a promo.",
            "why": "They asked about leaving, but the low-risk band does not get a discount.",
            "rejected": "Eligible credits were rejected because low risk never gets a discount.",
            "reasons": [
                _reason("Port-out inquiry is on the account.", "context"),
                _reason("Risk band is the rest of the book, so no promo is applied.", "context"),
                _reason("Retention promotions were not priced onto this account.", "promotions"),
            ],
        }
    if eligible:
        winner = eligible[0]
        runner = eligible[1]["name"] if len(eligible) > 1 else "a second promo"
        return {
            "trigger": "Port-out inquiry" if port_out else "High risk and high value",
            "offer_name": winner["name"],
            "offer_sku": winner["sku"],
            "offer_cents": winner["savings_cents"],
            "promo_skus": [winner["sku"]],
            "offer_line": f"Eligible offer: {winner['name']}.",
            "why": "This is the eligible sandbox retention promo with the highest savings. Only one promo is applied.",
            "rejected": f"{runner} was eligible too and was not stacked.",
            "reasons": [
                _reason("Port-out inquiry is on the account." if port_out else "High risk and high value.", "context"),
                _reason(f"{winner['name']} is eligible on an empty cart.", "promotions"),
                _reason(f"Sandbox savings on that promo are {winner['savings_cents']} cents, subtracted by us.", "promotions"),
            ],
        }
    if not high_value:
        return {
            "trigger": "Port-out inquiry on a lower-value account",
            "offer_name": "None",
            "offer_line": "No credit. Lower value does not get an assumption credit.",
            "why": "No retention promo is eligible, and a made-up credit is not used on lower value.",
            "rejected": "The assumption credit was rejected because this is not the high-value band.",
            "reasons": [
                _reason("Port-out inquiry is on the account.", "context"),
                _reason("None of the three retention offers is eligible.", "promotions"),
                _reason("Value band is lower, so no assumption credit.", "billing"),
            ],
        }
    cents = int(ctx.get("assumption_credit_cents") or ASSUMPTION_CREDIT_CENTS)
    return {
        "trigger": "High risk and high value, no eligible retention promo",
        "offer_name": "Assumption credit",
        "offer_cents": cents,
        "offer_is_assumption": True,
        "offer_line": f"Assumption credit of {cents} cents. This is not a T-Mobile price.",
        "why": "No sandbox retention promo is eligible. The credit amount is an editable assumption.",
        "rejected": "A real promo was not used because none of the three retention offers was eligible.",
        "assumption_note": "Assumption credit. Not a published T-Mobile offer.",
        "reasons": [
            _reason("High risk and high value, with no eligible retention promo.", "context"),
            _reason("The three stub retention offers were checked and none was eligible.", "promotions"),
            _reason(f"Assumption credit is {cents} cents.", "billing"),
        ],
    }


def _cheaper_plan(ctx: dict) -> dict | None:
    current = _current_price(ctx["lines"])
    if current is None:
        return None
    account = ctx["account"]
    best = None
    for plan in ctx.get("catalog_plans") or []:
        if not _plan_allowed(plan, account, len(ctx["lines"])):
            continue
        price = _first_price(plan["line_prices"])
        if price >= current:
            continue
        if best is None or price < best["price"]:
            best = {"name": plan["name"], "sku": plan["sku"], "price": price, "saves": current - price}
    return best


def _explain_bill(ctx: dict) -> dict | None:
    jump = float(ctx["account"].get("bill_increase_pct") or 0)
    if jump <= BILL_JUMP_PCT:
        return None
    cheaper = _cheaper_plan(ctx)
    reasons = [
        _reason(f"Latest bill is {jump:.0%} above the average of the earlier months.", "billing"),
    ]
    if cheaper is None:
        reasons.append(_reason("No eligible catalog plan has a lower first-line price.", "promotions"))
        reasons.append(_reason("The message explains the bill and does not invent a discount.", "context"))
        return {
            "trigger": "Bill jump",
            "offer_name": "Explain only",
            "offer_line": "We explain the bill. No cheaper catalog plan saves money.",
            "why": "Explain the bill first. A plan change is included only when the catalog price is lower.",
            "rejected": "A device offer was not used. The bill is explained before any upgrade.",
            "reasons": reasons,
        }
    reasons.append(_reason(f"{cheaper['name']} is {cheaper['saves']} cents less on the first line.", "promotions"))
    reasons.append(_reason("That gap is the catalog price, not a projected save.", "promotions"))
    return {
        "trigger": "Bill jump",
        "offer_name": cheaper["name"],
        "offer_sku": cheaper["sku"],
        "offer_cents": cheaper["saves"],
        "offer_line": f"Catalog plan {cheaper['name']} is lower by {cheaper['saves']} cents on the first line.",
        "why": "The bill is explained, and this catalog plan actually costs less.",
        "rejected": "A retention credit was not added on top of the cheaper plan.",
        "reasons": reasons,
    }


def _near_cap(ctx: dict) -> tuple[float, int] | None:
    worst = None
    for line in ctx["lines"]:
        cap = line.get("data_cap_gb")
        usage = line.get("usage_3m_gb")
        if cap is None or usage is None:
            continue
        if float(usage) + 1e-9 >= CAP_RATIO * float(cap):
            if worst is None or float(usage) > worst[0]:
                worst = (float(usage), int(cap))
    return worst


def _fit_plan(ctx: dict, usage: float) -> dict | None:
    account = ctx["account"]
    best = None
    for plan in ctx.get("catalog_plans") or []:
        if not _plan_allowed(plan, account, len(ctx["lines"])):
            continue
        cap = plan.get("data_cap_gb")
        if cap is not None and float(usage) > float(cap):
            continue
        price = _first_price(plan["line_prices"])
        if best is None or price < best["price"]:
            best = {"name": plan["name"], "sku": plan["sku"], "price": price, "cap": cap}
    return best


def _plan_fit(ctx: dict) -> dict | None:
    near = _near_cap(ctx)
    if near is None:
        return None
    usage, cap = near
    fit = _fit_plan(ctx, usage)
    if fit is None:
        return {
            "trigger": "Near data cap",
            "offer_name": "None",
            "offer_line": "No catalog plan covers this usage.",
            "why": "Usage is near the cap. No device offer is made before a plan.",
            "rejected": "An upgrade was not offered. Plan fit comes first, and no catalog plan covers the usage.",
            "reasons": [
                _reason(f"Recent usage is {usage:.1f} GB against a {cap} GB cap.", "usage"),
                _reason("No eligible catalog plan covers that usage.", "promotions"),
                _reason("A device promo is not stacked onto this step.", "promotions"),
            ],
        }
    return {
        "trigger": "Near data cap",
        "offer_name": fit["name"],
        "offer_sku": fit["sku"],
        "offer_line": f"Catalog plan {fit['name']} covers this usage. No device is offered first.",
        "why": "Plan fit comes before any device offer.",
        "rejected": "A device promo was rejected because the cap is a plan problem.",
        "reasons": [
            _reason(f"Recent usage is {usage:.1f} GB against a {cap} GB cap.", "usage"),
            _reason(f"{fit['name']} is a catalog plan that covers that usage.", "promotions"),
            _reason("Only the plan is offered. No second promo is added.", "promotions"),
        ],
    }


def _upgrade_case(ctx: dict) -> dict | None:
    lines = ctx["lines"]
    paid_off = any(
        (not line.get("byod")) and line.get("device_sku") and int(line.get("financing_balance_cents") or 0) == 0
        for line in lines
    )
    eligible_age = any(
        line.get("age_months") is not None and int(line["age_months"]) >= UPGRADE_MIN_AGE_MONTHS and line.get("device_sku")
        for line in lines
    )
    if not paid_off and not eligible_age:
        return None
    moment = ctx.get("moment")
    if moment is None and ctx.get("curves") is not None:
        moment = detect_moment(
            ctx["account"],
            lines,
            ctx.get("curves") or {},
            ctx.get("promos") or [],
            ctx.get("candidates") or [],
            ctx.get("device_names") or {},
        )
    outcome = (moment or {}).get("when") or ("now" if paid_off else "wait")
    if ctx["account"]["account_id"] in UPGRADE_PUSH_BLOCKED and outcome == "now":
        outcome = "keep" if not eligible_age else "wait"
    promo = (moment or {}).get("promo") if outcome == "now" else None
    if ctx["account"]["account_id"] in UPGRADE_PUSH_BLOCKED:
        promo = None
        outcome = "keep" if outcome == "now" else outcome
    assumption = ""
    if outcome == "wait":
        assumption = (
            "Modeled assumption: any wait that is not the 12-month ownership rule or the remaining "
            "installment is not a launch date. The sandbox has no release dates or battery health."
        )
    if outcome == "keep":
        offer_line = "Keep the phone. No upgrade push."
        offer_name = "Keep"
    elif outcome == "wait":
        headline = (moment or {}).get("headline") or "Wait. Upgrade eligibility is the 12-month ownership rule."
        offer_line = headline
        offer_name = "Wait"
    else:
        offer_name = (promo or {}).get("name") or "Upgrade now"
        offer_line = f"Upgrade now. {offer_name}."
    sku = (promo or {}).get("sku") if isinstance(promo, dict) else None
    return {
        "trigger": "Phone paid off" if paid_off else "Upgrade-eligible (12+ months owned)",
        "offer_name": offer_name,
        "offer_sku": sku,
        "offer_cents": (promo or {}).get("savings_cents") if isinstance(promo, dict) else None,
        "promo_skus": [sku] if sku else [],
        "upgrade_outcome": outcome,
        "offer_line": offer_line,
        "why": "Upgrade timing is now, wait, or keep. At most one device promo, and only on upgrade now.",
        "rejected": "A second device promo is not stacked. A bill credit is not added on top.",
        "assumption_note": assumption,
        "reasons": [
            _reason("Paid off." if paid_off else "Owned 12 months or more.", "context"),
            _reason(f"Timing outcome is {outcome}.", "context"),
            _reason(
                "Device promo savings are subtracted by us." if sku else "No device promo on this outcome.",
                "promotions",
            ),
        ],
    }


def _promo_expired(ctx: dict) -> dict | None:
    if int(ctx["account"].get("promo_expired_recent") or 0) != 1:
        return None
    if ctx["risk_band"] == "rest":
        return {
            "trigger": "Promo expired, low risk",
            "action": "DO NOTHING",
            "offer_name": "None",
            "offer_line": "No message: nothing would help them right now.",
            "why": "The promo ended, but low risk does not get a discount.",
            "template": "do_nothing",
            "rejected": "A re-offer was rejected because low risk never gets a discount.",
            "reasons": [
                _reason("A promo expired in the last 3 billing months.", "billing"),
                _reason("Risk band is the rest of the book.", "context"),
                _reason("No replacement promo is attached.", "promotions"),
            ],
        }
    eligible = _eligible_promos(ctx, None, allow_device=False)
    if not eligible:
        return None
    winner = eligible[0]
    return {
        "trigger": "Promo expired and still eligible",
        "offer_name": winner["name"],
        "offer_sku": winner["sku"],
        "offer_cents": winner["savings_cents"],
        "promo_skus": [winner["sku"]],
        "offer_line": f"Still eligible: {winner['name']}.",
        "why": "The expired promo is re-offered only because this account is still eligible for a real one.",
        "rejected": "A second promo was not stacked on the re-offer.",
        "reasons": [
            _reason("A promo expired in the last 3 billing months.", "billing"),
            _reason(f"{winner['name']} is still eligible.", "promotions"),
            _reason("Only that one promo is attached.", "promotions"),
        ],
    }


def _do_nothing(ctx: dict) -> dict:
    return {
        "trigger": "No earlier rule matched",
        "offer_name": "None",
        "offer_line": "No message: nothing would help them right now.",
        "why": "No message: nothing would help them right now.",
        "rejected": "No promo was next. Doing nothing is the choice.",
        "reasons": [
            _reason(f"Risk band is {ctx['risk_band']}.", "context"),
            _reason(f"Value band is {ctx['value_band']}.", "billing"),
            _reason("No unresolved support, port-out, bill jump, cap, upgrade moment, or eligible re-offer won.", "context"),
        ],
    }


def _block_upgrade_push(decision: dict) -> dict:
    decision = dict(decision)
    decision["upgrade_outcome"] = "keep"
    decision["offer_name"] = "Keep"
    decision["offer_sku"] = None
    decision["offer_cents"] = None
    decision["promo_skus"] = []
    decision["offer_line"] = "Keep the phone. No upgrade push."
    decision["message_en"] = TEMPLATES["upgrade_timing"]["en"].format(offer_line=decision["offer_line"])
    decision["message_es"] = TEMPLATES["upgrade_timing"]["es"].format(offer_line=decision["offer_line"])
    decision["rejected"] = "Upgrade push blocked for persona 07 or 31."
    decision["why"] = "This persona never gets an upgrade push. Keep is the outcome."
    decision["assumption_note"] = (
        "Modeled assumption: waiting out a launch is not in the data. The sandbox has no release dates or battery health."
    )
    return decision


_CHECKS = {
    "fix_first": _fix_first,
    "retention": _retention,
    "explain_bill": _explain_bill,
    "plan_fit": _plan_fit,
    "upgrade_timing": _upgrade_case,
    "promo_expired": _promo_expired,
    "do_nothing": _do_nothing,
}
