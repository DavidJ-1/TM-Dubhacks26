"""English, Spanish, Hindi, and Simplified Chinese on every draft we show."""

import re
from pathlib import Path

import pandas as pd

from harness.draft_lang import LANGUAGES, selected_draft
from harness.messages import draft
from harness.saved_sms import hindi_and_chinese

ROOT = Path(__file__).resolve().parents[1]
_CENTS = re.compile(r"\bcents\b", re.IGNORECASE)
_MONEY = re.compile(r"-?\$[0-9][0-9,]*(?:\.[0-9]+)?")


def _devanagari(text: str) -> bool:
    return any("\u0900" <= char <= "\u097f" for char in text)


def _cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def test_saved_landing_drafts_have_hindi_and_chinese():
    offers = pd.read_csv(ROOT / "demo_data" / "offers.csv")
    seen = 0
    for english in offers["message_en"].dropna().astype(str).unique():
        if not english.strip() or english.strip().lower() == "nan":
            continue
        hindi, chinese = hindi_and_chinese(english)
        seen += 1
        assert _devanagari(hindi)
        assert _cjk(chinese)
        assert _CENTS.search(hindi) is None
        assert _CENTS.search(chinese) is None
        for amount in _MONEY.findall(english):
            assert amount in hindi
            assert amount in chinese
    assert seen > 100
    assert hindi_and_chinese("") == ("", "")
    assert hindi_and_chinese("nan") == ("", "")
    persona = offers.loc[offers["account_id"] == "ACC-PERSONA-24"].iloc[0]
    assert hindi_and_chinese(str(persona["message_en"])) == ("", "")


def test_console_draft_has_four_languages_and_keeps_names():
    account = {
        "language": "en",
        "contact_preference": "sms",
        "support_90d": 4,
        "bill_increase_pct": 0.12,
        "tenure_months": 30,
    }
    action = {"choice": "offer", "sku": "PROMO-STUB-CARE-CREDIT", "name": "Care", "why": "support"}
    moment = {
        "when": "now",
        "device_name": "Galaxy S23",
        "age_months": 20,
        "balance_cents": 12000,
        "tradein_value_cents": 8000,
        "net_cents": 4000,
        "promo": {"name": "Trade in any phone, any condition.", "savings_cents": 2500},
        "battery_note": (
            "Estimated battery health is 80%. The sandbox has no battery reading; "
            "this assumes about 1.5 points lost per month of phone age, with a floor of 70%."
        ),
    }
    texts = {}
    for code, _label in LANGUAGES:
        texts[code] = draft({**account, "language": code}, action, moment)["text"]
        assert texts[code]
        assert _CENTS.search(texts[code]) is None
        assert "$25.00" in texts[code]
        assert "Galaxy S23" in texts[code]
        assert "Trade in any phone, any condition." in texts[code]
        assert "$120.00" in texts[code]
        assert "$40.00" in texts[code]
    assert _devanagari(texts["hi"])
    assert _cjk(texts["zh"])
    assert "केयर क्रेडिट" in texts["hi"]
    assert "关怀信用金" in texts["zh"]
    assert "crédito de cuidado" in texts["es"]
    nothing = {"choice": "nothing", "sku": "", "why": "Happy-caller trap: this account stays do nothing."}
    for code, _label in LANGUAGES:
        assert draft({**account, "language": code}, nothing, None)["text"] is None


def test_send_uses_only_the_selected_language():
    texts = {"en": "English $10.00", "es": "Español $10.00", "hi": "हिन्दी $10.00", "zh": "中文 $10.00"}
    assert [name for _code, name in LANGUAGES] == ["English", "Español", "हिन्दी", "中文"]
    assert selected_draft(texts, "हिन्दी") == "हिन्दी $10.00"
    assert "English" not in selected_draft(texts, "中文")
    assert selected_draft({"en": "nan", "es": "", "hi": None, "zh": "  "}, "English") == ""


def test_language_picker_is_on_the_draft_and_do_nothing_phrase_stays():
    source = (ROOT / "app" / "console_app.py").read_text()
    labels = (ROOT / "harness" / "draft_lang.py").read_text()
    panel = source.split("def text_we_would_send", 1)[1].split("\ndef ", 1)[0]
    for label in ("English", "Español", "हिन्दी", "中文"):
        assert label in labels
    assert "LANGUAGES" in panel
    assert 'st.radio("Language"' in panel
    assert "No message sent, here's why" in panel
    demo = (ROOT / "app" / "demo_app.py").read_text()
    assert "hindi_and_chinese" in demo
    grow = source.split("def upgrades_page", 1)[1]
    assert "message_hi" in grow and "message_zh" in grow
    assert "No message sent, here's why" in grow
