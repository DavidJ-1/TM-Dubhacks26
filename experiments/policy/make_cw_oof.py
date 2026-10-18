"""Class-weighted (balanced) LR OOF on the same folds/features as baseline. SYNTHETIC. Writes only here."""
import os, sys, warnings; warnings.filterwarnings("ignore"); sys.dont_write_bytecode=True
import numpy as np, pandas as pd
sys.path.insert(0, "/workspace/tmobile/scratch_models"); sys.path.insert(0, "/workspace/tmobile/TM-Dubhacks26/harness")
import folds
from churn_features import CORE_FEATURES, leak_columns, prepare
from sklearn.pipeline import make_pipeline; from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegressionCV; from sklearn.model_selection import StratifiedKFold
feats, y, labels = folds.load_raw()
barred = set(labels.columns) - {"account_id"}
fc = feats.drop(columns=[c for c in feats.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])
X = prepare(fc).astype(float); core=[c for c in CORE_FEATURES if c in X.columns]; yv=y.values
p=np.zeros(len(yv))
for tr,te in folds.get_folds(yv):
    m=make_pipeline(StandardScaler(),LogisticRegressionCV(Cs=[0.003,0.01,0.03,0.1,0.3,1,3,10],cv=StratifiedKFold(3,shuffle=True,random_state=0),scoring="neg_log_loss",max_iter=5000,class_weight="balanced")).fit(X[core].iloc[tr],yv[tr])
    p[te]=m.predict_proba(X[core].iloc[te])[:,1]
pd.DataFrame({"account_id":feats.account_id,"p_cw":p}).to_csv("oof_classweighted_lr.csv",index=False); print("done mean",p.mean())
