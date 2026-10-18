"""Regenerate data/weekly_candidates_12w.csv.gz: roll each account's REAL sandbox fields forward week by week and
re-run the engine's eligibility (harness/offers.evaluate_account, imported read-only, never edited) at every week.
Vendored from tm-models scratch moments/snap.py + rollforward.py; no scratch paths. ALL NUMBERS SYNTHETIC (comment only).

What moves with the calendar (as_of = 2026-10-01): financing payoff (installments assumed billed on the 1st), device
age, tenure (+1 on each 1st), days since bill shock (90-day upsell block lifts), support_90d (care-credit promo rule
rolls off). Held fixed: churn/upgrade scores, usage, open tickets/driver counts, no new contacts or bills.

Run from the repo root (about 5 min for 12 weeks; writes only to experiments/engine_rules/data and $TM_OUT_DIR):
    mkdir -p /tmp/er_in && cp demo_data/{churn_scores,enrichment,features,upgrade_scores}.csv /tmp/er_in/
    TM_OUT_DIR=/tmp/er_in DUBHACKS_DB=vendor/dubhacks/data/sandbox.db OMP_NUM_THREADS=1 \
        python3 -m experiments.engine_rules.rollforward 12
"""
import os, sys, time, sqlite3
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "harness")); sys.path.insert(0, str(REPO))
DATA = Path(__file__).resolve().parent / "data"


def build_weekly(weeks=12, out=DATA / "weekly_candidates_12w.csv.gz"):
    os.environ.setdefault("TM_OUT_DIR", "/tmp/er_in")
    import offers as O                   # read-only import of the engine
    import offer_detectors as det
    df, cat, conn, _ = O.prepare(write_line_tradein=False)
    df0 = df.set_index("account_id"); promos, plans = cat["promotions"], cat["plans"]
    con = det.connect_ro()
    AS_OF = date.fromisoformat(con.execute("select value from metadata where key='as_of'").fetchone()[0])
    L = pd.read_sql("select * from lines", con)
    sup = pd.read_sql("select * from support_interactions", con); sup["d"] = pd.to_datetime(sup.interaction_date).dt.date
    L["pdate"] = pd.to_datetime(L.device_purchase_date).dt.date
    has_dev = L.device_sku.notna().values

    def sup90(D):
        s = sup[(sup.d >= D - timedelta(days=det.SUPPORT_WINDOW_DAYS)) & (sup.d <= min(D, AS_OF))]
        return s.groupby("account_id").size().reindex(df0.index).fillna(0).astype(int)
    S0 = sup90(AS_OF)

    def state(w):
        D = AS_OF + timedelta(days=7 * w); m = det.months_between(AS_OF, D)
        fmr = np.maximum(0, L.financing_months_remaining.values - m)
        bal = np.where(fmr == 0, 0, np.maximum(0, L.financing_balance_cents.values - m * L.monthly_installment_cents.values))
        age = np.array([det.months_between(p, D) if pd.notna(p) else np.nan for p in L.pdate], float)
        ready = has_dev & (L.tradein_eligible.values == 1) & (age >= det.UPGRADE_MIN_DEVICE_AGE_MONTHS) & (fmr == 0)
        T = pd.DataFrame({"account_id": L.account_id, "fmr": fmr, "age": age, "paid": has_dev & (bal == 0),
                          "ready": ready, "old": ready & (age >= det.OLD_DEVICE_MONTHS), "age36": age >= det.OLD_DEVICE_MONTHS,
                          "soon": (fmr >= 1) & (fmr <= det.PAYOFF_SOON_MONTHS),
                          "inst_off": np.where((L.financing_months_remaining.values > 0) & (fmr == 0), L.monthly_installment_cents.values, 0)})
        g = T.groupby("account_id"); X = df0.copy()
        X["max_financing_months_left"] = g.fmr.max(); X["oldest_device_age_m"] = g.age.max()
        X["any_paid_off_device"] = g.paid.any(); X["n_upgrade_ready_lines"] = g.ready.sum(); X["n_old_upgrade_lines"] = g.old.sum()
        X["um_old_device"] = g.age36.any(); X["any_payoff_soon"] = g.soon.any(); X["um_payoff_soon"] = X.any_payoff_soon
        X["last_bill_cents"] = df0.last_bill_cents - g.inst_off.sum()
        X["tenure_months"] = df0.tenure_months + m
        X["contract_or_financing_months_remaining"] = np.maximum(0, df0.contract_or_financing_months_remaining - m)
        X["days_since_bill_shock"] = df0.days_since_bill_shock + 7 * w
        X["support_90d"] = df0["support_90d"] + (sup90(D) - S0)   # only the promo-rule count rolls off
        return X, D

    keycols = ["max_financing_months_left", "oldest_device_age_m", "any_paid_off_device", "n_upgrade_ready_lines",
               "n_old_upgrade_lines", "um_old_device", "tenure_months", "last_bill_cents", "support_90d",
               "contract_or_financing_months_remaining", "days_since_bill_shock"]
    rows = []; prev = None; t = time.time()
    for w in range(weeks):
        X, D = state(w)
        key = X[keycols].astype(float).fillna(-9)
        todo = X.index if prev is None else X.index[(key != prev[0]).any(axis=1).values]
        res = {} if prev is None else dict(prev[1])
        for a in todo:
            r = X.loc[a].copy(); r["account_id"] = a
            ev = O.evaluate_account(r, promos, plans)["res"]
            res[a] = [(k, v["eligible"], v["save_rate"], v["cost"], v["annoyance"], v.get("gain"), v.get("customer_benefit"))
                      for k, v in ev.items() if k != "do_nothing"]
        prev = (key, res)
        for a, lst in res.items():
            rows += [(a, w, str(D), k, s_, c_, an, g_, b_) for k, el, s_, c_, an, g_, b_ in lst if el]
        print(f"week {w} ({D}): re-evaluated {len(todo)} accounts, {time.time() - t:.0f}s", flush=True)
    W = pd.DataFrame(rows, columns=["account_id", "week", "date", "action_code", "save_rate", "cost", "annoyance", "gain", "benefit"])
    W.to_csv(out, index=False, compression="gzip")
    return W


if __name__ == "__main__":
    build_weekly(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
