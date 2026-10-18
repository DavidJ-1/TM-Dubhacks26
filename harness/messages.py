"""Template drafts. No network call. The offer decision is already made before this runs."""

from __future__ import annotations

import html


def _dollars(cents: int | None) -> str:
    if cents is None:
        return "n/a"
    return f"${cents / 100:,.2f}"


def draft(account: dict, action: dict, moment: dict | None) -> dict:
    language = account["language"] if account["language"] in {"en", "es"} else "en"
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
    if language == "es":
        if sku == "PROMO-STUB-CARE-CREDIT":
            bill = ""
            if float(account["bill_increase_pct"]) > 0.05:
                bill = f" Tu último recibo subió {float(account['bill_increase_pct']) * 100:.0f}% frente al promedio anterior."
            return (
                f"Hola. Vimos {int(account['support_90d'])} contactos con soporte en los últimos 90 días.{bill} "
                "Hay un crédito de cuidado de $25.00 en tu próximo recibo. No cambia tu plan."
            )
        if sku == "PROMO-STUB-LOYALTY-CREDIT":
            return (
                f"Hola. Llevas {int(account['tenure_months'])} meses con nosotros. "
                "Hay un crédito de lealtad de $5.00 al mes en la cuenta. No cambia tu plan ni tu teléfono."
            )
        return (
            "Hola. El crédito de estudiante de $20.00 al mes por línea está disponible en esta cuenta, hasta 2 líneas."
        )
    if sku == "PROMO-STUB-CARE-CREDIT":
        bill = ""
        if float(account["bill_increase_pct"]) > 0.05:
            bill = (
                f" The latest bill is {float(account['bill_increase_pct']) * 100:.0f}% "
                "above the prior-month average."
            )
        return (
            f"We saw {int(account['support_90d'])} support contacts in the last 90 days.{bill} "
            "A $25.00 care credit is on the next bill. It does not change the plan."
        )
    if sku == "PROMO-STUB-LOYALTY-CREDIT":
        return (
            f"You have been on this account for {int(account['tenure_months'])} months. "
            "A $5.00 per month loyalty credit is available. It does not change the plan or the phone."
        )
    return "A student credit of $20.00 per line per month is available on this account, up to 2 lines."


def _upgrade(language: str, moment: dict) -> str:
    promo = moment.get("promo")
    promo_sentence = "No device promotion is eligible on a one-phone trade-in cart."
    if promo:
        promo_sentence = (
            f"One device promo applies: {promo['name']} ({_dollars(promo['savings_cents'])}). "
            "A second device promo cannot be stacked. "
            "The sandbox cart total does not subtract this; the net below does."
        )
    net = moment.get("net_cents")
    net_sentence = "" if net is None else f" Net after the payoff and that promo: {_dollars(net)}."
    battery = moment.get("battery_note", "")
    balance = int(moment["balance_cents"])
    if language == "es":
        payoff = (
            "No queda saldo, así que el canje no cobra un payoff hoy."
            if balance == 0
            else f"Aún debe {_dollars(balance)}. Si lo entregas hoy, ese saldo se cobra hoy."
        )
        return (
            f"{moment['device_name']} tiene {moment['age_months']} meses. {payoff} "
            f"El canje en condición buena es {_dollars(moment.get('tradein_value_cents'))}. "
            f"{promo_sentence}{net_sentence} {battery}"
        )
    if balance == 0:
        payoff = "It is paid off, so a trade-in does not charge a payoff today."
    else:
        payoff = (
            f"It still has {_dollars(balance)} outstanding. "
            "Trading in an unpaid phone charges that remaining balance today."
        )
    return (
        f"{moment['device_name']} is {moment['age_months']} months old. {payoff} "
        f"Good-condition trade-in value is {_dollars(moment.get('tradein_value_cents'))}. "
        f"{promo_sentence}{net_sentence} {battery}"
    )
