"""Promotion eligibility, copied from the sandbox rules, and Model B's offer pick.

Empty-cart eligibility is what we can offer without asking the customer to buy a phone.
Device promotions are scored only on an upgrade cart (one new phone, one trade-in, no port-in).
Only one device promotion is kept. Promo savings are subtracted here; the sandbox cart does not.
"""

from __future__ import annotations

from harness.config import (
    ANNOYANCE_CENTS,
    FINANCING_TERM_MONTHS,
    ONGOING_HORIZON_MONTHS,
    POLICY_ACCEPTANCE,
    RISK_FLOOR,
)

RETENTION_OUTREACH = (
    "PROMO-STUB-CARE-CREDIT",
    "PROMO-STUB-LOYALTY-CREDIT",
    "PROMO-STUB-STUDENT",
)


def _split(value: str | None) -> list[str]:
    return value.split(",") if value else []


def _plan_matches(promo: dict, plan: dict) -> bool:
    families, variants = _split(promo["plan_families"]), _split(promo["plan_variants"])
    first_line = int(str(plan["line_prices"]).split(",")[0])
    min_plan = promo["min_plan_cents"]
    return (
        (not families or plan["plan_family"] in families)
        and (not variants or plan["plan_variant"] in variants)
        and (min_plan is None or first_line >= int(min_plan))
        and (not promo["discount_plan_only"] or plan["plan_eligibility"] is not None)
    )


def _plan_reason(promo: dict) -> str:
    parts = []
    if promo["plan_families"]:
        parts.append(" or ".join(part.replace("_", " ") for part in _split(promo["plan_families"])) + " plan")
    if promo["plan_variants"]:
        parts.append("the " + " or ".join(_split(promo["plan_variants"])) + " variant")
    if promo["discount_plan_only"]:
        parts.append("a 55+, partner, or community plan")
    if promo["min_plan_cents"]:
        parts.append(f"at least ${int(promo['min_plan_cents']) / 100:.0f}/month on the first line")
    return "Needs " + ", ".join(parts)


def _qualifying_devices(promo: dict, devices: tuple[str, ...]) -> int:
    allowed = _split(promo["device_skus"])
    return sum(1 for sku in devices if not allowed or sku in allowed)


def eligibility_reasons(promo: dict, facts: dict, device_names: dict[str, str]) -> list[str]:
    """Same checks as api/services/promotions.py, for one account and an optional cart."""
    reasons: list[str] = []
    account = facts["account"]
    groups = _split(promo["discount_groups"])
    if groups and account["discount_group"] not in groups:
        reasons.append(f"Only for {' / '.join(groups)} accounts")
    tiers = _split(promo["credit_tiers"])
    if tiers and account["credit_tier"] not in tiers:
        reasons.append(
            f"Requires well-qualified credit ({' or '.join(tiers)}); this account is {account['credit_tier']}"
        )
    tenure = int(account["tenure_months"])
    if promo["min_tenure_months"] and tenure < int(promo["min_tenure_months"]):
        reasons.append(f"Needs {int(promo['min_tenure_months'])}+ months of tenure (has {tenure})")
    if promo["min_support_contacts_90d"] and facts["support_contacts"] < int(promo["min_support_contacts_90d"]):
        reasons.append(
            f"Needs {int(promo['min_support_contacts_90d'])}+ support contacts in the last 90 days "
            f"(has {int(facts['support_contacts'])})"
        )
    min_age = promo["min_device_age_months"]
    tradein_ages = facts["tradein_ages"]
    if min_age and promo["requires_tradein"] and tradein_ages:
        if max(tradein_ages) < int(min_age):
            reasons.append(
                f"Trade in a phone owned {int(min_age)}+ months (the one in this cart: {max(tradein_ages)})"
            )
    elif min_age and (facts["oldest_device_age"] is None or facts["oldest_device_age"] < int(min_age)):
        reasons.append(f"Needs a device owned {int(min_age)}+ months")

    new_line_ok = facts["new_lines"] > 0 and (not promo["requires_port_in"] or facts["port_in"])
    if promo["new_line_or_tradein"]:
        if not (new_line_ok or facts["tradein"]):
            reasons.append("Add a new line (with a ported-in number) or a trade-in")
    else:
        if promo["requires_new_line"] and facts["new_lines"] == 0:
            reasons.append("Add a new line to the cart")
        elif promo["requires_port_in"] and not facts["port_in"]:
            reasons.append("The new line must port in a number from another carrier")
        if promo["requires_tradein"] and not facts["tradein"]:
            reasons.append("Add a trade-in to the cart")
    if promo["requires_byod"] and facts["new_lines"] > 0 and facts["devices"]:
        reasons.append("The new line must use your own phone (no device in the cart)")
    if int(promo["min_lines"] or 0) > facts["lines"]:
        reasons.append(f"Needs {int(promo['min_lines'])} lines; this household would have {facts['lines']}")

    allowed = _split(promo["device_skus"])
    if allowed and not _qualifying_devices(promo, facts["devices"]):
        names = ", ".join(device_names.get(sku, sku) for sku in allowed)
        reasons.append(f"Add one of these devices: {names}")
    elif promo["requires_device"] and not facts["devices"]:
        reasons.append("Add a device to the cart")
    if (
        promo["per"] == "device"
        and promo["max_units"]
        and _qualifying_devices(promo, facts["devices"]) > int(promo["max_units"])
    ):
        reasons.append(f"At most {int(promo['max_units'])} devices can receive this offer")
    if promo["requires_addon_kind"] and promo["requires_addon_kind"] not in facts["addon_kinds"]:
        reasons.append(f"Add a {str(promo['requires_addon_kind']).replace('_', ' ')} add-on to the cart")
    if promo["min_accessories"] and facts["accessories"] < int(promo["min_accessories"]):
        reasons.append(
            f"Add {int(promo['min_accessories'])} or more accessories (the cart has {facts['accessories']})"
        )
    needs_plan = promo["plan_families"] or promo["plan_variants"] or promo["min_plan_cents"] or promo["discount_plan_only"]
    if needs_plan and not any(_plan_matches(promo, plan) for plan in facts["plans"]):
        reasons.append(_plan_reason(promo))
    return reasons


def unit_value_cents(promo: dict) -> int:
    months = (promo["payout_months"] or ONGOING_HORIZON_MONTHS) if promo["kind"] == "bill_credit" else 1
    return int(promo["value_cents"]) * int(months)


def savings_cents(promo: dict, facts: dict) -> int:
    if promo["kind"] == "accessory_discount":
        return 0
    cap = int(promo["max_units"]) if promo["max_units"] else 99
    if promo["per"] == "device":
        units = min(_qualifying_devices(promo, facts["devices"]), cap)
    elif promo["per"] == "line":
        units = min(facts["new_lines"] or facts["lines"], cap)
    else:
        units = 1
    return unit_value_cents(promo) * units


def empty_cart_facts(account: dict, plans: list[dict], n_lines: int, oldest_age: int | None) -> dict:
    return {
        "account": account,
        "lines": n_lines,
        "new_lines": 0,
        "port_in": False,
        "devices": (),
        "tradein": False,
        "addon_kinds": frozenset(),
        "accessories": 0,
        "plans": plans,
        "oldest_device_age": oldest_age,
        "tradein_ages": (),
        "support_contacts": int(account["support_90d"]),
    }


def upgrade_cart_facts(account: dict, plans: list[dict], n_lines: int, oldest_age: int | None, line_age: int, device_sku: str) -> dict:
    return {
        "account": account,
        "lines": n_lines,
        "new_lines": 0,
        "port_in": False,
        "devices": (device_sku,),
        "tradein": True,
        "addon_kinds": frozenset(),
        "accessories": 0,
        "plans": plans,
        "oldest_device_age": oldest_age,
        "tradein_ages": (int(line_age),),
        "support_contacts": int(account["support_90d"]),
    }


def is_device_promo(promo: dict) -> bool:
    return promo["kind"] in {"device_credit", "prepaid_card"} and (
        promo["per"] == "device" or promo["requires_device"] or promo["requires_tradein"]
    )


def network_mismatch(account: dict) -> bool:
    """A bill credit does not fix coverage. Used only to down-weight CARE, not to invent an offer."""
    topic = account.get("top_topic")
    return (
        topic == "network"
        and float(account["bill_increase_pct"]) <= 0.05
        and int(account["port_out_inquiry"]) == 0
    )


def offer_fit(promo: dict, account: dict) -> tuple[float, str]:
    sku = promo["sku"]
    if sku == "PROMO-STUB-CARE-CREDIT":
        if network_mismatch(account):
            return (
                0.02,
                "Recent contacts are about the network and the bill is stable. "
                "The care credit is eligible, but it does not fix coverage.",
            )
        if float(account["avg_sentiment"]) < 0 and int(account["support_90d"]) >= 3:
            return (1.0, "Matches frustrated support contacts in the last 90 days.")
        if float(account["avg_sentiment"]) > 0.2:
            return (
                0.05,
                "The contact count qualifies, but average support sentiment is positive, "
                "so a goodwill credit is a weak match.",
            )
        return (0.45, "Eligible on recent support contacts.")
    if sku == "PROMO-STUB-LOYALTY-CREDIT":
        if network_mismatch(account):
            return (
                0.02,
                "Recent contacts are network issues and the bill is stable. "
                "A loyalty credit does not fix coverage, so it does not get credit for competitor research alone.",
            )
        drivers = []
        if float(account["bill_increase_pct"]) > 0.05:
            drivers.append("the bill increase")
        if int(account["port_out_inquiry"]):
            drivers.append("the port-out inquiry")
        if float(account["competitor_research"]) >= 0.6:
            drivers.append("competitor research")
        if drivers:
            return (0.75, "Matches " + " and ".join(drivers) + ".")
        if float(account["model_p"]) > 0.2:
            return (0.35, "Tenure qualifies and model risk is elevated, without a sharper bill or switching driver.")
        return (0.08, "Tenure qualifies, and there is no strong leave signal to spend against.")
    if sku == "PROMO-STUB-STUDENT":
        if float(account["model_p"]) >= 0.25:
            return (0.4, "The student credit is eligible and model risk is elevated.")
        return (0.0, "The student credit is an entitlement. It is not a response to a leave signal.")
    return (0.2, "Eligible promotion.")


def _money(cents: float) -> str:
    return f"${cents / 100:,.2f}"


def choose_outreach(account: dict, promos: list[dict], facts: dict, device_names: dict[str, str]) -> dict:
    """Pick one empty-cart promotion, or do nothing when nothing beats a score of zero."""
    considered = []
    clv = int(account["last_bill_cents"] or 0) * FINANCING_TERM_MONTHS
    risk = float(account["model_p"])
    for promo in promos:
        if promo["sku"] not in RETENTION_OUTREACH:
            continue
        reasons = eligibility_reasons(promo, facts, device_names)
        eligible = not reasons
        fit, fit_reason = offer_fit(promo, account) if eligible else (0.0, "")
        if eligible and risk < RISK_FLOOR:
            fit = 0.0
            fit_reason = (
                f"Model risk is {risk:.0%}, under the {RISK_FLOOR:.0%} floor around the sandbox base rate, "
                "so this credit is not spent."
            )
        cost = savings_cents(promo, facts) if eligible else 0
        gross = risk * fit * POLICY_ACCEPTANCE * clv if eligible else 0.0
        net = gross - cost - (ANNOYANCE_CENTS if eligible else 0)
        considered.append(
            {
                "sku": promo["sku"],
                "name": promo["name"],
                "source": promo["source"],
                "eligible": eligible,
                "reasons": reasons,
                "fit": fit,
                "fit_reason": fit_reason,
                "cost_cents": int(cost),
                "net_cents": int(round(net)),
                "value_cents": int(promo["value_cents"]),
                "kind": promo["kind"],
                "payout_months": promo["payout_months"],
            }
        )
    eligible_ones = [item for item in considered if item["eligible"]]
    winner = max(eligible_ones, key=lambda item: item["net_cents"], default=None)
    if winner is None or winner["net_cents"] <= 0:
        why_bits = ["No eligible offer scores above doing nothing."]
        for item in considered:
            if not item["eligible"]:
                why_bits.append(f"{item['name']} is not eligible: {'; '.join(item['reasons'])}.")
            else:
                why_bits.append(
                    f"{item['name']} is eligible but scores {_money(item['net_cents'])} "
                    f"after the offer cost and a {_money(ANNOYANCE_CENTS)} contact cost. {item['fit_reason']}"
                )
        return {
            "choice": "do_nothing",
            "sku": None,
            "name": "Do nothing",
            "why": " ".join(why_bits),
            "net_cents": 0,
            "cost_cents": 0,
            "fit": 0.0,
            "considered": considered,
            "formula": _formula(risk, clv),
        }
    return {
        "choice": "offer",
        "sku": winner["sku"],
        "name": winner["name"],
        "source": winner["source"],
        "why": (
            f"{winner['name']} is eligible and has the best score ({_money(winner['net_cents'])}). "
            f"{winner['fit_reason']} "
            f"Offer cost counted here is {_money(winner['cost_cents'])}."
        ),
        "net_cents": winner["net_cents"],
        "cost_cents": winner["cost_cents"],
        "fit": winner["fit"],
        "fit_reason": winner["fit_reason"],
        "value_cents": winner["value_cents"],
        "kind": winner["kind"],
        "payout_months": winner["payout_months"],
        "considered": considered,
        "formula": _formula(risk, clv),
    }


def _formula(risk: float, clv_cents: int) -> str:
    return (
        f"Score = model risk ({risk:.0%}) × fit × {POLICY_ACCEPTANCE:.0%} acceptance "
        f"× {_money(clv_cents)} value over {FINANCING_TERM_MONTHS} months "
        f"− offer cost − {_money(ANNOYANCE_CENTS)} contact cost. "
        f"Risk under {RISK_FLOOR:.0%} does not get a credit. "
        "The acceptance rate is an assumption used to rank offers. It is not a measured response."
    )


def best_device_promo(
    account: dict,
    promos: list[dict],
    plans: list[dict],
    n_lines: int,
    oldest_age: int | None,
    line_age: int,
    candidates: list[dict],
    device_names: dict[str, str],
) -> dict | None:
    """Highest-savings device promotion on a one-phone upgrade cart. Others are not stacked."""
    best: dict | None = None
    for device in candidates:
        facts = upgrade_cart_facts(account, plans, n_lines, oldest_age, line_age, device["sku"])
        for promo in promos:
            if not is_device_promo(promo):
                continue
            reasons = eligibility_reasons(promo, facts, device_names)
            if reasons:
                continue
            savings = savings_cents(promo, facts)
            better = best is None or savings > best["savings_cents"]
            cheaper_tie = (
                best is not None
                and savings == best["savings_cents"]
                and int(device["msrp_cents"]) < best["device_msrp_cents"]
            )
            if better or cheaper_tie:
                best = {
                    "sku": promo["sku"],
                    "name": promo["name"],
                    "source": promo["source"],
                    "savings_cents": int(savings),
                    "device_sku": device["sku"],
                    "device_name": device["name"],
                    "device_msrp_cents": int(device["msrp_cents"]),
                }
    return best
