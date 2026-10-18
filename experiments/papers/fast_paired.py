"""Fallback: fold-paired deltas (no bootstrap) for run_papers.py models. ALL SYNTHETIC."""
__file__ = "/workspace/tmobile/scratch_models/papers/run_papers.py"
src = open(__file__).read(); exec(src.split("B0, B1 = ")[0])
B0, B1 = "B0 baseline ModelA LR (core, incl. port/competitor)", "B1 ModelA LR CPNI-compliant core"
rows = []
for name, p in oof.items():
    ps = rk(p) if name in RANK_ONLY else np.clip(p, 0, 1); r = {"model": name, **M.all_metrics(yv, ps)}
    for ref, tag in ((B0, "vsB0"), (B1, "vsB1")):
        d, s = M.paired_fold_comparison(yv, ps, oof[ref], fid)
        r[f"{tag}_dauc"] = f"{s.loc['auc','mean']:+.4f}±{s.loc['auc','sd']:.4f}"; r[f"{tag}_dtop10"] = f"{s.loc['top10','mean']:+.3f}±{s.loc['top10','sd']:.3f} ({int(s.loc['top10','n_folds_better'])}/5 better)"
    if name in RANK_ONLY: r["brier"] = r["ece"] = np.nan
    rows.append(r)
res = pd.DataFrame(rows); res.to_csv("/workspace/tmobile/scratch_models/papers/results_foldpaired.csv", index=False)
pd.DataFrame(oof).assign(account_id=feats.account_id.values, fold=fid, churn_90d=yv).to_csv("/workspace/tmobile/scratch_models/papers/oof_predictions_fast.csv", index=False)
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40); print(res.round(4).to_string())
