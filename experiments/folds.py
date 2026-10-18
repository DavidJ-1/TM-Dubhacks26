"""Exact out-of-fold folds used by harness/churn_model.py (Model A). ALL DATA SYNTHETIC.

Definition (copied from harness/churn_model.py main()):
  rows   = demo_data/features.csv accounts, personas excluded (account_id startswith 'ACC-PERSONA-' or is_persona==1)
           -> 5,000 regular accounts (of 5,042), in file order
  y      = labels.csv churn_90d aligned to that order
  folds  = StratifiedKFold(n_splits=5, shuffle=True, random_state=2026).split(X, y)   (no grouping)
Fold ids match the `fold` column of demo_data/churn_oof_pred.csv (verified by verify()).
Inputs are opened read-only (pandas read_csv); nothing in the repo is written.
"""
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

REPO = Path("/workspace/tmobile/TM-Dubhacks26")
DATA = REPO / "demo_data"
SEED, N_SPLITS, PERSONA_PREFIX = 2026, 5, "ACC-PERSONA-"


def load_raw(data_dir=DATA):
    """Return (feats_regular DataFrame incl. account_id, y Series indexed by account_id, labels_regular)."""
    f = pd.read_csv(Path(data_dir) / "features.csv")
    lab = pd.read_csv(Path(data_dir) / "labels.csv")
    persona = f["account_id"].str.startswith(PERSONA_PREFIX)
    if "is_persona" in f.columns:
        persona |= f["is_persona"].fillna(0).astype(int).eq(1)
    y = lab.set_index("account_id")["churn_90d"].reindex(f["account_id"])
    keep = (~persona.values) & y.notna().values
    f = f[keep].reset_index(drop=True)
    y = y[keep].astype(int)
    return f, y, lab.set_index("account_id").loc[f["account_id"]].reset_index()


def get_folds(y=None):
    """List of (train_idx, test_idx) positional arrays over the 5,000 regular accounts."""
    if y is None:
        _, y, _ = load_raw()
    y = np.asarray(y)
    return list(StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED).split(np.zeros(len(y)), y))


def fold_ids(y=None):
    folds = get_folds(y)
    n = sum(len(te) for _, te in folds)
    fid = np.zeros(n, dtype=int)
    for k, (_, te) in enumerate(folds):
        fid[te] = k
    return fid


def verify():
    f, y, _ = load_raw()
    ref = pd.read_csv(DATA / "churn_oof_pred.csv").set_index("account_id").loc[f["account_id"], "fold"].values
    ok = bool((ref == fold_ids(y)).all())
    print(f"[SYNTHETIC] n={len(y)} positives={int(y.sum())} rate={y.mean():.4f}; folds match demo_data churn_oof_pred.csv: {ok}")
    return ok


if __name__ == "__main__":
    verify()
