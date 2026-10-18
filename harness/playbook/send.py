"""Frequency cap for outbound nudges. The drafted message itself stays on screen."""

from __future__ import annotations

from datetime import date, timedelta

from harness.playbook.rules import FREQUENCY_CAP_DAYS

_LEDGER: dict[str, date] = {}


def clear_ledger() -> None:
    _LEDGER.clear()


def record_send(account_id: str, when: date | None = None) -> None:
    _LEDGER[account_id] = when or date.today()


def frequency_open(account_id: str, when: date | None = None, cap_days: int = FREQUENCY_CAP_DAYS) -> bool:
    """Product setting: at most one outbound nudge per customer per cap_days."""
    last = _LEDGER.get(account_id)
    if last is None:
        return True
    return (when or date.today()) - last >= timedelta(days=cap_days)
