"""Vendored from tm-models scratch moments/events.py (no scratch paths). Moment Replay event feed from REAL sandbox fields only (sandbox.db opened read-only). ALL NUMBERS SYNTHETIC.
week = floor((event_date - as_of) / 7 days); as_of = 2026-10-01 (sandbox metadata). Negative weeks = history replay.
Forward-dated (scheduled) events, weeks 0..H-1:
  payoff          lines.financing_months_remaining      payoff on the 1st of as_of+k months [assumed billing day]
  device_age      lines.device_purchase_date            phone crosses promotions.min_device_age_months (36)
                                                        [+ the sandbox's 12-month upgrade rule, flagged rule_source]
  tenure          accounts.tenure_months                tenure crosses each promotions.min_tenure_months (6, 36),
                                                        +1 on the 1st of each month [assumed anniversary day]
History replay (live) events, weeks -H..-1 (the data stops at as_of; nothing after it is invented):
  bill_spike      billing_history                       month-over-month total rise > BILL_SPIKE_PCT (default 20%)
  unresolved_support support_interactions               resolved = 0, on interaction_date
Nothing in this file is simulated; every row has simulated = 0."""
import sqlite3, sys
import numpy as np, pandas as pd
from datetime import date, timedelta
import os
from pathlib import Path
_REPO = Path(__file__).resolve().parents[2]
DB = "file:" + os.environ.get("DUBHACKS_DB", str(_REPO / "vendor" / "dubhacks" / "data" / "sandbox.db")) + "?mode=ro"
BILL_SPIKE_PCT = 0.20

def mb(a, b): return (b.year - a.year) * 12 + (b.month - a.month)
def add_months(d, k): y, m = divmod(d.month - 1 + k, 12); return date(d.year + y, m + 1, 1)

def build(horizon_weeks=12, spike_pct=BILL_SPIKE_PCT, db=DB):
    con = sqlite3.connect(db, uri=True)
    as_of = date.fromisoformat(con.execute("select value from metadata where key='as_of'").fetchone()[0])
    end = as_of + timedelta(days=7 * horizon_weeks); start = as_of - timedelta(days=7 * horizon_weeks)
    wk = lambda d: (d - as_of).days // 7
    ev = []
    L = pd.read_sql("select line_id, account_id, device_sku, device_purchase_date, financing_months_remaining, tradein_eligible from lines", con)
    P = pd.read_sql("select sku, min_tenure_months, min_device_age_months from promotions", con)
    A = pd.read_sql("select account_id, tenure_months from accounts", con)
    # (a) payoff month
    for r in L[L.financing_months_remaining > 0].itertuples():
        d = add_months(as_of, int(r.financing_months_remaining))
        if d < end: ev.append((r.account_id, wk(d), str(d), "payoff", "lines.financing_months_remaining",
                               f"{r.line_id}: {r.financing_months_remaining} months left -> paid off", 0, ""))
    # (b) device age crossing promo minimum (36, OLD-PHONE-UPGRADE) and the sandbox 12-month upgrade rule
    thr = {int(v): s for s, v in P.dropna(subset=["min_device_age_months"])[["sku", "min_device_age_months"]].values}
    rules = {**{k: f"promotions.min_device_age_months ({s})" for k, s in thr.items()},
             12: "sandbox upgrade rule (UPGRADE_MIN_DEVICE_AGE_MONTHS=12)"}
    for r in L[L.device_purchase_date.notna()].itertuples():
        p = date.fromisoformat(r.device_purchase_date)
        for k, src in rules.items():
            d = add_months(date(p.year, p.month, 1), k)
            if as_of < d < end:   # crossing strictly after as_of
                ev.append((r.account_id, wk(d), str(d), f"device_age_{k}m", "lines.device_purchase_date",
                           f"{r.line_id}: bought {p}, turns {k} months", 0, src))
    # (c) tenure crossing promo minimum
    tthr = {int(v): s for s, v in P.dropna(subset=["min_tenure_months"])[["sku", "min_tenure_months"]].values}
    for r in A.itertuples():
        for k, s in tthr.items():
            need = k - int(r.tenure_months)
            if need >= 1:
                d = add_months(as_of, need)
                if d < end: ev.append((r.account_id, wk(d), str(d), f"tenure_{k}m", "accounts.tenure_months",
                                       f"tenure {r.tenure_months} -> {k}", 0, f"promotions.min_tenure_months ({s})"))
    # (d) bill spike (history)
    B = pd.read_sql("select * from billing_history", con).sort_values(["account_id", "month"])
    B["prev"] = B.groupby("account_id").total_cents.shift(1); B["pct"] = B.total_cents / B.prev - 1
    B["d"] = [date.fromisoformat(m + "-01") for m in B.month]
    spikes = B[(B.pct > spike_pct) & (B.d >= start) & (B.d <= as_of)]
    for r in spikes.itertuples():
        ev.append((r.account_id, wk(r.d), str(r.d), "bill_spike", "billing_history",
                   f"{r.month}: ${r.prev/100:.2f} -> ${r.total_cents/100:.2f} (+{r.pct:.0%}, reason={r.change_reason})", 0, ""))
    # (e) unresolved support contact (history)
    S = pd.read_sql("select * from support_interactions where resolved = 0", con)
    S["d"] = [date.fromisoformat(x) for x in S.interaction_date]
    for r in S[(S.d >= start) & (S.d <= as_of)].itertuples():
        ev.append((r.account_id, wk(r.d), str(r.d), "unresolved_support", "support_interactions",
                   f"{r.interaction_id}: {r.channel}/{r.topic}, sentiment {r.sentiment:+.2f}, resolved=0", 0, ""))
    E = pd.DataFrame(ev, columns=["account_id", "week", "date", "event_type", "source_field", "value", "simulated", "rule_source"])
    return E.sort_values(["week", "account_id", "event_type"]).reset_index(drop=True), B, as_of

def build_events(db_path=None, horizon_weeks=12, spike_pct=BILL_SPIKE_PCT) -> pd.DataFrame:
    """Public entry point for tm-offers. db_path: plain path to sandbox.db (opened READ-ONLY via a sqlite URI) or a
    ready 'file:...?mode=ro' URI. Returns events (account_id, week, date, event_type, source_field, value, simulated,
    rule_source, actionable_week). actionable_week = first planning week whose start date is on/after the event."""
    if db_path is None: uri = DB  # read-only URI
    elif str(db_path).startswith("file:"): uri = str(db_path)
    else: uri = f"file:{db_path}?mode=ro"
    E, _, as_of = build(horizon_weeks, spike_pct, uri)
    days = np.array([(date.fromisoformat(d) - as_of).days for d in E.date])
    E["actionable_week"] = np.where(days >= 0, -(-days // 7), E.week)
    assert (E.simulated == 0).all()
    return E

if __name__ == "__main__":
    H = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    E = build_events(None, H)
    print(E.groupby(["event_type"]).agg(events=("account_id", "size"), accounts=("account_id", "nunique")).to_string())
