"""Real catalog picks for one account. Prices come from the sandbox plans and add-ons.

Promo savings use harness.console_offers. At most one promo is attached here.
Parental controls are offered only when that add-on kind exists.
"""

from __future__ import annotations

import pandas as pd

from harness import enrichment
from harness.console_offers import eligibility_reasons, empty_cart_facts, savings_cents
from harness.upsell.config import UPGRADE_MIN_AGE_MONTHS, UPGRADE_PUSH_BLOCKED

STANDARD_SKU = {
    "essentials": "TMO-STUB-PLAN-ESSENTIALS",
    "experience_more": "TMO-STUB-PLAN-MORE",
    "experience_beyond": "TMO-STUB-PLAN-BEYOND",
}


def load_catalog(path=None) -> dict:
    plans = enrichment.load_plans()
    from harness.config import db_path
    from harness.data import connect

    conn = connect(path or db_path())
    try:
        addons = [dict(row) for row in conn.execute("SELECT sku, name, kind, monthly_cents, description FROM addons")]
        devices = [
            dict(row)
            for row in conn.execute(
                """
                SELECT sku, name, tier, msrp_cents FROM devices
                WHERE status = 'current' AND tier = 'value'
                ORDER BY msrp_cents, name
                """
            )
        ]
    finally:
        conn.close()
    plan_rows = _plan_rows(plans)
    return {
        "plans": plans,
        "addons": addons,
        "devices": devices,
        "plan_rows": plan_rows,
        "plan_by_sku": {row["sku"]: row for row in plan_rows},
    }


def _plan_rows(plans: pd.DataFrame) -> list[dict]:
    """One pass over the catalog. Later lookups are dict reads, not plan-table scans."""
    rows = []
    for sku, plan in plans.iterrows():
        parts = [int(value) for value in str(plan["line_prices"]).split(",") if value]
        extra_raw = plan["extra_line_cents"]
        extra = int(extra_raw) if pd.notna(extra_raw) else parts[-1]
        prices = {n: int(sum(parts[:n]) + max(0, n - len(parts)) * extra) for n in range(1, 13)}
        eligibility = plan["eligibility"]
        rows.append(
            {
                "sku": sku,
                "name": str(plan["name"]),
                "family": str(plan["family"]),
                "tier": "" if pd.isna(plan["tier"]) else str(plan["tier"]),
                "eligibility": None if pd.isna(eligibility) or not eligibility else eligibility,
                "min_lines": int(plan["min_lines"]) if pd.notna(plan["min_lines"]) else 1,
                "max_lines": int(plan["max_lines"]) if pd.notna(plan["max_lines"]) else None,
                "data_cap_gb": plan["data_cap_gb"],
                "hotspot_high_speed_gb": plan["hotspot_high_speed_gb"] if "hotspot_high_speed_gb" in plan.index else None,
                "prices": prices,
            }
        )
    return rows


def monthly_cents(plans: pd.DataFrame, sku: str, n_lines: int) -> int | None:
    if sku not in plans.index:
        return None
    cap = plans.loc[sku, "max_lines"]
    count = n_lines
    if pd.notna(cap):
        count = min(n_lines, int(cap))
    if count < 1:
        return None
    return int(enrichment.plan_price(plans, sku, count))


def _allowed(plan: pd.Series, account: dict, n_lines: int) -> bool:
    needed = plan.get("eligibility")
    if pd.notna(needed) and needed and account.get("discount_group") != needed:
        return False
    minimum = int(plan["min_lines"]) if pd.notna(plan.get("min_lines")) else 1
    maximum = int(plan["max_lines"]) if pd.notna(plan.get("max_lines")) else None
    if n_lines < minimum:
        return False
    if maximum is not None and n_lines > maximum:
        return False
    return True


def _offer(name: str, sku: str, monthly: int, current: int) -> dict:
    return {
        "name": name,
        "sku": sku,
        "monthly_cents": monthly,
        "diff_cents": monthly - current,
    }


def prepare(account: dict, lines: list[dict], catalog: dict, promos: list[dict], moment: dict | None) -> dict:
    plans: pd.DataFrame = catalog["plans"]
    rows = catalog.get("plan_rows") or _plan_rows(plans)
    by_sku = catalog.get("plan_by_sku") or {row["sku"]: row for row in rows}
    n_lines = max(len(lines), 1)
    current_sku = lines[0]["plan_sku"] if lines else None
    current_row = by_sku.get(current_sku)
    current = _priced(current_row, n_lines) if current_row is not None else None
    blocked = account["account_id"] in UPGRADE_PUSH_BLOCKED
    paid_off = any(
        (not line.get("byod")) and line.get("device_sku") and int(line.get("financing_balance_cents") or 0) == 0
        for line in lines
    )
    eligible_age = any(
        line.get("device_sku") and line.get("age_months") is not None and int(line["age_months"]) >= UPGRADE_MIN_AGE_MONTHS
        for line in lines
    )
    next_sku = enrichment.NEXT_PLAN.get(current_sku)
    next_row = by_sku.get(next_sku)
    next_plan = None
    if next_row is not None and current is not None and _row_allowed(next_row, account, n_lines):
        price = _priced(next_row, n_lines)
        if price is not None:
            next_plan = _offer(next_row["name"], next_sku, price, current)

    better = _better_value(rows, account, n_lines, current, current_row)
    standard = _standard_plan(by_sku, account, lines, n_lines, current, current_row)
    cheaper = _cheaper(rows, account, n_lines, current)
    merge = _merge(rows, account, n_lines, current)
    kid = _kid(account, lines, rows, catalog, promos, n_lines)
    device = _device(account, moment, blocked)
    home = _home_internet(account, catalog, promos, lines, n_lines)
    student = (account.get("discount_group") == "student" or account.get("segment") == "student") and standard is not None
    return {
        "current_monthly_cents": current,
        "next_plan": next_plan,
        "better_value": better,
        "standard_plan": standard,
        "student_graduating": bool(student),
        "cheaper_plan": cheaper,
        "merge_plan": merge,
        "kid": kid,
        "device": device,
        "premium_plan": next_plan if next_plan and next_row is not None and next_row["tier"] == "premium" else None,
        "home_internet": home,
        "has_home_internet": int(account.get("has_home_internet") or 0) == 1,
        "paid_off_eligible": bool(paid_off and eligible_age),
        "parental_controls": any("parent" in str(addon.get("kind", "")).lower() or "parent" in str(addon.get("name", "")).lower() for addon in catalog["addons"]),
        "upgrade_blocked": blocked,
    }


def _row_allowed(row: dict, account: dict, n_lines: int) -> bool:
    needed = row["eligibility"]
    if needed and account.get("discount_group") != needed:
        return False
    if n_lines < row["min_lines"]:
        return False
    if row["max_lines"] is not None and n_lines > row["max_lines"]:
        return False
    return True


def _priced(row: dict | None, n_lines: int) -> int | None:
    if row is None:
        return None
    count = n_lines
    if row["max_lines"] is not None:
        count = min(n_lines, row["max_lines"])
    if count < 1:
        return None
    return row["prices"].get(count)


def _better_value(rows, account, n_lines, current, current_row) -> dict | None:
    if current is None or current_row is None:
        return None
    current_cap = current_row["data_cap_gb"]
    current_hotspot = current_row["hotspot_high_speed_gb"]
    best = None
    for plan in rows:
        if plan["sku"] == current_row["sku"]:
            continue
        if not _row_allowed(plan, account, n_lines):
            continue
        price = _priced(plan, n_lines)
        if price is None or price > current:
            continue
        cap = plan["data_cap_gb"]
        hotspot = plan["hotspot_high_speed_gb"]
        more = False
        if pd.isna(current_cap) is False and (pd.isna(cap) or (pd.notna(cap) and float(cap) > float(current_cap))):
            more = True
        if pd.notna(hotspot) and (pd.isna(current_hotspot) or float(hotspot) > float(current_hotspot)):
            more = True
        if not more:
            continue
        rank = (0 if pd.isna(cap) else 1, price)
        if best is None or rank < best[0]:
            best = (rank, _offer(plan["name"], plan["sku"], price, current))
    return None if best is None else best[1]


def _standard_plan(by_sku, account, lines, n_lines, current, current_row) -> dict | None:
    if current is None or current_row is None or not lines:
        return None
    sku = STANDARD_SKU.get(current_row["family"])
    plan = by_sku.get(sku)
    if plan is None or not _row_allowed(plan, account, n_lines):
        return None
    price = _priced(plan, n_lines)
    if price is None:
        return None
    return _offer(plan["name"], sku, price, current)


def _cheaper(rows, account, n_lines, current) -> dict | None:
    if current is None:
        return None
    best = None
    for plan in rows:
        if not _row_allowed(plan, account, n_lines):
            continue
        price = _priced(plan, n_lines)
        if price is None or price >= current:
            continue
        if best is None or price < best["monthly_cents"]:
            best = _offer(plan["name"], plan["sku"], price, current)
    return best


def _merge(rows, account, n_lines, current) -> dict | None:
    if current is None:
        return None
    extra = n_lines + 1
    best = None
    for plan in rows:
        if not _row_allowed(plan, account, extra):
            continue
        price = _priced(plan, extra)
        if price is None:
            continue
        if best is None or price < best["monthly_cents"]:
            best = _offer(plan["name"], plan["sku"], price, current)
    if best is None:
        return None
    best["current_monthly_cents"] = current
    best["added_lines"] = extra
    return best


def _plans_for_facts(lines: list[dict]) -> list[dict]:
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


def _one_promo(account, lines, promos, *, new_lines: int, devices: tuple[str, ...], addon_kinds: frozenset[str], names: dict) -> dict | None:
    if not lines:
        return None
    ages = [int(line["age_months"]) for line in lines if line.get("age_months") is not None]
    oldest = max(ages) if ages else None
    facts = empty_cart_facts(account, _plans_for_facts(lines), len(lines) + new_lines, oldest)
    facts = dict(facts)
    facts["new_lines"] = new_lines
    facts["devices"] = devices
    facts["addon_kinds"] = addon_kinds
    found = []
    for promo in promos:
        if promo.get("requires_port_in"):
            continue
        reasons = eligibility_reasons(promo, facts, names)
        if reasons:
            continue
        found.append(promo)
    if not found:
        return None
    winner = max(found, key=lambda promo: savings_cents(promo, facts))
    return {
        "sku": winner["sku"],
        "name": winner["name"],
        "savings_cents": int(savings_cents(winner, facts)),
    }


def _kid(account, lines, plans, catalog, promos, n_lines) -> dict | None:
    devices = catalog["devices"]
    if not devices:
        return None
    device = devices[0]
    names = {item["sku"]: item["name"] for item in devices}
    promo = _one_promo(
        account,
        lines,
        [promo for promo in promos if promo.get("requires_new_line") or promo.get("kind") == "line_credit"],
        new_lines=1,
        devices=(device["sku"],),
        addon_kinds=frozenset(),
        names=names,
    )
    plan = _cheapest_extra_line(plans, account, n_lines)
    return {
        "device_name": device["name"],
        "device_sku": device["sku"],
        "promo": promo,
        "plan": plan,
    }


def _cheapest_extra_line(plans, account, n_lines) -> dict | None:
    extra = n_lines + 1
    best = None
    for plan in plans:
        if not _row_allowed(plan, account, extra):
            continue
        price = _priced(plan, extra)
        if price is None:
            continue
        if best is None or price < best["monthly_cents"]:
            best = _offer(plan["name"], plan["sku"], price, price)
            best["diff_cents"] = price
    return best


def _device(account, moment, blocked: bool) -> dict | None:
    if not moment or moment.get("when") != "now":
        return None
    promo = moment.get("promo") if isinstance(moment.get("promo"), dict) else None
    if blocked:
        return {"outcome": "keep", "headline": "Keep the phone. No upgrade push.", "promo": None, "name": moment.get("device_name")}
    return {
        "outcome": "now",
        "headline": moment.get("headline") or "Upgrade now.",
        "promo": promo,
        "name": moment.get("device_name") or "Upgrade now",
    }


def _home_internet(account, catalog, promos, lines, n_lines) -> dict | None:
    choices = [addon for addon in catalog["addons"] if addon.get("kind") == "home_internet"]
    if not choices:
        return None
    addon = min(choices, key=lambda item: int(item["monthly_cents"] or 0))
    names = {}
    promo = _one_promo(
        account,
        lines,
        [item for item in promos if "HINT" in str(item.get("sku")) or item.get("requires_addon_kind") == "home_internet"],
        new_lines=0,
        devices=(),
        addon_kinds=frozenset({"home_internet"}),
        names=names,
    )
    return {
        "name": addon["name"],
        "sku": addon["sku"],
        "monthly_cents": int(addon["monthly_cents"] or 0),
        "promo": promo,
    }
