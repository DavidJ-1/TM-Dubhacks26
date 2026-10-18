"""tm-offers lane (Model B): sandbox loader, per-account facts, and upgrade-moment detectors.

Reads the judge sandbox (mageshkumarj/dubhacks) READ-ONLY. Every customer in it is synthetic,
so every number this module produces is synthetic too.

Public entry point: build_account_facts(conn) -> pandas.DataFrame, one row per account.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# --- where the read-only sandbox lives ------------------------------------------------------
_SANDBOX_CANDIDATES = [
    os.environ.get("TM_SANDBOX_DB"),
    str(Path(__file__).resolve().parents[2] / "dubhacks" / "data" / "sandbox.db"),  # /workspace/tmobile/dubhacks
    "/workspace/tmobile/dubhacks/data/sandbox.db",
    "/tmp/dubhacks-ro/data/sandbox.db",
]

SUPPORT_WINDOW_DAYS = 90            # same window the sandbox API uses (api/services/common.py)
UPGRADE_MIN_DEVICE_AGE_MONTHS = 12  # sandbox stub rule (api/services/context.py)
TRADEIN_MAX_AGE = 60                # sandbox trade-in curves stop at 60 months

# Detector thresholds (synthetic judgement calls, documented in OFFERS_README.md)
NEAR_CAP_SHARE = 0.80          # a line averaging >= 80% of its plan's data cap is "near the limit"
USAGE_GROWTH_RATIO = 1.30      # last-3-month avg >= 1.3x first-3-month avg ...
USAGE_GROWTH_MIN_GB = 2.0      # ... and at least 2 GB/month, so tiny lines don't trigger it
OLD_DEVICE_MONTHS = 36         # matches PROMO-STUB-OLD-PHONE-UPGRADE min_device_age_months
PAYOFF_SOON_MONTHS = 2         # financing ends within 2 months
RECENT_BILL_MONTHS = 3         # "recent" = the last 3 billing months
OVERPAY_LOW_USAGE_GB = 5.0     # sandbox's own plan-misfit rule: premium plan, line < 5 GB
STUDENT_GRAD_TENURE_MONTHS = 36  # heuristic: student-discount household with 3+ years tenure
BILL_SHOCK_PCT = 0.15          # a month-over-month bill rise >= 15% that the customer didn't cause (not a new
                               # phone's installment) counts as a bill shock; any promo_expired month does too


def find_sandbox_db() -> str:
    for cand in _SANDBOX_CANDIDATES:
        if cand and Path(cand).is_file():
            return cand
    raise FileNotFoundError("sandbox.db not found; set TM_SANDBOX_DB or clone the sandbox read-only")


def connect_ro(path: str | None = None) -> sqlite3.Connection:
    """Open the sandbox strictly read-only (never writes to data/sandbox.db)."""
    path = path or find_sandbox_db()
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def as_of(conn: sqlite3.Connection) -> date:
    return date.fromisoformat(conn.execute("SELECT value FROM metadata WHERE key='as_of'").fetchone()[0])


def months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def plan_price_cents(line_prices: str, extra_line_cents: int, n_lines: int) -> int:
    """Household monthly plan price: sum of marginal line prices (sandbox convention)."""
    table = [int(p) for p in str(line_prices).split(",")]
    return int(sum(table[i] if i < len(table) else int(extra_line_cents) for i in range(n_lines)))


def load_catalog(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    return {
        "plans": pd.read_sql("SELECT * FROM plans", conn),
        "promotions": pd.read_sql("SELECT * FROM promotions", conn).set_index("sku", drop=False),
        "devices": pd.read_sql("SELECT * FROM devices", conn),
        "tradein_curves": pd.read_sql("SELECT * FROM tradein_curves", conn),
    }


def build_account_facts(conn: sqlite3.Connection) -> pd.DataFrame:
    today = as_of(conn)
    since = pd.Timestamp(today) - pd.Timedelta(days=SUPPORT_WINDOW_DAYS)

    acc = pd.read_sql("SELECT * FROM accounts", conn)
    sig = pd.read_sql("SELECT * FROM account_signals", conn)
    plans = pd.read_sql("SELECT * FROM plans", conn)
    lines = pd.read_sql("SELECT * FROM lines", conn)
    usage = pd.read_sql("SELECT * FROM usage_monthly", conn)
    bills = pd.read_sql("SELECT * FROM billing_history", conn)
    sup = pd.read_sql("SELECT * FROM support_interactions", conn)
    hint = pd.read_sql(
        "SELECT aa.account_id, a.kind FROM account_addons aa JOIN addons a ON a.sku = aa.addon_sku", conn)

    # ---- lines / devices / financing
    lines = lines.merge(plans[["sku", "family", "variant", "tier", "data_cap_gb", "hotspot_high_speed_gb",
                               "line_prices", "extra_line_cents", "eligibility"]],
                        left_on="plan_sku", right_on="sku", how="left")
    pdate = pd.to_datetime(lines["device_purchase_date"])
    lines["device_age_m"] = [
        months_between(d.date(), today) if pd.notna(d) else np.nan for d in pdate]
    has_dev = lines["device_sku"].notna()
    lines["paid_off_device"] = has_dev & (lines["financing_balance_cents"] == 0)
    lines["upgrade_ready_line"] = (has_dev & (lines["tradein_eligible"] == 1)
                                   & (lines["device_age_m"] >= UPGRADE_MIN_DEVICE_AGE_MONTHS)
                                   & (lines["financing_months_remaining"] == 0))
    lines["old_upgrade_line"] = lines["upgrade_ready_line"] & (lines["device_age_m"] >= OLD_DEVICE_MONTHS)
    lines["payoff_soon"] = lines["financing_months_remaining"].between(1, PAYOFF_SOON_MONTHS)

    # ---- usage per line: last 3 months vs first 3 months
    usage = usage.sort_values(["line_id", "month"])
    last3 = usage.groupby("line_id").tail(3).groupby("line_id").agg(
        data_last3=("data_gb", "mean"), data_max3=("data_gb", "max"), hotspot_last3=("hotspot_gb", "mean"))
    first3 = usage.groupby("line_id").head(3).groupby("line_id").agg(data_first3=("data_gb", "mean"))
    nmon = usage.groupby("line_id").size().rename("usage_months")
    lines = lines.join(last3, on="line_id").join(first3, on="line_id").join(nmon, on="line_id")
    cap = lines["data_cap_gb"]
    lines["near_cap"] = cap.notna() & (lines["data_last3"] >= NEAR_CAP_SHARE * cap)
    lines["over_cap"] = cap.notna() & (lines["data_last3"] > cap)
    lines["usage_growth"] = ((lines["usage_months"] >= 6)
                             & (lines["data_last3"] >= USAGE_GROWTH_RATIO * lines["data_first3"])
                             & (lines["data_last3"] - lines["data_first3"] >= USAGE_GROWTH_MIN_GB))
    lines["low_use_premium"] = (lines["tier"] == "premium") & (lines["data_last3"] < OVERPAY_LOW_USAGE_GB)

    g = lines.groupby("account_id")
    la = pd.DataFrame({
        "n_lines": g.size(),
        "plan_sku": g["plan_sku"].first(),
        "plan_family": g["family"].first(),
        "plan_variant": g["variant"].first(),
        "plan_tier": g["tier"].first(),
        "plan_cap_gb": g["data_cap_gb"].first(),
        "plan_hotspot_gb": g["hotspot_high_speed_gb"].first(),
        "n_devices": g["device_sku"].count(),
        "n_byod": g["byod"].sum(),
        "oldest_device_age_m": g["device_age_m"].max(),
        "financing_balance_cents": g["financing_balance_cents"].sum(),
        "max_financing_months_left": g["financing_months_remaining"].max(),
        "monthly_installments_cents": g["monthly_installment_cents"].sum(),
        "any_paid_off_device": g["paid_off_device"].any(),
        "n_upgrade_ready_lines": g["upgrade_ready_line"].sum(),
        "n_old_upgrade_lines": g["old_upgrade_line"].sum(),
        "any_payoff_soon": g["payoff_soon"].any(),
        "max_line_data_gb": g["data_last3"].max(),
        "max_line_data_peak_gb": g["data_max3"].max(),
        "max_line_hotspot_gb": g["hotspot_last3"].max(),
        "any_near_cap": g["near_cap"].any(),
        "any_over_cap": g["over_cap"].any(),
        "any_usage_growth": g["usage_growth"].any(),
        "all_low_use_premium": g["low_use_premium"].all(),
    })
    la["plan_price_cents"] = [
        plan_price_cents(*plans.set_index("sku").loc[sku, ["line_prices", "extra_line_cents"]], n)
        for sku, n in zip(la["plan_sku"], la["n_lines"])]

    # ---- billing
    bills = bills.sort_values(["account_id", "month"])
    months = sorted(bills["month"].unique())
    recent = set(months[-RECENT_BILL_MONTHS:])
    rb = bills[bills["month"].isin(recent)]
    last = bills.groupby("account_id").tail(1).set_index("account_id")["total_cents"]
    prior = bills[bills["month"] != bills.groupby("account_id")["month"].transform("max")] \
        .groupby("account_id")["total_cents"].mean()
    ba = pd.DataFrame({"last_bill_cents": last, "prior_avg_bill_cents": prior})
    ba["bill_increase_pct"] = (ba["last_bill_cents"] / ba["prior_avg_bill_cents"] - 1).clip(lower=0).fillna(0)
    ba["promo_expired_recent"] = rb[rb.change_reason == "promo_expired"].groupby("account_id").size() \
        .reindex(ba.index).fillna(0) > 0
    ba["installment_ended_recent"] = rb[rb.change_reason == "installment_ended"].groupby("account_id").size() \
        .reindex(ba.index).fillna(0) > 0

    # ---- bill shock: last month with promo_expired, or a >= BILL_SHOCK_PCT rise not caused by a new installment
    bills["prev_total"] = bills.groupby("account_id")["total_cents"].shift(1)
    shock = (bills["change_reason"] == "promo_expired") | (
        (bills["change_reason"] != "device_installment")
        & (bills["change_cents"] >= BILL_SHOCK_PCT * bills["prev_total"]))
    last_shock = bills[shock].groupby("account_id")["month"].max()
    ba["last_bill_shock_month"] = last_shock.reindex(ba.index)
    ba["days_since_bill_shock"] = [
        (pd.Timestamp(today) - pd.Timestamp(m + "-01")).days if isinstance(m, str) else np.nan
        for m in ba["last_bill_shock_month"]]

    # ---- support (90-day window, as in the sandbox API)
    sup["interaction_date"] = pd.to_datetime(sup["interaction_date"])
    s90 = sup[sup["interaction_date"] >= since]
    sg = s90.groupby("account_id")
    sa = pd.DataFrame({
        "support_90d": sg.size(),
        "unresolved_90d": sg["resolved"].apply(lambda r: int((1 - r).sum())),
        "neg_contacts_90d": sg["sentiment"].apply(lambda s: int((s < 0).sum())),
        "network_90d": s90[s90.topic == "network"].groupby("account_id").size(),
        "network_unresolved_90d": s90[(s90.topic == "network") & (s90.resolved == 0)].groupby("account_id").size(),
        "billing_90d": s90[s90.topic == "billing"].groupby("account_id").size(),
        "device_90d": s90[s90.topic == "device"].groupby("account_id").size(),
        "cancel_inquiry_90d": s90[s90.topic == "cancellation_inquiry"].groupby("account_id").size(),
        "avg_sentiment_90d": sg["sentiment"].mean(),
    })
    sa["avg_sentiment_all"] = sup.groupby("account_id")["sentiment"].mean()

    kinds = hint.groupby("account_id")["kind"].apply(set)

    df = acc.merge(sig, on="account_id", how="left").set_index("account_id")
    df = df.join(la).join(ba).join(sa)
    for c in ["support_90d", "unresolved_90d", "neg_contacts_90d", "network_90d", "network_unresolved_90d",
              "billing_90d", "device_90d", "cancel_inquiry_90d"]:
        df[c] = df[c].fillna(0).astype(int)
    df["avg_sentiment_90d"] = df["avg_sentiment_90d"].fillna(0.0)
    df["avg_sentiment_all"] = df["avg_sentiment_all"].fillna(0.0)
    df["has_home_internet"] = [("home_internet" in kinds.get(a, set())) for a in df.index]
    df["plan_misfit_share"] = (
        lines.assign(m=lambda x: (x["data_cap_gb"].notna() & (x["data_last3"] > x["data_cap_gb"]))
                     | x["low_use_premium"]).groupby("account_id")["m"].mean())

    return compute_flags(df.reset_index())


# features.csv column -> internal fact column (tm-data lane's real account-level features)
FEATURES_MAP = {
    "tenure_months": "tenure_months", "credit_tier": "credit_tier", "autopay": "autopay",
    "discount_group": "discount_group", "competitor_research_score": "competitor_research_score",
    "port_out_inquiry": "port_out_inquiry", "app_sessions_30d": "app_sessions_30d", "n_lines": "n_lines",
    "n_byod_lines": "n_byod", "plan_sku": "plan_sku", "plan_family": "plan_family", "plan_tier": "plan_tier",
    "plan_data_cap_gb": "plan_cap_gb", "plan_price_cents": "plan_price_cents",
    "financing_balance_total_cents": "financing_balance_cents",
    "monthly_installment_total_cents": "monthly_installments_cents",
    "max_financing_months_remaining": "max_financing_months_left", "max_device_age_months": "oldest_device_age_m",
    "financing_ends_within_3m": "any_payoff_soon", "last_bill_cents": "last_bill_cents",
    "prior_avg_bill_cents": "prior_avg_bill_cents", "bill_increase_pct": "bill_increase_pct",
    "promo_expired_recent": "promo_expired_recent", "installment_ended_recent": "installment_ended_recent",
    "support_90d": "support_90d", "unresolved_90d": "unresolved_90d", "negative_contacts_90d": "neg_contacts_90d",
    "billing_contacts_90d": "billing_90d", "device_contacts_90d": "device_90d",
    "network_contacts_90d": "network_90d", "cancellation_inquiry_contacts_90d": "cancel_inquiry_90d",
    "avg_sentiment_90d": "avg_sentiment_90d", "has_home_internet": "has_home_internet",
    "plan_misfit_share": "plan_misfit_share",
    "n_lines_device_36m_plus": "n_lines_device_36m_plus", "n_lines_over_cap_3m": "n_lines_over_cap_3m",
    "n_lines_usage_up_30pct": "n_lines_usage_up_30pct", "n_lines_light_on_premium": "n_lines_light_on_premium",
    "is_persona": "is_persona",
}


def apply_features_csv(facts: pd.DataFrame, path) -> tuple[pd.DataFrame, str]:
    """Override sandbox-derived facts with tm-data's features.csv where it has the field, then re-flag."""
    path = Path(path)
    if not path.exists():
        return facts, "features.csv not found; all facts computed from the sandbox"
    feat = pd.read_csv(path)
    cols = [c for c in FEATURES_MAP if c in feat.columns]
    f = feat[["account_id"] + cols].rename(columns=FEATURES_MAP)
    if "discount_group" in f:
        f["discount_group"] = f["discount_group"].replace({"none": np.nan, "": np.nan})
    merged = facts.set_index("account_id")
    f = f.set_index("account_id").reindex(merged.index)
    for c in f.columns:
        merged[c] = f[c].where(f[c].notna(), merged[c]) if c in merged else f[c]
    # blank plan_data_cap_gb = unlimited (keep NaN); blank device age = BYOD-only account (keep NaN)
    merged["plan_cap_gb"] = f["plan_cap_gb"] if "plan_cap_gb" in f else merged["plan_cap_gb"]
    merged["oldest_device_age_m"] = f["oldest_device_age_m"] if "oldest_device_age_m" in f else merged["oldest_device_age_m"]
    out = compute_flags(merged.reset_index(), from_features=True)
    missing = sorted(set(FEATURES_MAP) - set(cols))
    return out, (f"features.csv used for {len(cols)} columns ({len(feat)} rows)"
                 + (f"; missing {missing}" if missing else "")
                 + "; per-line peak usage/hotspot, near-cap 80%, paid-off & upgrade-ready lines from sandbox")


def compute_flags(df: pd.DataFrame, from_features: bool = False) -> pd.DataFrame:
    df = df.copy()
    for c in ["promo_expired_recent", "installment_ended_recent", "any_payoff_soon", "has_home_internet"]:
        df[c] = df[c].fillna(0).astype(bool)
    df["service_revenue_cents"] = (df["last_bill_cents"] - df["monthly_installments_cents"]).clip(lower=0)
    # ---- upgrade-moment detectors (booleans) -------------------------------------------------
    df["um_device_paid_off"] = df["installment_ended_recent"].astype(bool)          # billing_history
    df["um_payoff_soon"] = df["any_payoff_soon"].astype(bool)                        # lines.financing_months_remaining
    df["um_old_device"] = df["oldest_device_age_m"].fillna(0) >= OLD_DEVICE_MONTHS   # lines.device_purchase_date
    df["um_over_plan_cap"] = df["any_over_cap"].astype(bool)
    df["um_usage_growth"] = df["any_usage_growth"].astype(bool)
    if from_features:  # tm-data's line counts take precedence when present
        if "n_lines_device_36m_plus" in df:
            df["um_old_device"] = df["n_lines_device_36m_plus"].fillna(0) > 0
        if "n_lines_over_cap_3m" in df:
            df["um_over_plan_cap"] = df["n_lines_over_cap_3m"].fillna(0) > 0
        if "n_lines_usage_up_30pct" in df:
            df["um_usage_growth"] = df["n_lines_usage_up_30pct"].fillna(0) > 0
    df["um_near_plan_limit"] = (df["any_near_cap"].astype(bool) | df["um_over_plan_cap"])  # usage vs data cap
    df["um_promo_expired"] = df["promo_expired_recent"].astype(bool)                 # billing_history.change_reason
    df["um_student_graduating"] = ((df["discount_group"] == "student")
                                   & (df["tenure_months"] >= STUDENT_GRAD_TENURE_MONTHS))  # heuristic life event
    # um_plan_overpay is finalised in offers.py (needs the right-size search); start from the sandbox misfit rule
    df["um_plan_overpay"] = df["all_low_use_premium"].astype(bool)
    if from_features and "n_lines_light_on_premium" in df:
        df["um_plan_overpay"] = (df["n_lines_light_on_premium"] >= df["n_lines"]) & (df["n_lines"] > 0)
    return df


UPGRADE_MOMENT_COLS = [
    "um_device_paid_off", "um_payoff_soon", "um_old_device", "um_near_plan_limit", "um_over_plan_cap",
    "um_usage_growth", "um_plan_overpay", "um_promo_expired", "um_student_graduating",
]
