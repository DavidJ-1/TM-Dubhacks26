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
    if pd.notna(age) and age >= 36:
        cands.append(("device", {"en": f"your phone is about {int(age // 12)} years old",
                                 "es": f"su teléfono tiene unos {int(age // 12)} años"}))
    pref = {"care_credit": ["billing", "unresolved", "network"],
            "care_credit_fix_first": ["network", "unresolved", "billing"],
            "fix_first": ["network", "unresolved", "billing"],
            "loyalty_credit": ["billing"], "right_size": ["billing"],
            "step_up": ["usage"], "device_upgrade": ["device"], "family_upgrade": ["usage"]}.get(action, [])
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


def _guarantee(plan: pd.Series) -> int:
    g = plan.get("price_guarantee_years")
    return int(g) if pd.notna(g) else 0


def _benefit(plan: pd.Series, lang: str) -> str:
    if pd.isna(plan["data_cap_gb"]):
        return "unlimited premium data" if lang == "en" else "datos premium ilimitados"
    cap = int(plan["data_cap_gb"])
    return (f"{cap} GB of premium data per line" if lang == "en" else f"{cap} GB de datos premium por línea")


def build_message(f: pd.Series, action: str, res: dict, promos: pd.DataFrame, plans: pd.DataFrame,
                  lang: str) -> str:
    if action in ("do_nothing", "keep_your_phone"):
        return ""
    en = lang == "en"
    hi = "Hi there. " if en else "Hola. "
    noticed = ""   # explainability audit: no "We noticed" (reads as surveillance)
    stop = STOP_EN if en else STOP_ES
    why = risk_phrase(f, action, lang)
    why = why[:1].upper() + why[1:]
    calm = " Happy as is? No need to do anything." if en else " ¿Contento así? No tiene que hacer nada."
    if action in ("step_up", "family_upgrade"):   # show the stay-as-is option (rubric R4 trade-off)
        calm = (" Prefer to keep your plan? No need to do anything." if en
                else " ¿Prefiere mantener su plan? No tiene que hacer nada.")
    P = plans.set_index("sku")
    cur = P.loc[f["plan_sku"]]
    n = int(f["n_lines"])
    lines_en = f"Your {n} lines" if n > 1 else "Your line"
    lines_es = f"Sus {n} líneas" if n > 1 else "Su línea"
    cc = promos.loc["PROMO-STUB-CARE-CREDIT"]
    care_amt = _money(cc["value_cents"] * (cc["payout_months"] or 1))
    loy_amt = _money(promos.loc["PROMO-STUB-LOYALTY-CREDIT", "value_cents"])
    if action == "care_credit":
        body = (f"{noticed}{why}. We'd like to give you a one-time {care_amt} credit on your next bill. Reply YES to accept."
                if en else f"{noticed}{why}. Queremos darle un crédito único de {care_amt} en su próxima factura. "
                           "Responda SÍ para aceptarlo.")
    elif action == "care_credit_fix_first":
        body = (f"{noticed}{why}. A specialist will call you to fix it, and we'll add a one-time {care_amt} credit to "
                "your next bill. Reply YES to schedule the call."
                if en else f"{noticed}{why}. Un especialista le llamará para resolverlo y le daremos un crédito único "
                           f"de {care_amt} en su próxima factura. Responda SÍ para programar la llamada.")
    elif action == "fix_first":
        body = (f"{noticed}{why}. We want to get this fixed: reply YES and a specialist will call you."
                if en else f"{noticed}{why}. Queremos resolverlo: responda SÍ y un especialista le llamará.")
    elif action == "loyalty_credit":
        yrs = int(f["tenure_months"] // 12)
        body = (f"Thanks for {yrs} years with us. You can get a {loy_amt}/month loyalty credit. Reply YES to add it."
                if en else f"Gracias por {yrs} años con nosotros. Puede recibir un crédito de lealtad de {loy_amt} "
                           "al mes. Responda SÍ para agregarlo.")
    elif action == "bill_shock_price_lock":
        g = _guarantee(cur)
        loy = res["bill_shock_price_lock"].get("with_loyalty")
        body = (f"Your bill went up because a promo credit ended, not because your plan price changed. {cur['name']} "
                f"talk, text and data stay covered by your {g}-Year Price Guarantee. We'll add a one-time {care_amt} credit"
                + (f" and {loy_amt}/month off" if loy else "") + ". Reply YES to accept."
                if en else
                f"Su factura subió porque terminó un crédito de promoción, no porque cambió el precio de su plan. Su "
                f"{cur['name']} sigue cubierto por la garantía de precio de {g} años. Le daremos un crédito único "
                f"de {care_amt}" + (f" y {loy_amt} menos al mes" if loy else "") + ". Responda SÍ para aceptarlo.")
    elif action == "variant_switch":
        v = res["variant_switch"]
        tgt = P.loc[v["plan_sku"]]
        old, new = plan_price_cents(cur, n), plan_price_cents(tgt, n)
        body = (f"Good news: {lines_en[0].lower() + lines_en[1:]} qualify for {tgt['name']}. Same features, "
                f"{_money(new)}/month instead of {_money(old)}. Nothing else changes. Reply YES and we'll move you."
                if en else f"Buenas noticias: {lines_es[0].lower() + lines_es[1:]} califica{'n' if n > 1 else ''} para "
                           f"{tgt['name']}. Las mismas funciones por {_money(new)} al mes en lugar de {_money(old)}. "
                           "Nada más cambia. Responda SÍ y haremos el cambio.")
    elif action == "right_size":
        v = res["right_size"]
        tgt = P.loc[v["plan_sku"]]
        diff = plan_price_cents(cur, n) - plan_price_cents(tgt, n)
        gives_en, gives_es = [], []
        if tgt["hotspot_high_speed_gb"] == 0 < cur["hotspot_high_speed_gb"]:
            gives_en.append("high-speed hotspot")
            gives_es.append("hotspot rápido")
        elif tgt["hotspot_high_speed_gb"] < cur["hotspot_high_speed_gb"]:
            gives_en.append(f"hotspot drops from {cur['hotspot_high_speed_gb']} GB to {tgt['hotspot_high_speed_gb']} GB")
            gives_es.append(f"hotspot de {cur['hotspot_high_speed_gb']} a {tgt['hotspot_high_speed_gb']} GB")
        if _guarantee(cur) and not _guarantee(tgt):
            gives_en.append("the 5-Year Price Guarantee")
            gives_es.append("la garantía de precio de 5 años")
        elif len(str(tgt["perks"] or "").split(",")) < len(str(cur["perks"] or "").split(",")):
            gives_en.append("some streaming perks")
            gives_es.append("algunos beneficios de streaming")
        if pd.notna(cur.get("device_connection_cents")) and pd.isna(tgt.get("device_connection_cents")):
            gives_en.append("watch/tablet lines")
            gives_es.append("líneas de reloj/tableta")
        if pd.notna(tgt["max_lines"]) and (pd.isna(cur["max_lines"]) or tgt["max_lines"] < cur["max_lines"]):
            gives_en.append(f"more than {int(tgt['max_lines'])} lines")
            gives_es.append(f"más de {int(tgt['max_lines'])} líneas")
        body = (f"You could pay {_money(diff)}/month less: {tgt['name']} has {_benefit(tgt, 'en')}, enough for "
                "your use." + (f" You'd give up: {', '.join(gives_en)}." if gives_en else "")
                + " Reply YES to move, or ignore this to keep your plan."
                if en else f"Podría pagar {_money(diff)} menos al mes: {tgt['name']} tiene {_benefit(tgt, 'es')}, "
                           "suficiente para su uso." + (f" Perdería: {', '.join(gives_es)}." if gives_es else "")
                           + " Responda SÍ para cambiar.")
        if len(f"{hi}{body} {stop}") > MAX_LEN:   # long give-up list: drop the 'enough for your use' clause
            body = body.replace(", enough for your use.", ".").replace(", suficiente para su uso.", ".")
    elif action == "step_up":
        tgt = P.loc[res["step_up"]["plan_sku"]]
        diff = plan_price_cents(tgt, n) - plan_price_cents(cur, n)
        if f.get("um_student_graduating") and not (f.get("um_near_plan_limit") or f.get("um_usage_growth")):
            # plan-led (persona 28): no inference about the customer's life in the text
            body = (f"Your plan is our {cur['name']}. {tgt['name']} lets you add lines later, for "
                    f"{_money(diff)}/month more. Reply YES to learn more."
                    if en else f"Su plan es nuestro {cur['name']}. {tgt['name']} le permite agregar líneas más "
                               f"adelante, por {_money(diff)} más al mes. Responda SÍ para saber más.")
        else:
            if pd.isna(tgt["data_cap_gb"]) and pd.notna(cur["data_cap_gb"]):
                perk = ("unlimited premium data", "datos premium ilimitados")
            elif tgt["hotspot_high_speed_gb"] > cur["hotspot_high_speed_gb"]:
                perk = (f"{tgt['hotspot_high_speed_gb']} GB of high-speed hotspot",
                        f"{tgt['hotspot_high_speed_gb']} GB de hotspot de alta velocidad")
            elif pd.isna(tgt["max_lines"]) and pd.notna(cur["max_lines"]):
                perk = ("room to add more lines", "la opción de agregar más líneas")
            else:
                perk = ("more room to grow", "más espacio para crecer")
            body = (f"{noticed}{why}. {tgt['name']} gives you {perk[0]} for {_money(diff)}/month more.{calm} Reply YES to compare plans."
                    if en else f"{noticed}{why}. {tgt['name']} le ofrece {perk[1]} por {_money(diff)} más al mes.{calm} "
                               "Responda SÍ para comparar planes.")
    elif action == "family_upgrade":
        v = res["family_upgrade"]
        tgt = P.loc[v["plan_sku"]]
        diff = plan_price_cents(tgt, n) - plan_price_cents(cur, n)
        g = _guarantee(tgt)
        perk_en = "every line unlimited premium data" if pd.notna(cur["data_cap_gb"]) else \
            f"{tgt['hotspot_high_speed_gb']} GB hotspot per line"
        perk_es = "datos premium ilimitados en cada línea" if pd.notna(cur["data_cap_gb"]) else \
            f"{tgt['hotspot_high_speed_gb']} GB de hotspot por línea"
        # batch 7: plan move only; any phone trade-in is a separate offer, never bundled into this text
        body = (f"{why}. {tgt['name']} gives {perk_en} for {_money(diff)}/month more for your {n} lines.{calm} "
                "Reply YES to compare plans."
                if en else
                f"{why}. {tgt['name']} le da {perk_es} por {_money(diff)} más al mes para sus {n} líneas.{calm} "
                "Responda SÍ para comparar planes.")
    elif action == "device_upgrade":
        pr = promos.loc[res["device_upgrade"]["promo"]]
        amt, months = _money(pr["value_cents"]), int(pr["payout_months"])
        body = (f"{noticed}{why}. Trade it in and get {amt} in bill credits over {months} months toward a new phone.{calm} "
                "Reply YES to see phones."
                if en else f"{noticed}{why}. Entréguelo como parte de pago y reciba {amt} en créditos en su factura "
                           f"durante {months} meses para un teléfono nuevo.{calm} Responda SÍ para ver teléfonos.")
    elif action == "check_in":
        yrs = int(f["tenure_months"] // 12)
        g = _guarantee(cur)
        thanks_en = f"Thanks for {yrs} years with us. " if yrs >= 2 else "Thanks for being with us. "
        thanks_es = f"Gracias por {yrs} años con nosotros. " if yrs >= 2 else "Gracias por estar con nosotros. "
        fact_en = (f"Your {cur['name']} includes {_benefit(cur, 'en')}"
                   + (f", covered by your {g}-Year Price Guarantee" if g else "") + ". ")
        fact_es = (f"Su {cur['name']} incluye {_benefit(cur, 'es')}"
                   + (f", cubierto por su garantía de precio de {g} años" if g else "") + ". ")
        body = (f"{thanks_en}{fact_en}Is anything about your plan or service not working for you? Reply YES for a "
                "free plan review, no strings attached."
                if en else f"{thanks_es}{fact_es}¿Podemos mejorar algo de su plan? Responda SÍ para revisarlo.")
    elif action == "perk_reminder":
        body = (f"Your {cur['name']} already includes a streaming video service with ads at no extra cost. "
                "Reply YES and we'll help you set it up."
                if en else f"Su {cur['name']} ya incluye un servicio de video en streaming con anuncios sin costo "
                           "adicional. Responda SÍ y le ayudamos a activarlo.")
    elif action == "home_internet_bundle":
        body = (f"You can add Home Internet from $50/month and get $15/month off with your phone lines.{calm} "
                "Reply YES for details."
                if en else "Puede agregar Internet en Casa desde $50 al mes y recibir $15 de descuento al mes con "
                           f"sus líneas de teléfono.{calm} Responda SÍ para más detalles.")
    else:
        return ""
    msg = f"{hi}{body} {stop}"
    if len(msg) > MAX_LEN and action in ("step_up", "family_upgrade"):   # long plan names: shorter stay-as-is line
        short = " No need to do anything." if en else " No tiene que hacer nada."
        msg = f"{hi}{body.replace(calm, short)} {stop}"
    return msg


# ---------------------------------------------------------------- validator
_DOLLAR = re.compile(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)")
_PHONE = re.compile(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")


# Blocklist: inferred life details, shopping, public-only offers, AutoPay, and any "new lock" framing.
# Whole-word / word-prefix matching (\bport, \bjob) so "support" and "report" pass. "promo" passes, "promotion" fails.
BLOCK_EN = [r"\bschool", r"\bgraduat", r"\bjob", r"\bpromot", r"\bincome", r"\bkid", r"\bchild", r"\bcompetitor",
            r"\bswitch", r"\bport", r"\bauto\s?pay", r"\bmilitary", r"\bfirst responder", r"\bbetter value",
            r"\bgo5g", r"\b3rd line free", r"\bnetflix", r"\bhulu", r"\bapple tv", r"\btuesdays", r"\bmagenta status",
            r"\block", r"won't change", r"will never change", r"never go up"]
BLOCK_ES = [r"\bescuela", r"\bcolegio", r"\buniversidad", r"\bestudi", r"\bgradu", r"\btrabajo", r"\bempleo",
            r"\bascenso", r"\bingreso", r"\bniñ", r"\bhij", r"\bcompetencia", r"\bcompetidor", r"\bportab",
            r"\bportar", r"\bpago automático", r"\bautopay", r"\bmilitar", r"\bbloque", r"no cambiará",
            r"\bcongela", r"\bnetflix", r"\bhulu", r"\bapple tv"]
_BLOCK = {"en": re.compile("|".join(BLOCK_EN), re.I), "es": re.compile("|".join(BLOCK_ES), re.I)}
_GUAR = {"en": re.compile(r"guaranteed for \d+ years", re.I), "es": re.compile(r"garantizado por \d+ años", re.I)}
_COVER = {"en": re.compile(r"(\d+)-Year Price Guarantee", re.I), "es": re.compile(r"garantía de precio de (\d+) años", re.I)}


def allowed_amounts(f: pd.Series, action: str, promos: pd.DataFrame, plans: pd.DataFrame, msg: str,
                    addons: pd.DataFrame | None = None) -> set:
    """Dollar amounts a message for this action may contain, re-derived from the sandbox tables."""
    ok: set[float] = set()
    care = promos.loc["PROMO-STUB-CARE-CREDIT"]
    loy = promos.loc["PROMO-STUB-LOYALTY-CREDIT", "value_cents"] / 100
    if action in ("care_credit", "care_credit_fix_first", "bill_shock_price_lock"):
        ok.add(care["value_cents"] * (care["payout_months"] or 1) / 100)
    if action in ("loyalty_credit", "bill_shock_price_lock"):
        ok.add(loy)
    if action == "device_upgrade":
        ok |= {promos.loc[s, "value_cents"] / 100 for s in ("PROMO-STUB-OLD-PHONE-UPGRADE", "PROMO-STUB-TRADEIN-ANY")}
    if action == "home_internet_bundle":
        ok.add(promos.loc["PROMO-STUB-BUNDLE-HINT", "value_cents"] / 100)
        if addons is not None:
            ok.add(addons.loc["TMO-STUB-ADD-HINT-BASIC", "monthly_cents"] / 100)
    if action in ("right_size", "step_up", "family_upgrade", "variant_switch"):
        cur = plans.set_index("sku").loc[f["plan_sku"]]
        for _, p in plans.iterrows():
            if p["name"] in msg:
                a, b = plan_price_cents(p, f["n_lines"]), plan_price_cents(cur, f["n_lines"])
                ok.add(abs(a - b) / 100)
                if action == "variant_switch":
                    ok |= {a / 100, b / 100}
    return ok


def validate_messages(offers: pd.DataFrame, facts: pd.DataFrame, promos: pd.DataFrame,
                      plans: pd.DataFrame, addons: pd.DataFrame | None = None) -> pd.DataFrame:
    fx = facts.set_index("account_id")
    guar_years = {int(g) for g in plans["price_guarantee_years"].dropna()}
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
            hit = _BLOCK[lang].search(m)
            if hit:
                problems.append(f"{lang}: blocked term '{hit.group(0)}'")
            if _GUAR[lang].search(m):
                problems.append(f"{lang}: says 'guaranteed for N years' (use 'covered by your N-Year Price Guarantee')")
            cur_g = plans.set_index("sku").loc[f["plan_sku"], "price_guarantee_years"]
            for y in _COVER[lang].findall(m):
                if pd.isna(cur_g) or int(y) != int(cur_g):
                    problems.append(f"{lang}: price-guarantee claim not true for the current plan")
            amts = {float(x.replace(",", "")) for x in _DOLLAR.findall(m)}
            allowed = allowed_amounts(f, act, promos, plans, m, addons)
            bad = {a for a in amts if not any(abs(a - b) < 0.005 for b in allowed)}
            if bad:
                problems.append(f"{lang}: amounts {sorted(bad)} not in sandbox ({sorted(allowed)})")
            if re.search(r"\b(we noticed|notamos)\b", m, re.I):
                problems.append(f"{lang}: 'we noticed' framing")
            if act in ("fix_first", "check_in", "perk_reminder") and amts:
                problems.append(f"{lang}: {act} message contains a dollar amount")
        rows.append({"account_id": o["account_id"], "action": o["action"], "passed": not problems,
                     "problems": "; ".join(problems)})
    return pd.DataFrame(rows)
