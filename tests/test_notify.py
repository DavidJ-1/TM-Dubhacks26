"""Each send backend. requests is mocked, and no customer number is passed."""

import requests

from harness.notify import send


def _block_network(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("network was called")

    monkeypatch.setattr(requests, "post", boom)


def test_dryrun_returns_the_message_and_sends_nothing(monkeypatch):
    _block_network(monkeypatch)
    monkeypatch.delenv("SEND_BACKEND", raising=False)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    seen = {}
    real = __import__("harness.sms_send", fromlist=["send_sms"]).send_sms

    def wrapped(body, to=None):
        seen["body"] = body
        seen["to"] = to
        return real(body, to)

    monkeypatch.setattr("harness.notify.send_sms", wrapped)
    result = send("We want to keep you.")
    assert result["backend"] == "dryrun"
    assert result["sent"] is False
    assert result["message"] == "We want to keep you."
    assert seen["body"] == "We want to keep you."
    assert seen["to"] is None
    assert "DRY RUN" in result["detail"]


def test_ntfy_posts_plain_text_to_the_topic(monkeypatch):
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setenv("SEND_BACKEND", "ntfy")
    monkeypatch.setenv("NTFY_TOPIC", "tm-dubhacks26-lf3reo19tv")
    monkeypatch.setattr(requests, "post", fake_post)
    result = send("We want to keep you.")
    assert result["ok"] is True
    assert result["backend"] == "ntfy"
    assert result["sent"] is True
    assert captured["url"] == "https://ntfy.sh/tm-dubhacks26-lf3reo19tv"
    assert captured["data"] == b"We want to keep you."
    assert captured["headers"] == {"Content-Type": "text/plain"}
    assert captured["timeout"] == 5
    assert b"phone" not in captured["data"]

    _block_network(monkeypatch)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    fallback = send("Draft only")
    assert fallback["backend"] == "dryrun"
    assert fallback["sent"] is False
    assert fallback["message"] == "Draft only"
    assert "NTFY_TOPIC" in fallback["hint"]
