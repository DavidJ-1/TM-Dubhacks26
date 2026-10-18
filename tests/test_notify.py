"""Each send backend. requests is mocked, and no customer number is passed."""

import os
from pathlib import Path

import requests

from harness.notify import default_topic, load_project_env, send


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
    assert captured["headers"]["Content-Type"] == "text/plain; charset=utf-8"
    assert captured["headers"]["Title"] == "Draft"
    captured["headers"]["Title"].encode("latin-1")
    assert captured["timeout"] == 5
    assert b"phone" not in captured["data"]

    _block_network(monkeypatch)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    fallback = send("Draft only")
    assert fallback["backend"] == "dryrun"
    assert fallback["sent"] is False
    assert fallback["message"] == "Draft only"
    assert "NTFY_TOPIC" in fallback["hint"]


def test_ntfy_topic_argument_does_not_need_the_env(monkeypatch):
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return _Response()

    monkeypatch.delenv("SEND_BACKEND", raising=False)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.setattr(requests, "post", fake_post)
    result = send("Draft", backend="ntfy", topic="tm-dubhacks26-lf3reo19tv")
    assert result["sent"] is True
    assert captured["url"] == "https://ntfy.sh/tm-dubhacks26-lf3reo19tv"
    assert b"phone" not in captured["data"]


def test_missing_env_file_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("SEND_BACKEND", "dryrun")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert load_project_env(tmp_path / "missing.env") is False
    assert os.environ["SEND_BACKEND"] == "dryrun"
    assert "NTFY_TOPIC" not in os.environ


def test_process_env_beats_dotenv_and_file_fills_the_rest(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SEND_BACKEND=ntfy\nNTFY_TOPIC=from-file\n", encoding="utf-8")
    monkeypatch.setenv("SEND_BACKEND", "dryrun")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert load_project_env(env_file) is True
    assert os.environ["SEND_BACKEND"] == "dryrun"
    assert os.environ["NTFY_TOPIC"] == "from-file"


def test_dotenv_is_used_when_the_process_env_is_unset(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SEND_BACKEND=ntfy\nNTFY_TOPIC=topic-from-file\n", encoding="utf-8")
    monkeypatch.delenv("SEND_BACKEND", raising=False)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert load_project_env(env_file) is True

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return _Response()

    monkeypatch.setattr(requests, "post", fake_post)
    result = send("From the env file")
    assert result["sent"] is True
    assert captured["url"] == "https://ntfy.sh/topic-from-file"
    assert b"phone" not in captured["data"]


def test_notify_has_no_builtin_topic(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert default_topic() == ""
    assert "DEFAULT_TOPIC" not in Path(__file__).resolve().parents[1].joinpath("harness", "notify.py").read_text()


def test_dryrun_keeps_hindi_and_chinese(monkeypatch):
    _block_network(monkeypatch)
    monkeypatch.delenv("SEND_BACKEND", raising=False)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    text = "नमस्ते। अगले बिल पर $25.00 का क्रेडिट है।\n您好。下一期账单有$25.00的信用金。"
    result = send(text)
    assert result["ok"] is True
    assert result["backend"] == "dryrun"
    assert result["sent"] is False
    assert result["message"] == text
    assert "cents" not in result["message"].lower()


def test_ntfy_posts_utf8_and_keeps_headers_ascii(monkeypatch):
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return _Response()

    monkeypatch.delenv("SEND_BACKEND", raising=False)
    monkeypatch.setattr(requests, "post", fake_post)
    text = "हिन्दी $10.00 और 中文 $10.00"
    result = send(text, backend="ntfy", topic="tm-dubhacks26-lf3reo19tv", title="हिन्दी")
    assert result["sent"] is True
    assert captured["data"] == text.encode("utf-8")
    assert captured["headers"]["Content-Type"] == "text/plain; charset=utf-8"
    title = captured["headers"]["Title"]
    title.encode("latin-1")
    assert "हिन्दी" not in title
    assert title.startswith("=?utf-8?")
