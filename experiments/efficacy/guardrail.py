"""Do-not-contact guardrail + one plain-English line per account. ALL NUMBERS SYNTHETIC (sandbox stub accounts +
simulated labels; not T-Mobile customer data). Rule-based on purpose: our uplift tests on real randomized data could
not reliably find customers who get pushed away by contact, so we do not use a model for that.

Reads (read-only): demo_data/{features,offers,offer_candidates.csv.gz}, harness/offers.py CONFIG is NOT needed,
sandbox tables billing_history / support_interactions / plans via harness.offer_detectors.connect_ro (sqlite mode=ro).
Writes: experiments/efficacy/out/guardrail.csv (account_id, contact_ok, block_reason, why_line; one row per account),
        out/guardrail_detail.csv (same + the fields each decision used), out/guardrail_summary.txt.
Optional input: experiments/efficacy/proactive_contacts.csv (account_id, last_proactive_contact_date). The data has
no outreach log, so without this file the fatigue rule blocks nobody (hook only, no invented data).
Run from the repo root: python experiments/efficacy/guardrail.py   (~2 s)

Rules, highest priority first (see GUARDRAIL.md for sources):
 1 bill_change_no_fix      the 1,412 accounts with a non-'stable' bill-change reason and a bill increase in the last
                           3 billed months: contact only if the message we'd send is a credit that offsets the
                           increase. Otherwise never contact (outreach would point at the increase with no fix).
 2 receipt_only_plan_move  cheaper-plan / plan-variant moves are never sent as outreach; shown on the bill only.
 3 contacted_this_quarter  at most one proactive contact per 90 days (hook; no outreach log in the data).
 4 not_worth_contacting    not picked by the retention-only policy re-picked at a 10% save rate (246 contacts).
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
D = REPO / "demo_data"; OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO / "harness"))
import offer_detectors as det   # connect_ro opens the sandbox strictly read-only

DECIDE_SAVE_RATE = 0.10            # retention-only policy re-picked at this true save rate
FATIGUE_DAYS = 90                  # one proactive contact per quarter
UPSELL = {"step_up", "family_upgrade", "device_upgrade", "home_internet_bundle"}
PLAN_MOVES = {"right_size", "variant_switch"}
# credits that put money back against a higher bill (rule 1 "offer that addresses the change")
OFFSETS = {"bill_shock_price_lock", "loyalty_credit", "care_credit", "care_credit_fix_first", "keep_your_phone"}
TOPIC = {"billing": "billing issue", "device": "phone issue", "plan_change": "plan change issue",
         "network": "coverage issue", "cancellation_inquiry": "account issue"}

# ---------------------------------------------------------------- inputs
feats = pd.read_csv(D / "features.csv").set_index("account_id")
offers = pd.read_csv(D / "offers.csv").set_index("account_id")
cand = pd.read_csv(D / "offer_candidates.csv.gz")
ids = feats.index
assert len(ids) == 5042 and ids.is_unique
conn = det.connect_ro()
AS_OF = pd.Timestamp(str(det.as_of(conn)))
bh = pd.read_sql("select account_id, month, change_cents, change_reason from billing_history", conn)
sup = pd.read_sql("select account_id, interaction_date, topic, resolved from support_interactions", conn)
plans = pd.read_sql("select sku, name, price_guarantee_years, data_cap_gb, hotspot_high_speed_gb, hotspot_unlimited "
                    "from plans", conn).set_index("sku")
conn.close()

# ---------------------------------------------------------------- rule 1 input: the 1,412 bill changes
last3 = sorted(bh.month.unique())[-3:]
bc = bh[bh.month.isin(last3) & (bh.change_reason != "stable") & (bh.change_cents > 0)]
bc_last = bc.sort_values("month").groupby("account_id").last()          # most recent real change
bill_change = pd.Series(ids.isin(bc_last.index), index=ids)
assert bill_change.sum() == 1412, bill_change.sum()

# ---------------------------------------------------------------- open service issue (most recent unresolved, 90d)
sup["interaction_date"] = pd.to_datetime(sup.interaction_date)
op = sup[(sup.resolved == 0) & (sup.interaction_date >= AS_OF - pd.to_timedelta(90, unit="D"))]
open_topic = op.sort_values("interaction_date").groupby("account_id").topic.last().map(TOPIC).reindex(ids)

# ---------------------------------------------------------------- rule 4: retention-only policy re-picked at 10%
# Same accounting as the room's chart check: EV = p * min(1, save_rate * scale) * value - offer_cost - annoyance,
# p = engine score in offers.csv, scale = 10% / the shipped engine's risk-weighted save rate (44.37%).
el = cand[cand.eligible.astype(str) == "True"].copy()
el = el[el.action_code != "do_nothing"]
el["p"] = el.account_id.map(offers.p_churn_90d); el["V"] = el.account_id.map(offers.customer_value_usd)
ch = el[el.is_chosen.astype(str) == "True"]
base_rate = (ch.p * ch.save_rate).sum() / ch.p.sum()
scale = DECIDE_SAVE_RATE / base_rate
rt = el[~el.action_code.isin(UPSELL)].copy()
rt["ev"] = rt.p * np.minimum(1, rt.save_rate * scale) * rt.V - rt.offer_cost - rt.annoyance
pick = rt.sort_values("ev", ascending=False).drop_duplicates("account_id")
pick = pick[pick.ev > 0].set_index("account_id")
assert len(pick) == 246, len(pick)
# Rule 1 applied inside the pick: a bill-change account may only be sent a credit that offsets the increase. If the
# policy's best action is something else, take its best positive-EV offsetting credit instead; if none, no contact.
bc_ids = set(bc_last.index)
pick["swapped_from"] = ""
need = [a for a in pick.index if a in bc_ids and pick.action_code[a] not in OFFSETS]
alt = rt[rt.account_id.isin(need) & rt.action_code.isin(OFFSETS) & (rt.ev > 0)] \
        .sort_values("ev", ascending=False).drop_duplicates("account_id").set_index("account_id")
alt["swapped_from"] = pick.action_code.reindex(alt.index)
policy_ev_total = pick.ev.sum()
pick = pd.concat([pick.drop(index=alt.index), alt[pick.columns]])
n_swapped = len(alt)
assert not pick.action_code.isin(PLAN_MOVES).any()   # the policy never picks a plan move; rule 2 never has to undo one
selected = pd.Series(ids.isin(pick.index), index=ids)
action = pick.action_code.reindex(ids)

# ---------------------------------------------------------------- eligibility facts per account
elig = el.groupby("account_id").action_code.agg(set).reindex(ids).apply(lambda s: s if isinstance(s, set) else set())
has_offset_offer = elig.apply(lambda s: bool(s & OFFSETS))
fix_eligible = elig.apply(lambda s: "fix_first" in s or "care_credit_fix_first" in s)
bsl = el[el.action_code == "bill_shock_price_lock"].set_index("account_id").customer_monthly_delta  # -5 = adds $5/mo

# best plan move for the receipt: prefer one that gives up nothing, then the biggest monthly saving
name2sku = {v: k for k, v in plans.name.items()}
pm = el[el.action_code.isin(PLAN_MOVES)].copy()
pm["to_name"] = pm.reason.str.extract(r"move to (.+?) \(")[0]
pm["to_sku"] = pm.to_name.map(name2sku)
pm["from_sku"] = pm.account_id.map(feats.plan_sku)
def gives_up(r):
    f, t = plans.loc[r.from_sku], plans.loc[r.to_sku]
    nz = lambda x: 0.0 if pd.isna(x) else float(x)
    lost = []
    if nz(t.price_guarantee_years) < nz(f.price_guarantee_years): lost.append("your price guarantee")
    if pd.notna(t.data_cap_gb) and pd.isna(f.data_cap_gb): lost.append("unlimited data")
    if nz(t.hotspot_high_speed_gb) < nz(f.hotspot_high_speed_gb): lost.append("high-speed hotspot")
    return " and ".join(lost[:2])          # at most two items, to keep the line short
assert pm.to_sku.notna().all() and pm.from_sku.notna().all()
pm["gives_up"] = pm.apply(gives_up, axis=1)
pm["saving"] = -pm.customer_monthly_delta
pm = pm.sort_values(["gives_up", "saving"], key=lambda s: s.ne("") if s.name == "gives_up" else -s) \
       .drop_duplicates("account_id").set_index("account_id")
has_plan_move = pd.Series(ids.isin(pm.index), index=ids)

# ---------------------------------------------------------------- rule 3 hook: proactive-contact log
pc_path = HERE / "proactive_contacts.csv"
recent_contact = pd.Series(False, index=ids)
if pc_path.exists():
    pc = pd.read_csv(pc_path, parse_dates=["last_proactive_contact_date"]).set_index("account_id")
    d = pc.last_proactive_contact_date.reindex(ids)
    recent_contact = (AS_OF - d).dt.days.lt(FATIGUE_DAYS).fillna(False)

# ---------------------------------------------------------------- decide
def money(cents):
    c = abs(cents)
    return f"${c / 100:,.2f}" if c < 1000 else f"${c / 100:,.0f}"

def bill_phrase(a):
    r = bc_last.loc[a]; amt = money(r.change_cents)
    return {"promo_expired": f"Your bill went up {amt} when a promo ended",
            "device_installment": f"Your bill went up {amt} with a new phone payment",
            "installment_ended": f"Your bill went up {amt} recently"}.get(r.change_reason, f"Your bill went up {amt}")

def receipt_phrase(a):
    r = pm.loc[a]; s = f"${r.saving:,.0f}/mo"
    if r.gives_up:
        return f"A plan {s} cheaper is on your bill; it gives up {r.gives_up}, so we won't push it."
    return f"A plan with the same features for {s} less is on your bill. Switch only if you want to."

def contact_line(a):
    act = action[a]; t = open_topic.get(a); bc_ = bill_change[a]
    issue = t if isinstance(t, str) else None
    if act == "bill_shock_price_lock":
        extra = " and $5 off a month" if bsl.get(a, 0) < 0 else ""
        return f"{bill_phrase(a)}. Here's a one-time $25 credit{extra} to help offset it."
    if act == "loyalty_credit":
        if bc_: return f"{bill_phrase(a)}. Here's $5 off each month to help offset it."
        return f"Thanks for {int(feats.tenure_months[a] // 12)} years with us. Here's $5 off each month."
    if act == "keep_your_phone":
        if bc_: return f"{bill_phrase(a)}. Keep your paid-off phone and get $20 off a month for 6 months."
        return "Your phone is paid off. Keep it and get $20 off a month for 6 months."
    if act == "care_credit_fix_first":
        what = f"your open {issue}" if issue else "your recent issue"
        if bc_: return f"{bill_phrase(a)}. We'll call to fix {what} and add a one-time $25 credit."
        return f"We'll call to fix {what} first, and a one-time $25 credit is on us for the hassle."
    if act == "care_credit":
        if issue and fix_eligible[a]:
            return f"We're following up to fix your open {issue}, and a one-time $25 credit is on us for the trouble."
        if bc_: return f"{bill_phrase(a)}. A one-time $25 credit is on us for the recent trouble."
        return "Sorry for the recent trouble with your account. A one-time $25 credit is on us."
    if act == "fix_first":
        what = f"your open {issue}" if issue else "your recent support request"
        return f"We'd like to call and get {what} fixed. No sales pitch, no plan change."
    if act == "check_in":
        return "A quick check that your plan still fits how you use it. Nothing changes unless you ask."
    if act == "perk_reminder":
        return "Your plan already includes a streaming perk. Here's how to turn it on, at no extra cost."
    raise ValueError(act)

rows = []
for a in ids:
    bc_, sel = bool(bill_change[a]), bool(selected[a])
    issue = open_topic.get(a); issue = issue if isinstance(issue, str) else None
    if sel and bc_ and action[a] not in OFFSETS:
        reason = "bill_change_no_fix"
    elif not sel and bc_ and not has_offset_offer[a]:
        reason = "bill_change_no_fix"
    elif not sel and has_plan_move[a]:
        reason = "receipt_only_plan_move"
    elif recent_contact[a]:
        reason = "contacted_this_quarter"
    elif not sel:
        reason = "not_worth_contacting"
    else:
        reason = ""
    if reason == "":
        line = contact_line(a)
    elif reason == "bill_change_no_fix":
        gu = pm.gives_up.get(a, "")
        tail = ((f" A cheaper plan is on your bill; it gives up {gu}." if gu else
                 " A lower-cost plan option is on your bill if you want it.") if has_plan_move[a]
                else " We have no offer that lowers it right now, so we won't message you about it.")
        line = bill_phrase(a) + "." + tail
    elif reason == "receipt_only_plan_move":
        line = receipt_phrase(a)
    elif reason == "contacted_this_quarter":
        line = "We already reached out this quarter, so we'll hold off on more messages until next quarter."
    else:
        line = ("Nothing we'd offer right now beats leaving your account as is. Your open "
                f"{issue} stays with support." if issue else
                "Nothing we'd offer right now beats leaving your account as is.")
    rows.append(dict(account_id=a, contact_ok=reason == "", block_reason=reason, why_line=line,
                     bill_change_reason=bc_last.change_reason.get(a, ""), bill_change_usd=(bc_last.change_cents.get(a, 0) or 0) / 100,
                     policy_selected=sel, policy_action=action[a] if sel else "",
                     policy_ev_usd=round(pick.ev.get(a, 0.0), 2), has_offset_offer=bool(has_offset_offer[a]),
                     receipt_plan_move=bool(has_plan_move[a]), receipt_saving_mo=pm.saving.get(a, 0.0),
                     receipt_gives_up=pm.gives_up.get(a, ""), open_issue_topic=issue or "",
                     p_churn_90d=offers.p_churn_90d[a], data_note="synthetic/simulated"))
G = pd.DataFrame(rows)
G["swapped_from"] = G.account_id.map(pick.swapped_from).fillna("")

# ---------------------------------------------------------------- checks + write
assert len(G) == 5042 and G.account_id.is_unique
assert (G.why_line.str.len() <= 140).all(), G.loc[G.why_line.str.len() > 140, "why_line"].tolist()[:5]
bad = G.why_line.str.contains(r"income|job|kid|child|tailor|persona|ACC-|TMO-|PROMO-|STUB|sandbox|\$0(?![.,]\d)",
                                   case=False)
assert not bad.any(), G.loc[bad, "why_line"].unique()[:8]
assert (G.contact_ok == (G.block_reason == "")).all()
G[["account_id", "contact_ok", "block_reason", "why_line"]].to_csv(OUT / "guardrail.csv", index=False)
G.to_csv(OUT / "guardrail_detail.csv", index=False)

ok = G[G.contact_ok]; B = G[bill_change.values]
lines = ["Guardrail summary. ALL NUMBERS SYNTHETIC (stub accounts, simulated labels; not T-Mobile customer data).",
         f"Accounts: {len(G):,}   as_of {AS_OF.date()}   bill-change window {last3[0]}..{last3[-1]}",
         f"Policy: retention-only, re-picked at {DECIDE_SAVE_RATE:.0%} save rate (scale {scale:.4f} = 10% / {base_rate:.4f}): "
         f"{selected.sum()} selected, policy EV ${policy_ev_total:,.0f}",
         f"Rule 1 swaps: {n_swapped} bill-change accounts moved from a non-offsetting action to their best positive-EV "
         f"offsetting credit (EV after swaps ${pick.ev.sum():,.0f})",
         "", f"contact_ok True: {G.contact_ok.sum():,}   False: {(~G.contact_ok).sum():,}",
         f"contacted EV kept ${ok.policy_ev_usd.sum():,.0f} of ${policy_ev_total:,.0f} "
         f"(blocked selected accounts carried ${G[G.policy_selected & ~G.contact_ok].policy_ev_usd.sum():,.0f})",
         "", "block_reason counts:"]
lines += [f"  {k or '(contact ok)':<24} {v:,}" for k, v in G.block_reason.value_counts().items()]
lines += ["", f"The {len(B):,} bill-change accounts (non-'stable' reason, increase > 0):",
          f"  contacted {B.contact_ok.sum():,}   blocked {(~B.contact_ok).sum():,}"]
lines += [f"    {k or '(contact ok)':<24} {v:,}" for k, v in B.block_reason.value_counts().items()]
lines += ["  by bill-change reason (contacted / total):"]
lines += [f"    {r:<20} {g.contact_ok.sum():>4} / {len(g):,}" for r, g in B.groupby("bill_change_reason")]
lines += ["", "Selected by the policy but blocked: " + ", ".join(
    f"{k}: {v}" for k, v in G[G.policy_selected & ~G.contact_ok].block_reason.value_counts().items()),
          "Contacted, by action: " + ", ".join(f"{k}: {v}" for k, v in ok.policy_action.value_counts().items()),
          f"Contacted accounts that also get a receipt plan line: {int(ok.receipt_plan_move.sum())}",
          f"Fatigue hook: {'log found' if pc_path.exists() else 'no proactive-contact log in the data; rule blocks nobody'}",
          f"why_line length: max {G.why_line.str.len().max()}, mean {G.why_line.str.len().mean():.0f}",
          "", "10 example rows:"]
ex = pd.concat([G[G.block_reason == r].head(2 if r else 3) for r in ["", "bill_change_no_fix", "receipt_only_plan_move",
                                                                   "not_worth_contacting", "contacted_this_quarter"]]).head(10)
for _, r in ex.iterrows():
    lines.append(f"  {r.account_id}  ok={r.contact_ok!s:<5} {r.block_reason or '-':<24} {r.why_line}")
(OUT / "guardrail_summary.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
