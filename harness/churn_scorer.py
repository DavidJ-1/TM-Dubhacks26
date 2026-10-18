"""Pure Model A scorer for what-if edits (SYNTHETIC).

    from harness.churn_scorer import score_account
    p, risks, stays = score_account(row)   # row: dict or Series of features.csv columns (account_id optional)

Gives the same p_churn_90d / reasons as out/churn_scores.csv for an unmodified row. The model is fit once per
process from out/features.csv + out/labels.csv (same recipe as churn_model.py, ~1 s) and cached in
out/model_a_scorer.pkl, keyed on those files' mtimes, so later calls never retrain. An edited row is
swapped into the full feature table before prepare(), because prepare() uses table-level medians and one-hots.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from churn_features import leak_columns, prepare  # noqa: E402
from churn_model import OUT, PERSONA_PREFIX, ModelA  # noqa: E402

_STATE: dict = {}
SCRATCH_ID = "ACC-WHATIF-0001"


def _load(label: str = "churn_90d"):
    fp, lp, cache = OUT / "features.csv", OUT / "labels.csv", OUT / "model_a_scorer.pkl"
    key = (label, fp.stat().st_mtime, lp.stat().st_mtime)
    if _STATE.get("key") == key:
        return _STATE
    feats, labels = pd.read_csv(fp), pd.read_csv(lp)
    barred = set(labels.columns) - {"account_id"}
    feats = feats.drop(columns=[c for c in feats.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])
    model = None
    if cache.exists():
        try:
            saved = pickle.loads(cache.read_bytes())
            model = saved["model"] if saved.get("key") == key else None
        except Exception:
            model = None
    if model is None:
        persona = feats["account_id"].str.startswith(PERSONA_PREFIX)
        if "is_persona" in feats.columns:
            persona |= feats["is_persona"].fillna(0).astype(int).eq(1)
        X = prepare(feats)
        y = labels.set_index("account_id")[label].reindex(feats["account_id"])
        train = (~persona.values) & y.notna().values
        model = ModelA().fit(X[train], y[train].astype(int))
        try:
            cache.write_bytes(pickle.dumps({"key": key, "model": model}))
        except OSError:
            pass
    _STATE.clear()
    _STATE.update(key=key, feats=feats, model=model)
    return _STATE


def score_account(feature_row, label: str = "churn_90d") -> tuple[float, list[str], list[str]]:
    """Return (p_churn_90d, top-3 risk reasons, top-3 stay reasons) for one account's feature row (synthetic)."""
    st = _load(label)
    feats, model = st["feats"], st["model"]
    row = dict(feature_row)
    acc = str(row.get("account_id") or SCRATCH_ID)
    row["account_id"] = acc
    base = feats.set_index("account_id")
    if acc in base.index:
        new = base.loc[acc].copy()
        for k, v in row.items():
            if k != "account_id" and k in new.index:
                new[k] = v
        table = base.copy()
        table.loc[acc] = new
    else:
        table = pd.concat([base, pd.DataFrame([row]).set_index("account_id").reindex(columns=base.columns)])
    table = table.reset_index().rename(columns={"index": "account_id"})
    X = prepare(table)
    Xa = X.loc[[acc]]
    p = float(np.round(model.predict_proba(Xa)[0], 6))
    ex = model.explain(Xa, k=3, raw=table[table["account_id"] == acc]).iloc[0]
    risks = [ex[f"risk_reason_{i}"] for i in (1, 2, 3) if ex[f"risk_reason_{i}"]]
    stays = [ex[f"stay_reason_{i}"] for i in (1, 2, 3) if ex[f"stay_reason_{i}"]]
    return p, risks, stays


if __name__ == "__main__":  # self-check: unmodified rows reproduce churn_scores.csv
    sc = pd.read_csv(OUT / "churn_scores.csv").set_index("account_id")
    f = pd.read_csv(OUT / "features.csv")
    ids = [i for i in sc.index if i.startswith(PERSONA_PREFIX)][:6] + list(sc.index[:20])
    bad = 0
    for i in ids:
        p, r, s = score_account(f[f.account_id == i].iloc[0].to_dict())
        want = sc.loc[i]
        ok = abs(p - want.p_churn_90d) < 1e-6 and r == [x for x in want[["risk_reason_1", "risk_reason_2", "risk_reason_3"]].fillna("") if x] \
            and s == [x for x in want[["stay_reason_1", "stay_reason_2", "stay_reason_3"]].fillna("") if x]
        bad += not ok
        if not ok:
            print("MISMATCH", i, p, want.p_churn_90d, r, s)
    print(f"[SYNTHETIC] checked {len(ids)} accounts, mismatches {bad}")
