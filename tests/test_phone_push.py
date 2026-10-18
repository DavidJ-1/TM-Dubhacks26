"""phone_push: dry run default, zero network in dry run, live flag without topic -> dry run, topic masked.
Never posts: requests/urllib/notify network paths are patched to fail the test if touched."""
import json
import re
import sys
import urllib.request
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import phone_push as pp  # noqa: E402

TOPIC = "private-test-topic-abc123xyz"
BODY = "Hi there. Your plan has a 5-Year Price Guarantee. Reply STOP to opt out."


@pytest.fixture(autouse=True)
def guard(monkeypatch, tmp_path):
    for k in ("TM_SEND_LIVE", "NTFY_TOPIC", "SEND_BACKEND", "TM_OUT_DIR"):
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
    assert r["preview"]["text"] == "[DEMO, synthetic] " + BODY
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
    assert r["sent"] and calls == [("[DEMO, synthetic] " + BODY, "ntfy", TOPIC)]
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
    assert json.loads(capsys.readouterr().out)["preview"]["text"] == "[DEMO, synthetic] Hello en"


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
