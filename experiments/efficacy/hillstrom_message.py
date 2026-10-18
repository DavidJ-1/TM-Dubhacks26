"""Message-variant uplift on REAL randomized data: Hillstrom MineThatData e-mail test (2008, 64,000 customers).
Public RETAIL E-MAIL data, not telecom. It validates the method; it does not prove anything for carriers.

Arms (randomized 1/3 each): no e-mail, men's-merchandise e-mail, women's-merchandise e-mail.
Question: does matching the message to the customer beat sending the single best message, and how many
customers look like "sleeping dogs" (estimated negative effect), and is that real on held-out data?

Learners (one score per arm vs no e-mail): T-learner LR (same approach as the project's simulated-trial T-learner),
S-learner LR with arm x feature interactions (also the source of plain-language reasons), T-learner and
X-learner gradient boosting, a plain response/risk ranking P(visit) that ignores treatment, and random.
Held-out = pooled out-of-fold scores, 5-fold CV stratified on arm x outcome, 2 seeds.
Qini coefficient = sklift definition (model - random)/(perfect - random), same formula as the earlier public
benchmark; bootstrap 95% CIs on pooled OOF rows, paired.
Policy values are exact IPW (propensity 1/3 by design). Run: python experiments/efficacy/hillstrom_message.py
Data: env HILLSTROM_CSV, else downloads the public copy to experiments/efficacy/data/ (git-ignored).
"""
from __future__ import annotations
import json, os, sys, time, urllib.request, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
URL = "https://hillstrom-sklift.s3.eu-west-2.amazonaws.com/hillstrom.csv.gz"
ARMS = ["No E-Mail", "Mens E-Mail", "Womens E-Mail"]; SHORT = ["none", "mens", "womens"]
SEEDS = [0, 1]; B = int(os.environ.get("B", "200")); THR = 0.02  # |uplift| below 2 points = "no real effect"


def load():
    p = os.environ.get("HILLSTROM_CSV")
    if not p:
        p = HERE / "data" / "hillstrom.csv.gz"
        if not p.exists():
            p.parent.mkdir(exist_ok=True); urllib.request.urlretrieve(URL, p)
    df = pd.read_csv(p)
    a = df.segment.map({s: i for i, s in enumerate(ARMS)}).values.astype(int)
    X = pd.DataFrame({"recency": df.recency, "log_history": np.log1p(df.history), "bought_mens": df.mens,
                      "bought_womens": df.womens, "newbie": df.newbie})
    X = X.join(pd.get_dummies(df.zip_code, prefix="zip", dtype=float).drop(columns="zip_Surburban"))
    X = X.join(pd.get_dummies(df.channel, prefix="ch", dtype=float).drop(columns="ch_Web"))
    return X.astype(float), a, {"visit": df.visit.values, "conversion": df.conversion.values,
                                "spend": df.spend.values}


lr = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=3000))
hgb = lambda s: HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, max_leaf_nodes=15,
                                               min_samples_leaf=100, random_state=s)
hgbr = lambda s: HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05, max_leaf_nodes=15,
                                               min_samples_leaf=100, random_state=s)
P = lambda m, X: m.predict_proba(X)[:, 1]


def s_design(X, arm):
    """S-learner design: features, arm dummies, arm x (standardized) feature interactions."""
    Z = X.values
    t = np.zeros((len(X), 2)); 
    if np.isscalar(arm): t[:, arm - 1] = 1 if arm > 0 else 0
    else:
        for k in (1, 2): t[:, k - 1] = (arm == k)
    return np.hstack([Z, t, Z * t[:, [0]], Z * t[:, [1]]])


def fit_fold(Xtr, atr, ytr, Xte, seed):
    out = {}; n = len(Xte)
    out["random"] = np.random.default_rng(seed).random((n, 2)) - 0.5
    r = P(hgb(seed).fit(Xtr, ytr), Xte); out["response ranking (ignores treatment)"] = np.c_[r, r]
    m = [lr().fit(Xtr[atr == k], ytr[atr == k]) for k in range(3)]
    p = [P(mm, Xte) for mm in m]; out["T-learner LR"] = np.c_[p[1] - p[0], p[2] - p[0]]; out["_p0"] = p[0]
    sc = StandardScaler().fit(Xtr); Xs_tr = pd.DataFrame(sc.transform(Xtr), columns=Xtr.columns)
    Xs_te = pd.DataFrame(sc.transform(Xte), columns=Xte.columns)
    s = LogisticRegression(C=1.0, max_iter=3000).fit(s_design(Xs_tr, atr), ytr)
    ps = [P(s, s_design(Xs_te, k)) for k in range(3)]; out["S-learner LR (interactions)"] = np.c_[ps[1] - ps[0], ps[2] - ps[0]]
    g = [hgb(seed + k).fit(Xtr[atr == k], ytr[atr == k]) for k in range(3)]
    pg = [P(gg, Xte) for gg in g]; out["T-learner GBM"] = np.c_[pg[1] - pg[0], pg[2] - pg[0]]
    xs = []
    for k in (1, 2):  # X-learner (Kunzel et al. 2019) per arm vs control, propensity 0.5 within the pair
        d1 = ytr[atr == k] - P(g[0], Xtr[atr == k]); d0 = P(g[k], Xtr[atr == 0]) - ytr[atr == 0]
        r1 = hgbr(seed + 10 + k).fit(Xtr[atr == k], d1); r0 = hgbr(seed + 20 + k).fit(Xtr[atr == 0], d0)
        xs.append(0.5 * r0.predict(Xte) + 0.5 * r1.predict(Xte))
    out["X-learner GBM"] = np.c_[xs[0], xs[1]]
    out["_best_single"] = 1 + int(np.argmax([ytr[atr == k].mean() for k in (1, 2)]))
    return out


def qini_coef(score, y, t):
    """sklift qini_auc_score definition (same as the earlier public benchmark)."""
    def q(s):
        o = np.argsort(-s, kind="stable"); yt = np.cumsum((y * t)[o]); yc = np.cumsum((y * (1 - t))[o])
        nt = np.cumsum(t[o]); nc = np.cumsum((1 - t)[o])
        return yt - yc * nt / np.maximum(nc, 1)
    n = len(y); qm = q(score); qp = q(y * t - y * (1 - t) + 1e-9 * np.random.default_rng(0).random(n))
    rnd = np.linspace(0, qm[-1], n); a = np.trapezoid
    return (a(qm) - a(rnd)) / (a(qp) - a(rnd))


def decile_table(score, y, t):
    o = np.argsort(-score, kind="stable"); rows = []
    for d, idx in enumerate(np.array_split(o, 10)):
        tt, yy = t[idx], y[idx]
        rows.append({"decile": d + 1, "pred_uplift": score[idx].mean(), "obs_uplift": yy[tt == 1].mean() - yy[tt == 0].mean(),
                     "n": len(idx)})
    return pd.DataFrame(rows)


def ipw_value(pol, a, y):  # pol: chosen arm per row; propensity exactly 1/3
    return (y * (a == pol)).mean() * 3


def ci(x): return f"[{np.percentile(x, 2.5):+.4f}, {np.percentile(x, 97.5):+.4f}]"


def main():
    t0 = time.time(); X, a, Ys = load(); n = len(a); res = {}; lines = []
    for outcome in ("visit", "conversion"):
        y = Ys[outcome]; oof = {}
        for seed in SEEDS:
            strat = a * 2 + y
            for tr, te in StratifiedKFold(5, shuffle=True, random_state=seed).split(X, strat):
                o = fit_fold(X.iloc[tr], a[tr], y[tr], X.iloc[te], seed)
                for k, v in o.items():
                    if k == "_best_single":
                        oof.setdefault(k, []).append(v); continue
                    oof.setdefault(k, {}).setdefault(seed, np.zeros((n, 2)) if np.ndim(v) == 2 else np.zeros(n))[te] = v
        models = [k for k in oof if not k.startswith("_")]
        avg = {k: np.mean([oof[k][s] for s in SEEDS], axis=0) for k in models}
        p0 = np.mean([oof["_p0"][s] for s in SEEDS], axis=0)
        best_single = int(pd.Series(oof["_best_single"]).mode()[0])
        lines.append(f"\n=== Hillstrom outcome: {outcome} (REAL randomized retail e-mail data, n={n}) ===")
        lines.append("arm means: " + ", ".join(f"{SHORT[k]} {y[a == k].mean():.4f}" for k in range(3)))
        rng = np.random.default_rng(7); boots = [rng.integers(0, n, n) for _ in range(B)]
        # --- Qini per arm vs no e-mail
        qrows = []
        for k in (1, 2):
            sub = np.where((a == 0) | (a == k))[0]; tt = (a[sub] == k).astype(int); yy = y[sub]
            base = avg["response ranking (ignores treatment)"][sub, k - 1]
            rb = np.random.default_rng(k); bsub = [rb.integers(0, len(sub), len(sub)) for _ in range(B)]
            qb_base = np.array([qini_coef(base[i], yy[i], tt[i]) for i in bsub])
            for mname in models:
                s = avg[mname][sub, k - 1]; q = qini_coef(s, yy, tt)
                qb = np.array([qini_coef(s[i], yy[i], tt[i]) for i in bsub])
                qrows.append({"outcome": outcome, "arm": SHORT[k], "model": mname, "qini": q,
                              "ci_lo": np.percentile(qb, 2.5), "ci_hi": np.percentile(qb, 97.5),
                              "diff_vs_response_lo": np.percentile(qb - qb_base, 2.5),
                              "diff_vs_response_hi": np.percentile(qb - qb_base, 97.5)})
            dec = decile_table(avg["T-learner LR"][sub, k - 1], yy, tt); dec["arm"] = SHORT[k]; dec["outcome"] = outcome
            dec.to_csv(OUT / f"hillstrom_deciles_{outcome}_{SHORT[k]}_tlr.csv", index=False)
        qdf = pd.DataFrame(qrows); qdf.to_csv(OUT / f"hillstrom_qini_{outcome}.csv", index=False)
        lines.append(qdf.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        # --- policies: matched message vs single best message vs none
        prow = []
        for mname in ["T-learner LR", "S-learner LR (interactions)", "X-learner GBM", "T-learner GBM"]:
            tau = avg[mname]
            match = 1 + np.argmax(tau, axis=1)                       # always e-mail, pick message
            match0 = np.where(tau.max(axis=1) > 0, match, 0)          # allow "do not contact"
            pols = {"no e-mail": np.zeros(n, int), "men's to all": np.ones(n, int), "women's to all": np.full(n, 2),
                    "single best message": np.full(n, best_single), "matched message": match,
                    "matched or skip if negative": match0, "random arm": np.random.default_rng(3).integers(0, 3, n)}
            vb = {p: np.array([ipw_value(pol[i], a[i], y[i]) for i in boots]) for p, pol in pols.items()}
            for p, pol in pols.items():
                prow.append({"outcome": outcome, "model": mname, "policy": p, "value": ipw_value(pol, a, y),
                             "ci_lo": np.percentile(vb[p], 2.5), "ci_hi": np.percentile(vb[p], 97.5),
                             "diff_vs_single_best_lo": np.percentile(vb[p] - vb["single best message"], 2.5),
                             "diff_vs_single_best_hi": np.percentile(vb[p] - vb["single best message"], 97.5),
                             "share_mens": (pol == 1).mean(), "share_womens": (pol == 2).mean(), "share_skip": (pol == 0).mean()})
            # sleeping dogs: estimated negative for best message; check on held-out
            neg = tau.max(axis=1) < 0; neg_any = (tau < 0).any(axis=1)
            def obs_uplift(mask, k):
                i1 = mask & (a == k); i0 = mask & (a == 0)
                return y[i1].mean() - y[i0].mean() if i1.sum() and i0.sum() else np.nan
            sd_b = np.array([neg[i].mean() for i in boots])
            ob = [np.nanmean([obs_uplift(np.isin(np.arange(n), i) & neg, k) for k in (1, 2)]) for i in boots[:50]] if neg.sum() > 30 else [np.nan]
            res.setdefault("sleeping_dogs", []).append({
                "outcome": outcome, "model": mname, "share_negative_best_msg": float(neg.mean()),
                "share_ci": [float(np.percentile(sd_b, 2.5)), float(np.percentile(sd_b, 97.5))],
                "n_flagged": int(neg.sum()), "share_negative_for_some_msg": float(neg_any.mean()),
                "observed_uplift_in_flagged": float(np.nanmean([obs_uplift(neg, k) for k in (1, 2)])) if neg.sum() else None,
                "observed_uplift_ci": [float(np.nanpercentile(ob, 2.5)), float(np.nanpercentile(ob, 97.5))] if neg.sum() > 30 else None,
                "wrong_msg_obs_uplift": {SHORT[k]: float(obs_uplift(tau[:, k - 1] < 0, k)) if (tau[:, k - 1] < 0).sum() > 30 else None for k in (1, 2)},
                "wrong_msg_share": {SHORT[k]: float((tau[:, k - 1] < 0).mean()) for k in (1, 2)}})
            if mname == "T-learner LR":  # four-way segments (Hillstrom, real data, model estimates)
                tb = tau.max(axis=1); hi = p0 >= np.median(p0)
                seg = np.select([tb >= THR, tb <= -THR, hi], ["persuadable", "sleeping dog", "sure thing"], "lost cause")
                res.setdefault("segments", {})[outcome] = pd.Series(seg).value_counts(normalize=True).round(4).to_dict()
        pdf = pd.DataFrame(prow); pdf.to_csv(OUT / f"hillstrom_policy_{outcome}.csv", index=False)
        lines.append(pdf[pdf.model == "T-learner LR"].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    lines.append("\nSleeping dogs:\n" + json.dumps(res["sleeping_dogs"], indent=1))
    lines.append("\nSegments (T-learner LR, threshold 2 points):\n" + json.dumps(res["segments"], indent=1))
    lines.append(f"\nruntime {time.time() - t0:.0f}s, B={B}")
    txt = "\n".join(lines); print(txt); (OUT / "hillstrom_summary.txt").write_text(txt)
    json.dump(res, open(OUT / "hillstrom_summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
