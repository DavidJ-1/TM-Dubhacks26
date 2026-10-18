"""Two-sided value ledger (tm-offers). ALL NUMBERS SYNTHETIC: 5,042 sandbox stub accounts, no real T-Mobile data.

For every account x candidate offer it prices BOTH sides:

  T-Mobile side (per offer, horizon H months):
      kept value   = p_churn_90d x save_rate [x p_accept if the save needs acceptance] x KEPT_MARGIN_MO x H
      + support    = avoided assisted contacts x COST_PER_CONTACT          (fix-first actions only)
      + upsell     = p_accept x incremental margin                           (step-up / family / device / HINT)
      - given up   = p_accept x $/mo the customer saves x H                  (price-cut offers)
      - cost       = credits paid + contact/annoyance cost
    Replacement cost (CAC) is NOT added on top of kept margin (double count); it is an alternative column
    `tm_value_replacement_framing_12m` only. Ascarza 2016 backfire and a -1% reminder case are sensitivity columns.

  Customer side: $/mo if they accept (money back to customers), plus HIDDEN VALUE: value already on their
  account per the sandbox catalog (firm $ savings they qualify for, reminders of included perks, trade-in value of
  paid-off phones). Never claims a perk is unused (the sandbox has no activation field).

Hidden-value items come from tm-models' file (HV_OFFICIAL) when present, else a PLACEHOLDER pass that follows
tm-strategy's rules in strategy/ledger/HIDDEN_VALUE.md (items B1, B2, C, D, E, A2, F; G is an inference, skipped).

Run: python harness/value_ledger.py --out /tmp/value_ledger   (reads demo_data/ + sandbox.db read-only)
Writes only <out>/: ledger.csv, receipt.csv, hidden_value_items.csv, SUMMARY.md.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
HV_OFFICIAL = Path("/workspace/tmobile/scratch_models/hidden_value/hidden_value_items.csv")
DB_CANDIDATES = [ROOT / "vendor/dubhacks/data/sandbox.db",
                 Path("/workspace/tmobile/TM-Dubhacks26/vendor/dubhacks/data/sandbox.db"),
                 Path("/workspace/tmobile/dubhacks/data/sandbox.db")]

# ---------------------------------------------------------------------------------------------------------
# ASSUMPTIONS: value, (low, high) range, source. "ASSUMPTION" = not sourced; everything is synthetic.
# ---------------------------------------------------------------------------------------------------------
A = {
    "ARPA_MO": (152.91, None, "T-Mobile Q2'26 postpaid ARPA, TMUS Ex 99.1 2026-07-23 (RESEARCH.md s12)"),
    "SERVICE_MARGIN": (0.50, None, "Core Adj. EBITDA / service revenue Q2'26 ~50%, upper bound (RESEARCH.md s12)"),
    "H_MONTHS": (24, None, "kept-account horizon; $152.91 x 50% x 24 = $1.8K; Recon Analytics ~$1,900 (RESEARCH.md s12)"),
    "KEPT_VALUE_MODE": ("flat", None, "default flat ARPA-based; 'bill' = own service bill x 50% (reported side by side)"),
    "CAC": (350.0, (300.0, 400.0), "old CPGA $300-400 (2004-05, RESEARCH.md s2); ALTERNATIVE column only, never summed"),
    "P_ACCEPT_RIGHT_SIZE": (0.03, (0.02, 0.13), "Ascarza 2016 1.5%, Ofgem 2017 2.4-3.4%, Ofgem 12-13% (RESEARCH.md s11)"),
    "P_ACCEPT_VARIANT": (0.10, (0.03, 0.27), "customer must act: Ascarza 2016 / Ofgem 2017-18 (tm-research, group chat)"),
    "P_ACCEPT_UPSELL": (0.04, (0.03, 0.045), "upgrade base ~3-4.5% of postpaid subs per quarter (RESEARCH.md s5)"),
    "SAVE_IF_ACCEPT_PRICE": (0.30, (0.0, 0.30), "ASSUMPTION (engine SAVE_RATE right_size on_target; flagged optimistic)"),
    "SAVE_SCALE": (1.0, (0.25, 1.0), "engine SAVE_RATEs flagged optimistic; 0.25x sensitivity per RESEARCH.md s9"),
    "BACKFIRE_REL": (0.667, (0.0, 0.667), "Ascarza 2016: plan-savings outreach churn 6%->10% (+67% rel.); SENSITIVITY only"),
    "REMINDER_SAVE_FIT": (0.02, (0.0, 0.05), "no evidence reminders cut churn; McKenzie RCT null (RESEARCH.md s12)"),
    "REMINDER_SAVE_OFF": (0.01, None, "RESEARCH.md s12 off-target"),
    "REMINDER_SAVE_BILLSHOCK": (-0.01, None, "RESEARCH.md s12 -1% case for bill-shocked accounts; SENSITIVITY"),
    "REMINDER_COST": (0.50, (0.10, 1.84), "in-app/SMS; Gartner self-service $0.10-1.84 (RESEARCH.md s12)"),
    "REMINDER_ANNOYANCE": (2.0, None, "ASSUMPTION (engine ANNOYANCE, kept per RESEARCH.md s12)"),
    "COST_PER_CONTACT": (8.01, (8.01, 13.50), "Gartner 2019 $8.01 assisted contact; newer median $13.50 (RESEARCH.md s12)"),
    "CONTACT_REDUCTION": (0.30, (0.10, 0.50), "ASSUMPTION: share of recent contacts a fix-first callback avoids"),
    "CONTACT_MONTHS": (3, None, "ASSUMPTION: avoided contacts counted for 3 months (issue gets fixed eventually anyway)"),
    "STEP_UP_MARGIN": (0.80, None, "ASSUMPTION (engine, unsourced)"),
    "DEVICE_UPGRADE_MARGIN": (80.0, None, "ASSUMPTION (engine, unsourced)"),
    "HINT_MARGIN": (0.30, None, "ASSUMPTION (engine, unsourced)"),
    "CUSTOMER_WEIGHT": (0.5, (0.0, 1.0), "ASSUMPTION (engine CUSTOMER_BENEFIT_WEIGHT): $ of expected customer gain in rank score"),
    "BILL_SHOCK_PCT": (0.15, None, "engine rule: bill up >=15% or promo expired recently"),
    "STREAM_HOURS": (40.0, None, "tm-strategy HIDDEN_VALUE.md A2 threshold (account total, Jul-Sep 2026 avg)"),
}
V = {k: v[0] for k, v in A.items()}

PRICE_CUT = {"right_size", "variant_switch", "plan_fit", "hidden_saving"}   # customer must act, saves money
UPSELL = {"step_up", "family_upgrade", "device_upgrade", "home_internet_bundle"}
ENGINE_P_ACCEPT = {"device_upgrade": 0.15, "home_internet_bundle": 0.04, "step_up": 0.25, "family_upgrade": 0.20}
FIX = {"fix_first", "care_credit_fix_first"}
HV_COLUMNS = ["account_id", "item_type", "description", "customer_value_monthly", "tmobile_value_monthly",
              "source_field"]
HV_OPTIONAL = ["customer_value_one_time", "tmobile_cost_monthly", "tmobile_retention_gain", "source_date",
               "customer_line", "kind"]
# flexible column-name map for tm-models' file
HV_ALIASES = {
    "account_id": ["account_id", "account", "acct", "acc_id"],
    "item_type": ["item_type", "item", "type", "item_code", "category"],
    "description": ["description", "desc", "detail", "item_description", "label", "plain_text"],
    "customer_value_monthly": ["customer_value_monthly", "customer_monthly", "customer_value_mo", "customer_value",
                               "customer_usd_mo", "customer_value_usd_mo", "customer_value_usd"],
    "tmobile_value_monthly": ["tmobile_value_monthly", "tmobile_monthly", "tmobile_value", "tmo_value_monthly",
                              "tmobile_value_usd_mo", "tmobile_value_usd"],
    "source_field": ["source_field", "source", "source_fields", "rule"],
    "customer_value_one_time": ["customer_value_one_time", "customer_value_onetime", "one_time_value", "customer_one_time", "one_time_usd"],
    "tmobile_cost_monthly": ["tmobile_cost_monthly", "tmobile_cost", "tmo_cost_monthly", "tmobile_cost_usd_mo"],
    "tmobile_retention_gain": ["tmobile_retention_gain", "retention_gain", "tmobile_retention_value"],
    "source_date": ["source_date", "date", "as_of"],
    "customer_line": ["customer_line", "message", "message_en", "line_en", "plain_text"],
    "confidence": ["confidence"],
    "kind": ["kind", "value_kind"],
}


def find_db() -> Path:
    if os.environ.get("DUBHACKS_DB"):
        return Path(os.environ["DUBHACKS_DB"])
    for p in DB_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("sandbox.db not found; set DUBHACKS_DB")


def connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)   # never writes sandbox.db


def plan_price(p: pd.Series, n: int) -> int:
    t = [int(x) for x in str(p["line_prices"]).split(",")]
    return int(sum(t[i] if i < len(t) else int(p["extra_line_cents"]) for i in range(n)))


# ---------------------------------------------------------------------------------------------------------
# Hidden-value input
# ---------------------------------------------------------------------------------------------------------
def load_hidden_value(path: Path) -> pd.DataFrame:
    """Load a hidden-value item file, mapping column names flexibly. Fails loudly on missing required columns."""
    raw = pd.read_csv(path)
    low = {c.lower().strip(): c for c in raw.columns}
    out = {}
    for col, names in HV_ALIASES.items():
        hit = next((low[n] for n in names if n in low), None)
        if hit is not None:
            out[col] = raw[hit]
    missing = [c for c in HV_COLUMNS if c not in out]
    if "tmobile_value_monthly" in missing and "customer_value_monthly" in out:
        # tm-models' file gives 12-month T-Mobile cost/gain, not $/mo: a $/mo customer saving is $/mo revenue given up
        out["tmobile_value_monthly"] = -pd.to_numeric(out["customer_value_monthly"], errors="coerce").fillna(0)
        missing.remove("tmobile_value_monthly")
    if "tmobile_value_monthly" in missing and "tmobile_cost_monthly" in out:   # cost given instead of value
        out["tmobile_value_monthly"] = -pd.to_numeric(out["tmobile_cost_monthly"], errors="coerce").fillna(0)
        missing.remove("tmobile_value_monthly")
    if "description" in missing and "customer_line" in out:
        out["description"] = out["customer_line"]
        missing.remove("description")
    if missing:
        raise ValueError(f"hidden-value file {path} is missing required columns {missing}; has {list(raw.columns)}")
    df = pd.DataFrame(out)
    for c in ["customer_value_monthly", "tmobile_value_monthly", "customer_value_one_time"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    if "customer_value_one_time" not in df:
        df["customer_value_one_time"] = 0.0
    if "kind" not in df:   # price change if customer $/mo > 0 and T-Mobile gives it up; else reminder
        df["kind"] = np.where(df["customer_value_monthly"] > 0, "saving", "reminder")
        if "confidence" in df:   # inferred items (e.g. student credit) and purchase-conditional credits: not firm
            conf = df["confidence"].astype(str)
            df.loc[conf.str.contains("inferred"), "kind"] = "check"
            df.loc[conf.str.contains("conditional"), "kind"] = "conditional"
    return df


def placeholder_hidden_value(conn: sqlite3.Connection) -> pd.DataFrame:
    """PLACEHOLDER (to be replaced by tm-models' file). Rules = tm-strategy HIDDEN_VALUE.md B1, B2, C, D, E, A2, F."""
    rd = lambda q: pd.read_sql(q, conn)  # noqa: E731
    plans = rd("select * from plans").set_index("sku", drop=False)
    acc = rd("select a.account_id, a.discount_group, l.plan_sku, count(*) n from accounts a "
             "join lines l using(account_id) group by a.account_id")
    acc["family"] = acc.plan_sku.map(plans.family)
    acc["variant"] = acc.plan_sku.map(plans.variant)
    acc["cost"] = [plan_price(plans.loc[s], n) for s, n in zip(acc.plan_sku, acc.n)]
    aa = rd("select * from account_addons")
    has = lambda sku: set(aa.loc[aa.addon_sku == sku, "account_id"])  # noqa: E731
    rows = []

    def add(aid, t, desc, cust, tmo, src, kind, one=0.0):
        rows.append(dict(account_id=aid, item_type=t, description=desc, customer_value_monthly=cust,
                         tmobile_value_monthly=tmo, source_field=src, kind=kind, customer_value_one_time=one))
    beyond = set(acc.loc[acc.family == "experience_beyond", "account_id"])
    for sku, price, item in [("TMO-STUB-ADD-LINE-WATCH", 10, "B1_watch_line_on_beyond"),
                             ("TMO-STUB-ADD-LINE-WATCH-PLUS", 15, "B2_watch_plus_on_beyond")]:
        for aid in sorted(has(sku) & beyond):
            add(aid, item, f"Beyond includes a $5 watch line; this account pays ${price}"
                + (" (Plus adds intl/CA-MX watch data you'd lose)" if price == 15 else ""),
                price - 5.0, -(price - 5.0), "account_addons.addon_sku + addons.monthly_cents", "saving")
    e = acc[(acc.plan_sku == "TMO-STUB-PLAN-ESSENTIALS") & (acc.n >= 4)]
    for r in e.itertuples():
        s = (r.cost - plan_price(plans.loc["TMO-STUB-PLAN-ESSENTIALS-4LINE"], r.n)) / 100
        if s > 0:
            add(r.account_id, "C_essentials_4line_offer", f"{r.n} lines on Essentials: 4 Line Offer is ${s:.0f}/mo less",
                s, -s, "lines.plan_sku + plans.line_prices", "saving")
    dg = {"55_plus": "senior_55", "community": "community", "partner": "partner"}
    for r in acc.itertuples():
        if r.discount_group in dg and r.variant == "standard" and r.family in ("experience_more", "experience_beyond"):
            best = 0
            for sku, p in plans[(plans.family == r.family) & (plans.variant == dg[r.discount_group])].iterrows():
                if pd.isna(p.max_lines) or r.n <= p.max_lines:
                    best = max(best, (r.cost - plan_price(p, r.n)) / 100)
            if best > 0:
                add(r.account_id, "E_group_savings_version", f"{r.discount_group} pricing on the same plan "
                    f"(needs eligibility check)", best, -best, "accounts.discount_group + plans.eligibility", "saving")
    # D trade-in value of paid-off phones (one-time; never in $/mo totals)
    L = rd("select l.* from lines l where l.device_sku is not null and l.byod=0 and l.financing_months_remaining=0")
    L["age"] = ((pd.Timestamp("2026-10-01") - pd.to_datetime(L.device_purchase_date)).dt.days / 30.44).round().astype(int)
    tc = rd("select * from tradein_curves")
    tcd = {(r.device_sku, r.age_months): r.value_cents for r in tc.itertuples()}
    mx = tc.groupby("device_sku").age_months.max().to_dict()
    val = lambda s, a: tcd.get((s, min(a, mx[s])), np.nan) if s in mx else np.nan  # noqa: E731
    L["v_now"] = [val(s, a) for s, a in zip(L.device_sku, L.age)]
    L["v6"] = [val(s, a + 6) for s, a in zip(L.device_sku, L.age)]
    g = L[L.v_now > 0].groupby("account_id").agg(v=("v_now", "sum"), v6=("v6", "sum"), k=("line_id", "count"))
    for aid, r in g.iterrows():
        add(aid, "D_tradein_paid_off", f"{int(r.k)} paid-off phone(s) worth ~${r.v/100:.0f} in trade-in today, "
            f"~${r.v6/100:.0f} in 6 months", 0.0, 0.0, "lines.financing_months_remaining + tradein_curves",
            "reminder", r.v / 100)
    # A2 streaming already included (no activation field: never claim it's unused)
    u = rd("select l.account_id, u.month, sum(u.streaming_hours) s from usage_monthly u join lines l using(line_id) "
           "where u.month in ('2026-07','2026-08','2026-09') group by 1,2").groupby("account_id").s.mean()
    acc["stream"] = acc.account_id.map(u).fillna(0)
    inc = acc[(acc.stream >= V["STREAM_HOURS"]) & acc.plan_sku.map(plans.perks).fillna("").str.contains("streaming-video-ads")]
    for aid in inc.account_id:
        add(aid, "A2_streaming_included", "plan already includes ad-supported streaming; heavy streamer", 0.0, 0.0,
            "plans.perks + usage_monthly.streaming_hours", "reminder")
    pg = acc[acc.plan_sku.map(plans.price_guarantee_years).fillna(0) >= 5]
    for aid in pg.account_id:
        add(aid, "F_price_guarantee", "plan comes with a 5-year price guarantee", 0.0, 0.0,
            "plans.price_guarantee_years", "reminder")
    return pd.DataFrame(rows, columns=HV_COLUMNS + ["kind", "customer_value_one_time"])


# ---------------------------------------------------------------------------------------------------------
# Ledger math (pure functions, unit-tested)
# ---------------------------------------------------------------------------------------------------------
def kept_margin_mo(service_rev_mo: np.ndarray | float, mode: str = "flat"):
    if mode == "flat":
        return np.full_like(np.asarray(service_rev_mo, dtype=float), V["ARPA_MO"] * V["SERVICE_MARGIN"])
    return np.asarray(service_rev_mo, dtype=float) * V["SERVICE_MARGIN"]


def tm_value(p90, save_rate, needs_accept, p_accept, kept_mo, months, saving_mo=0.0, upsell=0.0,
             credit_cost=0.0, contact_cost=0.0, support_saved=0.0):
    """T-Mobile net $ over `months`: kept margin + support saved + upsell - revenue given up - costs."""
    p_eff = np.where(needs_accept, p_accept, 1.0)
    prevented = p90 * save_rate * p_eff
    kept = prevented * kept_mo * months
    given_up = p_accept * saving_mo * months
    return kept + support_saved + upsell - given_up - credit_cost - contact_cost, prevented, kept, given_up


def backfire_loss(p90, p_accept, kept_mo, months, rel=None):
    """Ascarza 2016 sensitivity: prompting raises churn among those who don't take the offer."""
    rel = V["BACKFIRE_REL"] if rel is None else rel
    return p90 * (1 - p_accept) * rel * kept_mo * months


def rank_offers(led: pd.DataFrame, w: float | None = None, by: str = "tm_net_12m") -> pd.DataFrame:
    """Best offer per account on BOTH sides: score = T-Mobile net + w x expected customer $ (12 mo).
    do_nothing (score 0) wins unless an offer scores > 0 (the expected-profit gate)."""
    w = V["CUSTOMER_WEIGHT"] if w is None else w
    d = led.copy()
    d["score"] = d[by] + w * d["customer_expected_12m"]
    d = d.sort_values(["account_id", "score"], ascending=[True, False])
    best = d.groupby("account_id").head(1).set_index("account_id")
    return best


# ---------------------------------------------------------------------------------------------------------
def build(out: Path, demo: Path = ROOT / "demo_data", hh_csv: Path | None = None, hv_path: Path | None = None):
    db = find_db()
    conn = connect_ro(db)
    f = pd.read_csv(demo / "features.csv")
    ch = pd.read_csv(demo / "churn_scores.csv")[["account_id", "p_churn_90d"]]
    offers = pd.read_csv(demo / "offers.csv", usecols=["account_id", "action_code", "expected_value"])
    cand = pd.read_csv(demo / "offer_candidates.csv.gz")
    cand = cand[(cand.eligible == True) & (cand.action_code != "do_nothing")]  # noqa: E712
    acct = f[["account_id", "is_persona", "n_lines", "plan_sku", "last_bill_cents", "monthly_installment_total_cents",
              "support_90d", "unresolved_90d", "bill_increase_pct", "promo_expired_recent"]].merge(ch, on="account_id")
    acct["service_rev"] = ((acct.last_bill_cents - acct.monthly_installment_total_cents).clip(lower=0)) / 100
    acct["bill_shock"] = (acct.bill_increase_pct >= V["BILL_SHOCK_PCT"]) | (acct.promo_expired_recent == 1)
    # household optimizer (commit d3adf09) -> plan_fit offers
    if hh_csv is None or not Path(hh_csv).exists():
        os.environ.setdefault("DUBHACKS_DB", str(db))
        sys.path.insert(0, str(HERE))
        import household_optimizer as H  # noqa: E402
        hh = H.build(str(demo))
    else:
        hh = pd.read_csv(hh_csv)
    # hidden value
    hv_source = "placeholder (tm-strategy HIDDEN_VALUE.md rules; to be replaced by tm-models' file)"
    if hv_path == "placeholder":
        hv_path = None
    elif hv_path is None and HV_OFFICIAL.exists():
        hv_path = HV_OFFICIAL
    if hv_path is not None:
        hv = load_hidden_value(Path(hv_path))
        hv_source = f"tm-models file {hv_path}"
    else:
        hv = placeholder_hidden_value(conn)

    rows = []
    a = acct.set_index("account_id")
    # --- engine candidates
    c = cand.merge(acct, on="account_id", how="left")
    for mode in ("flat",):
        pass
    c["kind"] = c.action_code
    pa = np.select([c.kind == "right_size", c.kind == "variant_switch", c.kind.isin(UPSELL)],
                   [V["P_ACCEPT_RIGHT_SIZE"], V["P_ACCEPT_VARIANT"], V["P_ACCEPT_UPSELL"]], 1.0)
    needs = c.kind.isin(PRICE_CUT | UPSELL).values
    save_rate = np.where(c.kind.isin(PRICE_CUT), V["SAVE_IF_ACCEPT_PRICE"], c.save_rate.fillna(0)) * V["SAVE_SCALE"]
    delta = c.customer_monthly_delta.fillna(0).values          # negative = customer pays less
    saving = np.where(c.kind.isin(PRICE_CUT), -delta, 0.0)
    eng_pa = c.kind.map(ENGINE_P_ACCEPT).fillna(1.0).values
    credit = np.where(c.kind.isin(PRICE_CUT), 0.0,
                      np.where(c.kind.isin(UPSELL), c.offer_cost.fillna(0) * pa / eng_pa, c.offer_cost.fillna(0)))
    contact = c.annoyance.fillna(0).values
    sup = np.where(c.kind.isin(FIX) & (c.unresolved_90d > 0),
                   c.support_90d / 3 * V["CONTACT_REDUCTION"] * V["CONTACT_MONTHS"] * V["COST_PER_CONTACT"], 0.0)
    cust_mo = np.select([c.kind.isin(PRICE_CUT), c.kind.isin(UPSELL), c.kind == "care_credit",
                         c.kind == "care_credit_fix_first"], [-delta, -delta, 25 / 12, 25 / 12], -delta)
    c["p_accept"] = pa
    c["needs"] = needs
    c["save_rate_used"] = save_rate
    c["saving_mo"] = saving
    c["credit"] = credit
    c["contact"] = contact
    c["support_saved"] = sup
    c["customer_gain_monthly"] = cust_mo
    c["offer"] = c.action_code
    c["upsell_mo_margin"] = np.select([c.kind.isin(["step_up", "family_upgrade"]), c.kind == "home_internet_bundle"],
                                      [delta * V["STEP_UP_MARGIN"], delta * V["HINT_MARGIN"]], 0.0)
    c["upsell_one_time"] = np.where(c.kind == "device_upgrade", V["DEVICE_UPGRADE_MARGIN"], 0.0)
    c["assumptions"] = np.select(
        [c.kind == "right_size", c.kind == "variant_switch", c.kind.isin(UPSELL), c.kind.isin(FIX)],
        ["p_accept 3% (2-13%) cited; save|accept 30% ASSUMPTION", "p_accept 10% (3-27%) cited; save|accept 30% ASSUMPTION",
         "p_accept 4% cited; save rate & margin ASSUMPTION (engine)", "engine save rate ASSUMPTION; $8.01/contact cited; 30% fewer contacts ASSUMPTION"],
        "engine save rate ASSUMPTION (flagged optimistic)")
    base_cols = ["account_id", "offer", "p_accept", "needs", "save_rate_used", "saving_mo", "credit", "contact",
                 "support_saved", "customer_gain_monthly", "upsell_mo_margin", "upsell_one_time", "assumptions",
                 "customer_one_time"]
    c["customer_one_time"] = 0.0
    rows.append(c[base_cols])
    # --- plan_fit (household optimizer) offers
    mv = hh[(hh.lines_affected > 0) & (hh.monthly_saving > 0)].copy()
    mv["like_for_like"] = ~(mv.reason.str.contains("gives up")
                            | (mv.best_plan.str.startswith("Essentials") & ~mv.current_plan.str.startswith("Essentials")))
    pf = pd.DataFrame({"account_id": mv.account_id, "offer": "plan_fit", "p_accept": V["P_ACCEPT_RIGHT_SIZE"],
                       "needs": True, "save_rate_used": V["SAVE_IF_ACCEPT_PRICE"] * V["SAVE_SCALE"],
                       "saving_mo": mv.monthly_saving, "credit": 0.0, "contact": 2.0, "support_saved": 0.0,
                       "customer_gain_monthly": mv.monthly_saving, "upsell_mo_margin": 0.0, "upsell_one_time": 0.0,
                       "assumptions": "household optimizer d3adf09; p_accept 3% (2-13%) cited; save|accept 30% ASSUMPTION; contact $2 ASSUMPTION",
                       "customer_one_time": 0.0})
    rows.append(pf)
    # --- hidden value offers
    hvs = hv[hv.kind == "saving"].groupby("account_id").agg(cv=("customer_value_monthly", "sum"),
                                                           tv=("tmobile_value_monthly", "sum"),
                                                           items=("item_type", lambda s: "+".join(sorted(set(s)))))
    rows.append(pd.DataFrame({"account_id": hvs.index, "offer": "hidden_saving", "p_accept": V["P_ACCEPT_VARIANT"],
                              "needs": True, "save_rate_used": V["SAVE_IF_ACCEPT_PRICE"] * V["SAVE_SCALE"],
                              "saving_mo": hvs.cv.values, "credit": 0.0, "contact": V["REMINDER_COST"] + V["REMINDER_ANNOYANCE"],
                              "support_saved": 0.0, "customer_gain_monthly": hvs.cv.values, "upsell_mo_margin": 0.0,
                              "upsell_one_time": 0.0, "customer_one_time": 0.0,
                              "assumptions": ("items " + hvs["items"] + "; p_accept 10% (3-27%) cited; save|accept 30% ASSUMPTION").values}))
    hvr = hv[hv.kind.isin(["reminder", "saving"])].groupby("account_id").agg(items=("item_type", lambda s: "+".join(sorted(set(s)))),
                                       one=("customer_value_one_time", "sum"),
                                       tv=("tmobile_value_monthly", lambda s: 0.0))
    fit = hvr["items"].str.replace(r"(F_price_guarantee|price_guarantee_reminder|payoff_upcoming)\+?", "", regex=True) != ""
    rows.append(pd.DataFrame({"account_id": hvr.index, "offer": "hidden_value_reminder", "p_accept": 1.0,
                              "needs": False, "save_rate_used": np.where(fit, V["REMINDER_SAVE_FIT"], V["REMINDER_SAVE_OFF"]),
                              "saving_mo": 0.0, "credit": 0.0, "contact": V["REMINDER_COST"] + V["REMINDER_ANNOYANCE"],
                              "support_saved": 0.0, "customer_gain_monthly": 0.0, "upsell_mo_margin": 0.0,
                              "upsell_one_time": 0.0, "customer_one_time": hvr.one.values,
                              "assumptions": ("items " + hvr["items"] + "; 'here's what your plan already gives you', no price change; "
                                              "retention 2% if fits (0-5%) / 1% otherwise, cited as NO evidence; cost $0.50 cited + $2 annoyance ASSUMPTION").values}))
    led = pd.concat(rows, ignore_index=True).merge(acct, on="account_id", how="left")
    hv_mo = hv[hv.kind == "saving"].groupby("account_id").customer_value_monthly.sum()
    led["hidden_value_monthly"] = led.account_id.map(hv_mo).fillna(0.0)
    led["kept_mo_flat"] = kept_margin_mo(led.service_rev, "flat")
    led["kept_mo_bill"] = kept_margin_mo(led.service_rev, "bill")
    p90 = led.p_churn_90d.values
    for tag, months in (("12m", 12), ("24m", V["H_MONTHS"])):
        for kv in ("flat", "bill"):
            net, prev, kept, given = tm_value(p90, led.save_rate_used.values, led.needs.values, led.p_accept.values,
                                              led[f"kept_mo_{kv}"].values, months, led.saving_mo.values,
                                              led.p_accept.values * (led.upsell_mo_margin.values * months + led.upsell_one_time.values),
                                              led.credit.values, led.contact.values, led.support_saved.values)
            sfx = "" if kv == "flat" else "_billbased"
            led[f"tm_net_{tag}{sfx}"] = net
            if tag == "12m" and kv == "flat":
                led["prevented_churn"] = prev
                led["tm_kept_margin_12m"] = kept
                led["tm_revenue_given_up_12m"] = given
    led["tm_net_monthly"] = led.tm_net_12m / 12
    # alternative framing: replacement cost instead of kept margin (never summed with it)
    led["tm_value_replacement_framing_12m"] = (led.tm_net_12m - led.tm_kept_margin_12m + led.prevented_churn * V["CAC"])
    is_pc = led.offer.isin(PRICE_CUT).values
    led["tm_net_12m_backfire"] = led.tm_net_12m - np.where(is_pc, backfire_loss(p90, led.p_accept.values, led.kept_mo_flat.values, 12), 0)
    rem = (led.offer == "hidden_value_reminder").values
    neg = rem & led.bill_shock.values
    led["tm_net_12m_reminder_neg"] = np.where(neg, led.tm_net_12m - p90 * (led.save_rate_used - V["REMINDER_SAVE_BILLSHOCK"]) * led.kept_mo_flat * 12, led.tm_net_12m)
    led["customer_expected_12m"] = led.p_accept * led.customer_gain_monthly * 12
    led["money_back_to_customers_mo"] = led.saving_mo
    led.to_csv(out / "ledger_full.csv", index=False)
    cols = ["account_id", "offer", "tm_net_monthly", "tm_net_12m", "customer_gain_monthly", "hidden_value_monthly",
            "assumptions", "p_churn_90d", "p_accept", "prevented_churn", "tm_kept_margin_12m", "tm_revenue_given_up_12m",
            "support_saved", "credit", "contact", "tm_net_24m", "tm_net_12m_billbased", "tm_net_24m_billbased",
            "tm_value_replacement_framing_12m", "tm_net_12m_backfire", "tm_net_12m_reminder_neg", "customer_one_time",
            "customer_expected_12m"]
    led[cols].round(4).to_csv(out / "ledger.csv", index=False)
    hv.to_csv(out / "hidden_value_items.csv", index=False)
    return led, hh, mv, hv, hv_source, offers, cand, acct


def receipt(mv: pd.DataFrame, acct: pd.DataFrame, out: Path, engine_ids: set | None = None) -> pd.DataFrame:
    """Receipt rows for every optimizer saver. Headline (team decision) = the 488 savers the engine also
    flags right-size/variant. `no_tradeoff` is the stricter check (nothing in the optimizer's 'gives up' list and
    no unlimited -> 50 GB move); the 'you'd lose X' line is shown whenever there is a trade-off, in or out of headline."""
    r = mv.merge(acct[["account_id", "p_churn_90d"]], on="account_id", how="left")
    r["no_tradeoff"] = r.like_for_like
    r["like_for_like"] = r.account_id.isin(engine_ids) if engine_ids is not None else r.like_for_like

    def lose(x):
        bits = []
        rs = str(x.reason)
        if "gives up" in rs:
            # never say "unused": the sandbox has no perk-activation field
            bits.append(rs.split("gives up", 1)[1].split(";")[0].strip().replace("unused perks", "plan perks"))
        if x.best_plan.startswith("Essentials") and not x.current_plan.startswith("Essentials"):
            bits.append("unlimited premium data (Essentials has a 50 GB cap)")
        return "" if not bits else f"Cheaper by ${x.monthly_saving:.0f}/mo, but you'd lose: " + "; ".join(dict.fromkeys(bits))
    r["tradeoff_line"] = r.apply(lose, axis=1)
    r["savings_line"] = [f"{b} would cost ${s:.0f}/mo less than {cp} for your lines" for b, s, cp in
                         zip(r.best_plan, r.monthly_saving, r.current_plan)]
    r["money_back_to_customers_mo"] = r.monthly_saving
    r["tmobile_revenue_given_up_mo_if_accepted"] = -r.monthly_saving
    r["expected_money_back_mo_at_3pct"] = r.monthly_saving * 0.03
    r["expected_money_back_mo_at_13pct"] = r.monthly_saving * 0.13
    r["in_headline"] = r.like_for_like
    r["reason"] = r.reason.str.replace("unused perks", "plan perks", regex=False)
    r["data_note"] = "SYNTHETIC (sandbox stub data)"
    r["note"] = np.where(r.best_plan.str.contains("Saver"), "Saver: max 2 lines, no watch/tablet lines", "")
    cols = ["account_id", "like_for_like", "in_headline", "no_tradeoff", "note", "current_plan", "best_plan", "savings_line", "tradeoff_line",
            "money_back_to_customers_mo", "tmobile_revenue_given_up_mo_if_accepted", "expected_money_back_mo_at_3pct",
            "expected_money_back_mo_at_13pct", "p_churn_90d", "reason", "data_note"]
    r[cols].to_csv(out / "receipt.csv", index=False)
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description="Two-sided value ledger (SYNTHETIC)")
    ap.add_argument("--out", default="/tmp/value_ledger")
    ap.add_argument("--household", default=None, help="household_plan.csv (else recomputed from d3adf09 optimizer)")
    ap.add_argument("--hidden-value", default=None, help="hidden-value items CSV, or 'placeholder' to force the fallback pass (default: tm-models file, else placeholder)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    led, hh, mv, hv, src, offers, cand, acct = build(out, hh_csv=a.household, hv_path=a.hidden_value)
    cand = cand  # noqa
    eng = set(cand.loc[cand.action_code.isin(["right_size", "variant_switch"]), "account_id"])
    receipt(mv, acct, out, eng)
    import value_ledger_report as R  # noqa: E402
    R.write_summary(out, led, hh, mv, hv, src, offers, cand, acct)
    print(f"wrote {out}/ledger.csv ({len(led)} rows), receipt.csv, SUMMARY.md. hidden value: {src}. ALL SYNTHETIC.")


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    main()
