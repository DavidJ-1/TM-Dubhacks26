"""Model A: 90-day churn scoring -> out/churn_scores.csv.   ALL DATA, LABELS AND SCORES ARE SYNTHETIC/SIMULATED.

One-command rerun (no cached artifacts; refits every time):
    python harness/churn_model.py                       # real: out/features.csv + out/labels.csv -> out/
    python harness/churn_model.py --label churn_90d     # pick label column explicitly
    python harness/churn_model.py --features out/mock/features.csv --labels out/mock/labels.csv --out-dir out/mock

Output contract (out/churn_scores.csv): account_id, p_churn_90d, risk_rank, risk_reason_1..3, stay_reason_1..3
  risk_rank 1 = highest risk; all accounts (incl. ACC-PERSONA-*) are scored; personas never used for training.
Also writes churn_persona_check.txt and churn_model_card.md to the same out dir.

Model (default 'model_a'): standardized logistic regression (L2, C by 5-fold CV on log loss) on
churn_features.prepare(); probabilities are maximum-likelihood calibrated to the synthetic label base rate
(optional --target-90d-rate intercept shift). Features whose fitted sign contradicts domain knowledge are dropped
and the model refit, so reason codes stay sensible. Reasons = per-account logit contributions vs the average
training account, summed per reason group, top 3 up (risk) and top 3 down (stay).
Uses harness/model_harness.py (ChurnModel base class, register_model) when importable; local fallback otherwise.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split

warnings.filterwarnings("ignore", category=FutureWarning)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from churn_features import CORE_FEATURES, NON_REASON_GROUPS, leak_columns, phrase, prepare, reason_group  # noqa: E402

try:
    import model_harness as mh  # tm-harness lane
    _Base = getattr(mh, "ChurnModel", object)
except Exception:  # file not there yet / broken: local fallback
    mh, _Base = None, object

OUT = HERE / "out"
PERSONA_PREFIX = "ACC-PERSONA-"
PERSONAS_HIGH, PERSONAS_LOW = ["04", "21", "22", "27"], ["10", "24"]
PERSONA_HIGH_PCT = 85.0  # high personas must land in the top 15% (David via tm-data, 2026-10-17); low = below median
LABEL_CANDIDATES = ["churn_90d", "churned_90d", "churn_label_90d", "churn_label", "churn", "churned", "label", "y"]
CONTRACT = ["account_id", "p_churn_90d", "risk_rank", "risk_reason_1", "risk_reason_2", "risk_reason_3",
            "stay_reason_1", "stay_reason_2", "stay_reason_3"]
SEED = 2026
FLIP_Z = 0.5  # sd on the churn-raising side that bars a feature group from being a stay reason
MIN_REASON_LOGIT = 0.05  # contributions smaller than this are not shown as reasons

# domain sign priors (+1 raises churn, -1 lowers). Fitted coefs with the opposite sign are dropped.
SIGN_PRIOR = {
    **{c: 1 for c in ["unresolved_90d", "unresolved_270d", "troubled_4plus", "negative_contacts_90d", "neg_sentiment",
                      "cancel_inquiries_270d", "cancellation_inquiry_contacts_90d", "bill_increase_pct",
                      "promo_expired_recent", "competitor_research_score", "port_out_inquiry", "early_tenure",
                      "low_app_use", "no_financing", "no_autopay", "plan_misfit_share", "short_history",
                      "max_device_age_months", "mean_device_age_months", "n_lines_device_36m_plus",
                      "bill_change_3m_pct", "n_lines_over_cap_3m", "n_lines_light_on_premium"]},
    **{c: -1 for c in ["tenure_capped60", "tenure_months", "app_sessions_30d", "avg_sentiment", "avg_sentiment_90d",
                       "min_sentiment_270d", "extra_lines", "n_lines", "autopay", "n_financed_lines"]},
}


class ModelA(_Base):
    """Interpretable logistic regression. Duck-types tm-harness ChurnModel: fit / predict_proba / explain."""
    name = "model_a"

    def __init__(self, target_rate: float | None = None, feature_set: str = "core"):
        self.target_rate, self.feature_set = target_rate, feature_set

    # -- ChurnModel interface
    def fit(self, X: pd.DataFrame, y):
        X = X.astype(float)
        y = np.asarray(y).astype(int)
        cols = list(X.columns)
        if self.feature_set == "core":
            core = [c for c in CORE_FEATURES if c in cols]
            cols = core if len(core) >= 5 else cols  # unknown schema -> use everything
        start, self.dropped_for_sign_ = list(cols), []
        for _ in range(5):
            mu, sd = X[cols].mean(), X[cols].std(ddof=0).replace(0, 1)
            Z = (X[cols] - mu) / sd
            cv = LogisticRegressionCV(Cs=[0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0], cv=5, scoring="neg_log_loss",
                                      max_iter=5000, random_state=SEED).fit(Z, y)
            coef = pd.Series(cv.coef_[0], index=cols)
            wrong = [c for c, s in SIGN_PRIOR.items() if c in coef.index and coef[c] * s < 0]
            if not wrong:
                break
            cols = [c for c in cols if c not in wrong]
            self.dropped_for_sign_ += wrong
        self.C_ = float(cv.C_[0])
        self.lr_ = LogisticRegression(C=self.C_, max_iter=5000).fit(Z, y)
        self.cols_, self.mu_, self.sd_ = cols, mu, sd
        self.coef_ = pd.Series(self.lr_.coef_[0], index=cols)
        self.intercept_ = float(self.lr_.intercept_[0])
        if self.target_rate:  # optional intercept shift so mean p over training rows = target
            z = self._z(X) @ self.coef_.values
            lo, hi = -30.0, 30.0
            for _ in range(100):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if (1 / (1 + np.exp(-(mid + z)))).mean() < self.target_rate else (lo, mid)
            self.intercept_ = mid
        return self

    def _z(self, X):
        X = X.reindex(columns=self.cols_, fill_value=0.0).astype(float)
        return (X - self.mu_) / self.sd_

    def decision_function(self, X):
        return self._z(X).values @ self.coef_.values + self.intercept_

    def predict_proba(self, X) -> np.ndarray:
        return 1 / (1 + np.exp(-self.decision_function(X)))

    def contributions(self, X) -> pd.DataFrame:
        """Per-account logit contribution of each feature vs the average training account."""
        return self._z(X) * self.coef_

    def explain(self, X, k: int = 3, raw: pd.DataFrame | None = None) -> pd.DataFrame:
        C = self.contributions(X)
        G = C.T.groupby([reason_group(c) for c in C.columns]).sum().T
        G = G.drop(columns=[c for c in G.columns if c in NON_REASON_GROUPS])
        if raw is None and mh is not None and hasattr(mh, "_raw_features"):
            try:
                raw = mh._raw_features(X.index).combine_first(X)
            except Exception:
                raw = None
        raw = raw if raw is not None else X
        raw = raw.set_index("account_id") if "account_id" in raw.columns else raw
        # direction guard: a group is never shown as a STAY reason if any of its sign-known features sits on the
        # churn-raising side for this account (> FLIP_Z sd), and never as a RISK reason if none of its sign-known
        # features is on the churn-raising side. Prevents collinearity from flipping a reason's direction.
        Z = self._z(X)
        prior = pd.Series({c: SIGN_PRIOR[c] for c in Z.columns if c in SIGN_PRIOR}, dtype=float)
        risky = Z[prior.index] * prior  # >0 = churn-raising side
        grp_of = {c: reason_group(c) for c in prior.index}
        self.flips_blocked_ = 0
        rows = []
        for acc, g in G.iterrows():
            r = raw.loc[acc] if acc in raw.index else pd.Series(dtype=float)
            ra = risky.loc[acc]
            bad_stay = {grp_of[c] for c in ra.index if ra[c] > FLIP_Z}
            has_prior = set(grp_of.values())
            some_risky = {grp_of[c] for c in ra.index if ra[c] > 0}
            up_c = [n for n, v in g.sort_values(ascending=False).items() if v > MIN_REASON_LOGIT]
            dn_c = [n for n, v in g.sort_values().items() if v < -MIN_REASON_LOGIT]
            up_ok = [n for n in up_c if n not in has_prior or n in some_risky]
            dn_ok = [n for n in dn_c if n not in bad_stay]
            self.flips_blocked_ += (len(up_c) - len(up_ok)) + (len(dn_c) - len(dn_ok))
            up = [phrase(n, r, True) for n in up_ok][:k]
            dn = [phrase(n, r, False) for n in dn_ok][:k]
            up, dn = up + [""] * (k - len(up)), dn + [""] * (k - len(dn))
            rows.append([acc, *up, *dn])
        return pd.DataFrame(rows, columns=["account_id", *[f"risk_reason_{i}" for i in range(1, k + 1)],
                                           *[f"stay_reason_{i}" for i in range(1, k + 1)]])


MODELS = {"model_a": ModelA}
if mh is not None and hasattr(mh, "register_model"):
    try:
        mh.register_model("model_a", ModelA)
    except Exception as e:  # already registered or different signature
        print(f"note: model_harness.register_model failed: {e}", file=sys.stderr)


def get_model(name: str, **kw):
    if name in MODELS:
        return MODELS[name](**kw)
    if mh is not None:
        for attr in ("get_model", "make_model"):
            if hasattr(mh, attr):
                return getattr(mh, attr)(name)
        for attr in ("REGISTRY", "MODELS", "_REGISTRY"):
            reg = getattr(mh, attr, None)
            if isinstance(reg, dict) and name in reg:
                return reg[name]()
    raise SystemExit(f"unknown model {name!r}; known: {list(MODELS)}")


def find_label(labels: pd.DataFrame, wanted: str | None) -> str:
    if wanted:
        if wanted not in labels.columns:
            raise SystemExit(f"label column {wanted!r} not in labels file: {list(labels.columns)}")
        return wanted
    for c in LABEL_CANDIDATES:
        if c in labels.columns:
            return c
    raise SystemExit(f"no churn label column found (tried {LABEL_CANDIDATES}); pass --label")


def persona_report(scores: pd.DataFrame, raw: pd.DataFrame) -> tuple[str, bool]:
    reg = scores[~scores["account_id"].str.startswith(PERSONA_PREFIX)]["p_churn_90d"]
    hi_cut, lo_cut = reg.quantile(PERSONA_HIGH_PCT / 100), reg.quantile(0.50)
    lines, ok = [f"High = top {100 - PERSONA_HIGH_PCT:g}% of regular accounts (p >= {hi_cut:.4f}); low = below median (p < {lo_cut:.4f})."], True
    lines.append(f"{'persona':<16}{'want':<6}{'p_churn_90d':>12}{'pctile':>8}{'rank':>7}{'vs cutoff':>11}  result  reasons")
    s = scores.set_index("account_id")
    for want, ids in (("high", PERSONAS_HIGH), ("low", PERSONAS_LOW)):
        for n in ids:
            acc = f"{PERSONA_PREFIX}{n}"
            if acc not in s.index:
                lines.append(f"{acc:<16}{want:<6} MISSING"); ok = False; continue
            r = s.loc[acc]
            pct = (reg < r.p_churn_90d).mean() * 100
            dist = r.p_churn_90d - (hi_cut if want == "high" else lo_cut)
            passed = (r.p_churn_90d >= hi_cut) if want == "high" else (r.p_churn_90d < lo_cut)
            ok &= bool(passed)
            why = (r.risk_reason_1, r.risk_reason_2, r.risk_reason_3) if want == "high" else \
                (r.stay_reason_1, r.stay_reason_2, r.stay_reason_3)
            lines.append(f"{acc:<16}{want:<6}{r.p_churn_90d:>12.4f}{pct:>7.1f}%{int(r.risk_rank):>7}{dist:>+11.4f}  "
                         f"{'PASS' if passed else 'FAIL':<6}  " + " | ".join(w for w in why if w))
    lines.append(f"OVERALL: {'PASS' if ok else 'FAIL'} (provisional: labels may be regenerated)")
    return "\n".join(lines), ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--features", default=str(OUT / "features.csv"))
    ap.add_argument("--labels", default=str(OUT / "labels.csv"))
    ap.add_argument("--label", default=None, help="label column (default: auto, prefers churn_90d)")
    ap.add_argument("--out-dir", default=None, help="default: out/ for real inputs; required for non-default inputs")
    ap.add_argument("--model", default="model_a")
    ap.add_argument("--feature-set", choices=["core", "all"], default="core",
                    help="model_a inputs: curated core subset (default) or every prepared column")
    ap.add_argument("--target-90d-rate", type=float, default=None,
                    help="optional: shift intercept so mean p (regular accounts) = this rate")
    a = ap.parse_args(argv)

    feat_p, lab_p = Path(a.features).resolve(), Path(a.labels).resolve()
    is_mock = "mock" in str(feat_p).lower() or "mock" in str(lab_p).lower()
    out_dir = Path(a.out_dir).resolve() if a.out_dir else (feat_p.parent / "mock" if is_mock else OUT)
    if is_mock and out_dir == OUT.resolve():
        raise SystemExit("refusing to write mock-based scores to the real out/ dir; use --out-dir out/mock")
    out_dir.mkdir(parents=True, exist_ok=True)

    feats = pd.read_csv(feat_p)
    labels = pd.read_csv(lab_p)
    if "account_id" not in feats.columns or "account_id" not in labels.columns:
        raise SystemExit("features and labels both need an account_id column")
    label = find_label(labels, a.label)
    if labels["account_id"].duplicated().any() or feats["account_id"].duplicated().any():
        raise SystemExit("duplicate account_id in features or labels")
    persona = feats["account_id"].str.startswith(PERSONA_PREFIX)
    if "is_persona" in feats.columns:
        persona |= feats["is_persona"].fillna(0).astype(int).eq(1)
    # leak guard (matches tm-harness loader): EVERY labels.csv column except account_id is barred from the
    # features, whatever tm-data adds (upgrade_*, drivers, ...), plus anything that looks label-derived.
    barred = set(labels.columns) - {"account_id"}
    feats = feats.drop(columns=[c for c in feats.columns if c != "account_id" and
                                (c in barred or c in leak_columns([c]))])
    X = prepare(feats)
    y_all = labels.set_index("account_id")[label].reindex(feats["account_id"])
    y_all.index.name = "account_id"
    vals = set(y_all.dropna().unique())
    if not vals <= {0, 1}:
        raise SystemExit(f"label {label!r} must be 0/1, found {sorted(vals)[:5]}")
    train = (~persona.values) & y_all.notna().values
    Xtr, ytr = X[train], y_all[train].astype(int)
    rate = ytr.mean()
    print(f"[SYNTHETIC] train rows {len(ytr)} (personas excluded), label {label!r} rate {rate:.4f}, features {X.shape[1]}")

    # quick AUC sanity on a stratified 25% account holdout (full metrics live in model_harness / bench)
    i_tr, i_te = train_test_split(np.arange(len(ytr)), test_size=0.25, stratify=ytr, random_state=SEED)
    kw = {"target_rate": a.target_90d_rate, "feature_set": a.feature_set} if a.model == "model_a" else {}
    m_ho = get_model(a.model, **{k: v for k, v in kw.items() if k != "target_rate"}).fit(Xtr.iloc[i_tr], ytr.iloc[i_tr])
    p_te = m_ho.predict_proba(Xtr.iloc[i_te])
    auc = roc_auc_score(ytr.iloc[i_te], p_te)
    lab_idx = labels.set_index("account_id")
    extra = {}
    te_ids = Xtr.index[i_te]
    churn_cols = [c for c in labels.columns if c not in (label, "account_id") and
                  any(t in c.lower() for t in ("churn", "toy", "p_true", "hazard")) and "upgrade" not in c.lower()]
    for c in churn_cols:
        v = lab_idx.loc[te_ids, c]
        if set(v.dropna().unique()) <= {0, 1} and v.nunique() == 2:
            extra[f"AUC vs {c}"] = roc_auc_score(v, p_te)
        elif pd.api.types.is_numeric_dtype(v) and v.nunique() > 10 and c not in ("is_persona",):
            extra[f"Spearman vs {c}"] = pd.Series(p_te, index=te_ids).corr(v, method="spearman")
    print(f"[SYNTHETIC] holdout AUC {auc:.3f} (n={len(i_te)}, positives={int(ytr.iloc[i_te].sum())}), "
          f"mean p {p_te.mean():.4f} vs observed {ytr.iloc[i_te].mean():.4f}; "
          + ", ".join(f"{k} {v:.3f}" for k, v in extra.items()))

    # out-of-fold predictions (5-fold stratified, regular accounts only): every row is scored by a model that never
    # saw it, so charts (gain, calibration) can use honest held-out scores instead of in-sample ones.
    oof = np.full(len(ytr), np.nan)
    fold_id = np.zeros(len(ytr), dtype=int)
    okw = {k: v for k, v in kw.items() if k != "target_rate"}
    for f, (a_tr, a_te) in enumerate(StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED).split(Xtr, ytr)):
        oof[a_te] = get_model(a.model, **okw).fit(Xtr.iloc[a_tr], ytr.iloc[a_tr]).predict_proba(Xtr.iloc[a_te])
        fold_id[a_te] = f
    oof_df = pd.DataFrame({"account_id": Xtr.index, "p_churn_90d": np.round(oof, 6), "fold": fold_id})
    oof_df.to_csv(out_dir / "churn_oof_pred.csv", index=False)
    oof_auc = roc_auc_score(ytr, oof)
    print(f"[SYNTHETIC] 5-fold out-of-fold AUC {oof_auc:.3f} (n={len(ytr)}, positives={int(ytr.sum())}), "
          f"mean p {oof.mean():.4f}; wrote churn_oof_pred.csv")

    # final model on all labeled regular accounts, score everyone
    model = get_model(a.model, **kw).fit(Xtr, ytr)
    p = model.predict_proba(X)
    try:
        expl = model.explain(X, k=3, raw=feats)
    except TypeError:
        expl = model.explain(X, k=3)
    print(f"[SYNTHETIC] reason-direction guard blocked {getattr(model, 'flips_blocked_', 0)} candidate reasons")
    sc = pd.DataFrame({"account_id": X.index, "p_churn_90d": np.round(p, 6)})
    sc["risk_rank"] = sc["p_churn_90d"].rank(ascending=False, method="first").astype(int)
    sc = sc.merge(expl, on="account_id", how="left").sort_values("risk_rank")[CONTRACT]
    sc.to_csv(out_dir / "churn_scores.csv", index=False)

    report, ok = persona_report(sc, feats)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M %Z").strip() + " PDT"
    hdr = (f"Model A persona check  [SYNTHETIC/SIMULATED]  {stamp}\ninputs: {feat_p} + {lab_p} (label {label})"
           f"{'  [MOCK INPUTS]' if is_mock else ''}\n")
    (out_dir / "churn_persona_check.txt").write_text(hdr + report + "\n")
    print(report)

    coef = model.coef_.sort_values() if hasattr(model, "coef_") else pd.Series(dtype=float)
    reg_p = sc[~sc["account_id"].str.startswith(PERSONA_PREFIX)]["p_churn_90d"]
    top = pd.concat([coef.tail(8)[::-1], coef.head(6)])
    card = f"""# Model A (churn) model card - SYNTHETIC / SIMULATED

**Pipeline validation on synthetic data, not real-world accuracy.** Inputs are the judge sandbox's stub accounts
(5,042 households, all fictional) and simulated 90-day churn labels. tm-data's labels come from a known logistic
formula over these same features, so a high AUC and LR ~ p_true_90d are expected by construction.
{'**MOCK INPUTS** (dev/test run, not the real output).' if is_mock else ''}

- Run: `python harness/churn_model.py{' --label ' + label if a.label else ''}` ({stamp}); refits from scratch each run.
- Inputs: `{feat_p.name}` + `{lab_p.name}`, label `{label}`; training rows {len(ytr)} regular accounts
  (ACC-PERSONA-* excluded from training, scored only).
- Features ({len(getattr(model, 'cols_', X.columns))} used of {X.shape[1]} prepared; `harness/churn_features.py`):
  unresolved / negative-sentiment support contacts (raw contact counts excluded), sentiment, cancellation inquiries,
  bill increase / promo expired, competitor research, port-out inquiry, tenure, app use, plan fit, financing,
  device age, AutoPay, lines, usage, add-ons, segment/plan one-hots; BYOD / unlimited / short-history flags.
  Dropped for contradicting domain sign: {', '.join(getattr(model, 'dropped_for_sign_', [])) or 'none'}.
- Method: {a.model} ({a.feature_set} features): standardized L2 logistic regression, C={getattr(model, 'C_', float('nan')):g} (5-fold CV,
  log loss). Probabilities calibrated by maximum likelihood to the label base rate
  {'(intercept shifted to target ' + str(a.target_90d_rate) + ')' if a.target_90d_rate else ''}.
  Reasons: per-account logit contribution vs the average account, summed per reason group; top 3 up = risk,
  top 3 down = stay (blank if no group moves the logit by >= {MIN_REASON_LOGIT}). Direction guard: a group with a
  churn-raising value (> {FLIP_Z} sd) is never a stay reason; blocked {getattr(model, 'flips_blocked_', 0)} candidate reasons.
- Synthetic metrics: holdout AUC **{auc:.3f}** (stratified 25%, n={len(i_te)}, {int(ytr.iloc[i_te].sum())} churners);
  {'; '.join(f'{k} {v:.3f}' for k, v in extra.items()) or ''}.
  5-fold out-of-fold AUC **{oof_auc:.3f}** (all {len(ytr)} regular accounts; held-out scores in `churn_oof_pred.csv`).
  Label base rate {rate:.4f} per 90 days (~{1 - (1 - rate) ** (1 / 3):.4%}/month); mean scored p (regular) {reg_p.mean():.4f}.
- Persona check (high = top {100 - PERSONA_HIGH_PCT:g}%, low = below median): {'PASS' if ok else 'FAIL'} (provisional; see churn_persona_check.txt).
- Largest standardized coefficients (synthetic): {', '.join(f'{k} {v:+.2f}' for k, v in top.items())}.
- Limits: no real churn outcomes; sandbox patterns are designed in; full metrics/backtest live in model_harness / bench.
"""
    (out_dir / "churn_model_card.md").write_text(card)
    print(f"wrote {out_dir/'churn_scores.csv'} ({len(sc)} rows), churn_persona_check.txt, churn_model_card.md")
    print(sc.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
