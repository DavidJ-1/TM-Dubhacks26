"""Deterministic SMS templates (en / es) for the action Model B chose. No LLM.

Rules
- Only the chosen action is offered; amounts come exactly from the sandbox promotions / plans tables.
- 'do nothing' -> blank. The adapted keep-your-phone credit is NOT a sandbox promo for existing customers, so it
  never gets a message (blank, message_status = suppressed_adapted_promo).
- fix-first -> a callback-to-fix note, no discount.
- Synthetic: no customer names ("Hi there" / "Hola"), no phone numbers. Spanish uses usted throughout.
- validate_messages() re-derives every allowed dollar amount from the sandbox tables and checks each message.

Pure functions: build_message(fact_row, action_code, res, promos, plans, lang) -> str
                validate_messages(offers, facts, promos, plans) -> DataFrame (one row per account)
"""

from __future__ import annotations

import re

import pandas as pd

MAX_LEN = 300
STOP_EN = "Reply STOP to opt out."
STOP_ES = "Responda STOP para no recibir mensajes."


def _money(cents: float) -> str:
    v = cents / 100
    return f"${v:,.0f}" if abs(v - round(v)) < 1e-9 else f"${v:,.2f}"


def plan_price_cents(plan: pd.Series, n_lines: int) -> int:
    table = [int(p) for p in str(plan["line_prices"]).split(",")]
    return int(sum(table[i] if i < len(table) else int(plan["extra_line_cents"]) for i in range(int(n_lines))))


def risk_phrase(f: pd.Series, action: str, lang: str) -> str:
    """Top risk reason in plain words with real values, preferring the one the chosen action addresses."""
    bump = f.get("bill_increase_pct", 0) or 0
    net = int(f.get("network_90d", 0) or 0)
    unres = int(f.get("unresolved_90d", 0) or 0)
    use = f.get("max_line_data_gb")
    cap = f.get("plan_cap_gb")
    age = f.get("oldest_device_age_m")
    cands = []
    if f.get("um_promo_expired") and bump >= 0.05:
        cands.append(("billing", {"en": f"your promo ended and your bill went up {bump*100:.0f}%",
                                  "es": f"su promoción terminó y su factura subió un {bump*100:.0f}%"}))
    elif bump >= 0.10:
        cands.append(("billing", {"en": f"your bill went up {bump*100:.0f}%",
                                  "es": f"su factura subió un {bump*100:.0f}%"}))
    if net >= 1:
        cands.append(("network", {"en": f"you've reported {net} network issue{'s' if net != 1 else ''} lately",
                                  "es": f"nos ha reportado {net} problema{'s' if net != 1 else ''} de red recientemente"}))
    if unres >= 1:
        cands.append(("unresolved", {"en": f"you have {unres} support request{'s' if unres != 1 else ''} we haven't resolved yet",
                                     "es": f"tiene {unres} solicitud{'es' if unres != 1 else ''} de soporte sin resolver"}))
    if pd.notna(use) and pd.notna(cap) and use >= 0.8 * cap:
        cands.append(("usage", {"en": f"you're using about {use:.0f} GB a month on a plan with {cap:.0f} GB of premium data",
                                "es": f"usa unos {use:.0f} GB al mes y su plan incluye {cap:.0f} GB de datos premium"}))
    growth = f.get("data_growth_pct")
    if f.get("um_usage_growth") and pd.notna(growth) and growth >= 0.10:
        cands.append(("usage", {"en": f"your data use is up {growth*100:.0f}% over the past year",
                                "es": f"su uso de datos subió un {growth*100:.0f}% en el último año"}))
    hs = f.get("max_line_hotspot_gb")
    if pd.notna(hs) and hs > 0.5 and (f.get("plan_hotspot_gb") or 0) == 0:
        cands.append(("usage", {"en": f"you use about {hs:.0f} GB of hotspot a month and your plan has no high-speed hotspot",
                                "es": f"usa unos {hs:.0f} GB de hotspot al mes y su plan no incluye hotspot de alta velocidad"}))
    if f.get("um_student_graduating"):
        cands.append(("life", {"en": "you're getting close to finishing school",
                               "es": "está por terminar sus estudios"}))
    if pd.notna(age) and age >= 36:
        cands.append(("device", {"en": f"your phone is about {int(age // 12)} years old",
                                 "es": f"su teléfono tiene unos {int(age // 12)} años"}))
    pref = {"care_credit": ["billing", "unresolved", "network"],
            "care_credit_fix_first": ["network", "unresolved", "billing"],
            "fix_first": ["network", "unresolved", "billing"],
            "loyalty_credit": ["billing"], "right_size": ["billing"],
            "step_up": ["usage", "life"], "device_upgrade": ["device"]}.get(action, [])
    for k in pref:
        for kk, ph in cands:
            if kk == k:
                return ph[lang]
    if cands:
        return cands[0][1][lang]
    return {"en": "we want to make sure your plan still fits you",
            "es": "queremos asegurarnos de que su plan le siga conviniendo"}[lang]


def _plan_by_name(plans: pd.DataFrame, name: str) -> pd.Series:
    return plans.set_index("name").loc[name]


def build_message(f: pd.Series, action: str, res: dict, promos: pd.DataFrame, plans: pd.DataFrame,
                  lang: str) -> str:
    if action in ("do_nothing", "keep_your_phone"):
        return ""
    why = risk_phrase(f, action, lang)
    en = lang == "en"
    hi = "Hi there. We noticed " if en else "Hola. Notamos que "
    stop = STOP_EN if en else STOP_ES
    if action in ("care_credit", "care_credit_fix_first"):
        pr = promos.loc["PROMO-STUB-CARE-CREDIT"]
        amt = _money(pr["value_cents"] * (pr["payout_months"] or 1))
    if action == "care_credit":
        body = (f"{why}. We'd like to give you a one-time {amt} credit on your next bill. Reply YES to accept."
                if en else f"{why}. Queremos darle un crédito único de {amt} en su próxima factura. "
                           "Responda SÍ para aceptarlo.")
    elif action == "care_credit_fix_first":
        body = (f"{why}. A specialist will call you to fix it, and we'll add a one-time {amt} credit to your "
                "next bill. Reply YES to schedule the call."
                if en else f"{why}. Un especialista le llamará para resolverlo y le daremos un crédito único de "
                           f"{amt} en su próxima factura. Responda SÍ para programar la llamada.")
    elif action == "fix_first":
        body = (f"{why}. We want to get this fixed: reply YES and a specialist will call you."
                if en else f"{why}. Queremos resolverlo: responda SÍ y un especialista le llamará.")
    elif action == "loyalty_credit":
        pr = promos.loc["PROMO-STUB-LOYALTY-CREDIT"]
        yrs = int(f["tenure_months"] // 12)
        amt = _money(pr["value_cents"])
        body = (f"{why}. Thanks for {yrs} years with us: you can get a {amt}/month loyalty credit. Reply YES to add it."
                if en else f"{why}. Gracias por {yrs} años con nosotros: puede recibir un crédito de lealtad de "
                           f"{amt} al mes. Responda SÍ para agregarlo.")
    elif action == "right_size":
        tgt = _plan_by_name(plans, res["right_size"]["plan_name"])
        cur = plans.set_index("sku").loc[f["plan_sku"]]
        diff = plan_price_cents(cur, f["n_lines"]) - plan_price_cents(tgt, f["n_lines"])
        body = (f"{why}. Switching to {tgt.name} would lower your plan price by {_money(diff)}/month and still "
                "fits your usage. Reply YES to switch."
                if en else f"{why}. Con {tgt.name} pagaría {_money(diff)} menos al mes por su plan y le alcanza "
                           "para su uso. Responda SÍ para cambiar.")
    elif action == "step_up":
        tgt = _plan_by_name(plans, res["step_up"]["plan_name"])
        cur = plans.set_index("sku").loc[f["plan_sku"]]
        diff = plan_price_cents(tgt, f["n_lines"]) - plan_price_cents(cur, f["n_lines"])
        if pd.isna(tgt["data_cap_gb"]) and pd.notna(cur["data_cap_gb"]):
            perk = ("unlimited premium data", "datos premium ilimitados")
        elif tgt["hotspot_high_speed_gb"] > cur["hotspot_high_speed_gb"]:
            perk = (f"{tgt['hotspot_high_speed_gb']} GB of high-speed hotspot",
                    f"{tgt['hotspot_high_speed_gb']} GB de hotspot de alta velocidad")
        elif pd.isna(tgt["max_lines"]) and pd.notna(cur["max_lines"]):
            perk = ("room to add more lines", "la opción de agregar más líneas")
        else:
            perk = ("more room to grow", "más espacio para crecer")
        body = (f"{why}. {tgt.name} gives you {perk[0]} for {_money(diff)}/month more. Reply YES to learn more."
                if en else f"{why}. {tgt.name} le ofrece {perk[1]} por {_money(diff)} más al mes. "
                           "Responda SÍ para saber más.")
    elif action == "device_upgrade":
        pr = promos.loc[res["device_upgrade"]["promo"]]
        amt, months = _money(pr["value_cents"]), int(pr["payout_months"])
        body = (f"{why}. Trade it in and get {amt} in bill credits over {months} months toward a new phone. "
                "Reply YES to see phones."
                if en else f"{why}. Entréguelo como parte de pago y reciba {amt} en créditos en su factura durante "
                           f"{months} meses para un teléfono nuevo. Responda SÍ para ver teléfonos.")
    else:
        return ""
    msg = f"{hi}{body} {stop}"
    return msg


# ---------------------------------------------------------------- validator
_DOLLAR = re.compile(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)")
_PHONE = re.compile(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")


def allowed_amounts(f: pd.Series, action: str, promos: pd.DataFrame, plans: pd.DataFrame, msg: str) -> set:
    """Dollar amounts a message for this action may contain, re-derived from the sandbox tables."""
    ok: set[float] = set()
    if action in ("care_credit", "care_credit_fix_first"):
        pr = promos.loc["PROMO-STUB-CARE-CREDIT"]
        ok.add(pr["value_cents"] * (pr["payout_months"] or 1) / 100)
    if action == "loyalty_credit":
        ok.add(promos.loc["PROMO-STUB-LOYALTY-CREDIT", "value_cents"] / 100)
    if action == "device_upgrade":
        ok |= {v / 100 for v in promos.loc[promos["kind"] == "device_credit", "value_cents"]
               if f"${v/100:,.0f}" in msg}  # must be some real device-credit promo value...
        ok &= {promos.loc[s, "value_cents"] / 100 for s in ("PROMO-STUB-OLD-PHONE-UPGRADE", "PROMO-STUB-TRADEIN-ANY")}
    if action in ("right_size", "step_up"):
        cur = plans.set_index("sku").loc[f["plan_sku"]]
        for _, p in plans.iterrows():
            if p["name"] in msg:
                ok.add(abs(plan_price_cents(p, f["n_lines"]) - plan_price_cents(cur, f["n_lines"])) / 100)
    return ok


def validate_messages(offers: pd.DataFrame, facts: pd.DataFrame, promos: pd.DataFrame,
                      plans: pd.DataFrame) -> pd.DataFrame:
    fx = facts.set_index("account_id")
    rows = []
    for _, o in offers.iterrows():
        f = fx.loc[o["account_id"]]
        act = o["action_code"]
        problems = []
        for lang in ("en", "es"):
            m = o[f"message_{lang}"] if isinstance(o[f"message_{lang}"], str) else ""
            if act in ("do_nothing", "keep_your_phone"):
                if m:
                    problems.append(f"{lang}: message present for {act}")
                continue
            if not m:
                problems.append(f"{lang}: missing message")
                continue
            if len(m) > MAX_LEN:
                problems.append(f"{lang}: {len(m)} chars > {MAX_LEN}")
            if _PHONE.search(m):
                problems.append(f"{lang}: phone-number-like text")
            amts = {float(x.replace(",", "")) for x in _DOLLAR.findall(m)}
            allowed = allowed_amounts(f, act, promos, plans, m)
            bad = {a for a in amts if not any(abs(a - b) < 0.005 for b in allowed)}
            if bad:
                problems.append(f"{lang}: amounts {sorted(bad)} not in sandbox ({sorted(allowed)})")
            if act == "fix_first" and amts:
                problems.append(f"{lang}: fix-first message contains a dollar amount")
        rows.append({"account_id": o["account_id"], "action": o["action"], "passed": not problems,
                     "problems": "; ".join(problems)})
    return pd.DataFrame(rows)
