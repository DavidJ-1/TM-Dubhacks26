"""Interactive 'Customer journey' view: a pan/zoom field of synthetic customers. Click one and follow it:
signals -> Model A score -> ranked options (Model B) -> bucket -> delivered SMS.
ALL CUSTOMERS AND NUMBERS ARE SYNTHETIC. Everything is read from the repo's demo_data/ at build time.

Usage:  python app/viz/make_journey.py          (writes app/viz/customer_journey.html)
        TM_VIZ_OUT_DIR=/some/dir python app/viz/make_journey.py
Single self-contained HTML (vanilla JS + canvas, no CDN)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = Path(os.environ.get("TM_DEMO_DATA_DIR", REPO / "demo_data"))
OUT_DIR = Path(os.environ.get("TM_VIZ_OUT_DIR", HERE))
N_SAMPLE = 1350
SEED = 26

BUCKETS = [  # (key, label, sublabel)
    ("leave", "Leave alone", "no message sent"),
    ("checkin", "Check-in", "no-strings plan review"),
    ("fix", "Fix first", "agent callback"),
    ("carefix", "Care credit + fix", "$25 one-time + callback"),
    ("rightsize", "Plan right-size / variant", "saves $/mo"),
    ("stepup", "Plan upgrades", "step-up plan"),
    ("family", "Family upgrade", "kid/teen line"),
    ("other", "Other", "credit, bundle, bill-shock"),
]
CODE2BUCKET = {
    "do_nothing": "leave", "check_in": "checkin", "fix_first": "fix", "care_credit_fix_first": "carefix",
    "right_size": "rightsize", "variant_switch": "rightsize", "step_up": "stepup", "family_upgrade": "family",
}
ACTION_LABEL = {
    "do_nothing": "Do nothing", "care_credit": "$25 care credit", "loyalty_credit": "Loyalty credit",
    "keep_your_phone": "Keep-your-phone credit", "variant_switch": "Discount plan variant",
    "right_size": "Right-size plan", "step_up": "Step-up plan", "family_upgrade": "Family upgrade",
    "device_upgrade": "Device upgrade", "fix_first": "Fix-first callback",
    "care_credit_fix_first": "$25 care credit + fix", "bill_shock_price_lock": "Bill-shock relief",
    "check_in": "Check-in / plan review", "perk_reminder": "Perk reminder",
    "home_internet_bundle": "Home Internet bundle",
}


def plan_name(sku: str) -> str:
    s = str(sku).replace("TMO-STUB-PLAN-", "")
    base = {"MORE": "Experience More", "BEYOND": "Experience Beyond", "ESSENTIALS": "Essentials"}
    parts = s.split("-")
    name = base.get(parts[0], parts[0].title())
    extra = {"SAVER": " Saver", "4LINE": " 4-Line", "55": " 55+", "PARTNER": " Partner", "COMMUNITY": " Community"}
    return name + "".join(extra.get(p, " " + p.title()) for p in parts[1:])


def nz(x, nd=None):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    if nd is not None:
        return round(float(x), nd)
    return x


def saving_text(code: str, detail, price_usd: float) -> str | None:
    """Plain customer-facing $ from plan prices / action detail. Never the model's benefit estimate."""
    d = "" if not isinstance(detail, str) else detail
    m = re.search(r"saves \$(\d+(?:\.\d+)?)/mo", d)
    if m:
        s = float(m.group(1))
        return f"Saves ${s:,.0f}/mo (${price_usd:,.0f} \u2192 ${price_usd - s:,.0f})"
    m = re.search(r"\(\+\$(\d+(?:\.\d+)?)/mo\)", d)
    if m:
        s = float(m.group(1))
        return f"Plan change +${s:,.0f}/mo (${price_usd:,.0f} \u2192 ${price_usd + s:,.0f})"
    if code in ("care_credit", "care_credit_fix_first", "bill_shock_price_lock") or "$25" in d:
        return "$25 one-time credit"
    return None


def build() -> Path:
    cs = pd.read_csv(DATA / "churn_scores.csv")
    of = pd.read_csv(DATA / "offers.csv")
    ft = pd.read_csv(DATA / "features.csv")
    cand = pd.read_csv(DATA / "offer_candidates.csv.gz")
    if "offer_segment" in of.columns and "segment" not in of.columns:
        of = of.rename(columns={"offer_segment": "segment"})

    n_all = len(cs)
    n_flag = int(round(n_all * 0.10))
    cutoff = float(cs.sort_values("p_churn_90d", ascending=False).p_churn_90d.iloc[n_flag - 1])
    of["bucket"] = of.action_code.map(CODE2BUCKET).fillna("other")
    bucket_counts = of.bucket.value_counts().to_dict()
    n_contacted = int((of.action_code != "do_nothing").sum())

    df = cs.merge(of.drop(columns=["p_churn_90d", "risk_rank"], errors="ignore"), on="account_id", how="left")
    df = df.merge(ft.drop(columns=["segment"]), on="account_id", how="left")
    df["pct"] = df.p_churn_90d.rank(pct=True)

    rng = np.random.default_rng(SEED)
    persona = df.account_id.str.contains("PERSONA")
    rest = df[~persona]
    # stratify a bit: keep all flagged-ish share proportional, plus random rest
    samp = rest.sample(n=min(N_SAMPLE, len(rest)), random_state=SEED)
    sub = pd.concat([df[persona], samp]).reset_index(drop=True)

    reason_tab: list[str] = []
    rindex: dict[str, int] = {}

    def ri(s):
        if not isinstance(s, str) or not s:
            return -1
        if s not in rindex:
            rindex[s] = len(reason_tab)
            reason_tab.append(s)
        return rindex[s]

    cand = cand[cand.account_id.isin(sub.account_id)].copy()
    cand["rk"] = cand["rank"].fillna(99)
    cand = cand.sort_values(["account_id", "eligible", "rk"], ascending=[True, False, True])
    cg = {a: g for a, g in cand.groupby("account_id")}

    custs = []
    for _, r in sub.iterrows():
        price = float(r.plan_price_cents or 0) / 100
        code = r.action_code if isinstance(r.action_code, str) else "do_nothing"
        g = cg.get(r.account_id)
        cl = []
        if g is not None:
            for _, c in g.iterrows():
                cl.append([c.action_code, int(bool(c.eligible)), nz(c["rank"]) and int(c["rank"]),
                           nz(c.expected_value, 2), ri(c.blocked_or_ineligible_reason), int(bool(c.is_chosen))])
        pid = r.account_id.replace("ACC-PERSONA-", "P") if "PERSONA" in r.account_id else None
        custs.append({
            "id": r.account_id, "pid": pid, "p": round(float(r.p_churn_90d), 5), "rank": int(r.risk_rank),
            "pct": round(float(r.pct), 4), "plan": plan_name(r.plan_sku), "price": price,
            "lines": int(r.n_lines), "tenure": int(r.tenure_months), "lang": r.language,
            "sup": int(r.support_270d), "unres": int(r.unresolved_270d), "sent": nz(r.avg_sentiment, 2),
            "port": int(r.port_out_inquiry), "comp": nz(r.competitor_research_score, 2),
            "gb": nz(r.data_gb_3m_avg, 1), "app": nz(r.app_sessions_30d), "dev": nz(r.max_device_age_months, 0), "cap": nz(r.plan_data_cap_gb, 0), "unl": int(r.plan_is_unlimited or 0),
            "bill": nz(r.bill_increase_pct, 0),
            "rr": [ri(r[f"risk_reason_{i}"]) for i in (1, 2, 3)], "sr": [ri(r[f"stay_reason_{i}"]) for i in (1, 2, 3)],
            "code": code, "bucket": CODE2BUCKET.get(code, "other"), "seg": r.segment if isinstance(r.segment, str) else "",
            "act": r.action if isinstance(r.action, str) else "", "why": r.why_this_offer if isinstance(r.why_this_offer, str) else "",
            "save": saving_text(code, r.action_detail, price) if code != "do_nothing" else None,
            "en": r.message_en if isinstance(r.message_en, str) else None,
            "es": r.message_es if isinstance(r.message_es, str) else None,
            "c": cl,
        })

    meta = {
        "n_all": n_all, "n_flag": n_flag, "cutoff": cutoff, "n_contacted": n_contacted, "n_shown": len(custs),
        "buckets": [{"key": k, "label": l, "sub": s, "count": int(bucket_counts.get(k, 0))} for k, l, s in BUCKETS],
        "labels": ACTION_LABEL,
    }
    payload = json.dumps({"meta": meta, "reasons": reason_tab, "c": custs}, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    html = TEMPLATE.replace("/*__DATA__*/null", payload)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "customer_journey.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1e6:.2f} MB, {len(custs)} customers, synthetic)")
    return out


TEMPLATE = (HERE / "journey_template.html").read_text(encoding="utf-8") if (HERE / "journey_template.html").exists() else ""

if __name__ == "__main__":
    build()
