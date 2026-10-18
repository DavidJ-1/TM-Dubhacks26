"""Template drafts. No network call. The offer decision is already made before this runs."""

from __future__ import annotations

import html
import re


def _dollars(cents: int | None) -> str:
    if cents is None:
        return "n/a"
    return f"${cents / 100:,.2f}"


def outbound_title(action: dict, moment: dict | None) -> str:
    """Heading for the message we would actually send. A paid-off upgrade is not 'do nothing'."""
    upgrading = bool(moment and moment.get("when") == "now" and moment.get("device_name"))
    if action.get("choice") == "offer" and upgrading:
        return f"{action['name']} · upgrade {moment['device_name']}"
    if action.get("choice") == "offer":
        return action["name"]
    if upgrading:
        promo = (moment.get("promo") or {}).get("name")
        if promo:
            return f"Upgrade now · {promo}"
        return f"Upgrade now · {moment['device_name']}"
    return "Do nothing"


def draft(account: dict, action: dict, moment: dict | None) -> dict:
    language = account["language"] if account["language"] in {"en", "es", "hi", "zh"} else "en"
    channel = account["contact_preference"]
    parts: list[str] = []
    purpose = "none"
    if action["choice"] == "offer":
        parts.append(_retention(language, account, action))
        purpose = "retention"
    if moment and moment.get("when") == "now" and moment.get("device_name"):
        parts.append(_upgrade(language, moment))
        purpose = "both" if purpose == "retention" else "upgrade"
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


def _promo_sentence(language: str, promo: dict | None) -> str:
    if not promo:
        return {
            "en": "No device promotion is eligible on a one-phone trade-in cart.",
            "es": "No device promotion is eligible on a one-phone trade-in cart.",
            "hi": "एक फ़ोन के ट्रेड-इन पर कोई डिवाइस प्रोमो लागू नहीं है।",
            "zh": "一部手机的以旧换新没有可用的设备优惠。",
        }[language]
    amount = _dollars(promo["savings_cents"])
    name = promo["name"]
    return {
        "en": (
            f"One device promo applies: {name} ({amount}). "
            "A second device promo cannot be stacked. "
            "The sandbox cart total does not subtract this; the net below does."
        ),
        "es": (
            f"One device promo applies: {name} ({amount}). "
            "A second device promo cannot be stacked. "
            "The sandbox cart total does not subtract this; the net below does."
        ),
        "hi": (
            f"एक डिवाइस प्रोमो लागू है: {name} ({amount})। "
            "दूसरा डिवाइस प्रोमो साथ नहीं जोड़ा जा सकता। "
            "सैंडबॉक्स कार्ट का कुल इसे नहीं घटाता; नीचे दिया नेट घटाता है।"
        ),
        "zh": (
            f"适用一项设备优惠：{name}（{amount}）。"
            "不能叠加第二项设备优惠。"
            "沙盒购物车总额没有减去这笔优惠；下面的净额已经减去。"
        ),
    }[language]


def _net_sentence(language: str, net: int | None) -> str:
    if net is None:
        return ""
    amount = _dollars(net)
    return {
        "en": f" Net after the payoff and that promo: {amount}.",
        "es": f" Net after the payoff and that promo: {amount}.",
        "hi": f" पेऑफ और उस प्रोमो के बाद नेट: {amount}।",
        "zh": f"还清余额并减去该优惠后的净额：{amount}。",
    }[language]


def _battery_sentence(language: str, note: str) -> str:
    if language in {"en", "es"}:
        return note
    match = re.search(
        r"Estimated battery health is (\d+)%\. The sandbox has no battery reading; "
        r"this assumes about ([0-9.]+) points lost per month of phone age, "
        r"with a floor of (\d+)%\.",
        note or "",
    )
    if not match:
        return ""
    pct, drop, floor = match.groups()
    if language == "hi":
        return (
            f"अनुमानित बैटरी सेहत {pct}% है। सैंडबॉक्स में बैटरी की रीडिंग नहीं है; "
            f"यह मानता है कि फ़ोन की उम्र के हर महीने लगभग {drop} अंक घटते हैं, "
            f"और न्यूनतम {floor}% है।"
        )
    return (
        f"估计电池健康度为{pct}%。沙盒没有电池读数；"
        f"这里假设手机每使用一个月大约下降{drop}个百分点，最低为{floor}%。"
    )


def _upgrade(language: str, moment: dict) -> str:
    language = language if language in {"en", "es", "hi", "zh"} else "en"
    promo = moment.get("promo")
    promo_sentence = _promo_sentence(language, promo if isinstance(promo, dict) else None)
    net_sentence = _net_sentence(language, moment.get("net_cents"))
    battery = _battery_sentence(language, moment.get("battery_note", ""))
    balance = int(moment["balance_cents"])
    owed = _dollars(balance)
    trade = _dollars(moment.get("tradein_value_cents"))
    device = moment["device_name"]
    age = moment["age_months"]
    if language == "es":
        payoff = (
            "No queda saldo, así que el canje no cobra un payoff hoy."
            if balance == 0
            else f"Aún debe {owed}. Si lo entregas hoy, ese saldo se cobra hoy."
        )
        return (
            f"{device} tiene {age} meses. {payoff} "
            f"El canje en condición buena es {trade}. "
            f"{promo_sentence}{net_sentence} {battery}"
        )
    if language == "hi":
        payoff = (
            "यह चुकाया जा चुका है, इसलिए ट्रेड-इन पर आज कोई पेऑफ नहीं लगता।"
            if balance == 0
            else f"इस पर अभी {owed} बकाया है। बिना चुकाए फ़ोन को ट्रेड-इन करने पर वह शेष राशि आज चार्ज होती है।"
        )
        return (
            f"{device} {age} महीने पुराना है। {payoff} "
            f"अच्छी स्थिति में ट्रेड-इन मूल्य {trade} है। "
            f"{promo_sentence}{net_sentence} {battery}"
        )
    if language == "zh":
        payoff = (
            "已经还清，所以今天以旧换新不会收取剩余余额。"
            if balance == 0
            else f"还剩{owed}未还清。用尚未还清的手机以旧换新，今天会收取这笔剩余余额。"
        )
        return (
            f"{device}已使用{age}个月。{payoff}"
            f"良好成色的以旧换新价值为{trade}。"
            f"{promo_sentence}{net_sentence} {battery}"
        )
    if balance == 0:
        payoff = "It is paid off, so a trade-in does not charge a payoff today."
    else:
        payoff = (
            f"It still has {owed} outstanding. "
            "Trading in an unpaid phone charges that remaining balance today."
        )
    return (
        f"{device} is {age} months old. {payoff} "
        f"Good-condition trade-in value is {trade}. "
        f"{promo_sentence}{net_sentence} {battery}"
    )
