"""Rule 2: timing (act now / wait until a dated unlock / silent). ALL NUMBERS SYNTHETIC (comments only; emitted
columns carry no such label by David's rule).

Vendored from tm-models scratch moments/schedule.py (Moment Replay scheduler); no dependency on scratch paths.
Default is ACT NOW. A later (offer, week) option exists only when a real dated change (tenure crossing a promo
minimum, phone payoff, device age, bill-shock window closing, support contacts rolling off) makes an offer eligible
that was not available today AND its decision EV beats the best offer today; it is then survival- and
time-discounted. On the 12-week moments run only 11 accounts wait, almost all for the care credit's 6-month tenure
minimum (CARE-CREDIT min_tenure_months=6).

NOTE (supersedes tm-offers' harness/moment_replay.py on timing): moment_replay.py writes moment_decisions.csv with
0 waits because it excludes credits (care_credit, care_credit_fix_first, ...) as wait targets (WINDOWED_ACTIONS /
"problem-solving actions never wait"). This rule allows a credit to be a wait target when a dated tenure unlock makes
it newly eligible and better than today's best (the care credit's 6-month tenure wait), so use `timing` /
`wait_until` from here, not moment_replay's act/wait column.

Value of an option at week w (constant monthly hazard, because the labels have no churn timing):
    h = 1 - (1 - p) ** (1/3);  EV(w) = (1 - h) ** months(w) * (1 + r) ** -years(w) * EV_offer(p, uq)
"""
from __future__ import annotations
import os
from datetime import date, timedelta
from pathlib import Path
from dataclasses import dataclass, field
import numpy as np, pandas as pd

UPSELL = ("step_up", "family_upgrade", "device_upgrade", "home_internet_bundle")
COST_ON_ACCEPT = ("device_upgrade", "home_internet_bundle")
P_ACCEPT_REPO = {"step_up": 0.25, "device_upgrade": 0.15, "family_upgrade": 0.20, "home_internet_bundle": 0.04}
WEEK_MONTHS = 7 * 12 / 365.25


@dataclass
class ScheduleConfig:
    horizon_months: float = 24.0      # [repo] months of margin a save is worth
    service_margin: float = 0.50      # [repo]
    save_rate_mult: float = 1.0       # [ours]
    cost_mult: float = 1.0            # [ours]
    annoyance_mult: float = 1.0       # [repo]
    upsell_lift: float = 1.0          # [ours] P(take) = min(1, lift * uq)
    backfire_rel: float = 0.67        # [research-derived, ours] (Ascarza 2016)
    benefit_weight: float = 0.0       # [ours] company-$ view
    annual_discount: float = 0.10     # [ours] time value of money
    weeks: int = 12                   # planning horizon (weeks 0..weeks-1)
    allow_delay: bool = False         # also allow today's offers in later weeks (capacity-spread baseline)
    allow_wait: bool = True           # event-driven later options
    hazard_discount: bool = True      # False = pretend nobody churns before a later contact (upper bound for wait)


def _row_params(W: pd.DataFrame) -> pd.DataFrame:
    W = W.copy()
    isU = W.action_code.isin(UPSELL).values
    pa = W.action_code.map(P_ACCEPT_REPO).fillna(1.0).values
    W["is_U"] = isU
    W["gain_acc"] = np.where(isU, W.gain.fillna(0).values / pa, 0.0)          # engine gain = repo P_ACCEPT * gain
    W["gain_hscale"] = W.action_code.isin(["step_up", "family_upgrade", "home_internet_bundle"]).values
    W["cost_on_accept"] = W.action_code.isin(COST_ON_ACCEPT).values
    W["cost_acc"] = np.where(W.cost_on_accept, W.cost.fillna(0).values / pa, W.cost.fillna(0).values)
    W["sr"] = W.save_rate.fillna(0).values
    return W


def offer_ev(W: pd.DataFrame, p, uq, V0, cfg: ScheduleConfig):
    """Undiscounted EV per option row (same formula as scratch_models/policy/policy_eval.ev_rows). Returns (ev, exp_cost)."""
    V = V0 * cfg.service_margin * cfg.horizon_months
    take = np.minimum(1.0, cfg.upsell_lift * uq)
    gain = W.gain_acc.values * np.where(W.gain_hscale.values, cfg.horizon_months / 24, 1.0) * (cfg.service_margin / 0.5)
    gain = np.where(W.action_code.values == "device_upgrade", W.gain_acc.values, gain)
    cost = W.cost_acc.values * cfg.cost_mult * np.where(W.cost_on_accept.values, take, 1.0)
    ann = W.annoyance.fillna(0).values * cfg.annoyance_mult
    ret = p * np.minimum(1, W.sr.values * cfg.save_rate_mult) * V
    ups = take * gain * (1 - p) - cfg.backfire_rel * p * V
    ev = np.where(W.is_U.values, ups, ret) - cost - ann + cfg.benefit_weight * W.benefit.fillna(0).values
    return ev, cost


def time_factor(p, week, cfg: ScheduleConfig):
    h = (1 - (1 - np.asarray(p, float)) ** (1 / 3)) * (1.0 if cfg.hazard_discount else 0.0)
    m = np.asarray(week, float) * WEEK_MONTHS
    return (1 - h) ** m * (1 + cfg.annual_discount) ** (-m / 12)


def build_options(weekly: pd.DataFrame, acct: pd.DataFrame, cfg: ScheduleConfig, p_col="p", uq_col="uq") -> pd.DataFrame:
    """All candidate (account, action, week) options with decision EV (ev) and discounted EV (ev_t)."""
    W = weekly[weekly.account_id.isin(acct.index) & (weekly.week < cfg.weeks)]
    W = _row_params(W).reset_index(drop=True)
    a = acct.loc[W.account_id]
    blocked = a.upsell_blocked.values & W.is_U.values
    W = W[~blocked].reset_index(drop=True); a = acct.loc[W.account_id]
    ev, cost = offer_ev(W, a[p_col].values, a[uq_col].values, a.V0.values, cfg)
    W["ev"] = ev; W["exp_cost"] = cost
    # params signature: an option is "new" at week w if (action, params) was not available at week 0
    sig = W.action_code + "|" + W.sr.round(4).astype(str) + "|" + W.cost_acc.round(2).astype(str) + "|" + W.gain_acc.round(2).astype(str)
    W["sig"] = sig
    now = W[W.week == 0]
    best_now = now.groupby("account_id").ev.max().reindex(acct.index).fillna(0.0).clip(lower=0.0)  # do-nothing = 0
    now_sigs = set(zip(now.account_id, now.sig)); now_acts = set(zip(now.account_id, now.action_code))
    is_new = np.array([(x, s) not in now_sigs for x, s in zip(W.account_id, W.sig)])
    still = np.array([(x, c) in now_acts for x, c in zip(W.account_id, W.action_code)])
    W["kind"] = np.where(W.week == 0, "now",
                np.where(is_new & (W.ev.values > best_now.loc[W.account_id].values + 1e-9), "wait",
                np.where(~is_new & still, "delay", "drop")))
    keep = (W.kind == "now") | ((W.kind == "wait") & cfg.allow_wait) | ((W.kind == "delay") & cfg.allow_delay)
    W = W[keep & (W.ev > 0)].copy()
    # every (account, option, week) is kept: under a weekly cap a later copy can be the only slot left
    W = W.sort_values(["week", "account_id"]).reset_index(drop=True)
    tf = time_factor(acct.loc[W.account_id, p_col].values, W.week.values, cfg)
    W["ev_t"] = W.ev * tf; W["cost_t"] = W.exp_cost * tf
    return W


def solve_schedule(opts: pd.DataFrame, weekly_cap=None, dollar_budget=None, total_cap=None, col="ev_t",
                   mip_rel_gap=1e-7, time_limit=120):
    """MILP: max sum ev_t; <= 1 option per account; <= weekly_cap contacts per week; expected credit spend <= budget."""
    from scipy.optimize import milp, LinearConstraint, Bounds
    from scipy.sparse import csr_matrix
    n = len(opts)
    if n == 0: return np.zeros(0, bool)
    acc_codes, ai = np.unique(opts.account_id.values, return_inverse=True)
    cons = [LinearConstraint(csr_matrix((np.ones(n), (ai, np.arange(n))), shape=(len(acc_codes), n)), 0, 1)]
    if weekly_cap is not None:
        wk, wi = np.unique(opts.week.values, return_inverse=True)
        cons.append(LinearConstraint(csr_matrix((np.ones(n), (wi, np.arange(n))), shape=(len(wk), n)), 0, weekly_cap))
    if total_cap is not None:
        cons.append(LinearConstraint(np.ones((1, n)), 0, total_cap))
    if dollar_budget is not None:
        cons.append(LinearConstraint(opts.cost_t.values[None, :], 0, dollar_budget))
    v = opts[col].values
    r = milp(-np.where(v > 0, v, 0), constraints=cons, integrality=np.ones(n), bounds=Bounds(0, (v > 0).astype(float)),
             options=dict(mip_rel_gap=mip_rel_gap, time_limit=time_limit))
    assert r.x is not None and r.status in (0, 1), r.message   # 1 = time limit with a feasible incumbent
    return np.round(r.x).astype(bool)


def greedy_schedule(opts: pd.DataFrame, weekly_cap=None, dollar_budget=None, total_cap=None, col="ev_t"):
    """Each account takes its single best option; accounts ranked by that value; filled while caps allow (no fallback)."""
    o = opts.reset_index(drop=True)
    best = o[o[col] > 0].sort_values(col, ascending=False).drop_duplicates("account_id")
    used = {}; spent = 0.0; k = 0; sel = np.zeros(len(o), bool)
    for i, r in best.iterrows():
        if total_cap is not None and k >= total_cap: break
        if weekly_cap is not None and used.get(r.week, 0) >= weekly_cap: continue
        if dollar_budget is not None and spent + r.cost_t > dollar_budget: continue
        sel[i] = True; used[r.week] = used.get(r.week, 0) + 1; spent += r.cost_t; k += 1
    return sel


def greedy_fill_schedule(opts: pd.DataFrame, weekly_cap=None, dollar_budget=None, total_cap=None, col="ev_t"):
    """Stronger greedy: walk ALL options by value; take one if its account is unused and its week/budget has room
    (so an account bumped from a full week can still land in a later week)."""
    o = opts.reset_index(drop=True); o = o[o[col] > 0].sort_values(col, ascending=False, kind="stable")
    used_acc = set(); used = {}; spent = 0.0; sel = np.zeros(len(opts), bool)
    for i, r in zip(o.index, o.itertuples()):
        if r.account_id in used_acc: continue
        if total_cap is not None and len(used_acc) >= total_cap: break
        if weekly_cap is not None and used.get(r.week, 0) >= weekly_cap: continue
        if dollar_budget is not None and spent + r.cost_t > dollar_budget: continue
        sel[i] = True; used_acc.add(r.account_id); used[r.week] = used.get(r.week, 0) + 1; spent += r.cost_t
    return sel


def score(opts: pd.DataFrame, sel, acct_true: pd.DataFrame, cfg: ScheduleConfig, p_col="p", uq_col="uq"):
    """True expected net $ of the chosen options under another probability set (e.g. generator truth)."""
    S = opts[sel]
    if len(S) == 0: return 0.0, S.assign(ev_true=[])
    a = acct_true.loc[S.account_id]
    ev, _ = offer_ev(S, a[p_col].values, a[uq_col].values, a.V0.values, cfg)
    S = S.assign(ev_true=ev * time_factor(a[p_col].values, S.week.values, cfg))
    return float(S.ev_true.sum()), S


def decisions(opts: pd.DataFrame, sel, accounts) -> pd.Series:
    S = opts[sel].set_index("account_id")
    out = pd.Series("silent", index=pd.Index(accounts, name="account_id"))
    out.loc[S.index] = np.where(S.week.values == 0, "act_now", ["wait_until_week_%d" % w for w in S.week.values])
    return out


def solve(candidates_df: pd.DataFrame, budget=None, weekly_cap=None, total_cap=None, **milp_kw):
    """v2 entry point: MILP over (account, action, week) options. Returns the selected rows (copy).
    <= 1 option per account over the whole horizon (so also <= 1 per account per week)."""
    sel = solve_schedule(candidates_df, weekly_cap=weekly_cap, dollar_budget=budget, total_cap=total_cap, **milp_kw)
    out = candidates_df[sel].copy(); check_caps(out, weekly_cap, budget, total_cap); return out


def greedy(candidates_df: pd.DataFrame, budget=None, weekly_cap=None, total_cap=None, fill=False):
    """v2 entry point: best option per account, ranked by value, filled while caps allow (fill=False), or the
    stronger option-level greedy (fill=True, see greedy_fill_schedule). Returns selected rows."""
    f = greedy_fill_schedule if fill else greedy_schedule
    sel = f(candidates_df, weekly_cap=weekly_cap, dollar_budget=budget, total_cap=total_cap)
    out = candidates_df[sel].copy(); check_caps(out, weekly_cap, budget, total_cap); return out


def _mx(s): return int(s.max()) if len(s) else 0


def check_caps(chosen: pd.DataFrame, weekly_cap=None, budget=None, total_cap=None):
    """Hard asserts: <= 1 contact per account (= household: the sandbox has no cross-account household id) per week
    and over the horizon; <= weekly_cap contacts in any week; expected spend <= budget; <= total_cap contacts."""
    assert chosen.account_id.value_counts().pipe(_mx) <= 1, "an account/household got >1 contact"
    assert chosen.groupby(["account_id", "week"]).size().pipe(_mx) <= 1
    if weekly_cap is not None:
        assert chosen.groupby("week").size().pipe(_mx) <= weekly_cap, "weekly contact cap exceeded"
    if budget is not None:
        assert chosen.cost_t.sum() <= budget + 1e-6, "dollar budget exceeded"
    if total_cap is not None:
        assert len(chosen) <= total_cap
    return True


# ------------------------------------------------------------------ v2 glue (new, not in scratch)
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
HIGH_RISK_FRAC = 0.10   # upsell guardrail: no upsell to the top churn-risk decile ...
SUPPORT_BLOCK = 3       # ... or to accounts with >= 3 support contacts in 90 days
UPGRADE_BASE_RATE_Q = 0.039


def decision_accounts(churn_oof: pd.DataFrame, offers: pd.DataFrame, feats: pd.DataFrame,
                      upgrade_oof: pd.DataFrame | None = None) -> pd.DataFrame:
    """Decision inputs per scored account (same as moments/run_schedule.py DEC): p = OOF LR churn prob
    (demo_data/churn_oof_pred.csv), uq = upgrade OOF score rescaled to a 3.9%/qtr mean, V0 = monthly service revenue
    (engine customer_value_usd / 12), upsell_blocked = top-decile risk or >= 3 support contacts / 90 d."""
    if upgrade_oof is None:
        upgrade_oof = pd.read_csv(DATA / "upgrade_oof_lr16.csv")
    oof = churn_oof.set_index("account_id")
    ids = oof.index
    u = upgrade_oof.set_index("account_id").u_score.reindex(ids).values.astype(float)
    p = oof.p_churn_90d.values
    hi = p >= np.quantile(p, 1 - HIGH_RISK_FRAC)
    return pd.DataFrame({"p": p, "uq": np.clip(u * UPGRADE_BASE_RATE_Q / u.mean(), 0, 1),
                         "V0": (offers.customer_value_usd.reindex(ids) / (24 * 0.5)).values,
                         "upsell_blocked": hi | (feats.support_90d.reindex(ids).values >= SUPPORT_BLOCK)}, index=ids)


def run_timing(weekly: pd.DataFrame, acct: pd.DataFrame, all_ids, as_of: date, weeks: int = 12,
               budget=None, weekly_cap=None) -> pd.DataFrame:
    """Per account: timing in {'now','wait','silent'}, wait_until (ISO date of the planning week or ''), timing_action,
    timing_week. Unconstrained by default (the moments headline run). Accounts without a churn score are 'silent'."""
    cfg = ScheduleConfig(weeks=weeks)
    opts = build_options(weekly, acct, cfg)
    chosen = solve(opts, budget=budget, weekly_cap=weekly_cap)
    out = pd.DataFrame(index=pd.Index(list(all_ids), name="account_id"))
    out["timing"] = "silent"; out["wait_until"] = ""; out["timing_action"] = ""; out["timing_week"] = -1
    c = chosen.set_index("account_id")
    out.loc[c.index, "timing"] = np.where(c.week.values == 0, "now", "wait")
    out.loc[c.index, "wait_until"] = [str(as_of + timedelta(days=7 * int(w))) if w > 0 else "" for w in c.week]
    out.loc[c.index, "timing_action"] = c.action_code.values
    out.loc[c.index, "timing_week"] = c.week.astype(int).values
    out["timing_scored"] = out.index.isin(acct.index)
    return out.reset_index()
