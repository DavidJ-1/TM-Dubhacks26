"""Deterministic en/es SMS templates (tm-ui lane). The engine picks the action; this only words it."""
from __future__ import annotations

ACTION_LABELS = {
    "do_nothing": ("Do nothing", "No hacer nada"),
    "care_credit_25": ("$25/mo care credit", "Crédito de cortesía de $25/mes"),
    "loyalty_credit": ("Loyalty credit", "Crédito de lealtad"),
    "keep_phone_credit": ("Keep-your-phone credit", "Crédito por conservar tu teléfono"),
    "right_size_plan": ("Right-size plan", "Ajustar plan"),
    "step_up_plan": ("Step-up plan", "Mejorar plan"),
    "device_upgrade": ("Device upgrade", "Cambio de teléfono"),
    "fix_first_callback": ("Fix-first callback", "Llamada para resolver primero"),
    "care_credit_fix_first": ("$25 care credit + fix-first callback", "Crédito de $25 + llamada para resolver"),
}

# Accept human-readable action strings from tm-offers too.
_ALIASES = {
    "do nothing": "do_nothing", "none": "do_nothing", "no offer": "do_nothing",
    "$25 care credit": "care_credit_25", "care credit": "care_credit_25", "care_credit": "care_credit_25",
    "loyalty credit": "loyalty_credit", "keep-your-phone credit": "keep_phone_credit",
    "keep your phone credit": "keep_phone_credit", "keep_your_phone_credit": "keep_phone_credit",
    "right-size plan": "right_size_plan", "right size plan": "right_size_plan", "right_size": "right_size_plan",
    "step-up plan": "step_up_plan", "step up plan": "step_up_plan", "step_up": "step_up_plan",
    "device upgrade": "device_upgrade", "fix-first callback": "fix_first_callback",
    "fix first callback": "fix_first_callback", "fix_first": "fix_first_callback",
    # tm-offers action_code values (aliases above already cover right_size / step_up)
    "keep_your_phone": "keep_phone_credit",
}


def normalize_action(a) -> str:
    s = str(a or "").strip()
    if s in ACTION_LABELS:
        return s
    return _ALIASES.get(s.lower(), s.lower().replace(" ", "_").replace("-", "_") or "do_nothing")


def action_label(a, lang: str = "en") -> str:
    k = normalize_action(a)
    en, es = ACTION_LABELS.get(k, (str(a), str(a)))
    return es if lang == "es" else en


TEMPLATES = {
    "care_credit_25": (
        "T-Mobile: Hi! We noticed your bill went up after a promo ended. We've added a $25/mo credit for the next 6 months. No action needed. Questions? Reply HELP.",
        "T-Mobile: ¡Hola! Notamos que tu factura subió al terminar una promoción. Agregamos un crédito de $25/mes por los próximos 6 meses. No necesitas hacer nada. ¿Preguntas? Responde AYUDA.",
    ),
    "loyalty_credit": (
        "T-Mobile: Thanks for {years} with us! As a thank-you, we've added a $5/mo loyalty credit to your account for the next year.",
        "T-Mobile: ¡Gracias por {years_es} con nosotros! Como agradecimiento, agregamos un crédito de lealtad de $5/mes a tu cuenta durante el próximo año.",
    ),
    "keep_phone_credit": (
        "T-Mobile: Your phone is paid off. Nice! Keep it and get a $20/mo credit. No new contract. Reply YES to add it.",
        "T-Mobile: Tu teléfono ya está pagado. ¡Bien! Consérvalo y recibe un crédito de $20/mes. Sin contrato nuevo. Responde SI para agregarlo.",
    ),
    "right_size_plan": (
        "T-Mobile: Looks like you use less than your plan includes. A plan that fits could save you money each month. Want us to show you? Reply YES.",
        "T-Mobile: Parece que usas menos de lo que incluye tu plan. Un plan a tu medida podría ahorrarte dinero cada mes. ¿Te mostramos? Responde SI.",
    ),
    "step_up_plan": (
        "T-Mobile: Your data use has grown a lot lately. A plan with more high-speed data and hotspot may fit better. See options in T-Life or reply INFO.",
        "T-Mobile: Tu uso de datos ha crecido mucho. Un plan con más datos de alta velocidad y hotspot podría quedarte mejor. Mira opciones en T-Life o responde INFO.",
    ),
    "device_upgrade": (
        "T-Mobile: Your phone is over 3 years old. You may qualify for an upgrade credit with trade-in. See your offer in T-Life or reply INFO.",
        "T-Mobile: Tu teléfono tiene más de 3 años. Podrías calificar para un crédito de cambio con intercambio. Mira tu oferta en T-Life o responde INFO.",
    ),
    "care_credit_fix_first": (
        "T-Mobile: We're sorry for the trouble lately. We've added a $25/mo credit for the next 6 months, and a specialist will call you within 24 hours to fix the open issue. Reply TIME to pick a time.",
        "T-Mobile: Lamentamos los problemas recientes. Agregamos un crédito de $25/mes por los próximos 6 meses y un especialista te llamará en 24 horas para resolver el problema. Responde HORA para elegir un horario.",
    ),
    "fix_first_callback": (
        "T-Mobile: Sorry about the coverage trouble. A network specialist will call you within 24 hours to fix it. Reply TIME to pick a time.",
        "T-Mobile: Lamentamos los problemas de cobertura. Un especialista de red te llamará en 24 horas para resolverlo. Responde HORA para elegir un horario.",
    ),
}


def render_message(action, lang: str = "en", tenure_months: int | None = None) -> str | None:
    k = normalize_action(action)
    if k == "do_nothing" or k not in TEMPLATES:
        return None
    en, es = TEMPLATES[k]
    y = max(1, int((tenure_months or 12) // 12))
    return (es if lang == "es" else en).format(
        years=f"{y} year{'s' if y != 1 else ''}", years_es=f"{y} año{'s' if y != 1 else ''}")
