"""Upgrade model improvement study (ALL SYNTHETIC). Baseline: LR on prepare() features, ~0.74 AUC vs oracle 0.808.

Feature tiers (tm-data / David):
  (a) features.csv only: prepare() features (+ 'domain' upgrade features built from raw features.csv columns:
      per-line cap utilisation, over-cap share, hotspot GB per line, plan tier dummies, device age beyond 12 months).
      These are legitimate inputs, but we chose them after reading the labels.py upgrade recipe.
  (b) (a) + NON-driver enrichment: recent_job_change (b1), + income_band as an ordinal (b2). income_band is a
      coarsened version of the income driver, so b2 is a partial proxy for a recipe driver.
  (b3) (b2) + household columns (is_family_plan, likely_kid_flag, n_kid_lines, kid_age_band, promo_months_remaining,
      contract_or_financing_months_remaining): derived from real sandbox tables, used in NO label (DATA_README).
  (c) (b3) + the RECIPE-REVEALING driver columns: step_up_cost_pct_income (the affordability term itself),
      log(household_income / national median) (the income term itself), on_top_plan (no next plan).
      If (c) closes the gap, the model is recovering our own label formula; (a)/(b) are the honest numbers.
Models: LR (C tuned by inner CV), LR + degree-2 interactions on a subset (C tuned), HGB + sigmoid (bench params),
HGB tuned (RandomizedSearchCV over learning_rate, max_leaf_nodes, min_samples_leaf, l2_regularization).
Evaluation: outer 5-fold stratified CV (seed 42) on the 5,000 real regular accounts, so all scores are
out-of-fold; tuning happens inside each outer training fold. Also trained on the 50k synthetic set (and 250k if
present) and tested on all 5,000 real accounts.

    OMP_NUM_THREADS=1 python3 -m harness.bench.upgrade_improve [--skip-synthetic]
Outputs: out/upgrade_improve.csv/.md, out/upgrade_improve_check.png, out/upgrade_persona_check.csv
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, StratifiedKFold  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import PolynomialFeatures, StandardScaler  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402

from harness.bench import bench as B  # noqa: E402

T = "upgrade_90d"
ENRICH = B.REPO / "harness/out/enrichment.csv"
SCALED = {"synthetic_50k": B.REPO / "harness/out/scaled", "synthetic_250k": B.REPO / "harness/out/scaled_250k"}
BANDS = ["<$25k", "$25-50k", "$50-75k", "$75-100k", "$100-150k", "$150-200k", "$200k+"]
DOMAIN = ["util_per_line", "over_cap_share", "hotspot_per_line", "tier_basic", "tier_standard", "device_age_beyond12"]
B1 = ["recent_job_change"]
B2 = B1 + ["income_band_ord"]
HOUSE = ["is_family_plan", "likely_kid_flag", "n_kid_lines", "kid_age_band_ord", "promo_months_remaining",
         "contract_or_financing_months_remaining"]
B3 = B2 + HOUSE
C = B3 + ["step_up_cost_pct_income_c", "log_income_ratio", "on_top_plan"]
RECIPE_REVEALING = ["step_up_cost_pct_income_c", "log_income_ratio", "on_top_plan"]
# interaction subset: usage/plan headroom, device, bill shock, tenure (+ affordability terms when present)
INTER = ["util_per_line", "over_cap_share", "tier_basic", "tier_standard", "device_age_beyond12", "bill_increase_pct",
         "promo_expired_recent", "tenure_capped60", "data_growth_pct", "installment_ended_recent", "income_band_ord",
         "step_up_cost_pct_income_c", "log_income_ratio"]


def extra_cols(f: pd.DataFrame) -> pd.DataFrame:
    """Domain + enrichment columns from a raw frame that already carries the enrichment columns."""
    o = pd.DataFrame(index=f.index)
    nl = f["n_lines"].clip(lower=1)
    cap = f["plan_data_cap_gb"]
    o["util_per_line"] = ((f["data_gb_3m_avg"] / nl) / cap).where(cap.notna() & (cap > 0), 0.0).clip(0, 5)
    o["over_cap_share"] = f["n_lines_over_cap_3m"] / nl
    o["hotspot_per_line"] = f["hotspot_gb_3m_avg"] / nl
    o["tier_basic"] = (f["plan_tier"] == "basic").astype(float)
    o["tier_standard"] = (f["plan_tier"] == "standard").astype(float)
    o["device_age_beyond12"] = (f["max_device_age_months"].fillna(0) - 12).clip(lower=0) / 12
    o["recent_job_change"] = f["recent_job_change"].astype(float)
    o["income_band_ord"] = f["income_band"].map({b: i for i, b in enumerate(BANDS)}).astype(float)
    o["step_up_cost_pct_income_c"] = f["step_up_cost_pct_income"].fillna(0).clip(0, 10)
    o["log_income_ratio"] = np.log(f["household_income_usd"] / f["area_median_income_usd"]).clip(-2, 2)
    o["on_top_plan"] = f["next_plan_sku"].isna().astype(float)
    for c in HOUSE:
        if c == "kid_age_band_ord":
            o[c] = f["kid_age_band"].map({"none": 0, "18-24": 1, "13-17": 2, "0-12": 3}).astype(float)
        else:
            o[c] = f[c].astype(float)
    assert not o.isna().any().any(), o.isna().sum()
    return o


def build(frames):
    """frames: list of (name, raw features incl. enrichment). One prepare() over all of them, then split."""
    # account ids repeat across the 50k and 250k sets (both start at SYN-000001); make them unique per frame so
    # prepare()'s index joins cannot misalign rows
    allf = pd.concat([f.assign(account_id=nm + ":" + f["account_id"].astype(str)) for nm, f in frames],
                     ignore_index=True)
    assert allf["account_id"].is_unique
    base_cols = pd.read_csv(B.DEFAULT_FEATURES, nrows=1).columns  # prepare() sees only features.csv columns
    P = B.prepare_fn()(allf[[c for c in base_cols if c in allf.columns]].copy())
    assert (P.index.values == allf["account_id"].values).all(), "prepare() reordered rows"
    P = P.reset_index(drop=True)
    E = extra_cols(allf).reset_index(drop=True)
    X = pd.concat([P, E], axis=1)
    out, i = {}, 0
    for name, f in frames:
        out[name] = X.iloc[i:i + len(f)].reset_index(drop=True); i += len(f)
    return out, list(P.columns)


def tiers(base):
    a = base + DOMAIN
    return {"a0 prepare() only (baseline)": base, "a features.csv + domain": a, "b1 a + job change": a + B1,
            "b2 b1 + income band": a + B2, "b3 b2 + household (family/kids/promo)": a + B3,
            "c b3 + recipe drivers (RECIPE-REVEALING)": a + C}


# ---------------- models ----------------
def lr_tuned(cols):
    return GridSearchCV(Pipeline([("sc", StandardScaler()), ("lr", LogisticRegression(max_iter=5000))]),
                        {"lr__C": [0.01, 0.03, 0.1, 0.3, 1.0]}, scoring="roc_auc",
                        cv=StratifiedKFold(3, shuffle=True, random_state=1))


def lr_inter(cols):
    sub = [c for c in INTER if c in cols]
    rest = [c for c in cols if c not in sub]
    ct = ColumnTransformer([("int", Pipeline([("sc", StandardScaler()), ("poly", PolynomialFeatures(
        2, interaction_only=True, include_bias=False))]), sub), ("rest", "passthrough", rest)])
    return GridSearchCV(Pipeline([("ct", ct), ("sc", StandardScaler()), ("lr", LogisticRegression(max_iter=5000))]),
                        {"lr__C": [0.003, 0.01, 0.03, 0.1, 0.3]}, scoring="roc_auc",
                        cv=StratifiedKFold(3, shuffle=True, random_state=1))


HGB_BENCH = dict(max_depth=3, max_iter=200, learning_rate=0.05, early_stopping=True, validation_fraction=0.15,
                 n_iter_no_change=20, l2_regularization=1.0, min_samples_leaf=40, random_state=B.SEED)


def hgb_sigmoid(cols):
    return CalibratedClassifierCV(HistGradientBoostingClassifier(**HGB_BENCH), method="sigmoid", cv=3)


HGB_SPACE = {"learning_rate": [0.02, 0.05, 0.1], "max_leaf_nodes": [4, 8, 15, 31], "min_samples_leaf": [20, 40, 80, 160],
             "l2_regularization": [0.0, 1.0, 5.0], "max_iter": [100, 200, 400]}


def hgb_tuned(cols, n_iter=12):
    return RandomizedSearchCV(HistGradientBoostingClassifier(early_stopping=False, random_state=B.SEED), HGB_SPACE,
                              n_iter=n_iter, scoring="roc_auc", cv=StratifiedKFold(3, shuffle=True, random_state=1),
                              random_state=0)


MODELS = {"lr_tuned": lr_tuned, "lr_interactions": lr_inter, "hgb_sigmoid": hgb_sigmoid, "hgb_tuned": hgb_tuned}


def best_params(m):
    return getattr(m, "best_params_", None)


def oof_eval(X, y, cols, mk):
    skf = StratifiedKFold(B.N_FOLDS, shuffle=True, random_state=B.SEED)
    p = np.zeros(len(y)); fa, bp = [], []
    for tr, te in skf.split(X, y):
        m = mk(cols).fit(X.iloc[tr][cols], y[tr])
        p[te] = m.predict_proba(X.iloc[te][cols])[:, 1]
        fa.append(roc_auc_score(y[te], p[te])); bp.append(best_params(m))
    return p, fa, bp


def row(y, p, extra):
    return {"auc": roc_auc_score(y, p), "prauc": average_precision_score(y, p), "top10_capture": B.capture(y, p, 0.1),
            **extra}


def personas(X_reg, y, X_all_ids, Xp, cols, mk):
    m = mk(cols).fit(X_reg[cols], y)
    pop, pp = m.predict_proba(X_reg[cols])[:, 1], m.predict_proba(Xp[cols])[:, 1]
    hi, lo = B.EXPECT[T]
    out = {}
    for i, a in enumerate(X_all_ids):
        pct = float((pop < pp[i]).mean() * 100 + (pop == pp[i]).mean() * 50)
        out[a] = {"pct": round(pct, 1), "expect": "high" if a in hi else "low",
                  "pass": bool(pct >= 90 if a in hi else pct < 50)}
    return out


def main():
    ap = argparse.ArgumentParser(description="Upgrade improvement study. ALL SYNTHETIC.")
    ap.add_argument("--skip-synthetic", action="store_true")
    ap.add_argument("--sources", nargs="+", default=list(SCALED))
    a = ap.parse_args()
    B.OUT.mkdir(parents=True, exist_ok=True)
    fr = pd.read_csv(B.DEFAULT_FEATURES).merge(pd.read_csv(ENRICH).drop(columns=["n_lines"], errors="ignore"),
                                                on="account_id", validate="1:1")
    lr_ = pd.read_csv(B.DEFAULT_LABELS)
    frames = [("real", fr)]
    syn = {}
    if not a.skip_synthetic:
        for src, d in [(k, v) for k, v in SCALED.items() if k in a.sources]:
            fs = d / ("features_scaled.csv" if src == "synthetic_50k" else "features_scaled.csv")
            ls = d / "labels_scaled.csv"
            if fs.exists() and ls.exists():
                F = pd.read_csv(fs)
                hh = d / "household_scaled.csv"
                if not set(HOUSE[:3]) <= set(F.columns) and hh.exists():
                    F = F.merge(pd.read_csv(hh).drop(columns=["n_lines"], errors="ignore"), on="account_id",
                                validate="1:1")
                L = pd.read_csv(ls)
                assert (F.account_id.values == L.account_id.values).all()
                syn[src] = (F, L)
                frames.append((src, F))
                print(f"loaded {src}: {len(F)} rows", flush=True)
    # leak guard: no labels.csv column (other than ids) may be an input
    label_cols = set(lr_.columns) - {"account_id", "is_persona"}
    Xs, base = build(frames)
    for nm, X in Xs.items():
        bad = [c for c in X.columns if c in label_cols or B.re.search(B.LEAK_RE, c)]
        assert not bad, (nm, bad)
    d = fr[["account_id", "is_persona"]].merge(lr_.drop(columns=["is_persona"]), on="account_id", validate="1:1")
    reg = (d["is_persona"] == 0).values
    Xr = Xs["real"][reg].reset_index(drop=True); y = d.loc[reg, T].values.astype(int)
    orc = d.loc[reg, B.ORACLE[T]].values
    pers_ids = [x for x in B.EXPECT[T][0] + B.EXPECT[T][1]]
    pmask = d["account_id"].isin(pers_ids).values
    Xp = Xs["real"][pmask].reset_index(drop=True); pid = d.loc[pmask, "account_id"].tolist()
    TI = tiers(base)
    rows, prs, modal = [], {}, {}
    oracle = row(y, orc, {})
    for tn, cols in TI.items():
        for mn, mk in MODELS.items():
            if tn.startswith("a0") and mn in ("lr_interactions",):
                continue
            t0 = time.time()
            p, fa, bp = oof_eval(Xr, y, cols, mk)
            r = row(y, p, {"tier": tn, "model": mn, "train_source": "real_5k (5-fold OOF)", "n_features": len(cols),
                           "auc_fold_sd": float(np.std(fa, ddof=1)), "best_params_per_fold": json.dumps(bp, default=str),
                           "secs": round(time.time() - t0, 1)})
            rows.append(r)
            print(f"{tn:48s} {mn:16s} auc {r['auc']:.4f} sd {r['auc_fold_sd']:.3f} pr {r['prauc']:.3f} "
                  f"top10 {r['top10_capture']:.3f} ({r['secs']}s)", flush=True)
            if mn in ("lr_tuned", "hgb_tuned"):
                prs[(tn, mn)] = personas(Xr, y, pid, Xp, cols, mk)
            if mn == "hgb_tuned":
                ks = [json.dumps(b, sort_keys=True) for b in bp]
                modal[tn] = json.loads(max(set(ks), key=ks.count))
        for src in syn:
            ds = syn[src][1]
            ys = Xs[src].pipe(lambda X: ds[T].values.astype(int))
            for mn in ("lr_tuned", "hgb_tuned"):
                t0 = time.time()
                if mn == "hgb_tuned":  # too slow to re-search on 250k: reuse the modal real-5k CV choice
                    mk = lambda cols, bp=modal[tn]: HistGradientBoostingClassifier(early_stopping=False,  # noqa: E731
                                                                                   random_state=B.SEED, **bp)
                else:
                    mk = MODELS[mn]
                m = mk(cols).fit(Xs[src][cols], ys)
                p = m.predict_proba(Xr[cols])[:, 1]
                r = row(y, p, {"tier": tn, "model": mn, "train_source": f"{src} -> real 5k", "n_features": len(cols),
                               "auc_fold_sd": np.nan, "best_params_per_fold": json.dumps(best_params(m) or modal.get(tn), default=str),
                               "secs": round(time.time() - t0, 1)})
                rows.append(r)
                print(f"{tn:48s} {mn:16s} [{src}] auc {r['auc']:.4f} pr {r['prauc']:.3f} top10 {r['top10_capture']:.3f}",
                      flush=True)
    res = pd.DataFrame(rows)
    res.insert(0, "synthetic", 1)
    res["oracle_auc_same_rows"] = oracle["auc"]; res["gap_to_oracle"] = res["oracle_auc_same_rows"] - res["auc"]
    res.to_csv(B.OUT / "upgrade_improve.csv", index=False, float_format="%.4f")
    pr = pd.DataFrame([{"tier": t, "model": m, "account_id": a, **v} for (t, m), dd in prs.items() for a, v in dd.items()])
    pr.insert(0, "synthetic", 1); pr.to_csv(B.OUT / "upgrade_persona_check.csv", index=False)
    md = ["# Upgrade model improvement (ALL SYNTHETIC)\n",
          f"Target upgrade_90d, {int(y.sum())}/{len(y)} positives on the real sandbox accounts; oracle AUC on the same "
          f"rows {oracle['auc']:.3f}, PR-AUC {oracle['prauc']:.3f}, top-10% {oracle['top10_capture']:.3f}.\n",
          "| tier | model | trained on | AUC | fold sd | PR-AUC | top-10% | gap to oracle | personas (5) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in res.iterrows():
        pp = prs.get((r.tier, r.model)) if r.train_source.startswith("real") else None
        ps = f"{sum(v['pass'] for v in pp.values())}/5" if pp else ""
        md.append(f"| {r.tier} | {r.model} | {r.train_source} | {r.auc:.3f} | "
                  f"{'' if pd.isna(r.auc_fold_sd) else f'{r.auc_fold_sd:.3f}'} | {r.prauc:.3f} | {r.top10_capture:.3f} | "
                  f"{r.gap_to_oracle:+.3f} | {ps} |")
    md.append("\nPersona percentiles (refit on all 5,000; high = 25/28 must be >= 90th pct, low = 22/24/27 < 50th):\n")
    md.append(pr.pivot_table(index=["tier", "model"], columns="account_id", values="pct").round(1).to_markdown()
              if hasattr(pd.DataFrame, "to_markdown") and _has_tabulate() else
              pr.pivot_table(index=["tier", "model"], columns="account_id", values="pct").round(1).to_string())
    (B.OUT / "upgrade_improve.md").write_text("\n".join(md))
    plot(res, oracle["auc"], B.OUT / "upgrade_improve_check.png")
    print("\n".join(md))


def _has_tabulate():
    try:
        import tabulate  # noqa: F401
        return True
    except ImportError:
        return False


def plot(res, orc, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    r = res[res.train_source.str.startswith("real")]
    fig, ax = plt.subplots(figsize=B.FIG_IN, dpi=B.FIG_DPI)
    tiers_ = list(dict.fromkeys(r.tier)); models = list(dict.fromkeys(r.model))
    w = 0.8 / len(models)
    for j, m in enumerate(models):
        g = r[r.model == m].set_index("tier").reindex(tiers_)
        ax.bar(np.arange(len(tiers_)) + j * w, g.auc, w, yerr=g.auc_fold_sd, capsize=3, label=m)
    ax.axhline(orc, ls="--", c="k", label=f"oracle ceiling {orc:.3f}")
    ax.set_xticks(np.arange(len(tiers_)) + 0.4 - w / 2); ax.set_xticklabels(tiers_, rotation=12, fontsize=9)
    ax.set_ylim(0.6, 0.85); ax.set_ylabel("ROC AUC, 5-fold OOF on real 5k"); ax.legend(fontsize=9)
    ax.set_title("upgrade_90d by feature tier. Tier c uses the label recipe's own driver columns (recipe-revealing)")
    B.save_fig(fig, path); plt.close(fig)


if __name__ == "__main__":
    main()
