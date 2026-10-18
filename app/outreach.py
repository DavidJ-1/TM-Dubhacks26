"""Per-account outreach line loader (tm-ui). Data comes from the strategy/efficacy lanes, joined on account_id.

Expected columns: account_id, outreach_reason, message_en, message_es. Looked up in this order:
TM_OUTREACH_CSV, demo_data/outreach.csv(.gz), experiments/*/out/outreach*.csv(.gz). If nothing is found the app
shows a quiet "coming soon" placeholder; it never invents a reason.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
COLS = ["account_id", "outreach_reason", "message_en", "message_es"]


def find_file() -> Path | None:
    env = os.environ.get("TM_OUTREACH_CSV")
    if env and Path(env).exists():
        return Path(env)
    cands = [REPO / "demo_data" / "outreach.csv", REPO / "demo_data" / "outreach.csv.gz"]
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
    return d.drop_duplicates("account_id").set_index("account_id")
