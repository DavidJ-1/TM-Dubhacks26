"""Risk-by-value grid. Risk is the Model A score. Value is the formula in rules.py."""

from __future__ import annotations

import pandas as pd

from harness.playbook.rules import RISK_MID, RISK_TOP, VALUE_FORMULA, VALUE_HIGH_SHARE, VALUE_LINE_STEP, VALUE_TENURE_CAP_MONTHS

RISK_LABELS = {
    "top_10": "Top 10% risk",
    "mid_10_30": "10–30% risk",
    "rest": "Rest",
}
VALUE_LABELS = {"high": "High value", "low": "Lower value"}
PRIORITY_RISK = "top_10"
PRIORITY_VALUE = "high"


def value_score(last_bill_cents: float, n_lines: int, tenure_months: int) -> float:
    """Sandbox cents, line count, and tenure. See VALUE_FORMULA."""
    bill = max(float(last_bill_cents or 0), 0.0)
    extra = max(int(n_lines) - 1, 0)
    tenure = min(max(int(tenure_months), 0), VALUE_TENURE_CAP_MONTHS) / VALUE_TENURE_CAP_MONTHS
    return bill * (1 + VALUE_LINE_STEP * extra) * tenure


def assign_bands(frame: pd.DataFrame) -> pd.DataFrame:
    """Add value_score, risk_band, and value_band. Every account is placed."""
    out = frame.copy()
    out["n_lines"] = out["n_lines"].fillna(1).astype(int)
    out["value_score"] = [
        value_score(bill, lines, tenure)
        for bill, lines, tenure in zip(out["last_bill_cents"], out["n_lines"], out["tenure_months"], strict=True)
    ]
    count = max(len(out), 1)
    risk_pct = out["model_p"].rank(ascending=False, method="first") / count
    out["risk_band"] = "rest"
    out.loc[risk_pct <= RISK_MID, "risk_band"] = "mid_10_30"
    out.loc[risk_pct <= RISK_TOP, "risk_band"] = "top_10"
    value_pct = out["value_score"].rank(ascending=False, method="first") / count
    out["value_band"] = "low"
    out.loc[value_pct <= VALUE_HIGH_SHARE, "value_band"] = "high"
    out["priority_cell"] = (out["risk_band"] == PRIORITY_RISK) & (out["value_band"] == PRIORITY_VALUE)
    return out


def grid(frame: pd.DataFrame) -> pd.DataFrame:
    """Counts and expected churners (sum of the sandbox score) in each cell."""
    labeled = frame if "risk_band" in frame.columns else assign_bands(frame)
    rows = []
    for risk in ("top_10", "mid_10_30", "rest"):
        for value in ("high", "low"):
            cell = labeled.loc[(labeled["risk_band"] == risk) & (labeled["value_band"] == value)]
            rows.append(
                {
                    "risk_band": risk,
                    "risk_label": RISK_LABELS[risk],
                    "value_band": value,
                    "value_label": VALUE_LABELS[value],
                    "accounts": int(len(cell)),
                    "expected_churners": float(cell["sandbox_p"].sum()) if len(cell) else 0.0,
                    "priority": risk == PRIORITY_RISK and value == PRIORITY_VALUE,
                }
            )
    table = pd.DataFrame(rows)
    table["formula"] = VALUE_FORMULA
    return table
