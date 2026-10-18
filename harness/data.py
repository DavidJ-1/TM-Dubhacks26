"""Load the judge sandbox SQLite file. Money stays in cents until the UI formats it."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from harness.config import AS_OF, SUPPORT_WINDOW_DAYS

ACCOUNT_SQL = """
SELECT
  a.account_id,
  a.segment,
  a.tenure_months,
  a.language,
  a.contact_preference,
  a.credit_tier,
  a.autopay,
  a.discount_group,
  CASE WHEN a.account_id LIKE 'ACC-PERSONA-%' THEN 1 ELSE 0 END AS is_persona,
  s.competitor_research_score AS competitor_research,
  s.port_out_inquiry,
  s.app_sessions_30d,
  (SELECT COUNT(*) FROM support_interactions i
     WHERE i.account_id = a.account_id
       AND i.interaction_date >= date(:as_of, :window)) AS support_90d,
  (SELECT COALESCE(AVG(sentiment), 0) FROM support_interactions i
     WHERE i.account_id = a.account_id) AS avg_sentiment,
  (SELECT COUNT(*) FROM support_interactions i
     WHERE i.account_id = a.account_id AND i.topic = 'cancellation_inquiry') AS cancellation_inquiries,
  (SELECT total_cents FROM billing_history b
     WHERE b.account_id = a.account_id ORDER BY month DESC LIMIT 1) AS last_bill_cents,
  (SELECT AVG(total_cents) FROM billing_history b
     WHERE b.account_id = a.account_id
       AND month < (SELECT MAX(month) FROM billing_history c WHERE c.account_id = a.account_id)) AS prior_bill_cents,
  (SELECT COALESCE(AVG(CASE
        WHEN (p.data_cap_gb IS NOT NULL AND u.g > p.data_cap_gb)
          OR (p.tier = 'premium' AND u.g < 5) THEN 1.0 ELSE 0.0 END), 0)
     FROM lines l
     JOIN plans p ON p.sku = l.plan_sku
     JOIN (SELECT line_id, AVG(data_gb) AS g FROM usage_monthly GROUP BY line_id) u USING (line_id)
     WHERE l.account_id = a.account_id) AS plan_misfit_share
FROM accounts a
JOIN account_signals s USING (account_id)
ORDER BY a.account_id
"""

LINES_SQL = """
SELECT
  l.account_id, l.line_id, l.member_label, l.member_role, l.byod,
  l.device_sku, d.name AS device_name, d.tier AS device_tier,
  l.device_purchase_date, l.financing_balance_cents, l.financing_months_remaining,
  l.monthly_installment_cents, l.tradein_eligible,
  p.sku AS plan_sku, p.name AS plan_name, p.family AS plan_family, p.variant AS plan_variant,
  p.tier AS plan_tier, p.line_prices, p.data_cap_gb, p.eligibility AS plan_eligibility,
  (SELECT AVG(data_gb) FROM (
      SELECT data_gb FROM usage_monthly u WHERE u.line_id = l.line_id ORDER BY month DESC LIMIT 3
  )) AS usage_3m_gb
FROM lines l
JOIN plans p ON p.sku = l.plan_sku
LEFT JOIN devices d ON d.sku = l.device_sku
ORDER BY l.account_id, l.line_id
"""


def connect(db_path: Path) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"Sandbox database not found at {db_path}. Run `make setup` to clone "
            "https://github.com/mageshkumarj/dubhacks into vendor/dubhacks."
        )
    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_metadata(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM metadata")}


def months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def load_accounts(conn: sqlite3.Connection, as_of: date = AS_OF) -> pd.DataFrame:
    window = f"-{SUPPORT_WINDOW_DAYS} day"
    frame = pd.read_sql_query(ACCOUNT_SQL, conn, params={"as_of": as_of.isoformat(), "window": window})
    prior = frame["prior_bill_cents"]
    last = frame["last_bill_cents"]
    increase = (last / prior - 1).where(prior.notna() & (prior > 0), 0.0)
    frame["bill_increase_pct"] = increase.clip(lower=0).fillna(0.0)
    frame["negative_sentiment"] = (-frame["avg_sentiment"]).clip(lower=0).fillna(0.0)
    frame["tenure_capped"] = frame["tenure_months"].clip(upper=60)
    frame["plan_misfit_share"] = frame["plan_misfit_share"].fillna(0.0)
    return frame


def load_lines(conn: sqlite3.Connection, as_of: date = AS_OF) -> pd.DataFrame:
    frame = pd.read_sql_query(LINES_SQL, conn)
    purchased = pd.to_datetime(frame["device_purchase_date"])
    age = (as_of.year - purchased.dt.year) * 12 + (as_of.month - purchased.dt.month)
    frame["age_months"] = age.where(frame["device_sku"].notna())
    return frame


def load_promotions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM promotions ORDER BY rowid").fetchall()
    return [dict(row) for row in rows]


def load_devices(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT sku, name, manufacturer, tier, msrp_cents, release_date, status FROM devices",
        conn,
    )


def load_tradein(conn: sqlite3.Connection) -> dict[tuple[str, int], int]:
    rows = conn.execute("SELECT device_sku, age_months, value_cents FROM tradein_curves")
    return {(sku, int(age)): int(value) for sku, age, value in rows}


def load_personas(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT account_id, title, scenario, primary_theme
        FROM personas
        WHERE account_id IS NOT NULL
        """,
        conn,
    )


def load_billing_flags(conn: sqlite3.Connection) -> pd.DataFrame:
    # Last three billing months before the 2026-10-01 as-of date are 2026-07..2026-09.
    return pd.read_sql_query(
        """
        SELECT account_id,
          MAX(CASE WHEN change_reason = 'promo_expired' AND month >= '2026-07' THEN 1 ELSE 0 END)
            AS promo_expired_recent,
          MAX(CASE WHEN change_reason = 'installment_ended' AND month >= '2026-07' THEN 1 ELSE 0 END)
            AS installment_ended_recent
        FROM billing_history
        GROUP BY account_id
        """,
        conn,
    )


def load_support_topics(conn: sqlite3.Connection, as_of: date = AS_OF) -> pd.DataFrame:
    window = f"-{SUPPORT_WINDOW_DAYS} day"
    return pd.read_sql_query(
        """
        SELECT account_id, topic, COUNT(*) AS n
        FROM support_interactions
        WHERE interaction_date >= date(:as_of, :window)
        GROUP BY account_id, topic
        """,
        conn,
        params={"as_of": as_of.isoformat(), "window": window},
    )


def load_addon_flags(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT aa.account_id,
          MAX(CASE WHEN a.kind = 'home_internet' THEN 1 ELSE 0 END) AS has_home_internet,
          MAX(CASE WHEN a.kind = 'streaming' THEN 1 ELSE 0 END) AS has_streaming
        FROM account_addons aa
        JOIN addons a ON a.sku = aa.addon_sku
        GROUP BY aa.account_id
        """,
        conn,
    )


def tradein_value_cents(curves: dict[tuple[str, int], int], device_sku: str, age_months: int) -> int | None:
    if device_sku is None or age_months is None or pd.isna(age_months):
        return None
    age = max(0, min(int(age_months), 60))
    return curves.get((device_sku, age))
