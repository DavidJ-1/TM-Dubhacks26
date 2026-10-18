"""Data loaders for the scroll page (adapted from the orbit design mock's odata.py / mockdata.py).

Read-only: every input is a file in this repo (demo_data/, docs/outreach/outreach_card.csv, docs/considerations.csv);
falls back to the shared clone if the worktree lacks one. The risk scorer's model cache is redirected to a temp dir,
so nothing is ever written into the repo. All number logic lives here or in scroll_app.py; app/orbit_sections.py only
draws what it is handed, so swapping the sections file never changes a number.
"""
from __future__ import annotations

import math
import re
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SHARED = Path("/workspace/tmobile/TM-Dubhacks26")
PERSONA = "ACC-PERSONA-"
DEMO = ["38", "04", "21", "24"]
_TMP = Path(tempfile.mkdtemp(prefix="scroll_scorer_"))


def _pick(rel: str) -> Path:
    p = ROOT / rel
    return p if p.exists() else SHARED / rel


D = _pick("demo_data")
OUTREACH = _pick("docs/outreach/outreach_card.csv")
CONSIDERATIONS = _pick("docs/considerations.csv")
REPO = D.parent

# plain-language clean-up for strings that come straight from data files
_CLEAN = [
    (re.compile(r"asked about porting (their )?number out", re.I), "Asked about transferring their number"),
    (re.compile(r"port[- ]?out inquir(y|ies)", re.I), "number-transfer question"),
    (re.compile(r"port[- ]?out", re.I), "number-transfer"),
    (re.compile(r"\s*\((?:[a-z_]+\.)+[a-z_]+\)"), ""),   # table.column references
    (re.compile(r"\bsandbox\s+", re.I), ""),
]


def clean(s) -> str:
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return ""
    s = str(s)
    for rx, rep in _CLEAN:
        s = rx.sub(rep, s)
    return s


# ------------------------------------------------------------------ frames
@st.cache_data(show_spinner=False)
def merged() -> pd.DataFrame:
    """One row per account: churn scores + features + the offer engine's action, plus rule columns derived
    from the outreach card (block_reason / policy_selected) for the walk-through's 'rules' step."""
    c = pd.read_csv(D / "churn_scores.csv")
    for col in ("risk_reason_1", "risk_reason_2", "risk_reason_3"):
        if col in c:
            c[col] = c[col].map(clean)
    f = pd.read_csv(D / "features.csv")
    o = pd.read_csv(D / "offers.csv", usecols=["account_id", "action_code", "do_nothing_reason", "customer_monthly_delta"])
    m = c.merge(f, on="account_id", how="left").merge(o, on="account_id", how="left")
    oc = outreach()
    reason = m.account_id.map(oc.set_index("account_id").outreach_reason).fillna("").astype(str)
    msg = m.account_id.map(oc.set_index("account_id").message_en).fillna("").astype(str).str.strip()
    m["block_reason"] = ""
    m.loc[reason.str.contains("shown on the bill", case=False), "block_reason"] = "receipt_only_plan_move"
    m.loc[reason.str.contains("nothing that offsets it", case=False), "block_reason"] = "bill_change_no_fix"
    ps = pd.Series(pd.NA, index=m.index, dtype="object")
    ps[msg.ne("")] = True
    ps[reason.str.contains("pays off", case=False) & msg.eq("")] = False
    m["policy_selected"] = ps
    return m


@st.cache_data(show_spinner=False)
def outreach() -> pd.DataFrame:
    oc = pd.read_csv(OUTREACH)
    for c in ("outreach_reason", "message_en", "message_es"):
        oc[c] = oc[c].fillna("").astype(str)
    oc["outreach_reason"] = oc.outreach_reason.map(clean)
    return oc


@st.cache_data(show_spinner=False)
def receipts() -> pd.DataFrame:
    """Savings lines printed on the bill: accounts whose outreach card says the cheaper plan goes on the bill only."""
    oc = outreach()
    acc = oc[oc.outreach_reason.str.contains("shown on the bill", case=False) & oc.message_en.str.strip().eq("")].account_id
    o = pd.read_csv(D / "offers.csv", usecols=["account_id", "customer_monthly_delta"]).set_index("account_id")
    r = pd.DataFrame({"account_id": acc.values})
    r["receipt_saving_mo"] = (-r.account_id.map(o.customer_monthly_delta)).clip(lower=0)
    r["receipt_line_en"] = ["Same features, lower price: a cheaper version of your plan is available" for _ in range(len(r))]
    return r


def economics() -> dict:
    r = receipts()
    return {"receipt_lines": int(len(r)), "receipt_monthly": float(r.receipt_saving_mo.fillna(0).sum())}


def funnel(df: pd.DataFrame) -> dict:
    return dict(scored=len(df), flagged=int(df.flagged.sum()), messaged=int(df.messaged.sum()),
                texts=int((df.channel == "text").sum()), cut=float(df.attrs.get("flag_cut", float("nan"))))


# ------------------------------------------------------------------ per-customer
def policy_pick(row) -> str:
    """The action the shipped policy picked for this account, consistent with the outreach card."""
    if bool(row.get("messaged", False)) and isinstance(row.get("action_code"), str):
        return row["action_code"]
    if str(row.get("receipt_line_en", "") or "").strip():
        return "variant_switch|right_size"
    return "do_nothing"


@st.cache_data(show_spinner=False)
def _all_candidates() -> pd.DataFrame:
    c = pd.read_csv(D / "offer_candidates.csv.gz")
    c["action"] = c.action.map(clean)
    c["blocked_or_ineligible_reason"] = c.blocked_or_ineligible_reason.map(clean)
    return c


def candidates(acc: str, pick: str) -> pd.DataFrame:
    c = _all_candidates()
    c = c[c.account_id == acc].copy()
    c["is_chosen"] = c.action_code.isin(pick.split("|"))
    return c


@st.cache_resource(show_spinner=False)
def _model():
    for p in (REPO / "harness", REPO):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import churn_scorer as cs
    cs.OUT = _TMP  # model cache goes to a temp dir; nothing is written in the repo
    return cs, cs._load()


def contributions(acc: str, edits=None):
    cs, stt = _model()
    m, feats = stt["model"], stt["feats"]
    table = feats.set_index("account_id")
    if edits:
        table = table.copy()
        for k, v in edits.items():
            if k in table.columns:
                table.loc[acc, k] = v
    X = cs.prepare(table.reset_index())
    if "account_id" in X.columns:
        X = X.set_index("account_id")
    X.index = table.index
    Xa = X.loc[[acc]]
    Z = m._z(Xa).iloc[0] if hasattr(m, "_z") else None
    return float(m.intercept_), m.contributions(Xa).iloc[0].astype(float), float(m.predict_proba(Xa)[0]), Z


def typical_risk() -> float:
    _, stt = _model()
    return 100 / (1 + math.exp(-float(stt["model"].intercept_)))


def considerations() -> pd.DataFrame | None:
    if not CONSIDERATIONS.exists():
        return None
    d = pd.read_csv(CONSIDERATIONS)
    for c in ("item", "how_handled"):
        if c in d:
            d[c] = d[c].map(clean)
    return d
