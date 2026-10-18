"""Join point for tm-models' do-not-contact guardrail (v2). ALL NUMBERS SYNTHETIC.

tm-models owns the guardrail (scratch_models/economics/guardrail/guardrail.py, out/guardrail.csv + guardrail_detail.csv;
read-only here, never edited). Two things live here:

  join(offers)          left-joins whatever per-account columns tm-models publishes (today contact_ok, block_reason,
                        why_line; later timing, holdout) on account_id. Missing file -> columns absent, no crash.
  bill_rule(offers)     reproduces their rule 1 (RULE=new) on OUR picks: an account with a blocking bill change (their
                        detail column blocking_bill_change: a non-stable increase in the last 3 billed months that is
                        not new-phone-only) may only be texted an offsetting credit or a fix-only callback. Otherwise
                        swap to the account's best positive-EV offsetting credit, else no text.

Rules 2 (plan moves receipt-only) and 3 (fatigue hook, no outreach log) are already true in the engine. Their rule 4
(not_worth_contacting) is THEIR EV policy; ours is the engine's EV + profit gate, so it is not applied here.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

GUARDRAIL_DIR = Path(os.environ.get("TM_GUARDRAIL_DIR", "/workspace/tmobile/scratch_models/economics/guardrail/out"))
JOIN_COLS = ("contact_ok", "block_reason", "why_line", "timing", "holdout")   # whichever exist
# their OFFSETS set (credits that put money back against a higher bill) + fix-only callbacks (RULE=new)
OFFSETS = {"bill_shock_price_lock", "loyalty_credit", "care_credit", "care_credit_fix_first", "keep_your_phone"}
ALLOWED_ON_BILL_CHANGE = OFFSETS | {"fix_first"}


def load(path: Path | None = None) -> pd.DataFrame | None:
    p = Path(path) if path else GUARDRAIL_DIR / "guardrail.csv"
    if not p.exists():
        return None
    g = pd.read_csv(p)
    det = p.with_name("guardrail_detail.csv")
    if det.exists():
        d = pd.read_csv(det, usecols=lambda c: c in ("account_id", "blocking_bill_change", "bill_change_reason",
                                                     "bill_change_usd"))
        g = g.merge(d, on="account_id", how="left")
    return g


def join(offers: pd.DataFrame, g: pd.DataFrame | None = None, prefix: str = "tmm_") -> pd.DataFrame:
    """Left-join tm-models' guardrail columns (prefixed, so their later columns never collide with ours)."""
    g = load() if g is None else g
    if g is None:
        return offers
    cols = [c for c in g.columns if c in JOIN_COLS or c in ("blocking_bill_change", "bill_change_reason",
                                                             "bill_change_usd")]
    return offers.merge(g[["account_id"] + cols].rename(columns={c: prefix + c for c in cols}),
                        on="account_id", how="left")


def bill_rule(offers: pd.DataFrame, cands: pd.DataFrame, g: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return per-account: bill_rule_action (action after rule 1), bill_rule_ev, bill_rule_note."""
    g = load() if g is None else g
    o = offers[["account_id", "action_code", "expected_value"]].copy()
    blk = set(g.loc[g.get("blocking_bill_change", pd.Series(False, index=g.index)).fillna(False).astype(bool),
                    "account_id"]) if g is not None else set()
    o["blocking_bill_change"] = o.account_id.isin(blk)
    need = o.blocking_bill_change & (o.action_code != "do_nothing") & ~o.action_code.isin(ALLOWED_ON_BILL_CHANGE)
    alt = cands[cands.account_id.isin(o.account_id[need]) & cands.action_code.isin(OFFSETS)
                & (cands.eligible.astype(str) == "True") & (cands.expected_value > 0)]
    best = alt.sort_values("expected_value", ascending=False).groupby("account_id").head(1).set_index("account_id")
    o["bill_rule_action"], o["bill_rule_ev"], o["bill_rule_note"] = o.action_code, o.expected_value, ""
    for i in o.index[need]:
        a = o.at[i, "account_id"]
        if a in best.index:
            o.at[i, "bill_rule_action"], o.at[i, "bill_rule_ev"] = best.at[a, "action_code"], best.at[a, "expected_value"]
            o.at[i, "bill_rule_note"] = "swapped_to_offsetting_credit"
        else:
            o.at[i, "bill_rule_action"], o.at[i, "bill_rule_ev"] = "do_nothing", 0.0
            o.at[i, "bill_rule_note"] = "bill_change_no_fix"
    return o
