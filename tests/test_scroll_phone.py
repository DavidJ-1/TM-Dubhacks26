"""Send to customer on the scroll page. Dry-run only: requests.post must not run."""
from __future__ import annotations

import html
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

import orbit_sections as O  # noqa: E402


def _open(at, account_id: str, step: int, lang: str | None = None):
    at.session_state["orbit_last_acc"] = account_id
    at.session_state["orbit_step"] = step
    if lang:
        at.session_state[f"orbit_lang_{account_id}"] = lang
    return at.run()


def test_drafts_keep_only_languages_that_exist():
    r = pd.Series({
        "message_en": "Hello",
        "message_es": "Hola",
        "message_hi": "नमस्ते",
        "message_zh": "您好",
    })
    drafts = O._drafts(r, None)
    assert list(drafts) == ["EN", "ES", "HI", "ZH"]
    assert "नमस्ते" in drafts["HI"] and "您好" in drafts["ZH"]
    assert O._drafts(pd.Series({"message_en": "  ", "message_es": ""}), None) == {}
    html = O._message_html(r, None, "ZH")
    assert "您好" in html and "Hello" not in html


def test_do_nothing_copy_has_no_send():
    from streamlit.testing.v1 import AppTest

    def page():
        import pandas as pd
        import orbit_sections as sections

        df = pd.DataFrame([{
            "account_id": "ACC-00347",
            "p_churn_90d": 0.0021,
            "segment": "single",
            "tenure_months": 40,
            "n_lines": 1,
            "messaged": False,
            "channel": None,
            "message_en": "",
            "message_es": "",
            "reason_line": "Nothing we could offer is likely to pay off.",
            "language": "en",
            "receipt_line_en": "",
        }])
        sections.render_customer(df, "ACC-00347", key="orbit")

    at = _open(AppTest.from_function(page), "ACC-00347", 4)
    text = html.unescape(" ".join(m.value for m in at.markdown))
    assert "No message sent, here's why" in text
    assert "likely to pay off" in text
    assert not any(b.label == "Send to customer" for b in at.button)

    at3 = _open(AppTest.from_function(page), "ACC-00347", 3)
    text3 = html.unescape(" ".join(m.value for m in at3.markdown))
    assert "No message sent, here's why" in text3
    assert not any(b.label == "Send to customer" for b in at3.button)


def test_send_button_posts_the_shown_language_as_dryrun(monkeypatch):
    import requests
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("SEND_BACKEND", "dryrun")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)

    def boom(*_a, **_k):
        raise AssertionError("network was called")

    monkeypatch.setattr(requests, "post", boom)
    seen = {}
    import harness.notify as notify
    real = notify.send_sms

    def wrapped(body, to=None):
        seen["body"] = body
        seen["to"] = to
        return real(body, to)

    monkeypatch.setattr(notify, "send_sms", wrapped)

    def page():
        import pandas as pd
        import orbit_sections as sections

        df = pd.DataFrame([{
            "account_id": "ACC-01607",
            "p_churn_90d": 0.742,
            "segment": "family",
            "tenure_months": 36,
            "n_lines": 2,
            "messaged": True,
            "channel": "text",
            "message_en": "We'll help fix it. A one-time $25 credit is on the way.",
            "message_es": "Lo arreglamos. Hay un crédito único de $25.",
            "message_hi": "हिन्दी ड्राफ्ट",
            "message_zh": "中文草稿",
            "reason_line": "Open ticket, so the message is a fix.",
            "language": "en",
            "receipt_line_en": "",
        }])
        sections.render_customer(df, "ACC-01607", key="orbit")

    at = _open(AppTest.from_function(page), "ACC-01607", 4, lang="ES")
    assert any(b.label == "Send to customer" for b in at.button)
    assert any("Lo arreglamos" in m.value for m in at.markdown)
    assert any("ntfy" in c.value and "demo phone" in c.value for c in at.caption)
    at = next(b for b in at.button if b.label == "Send to customer").click().run()
    assert seen["body"] == "Lo arreglamos. Hay un crédito único de $25."
    assert seen["to"] is None
    assert any("Preview only" in t.value and "customer" in t.value for t in at.toast)

    at_hi = _open(AppTest.from_function(page), "ACC-01607", 4, lang="HI")
    assert any("हिन्दी" in m.value for m in at_hi.markdown)
    at_hi = next(b for b in at_hi.button if b.label == "Send to customer").click().run()
    assert seen["body"] == "हिन्दी ड्राफ्ट"
    assert any("Preview only" in t.value and "customer" in t.value for t in at_hi.toast)
