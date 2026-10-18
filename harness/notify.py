"""Pluggable demo sender. Nothing here reads a customer phone number.

SEND_BACKEND selects the backend: dryrun (default) or ntfy.
A click is the only thing that calls send().
"""

import os

import requests

from harness.sms_send import send_sms

# TODO: a webhook or Twilio backend plugs in as another _BACKENDS entry.
# Keep customer phone numbers out of this module. Call it only from send().


def send(message: str, backend: str | None = None) -> dict:
    """Send the drafted demo message, or return it unchanged on dryrun."""
    name = _backend_name(backend)
    if name == "ntfy" and not _topic():
        preview = _dryrun(message)
        preview["hint"] = "SEND_BACKEND is ntfy but NTFY_TOPIC is unset, so this stayed a preview."
        return preview
    handler = _BACKENDS.get(name)
    if handler is None:
        preview = _dryrun(message)
        preview["hint"] = f"SEND_BACKEND {name} is not wired up. Preview only."
        return preview
    return handler(message)


def will_send() -> bool:
    """True only when a click would post to ntfy. Does not send."""
    return _backend_name(None) == "ntfy" and bool(_topic())


def hint() -> str:
    """Page-load hint. Does not send."""
    if _backend_name(None) == "ntfy" and not _topic():
        return "SEND_BACKEND is ntfy but NTFY_TOPIC is unset, so Send stays a preview."
    return ""


def _backend_name(backend: str | None) -> str:
    chosen = backend if backend is not None else os.environ.get("SEND_BACKEND")
    return (chosen or "dryrun").strip().lower()


def _topic() -> str:
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    if not topic or "/" in topic:
        return ""
    return topic


def _dryrun(message: str) -> dict:
    """Send nothing. Reuse sms_send's dry-run, and never pass a destination."""
    previous = os.environ.get("TM_SMS_DRY_RUN")
    os.environ["TM_SMS_DRY_RUN"] = "1"
    try:
        result = send_sms(message)
    finally:
        if previous is None:
            os.environ.pop("TM_SMS_DRY_RUN", None)
        else:
            os.environ["TM_SMS_DRY_RUN"] = previous
    return {
        "ok": True,
        "backend": "dryrun",
        "sent": False,
        "message": message,
        "detail": result.get("detail", ""),
        "hint": "",
    }


def _ntfy(message: str) -> dict:
    topic = _topic()
    try:
        response = requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"ok": False, "backend": "ntfy", "sent": False, "message": message, "detail": str(exc), "hint": ""}
    return {"ok": True, "backend": "ntfy", "sent": True, "message": message, "detail": "Sent.", "hint": ""}


_BACKENDS = {
    "dryrun": _dryrun,
    "ntfy": _ntfy,
}
