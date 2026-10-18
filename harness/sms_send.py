"""Optional live-SMS sender for the demo (e.g. Customer 38's text to the presenter's phone).

Nothing is hardcoded: provider, credentials and the destination number all come from env.
All customers/messages are synthetic; this only ever texts the presenter's own phone.

Env:
  TM_SMS_PROVIDER   twilio | webhook | gateway   (unset -> not configured)
  TM_DEMO_PHONE     default destination, 10-digit US number (normalized to +1XXXXXXXXXX)
  TM_SMS_DRY_RUN=1  return ok=True without sending anything
  twilio:  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM
  webhook: TM_SMS_WEBHOOK_URL  (POST JSON {"to": "+1...", "body": "..."}; Photon or similar)
  gateway: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM  (-> <10digits>@tmomail.net; unreliable)

API:
  is_configured() -> bool
  send_sms(body: str, to: str | None = None) -> dict {"ok": bool, "provider": str|None, "detail": str}
  send_sms never raises and sends `body` exactly as given.

CLI:
  python3 harness/sms_send.py --persona 38          # message_en of ACC-PERSONA-38 in demo_data/offers.csv
  python3 harness/sms_send.py --body "text" [--to 4255550100] [--dry-run]
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import smtplib
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OFFERS = ROOT / "demo_data" / "offers.csv"
PROVIDERS = ("twilio", "webhook", "gateway")
TIMEOUT_S = 15

_REQUIRED_ENV = {
    "twilio": ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"),
    "webhook": ("TM_SMS_WEBHOOK_URL",),
    "gateway": ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM"),
}


def _provider() -> str | None:
    p = (os.environ.get("TM_SMS_PROVIDER") or "").strip().lower()
    return p if p in PROVIDERS else None


def _dry_run() -> bool:
    return (os.environ.get("TM_SMS_DRY_RUN") or "").strip().lower() in ("1", "true", "yes")


def _missing_env(provider: str) -> list[str]:
    return [k for k in _REQUIRED_ENV[provider] if not (os.environ.get(k) or "").strip()]


def is_configured() -> bool:
    """True when a provider is selected and its env (plus TM_DEMO_PHONE) is set, or dry-run is on."""
    p = _provider()
    if p is None:
        return _dry_run()
    if _dry_run():
        return True
    return not _missing_env(p) and _normalize(os.environ.get("TM_DEMO_PHONE")) is not None


def _normalize(number: str | None) -> str | None:
    """10-digit US number (or 1+10 / +1...) -> '+1XXXXXXXXXX'; anything else -> None."""
    if not number:
        return None
    digits = re.sub(r"\D", "", str(number))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return "+1" + digits


def _mask(e164: str) -> str:
    return "***-***-" + e164[-4:]


def _result(ok: bool, provider: str | None, detail: str) -> dict:
    return {"ok": ok, "provider": provider, "detail": detail}


def _send_twilio(body: str, to: str) -> dict:
    sid = os.environ["TWILIO_ACCOUNT_SID"].strip()
    token = os.environ["TWILIO_AUTH_TOKEN"].strip()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{urllib.parse.quote(sid)}/Messages.json"
    data = urllib.parse.urlencode(
        {"To": to, "From": os.environ["TWILIO_FROM"].strip(), "Body": body}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
        return _result(True, "twilio", f"queued to {_mask(to)}; sid={payload.get('sid')} status={payload.get('status')}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("message", "")
        except Exception:
            msg = ""
        return _result(False, "twilio", f"Twilio HTTP {e.code}: {msg}".strip())


def _send_webhook(body: str, to: str) -> dict:
    url = os.environ["TM_SMS_WEBHOOK_URL"].strip()
    data = json.dumps({"to": to, "body": body}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
        ok = 200 <= int(code) < 300
        return _result(ok, "webhook", f"webhook HTTP {code} for {_mask(to)}")
    except urllib.error.HTTPError as e:
        return _result(False, "webhook", f"webhook HTTP {e.code}")


def _send_gateway(body: str, to: str) -> dict:
    host = os.environ["SMTP_HOST"].strip()
    port = int(os.environ["SMTP_PORT"].strip())
    rcpt = f"{to[-10:]}@tmomail.net"
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = os.environ["SMTP_FROM"].strip()
    msg["To"] = rcpt
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_S)
    else:
        server = smtplib.SMTP(host, port, timeout=TIMEOUT_S)
        server.ehlo()
        if server.has_extn("starttls"):
            server.starttls()
            server.ehlo()
    try:
        server.login(os.environ["SMTP_USER"].strip(), os.environ["SMTP_PASS"])
        server.sendmail(msg["From"], [rcpt], msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass
    return _result(
        True,
        "gateway",
        f"handed to SMTP for {_mask(to)} via tmomail.net (UNRELIABLE: T-Mobile's email-to-text "
        "gateway often drops messages silently; ok only means SMTP accepted it)",
    )


_SENDERS = {"twilio": _send_twilio, "webhook": _send_webhook, "gateway": _send_gateway}


def send_sms(body: str, to: str | None = None) -> dict:
    """Send `body` exactly as given. Never raises. Returns {ok, provider, detail}."""
    p = _provider()
    try:
        if not isinstance(body, str) or not body:
            return _result(False, p, "empty body")
        dest = _normalize(to if to is not None else os.environ.get("TM_DEMO_PHONE"))
        if _dry_run():
            where = _mask(dest) if dest else "(no number set)"
            return _result(True, p or "dry-run", f"DRY RUN: not sent; would send {len(body)} chars to {where}")
        if p is None:
            return _result(False, None, "SMS sender not configured")
        missing = _missing_env(p)
        if missing:
            return _result(False, p, "SMS sender not configured: missing " + ", ".join(missing))
        if dest is None:
            return _result(False, p, "no valid destination: pass `to` or set TM_DEMO_PHONE (10 digits)")
        return _SENDERS[p](body, dest)
    except Exception as e:  # never raise into the UI
        return _result(False, p, f"send failed: {type(e).__name__}: {e}")


def persona_message(persona: str, offers_csv: str | os.PathLike = DEFAULT_OFFERS, lang: str = "en") -> str | None:
    """message_en (or message_es) for ACC-PERSONA-<NN>; accepts '38' or 'ACC-PERSONA-38'."""
    pid = str(persona).strip().upper()
    if not pid.startswith("ACC-"):
        pid = f"ACC-PERSONA-{int(pid):02d}" if pid.isdigit() else pid
    col = f"message_{lang}"
    with open(offers_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("account_id") or "").strip().upper() == pid:
                return row.get(col) or None
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Send a demo SMS (env-configured; see module docstring).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--persona", help="persona number or account id, e.g. 38 or ACC-PERSONA-38")
    g.add_argument("--body", help="arbitrary text to send exactly as given")
    ap.add_argument("--lang", choices=("en", "es"), default="en", help="with --persona: message_en or message_es")
    ap.add_argument("--offers", default=str(DEFAULT_OFFERS), help="offers.csv path (default demo_data/offers.csv)")
    ap.add_argument("--to", default=None, help="destination (default env TM_DEMO_PHONE)")
    ap.add_argument("--dry-run", action="store_true", help="same as TM_SMS_DRY_RUN=1")
    a = ap.parse_args(argv)
    if a.dry_run:
        os.environ["TM_SMS_DRY_RUN"] = "1"
    if a.persona is not None:
        try:
            body = persona_message(a.persona, a.offers, a.lang)
        except (OSError, ValueError) as e:
            print(json.dumps(_result(False, _provider(), f"could not read offers: {e}")))
            return 1
        if not body:
            print(json.dumps(_result(False, _provider(), f"no message_{a.lang} for persona {a.persona}")))
            return 1
    else:
        body = a.body
    res = send_sms(body, a.to)
    print(json.dumps(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
