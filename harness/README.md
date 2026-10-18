# harness/: model harness (churn + upgrade + Model C hooks)

> **All data, labels and numbers here are SYNTHETIC / SIMULATED** (T-Mobile judge sandbox stub data plus
> simulated labels). They test the pipeline, not real-world accuracy.

`model_harness.py` is a model-agnostic test bench. It loads `out/features.csv` + `out/labels.csv`, trains any
registered model, and backtests it against a simple business rule and an oracle ceiling. It also checks the demo
personas and writes plain-English reason codes. `uplift_eval.py` evaluates uplift / offer policies (Model C).

Other lanes' docs: [DATA_README.md](DATA_README.md) (features + labels), [UPLIFT_README.md](UPLIFT_README.md)
(tm-offers' uplift model), [OFFERS_README.md](OFFERS_README.md) (EV offer engine).

## Rerun everything (one command, from the repo root)

```bash
/workspace/tmobile/harness/.venv/bin/python harness/model_harness.py --all
```

This covers churn (`churn_90d` and `toy_churn`), then upgrade (`upgrade_90d`), then the uplift evaluation. It
re-reads `labels.csv` every time; nothing is cached. Other options: `--target churn|upgrade`, `--model NAME`,
`--uplift`, `--no-cv` (faster), `--data scaled` (50k synthetic accounts), `--scaled-to-real` (train on 50k,
test on the real 5k), `--include-enrichment` (enrichment columns are excluded from X by default).
Tests: `/workspace/tmobile/harness/.venv/bin/python -m pytest tests/test_model_harness.py -q`

## Targets and models

| target | label (oracle) | baseline rule | personas (high / low) |
|---|---|---|---|
| churn | `churn_90d` (`p_true_90d`); `toy_churn` (`toy_p`) for ranking checks only | `rule_support3`: 3+ support contacts in 90 days | 04, 21, 22, 27 / 10, 24 |
| upgrade | `upgrade_90d` (`p_upgrade_90d`) | `rule_near_or_over_data_cap`: a line over its cap, or 3-month use >= 90% of the per-line cap; unlimited plans never flagged | 25, 28 / 22, 24, 27 |

Built-in models: `logreg`, `hgb` (HistGradientBoosting), `rf` (random forest), plus the rules. tm-churn's
`model_a` self-registers from `churn_model.py` for churn. Features come from tm-churn's
`churn_features.prepare()`, with a fallback if it's missing. Every `labels.csv` column is barred from X.

## Outputs (`harness/out/`, gitignored)

- `backtest_<target>_<label>.csv/.md`: every model vs the rule and the oracle. It shows 5-fold CV mean ± std
  next to the oracle AUC on the same folds, plus a seed-42 25% holdout with the oracle on the same rows.
- `eval_<target>_<model>[_<label>].json`, `summary_<target>_<model>[...].txt`: metrics (AUC, PR-AUC, Brier, ECE,
  reliability bins, top-10% recall and lift) and the persona check.
- `harness_scores_churn_<model>.csv`: tm-churn contract columns (`account_id, p_churn_90d, risk_rank,
  risk_reason_1..3, stay_reason_1..3`). `harness_scores_upgrade_<model>.csv`: `p_upgrade_90d, upgrade_rank,
  upgrade_reason_1..3, against_upgrade_reason_1..3`. These never overwrite tm-churn's `churn_scores.csv`.
- `persona_check_<target>_<label>.csv` (provisional), `harness_near_or_over_data_cap.csv`,
  `eval_scaled_to_real*.{csv,json}`, `uplift_eval_summary.json/.md`.

## Plug in a model

```python
import model_harness as mh

class MyModel(mh.ChurnModel):
    def fit(self, X, y): ...; return self
    def predict_proba(self, X): ...            # np.ndarray, shape (n,), P(label = 1)
    # explain(X, k=3) is optional: the default is perturbation-based and works for any model

mh.register_model("my_model", MyModel, targets=("churn", "upgrade"))   # default targets=("churn",)
mh.backtest(["my_model"], target="churn")      # or: python harness/model_harness.py --model my_model
```

Uplift models: subclass `mh.UpliftModel` (`fit(X, treatment, y)`, `predict_uplift(X)` -> per-account uplift,
or a DataFrame with one column per action), then call `mh.register_uplift_model("name", factory)`. A two-model
baseline `TLearner` is built in.

## Data contract: `out/uplift.csv` (written by tm-offers, read by `uplift_eval.load_uplift`)

Long format, one row per account x eligible action, including `do nothing`:
`account_id, action, split (train|test), treated (0/1, exactly one per account), propensity (1/n eligible arms),
outcome_stay_90d (treated row only; 1 = stayed), uplift_hat (P(stay|action) - P(stay|do nothing); 0 for do
nothing)`. Optional: `net_value_hat, true_uplift (simulator truth, evaluation only), pick_uplift, pick_ev,
synthetic`. Policy values use the `split == test` rows (IPW / self-normalised IPW / direct / doubly robust).
The harness never writes `uplift.csv` or `policy_eval.csv`.

## Caveats

- Labels are drawn from a known formula over these same features (`labels.py`), so high AUCs test the pipeline,
  not real-world accuracy. Every output says so.
- The data is one snapshot (as of 2026-10-01). The holdout is a stratified account-level split, **not** a time
  split. With about 35 churn positives per holdout, single splits are noisy: read the CV mean and the
  same-rows oracle.
- Persona checks are provisional. "High" means at or above the 90th percentile of regular accounts' scores
  (David has not yet chosen between 80 and 90); "low" means at or below the median.
- The upgrade rule is a proxy for "near the cap 2+ months", because features.csv has no monthly near-cap count.
- The Orange Belgium uplift data (CC BY-NC-ND) is read in place from `/workspace/tmobile/raw/` and is never
  committed.
