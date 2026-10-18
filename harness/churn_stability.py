"""Model A stability check (SYNTHETIC): bootstrap-resample the training accounts, refit Model A each time,
and record how often each persona clears its bar (high = top 10%, low = below median) and how often its
top reason stays the same. Answers "are personas 21/22 robust or did they squeak by on one fit?".

Run: python harness/churn_stability.py [--n 200]   -> out/churn_stability.csv, out/churn_stability.md
All numbers are synthetic (simulated labels on the sandbox's fictional accounts).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from churn_features import leak_columns, prepare  # noqa: E402
from churn_model import OUT, PERSONA_PREFIX, PERSONAS_HIGH, PERSONAS_LOW, SEED, ModelA  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--label", default="churn_90d")
    a = ap.parse_args(argv)
    feats, labels = pd.read_csv(OUT / "features.csv"), pd.read_csv(OUT / "labels.csv")
    barred = set(labels.columns) - {"account_id"}
    feats = feats.drop(columns=[c for c in feats.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])
    persona = feats["account_id"].str.startswith(PERSONA_PREFIX).values
    X = prepare(feats)
    y = labels.set_index("account_id")[a.label].reindex(X.index)
    train = (~persona) & y.notna().values
    Xtr, ytr = X[train], y[train].astype(int)
    pids = [(f"{PERSONA_PREFIX}{n}", "high") for n in PERSONAS_HIGH] + [(f"{PERSONA_PREFIX}{n}", "low") for n in PERSONAS_LOW]

    def run(idx):
        m = ModelA().fit(Xtr.iloc[idx], ytr.iloc[idx])
        p = pd.Series(m.predict_proba(X), index=X.index)
        reg = p[~persona]
        hi, lo = reg.quantile(0.90), reg.quantile(0.50)
        ex = m.explain(X.loc[[pid for pid, _ in pids]], k=3, raw=feats.set_index("account_id").loc[[pid for pid, _ in pids]].reset_index()).set_index("account_id")
        out = []
        for pid, want in pids:
            v = p[pid]
            out.append({"account_id": pid, "want": want, "p": v, "pctile": (reg < v).mean() * 100,
                        "pass": bool(v >= hi) if want == "high" else bool(v < lo),
                        "top_reason": ex.loc[pid, "risk_reason_1" if want == "high" else "stay_reason_1"],
                        "top3": " | ".join(str(ex.loc[pid, f"{'risk' if want == 'high' else 'stay'}_reason_{i}"]) for i in (1, 2, 3))})
        return out

    base = pd.DataFrame(run(np.arange(len(ytr)))).set_index("account_id")
    rng = np.random.default_rng(SEED)
    pos, neg = np.where(ytr.values == 1)[0], np.where(ytr.values == 0)[0]
    rows = []
    for b in range(a.n):
        idx = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])  # stratified bootstrap
        for r in run(idx):
            r["boot"] = b
            rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "churn_stability.csv", index=False)

    def topword(s):
        return s.str.replace(r"\d+(\.\d+)?", "#", regex=True)  # compare reason type, not the exact number
    summ = []
    for pid, want in pids:
        d = df[df.account_id == pid]
        summ.append({"persona": pid.replace(PERSONA_PREFIX, ""), "want": want,
                     "pass_rate": d["pass"].mean(), "pctile_p05": d.pctile.quantile(0.05),
                     "pctile_median": d.pctile.median(), "pctile_p95": d.pctile.quantile(0.95),
                     "same_top_reason": (topword(d.top_reason.fillna("")) == topword(pd.Series([base.loc[pid, "top_reason"] or ""]))[0]).mean(),
                     "top_in_top3": topword(d.top3.fillna("")).str.contains(topword(pd.Series([base.loc[pid, "top_reason"] or ""]))[0], regex=False).mean(),
                     "base_top_reason": base.loc[pid, "top_reason"]})
    s = pd.DataFrame(summ)
    all_pass = df.groupby("boot")["pass"].all().mean()
    md = ["# Model A stability check - SYNTHETIC", "",
          f"{a.n} stratified bootstrap refits of Model A on the {len(ytr)} regular accounts (label `{a.label}`). "
          "High personas must land in the top 10% of regular accounts and low personas below the median.", "",
          f"**All 6 personas pass together in {all_pass:.0%} of refits.**", "",
          "| persona | want | pass rate | percentile (5th / median / 95th) | same #1 reason | #1 reason still in top 3 | #1 reason (full fit) |",
          "|---|---|---|---|---|---|---|"]
    for r in s.itertuples():
        md.append(f"| {r.persona} | {r.want} | {r.pass_rate:.0%} | {r.pctile_p05:.1f} / {r.pctile_median:.1f} / {r.pctile_p95:.1f} "
                  f"| {r.same_top_reason:.0%} | {r.top_in_top3:.0%} | {r.base_top_reason} |")
    md += ["", "Synthetic labels on fictional sandbox accounts; pipeline validation, not real-world accuracy."]
    (OUT / "churn_stability.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
