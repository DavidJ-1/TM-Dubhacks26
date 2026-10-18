"""Does anything beyond line counts + pre-cutoff financing events predict the real label? SYNTHETIC."""
import os; os.environ.setdefault("OMP_NUM_THREADS", "1")
import sys; sys.path.insert(0, "/workspace/tmobile/scratch_models"); sys.argv = ["x"]
import numpy as np, pandas as pd, importlib.util, metrics as M
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
src = open("backtest.py").read().split("out, info = [], {}")[0]; g = {}; exec(src, g)
for cut in ["2026-06", "2026-03"]:
    a, X, _ = g["build"](pd.Period(cut, "M")); y = a.y.values
    cv = StratifiedKFold(5, shuffle=True, random_state=2026)
    S = ["n_device_lines", "n_lines", "n_byod", "n_fin_starts_pre", "n_fin_ends_pre", "months_since_fin_start", "months_since_fin_end", "fin_start_cents_pre"]
    m = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=3000))
    for name, cols in [("structural only (line counts + pre-cutoff financing events)", S), ("all features", list(X.columns)),
                       ("behaviour only (no line counts, no financing/bill)", [c for c in X.columns if c not in S and not c.startswith("bill") and c not in ("data_gb_l3","voice_minutes_l3","streaming_hours_l3","hotspot_gb_l3","data_p3")])]:
        p = cross_val_predict(m(), X[cols], y, cv=cv, method="predict_proba")[:, 1]
        print(cut, f"{name}: AUC={M.roc_auc_score(y,p):.3f} PR-AUC={M.average_precision_score(y,p):.3f} top10={M.top_capture(y,p):.3f} n_feat={len(cols)}")
    # per-line purchase rate in window by device-line count (is it ~flat per line?)
    t = a.assign(k=a.n_device_lines.clip(upper=5)).groupby("k").y.agg(["mean", "size"]); print(t.round(3).T.to_string())
