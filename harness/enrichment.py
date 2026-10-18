"""Enrichment columns -> harness/out/enrichment.csv (account_id + new columns). Kept OUT of features.csv
so Model A's inputs don't change. ALL PER-ACCOUNT VALUES ARE SYNTHETIC; only the cited aggregates are real.

recent_job_change (0/1, SYNTHETIC): account holder started a new job in the last 90 days.
  Base rate: BLS JOLTS hires rate 3.3% per month (Aug 2026, seasonally adjusted, total nonfarm; released
  2026-09-29, https://www.bls.gov/news.release/jolts.nr0.htm) -> 90 days: 1 - (1 - 0.033)^3 = 9.57%.
  (Hires per employee is a proxy; it includes rehires and people with several hires. Judgement call.)
  Mild links: student +0.6, senior -1.2, tenure < 12 months +0.4, tenure >= 60 months -0.2 (logit),
  intercept solved so the mean over the 5,000 regular accounts = 9.57%.
household_income_usd / income_band (SYNTHETIC individual values): the sandbox has NO geography (no ZIP,
  city or state), so incomes come from the REAL national distribution, ACS 2020-2024 5-year table
  B19001 (household income, 16 bins), median B19013 = $80,734 (+/-166), fetched via the Census Reporter
  API (https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B19001,B19013&geo_ids=01000US;
  cached in <raw>/censusreporter_acs2024_5yr_B19001_B19013_us.json). (api.census.gov now requires a key
  from this host; we did not sign up.) The latent rank links mildly to credit tier, segment and bill size, then
  maps to the national inverse CDF, so the marginal matches ACS exactly. Uniform within bins; Pareto(2.5)
  above $200k, capped at $2M.
next_plan_sku / next_plan_price_cents / step_up_cost_cents / step_up_cost_pct_income: from the REAL sandbox
  plans table. Ladder: Essentials Saver -> Essentials -> Experience More -> Experience Beyond, keeping the
  variant (Community/Partner/55); Essentials 4-line -> More. Beyond is the top (blank next plan / cost).
  step_up_cost_pct_income = 12 x monthly step-up cost / household income x 100.
Run: python harness/enrichment.py   (after features.py)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from features import find_db  # noqa: E402
from labels import sigmoid, solve_b0, uniform  # noqa: E402

RAW = HERE.parent.parent / "raw"
ACS_FILE = RAW / "censusreporter_acs2024_5yr_B19001_B19013_us.json"
ACS_URL = "https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B19001,B19013&geo_ids=01000US"
OUT = HERE / "out" / "enrichment.csv"
JOB_RATE_MONTHLY = 0.033  # BLS JOLTS hires rate, Aug 2026
JOB_TARGET_90D = 1 - (1 - JOB_RATE_MONTHLY) ** 3
BIN_EDGES = [0, 10000, 15000, 20000, 25000, 30000, 35000, 40000, 45000, 50000, 60000, 75000, 100000, 125000,
             150000, 200000]  # last bin: 200000+
BANDS = [(0, 25000, "<$25k"), (25000, 50000, "$25-50k"), (50000, 75000, "$50-75k"), (75000, 100000, "$75-100k"),
         (100000, 150000, "$100-150k"), (150000, 200000, "$150-200k"), (200000, np.inf, "$200k+")]
P = "TMO-STUB-PLAN-"
NEXT_PLAN = {"ESSENTIALS-SAVER": "ESSENTIALS", "ESSENTIALS": "MORE", "ESSENTIALS-4LINE": "MORE",
             "MORE": "BEYOND", "MORE-COMMUNITY": "BEYOND-COMMUNITY", "MORE-PARTNER": "BEYOND-PARTNER",
             "MORE-55": "BEYOND-55"}
NEXT_PLAN = {P + k: P + v for k, v in NEXT_PLAN.items()}


def load_acs() -> tuple[np.ndarray, float]:
    if not ACS_FILE.exists():
        import urllib.request
        RAW.mkdir(parents=True, exist_ok=True)
        ACS_FILE.write_bytes(urllib.request.urlopen(ACS_URL, timeout=60).read())
    d = json.loads(ACS_FILE.read_text())["data"]["01000US"]
    est = d["B19001"]["estimate"]
    counts = np.array([est[f"B19001{k:03d}"] for k in range(2, 18)], dtype=float)
    return counts / counts.sum(), float(d["B19013"]["estimate"]["B19013001"])


def income_from_u(u: np.ndarray, u2: np.ndarray, probs: np.ndarray) -> np.ndarray:
    cdf = np.concatenate([[0], np.cumsum(probs)])
    b = np.clip(np.searchsorted(cdf, u, side="right") - 1, 0, len(probs) - 1)
    lo = np.array(BIN_EDGES)[b]
    hi = np.array(BIN_EDGES[1:] + [np.nan])[b]
    inc = lo + u2 * (np.nan_to_num(hi) - lo)
    top = b == len(probs) - 1
    inc[top] = np.minimum(200000 / (1 - u2[top]) ** (1 / 2.5), 2_000_000)
    inc[b == 0] = 2500 + u2[b == 0] * 7500
    return np.round(inc, -2)


def band(x: pd.Series) -> pd.Series:
    out = pd.Series("", index=x.index, dtype=object)
    for lo, hi, name in BANDS:
        out[(x >= lo) & (x < hi)] = name
    return out


def plan_price(plans: pd.DataFrame, sku: str, n: int) -> float:
    p = plans.loc[sku]
    pr = [int(v) for v in str(p["line_prices"]).split(",") if v]
    extra = p["extra_line_cents"] if pd.notna(p["extra_line_cents"]) else pr[-1]
    return float(sum(pr[:n]) + max(0, n - len(pr)) * extra)


def load_plans() -> pd.DataFrame:
    conn = sqlite3.connect(find_db().as_uri() + "?mode=ro", uri=True)
    try:
        return pd.read_sql("SELECT * FROM plans", conn).set_index("sku")
    finally:
        conn.close()


def step_up(df: pd.DataFrame, plans: pd.DataFrame) -> pd.DataFrame:
    """Next plan up + monthly step-up cost (sandbox plans table). Needs plan_sku, n_lines, plan_price_cents,
    household_income_usd."""
    nxt = df["plan_sku"].map(NEXT_PLAN)
    price = [plan_price(plans, s, min(int(n), int(plans.loc[s, "max_lines"]) if pd.notna(plans.loc[s, "max_lines"]) else int(n)))
             if isinstance(s, str) else np.nan for s, n in zip(nxt, df["n_lines"])]
    out = pd.DataFrame({"next_plan_sku": nxt, "next_plan_price_cents": price}, index=df.index)
    out["step_up_cost_cents"] = (out["next_plan_price_cents"] - df["plan_price_cents"]).clip(lower=0)
    out["step_up_cost_pct_income"] = (12 * out["step_up_cost_cents"] / 100 / df["household_income_usd"] * 100).round(4)
    return out


def build(f: pd.DataFrame) -> pd.DataFrame:
    probs, median = load_acs()
    regular = (f["is_persona"] == 0).values
    ids = f["account_id"]
    # job change
    s = (0.6 * (f["segment"] == "student") - 1.2 * (f["segment"] == "senior")
         + 0.4 * (f["tenure_months"] < 12) - 0.2 * (f["tenure_months"] >= 60)).astype(float).values
    b = solve_b0(s[regular], JOB_TARGET_90D)
    job = (uniform("tm-jobchange-2026", ids) < sigmoid(b + s)).astype(int)
    # income: latent = mild signal + noise -> rank among regular accounts -> national inverse CDF
    credit = f["credit_tier"].map({"prime": 0.35, "near_prime": 0.0, "subprime": -0.35}).fillna(0)
    seg = f["segment"].map({"student": -0.5, "senior": -0.2, "smb": 0.2, "family": 0.2}).fillna(0)
    bill = np.log(f["last_bill_cents"].clip(lower=1))
    lat = credit + seg + 0.2 * (bill - bill[regular].mean()) / bill[regular].std()
    lat = lat.values + stats.norm.ppf(np.clip(uniform("tm-income-noise-2026", ids), 1e-9, 1 - 1e-9))
    ref = np.sort(lat[regular])
    u = (np.searchsorted(ref, lat, side="left") + 0.5) / (len(ref) + 1)
    income = income_from_u(np.clip(u, 0, 1 - 1e-9), uniform("tm-income-within-2026", ids), probs)
    e = pd.DataFrame({"account_id": ids, "recent_job_change": job, "household_income_usd": income})
    e["income_band"] = band(e["household_income_usd"])
    e["area_median_income_usd"] = median
    e["income_geo_level"] = "national (sandbox has no geography)"
    e = pd.concat([e, step_up(f.assign(household_income_usd=income), load_plans())], axis=1)
    return e


def main():
    f = pd.read_csv(HERE / "out" / "features.csv")
    e = build(f)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    e.to_csv(OUT, index=False)
    r = e[f["is_persona"].values == 0]
    print(f"wrote {OUT} rows={len(e)} [SYNTHETIC per-account values]")
    print(f"recent_job_change rate={r.recent_job_change.mean():.4f} (target {JOB_TARGET_90D:.4f}); "
          f"income median={r.household_income_usd.median():,.0f} (ACS national {e.area_median_income_usd.iloc[0]:,.0f}); "
          f"top-tier (no step-up) share={r.next_plan_sku.isna().mean():.3f}; "
          f"median step-up ${r.step_up_cost_cents.median() / 100:.0f}/mo, {r.step_up_cost_pct_income.median():.2f}% of income")


if __name__ == "__main__":
    main()
