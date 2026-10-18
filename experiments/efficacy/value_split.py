"""Value split for the strategy chart: business net vs customer savings vs margin given up on purpose.
ALL NUMBERS SYNTHETIC / SIMULATED (synthetic accounts, simulated labels, assumed save and accept rates).

Three bars per policy (dollars, expected):
  business_net    company dollars, the same definition as the dev strategy chart (harness/compare_strategies.py):
                  saved 24-month margin - offer cost - contact cost. Upsell margin and "trust value" are NOT counted.
  customer_savings dollars customers keep: bill credits + 12 months of lower plan price x P(accept).
  margin_given_up revenue the company forgoes ON PURPOSE by moving customers to cheaper plans
                  (right-size, same-plan variant), 12 months x P(accept). NOTE: the dev chart's offer cost already
                  charges only (1 - CUSTOMER_BENEFIT_WEIGHT) = 50% of this, so business_net is not fully company-dollar.
Primary source: tm-models' file (env TM_POLICY_BY_SAVE_RATE, default ../scratch_models/chart_check/
policy_by_save_rate.csv, schema: policy, decide_save_rate, true_save_rate, contacts, business_net,
customer_savings, margin_given_up, notes). If it is missing, the rows below are our own CROSS-CHECK, rebuilt from
the engine outputs (offers.csv + offer_candidates.csv.gz; --engine-dir to point at another engine run).

"Save rate" = share of reached would-be churners an offer saves. The engine's assumptions give about 44% for "Ours"
(42.6 expected saves / 96 churners reached). Field anchors: 5-15% (a 1.9-point cut from 17.2%, about 11% relative,
Marketing Science 2018; 3.6% -> 3.4%, about 6% relative, Verhelst et al. 2023). Picks stay fixed (decided at the
assumed rates); only the realized save rate changes, so saved margin scales linearly and costs do not.
Run: python experiments/efficacy/value_split.py [--engine-dir demo_data]
"""
from __future__ import annotations
import argparse, os, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "harness"))
TM_FILE = Path(os.environ.get("TM_POLICY_BY_SAVE_RATE", ROOT.parent / "scratch_models" / "chart_check" / "policy_by_save_rate.csv"))
SCHEMA = ["policy", "decide_save_rate", "true_save_rate", "contacts", "business_net", "customer_savings",
          "margin_given_up", "notes"]
RATES = [0.44, 0.22, 0.15, 0.10, 0.05]  # first entry is replaced by the exact assumed rate (scale 1.0)
CUSTOMER_FIRST = ("right_size", "variant_switch")
UPSELL = ("step_up", "family_upgrade", "device_upgrade", "home_internet_bundle")
NOTE = "SYNTHETIC; cross-check rebuilt from engine outputs"


def load(engine_dir: Path):
    import offers as eng
    C = eng.CONFIG
    off = pd.read_csv(engine_dir / "offers.csv")
    cand = pd.read_csv(engine_dir / "offer_candidates.csv.gz") if (engine_dir / "offer_candidates.csv.gz").exists() \
        else pd.read_csv(engine_dir / "offer_candidates.csv")
    feats = pd.read_csv(ROOT / "demo_data" / "features.csv")[["account_id", "support_90d"]]
    lab = pd.read_csv(ROOT / "demo_data" / "labels.csv")[["account_id", "churn_90d"]]
    return C, off, cand, feats, lab


def build(engine_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    C, off, cand, feats, lab = load(engine_dir)
    W = C["CUSTOMER_BENEFIT_WEIGHT"]
    base = off[["account_id", "p_churn_90d", "customer_value_usd", "action_code"]].merge(feats, on="account_id").merge(lab, on="account_id")
    p, val = base.p_churn_90d.values, base.customer_value_usd.values
    # care-credit save rate per account, exactly as the dev chart computes it
    import compare_strategies as cs
    cs.IN_DIR = engine_dir
    try:
        sr_cc, _ = cs.engine_care_credit_save_rate(off, C)
    except Exception:  # noqa: BLE001
        sr_cc, _ = cs.fallback_care_credit_save_rate(pd.read_csv(ROOT / "demo_data" / "features.csv"), C)
    sr_cc = sr_cc.reindex(base.account_id).fillna(C["SAVE_RATE"]["care_credit"]["off_target"]).values
    cc = cand[(cand.action_code == "care_credit") & (cand.eligible.astype(str) == "True")]
    cc_cost = float(cc.offer_cost.median()) if len(cc) else 25.0; cc_ann = float(C["ANNOYANCE"]["care_credit"])
    n = len(base); churners = max(1, int(base.churn_90d.sum()))

    rows = []  # (policy, mask, saved_at_assumed, offer_cost, contact_cost, customer_savings, margin_given_up)
    def credit(name, m):
        m = np.asarray(m, bool)
        rows.append(dict(policy=name, contacts=int(m.sum()), saved=(p * sr_cc * val)[m].sum(), saves=(p * sr_cc)[m].sum(),
                         offer_cost=m.sum() * cc_cost, contact_cost=m.sum() * cc_ann, customer_savings=m.sum() * cc_cost,
                         margin_given_up=0.0, reached=int(base.churn_90d.values[m].sum())))
    rows.append(dict(policy="Do nothing", contacts=0, saved=0.0, saves=0.0, offer_cost=0.0, contact_cost=0.0,
                     customer_savings=0.0, margin_given_up=0.0, reached=0))
    credit("Discount everyone", np.ones(n))
    credit("3+ support calls rule", base.support_90d.values >= 3)
    top = np.zeros(n, bool); top[np.argsort(-p, kind="stable")[: int(round(0.1 * n))]] = True
    credit("Top 10% risk score only", top)

    ch = cand[cand.is_chosen.astype(str) == "True"].set_index("account_id").reindex(base.account_id)
    ac = base.action_code.values; contact = ac != "do_nothing"
    sr = ch.save_rate.fillna(0).values; ocost = ch.offer_cost.fillna(0).values; ann = ch.annoyance.fillna(0).values
    benefit = ch.customer_benefit.fillna(0).values
    is_cf = np.isin(ac, CUSTOMER_FIRST)
    plan_savings = np.where(is_cf, ocost + benefit, 0.0)          # full expected 12-month lost revenue = customer savings
    credit_paid = np.where(contact & ~is_cf & ~np.isin(ac, UPSELL), ocost, 0.0)
    credit_paid = credit_paid - np.where(ac == "care_credit_fix_first", C["FIX_FIRST_CALLBACK_COST"], 0.0)
    credit_paid = credit_paid - np.where(ac == "fix_first", C["FIX_FIRST_CALLBACK_COST"], 0.0)  # callbacks are not $ to customers
    credit_paid = np.clip(credit_paid, 0, None)
    def ours(name, m, note=""):
        rows.append(dict(policy=name, contacts=int(m.sum()), saved=(p * sr * val)[m].sum(), saves=(p * sr)[m].sum(),
                         offer_cost=ocost[m].sum(), contact_cost=ann[m].sum(),
                         customer_savings=(plan_savings + credit_paid)[m].sum(), margin_given_up=plan_savings[m].sum(),
                         reached=int(base.churn_90d.values[m].sum()), note=note))
    ours("Ours", contact)
    ours("  Ours: retention offers only", contact & ~is_cf & ~np.isin(ac, UPSELL), "decomposition slice of Ours")
    ours("  Ours: cheaper-plan moves (right-size, variant)", contact & is_cf, "decomposition slice of Ours")
    ours("  Ours: upsells", contact & np.isin(ac, UPSELL), "decomposition slice of Ours; upsell margin not counted")
    R = pd.DataFrame(rows)
    assumed = R.loc[R.policy == "Ours", "saves"].item() / max(1, R.loc[R.policy == "Ours", "reached"].item())

    out = []
    for r in [round(assumed, 3)] + RATES[1:]:
        sc = 1.0 if r == round(assumed, 3) else r / assumed
        for _, x in R.iterrows():
            net_chart = x.saved * sc - x.offer_cost - x.contact_cost
            out.append(dict(policy=x.policy, decide_save_rate=round(assumed, 3), true_save_rate=r, save_scale=round(sc, 3),
                            contacts=x.contacts, business_net=round(net_chart, 0),
                            business_net_full_company_view=round(net_chart - W * x.margin_given_up, 0),
                            customer_savings=round(x.customer_savings, 0), margin_given_up=round(x.margin_given_up, 0),
                            expected_saves=round(x.saves * sc, 2), offer_cost=round(x.offer_cost, 0),
                            notes="; ".join(s for s in [NOTE, x.get("note") if isinstance(x.get("note"), str) else ""] if s), source="cross-check (ours)"))
    return pd.DataFrame(out), R


def validate(df: pd.DataFrame) -> list[str]:
    flags = []
    for _, r in df.iterrows():
        tag = f"{r.policy} @ {r.true_save_rate}"
        if pd.isna([r.business_net, r.customer_savings, r.margin_given_up]).any(): flags.append(f"{tag}: missing value")
        if r.customer_savings < -0.5 or r.margin_given_up < -0.5: flags.append(f"{tag}: negative savings/give-up")
        if r.contacts == 0 and (abs(r.business_net) + r.customer_savings + r.margin_given_up) > 0.5:
            flags.append(f"{tag}: nonzero dollars with 0 contacts")
        if r.margin_given_up > r.customer_savings + 1 and "upsell" not in str(r.notes).lower():
            flags.append(f"{tag}: margin given up exceeds customer savings (only skipped upsell could explain that)")
        if r.contacts > 0 and abs(r.business_net) > 1e6: flags.append(f"{tag}: implausible business_net")
    # monotonic in save rate: business net must fall as the realized save rate falls (picks fixed)
    for pol, g in df.groupby("policy"):
        g = g.sort_values("true_save_rate")
        if g.contacts.max() > 0 and (np.diff(g.business_net.values) < -1).any():
            flags.append(f"{pol}: business_net not increasing in save rate")
    return flags


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--engine-dir", default=str(ROOT / "demo_data")); a = ap.parse_args()
    mine, R = build(Path(a.engine_dir))
    mine.to_csv(OUT / "value_split_crosscheck.csv", index=False)
    if TM_FILE.exists():
        tm = pd.read_csv(TM_FILE); missing = [c for c in SCHEMA if c not in tm.columns]
        if missing: raise SystemExit(f"{TM_FILE} is missing columns {missing}")
        tm["source"] = "tm-models policy_by_save_rate.csv"; primary = tm
    else:
        print(f"note: {TM_FILE} not found; chart data uses our cross-check rows (marked)"); primary = mine
    flags = validate(primary)
    primary.to_csv(OUT / "value_split.csv", index=False)
    long = primary.melt(id_vars=["policy", "true_save_rate", "contacts", "source"],
                        value_vars=["business_net", "customer_savings", "margin_given_up"], var_name="bar", value_name="usd")
    long["bar"] = long.bar.map({"business_net": "Business net (company $)", "customer_savings": "Customer savings",
                                "margin_given_up": "Margin given up on purpose"})
    long["data_note"] = "SYNTHETIC/SIMULATED"; long.to_csv(OUT / "value_split_chart.csv", index=False)
    # gap decomposition at the assumed rate (dev chart numbers)
    m = mine[mine.save_scale == 1.0].set_index("policy")
    gap = m.loc["Ours", "business_net"] - m.loc["Top 10% risk score only", "business_net"]
    lines = [f"[SYNTHETIC] Ours minus Top-10% risk, dev chart definition, assumed save rate: ${gap:,.0f}"]
    for s in [x for x in m.index if x.startswith("  Ours")]:
        lines.append(f"  {s.strip()}: contacts {int(m.loc[s,'contacts'])}, business net ${m.loc[s,'business_net']:,.0f}, "
                     f"customer savings ${m.loc[s,'customer_savings']:,.0f}, margin given up ${m.loc[s,'margin_given_up']:,.0f}")
    lines.append("validation flags: " + ("none" if not flags else "\n  " + "\n  ".join(flags)))
    t = mine.pivot(index="policy", columns="true_save_rate", values="business_net")
    lines.append("\nbusiness net by realized save rate (cross-check, picks fixed):\n" + t[sorted(t.columns, reverse=True)].to_string())
    txt = "\n".join(lines); print(txt); (OUT / "value_split_summary.txt").write_text(txt)


if __name__ == "__main__":
    main()
