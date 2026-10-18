"""Per-account money ledger (tm-design column spec, final) + events.csv. ALL NUMBERS SYNTHETIC (docs say so;
no output string says it, per David's rule). Read-only inputs: committed guardrail + detail (v2-efficacy engine_rules/out/demo),
outreach_card.csv (TM-Dubhacks26 docs/outreach; v2-efficacy has none), events.build_events (sandbox opened mode=ro),
base.py economics. Open-ticket rule (Grok Bot / tm-design 23:33): a contacted account with an open ticket
(unresolved_90d >= 1) whose action is perk_reminder gets the engine's fix-first message instead (cost $15, annoyance $4,
save rate 0.35 before the 10%/44.4% scaling); fix-first types are unchanged. The total is NOT forced to $4,109."""
import sys, json, re, numpy as np, pandas as pd
from final_policy import *
import final_policy as FP
SW = pd.DataFrame(dict(account_id=P.account_id.values[swap], before_action="perk_reminder", after_action="fix_first",
                       net_mid_before=before[swap].round(2), net_mid_after_all_calls=after_swap[swap].round(2),
                       net_mid_after=after[swap].round(2), net_mid_after_self_serve=after_self[swap].round(2)))
SW.to_csv(HERE / "out" / "open_ticket_swap.csv", index=False)
X = arrays(P)
mid = net_acc(X, CENTRAL); TOTAL_MID = round(float(mid.sum()), 0)
low = net_acc(X, dict(CENTRAL, save_rate=0.05, value_low=1.0), low="surv")
high = net_acc(X, dict(CENTRAL, save_rate=0.22))
print(f"open-ticket swap: {swap.sum()} perk reminders -> fix-first; their mid net {before[swap].sum():,.0f} -> {after_swap[swap].sum():,.0f} (all calls) -> {after[swap].sum():,.0f} (conservative) / {after_self[swap].sum():,.0f} (self-serve); "
      f"total over 184: {before.sum():,.0f} -> {after_swap.sum():,.0f} -> {TOTAL_MID:,.0f}")

def money(v): return f"-${abs(v):,.0f}" if v < 0 else f"+${v:,.0f}"
po = feats.port_out_inquiry.reindex(g.account_id).fillna(0).astype(int).values.astype(bool)
REASON = {"promo_expired": "when a promo ended", "device_installment": "for a new phone payment",
          "installment_ended": "after a phone payment plan changed"}
ACT = dict(zip(P.account_id, P.action_code))
def note(a, ok, br):
    d = gd.loc[a]; rs = d.bill_change_reason if isinstance(d.bill_change_reason, str) else ""
    topic = d.open_issue_topic if isinstance(d.open_issue_topic, str) else ""
    if ok:
        act = ACT.get(a, "")
        if rs and bool(d.blocking_bill_change):
            if act in OFFSETS: return f"Bill went up {REASON[rs]}, so the message comes with a credit that offsets it."
            t = f"open {topic}" if topic else "open issue"
            return f"Bill went up {REASON[rs]}, so the message only offers to fix their {t}, with no sales pitch."
        if rs == "device_installment": return "Bill went up for a new phone payment they chose, so that doesn't hold a message back."
        if topic: return f"Their open {topic} comes first, so the message offers to fix it."
        if rs: return f"Bill went up {REASON[rs]}, and the message offers help with it."
        return "No recent bill rise or open issue stands in the way of a message."
    if br == "bill_change_no_fix": return f"Bill went up {REASON.get(rs, 'recently')} and we have nothing that offsets it, so we stay quiet."
    if br == "receipt_only_plan_move": return "A cheaper plan fits, so it shows on the bill instead of in a message."
    return "Nothing we could send is likely to be worth it, so we stay quiet."
L = pd.DataFrame({"account_id": card.account_id.values})
L = L.merge(g, on="account_id", how="left")
L["guardrail_result"] = np.where(L.contact_ok, "pass", "blocked")
L["guardrail_note"] = [note(a, ok, br) for a, ok, br in zip(L.account_id, L.contact_ok, L.block_reason)]
L["save_rate_low"], L["save_rate_mid"], L["save_rate_high"] = 0.05, 0.10, 0.22
M = pd.DataFrame({"account_id": X["ids"], "net_low_usd": low.round(2), "net_mid_usd": mid.round(2), "net_high_usd": high.round(2)})
M["why_low"] = [f"If only 1 in 20 people about to leave stay, and stay fewer months: {money(v)}." for v in low]
M["why_mid"] = [f"If 1 in 10 people about to leave stay (our planning case): {money(v)}." for v in mid]
M["why_high"] = [f"Upper bound, above published results: if 22 in 100 people about to leave stay, {money(v)}." for v in high]
L = L.merge(M, on="account_id", how="left")
for c in ("net_low_usd", "net_mid_usd", "net_high_usd"): L[c] = L[c].fillna(0.0)
nomsg = "No message, so nothing is spent or counted."
for c in ("why_low", "why_mid", "why_high"): L[c] = L[c].fillna(nomsg)
L["already_leaving"] = L.account_id.map(feats.port_out_inquiry).fillna(0).astype(int).eq(1).values; po = L.already_leaving.values
L["already_leaving_note"] = np.where(po, "Asked us about moving their number to another carrier, so this account is counted on its own line, not in money saved.", "")
L["in_holdout"] = L.holdout.astype(bool)
L["timing"] = np.where(L.contact_ok, np.where(L.timing.eq("wait"), "wait", "now"), "")
L["wait_until"] = L.wait_until.fillna("")
COLS = ["account_id", "guardrail_result", "guardrail_note", "save_rate_low", "save_rate_mid", "save_rate_high",
        "net_low_usd", "net_mid_usd", "net_high_usd", "why_low", "why_mid", "why_high",
        "already_leaving", "already_leaving_note", "in_holdout", "timing", "wait_until"]
L = L[COLS]
# ---------- checks
assert len(L) == 5042 and L.account_id.is_unique and list(L.account_id) == list(card.account_id)
assert (L.guardrail_result == "pass").sum() == 184
assert round(L.loc[L.guardrail_result == "pass", "net_mid_usd"].sum()) == TOTAL_MID, "mid total mismatch"
assert (L.loc[L.in_holdout, "guardrail_result"] == "pass").all()
BAD = re.compile(r"synthetic|simulat|sandbox|/workspace|\.py|\.csv|tm-|grok|david|ACC-|EV\b|guardrail", re.I)
txt = L.select_dtypes(object).drop(columns=["account_id"]).astype(str)
assert not txt.apply(lambda s: s.str.contains(BAD)).any().any(), "forbidden word in an output string"
L.to_csv(HERE / "ledger.csv", index=False)

# ---------- events.csv (past events only, newest first, up to 3 per account)
sys.path.insert(0, str(ER))
import events as EV
E = EV.build_events(str(db), 12)   # TM-Dubhacks26 sandbox, opened mode=ro
E = E[pd.to_datetime(E.date) <= pd.Timestamp("2026-10-01")].copy()
def etext(r):
    if r.event_type == "bill_spike":
        m = re.search(r"\$([\d.]+) -> \$([\d.]+)", r.value); up = float(m.group(2)) - float(m.group(1))
        return f"bill up ${up:,.0f}"
    if r.event_type == "unresolved_support":
        m = re.search(r": ([^/]+)/([^,]+),", r.value); topic = m.group(2).replace("_", " ") if m else "support"
        return f"{topic} ticket opened, still open"
    return r.event_type.replace("_", " ")
E["event_text"] = [etext(r) for r in E.itertuples()]
E["event_type"] = E.event_type.map({"bill_spike": "bill_up", "unresolved_support": "open_ticket"}).fillna(E.event_type)
E = E.rename(columns={"date": "event_date"}).sort_values(["account_id", "event_date"], ascending=[True, False])
E = E.groupby("account_id").head(3)[["account_id", "event_date", "event_type", "event_text"]]
assert set(E.account_id) <= set(L.account_id)
assert not E.event_text.str.contains(BAD).any()
E.to_csv(HERE / "events.csv", index=False)
# ---------- bootstrap (same as ../economics boot: resample all 5,042 accounts, true churn p, Bernoulli churn x save)
POS = pd.Series(np.arange(N_ALL), index=ids)
def boot(sel, tr, B=2000, seed=2026):
    rng = np.random.default_rng(seed); sc = s(tr); pi = POS.loc[sel.account_id].values
    p = sel.p_true.values; srr = np.minimum(1, sel.save_rate.values * sc); V = sel.V.values
    fixed = sel.offer_cost.values + sel.annoyance.values; real_b = np.empty(B)
    for b in range(B):
        idx = rng.integers(0, N_ALL, N_ALL); cnt = np.bincount(idx, minlength=N_ALL)[pi]; m = cnt > 0
        reps = np.repeat(np.arange(len(pi))[m], cnt[m])
        saved = (rng.random(len(reps)) < p[reps]) & (rng.random(len(reps)) < srr[reps])
        real_b[b] = (saved * V[reps]).sum() - fixed[reps].sum()
    return dict(mean=round(real_b.mean(), 0), lo95=round(np.percentile(real_b, 2.5), 0), hi95=round(np.percentile(real_b, 97.5), 0),
                p_pos=round(float((real_b > 0).mean()), 3))
b_old = boot(PICKS, 0.10)
assert (b_old["lo95"], b_old["hi95"]) == (-2805.0, 13292.0), b_old    # reproduces the shipped range exactly
def be_stats(Q):
    n0, n1 = acct(Q, 0.0).sum(), acct(Q, 1.0).sum()
    be = float(-n0 / (n1 - n0) * BASE_RATE)                              # same definition as the 4.80%
    sr_be = np.minimum(1, Q.save_rate.values * s(be))
    return be, float((Q.p_in.values * sr_be).sum() / Q.p_in.sum()), float(100 * (Q.p_in.values * sr_be).sum() / len(Q))
B10, B5 = boot(P, 0.10), boot(P, 0.05)
BE, BE_EFF_RISKW, BE_SAVES_PER_100 = be_stats(P)
SB10, SB5 = boot(P_SELF, 0.10), boot(P_SELF, 0.05); SBE = be_stats(P_SELF)
XS = arrays(P_SELF)
SELF = dict(label="if the fix is self-serve (Q&A only)", total_mid=round(float(net_acc(XS, CENTRAL).sum()), 0),
            total_low=round(float(net_acc(XS, dict(CENTRAL, save_rate=0.05, value_low=1.0), low="surv").sum()), 0),
            total_high=round(float(net_acc(XS, dict(CENTRAL, save_rate=0.22)).sum()), 0),
            range95_low=SB10["lo95"], range95_high=SB10["hi95"], p_net_pos_at_10=SB10["p_pos"], p_net_pos_at_5=SB5["p_pos"],
            breakeven_save_rate=round(SBE[0], 4), breakeven_effective_per_attempt_riskweighted=round(SBE[1], 4),
            channel_cost_usd=CH_COST_SELF)
assert SELF["total_mid"] == 6428.0, SELF
ALL15 = round(float(acct(P_ALL15, s(0.10)).sum()), 0); assert ALL15 == 3939.0
print("bootstrap 10%", B10, "5%", B5, f"breakeven {BE:.4f}, effective per-attempt (risk-weighted) {BE_EFF_RISKW:.4f}, saves/100 contacts {BE_SAVES_PER_100:.2f}")
S = dict(contacts=184, costing="conservative: agent time on every fix-first contact + channel send cost", total_mid=TOTAL_MID, total_mid_all_fix_first_as_15_calls=ALL15, total_mid_before_open_ticket_rule=round(float(before.sum()), 0),
         open_ticket_swaps=int(swap.sum()), swap_mid_before=round(float(before[swap].sum()), 0), swap_mid_after_all_calls=round(float(after_swap[swap].sum()), 0), swap_mid_after=round(float(after[swap].sum()), 0), swap_mid_after_self_serve=round(float(after_self[swap].sum()), 0),
         total_low=round(float(low.sum()), 0), total_high=round(float(high.sum()), 0),
         already_leaving_in_184=int(L[(L.guardrail_result == "pass") & L.already_leaving].shape[0]),
         mid_already_leaving=round(float(L[(L.guardrail_result == "pass") & L.already_leaving].net_mid_usd.sum()), 0),
         in_holdout=int(L.in_holdout.sum()), mid_holdout=round(float(L[L.in_holdout].net_mid_usd.sum()), 0),
         text_channel_count=n_text, channel_cost_usd=CH_COST, channel_cost_source=CH_SRC,
         fix_first_contacts_by_channel={k: {a: int(v) for a, v in r.items()} for k, r in FIX_BY_CH.iterrows()},
         boot10_mean=B10["mean"], range95_low=B10["lo95"], range95_high=B10["hi95"], p_net_pos_at_10=B10["p_pos"], p_net_pos_at_5=B5["p_pos"],
         boot5_lo95=B5["lo95"], boot5_hi95=B5["hi95"], breakeven_save_rate=round(BE, 4),
         breakeven_effective_per_attempt_riskweighted=round(BE_EFF_RISKW, 4), breakeven_saves_per_100_contacts=round(BE_SAVES_PER_100, 2),
         old_range95=[b_old["lo95"], b_old["hi95"]], self_serve_secondary=SELF, events_rows=len(E), events_accounts=int(E.account_id.nunique()),
         event_types=E.event_type.value_counts().to_dict())
json.dump(S, open(HERE / "ledger_summary.json", "w"), indent=1, default=float); print(json.dumps(S, indent=1, default=float))
