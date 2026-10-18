"""Model C: simulated randomized trial + T-learner uplift + offline policy evaluation (IPW and DR).

    python harness/uplift.py        # single command: rebuilds Model B outputs and all Model C outputs

Steps
 1. Model B (offers.py) -> out/offers.csv, out/offer_candidates.csv (behaviour unchanged).
 2. Simulated randomized trial (seed TRIAL_SEED): every account is assigned uniformly at random to one of its
    ELIGIBLE arms (incl. do nothing; eligibility = Model B's sandbox promo rules). A hidden heterogeneous
    true effect on P(stay 90d) (true_effects(), deliberately NOT Model B's EV formula) drives
    outcome_stay_90d ~ Bernoulli(1 - p_churn_90d + true_effect).
 3. T-learner: one LogisticRegression per arm on the ~70% train split (features.csv + p_churn_90d).
    uplift_hat(a) = P(stay|a) - P(stay|do nothing); net_value_hat = uplift_hat x value + upsell - cost - annoyance.
 4. Offline policy evaluation on the 30% test split, IPW and doubly robust, for: Model B EV, uplift policy,
    offer-to-everyone, 3+ calls rule, random, do nothing (+ true-effect oracle for reference).
 5. Qini curve (IPW, test split) + ground-truth curves; charts with the synthetic/circularity footnote.

ALL DATA SYNTHETIC. The "truth" is our own simulation: it is grounded in the sandbox promo rules and our
save-rate assumptions, so the evaluation is partly circular. It shows the method works end to end; it is not
measured lift on real customers.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import os
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offers as ob  # noqa: E402

OUT = ob.OUT_DIR
CHART_DIR = OUT / "charts"
ARTIFACT_DIR = HERE / "model_c_artifacts"   # committed copies for the deck (out/ is gitignored)

# ============================== CONFIG (all synthetic) ==============================
TRIAL_SEED = 2026          # arm assignment + outcome draws
EFFECT_SEED = 1017         # hidden effect noise
SPLIT_SEED = 7
TRAIN_FRAC = 0.70
TRIAL_REPLICATES = 20      # K independent re-randomized cohorts of the same 5,042-account base (fresh arm
                           # assignment + outcome draws each). K=1 is a single trial and is badly underpowered
                           # (~28 churners in the test split vs ~12 true saves); env TM_TRIAL_REPLICATES overrides.
RANDOM_POLICY_SEED = 99
TRIAL_REPLICATES = int(os.environ.get("TM_TRIAL_REPLICATES", TRIAL_REPLICATES))
# ---- TRIAL SIZE KNOB. Default 50,000 simulated accounts (approved by David, Sat 10/17 ~7:25 PM PDT);
# TM_TRIAL_N=0 uses only the 5,042 real sandbox accounts. TM_TRIAL_N=<n> grows the simulated
# population to n accounts by resampling real accounts with jitter (p_churn x lognormal(0, 0.15), continuous
# features x (1 + N(0, 0.05))); clones keep the original's eligibility, drivers and Model B terms and get ids
# like "ACC-00001~1". Clones exist only inside the trial (uplift.csv, policy_eval*): offers.csv and
# offer_candidates.csv are written by offers.py before expansion and always hold the 5,042 real accounts.
TRIAL_N = int(os.environ.get("TM_TRIAL_N", 50000))
TRIAL_N_SEED = 4242
TRIAL_N_P_JITTER_SD = 0.15
TRIAL_N_FEATURE_JITTER_SD = 0.05
PROVISIONAL_NOTE = ("Simulated 50k trial (35k train / 15k test accounts x 20 re-randomized cohorts): targeted "
                    "policies (Model B, Model C, oracle) separate from offer-to-everyone, the 3+ calls rule and "
                    "random beyond noise; Model B vs Model C vs oracle do NOT separate on net value (paired "
                    "95% CIs cross 0, see policy_pairwise.csv)")
MIN_ARM_TRAIN = 40         # fewer treated train rows (or one outcome class) -> fallback model for that arm
LOGREG_C = 0.3
CURVE_POINTS = 101
# Hidden truth: share of would-be churners an arm saves, by problem match (deliberately different from
# Model B's SAVE_RATE table: other levels, tenure/value/bill-shock modifiers, noise, backfires).
TRUE_SAVE = {
    "fix_first": {"network": 0.45, "fixable": 0.30, "billing_only": 0.06, "none": 0.00},
    "care_credit": {"bill_shock": 0.30, "billing": 0.20, "service": 0.10, "none": 0.02},
    "loyalty_credit": {"shopping": 0.15, "none": 0.03},
    "keep_your_phone": {"match": 0.22, "none": 0.04},
    "right_size": {"overpay": 0.35, "billing": 0.15, "none": 0.05},
    "step_up": {"outgrowing": 0.20, "life_event": 0.25, "none": 0.00, "bill_shock_backfire": -0.10},
    "device_upgrade": {"device": 0.25, "free_to_leave": 0.12, "none": 0.03, "bill_shock_backfire": -0.08},
    "variant_switch": {"overpay": 0.30, "billing": 0.18, "none": 0.08},
    "family_upgrade": {"match": 0.20, "none": 0.04, "bill_shock_backfire": -0.10},
    "bill_shock_price_lock": {"bill_shock": 0.33, "billing": 0.18, "none": 0.03},
    "check_in": {"shopping": 0.10, "quiet": 0.06, "none": 0.01},
    "perk_reminder": {"streaming": 0.07, "none": 0.01},
    "home_internet_bundle": {"none": 0.04, "bill_shock_backfire": -0.05},
}
COMBO_CARE_SHARE = 0.8         # combined arm: credit adds 80% of its standalone effect (diminishing returns)
SLEEPING_DOG = 0.004           # contacting a low-risk (<1%) customer with no matching problem lowers P(stay)
NOISE_MULT_SD = 0.35           # multiplicative lognormal noise on the save share
NOISE_ADD_SD = 0.003           # additive noise on the effect
TRUE_SAVE_CAP = 0.85
# =====================================================================================

ARMS = ob.ACTIONS
CODE_BY_LABEL = {v: k for k, v in ob.ACTION_LABEL.items()}
FEATURE_CATS = ["segment", "credit_tier", "contact_preference", "plan_family", "language"]


# ------------------------------------------------------------------ pure functions
def eligible_arms(details: dict) -> dict[str, list[str]]:
    """account_id -> eligible arm codes (always includes do_nothing), from Model B's evaluation."""
    return {a: [k for k in ARMS if ev["res"][k]["eligible"]] for a, ev in details.items()}


def assign_arms(elig: dict[str, list[str]], seed: int = TRIAL_SEED) -> pd.DataFrame:
    """Uniform random assignment over each account's eligible arms. Returns account_id, arm, propensity."""
    rng = np.random.default_rng(seed)
    rows = [{"account_id": a, "arm": arms[rng.integers(len(arms))], "propensity": 1 / len(arms)}
            for a, arms in sorted(elig.items())]
    return pd.DataFrame(rows)


def true_save_share(arm: str, d: dict, tenure: float, value_z: float) -> float:
    """Hidden share of would-be churners saved by `arm` for an account with drivers `d` (before noise)."""
    T = TRUE_SAVE
    if arm == "do_nothing":
        return 0.0
    if arm == "fix_first":
        s = T[arm]["network"] if d["network_pain"] else T[arm]["fixable"] if d["fixable_unresolved"] else \
            T[arm]["billing_only"] if d["unresolved"] else T[arm]["none"]
    elif arm == "care_credit":
        s = T[arm]["bill_shock"] if d["bill_shock_recent"] else T[arm]["billing"] if d["billing_pain"] else \
            T[arm]["service"] if d["service_pain"] else T[arm]["none"]
        s *= 1 - 0.15 * np.clip(value_z, -1, 2)      # $25 matters less to high-value households
    elif arm == "care_credit_fix_first":
        fix = true_save_share("fix_first", d, tenure, value_z)
        care = true_save_share("care_credit", d, tenure, value_z) * COMBO_CARE_SHARE
        return 1 - (1 - fix) * (1 - care)
    elif arm == "loyalty_credit":
        s = (T[arm]["shopping"] if d["shopping"] else T[arm]["none"]) * np.clip(tenure / 60, 0.5, 1.5)
    elif arm == "keep_your_phone":
        s = T[arm]["match"] if d["free_to_leave"] and (d["billing_pain"] or d["shopping"]) else T[arm]["none"]
    elif arm == "right_size":
        s = T[arm]["overpay"] if d["overpay"] else T[arm]["billing"] if d["billing_pain"] else T[arm]["none"]
    elif arm == "step_up":
        s = T[arm]["life_event"] if d["life_event"] else T[arm]["outgrowing"] if d["outgrowing"] else T[arm]["none"]
        if d["bill_shock_recent"]:
            s += T[arm]["bill_shock_backfire"]
    elif arm == "device_upgrade":
        s = T[arm]["device"] if d["device_pain"] else T[arm]["free_to_leave"] if d["free_to_leave"] else T[arm]["none"]
        if d["bill_shock_recent"]:
            s += T[arm]["bill_shock_backfire"]
    elif arm == "variant_switch":
        s = T[arm]["overpay"] if d["overpay"] else T[arm]["billing"] if d["billing_pain"] else T[arm]["none"]
    elif arm == "family_upgrade":
        s = T[arm]["match"] if (d["outgrowing"] or d["device_pain"] or d["free_to_leave"]) else T[arm]["none"]
        if d["bill_shock_recent"]:
            s += T[arm]["bill_shock_backfire"]
    elif arm == "bill_shock_price_lock":
        s = T[arm]["bill_shock"] if d["bill_shock_recent"] else T[arm]["billing"] if d["billing_pain"] else T[arm]["none"]
    elif arm == "check_in":
        s = T[arm]["shopping"] if d["shopping"] else T[arm]["quiet"] if d.get("quiet") else T[arm]["none"]
    elif arm == "perk_reminder":
        s = T[arm]["streaming"] if d.get("streaming") else T[arm]["none"]
    elif arm == "home_internet_bundle":
        s = T[arm]["none"] + (T[arm]["bill_shock_backfire"] if d["bill_shock_recent"] else 0)
    else:
        raise ValueError(arm)
    return s * (0.8 + 0.4 * min(tenure, 120) / 120)   # longer-tenured customers respond a bit more


def true_effects(details: dict, p_churn: pd.Series, tenure: pd.Series, seed: int = EFFECT_SEED) -> pd.DataFrame:
    """Hidden effect on P(stay 90d) per account x eligible arm: true_uplift (do nothing = 0)."""
    rng = np.random.default_rng(seed)
    values = pd.Series({a: ev["value"] for a, ev in details.items()})
    vz = (values - values.mean()) / values.std()
    rows = []
    for a in sorted(details):
        ev, p = details[a], float(p_churn[a])
        for arm in ARMS:
            if not ev["res"][arm]["eligible"]:
                continue
            if arm == "do_nothing":
                rows.append({"account_id": a, "arm": arm, "true_uplift": 0.0})
                continue
            share = true_save_share(arm, ev["drivers"], float(tenure[a]), float(vz[a]))
            share = min(share * np.exp(rng.normal(0, NOISE_MULT_SD)) if share > 0 else share, TRUE_SAVE_CAP)
            eff = p * share + rng.normal(0, NOISE_ADD_SD)
            if p < 0.01 and share <= 0.05:
                eff -= SLEEPING_DOG
            eff = float(np.clip(eff, -(1 - p), p))      # keeps 1 - p + effect inside [0, 1]
            rows.append({"account_id": a, "arm": arm, "true_uplift": round(eff, 6)})
    return pd.DataFrame(rows)


def simulate_outcomes(assign: pd.DataFrame, truth: pd.DataFrame, p_churn: pd.Series,
                      seed: int = TRIAL_SEED + 1) -> pd.DataFrame:
    """outcome_stay_90d ~ Bernoulli(1 - p_churn_90d + true_effect) for the assigned arm."""
    rng = np.random.default_rng(seed)
    t = assign.merge(truth, on=["account_id", "arm"], how="left")
    p_stay = (1 - t["account_id"].map(p_churn) + t["true_uplift"]).clip(0, 1)
    t["outcome_stay_90d"] = (rng.random(len(t)) < p_stay).astype(int)
    return t


def split_accounts(ids: list[str], train_frac: float = TRAIN_FRAC, seed: int = SPLIT_SEED) -> pd.Series:
    rng = np.random.default_rng(seed)
    ids = sorted(ids)
    perm = rng.permutation(len(ids))
    n_train = int(round(train_frac * len(ids)))
    split = np.where(np.isin(np.arange(len(ids)), perm[:n_train]), "train", "test")
    return pd.Series(split, index=ids)


def build_X(features: pd.DataFrame, p_churn: pd.Series) -> pd.DataFrame:
    f = features.set_index("account_id")
    X = f.select_dtypes("number").copy()
    for c in FEATURE_CATS:
        if c in f:
            X = X.join(pd.get_dummies(f[c].astype(str), prefix=c, dtype=float))
    X["p_churn_90d"] = p_churn.reindex(X.index)
    return X.fillna(0.0).astype(float)


def fit_t_learner(X: pd.DataFrame, trial: pd.DataFrame, train_ids) -> dict:
    """One classifier per arm, fit on train accounts assigned that arm. Returns arm -> model info."""
    tr = trial[trial["account_id"].isin(train_ids)]
    models = {}
    for arm in ARMS:
        rows = tr[tr["arm"] == arm]
        y = rows["outcome_stay_90d"].values
        info = {"n_train": int(len(rows)), "stay_rate": float(y.mean()) if len(y) else np.nan}
        if len(rows) >= MIN_ARM_TRAIN and len(np.unique(y)) == 2:
            m = make_pipeline(StandardScaler(), LogisticRegression(C=LOGREG_C, max_iter=3000,
                                                                   class_weight=None))
            m.fit(X.loc[rows["account_id"]].values, y)
            info.update(model=m, kind="logistic")
        else:
            info.update(model=None, kind="fallback")  # do-nothing model + arm's shrunk mean shift
        models[arm] = info
    dn = models["do_nothing"]
    for arm, info in models.items():
        if info["kind"] == "fallback":
            k = info["n_train"]
            shift = (info["stay_rate"] - dn["stay_rate"]) if k else 0.0
            info["shift"] = float(shift * k / (k + 100))  # shrink toward 0 with few rows
    return models


def predict_stay(models: dict, X: pd.DataFrame, arm: str) -> np.ndarray:
    info = models[arm]
    if info["kind"] == "logistic":
        return info["model"].predict_proba(X.values)[:, 1]
    base = predict_stay(models, X, "do_nothing")
    return np.clip(base + info["shift"], 0, 1)


def terms(details: dict, a: str, arm: str) -> tuple[float, float, float, float]:
    """Model B's (value, cost, annoyance, upsell_gain) for account a and arm (eligible rows only)."""
    ev = details[a]
    if arm == "do_nothing":
        return ev["value"], 0.0, 0.0, 0.0
    r = ev["res"][arm]
    return ev["value"], r["forced_cost"], r["forced_annoyance"], r["forced_gain"]


# ------------------------------------------------------------------ policies
def make_policies(long: pd.DataFrame, offers: pd.DataFrame, facts: pd.DataFrame) -> dict[str, pd.Series]:
    """Policy name -> Series(account_id -> arm code). All picks are eligible arms. (Vectorized for 50k+.)"""
    ids = pd.Index(sorted(long["account_id"].unique()))
    rng = np.random.default_rng(RANDOM_POLICY_SEED)
    evs = offers.set_index("account_id")
    sup = facts.set_index("account_id")["support_90d"].reindex(ids)
    offers_only = long[long.action_code != "do_nothing"]
    best_offer = offers_only.sort_values(["account_id", "ev_b"], ascending=[True, False]) \
        .drop_duplicates("account_id").set_index("account_id")["action_code"].reindex(ids).fillna("do_nothing")
    # random eligible arm: random key per (account, arm), take the max
    rnd = long[["account_id", "action_code"]].assign(k=rng.random(len(long)))
    random_pick = rnd.sort_values(["account_id", "k"]).drop_duplicates("account_id", keep="last") \
        .set_index("account_id")["action_code"].reindex(ids)
    has_cc = set(long.loc[long.action_code == "care_credit", "account_id"])
    calls = pd.Series(np.where((sup.values >= 3) & ids.isin(list(has_cc)), "care_credit", "do_nothing"), index=ids)
    pick_up = long[long["pick_uplift"]].set_index("account_id")["action_code"]
    tru = long.assign(true_net=long["true_uplift"] * long["value"] + long["gain"] - long["cost"] - long["annoyance"])
    top = tru.sort_values(["account_id", "true_net"], ascending=[True, False]).drop_duplicates("account_id") \
        .set_index("account_id")
    oracle = pd.Series(np.where(top["true_net"] > 0, top["action_code"], "do_nothing"), index=top.index)
    return {
        "do nothing": pd.Series("do_nothing", index=ids),
        "random (eligible arm)": random_pick,
        "3+ calls rule -> $25 care credit": calls,
        "offer to everyone (best eligible offer)": best_offer,
        "Model B EV chooser": evs["action_code"].reindex(ids),
        "Model C uplift policy": pick_up.reindex(ids),
        "oracle (true effects; reference only)": oracle.reindex(ids),
    }


# ------------------------------------------------------------------ offline policy evaluation
def ope(policy: pd.Series, test: pd.DataFrame, long_test: pd.DataFrame, reps: int) -> dict:
    """IPW (self-normalized) and DR estimates on the randomized test split, reported per test split.

    test: one row per (replicate, test account) with assigned arm, propensity, outcome and the assigned arm's
    value/cost/gain. long_test: account x eligible arm with p_stay_hat, cost, gain, true_uplift.
    Rewards: stay (0/1); value_net = stay x value - cost; value_net_up = value_net + stay x upsell gain.
    """
    keep = ["account_id", "action_code", "p_stay_hat", "value", "cost", "gain", "true_uplift", "p_churn"]
    pi = policy.dropna().rename("action_code").rename_axis("account_id").reset_index()
    sel = pi.merge(long_test[keep], on=["account_id", "action_code"], how="left")   # one row per test account
    t = test.merge(pi.rename(columns={"action_code": "pi"}), on="account_id", how="left")
    t = t.merge(long_test[["account_id", "action_code", "p_stay_hat"]].rename(
        columns={"action_code": "arm", "p_stay_hat": "mu_obs"}), on=["account_id", "arm"], how="left")
    t = t.merge(sel[["account_id", "p_stay_hat", "value", "cost", "gain"]].rename(
        columns={"p_stay_hat": "mu_pi", "value": "v_pi", "cost": "c_pi", "gain": "g_pi"}), on="account_id", how="left")
    w = ((t["arm"] == t["pi"]).astype(float) / t["propensity"]).values
    y = t["outcome_stay_90d"].astype(float).values
    r = y * t["value"].values - t["cost"].values
    r_up = r + y * t["gain"].values
    n_acc = len(sel)

    def hajek(v):
        return float(n_acc * (w * v).sum() / w.sum())

    def dr(mu_pi_v, mu_obs_v, v):
        return float((mu_pi_v + w * (v - mu_obs_v)).sum() / reps)

    m_pi_y, m_obs_y = t["mu_pi"].values, t["mu_obs"].values
    m_pi_r = m_pi_y * t["v_pi"].values - t["c_pi"].values
    m_obs_r = m_obs_y * t["value"].values - t["cost"].values
    m_pi_ru = m_pi_r + m_pi_y * t["g_pi"].values
    m_obs_ru = m_obs_r + m_obs_y * t["gain"].values
    return {
        "stay_ipw": hajek(y), "stay_dr": dr(m_pi_y, m_obs_y, y),
        "net_ipw": hajek(r), "net_dr": dr(m_pi_r, m_obs_r, r),
        "netup_ipw": hajek(r_up), "netup_dr": dr(m_pi_ru, m_obs_ru, r_up),
        "n_contacted": int((sel["action_code"] != "do_nothing").sum()), "offer_cost": float(sel["cost"].sum()),
        "true_saves": float(sel["true_uplift"].sum()),
        "true_net": float((sel["true_uplift"] * sel["value"] - sel["cost"]).sum()),
        "true_netup": float((sel["true_uplift"] * sel["value"] - sel["cost"]
                             + (1 - sel["p_churn"] + sel["true_uplift"]) * sel["gain"]).sum()),
        "n": n_acc, "n_trial_rows": len(t),
    }


def replicate_spread(policies: dict, test: pd.DataFrame, long_test: pd.DataFrame, reps: int) -> pd.DataFrame:
    """Per-replicate DR/IPW estimates (each replicate = one full re-randomized trial), minus do nothing.
    Returns long table: replicate, policy, churners_saved_dr, net_no_upsell_dr, net_with_upsell_dr (+ ipw)."""
    rows = []
    for rep in range(reps):
        tr = test[test["rep"] == rep]
        res = {k: ope(v, tr, long_test, 1) for k, v in policies.items()}
        base = res["do nothing"]
        for k, r in res.items():
            rows.append({"replicate": rep, "policy": k,
                         "churners_saved_dr": r["stay_dr"] - base["stay_dr"],
                         "net_no_upsell_dr": r["net_dr"] - base["net_dr"],
                         "net_with_upsell_dr": r["netup_dr"] - base["netup_dr"],
                         "churners_saved_ipw": r["stay_ipw"] - base["stay_ipw"],
                         "net_no_upsell_ipw": r["net_ipw"] - base["net_ipw"]})
    return pd.DataFrame(rows)


def spread_summary(rs: pd.DataFrame, reps: int) -> pd.DataFrame:
    """95% CI of the pooled (mean over replicates) estimate: mean +/- 1.96 x SD / sqrt(K)."""
    out = []
    for pol, g in rs.groupby("policy", sort=False):
        row = {"policy": pol}
        for c in ["churners_saved_dr", "net_no_upsell_dr", "net_with_upsell_dr"]:
            m, sd = g[c].mean(), g[c].std(ddof=1)
            half = 1.96 * sd / np.sqrt(reps)
            row[f"{c}_ci_low"], row[f"{c}_ci_high"], row[f"{c}_rep_sd"] = round(m - half, 2), round(m + half, 2), round(sd, 2)
        out.append(row)
    return pd.DataFrame(out)


def pairwise_diffs(rs: pd.DataFrame, pairs: list[tuple[str, str]], reps: int) -> pd.DataFrame:
    """Paired per-replicate differences A - B with 95% CI (same replicate = same randomization)."""
    out = []
    for a, b in pairs:
        A = rs[rs.policy == a].set_index("replicate")
        B = rs[rs.policy == b].set_index("replicate")
        for c in ["churners_saved_dr", "net_no_upsell_dr", "net_with_upsell_dr"]:
            d = A[c] - B[c]
            half = 1.96 * d.std(ddof=1) / np.sqrt(reps)
            out.append({"comparison": f"{a} minus {b}", "metric": c, "mean_diff": round(d.mean(), 2),
                        "ci_low": round(d.mean() - half, 2), "ci_high": round(d.mean() + half, 2),
                        "separates": bool(d.mean() - half > 0 or d.mean() + half < 0),
                        "replicates_A_wins": int((d > 0).sum())})
    return pd.DataFrame(out)


def policy_table(policies: dict, test: pd.DataFrame, long_test: pd.DataFrame, reps: int) -> pd.DataFrame:
    res = {k: ope(v, test, long_test, reps) for k, v in policies.items()}
    base = res["do nothing"]
    # true do-nothing upsell baseline is 0 (no gain without an upsell arm)
    rows = []
    for k, r in res.items():
        row = {"policy": k, "n_test_accounts": r["n"], "trial_replicates": reps, "n_contacted": r["n_contacted"],
               "offer_cost_usd": round(r["offer_cost"], 0)}
        for est in ("ipw", "dr"):
            saves = r[f"stay_{est}"] - base[f"stay_{est}"]
            row[f"churners_saved_{est}"] = round(saves, 2)
            row[f"net_value_no_upsell_{est}_usd"] = round(r[f"net_{est}"] - base[f"net_{est}"], 0)
            row[f"net_value_with_upsell_{est}_usd"] = round(r[f"netup_{est}"] - base[f"netup_{est}"], 0)
            row[f"cost_per_save_{est}_usd"] = round(r["offer_cost"] / saves, 2) if saves > 0.05 else np.nan
        row["true_churners_saved"] = round(r["true_saves"], 2)
        row["true_net_value_no_upsell_usd"] = round(r["true_net"], 0)
        row["true_net_value_with_upsell_usd"] = round(r["true_netup"], 0)
        row["true_cost_per_save_usd"] = round(r["offer_cost"] / r["true_saves"], 2) if r["true_saves"] > 0.05 else np.nan
        rows.append(row)
    pe = pd.DataFrame(rows)
    pe["data_note"] = ("SYNTHETIC simulated randomized trial (K re-randomized cohorts, reported per test split), "
                       "test split only; self-normalized IPW and doubly-robust estimates; "
                       "true_* columns use the hidden simulated effects. Truth is grounded in our own save-rate "
                       "assumptions (partly circular); not measured lift. Net value = 24-month margin net of "
                       "offer cost (annoyance excluded). " + PROVISIONAL_NOTE)
    return pe


# ------------------------------------------------------------------ Qini curve
def qini_curves(test: pd.DataFrame, long_test: pd.DataFrame, offers: pd.DataFrame,
                facts: pd.DataFrame, reps: int) -> pd.DataFrame:
    """Multi-arm Qini on the randomized test split. Each model ranks test accounts and names one treatment arm
    per account; treating the top k is valued by the IPW estimate of incremental stays:
        sum_{i in top k} [ 1(A_i = do nothing) C_i / e_i  -  1(A_i = arm_i) C_i / e_i ],  C = 1 - stay (churned)
    (same expectation as the stay form, far lower variance because churn is rare)
    cum_true_incremental_saves (extra column) is the same ranking valued with the hidden true effects."""
    lt = long_test[long_test["action_code"] != "do_nothing"]
    sup = facts.set_index("account_id")["support_90d"]
    evs = offers.set_index("account_id")
    rng = np.random.default_rng(RANDOM_POLICY_SEED + 1)
    ids = pd.Index(sorted(test["account_id"].unique()))

    def best(col):
        b = lt.sort_values(col, ascending=False).drop_duplicates("account_id").set_index("account_id")
        return b.reindex(ids)

    b_up, b_ev, b_true = best("uplift_hat"), best("ev_b"), best("true_uplift")
    specs = {
        "Model C (T-learner uplift)": (b_up["uplift_hat"], b_up["action_code"]),
        "Model B (expected value)": (b_ev["ev_b"], b_ev["action_code"]),
        "Model A (churn risk only)": (evs["p_churn_90d"].reindex(ids), b_ev["action_code"]),
        "3+ support calls rule": (sup.reindex(ids) + 1e-6 * rng.random(len(ids)), b_ev["action_code"]),
        "random": (pd.Series(rng.random(len(ids)), index=ids), b_ev["action_code"]),
        "oracle (true uplift)": (b_true["true_uplift"], b_true["action_code"]),
    }
    true_map = lt.set_index(["account_id", "action_code"])["true_uplift"]
    fr = np.linspace(0, 1, CURVE_POINTS)
    rows = []
    for name, (score, rec) in specs.items():
        has = rec.notna()
        order = score.where(has, -np.inf).sort_values(ascending=False, kind="mergesort").index
        rec_o = rec.reindex(order)
        tt = test.assign(rec=test["account_id"].map(rec))
        c = ((tt["arm"] == "do_nothing").astype(float) * tt["rec"].notna()
             - ((tt["arm"] == tt["rec"]) & tt["rec"].notna()).astype(float)) \
            * (1 - tt["outcome_stay_90d"]) / tt["propensity"]
        contrib = c.groupby(tt["account_id"]).sum().reindex(order).fillna(0) / reps
        tru = pd.DataFrame({"account_id": rec_o.index, "action_code": rec_o.values}).merge(
            lt[["account_id", "action_code", "true_uplift"]], on=["account_id", "action_code"], how="left")[
            "true_uplift"].fillna(0.0).values
        cs = np.concatenate([[0.0], contrib.cumsum().values])
        ct = np.concatenate([[0.0], np.cumsum(tru)])
        n = len(order)
        for f in fr:
            k = int(round(f * n))
            rows.append({"policy_or_model": name, "frac_targeted": round(f, 2),
                         "cum_incremental_saves": round(cs[k], 3), "random_baseline": round(f * cs[-1], 3),
                         "cum_true_incremental_saves": round(ct[k], 3),
                         "true_random_baseline": round(f * ct[-1], 3)})
    curve = pd.DataFrame(rows)
    curve["data_note"] = ("SYNTHETIC simulated trial (K re-randomized cohorts, per test split); IPW Qini on churn "
                          "outcome; true_* = hidden simulated effects")
    return curve


def auuc_table(curve: pd.DataFrame) -> pd.DataFrame:
    """Area between each curve and its random baseline (mean over frac points), IPW and true."""
    g = curve.groupby("policy_or_model", sort=False)
    t = pd.DataFrame({
        "qini_area_ipw": g.apply(lambda d: (d.cum_incremental_saves - d.random_baseline).mean()),
        "qini_area_true": g.apply(lambda d: (d.cum_true_incremental_saves - d.true_random_baseline).mean()),
    })
    orc = t.loc["oracle (true uplift)", "qini_area_true"]
    t["share_of_oracle_true"] = (t["qini_area_true"] / orc).round(3)
    return t.round(3)


# ------------------------------------------------------------------ charts
FOOTNOTE = ("SYNTHETIC: simulated customers (50k resampled from the 5,042 sandbox accounts) and a simulated randomized trial. Circularity caveat: the "
            "hidden 'true' effects are built from our own\nsave-rate assumptions and sandbox promo rules, so this "
            "validates the method end to end, not real-world lift. No real offer outcomes exist.\n"
            "Simulated 50k trial (15k test accounts x 20 cohorts): targeted policies beat blanket offers and the "
            "3+ calls rule beyond noise; Model B vs Model C vs oracle are within noise on net value.")


def charts(curve: pd.DataFrame, pe: pd.DataFrame) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed: PNGs skipped (CSVs written)")
        return []
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    colors = {"Model C (T-learner uplift)": "#e20074", "Model B (expected value)": "#1f77b4",
              "Model A (churn risk only)": "#2ca02c", "3+ support calls rule": "#d62728",
              "random": "#7f7f7f", "oracle (true uplift)": "#000000"}
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6))
    for ax, ycol, bcol, title in [
            (axes[0], "cum_incremental_saves", "random_baseline", "Estimated from trial outcomes (IPW Qini)"),
            (axes[1], "cum_true_incremental_saves", "true_random_baseline", "Same rankings, hidden true effects")]:
        for name, g in curve.groupby("policy_or_model", sort=False):
            if name == "random":
                continue
            ax.plot(g.frac_targeted * 100, g[ycol], label=name, color=colors.get(name),
                    lw=1.2 if name.startswith("oracle") else 2, ls=":" if name.startswith("oracle") else "-")
        g0 = curve[curve.policy_or_model == "Model C (T-learner uplift)"]
        ax.plot(g0.frac_targeted * 100, g0[bcol], "k--", lw=1, label="random baseline (Model C)")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("% of test customers contacted (highest score first)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("cumulative incremental saves (test split)")
    axes[1].legend(fontsize=8, loc="lower right")
    fig.suptitle("Who to contact: Qini / uplift curves (SIMULATED)")
    fig.tight_layout(rect=(0, 0.10, 1, 0.97))
    fig.text(0.01, 0.01, FOOTNOTE, fontsize=7, color="#444444")
    p1 = CHART_DIR / "uplift_curve.png"
    fig.savefig(p1, dpi=140)
    plt.close(fig)

    d = pe[~pe.policy.str.startswith("oracle")].iloc[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4), sharey=True)
    for ax, col, title in [(axes[0], "no_upsell", "Retention value only (no upsell revenue)"),
                           (axes[1], "with_upsell", "Including step-up / device upsell revenue")]:
        y = np.arange(len(d))
        ax.barh(y, d[f"net_value_{col}_dr_usd"] / 1000, color=["#e20074" if "Model" in s else "#999999"
                                                                  for s in d.policy], label="doubly robust")
        ax.scatter(d[f"net_value_{col}_ipw_usd"] / 1000, y, color="k", marker="|", s=200, label="IPW", zorder=3)
        ax.scatter(d[f"true_net_value_{col}_usd"] / 1000, y, color="#1f77b4", marker="D", s=25,
                   label="true (hidden)", zorder=3)
        ax.axvline(0, color="k", lw=0.8)
        ax.set_yticks(y, d.policy, fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("net value vs do nothing, $k (test split, 24-mo margin minus offer cost)")
        ax.grid(axis="x", alpha=0.3)
    axes[1].legend(fontsize=8)
    fig.suptitle("Policy value on the simulated trial (SIMULATED)")
    fig.tight_layout(rect=(0, 0.10, 1, 0.97))
    fig.text(0.01, 0.01, FOOTNOTE, fontsize=7, color="#444444")
    p2 = CHART_DIR / "policy_value.png"
    fig.savefig(p2, dpi=140)
    plt.close(fig)
    return [str(p1), str(p2)]


def expand_population(n_target: int, offers: pd.DataFrame, details: dict, features: pd.DataFrame,
                      facts: pd.DataFrame, seed: int = TRIAL_N_SEED):
    """Grow the simulated population to n_target accounts by resampling real accounts with jitter (TM_TRIAL_N)."""
    n0 = len(offers)
    if n_target <= n0:
        return offers, details, features, facts
    rng = np.random.default_rng(seed)
    src = rng.choice(offers["account_id"].values, size=n_target - n0, replace=True)
    count: dict[str, int] = {}
    new_ids = []
    for a in src:
        count[a] = count.get(a, 0) + 1
        new_ids.append(f"{a}~{count[a]}")
    m = dict(zip(new_ids, src))
    o2 = offers.set_index("account_id").loc[src].reset_index(drop=True)
    o2.insert(0, "account_id", new_ids)
    o2["p_churn_90d"] = (o2["p_churn_90d"] * np.exp(rng.normal(0, TRIAL_N_P_JITTER_SD, len(o2)))).clip(1e-4, 0.95)
    f2 = features.set_index("account_id").loc[src].reset_index(drop=True)
    cont = [c for c in f2.select_dtypes("float").columns if c != "is_persona"]
    f2[cont] = f2[cont] * (1 + rng.normal(0, TRIAL_N_FEATURE_JITTER_SD, (len(f2), len(cont))))
    f2.insert(0, "account_id", new_ids)
    x2 = facts.set_index("account_id").loc[src].reset_index(drop=True)
    x2.insert(0, "account_id", new_ids)
    d2 = dict(details)
    d2.update({nid: details[orig] for nid, orig in m.items()})
    return (pd.concat([offers, o2], ignore_index=True), d2, pd.concat([features, f2], ignore_index=True),
            pd.concat([facts, x2], ignore_index=True))


# ------------------------------------------------------------------ pipeline
UPLIFT_COLS = ["account_id", "action", "split", "treated", "propensity", "outcome_stay_90d", "uplift_hat",
               "net_value_hat", "true_uplift", "pick_uplift", "pick_ev", "synthetic"]


def _mtime(p: Path):
    return p.stat().st_mtime if p.exists() else None


def run_once() -> dict:
    scores_mtime = _mtime(OUT / "churn_scores.csv")
    offers = ob.main().reset_index(drop=True)
    details = ob.DETAILS
    features = pd.read_csv(OUT / "features.csv")
    conn = ob.det.connect_ro()
    facts, _ = ob.det.apply_features_csv(ob.det.build_account_facts(conn), OUT / "features.csv")
    details = dict(details)
    if TRIAL_N > len(offers):
        offers, details, features, facts = expand_population(TRIAL_N, offers, details, features, facts)
    p = offers.set_index("account_id")["p_churn_90d"]
    tenure = facts.set_index("account_id")["tenure_months"]

    elig = eligible_arms(details)
    truth = true_effects(details, p, tenure)
    trials = []
    for rep in range(TRIAL_REPLICATES):
        tr_r = simulate_outcomes(assign_arms(elig, TRIAL_SEED + 1000 * rep), truth, p, TRIAL_SEED + 1000 * rep + 1)
        trials.append(tr_r.assign(rep=rep))
    trial = pd.concat(trials, ignore_index=True)
    split = split_accounts(list(elig))
    X = build_X(features, p).reindex(sorted(elig))
    models = fit_t_learner(X, trial, split[split == "train"].index)

    # long table: account x eligible arm
    long = truth.rename(columns={"arm": "action_code"})
    stay_hat = {arm: pd.Series(predict_stay(models, X, arm), index=X.index) for arm in ARMS}
    sh = pd.DataFrame(stay_hat).rename_axis("account_id").reset_index().melt(
        id_vars="account_id", var_name="action_code", value_name="p_stay_hat")
    long = long.merge(sh, on=["account_id", "action_code"], how="left")
    long["p_stay_dn_hat"] = long["account_id"].map(stay_hat["do_nothing"])
    long["uplift_hat"] = np.where(long.action_code == "do_nothing", 0.0, long.p_stay_hat - long.p_stay_dn_hat)
    tv = [terms(details, a, k) for a, k in zip(long.account_id, long.action_code)]
    long[["value", "cost", "annoyance", "gain"]] = pd.DataFrame(tv, index=long.index)
    long["net_value_hat"] = np.where(long.action_code == "do_nothing", 0.0,
                                     long.uplift_hat * long.value + long.gain - long.cost - long.annoyance)
    evs = offers.set_index("account_id")
    evcols = {f"ev_{k}": k for k in ARMS if k != "do_nothing"}
    evl = evs[list(evcols)].rename(columns=evcols).rename_axis("account_id").reset_index().melt(
        id_vars="account_id", var_name="action_code", value_name="ev_b")
    long = long.merge(evl, on=["account_id", "action_code"], how="left")
    long["ev_b"] = long["ev_b"].where(long.action_code != "do_nothing", 0.0).fillna(0.0)
    best_up = long.sort_values(["net_value_hat"], ascending=False).drop_duplicates("account_id").set_index("account_id")
    pick = best_up.apply(lambda r: r["action_code"] if r["net_value_hat"] > 0 else "do_nothing", axis=1)
    long["pick_uplift"] = long.action_code == long.account_id.map(pick)
    long["pick_ev"] = long.action_code == long.account_id.map(evs["action_code"])
    long["p_churn"] = long.account_id.map(p)
    long["split"] = long.account_id.map(split)
    tr = trial[trial.rep == 0].set_index("account_id")   # uplift.csv shows the first trial cohort
    long["treated"] = long.action_code == long.account_id.map(tr["arm"])
    long["propensity"] = long.account_id.map(tr["propensity"])
    long["outcome_stay_90d"] = np.where(long.treated, long.account_id.map(tr["outcome_stay_90d"]), np.nan)
    long["action"] = long.action_code.map(ob.ACTION_LABEL)
    long["synthetic"] = True

    out_long = long.copy()
    out_long["outcome_stay_90d"] = out_long["outcome_stay_90d"].astype("Int64")
    for c in ("uplift_hat", "net_value_hat"):
        out_long[c] = out_long[c].round(6 if c == "uplift_hat" else 2)
    out_long[UPLIFT_COLS].sort_values(["account_id", "action"]).to_csv(OUT / "uplift.csv", index=False)

    # test split evaluation
    test_ids = split[split == "test"].index
    lt = long[long.account_id.isin(test_ids)]
    test = trial[trial.account_id.isin(test_ids)][["rep", "account_id", "arm", "propensity", "outcome_stay_90d"]] \
        .merge(long[["account_id", "action_code", "value", "cost", "gain"]]
               .rename(columns={"action_code": "arm"}), on=["account_id", "arm"], how="left")
    policies = make_policies(long, offers, facts)
    pols = {k: v.reindex(test_ids) for k, v in policies.items()}
    pe = policy_table(pols, test, lt, TRIAL_REPLICATES)
    rs = replicate_spread(pols, test, lt, TRIAL_REPLICATES)
    ss = spread_summary(rs, TRIAL_REPLICATES)
    pe = pe.merge(ss, on="policy", how="left")
    pe = pe[[c for c in pe.columns if c != "data_note"] + ["data_note"]]
    pe.to_csv(OUT / "policy_eval.csv", index=False)
    rs.to_csv(OUT / "policy_eval_replicates.csv", index=False)
    diffs = pairwise_diffs(rs, [("Model B EV chooser", "oracle (true effects; reference only)"),
                                ("Model B EV chooser", "Model C uplift policy"),
                                ("Model C uplift policy", "oracle (true effects; reference only)"),
                                ("Model B EV chooser", "offer to everyone (best eligible offer)"),
                                ("Model B EV chooser", "3+ calls rule -> $25 care credit")], TRIAL_REPLICATES)
    diffs.to_csv(OUT / "policy_pairwise.csv", index=False)
    curve = qini_curves(test, lt, offers, facts, TRIAL_REPLICATES)
    curve.to_csv(OUT / "uplift_curve.csv", index=False)
    auuc = auuc_table(curve)
    auuc.to_csv(OUT / "uplift_auuc.csv")
    pngs = charts(curve, pe)

    # deck-ready committed copies (only for the canonical out/ dir, so test runs never overwrite them)
    write_artifacts = OUT.resolve() == (HERE / "out").resolve()
    if write_artifacts:
        ARTIFACT_DIR.mkdir(exist_ok=True)
    for src in ([] if not write_artifacts else [OUT / "policy_eval.csv", OUT / "uplift_curve.csv", OUT / "uplift_auuc.csv",
                                                  OUT / "policy_pairwise.csv"] + [Path(x) for x in pngs]):
        shutil.copy2(src, ARTIFACT_DIR / src.name)

    lt_c = lt[lt.action_code != "do_nothing"]
    corr_p = float(np.corrcoef(lt_c.uplift_hat, lt_c.true_uplift)[0, 1])
    corr_s = float(lt_c[["uplift_hat", "true_uplift"]].corr(method="spearman").iloc[0, 1])
    return {
        "churn_scores_mtime_used": datetime.fromtimestamp(scores_mtime).strftime("%Y-%m-%d %H:%M:%S") + " PDT",
        "churn_scores_mtime_epoch": scores_mtime,
        "churn_source": offers["churn_source"].iloc[0],
        "n_train": int((split == "train").sum()), "n_test": int((split == "test").sum()),
        "trial_replicates": TRIAL_REPLICATES, "trial_n_accounts": len(offers),
        "arm_models": {k: {"kind": v["kind"], "n_train": v["n_train"]} for k, v in models.items()},
        "corr_uplift_hat_true_test_pearson": round(corr_p, 3),
        "corr_uplift_hat_true_test_spearman": round(corr_s, 3),
        "trial_stay_rate": round(float(trial.outcome_stay_90d.mean()), 4),
        "pngs": pngs, "auuc": auuc.reset_index().to_dict(orient="records"),
    }


def main() -> dict:
    t0 = time.time()
    info = run_once()
    now = _mtime(OUT / "churn_scores.csv")
    if now is not None and now != info["churn_scores_mtime_epoch"]:
        print("churn_scores.csv changed during the run; rebuilding on the fresh scores")
        info = run_once()
    info["finished"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " PDT"
    info["elapsed_s"] = round(time.time() - t0, 1)
    (OUT / "offers_pipeline_run.json").write_text(json.dumps(info, indent=2, default=str))
    return info


if __name__ == "__main__":
    info = main()
    pd.set_option("display.width", 250)
    pe = pd.read_csv(OUT / "policy_eval.csv")
    print(pe.drop(columns=["data_note"]).to_string(index=False))
    print(json.dumps({k: v for k, v in info.items() if k != "churn_scores_mtime_epoch"}, indent=2, default=str))
    print("ALL NUMBERS SYNTHETIC / SIMULATED.")
