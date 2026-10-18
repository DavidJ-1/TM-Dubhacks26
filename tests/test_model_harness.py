"""Tests for harness/model_harness.py (SYNTHETIC toy data; real out/ data only where noted)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
import model_harness as mh  # noqa: E402


def toy(n=600, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({
        "support_90d": rng.poisson(1.2, n).astype(float),
        "competitor_research_score": rng.random(n),
        "tenure_months": rng.integers(1, 120, n).astype(float),
        "segment=family": rng.integers(0, 2, n).astype(float),
    }, index=pd.Index([f"ACC-{i:05d}" for i in range(n)], name="account_id"))
    X["segment=single"] = 1 - X["segment=family"]
    logit = -3 + 0.6 * X.support_90d + 2.5 * X.competitor_research_score - 0.01 * X.tenure_months
    y = pd.Series((rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int), index=X.index, name="churn_90d")
    meta = pd.DataFrame({"is_persona": 0, "oracle_p": 1 / (1 + np.exp(-logit)), "label": "churn_90d",
                         "prep_source": "toy"}, index=X.index)
    return X, y, meta


# ---------------------------------------------------------------- split
def test_holdout_split_disjoint_stratified_and_complete():
    X, y, meta = toy()
    Xtr, Xte, ytr, yte, mtr, mte = mh.holdout_split(X, y, meta, test_size=0.25, seed=42)
    assert set(Xtr.index).isdisjoint(Xte.index)
    assert len(Xtr) + len(Xte) == len(X)
    assert abs(ytr.mean() - yte.mean()) < 0.03          # stratified
    assert list(Xte.index) == list(yte.index) == list(mte.index)


def test_holdout_split_rejects_personas():
    X, y, meta = toy()
    meta.iloc[0, meta.columns.get_loc("is_persona")] = 1
    with pytest.raises(mh.HarnessDataError):
        mh.holdout_split(X, y, meta)


def test_cv_folds_partition():
    X, y, _ = toy()
    folds = mh.cv_folds(X, y, k=5)
    seen = np.concatenate([te for _, te in folds])
    assert len(folds) == 5 and sorted(seen) == list(range(len(X)))
    for tr, te in folds:
        assert set(tr).isdisjoint(te)


def test_no_label_columns_leak_into_features():
    f = pd.DataFrame({"account_id": ["A", "B"], "is_persona": [0, 0], "support_90d": [1, 2],
                      "churn_90d": [0, 1], "toy_p": [0.1, 0.2]})
    with pytest.raises(mh.HarnessDataError):
        # fallback prep keeps churn_90d -> must be caught
        X = mh._fallback_prepare(f)
        if mh.LEAKY_COLS.intersection(X.columns):
            raise mh.HarnessDataError("leak")


# ---------------------------------------------------------------- metrics
def test_metrics_perfect_and_random():
    y = np.array([0] * 90 + [1] * 10)
    m = mh.compute_metrics(y, y.astype(float) * 0.9 + 0.05)
    assert m["auc"] == 1.0 and m["pr_auc"] == 1.0
    assert m["top10_recall"] == 1.0 and m["top10_lift"] == pytest.approx(10.0)
    flat = mh.compute_metrics(y, np.full(100, 0.1))
    assert flat["auc"] == 0.5
    assert flat["top10_recall"] == pytest.approx(0.10)   # ties shared proportionally
    assert flat["brier"] == pytest.approx(np.mean((y - 0.1) ** 2))


def test_top_frac_recall_ties():
    y = np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
    s = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], float)   # 4 tied at top, k=2 -> expect 2 * (2/4) / 2 = 0.5
    assert mh.top_frac_recall(y, s, 0.2) == pytest.approx(0.5)


def test_calibration_bins_cover_all_rows():
    rng = np.random.default_rng(1)
    p = rng.random(1000)
    y = (rng.random(1000) < p).astype(int)
    bins = mh.calibration_bins(y, p, 10)
    assert sum(b["n"] for b in bins) == 1000
    assert all(abs(b["mean_pred"] - b["observed_rate"]) < 0.15 for b in bins)


# ---------------------------------------------------------------- interface conformance
@pytest.mark.parametrize("name", mh.list_models())
def test_registered_models_conform(name):
    X, y, _ = toy()
    m = mh.get_model(name)
    assert isinstance(m, mh.ChurnModel) and m.name == name
    assert m.fit(X, y) is m
    p = m.predict_proba(X)
    assert isinstance(p, np.ndarray) and p.shape == (len(X),)
    assert np.all((p >= 0) & (p <= 1))
    ex = m.explain(X.iloc[:20], k=3)
    assert list(ex.columns) == ["account_id"] + [f"risk_reason_{i}" for i in (1, 2, 3)] + \
        [f"stay_reason_{i}" for i in (1, 2, 3)]
    assert len(ex) == 20 and (ex["account_id"].values == X.index[:20]).all()


def test_register_custom_model_and_default_explain():
    class Const(mh.ChurnModel):
        def fit(self, X, y):
            self.w = 1.0
            return self

        def predict_proba(self, X):
            return 1 / (1 + np.exp(-(X["competitor_research_score"].values * 3 - 2)))

    mh.register_model("const_test", Const)
    try:
        X, y, meta = toy()
        r = mh.evaluate("const_test", data=(X, y, meta), cv=False)
        for k in ("auc", "pr_auc", "brier", "calibration_bins", "top10_recall", "top10_lift"):
            assert k in r
        assert "pipeline" in r["caveat"] and "SYNTHETIC" in r["caveat"]
        ex = mh.get_model("const_test").fit(X, y).explain(X.iloc[:5])
        hi = X["competitor_research_score"].iloc[:5] > X["competitor_research_score"].median()
        # default perturbation explain: competitor score drives risk for high scorers
        assert all(("ompetitor" in t or "carrier" in t) for t in ex.loc[hi.values, "risk_reason_1"])
    finally:
        mh._REGISTRY.pop("const_test", None)


def test_rule_is_support_threshold():
    X, y, _ = toy()
    m = mh.get_model("rule_support3").fit(X, y)
    p = m.predict_proba(X)
    assert len(np.unique(p)) <= 2
    assert (p[X.support_90d.values >= 3] >= p[X.support_90d.values < 3].max()).all()


def test_near_or_over_data_cap():
    f = pd.DataFrame({"account_id": ["A", "B", "C", "D"], "n_lines_over_cap_3m": [1, 0, 0, 0],
                      "data_gb_3m_avg": [60, 46, 46, 500], "plan_data_cap_gb": [50, 50, np.nan, np.nan],
                      "n_lines": [1, 1, 1, 1]})
    r = mh.near_or_over_data_cap(f)
    assert r.near_or_over_data_cap.tolist() == [1, 1, 0, 0]       # unlimited (blank cap) never flagged


# ---------------------------------------------------------------- data loading (real files if present)
def test_load_data_errors_clearly(tmp_path):
    pd.DataFrame({"account_id": ["A"], "is_persona": [0]}).to_csv(tmp_path / "features.csv", index=False)
    pd.DataFrame({"account_id": ["A"], "churn_90d": [0]}).to_csv(tmp_path / "labels.csv", index=False)
    with pytest.raises(mh.HarnessDataError, match="missing required columns"):
        mh.load_data(data_dir=str(tmp_path))
    with pytest.raises(mh.HarnessDataError, match="not found"):
        mh.load_data(data_dir=str(tmp_path / "nope"))


REAL = Path(mh.CONFIG["data_dir"])


@pytest.mark.skipif(not (REAL / "labels.csv").exists(), reason="out/ data not built")
def test_real_data_excludes_personas_and_labels():
    for label in ("churn_90d", "toy_churn"):
        X, y, meta = mh.load_data(label)
        assert not X.index.str.startswith("ACC-PERSONA-").any()
        assert (meta.is_persona == 0).all() and set(y.unique()) <= {0, 1}
        assert not mh.LEAKY_COLS.intersection(X.columns)
    Xp, mp = mh.load_personas()
    assert len(Xp) == 42 and Xp.index.str.startswith("ACC-PERSONA-").all()
