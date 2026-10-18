"""sms_send: unconfigured, dry-run and mocked-webhook paths. Never sends a real message."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
import sms_send  # noqa: E402

ENV_KEYS = [
    "TM_SMS_PROVIDER", "TM_DEMO_PHONE", "TM_SMS_DRY_RUN", "TM_SMS_WEBHOOK_URL",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM",
]
FAKE_PHONE = "5555550100"  # fictional 555-01xx number


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)

    def _no_network(*a, **k):
        raise AssertionError("network call attempted in test")

    monkeypatch.setattr(sms_send.urllib.request, "urlopen", _no_network)
    monkeypatch.setattr(sms_send.smtplib, "SMTP", _no_network)
    monkeypatch.setattr(sms_send.smtplib, "SMTP_SSL", _no_network)


def test_unconfigured():
    assert sms_send.is_configured() is False
    r = sms_send.send_sms("hello")
    assert r == {"ok": False, "provider": None, "detail": "SMS sender not configured"}


def test_missing_provider_env_is_not_configured(monkeypatch):
    monkeypatch.setenv("TM_SMS_PROVIDER", "twilio")
    monkeypatch.setenv("TM_DEMO_PHONE", FAKE_PHONE)
    assert sms_send.is_configured() is False
    r = sms_send.send_sms("hello")
    assert r["ok"] is False and "TWILIO_AUTH_TOKEN" in r["detail"]


def test_dry_run(monkeypatch):
    monkeypatch.setenv("TM_SMS_DRY_RUN", "1")
    monkeypatch.setenv("TM_DEMO_PHONE", FAKE_PHONE)
    assert sms_send.is_configured() is True
    r = sms_send.send_sms("hello there")
    assert r["ok"] is True and "DRY RUN" in r["detail"] and "0100" in r["detail"]
    assert FAKE_PHONE not in r["detail"]  # number is masked


def test_normalize():
    assert sms_send._normalize("555-555-0100") == "+15555550100"
    assert sms_send._normalize("+1 (555) 555 0100") == "+15555550100"
    assert sms_send._normalize("12345") is None


def test_webhook_mocked(monkeypatch):
    monkeypatch.setenv("TM_SMS_PROVIDER", "webhook")
    monkeypatch.setenv("TM_SMS_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setenv("TM_DEMO_PHONE", FAKE_PHONE)
    captured = {}

    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def getcode(self): return 200

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return Resp()

    monkeypatch.setattr(sms_send.urllib.request, "urlopen", fake_urlopen)
    body = "Hi there. Same features, $110/month instead of $150.\nReply STOP to opt out."
    assert sms_send.is_configured() is True
    r = sms_send.send_sms(body)
    assert r["ok"] is True and r["provider"] == "webhook"
    assert captured["url"] == "https://example.invalid/hook"
    assert captured["payload"] == {"to": "+15555550100", "body": body}  # exact body


def test_webhook_error_never_raises(monkeypatch):
    monkeypatch.setenv("TM_SMS_PROVIDER", "webhook")
    monkeypatch.setenv("TM_SMS_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setenv("TM_DEMO_PHONE", FAKE_PHONE)

    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(sms_send.urllib.request, "urlopen", boom)
    r = sms_send.send_sms("hello")
    assert r["ok"] is False and "connection refused" in r["detail"]


def test_persona_38_message_and_cli_dry_run(monkeypatch, capsys):
    msg = sms_send.persona_message("38")
    assert msg and msg.startswith("Hi there.")
    assert sms_send.persona_message("ACC-PERSONA-38") == msg
    monkeypatch.setenv("TM_DEMO_PHONE", FAKE_PHONE)
    rc = sms_send.main(["--persona", "38", "--dry-run"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["ok"] is True and f"{len(msg)} chars" in out["detail"]
