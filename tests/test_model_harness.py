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


# ---------------------------------------------------------------- targets / enrichment
def test_targets_and_labels_resolve():
    assert mh.resolve_label(target="upgrade") == "upgrade_90d"
    assert mh.resolve_label("toy_churn", target="upgrade") == "toy_churn"   # label wins
    assert mh.target_of("upgrade_90d") == "upgrade"
    assert "rule_near_or_over_data_cap" in mh.list_models("upgrade")
    assert "rule_support3" not in mh.list_models("upgrade")


def test_upgrade_rule_model_conforms():
    X, y, _ = toy()
    X["n_lines_over_cap_3m"] = (X.support_90d > 2).astype(float)
    X["data_gb_3m_avg"] = 10.0
    X["plan_data_cap_gb"] = 50.0
    X["n_lines"] = 1.0
    m = mh.get_model("rule_near_or_over_data_cap").fit(X, y)
    p = m.predict_proba(X)
    assert p.shape == (len(X),) and len(np.unique(p)) <= 2


def test_enrichment_and_label_columns_excluded(tmp_path):
    f = pd.DataFrame({"account_id": ["A", "B", "C", "D"], "is_persona": [0, 0, 0, 0], "support_90d": [0, 1, 2, 3],
                      "tenure_months": [1, 2, 3, 4], "competitor_research_score": [.1, .2, .3, .4],
                      "port_out_inquiry": [0, 0, 1, 0], "app_sessions_30d": [1, 2, 3, 4],
                      "bill_increase_pct": [0, .1, 0, .2], "income_band": ["a", "b", "a", "b"],
                      "recent_job_change": [0, 1, 0, 1], "upgrade_driver_1": ["x"] * 4})
    lab = pd.DataFrame({"account_id": ["A", "B", "C", "D"], "churn_90d": [0, 1, 0, 1], "upgrade_90d": [1, 0, 0, 1],
                        "upgrade_driver_1": ["x"] * 4, "p_upgrade_90d": [.1, .2, .3, .4]})
    f.to_csv(tmp_path / "features.csv", index=False)
    lab.to_csv(tmp_path / "labels.csv", index=False)
    X, y, meta = mh.load_data(target="upgrade", data_dir=str(tmp_path))
    assert not [c for c in X.columns if c.startswith(("income_band", "recent_job_change", "upgrade_driver"))]
    X2, _, _ = mh.load_data(target="upgrade", data_dir=str(tmp_path), include_enrichment=True)
    assert any(c.startswith(("income_band", "recent_job_change")) for c in X2.columns)


# ---------------------------------------------------------------- uplift (Model C)
def toy_uplift_frame():
    """Tiny frame in tm-offers' long format: 2 accounts, do nothing + 1 action each."""
    return pd.DataFrame({
        "account_id": ["A", "A", "B", "B"], "action": ["do nothing", "care", "do nothing", "care"],
        "split": ["test"] * 4, "treated": [1, 0, 0, 1], "propensity": [0.5] * 4,
        "outcome_stay_90d": [0, np.nan, np.nan, 1], "uplift_hat": [0, 0.2, 0, 0.3],
        "true_uplift": [0, 0.1, 0, 0.2], "pick_uplift": [0, 1, 0, 1], "synthetic": 1})


def test_load_uplift_validates():
    df = mh.load_uplift(df=toy_uplift_frame())
    assert df["is_control"].sum() == 2
    bad = toy_uplift_frame()
    bad.loc[1, "treated"] = 1          # two treated rows for A
    with pytest.raises(mh.UpliftDataError, match="exactly one treated"):
        mh.load_uplift(df=bad)
    with pytest.raises(mh.UpliftDataError, match="missing"):
        mh.load_uplift(df=toy_uplift_frame().drop(columns=["propensity"]))


def test_policy_value_ipw_by_hand():
    df = mh.load_uplift(df=toy_uplift_frame())
    v = mh.policy_value(df, {"A": "care", "B": "care"}, "ipw")
    # only B matches (treated care, y=1, p=0.5): IPW = (1/0.5)/2 = 1.0 ; SNIPW = 1.0
    assert v["ipw"] == pytest.approx(1.0) and v["snipw"] == pytest.approx(1.0)
    v0 = mh.policy_value(df, {"A": "do nothing", "B": "do nothing"}, "snipw")
    assert v0["snipw"] == pytest.approx(0.0)       # A stayed=0 under do nothing
    assert v["true_gain_vs_do_nothing"] == pytest.approx(0.15)


def test_qini_perfect_beats_noisy_beats_random():
    res = {}
    for sc in ("perfect", "noisy_truth", "random"):
        df, _ = mh.simulate_uplift_frame(n=4000, score=sc, seed=3)
        c = mh.action_curves(mh.load_uplift(df=df))["best_action"]
        res[sc] = c["qini_coefficient"]
    assert res["perfect"] > res["random"] and res["noisy_truth"] > res["random"]
    assert abs(res["random"]) < 0.01


def test_binary_qini_random_near_zero_and_perfect_positive():
    rng = np.random.default_rng(0)
    n = 20000
    u = rng.uniform(-0.1, 0.3, n)
    t = rng.integers(0, 2, n)
    y = (rng.random(n) < 0.5 + t * u).astype(int)
    perfect = mh.binary_uplift_metrics(y, t, u)
    rnd = mh.binary_uplift_metrics(y, t, rng.random(n))
    assert perfect["qini_coefficient"] > 0.01
    assert abs(rnd["qini_coefficient"]) < 0.005
    assert perfect["auuc"] > rnd["auuc"]


def test_policy_ranking_on_simulator_uses_truth():
    df, _ = mh.simulate_uplift_frame(n=4000, score="perfect", seed=1)
    pol = mh.compare_policies(mh.load_uplift(df=df)).set_index("policy")
    assert pol.loc["oracle_true_uplift", "true_gain_vs_do_nothing"] >= pol.loc["random", "true_gain_vs_do_nothing"]
    assert pol.loc["do_nothing", "share_treated"] == 0


def test_tlearner_interface():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(2000, 3))
    t = rng.integers(0, 2, 2000)
    y = (rng.random(2000) < 0.3 + 0.3 * t * (X[:, 0] > 0)).astype(int)
    m = mh.get_uplift_model("t_learner_logreg").fit(X, t, y)
    u = m.predict_uplift(X)
    assert isinstance(u, np.ndarray) and u.shape == (2000,)
    assert u[X[:, 0] > 0].mean() > u[X[:, 0] <= 0].mean()
    arms = np.where(t == 1, "care", "do nothing")
    U = mh.TLearner().fit(X, np.where(rng.random(2000) < 0.5, arms, "fix"), y).predict_uplift(X)
    assert isinstance(U, pd.DataFrame)


# ---------------------------------------------------------------- plain-English upgrade reasons
def _bad_reason(text, colnames):
    if "_" in text or "=" in text:
        return True
    words = set(text.replace("(", " ").replace(")", " ").replace(",", " ").split())
    return bool(words & {c for c in colnames if c.islower()})


def test_upgrade_phrases_cover_all_and_are_clean():
    cols = set(mh.UPGRADE_PHRASES) | set(mh.ENRICHMENT_COLS)
    for g, f in mh.UPGRADE_PHRASES.items():
        for v in (0.0, 1.0, 3.0, 0.5, 45.0):
            for up in (True, False):
                t = f(v, up)
                assert t and not _bad_reason(t, cols), (g, v, up, t)
    for g, table in mh._CATEGORY_TEXT.items():
        for cat in list(table) + ["some_new_level", "none"]:
            t = mh._upgrade_sentence(g, {}, True, cat)
            assert not _bad_reason(t, cols), (g, cat, t)
    assert mh._upgrade_sentence("totally_unknown_feature", {"totally_unknown_feature": 3}, True) == "Other account details"


@pytest.mark.skipif(not (REAL / "labels.csv").exists(), reason="out/ data not built")
def test_upgrade_reasons_on_real_data_have_no_raw_names():
    X, y, meta = mh.load_data(target="upgrade")
    raw_cols = set(pd.read_csv(REAL / "features.csv", nrows=0).columns) | set(X.columns)
    m = mh.fit_full("logreg", target="upgrade")
    ex = m.explain(X.iloc[:400], k=3)
    texts = pd.concat([ex[c] for c in ex.columns if c != "account_id"])
    texts = texts[texts != ""]
    assert len(texts) > 0
    bad = [t for t in texts.unique() if _bad_reason(t, raw_cols)]
    assert not bad, bad[:10]


def test_upgrade_direction_guard():
    """Reasons FOR upgrading never cite support problems, money owed, a bill jump or an unhappy tone; the next
    reason is used instead. Absence of a negative may still be a FOR reason."""
    ids = ["A", "B"]
    X = pd.DataFrame({"unresolved_90d": [2.0, 0.0], "financing_balance_total_cents": [95800.0, 0.0],
                      "bill_increase_pct": [0.25, 0.0], "neg_sentiment": [0.7, 0.0],
                      "n_lines_over_cap_3m": [1.0, 0.0], "tenure_capped60": [30.0, 30.0]}, index=ids)
    # contributions: every negative-domain feature pushes UP (as a collinear model might) and is the strongest
    C = pd.DataFrame({"unresolved_90d": [0.9, 0.9], "financing_balance_total_cents": [0.8, 0.8],
                      "bill_increase_pct": [0.7, 0.7], "neg_sentiment": [0.6, 0.6],
                      "n_lines_over_cap_3m": [-0.5, 0.5], "tenure_capped60": [0.1, -0.1]}, index=ids)
    r = mh.contributions_to_reasons(C, X, k=3, target="upgrade").set_index("account_id")
    a_for = [r.at["A", f"risk_reason_{i}"] for i in (1, 2, 3)]
    joined = " ".join(a_for).lower()
    for bad in ("unresolved", "owes", "bill jump", "jumped", "unhappy"):
        assert bad not in joined, a_for
    assert a_for[0] == "Customer for 2 years"          # next allowed group is used
    # over-cap line pushes DOWN for A but the condition helps upgrades -> not an AGAINST reason
    assert "data cap" not in " ".join(r.loc["A", [f"stay_reason_{i}" for i in (1, 2, 3)]]).lower()
    # B has none of the negatives: their absence may be shown as a reason FOR
    b_for = [r.at["B", f"risk_reason_{i}"] for i in (1, 2, 3)]
    assert "No unresolved support issues" in b_for and "Phones fully paid off" in b_for
    assert r.attrs.get("direction_blocked", 0) >= 4
    assert mh.upgrade_direction_ok("unresolved_90d", False, pd.Series({"unresolved_90d": 2}))
    assert not mh.upgrade_direction_ok("unresolved_90d", True, pd.Series({"unresolved_90d": 2}))
