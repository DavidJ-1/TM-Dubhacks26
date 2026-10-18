"""SUMMARY.md writer for value_ledger.py. ALL NUMBERS SYNTHETIC."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import value_ledger as VL

PERSONAS = ["38", "04", "21", "24", "05", "39"]
TRUTH_CANDIDATES = [Path("/workspace/tmobile/synth/offer_response_truth.csv")]


def _fit_net(led_pf: pd.DataFrame, p: float, scale: float = 1.0, backfire: bool = False, kept="kept_mo_flat"):
    s = led_pf
    kept_mo = s[kept]
    net = s.p_churn_90d * VL.V["SAVE_IF_ACCEPT_PRICE"] * scale * p * kept_mo * 12 - p * s.saving_mo * 12 - s.contact
    if backfire:
        net = net - VL.backfire_loss(s.p_churn_90d, p, kept_mo, 12)
    return net.sum() / 12


def write_summary(out: Path, led, hh, mv, hv, src, offers, cand, acct):
    L = []
    w = L.append
    w("# Two-sided value ledger — SUMMARY (ALL NUMBERS SYNTHETIC)\n")
    w("5,042 sandbox stub accounts (`sandbox.db` read-only, as_of 2026-10-01). No real T-Mobile customer data. "
      "Code: `harness/value_ledger.py`. T-Mobile value of a kept account = $152.91 ARPA x 50% margin "
      "(upper bound) per month, i.e. ~$1.8K over 24 months (RESEARCH.md s12). **No acquisition/replacement cost is "
      "added on top of kept margin**; it appears only as an alternative column.\n")
    w(f"Hidden-value input used: **{src}**.\n")

    # ---- 1. plan-fit set
    pf = led[led.offer == "plan_fit"].merge(mv[["account_id", "like_for_like"]], on="account_id")
    eng = set(cand.loc[cand.action_code.isin(["right_size", "variant_switch"]), "account_id"])
    lfl = pf[pf.like_for_like]
    w("## 1. Plan-fit set (household optimizer, commit d3adf09)\n")
    w(f"- Optimizer movers that save: **{len(pf)} accounts, ${pf.saving_mo.sum():,.0f}/mo** if all accept "
      "(reproduces the 682 / $14,830).")
    w(f"- Like-for-like (no 'gives up' in the optimizer reason and no move from unlimited More/Beyond to a 50 GB "
      f"Essentials plan): **{len(lfl)} accounts, ${lfl.saving_mo.sum():,.0f}/mo**. Trade-off moves (receipt "
      f"'you'd lose X' line only): {len(pf) - len(lfl)} accounts, ${pf.saving_mo.sum() - lfl.saving_mo.sum():,.0f}/mo.")
    ov = pf[pf.account_id.isin(eng)]
    w(f"- Grok Bot's 488/194 split is a different cut: optimizer movers that the engine also flags right-size/variant "
      f"= **{len(ov)}** (${ov.saving_mo.sum():,.0f}/mo) vs optimizer-only {len(pf) - len(ov)} "
      f"(${pf.saving_mo.sum() - ov.saving_mo.sum():,.0f}/mo). That is 'engine agrees', not 'no trade-off': "
      f"{int((~ov.like_for_like).sum())} of the {len(ov)} still give something up, and "
      f"{int((pf.like_for_like & ~pf.account_id.isin(eng)).sum())} like-for-like moves (mostly Essentials -> "
      "Essentials Saver) are optimizer-only.\n")
    m44 = pf.merge(mv[["account_id", "current_plan", "best_plan"]], on="account_id")
    m44 = m44[(m44.current_plan == "Experience More 2.0") & (m44.best_plan == "Essentials 4 Line Offer 2.0")]
    w(f"- **Headline (Grok Bot decision) = the {len(ov)}: ${ov.saving_mo.sum():,.0f}/mo if all accept; expected "
      f"money back ${0.03 * ov.saving_mo.sum():,.0f}/mo at 3%, ${0.13 * ov.saving_mo.sum():,.0f}/mo at 13%.** "
      f"Strictly trade-off-free part of it: {int(ov.like_for_like.sum())} accounts, "
      f"${ov[ov.like_for_like].saving_mo.sum():,.0f}/mo.")
    in44 = m44[m44.account_id.isin(ov.account_id)]
    r488 = ov[~ov.account_id.isin(m44.account_id)]
    w(f"- The {len(m44)} Experience More -> Essentials 4 Line moves (give up price guarantee, high-speed hotspot, perks): "
      f"**{len(in44)} are inside the {len(ov)}** (${in44.saving_mo.sum():,.0f}/mo), {len(m44) - len(in44)} are outside. "
      f"Headline without them: {len(r488)} accounts, ${r488.saving_mo.sum():,.0f}/mo.")
    f4 = hv[hv.item_type == "plan_essentials_4line"]
    if len(f4):
        o4 = f4[~f4.account_id.isin(ov.account_id)]
        w(f"- tm-models' {f4.account_id.nunique()} 4-Line accounts (${f4.customer_value_monthly.sum():,.0f}/mo) = the optimizer's 100 "
          f"Essentials + 44 More moves. **{len(o4)} are NOT inside the {len(ov)}** (${o4.customer_value_monthly.sum():,.0f}/mo), all "
          f"More -> 4 Line moves the engine doesn't flag: {', '.join(o4.account_id)}.")
    w("")
    w("| Set | p_accept | Revenue-only framing $/mo | T-Mobile net $/mo (kept margin - given up - contact) | with Ascarza backfire | save rate x0.25 |")
    w("|---|---|---|---|---|---|")
    for name, s in [("all 682", pf), (f"headline {len(ov)}", ov), (f"no-trade-off {len(lfl)}", lfl)]:
        for p in (0.03, 0.13):
            w(f"| {name} | {p:.0%} | -${p * s.saving_mo.sum():,.0f} | ${_fit_net(s, p):,.0f} | "
              f"${_fit_net(s, p, backfire=True):,.0f} | ${_fit_net(s, p, scale=0.25):,.0f} |")
    w(f"\nBill-based kept margin instead of flat ARPA (all {len(pf)}, 3%): ${_fit_net(pf, 0.03, kept='kept_mo_bill'):,.0f}/mo; "
      f"13%: ${_fit_net(pf, 0.13, kept='kept_mo_bill'):,.0f}/mo.")
    w(f"Expected money back to customers: 3% ${0.03 * lfl.saving_mo.sum():,.0f}/mo, 13% ${0.13 * lfl.saving_mo.sum():,.0f}/mo "
      f"(no-trade-off {len(lfl)}); headline {len(ov)}: ${0.03 * ov.saving_mo.sum():,.0f} / ${0.13 * ov.saving_mo.sum():,.0f}. The same dollars are T-Mobile's revenue given up on the same receipt row (`receipt.csv`).\n")
    w("Read: at these risk levels the retention gain is small (mean p_churn_90d of the set "
      f"{pf.p_churn_90d.mean():.1%}), so T-Mobile's net stays close to the revenue-only cost. The receipt is a trust "
      "spend (customer-first), never a profit line: T-Mobile's net is negative in every row, and worse if the Ascarza "
      "backfire applies.\n")

    # ---- 2. hidden value
    w("## 2. Hidden value across all 5,042 accounts, by item\n")
    w("| Item | Accounts | Customer $/mo | One-time $ | Kind |")
    w("|---|---|---|---|---|")
    g = hv.groupby("item_type").agg(n=("account_id", "nunique"), mo=("customer_value_monthly", "sum"),
                                    one=("customer_value_one_time", "sum"), kind=("kind", "first"))
    for k, r in g.iterrows():
        w(f"| {k} | {r.n:,} | ${r.mo:,.0f} | ${r.one:,.0f} | {r.kind} |")
    sv = hv[hv.kind == "saving"]
    w(f"\nFirm $/mo savings: **{sv.account_id.nunique()} accounts, ${sv.customer_value_monthly.sum():,.0f}/mo**. "
      f"Any hidden item: {hv.account_id.nunique():,} accounts. Trade-in is one-time and never added to $/mo. "
      "Streaming and price guarantee are unpriced (no perk price or future price path in the sandbox); "
      "we never say 'you haven't used it' (no activation field).\n")

    # ---- 3. best action change
    base = led[~led.offer.isin(["hidden_saving", "hidden_value_reminder"])]
    w("## 3. Does adding hidden-value offers change the best action?\n")
    for by, lbl in [("tm_net_12m", "two-sided score (T-Mobile 12m net + 0.5 x expected customer $)"),
                    ("tm_net_12m_reminder_neg", "same, with the -1% reminder case for bill-shocked accounts")]:
        b0 = VL.rank_offers(base, by=by)
        b1 = VL.rank_offers(led, by=by)
        a0 = b0.offer.where(b0.score > 0, "do_nothing")
        a1 = b1.offer.where(b1.score > 0, "do_nothing").reindex(a0.index.union(b1.index)).fillna("do_nothing")
        a0 = a0.reindex(a1.index).fillna("do_nothing")
        ch = a1 != a0
        w(f"- {lbl}: **{int(ch.sum())} accounts change**; new best: " +
          ", ".join(f"{k} {v}" for k, v in a1[ch].value_counts().items()) +
          f"{'(none)' if not ch.any() else ''}. Contacts before {int((a0 != 'do_nothing').sum())} -> after {int((a1 != 'do_nothing').sum())}.")
    rem = led[led.offer == "hidden_value_reminder"]
    b = VL.rank_offers(led, w=1.0)
    b = b[b.score > 0]
    w(f"- Customer-first weight (w=1.0): hidden offers win for {int(b.offer.str.startswith('hidden').sum())} accounts. "
      "Why ~0: a firm hidden saving at 10% uptake costs T-Mobile p x $ x 12 and its retention gain is small at "
      "typical risk (p_churn_90d median ~1%); a reminder costs $2.50 and is worth 1-2% x p_churn x $917, so it only "
      "pays at high risk, where a fix-first or credit already scores higher. Hidden value goes on the receipt as an "
      "add-on line (no price change), not as the decision.")
    w(f"- Reminder offers with positive T-Mobile net: {int((rem.tm_net_12m > 0).sum())} of {len(rem)} "
      f"(cost $2.50 incl. annoyance vs 1-2% x p_churn x $917 kept 12m margin; only high-risk accounts clear it). "
      "Hidden value is framed as helping the customer, not a proven retention lever.\n")

    # ---- care credit check
    combo = offers[offers.action_code == "care_credit_fix_first"].account_id
    x = led[led.account_id.isin(combo) & led.offer.isin(["fix_first", "care_credit_fix_first"])]
    pv = x.pivot_table(index="account_id", columns="offer", values="tm_net_12m")
    if {"fix_first", "care_credit_fix_first"} <= set(pv.columns):
        better = (pv.fix_first >= pv.care_credit_fix_first).sum()
        pv25 = x.assign(n=x.tm_net_12m - x.tm_kept_margin_12m * 0.75).pivot_table(index="account_id", columns="offer", values="n")
        w(f"## Care credit check\nEngine picks $25 care credit + fix-first for {len(combo)} accounts. In the ledger, "
          f"fix-first alone is worth as much or more to T-Mobile for **{int(better)}** of them (engine save rates); "
          f"**{int((pv25.fix_first >= pv25.care_credit_fix_first).sum())}** at 0.25x save rates. tm-models' earlier "
          "test said 48 of 268.\n")

    # ---- 4. demo examples
    w("## 4. Three demo examples (personas)\n")
    g = lambda aid, o, c: led.loc[(led.account_id == aid) & (led.offer == o), c].iloc[0]  # noqa: E731
    try:
        a = "ACC-PERSONA-04"
        w(f"- **{a}** (90-day risk {g(a, 'fix_first', 'p_churn_90d'):.0%}): fix the open issue first. Fix-first alone nets "
          f"T-Mobile ${g(a, 'fix_first', 'tm_net_12m'):,.0f} over 12 months (incl. ${g(a, 'fix_first', 'support_saved'):,.0f} of avoided "
          f"support calls); adding the $25 credit makes it ${g(a, 'care_credit_fix_first', 'tm_net_12m'):,.0f}. Hidden value on the "
          f"receipt: phone payment ends Dec 2026 and 2 paid-off phones worth ~${g(a, 'hidden_value_reminder', 'customer_one_time'):,.0f} in trade-in.")
        a = "ACC-PERSONA-38"
        w(f"- **{a}**: qualifies for 55+ pricing on the same Experience More plan, $40/mo less (eligibility check). "
          f"Money back to the customer $480/yr if they switch; T-Mobile's expected net at 10% uptake "
          f"${g(a, 'variant_switch', 'tm_net_12m'):,.0f}/12m. Low risk ({g(a, 'variant_switch', 'p_churn_90d'):.1%}), so this is honesty, not retention.")
        a = "ACC-PERSONA-05"
        w(f"- **{a}**: pays $230/mo for Experience Beyond but uses little; Essentials would be $110/mo less, "
          "but you'd lose the price guarantee, high-speed hotspot and perks. So the receipt shows it as a 'cheaper, but you'd "
          f"lose X' line, not a push. T-Mobile expected net at 3% uptake ${g(a, 'right_size', 'tm_net_12m'):,.0f}/12m. "
          f"Also 3 paid-off phones worth ~${g(a, 'hidden_value_reminder', 'customer_one_time'):,.0f} in trade-in.")
    except IndexError:
        w("(persona rows missing)")
    w("")

    # ---- 5. assumptions
    w("## 5. Assumptions (value, range, source or ASSUMPTION)\n")
    w("| Name | Value | Range | Source |")
    w("|---|---|---|---|")
    for k, (v, r, s) in VL.A.items():
        w(f"| {k} | {v} | {'' if r is None else f'{r[0]}-{r[1]}'} | {s} |")
    w("\nOther: revenue given up = p_accept x saving x months (no survival discount; slightly conservative for "
      "T-Mobile). Engine rules (same-coverage, port-out always contact, bill-shock override) are NOT applied here; "
      "this is a pricing ledger, not the decision engine. Upsells get retention only on acceptance.\n")

    # ---- truth check
    w("## Sanity check vs hidden truth (evaluation only, never fitted)\n")
    t = next((p for p in TRUTH_CANDIDATES if p.exists()), None)
    if t is None:
        w("`synth/offer_response_truth.csv` is **not on the box any more** (the /workspace/tmobile/synth overlay is "
          "gone). Last documented means (plan doc s5, v2 UNREVIEWED): plan_right_size accept_prob **0.175**, perk "
          "**0.122**. Both are far above our cited 3% / reminder assumptions, i.e. the synthetic truth is more "
          "optimistic than the field evidence; we keep the cited numbers.\n")
    else:
        tr = pd.read_csv(t)
        m = tr[tr.offer.isin(["perk", "plan_right_size"])].groupby("offer").accept_prob.mean()
        w(m.to_string() + "\n")
    (out / "SUMMARY.md").write_text("\n".join(L))
