"""Strategy chart data + PNG preview. ALL NUMBERS SYNTHETIC / SIMULATED (synthetic accounts, simulated labels,
assumed save, accept and take rates). Nothing here is measured on real customers.

Rules for the chart:
- Every policy is PICKED assuming a 10% save rate (share of reached would-be churners an offer saves; field anchors
  5-15%), then SCORED at 5% (headline), 10% and 22% (range).
- Business net is in FULL company dollars: no 50% weighting of plan moves, upsell margin included, customer savings
  weighted 0 when picking texts.
- Plan moves are never texted. They go on the receipt. Its dollars show twice, labelled honestly: "money back to
  customers" on the customer side and as a cost on T-Mobile's side. They are never folded into business net.
  Receipt headline = the accounts where the plan-mix optimizer and the offer engine agree (like-for-like). The rest
  is a separate "cheaper, but you'd lose ..." line and never counts in the headline.
- Home Internet take rate: 2% per offer contact per quarter, range 1-4%, eligible addresses only (derived; research
  notes section 12a). The upsell bar is shown at 1%, 2%, 4% and with no Home Internet.

Source of the numbers: tm-models' policy-by-save-rate table (env TM_POLICY_BY_SAVE_RATE). This script does not
recompute policy values; any bar not yet in that table is written as "pending tm-models" (value blank).
Receipt dollars come from the plan-mix optimizer output (env HOUSEHOLD_PLAN_CSV) joined to the engine's eligible
plan moves (demo_data/offer_candidates.csv.gz).
Run: python experiments/efficacy/chart_data.py  -> out/chart_bars.csv, out/chart_receipt.csv, out/chart_preview.png
"""
from __future__ import annotations
import os, re
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
TM = Path(os.environ.get("TM_POLICY_BY_SAVE_RATE", ROOT.parent / "scratch_models" / "chart_check" / "policy_by_save_rate.csv"))
HH = Path(os.environ.get("HOUSEHOLD_PLAN_CSV", "/tmp/household_opt_v2/household_plan.csv"))
DECIDE = 0.10; SCORED = [0.05, 0.10, 0.22]; HEADLINE = 0.05
SWITCH = {"base": 0.03, "low": 0.02, "high": 0.13}   # receipt switch rate (assumption; randomized plan-fit trials 1-13%)
PENDING = "pending (not computed yet)"

# (key, chart label, regex on tm-models policy name, required decide rate or None for rules that don't decide)
BARS = [
    ("shipped", "Shipped engine (picks made at its assumed ~44%)", r"^shipped_engine$", "any"),
    ("risk_credit", "Top 10% risk: $25 credit to all (old chart rule)", r"^top10_risk_care_credit$", None),
    ("risk_best", "Top 10% risk: best fix for each", r"^(?:risk|top10_risk)\w*(?:best|fix)\w*$", DECIDE),
    ("ret_fixed44", "Retention-only, picks fixed at 44%", r"^ev_retention_only_unlimited_mismatched$", 0.44),
    ("ret_10", "Retention-only, re-picked at 10%", r"^ev_retention_only_unlimited(?:_picked10)?$", DECIDE),
    ("texts_receipt", "Retention texts + plan moves on the receipt", r"receipt", DECIDE),
    ("up_nohi", "Profit-ranked incl. upsell, no Home Internet", r"^ev_ranked_unlimited_no_?h\w*$", DECIDE),
    ("up_hi1", "Profit-ranked incl. upsell, Home Internet 1% (derived)", r"^ev_ranked_unlimited_hi1(?:_picked10)?$", DECIDE),
    ("up_hi2", "Profit-ranked incl. upsell, Home Internet 2% base (1-4%), derived", r"^ev_ranked_unlimited_hi2(?:_picked10)?$", DECIDE),
    ("up_hi4", "Profit-ranked incl. upsell, Home Internet 4% (derived)", r"^ev_ranked_unlimited_hi4(?:_picked10)?$", DECIDE),
    ("nothing", "Do nothing", r"^do_nothing$", None),
]
# bootstrap companion rows: "<policy>_bootstrap" (tm-models: 2,000 account resamples, true p)
BOOT = {"boot_ev_ci_lo": "ev_ci_lo", "boot_ev_ci_hi": "ev_ci_hi", "boot_ev_p_net_pos": "ev_p_net_pos",
        "boot_ci_lo": "realised_ci_lo", "boot_ci_hi": "realised_ci_hi", "boot_p_net_pos": "realised_p_net_pos"}


def tm_rows() -> pd.DataFrame:
    if not TM.exists():
        print(f"note: {TM} missing; every bar pending"); return pd.DataFrame()
    t = pd.read_csv(TM)
    t["true_save_rate_exact"] = pd.to_numeric(t["true_save_rate"], errors="coerce")
    for c in ("decide_save_rate", "true_save_rate"): t[c] = pd.to_numeric(t[c], errors="coerce").round(2)
    return t


def pick(t, rx, dec, scored):
    if t.empty: return None
    m = t[t.policy.astype(str).str.contains(rx, regex=True, flags=re.I) & (t.true_save_rate == scored)]
    if dec not in (None, "any"): m = m[m.decide_save_rate == dec]
    elif dec is None: m = m[m.decide_save_rate.isna() | True]
    return m.iloc[0] if len(m) else None


def build_bars(t):
    """Map tm-models rows to chart bars. Returns (bars, break-even rows)."""
    used = set(); out = []
    full = "business_net_full_dollar" if (not t.empty and "business_net_full_dollar" in t) else "business_net"
    for key, label, rx, dec in BARS:
        for s in SCORED:
            r = pick(t, rx, dec, s)
            row = dict(bar=key, label=label, decide_save_rate=(dec if isinstance(dec, float) else ("as shipped" if dec == "any" else "rule")),
                       scored_save_rate=s, headline=s == HEADLINE, data_note="SYNTHETIC/SIMULATED")
            if r is None:
                row.update(status=PENDING, tm_models_policy="", contacts=np.nan, business_net_full_usd=np.nan,
                           customer_savings_usd=np.nan)
            else:
                used.add(r.policy)
                row.update(status="from tm-models", tm_models_policy=r.policy, contacts=r.contacts,
                           business_net_full_usd=r[full], customer_savings_usd=r.customer_savings,
                           upsell_contacts=r.get("upsell_contacts", np.nan), notes=r.get("notes", ""))
                base = re.sub(r"_picked10$", "", str(r.policy))
                bt = t[t.policy.isin([base + "_bootstrap", base + "_picked10_bootstrap"]) & (t.true_save_rate == s)
                       & (t.decide_save_rate == r.decide_save_rate)]
                if len(bt):
                    used.update(bt.policy)
                    for src, dst in BOOT.items(): row[dst] = bt.iloc[0].get(src, np.nan)
            out.append(row)
    B = pd.DataFrame(out)
    if not t.empty:
        print("tm-models rows not used by any bar:", sorted(set(t.policy) - used - set(t.policy[t.policy.str.endswith("_breakeven")])))
    # shipped engine: picks were made at the engine's assumed rates, not 10%; say so on the label
    be = t[t.policy.astype(str).str.endswith("_breakeven")] if not t.empty else t
    used.update(be.policy if len(be) else [])
    return B, be


def receipt():
    """Receipt line from the plan-mix optimizer, limited to accounts where it agrees with the engine."""
    if not HH.exists():
        return pd.DataFrame([dict(line="money back to customers (receipt)", status="pending: optimizer output missing")])
    h = pd.read_csv(HH); s = h[h.monthly_saving > 0].set_index("account_id")
    c = pd.read_csv(ROOT / "demo_data" / "offer_candidates.csv.gz")
    e = c[(c.eligible.astype(str) == "True") & c.action_code.isin(["right_size", "variant_switch"])].copy()
    e["sav"] = -e.customer_monthly_delta
    e = e.sort_values("sav", ascending=False).drop_duplicates("account_id").set_index("account_id")
    agree = s.index.intersection(e.index); agree = agree[np.isclose(s.loc[agree, "monthly_saving"], e.loc[agree, "sav"])]
    other = s.index.difference(agree)
    def line(name, idx, headline):
        mo = float(s.loc[idx, "monthly_saving"].sum()); pg = int(s.loc[idx, "reason"].astype(str).str.contains("price guarantee").sum())
        r = dict(line=name, accounts=len(idx), counts_in_headline=headline, monthly_if_all_switch=mo,
                 yearly_if_all_switch=12 * mo, lose_price_guarantee=pg, status="computed here from optimizer + engine",
                 data_note="SYNTHETIC; switch rate is an assumption")
        for k, v in SWITCH.items(): r[f"yearly_at_{int(v*100)}pct_switch"] = round(12 * mo * v, 0)
        return r
    R = pd.DataFrame([line("Money back to customers (receipt): like-for-like accounts", agree, True),
                      line("Cheaper, but you'd lose something (separate line, never in the headline)", other, False)])
    # same dollars on T-Mobile's side: a cost, shown as its own line
    t = R.iloc[[0]].copy(); t["line"] = "T-Mobile side: the same receipt dollars as a cost (not in business net)"
    for col in [c for c in R.columns if c.startswith(("monthly", "yearly"))]: t[col] = -t[col]
    return pd.concat([R, t], ignore_index=True)


def chart(B, R):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    labels = [lb for lb in dict.fromkeys(B.label)]
    fig, ax = plt.subplots(figsize=(11, 0.55 * len(labels) + 2.6))
    y = np.arange(len(labels)); h = 0.26; colors = {0.05: "#c2185b", 0.10: "#e48aae", 0.22: "#f4cde0"}
    for j, s in enumerate(SCORED):
        v = [B[(B.label == lb) & (B.scored_save_rate == s)].business_net_full_usd.iloc[0] for lb in labels]
        vv = np.nan_to_num(np.array(v, float))
        ax.barh(y + (j - 1) * h, vv, h, color=colors[s], label=f"scored at {int(s*100)}% save rate" + (" (headline)" if s == HEADLINE else ""))
        if "ev_ci_lo" in B:
            sub = [B[(B.label == lb) & (B.scored_save_rate == s)].iloc[0] for lb in labels]
            for yi, r in zip(y + (j - 1) * h, sub):
                if pd.notna(r.get("ev_ci_lo", np.nan)):
                    ax.plot([r.ev_ci_lo, r.ev_ci_hi], [yi, yi], color="#222", lw=1.2)
        for yi, val in zip(y + (j - 1) * h, v):
            txt = PENDING if pd.isna(val) else ("-" if val < 0 else "") + f"${abs(val):,.0f}"
            ax.text(0 if pd.isna(val) else val, yi, " " + txt, va="center", fontsize=7, color="#555" if pd.isna(val) else "#111")
    cs = [B[(B.label == lb) & (B.scored_save_rate == HEADLINE)].customer_savings_usd.iloc[0] for lb in labels]
    cs = np.array(cs, float); ok = ~np.isnan(cs)
    ax.scatter(cs[ok], (y + 0.42)[ok], marker="D", s=18, color="#1b5e20", label="customer savings (separate, not in net)")
    ax.axvline(0, color="#333", lw=0.8); ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=8); ax.invert_yaxis()
    ax.set_xlabel("expected $ over the 5,042 synthetic accounts")
    ax.set_title("Business net in full company dollars, picks made at a 10% save rate (SYNTHETIC)", fontsize=11)
    r0 = R.iloc[0]
    note = ("Receipt (not in business net): money back to customers on " + f"{int(r0.get('accounts', 0)):,} like-for-like accounts, "
            f"${r0.get('yearly_at_3pct_switch', 0):,.0f}/yr at a 3% switch rate (2-13%: ${r0.get('yearly_at_2pct_switch', 0):,.0f}"
            f"-${r0.get('yearly_at_13pct_switch', 0):,.0f}); the same dollars are a cost on T-Mobile's side."
            if "accounts" in R else "Receipt: pending")
    fig.text(0.01, 0.01, note + "\nAll rates assumed; save rates 5-22% bracket the field evidence. Home Internet take rate derived (1-4%). "
             "Black lines: 95% bootstrap CI (2,000 account resamples, expected value). 'pending' = not computed yet.",
             fontsize=7, color="#444")
    ax.legend(fontsize=7, loc="lower right"); fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(OUT / "chart_preview.png", dpi=140); plt.close(fig)


def main():
    t = tm_rows(); B, be = build_bars(t); R = receipt()
    if len(be): be.to_csv(OUT / "chart_breakeven.csv", index=False); print("break-even rows:\n" + be[["policy", "true_save_rate_exact", "notes"]].to_string(index=False))
    B.to_csv(OUT / "chart_bars.csv", index=False); R.to_csv(OUT / "chart_receipt.csv", index=False)
    chart(B, R)
    pd.set_option("display.width", 220)
    print(B.pivot_table(index="label", columns="scored_save_rate", values="business_net_full_usd", sort=False, dropna=False).to_string())
    print("pending bars:", sorted(B[B.status == PENDING].bar.unique()))
    print(R.drop(columns=["data_note"]).to_string(index=False))


if __name__ == "__main__":
    main()
