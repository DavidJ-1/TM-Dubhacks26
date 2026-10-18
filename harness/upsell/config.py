"""Editable upsell rules. Guardrails run first. Then the first matching offer wins.

SYNTHETIC_SHARE is the one seeded share of accounts that receive a Tier 2 signal.
It is synthetic. It is not a measured base rate, and the screen does not display it.
"""

from __future__ import annotations

from harness.config import UPGRADE_MIN_AGE_MONTHS
from harness.playbook.rules import (
    BILL_JUMP_PCT,
    CAP_RATIO,
    DO_NOTHING_ACCOUNTS,
    FREQUENCY_CAP_DAYS,
    UPGRADE_PUSH_BLOCKED,
)

# Fixed RNG seed. Keyed with the account id so the draw does not depend on row order.
SYNTHETIC_SEED = "tm-life-moments-2026"

# Synthetic. One config value. Not shown in the UI.
SYNTHETIC_SHARE = 0.08

SYNTHETIC_BADGE = "synthetic, consented, illustrative"
INCLUDE_SYNTHETIC_DEFAULT = False

SATISFIED_TENURE_MONTHS = 24
LOW_CREDIT_TIER = "subprime"
GROWTH_RATIO = 1.10
AT_RISK_BANDS = frozenset({"top_10", "mid_10_30"})

# Reused from the retention playbook and the sandbox upgrade rule.
FREQUENCY_CAP_DAYS = FREQUENCY_CAP_DAYS
BILL_JUMP_PCT = BILL_JUMP_PCT
CAP_RATIO = CAP_RATIO
UPGRADE_MIN_AGE_MONTHS = UPGRADE_MIN_AGE_MONTHS
UPGRADE_PUSH_BLOCKED = UPGRADE_PUSH_BLOCKED
DO_NOTHING_ACCOUNTS = DO_NOTHING_ACCOUNTS

# Tier 2 event ids. The generator assigns at most one of these.
SYNTHETIC_EVENTS = (
    "kid_turning_13",
    "promotion_or_new_job",
    "moving",
    "household_merge",
    "retirement_or_income_down",
)

# First match wins after the guardrails. Tier 2 is skipped unless the toggle is on.
# "Satisfied, no trigger" is last so a synthetic signal still counts as a trigger.
RULES: tuple[dict, ...] = (
    {
        "id": "near_cap",
        "tier": "tier1",
        "when": "Near or over the data cap in 2 or more of the last 3 months",
        "action": "PLAN STEP-UP",
        "source": "usage_monthly",
    },
    {
        "id": "usage_growth",
        "tier": "tier1",
        "when": "Usage growth with no cap issue",
        "action": "PLAN FIT",
        "source": "usage_monthly",
    },
    {
        "id": "paid_off",
        "tier": "tier1",
        "when": "Phone paid off and upgrade-eligible",
        "action": "UPGRADE TIMING",
        "source": "lines",
    },
    {
        "id": "student_graduating",
        "tier": "tier1",
        "when": "Student graduating off a student or discount plan",
        "action": "AVOID SURPRISE BILL",
        "source": "accounts.discount_group",
    },
    {
        "id": "kid_turning_13",
        "tier": "tier2",
        "when": "Kid turning 13",
        "action": "ADD A LINE",
        "source": "synthetic signal",
    },
    {
        "id": "promotion_or_new_job",
        "tier": "tier2",
        "when": "Promotion or new job",
        "action": "PLAN OR DEVICE",
        "source": "synthetic signal",
    },
    {
        "id": "moving",
        "tier": "tier2",
        "when": "Moving",
        "action": "COVERAGE CHECK",
        "source": "synthetic signal",
    },
    {
        "id": "household_merge",
        "tier": "tier2",
        "when": "New partner or household merge",
        "action": "HOUSEHOLD MERGE",
        "source": "synthetic signal",
    },
    {
        "id": "retirement_or_income_down",
        "tier": "tier2",
        "when": "Retirement or income down",
        "action": "CHEAPER PLAN",
        "source": "synthetic signal",
    },
    {
        "id": "satisfied",
        "tier": "tier1",
        "when": "Highly satisfied with no trigger",
        "action": "DO NOTHING",
        "source": "support, billing, tenure",
    },
)

TIER2_RULES = frozenset(rule["id"] for rule in RULES if rule["tier"] == "tier2")

# Columns the screen and the CSV are allowed to show. No rates.
DISPLAY_COLUMNS = (
    "account_id",
    "trigger",
    "action",
    "offer",
    "monthly_difference",
    "data_source",
    "tier",
    "badge",
    "rejected",
)
