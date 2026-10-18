"""Paths and the sandbox rules the console has to respect."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Cloned by `make setup` from https://github.com/mageshkumarj/dubhacks
DEFAULT_DB = ROOT / "vendor" / "dubhacks" / "data" / "sandbox.db"

AS_OF = date(2026, 10, 1)
SUPPORT_WINDOW_DAYS = 90
FINANCING_TERM_MONTHS = 24
UPGRADE_MIN_AGE_MONTHS = 12
OLD_PHONE_MONTHS = 36
TRADEIN_MAX_AGE = 60
# An open-ended monthly credit is valued over one year, matching the sandbox.
ONGOING_HORIZON_MONTHS = 12
LABEL_SEED = 2026
MODEL_SEED = 2026
# Ranking assumption only. Not a measured offer-response rate.
POLICY_ACCEPTANCE = 0.25
# Credits are not spent below the sandbox base rate. The book is about 14.6%.
RISK_FLOOR = 0.15
# Illustrative cost of sending a message, so "do nothing" can win.
ANNOYANCE_CENTS = 500
# Modeled battery drop. The sandbox has no battery-health field.
BATTERY_DROP_PER_MONTH = 0.7
BATTERY_FLOOR = 70
# Below this 6-month trade-in drop, a paid-off phone is not pushed as "upgrade now".
TRADEIN_DROP_NOW_CENTS = 2_000

FEATURE_COLUMNS = (
    "support_90d",
    "negative_sentiment",
    "bill_increase_pct",
    "competitor_research",
    "port_out_inquiry",
    "plan_misfit_share",
    "tenure_capped",
)

FEATURE_LABELS = {
    "support_90d": "Support contacts, last 90 days",
    "negative_sentiment": "Negative support sentiment",
    "bill_increase_pct": "Bill increase vs prior months",
    "competitor_research": "Competitor research",
    "port_out_inquiry": "Port-out inquiry",
    "plan_misfit_share": "Plan misfit",
    "tenure_capped": "Tenure (capped at 60 months)",
}

RETENTION_SKUS = (
    "PROMO-STUB-LOYALTY-CREDIT",
    "PROMO-STUB-CARE-CREDIT",
    "PROMO-STUB-OLD-PHONE-UPGRADE",
)


def db_path() -> Path:
    override = os.environ.get("DUBHACKS_DB")
    return Path(override) if override else DEFAULT_DB
