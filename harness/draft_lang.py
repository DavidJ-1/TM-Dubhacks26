"""Language labels for the on-screen text draft. Send uses one of these at a time."""

LANGUAGES = (
    ("en", "English"),
    ("es", "Español"),
    ("hi", "हिन्दी"),
    ("zh", "中文"),
)


def clean_draft(text: object) -> str:
    if text is None:
        return ""
    value = str(text).strip()
    if not value or value.lower() == "nan":
        return ""
    return value


def selected_draft(texts: dict[str, str], label: str) -> str:
    code = next(code for code, name in LANGUAGES if name == label)
    return clean_draft(texts.get(code))
