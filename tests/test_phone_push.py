"""phone_push: dry run default, zero network in dry run, live flag without topic -> dry run, topic masked.
Never posts: requests/urllib/notify network paths are patched to fail the test if touched."""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import phone_push as pp  # noqa: E402

TOPIC = "private-test-topic-abc123xyz-0123456789abcd"  # >= 32 chars
BODY = "Hi there. Your plan has a 5-Year Price Guarantee. Reply STOP to opt out."


@pytest.fixture(autouse=True)
def guard(monkeypatch, tmp_path):
    for k in ("TM_SEND_LIVE", "NTFY_TOPIC", "SEND_BACKEND", "TM_OUT_DIR", "TM_PHONE_BACKEND",
              "TELEGRAM_BOT_TOKEN", "TM_TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TM_SEND_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(pp, "ROOT", tmp_path)  # no real .env
    pp._last.clear()

    def boom(*a, **k):
        raise AssertionError("network call attempted")

    for name in ("post", "get", "request"):
        monkeypatch.setattr(requests, name, boom)
    monkeypatch.setattr(requests.Session, "request", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    return tmp_path / "log.jsonl"


def test_dry_run_default_exact_payload_and_log(guard):
    r = pp.send_to_my_phone(BODY, "ACC-X", "en")
    assert r["ok"] and r["mode"] == "dry-run" and r["sent"] is False
    assert r["preview"]["text"] == BODY  # exactly the engine text, no prefix
    assert "synthetic" not in r["preview"]["text"].lower()
    log = [json.loads(x) for x in guard.read_text().splitlines()]
    assert log[-1]["event"] == "dry-run" and log[-1]["text"] == r["preview"]["text"]


def test_topic_alone_without_live_flag_is_dry(monkeypatch, guard):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    monkeypatch.setenv("SEND_BACKEND", "ntfy")  # notify.py would post here; we must not
    r = pp.send_to_my_phone(BODY)
    assert r["mode"] == "dry-run" and not r["sent"]
    assert TOPIC not in json.dumps(r) + guard.read_text()  # masked in UI payload and log
    assert r["preview"]["topic_masked"].startswith("pri…")


def test_live_flag_without_topic_falls_back(monkeypatch):
    monkeypatch.setenv("TM_SEND_LIVE", "1")
    r = pp.send_to_my_phone(BODY)
    assert r["ok"] and r["mode"] == "dry-run" and "NTFY_TOPIC" in r["detail"]


def test_dry_run_never_imports_notify(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    sys.modules.pop("harness.notify", None)
    pp.send_to_my_phone(BODY)
    assert "harness.notify" not in sys.modules


def test_live_path_calls_notify_once_with_masked_output(monkeypatch, guard):
    calls = []
    import types
    fake = types.SimpleNamespace(send=lambda msg, backend=None, topic=None: calls.append((msg, backend, topic))
                                 or {"ok": True, "sent": True, "detail": f"Sent to {topic}."})
    monkeypatch.setitem(sys.modules, "harness.notify", fake)
    import harness
    monkeypatch.setattr(harness, "notify", fake, raising=False)
    monkeypatch.setenv("TM_SEND_LIVE", "1")
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    r = pp.send_to_my_phone(BODY, "ACC-X", "en")
    assert r["sent"] and calls == [(BODY, "ntfy", TOPIC)]
    assert TOPIC not in json.dumps(r) + guard.read_text()
    assert pp.send_to_my_phone(BODY, "ACC-X", "en")["sent"] is False and len(calls) == 1  # double click


def test_empty_and_overlong_refused():
    assert pp.send_to_my_phone("  ")["ok"] is False
    assert pp.send_to_my_phone("x" * 2000)["ok"] is False


def test_engine_text_and_cli(tmp_path, capsys):
    p = tmp_path / "offers.csv"
    p.write_text("account_id,action_code,message_en,message_es\nACC-PERSONA-38,v,Hello en,Hola es\n"
                 "ACC-PERSONA-24,do_nothing,,\n")
    assert pp.engine_text("38", "es", p) == "Hola es"
    assert pp.engine_text("ACC-PERSONA-24", "en", p) is None
    assert pp.main(["--account", "38", "--offers", str(p)]) == 0
    assert json.loads(capsys.readouterr().out)["preview"]["text"] == "Hello en"


def test_notify_has_no_hardcoded_topic():
    src = (Path(__file__).resolve().parents[1] / "harness" / "notify.py").read_text()
    assert "DEFAULT_TOPIC" not in src
    assert re.findall(r"ntfy\.sh/[^\"'\s]*", src) == ["ntfy.sh/{topic}"]  # only URL: built from an explicit topic
    assert not re.search(r"=\s*[\"']tm-", src)  # no topic-like string literal


def test_notify_without_topic_never_posts(monkeypatch):
    monkeypatch.setenv("SEND_BACKEND", "ntfy")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    from harness import notify  # network is patched to fail in the autouse fixture
    monkeypatch.delenv("NTFY_TOPIC", raising=False)  # in case a local .env set it at import
    assert notify.default_topic() == ""
    assert notify.will_send() is False
    r = notify.send("hello")
    assert r["sent"] is False and r["backend"] == "dryrun"


def test_env_example_topic_blank():
    ex = Path(__file__).resolve().parents[1] / ".env.example"
    for line in ex.read_text().splitlines():
        if line.strip().startswith("NTFY_TOPIC"):
            assert line.split("=", 1)[1].strip() == ""


# ---------- telegram backend + hardening ----------
TOKEN = "123456789:AAH-fake_token_for_tests_only_0123456789"
CHAT = "987654321"


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _arm_tg(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TM_TELEGRAM_CHAT_ID", CHAT)


def test_telegram_configured_but_not_armed_is_dry_and_masked(monkeypatch, guard):
    _arm_tg(monkeypatch)
    r = pp.send_to_my_phone(BODY, "ACC-X", "en")
    assert r["mode"] == "dry-run" and not r["sent"] and r["preview"]["backend"] == "telegram"
    blob = json.dumps(r) + guard.read_text()
    assert TOKEN not in blob and CHAT not in blob
    assert "Telegram" not in r["preview"]["to"] and "ntfy" not in r["preview"]["to"]  # no vendor name on screen


def test_telegram_live_sends_exact_text_to_locked_chat_once(monkeypatch, guard):
    _arm_tg(monkeypatch)
    monkeypatch.setenv("TM_SEND_LIVE", "1")
    sent = []

    def fake_urlopen(req, timeout=None):
        sent.append((req.full_url, json.loads(req.data)))
        return _Resp({"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    r = pp.send_to_my_phone(BODY, "ACC-X", "en")
    assert r["sent"] and r["backend"] == "telegram"
    assert len(sent) == 1 and sent[0][0].endswith("/sendMessage")
    assert sent[0][1]["chat_id"] == int(CHAT) and sent[0][1]["text"] == BODY  # exact engine text, locked chat
    assert TOKEN not in json.dumps(r) + guard.read_text()
    assert pp.send_to_my_phone(BODY, "ACC-X", "en")["sent"] is False and len(sent) == 1  # double click


def test_send_signature_has_no_destination_parameter():
    import inspect
    assert list(inspect.signature(pp.send_to_my_phone).parameters) == ["body", "account_id", "lang"]


def test_group_chat_ids_and_bad_tokens_rejected(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TM_TELEGRAM_CHAT_ID", "-100123456789")  # group/channel
    monkeypatch.setenv("TM_SEND_LIVE", "1")
    assert pp.backends() == [] and pp.mode()[0] == "dry-run"
    monkeypatch.setenv("TM_TELEGRAM_CHAT_ID", CHAT)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "not-a-token")
    assert pp.backends() == []


def test_telegram_failure_falls_back_to_ntfy_and_scrubs_token(monkeypatch, guard):
    import types
    _arm_tg(monkeypatch)
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    monkeypatch.setenv("TM_SEND_LIVE", "1")

    def bad_urlopen(req, timeout=None):
        raise OSError(f"boom {req.full_url}")  # error text contains the token-bearing URL

    monkeypatch.setattr(urllib.request, "urlopen", bad_urlopen)
    calls = []
    fake = types.SimpleNamespace(send=lambda msg, backend=None, topic=None: calls.append(topic)
                                 or {"ok": True, "sent": True, "detail": f"Sent to {topic}."})
    monkeypatch.setitem(sys.modules, "harness.notify", fake)
    import harness
    monkeypatch.setattr(harness, "notify", fake, raising=False)
    assert pp.backends() == ["telegram", "ntfy"]
    r = pp.send_to_my_phone(BODY, "ACC-Y", "en")
    assert r["sent"] and r["backend"] == "ntfy" and calls == [TOPIC]
    blob = json.dumps(r) + guard.read_text()
    assert TOKEN not in blob and TOPIC not in blob


def test_forced_backend(monkeypatch):
    _arm_tg(monkeypatch)
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    monkeypatch.setenv("TM_PHONE_BACKEND", "ntfy")
    assert pp.backends() == ["ntfy"]
    monkeypatch.setenv("TM_PHONE_BACKEND", "telegram")
    monkeypatch.delenv("TM_TELEGRAM_CHAT_ID")
    assert pp.backends() == []


def test_short_or_burned_topic_refused(monkeypatch):
    import hashlib
    monkeypatch.setenv("TM_SEND_LIVE", "1")
    monkeypatch.setenv("NTFY_TOPIC", "short-topic")
    assert pp.mode()[0] == "dry-run"
    burned = "tm-dubhacks26-" + "lf3reo19tv"
    assert hashlib.sha256(burned.encode()).hexdigest() in pp._BURNED_TOPIC_SHA256
    monkeypatch.setenv("NTFY_TOPIC", burned + "x" * 20)
    assert pp._topic() != ""  # only the exact burned value is on the list
    monkeypatch.setattr(pp, "MIN_TOPIC_LEN", 10)
    monkeypatch.setenv("NTFY_TOPIC", burned)
    assert pp._topic() == "" and "burned" in pp._topic_problem(burned)


def test_live_flag_is_never_read_from_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(f"TM_SEND_LIVE=1\nNTFY_TOPIC={TOPIC}\n")
    assert pp._topic() == TOPIC  # .env supplies config...
    assert pp.mode()[0] == "dry-run"  # ...but never arms
    assert "NTFY_TOPIC" not in os.environ  # and does not mutate os.environ


def test_setup_helpers(monkeypatch, tmp_path):
    r = pp.new_ntfy_topic(write=True)
    env = (tmp_path / ".env").read_text()
    topic = env.split("NTFY_TOPIC=", 1)[1].strip()
    assert len(topic) >= pp.MIN_TOPIC_LEN and pp._topic() == topic and topic not in json.dumps(r)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    upd = {"ok": True, "result": [{"message": {"chat": {"id": int(CHAT), "type": "private", "first_name": "D"}}}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp(upd))
    s = pp.telegram_setup(write=True)
    assert s["ok"] and CHAT not in json.dumps(s) and f"TM_TELEGRAM_CHAT_ID={CHAT}" in (tmp_path / ".env").read_text()
    two = {"ok": True, "result": upd["result"] + [{"message": {"chat": {"id": 5555, "type": "private"}}}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp(two))
    assert pp.telegram_setup()["ok"] is False  # refuses to guess between two people
