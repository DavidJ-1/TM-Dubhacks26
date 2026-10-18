"""Public-dataset sanity check of our SYNTHETIC churn-label drivers -> harness/out/validation.md

Compares driver direction and strength in public churn datasets (IBM Telco, Cell2Cell, Orange/Larose,
KDD Cup 2009 Orange, Orange Belgium uplift) against our synthetic label recipes (labels.py tuned + doc)
and the judge sandbox's toy formula (toy_p).
Raw data lives OUTSIDE the repo ($RAW_DIR, default <repo>/../raw). Never commit it (licenses below).
Run: python harness/validate_public.py   (needs pandas, numpy, scikit-learn; run features.py first)

Methods
- Univariate ratio: churn rate in top vs bottom group (binary: 1 vs 0; continuous: rank quartile Q4 vs Q1).
  For our data, the "churn rate" is the mean SYNTHETIC p_true_90d (or toy_p), i.e. the expected rate.
- Standardized multivariate effect: public data -> sklearn LogisticRegression on z-scored mapped features
  (log-odds per +1 SD). Ours/toy -> OLS of logit(monthly_hazard) / logit(toy_p) on the same z-scored
  representative features (the labels are deterministic functions of features, so this recovers the
  implied per-SD log-odds effect). Different outcomes and horizons: compare sign and rough size, not decimals.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
RAW = Path(os.environ.get("RAW_DIR", HERE.parent.parent / "raw"))
OUT = HERE / "out" / "validation.md"
PY = sys.executable

# concept -> human label, expected direction for "more of X" (+ = more churn)
CONCEPTS = {
    "support_calls": "Support / care calls",
    "tenure": "Tenure (longer)",
    "lock_in": "Contract / financing lock-in",
    "device_age": "Equipment / device age (older)",
    "bill_increase": "Bill increase (% change)",
    "charges": "Bill level / monthly charges",
    "autopay": "AutoPay / automatic payment",
    "retention_calls": "Retention / cancel-intent calls",
    "lines": "More lines / subscribers",
    "network": "Network problems (dropped calls / network contacts)",
    "engagement": "Engagement / usage trend (more)",
}

LICENSES = {
    "IBM Telco": "Apache-2.0 per IBM's GitHub repo (fictional IBM sample data). Commercial use OK with attribution.",
    "Cell2Cell": "No explicit license (Duke Teradata Center data via Kaggle/GitHub mirror). Treat as research/demo only.",
    "Orange (Larose)": "No explicit license (classic Larose / MLC++ 'churn' set via a GitHub mirror). Treat as research/demo only.",
    "KDD Cup 2009 Orange": "Free for research use per KDD Cup 2009 terms. Research only.",
    "Orange Belgium uplift": "CC BY-NC-ND (OpenML 45580). Non-commercial, no derivatives. Research only.",
}


# ---------------------------------------------------------------- loaders -> (df of concept columns, y, meta)
def load_telco():
    d = pd.read_csv(RAW / "telco.csv")
    y = (d["Churn"] == "Yes").astype(int)
    X = pd.DataFrame({
        "tenure": d["tenure"].astype(float),
        "lock_in": (d["Contract"] != "Month-to-month").astype(float),
        "charges": d["MonthlyCharges"].astype(float),
        "autopay": d["PaymentMethod"].str.contains("automatic").astype(float),
        "lines": (d["MultipleLines"] == "Yes").astype(float),
    })
    return X, y, {"rows": len(d), "horizon": "'left within the last month' (IBM sample; single snapshot)",
                  "unit": "customer (fictional)", "notes": "No support-call, device or bill-change fields. "
                  "'lines' = MultipleLines=Yes. Contract = lock-in proxy for our financing."}


def load_cell2cell():
    d = pd.read_csv(RAW / "cell2celltrain.csv")
    y = (d["Churn"] == "Yes").astype(int)
    X = pd.DataFrame({
        "support_calls": d["CustomerCareCalls"],
        "tenure": d["MonthsInService"],
        "device_age": d["CurrentEquipmentDays"] / 30.4,
        "bill_increase": d["PercChangeRevenues"],
        "charges": d["MonthlyRevenue"],
        "retention_calls": d["RetentionCalls"],
        "lines": d["UniqueSubs"],
        "network": d["DroppedCalls"],
        "engagement": d["PercChangeMinutes"],
    }).astype(float)
    keep = X.notna().all(axis=1)
    return X[keep], y[keep], {"rows": int(keep.sum()), "horizon": "churned within ~60 days after the "
                              "observation month (Duke/Teradata 2002 tournament; churners OVERSAMPLED to ~50/50 "
                              "in the calibration sample, ~29% in this train file; real monthly rate ~1.8-2%)",
                              "unit": "subscriber (real, anonymized US carrier, ~1998-2001)",
                              "notes": f"Dropped {int((~keep).sum())} rows with missing values. "
                              "bill_increase = PercChangeRevenues (% change in revenue); "
                              "engagement = PercChangeMinutes. No lock-in or AutoPay field."}


def load_orange():
    d = pd.read_csv(RAW / "orange_churn.csv")
    y = d["Churn?"].astype(str).str.startswith("True").astype(int)
    charge = d[["Day Charge", "Eve Charge", "Night Charge", "Intl Charge"]].sum(axis=1)
    X = pd.DataFrame({
        "support_calls": d["CustServ Calls"].astype(float),
        "tenure": d["Account Length"].astype(float),
        "charges": charge,
        "engagement": (d["Day Mins"] + d["Eve Mins"] + d["Night Mins"]).astype(float),
    })
    return X, y, {"rows": len(d), "horizon": "unstated (snapshot label; source does not give a window)",
                  "unit": "account (US telco, origin unclear)", "notes": "engagement = total minutes (a level, "
                  "not a trend). charges = total usage charge. Account Length units are unstated (assumed days)."}


def load_kdd():
    d = pd.read_csv(RAW / "orange_small_train.data", sep="\t")
    y = (pd.read_csv(RAW / "orange_small_train_churn.labels", header=None)[0] == 1).astype(int)
    # anonymized: no concept mapping; report base rate + best single-variable AUC for context
    num = d.select_dtypes("number")
    num = num.loc[:, num.notna().mean() > 0.5]
    aucs = {}
    for c in num.columns:
        v = num[c].fillna(num[c].median())
        if v.nunique() > 1:
            a = roc_auc_score(y, v)
            aucs[c] = max(a, 1 - a)
    top = sorted(aucs.items(), key=lambda kv: -kv[1])[:3]
    return None, y, {"rows": len(d), "horizon": "unstated (Orange France, 2009; label = churn flag)",
                     "unit": "customer (real, French carrier, 230 anonymized vars)",
                     "notes": "All 230 variables are anonymized (Var1..Var230), so drivers can't be mapped "
                     "to ours. Best single numeric vars (AUC, either direction): "
                     + ", ".join(f"{k} {v:.3f}" for k, v in top)}


def load_belgium():
    path = RAW / "orange_belgium_churn_uplift_openml45580.arff"
    with open(path) as fh:
        cols = []
        for line in fh:
            if line.upper().startswith("@ATTRIBUTE"):
                cols.append(line.split()[1])
            if line.upper().startswith("@DATA"):
                break
        d = pd.read_csv(fh, header=None, names=cols, usecols=["y", "t"])
    y = d["y"].astype(int)
    rc, rt = y[d["t"] == 0].mean(), y[d["t"] == 1].mean()
    return None, y, {"rows": len(d), "horizon": "unstated in OpenML metadata (retention campaign follow-up)",
                     "unit": "customer (real, Orange Belgium RCT)", "notes": f"Features are PCA components, "
                     f"so drivers can't be mapped. Control churn {rc:.2%} (n={int((d['t'] == 0).sum())}), "
                     f"treated {rt:.2%} (n={int((d['t'] == 1).sum())}), uplift {rc - rt:+.2%}. "
                     "This is the only real telco retention RCT found: it argues for modest save rates in Model B."}


DATASETS = [("IBM Telco", load_telco), ("Cell2Cell", load_cell2cell), ("Orange (Larose)", load_orange),
            ("KDD Cup 2009 Orange", load_kdd), ("Orange Belgium uplift", load_belgium)]


# ---------------------------------------------------------------- stats
def uni_ratio(x: pd.Series, rate: pd.Series) -> float:
    """Top vs bottom group mean of `rate` (0/1 churn or expected probability)."""
    x = x.astype(float)
    if x.nunique() <= 2:
        hi, lo = rate[x == x.max()], rate[x == x.min()]
    else:
        q = pd.qcut(x.rank(method="first"), 4, labels=False)
        hi, lo = rate[q == 3], rate[q == 0]
    return float(hi.mean() / lo.mean()) if lo.mean() > 0 else float("nan")


def std_logit(X: pd.DataFrame, y: pd.Series) -> pd.Series:
    Z = StandardScaler().fit_transform(X.values)
    m = LogisticRegression(max_iter=5000, C=1e6).fit(Z, y.values)
    return pd.Series(m.coef_[0], index=X.columns)


def std_ols(X: pd.DataFrame, target: np.ndarray) -> pd.Series:
    Z = StandardScaler().fit_transform(X.values)
    return pd.Series(LinearRegression().fit(Z, target).coef_, index=X.columns)


def our_concepts(f: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "support_calls": f["support_90d"],
        "tenure": f["tenure_months"],
        "lock_in": (f["n_financed_lines"] > 0).astype(float),
        "device_age": f["max_device_age_months"].fillna(0),
        "bill_increase": f["bill_increase_pct"],
        "charges": f["last_bill_cents"],
        "autopay": f["autopay"],
        "retention_calls": f["cancel_inquiries_270d"],
        "lines": f["n_lines"],
        "network": f["network_contacts_90d"],
        "engagement": f["app_sessions_30d"],
    }).astype(float)


def run_labels(recipe: str) -> pd.DataFrame:
    """Run labels.py for a recipe, read the result, and restore the default (tuned) output afterwards."""
    subprocess.run([PY, str(HERE / "labels.py"), "--recipe", recipe], check=True, capture_output=True)
    return pd.read_csv(HERE / "out" / "labels.csv")


def logit(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


# ---------------------------------------------------------------- main
def main():
    f = pd.read_csv(HERE / "out" / "features.csv")
    lab_doc = run_labels("doc")
    lab_tuned = run_labels("tuned")  # leaves out/labels.csv as the default tuned output
    reg = (f["is_persona"] == 0).values
    C = our_concepts(f)[reg].reset_index(drop=True)
    ours = {
        "ours tuned (synthetic)": (lab_tuned.loc[reg, "monthly_hazard"].values, lab_tuned.loc[reg, "p_true_90d"]),
        "ours doc (synthetic)": (lab_doc.loc[reg, "monthly_hazard"].values, lab_doc.loc[reg, "p_true_90d"]),
        "sandbox toy_p": (lab_tuned.loc[reg, "toy_p"].values, lab_tuned.loc[reg, "toy_p"]),
    }
    std, uni, meta, rates = {}, {}, {}, {}
    for name, loader in DATASETS:
        try:
            X, y, m = loader()
        except FileNotFoundError as e:
            meta[name] = {"skipped": f"file missing: {e.filename}"}
            continue
        meta[name] = m
        rates[name] = float(y.mean())
        if X is not None:
            X, y = X.reset_index(drop=True), y.reset_index(drop=True)
            std[name] = std_logit(X, y)
            uni[name] = pd.Series({c: uni_ratio(X[c], y) for c in X.columns})
    for name, (h, p) in ours.items():
        std[name] = std_ols(C, logit(h))
        uni[name] = pd.Series({c: uni_ratio(C[c], p.reset_index(drop=True)) for c in C.columns})
    S, U = pd.DataFrame(std).reindex(CONCEPTS), pd.DataFrame(uni).reindex(CONCEPTS)
    # upgrade target (synthetic): implied per-SD effects + univariate ratios, for context only
    pu = lab_tuned.loc[reg, "p_upgrade_90d"].reset_index(drop=True)
    UP = pd.DataFrame({"upgrade std effect (synthetic)": std_ols(C, logit(pu.values)),
                       "upgrade ratio Q4/Q1 (synthetic)": pd.Series({c: uni_ratio(C[c], pu) for c in C.columns})}
                      ).reindex(CONCEPTS)
    public = [n for n, _ in DATASETS if n in std]
    ourcols = list(ours)

    # flags
    flags = []
    for c in CONCEPTS:
        pub = S.loc[c, public].dropna()
        if pub.empty:
            continue
        pub_sign = np.sign(pub)
        consensus = np.sign(pub.median()) if (pub_sign == pub_sign.iloc[0]).all() else 0
        pub_mag = pub.abs().median()
        for o in ourcols:
            v = S.loc[c, o]
            if consensus != 0 and abs(v) > 0.02 and np.sign(v) != consensus:
                flags.append(f"DIRECTION: **{CONCEPTS[c]}**: {o} {v:+.2f} vs public {', '.join(f'{k} {x:+.2f}' for k, x in pub.items())}")
            elif consensus != 0 and pub_mag > 0.05 and abs(v) > 0 and (abs(v) / pub_mag > 3 or abs(v) / pub_mag < 1 / 3):
                flags.append(f"STRENGTH (>3x gap): **{CONCEPTS[c]}**: {o} |{v:.2f}| vs public median |{pub_mag:.2f}|")
            elif consensus != 0 and abs(v) <= 0.02 and pub_mag > 0.05:
                flags.append(f"ABSENT: **{CONCEPTS[c]}**: {o} has ~0 effect; public median {pub.median():+.2f}")
        if consensus == 0:
            flags.append(f"PUBLIC DISAGREE: **{CONCEPTS[c]}**: public signs differ ({', '.join(f'{k} {x:+.2f}' for k, x in pub.items())})")

    def table(df, fmt):
        cols = public + ourcols
        h = "| driver | " + " | ".join(cols) + " |\n|---|" + "---|" * len(cols) + "\n"
        for c in CONCEPTS:
            h += f"| {CONCEPTS[c]} | " + " | ".join("–" if pd.isna(df.loc[c, k]) else fmt.format(df.loc[c, k]) for k in cols) + " |\n"
        return h

    r_t, r_d = lab_tuned.loc[reg], lab_doc.loc[reg]
    md = ["# Public-dataset validation of churn drivers",
          "", "> **Our numbers are SYNTHETIC.** Our labels (`labels.py`) and the sandbox toy formula are invented. "
          "This file checks whether the *direction and rough strength* of their drivers resemble what public "
          "churn data shows. It does not measure accuracy. Public data is kept outside the repo in `" + str(RAW) + "` and is never committed.",
          "", "Regenerate: `python harness/validate_public.py` (it runs `labels.py --recipe doc` and then `--recipe tuned`, so `out/labels.csv` ends up as the default tuned output).",
          "", "## Datasets", "", "| dataset | rows | churn rate | horizon / unit | license | notes |", "|---|---|---|---|---|---|"]
    for name, _ in DATASETS:
        m = meta.get(name, {})
        if "skipped" in m:
            md.append(f"| {name} | – | – | – | {LICENSES[name]} | SKIPPED: {m['skipped']} |")
        else:
            md.append(f"| {name} | {m['rows']:,} | {rates[name]:.2%} | {m['horizon']}; {m['unit']} | {LICENSES[name]} | {m['notes']} |")
    md += [f"| ours tuned (synthetic) | 5,000 | {r_t.p_true_90d.mean():.2%} expected per 90 days ({r_t.churn_90d.mean():.2%} drawn); mean monthly hazard {r_t.monthly_hazard.mean():.3%} | 90 days | n/a | calibrated to TMUS Q2 2026 postpaid account churn of 0.99%/month |",
           f"| ours doc (synthetic) | 5,000 | {r_d.p_true_90d.mean():.2%} expected per 90 days ({r_d.churn_90d.mean():.2%} drawn) | 90 days | n/a | plan-doc recipe as written |",
           f"| sandbox toy_p | 5,000 | {r_t.toy_p.mean():.2%} expected per 90 days | 90 days | sandbox repo | public toy formula, ≈5%/month (unrealistic) |",
           "", "## Standardized effect (log-odds per +1 SD; multivariate within each column)",
           "Public columns: logistic regression on churn. Our columns: OLS of logit(monthly hazard) (toy: logit(toy_p)) on the same z-scored representative features. "
           "Our features: support_90d, tenure_months, any financed line, max device age, bill_increase_pct, last bill, autopay, cancel_inquiries_270d, n_lines, network_contacts_90d, app_sessions_30d (engagement). "
           "The tuned recipe's unresolved/negative-contact terms load mainly onto support_calls here.", "",
           table(S, "{:+.2f}"),
           "## Univariate churn-rate ratio (top vs bottom group)",
           "Binary features: rate(1) / rate(0). Continuous features: Q4 / Q1 by rank. Our columns use mean expected probability (synthetic).", "",
           table(U, "{:.2f}x"),
           "## Flags (direction mismatches, >3x strength gaps, missing effects)",
           "Rule: sign differs from a unanimous public sign, or |ours| is more than 3x or less than 1/3 of the public median |effect|.", ""]
    md += [f"- {x}" for x in flags] or ["- none"]
    md += ["", "## Reading the flags (interpretation, written against the 2026-10-17 run)",
           "- **Care calls:** Larose agrees strongly with us (+0.58 per SD; 4+ calls ≈ 46-64% churn). Cell2Cell is slightly *negative* (-0.07 multivariate, 0.79x univariate), probably because care calls track overall usage and heavy users churn less there. The sign question is open, not settled against us. Our ~x10 univariate ratio is far steeper than any public set (x0.8 to x1.9). That's partly by design: the sandbox's hidden 'unhappiness' drives support contacts.",
           "- **Tenure:** Telco shows a strong negative (-0.91; x0.16), matching us in sign; ours is much weaker. Cell2Cell's univariate ratio is >1 (churn peaks around contract-end months), and Larose is flat. Our weak tenure effect sits between them.",
           "- **Lock-in:** Telco contracts cut churn sharply (-0.63; x0.16). Our financing effect points the same way but is about 6x weaker. If David wants 'locked in' to matter more (persona 27), raise `no_financing` (currently 0.6 doc-scale). The toy formula has no lock-in term at all.",
           "- **Device age:** Cell2Cell older equipment +0.29 (x1.5). Ours (+0.07) is the same direction but weak. The toy formula is slightly negative: it has no device term, and the -0.04 comes from correlated fields.",
           "- **Bill level:** public charges are strongly positive in Telco and Larose (+0.8), but those reflect service type and usage minutes, not a price for the same service. We use bill *change*, not level. This is a deliberate gap and the main candidate if a 'pays a lot' driver is wanted.",
           "- **Lines:** public data shows slightly more churn with more lines/subs (+0.09 to +0.13); ours is negative (-0.15 per extra line, from the plan doc). This is a real direction mismatch. Industry lore holds that multi-line accounts are stickier, but these datasets don't show it.",
           "- **Engagement:** matches (more usage, less churn) in Cell2Cell and our recipes.",
           ]
    md += ["", "## Upgrade target (`upgrade_90d`, synthetic): what public data can and can't say",
           "None of these public datasets has an upgrade or plan step-up outcome, so the upgrade recipe **can't be validated on public data**. "
           "The only indirect check: older equipment raises churn in Cell2Cell (see device_age above), which matches treating an old phone as a 'moment' where the customer will either upgrade or leave. "
           "Our upgrade label's implied per-SD effects on the same representative features (context only):", "",
           "| driver | upgrade std effect (synthetic) | upgrade ratio Q4/Q1 (synthetic) |", "|---|---|---|"]
    md += [f"| {CONCEPTS[c]} | {UP.iloc[i, 0]:+.2f} | {UP.iloc[i, 1]:.2f}x |" for i, c in enumerate(CONCEPTS)]
    md += ["", "Plan headroom, cap use and student status drive the upgrade label but are not among these representative features (see DATA_README). Public anchor for the 6%/90d rate: Verizon's postpaid phone upgrade rate of 2.6%/quarter (carrier KPI, not a dataset).",
           "", "## What this does and doesn't validate",
           "- **Does:** checks that our invented drivers point the same way as real or realistic churn data for the concepts that map: care calls up, tenure down, lock-in down, older equipment up, and so on. It also gives a rough sense of whether any single driver is wildly over- or under-weighted.",
           "- **Doesn't:** prove our labels or model are accurate for T-Mobile. Every public set is a different carrier, era (1998-2009 for the real ones), population and horizon. Two are fictional (IBM Telco) or of unclear origin (Larose). Cell2Cell oversamples churners. Field definitions only roughly match ours (Telco contract vs our device financing; Cell2Cell revenue change vs our bill change). Standardized effects depend on each dataset's feature spread and outcome base rate, so only sign and rough size are meaningful.",
           "- Our label coefficients are judgement calls, and the sandbox's own data was generated with these patterns built in (a hidden 'unhappiness' variable drives support, sentiment, competitor score and so on). Agreement here means our assumptions are plausible, not that they're true.",
           "- Anonymized and PCA datasets (KDD 2009, Orange Belgium) give base rates and RCT context only, no driver checks. Orange Belgium's small treated-vs-control churn gap supports conservative save rates in Model B.",
           "- Competitor research score, port-out inquiry, sentiment and promo-expiry (key drivers in our recipe) have **no public counterpart** in these datasets and remain unvalidated.",
           ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(md) + "\n")
    print(f"wrote {OUT}")
    print(S.round(2).to_string())
    print("\n".join(flags))


if __name__ == "__main__":
    main()
