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
- Retention-only, re-picked at 10% is the headline bar. The profit-ranked upsell row is Q&A only: its gain rests on
  the 3.9%/quarter plan-upgrade assumption. Home Internet (take rate 1-4%, derived) is never picked, so it is a
  footnote, not a bar; the script checks that the 1/2/4% rows pick zero Home Internet and equal the no-HI row.
- Whiskers = realized-outcome bootstrap (2,000 account resamples, also drawing who churns and who is saved), read
  from the policy table (CI, P(net>0)) and its RESULTS.md section 4 (mean). The expected-value CI stays in the CSV only.
- Pending bars are hidden on the chart (kept in chart_bars.csv with status=pending) and listed in one footnote.
- Receipt headline uses the STRICT like-for-like rule: losing a price guarantee, adding a 50 GB cap, losing hotspot
  or losing perks all mean "you'd lose something". Source order: tm-models receipt.csv if present; else their
  plan_moves_classified.csv (cap / guarantee / hotspot flags) plus the optimizer reason for perks; else the older
  optimizer-agrees-with-engine set minus price-guarantee losses (403), flagged as a fallback.
- Shipped engine and every bar use full company dollars only (business_net_full_dollar), never the chart-style column.

Source of the numbers: tm-models' policy-by-save-rate table (env TM_POLICY_BY_SAVE_RATE). This script does not
recompute policy values; any bar not yet in that table is written as "pending tm-models" (value blank).
Receipt dollars come from the plan-mix optimizer output (env HOUSEHOLD_PLAN_CSV, default data/household_plan.csv) joined to the engine's eligible
plan moves (demo_data/offer_candidates.csv.gz).
Run: python experiments/efficacy/chart_data.py  -> out/chart_bars.csv, out/chart_receipt.csv, out/chart_preview.png
"""
from __future__ import annotations
import os, re
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
TM = Path(os.environ.get("TM_POLICY_BY_SAVE_RATE", ROOT.parent / "scratch_models" / "chart_check" / "policy_by_save_rate.csv"))
HH = Path(os.environ.get("HOUSEHOLD_PLAN_CSV", HERE / "data" / "household_plan.csv"))
TM_RESULTS = TM.parent / "RESULTS.md"
TM_RECEIPT = TM.parent / "receipt.csv"                     # preferred: tm-models' receipt table (RESULTS.md section 6)
TM_MOVES = TM.parent / "plan_moves_classified.csv"         # else: their per-move classification, strict rule applied here
DECIDE = 0.10; SCORED = [0.05, 0.10, 0.22]; HEADLINE = 0.10
SWITCH = {"base": 0.03, "low": 0.02, "high": 0.13}   # receipt switch rate (assumption; randomized plan-fit trials 1-13%)
PENDING = "pending"
HEADLINE_BAR = "ret_10"
UPSELL_LABEL = "Profit-ranked incl. upsell (Q&A only; rests on 3.9%/quarter upgrade assumption)"
TITLE = "Business net in full company dollars, picks made at a 10% save rate (SYNTHETIC)"
SUBTITLE = "Profitable if real save rates are at least about 4.5%. At 10% it wins ~7 in 8; at 5% it's a coin flip."
HI_NOTE = "Home Internet never picked at a 1-4% take rate (derived)."
PERK_NOTE = "Perk reminders never pay as texts; shown on the bill/app instead."

# (key, chart label, regex on tm-models policy name, required decide rate or None for rules that don't decide)
BARS = [
    # chart accounting only (retention, no upsell margin); plain shipped_engine adds upsell margin and is Q&A only
    ("shipped", "Shipped engine, full company dollars, retention only", r"^shipped_engine_chart_accounting$", "any"),
    ("risk_credit", "Top 10% risk: $25 credit to all (old chart rule)", r"^top10_risk_care_credit$", None),
    ("risk_best", "Top 10% risk: best fix for each (fix chosen at each rate)", r"^risk_only_best_fix_top500$", "own"),
    ("ret_fixed44", "Retention-only, picks fixed at 44%", r"^ev_retention_only_unlimited_mismatched$", 0.44),
    ("ret_10", "Retention-only, re-picked at 10%", r"^ev_retention_only_unlimited(?:_picked10)?$", DECIDE),
    ("receipt_only", "Receipt only: like-for-like plan moves, no texts (3% switch)", r"^texts10_receipt_like_for_like_acc3$", DECIDE),
    ("texts_receipt", "Retention texts + like-for-like plan moves on the receipt (3% switch)", r"^texts10_receipt_like_for_like_acc3$", DECIDE),
    # corrected profit-ranked (Home Internet fixed take; identical at 1/2/4% because HI is never picked). The older
    # ev_ranked_unlimited_picked10 rows are NOT used: they priced Home Internet off the phone-upgrade score (a bug).
    ("upsell_qa", UPSELL_LABEL, r"^ev_ranked_corrected_noHI(?:_picked10)?$", DECIDE),
    ("nothing", "Do nothing", r"^do_nothing$", None),
]
# bootstrap companion rows: "<policy>_bootstrap" (tm-models: 2,000 account resamples, true p)
BOOT = {"boot_ev_ci_lo": "ev_ci_lo", "boot_ev_ci_hi": "ev_ci_hi", "boot_ev_p_net_pos": "ev_p_net_pos",
        "boot_ci_lo": "realized_ci_lo", "boot_ci_hi": "realized_ci_hi", "boot_p_net_pos": "realized_p_net_pos"}


def results_boot_means() -> dict:
    """Realized-outcome bootstrap means from RESULTS.md section 4 (the CSV has CI and P but no mean).
    Returns {scored_rate: (ev_mean, realized_mean)}; {} if the table is not found."""
    if not TM_RESULTS.exists(): return {}
    txt = TM_RESULTS.read_text(); sec = txt[txt.find("## 4."):txt.find("## 5.")]
    num = lambda x: float(x.replace(",", "").replace("\u2212", "-"))
    out = {}
    for m in re.finditer(r"^\|\s*(\d+)%\s*\|\s*([\-\u2212\d,]+),\s*\[[^\]]*\],\s*[\d.]+\s*\|\s*([\-\u2212\d,]+),", sec, re.M):
        out[round(int(m.group(1)) / 100, 2)] = (num(m.group(2)), num(m.group(3)))
    return out


def check_home_internet(t):
    """Derive the Home Internet footnote: 1/2/4% rows must pick 0 HI and equal the no-HI row at every rate."""
    if t.empty: return False
    base = t[t.policy == "ev_ranked_corrected_noHI"].set_index("true_save_rate").business_net_full_dollar
    ok = len(base) > 0
    for k in (1, 2, 4):
        r = t[t.policy == f"ev_ranked_unlimited_hi{k}"].set_index("true_save_rate")
        ok &= len(r) > 0 and bool((pd.to_numeric(r.n_home_internet, errors="coerce").fillna(0) == 0).all()) \
            and bool(np.allclose(r.business_net_full_dollar.reindex(base.index), base))
    print("Home Internet never picked at 1/2/4%:", ok)
    return ok


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
    if dec == "own": m = m[m.decide_save_rate == scored]
    elif dec not in (None, "any"): m = m[m.decide_save_rate == dec]
    elif dec is None: m = m[m.decide_save_rate.isna() | True]
    return m.iloc[0] if len(m) else None


def build_bars(t):
    """Map tm-models rows to chart bars. Returns (bars, break-even rows)."""
    used = set(); out = []; means = results_boot_means()
    full = "business_net_full_dollar" if (not t.empty and "business_net_full_dollar" in t) else "business_net"
    for key, label, rx, dec in BARS:
        for s in SCORED:
            r = pick(t, rx, dec, s)
            row = dict(bar=key, label=label, decide_save_rate=(dec if isinstance(dec, float) else {"any": "as shipped", "own": "at scored rate"}.get(dec, "rule")),
                       scored_save_rate=s, headline=s == HEADLINE, data_note="SYNTHETIC/SIMULATED")
            if r is None:
                row.update(status=PENDING, tm_models_policy="", contacts=np.nan, business_net_full_usd=np.nan,
                           customer_savings_usd=np.nan)
            else:
                used.add(r.policy)
                row.update(status="from tm-models", tm_models_policy=r.policy, contacts=r.contacts,
                           business_net_full_usd=r[full], value_column=full, customer_savings_usd=r.customer_savings,
                           upsell_contacts=r.get("upsell_contacts", np.nan), notes=r.get("notes", ""))
                if key == "receipt_only":   # the receipt part alone of the texts+receipt run: no texts, no contact cost
                    row.update(contacts=0, business_net_full_usd=r.get("receipt_net_full", np.nan), value_column="receipt_net_full",
                               customer_savings_usd=r.get("receipt_customer_savings", np.nan),
                               notes="receipt part alone (receipt_net_full) of " + str(r.policy))
                    out.append(row); continue
                base = re.sub(r"_picked10$", "", str(r.policy))
                bt = t[t.policy.isin([base + "_bootstrap", base + "_picked10_bootstrap"]) & (t.true_save_rate == s)
                       & (t.decide_save_rate == r.decide_save_rate)]
                if len(bt):
                    used.update(bt.policy)
                    for src, dst in BOOT.items(): row[dst] = bt.iloc[0].get(src, np.nan)
                    row["ev_mean"], row["realized_mean"] = means.get(s, (np.nan, np.nan))
                    row["bootstrap_source"] = "realized outcomes: 2,000 account resamples + Bernoulli churn x save"
            out.append(row)
    B = pd.DataFrame(out)
    assert (B.loc[B.status != PENDING, "value_column"].isin(["business_net_full_dollar", "receipt_net_full"])).all(), \
        "every bar must be in full company dollars"
    if not t.empty:
        print("tm-models rows not used by any bar:", sorted(set(t.policy) - used - set(t.policy[t.policy.str.endswith("_breakeven")])))
    # shipped engine: picks were made at the engine's assumed rates, not 10%; say so on the label
    be = t[t.policy.astype(str).str.endswith("_breakeven")] if not t.empty else t
    used.update(be.policy if len(be) else [])
    return B, be


def _receipt_frame(n_ll, mo_ll, n_lx, mo_lx, src, fallback):
    def line(name, n, mo, headline):
        r = dict(line=name, accounts=int(n), counts_in_headline=headline, monthly_if_all_switch=float(mo),
                 yearly_if_all_switch=12 * float(mo), status=src, fallback=fallback,
                 data_note="SYNTHETIC; switch rate is an assumption")
        for k, v in SWITCH.items(): r[f"yearly_at_{int(v*100)}pct_switch"] = round(12 * mo * v, 0)
        return r
    R = pd.DataFrame([line("Money back to customers (receipt): like-for-like accounts", n_ll, mo_ll, True),
                      line("Cheaper, but you'd lose something (separate line, never in the headline)", n_lx, mo_lx, False)])
    t = R.iloc[[0]].copy(); t["line"] = "T-Mobile side: the same receipt dollars as a cost (not in business net)"
    for col in [c for c in R.columns if c.startswith(("monthly", "yearly"))]: t[col] = -t[col]
    return pd.concat([R, t], ignore_index=True)


def _strict_moves(m):
    """Strict like-for-like: no added cap, no lost price guarantee, no lost hotspot, no lost perks."""
    lose = m.adds_cap.astype(bool) | m.loses_guarantee.astype(bool) | m.less_hotspot.astype(bool)
    if HH.exists():   # perks: the classification has no perks flag, so use the optimizer's reason text
        h = pd.read_csv(HH).set_index("account_id")
        lose |= m.account_id.map(h.reason.astype(str).str.contains("perk", case=False)).fillna(False).astype(bool)
    return lose


def receipt():
    """Receipt line, strict like-for-like rule (see module docstring for source order)."""
    for f, kind in ((TM_RECEIPT, "receipt"), (TM_MOVES, "moves")):
        if not f.exists(): continue
        m = pd.read_csv(f)
        need = {"account_id", "customer_monthly_delta", "adds_cap", "loses_guarantee", "less_hotspot"}
        if not need <= set(m.columns): print(f"note: {f.name} lacks {need - set(m.columns)}; skipped"); continue
        m["sav"] = -m.customer_monthly_delta; lose = _strict_moves(m)
        ll, lx = m[~lose], m[lose]
        print(f"receipt source: {f.name} (strict rule) -> like-for-like {len(ll)}, lose-something {len(lx)}")
        return _receipt_frame(ll.account_id.nunique(), ll.sav.sum(), lx.account_id.nunique(), lx.sav.sum(),
                              f"tm-models {f.name}, strict rule (cap/guarantee/hotspot/perks)", False)
    print("WARNING: no tm-models receipt file; FALLBACK to optimizer-agrees-with-engine minus price-guarantee (403)")
    if not HH.exists():
        return pd.DataFrame([dict(line="money back to customers (receipt)", status="pending: optimizer output missing")])
    h = pd.read_csv(HH); s = h[h.monthly_saving > 0].set_index("account_id")
    c = pd.read_csv(ROOT / "demo_data" / "offer_candidates.csv.gz")
    e = c[(c.eligible.astype(str) == "True") & c.action_code.isin(["right_size", "variant_switch"])].copy()
    e["sav"] = -e.customer_monthly_delta
    e = e.sort_values("sav", ascending=False).drop_duplicates("account_id").set_index("account_id")
    agree = s.index.intersection(e.index); agree = agree[np.isclose(s.loc[agree, "monthly_saving"], e.loc[agree, "sav"])]
    agree = agree[~s.loc[agree, "reason"].astype(str).str.contains("price guarantee", case=False).to_numpy()]
    other = s.index.difference(agree)
    return _receipt_frame(len(agree), s.loc[agree, "monthly_saving"].sum(), len(other), s.loc[other, "monthly_saving"].sum(),
                          "FALLBACK: optimizer + engine agree, minus price-guarantee losses", True)


SHORT = {"risk_best": "Top 10% risk: best fix for each", "receipt_only": "Receipt only", "texts_receipt": "Texts + receipt",
         "upsell_qa": "Profit-ranked incl. upsell", "shipped": "Shipped engine", "risk_credit": "Top 10% risk credit",
         "ret_fixed44": "Retention-only fixed at 44%", "ret_10": "Retention-only at 10%", "nothing": "Do nothing"}


def pending_note(B):
    parts = []
    for key in dict.fromkeys(B.bar):
        miss = B[(B.bar == key) & (B.status == PENDING)].scored_save_rate.tolist()
        if not miss: continue
        n = SHORT.get(key, key)
        parts.append(n + (" (all rates)" if len(miss) == len(SCORED) else " at " + ", ".join(f"{int(m*100)}%" for m in miss)))
    return ("Not computed yet, hidden: " + "; ".join(parts) + ".") if parts else ""


def money(v): return ("-" if v < 0 else "+" if v > 0 else "") + f"${abs(v):,.0f}"


def chart(B, R, hi_ok=True):
    import matplotlib, textwrap; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    shown = B.groupby("bar", sort=False).status.apply(lambda x: (x != PENDING).any())
    keys = [k for k in dict.fromkeys(B.bar) if shown[k]]
    labels = [textwrap.fill(B[B.bar == k].label.iloc[0], 34) for k in keys]
    fig = plt.figure(figsize=(13, 0.8 * len(keys) + 3.8))
    gs = fig.add_gridspec(1, 2, width_ratios=[4.2, 1], wspace=0.10)
    ax = fig.add_subplot(gs[0]); ax2 = fig.add_subplot(gs[1], sharey=ax)
    y = np.arange(len(keys)); h = 0.26; colors = {0.05: "#c2185b", 0.10: "#e48aae", 0.22: "#f4cde0"}
    span = np.nanmax(np.abs(np.r_[B.business_net_full_usd.to_numpy(float), B.get("realized_ci_hi", pd.Series(dtype=float)).to_numpy(float),
                                  B.get("realized_ci_lo", pd.Series(dtype=float)).to_numpy(float)]))
    pad = 0.012 * span; whisk_drawn = False
    for j, s in enumerate(SCORED):
        for yi, k in zip(y + (j - 1) * h, keys):
            r = B[(B.bar == k) & (B.scored_save_rate == s)].iloc[0]
            if r.status == PENDING or pd.isna(r.business_net_full_usd): continue   # hidden, listed in footnote
            v = float(r.business_net_full_usd); hd = k == HEADLINE_BAR
            ax.barh(yi, v, h, color=colors[s], edgecolor="#111" if hd else "none", lw=1.3 if hd else 0)
            end = v
            if pd.notna(r.get("realized_ci_lo", np.nan)):
                ax.errorbar(v, yi, xerr=[[v - r.realized_ci_lo], [r.realized_ci_hi - v]], fmt="none", ecolor="#222",
                            elinewidth=1.1, capsize=3); whisk_drawn = True
                end = r.realized_ci_hi if v >= 0 else r.realized_ci_lo
                if pd.notna(r.get("realized_p_net_pos", np.nan)):
                    ax.text(r.realized_ci_hi + pad, yi, f"P(net>0) {r.realized_p_net_pos:.2f}", va="center", ha="left",
                            fontsize=7, color="#222", fontweight="bold" if hd else "normal")
            txt = money(v)
            if pd.notna(r.get("realized_ci_lo", np.nan)):
                ax.text(min(0, r.realized_ci_lo) - pad, yi, txt, va="center", ha="right", fontsize=7.5,
                        fontweight="bold" if hd else "normal")
            elif v >= 0:
                ax.text(end + pad, yi, txt, va="center", ha="left", fontsize=7.5, fontweight="bold" if hd else "normal")
            else:
                ax.text(end - pad, yi, txt, va="center", ha="right", fontsize=7.5)
    for s in SCORED:
        ax.barh(np.nan, 0, color=colors[s], label=f"scored at {int(s*100)}% save rate" + (" (headline)" if s == HEADLINE else ""))
    if whisk_drawn:
        ax.errorbar([np.nan], [np.nan], xerr=[[1]], fmt="none", ecolor="#222", capsize=3,
                    label="95% range, realized outcomes (bootstrap)")
    ax.axvline(0, color="#333", lw=0.8); ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=8.5); ax.invert_yaxis()
    for tl, k in zip(ax.get_yticklabels(), keys):
        if k == HEADLINE_BAR: tl.set_fontweight("bold")
    ax.set_xlim(-span * 1.32, span * 1.12)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: money(v)))
    ax.tick_params(axis="x", labelsize=8)
    ax.set_xlabel("business net, $ over the 5,042 synthetic accounts", fontsize=9)
    ax.legend(fontsize=7.5, loc="lower right", framealpha=0.95)
    # money back to customers: own panel/axis so it doesn't stretch the main one
    cs = np.array([B[(B.bar == k) & (B.scored_save_rate == HEADLINE)].customer_savings_usd.iloc[0] for k in keys], float)
    ok = ~np.isnan(cs)
    ax2.hlines(y[ok], 0, cs[ok], color="#1b5e20", lw=1)
    ax2.scatter(cs[ok], y[ok], marker="D", s=26, color="#1b5e20", zorder=3)
    for yi, c in zip(y[ok], cs[ok]):
        ax2.text(c + 0.04 * np.nanmax(cs), yi, f"${c:,.0f}", ha="left", va="center", fontsize=7, color="#1b5e20")
    ax2.set_xlim(0, np.nanmax(cs) * 1.45 if ok.any() else 1); ax2.tick_params(axis="y", left=False, labelleft=False)
    ax2.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v/1000:,.0f}k"))
    ax2.tick_params(axis="x", labelsize=7.5)
    ax2.set_title("money back to customers\n(also a cost to T-Mobile;\nnot in business net)", fontsize=8.5, color="#1b5e20")
    for a_ in (ax, ax2):
        a_.spines[["top", "right"]].set_visible(False)
    fig.suptitle(TITLE, fontsize=12, fontweight="bold", x=0.01, ha="left", y=0.995)
    fig.text(0.01, 0.995 - 0.33 / fig.get_figheight(), SUBTITLE, fontsize=10, ha="left", va="top", color="#c2185b")
    r0 = R.iloc[0]
    rec = ("Receipt (not in business net): money back to customers on " + f"{int(r0.get('accounts', 0)):,} like-for-like accounts "
           f"(nothing given up), ${r0.get('yearly_at_3pct_switch', 0):,.0f}/yr at a 3% switch rate (2-13%: "
           f"${r0.get('yearly_at_2pct_switch', 0):,.0f}-${r0.get('yearly_at_13pct_switch', 0):,.0f}); the same dollars are a cost "
           "on T-Mobile's side. Moves that would lose a price guarantee, hotspot, perks or unlimited data are a separate line, never in the headline."
           + (" (FALLBACK definition.)" if bool(r0.get("fallback", False)) else "")
           if "accounts" in R else "Receipt: not computed yet.")
    notes = [rec,
             (HI_NOTE + " " if hi_ok else "") + PERK_NOTE + " All rates assumed; save rates 5-22% bracket the field evidence. Upsell row rests on "
             "a 3.9%/quarter upgrade assumption.",
             "Whiskers: 95% range over 2,000 account resamples that also draw who actually churns and who is saved (realized outcomes).",
             pending_note(B)]
    lines = [ln for n in notes if n for ln in textwrap.wrap(n, 205)]
    fig.text(0.01, 0.012, "\n".join(lines), fontsize=7.3, color="#444", va="bottom", ha="left")
    top = 1 - 0.8 / fig.get_figheight(); bottom = (0.14 * len(lines) + 0.65) / fig.get_figheight()
    fig.subplots_adjust(left=0.235, right=0.985, top=top, bottom=bottom)
    fig.savefig(OUT / "chart_preview.png", dpi=150); plt.close(fig)


def main():
    t = tm_rows(); B, be = build_bars(t); R = receipt(); hi_ok = check_home_internet(t)
    if len(be): be.to_csv(OUT / "chart_breakeven.csv", index=False); print("break-even rows:\n" + be[["policy", "true_save_rate_exact", "notes"]].to_string(index=False))
    B.to_csv(OUT / "chart_bars.csv", index=False); R.to_csv(OUT / "chart_receipt.csv", index=False)
    chart(B, R, hi_ok)
    pd.set_option("display.width", 220)
    print(B.pivot_table(index="label", columns="scored_save_rate", values="business_net_full_usd", sort=False, dropna=False).to_string())
    print("pending bars:", sorted(B[B.status == PENDING].bar.unique()))
    print(R.drop(columns=["data_note"]).to_string(index=False))


if __name__ == "__main__":
    main()
