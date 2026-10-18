"""Model A: logistic regression on a seeded draw from the public sandbox score.

The sandbox has no observed churn. The public reference model in the judge repo is a
logistic score. We draw one label per non-persona account from that probability and fit
an explainable logistic regression on the same real fields, so each coefficient is a reason.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from harness.config import FEATURE_COLUMNS, FEATURE_LABELS, LABEL_SEED, MODEL_SEED


def sandbox_probability(row: pd.Series) -> float:
    """Public reference model (datagen/reference_model.py). Same weights, same fields."""
    logit = (
        -3.9
        + 0.45 * float(row["support_90d"])
        + 0.8 * max(0.0, -float(row["avg_sentiment"]))
        + 4.0 * float(row["bill_increase_pct"])
        + 2.2 * float(row["competitor_research"])
        + 1.2 * float(row["port_out_inquiry"])
        - 0.01 * min(float(row["tenure_months"]), 60)
        + 0.7 * float(row["plan_misfit_share"])
    )
    return 1.0 / (1.0 + math.exp(-logit))


class ChurnModel:
    def __init__(self, frame: pd.DataFrame):
        self.feature_columns = FEATURE_COLUMNS
        scored = frame.copy()
        scored["sandbox_p"] = scored.apply(sandbox_probability, axis=1)
        population = scored.loc[scored["is_persona"] == 0].sort_values("account_id")
        rng = np.random.default_rng(LABEL_SEED)
        labels = (rng.random(len(population)) < population["sandbox_p"].to_numpy()).astype(int)
        matrix = population.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)

        x_train, x_test, y_train, y_test = train_test_split(
            matrix, labels, test_size=0.25, random_state=MODEL_SEED, stratify=labels
        )
        holdout_scaler = StandardScaler().fit(x_train)
        holdout = LogisticRegression(max_iter=500, random_state=MODEL_SEED)
        holdout.fit(holdout_scaler.transform(x_train), y_train)
        holdout_p = holdout.predict_proba(holdout_scaler.transform(x_test))[:, 1]

        self.scaler = StandardScaler().fit(matrix)
        self.classifier = LogisticRegression(max_iter=500, random_state=MODEL_SEED)
        self.classifier.fit(self.scaler.transform(matrix), labels)

        everyone = self.scaler.transform(scored.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float))
        scored["model_p"] = self.classifier.predict_proba(everyone)[:, 1]
        self.frame = scored
        self.coefficients = {
            name: float(coef)
            for name, coef in zip(FEATURE_COLUMNS, self.classifier.coef_[0], strict=True)
        }
        self.metrics = {
            "holdout_auc": float(roc_auc_score(y_test, holdout_p)),
            "holdout_brier": float(brier_score_loss(y_test, holdout_p)),
            "holdout_n": int(len(y_test)),
            "draw_rate": float(labels.mean()),
            "train_n": int(len(population)),
            "label_note": (
                "Labels are one seeded draw from the public sandbox reference probability. "
                "The dataset has no observed churn, and the judges' private model is not used here."
            ),
        }

    def contributions(self, row: pd.Series) -> list[dict]:
        raw = row.loc[list(FEATURE_COLUMNS)].to_numpy(dtype=float).reshape(1, -1)
        centered = self.scaler.transform(raw)[0]
        weights = self.classifier.coef_[0]
        items = []
        for name, z, coef in zip(FEATURE_COLUMNS, centered, weights, strict=True):
            items.append(
                {
                    "feature": name,
                    "label": FEATURE_LABELS[name],
                    "contribution": float(z * coef),
                    "coefficient": float(coef),
                }
            )
        return items


def leave_reason(feature: str, row: pd.Series) -> str:
    support = int(row["support_90d"])
    if feature == "support_90d":
        return (
            f"{support} support contacts in the last 90 days. "
            "That count comes from support_interactions, not from an invented score."
        )
    if feature == "negative_sentiment":
        return (
            f"Average support sentiment is {float(row['avg_sentiment']):.2f}. "
            "The model only treats the negative part as a push to leave."
        )
    if feature == "bill_increase_pct":
        return (
            f"The latest bill is {float(row['bill_increase_pct']) * 100:.0f}% above "
            "the average of the earlier months."
        )
    if feature == "competitor_research":
        return f"Competitor research score is {float(row['competitor_research']):.2f} (0 to 1, from account_signals)."
    if feature == "port_out_inquiry":
        return "There is a port-out inquiry on the account."
    if feature == "plan_misfit_share":
        return (
            f"{float(row['plan_misfit_share']) * 100:.0f}% of lines look misfit: "
            "over a capped plan, or a premium plan averaging under 5 GB."
        )
    if feature == "tenure_capped":
        return f"Tenure is only {int(row['tenure_months'])} months, so the protective tenure term is small."
    return feature


def stay_reason(feature: str, row: pd.Series) -> str:
    if feature == "tenure_capped":
        return (
            f"{int(row['tenure_months'])} months on the account. "
            "Tenure pulls risk down, and the model caps that effect at 60 months."
        )
    if feature == "support_90d":
        return f"Only {int(row['support_90d'])} support contacts in the last 90 days."
    if feature == "negative_sentiment":
        sentiment = float(row["avg_sentiment"])
        if sentiment >= 0:
            return f"Average support sentiment is {sentiment:.2f}, so negativity is not adding risk."
        return "Support sentiment is only mildly negative compared with the customers the model was fit on."
    if feature == "bill_increase_pct":
        return (
            f"The latest bill is {float(row['bill_increase_pct']) * 100:.0f}% above the prior-month average, "
            "which is low relative to other accounts."
        )
    if feature == "competitor_research":
        return f"Competitor research is {float(row['competitor_research']):.2f}, on the low side of this book."
    if feature == "port_out_inquiry":
        return "No port-out inquiry."
    if feature == "plan_misfit_share":
        return "Usage fits the current plan on the misfit rule (cap and premium-under-5-GB)."
    return feature


def explain(model: ChurnModel, row: pd.Series) -> tuple[list[str], list[str], list[dict]]:
    parts = model.contributions(row)
    ranked = sorted(parts, key=lambda item: item["contribution"], reverse=True)
    leave_items = [item for item in ranked if item["contribution"] > 0][:3]
    stay_items = [item for item in ranked if item["contribution"] < 0][-3:]
    stay_items.reverse()
    leave = [leave_reason(item["feature"], row) for item in leave_items]
    stay = [stay_reason(item["feature"], row) for item in stay_items]
    used = {item["feature"] for item in leave_items}
    used.update(item["feature"] for item in stay_items)
    if len(stay) < 3:
        stay.extend(_stay_fillers(row, used, 3 - len(stay)))
    return leave, stay, ranked


def _stay_fillers(row: pd.Series, used: set[str], needed: int) -> list[str]:
    extras: list[str] = []
    if "tenure_capped" not in used:
        extras.append(stay_reason("tenure_capped", row))
    if "port_out_inquiry" not in used and int(row["port_out_inquiry"]) == 0:
        extras.append(stay_reason("port_out_inquiry", row))
    if "bill_increase_pct" not in used and float(row["bill_increase_pct"]) < 0.02:
        extras.append(
            "The latest bill is within 2% of the prior-month average."
        )
    if "negative_sentiment" not in used and float(row["avg_sentiment"]) >= 0:
        extras.append(stay_reason("negative_sentiment", row))
    if "competitor_research" not in used and float(row["competitor_research"]) < 0.25:
        extras.append(stay_reason("competitor_research", row))
    return extras[:needed]
