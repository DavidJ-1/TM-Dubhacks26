"""'Send to my phone' for the live demo: one click delivers the engine's chosen message to the presenter's phone.

Backends (all free, no card):
  * telegram (primary): a private bot DMs ONE chat id. Only that chat can see it; nothing is public.
  * ntfy (fallback):    push via harness/notify.py to a long random topic (>= 32 chars). Anyone who knows the
                        topic can read it, so it lives only in the local .env and is masked everywhere.
TM_PHONE_BACKEND = telegram | ntfy | auto (default auto: telegram if configured, else ntfy). In auto, a failed
live Telegram send falls back to ntfy once, if ntfy is configured.

Safety:
  * DRY RUN BY DEFAULT. Live only when TM_SEND_LIVE=1 is in the PROCESS env (never read from .env) AND the
    chosen backend is configured. In dry run there are zero network calls and notify.py is not imported.
  * Recipient is locked: the only destination is TM_TELEGRAM_CHAT_ID (a private 1:1 chat, positive integer) or
    NTFY_TOPIC. Callers (the app) cannot pass a number, chat or topic.
  * Secrets come only from the process env or the gitignored local .env (read without mutating os.environ),
    and are masked in every return value, log line and error string.
  * Body = the engine's message_en / message_es exactly as given (no prefix, no edits). No LLM.
  * Double-click guard: the same text for the same account is not re-sent within COOLDOWN_S.

Env:  TM_SEND_LIVE=1, TM_PHONE_BACKEND, TELEGRAM_BOT_TOKEN, TM_TELEGRAM_CHAT_ID, NTFY_TOPIC,
      TM_SEND_LOG (default <repo>/out/phone_push_log.jsonl)
CLI:  .venv/bin/python -m harness.phone_push --account ACC-PERSONA-38 [--lang es]     # dry run unless armed
      .venv/bin/python -m harness.phone_push --telegram-setup [--write]   # find the chat id after you /start the bot
      .venv/bin/python -m harness.phone_push --new-ntfy-topic [--write]   # make a fresh random fallback topic
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_CHARS = 1000
COOLDOWN_S = 20
MIN_TOPIC_LEN = 32
TIMEOUT_S = 8
# sha256 of topics that were ever published in the repo: refused even if someone puts them back in .env.
_BURNED_TOPIC_SHA256 = {"ff3ecaf11a1b8867a7efe693a0d0a88214cdb3c7d3e75fe2168b3fce77349dd8"}
_last: dict[str, float] = {}


# ---------- config (process env first, then local .env; never mutates os.environ) ----------
def _env(key: str) -> str:
    v = (os.environ.get(key) or "").strip()
    if v or not (ROOT / ".env").is_file():
        return v
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        m = re.match(rf"\s*(?:export\s+)?{re.escape(key)}\s*=\s*['\"]?([^'\"#\s]*)", line)
        if m:
            v = m.group(1).strip()
    return v


def mask_topic(topic: str) -> str:
    t = (topic or "").strip()
    return f"{t[:3]}…({len(t)} chars)" if t else "(unset)"


def mask_chat(chat: str) -> str:
    c = (chat or "").strip()
    return f"chat …{c[-3:]}" if c else "(unset)"


def _raw_topic() -> str:
    t = _env("NTFY_TOPIC")
    return "" if "/" in t else t


def _topic_problem(t: str) -> str:
    if not t:
        return "NTFY_TOPIC is unset"
    if hashlib.sha256(t.encode()).hexdigest() in _BURNED_TOPIC_SHA256:
        return "NTFY_TOPIC is a burned (publicly published) topic; make a new one with --new-ntfy-topic"
    if len(t) < MIN_TOPIC_LEN or not re.fullmatch(r"[A-Za-z0-9_-]+", t):
        return f"NTFY_TOPIC must be {MIN_TOPIC_LEN}+ random letters/digits/-/_ (use --new-ntfy-topic)"
    return ""


def _topic() -> str:
    """Usable fallback topic, or '' (unset, too short, or burned)."""
    t = _raw_topic()
    return "" if _topic_problem(t) else t


def _tg_token() -> str:
    t = _env("TELEGRAM_BOT_TOKEN")
    return t if re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{30,}", t) else ""


def _tg_chat() -> str:
    c = _env("TM_TELEGRAM_CHAT_ID")
    return c if re.fullmatch(r"[1-9]\d{3,14}", c) else ""  # private 1:1 chats only (groups are negative)


def _configured() -> list[str]:
    out = []
    if _tg_token() and _tg_chat():
        out.append("telegram")
    if _topic():
        out.append("ntfy")
    return out


def backends() -> list[str]:
    """Backends to try, in order, for the current env."""
    want = (_env("TM_PHONE_BACKEND") or "auto").lower()
    have = _configured()
    if want in ("telegram", "ntfy"):
        return [want] if want in have else []
    return have  # auto: telegram first, ntfy as fallback


def _not_configured_reason() -> str:
    want = (_env("TM_PHONE_BACKEND") or "auto").lower()
    tg = "TELEGRAM_BOT_TOKEN + TM_TELEGRAM_CHAT_ID" + ("" if (_tg_token() and _tg_chat()) else " not set")
    nt = _topic_problem(_raw_topic()) or "NTFY_TOPIC ok"
    return f"backend={want}: {tg}; {nt}"


def mode() -> tuple[str, str]:
    if (os.environ.get("TM_SEND_LIVE") or "").strip() != "1":
        return "dry-run", "dry run (default): set TM_SEND_LIVE=1 plus a Telegram bot or NTFY_TOPIC to send for real"
    b = backends()
    if not b:
        return "dry-run", "TM_SEND_LIVE=1 but no backend is configured -> dry run, nothing sent (" + _not_configured_reason() + ")"
    return "live", "LIVE: " + " then ".join(b)


def _to_label(b: str | None) -> str:
    if b == "telegram":
        return f"private chat bot, {mask_chat(_tg_chat())} (presenter's phone only)"
    if b == "ntfy":
        return f"private push, topic {mask_topic(_topic())} (presenter's phone only)"
    return "presenter's phone (not configured: dry run)"


def preview(body: str) -> dict:
    text = body
    b = (backends() or [None])[0]
    return {"backend": b or "none", "to": _to_label(b), "topic_masked": mask_topic(_raw_topic()),
            "chat_masked": mask_chat(_tg_chat()), "text": text, "chars": len(text)}


def _scrub(s: str) -> str:
    """Mask every secret that could appear in an error string."""
    s = str(s)
    for secret, masked in ((_env("TELEGRAM_BOT_TOKEN"), "bot…(token)"), (_raw_topic(), mask_topic(_raw_topic())),
                           (_tg_chat(), mask_chat(_tg_chat()))):
        if secret:
            s = s.replace(secret, masked)
    return s


def _log(entry: dict) -> None:
    try:
        p = Path(os.environ.get("TM_SEND_LOG") or ROOT / "out" / "phone_push_log.jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------- live senders (only reached when armed) ----------
def _tg_api(method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{_env('TELEGRAM_BOT_TOKEN')}/{method}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8") or "{}") | {"ok": False, "http": e.code}
        except Exception:  # noqa: BLE001
            return {"ok": False, "http": e.code}


def _send_telegram(text: str) -> dict:
    r = _tg_api("sendMessage", {"chat_id": int(_tg_chat()), "text": text, "disable_web_page_preview": True})
    if r.get("ok"):
        return {"ok": True, "sent": True, "detail": f"Delivered by the bot to {mask_chat(_tg_chat())}."}
    return {"ok": False, "sent": False,
            "detail": f"bot send failed: HTTP {r.get('http', '?')} {r.get('description', '')}".strip()}


def _send_ntfy(text: str) -> dict:
    from harness import notify  # imported only on the armed live path
    return notify.send(text, backend="ntfy", topic=_topic())


_SENDERS = {"telegram": _send_telegram, "ntfy": _send_ntfy}


def send_to_my_phone(body: str, account_id: str = "", lang: str = "") -> dict:
    """Never raises. {ok, mode, sent, backend, detail, preview}. Dry run unless TM_SEND_LIVE=1 and a backend is set."""
    base = {"ok": False, "mode": None, "sent": False, "backend": None, "detail": "", "preview": None}
    if not isinstance(body, str) or not body.strip():
        return {**base, "detail": "empty text: nothing to send"}
    pv = preview(body)
    if pv["chars"] > MAX_CHARS:
        return {**base, "detail": f"text is {pv['chars']} chars; refusing", "preview": pv}
    m, reason = mode()
    entry = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "event": m, "account_id": account_id,
             "lang": lang, "to": pv["to"], "text": pv["text"]}
    if m != "live":
        _log(entry)
        return {**base, "ok": True, "mode": "dry-run", "detail": _scrub("DRY RUN, nothing sent. " + reason), "preview": pv}
    key = f"{account_id}|{lang}|{pv['text']}"
    if time.monotonic() - _last.get(key, -1e9) < COOLDOWN_S:
        return {**base, "mode": "live", "detail": f"already sent in the last {COOLDOWN_S}s; not resending", "preview": pv}
    res, used, notes = {"ok": False, "sent": False, "detail": "no backend"}, None, []
    for b in backends():
        try:
            res = _SENDERS[b](pv["text"])
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "sent": False, "detail": f"{b} failed: {type(e).__name__}"}
        used = b
        if res.get("sent"):
            break
        notes.append(f"{b}: {res.get('detail', '')}")
    sent = bool(res.get("sent"))
    detail = _scrub(" | ".join(notes + ([str(res.get("detail", ""))] if sent else [])))
    if sent:
        _last[key] = time.monotonic()
    _log({**entry, "event": "live-sent" if sent else "live-failed", "backend": used, "detail": detail})
    return {**base, "ok": sent, "mode": "live", "sent": sent, "backend": used, "detail": detail,
            "preview": {**pv, "backend": used or pv["backend"], "to": _to_label(used)}}


# ---------- one-time setup helpers (CLI only, never called by the app) ----------
def _write_env(key: str, value: str) -> None:
    p = ROOT / ".env"
    lines = p.read_text(encoding="utf-8").splitlines() if p.is_file() else []
    lines = [ln for ln in lines if not re.match(rf"\s*(?:export\s+)?{re.escape(key)}\s*=", ln)] + [f"{key}={value}"]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(p, 0o600)


def telegram_setup(write: bool = False) -> dict:
    """Read the bot's recent messages (getUpdates, read-only) and find the private chat that sent /start.
    Locks onto it only if exactly one private chat has messaged the bot."""
    if not _tg_token():
        return {"ok": False, "detail": "TELEGRAM_BOT_TOKEN missing or malformed (put it in .env)"}
    r = _tg_api("getUpdates")
    if not r.get("ok"):
        return {"ok": False, "detail": _scrub(f"getUpdates failed: HTTP {r.get('http', '?')} {r.get('description', '')}")}
    chats = {}
    for u in r.get("result", []):
        c = (u.get("message") or {}).get("chat") or {}
        if c.get("type") == "private":
            chats[str(c["id"])] = c.get("first_name", "")
    if len(chats) != 1:
        return {"ok": False, "detail": f"found {len(chats)} private chats; need exactly 1 (send /start to the bot from your phone, and only you)"}
    chat, name = next(iter(chats.items()))
    if write:
        _write_env("TM_TELEGRAM_CHAT_ID", chat)
    return {"ok": True, "chat": mask_chat(chat), "first_name": name, "written_to_env": write}


def new_ntfy_topic(write: bool = False) -> dict:
    topic = "p-" + secrets.token_urlsafe(30).replace("_", "x")  # ~42 chars, unguessable
    if write:
        _write_env("NTFY_TOPIC", topic)
    return {"ok": True, "topic": topic if not write else mask_topic(topic), "written_to_env": write,
            "next": "subscribe to this exact topic in the ntfy phone app (server ntfy.sh); never commit it"}


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
    ap = argparse.ArgumentParser(description="Send the engine's offer text to the presenter's phone (dry run by default).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--account", help="e.g. ACC-PERSONA-38 or 38")
    g.add_argument("--telegram-setup", action="store_true", help="find the chat id after you send /start to the bot")
    g.add_argument("--new-ntfy-topic", action="store_true", help="generate a fresh random fallback topic")
    g.add_argument("--status", action="store_true", help="show mode and masked config; sends nothing")
    ap.add_argument("--write", action="store_true", help="with a setup flag: save the value into the local .env")
    ap.add_argument("--lang", choices=("en", "es"), default="en")
    ap.add_argument("--offers", default=None)
    a = ap.parse_args(argv)
    if a.telegram_setup:
        res = telegram_setup(a.write)
    elif a.new_ntfy_topic:
        res = new_ntfy_topic(a.write)
    elif a.status:
        m, why = mode()
        res = {"ok": True, "mode": m, "detail": _scrub(why), "order": backends(),
               "telegram_chat": mask_chat(_tg_chat()), "ntfy_topic": mask_topic(_raw_topic())}
    else:
        body = engine_text(a.account, a.lang, a.offers)
        if not body:
            print(json.dumps({"ok": False, "detail": f"no message_{a.lang} for {a.account} (engine chose do nothing?)"}))
            return 1
        res = send_to_my_phone(body, a.account, a.lang)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
