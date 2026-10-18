"""Task 3: upsell-eligible ranking = upgrade score with churn guardrail. ALL SYNTHETIC (simulated upgrade label)."""
import numpy as np, pandas as pd, json
d = pd.read_csv("task2_oof.csv"); best = open("task2_best.txt").read().strip()
s = d[best].values; y = d.upgrade_90d.values; n = len(d); P = y.sum()
churn_top = d.p_churn_oof.rank(ascending=False, method="first") <= round(0.1 * n)
sup3 = d.support_90d >= 3
elig = ~(churn_top | sup3)
rows = []
def summarize(name, mask_rank, k):
    idx = np.where(mask_rank)[0]; top = idx[np.argsort(-s[idx])][:k]
    rows.append({"strategy": name, "pool": int(mask_rank.sum()), "targeted": len(top), "upgraders_hit": int(y[top].sum()),
                 "capture_of_all_upgraders": round(y[top].sum() / P, 3), "precision": round(y[top].mean(), 3),
                 "expected_upgrades_from_score": round(float(s[top].sum()), 1),
                 "churners_targeted": int(d.churn_90d.values[top].sum()), "support3plus_targeted": int(sup3.values[top].sum()),
                 "churn_top10_targeted": int(churn_top.values[top].sum())})
k = round(0.1 * n)
summarize("Unguarded: top 10% (500) by upgrade score", np.ones(n, bool), k)
summarize("Guarded: top 500 by upgrade score among eligible", elig.values, k)
summarize("Guarded: all eligible accounts above unguarded top-10% score threshold", elig.values & (s >= np.sort(s)[::-1][k - 1]), n)
summarize("Guarded: whole eligible pool (no score cut)", elig.values, n)
r = pd.DataFrame(rows)
info = {"model": best, "n": n, "upgraders": int(P), "excluded_churn_top10": int(churn_top.sum()), "excluded_support_3plus": int(sup3.sum()),
        "excluded_total": int((~elig).sum()), "eligible": int(elig.sum()), "upgraders_lost_to_guardrail": int(y[~elig.values].sum()),
        "upgrade_rate_excluded": round(float(y[~elig.values].mean()), 4), "upgrade_rate_eligible": round(float(y[elig.values].mean()), 4)}
r.to_csv("task3_results.csv", index=False); json.dump(info, open("task3_info.json", "w"), indent=1)
print(json.dumps(info, indent=1)); print(r.to_string())
