"""Build one feature row per sandbox account -> harness/out/features.csv.

Source: judge sandbox (mageshkumarj/dubhacks) data/sandbox.db, opened READ-ONLY (mode=ro).
All sandbox data is synthetic (stub data, as_of 2026-10-01). Money in cents.
Deterministic: no randomness. Run from repo root: python harness/features.py
Sandbox path: $DUBHACKS_DB (same as the top-level README/Makefile), else legacy $SANDBOX_DB, else
<repo>/vendor/dubhacks/data/sandbox.db (where `make setup` clones it), else <repo>/dubhacks/data/sandbox.db,
else <repo>/../dubhacks/data/sandbox.db
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


DB_CANDIDATES = (
    REPO / "vendor" / "dubhacks" / "data" / "sandbox.db",  # `make setup` clones the judge sandbox here
    REPO / "dubhacks" / "data" / "sandbox.db",
    REPO.parent / "dubhacks" / "data" / "sandbox.db",
)


def find_db() -> Path:
    # DUBHACKS_DB is the project-wide name (top-level README + Makefile); SANDBOX_DB still works as a fallback.
    for var in ("DUBHACKS_DB", "SANDBOX_DB"):
        if os.environ.get(var):
            return Path(os.environ[var]).resolve()
    for cand in DB_CANDIDATES:
        if cand.exists():
            return cand.resolve()
    raise FileNotFoundError("sandbox.db not found; run `make setup` or set DUBHACKS_DB=/path/to/sandbox.db")


OUT = HERE / "out" / "features.csv"
AS_OF = pd.Timestamp("2026-10-01")
PERSONA_PREFIX = "ACC-PERSONA-"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(find_db().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def q(conn, sql):
    return pd.read_sql(sql, conn)


def months_between(later: pd.Timestamp, earlier: pd.Series) -> pd.Series:
    return (later.year - earlier.dt.year) * 12 + (later.month - earlier.dt.month)


def plan_price_cents(row, plans) -> float:
    p = plans.loc[row["plan_sku"]]
    prices = [int(x) for x in str(p["line_prices"]).split(",") if x]
    n = int(row["n_lines"])
    total = sum(prices[:n])
    if n > len(prices):
        extra = p["extra_line_cents"] if pd.notna(p["extra_line_cents"]) else prices[-1]
        total += (n - len(prices)) * extra
    return float(total)


def build() -> pd.DataFrame:
    conn = connect()
    try:
        acc = q(conn, "SELECT account_id, segment, tenure_months, language, contact_preference, credit_tier, "
                      "autopay, discount_group FROM accounts")
        sig = q(conn, "SELECT * FROM account_signals")
        lines = q(conn, "SELECT * FROM lines")
        plans = q(conn, "SELECT * FROM plans").set_index("sku")
        devices = q(conn, "SELECT sku, tier AS device_tier FROM devices")
        usage = q(conn, "SELECT * FROM usage_monthly")
        bills = q(conn, "SELECT * FROM billing_history")
        sup = q(conn, "SELECT * FROM support_interactions")
        acc_add = q(conn, "SELECT aa.account_id, a.kind FROM account_addons aa JOIN addons a ON a.sku = aa.addon_sku")
        line_add = q(conn, "SELECT l.account_id, a.kind FROM line_addons la JOIN addons a ON a.sku = la.addon_sku "
                           "JOIN lines l ON l.line_id = la.line_id")
    finally:
        conn.close()

    df = acc.copy()
    df["is_persona"] = df["account_id"].str.startswith(PERSONA_PREFIX).astype(int)
    df["discount_group"] = df["discount_group"].fillna("none")
    df = df.merge(sig, on="account_id", how="left")

    # ---- lines / plan / devices / financing
    lines = lines.merge(devices, left_on="device_sku", right_on="sku", how="left")
    lines["device_purchase_date"] = pd.to_datetime(lines["device_purchase_date"])
    lines["device_age_months"] = months_between(AS_OF, lines["device_purchase_date"])
    lines["financed"] = (lines["financing_months_remaining"] > 0).astype(int)
    lines["fin_left_if_financed"] = lines["financing_months_remaining"].where(lines["financed"] == 1)
    lines["old_device_36m"] = (lines["device_age_months"] >= 36).astype(int)
    lines["flagship"] = (lines["device_tier"] == "flagship").astype(int)
    g = lines.groupby("account_id")
    L = pd.DataFrame({
        "n_lines": g.size(),
        "n_byod_lines": g["byod"].sum(),
        "plan_sku": g["plan_sku"].first(),
        "n_financed_lines": g["financed"].sum(),
        "financing_balance_total_cents": g["financing_balance_cents"].sum(),
        "monthly_installment_total_cents": g["monthly_installment_cents"].sum(),
        "max_financing_months_remaining": g["financing_months_remaining"].max(),
        "min_financing_months_left_financed": g["fin_left_if_financed"].min(),
        "max_device_age_months": g["device_age_months"].max(),   # NaN if all lines BYOD w/o date
        "mean_device_age_months": g["device_age_months"].mean().round(2),
        "n_lines_device_36m_plus": g["old_device_36m"].sum(),
        "n_tradein_eligible_lines": g["tradein_eligible"].sum(),
        "n_flagship_devices": g["flagship"].sum(),
    }).reset_index()
    L["financing_ends_within_3m"] = L["min_financing_months_left_financed"].between(1, 3).astype(int)
    L["min_financing_months_left_financed"] = L["min_financing_months_left_financed"].fillna(0)
    L["plan_family"] = L["plan_sku"].map(plans["family"])
    L["plan_tier"] = L["plan_sku"].map(plans["tier"])
    L["plan_data_cap_gb"] = L["plan_sku"].map(plans["data_cap_gb"])  # NaN = unlimited
    L["plan_is_unlimited"] = L["plan_data_cap_gb"].isna().astype(int)
    L["plan_price_cents"] = L.apply(plan_price_cents, axis=1, plans=plans)
    df = df.merge(L, on="account_id", how="left")

    # ---- usage (per line, then account). Months 2025-10..2026-09.
    months = sorted(usage["month"].unique())
    last3, prev3 = months[-3:], months[-6:-3]
    u = usage.merge(lines[["line_id", "account_id", "plan_sku"]], on="line_id")
    u["cap"] = u["plan_sku"].map(plans["data_cap_gb"])
    u["tier"] = u["plan_sku"].map(plans["tier"])
    pl = u.groupby("line_id").agg(avg_gb=("data_gb", "mean"), cap=("cap", "first"),
                                  tier=("tier", "first"), account_id=("account_id", "first"))
    # toy-model definition of misfit: 12m avg data over cap, or premium plan with < 5 GB avg
    pl["light_on_premium"] = ((pl["tier"] == "premium") & (pl["avg_gb"] < 5)).astype(int)
    pl["misfit"] = ((pl["cap"].notna() & (pl["avg_gb"] > pl["cap"])) | (pl["light_on_premium"] == 1)).astype(float)
    l3 = u[u["month"].isin(last3)].groupby("line_id").agg(gb3=("data_gb", "mean"), cap=("cap", "first"),
                                                         account_id=("account_id", "first"))
    l3 = l3.join(u[u["month"].isin(prev3)].groupby("line_id")["data_gb"].mean().rename("gb_prev3"))
    l3["over_cap_3m"] = (l3["cap"].notna() & (l3["gb3"] > l3["cap"])).astype(int)
    l3["growth"] = np.where(l3["gb_prev3"] > 0.5, l3["gb3"] / l3["gb_prev3"].clip(lower=0.5) - 1, 0.0)
    l3["growth30"] = (l3["growth"] >= 0.30).astype(int)
    ua = u[u["month"].isin(last3)].groupby(["account_id", "month"])[
        ["data_gb", "voice_minutes", "streaming_hours", "hotspot_gb"]].sum().groupby("account_id").mean()
    ua.columns = ["data_gb_3m_avg", "voice_min_3m_avg", "streaming_hours_3m_avg", "hotspot_gb_3m_avg"]
    prev = u[u["month"].isin(prev3)].groupby(["account_id", "month"])["data_gb"].sum().groupby("account_id").mean()
    U = ua.join(prev.rename("prev"))
    U["data_growth_pct"] = np.where(U["prev"] > 0.5, U["data_gb_3m_avg"] / U["prev"].clip(lower=0.5) - 1, 0.0)
    U = U.drop(columns="prev")
    U = U.join(pl.groupby("account_id").agg(plan_misfit_share=("misfit", "mean"),
                                            n_lines_light_on_premium=("light_on_premium", "sum")))
    U = U.join(l3.groupby("account_id").agg(n_lines_over_cap_3m=("over_cap_3m", "sum"),
                                           n_lines_usage_up_30pct=("growth30", "sum")))
    df = df.merge(U.round(4).reset_index(), on="account_id", how="left")

    # ---- billing (12 months per household)
    b = bills.sort_values(["account_id", "month"])
    bm = sorted(b["month"].unique())
    gb = b.groupby("account_id")
    max_m = gb["month"].transform("max")
    B = pd.DataFrame({"last_bill_cents": gb["total_cents"].last(),
                      "prior_avg_bill_cents": b[b["month"] < max_m].groupby("account_id")["total_cents"].mean().round(0)})
    # toy-model definition: max(0, last / mean(all prior months) - 1)
    B["bill_increase_pct"] = (B["last_bill_cents"] / B["prior_avg_bill_cents"] - 1).clip(lower=0).fillna(0).round(4)
    bill_3ago = b[b["month"] == bm[-4]].set_index("account_id")["total_cents"]
    B["bill_change_3m_pct"] = (B["last_bill_cents"] / bill_3ago - 1).round(4)
    rec = b[b["month"].isin(bm[-3:])]
    for col, reason in [("promo_expired_recent", "promo_expired"), ("installment_ended_recent", "installment_ended"),
                        ("new_installment_recent", "device_installment")]:
        B[col] = (rec["change_reason"] == reason).groupby(rec["account_id"]).any().astype(int)
    B["bill_changes_12m"] = (b["change_reason"] != "stable").groupby(b["account_id"]).sum()
    df = df.merge(B.reset_index(), on="account_id", how="left")

    # ---- support (sandbox covers 2026-01-04..2026-09-30, ~270 days)
    s = sup.copy()
    s["interaction_date"] = pd.to_datetime(s["interaction_date"])
    s["unres"] = 1 - s["resolved"]
    s["neg"] = (s["sentiment"] < 0).astype(int)
    s90 = s[s["interaction_date"] >= AS_OF - pd.Timedelta(days=90)]
    gs, g90 = s.groupby("account_id"), s90.groupby("account_id")
    S = pd.DataFrame({
        "support_270d": gs.size(),
        "support_90d": g90.size(),
        "unresolved_270d": gs["unres"].sum(),
        "unresolved_90d": g90["unres"].sum(),
        "negative_contacts_90d": g90["neg"].sum(),
        "avg_sentiment": gs["sentiment"].mean().round(4),  # toy def: all contacts, 0 if none
        "avg_sentiment_90d": g90["sentiment"].mean().round(4),
        "min_sentiment_270d": gs["sentiment"].min(),
        "days_since_last_contact": (AS_OF - gs["interaction_date"].max()).dt.days,
        "cancel_inquiries_270d": s[s["topic"] == "cancellation_inquiry"].groupby("account_id").size(),
    })
    for t in ["billing", "device", "plan_change", "network", "cancellation_inquiry"]:
        S[f"{t}_contacts_90d"] = s90[s90["topic"] == t].groupby("account_id").size()
    df = df.merge(S.reset_index(), on="account_id", how="left")
    df["days_since_last_contact"] = df["days_since_last_contact"].fillna(999)  # 999 = no contact in window
    df[list(S.columns)] = df[list(S.columns)].fillna(0)

    # ---- add-ons
    def has(kind):
        return df["account_id"].isin(acc_add.loc[acc_add["kind"] == kind, "account_id"]).astype(int)
    df["has_home_internet"] = has("home_internet")
    df["has_streaming_addon"] = has("streaming")
    df["n_account_addons"] = df["account_id"].map(acc_add.groupby("account_id").size()).fillna(0)
    df["n_line_addons"] = df["account_id"].map(line_add.groupby("account_id").size()).fillna(0)
    for col, kind in [("n_protection_addons", "protection"), ("n_connected_lines", "connected_line")]:
        df[col] = df["account_id"].map(line_add[line_add["kind"] == kind].groupby("account_id").size()).fillna(0)

    for c in df.columns:
        if df[c].dtype == float and c != "plan_data_cap_gb" and df[c].notna().all() and (df[c] % 1 == 0).all():
            df[c] = df[c].astype(int)
    df = df.sort_values("account_id").reset_index(drop=True)
    first = ["account_id", "is_persona"]
    return df[first + [c for c in df.columns if c not in first]]


def main():
    df = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT} rows={len(df)} cols={df.shape[1]}")


if __name__ == "__main__":
    main()
