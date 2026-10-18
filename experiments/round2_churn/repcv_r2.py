"""3-seed repeated 5-fold CV (seeds 101-103; noise estimate, NOT the canonical folds) for candidates. ALL SYNTHETIC."""
import os, sys; sys.dont_write_bytecode = True
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from run_r2 import *
CAND = {"full": ["baseline ModelA LR", "RECIPE-LR: generator terms (fits synthetic recipe)", "spline-LR tuned (core+raw contacts)", "RECIPE-spline-LR (fits synthetic recipe)", "stack LR-meta[recipe-LR, spline, EBM]"],
        "compliant": ["baseline ModelA LR", "spline-LR tuned (core)", "spline-LR tuned (core+raw contacts)", "RECIPE-spline-LR (fits synthetic recipe)", "EBM interactions=10 (core+raw contacts)", "stack LR-meta[recipe-LR, spline, EBM]"]}
jobs = []
for seed in (101, 102, 103):
    fl = list(StratifiedKFold(5, shuffle=True, random_state=seed).split(np.zeros(len(yv)), yv))
    for tr in CAND:
        sp = specs(tr)
        for n in CAND[tr]: jobs.append((tr, n, sp[n][0], sp[n][1], fl, seed))
def go(tr, n, mk, c, fl, seed):
    _, _, p, _, _ = run_one(tr, n, mk, c, fl); return seed, tr, n, p
out = Parallel(n_jobs=8)(delayed(go)(*j) for j in jobs)
rows = []; preds = {}
for seed, tr, n, p in out:
    rows.append({"seed": seed, "model": f"[{tr}] {n}", **M.all_metrics(yv, np.clip(p, 0, 1))}); preds[(seed, tr, n)] = p
rep = pd.DataFrame(rows); rep.to_csv(HERE / "repeated_cv_r2.csv", index=False)
# paired per-seed deltas vs the track baseline
for (seed, tr, n), p in preds.items():
    b = preds[(seed, tr, "baseline ModelA LR")]
    rep.loc[(rep.seed == seed) & (rep.model == f"[{tr}] {n}"), "d_top10_vs_track_base"] = M.top_capture(yv, p) - M.top_capture(yv, b)
    rep.loc[(rep.seed == seed) & (rep.model == f"[{tr}] {n}"), "d_auc_vs_track_base"] = M.roc_auc_score(yv, p) - M.roc_auc_score(yv, b)
    b0 = preds[(seed, "full", "baseline ModelA LR")]
    rep.loc[(rep.seed == seed) & (rep.model == f"[{tr}] {n}"), "d_top10_vs_B0"] = M.top_capture(yv, p) - M.top_capture(yv, b0)
rep.to_csv(HERE / "repeated_cv_r2.csv", index=False)
pd.set_option("display.width", 300)
print(rep.groupby("model")[["auc", "pr_auc", "top10", "brier", "d_auc_vs_track_base", "d_top10_vs_track_base", "d_top10_vs_B0"]].agg(["mean", "std"]).round(4).to_string())
