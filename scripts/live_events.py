"""Precompute the scripted 'what if this happens next' strip for one customer (offline; the app only reads the CSV).

Each event changes a few of that customer's input fields, cumulatively. After every event we:
  1. rescore churn risk with the same Model A the app uses (harness/churn_scorer.score_account, demo_data inputs),
  2. rerun the offer engine on that one row (harness/offers.choose, current code, same frame offers.prepare builds),
  3. rerun the do-not-contact guardrail over the WHOLE book with only this customer's rows swapped
     (experiments/engine_rules/guardrail_rule.run_guardrail, policy retention10, save-rate scale frozen at the value
     that produced the shipped 184-contact set, so no other account can move),
  4. map the result to the on-screen decision the same way harness/decisions_out.py does (fix-first when an issue is
     open, its reason sentences).
Nothing is written to sandbox.db (opened read-only; new support/bill rows are added to in-memory copies only), to
demo_data/ or to harness/out (temp dirs). Deterministic: no randomness is used (SEED kept for the record).
Numbers are synthetic; that label stays out of the CSV's on-screen text columns (David's rule).

Run from the repo root:  DUBHACKS_DB=/path/to/sandbox.db python3 scripts/live_events.py [--account ACC-...]
Writes data/live_events/live_events.csv and, per step, the sidecar data/live_events/live_events_steps.json:
  inputs_changed  model-input fields this event changed: [{field, old, new}] (old = value before this event)
  engine_changed  engine-frame fields this event changed: [{field, old, new}] (old = None when the field was unset)
  inputs_now      every model-input field changed so far vs the start, with its current value (cumulative edits)
  intercept       Model A's intercept (logit)
  contributions   Model A's full per-signal logit contributions for this row ({feature: logit})
  groups          the same, summed by reason group (what reason_changed is chosen from)
  risk            the rescored risk (same value as the CSV's risk column, unrounded)
All of these are values the script already computes; nothing is added or estimated.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEED = 2026
_TMP = Path(tempfile.mkdtemp(prefix="live_events_"))
for f in ("features.csv", "enrichment.csv", "churn_scores.csv", "labels.csv"):
    shutil.copy(ROOT / "demo_data" / f, _TMP / f)
os.environ["TM_OUT_DIR"] = str(_TMP)          # offers.prepare reads/writes here, never harness/out
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT))

import churn_scorer as cs  # noqa: E402
import offers as eng  # noqa: E402
import decisions_out as dout  # noqa: E402
from experiments.engine_rules import guardrail_rule as GR  # noqa: E402
from experiments.engine_rules.apply_rules import _db_path, connect_ro  # noqa: E402

cs.OUT = _TMP                                  # scorer cache to temp, nothing written in the repo
OUT_CSV = ROOT / "data" / "live_events" / "live_events.csv"
OUT_STEPS = ROOT / "data" / "live_events" / "live_events_steps.json"
DECISIONS = ROOT / "data" / "decisions" / "decisions.csv"


class StepZeroMismatch(AssertionError):
    pass
SUMMARY = json.loads((ROOT / "experiments/engine_rules/out/demo/summary.json").read_text())["guardrail"]
FROZEN_SCALE = float(SUMMARY["save_rate_scale"])   # the scale behind the shipped 184; frozen so no other row moves
SHIPPED_GUARD = ROOT / "experiments/engine_rules/out/demo/guardrail_detail.csv"

# ---- the script: (key, short label, plain line, feature edits fn, engine edits fn, support rows to add)
# feature edits act on demo_data/features.csv columns (the churn model's inputs); engine edits on offers.prepare's
# frame (same facts under the engine's column names). Both are applied cumulatively.


def _inc(d, k, n=1):
    d[k] = (d.get(k, 0) or 0) + n


def ev_app(f, e):
    _inc(f, "app_sessions_30d", 1); _inc(e, "app_sessions_30d", 1)


def ev_drop(f, e):     # dropped call -> support chat about coverage, still open
    for k in ("support_90d", "support_270d", "unresolved_90d", "unresolved_270d", "network_contacts_90d",
              "negative_contacts_90d"):
        _inc(f, k)
    n90 = max(int(f["support_90d"]), 1)
    f["avg_sentiment_90d"] = round(((n90 - 1) * float(f.get("avg_sentiment_90d", 0) or 0) - 0.6) / n90, 4)
    f["min_sentiment_270d"] = min(float(f.get("min_sentiment_270d", 0) or 0), -0.6)
    f["days_since_last_contact"] = 0
    for k in ("support_90d", "unresolved_90d", "network_90d", "network_unresolved_90d", "neg_contacts_90d"):
        _inc(e, k)
    e["avg_sentiment_90d"] = f["avg_sentiment_90d"]


def ev_bill(f, e):     # next bill comes in higher (not a new phone)
    last = float(f["last_bill_cents"])
    new = round(last * 1.18)
    prior = float(f.get("prior_avg_bill_cents") or last)
    f["last_bill_cents"] = new
    f["bill_increase_pct"] = round(new / prior - 1, 4) if prior else 0.18
    f["bill_change_3m_pct"] = max(float(f.get("bill_change_3m_pct", 0) or 0), f["bill_increase_pct"])
    _inc(f, "bill_changes_12m")
    e["last_bill_cents"] = new
    e["bill_increase_pct"] = f["bill_increase_pct"]
    e["days_since_bill_shock"] = 0


def ev_comp(f, e):     # carrier-shopping score rises (a field in the account data)
    v = max(float(f.get("competitor_research_score", 0) or 0), 0.8)
    f["competitor_research_score"] = v; e["competitor_research_score"] = v


def ev_port(f, e):     # asks how to move their number
    f["port_out_inquiry"] = 1; e["port_out_inquiry"] = 1


# every engine-frame field an event function writes (seeded from the real row in run_path)
ENGINE_FIELDS = ("app_sessions_30d", "support_90d", "unresolved_90d", "network_90d", "network_unresolved_90d",
                 "neg_contacts_90d", "avg_sentiment_90d", "last_bill_cents", "bill_increase_pct", "days_since_bill_shock",
                 "competitor_research_score", "port_out_inquiry")

EVENTS = {
    "app":  ("Logged into the app", "Opened the app to check their usage.", ev_app, None),
    "drop": ("Dropped call", "A call dropped, and their support chat about coverage is still open.", ev_drop,
             "network"),
    "bill": ("Bill went up", "Their next bill came in about 18% higher.", ev_bill, None),
    "comp": ("Carrier-shopping score up", "Their score for comparing other carriers jumped from 0.21 to 0.80.", ev_comp, None),
    "port": ("Asked to move their number", "They asked how to move their number to another carrier.", ev_port,
             None),
}


class World:
    """Loaded once: the engine frame, the guardrail's book-wide inputs, and the sandbox (read-only, in memory)."""

    def __init__(self):
        self.df, self.cat, conn, _ = eng.prepare(write_line_tradein=False)
        conn.close()
        # The shipped guardrail (184) was run on demo_data/offer_candidates, whose save rates are on the BASE table
        # (pre-field-scaling); the guardrail then applies its own frozen 10%-field scale. So the engine rerun here uses
        # the base table too (FIELD_SAVE_RATE = anchor, perk reminder on its base row); otherwise the field scaling
        # would be applied twice. Step 0 is checked against the shipped candidate rows below.
        eng.apply_field_save_rate(eng.CONFIG["SAVE_RATE_ANCHOR"])
        eng.CONFIG["SAVE_RATE"]["perk_reminder"] = dict(eng.CONFIG["SAVE_RATE_BASE"]["perk_reminder"])
        dd = ROOT / "demo_data"
        self.offers = pd.read_csv(dd / "offers.csv").set_index("account_id")
        self.cand = pd.read_csv(dd / "offer_candidates.csv.gz")
        self.feats_g = pd.read_csv(dd / "features.csv").set_index("account_id").reindex(self.offers.index)
        self.feats_m = pd.read_csv(dd / "features.csv").set_index("account_id")
        con = connect_ro(_db_path())
        self.sandbox = GR.load_sandbox(con)
        self.contact_pref = dict(pd.read_sql("SELECT account_id, contact_preference FROM accounts", con).values)
        con.close()
        k = int(round(eng.CONFIG["UPSELL_GUARD_TOP_RISK_SHARE"] * len(self.df)))
        self.decile_cut = self.df.sort_values(["p_churn_90d", "account_id"], ascending=[False, True]) \
            .p_churn_90d.iloc[k - 1]
        self.df.index = pd.Index(list(self.df.account_id))
        self.base_G, self.base_sum = self.guardrail()

    def guardrail(self, offers=None, cand=None, feats=None, sandbox=None):
        return GR.run_guardrail(feats if feats is not None else self.feats_g,
                                offers if offers is not None else self.offers,
                                cand if cand is not None else self.cand, sandbox or self.sandbox,
                                GR.GuardrailConfig(rule="new", value_scale=GR.V_SCALE_1478,
                                                   save_rate_scale=FROZEN_SCALE, policy="retention10"))


def grouped_contrib(f: dict, aid: str):
    """Model A's per-reason-group logit contributions for this row (same grouping as its explain()), plus the raw row
    used to word them. Mirrors churn_scorer.score_account's table swap."""
    import churn_model as cm
    st = cs._load()
    base = st["feats"].set_index("account_id")
    new = base.loc[aid].copy()
    for k, v in f.items():
        if k in new.index:
            new[k] = v
    table = base.copy()
    table.loc[aid] = new
    table = table.reset_index().rename(columns={"index": "account_id"})
    X = cs.prepare(table)
    C = st["model"].contributions(X.loc[[aid]])
    G = C.T.groupby([cm.reason_group(c) for c in C.columns]).sum().T.iloc[0]
    G = G.drop([c for c in G.index if c in cm.NON_REASON_GROUPS])
    return G, table[table.account_id == aid].set_index("account_id").iloc[0], C.iloc[0], float(st["model"].intercept_)


def decision_for(aid: str, g: pd.Series, chan_pref: str, offers_row: pd.Series) -> dict:
    """decisions_out.build's mapping, for one guardrail row (open issue -> fix-first; same reason sentences)."""
    chan = dout.CHANNEL.get(str(chan_pref), "text")
    topic = g.open_issue_topic if isinstance(g.open_issue_topic, str) and g.open_issue_topic else ""
    pol = g.policy_action if isinstance(g.policy_action, str) else ""
    if bool(g.contact_ok):
        conv = bool(topic) and pol not in dout.FIX and pol != "bill_shock_price_lock"
        offer = "fix_first" if conv else pol
        label = dict(eng.ACTION_LABEL).get(offer, offer)
        if offer in dout.FIX and chan != "call":
            label = label.replace("fix-first callback", "fix-first message")
        return {"pick": "message", "pick_code": offer, "pick_label": label, "channel": chan,
                "why": dout.msg_reason(offer, chan, conv)}
    br = g.block_reason
    if br == "bill_change_no_fix":
        why = ("Bill rose after a new phone payment, and nothing we have offsets it." if "phone" in str(g.why_line)
               else "Bill rose recently, and nothing we have offsets it.")
    elif br == "receipt_only_plan_move":
        why = "No message; the cheaper plan shows on the bill and in the app."
    elif str(offers_row.get("already_leaving_save_attempt", "")).startswith("already leaving"):
        why = "They asked about leaving, and a check-in isn't likely to pay off."
    else:
        why = "No message, since nothing we could offer is likely to pay off."
    return {"pick": "silent", "pick_code": "do_nothing", "pick_label": "Do nothing", "channel": "none", "why": why}


def _plain(v):
    """JSON-safe scalar (numpy -> python; NaN -> None)."""
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v.item() if hasattr(v, "item") else v


def _diff(before: dict, after: dict) -> list[dict]:
    return [{"field": k, "old": _plain(before.get(k)), "new": _plain(after[k])}
            for k in after if _plain(before.get(k)) != _plain(after[k])]


def options_for(aid: str, d: dict, g: pd.Series, c1: pd.DataFrame) -> list[dict]:
    """decisions_out.build's 'options weighed' rows for one account (do nothing first), from this step's engine
    candidates and decision. Same wording and order as data/decisions/options.csv."""
    lab = dict(eng.ACTION_LABEL)
    strict = set(pd.read_csv(dout.STRICT_RECEIPT).account_id) if dout.STRICT_RECEIPT.exists() else set()
    trade = set(pd.read_csv(dout.TRADEOFF_RECEIPT).account_id) if dout.TRADEOFF_RECEIPT.exists() else set()
    line, tline = aid in strict, aid in trade
    ok, offer, chan = d["pick"] == "message", d["pick_code"] if d["pick"] == "message" else "", d["channel"]
    open_t = isinstance(g.open_issue_topic, str) and bool(g.open_issue_topic)
    out = [{"option_label": "Do nothing", "verdict": "not_sent" if ok else "picked",
            "reason": "Baseline: no message, no cost." if ok else dout.money_free(dout.clean(d["why"])), "net_mid_usd": 0.0}]
    seen = False
    for _, c in c1.sort_values("expected_value", ascending=False).iterrows():
        a = c.action_code
        if a == "do_nothing":
            continue
        olab = lab.get(a, a)
        if a in dout.FIX and chan != "call":
            olab = olab.replace("fix-first callback", "fix-first message")
        if str(c.eligible) != "True":
            out.append({"option_label": olab, "verdict": "ruled_out", "reason": dout.plain_reason(c.blocked_or_ineligible_reason),
                        "net_mid_usd": None})
            continue
        ev = float(c.expected_value)
        if a == offer:
            v, why, seen = "picked", "Sent.", True
        elif a in eng.PLAN_MOVES:
            v, why = "not_sent", ("Shown on the bill only: same features, lower price." if line
                                  else "Shown on the bill with what they'd lose." if tline
                                  else "Not suggested: not a like-for-like match." if not line
                                  else "Plan changes are shown on the bill, never sent as a message.")
        elif open_t and a not in dout.FIX:
            v, why = "not_sent", "Open support issue: only a fix message is allowed."
        elif ev <= 0:
            v, why = "not_sent", "Expected to cost more than it brings back."
        elif ok:
            v, why = "not_sent", "One message per account; another option was sent."
        else:
            v, why = "not_sent", "Didn't pass the outreach rules for a message."
        out.append({"option_label": olab, "verdict": v, "reason": why, "net_mid_usd": round(ev, 2)})
    if offer and not seen:
        out.append({"option_label": d["pick_label"], "verdict": "picked", "reason": "Sent.", "net_mid_usd": None})
    return out


def message_for(d: dict, aid: str, sup: pd.DataFrame, as_of) -> tuple[str, str]:
    """decisions_out.build's text for a message that has no outreach-card text: the fix-first template for the channel
    and the latest open support topic in the last 90 days (same rule as decisions_out.sandbox_facts, on this step's
    support rows); digital channels never promise a call."""
    if d["pick"] != "message":
        return "", ""
    chan = d["channel"]
    s_ = sup[sup.account_id == aid].copy()
    s_["interaction_date"] = pd.to_datetime(s_.interaction_date)
    op = s_[(s_.resolved.astype(int) == 0) & (s_.interaction_date >= pd.Timestamp(as_of) - pd.Timedelta(days=90))]
    tp = str(op.sort_values("interaction_date").topic.iloc[-1]) if len(op) else "billing"
    m = dout.FIX_EN[chan].format(t=dout.TOPIC_EN.get(tp, "your account")) if chan in dout.FIX_EN else ""
    es = dout.FIX_ES[chan].format(t=dout.TOPIC_ES.get(tp, "su cuenta")) if chan in dout.FIX_ES else ""
    if chan != "call":
        m, es = dout.no_call(m), dout.no_call(es)
    return dout.clean(m), dout.clean(es)


def run_path(W: World, aid: str, keys: list[str], check_book: bool = True, steps_out: list | None = None) -> pd.DataFrame:
    f = W.feats_m.loc[aid].to_dict()
    f0 = dict(f)
    # engine-frame fields the events touch, seeded from this customer's real row in the engine frame (the same frame
    # behind today's decisions.csv), so each event adds to the real value instead of to an empty start
    e = {k: _plain(W.df.loc[aid, k]) for k in ENGINE_FIELDS if k in W.df.columns}
    missing = [k for k in ENGINE_FIELDS if k not in W.df.columns]
    if missing:
        print("engine frame lacks (left unseeded):", missing)
    rows = []
    sup_add = []
    as_of = W.sandbox[0]
    for step, key in enumerate(["start"] + keys):
        if key != "start":
            label, line, fn, topic = EVENTS[key]
            f_before, e_before = dict(f), dict(e)
            fn(f, e)
            if topic:
                sup_add.append({"account_id": aid, "interaction_date": str(as_of.date()), "topic": topic, "resolved": 0})
        p, risks, stays = cs.score_account({**f, "account_id": aid})
        Gc, raw, Cfull, b0 = grouped_contrib(f, aid)
        if steps_out is not None:
            steps_out.append({
                "account_id": aid, "step": step, "event": key,
                "inputs_changed": [] if key == "start" else _diff(f_before, f),
                "engine_changed": [] if key == "start" else _diff(e_before, e),
                "inputs_now": {d["field"]: d["new"] for d in _diff(f0, f)},
                "intercept": b0, "contributions": {k: float(v) for k, v in Cfull.items()},
                "groups": {k: float(v) for k, v in Gc.items()}, "risk": float(p)})
        if step == 0:
            changed, prevG = "", Gc
        else:   # the reason group that moved most this step (up = a risk phrase, down = a stay phrase)
            import churn_model as cm
            dG = (Gc - prevG)
            top = dG.abs().idxmax()
            changed = cm.phrase(top, raw, bool(dG[top] > 0)) if abs(dG[top]) > 1e-6 else ""
            prevG = Gc
        row = W.df.loc[aid].copy()
        for k, v in e.items():
            row[k] = v
        row["p_churn_90d"] = p
        for i in range(3):
            row[f"risk_reason_{i+1}"] = risks[i] if i < len(risks) else ""
            row[f"stay_reason_{i+1}"] = stays[i] if i < len(stays) else ""
        row["top_churn_decile"] = bool(p >= W.decile_cut)
        o1, c1 = eng.choose(pd.DataFrame([row]), W.cat["promotions"], W.cat["plans"])
        o1 = o1.set_index("account_id")
        if step == 0 and check_book:   # unmodified row: the rerun must reproduce the shipped retention candidates
            keys = ["action_code", "save_rate", "offer_cost", "annoyance"]
            a_ = W.cand[(W.cand.account_id == aid) & (W.cand.eligible.astype(str) == "True")
                        & ~W.cand.action_code.isin(GR.UPSELL | {"do_nothing"})][keys].sort_values("action_code")
            b_ = c1[c1.eligible & ~c1.action_code.isin(GR.UPSELL | {"do_nothing"})][keys].sort_values("action_code")
            assert list(a_.action_code) == list(b_.action_code), (list(a_.action_code), list(b_.action_code))
            for k in keys[1:]:
                assert (a_[k].astype(float).round(4).values == b_[k].astype(float).round(4).values).all(), (k, a_, b_)
            assert abs(p - float(W.offers.loc[aid, "p_churn_90d"])) < 1e-4, (p, W.offers.loc[aid, "p_churn_90d"])
        offers = W.offers.copy()
        for c in ("p_churn_90d", "customer_value_usd", "action_code", "pick_override", "already_leaving_save_attempt"):
            if c in o1.columns and c in offers.columns:
                offers.loc[aid, c] = o1.loc[aid, c]
        cand = pd.concat([W.cand[W.cand.account_id != aid], c1[[c for c in c1.columns if c in W.cand.columns]]],
                         ignore_index=True)
        AS_OF, bh, sup, plans = W.sandbox
        if sup_add:
            sup = pd.concat([sup, pd.DataFrame(sup_add)], ignore_index=True)
        if key == "bill" or "bill" in keys[:step]:
            bh = bh.copy()
            last_m = sorted(bh.month.unique())[-1]
            m = (bh.account_id == aid) & (bh.month == last_m)
            add = int(round(f["last_bill_cents"] - W.feats_m.loc[aid, "last_bill_cents"]))
            if m.any():
                bh.loc[m, "change_cents"] = bh.loc[m, "change_cents"].clip(lower=0) + add
                bh.loc[m, "change_reason"] = bh.loc[m, "change_reason"].where(
                    bh.loc[m, "change_reason"] != "stable", "promo_expired")
        G, gs = W.guardrail(offers=offers, cand=cand, sandbox=(AS_OF, bh, sup, plans))
        G = G.set_index("account_id")
        if check_book:
            others = G.index != aid
            base = W.base_G.set_index("account_id")
            assert (G.loc[others, "contact_ok"] == base.loc[G.index[others], "contact_ok"]).all(), "another row moved"
            assert int(base.loc[G.index[others], "contact_ok"].sum()) + int(base.loc[aid, "contact_ok"]) == 184
        d = decision_for(aid, G.loc[aid], W.contact_pref.get(aid, ""), o1.loc[aid])
        opts = options_for(aid, d, G.loc[aid], c1)
        if steps_out is not None:
            gr = G.loc[aid]
            steps_out[-1].update({
                "rules": {"action_code": _plain(o1.loc[aid, "action_code"]),
                          "do_nothing_reason": _plain(o1.loc[aid].get("do_nothing_reason")),
                          "policy_selected": _plain(gr.get("policy_selected")), "block_reason": _plain(gr.block_reason),
                          "contact_ok": _plain(gr.contact_ok), "open_issue_topic": _plain(gr.open_issue_topic)},
                "decision": {"decision": d["pick"], "channel": d["channel"], "decision_reason": d["why"],
                             "offer_label": d["pick_label"] if d["pick"] == "message" else "",
                             **dict(zip(("message_en", "message_es"), message_for(d, aid, sup, AS_OF)))},
                "policy_ev_usd": _plain(gr.policy_ev_usd), "options": opts})
        if step == 0 and DECISIONS.exists():   # step 0 must reproduce today's decision file exactly
            dr = pd.read_csv(DECISIONS).set_index("account_id").loc[aid]
            want = ("message" if dr.decision == "message" else "silent", str(dr.channel), str(dr.decision_reason))
            got = (d["pick"], d["channel"], d["why"])
            if got != want:
                raise StepZeroMismatch(f"{aid}: step 0 {got} != decisions.csv {want}")
            OPTS = ROOT / "data" / "decisions" / "options.csv"
            if OPTS.exists():
                oc = pd.read_csv(OPTS)
                oc = oc[oc.account_id == aid]
                a_ = [(x.option_label, x.verdict, x.reason) for x in oc.itertuples()]
                b_ = [(x["option_label"], x["verdict"], x["reason"]) for x in opts]
                if a_ != b_:
                    raise StepZeroMismatch(f"{aid}: step 0 options differ from options.csv: {a_} vs {b_}")
        rows.append({"step": step, "event": key, "event_label": "" if key == "start" else EVENTS[key][0],
                     "event_line": "" if key == "start" else EVENTS[key][1],
                     "risk": round(p, 4), "reason_1": risks[0] if risks else "",
                     "reason_2": risks[1] if len(risks) > 1 else "", "reason_3": risks[2] if len(risks) > 2 else "",
                     "reason_changed": changed, "engine_pick": o1.loc[aid, "action_code"], "policy_action": G.loc[aid, "policy_action"],
                     "policy_ev_usd": float(G.loc[aid, "policy_ev_usd"]), "block_reason": G.loc[aid, "block_reason"],
                     **d})
    P = pd.DataFrame(rows)
    # reason_changed: the Model A reason group that moved most at this step, worded by Model A's own phrase()
    P.insert(0, "account_id", aid)
    for c in ("why", "event_line"):
        bad = [x for x in P[c] if dout.reason_problem(x, call_ok=True)]
        assert not bad, (c, bad)
        assert not P[c].str.contains(dout.FORBIDDEN).any(), c
    return P


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="ACC-02363")
    ap.add_argument("--events", default="app,drop,comp,port")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    W = World()
    print("baseline guardrail contact_ok:", W.base_sum["contact_ok"])
    shipped = pd.read_csv(SHIPPED_GUARD).set_index("account_id")
    bg = W.base_G.set_index("account_id")
    print("matches shipped guardrail:", bool((bg.contact_ok == shipped.contact_ok.reindex(bg.index)).all()))
    steps = []
    P = run_path(W, a.account, a.events.split(","), steps_out=steps)
    P["inputs_changed"] = [",".join(d["field"] for d in s_["inputs_changed"]) for s_ in steps]
    pd.set_option("display.width", 250)
    print(P.to_string())
    if a.write:
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        P.to_csv(OUT_CSV, index=False)
        OUT_STEPS.write_text(json.dumps(steps, indent=1) + "\n")
        print("wrote", OUT_CSV, OUT_STEPS)


if __name__ == "__main__":
    main()
