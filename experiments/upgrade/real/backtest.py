"""REAL-history device-upgrade backtest from the judge sandbox (stub data, SYNTHETIC). Sandbox opened read-only.
Label (account): any line's device_purchase_date falls in the 3 purchase months after the cutoff.
Features: ONLY pre-cutoff observations (billing/usage/support before cutoff, account attributes); nothing from
the lines' current device (age, sku, financing balance/remaining, trade-in, protection add-ons) is used."""
import os, sys, json, sqlite3, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.path.insert(0, "/workspace/tmobile/scratch_models")
import numpy as np, pandas as pd
import metrics as M
from sklearn.model_selection import StratifiedKFold
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score

DB = "file:/workspace/tmobile/TM-Dubhacks26/vendor/dubhacks/data/sandbox.db?mode=ro"
DEMO = "/workspace/tmobile/TM-Dubhacks26/demo_data"
c = sqlite3.connect(DB, uri=True)
acc = pd.read_sql("select account_id, tenure_months, contact_preference, credit_tier, autopay from accounts", c)
lines = pd.read_sql("select line_id, account_id, plan_sku, byod, device_purchase_date from lines", c)
plans = pd.read_sql("select sku, family, tier, data_cap_gb from plans", c)
bill = pd.read_sql("select * from billing_history", c)
use = pd.read_sql("select u.*, l.account_id from usage_monthly u join lines l using(line_id)", c)
sup = pd.read_sql("select * from support_interactions", c)
aadd = pd.read_sql("select a.account_id, d.kind from account_addons a join addons d on d.sku=a.addon_sku", c)
acc = acc[~acc.account_id.str.startswith("ACC-PERSONA-")].reset_index(drop=True)
AS_OF = pd.Period("2026-10", "M")

def mlist(end, n): return [str(end - i) for i in range(n)][::-1]

def build(cut):  # cut = last pre-cutoff month (Period); window = next 3 months
    win = [str(cut + i) for i in (1, 2, 3)]
    lag = (AS_OF - cut).n - 1                    # months between cutoff month-end and as_of
    a = acc.copy(); a["tenure_at_cut"] = a.tenure_months - (AS_OF - cut).n + 1
    a = a[a.tenure_at_cut >= 1].copy()           # account must exist before cutoff
    L = lines.copy(); L["pm"] = L.device_purchase_date.str[:7]
    lab = L[L.pm.isin(win)].groupby("account_id").size()
    a["y"] = a.account_id.map(lab).fillna(0).gt(0).astype(int)
    # roster at cutoff (no line add/remove events exist in the sandbox; usage rows start at account open)
    r = L.groupby("account_id").agg(n_lines=("line_id", "size"), n_byod=("byod", "sum"), plan_sku=("plan_sku", "first"))
    a = a.join(r, on="account_id"); a["n_device_lines"] = a.n_lines - a.n_byod
    a = a.merge(plans.rename(columns={"sku": "plan_sku"}), on="plan_sku", how="left")
    # billing strictly before/at cutoff month
    b = bill[bill.month <= str(cut)].copy(); b["mi"] = b.month.map(lambda m: (cut - pd.Period(m, "M")).n)
    g = b.groupby("account_id")
    di = b[b.change_reason == "device_installment"]; ie = b[b.change_reason == "installment_ended"]
    F = pd.DataFrame({
        "bill_last": g.total_cents.last(), "bill_mean": g.total_cents.mean(),
        "bill_trend_3m": g.apply(lambda d: d.sort_values("month").total_cents.tail(3).mean() / max(1, d.sort_values("month").total_cents.head(max(1, len(d) - 3)).mean()) - 1),
        "n_fin_starts_pre": di.groupby("account_id").size(), "months_since_fin_start": di.groupby("account_id").mi.min(),
        "n_fin_ends_pre": ie.groupby("account_id").size(), "months_since_fin_end": ie.groupby("account_id").mi.min(),
        "fin_start_cents_pre": di.groupby("account_id").change_cents.sum(), "bill_months_pre": g.size()})
    a = a.join(F, on="account_id")
    for col in ["n_fin_starts_pre", "n_fin_ends_pre", "fin_start_cents_pre"]: a[col] = a[col].fillna(0)
    for col in ["months_since_fin_start", "months_since_fin_end"]: a[col] = a[col].fillna(24)
    # usage pre-cutoff
    u = use[use.month <= str(cut)]
    last3, prev3 = mlist(cut, 3), mlist(cut - 3, 3)
    ua = u.groupby(["account_id", "month"])[["data_gb", "voice_minutes", "streaming_hours", "hotspot_gb"]].sum().reset_index()
    l3 = ua[ua.month.isin(last3)].groupby("account_id").mean(numeric_only=True).add_suffix("_l3")
    p3 = ua[ua.month.isin(prev3)].groupby("account_id").data_gb.mean().rename("data_p3")
    a = a.join(l3, on="account_id").join(p3, on="account_id")
    a["data_growth"] = (a.data_gb_l3 / a.data_p3 - 1).clip(-1, 3)
    a["data_per_line"] = a.data_gb_l3 / a.n_lines
    a["util_vs_cap"] = (a.data_per_line / a.data_cap_gb).fillna(0)
    # support strictly before cutoff
    s = sup[sup.interaction_date < str(cut + 1) + "-01"]
    sg = s.groupby("account_id")
    a = a.join(pd.DataFrame({"sup_n_pre": sg.size(), "sup_unres_pre": sg.resolved.apply(lambda x: (x == 0).sum()),
                             "sup_sent_pre": sg.sentiment.mean(), "sup_device_pre": s[s.topic == "device"].groupby("account_id").size(),
                             "sup_plan_pre": s[s.topic == "plan_change"].groupby("account_id").size()}), on="account_id")
    for col in ["sup_n_pre", "sup_unres_pre", "sup_device_pre", "sup_plan_pre"]: a[col] = a[col].fillna(0)
    # account add-ons (home internet/streaming). Caveat: current state, no add/remove history exists.
    k = pd.crosstab(aadd.account_id, aadd.kind).add_prefix("acct_addon_")
    a = a.join(k, on="account_id")
    a = a.reset_index(drop=True)
    X = a.drop(columns=["account_id", "y", "tenure_months", "plan_sku"])
    X = pd.get_dummies(X, columns=[c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]).astype(float)
    X["cap_missing"] = X.data_cap_gb.isna().astype(float)
    X = X.fillna(0)
    return a, X, win

def run(cut):
    a, X, win = build(cut); y = a.y.values
    folds = list(StratifiedKFold(5, shuffle=True, random_state=2026).split(X, y)); fid = np.zeros(len(y), int)
    for k, (_, te) in enumerate(folds): fid[te] = k
    mk = {"LR": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=3000)),
          "HGB": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, l2_regularization=1.0, min_samples_leaf=40, random_state=0)}
    P = {}
    for n, m in mk.items():
        p = np.zeros(len(y))
        for tr, te in folds: p[te] = m().fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
        P[n] = p
    # heuristic: P(any device line buys) with flat per-line rate, minus lines with a financing start in last 8 months
    elig = (a.n_device_lines - a.n_fin_starts_pre).clip(lower=0).values
    P["Heuristic: eligible device lines (count)"] = elig + 1e-3 * a.months_since_fin_start.values
    lab = pd.read_csv(f"{DEMO}/labels.csv").set_index("account_id")
    churn = pd.read_csv(f"{DEMO}/churn_oof_pred.csv").set_index("account_id")
    P["Simulated p_upgrade_90d (as-of Oct; uses CURRENT device, leaky)"] = lab.loc[a.account_id, "p_upgrade_90d"].values
    P["Churn OOF p_churn_90d (as-of Oct)"] = churn.loc[a.account_id, "p_churn_90d"].values
    rows = []
    for n, p in P.items():
        cal = n in ("LR", "HGB"); pf = M.per_fold(y, np.clip(p, 0, 1) if cal else p, fid)
        am = M.all_metrics(y, np.clip(p, 0, 1)) if cal else {"auc": roc_auc_score(y, p), "pr_auc": M.average_precision_score(y, p), "top10": M.top_capture(y, p)}
        ci = M.bootstrap_ci(y, p, n_boot=200)
        r = {"cutoff": str(cut), "window": "..".join([win[0], win[-1]]), "n": len(y), "pos": int(y.sum()), "rate": round(y.mean(), 4), "model": n,
             **{k: round(v, 4) for k, v in am.items()}, "auc_fold": f"{pf.auc.mean():.3f}±{pf.auc.std():.3f}",
             "top10_fold": f"{pf.top10.mean():.3f}±{pf.top10.std():.3f}", "auc_ci": "[%.3f, %.3f]" % ci["auc_ci"],
             "top10_ci": "[%.3f, %.3f]" % ci["top10_ci"], "pr_auc_ci": "[%.3f, %.3f]" % ci["pr_auc_ci"]}
        if n == "HGB":
            d = M.paired_bootstrap_delta(y, p, P["LR"], n_boot=200); r["dAUC_vs_LR"] = "%+.3f [%+.3f, %+.3f]" % d["d_auc_boot"]
            r["dTop10_vs_LR"] = "%+.3f [%+.3f, %+.3f]" % d["d_top10_boot"]
        rows.append(r)
    sf = pd.Series({col: max(roc_auc_score(y, X[col]), 1 - roc_auc_score(y, X[col])) for col in X.columns if X[col].nunique() > 1}).sort_values(ascending=False)
    lr = mk["LR"]().fit(X, y); coef = pd.Series(lr[-1].coef_[0], index=X.columns).sort_values(key=abs, ascending=False)
    # label agreement: billing device_installment events in window (financed only)
    bl = bill[bill.month.isin(win) & (bill.change_reason == "device_installment")].account_id.unique()
    agree = {"purchase_label_pos": int(y.sum()), "billing_label_pos": int(a.account_id.isin(bl).sum()),
             "both": int((a.account_id.isin(bl) & (a.y == 1)).sum())}
    return pd.DataFrame(rows), sf, coef, agree

out, info = [], {}
for cut in [pd.Period("2026-06", "M"), pd.Period("2026-03", "M")]:
    r, sf, coef, agree = run(cut); out.append(r)
    sf.to_csv(f"single_feature_auc_{cut}.csv"); coef.to_csv(f"lr_coefs_{cut}.csv")
    info[str(cut)] = {"label_agreement": agree, "top_single_feature_auc": sf.head(8).round(3).to_dict(), "top_lr_coefs": coef.head(8).round(3).to_dict()}
    print(r.drop(columns=["cutoff"]).to_string(index=False)); print(json.dumps(info[str(cut)], indent=1), flush=True)
pd.concat(out).to_csv("results.csv", index=False); json.dump(info, open("audit.json", "w"), indent=1)
