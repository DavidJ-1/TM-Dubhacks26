"""One decision per customer (v2): decision in {text_now, wait_until <YYYY-MM-DD>, receipt_only, silent}.
ALL NUMBERS SYNTHETIC. No LLM. Adds columns to <out>/offers.csv in place (scratch outputs only).

  text_now      the engine texts now (after tm-models' bill-change rule, guardrail_join.bill_rule).
  wait_until    Moment Replay found a GENUINE wait (moment_decisions.csv): a better offer opens on a dated sandbox
                field (today only: a care credit gated by promotions.min_tenure_months) and EV x survival > EV now.
  receipt_only  no text, but the account has a receipt line: tm-models' strict like-for-like plan move (394) or a
                'cheaper, but you'd lose X' line (142) (scratch_models/chart_check/plan_moves_classified.csv;
                tm-offers-ledger receipt.csv tradeoff_line as a cross-check).
  silent        everything else.

Counting (headline): text_now rows that are NOT port-out save attempts. Port-out save attempts (only when
PORT_OUT_CONTACT allows) are reported on their own line and never in the headline count or net. Forced open-ticket
fix-first contacts with EV <= 0 are reported separately in the reconciliation.

Join point: guardrail_join.join() adds tm-models' columns (tmm_contact_ok, tmm_block_reason, ... ) by account_id.
Run: TM_OUT_DIR=<dir> python harness/one_decision.py [--moments <moment_decisions.csv>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guardrail_join as gj  # noqa: E402

MOVES = Path(os.environ.get("TM_PLAN_MOVES_CLASSIFIED",
                            "/workspace/tmobile/scratch_models/chart_check/plan_moves_classified.csv"))
LEDGER_RECEIPT = Path(os.environ.get("TM_LEDGER_RECEIPT", "/tmp/value_ledger/receipt.csv"))
APPLY_BILL_RULE = os.environ.get("TM_ONE_DECISION_BILL_RULE", "1") not in ("0", "false", "False", "")
AS_OF = pd.Timestamp("2026-10-01")   # sandbox metadata.as_of


def receipt_sets() -> dict:
    s = {"strict": set(), "lose_x": set(), "source": []}
    if MOVES.exists():
        m = pd.read_csv(MOVES)
        s["strict"] = set(m.loc[m.receipt_line == "like_for_like", "account_id"])
        s["lose_x"] = set(m.loc[m.receipt_line == "lose_x", "account_id"])
        s["source"].append(str(MOVES))
    if LEDGER_RECEIPT.exists():
        r = pd.read_csv(LEDGER_RECEIPT)
        s["lose_x"] |= set(r.loc[r.tradeoff_line.fillna("") != "", "account_id"])
        s["source"].append(str(LEDGER_RECEIPT))
    return s


def retention_net(o: pd.DataFrame, cands: pd.DataFrame, action_col: str) -> pd.Series:
    """Company retention net per account for the given action: p x save_rate x kept value - offer cost - annoyance
    (same accounting as compare_strategies '5. Ours'; upsell gain excluded)."""
    c = cands.set_index(["account_id", "action_code"])
    out = []
    for aid, a, p, v in zip(o.account_id, o[action_col], o.p_churn_90d, o.customer_value_usd):
        if a == "do_nothing" or (aid, a) not in c.index:
            out.append(0.0)
            continue
        r = c.loc[(aid, a)]
        out.append(float(p * (r.save_rate or 0) * v - (r.offer_cost or 0) - (r.annoyance or 0)))
    return pd.Series(out, index=o.index)


def holdout_on() -> bool:
    """Holdout is a flag column only; it changes the decision only when env TM_HOLDOUT is set (e.g. 0.2)."""
    return bool(os.environ.get("TM_HOLDOUT"))


def decide(o: pd.DataFrame, cands: pd.DataFrame, moments: pd.DataFrame | None, g=None) -> pd.DataFrame:
    """decision in {text_now, wait_until <date>, already_leaving, receipt_only, silent} (+ 'silent (holdout)' only
    when TM_HOLDOUT is set). When tm-models' guardrail is present, contact_ok gates EVERY contact (texts and port-out
    save attempts) and their bill rule is already in it; our own bill_rule() is used only when it is absent."""
    o = o.copy()
    have_g = g is not None and "contact_ok" in g.columns
    if APPLY_BILL_RULE and not have_g:
        br = gj.bill_rule(o, cands, g)
        o["final_action"], o["final_ev"], o["bill_rule_note"] = br.bill_rule_action.values, br.bill_rule_ev.values, \
            br.bill_rule_note.values
    else:
        o["final_action"], o["final_ev"], o["bill_rule_note"] = o.action_code, o.expected_value, ""
    rs = receipt_sets()
    save_attempt = o.get("already_leaving_save_attempt", pd.Series("", index=o.index)).fillna("") != ""
    o.loc[save_attempt, ["final_action", "final_ev"]] = o.loc[save_attempt, ["action_code", "expected_value"]].values
    o = gj.join(o, g)
    ok = o["tmm_contact_ok"].fillna(False).astype(bool) if have_g else pd.Series(True, index=o.index)
    hold = (o["tmm_holdout"].fillna(False).astype(bool) if have_g and "tmm_holdout" in o else
            pd.Series(False, index=o.index))
    wait = {}
    if have_g and "tmm_timing" in o:
        wait = {a: str(d) for a, t, d in zip(o.account_id, o.tmm_timing, o.get("tmm_wait_until", "")) if t == "wait"}
    elif moments is not None and len(moments):
        w = moments[moments.decision == "wait_until"]
        wait = {a: (AS_OF + pd.DateOffset(months=int(m))).date().isoformat()
                for a, m in zip(w.account_id, w.wait_months)}
    contact = (o.final_action != "do_nothing") & ok
    o.loc[~contact, ["final_action", "final_ev"]] = ["do_nothing", 0.0]   # guardrail-blocked picks send nothing
    o["blocked_by_guardrail"] = (o.action_code != "do_nothing") & ~ok
    o["retention_net"] = retention_net(o, cands, "final_action").round(2)
    dec = []
    for aid, c, sa, h in zip(o.account_id, contact, save_attempt, hold):
        if c and h and holdout_on():
            dec.append("silent (holdout)")
        elif c and sa:
            dec.append("already_leaving")
        elif c and aid in wait:
            dec.append(f"wait_until {wait[aid]}")
        elif c:
            dec.append("text_now")
        elif aid in rs["strict"] or aid in rs["lose_x"]:
            dec.append("receipt_only")
        else:
            dec.append("silent")
    o["decision"] = dec
    o["holdout_flag"] = hold.values
    o["receipt_line_kind"] = ["strict_like_for_like" if a in rs["strict"] else "you_d_lose_x" if a in rs["lose_x"]
                              else "" for a in o.account_id]
    k = o.decision.str.split(" ").str[0]
    o["in_headline"] = k.isin(["text_now", "wait_until"])
    return o


UPSELLS = {"step_up", "family_upgrade", "device_upgrade", "home_internet_bundle"}


def reconcile(o: pd.DataFrame) -> dict:
    h = o[o.in_headline]
    ov = h.pick_override.fillna("")
    forced_ot = h[ov == "open_ticket"]            # FIX_FIRST_FORCE=all_open only (EV <= 0 forced contacts)
    up = h[h.final_action.isin(UPSELLS)]
    ret = h[~h.final_action.isin(UPSELLS)]
    sa = o[o.decision == "already_leaving"]
    return {
        "decision_counts": o.decision.str.split(" ").str[0].value_counts().to_dict(),
        "headline_contacts": int(len(h)),
        "headline_retention_contacts": int(len(ret)), "headline_retention_net": round(float(ret.retention_net.sum()), 2),
        "headline_retention_ev": round(float(ret.final_ev.sum()), 2),
        "headline_upsell_contacts": int(len(up)), "headline_upsell_ev": round(float(up.final_ev.sum()), 2),
        "headline_upsell_retention_part": round(float(up.retention_net.sum()), 2),
        "headline_ev_le0": int((h.final_ev <= 0).sum()),
        "headline_mix": h.final_action.value_counts().to_dict(),
        "open_ticket_fix_only_restricted": int((ov == "open_ticket_fix_only").sum()),
        "forced_open_ticket_contacts": int(len(forced_ot)),
        "forced_open_ticket_retention_net": round(float(forced_ot.retention_net.sum()), 2),
        "open_ticket_silent_ev_le0": int((o.get("do_nothing_reason", pd.Series("", index=o.index)) ==
                                          "open_ticket_ev_le0").sum()),
        "port_out_save_attempts": int(len(sa)), "port_out_mix": sa.final_action.value_counts().to_dict(),
        "port_out_ev_sum_all": round(float(sa.final_ev.sum()), 2),
        "port_out_ev_le0": int((sa.final_ev <= 0).sum()),
        "port_out_ev_pos_count": int((sa.final_ev > 0).sum()),
        "port_out_ev_sum_counted_ev_pos_only": round(float(sa.final_ev[sa.final_ev > 0].sum()), 2),
        "port_out_retention_net_ev_pos_only": round(float(sa.retention_net[sa.final_ev > 0].sum()), 2),
        "bill_rule": o.bill_rule_note.value_counts().to_dict(),
        "blocked_by_guardrail": int(o.blocked_by_guardrail.sum()),
        "blocked_by_guardrail_reasons": o.loc[o.blocked_by_guardrail, "tmm_block_reason"].value_counts().to_dict()
        if "tmm_block_reason" in o else {},
        "blocked_by_guardrail_actions": o.loc[o.blocked_by_guardrail, "action_code"].value_counts().to_dict(),
        "holdout_flagged": int(o.holdout_flag.sum()), "holdout_applied": holdout_on(),
        "wait_until": int(o.decision.str.startswith("wait_until").sum()),
        "receipt_only": int((o.decision == "receipt_only").sum()),
        "mean_kept_value_usd": round(float(o.customer_value_usd.mean()), 2),
        "data_note": "SYNTHETIC; port-out save attempts never in headline; their EV<=0 rows never in any net",
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("TM_OUT_DIR", str(HERE / "out")))
    ap.add_argument("--moments", default=None)
    a = ap.parse_args(argv)
    out = Path(a.out)
    o = pd.read_csv(out / "offers.csv")
    cands = pd.read_csv(out / "offer_candidates.csv")
    mp = Path(a.moments) if a.moments else out / "moment_decisions.csv"
    mom = pd.read_csv(mp) if mp.exists() else None
    g = gj.load(out / "guardrail.csv")
    o = decide(o.drop(columns=[c for c in o.columns if c.startswith("tmm_") or c in (
        "decision", "final_action", "final_ev", "bill_rule_note", "retention_net", "receipt_line_kind",
        "blocked_by_guardrail", "holdout_flag")]), cands, mom, g)
    o.to_csv(out / "offers.csv", index=False)
    rec = reconcile(o)
    (out / "one_decision_summary.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))
    return o


if __name__ == "__main__":
    main()
