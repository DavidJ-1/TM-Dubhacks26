"""'Send to my phone' for the live demo, via harness/notify.py's ntfy push backend.

notify.py (copied unchanged from feature/retention-console) does NOT honour TM_SMS_DRY_RUN: with
SEND_BACKEND=ntfy and NTFY_TOPIC set it posts to the public ntfy.sh server, and it loads .env at import.
So this wrapper enforces dry run itself:

  * DRY RUN BY DEFAULT. Live only when TM_SEND_LIVE=1 is in the process env AND a topic is set
    (NTFY_TOPIC in env, or in .env). There is no built-in topic.
  * In dry run notify.py is not even imported: zero network calls, no .env side effects.
    It returns the exact payload (url with masked topic, headers, body) and writes a log line.
  * The topic is masked everywhere it is shown or logged (ntfy topics are readable by anyone who knows them).
  * Body = the engine's message_en / message_es exactly as given (no prefix, no edits). No LLM.

Env:  TM_SEND_LIVE=1 (arm), NTFY_TOPIC=<private random topic>, TM_SEND_LOG (default <repo>/out/phone_push_log.jsonl)
CLI:  .venv/bin/python -m harness.phone_push --account ACC-PERSONA-38 [--lang es]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_CHARS = 1000
COOLDOWN_S = 20
_last: dict[str, float] = {}


def mask_topic(topic: str) -> str:
    t = (topic or "").strip()
    return f"{t[:3]}…({len(t)} chars)" if t else "(unset)"


def _topic() -> str:
    t = (os.environ.get("NTFY_TOPIC") or "").strip()
    if not t and (ROOT / ".env").is_file():  # read .env without mutating os.environ
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*NTFY_TOPIC\s*=\s*['\"]?([^'\"#\s]*)", line)
            if m:
                t = m.group(1).strip()
    return "" if "/" in t else t


def mode() -> tuple[str, str]:
    if (os.environ.get("TM_SEND_LIVE") or "").strip() != "1":
        return "dry-run", "dry run (default): set TM_SEND_LIVE=1 and NTFY_TOPIC to send for real"
    if not _topic():
        return "dry-run", "TM_SEND_LIVE=1 but NTFY_TOPIC is unset -> dry run, nothing sent"
    return "live", "LIVE: posts to ntfy.sh"


def preview(body: str) -> dict:
    text = body
    return {"url": f"https://ntfy.sh/{mask_topic(_topic())}", "topic_masked": mask_topic(_topic()),
            "headers": {"Content-Type": "text/plain"}, "text": text, "chars": len(text)}


def _log(entry: dict) -> None:
    try:
        p = Path(os.environ.get("TM_SEND_LOG") or ROOT / "out" / "phone_push_log.jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def send_to_my_phone(body: str, account_id: str = "", lang: str = "") -> dict:
    """Never raises. {ok, mode, sent, detail, preview}. Dry run unless TM_SEND_LIVE=1 and a topic is set."""
    base = {"ok": False, "mode": None, "sent": False, "detail": "", "preview": None}
    if not isinstance(body, str) or not body.strip():
        return {**base, "detail": "empty text: nothing to send"}
    pv = preview(body)
    if pv["chars"] > MAX_CHARS:
        return {**base, "detail": f"text is {pv['chars']} chars; refusing", "preview": pv}
    m, reason = mode()
    entry = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "event": m,
             "account_id": account_id, "lang": lang, "topic": pv["topic_masked"], "text": pv["text"]}
    if m != "live":
        _log(entry)
        return {**base, "ok": True, "mode": "dry-run", "detail": "DRY RUN, nothing sent. " + reason, "preview": pv}
    key = f"{account_id}|{lang}|{pv['text']}"
    if time.monotonic() - _last.get(key, -1e9) < COOLDOWN_S:
        return {**base, "mode": "live", "detail": f"already sent in the last {COOLDOWN_S}s; not resending", "preview": pv}
    try:
        from harness import notify  # imported only on the armed live path
        res = notify.send(pv["text"], backend="ntfy", topic=_topic())
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "sent": False, "detail": type(e).__name__}
    topic = _topic()
    detail = str(res.get("detail", "")).replace(topic, mask_topic(topic)) if topic else str(res.get("detail", ""))
    sent = bool(res.get("sent"))
    if sent:
        _last[key] = time.monotonic()
    _log({**entry, "event": "live-sent" if sent else "live-failed"})
    return {**base, "ok": bool(res.get("ok")), "mode": "live", "sent": sent, "detail": detail, "preview": pv}


def offers_csv() -> Path:
    """Same order as app/data.py: TM_OUT_DIR -> demo_data/ -> harness/out/."""
    dirs = ([Path(os.environ["TM_OUT_DIR"])] if os.environ.get("TM_OUT_DIR") else []) + [ROOT / "demo_data", ROOT / "harness" / "out"]
    return next((d / "offers.csv" for d in dirs if (d / "offers.csv").is_file()), ROOT / "harness" / "out" / "offers.csv")


def engine_text(account_id: str, lang: str = "en", path: str | os.PathLike | None = None) -> str | None:
    """Engine's chosen message_en / message_es for an account; None for do nothing or unknown."""
    acc = str(account_id).strip().upper()
    acc = f"ACC-PERSONA-{int(acc):02d}" if acc.isdigit() else acc
    with open(path or offers_csv(), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("account_id") or "").strip().upper() == acc:
                if (row.get("action_code") or "").strip().lower() == "do_nothing":
                    return None
                return (row.get(f"message_{lang}") or "").strip() or None
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Push the engine's offer text to the demo phone (dry run by default).")
    ap.add_argument("--account", required=True, help="e.g. ACC-PERSONA-38 or 38")
    ap.add_argument("--lang", choices=("en", "es"), default="en")
    ap.add_argument("--offers", default=None)
    a = ap.parse_args(argv)
    body = engine_text(a.account, a.lang, a.offers)
    if not body:
        print(json.dumps({"ok": False, "detail": f"no message_{a.lang} for {a.account} (engine chose do nothing?)"}))
        return 1
    res = send_to_my_phone(body, a.account, a.lang)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
