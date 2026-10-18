"""Timekeeper math (tm-offers, Model B): keep / wait until <date> / upgrade now, per line. ALL NUMBERS SYNTHETIC.

Inputs are read-only sandbox tables only: lines, tradein_curves, devices, promotions, support_interactions.

Cost of upgrading at month t (t = 0 is the sandbox as_of date), in cents, from the customer's side:

    cost(t) = installments_paid(0..t) + balance_at(t) - tradein_value(t) - promo_value(t)

Installments paid while waiting reduce the balance one for one, so installments_paid(t) + balance_at(t) equals
today's balance for every t: the balance is owed either way and drops out of the comparison. Therefore

    delta_cents = cost_now - cost_wait = [tradein(t*) - tradein(0)] + [promo(t*) - promo(0)]
                = -tradein_drop_cents + promo_gain_cents          (> 0: waiting until t* saves that much)

Trade-in promos (only real sandbox rows, values read from the promotions table):
  * PROMO-STUB-TRADEIN-ANY  ($200): line is trade-in eligible, account plan family in its plan_families.
  * PROMO-STUB-OLD-PHONE-UPGRADE ($150): trade-in phone owned >= min_device_age_months (36).
  The sandbox has no exclusivity rule, so both can apply to the same trade-in.
  Team convention (handoff spec 6b, NOT a sandbox rule): trade-in promos are only counted once the phone is paid
  off, so paying off is what "unlocks" the $200. Set COUNT_PROMO_ONLY_WHEN_PAID_OFF = False to drop it.

Decision (strategy/rubric/customer_value.md section 5, R9), one verdict per line:
  wait_until_payoff : the best date within the horizon is the payoff month and it gains >= WAIT_MIN_GAIN_CENTS,
                      or the phone is still financed and payoff is no worse than now (a wash: revisit at payoff).
  wait_until_promo  : the best date is a promo threshold (36-month OLD-PHONE-UPGRADE) and gains >= the minimum.
  upgrade_now       : nothing ahead gains the minimum AND the phone is 36+ months old or had a device
                      support contact in the last 90 days (upgrading is reasonable, waiting loses value).
  keep              : keeping the phone beats both: no date ahead is worth waiting for and the phone is young and
                      working, so there is no reason to buy now either (e.g. 3-month-old phone, 1-year-old phone).
Same-account lines whose wait dates fall within JOINT_WINDOW_MONTHS share the later date (both still qualify).
"""
from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd

WAIT_MIN_GAIN_CENTS = 5000          # $50: smaller gains are a wash (synthetic judgement call, rubric R9)
OLD_PHONE_MIN_AGE = 36              # fallback if the promotions row has no min_device_age_months
HORIZON_MONTHS = 12                 # look this far ahead (and always to the payoff month)
JOINT_WINDOW_MONTHS = 2             # rubric R9: lines due within 2 months of each other share one date
DEVICE_PAIN_WINDOW_DAYS = 90
COUNT_PROMO_ONLY_WHEN_PAID_OFF = True
TRADEIN_ANY = "PROMO-STUB-TRADEIN-ANY"
OLD_PHONE = "PROMO-STUB-OLD-PHONE-UPGRADE"


def _months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def _split(v) -> list[str]:
    return [s for s in str(v).split(",") if s and s != "nan" and s != "None"] if pd.notna(v) else []


def _date_plus(today: date, months: int) -> str:
    return (pd.Timestamp(today) + pd.DateOffset(months=int(months))).strftime("%Y-%m-%d")


def build_line_tradein(conn: sqlite3.Connection, promos: pd.DataFrame, plan_family: pd.Series,
                       wait_min_gain_cents: int = WAIT_MIN_GAIN_CENTS) -> pd.DataFrame:
    today = date.fromisoformat(conn.execute("SELECT value FROM metadata WHERE key='as_of'").fetchone()[0])
    promos = promos.set_index("sku", drop=False) if "sku" in promos.columns and promos.index.name != "sku" else promos
    lines = pd.read_sql("SELECT line_id, account_id, device_sku, device_purchase_date, financing_balance_cents, "
                        "financing_months_remaining, monthly_installment_cents, tradein_eligible "
                        "FROM lines WHERE device_sku IS NOT NULL", conn)
    curves = pd.read_sql("SELECT * FROM tradein_curves", conn)
    cmax = curves.groupby("device_sku")["age_months"].max()
    cv = curves.set_index(["device_sku", "age_months"])["value_cents"]
    names = pd.read_sql("SELECT sku, name FROM devices", conn).set_index("sku")["name"]
    since = (pd.Timestamp(today) - pd.Timedelta(days=DEVICE_PAIN_WINDOW_DAYS)).strftime("%Y-%m-%d")
    pain = pd.read_sql("SELECT account_id, COUNT(*) n FROM support_interactions WHERE topic='device' "
                       "AND interaction_date >= ? GROUP BY account_id", conn, params=(since,)) \
        .set_index("account_id")["n"]

    anyt = promos.loc[TRADEIN_ANY] if TRADEIN_ANY in promos.index else None
    oldp = promos.loc[OLD_PHONE] if OLD_PHONE in promos.index else None
    anyt_fams = _split(anyt["plan_families"]) if anyt is not None else []
    oldp_fams = _split(oldp["plan_families"]) if oldp is not None else []
    oldp_age = int(oldp["min_device_age_months"]) if oldp is not None and pd.notna(oldp["min_device_age_months"]) \
        else OLD_PHONE_MIN_AGE

    def val(sku, age):
        if sku not in cmax.index:
            return 0
        return int(cv.get((sku, int(min(max(age, 0), cmax[sku]))), 0))

    rows = []
    for _, l in lines.iterrows():
        sku, acc = l["device_sku"], l["account_id"]
        age = _months_between(pd.Timestamp(l["device_purchase_date"]).date(), today)
        bal, mleft, inst = int(l["financing_balance_cents"]), int(l["financing_months_remaining"]), \
            int(l["monthly_installment_cents"])
        elig = bool(l["tradein_eligible"])
        fam = plan_family.get(acc)

        def balance_at(t):
            return 0 if t >= mleft else max(0, bal - inst * t)

        def promo_at(t):
            """(cents, skus) of real sandbox trade-in promos the line qualifies for at month t."""
            if not elig or (COUNT_PROMO_ONLY_WHEN_PAID_OFF and balance_at(t) > 0):
                return 0, []
            cents, skus = 0, []
            if anyt is not None and (not anyt_fams or fam in anyt_fams):
                cents += int(anyt["value_cents"]); skus.append(TRADEIN_ANY)
            if oldp is not None and age + t >= oldp_age and (not oldp_fams or fam in oldp_fams):
                cents += int(oldp["value_cents"]); skus.append(OLD_PHONE)
            return cents, skus

        def value_at(t):
            return val(sku, age + t) + promo_at(t)[0]

        out = {"account_id": acc, "line_id": l["line_id"], "device_sku": sku, "device_name": names.get(sku, ""),
               "age_months": age, "financing_balance_cents": bal, "financing_months_remaining": mleft,
               "monthly_installment_cents": inst}
        for tag, k in (("now", 0), ("6m", 6), ("12m", 12)):
            v, b = val(sku, age + k), balance_at(k)
            out[f"tradein_value_{tag}_cents"] = v
            out[f"balance_{tag}_cents"] = b
            out[f"net_{tag}_cents"] = max(0, v - b)
            out[f"promo_{tag}_cents"] = promo_at(k)[0]
        out["tradein_value_at_payoff_cents"] = val(sku, age + mleft)
        out["net_tradein_now_cents"] = out["net_now_cents"]

        horizon = max(HORIZON_MONTHS, mleft)
        v0 = value_at(0)
        best_t, best_v = 0, v0
        for t in range(1, horizon + 1):          # earliest month with the highest value wins ties
            vt = value_at(t)
            if vt > best_v:
                best_t, best_v = t, vt
        gain = best_v - v0
        out["device_pain_90d"] = int(pain.get(acc, 0))
        if gain >= wait_min_gain_cents and best_t > 0:
            dec = "wait_until_payoff" if (mleft > 0 and best_t == mleft) else "wait_until_promo"
        elif mleft > 0 and value_at(mleft) - v0 >= 0 and out["device_pain_90d"] == 0:
            # still being paid off and payoff is no worse than now: the honest date to revisit is payoff
            # (trading in early only means paying the balance off sooner). Small gains are flagged as a wash.
            dec, best_t = "wait_until_payoff", mleft
        elif age >= oldp_age or out["device_pain_90d"] > 0:
            dec = "upgrade_now"
        else:
            dec = "keep"
        out["decision"] = dec
        out["_best_t"] = best_t if dec.startswith("wait") else 0
        rows.append(out)

    df = pd.DataFrame(rows)
    # joint upgrade date for same-account lines that are both waiting and due within the window: use the later date
    df["joint_upgrade"] = False
    for acc, g in df[df["decision"].str.startswith("wait")].groupby("account_id"):
        if len(g) < 2:
            continue
        ts = g["_best_t"]
        if ts.max() - ts.min() <= JOINT_WINDOW_MONTHS:
            df.loc[g.index, "_best_t"] = ts.max()
            df.loc[g.index, "joint_upgrade"] = True

    # final per-line comparison at the (possibly shared) wait month; everything in cents, synthetic
    recs = []
    lines_by_id = lines.set_index("line_id")
    for i, r in df.iterrows():
        sku, age, bal, mleft, inst = r["device_sku"], r["age_months"], r["financing_balance_cents"], \
            r["financing_months_remaining"], r["monthly_installment_cents"]
        fam = plan_family.get(r["account_id"])
        elig = bool(lines_by_id.loc[r["line_id"], "tradein_eligible"])
        t = int(r["_best_t"])

        def balance_at(k):
            return 0 if k >= mleft else max(0, bal - inst * k)

        def promo_at(k):
            if not elig or (COUNT_PROMO_ONLY_WHEN_PAID_OFF and balance_at(k) > 0):
                return 0, []
            cents, skus = 0, []
            if anyt is not None and (not anyt_fams or fam in anyt_fams):
                cents += int(anyt["value_cents"]); skus.append(TRADEIN_ANY)
            if oldp is not None and age + k >= oldp_age and (not oldp_fams or fam in oldp_fams):
                cents += int(oldp["value_cents"]); skus.append(OLD_PHONE)
            return cents, skus

        # comparison month: the wait month for wait verdicts, else the best alternative in the horizon (for display)
        if t == 0:
            horizon = max(HORIZON_MONTHS, mleft)
            vals = [(val(sku, age + k) + promo_at(k)[0], -k) for k in range(1, horizon + 1)]
            t = -max(vals)[1] if vals else 0
        tv0, tvt = val(sku, age), val(sku, age + t)
        p0, s0 = promo_at(0)
        pt, st = promo_at(t)
        paid = bal - balance_at(t)
        rec = {
            "wait_months": t, "wait_date": _date_plus(today, t),
            "tradein_value_wait_cents": tvt, "promo_wait_cents": pt, "promo_now_skus": ",".join(s0),
            "promo_wait_skus": ",".join(st), "installments_paid_by_wait_cents": paid,
            "balance_at_wait_cents": balance_at(t),
            "value_now_cents": tv0 + p0, "value_wait_cents": tvt + pt,
            "tradein_drop_cents": tv0 - tvt, "promo_gain_cents": pt - p0,
            "cost_now_cents": bal - tv0 - p0,
            "cost_wait_cents": paid + balance_at(t) - tvt - pt,
        }
        rec["delta_cents"] = rec["cost_now_cents"] - rec["cost_wait_cents"]
        rec["best_promo_sku"] = rec["promo_wait_skus"] if r["decision"].startswith("wait") else rec["promo_now_skus"]
        rec["promo_value_cents"] = pt if r["decision"].startswith("wait") else p0
        recs.append(rec)
    df = pd.concat([df.drop(columns="_best_t"), pd.DataFrame(recs, index=df.index)], axis=1)
    df["wait_until"] = [d if dec.startswith("wait") else "" for d, dec in zip(df["wait_date"], df["decision"])]
    # single verdict: wait_verdict is kept only as a short alias of decision (it no longer disagrees with it)
    df["wait_verdict"] = df["decision"].map(lambda d: "wait" if d.startswith("wait") else d)

    def reason(r):
        usd = lambda c: f"${abs(c) / 100:,.0f}"
        if r["decision"] == "wait_until_payoff":
            w = " That is about a wash, so there is no rush either way." if r.delta_cents < WAIT_MIN_GAIN_CENTS else ""
            return (f"Wait until {r.wait_until}: the phone is paid off then and the trade-in credit applies; "
                    f"{usd(r.promo_gain_cents)} more in credits vs {usd(r.tradein_drop_cents)} less trade-in value "
                    f"= {usd(r.delta_cents)} better (balance is owed either way).{w}")
        if r["decision"] == "wait_until_promo":
            j = " Upgrade both phones together on that date." if r["joint_upgrade"] else ""
            return (f"Wait until {r.wait_until}: the phone reaches {oldp_age} months and qualifies for the older-phone "
                    f"credit; {usd(r.promo_gain_cents)} more in credits vs {usd(r.tradein_drop_cents)} less trade-in "
                    f"value = {usd(r.delta_cents)} better.{j}")
        if r["decision"] == "upgrade_now":
            return (f"Upgrading now is reasonable (phone {r.age_months} months old"
                    f"{', recent device support contact' if r.device_pain_90d else ''}); waiting until {r.wait_date} "
                    f"changes the trade-in side by {'+' if r.delta_cents >= 0 else '-'}{usd(r.delta_cents)}, "
                    f"so no rush either way.")
        return (f"Keep the phone: it is {r.age_months} months old and working; no date ahead is worth waiting for "
                f"(best by {r.wait_date}: {'+' if r.delta_cents >= 0 else '-'}{usd(r.delta_cents)}).")

    df["verdict_reason"] = df.apply(reason, axis=1)
    df["data_note"] = "synthetic/simulated"
    return df
