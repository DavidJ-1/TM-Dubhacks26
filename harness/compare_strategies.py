"""Headline strategy comparison for the presentation. ALL NUMBERS ARE SYNTHETIC / SIMULATED.

Compares, on the 5,042 synthetic sandbox accounts, using ONLY the assumptions already in the
tm-offers EV engine (harness/offers.py CONFIG + sandbox promotions table; nothing new is invented):

  1. Do nothing for anyone
  2. Blanket discount: everyone gets the standard retention credit ($25 care credit, PROMO-STUB-CARE-CREDIT)
  3. Naive rule: $25 care credit to anyone with 3+ support contacts in 90 days ("panic at calls")
  4. Score-only: $25 care credit to the top 10% by Model A churn risk
  5. Ours: Model A + EV engine picks (offers.csv / offer_candidates.csv)

Per strategy: contacted, expected saves (sum p_churn x save_rate), offer cost, cost per save,
net expected value (saved 24-month margin - offer cost - contact/annoyance cost, i.e. the engine's
own EV terms without upsell/lock/benefit), and contacts to low-risk customers (contacted while p_churn < 5%,
the engine's MIN_CREDIT_P_CHURN guardrail). A "truth check" re-scores saves with the hidden simulated
p_true_90d from labels.csv instead of the model's own scores.
Plus churn-model lift from out-of-fold predictions (churn_oof_pred.csv).

Read-only on everything except its outputs; opens sandbox.db read-only (mode=ro) only to recover the
engine's driver flags for the off-eligibility credit baselines.

Run (one command, re-run after offers.csv changes):  python3 harness/compare_strategies.py
Outputs: harness/out/comparison.csv, harness/out/comparison_lift.csv, harness/out/COMPARISON.md,
         demo_data/comparison.csv, demo_data/COMPARISON.md, demo_data/comparison_chart.png
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = Path(os.environ.get("TM_OUT_DIR", HERE / "out"))
DEMO = ROOT / "demo_data"
sys.path.insert(0, str(HERE))

NOTE = "SYNTHETIC/SIMULATED"


def find(name: str) -> Path:
    for d in (OUT, DEMO):
        for n in (name, name + ".gz"):
            if (d / n).exists():
                return d / n
    raise FileNotFoundError(f"{name} not found in {OUT} or {DEMO}")


def load_inputs():
    offers = pd.read_csv(find("offers.csv"))
    cands = pd.read_csv(find("offer_candidates.csv"))
    feats = pd.read_csv(find("features.csv"))
    labels = pd.read_csv(find("labels.csv"))
    oof = pd.read_csv(find("churn_oof_pred.csv"))
    return offers, cands, feats, labels, oof


def engine_care_credit_save_rate(offers: pd.DataFrame, C: dict) -> tuple[pd.Series, str]:
    """Per-account save rate of the $25 care credit as the engine computes it (on/off target + bill-shock boost),
    regardless of eligibility. Uses offers.drivers() on the engine's own facts (sandbox read-only)."""
    import offers as eng  # tm-offers' module; imported read-only, never modified
    det = eng.det
    conn = det.connect_ro()
    facts = det.build_account_facts(conn)
    facts, _ = det.apply_features_csv(facts, find("features.csv"))
    facts, _ = det.apply_enrichment(facts, find("enrichment.csv"))
    df = facts.merge(offers[["account_id", "p_churn_90d"]], on="account_id", how="inner")
    for c in eng.CHURN_COLS:
        if c not in df.columns:
            df[c] = ""
    cs = pd.read_csv(find("churn_scores.csv"))
    rr = [c for c in ("risk_reason_1",) if c in cs.columns]
    if rr:
        df = df.drop(columns=rr, errors="ignore").merge(cs[["account_id"] + rr], on="account_id", how="left")
    sr = C["SAVE_RATE"]["care_credit"]
    relief = C["BILL_SHOCK_RELIEF"]
    out = {}
    for _, row in df.iterrows():
        d = eng.drivers(row)
        r = sr["on_target"] if any(d[k] for k in eng.ON_TARGET["care_credit"]) else sr["off_target"]
        if d["bill_shock_recent"] and relief["enabled"] and C["BILL_SHOCK_RELIEF_OVERRIDE"]:
            r += relief["credit_save_boost"]
        out[row["account_id"]] = r
    return pd.Series(out), "engine drivers() on sandbox facts (read-only)"


def fallback_care_credit_save_rate(feats: pd.DataFrame, C: dict) -> tuple[pd.Series, str]:
    """Used only if the sandbox/engine import is unavailable (fresh clone without vendor data)."""
    sr = C["SAVE_RATE"]["care_credit"]
    f = feats.set_index("account_id")
    pain = ((f["bill_increase_pct"].fillna(0) >= 15) | (f["promo_expired_recent"].fillna(0) > 0)
            | (f["billing_contacts_90d"].fillna(0) > 0) | (f["unresolved_90d"].fillna(0) > 0)
            | (f["network_contacts_90d"].fillna(0) > 0) | (f["negative_contacts_90d"].fillna(0) > 0))
    return pd.Series(np.where(pain, sr["on_target"], sr["off_target"]), index=f.index), \
        "APPROXIMATE fallback from features.csv (engine import unavailable)"


def auc(y, s) -> float:
    y = np.asarray(y); s = pd.Series(np.asarray(s, dtype=float))
    r = s.rank(method="average").values
    npos = y.sum(); nneg = len(y) - npos
    return float((r[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def topk_capture(y, s, frac=0.10, seed=2026) -> float:
    y = np.asarray(y); s = np.asarray(s, dtype=float)
    rng = np.random.default_rng(seed)
    k = int(round(frac * len(y)))
    order = np.lexsort((rng.random(len(y)), -s))  # ties broken randomly
    return float(y[order[:k]].sum() / y.sum())


def main():
    import offers as eng_cfg_mod  # only to read CONFIG; same assumptions as the engine
    C = eng_cfg_mod.CONFIG
    offers, cands, feats, labels, oof = load_inputs()
    low_risk = C["MIN_CREDIT_P_CHURN"]

    base = offers[["account_id", "p_churn_90d", "customer_value_usd", "action_code"]].merge(
        feats[["account_id", "support_90d", "is_persona"]], on="account_id", how="left").merge(
        labels[["account_id", "p_true_90d", "churn_90d"]], on="account_id", how="left")
    base = base.set_index("account_id")
    n = len(base)

    try:
        cc_sr, cc_src = engine_care_credit_save_rate(offers, C)
    except Exception as e:  # noqa: BLE001
        print(f"note: engine driver import failed ({e!r}); using fallback")
        cc_sr, cc_src = fallback_care_credit_save_rate(feats, C)
    base["cc_sr"] = cc_sr.reindex(base.index).fillna(C["SAVE_RATE"]["care_credit"]["off_target"])

    cc_rows = cands[(cands.action_code == "care_credit") & (cands.eligible.astype(str) == "True")]
    care_cost = float(cc_rows.offer_cost.median()) if len(cc_rows) else 25.0
    care_ann = float(C["ANNOYANCE"]["care_credit"])

    p, ptrue, val = base["p_churn_90d"], base["p_true_90d"], base["customer_value_usd"]

    def credit_strategy(name, mask, desc):
        m = mask.astype(bool)
        saves = (p * base.cc_sr)[m].sum()
        saves_t = (ptrue * base.cc_sr)[m].sum()
        sv = (p * base.cc_sr * val)[m].sum()
        sv_t = (ptrue * base.cc_sr * val)[m].sum()
        k = int(m.sum())
        return dict(strategy=name, description=desc, contacted=k, expected_saves=saves,
                    offer_cost_usd=k * care_cost, contact_cost_usd=k * care_ann, saved_margin_usd=sv,
                    contacts_to_low_risk=int((m & (p < low_risk)).sum()),
                    churners_reached=int(base.churn_90d.fillna(0)[m].sum()), credit_spend_usd=k * care_cost,
                    expected_saves_true_p=saves_t, saved_margin_true_p_usd=sv_t,
                    other_ev_usd=0.0)

    rows = [dict(strategy="1. Do nothing", description="no contact, no cost", contacted=0, expected_saves=0.0,
                 offer_cost_usd=0.0, contact_cost_usd=0.0, saved_margin_usd=0.0, contacts_to_low_risk=0,
                 churners_reached=0, credit_spend_usd=0.0, expected_saves_true_p=0.0, saved_margin_true_p_usd=0.0, other_ev_usd=0.0)]
    rows.append(credit_strategy("2. Discount everyone", pd.Series(True, index=base.index),
                                f"${care_cost:.0f} care credit to all {n:,} accounts"))
    rows.append(credit_strategy("3. 3+ support calls rule", base.support_90d.fillna(0) >= 3,
                                f"${care_cost:.0f} care credit if 3+ support contacts in 90 days"))
    k10 = int(round(0.10 * n))
    top = pd.Series(False, index=base.index); top[p.sort_values(ascending=False).index[:k10]] = True
    rows.append(credit_strategy("4. Top 10% risk score only", top,
                                f"${care_cost:.0f} care credit to the top {k10} by Model A risk"))

    ch = cands[cands.is_chosen.astype(str) == "True"].set_index("account_id").reindex(base.index)
    contact = base.action_code != "do_nothing"
    sr = ch["save_rate"].fillna(0)
    other = (ch[["upsell_gain", "customer_benefit", "lock_value"]].fillna(0).sum(axis=1))[contact].sum()
    rows.append(dict(strategy="5. Ours (Model A + EV engine)", description="per-customer pick from offers.csv; "
                     "do nothing allowed to win", contacted=int(contact.sum()),
                     expected_saves=(p * sr)[contact].sum(), offer_cost_usd=ch["offer_cost"].fillna(0)[contact].sum(),
                     contact_cost_usd=ch["annoyance"].fillna(0)[contact].sum(),
                     saved_margin_usd=(p * sr * val)[contact].sum(),
                     contacts_to_low_risk=int((contact & (p < low_risk)).sum()),
                     churners_reached=int(base.churn_90d.fillna(0)[contact].sum()),
                     credit_spend_usd=ch["offer_cost"].fillna(0)[contact & base.action_code.isin(eng_cfg_mod.CREDIT_ACTIONS)].sum()
                     - (contact & (base.action_code == "care_credit_fix_first")).sum() * C["FIX_FIRST_CALLBACK_COST"],
                     expected_saves_true_p=(ptrue * sr)[contact].sum(),
                     saved_margin_true_p_usd=(ptrue * sr * val)[contact].sum(), other_ev_usd=other))
    t = pd.DataFrame(rows)
    t["cost_per_save_usd"] = np.where(t.expected_saves > 0, t.offer_cost_usd / t.expected_saves.replace(0, np.nan), np.nan)
    t["net_value_usd"] = t.saved_margin_usd - t.offer_cost_usd - t.contact_cost_usd
    t["net_value_true_p_usd"] = t.saved_margin_true_p_usd - t.offer_cost_usd - t.contact_cost_usd
    t["cost_per_save_true_p_usd"] = np.where(t.expected_saves_true_p > 0,
                                             t.offer_cost_usd / t.expected_saves_true_p.replace(0, np.nan), np.nan)
    t["contacts_to_low_risk_share"] = np.where(t.contacted > 0, t.contacts_to_low_risk / t.contacted.replace(0, np.nan), np.nan)
    t["data_note"] = NOTE
    t["churners_reached_share"] = t.churners_reached / max(1, int(base.churn_90d.fillna(0).sum()))
    cols = ["strategy", "description", "contacted", "contacts_to_low_risk", "contacts_to_low_risk_share", "credit_spend_usd",
            "churners_reached", "churners_reached_share", "expected_saves", "offer_cost_usd", "cost_per_save_usd",
            "contact_cost_usd", "saved_margin_usd", "net_value_usd",
            "expected_saves_true_p", "cost_per_save_true_p_usd", "net_value_true_p_usd", "other_ev_usd", "data_note"]
    t = t[cols].round(2)

    # ours: contacts by type for the low-risk bucket (most are money-saving moves, not credits)
    ours_low = base[contact & (p < low_risk)].action_code.value_counts()

    # ---- churn model lift (out-of-fold, regular accounts only)
    L = oof.merge(labels[["account_id", "churn_90d", "p_true_90d"]], on="account_id").merge(
        feats[["account_id", "support_90d"]], on="account_id")
    y = L.churn_90d.values
    rule_mask = L.support_90d >= 3
    lift = pd.DataFrame([
        dict(method="Model A (out-of-fold)", auc=auc(y, L.p_churn_90d), top10_capture=topk_capture(y, L.p_churn_90d)),
        dict(method="Support-call count (naive rule)", auc=auc(y, L.support_90d),
             top10_capture=topk_capture(y, L.support_90d)),
        dict(method="Random", auc=0.5, top10_capture=0.10),
        dict(method="Oracle: hidden true probability (ceiling)", auc=auc(y, L.p_true_90d),
             top10_capture=topk_capture(y, L.p_true_90d)),
    ])
    lift["top10_lift_x"] = lift.top10_capture / 0.10
    lift["data_note"] = NOTE
    lift = lift.round(3)
    rule_info = dict(n=int(rule_mask.sum()), share=rule_mask.mean(), cap=y[rule_mask].sum() / y.sum())
    n_ch, n_reg = int(y.sum()), len(y)

    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / "comparison.csv", index=False)
    lift.to_csv(OUT / "comparison_lift.csv", index=False)

    # ---- markdown
    def money(x):
        return "n/a" if pd.isna(x) else (f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}")
    r = t.set_index("strategy")
    ours, blanket, rule, score = (r.loc["5. Ours (Model A + EV engine)"], r.loc["2. Discount everyone"],
                                  r.loc["3. 3+ support calls rule"], r.loc["4. Top 10% risk score only"])
    ccs = C["SAVE_RATE"]["care_credit"]; ff = C["SAVE_RATE"]["fix_first"]
    sr_txt = (f"{ccs['on_target']:.0%} if billing/service pain else {ccs['off_target']:.0%} "
              f"(+{C['BILL_SHOCK_RELIEF']['credit_save_boost']*100:.0f} pts after bill shock); ours also uses fix-first "
              f"{ff['on_target']:.0%}/{ff['off_target']:.0%}, right-size/variant {C['SAVE_RATE']['right_size']['on_target']:.0%}/"
              f"{C['SAVE_RATE']['right_size']['off_target']:.0%}, check-in {C['SAVE_RATE']['check_in']['on_target']:.0%}/"
              f"{C['SAVE_RATE']['check_in']['off_target']:.0%} (on/off target); value = 24 mo x 50% margin")
    cheaper = 1 - ours.cost_per_save_usd / blanket.cost_per_save_usd
    n_churn = int(base.churn_90d.fillna(0).sum())
    headline = [
        f"Ours makes {int(ours.contacts_to_low_risk):,} contacts to low-risk customers (no credits: fix-first callbacks, "
        f"money-saving plan moves, check-ins and usage-based upsells) vs {int(blanket.contacts_to_low_risk):,} for discounting everyone and "
        f"{int(rule.contacts_to_low_risk):,} for the 3+ calls rule, and spends {money(ours.credit_spend_usd)} on credits vs "
        f"{money(blanket.credit_spend_usd)} for discounting everyone.",
        f"Ours reaches {int(ours.churners_reached)} of the {n_churn} customers who actually churned in the simulation "
        f"({ours.churners_reached_share:.0%}) with {int(ours.contacted):,} contacts; the 3+ calls rule reaches "
        f"{int(rule.churners_reached)} with {int(rule.contacted):,}, score-only {int(score.churners_reached)} with {int(score.contacted)}.",
        f"Depends on assumed save rates: ~{ours.expected_saves:.0f} expected saves at {money(ours.cost_per_save_usd)} per save, "
        f"{cheaper:.0%} cheaper per save than a $25 credit to everyone, net {money(ours.net_value_usd)} vs "
        f"{money(blanket.net_value_usd)}.",
        f"Model A puts {lift.loc[0,'top10_capture']:.0%} of actual churners in its top 10% (out-of-fold), vs "
        f"{lift.loc[1,'top10_capture']:.0%} for ranking by support calls and 10% at random "
        f"(AUC {lift.loc[0,'auc']:.2f} vs {lift.loc[1,'auc']:.2f}).",
    ]
    md = [f"# Same assumptions, different strategies (simulated)", "",
          "**All customers and numbers are synthetic/simulated. We don't claim real lift until a holdout test.**", "",
          "## Headline", ""] + [f"- {h}" for h in headline] + [
          "", f"## 1. Assumption-free metrics ({n:,} synthetic accounts)", "",
          f"These depend only on who each strategy contacts: no assumed save rates. Low risk = Model A risk < "
          f"{low_risk:.0%}. Churners reached = contacted accounts that churned in the simulated labels ({n_churn} total).", "",
          "| strategy | contacted | contacts to low-risk customers (risk < 5%) | credit / discount spend | actual churners reached |",
          "|---|---:|---:|---:|---:|"]
    for _, x in t.iterrows():
        md.append(f"| {x.strategy} | {x.contacted:,} | {x.contacts_to_low_risk:,} ({0 if pd.isna(x.contacts_to_low_risk_share) else x.contacts_to_low_risk_share:.0%}) | "
                  f"{money(x.credit_spend_usd)} | {x.churners_reached} ({x.churners_reached_share:.0%}) |")
    md += ["", "## 2. Simulated value (depends on assumed save rates)", "",
           f"Assumed save rates (engine CONFIG, illustrative): $25 care credit {sr_txt}. Same for every strategy.", "",
           "| strategy | expected saves | offer cost | cost per save | net expected value |",
           "|---|---:|---:|---:|---:|"]
    for _, x in t.iterrows():
        md.append(f"| {x.strategy} | {x.expected_saves:.1f} | {money(x.offer_cost_usd)} | "
                  f"{money(x.cost_per_save_usd)} | {money(x.net_value_usd)} |")
    md += ["", "### Truth check (still depends on assumed save rates): same picks, saves re-scored with the hidden simulated churn probability", "",
           "| strategy | expected saves (true p) | cost per save (true p) | net value (true p) |", "|---|---:|---:|---:|"]
    for _, x in t.iterrows():
        md.append(f"| {x.strategy} | {x.expected_saves_true_p:.1f} | {money(x.cost_per_save_true_p_usd)} | "
                  f"{money(x.net_value_true_p_usd)} |")
    md += ["", f"Ours also carries {money(ours.other_ev_usd)} of non-retention EV (upsell margin, lock-in value and "
           "customer-savings trust value) that is **not** included in net value above, to keep the comparison "
           "like-for-like.", "",
           f"Ours' {int(ours.contacts_to_low_risk)} low-risk contacts by action: " +
           ", ".join(f"{k} {v}" for k, v in ours_low.items()) + ". None are credits (the engine blocks credits below 5% risk); "
           "upsells (step_up/family_upgrade/home_internet_bundle) are the ones a judge could question.", "",
           "## Churn model lift (out-of-fold, 5-fold CV)", "",
           f"{n_reg:,} regular accounts, {n_ch} actual churners in 90 days (base rate {n_ch/n_reg:.1%}).", "",
           "| method | AUC | share of churners in top 10% | lift |", "|---|---:|---:|---:|"]
    for _, x in lift.iterrows():
        md.append(f"| {x.method} | {x.auc:.3f} | {x.top10_capture:.0%} | {x.top10_lift_x:.1f}x |")
    md += ["", f"The literal 3+ calls rule flags {rule_info['n']:,} accounts ({rule_info['share']:.0%}) and catches "
           f"{rule_info['cap']:.0%} of churners. Existing holdout backtest (harness/out/backtest_churn_churn_90d.md) "
           "agrees: model_a CV top-10% recall 60.6% vs 26.2% for rule_support3.", "",
           "## How it's computed", "",
           "- Expected saves = sum over contacted accounts of p_churn_90d (Model A) x save rate. Save value = that x "
           "customer value (24 months x 50% service margin), exactly as in the engine.",
           f"- Credit baselines (2-4) give the ${care_cost:.0f} care credit regardless of eligibility, with the engine's "
           f"care-credit save rate per account (25% on target for billing/service pain, 5% off target, +5 pts after "
           f"bill shock) and ${care_ann:.0f} contact/annoyance cost. Save-rate source: {cc_src}.",
           "- Ours uses the chosen row in offer_candidates.csv (save rate, offer cost, annoyance) for each account.",
           "- Net value = saved margin - offer cost - contact/annoyance cost.",
           "- Contact to a low-risk customer = contacted while Model A risk < 5% (the engine's MIN_CREDIT_P_CHURN).",
           "", "## Caveats", "",
           "- We don't claim real lift until a holdout test. Synthetic data; save rates and costs are made-up but consistent across strategies.",
           "- Ours' offer cost includes expected revenue given back on plan moves (right-size/variant) and $15 callbacks; credit spend counts only bill credits.",
           "- Churners reached is in-sample for strategies 4-5 (Model A was fit on these labels); the out-of-fold lift table below is the honest model comparison.",
           "- Partly circular: ours is scored with the same assumptions it optimizes. The truth-check table and "
           "harness/out/policy_eval.csv (simulated 50k randomized trial) are the less-circular views.",
           "- Model A scores are in-sample for the strategy table; lift uses out-of-fold scores.",
           "", f"Source: offers.csv rows {len(offers):,}; regenerate with `python3 harness/compare_strategies.py`."]
    pe = OUT / "policy_eval.csv"
    if pe.exists():
        P = pd.read_csv(pe)
        md += ["", "## Cross-check: simulated 50k randomized trial (tm-offers' policy_eval.csv, test split, DR estimate)", "",
               "| policy | contacted | churners saved | offer cost | cost per save | net value (no upsell) |",
               "|---|---:|---:|---:|---:|---:|"]
        for _, x in P.iterrows():
            md.append(f"| {x.policy} | {int(x.n_contacted):,} | {x.churners_saved_dr:.1f} | {money(x.offer_cost_usd)} | "
                      f"{money(x.cost_per_save_dr_usd)} | {money(x.net_value_no_upsell_dr_usd)} |")
    (OUT / "COMPARISON.md").write_text("\n".join(md) + "\n")

    chart(t, sr_txt)
    DEMO.mkdir(exist_ok=True)
    for f in ("comparison.csv", "COMPARISON.md", "comparison_lift.csv"):
        shutil.copy(OUT / f, DEMO / f)
    print("\n".join(headline))
    print(t[["strategy", "contacted", "contacts_to_low_risk", "credit_spend_usd", "churners_reached", "expected_saves", "offer_cost_usd", "cost_per_save_usd", "net_value_usd"]].to_string(index=False))
    print(lift.to_string(index=False))
    print(f"wrote {OUT/'comparison.csv'}, {OUT/'COMPARISON.md'}, {DEMO/'comparison_chart.png'}. ALL NUMBERS SYNTHETIC.")


def chart(t: pd.DataFrame, sr_txt: str):
    import textwrap
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = t[t.contacted > 0].copy()
    labels = [s.split(". ", 1)[1].replace(" (Model A + EV engine)", "") for s in d.strategy]
    y = np.arange(len(d))
    pink, grey, dark = "#E20074", "#9AA0A6", "#555555"
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.6))
    h = 0.38
    b1 = a1.barh(y - h / 2, d.churners_reached, h, color=pink, label="actual churners reached")
    b2 = a1.barh(y + h / 2, d.contacts_to_low_risk, h, color=grey, label="contacts to low-risk customers (risk < 5%)")
    for bars, vals in ((b1, d.churners_reached), (b2, d.contacts_to_low_risk)):
        for b, v in zip(bars, vals):
            a1.text(v, b.get_y() + b.get_height() / 2, f" {int(v):,}", va="center", fontsize=9)
    a1.set_xscale("symlog", linthresh=100)
    a1.set_xlim(0, max(d.contacts_to_low_risk.max(), d.churners_reached.max()) * 4)
    a1.set_yticks(y, [f"{l}\ncredit spend \\${sp:,.0f}" for l, sp in zip(labels, d.credit_spend_usd)], fontsize=9)
    a1.invert_yaxis()
    a1.set_title("Assumption-free: who gets contacted", fontsize=12, weight="bold")
    a1.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=8, frameon=False)
    a1.set_xlabel("accounts (log scale)", fontsize=9)
    v = d.net_value_usd.values
    cols = [pink if s.startswith("5.") else grey for s in d.strategy]
    bars = a2.barh(y, v, 0.6, color=cols)
    a2.invert_yaxis(); a2.axvline(0, color="#333", lw=0.8); a2.set_yticks(y, [""] * len(y))
    for b, x, cps in zip(bars, v, d.cost_per_save_usd):
        s = f"-\\${-x:,.0f}" if x < 0 else f"\\${x:,.0f}"
        a2.text(x, b.get_y() + b.get_height() / 2, f" {s}  (\\${cps:,.0f}/save) ", va="center",
                ha="left" if x >= 0 else "right", fontsize=9)
    lo, hi = min(0, v.min()), max(0, v.max())
    a2.set_xlim(lo - (hi - lo) * 0.45 * (lo < 0), hi + (hi - lo) * 0.6)
    a2.set_title("Simulated net value (depends on assumed save rates)", fontsize=12, weight="bold")
    a2.tick_params(axis="x", labelsize=8)
    for ax in (a1, a2):
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Same assumptions, different strategies (simulated) - 5,042 synthetic accounts", fontsize=13)
    foot = ("Assumed save rates: \\$25 care credit " + sr_txt + ". We don't claim real lift until a holdout test.")
    fig.text(0.5, 0.012, "\n".join(textwrap.wrap(foot, 170)), ha="center", fontsize=8, color=dark)
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    DEMO.mkdir(exist_ok=True)
    fig.savefig(DEMO / "comparison_chart.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
