"""Tests for harness/budget_optimizer.py (synthetic data only)."""
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
import budget_optimizer as bo  # noqa: E402


def _toy():
    rows = [
        # acc A: do nothing, cheap good offer, expensive slightly better offer, an ineligible huge-EV offer
        ("A", "do nothing", True, 0.0, 0.0), ("A", "fix", True, 30.0, 10.0),
        ("A", "credit", True, 40.0, 50.0), ("A", "blocked upsell", False, 999.0, 0.0),
        # acc B: free positive action, plus paid one
        ("B", "do nothing", True, 0.0, 0.0), ("B", "family upgrade", True, 5.0, 0.0),
        ("B", "loyalty", True, 60.0, 20.0),
        # acc C: only negative-EV offer -> do nothing
        ("C", "do nothing", True, 0.0, 0.0), ("C", "care credit", True, -5.0, 25.0),
        # acc D: dominated option (costs more, earns less) and a non-convex middle point
        ("D", "do nothing", True, 0.0, 0.0), ("D", "mid", True, 2.0, 10.0),
        ("D", "dominated", True, 1.0, 30.0), ("D", "top", True, 30.0, 20.0),
    ]
    return pd.DataFrame(rows, columns=["account_id", "action", "eligible", "expected_value", "offer_cost"])


def _real():
    try:
        return bo.load_candidates()
    except FileNotFoundError:
        pytest.skip("no offer_candidates data")


@pytest.mark.parametrize("df_fn", [_toy, _real])
def test_budget_zero_only_zero_cost(df_fn):
    df = df_fn()
    p = bo.optimize(df, 0)
    assert p["offer_cost"].sum() == 0
    assert p["account_id"].is_unique and set(p["account_id"]) == set(df["account_id"])
    assert (p["expected_value"] >= 0).all()


@pytest.mark.parametrize("df_fn", [_toy, _real])
def test_unlimited_matches_per_account_max_ev(df_fn):
    df = df_fn()
    p = bo.optimize(df, math.inf).set_index("account_id")
    e = df[df["eligible"].astype(bool)]
    best = e.groupby("account_id")["expected_value"].max()
    assert (p.loc[best.index, "expected_value"] - best).abs().max() < 1e-6


@pytest.mark.parametrize("df_fn", [_toy, _real])
def test_never_exceeds_budget_and_only_eligible(df_fn):
    df = df_fn()
    prep = bo.prepare(df)
    elig = set(map(tuple, df[df["eligible"].astype(bool)][["account_id", "action"]].values))
    prev = -1.0
    for b in [0, 7, 15, 33, 100, 1_000, 5_000, 25_000]:
        p = bo.optimize(df, b, prep)
        assert p["offer_cost"].sum() <= b + 1e-6
        assert p["account_id"].is_unique
        assert set(map(tuple, p[["account_id", "action"]].values)) <= elig
        tot = p["expected_value"].sum()
        assert tot >= prev - 1e-6  # more budget never hurts in this greedy on these inputs
        prev = tot


def test_toy_greedy_order():
    df = _toy()
    p = bo.optimize(df, 0).set_index("account_id")["action"]
    assert p["B"] == "family upgrade" and p["C"] == "do nothing"
    p = bo.optimize(df, 30).set_index("account_id")["action"]
    # best ratios: B loyalty (55/20=2.75), A fix (3.0), D mid (0.2) -> A fix + B loyalty = $30
    assert p["A"] == "fix" and p["B"] == "loyalty" and p["D"] == "do nothing"
    p = bo.optimize(df, math.inf).set_index("account_id")["action"]
    assert p["D"] == "top" and p["A"] == "credit"
