"""Moment Replay (tm-offers, v2): decide WHEN, not just WHAT. ALL CUSTOMERS AND NUMBERS ARE SYNTHETIC.

For each account: act_now (the engine's current pick), wait_until <month> (a strictly better offer becomes eligible
on a date we can read from the account's OWN sandbox fields), or stay_silent.

Dated fields (sandbox, read-only):
  lines.financing_months_remaining    -> month the phone is paid off
  lines.device_purchase_date          -> month a phone reaches a promo's min_device_age_months (12 / 36)
  accounts.tenure_months              -> month tenure reaches a promo's min_tenure_months (6 / 36)
Every other field (usage, bills, support, Model A risk) is HELD CONSTANT at the as-of date (assumption), with ONE
exception (v2): for a care credit that is blocked today ONLY by promotions.min_tenure_months, the 90-day support
window is re-counted at the future date from the dated support_interactions rows (contacts roll out; no new contacts
are invented) and days_since_bill_shock is aged. That is the only "genuine wait" allowed for a windowed action.

Cost of waiting: our synthetic labels carry NO churn timing, so the chance of losing the customer before the moment
is a constant monthly hazard h = 1 - (1 - p_churn_90d)^(1/3) (ASSUMPTION, scaled by WAIT["hazard_scale"]).
Wait wins only if the future best action was NOT eligible now, EV_later > EV_now, and EV_later x S(m) - EV_now > 0,
with S(m) = (1 - h)^m. Problem-solving actions (fix-first / care credit) and port-out inquiries never wait.

Live events: apply_event(row, event) re-decides one account (real-field events: bill_spike, payoff_reached,
unresolved_support; simulated, labelled: outage, price_notice). tm-models owns the event feed.

Contact cap: <= 1 scheduled text per account in the horizon (so <= 1 per account per week). The sandbox has no shared
household id, so this is PER ACCOUNT, not per real household. Optional weekly $ budget for credits. The optimizer is
tm-models' scipy.optimize.milp formulation (scratch_models/proofloop/milp_opt.py: <=1 row per account, linear budget
rows, HiGHS) and their greedy baseline (best row per account, ranked by EV, filled while it fits), ported here as
functions because their script runs end-to-end at import time on out-of-repo inputs.

Run:  TM_OUT_DIR=<dir with features/churn_scores/...> python harness/moment_replay.py --out /tmp/v2_moment_out
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offers as eng  # noqa: E402
import offer_detectors as det  # noqa: E402

WAIT = {
    "horizon_months": 6,     # look this far ahead for dated moments
    "hazard_scale": 1.0,     # ASSUMPTION sensitivity: multiplies the constant monthly hazard from p_churn_90d
    "weeks_per_month": 4.345,
}
NEVER_WAIT = set(eng.PROBLEM_ACTIONS)   # something is broken: fix it now
# never a WAIT target: eligibility rests on a rolling 90-day window (support contacts / bill shock) that will have
# rolled off by the moment, and we hold those fields constant, so the date would be invented
WINDOWED_ACTIONS = {"care_credit", "care_credit_fix_first", "bill_shock_price_lock", "fix_first"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# which dated field is the natural reason for which future action
ACTION_TRIGGERS = {
    "device_upgrade": ("payoff", "device_age"), "keep_your_phone": ("payoff",), "family_upgrade": ("payoff", "device_age"),
    "loyalty_credit": ("tenure",), "care_credit": ("tenure",), "care_credit_fix_first": ("tenure",),
    "bill_shock_price_lock": ("tenure",),
}


def month_label(as_of, m: int) -> str:
    y, mo = as_of.year + (as_of.month - 1 + m) // 12, (as_of.month - 1 + m) % 12
    return f"{MONTHS[mo]} {y}"


def monthly_hazard(p90: float) -> float:
    h = 1 - (1 - min(max(float(p90), 0.0), 0.999)) ** (1 / 3)
    return min(1.0, h * WAIT["hazard_scale"])


def survival(p90: float, m: int) -> float:
    return (1 - monthly_hazard(p90)) ** m


# --------------------------------------------------------------------------------------------- dated facts
@dataclass
class Context:
    df: pd.DataFrame          # engine-prepared accounts (index account_id)
    lines: pd.DataFrame       # sandbox lines + device_age_m
    promos: pd.DataFrame
    plans: pd.DataFrame
    as_of: object
    support: pd.DataFrame | None = None   # sandbox support_interactions (dated), for the tenure-gated credit wait


def load_context() -> Context:
    df, cat, conn, _ = eng.prepare(write_line_tradein=False)
    today = det.as_of(conn)
    lines = pd.read_sql("SELECT line_id, account_id, device_sku, device_purchase_date, financing_months_remaining, "
                        "monthly_installment_cents, tradein_eligible FROM lines", conn)
    pdate = pd.to_datetime(lines["device_purchase_date"])
    lines["device_age_m"] = [det.months_between(d.date(), today) if pd.notna(d) else np.nan for d in pdate]
    sup = pd.read_sql("SELECT account_id, interaction_date, topic, sentiment, resolved FROM support_interactions", conn)
    sup["interaction_date"] = pd.to_datetime(sup["interaction_date"])
    return Context(df.set_index("account_id", drop=False), lines, cat["promotions"], cat["plans"], today, sup)


TENURE_GATED_CREDITS = ("care_credit", "care_credit_fix_first")


def support_window_at(sup: pd.DataFrame, as_of, m: int) -> dict:
    """90-day support counts at as_of + m months, from EXISTING dated contacts only (none invented)."""
    end = pd.Timestamp(as_of) + pd.DateOffset(months=m)
    s = sup[(sup["interaction_date"] >= end - pd.Timedelta(days=90)) & (sup["interaction_date"] <= end)] \
        if sup is not None and len(sup) else pd.DataFrame(columns=["topic", "sentiment", "resolved"])
    net = s[s.topic == "network"]
    return {"support_90d": len(s), "unresolved_90d": int((s.resolved == 0).sum()),
            "neg_contacts_90d": int((s.sentiment < 0).sum()), "network_90d": len(net),
            "network_unresolved_90d": int((net.resolved == 0).sum())}


def tenure_gated_row(row: pd.Series, lines, sup, as_of, m: int) -> pd.Series:
    """Account at month m for the tenure-gated care-credit check: dated fields + rolled support window + aged shock."""
    r = row_as_of(row, lines, m)
    r.update(pd.Series(support_window_at(sup, as_of, m)))
    if pd.notna(row.get("days_since_bill_shock")):
        r["days_since_bill_shock"] = row["days_since_bill_shock"] + (
            (pd.Timestamp(as_of) + pd.DateOffset(months=m)) - pd.Timestamp(as_of)).days
    return r


def tenure_thresholds(promos) -> list[int]:
    return sorted({int(v) for v in promos["min_tenure_months"].dropna()})


def device_age_thresholds(promos) -> list[int]:
    return sorted({int(v) for v in promos["min_device_age_months"].dropna()} | {det.UPGRADE_MIN_DEVICE_AGE_MONTHS})


def moments(row: pd.Series, lines: pd.DataFrame, promos, H: int) -> dict[int, list[dict]]:
    """month offset -> dated events from the account's own fields (1..H)."""
    ev: dict[int, list[dict]] = {}
    for _, ln in lines.iterrows():
        f = int(ln["financing_months_remaining"] or 0)
        if 1 <= f <= H:
            ev.setdefault(f, []).append({"kind": "payoff", "line_id": ln["line_id"],
                                         "field": f"financing_months_remaining={f}", "text": "phone paid off"})
        if pd.notna(ln["device_purchase_date"]) and pd.notna(ln["device_age_m"]):
            for t in device_age_thresholds(promos):
                m = t - int(ln["device_age_m"])
                if 1 <= m <= H:
                    ev.setdefault(m, []).append({"kind": "device_age", "line_id": ln["line_id"],
                                                 "field": f"device_purchase_date={ln['device_purchase_date']} "
                                                          f"(reaches {t} months)",
                                                 "text": f"phone turns {t} months old"})
    ten = int(row["tenure_months"])
    for t in tenure_thresholds(promos):
        m = t - ten
        if 1 <= m <= H:
            ev.setdefault(m, []).append({"kind": "tenure", "line_id": "",
                                         "field": f"tenure_months={ten} (reaches {t})",
                                         "text": f"{t} months with us"})
    return ev


def row_as_of(row: pd.Series, lines: pd.DataFrame, m: int, paid_off_lines: set | None = None) -> pd.Series:
    """The account as of month offset m: only the three dated fields move; everything else held constant."""
    r = row.copy()
    if m == 0 and not paid_off_lines:
        return r
    ln = lines.copy()
    f = (ln["financing_months_remaining"].fillna(0) - m).clip(lower=0)
    if paid_off_lines:
        f[ln["line_id"].isin(paid_off_lines)] = 0
    age = ln["device_age_m"] + m
    has_dev = ln["device_sku"].notna()
    ready = has_dev & (ln["tradein_eligible"] == 1) & (age >= det.UPGRADE_MIN_DEVICE_AGE_MONTHS) & (f == 0)
    r["max_financing_months_left"] = int(f.max()) if len(f) else 0
    r["any_paid_off_device"] = bool((has_dev & (f == 0)).any())
    r["n_upgrade_ready_lines"] = int(ready.sum())
    r["n_old_upgrade_lines"] = int((ready & (age >= det.OLD_DEVICE_MONTHS)).sum())
    if pd.notna(row.get("oldest_device_age_m")):
        r["oldest_device_age_m"] = row["oldest_device_age_m"] + m
    r["um_old_device"] = bool((r.get("oldest_device_age_m") or 0) >= det.OLD_DEVICE_MONTHS)
    r["any_payoff_soon"] = bool(f.between(1, det.PAYOFF_SOON_MONTHS).any())
    if pd.notna(row.get("contract_or_financing_months_remaining")):
        r["contract_or_financing_months_remaining"] = max(0, row["contract_or_financing_months_remaining"] - m)
    r["tenure_months"] = int(row["tenure_months"]) + m
    return r


# --------------------------------------------------------------------------------------------- decision
def _pick(res: dict, row: pd.Series):
    pm = eng.PLAN_MOVES if eng.CONFIG.get("PLAN_MOVES_RECEIPT_ONLY") else ()
    po = bool(row["port_out_inquiry"] == 1)
    if po and not eng.port_out_allowed():     # PORT_OUT_CONTACT=off: no outreach on a port-out inquiry
        return "do_nothing", 0.0
    a, evv, _, _ = eng.pick(res, port_out=po, exclude=pm,
                            open_ticket=bool((row.get("unresolved_90d", 0) or 0) >= 1))
    return a, float(evv)


def decide(row: pd.Series, lines: pd.DataFrame, promos, plans, as_of, H: int | None = None,
           paid_off_lines: set | None = None, sup: pd.DataFrame | None = None) -> dict:
    H = WAIT["horizon_months"] if H is None else H
    base = row_as_of(row, lines, 0, paid_off_lines)
    now = eng.evaluate_account(base, promos, plans)["res"]
    a0, ev0 = _pick(now, base)
    out = {"account_id": row["account_id"], "p_churn_90d": float(row["p_churn_90d"]), "now_action": a0,
           "now_ev": round(ev0, 2), "decision": "", "when": "now", "action": a0, "ev": round(ev0, 2),
           "wait_months": 0, "wait_action": "", "wait_ev": np.nan, "wait_ev_discounted": np.nan,
           "survival_to_moment": 1.0, "dated_field": "", "reason_type": "", "reason": "", "data_note": "synthetic"}
    po = bool(row["port_out_inquiry"] == 1)
    forced = a0 in NEVER_WAIT or (po and eng.CONFIG["PORT_OUT_ALWAYS_CONTACT"] and eng.port_out_allowed())
    if po and not eng.port_out_allowed():   # no outreach now or later on a port-out inquiry (PORT_OUT_CONTACT=off)
        out.update(decision="stay_silent", when="", reason_type="port_out_off", next_moment="", next_moment_action="",
                   next_moment_field="", reason="Stay silent: they asked about porting out; no outreach on that signal "
                                                "until the port-out policy is decided (synthetic).")
        return out
    best, follow = None, None
    mom = moments(base, lines, promos, H)
    for m in sorted(mom):
        fut_row = row_as_of(row, lines, m, paid_off_lines)
        fut = eng.evaluate_account(fut_row, promos, plans)["res"]
        # offers UNLOCKED by the date: eligible then, not now, not resting on a rolling 90-day window, EV > 0
        new = [(a, v["ev"]) for a, v in fut.items() if a != "do_nothing" and a not in WINDOWED_ACTIONS
               and not (eng.CONFIG.get("PLAN_MOVES_RECEIPT_ONLY") and a in eng.PLAN_MOVES)
               and v["eligible"] and not now.get(a, {}).get("eligible") and v["ev"] > 0]
        # v2 genuine wait: care credit blocked today ONLY by min_tenure_months, eligible at a tenure moment with the
        # support window re-counted from dated contacts
        if sup is not None and any(e["kind"] == "tenure" for e in mom[m]):
            gated = [a for a in TENURE_GATED_CREDITS if not now.get(a, {}).get("eligible")
                     and "tenure" in str(now.get(a, {}).get("detail", ""))]
            if gated:
                tg = eng.evaluate_account(tenure_gated_row(row, lines, sup, as_of, m), promos, plans)["res"]
                new += [(a, tg[a]["ev"]) for a in gated if tg[a]["eligible"] and tg[a]["ev"] > 0]
        if not new:
            continue
        af, evf = max(new, key=lambda t: t[1])
        trig = [e for e in mom[m] if e["kind"] in ACTION_TRIGGERS.get(af, ())] or mom[m]
        if follow is None:
            follow = (m, af, evf, trig[0])
        disc = evf * survival(row["p_churn_90d"], m)
        if not forced and evf > ev0 and disc - ev0 > 0 and (best is None or disc > best[2]):
            best = (m, af, disc, evf, trig[0])
    out.update(next_moment="", next_moment_action="", next_moment_field="")
    if follow is not None and best is None:   # informational: the next dated moment after today's decision
        out.update(next_moment=month_label(as_of, follow[0]), next_moment_action=follow[1],
                   next_moment_field=follow[3]["field"])
    if best is not None:
        m, af, disc, evf, trig = best
        lbl = month_label(as_of, m)
        out.update(decision="wait_until", when=lbl, action=af, ev=round(disc, 2), wait_months=m, wait_action=af,
                   wait_ev=round(evf, 2), wait_ev_discounted=round(disc, 2),
                   survival_to_moment=round(survival(row["p_churn_90d"], m), 4), dated_field=trig["field"],
                   reason_type=f"wait_{trig['kind']}",
                   reason=(f"Wait until {lbl}: {trig['text']} ({trig['field']}); then {eng.ACTION_LABEL[af]} "
                           f"is worth ${evf:.2f} (${disc:.2f} after the {1 - survival(row['p_churn_90d'], m):.1%} "
                           f"assumed chance they leave first) vs ${ev0:.2f} now (synthetic)."))
    elif a0 == "do_nothing":
        out.update(decision="stay_silent", when="", reason_type="silent",
                   reason=f"Stay silent: no offer beats doing nothing now or on any dated moment in the next {H} "
                          f"months (risk {row['p_churn_90d']:.1%}, synthetic).")
    else:
        why = ("something is broken, so we fix it now" if a0 in NEVER_WAIT else
               "they asked about leaving, so we never wait" if forced else
               "no dated moment in their account unlocks a better offer")
        out.update(decision="act_now", reason_type="act_now_forced" if forced else "act_now",
                   reason=f"Act now: {eng.ACTION_LABEL[a0]} (EV ${ev0:.2f}); {why} (synthetic).")
    return out


def replay(ctx: Context, accounts=None) -> pd.DataFrame:
    rows = []
    g = ctx.lines.groupby("account_id")
    sup_g = ctx.support.groupby("account_id") if ctx.support is not None else None
    empty = ctx.lines.iloc[0:0]
    for aid in (accounts if accounts is not None else ctx.df.index):
        row = ctx.df.loc[aid]
        ln = g.get_group(aid) if aid in g.groups else empty
        sg = sup_g.get_group(aid) if sup_g is not None and aid in sup_g.groups else \
            (ctx.support.iloc[0:0] if ctx.support is not None else None)
        rows.append(decide(row, ln, ctx.promos, ctx.plans, ctx.as_of, sup=sg))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------- live events
REAL_EVENTS = {"bill_spike", "payoff_reached", "unresolved_support"}
SIMULATED_EVENTS = {"outage", "price_notice"}


def apply_event(row: pd.Series, event: dict, lines: pd.DataFrame, promos, plans, as_of) -> dict:
    """Re-decide one account after a live event. Real-field events mirror sandbox fields (billing_history,
    lines.financing_months_remaining, support_interactions); simulated events are labelled simulated.
    Model A is not re-run here: pass event['p_churn_90d'] if the feed re-scored the account."""
    kind = event.get("type")
    if kind not in REAL_EVENTS | SIMULATED_EVENTS:
        raise ValueError(f"unknown event {kind!r}; real: {sorted(REAL_EVENTS)}, simulated: {sorted(SIMULATED_EVENTS)}")
    r = row.copy()
    paid = None
    if kind == "bill_spike":                       # billing_history: a bill rise the customer didn't cause
        r["bill_increase_pct"] = max(float(r["bill_increase_pct"]), float(event.get("pct", det.BILL_SHOCK_PCT)))
        r["days_since_bill_shock"] = 0
    elif kind == "payoff_reached":                 # lines.financing_months_remaining -> 0
        ids = event.get("line_ids") or lines.loc[lines["financing_months_remaining"].fillna(0) > 0, "line_id"].tolist()
        paid = set(ids)
    elif kind == "unresolved_support":             # support_interactions: an unresolved contact
        cat = event.get("category", "billing")
        r["support_90d"] = int(r["support_90d"]) + 1
        r["unresolved_90d"] = int(r["unresolved_90d"]) + 1
        r["neg_contacts_90d"] = int(r["neg_contacts_90d"]) + 1
        col = {"network": "network_90d", "device": "device_90d", "billing": "billing_90d"}.get(cat)
        if col:
            r[col] = int(r[col]) + 1
        if cat == "network":
            r["network_unresolved_90d"] = int(r.get("network_unresolved_90d", 0) or 0) + 1
    elif kind == "outage":                         # SIMULATED: no outage table in the sandbox
        r["network_90d"] = int(r["network_90d"]) + 1
        r["network_unresolved_90d"] = int(r.get("network_unresolved_90d", 0) or 0) + 1
    elif kind == "price_notice":                   # SIMULATED: no price-change table in the sandbox
        r["bill_increase_pct"] = max(float(r["bill_increase_pct"]), float(event.get("pct", 0.10)))
        r["days_since_bill_shock"] = 0
    if "p_churn_90d" in event:
        r["p_churn_90d"] = float(event["p_churn_90d"])
    d = decide(r, lines, promos, plans, as_of, paid_off_lines=paid)
    d["event"] = kind
    d["event_source"] = "simulated" if kind in SIMULATED_EVENTS else "real sandbox field"
    return d


# --------------------------------------------------------------------------------------------- cap + budget
def options_table(ctx: Context, decisions: pd.DataFrame, max_alt: int = 3) -> pd.DataFrame:
    """Scheduling options per account: up to max_alt eligible positive-EV actions now (week 0) plus the wait option
    (week of the moment, discounted EV). credit_usd = expected credit spend (callbacks are not credits)."""
    rows = []
    for _, d in decisions.iterrows():
        aid = d["account_id"]
        row = ctx.df.loc[aid]
        res = eng.evaluate_account(row, ctx.promos, ctx.plans)["res"]
        po = bool(row["port_out_inquiry"] == 1)
        if po and not eng.port_out_allowed():
            continue                      # PORT_OUT_CONTACT=off: never scheduled
        # forced CONTACT (must be scheduled, now): port-out save attempt (when allowed) or open-ticket fix-first
        has_ticket = bool((row.get("unresolved_90d", 0) or 0) >= 1)
        open_t = bool(eng.CONFIG["FIX_FIRST_FORCE"] == "all_open" and has_ticket
                      and d["now_action"] in ("fix_first", "care_credit_fix_first"))
        forced = bool(((po and eng.CONFIG["PORT_OUT_ALWAYS_CONTACT"]) or open_t) and d["now_action"] != "do_nothing")
        pm = eng.PLAN_MOVES if eng.CONFIG.get("PLAN_MOVES_RECEIPT_ONLY") else ()
        if forced and open_t and not po:   # either fix-first variant may be scheduled; one is mandatory
            cands = [(a, res[a]) for a in ("care_credit_fix_first", "fix_first") if res[a]["eligible"]]
        elif forced:   # only the forced action, scheduled now
            cands = [(d["now_action"], res[d["now_action"]])]
        else:
            cands = sorted(((a, v) for a, v in res.items() if a != "do_nothing" and a not in pm
                            and (not has_ticket or a in ("fix_first", "care_credit_fix_first"))   # fix-first only
                            and v["eligible"] and v["ev"] > 0), key=lambda t: -t[1]["ev"])[:max_alt]
        for a, v in cands:
            rows.append(_opt(aid, 0, a, v["ev"], v["cost"], forced))
        if d["decision"] == "wait_until":
            fut = row_as_of(row, ctx.lines[ctx.lines.account_id == aid], int(d["wait_months"]))
            v = eng.evaluate_account(fut, ctx.promos, ctx.plans)["res"][d["wait_action"]]
            wk = int(round(d["wait_months"] * WAIT["weeks_per_month"]))
            rows.append(_opt(aid, wk, d["wait_action"], d["wait_ev_discounted"], v["cost"], False))
    return pd.DataFrame(rows)


def _opt(aid, week, a, ev, cost, forced):
    credit = 0.0
    if a in eng.CREDIT_ACTIONS:
        credit = float(cost) - (eng.CONFIG["FIX_FIRST_CALLBACK_COST"] if a == "care_credit_fix_first" else 0.0)
    return {"account_id": aid, "week": week, "action": a, "ev": float(ev), "credit_usd": max(0.0, credit),
            "forced": bool(forced)}


def _budget_exempt(opts: pd.DataFrame) -> np.ndarray:
    """Forced rows that are their account's ONLY option (port-out save attempt) spend outside the credit budget;
    forced accounts with a choice (open ticket: fix-first $0 vs care credit + fix-first) count against it."""
    n_opt = opts.groupby("account_id")["account_id"].transform("size").values
    return opts["forced"].values.astype(bool) & (n_opt == 1)


def solve_milp(opts: pd.DataFrame, max_contacts: int | None = None, weekly_credit_budget: float | None = None):
    """tm-models' formulation: max sum EV x, x binary, <= 1 option per account (the per-account contact cap),
    optional total contact cap, optional per-week credit budget. Returns a boolean mask over opts."""
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import csr_matrix
    n = len(opts)
    if n == 0:
        return np.zeros(0, bool)
    ai = pd.factorize(opts["account_id"])[0]
    forced = opts["forced"].values.astype(bool)
    # forced account: exactly one of its options (open-ticket accounts may pick fix-first or care credit + fix-first)
    lo = np.zeros(ai.max() + 1)
    lo[np.unique(ai[forced])] = 1
    cons = [LinearConstraint(csr_matrix((np.ones(n), (ai, np.arange(n))), shape=(ai.max() + 1, n)), lo, 1)]
    exempt = _budget_exempt(opts)
    if max_contacts is not None:   # the contact cap counts non-forced contacts (forced port-out contacts always go)
        cons.append(LinearConstraint(csr_matrix((~forced).astype(float)[None, :]), 0, max_contacts))
    if weekly_credit_budget is not None:
        wk = pd.factorize(opts["week"])[0]
        # forced port-out contacts spend outside the budget (they go regardless); budget = discretionary credits
        A = csr_matrix((opts["credit_usd"].values * (~exempt), (wk, np.arange(n))), shape=(wk.max() + 1, n))
        cons.append(LinearConstraint(A, 0, weekly_credit_budget))
    r = milp(-opts["ev"].values, constraints=cons, integrality=np.ones(n), bounds=Bounds(0, 1),
             options={"mip_rel_gap": 1e-9, "time_limit": 120})
    assert r.status == 0, r.message
    return np.round(r.x).astype(bool)


def greedy(opts: pd.DataFrame, max_contacts: int | None = None, weekly_credit_budget: float | None = None):
    """tm-models' greedy: each account's single best option by EV; accounts ranked by that EV; filled while it fits."""
    x = np.zeros(len(opts), bool)
    if len(opts) == 0:
        return x
    o2 = opts.reset_index(drop=True).assign(_ex=_budget_exempt(opts))
    srt = o2.sort_values(["account_id", "ev"], ascending=[True, False])
    best = srt.groupby("account_id").head(1)
    best = best.assign(_f=best["forced"].astype(bool)).sort_values(["_f", "ev"], ascending=[False, False], kind="stable")
    spent: dict = {}
    k = 0
    for i, o in best.iterrows():
        if o["_f"]:   # forced contacts go first, outside the contact cap; best forced option that fits the budget
            for j, f in srt[srt.account_id == o["account_id"]].iterrows():
                if (f["_ex"] or weekly_credit_budget is None
                        or spent.get(f["week"], 0.0) + f["credit_usd"] <= weekly_credit_budget + 1e-9):
                    x[j] = True
                    if not f["_ex"]:
                        spent[f["week"]] = spent.get(f["week"], 0.0) + f["credit_usd"]
                    break
            continue
        if max_contacts is not None and k >= max_contacts:
            continue
        if weekly_credit_budget is not None and spent.get(o["week"], 0.0) + o["credit_usd"] > weekly_credit_budget + 1e-9:
            continue
        x[i] = True
        spent[o["week"]] = spent.get(o["week"], 0.0) + o["credit_usd"]
        k += 1
    return x


def schedule_compare(opts: pd.DataFrame, max_contacts=None, weekly_credit_budget=None) -> dict:
    o = opts.reset_index(drop=True)
    xm, xg = solve_milp(o, max_contacts, weekly_credit_budget), greedy(o, max_contacts, weekly_credit_budget)
    return {"max_contacts": max_contacts, "weekly_credit_budget": weekly_credit_budget,
            "milp_ev": round(float(o.ev[xm].sum()), 2), "greedy_ev": round(float(o.ev[xg].sum()), 2),
            "milp_contacts": int(xm.sum()), "greedy_contacts": int(xg.sum()),
            "milp_waits": int((o.week[xm] > 0).sum()), "greedy_waits": int((o.week[xg] > 0).sum()),
            "max_per_account_milp": int(o[xm].groupby("account_id").size().max() if xm.any() else 0),
            "data_note": "synthetic"}


# --------------------------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Moment Replay (synthetic)")
    ap.add_argument("--out", default="/tmp/v2_moment_out")
    ap.add_argument("--hazard-scale", type=float, default=None)
    args = ap.parse_args(argv)
    if args.hazard_scale is not None:
        WAIT["hazard_scale"] = args.hazard_scale
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ctx = load_context()
    dec = replay(ctx)
    dec.to_csv(out / "moment_decisions.csv", index=False)
    print(dec.decision.value_counts().to_string())
    print(dec.reason_type.value_counts().to_string())
    opts = options_table(ctx, dec)
    opts.to_csv(out / "moment_options.csv", index=False)
    cmp = [schedule_compare(opts, max_contacts=k) for k in (100, 300, 500)]
    cmp += [schedule_compare(opts, weekly_credit_budget=b) for b in (250, 500, 1000, 2500)]
    pd.DataFrame(cmp).to_csv(out / "moment_cap_compare.csv", index=False)
    print(pd.DataFrame(cmp).to_string(index=False))
    print(f"wrote {out}/moment_decisions.csv ({len(dec)} rows). ALL NUMBERS SYNTHETIC.")
    return dec


if __name__ == "__main__":
    main()
