"""Data loading for the tm-ui lane.

Search order per file: TM_OUT_DIR (if set) -> demo_data/ (tracked, tested copy of the real 5k sandbox run; the demo
default) -> harness/out/ (only if demo_data/ is missing; may hold a work-in-progress run) -> app/mock/*.csv
(48-account mock, flagged loudly).
A real file is only used if it has every contract column; .csv.gz is read too. Force mocks with TM_USE_MOCK=1.
ALL DATA IS SYNTHETIC.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parent
REPO = APP_DIR.parent
MOCK_DIR = APP_DIR / "mock"

# Contract columns from /workspace/tmobile/handoff/LANES.md
CONTRACTS: dict[str, list[str]] = {
    "churn_scores": ["account_id", "p_churn_90d", "risk_rank",
                     "risk_reason_1", "risk_reason_2", "risk_reason_3",
                     "stay_reason_1", "stay_reason_2", "stay_reason_3"],
    # "upgrade_moment flags" are unnamed in LANES.md; any column starting with upgrade_ is treated as one.
    "offers": ["account_id", "action", "expected_value", "reason"],  # tm-offers also adds action_code, runner_up_*, um_*
    # LANES.md names no columns for these two; only account_id is required.
    "features": ["account_id"],
    "labels": ["account_id"],
}
# Optional extras (no mock): tm-offers' full option table and Model A out-of-fold predictions.
OPTIONAL = {"offer_candidates": ["account_id", "action_code"], "churn_oof_pred": ["account_id", "p_churn_90d"]}


def out_dirs() -> list[Path]:
    if os.environ.get("TM_USE_MOCK") == "1":  # force mocks (demo fallback / testing)
        return []
    dirs = []
    if os.environ.get("TM_OUT_DIR"):
        dirs.append(Path(os.environ["TM_OUT_DIR"]))
    if (REPO / "demo_data").is_dir():
        dirs.append(REPO / "demo_data")
    else:
        dirs.append(REPO / "harness" / "out")
    return dirs


@dataclass
class Loaded:
    df: pd.DataFrame
    source: str  # "real" | "mock" | "missing"
    path: str
    note: str = ""


def load_one(name: str) -> Loaded:
    need = CONTRACTS.get(name) or OPTIONAL[name]
    notes = []
    for d in out_dirs():
        p = next((q for q in (d / f"{name}.csv", d / f"{name}.csv.gz") if q.exists()), None)
        if p is not None:
            try:
                df = pd.read_csv(p)
            except Exception as e:  # noqa: BLE001
                notes.append(f"{p}: unreadable ({e})")
                continue
            missing = [c for c in need if c not in df.columns]
            if missing:
                notes.append(f"{p}: missing contract columns {missing}; using mock")
                continue
            return Loaded(df, "real", str(p), "; ".join(notes))
    p = MOCK_DIR / f"{name}.csv"
    if p.exists():
        return Loaded(pd.read_csv(p), "mock", str(p), "; ".join(notes))
    return Loaded(pd.DataFrame(columns=need), "missing", "", "; ".join(notes))


def load_all() -> dict[str, Loaded]:
    # One churn number everywhere: churn_scores.csv p_churn_90d is the only churn probability the app shows.
    # (No fallback to tm-offers' mock_churn_scores.csv any more; a mock is flagged by the banner instead.)
    data = {n: load_one(n) for n in CONTRACTS}
    data.update({n: load_one(n) for n in OPTIONAL})
    return data


def is_mock(data: dict[str, Loaded]) -> bool:
    return any(data[k].source != "real" for k in CONTRACTS)


def upgrade_flag_cols(offers: pd.DataFrame) -> list[str]:
    """Per-moment flag columns: tm-offers uses um_* (+ an aggregate upgrade_moment bool, excluded)."""
    return [c for c in offers.columns if (c.startswith("um_") or c.startswith("upgrade_")) and c != "upgrade_moment"]


def truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "1.0")


def merged(data: dict[str, Loaded]) -> pd.DataFrame:
    """One row per scored account: churn_scores + offers + features (left joins)."""
    df = data["churn_scores"].df.copy()
    for n in ("offers", "features"):
        other = data[n].df
        if n == "offers" and "segment" in other:  # offers.segment is the OFFER segment; keep features' customer segment
            other = other.rename(columns={"segment": "offer_segment"})
        if len(other):
            # churn_scores wins on clashes (p_churn_90d, risk_rank): one churn number everywhere
            dup = [c for c in other.columns if c in df.columns and c != "account_id"]
            df = df.merge(other.drop(columns=dup), on="account_id", how="left")
    if "risk_rank" in df:
        df = df.sort_values("risk_rank")
    return df.reset_index(drop=True)


def persona_titles() -> dict[str, str]:
    """Persona titles from the judge sandbox (opened read-only). Empty if not on disk."""
    import sqlite3
    for p in (os.environ.get("DUBHACKS_DB", ""), os.environ.get("SANDBOX_DB", ""),
              str(REPO / "vendor" / "dubhacks" / "data" / "sandbox.db"),
              str(REPO / "dubhacks" / "data" / "sandbox.db"), str(REPO.parent / "dubhacks" / "data" / "sandbox.db")):
        if p and Path(p).exists():
            try:
                con = sqlite3.connect(Path(p).resolve().as_uri() + "?mode=ro", uri=True)
                rows = con.execute("select account_id, title from personas where account_id is not null").fetchall()
                con.close()
                return dict(rows)
            except sqlite3.Error:
                return {}
    return {}


# ---------------- stay-reason consistency filter ----------------
def _num(r, c, default=0.0) -> float:
    try:
        v = float(r.get(c, default))
        return default if pd.isna(v) else v
    except (TypeError, ValueError):
        return default


def stay_conflict(stay: str, r, risks: list[str]) -> str | None:
    """Why a stay reason contradicts the customer's facts or own risk reasons (None = consistent)."""
    s, rk = str(stay).lower(), " | ".join(str(x).lower() for x in risks)
    if s.startswith("no unresolved") and (_num(r, "unresolved_90d") > 0 or "unresolved" in rk):
        return "has unresolved support contacts"
    if s.startswith("steady bill") and (_num(r, "bill_change_3m_pct") > 0.05 or _num(r, "bill_increase_pct") > 0.05
                                        or _num(r, "promo_expired_recent") > 0 or "bill up" in rk or "promo" in rk):
        return "bill went up / promo ended"
    if s.startswith("not shopping") and (_num(r, "competitor_research_score") >= 0.5 or _num(r, "port_out_inquiry") > 0
                                         or "shopping" in rk or "porting" in rk):
        return "is researching competitors or asked about porting out"
    if s.startswith("positive experiences") and (_num(r, "negative_contacts_90d") > 0 or _num(r, "avg_sentiment_90d") < 0
                                                 or "unhappy" in rk):
        return "has unhappy support contacts"
    if s.startswith("no complaints") and (_num(r, "support_90d") > 0 or _num(r, "network_contacts_90d") > 0
                                          or "unhappy" in rk or "unresolved" in rk):
        return "has support or network contacts"
    if (s.startswith("low support") or s.startswith("few support")) and (_num(r, "support_90d") >= 3 or "support" in rk):
        return "has many support contacts"
    if s.startswith("long-time customer") and "new customer" in rk:
        return "risk says new customer"
    if "lines on account" in s and "single line" in rk:
        return "risk says single line"
    if s.startswith("newer phone") and "phone is" in rk:
        return "risk says old phone"
    if s.startswith("active app user") and "rarely uses the app" in rk:
        return "risk says rarely uses the app"
    return None


def clean_stays(r) -> tuple[list[str], list[tuple[str, str]]]:
    """(kept stay reasons, dropped [(reason, why)]) for one merged row."""
    risks = [r.get(f"risk_reason_{i}") for i in (1, 2, 3)]
    risks = [x for x in risks if isinstance(x, str) and x]
    kept, dropped = [], []
    for i in (1, 2, 3):
        t = r.get(f"stay_reason_{i}")
        if not (isinstance(t, str) and t):
            continue
        why = stay_conflict(t, r, risks)
        (dropped.append((t, why)) if why else kept.append(t))
    return kept, dropped
