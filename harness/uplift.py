"""Model C (uplift / policy evaluation) and the single rerunnable tm-offers pipeline.

    python harness/uplift.py

1. Runs Model B (offers.py): out/offers.csv, out/offer_candidates.csv
2. Model C uplift score per account: out/uplift.csv
     uplift_score = p_churn_90d (Model A) x save_rate of the account's best retention action (Model B)
   i.e. the expected incremental save from contacting them: "persuadable x at-risk", not risk alone.
3. Policy evaluation (out/policy_eval.csv) and Qini/uplift curves (out/uplift_curve.csv) + PNG charts.
4. If out/churn_scores.csv changed while this ran, everything is rebuilt once more on the fresh file.

HOW IT IS SCORED (read before quoting any number): there are no real offer outcomes in the sandbox.
Policies are evaluated with tm-data's SYNTHETIC ground-truth churn probability (out/labels.csv, p_true_90d)
when present, otherwise with Model A's p_churn_90d. Save rates, costs and annoyance are Model B's own
SYNTHETIC assumptions (CONFIG in offers.py). So this measures how well each targeting rule spends contacts
under those assumptions; it is NOT measured lift and must be labeled "simulated" on screen.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offers as ob  # noqa: E402

OUT = ob.OUT_DIR
SEED = 26  # random baseline ordering (deterministic)
CURVE_POINTS = 101  # 0%, 1%, ..., 100% targeted
RETENTION_ACTIONS = [a for a in ob.ACTIONS if a != "do_nothing"]


def _mtime(path: Path) -> float | None:
    return path.stat().st_mtime if path.exists() else None


def _fmt(ts: float | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S %Z").strip() + " PDT" if ts else "n/a"


def load_eval_probability(offers: pd.DataFrame) -> tuple[pd.Series, str]:
    labels = OUT / "labels.csv"
    if labels.exists():
        lab = pd.read_csv(labels)
        if "p_true_90d" in lab.columns:
            p = lab.set_index("account_id")["p_true_90d"].reindex(offers["account_id"])
            if p.notna().all():
                return p.reset_index(drop=True), "p_true_90d (tm-data synthetic labels)"
    return offers["p_churn_90d"].reset_index(drop=True), "p_churn_90d (Model A; labels.csv unavailable)"


def terms(ev: dict, action: str) -> tuple[float, float, float, float]:
    r = ev["res"][action]
    if action == "do_nothing":
        return 0.0, 0.0, 0.0, 0.0
    return r["forced_save_rate"], r["forced_cost"], r["forced_annoyance"], r["forced_gain"]


def build_uplift(offers: pd.DataFrame, p_eval: pd.Series) -> pd.DataFrame:
    rows = []
    for i, o in offers.reset_index(drop=True).iterrows():
        ev = ob.DETAILS[o["account_id"]]
        elig = [(a, ev["res"][a]["ev"]) for a in RETENTION_ACTIONS if ev["res"][a]["eligible"]]
        best = max(elig, key=lambda t: (t[1], -ob.ACTIONS.index(t[0])))[0] if elig else None
        sr, cost, ann, gain = terms(ev, best) if best else (0.0, 0.0, 0.0, 0.0)
        value = ev["value"]
        pt = float(p_eval.iloc[i])
        rows.append({
            "account_id": o["account_id"],
            "best_retention_action": ob.ACTION_LABEL[best] if best else "none eligible",
            "p_churn_90d": o["p_churn_90d"], "risk_rank": o["risk_rank"],
            "save_rate": sr, "uplift_score": round(o["p_churn_90d"] * sr, 6),
            "model_b_action": o["action"], "model_b_ev": o["expected_value"],
            "p_eval_90d": pt, "sim_incremental_save": round(pt * sr, 6),
            "sim_net_value_if_treated": round(pt * sr * value + gain - cost - ann, 2),
            "customer_value_usd": round(value, 2),
            "support_90d": ev.get("support_90d", np.nan),
        })
    up = pd.DataFrame(rows)
    up["uplift_rank"] = up["uplift_score"].rank(ascending=False, method="first").astype(int)
    up["data_note"] = "synthetic/simulated"
    return up.sort_values("uplift_rank")


def policy_eval(offers: pd.DataFrame, up: pd.DataFrame, p_eval: pd.Series, facts: pd.DataFrame) -> pd.DataFrame:
    """Each policy = which accounts get which action. Scored with p_eval x Model B save rates (simulated)."""
    o = offers.reset_index(drop=True)
    sup = facts.set_index("account_id")["support_90d"].reindex(o["account_id"]).values
    n = len(o)
    best_code = {lab: code for code, lab in ob.ACTION_LABEL.items()}
    up_i = up.set_index("account_id").reindex(o["account_id"])
    top20_risk = set(o.nsmallest(int(round(0.2 * n)), "risk_rank")["account_id"])
    n_model_b = int((o["action"] != "do nothing").sum())
    top_uplift = set(up.nsmallest(n_model_b, "uplift_rank")["account_id"])

    policies = {
        "no outreach": lambda i, a: "do_nothing",
        "blanket $25 care credit (everyone)": lambda i, a: "care_credit",
        "3+ support calls rule -> $25 care credit": lambda i, a: "care_credit" if sup[i] >= 3 else "do_nothing",
        "Model A top 20% risk -> best eligible action": lambda i, a: (
            best_code.get(up_i.loc[a, "best_retention_action"], "do_nothing") if a in top20_risk else "do_nothing"),
        f"Model C top {n_model_b} by uplift -> best eligible action": lambda i, a: (
            best_code.get(up_i.loc[a, "best_retention_action"], "do_nothing") if a in top_uplift else "do_nothing"),
        "Model B EV chooser (do nothing allowed)": lambda i, a: o.loc[i, "action_code"],
    }
    out = []
    for name, pick in policies.items():
        saves = cost = ann = gain = retained = 0.0
        k = 0
        for i, a in enumerate(o["account_id"]):
            act = pick(i, a)
            if act == "do_nothing":
                continue
            ev = ob.DETAILS[a]
            sr, c, an, g = terms(ev, act)
            pt = float(p_eval.iloc[i])
            k += 1
            saves += pt * sr
            retained += pt * sr * ev["value"]
            cost += c
            ann += an
            gain += g
        net = retained + gain - cost - ann
        out.append({
            "policy": name, "n_targeted": k, "frac_targeted": round(k / n, 4),
            "sim_incremental_saves": round(saves, 2), "sim_retained_value_usd": round(retained, 0),
            "sim_upsell_gain_usd": round(gain, 0), "offer_cost_usd": round(cost, 0),
            "annoyance_usd": round(ann, 0), "sim_net_value_usd": round(net, 0),
            "sim_net_value_per_contact_usd": round(net / k, 2) if k else 0.0,
            "saves_per_1000_contacts": round(1000 * saves / k, 1) if k else 0.0,
        })
    pe = pd.DataFrame(out)
    pe["data_note"] = ("simulated: synthetic labels x Model B's own assumed save rates (circular); "
                       "not measured lift")
    return pe


def uplift_curves(up: pd.DataFrame, facts: pd.DataFrame) -> pd.DataFrame:
    """Qini-style curves: rank accounts by each model's score, treat the top x% with their best eligible
    retention action, accumulate simulated incremental saves. Same action per account in every curve, so all
    curves end at the same total; the random baseline is the straight line to that total."""
    u = up.copy()
    u["support_90d"] = facts.set_index("account_id")["support_90d"].reindex(u["account_id"]).values
    rng = np.random.default_rng(SEED)
    u["rand"] = rng.random(len(u))
    orders = {
        "Model C (uplift score)": u.sort_values(["uplift_score", "account_id"], ascending=[False, True]),
        "Model B (expected value)": u.sort_values(["model_b_ev", "uplift_score"], ascending=[False, False]),
        "Model A (churn risk only)": u.sort_values("risk_rank"),
        "3+ support calls rule": u.sort_values(["support_90d", "rand"], ascending=[False, True]),
        "random": u.sort_values("rand"),
    }
    n = len(u)
    total = u["sim_incremental_save"].sum()
    fracs = np.linspace(0, 1, CURVE_POINTS)
    rows = []
    for name, df in orders.items():
        cs = np.concatenate([[0.0], df["sim_incremental_save"].cumsum().values])
        cv = np.concatenate([[0.0], df["sim_net_value_if_treated"].cumsum().values])
        for f in fracs:
            k = int(round(f * n))
            rows.append({"policy_or_model": name, "frac_targeted": round(f, 2),
                         "cum_incremental_saves": round(cs[k], 3), "random_baseline": round(f * total, 3),
                         "cum_net_value_usd": round(cv[k], 0)})
    curve = pd.DataFrame(rows)
    curve["data_note"] = "simulated"
    return curve


FOOTNOTE = ("SIMULATED, synthetic customers. Scored with tm-data's synthetic churn labels x Model B's OWN assumed "
            "save rates, costs and annoyance,\nso it is partly circular: it shows how each rule spends contacts under "
            "those assumptions, not measured lift. No real offer outcomes exist.")


def _footnote(fig) -> None:
    fig.text(0.01, 0.01, FOOTNOTE, fontsize=7, color="#444444", ha="left", va="bottom")


def charts(curve: pd.DataFrame, pe: pd.DataFrame) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed: skipping PNGs (CSVs written; tm-ui redraws from them)")
        return []
    paths = []
    fig, ax = plt.subplots(figsize=(8, 5.6))
    for name, g in curve.groupby("policy_or_model", sort=False):
        if name == "random":
            continue
        ax.plot(g["frac_targeted"] * 100, g["cum_incremental_saves"], label=name, lw=2)
    g0 = curve[curve.policy_or_model == curve.policy_or_model.iloc[0]]
    ax.plot(g0["frac_targeted"] * 100, g0["random_baseline"], "k--", label="random baseline", lw=1)
    ax.set_xlabel("% of customers contacted")
    ax.set_ylabel("cumulative incremental saves (simulated)")
    ax.set_title("Who to contact: uplift curve (SIMULATED, synthetic customers)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    _footnote(fig)
    p1 = OUT / "uplift_curve.png"
    fig.savefig(p1, dpi=140)
    plt.close(fig)
    paths.append(str(p1))

    fig, ax = plt.subplots(figsize=(10, 5.4))
    d = pe.iloc[::-1]
    colors = ["#e20074" if "Model B" in s else "#999999" for s in d["policy"]]
    ax.barh(d["policy"], d["sim_net_value_usd"] / 1000, color=colors)
    ax.axvline(0, color="k", lw=0.8)
    for y, (v, k) in enumerate(zip(d["sim_net_value_usd"], d["n_targeted"])):
        ax.text(v / 1000, y, f"  ${v/1000:,.1f}k  ({k:,} contacts)", va="center", fontsize=8)
    ax.set_xlabel("net value, $ thousands (simulated, 24-month horizon)")
    ax.set_title("Policy value: targeted EV vs blanket offers (SIMULATED)")
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    _footnote(fig)
    p2 = OUT / "policy_value.png"
    fig.savefig(p2, dpi=140)
    plt.close(fig)
    paths.append(str(p2))
    return paths


def run_once() -> dict:
    scores = OUT / "churn_scores.csv"
    m_before = _mtime(scores)
    offers = ob.main()
    conn = ob.det.connect_ro()
    facts = ob.det.build_account_facts(conn)
    facts, _ = ob.det.apply_features_csv(facts, OUT / "features.csv")
    offers = offers.reset_index(drop=True)
    p_eval, p_src = load_eval_probability(offers)
    up = build_uplift(offers, p_eval)
    up["support_90d"] = facts.set_index("account_id")["support_90d"].reindex(up["account_id"]).values
    up.to_csv(OUT / "uplift.csv", index=False)
    pe = policy_eval(offers, up, p_eval, facts)
    pe["eval_probability"] = p_src
    pe.to_csv(OUT / "policy_eval.csv", index=False)
    curve = uplift_curves(up, facts)
    curve.to_csv(OUT / "uplift_curve.csv", index=False)
    pngs = charts(curve, pe)
    return {"churn_scores_mtime_used": _fmt(m_before), "churn_scores_mtime_epoch": m_before,
            "churn_source": offers["churn_source"].iloc[0], "eval_probability": p_src, "pngs": pngs,
            "action_counts": offers["action"].value_counts().to_dict()}


def main() -> dict:
    t0 = time.time()
    info = run_once()
    now = _mtime(OUT / "churn_scores.csv")
    if now is not None and now != info["churn_scores_mtime_epoch"]:
        print(f"churn_scores.csv changed during the run ({_fmt(now)}); rebuilding on the fresh scores")
        info = run_once()
    info["finished"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " PDT"
    info["elapsed_s"] = round(time.time() - t0, 1)
    (OUT / "offers_pipeline_run.json").write_text(json.dumps(info, indent=2, default=str))
    return info


if __name__ == "__main__":
    info = main()
    pe = pd.read_csv(OUT / "policy_eval.csv")
    print(pe.drop(columns=["data_note", "eval_probability"]).to_string(index=False))
    print(json.dumps({k: v for k, v in info.items() if k != "churn_scores_mtime_epoch"}, indent=2, default=str))
    print("ALL NUMBERS SYNTHETIC / SIMULATED.")
