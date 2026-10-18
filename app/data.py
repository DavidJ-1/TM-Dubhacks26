"""Data loading for the tm-ui lane.

Prefers the real lane outputs (harness/out/*.csv per LANES.md) and falls back to
app/mock/*.csv per file. A real file is only used if it has every contract column.
Override the search with TM_OUT_DIR=/path/to/out; force mocks with TM_USE_MOCK=1.
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


def out_dirs() -> list[Path]:
    if os.environ.get("TM_USE_MOCK") == "1":  # force mocks (demo fallback / testing)
        return []
    dirs = []
    if os.environ.get("TM_OUT_DIR"):
        dirs.append(Path(os.environ["TM_OUT_DIR"]))
    dirs += [REPO / "harness" / "out", Path("/workspace/tmobile/harness/out")]
    return dirs


@dataclass
class Loaded:
    df: pd.DataFrame
    source: str  # "real" | "mock" | "missing"
    path: str
    note: str = ""


def load_one(name: str) -> Loaded:
    need = CONTRACTS[name]
    notes = []
    for d in out_dirs():
        p = d / f"{name}.csv"
        if p.exists():
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
    data = {n: load_one(n) for n in CONTRACTS}
    # Keep scores and offers consistent: if tm-offers' real offers.csv exists but tm-churn's
    # churn_scores.csv doesn't, use the mock_churn_scores.csv that tm-offers scored against.
    if data["churn_scores"].source != "real" and data["offers"].source == "real":
        for d in out_dirs():
            p = d / "mock_churn_scores.csv"
            if p.exists():
                df = pd.read_csv(p)
                if all(c in df.columns for c in CONTRACTS["churn_scores"]):
                    data["churn_scores"] = Loaded(df, "mock", str(p), "tm-offers' mock churn (paired with real offers.csv)")
                    break
    return data


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
        if len(other):
            dup = [c for c in other.columns if c in df.columns and c != "account_id"]
            df = df.merge(other.drop(columns=dup), on="account_id", how="left")
    if "risk_rank" in df:
        df = df.sort_values("risk_rank")
    return df.reset_index(drop=True)


def persona_titles() -> dict[str, str]:
    """Persona titles from the judge sandbox (opened read-only). Empty if not on disk."""
    import sqlite3
    for p in (os.environ.get("SANDBOX_DB", ""), str(REPO / "dubhacks" / "data" / "sandbox.db"),
              str(REPO.parent / "dubhacks" / "data" / "sandbox.db")):
        if p and Path(p).exists():
            try:
                con = sqlite3.connect(Path(p).resolve().as_uri() + "?mode=ro", uri=True)
                rows = con.execute("select account_id, title from personas where account_id is not null").fetchall()
                con.close()
                return dict(rows)
            except sqlite3.Error:
                return {}
    return {}
