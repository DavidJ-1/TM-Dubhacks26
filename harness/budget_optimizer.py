"""Credit-budget portfolio optimizer on top of the per-customer EV engine. ALL NUMBERS ARE SYNTHETIC / SIMULATED.

The tm-offers engine (harness/offers.py) scores every eligible action per account (including "do nothing")
by expected value and writes them to offer_candidates.csv. This module answers the portfolio question:
"with a total credit budget of $B, which customers get which action?"

Problem: multiple-choice knapsack. Each account gets exactly one action (do nothing = $0); maximise
sum(expected_value) subject to sum(offer_cost) <= B. Only rows with eligible == True are considered, so
anything the engine blocks (eligibility, upsell gates, guardrails) can never be picked here.

Method (greedy incremental efficiency, LP-relaxation greedy for MCKP):
  1. Per account, start at the best-EV action among the cheapest-cost options (usually do nothing, or a
     free action like a family upgrade with positive EV).
  2. Build the upper convex hull of (cost, EV) points above that start; each hull step is an "upgrade"
     with marginal EV / marginal $ ratio. Ratios decrease along the hull, so steps are taken in order.
  3. Globally sort every positive upgrade step by ratio and take them while they fit the budget. If a step
     does not fit, that account stops upgrading (later steps depend on it) but other accounts continue.
With unlimited budget this lands exactly on each account's max-EV eligible action. Simple, fast
(~5k accounts in well under a second), and every pick is explainable as "next best value per $1 of credit".

Usage:
  python3 harness/budget_optimizer.py                 # sweep default budgets, write curve CSV + chart
  python3 harness/budget_optimizer.py --budgets 0 5000 inf
Outputs: harness/out/budget_curve.csv, demo_data/budget_curve.csv, demo_data/budget_curve.png
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = Path(os.environ.get("TM_OUT_DIR", HERE / "out"))
DEMO = ROOT / "demo_data"

DO_NOTHING = "do nothing"
DEFAULT_BUDGETS = [0, 2_000, 5_000, 10_000, 20_000, 40_000, math.inf]
EPS = 1e-9


def load_candidates() -> pd.DataFrame:
    for p in (OUT / "offer_candidates.csv", DEMO / "offer_candidates.csv.gz"):
        if p.exists():
            df = pd.read_csv(p)
            df.attrs["source"] = str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p)
            return df
    raise FileNotFoundError("offer_candidates.csv not found in harness/out or demo_data")


def load_p_churn() -> pd.Series | None:
    for p in (OUT / "churn_scores.csv", DEMO / "churn_scores.csv"):
        if p.exists():
            s = pd.read_csv(p, usecols=["account_id", "p_churn_90d"])
            return s.set_index("account_id")["p_churn_90d"]
    return None


def _eligible(cands: pd.DataFrame) -> pd.DataFrame:
    e = cands[cands["eligible"].astype(bool)].copy()
    e = e[e["expected_value"].notna() & e["offer_cost"].notna()]
    e["offer_cost"] = e["offer_cost"].clip(lower=0.0)
    # every account always has a $0 do-nothing fallback, even if the file omitted it
    missing = set(cands["account_id"]) - set(e.loc[e["action"] == DO_NOTHING, "account_id"])
    if missing:
        e = pd.concat([e, pd.DataFrame({"account_id": sorted(missing), "action": DO_NOTHING,
                                        "expected_value": 0.0, "offer_cost": 0.0})], ignore_index=True)
    return e


def _hull_steps(costs: np.ndarray, evs: np.ndarray, idx: np.ndarray):
    """Return (start_idx, [(ratio, d_cost, d_ev, to_idx), ...]) along the upper convex hull."""
    order = np.lexsort((-evs, costs))            # cost asc, EV desc within same cost
    c, v, ix = costs[order], evs[order], idx[order]
    start = 0                                    # best EV at the minimum cost
    pts = [(c[0], v[0], ix[0])]
    for k in range(1, len(c)):
        if v[k] <= pts[-1][1] + EPS:             # dominated: costs more, earns no more
            continue
        if c[k] <= pts[-1][0] + EPS:             # same cost, (can't be higher EV given sort) skip
            continue
        # pop while last point lies on/below the segment from second-last to new point (keeps concavity)
        while len(pts) >= 2:
            (c1, v1, _), (c2, v2, _) = pts[-2], pts[-1]
            if (v2 - v1) * (c[k] - c1) <= (v[k] - v1) * (c2 - c1) + EPS:
                pts.pop()
            else:
                break
        pts.append((c[k], v[k], ix[k]))
    steps = []
    for (c1, v1, _), (c2, v2, i2) in zip(pts, pts[1:]):
        dc, dv = c2 - c1, v2 - v1
        steps.append((dv / dc if dc > EPS else math.inf, dc, dv, i2))
    return pts[0][2], steps


def prepare(candidates_df: pd.DataFrame):
    """Precompute eligible rows, per-account start points and sorted hull steps (reusable across budgets)."""
    e = _eligible(candidates_df).reset_index(drop=True)
    start_idx, steps = {}, []
    for acc, g in e.groupby("account_id", sort=False):
        s, st = _hull_steps(g["offer_cost"].to_numpy(float), g["expected_value"].to_numpy(float),
                            g.index.to_numpy())
        start_idx[acc] = s
        for k, (ratio, dc, dv, to_i) in enumerate(st):
            steps.append((ratio, acc, k, dc, dv, to_i))
    steps.sort(key=lambda t: (-t[0], t[1], t[2]))
    return e, start_idx, steps


def optimize(candidates_df: pd.DataFrame, budget: float, prepared=None) -> pd.DataFrame:
    """Pick at most one eligible action per account to maximise total EV with sum(offer_cost) <= budget.

    Returns one row per account (the chosen candidate row) plus columns:
      bo_step (hull steps taken, 0 = base), bo_marginal_ratio (EV per $ of the last step taken, NaN at base).
    Pass prepared=prepare(candidates_df) to reuse the hull across many budgets.
    """
    budget = float(budget)
    e, start_idx, steps = prepared if prepared is not None else prepare(candidates_df)
    current = dict(start_idx)
    taken = {acc: 0 for acc in start_idx}
    last_ratio: dict = {}
    blocked: set = set()
    spent = float(e.loc[list(start_idx.values()), "offer_cost"].sum())   # normally 0
    for ratio, acc, k, dc, dv, to_i in steps:
        if acc in blocked or k != taken[acc] or dv <= EPS:
            continue
        if spent + dc <= budget + EPS:
            spent += dc
            current[acc] = to_i
            taken[acc] = k + 1
            last_ratio[acc] = ratio
        else:
            blocked.add(acc)
    picks = e.loc[list(current.values())].copy()
    picks["bo_step"] = picks["account_id"].map(taken)
    picks["bo_marginal_ratio"] = picks["account_id"].map(last_ratio)
    picks["bo_budget"] = budget
    picks["data_note"] = "synthetic/simulated"
    return picks.reset_index(drop=True)


def summarize(picks: pd.DataFrame, budget: float, p_churn: pd.Series | None) -> dict:
    contacted = picks["action"] != DO_NOTHING
    row = {
        "budget": "unlimited" if math.isinf(budget) else int(budget),
        "total_ev": round(float(picks["expected_value"].sum()), 2),
        "expected_saves": np.nan,
        "customers_contacted": int(contacted.sum()),
        "credits_used": round(float(picks["offer_cost"].sum()), 2),
        "paid_actions": int((picks["offer_cost"] > 0).sum()),
    }
    if p_churn is not None and "save_rate" in picks:
        p = picks["account_id"].map(p_churn).fillna(0.0)
        row["expected_saves"] = round(float((p * picks["save_rate"].fillna(0.0)).sum()), 1)
    row["data_note"] = "SYNTHETIC / simulated"
    return row


def engine_point(cands: pd.DataFrame, p_churn) -> dict | None:
    if "is_chosen" not in cands:
        return None
    ch = cands[cands["is_chosen"].astype(bool)].copy()
    ch["offer_cost"] = ch["offer_cost"].fillna(0.0)
    ch["expected_value"] = ch["expected_value"].fillna(0.0)
    r = summarize(ch, math.inf, p_churn)
    r["budget"] = "engine picks (is_chosen)"
    return r


def make_chart(cands, curve: pd.DataFrame, eng: dict | None, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # dense frontier for the line
    prep = prepare(cands)
    unl = optimize(cands, math.inf, prep)
    max_b = float(unl["offer_cost"].sum())
    grid = sorted(set(np.linspace(0, max_b, 60).tolist() + [b for b in DEFAULT_BUDGETS if b <= max_b]))
    ys = [optimize(cands, b, prep)["expected_value"].sum() for b in grid]
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=130)
    ax.plot(np.array(grid) / 1000, np.array(ys) / 1000, color="#E20074", lw=2.5,
            label="Budget optimizer (efficient frontier)")
    fin = curve[(curve["budget"] != "unlimited")]
    fin = fin[fin["budget"].astype(float) < max_b - 1]   # budgets above the unconstrained spend sit on the star
    ax.scatter(fin["credits_used"].astype(float) / 1000, fin["total_ev"] / 1000, color="#E20074", zorder=3)
    for _, r in fin.iterrows():
        ax.annotate(f"${int(r['budget'])/1000:g}k budget", (r["credits_used"] / 1000, r["total_ev"] / 1000),
                    textcoords="offset points", xytext=(6, -14), fontsize=8, color="#555")
    top = curve[curve["budget"] == "unlimited"].iloc[0]
    ax.scatter([top["credits_used"] / 1000], [top["total_ev"] / 1000], marker="*", s=260, color="#7a0047",
               zorder=4, label=f"Unconstrained per-customer max-EV picks (${top['credits_used']/1000:.1f}k)")
    if eng is not None:
        ax.scatter([eng["credits_used"] / 1000], [eng["total_ev"] / 1000], marker="D", s=70, color="#333",
                   zorder=4, label=f"Current engine picks incl. policy overrides (${eng['credits_used']/1000:.1f}k)")
    ax.axhline(top["total_ev"] / 1000, color="#999", ls=":", lw=1)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Credits / offer cost spent ($k, synthetic)")
    ax.set_ylabel("Total simulated expected value ($k, net of offer cost)")
    ax.set_title("More value per credit dollar: retention budget efficient frontier (simulated)")
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right", fontsize=8.5)
    fig.text(0.01, 0.005, "SYNTHETIC: 5,042 synthetic sandbox accounts; EV terms from the tm-offers engine. "
             "Not real T-Mobile customer data.", fontsize=7.5, color="#777")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--budgets", nargs="*", type=float, default=DEFAULT_BUDGETS)
    ap.add_argument("--no-chart", action="store_true")
    a = ap.parse_args(argv)
    cands = load_candidates()
    pc = load_p_churn()
    prep = prepare(cands)
    rows = [summarize(optimize(cands, b, prep), b, pc) for b in a.budgets]
    curve = pd.DataFrame(rows)
    unl_ev = optimize(cands, math.inf, prep)["expected_value"].sum()
    curve["pct_of_unlimited_ev"] = (100 * curve["total_ev"] / unl_ev).round(1)
    eng = engine_point(cands, pc)
    OUT.mkdir(parents=True, exist_ok=True)
    curve.to_csv(OUT / "budget_curve.csv", index=False)
    curve.to_csv(DEMO / "budget_curve.csv", index=False)
    if not a.no_chart:
        make_chart(cands, curve, eng, DEMO / "budget_curve.png")
    print(f"source: {cands.attrs.get('source')}  (SYNTHETIC / simulated)")
    print(curve.to_string(index=False))
    if eng:
        print("engine picks:", {k: eng[k] for k in ("total_ev", "customers_contacted", "credits_used", "expected_saves")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
