"""One upsell per customer. Guardrails first, then the config order, first match wins."""

from __future__ import annotations

from harness.upsell.config import (
    AT_RISK_BANDS,
    BILL_JUMP_PCT,
    DO_NOTHING_ACCOUNTS,
    LOW_CREDIT_TIER,
    RULES,
    SATISFIED_TENURE_MONTHS,
)

_BY_ID = {rule["id"]: rule for rule in RULES}


def decide(ctx: dict, *, include_synthetic: bool = False) -> dict:
    account = ctx["account"]
    if account["account_id"] in DO_NOTHING_ACCOUNTS:
        return _pack(
            _BY_ID["satisfied"],
            action="DO NOTHING",
            trigger="Happy frequent caller",
            offer_name="None",
            why="Happy-caller trap: this account stays do nothing.",
            rejected="Resolved support contacts are not an unresolved issue, and no offer is attached.",
            offer_line="No message: nothing would help them right now.",
            send=False,
        )
    if int(ctx.get("unresolved_90d") or 0) >= 1 or ctx.get("risk_band") in AT_RISK_BANDS:
        return _pack(
            None,
            action="RETENTION PLAYBOOK",
            trigger="At risk or unresolved support",
            offer_name="None",
            why="At-risk or unresolved support goes to the retention playbook before any upsell.",
            rejected="An upsell was not considered.",
            offer_line="No upsell. The retention playbook handles this account.",
            source="support" if int(ctx.get("unresolved_90d") or 0) >= 1 else "model_p",
            tier="guardrail",
            send=False,
        )
    if _unaffordable(ctx):
        return _pack(
            None,
            action="NO UPSELL",
            trigger="Negative affordability",
            offer_name="None",
            why="A bill jump, a late payment, or a low credit tier blocks an upsell.",
            rejected="Plan and device offers were not considered.",
            offer_line="No upsell.",
            source="billing",
            tier="guardrail",
            send=False,
        )
    for rule in RULES:
        if rule["tier"] == "tier2" and not include_synthetic:
            continue
        if rule["tier"] == "tier2" and ctx.get("synthetic_event") != rule["id"]:
            continue
        if rule["id"] == "satisfied" and include_synthetic and ctx.get("synthetic_event"):
            continue
        hit = _CHECKS[rule["id"]](ctx)
        if hit is None:
            continue
        if account["account_id"] in ctx.get("upgrade_blocked_ids", ()) and hit.get("upgrade_outcome") == "now":
            hit = _keep(hit)
        return _pack(rule, **hit)
    return _pack(
        None,
        action="NO UPSELL",
        trigger="No trigger",
        offer_name="None",
        why="No real trigger matched, and there is no synthetic signal on this view.",
        rejected="Nothing later was reached.",
        offer_line="No upsell.",
        tier="none",
        send=False,
    )


def _unaffordable(ctx: dict) -> bool:
    account = ctx["account"]
    if float(account.get("bill_increase_pct") or 0) > BILL_JUMP_PCT:
        return True
    if account.get("credit_tier") == LOW_CREDIT_TIER:
        return True
    return int(ctx.get("late_payments") or 0) > 0


def _near_cap(ctx: dict) -> dict | None:
    if int(ctx.get("near_cap_months") or 0) < 2:
        return None
    plan = ctx["candidates"].get("next_plan")
    if not plan:
        return None
    return _plan_hit(
        trigger=f"Near or over the cap in {int(ctx['near_cap_months'])} of the last 3 months",
        plan=plan,
        why="The next catalog tier covers the cap. The monthly difference is the catalog price.",
        rejected="Upgrade timing was not reached. A cap this wide is a plan problem, and a device was not added.",
        offer_line=f"Next catalog plan {plan['name']}. Monthly difference {plan['diff_cents']} cents.",
    )


def _usage_growth(ctx: dict) -> dict | None:
    if not ctx.get("usage_growth"):
        return None
    plan = ctx["candidates"].get("better_value")
    detail = ctx.get("growth_detail") or "usage"
    if not plan:
        return {
            "action": "DO NOTHING",
            "trigger": f"Usage growth ({detail}) with no cap issue",
            "offer_name": "None",
            "why": "Usage grew, and no real plan costs the same or less while giving more.",
            "rejected": "A device upgrade was not offered. Nothing cheaper in the catalog adds value.",
            "offer_line": "No message: nothing would help them right now.",
            "send": False,
            "diff_cents": 0,
        }
    return _plan_hit(
        trigger=f"Usage growth ({detail}) with no cap issue",
        plan=plan,
        why="A real plan costs the same or less and adds data or hotspot.",
        rejected="A step-up that costs more was not used. A device was not added.",
        offer_line=f"Catalog plan {plan['name']} costs the same or less. Monthly difference {plan['diff_cents']} cents.",
        action="PLAN FIT",
    )


def _paid_off(ctx: dict) -> dict | None:
    if not ctx.get("paid_off_eligible"):
        return None
    moment = ctx.get("moment") or {}
    outcome = moment.get("when") if moment else "keep"
    if outcome not in {"now", "wait"}:
        outcome = "keep"
    if ctx["account"]["account_id"] in ctx.get("upgrade_blocked_ids", ()) and outcome == "now":
        outcome = "keep"
    promo = moment.get("promo") if outcome == "now" and isinstance(moment.get("promo"), dict) else None
    if outcome == "keep":
        line = "Keep the phone. No upgrade push."
        name = "Keep"
    elif outcome == "wait":
        line = moment.get("headline") or "Wait. Upgrade eligibility follows the 12-month ownership rule."
        name = "Wait"
    else:
        name = (promo or {}).get("name") or moment.get("device_name") or "Upgrade now"
        line = f"Upgrade now. {name}."
    return {
        "trigger": "Phone paid off and upgrade-eligible",
        "offer_name": name,
        "offer_sku": (promo or {}).get("sku") if isinstance(promo, dict) else None,
        "promo_skus": [(promo or {}).get("sku")] if isinstance(promo, dict) and promo.get("sku") else [],
        "promo_savings_cents": (promo or {}).get("savings_cents") if isinstance(promo, dict) else None,
        "diff_cents": 0,
        "upgrade_outcome": outcome,
        "why": "Not Yet timing is upgrade now, wait, or keep. Keep is a valid answer. At most one device promo.",
        "rejected": "A second device promo is not stacked. A plan change is not added on the same nudge.",
        "offer_line": line,
        "assumption_note": (moment or {}).get("assumption") or "",
        "send": True,
    }


def _student(ctx: dict) -> dict | None:
    if not ctx.get("student_graduating"):
        return None
    plan = ctx["candidates"].get("standard_plan")
    if not plan:
        return None
    same = plan["diff_cents"] == 0
    line = (
        f"You are already on the closest standard plan, {plan['name']}. This is not an upsell."
        if same
        else f"Move to {plan['name']} before the discount ends, so the bill is not a surprise. Monthly difference {plan['diff_cents']} cents."
    )
    return _plan_hit(
        trigger="Student or discount plan",
        plan=plan,
        why="This moves a student or discount plan to the closest standard catalog plan. It is framed as avoiding a surprise bill, not as an upsell.",
        rejected="A device upgrade was not added. A premium tier was not added on top.",
        offer_line=line,
        action="AVOID SURPRISE BILL",
        send=not same,
    )


def _kid(ctx: dict) -> dict | None:
    kid = ctx["candidates"].get("kid")
    if not kid:
        return None
    promo = kid.get("promo")
    plan = kid.get("plan")
    controls = (
        "Parental controls are in the add-ons catalog."
        if ctx["candidates"].get("parental_controls")
        else "Parental controls are not in the add-ons catalog, so they were not added."
    )
    if promo:
        return {
            "trigger": "Kid turning 13",
            "offer_name": promo["name"],
            "offer_sku": promo["sku"],
            "promo_skus": [promo["sku"]],
            "promo_savings_cents": promo["savings_cents"],
            "diff_cents": 0,
            "why": f"Add a line on {kid['device_name']} with one eligible line promo. {controls}",
            "rejected": f"A second promo was not stacked. {controls}",
            "offer_line": f"Add a line. Device {kid['device_name']}. Promo {promo['name']}.",
            "source": "synthetic signal",
            "send": True,
        }
    if not plan:
        return None
    return _plan_hit(
        trigger="Kid turning 13",
        plan=plan,
        why=f"No kids or family line promo was eligible. The cheapest real plan for the extra line is {plan['name']}. {controls}",
        rejected=f"A device promo was not attached. {controls}",
        offer_line=f"Add a line on {plan['name']}. Monthly difference {plan['diff_cents']} cents.",
        source="synthetic signal",
    )


def _promotion(ctx: dict) -> dict | None:
    device = ctx["candidates"].get("device")
    plan = ctx["candidates"].get("premium_plan")
    if device and device.get("outcome") == "now":
        promo = device.get("promo") if isinstance(device.get("promo"), dict) else None
        return {
            "trigger": "Promotion or new job",
            "offer_name": (promo or {}).get("name") or device.get("name") or "Upgrade now",
            "offer_sku": (promo or {}).get("sku") if promo else None,
            "promo_skus": [promo["sku"]] if promo and promo.get("sku") else [],
            "promo_savings_cents": (promo or {}).get("savings_cents") if promo else None,
            "diff_cents": 0,
            "upgrade_outcome": "now",
            "why": "The Not Yet timing says upgrade now, so this nudge is the device, not a plan as well.",
            "rejected": "The premium plan was not included. One nudge does not carry both a plan and a device.",
            "offer_line": f"Upgrade now. {device.get('name') or 'A catalog device'}.",
            "source": "synthetic signal",
            "send": True,
        }
    if plan:
        return _plan_hit(
            trigger="Promotion or new job",
            plan=plan,
            why="The Not Yet timing does not say upgrade now, so the real catalog step-up is the one offer.",
            rejected="A device was not added on the same nudge.",
            offer_line=f"Premium tier {plan['name']}. Monthly difference {plan['diff_cents']} cents.",
            source="synthetic signal",
        )
    return None


def _moving(ctx: dict) -> dict | None:
    if ctx["candidates"].get("has_home_internet") or not ctx["candidates"].get("home_internet"):
        return {
            "trigger": "Moving",
            "action": "COVERAGE CHECK",
            "offer_name": "Address update",
            "diff_cents": 0,
            "why": "Home Internet is already on the account, or it is not in the catalog. This is a coverage check and an address update, not a sale.",
            "rejected": "No home-internet add-on was attached.",
            "offer_line": "Check coverage at the new address. No sale on this message.",
            "source": "synthetic signal",
            "send": True,
        }
    home = ctx["candidates"]["home_internet"]
    promo = home.get("promo") if isinstance(home.get("promo"), dict) else None
    return {
        "trigger": "Moving",
        "action": "COVERAGE CHECK",
        "offer_name": home["name"],
        "offer_sku": home["sku"],
        "promo_skus": [promo["sku"]] if promo else [],
        "promo_savings_cents": promo["savings_cents"] if promo else None,
        "diff_cents": home["monthly_cents"],
        "why": "Home Internet is in the add-on catalog, so the coverage check can include it. One promo at most.",
        "rejected": "A phone upgrade was not added.",
        "offer_line": f"Check coverage, and Home Internet {home['name']} is {home['monthly_cents']} cents a month.",
        "source": "synthetic signal",
        "send": True,
    }


def _merge(ctx: dict) -> dict | None:
    plan = ctx["candidates"].get("merge_plan")
    if not plan:
        return None
    return _plan_hit(
        trigger="New partner or household merge",
        plan=plan,
        why=(
            f"Combined catalog bill for {plan.get('added_lines')} lines is {plan['monthly_cents']} cents. "
            f"The current catalog bill is {plan.get('current_monthly_cents')} cents."
        ),
        rejected="A device promo was not stacked on the plan comparison.",
        offer_line=(
            f"Compare {plan['name']} at {plan['monthly_cents']} cents with the current "
            f"{plan.get('current_monthly_cents')} cents. Monthly difference {plan['diff_cents']} cents."
        ),
        source="synthetic signal",
        action="HOUSEHOLD MERGE",
    )


def _retirement(ctx: dict) -> dict | None:
    plan = ctx["candidates"].get("cheaper_plan")
    if not plan:
        return None
    return _plan_hit(
        trigger="Retirement or income down",
        plan=plan,
        why="A cheaper real plan is a valid offer. A downgrade can be an upgrade of trust.",
        rejected="A premium tier and a device were not offered.",
        offer_line=f"Cheaper catalog plan {plan['name']}. Monthly difference {plan['diff_cents']} cents.",
        source="synthetic signal",
        action="CHEAPER PLAN",
    )


def _satisfied(ctx: dict) -> dict | None:
    account = ctx["account"]
    if int(account.get("tenure_months") or 0) < SATISFIED_TENURE_MONTHS:
        return None
    if int(ctx.get("unresolved_90d") or 0) != 0:
        return None
    if float(account.get("bill_increase_pct") or 0) > BILL_JUMP_PCT:
        return None
    return {
        "action": "DO NOTHING",
        "trigger": "Highly satisfied with no trigger",
        "offer_name": "None",
        "why": "Satisfaction alone is not a reason to sell.",
        "rejected": "No plan or device was next.",
        "offer_line": "No message: nothing would help them right now.",
        "diff_cents": 0,
        "send": False,
    }


def _plan_hit(*, trigger, plan, why, rejected, offer_line, action=None, source=None, send=True) -> dict:
    hit = {
        "trigger": trigger,
        "offer_name": plan["name"],
        "offer_sku": plan["sku"],
        "diff_cents": int(plan["diff_cents"]),
        "why": why,
        "rejected": rejected,
        "offer_line": offer_line,
        "send": send,
    }
    if action:
        hit["action"] = action
    if source:
        hit["source"] = source
    return hit


def _keep(hit: dict) -> dict:
    hit = dict(hit)
    hit["upgrade_outcome"] = "keep"
    hit["offer_name"] = "Keep"
    hit["offer_sku"] = None
    hit["promo_skus"] = []
    hit["promo_savings_cents"] = None
    hit["offer_line"] = "Keep the phone. No upgrade push."
    hit["rejected"] = "Upgrade push blocked for persona 07 or 31."
    hit["why"] = "This persona never gets an upgrade push. Keep is the outcome."
    return hit


def _pack(rule: dict | None, **hit) -> dict:
    promo_skus = [sku for sku in (hit.get("promo_skus") or []) if sku][:1]
    offer_line = hit.get("offer_line") or "No upsell."
    tier = hit.get("tier") or (rule["tier"] if rule else "none")
    source = hit.get("source") or (rule["source"] if rule else "")
    if tier == "tier2":
        source = "synthetic signal"
    templates = _TEMPLATES.get((rule or {}).get("id") or hit.get("action"), _TEMPLATES["none"])
    if hit.get("send") is False:
        templates = _TEMPLATES["none"]
    return {
        "rule_id": (rule or {}).get("id") or hit.get("action") or "none",
        "tier": tier,
        "action": hit.get("action") or (rule["action"] if rule else "NO UPSELL"),
        "trigger": hit.get("trigger") or (rule["when"] if rule else "No trigger"),
        "offer_name": hit.get("offer_name") or "None",
        "offer_sku": hit.get("offer_sku"),
        "diff_cents": hit.get("diff_cents"),
        "promo_skus": promo_skus,
        "promo_savings_cents": hit.get("promo_savings_cents"),
        "stacked_promos": False,
        "data_source": source,
        "why": hit.get("why") or "",
        "rejected": hit.get("rejected") or "",
        "upgrade_outcome": hit.get("upgrade_outcome"),
        "assumption_note": hit.get("assumption_note") or "",
        "badge": "synthetic, consented, illustrative" if tier == "tier2" else "",
        "send": bool(hit.get("send")),
        "message_en": templates["en"].format(offer_line=offer_line),
        "message_es": templates["es"].format(offer_line=offer_line),
    }


_TEMPLATES = {
    "near_cap": {
        "en": "Your data has been tight against the cap. {offer_line}",
        "es": "Tus datos han estado cerca del límite. {offer_line}",
    },
    "usage_growth": {
        "en": "Your recent usage is higher than the earlier months. {offer_line}",
        "es": "Tu uso reciente es más alto que los meses anteriores. {offer_line}",
    },
    "paid_off": {
        "en": "{offer_line}",
        "es": "{offer_line}",
    },
    "student_graduating": {
        "en": "This is so the bill is not a surprise. It is not an upsell. {offer_line}",
        "es": "Esto es para que la factura no sea una sorpresa. No es una venta adicional. {offer_line}",
    },
    "kid_turning_13": {
        "en": "A line for a kid turning 13. {offer_line}",
        "es": "Una línea para un hijo que cumple 13. {offer_line}",
    },
    "promotion_or_new_job": {
        "en": "Congratulations on the new role. {offer_line}",
        "es": "Felicidades por el nuevo puesto. {offer_line}",
    },
    "moving": {
        "en": "You are moving. {offer_line}",
        "es": "Te estás mudando. {offer_line}",
    },
    "household_merge": {
        "en": "Two households on one account. {offer_line}",
        "es": "Dos hogares en una cuenta. {offer_line}",
    },
    "retirement_or_income_down": {
        "en": "A smaller plan is available. {offer_line}",
        "es": "Hay un plan más pequeño. {offer_line}",
    },
    "none": {
        "en": "No message: nothing would help them right now.",
        "es": "Sin mensaje: ahora mismo nada les ayudaría.",
    },
}

_CHECKS = {
    "near_cap": _near_cap,
    "usage_growth": _usage_growth,
    "paid_off": _paid_off,
    "student_graduating": _student,
    "kid_turning_13": _kid,
    "promotion_or_new_job": _promotion,
    "moving": _moving,
    "household_merge": _merge,
    "retirement_or_income_down": _retirement,
    "satisfied": _satisfied,
}
