"""Metrics + paired comparisons for oof_r2.csv. ALL SYNTHETIC."""
import sys; sys.dont_write_bytecode = True
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from common import *
oof = pd.read_csv(HERE / "oof_r2.csv"); cols = [c for c in oof.columns if c.startswith("[")]
B0, B1 = "[full] baseline ModelA LR", "[compliant] baseline ModelA LR"
rows = []
for n in cols:
    p = oof[n].values; a = M.all_metrics(yv, np.clip(p, 0, 1)); pf = M.per_fold(yv, p, fid); ci = M.bootstrap_ci(yv, p, n_boot=500)
    r = {"model": n, **{k: round(v, 4) for k, v in a.items()}, "top10_ci": "[%.3f,%.3f]" % ci["top10_ci"], "auc_ci": "[%.3f,%.3f]" % ci["auc_ci"]}
    for ref, tag in ((B0, "vsB0"), (B1, "vsB1")):
        if n == ref: continue
        d, s = M.paired_fold_comparison(yv, p, oof[ref].values, fid); pb = M.paired_bootstrap_delta(yv, p, oof[ref].values, n_boot=500)
        r[f"{tag}_dAUC_fold"] = f"{s.loc['auc','mean']:+.4f}±{s.loc['auc','sd']:.4f}"
        r[f"{tag}_dAUC_boot"] = "%+.4f [%+.4f,%+.4f]" % pb["d_auc_boot"]
        r[f"{tag}_dTop10_fold"] = f"{s.loc['top10','mean']:+.3f}±{s.loc['top10','sd']:.3f} ({int(s.loc['top10','n_folds_better'])}/5)"
        r[f"{tag}_dTop10_boot"] = "%+.3f [%+.3f,%+.3f]" % pb["d_top10_boot"]
    rows.append(r)
res = pd.DataFrame(rows); res.to_csv(HERE / "results_r2.csv", index=False)
pd.set_option("display.width", 400); pd.set_option("display.max_columns", 40); pd.set_option("display.max_colwidth", 70)
print(res.to_string())
print("ORACLE p_true_90d (eval-only, full):", {k: round(v, 4) for k, v in M.all_metrics(yv, p_true).items()})
