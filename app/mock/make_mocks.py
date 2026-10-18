"""Generate MOCK stand-ins for harness/out/{features,labels,churn_scores,offers}.csv.

Owned by the tm-ui lane. These are placeholders so the Streamlit demo runs before
tm-data / tm-churn / tm-offers land their real outputs. Every row is synthetic:
signal values are read (read-only) from the judge's fully synthetic sandbox.db
when it is available; scores, reasons and offers are made up by a toy heuristic
here and are NOT Model A / Model B.

Run:  python app/mock/make_mocks.py   (writes app/mock/*.csv, seed fixed)
"""
from __future__ import annotations

import math
import os
import random
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SEED = 2026
N_RANDOM = 39
AS_OF = "2026-10-01"
DEMO_PERSONAS = ["04", "10", "21", "22", "23", "24", "25", "27", "28"]
SANDBOX_CANDIDATES = [
    os.environ.get("TM_SANDBOX_DB", ""),
    str(HERE.parents[1] / "dubhacks" / "data" / "sandbox.db"),  # submodule (planned)
    "/workspace/tmobile/dubhacks/data/sandbox.db",  # shared-box read-only clone
]

# ---- contract columns (LANES.md) -------------------------------------------
CHURN_COLS = ["account_id", "p_churn_90d", "risk_rank",
              "risk_reason_1", "risk_reason_2", "risk_reason_3",
              "stay_reason_1", "stay_reason_2", "stay_reason_3"]
# LANES.md says "upgrade_moment flags" without naming them; these 4 names follow
# the plan doc's list of upgrade moments. Flag columns are prefixed upgrade_.
# Flag names aligned with tm-offers' real harness/out/offers.csv (um_* + aggregate upgrade_moment).
UPGRADE_FLAGS = ["upgrade_moment", "um_device_paid_off", "um_usage_growth", "um_student_graduating", "um_old_device"]
OFFER_COLS = ["account_id", "action", "expected_value", "reason"] + UPGRADE_FLAGS
LABEL_COLS = ["account_id", "churn_90d"]  # LANES.md gives no columns; minimal guess


def find_sandbox() -> str | None:
    for p in SANDBOX_CANDIDATES:
        if p and Path(p).exists():
            return p
    return None


def load_signals(db: str, ids: list[str]) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    q = ",".join("?" * len(ids))
    acc = pd.read_sql(f"select a.*, s.competitor_research_score, s.port_out_inquiry, s.app_sessions_30d "
                      f"from accounts a join account_signals s using(account_id) where account_id in ({q})", con, params=ids)
    lines = pd.read_sql(f"select l.*, p.name plan_name, p.data_cap_gb from lines l join plans p on p.sku=l.plan_sku "
                        f"where account_id in ({q})", con, params=ids)
    dev = pd.read_sql("select sku, name device_name from devices", con)
    lines = lines.merge(dev, left_on="device_sku", right_on="sku", how="left")
    lines["device_age_months"] = ((pd.Timestamp(AS_OF) - pd.to_datetime(lines["device_purchase_date"])).dt.days / 30.44).round()
    use = pd.read_sql(f"select u.line_id, u.month, u.data_gb from usage_monthly u join lines l using(line_id) "
                      f"where l.account_id in ({q})", con, params=ids)
    bill = pd.read_sql(f"select * from billing_history where account_id in ({q}) order by month", con, params=ids)
    sup = pd.read_sql(f"select * from support_interactions where account_id in ({q})", con, params=ids)
    con.close()

    sup["days_ago"] = (pd.Timestamp(AS_OF) - pd.to_datetime(sup["interaction_date"])).dt.days
    s90 = sup[sup.days_ago <= 90]
    sup_agg = pd.DataFrame({
        "support_contacts_90d": s90.groupby("account_id").size(),
        "unresolved_90d": s90[s90.resolved == 0].groupby("account_id").size(),
        "avg_sentiment_90d": s90.groupby("account_id").sentiment.mean().round(2),
        "network_contacts_90d": s90[s90.topic == "network"].groupby("account_id").size(),
        "cancel_inquiries_270d": sup[sup.topic == "cancellation_inquiry"].groupby("account_id").size(),
    })
    last = bill.groupby("account_id").tail(1).set_index("account_id")
    prior = bill.groupby("account_id").apply(lambda g: g.iloc[-4:-1].total_cents.mean(), include_groups=False)
    recent = bill[bill.month >= "2026-07"]
    bill_agg = pd.DataFrame({
        "monthly_bill_usd": (last.total_cents / 100).round(2),
        "bill_change_pct_3m": ((last.total_cents / prior - 1) * 100).round(1),
        "promo_expired_recent": recent[recent.change_reason == "promo_expired"].groupby("account_id").size().gt(0).astype(int),
        "installment_ended_recent": recent[recent.change_reason == "installment_ended"].groupby("account_id").size().gt(0).astype(int),
    })
    u = use.merge(lines[["line_id", "account_id", "data_cap_gb"]], on="line_id")
    u_last = u[u.month == u.month.max()]
    u_prev = u[u.month.isin(sorted(u.month.unique())[-6:-3])].groupby("line_id").data_gb.mean()
    u_last = u_last.assign(prev=u_last.line_id.map(u_prev))
    u_last["growth"] = (u_last.data_gb / u_last.prev - 1) * 100
    u_last["over_cap"] = (u_last.data_cap_gb.notna() & (u_last.data_gb > u_last.data_cap_gb)).astype(int)
    use_agg = pd.DataFrame({
        "usage_growth_pct": u_last.groupby("account_id").growth.max().round(0),
        "over_plan_cap_lines": u_last.groupby("account_id").over_cap.sum(),
    })
    line_agg = pd.DataFrame({
        "lines": lines.groupby("account_id").size(),
        "plan_name": lines.groupby("account_id").plan_name.first(),
        "devices": lines.groupby("account_id").device_name.apply(lambda s: ", ".join(sorted(set(s.dropna())))),
        "financing_months_left_min": lines.groupby("account_id").financing_months_remaining.min(),
        "max_device_age_months": lines.groupby("account_id").device_age_months.max(),
    })
    df = acc.set_index("account_id").join([line_agg, bill_agg, use_agg, sup_agg])
    for c in ["support_contacts_90d", "unresolved_90d", "network_contacts_90d", "cancel_inquiries_270d",
              "promo_expired_recent", "installment_ended_recent", "over_plan_cap_lines"]:
        df[c] = df[c].fillna(0).astype(int)
    df["avg_sentiment_90d"] = df["avg_sentiment_90d"].fillna(0.0)
    return df.reset_index()


def fake_signals(ids: list[str], rng: random.Random) -> pd.DataFrame:
    """Fallback if no sandbox is on disk: purely random synthetic rows."""
    rows = []
    for a in ids:
        rows.append(dict(account_id=a, segment=rng.choice(["family", "couple", "single", "student", "senior", "smb"]),
                         tenure_months=rng.randint(1, 180), language=rng.choice(["en"] * 4 + ["es"]),
                         contact_preference=rng.choice(["app", "sms", "email", "call"]), credit_tier="prime",
                         autopay=rng.randint(0, 1), discount_group=None, persona_note=None,
                         competitor_research_score=round(rng.random() ** 2, 2), port_out_inquiry=int(rng.random() < .05),
                         app_sessions_30d=rng.randint(0, 40), lines=rng.randint(1, 5), plan_name="Experience More 2.0",
                         devices="Synthetic Phone", financing_months_left_min=rng.randint(0, 24),
                         max_device_age_months=rng.randint(1, 60), monthly_bill_usd=round(rng.uniform(60, 400), 2),
                         bill_change_pct_3m=round(rng.gauss(0, 6), 1), promo_expired_recent=int(rng.random() < .1),
                         installment_ended_recent=int(rng.random() < .05), usage_growth_pct=round(rng.gauss(5, 20)),
                         over_plan_cap_lines=int(rng.random() < .05), support_contacts_90d=rng.choice([0, 0, 0, 1, 2, 3, 5]),
                         unresolved_90d=rng.choice([0, 0, 1]), avg_sentiment_90d=round(rng.uniform(-.8, .6), 2),
                         network_contacts_90d=rng.choice([0, 0, 1]), cancel_inquiries_270d=int(rng.random() < .07)))
    return pd.DataFrame(rows)


# ---- toy scoring (NOT Model A) ---------------------------------------------
def toy_score(r) -> tuple[float, list[str], list[str]]:
    contrib = {
        f"{r.support_contacts_90d} support contacts in 90 days": 0.45 * r.support_contacts_90d * (1.0 if r.avg_sentiment_90d < 0.2 else 0.2),
        f"{r.unresolved_90d} unresolved support issue(s)": 0.6 * r.unresolved_90d,
        f"Bill up {r.bill_change_pct_3m:.0f}% vs prior 3 months": 0.08 * max(0, r.bill_change_pct_3m or 0),
        "Promo credit expired recently": 1.0 * r.promo_expired_recent,
        f"Shopping competitors (research score {r.competitor_research_score:.2f})": 3.0 * r.competitor_research_score,
        "Asked about porting out": 1.4 * r.port_out_inquiry,
        "Asked about cancelling": 0.9 * min(r.cancel_inquiries_270d, 2),
        f"{r.network_contacts_90d} coverage/network complaint(s)": 0.5 * r.network_contacts_90d,
        "Negative support sentiment": 1.2 * max(0, -r.avg_sentiment_90d),
    }
    logit = -3.3 + 0.65 * sum(contrib.values()) - 0.004 * r.tenure_months
    p = 1 / (1 + math.exp(-logit))
    risk = [k for k, v in sorted(contrib.items(), key=lambda kv: -kv[1]) if v > 0.05][:3]
    stay_c = {
        f"{r.tenure_months // 12} years with T-Mobile" if r.tenure_months >= 12 else "Recently joined": 0.01 * r.tenure_months,
        "No unresolved support issues": 1.0 if r.unresolved_90d == 0 else 0,
        "Steady bill (no recent jump)": 1.0 if abs(r.bill_change_pct_3m or 0) < 3 else 0,
        "Not shopping competitors": 1.0 - r.competitor_research_score,
        f"Active in the T-Life app ({r.app_sessions_30d} sessions/30d)": 0.03 * r.app_sessions_30d,
        "Positive support experiences": max(0, r.avg_sentiment_90d) * 2,
        f"Phone financing keeps them on ({r.financing_months_left_min} months left)": 0.04 * r.financing_months_left_min,
    }
    stay = [k for k, v in sorted(stay_c.items(), key=lambda kv: -kv[1]) if v > 0.1][:3]
    while len(risk) < 3:
        risk.append("")
    while len(stay) < 3:
        stay.append("")
    return p, risk, stay


def toy_offer(r, p: float) -> dict:
    value = r.monthly_bill_usd * 12 * 0.55
    flags = dict(
        um_device_paid_off=int(r.installment_ended_recent == 1 or (r.financing_months_left_min == 0 and r.max_device_age_months >= 24)),
        um_usage_growth=int((r.usage_growth_pct or 0) >= 30 or r.over_plan_cap_lines > 0),
        um_student_graduating=int(r.segment == "student"),
        um_old_device=int((r.max_device_age_months or 0) >= 36),
    )
    cands = {"do_nothing": (0.0, "Expected value of any offer is below zero, so we wait")}
    annoy = 15 + (25 if r.avg_sentiment_90d > 0.2 and r.support_contacts_90d >= 3 else 0)
    if r.network_contacts_90d >= 1:
        cands["fix_first_callback"] = (p * 0.30 * value - 20 - annoy, "Coverage complaints: fix the network issue first, no discount")
    if r.promo_expired_recent or (r.bill_change_pct_3m or 0) > 5:
        cands["care_credit_25"] = (p * 0.35 * value - 25 * 6 - annoy, "Bill jumped after a promo ended; $25/mo care credit softens it")
    if r.tenure_months >= 24:
        cands["loyalty_credit"] = (p * 0.20 * value - 5 * 12 - annoy, "Long tenure; small loyalty credit recognizes it")
    if r.financing_months_left_min == 0 and flags["um_device_paid_off"]:
        cands["keep_phone_credit"] = (p * 0.18 * value - 20 * 6 - annoy, "Phone is paid off; keep-your-phone credit")
    if flags["um_usage_growth"] or flags["um_student_graduating"]:
        cands["step_up_plan"] = (25 + p * 0.10 * value - annoy, "Usage is outgrowing the plan (upgrade moment)")
    if flags["um_old_device"] and p < 0.3:
        cands["device_upgrade"] = (40 + p * 0.10 * value - annoy, "Phone is 3+ years old (upgrade moment)")
    if r.monthly_bill_usd > 250 and r.lines <= 2 and p > 0.3:
        cands["right_size_plan"] = (p * 0.25 * value - 15 * 12 - annoy, "Paying for more plan than they use")
    flags = {"upgrade_moment": int(any(flags.values())), **flags}
    best = max(cands.items(), key=lambda kv: kv[1][0])
    action, (ev, reason) = best
    if ev <= 0:
        action, ev, reason = "do_nothing", 0.0, cands["do_nothing"][1]
    return dict(action=action, expected_value=round(ev, 2), reason=reason, **flags)


# Column names follow tm-data's real harness/out/features.csv (harness/features.py), since
# LANES.md does not list features columns. Units converted to match (cents, fractions).
TMDATA_RENAME = {
    "lines": "n_lines", "support_contacts_90d": "support_90d", "over_plan_cap_lines": "n_lines_over_cap_3m",
    "financing_months_left_min": "min_financing_months_left_financed",
}


def write_features(feats: pd.DataFrame) -> None:
    real = HERE.parents[1] / "harness" / "out" / "features.csv"
    if real.exists():  # exact tm-data schema: take the same accounts' rows
        r = pd.read_csv(real)
        sub = r[r.account_id.isin(feats.account_id)]
        if len(sub) == len(feats):
            sub.to_csv(HERE / "features.csv", index=False)
            print("mock features.csv = subset of tm-data features.csv (same schema)")
            return
    f = feats.rename(columns=TMDATA_RENAME).copy()
    f["last_bill_cents"] = (f.pop("monthly_bill_usd") * 100).round().astype(int)
    f["bill_change_3m_pct"] = (f.pop("bill_change_pct_3m") / 100).round(4)
    f["data_growth_pct"] = (f.pop("usage_growth_pct") / 100).round(4)
    f = f.drop(columns=["plan_name", "devices", "persona_note"], errors="ignore")
    f.to_csv(HERE / "features.csv", index=False)


def main() -> None:
    rng = random.Random(SEED)
    persona_ids = [f"ACC-PERSONA-{p}" for p in DEMO_PERSONAS]
    db = find_sandbox()
    if db:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        regular = [r[0] for r in con.execute("select account_id from accounts where account_id not like 'ACC-PERSONA%' order by account_id")]
        con.close()
        ids = persona_ids + rng.sample(regular, N_RANDOM)
        feats = load_signals(db, ids)
        print(f"signals read (read-only) from {db}")
    else:
        ids = persona_ids + [f"ACC-MOCK-{i:03d}" for i in range(N_RANDOM)]
        feats = fake_signals(ids, rng)
        print("no sandbox found; using random synthetic signals")

    churn_rows, offer_rows, label_rows = [], [], []
    for r in feats.itertuples():
        p, risk, stay = toy_score(r)
        churn_rows.append(dict(account_id=r.account_id, p_churn_90d=round(p, 4),
                               **{f"risk_reason_{i+1}": risk[i] for i in range(3)},
                               **{f"stay_reason_{i+1}": stay[i] for i in range(3)}))
        offer_rows.append(dict(account_id=r.account_id, **toy_offer(r, p)))
        label_rows.append(dict(account_id=r.account_id, churn_90d=int(rng.random() < p)))
    churn = pd.DataFrame(churn_rows)
    churn["risk_rank"] = churn.p_churn_90d.rank(ascending=False, method="first").astype(int)
    churn = churn[CHURN_COLS].sort_values("risk_rank")
    offers = pd.DataFrame(offer_rows)[OFFER_COLS]

    write_features(feats)
    pd.DataFrame(label_rows)[LABEL_COLS].to_csv(HERE / "labels.csv", index=False)
    churn.to_csv(HERE / "churn_scores.csv", index=False)
    offers.to_csv(HERE / "offers.csv", index=False)
    print(f"wrote {len(feats)} mock accounts to {HERE}")
    print(offers.action.value_counts().to_string())


if __name__ == "__main__":
    main()
