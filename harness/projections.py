"""Illustrative projections. The offer list stays fixed. Sliders only change the arithmetic.

Nothing here is a measured before/after, a simulated customer response, or a retrained model.
"""

from __future__ import annotations

import pandas as pd


def project(frame: pd.DataFrame, acceptance: float, save_given_accept: float, upgrade_acceptance: float) -> dict:
    """Population is the 5,000 non-persona accounts. `frame` must already be filtered."""
    n = int(len(frame))
    expected = float(frame["sandbox_p"].sum())
    targeted = frame.loc[frame["action_choice"] == "offer"]
    saves = float((targeted["sandbox_p"] * acceptance * save_given_accept).sum())
    saves = min(saves, expected)
    upgrade_now = int((frame["upgrade_when"] == "now").sum())
    return {
        "label": "Projected, illustrative assumptions",
        "accounts": n,
        "baseline_expected_churners": expected,
        "baseline_rate": expected / n if n else 0.0,
        "targeted_offers": int(len(targeted)),
        "expected_saves": saves,
        "projected_expected_churners": expected - saves,
        "projected_rate": (expected - saves) / n if n else 0.0,
        "upgrade_now_accounts": upgrade_now,
        "projected_upgrades": upgrade_now * upgrade_acceptance,
        "acceptance": acceptance,
        "save_given_accept": save_given_accept,
        "upgrade_acceptance": upgrade_acceptance,
    }


def acceptance_curve(frame: pd.DataFrame, save_given_accept: float, points: int = 17) -> pd.DataFrame:
    rows = []
    for step in range(points):
        acceptance = step / (points - 1) * 0.8
        outcome = project(frame, acceptance, save_given_accept, upgrade_acceptance=0.0)
        rows.append(
            {
                "acceptance": acceptance,
                "projected_churn_rate": outcome["projected_rate"],
                "expected_saves": outcome["expected_saves"],
            }
        )
    return pd.DataFrame(rows)


def upgrade_curve(frame: pd.DataFrame, points: int = 17) -> pd.DataFrame:
    now = int((frame["upgrade_when"] == "now").sum())
    rows = []
    for step in range(points):
        rate = step / (points - 1)
        rows.append({"upgrade_acceptance": rate, "projected_upgrades": now * rate})
    return pd.DataFrame(rows)
