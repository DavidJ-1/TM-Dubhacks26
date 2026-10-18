"""Model A (churn) feature prep, shared by churn_model.py, model_harness.py and the bench.

ALL DATA IS SYNTHETIC (judge sandbox stub data + simulated labels).

    from churn_features import prepare
    X = prepare(features_df)          # float DataFrame indexed by account_id, model-ready, no NaN

What prepare() does:
  * blanks are meaningful, not generic NaN:
      max/mean_device_age_months blank -> BYOD-only household: is_byod=1, age 0
      plan_data_cap_gb blank          -> unlimited plan: is_unlimited=1, cap column dropped (never imputed)
      prior_avg_bill_cents / bill_change_3m_pct blank -> short billing history: short_history=1, change 0
  * support: raw contact COUNTS are dropped (support_90d/270d, device/plan_change/network/billing topic counts,
    days_since_last_contact) so a happy frequent caller (persona 24) is not read as risk. Kept: unresolved and
    negative-sentiment contacts, sentiment, cancellation inquiries, and troubled_4plus (4+ contacts AND at least
    one unresolved or negative).
  * domain flags: early_tenure (<12 mo), tenure_capped60, no_financing, no_autopay, low_app_use (<=3 sessions),
    neg_sentiment = max(0, -avg_sentiment), extra_lines.
  * drops ids/leaks: account_id (-> index), is_persona, plan_sku, any churn/label/probability/toy column.
  * categoricals one-hot (low cardinality only); everything else numeric.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

RAW_CONTACT_COUNTS = ["support_90d", "support_270d", "device_contacts_90d", "plan_change_contacts_90d",
                      "network_contacts_90d", "billing_contacts_90d", "days_since_last_contact"]
ALWAYS_DROP = ["is_persona", "plan_sku", "plan_data_cap_gb", "prior_avg_bill_cents"]
# not used as model inputs: protected-ish attributes a care rep shouldn't see as a churn reason (and the
# sandbox analysis found no effect for credit tier)
FAIRNESS_DROP = ["language", "credit_tier"]
# kept in the model, but never shown as a plain-English reason (no actionable meaning for a rep)
NON_REASON_GROUPS = {"segment", "contact_preference", "discount_group", "plan_family", "plan_tier",
                     "voice_min_3m_avg", "n_line_addons", "n_account_addons", "n_tradein_eligible_lines",
                     "n_flagship_devices", "plan_price_cents", "is_unlimited", "monthly_installment_total_cents",
                     "n_protection_addons", "n_connected_lines", "data_growth_pct", "hotspot_gb_3m_avg",
                     "streaming_hours_3m_avg", "data_gb_3m_avg", "n_lines_usage_up_30pct", "has_streaming_addon"}
LEAK_PATTERN = re.compile(r"(churn|label|p_true|hazard|^toy_|_toy$|^y$|^target$|driver)", re.I)
MAX_CATEGORY_LEVELS = 20
# curated, interpretable subset used by Model A by default (prepare() still returns everything for the bench)
CORE_FEATURES = ["unresolved_90d", "negative_contacts_90d", "neg_sentiment", "troubled_4plus", "cancel_inquiries_270d",
                 "bill_increase_pct", "promo_expired_recent", "competitor_research_score", "port_out_inquiry",
                 "tenure_capped60", "early_tenure", "app_sessions_30d", "low_app_use", "plan_misfit_share",
                 "no_financing", "no_autopay", "max_device_age_months", "extra_lines", "is_byod", "short_history",
                 "financing_ends_within_3m", "has_home_internet"]


def leak_columns(cols) -> list[str]:
    return [c for c in cols if LEAK_PATTERN.search(str(c))]


def prepare(features: pd.DataFrame, drop_raw_contacts: bool = True) -> pd.DataFrame:
    f = features.copy()
    if "account_id" in f.columns:
        f = f.set_index("account_id")
    out = pd.DataFrame(index=f.index)

    def col(name, default=0.0):
        return f[name].astype(float) if name in f.columns else pd.Series(default, index=f.index, dtype=float)

    # --- meaningful blanks
    if "max_device_age_months" in f.columns:
        out["is_byod"] = f["max_device_age_months"].isna().astype(float)
        for c in ("max_device_age_months", "mean_device_age_months"):
            if c in f.columns:
                f[c] = f[c].fillna(0.0)
    if "plan_data_cap_gb" in f.columns:
        out["is_unlimited"] = f["plan_data_cap_gb"].isna().astype(float)
        f = f.drop(columns=[c for c in ("plan_is_unlimited",) if c in f.columns])
    if "prior_avg_bill_cents" in f.columns or "bill_change_3m_pct" in f.columns:
        short = pd.Series(False, index=f.index)
        for c in ("prior_avg_bill_cents", "bill_change_3m_pct"):
            if c in f.columns:
                short |= f[c].isna()
        out["short_history"] = short.astype(float)
        if "bill_change_3m_pct" in f.columns:
            f["bill_change_3m_pct"] = f["bill_change_3m_pct"].fillna(0.0)

    # --- domain features (skipped silently if source column absent)
    if "tenure_months" in f.columns:
        out["early_tenure"] = (f["tenure_months"] < 12).astype(float)
        out["tenure_capped60"] = f["tenure_months"].clip(upper=60).astype(float)
    if "n_financed_lines" in f.columns:
        out["no_financing"] = (f["n_financed_lines"] == 0).astype(float)
    if "autopay" in f.columns:
        out["no_autopay"] = (f["autopay"] == 0).astype(float)
    if "app_sessions_30d" in f.columns:
        out["low_app_use"] = (f["app_sessions_30d"] <= 3).astype(float)
    if "avg_sentiment" in f.columns:
        out["neg_sentiment"] = (-col("avg_sentiment").fillna(0)).clip(lower=0)
    if "n_lines" in f.columns:
        out["extra_lines"] = (col("n_lines") - 1).clip(lower=0)
    if "support_90d" in f.columns and ("unresolved_90d" in f.columns or "negative_contacts_90d" in f.columns):
        bad = (col("unresolved_90d").fillna(0) > 0) | (col("negative_contacts_90d").fillna(0) > 0)
        out["troubled_4plus"] = ((col("support_90d").fillna(0) >= 4) & bad).astype(float)

    # --- drop ids, leaks, raw counts
    drop = set(ALWAYS_DROP) | set(FAIRNESS_DROP) | set(leak_columns(f.columns)) | set(out.columns)
    if drop_raw_contacts:
        drop |= set(RAW_CONTACT_COUNTS)
    f = f.drop(columns=[c for c in f.columns if c in drop])

    # --- numeric vs categorical auto-detect
    num, cat = [], []
    for c in f.columns:
        if pd.api.types.is_bool_dtype(f[c]) or pd.api.types.is_numeric_dtype(f[c]):
            num.append(c)
        elif f[c].nunique(dropna=True) <= MAX_CATEGORY_LEVELS:
            cat.append(c)
    for c in num:
        s = f[c].astype(float)
        out[c] = s.fillna(s.median() if s.notna().any() else 0.0)
    if cat:
        d = pd.get_dummies(f[cat].astype("string").fillna("unknown"), prefix=cat, prefix_sep="=", dtype=float)
        out = out.join(d)
    out = out.loc[:, out.std(ddof=0) > 0]  # drop constant columns
    return out.astype(float)


# ---------------------------------------------------------------- plain-English reason text
# group -> features in it. Contributions are summed per group so reasons don't repeat.
REASON_GROUPS = {
    "unresolved": ["unresolved_90d", "unresolved_270d", "troubled_4plus"],
    "sentiment": ["negative_contacts_90d", "neg_sentiment", "avg_sentiment", "avg_sentiment_90d", "min_sentiment_270d"],
    "cancel": ["cancel_inquiries_270d", "cancellation_inquiry_contacts_90d"],
    "bill": ["bill_increase_pct", "bill_change_3m_pct", "promo_expired_recent", "last_bill_cents", "bill_changes_12m"],
    "competitor": ["competitor_research_score"],
    "port_out": ["port_out_inquiry"],
    "tenure": ["tenure_months", "tenure_capped60", "early_tenure", "short_history"],
    "app": ["app_sessions_30d", "low_app_use"],
    "plan_fit": ["plan_misfit_share", "n_lines_light_on_premium", "n_lines_over_cap_3m"],
    "financing": ["no_financing", "n_financed_lines", "financing_balance_total_cents", "monthly_installment_total_cents",
                  "max_financing_months_remaining", "min_financing_months_left_financed", "financing_ends_within_3m",
                  "installment_ended_recent", "new_installment_recent"],
    "device": ["max_device_age_months", "mean_device_age_months", "n_lines_device_36m_plus", "is_byod", "n_byod_lines"],
    "autopay": ["no_autopay", "autopay"],
    "lines": ["extra_lines", "n_lines"],
}
_FEATURE_GROUP = {feat: g for g, feats in REASON_GROUPS.items() for feat in feats}


def reason_group(feature: str) -> str:
    return _FEATURE_GROUP.get(feature, feature.split("=")[0])


def _money(c):
    return f"${float(c) / 100:,.0f}"


def phrase(group: str, row: pd.Series, risk: bool) -> str:
    """Short care-rep phrase for a reason group, using the account's raw feature values (row)."""
    g = lambda k, d=0: row[k] if k in row.index and pd.notna(row[k]) else d  # noqa: E731
    if group == "unresolved":
        n = int(g("unresolved_90d"))
        return f"{n} unresolved support contact{'s' * (n != 1)} in 90 days" if risk and n else \
            ("No unresolved support issues" if not risk else "Recent unresolved support issues")
    if group == "sentiment":
        n = int(g("negative_contacts_90d"))
        if risk:
            return f"{n} unhappy support contact{'s' * (n != 1)} in 90 days" if n else "Unhappy tone in past support contacts"
        return "Positive experiences with support" if g("support_90d") or g("support_270d") else "No complaints on record"
    if group == "cancel":
        n = int(g("cancel_inquiries_270d"))
        return f"Asked about cancelling ({n}x this year)" if risk else "Never asked about cancelling"
    if group == "bill":
        pct = float(g("bill_increase_pct"))
        if risk:
            if g("promo_expired_recent"):
                return f"Promo ended, bill up {pct:.0%}" if pct >= 0.02 else "Promo recently ended"
            return f"Bill up {pct:.0%} vs prior months" if pct >= 0.02 else "Recent bill change"
        return "Steady bill, no recent jumps"
    if group == "competitor":
        s = float(g("competitor_research_score"))
        return f"Shopping other carriers (score {s:.2f})" if risk else "Not shopping other carriers"
    if group == "port_out":
        return "Asked about porting number out" if risk else "No port-out inquiry"
    if group == "tenure":
        t = int(g("tenure_months"))
        yrs = f"{t // 12} yr{'s' * (t >= 24)}" if t >= 12 else f"{t} mo"
        return f"New customer ({yrs})" if risk else f"Long-time customer ({yrs})"
    if group == "app":
        n = int(g("app_sessions_30d"))
        return f"Rarely uses the app ({n} sessions/30d)" if risk else f"Active app user ({n} sessions/30d)"
    if group == "plan_fit":
        if not risk:
            return "Plan fits their usage"
        if g("n_lines_over_cap_3m"):
            return "Using more data than plan includes"
        if g("n_lines_light_on_premium"):
            return "Paying for premium plan, light usage"
        return "Plan doesn't fit their usage"
    if group == "financing":
        n, m = int(g("n_financed_lines")), int(g("min_financing_months_left_financed"))
        if risk:
            return "No phone payments keeping them" if n == 0 else \
                ("Phone paid off soon" if g("financing_ends_within_3m") else "Phone financing status")
        return f"Paying off {n} phone{'s' * (n != 1)} ({m} mo left)" if n else "Phone financing in place"
    if group == "device":
        a = int(g("max_device_age_months"))
        if not a:
            return "Brought own phone (BYOD)" if risk else "BYOD household"
        return f"Phone is {a} months old" if risk else f"Newer phone ({a} months old)"
    if group == "autopay":
        return "Not on AutoPay" if risk else "On AutoPay"
    if group == "lines":
        n = int(g("n_lines", 1))
        return "Single line account" if risk else f"{n} lines on account"
    # fallback: categorical -> "Segment: family"; numeric -> "High/Low <readable name>"
    name = READABLE.get(group, group.replace("_", " "))
    if group in row.index and not pd.api.types.is_number(row[group]):
        return f"{name.capitalize()}: {str(row[group]).replace('_', ' ')}"
    v = g(group)
    if set(pd.Series([v]).astype(float)) <= {0.0, 1.0} and group.startswith(("has_", "is_")):
        return f"{'Has' if v else 'No'} {name}"
    return f"{'Higher' if (v and risk) or (not risk and not v) else 'Lower'} {name}"


READABLE = {
    "segment": "segment", "language": "language", "contact_preference": "contact preference",
    "credit_tier": "credit tier", "discount_group": "discount group", "plan_family": "plan",
    "plan_tier": "plan tier", "has_home_internet": "Home Internet bundle", "has_streaming_addon": "streaming add-on",
    "data_gb_3m_avg": "data use", "voice_min_3m_avg": "call minutes", "streaming_hours_3m_avg": "streaming",
    "hotspot_gb_3m_avg": "hotspot use", "data_growth_pct": "data growth", "plan_price_cents": "plan price",
    "n_account_addons": "add-ons", "n_line_addons": "line add-ons", "n_protection_addons": "device protection",
    "n_tradein_eligible_lines": "trade-in eligible lines", "n_flagship_devices": "flagship phones",
    "n_lines_usage_up_30pct": "lines with growing usage", "n_connected_lines": "connected devices",
}
