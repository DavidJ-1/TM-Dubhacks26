"""Per-account outreach line loader (tm-ui). Data comes from the strategy/efficacy lanes, joined on account_id.

Expected columns: account_id, outreach_reason, message_en, message_es. Looked up in this order:
TM_OUTREACH_CSV, docs/outreach/outreach_card.csv, demo_data/outreach.csv(.gz), experiments/*/out/outreach*.csv(.gz).
outreach_reason ends with "Sent as: <channel>." when a message goes out; that suffix is parsed into `channel`
(text / in-app message / email / agent call) and stripped from `reason`. If nothing is found the app
shows a quiet "coming soon" placeholder; it never invents a reason.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
COLS = ["account_id", "outreach_reason", "message_en", "message_es"]
SENT_AS = r"\s*Sent as:\s*([^.]+)\.?\s*$"
CHANNEL_LABEL = {"text": "Text message", "in-app message": "In-app message", "email": "Email", "agent call": "Call script"}


def find_file() -> Path | None:
    env = os.environ.get("TM_OUTREACH_CSV")
    if env and Path(env).exists():
        return Path(env)
    cands = [REPO / "docs" / "outreach" / "outreach_card.csv", REPO / "demo_data" / "outreach.csv", REPO / "demo_data" / "outreach.csv.gz"]
    cands += sorted((REPO / "experiments").glob("*/out/outreach*.csv*"))
    return next((p for p in cands if p.exists()), None)


def load_outreach() -> pd.DataFrame | None:
    """account_id-indexed frame with the expected columns, or None if no usable file exists."""
    p = find_file()
    if p is None:
        return None
    try:
        d = pd.read_csv(p, dtype=str)
    except Exception:  # noqa: BLE001
        return None
    if not {"account_id", "outreach_reason"}.issubset(d.columns):
        return None
    for c in COLS:
        if c not in d:
            d[c] = ""
    d = d[COLS].fillna("")
    d["account_id"] = d.account_id.str.strip()
    d["has_msg"] = d.message_en.str.strip() != ""
    d["channel"] = d.outreach_reason.str.extract(SENT_AS, expand=False).fillna("").str.strip().str.lower()
    d["reason"] = d.outreach_reason.str.replace(SENT_AS, "", regex=True).str.strip()
    return d.drop_duplicates("account_id").set_index("account_id")
