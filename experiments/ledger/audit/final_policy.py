"""Per-account money ledger (tm-design column spec, final) + events.csv. ALL NUMBERS SYNTHETIC (docs say so;
no output string says it, per David's rule). Read-only inputs: committed guardrail + detail (v2-efficacy engine_rules/out/demo),
outreach_card.csv (TM-Dubhacks26 docs/outreach; v2-efficacy has none), events.build_events (sandbox opened mode=ro),
base.py economics. Open-ticket rule (team 23:33): a contacted account with an open ticket
(unresolved_90d >= 1) whose action is perk_reminder gets the engine's fix-first message instead (cost $15, annoyance $4,
save rate 0.35 before the 10%/44.4% scaling); fix-first types are unchanged. The total is NOT forced to $4,109."""
import sys, json, re, numpy as np, pandas as pd
"""(moved here from ledger.py so the audits can import the final policy)"""
from model import *
ER = Path("/workspace/tmobile/v2-efficacy/experiments/engine_rules")
CARD = Path("/workspace/tmobile/v2-efficacy/docs/outreach/outreach_card.csv")
if not CARD.exists(): CARD = Path("/workspace/tmobile/TM-Dubhacks26/docs/outreach/outreach_card.csv")
g = pd.read_csv(ER / "out/demo/guardrail.csv"); gd = pd.read_csv(ER / "out/demo/guardrail_detail.csv").set_index("account_id")
card = pd.read_csv(CARD)
assert len(card) == 5042 and set(card.account_id) == set(g.account_id)
assert set(g[g.contact_ok].account_id) == set(PICKS.account_id)
card_ch = card.outreach_reason.str.extract(r"Sent as: ([a-z -]+)")[0].str.strip()
n_text = int((card_ch[card.account_id.isin(PICKS.account_id)] == "text").sum())
assert n_text == 64, n_text

# ---------- open-ticket rule
P = PICKS.copy()
unres = P.account_id.map(feats.unresolved_90d).fillna(0).values
swap = (unres >= 1) & (P.action_code.values == "perk_reminder")
ff = CANDS[CANDS.action_code == "fix_first"].set_index("account_id")
before = acct(P, s(0.10)).copy()
rows = []
for i in np.where(swap)[0]:
    a = P.iloc[i].account_id
    if a in ff.index: r = ff.loc[a].copy()
    else:   # not an eligible candidate row: build it from the engine's fix-first terms
        r = P.iloc[i].copy(); r["save_rate"], r["offer_cost"], r["annoyance"] = 0.35, 15.0, 4.0
    r["action_code"] = "fix_first"; r["account_id"] = a; rows.append((i, r))
for i, r in rows:
    for c in ("action_code", "save_rate", "offer_cost", "annoyance"): P.iloc[i, P.columns.get_loc(c)] = r[c]
after_swap = acct(P, s(0.10)).copy()

# ---------- costing.
# HEADLINE / conservative (team ruling 23:39): every fix-first contact (incl. care credit + fix-first) pays agent time
# whatever the channel: $10.75 per live contact + $4.25 escalation = $15.00 (research14), plus the channel's own send cost:
# text $0.013, in-app $0, email $0.0001. Agent CALLS pay the engine's $15 callback ONLY (it is the same agent contact +
# escalation; adding $10.75+$4.25 on top would count the agent twice). $25 credit and $4 annoyance unchanged.
# SELF-SERVE (Q&A only, 23:37 version): only calls pay $15; digital fix-first pays the send cost only.
# harness/offers.py (tm-offers-v2 a20b2dd) has no per-channel costs, so send costs come from research14 (RESEARCH s14a).
AGENT = 10.75 + 4.25
SEND = {"agent call": 0.0, "text": 0.013, "in-app message": 0.0, "email": 0.0001}
CH_COST = {"agent call": 15.0, "text": AGENT + 0.013, "in-app message": AGENT, "email": AGENT + 0.0001}
CH_COST_SELF = {"agent call": 15.0, "text": 0.013, "in-app message": 0.0, "email": 0.0001}
CH_SRC = {"agent call": "engine FIX_FIRST_CALLBACK_COST $15 (= agent live contact + escalation; not added twice)",
          "text": "agent $10.75 + escalation $4.25 (research14) + SMS $0.013 (RESEARCH s14a)",
          "in-app message": "agent $10.75 + escalation $4.25 (research14) + push/in-app $0",
          "email": "agent $10.75 + escalation $4.25 (research14) + email $0.0001"}
chan = P.account_id.map(pd.Series(card_ch.values, index=card.account_id)).values
FIXT = np.isin(P.action_code.values, ["fix_first", "care_credit_fix_first"])
credit_part = np.where(P.action_code.values == "care_credit_fix_first", P.offer_cost.values - 15.0, 0.0)
def costed(table):
    Q = P.copy()
    c = np.where(FIXT, credit_part + pd.Series(chan).map(table).values, P.offer_cost.values)
    assert not np.isnan(c).any(); Q["offer_cost"] = c; return Q
P_ALL15 = P.copy()                      # every fix-first a $15 call (23:33 version, +$3,939)
P_SELF = costed(CH_COST_SELF)           # self-serve fix (Q&A only)
P = costed(CH_COST)                     # HEADLINE
after = acct(P, s(0.10)); after_self = acct(P_SELF, s(0.10))
FIX_BY_CH = pd.crosstab(pd.Series(chan[FIXT], name="channel"), pd.Series(P.action_code.values[FIXT], name="action"))

