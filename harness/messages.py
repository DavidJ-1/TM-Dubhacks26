"""Template drafts. No network call. The offer decision is already made before this runs."""

from __future__ import annotations

import html


def _dollars(cents: int | None) -> str:
    if cents is None:
        return "n/a"
    return f"${cents / 100:,.2f}"


def outbound_title(action: dict, moment: dict | None, account: dict | None = None) -> str:
    """Heading for the message we would actually send. A paid-off upgrade is not 'do nothing'.

    One message, one action: a retention offer is never paired with an upgrade pitch.
    """
    upgrading = bool(moment and moment.get("when") == "now" and moment.get("device_name"))
    if account is not None and upgrading:
        upgrading = upgrade_allowed(action, account, moment)
    if action.get("choice") == "offer":
        return action["name"]
    if upgrading:
        promo = (moment.get("promo") or {}).get("name")
        if promo:
            return f"Upgrade now · {promo}"
        return f"Upgrade now · {moment['device_name']}"
    return "Do nothing"


BILL_SHOCK_PCT = 0.05  # same 5% line the console uses for "bill up"


def upgrade_allowed(action: dict, account: dict, moment: dict | None) -> bool:
    """One message, one action: no upgrade pitch next to a retention offer or after a bill jump."""
    if not (moment and moment.get("when") == "now" and moment.get("device_name")):
        return False
    if action.get("choice") == "offer":
        return False
    return float(account.get("bill_increase_pct") or 0) <= BILL_SHOCK_PCT


def draft(account: dict, action: dict, moment: dict | None) -> dict:
    language = account["language"] if account["language"] in {"en", "es", "hi", "zh"} else "en"
    channel = account["contact_preference"]
    parts: list[str] = []
    purpose = "none"
    if action["choice"] == "offer":
        parts.append(_fit([_retention(language, account, action)], language))
        purpose = "retention"
    if upgrade_allowed(action, account, moment):
        parts.append(_upgrade(language, moment))
        purpose = "upgrade"
    text = "\n\n".join(parts) if parts else None
    return {
        "language": language,
        "channel": channel,
        "purpose": purpose,
        "text": text,
        "html": html.escape(text) if text else None,
    }


def _retention(language: str, account: dict, action: dict) -> str:
    sku = action["sku"]
    contacts = int(account["support_90d"])
    months = int(account["tenure_months"])
    jump = float(account["bill_increase_pct"]) > 0.05
    pct = f"{float(account['bill_increase_pct']) * 100:.0f}"
    if language == "es":
        if sku == "PROMO-STUB-CARE-CREDIT":
            bill = f" Tu último recibo subió {pct}% frente al promedio anterior." if jump else ""
            return (
                f"Hola. Vimos {contacts} contactos con soporte en los últimos 90 días.{bill} "
                "Hay un crédito de cuidado de $25.00 en tu próximo recibo. No cambia tu plan."
            )
        if sku == "PROMO-STUB-LOYALTY-CREDIT":
            return (
                f"Hola. Llevas {months} meses con nosotros. "
                "Hay un crédito de lealtad de $5.00 al mes en la cuenta. No cambia tu plan ni tu teléfono."
            )
        return "Hola. El crédito de estudiante de $20.00 al mes por línea está disponible en esta cuenta, hasta 2 líneas."
    if language == "hi":
        if sku == "PROMO-STUB-CARE-CREDIT":
            bill = f" आपका हाल का बिल पिछले औसत से {pct}% ज़्यादा है।" if jump else ""
            return (
                f"नमस्ते। पिछले 90 दिनों में {contacts} सपोर्ट संपर्क दिखे।{bill} "
                "अगले बिल पर $25.00 का केयर क्रेडिट है। इससे प्लान नहीं बदलता।"
            )
        if sku == "PROMO-STUB-LOYALTY-CREDIT":
            return (
                f"नमस्ते। आप इस खाते पर {months} महीने से हैं। "
                "$5.00 प्रति माह का लॉयल्टी क्रेडिट उपलब्ध है। इससे प्लान या फ़ोन नहीं बदलता।"
            )
        return "नमस्ते। इस खाते पर प्रति लाइन प्रति माह $20.00 का छात्र क्रेडिट उपलब्ध है, अधिकतम 2 लाइनें।"
    if language == "zh":
        if sku == "PROMO-STUB-CARE-CREDIT":
            bill = f"最近一期账单比之前的月均高出{pct}%。" if jump else ""
            return (
                f"您好。过去90天里有{contacts}次客服联系。{bill}"
                "下一期账单有$25.00的关怀信用金。这不会改变套餐。"
            )
        if sku == "PROMO-STUB-LOYALTY-CREDIT":
            return (
                f"您好。您使用这个账户已有{months}个月。"
                "每月有$5.00的忠诚信用金。这不会改变套餐或手机。"
            )
        return "您好。此账户每条线路每月可享$20.00学生信用金，最多2条线路。"
    if sku == "PROMO-STUB-CARE-CREDIT":
        bill = f" The latest bill is {pct}% above the prior-month average." if jump else ""
        return (
            f"We saw {contacts} support contacts in the last 90 days.{bill} "
            "A $25.00 care credit is on the next bill. It does not change the plan."
        )
    if sku == "PROMO-STUB-LOYALTY-CREDIT":
        return (
            f"You have been on this account for {months} months. "
            "A $5.00 per month loyalty credit is available. It does not change the plan or the phone."
        )
    return "A student credit of $20.00 per line per month is available on this account, up to 2 lines."


MAX_SMS_CHARS = 300

_OPT_OUT = {
    "en": "Reply STOP to opt out.",
    "es": "Responde STOP para no recibir más.",
    "hi": "बंद करने के लिए STOP लिखें।",
    "zh": "回复STOP退订。",
}


def _fit(parts: list[str], language: str) -> str:
    """Join sentences, dropping optional ones from the end until the text fits one SMS screen.

    parts[0] is required. The opt-out line is always kept.
    """
    tail = _OPT_OUT.get(language, _OPT_OUT["en"])
    joiner = "" if language == "zh" else " "
    keep = [p for p in parts if p]
    while keep:
        text = joiner.join([*keep, tail])
        if len(text) <= MAX_SMS_CHARS or len(keep) == 1:
            return text[:MAX_SMS_CHARS]
        keep.pop()
    return tail


def _upgrade(language: str, moment: dict) -> str:
    """Short, customer-facing upgrade nudge. Modeling notes stay on screen, never in the text."""
    language = language if language in {"en", "es", "hi", "zh"} else "en"
    promo = moment.get("promo") if isinstance(moment.get("promo"), dict) else None
    balance = int(moment.get("balance_cents") or 0)
    owed = _dollars(balance)
    trade = _dollars(moment.get("tradein_value_cents")) if moment.get("tradein_value_cents") is not None else None
    device = moment["device_name"]
    age = moment["age_months"]
    promo_text = f"{promo['name']} ({_dollars(promo['savings_cents'])})" if promo else ""
    if language == "es":
        head = f"Tu {device} tiene {age} meses" + (" y ya está pagado." if balance == 0 else f". Aún debes {owed}.")
        return _fit([
            head,
            f"Valor de canje en buena condición: {trade}." if trade else "",
            f"Promo disponible: {promo_text}." if promo else "",
            "Responde UPGRADE para ver opciones.",
        ], language)
    if language == "hi":
        head = f"आपका {device} {age} महीने पुराना है" + (", और पूरा चुका दिया गया है।" if balance == 0 else f"। अभी {owed} बकाया है।")
        return _fit([
            head,
            f"अच्छी स्थिति में ट्रेड-इन मूल्य: {trade}।" if trade else "",
            f"उपलब्ध प्रोमो: {promo_text}।" if promo else "",
            "विकल्प देखने के लिए UPGRADE लिखें।",
        ], language)
    if language == "zh":
        head = f"您的{device}已使用{age}个月" + ("，并已还清。" if balance == 0 else f"，还剩{owed}未还清。")
        return _fit([
            head,
            f"良好成色的以旧换新价值：{trade}。" if trade else "",
            f"可用优惠：{promo_text}。" if promo else "",
            "回复UPGRADE查看选项。",
        ], language)
    head = f"Your {device} is {age} months old" + (" and paid off." if balance == 0 else f". {owed} is still owed on it.")
    return _fit([
        head,
        f"Good-condition trade-in value: {trade}." if trade else "",
        f"Available promo: {promo_text}." if promo else "",
        "Reply UPGRADE to see options.",
    ], language)
