"""Editable targeting rules. The first match wins. Change the order here, not in the screen.

Credit dollars in this file are an assumption. They are not a T-Mobile price.
"""

from __future__ import annotations

# Product setting. At most one outbound nudge per customer in this window.
FREQUENCY_CAP_DAYS = 30

# Assumption only. Shown in the UI as an assumption, never as a real offer price.
ASSUMPTION_CREDIT_CENTS = 2_500

# Bill jump uses the same 5% cutoff the overview uses on sandbox bills.
BILL_JUMP_PCT = 0.05

# Near the cap: usage at or above 90% of a finite cap, or already over it.
CAP_RATIO = 0.90

# Personas that must never receive an upgrade push.
UPGRADE_PUSH_BLOCKED = frozenset({"ACC-PERSONA-07", "ACC-PERSONA-31"})

# Happy frequent caller. Stays do-nothing even if a later rule would write.
DO_NOTHING_ACCOUNTS = frozenset({"ACC-PERSONA-24"})

# Value = monthly revenue x line weight x tenure weight.
# monthly revenue is the latest sandbox bill, in cents.
# line weight is 1 + 0.10 for each line after the first.
# tenure weight is min(tenure months, 60) / 60, so a brand-new account is not treated as high value.
VALUE_LINE_STEP = 0.10
VALUE_TENURE_CAP_MONTHS = 60
VALUE_HIGH_SHARE = 0.30  # top 30% of value_score is "high"

RISK_TOP = 0.10
RISK_MID = 0.30

VALUE_FORMULA = (
    "value_score = last_bill_cents x (1 + 0.10 x extra lines) x min(tenure_months, 60) / 60. "
    "last_bill_cents is the latest sandbox bill. High value is the top 30% of that score."
)

# Order is the product order. decide.py runs these ids from top to bottom.
RULES: tuple[dict, ...] = (
    {
        "id": "fix_first",
        "when": "Unresolved support issue in the last 90 days",
        "action": "FIX-FIRST",
        "offer": "No promo and no upgrade",
        "channel": "support callback",
        "template": "fix_first",
    },
    {
        "id": "retention",
        "when": "Port-out inquiry, or a high-risk band and high value",
        "action": "RETENTION",
        "offer": "Best eligible sandbox retention promo, else an assumption credit on high value only",
        "channel": "account contact preference",
        "template": "retention",
    },
    {
        "id": "explain_bill",
        "when": "Latest bill is more than 5% above the prior average",
        "action": "EXPLAIN THE BILL",
        "offer": "A cheaper catalog plan only when the price is actually lower",
        "channel": "account contact preference",
        "template": "explain_bill",
    },
    {
        "id": "plan_fit",
        "when": "Usage is near or over a finite data cap",
        "action": "PLAN FIT",
        "offer": "A real catalog plan that covers the usage, before any device",
        "channel": "account contact preference",
        "template": "plan_fit",
    },
    {
        "id": "upgrade_timing",
        "when": "Phone is paid off, or owned 12 months or more",
        "action": "UPGRADE TIMING",
        "offer": "Upgrade now, wait, or keep. One device promo at most, and never for personas 07 and 31",
        "channel": "account contact preference",
        "template": "upgrade_timing",
    },
    {
        "id": "promo_expired",
        "when": "A promo expired in the last 3 billing months, and a real promo is still eligible",
        "action": "RE-OFFER",
        "offer": "One eligible sandbox promo. Skipped for the low-risk band",
        "channel": "account contact preference",
        "template": "promo_expired",
    },
    {
        "id": "do_nothing",
        "when": "Low risk and no trigger, including the happy-caller trap",
        "action": "DO NOTHING",
        "offer": "No message",
        "channel": "none",
        "template": "do_nothing",
    },
)

TEMPLATES = {
    "fix_first": {
        "en": "We're sorry this is still open. We'll resolve the support issue first. There is no offer and no upgrade in this message.",
        "es": "Lamentamos que esto siga abierto. Primero resolveremos el caso de soporte. Este mensaje no incluye una oferta ni un cambio de equipo.",
    },
    "retention": {
        "en": "We want to keep you. {offer_line}",
        "es": "Queremos que te quedes. {offer_line}",
    },
    "explain_bill": {
        "en": "Your latest bill is higher than the earlier months. {offer_line}",
        "es": "Tu última factura es más alta que los meses anteriores. {offer_line}",
    },
    "plan_fit": {
        "en": "Your recent usage is tight against the data cap. {offer_line}",
        "es": "Tu uso reciente está cerca del límite de datos. {offer_line}",
    },
    "upgrade_timing": {
        "en": "{offer_line}",
        "es": "{offer_line}",
    },
    "promo_expired": {
        "en": "A recent promotion ended. {offer_line}",
        "es": "Una promoción reciente terminó. {offer_line}",
    },
    "do_nothing": {
        "en": "No message: nothing would help them right now.",
        "es": "Sin mensaje: ahora mismo nada les ayudaría.",
    },
}
