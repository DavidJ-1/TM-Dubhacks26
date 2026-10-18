"""Expected-value policy evaluator. Decisions use model scores; value is scored under the synthetic generator's TRUE
probabilities (labels.csv p_true_90d / p_upgrade_90d). Reads repo/scratch read-only; writes only to this folder.
ALL NUMBERS SYNTHETIC."""
import itertools, json, sys
import numpy as np, pandas as pd
from config import BASE, GRID, TEAMMATE, EMP
R = "/workspace/tmobile/TM-Dubhacks26/demo_data/"; S = "/workspace/tmobile/scratch_models/"
RET = ["care_credit","care_credit_fix_first","fix_first","loyalty_credit","keep_your_phone","bill_shock_price_lock",
       "check_in","perk_reminder","right_size","variant_switch"]
UPS = ["step_up","family_upgrade","device_upgrade","home_internet_bundle"]
PA = {"step_up":0.25,"device_upgrade":0.15,"family_upgrade":0.20,"home_internet_bundle":0.04}  # repo P_ACCEPT

# ---------- per-account data
lab = pd.read_csv(R+"labels.csv").set_index("account_id")
f = pd.read_csv(R+"features.csv").set_index("account_id")
off = pd.read_csv(R+"offers.csv").set_index("account_id")
oof = pd.read_csv(R+"churn_oof_pred.csv").set_index("account_id")
ids = oof.index.values; N = len(ids)
A = pd.DataFrame(index=ids)
A["p_base"] = oof.p_churn_90d
r2 = pd.read_csv(S+"round2_churn/oof_r2.csv").set_index("account_id")
A["p_spline_c"] = r2["[compliant] spline-LR tuned (core)"]
A["p_cw"] = pd.read_csv("oof_classweighted_lr.csv").set_index("account_id").p_cw
up = pd.read_csv(S+"round2_upgrade/task2_oof.csv").set_index("account_id")
A["u_score"] = up["LR generator-matched transforms only (16)"]
A["p_true"] = lab.p_true_90d; A["u_true"] = lab.p_upgrade_90d; A["y"] = lab.churn_90d; A["y_up"] = lab.upgrade_90d
A["V0"] = off.customer_value_usd / (24*0.5)    # monthly service revenue $ (repo value = rev*0.5*24)
for c in ["support_90d","port_out_inquiry","competitor_research_score","app_sessions_30d","avg_sentiment"]: A[c] = f[c]
A = A.loc[ids]; A["idx"] = np.arange(N)

# ---------- action rows (eligible candidates + engine's chosen + teammates' forced)
cand = pd.read_csv(R+"offer_candidates.csv.gz")
cand = cand[cand.account_id.isin(ids) & cand.eligible & cand.action_code.isin(RET+UPS)].copy()
cand["kind"] = np.where(cand.action_code.isin(UPS), "U", "R")
cand["pa"] = cand.action_code.map(PA).fillna(1.0)
# gain if accepted (repo upsell_gain = pa*gain*(1-p) for plan moves; device = pa*$80)
cand["gain_acc"] = np.where(cand.kind=="U", cand.upsell_gain/cand.pa, 0.0)
cand["gain_hscale"] = cand.action_code.isin(["step_up","family_upgrade","home_internet_bundle"])
cand["cost_on_accept"] = cand.action_code.isin(["device_upgrade","home_internet_bundle"])
cand["cost_acc"] = np.where(cand.cost_on_accept, cand.offer_cost/cand.pa, cand.offer_cost)
cand["sr"] = np.where(cand.kind=="U", 0.0, cand.save_rate)
cand["benefit"] = cand.customer_benefit.fillna(0)
# compliance: actions whose trigger/on-target rate comes from port-out or competitor signals
a_ = A.loc[cand.account_id]
shop = (a_.port_out_inquiry.values==1) | (a_.competitor_research_score.values>=0.6)
quiet = a_.app_sessions_30d.values <= 3
cand["noncompliant"] = ((cand.action_code=="check_in") & shop & ~quiet).values
cand["sr_c"] = np.where((cand.action_code=="loyalty_credit") & shop, 0.05, cand.sr)  # off-target rate w/o shop signal
cand["sr_c"] = np.where(cand.noncompliant, 0.0, cand.sr_c)
cand["src"] = "cand"
cols = ["account_id","action_code","kind","sr","sr_c","cost_acc","cost_on_accept","annoyance","gain_acc","gain_hscale","benefit","noncompliant","src"]
rows = cand[cols]
tm = pd.read_csv("/tmp/integ_console_out.csv").set_index("account_id").loc[ids]
t = tm[tm.c_choice=="offer"].copy()
trow = []
for aid, r in t.iterrows():
    a = A.loc[aid]
    if r.c_name.startswith("Care"):
        k="care_credit"; on = a.support_90d>=3
    else:
        k="loyalty_credit"; on = (a.port_out_inquiry==1) or (a.competitor_research_score>=0.6)
    P = TEAMMATE[k]; sr = P["sr_on"] if on else P["sr_off"]
    trow.append(dict(account_id=aid, action_code=k, kind="R", sr=sr, sr_c=sr, cost_acc=P["cost"], cost_on_accept=False,
                     annoyance=P["ann"], gain_acc=0.0, gain_hscale=False, benefit=0.0,
                     noncompliant=bool(k=="loyalty_credit" and a.port_out_inquiry==1), src="team"))
rows = pd.concat([rows, pd.DataFrame(trow)], ignore_index=True)
rows["ai"] = A.idx.loc[rows.account_id].values
rows["is_U"] = rows.kind.values=="U"
eng = off.loc[ids]; eng = eng[eng.action_code!="do_nothing"]
ekey = set(zip(eng.index, eng.action_code))
rows["engine_pick"] = [(a,c) in ekey and s=="cand" for a,c,s in zip(rows.account_id,rows.action_code,rows.src)]
assert rows.engine_pick.sum()==len(eng), (rows.engine_pick.sum(), len(eng))
rows["engine_ev"] = rows.account_id.map(off.expected_value).where(rows.engine_pick, np.nan)
rows["team_p"] = rows.account_id.map(tm.model_p)
rows.to_csv("action_rows.csv", index=False)
AI = rows.ai.values; ISU = rows.is_U.values; CAND = (rows.src=="cand").values

def rescale_up(score):  # rescale upgrade scores to the research base rate (keeps ranking)
    s = np.asarray(score, float); return np.clip(s * BASE["UPGRADE_BASE_RATE_Q"]/s.mean(), 0, 1)
UQ_DEC = rescale_up(A.u_score.values); UQ_TRUE = rescale_up(A.u_true.values)

def ev_rows(cfg, p_acc, uq_acc, compliant=False):
    """EV of each action row for account-level churn prob p_acc and upgrade prob uq_acc."""
    p = p_acc[AI]; uq = uq_acc[AI]; V = A.V0.values[AI]*cfg["SERVICE_MARGIN"]*cfg["HORIZON_MONTHS"]
    sr = (rows.sr_c.values if compliant else rows.sr.values)*cfg["SAVE_RATE_MULT"]
    take = np.minimum(1.0, cfg["UPSELL_LIFT"]*uq)
    gain = rows.gain_acc.values*np.where(rows.gain_hscale.values, cfg["HORIZON_MONTHS"]/24, 1.0)*(cfg["SERVICE_MARGIN"]/0.5 if True else 1)
    gain = np.where(rows.action_code.values=="device_upgrade", rows.gain_acc.values, gain)  # device $80 margin fixed
    cost = rows.cost_acc.values*cfg["COST_MULT"]*np.where(rows.cost_on_accept.values, take, 1.0)
    ann = rows.annoyance.values*cfg["ANNOYANCE_MULT"]
    ret = p*np.minimum(1, sr)*V
    upsell = take*gain*(1-p) - cfg["BACKFIRE_REL"]*p*V
    ev = np.where(ISU, upsell + cfg["UPSELL_SAVE_RATE"]*p*V, ret) - cost - ann + cfg["CUSTOMER_BENEFIT_WEIGHT"]*rows.benefit.values
    return ev

def best_per_account(score, mask):
    """index of best row per account under `mask` (or -1)"""
    s = np.where(mask, score, -np.inf); order = np.lexsort((-s, AI))
    first = np.r_[True, AI[order][1:] != AI[order][:-1]]; o = order[first]
    out = -np.ones(N, int); ok = np.isfinite(s[o]); out[AI[o][ok]] = o[ok]; return out

def select(best, rank_key, k, require_pos=None):
    acc = np.where(best >= 0)[0]
    if require_pos is not None: acc = acc[require_pos[best[acc]] > 0]
    acc = acc[np.argsort(-rank_key[acc], kind="stable")]
    if k is not None: acc = acc[:k]
    return best[acc]

def policies(cfg, p_dec, compliant_p, budget):
    """Return dict name -> selected row indices. budget=None -> unconstrained."""
    uq = UQ_DEC; out = {}
    ev = ev_rows(cfg, p_dec, uq); evc = ev_rows(cfg, compliant_p, uq, compliant=True)
    hi = p_dec >= np.quantile(p_dec, 1-cfg["HIGH_RISK_FRAC"])
    sup = A.support_90d.values
    # 1 current engine
    e = rows.engine_pick.values; be = best_per_account(np.where(e,1.0,0.0), e)
    out["engine (current offers.csv)"] = select(be, np.nan_to_num(rows.engine_ev.values)[np.maximum(be,0)], budget)
    # 2 teammates
    tmask = (rows.src=="team").values; bt = best_per_account(np.ones(len(rows)), tmask)
    out["teammates' playbook"] = select(bt, tm.model_p.values, budget)
    # 3/4 risk-only and value-weighted: best retention action by EV, contacted regardless of EV
    br = best_per_account(ev, CAND & ~ISU)
    kU = budget if budget is not None else int((p_dec >= 0.05).sum())
    out["risk-only (top p_churn)"] = select(br, p_dec, kU)
    out["value-weighted (p_churn x bill)"] = select(br, p_dec*A.V0.values, kU)
    # 5 EV-optimal (no guardrails), rank by EV per contact
    b5 = best_per_account(ev, CAND); out["EV-optimal"] = select(b5, ev[np.maximum(b5,0)], budget, ev)
    # 6 EV-optimal + guardrails (no upsell to top-decile risk or >=3 support)
    for thr in [cfg["SUPPORT_BLOCK"], 5]:
        blk = ISU & (hi[AI] | (sup[AI] >= thr))
        b6 = best_per_account(ev, CAND & ~blk)
        out[f"EV + guardrails (support>={thr})"] = select(b6, ev[np.maximum(b6,0)], budget, ev)
    # 7 compliant: compliant spline churn probs, no port-out/competitor-triggered actions, guardrails support>=3
    hic = compliant_p >= np.quantile(compliant_p, 1-cfg["HIGH_RISK_FRAC"])
    blk = ISU & (hic[AI] | (sup[AI] >= cfg["SUPPORT_BLOCK"]))
    b7 = best_per_account(evc, CAND & ~blk & ~rows.noncompliant.values)
    out["EV + guardrails, compliant"] = select(b7, evc[np.maximum(b7,0)], budget, evc)
    return out

def score(cfg, sel, compliant=False):
    """true expected net $ of selected rows, under generator probabilities"""
    evt = ev_rows(cfg, A.p_true.values, UQ_TRUE, compliant=compliant)
    return evt[sel].sum()

def summarize(cfg, p_dec, budget, tag):
    pol = policies(cfg, p_dec, A.p_spline_c.values, budget); res = []
    for n, s in pol.items():
        comp = "compliant" in n
        tv = score(cfg, s, comp); dv = ev_rows(cfg, A.p_spline_c.values if comp else p_dec, UQ_DEC, comp)[s].sum()
        nu = int(ISU[s].sum()); cost = (rows.cost_acc.values[s]*cfg["COST_MULT"]).sum()
        res.append(dict(setting=tag, policy=n, contacts=len(s), upsell_contacts=nu, net_true=round(tv,0),
                        per_contact=round(tv/max(len(s),1),2), net_model_believed=round(dv,0),
                        nominal_offer_cost=round(cost,0),
                        uses_port_out_or_competitor=int(rows.noncompliant.values[s].sum()) if not comp else 0))
    return pd.DataFrame(res)

if __name__ == "__main__":
    K = int(BASE["BUDGET_FRAC"]*N)
    main = pd.concat([summarize(BASE, A.p_base.values, K, f"budget {K}"), summarize(BASE, A.p_base.values, None, "unconstrained")])
    side = summarize({**BASE, "CUSTOMER_BENEFIT_WEIGHT":0.5}, A.p_base.values, None, "unconstrained, customer benefit x0.5 (repo view)")
    main = pd.concat([main, side]); main.to_csv("policy_results.csv", index=False)
    print(main.to_string(index=False))
    # ---- sensitivity grid
    keys = list(GRID); wins = []
    for vals in itertools.product(*[GRID[k] for k in keys]):
        cfg = {**BASE, **dict(zip(keys, vals))}
        for b, tag in [(K, "budget"), (None, "unconstrained")]:
            pol = policies(cfg, A.p_base.values, A.p_spline_c.values, b)
            sc = {n: score(cfg, s, "compliant" in n) for n, s in pol.items()}
            wins.append(dict(zip(keys, vals), budget=tag, **sc))
    W = pd.DataFrame(wins); W.to_csv("grid_results.csv", index=False)
    pn = [c for c in W.columns if c not in keys+["budget"]]
    rob = []
    for tag, g in W.groupby("budget"):
        M = g[pn].values; win = M.argmax(1)
        ex = [i for i,n in enumerate(pn) if not n.startswith("EV")]
        for i, n in enumerate(pn):
            rob.append(dict(budget=tag, policy=n, win_share=round((win==i).mean(),3),
                            beats_engine_share=round((M[:,i] > M[:,pn.index("engine (current offers.csv)")]).mean(),3),
                            median_net=round(np.median(M[:,i]),0), p10_net=round(np.quantile(M[:,i],.1),0),
                            p90_net=round(np.quantile(M[:,i],.9),0)))
    rob = pd.DataFrame(rob); rob.to_csv("grid_robustness.csv", index=False); print(rob.to_string(index=False))
    # ---- calibration: same EV policy, decisions from calibrated vs miscalibrated probs
    cal = []
    from sklearn.linear_model import LogisticRegression
    fold = oof.fold.loc[ids].values; lg = lambda p: np.log(np.clip(p,1e-6,1-1e-6)/(1-np.clip(p,1e-6,1-1e-6)))
    p_cw_platt = np.zeros(N)
    for k in np.unique(fold):  # cross-fitted Platt recalibration of the class-weighted scores
        tr, te = fold!=k, fold==k
        m = LogisticRegression(C=1e6).fit(lg(A.p_cw.values[tr])[:,None], A.y.values[tr])
        p_cw_platt[te] = m.predict_proba(lg(A.p_cw.values[te])[:,None])[:,1]
    A["p_cw_platt"] = p_cw_platt
    variants = {"oracle (generator p_true)": A.p_true.values, "baseline LR (calibrated)": A.p_base.values,
                "class-weighted LR (miscalibrated)": A.p_cw.values, "class-weighted LR + Platt recal": p_cw_platt,
                "baseline LR x2 (overconfident)": np.clip(A.p_base.values*2,0,1), "baseline LR x0.5 (underconfident)": A.p_base.values*0.5}
    pname = "EV + guardrails (support>=3)"
    for b, tag in [(K, f"budget {K}"), (None, "unconstrained")]:
        for n, p in variants.items():
            s = policies(BASE, p, A.p_spline_c.values, b)[pname]
            cal.append(dict(setting=tag, churn_probs=n, mean_p=round(p.mean(),4), contacts=len(s),
                            net_true=round(score(BASE, s),0), model_believed=round(ev_rows(BASE,p,UQ_DEC)[s].sum(),0)))
    cal = pd.DataFrame(cal); cal.to_csv("calibration_results.csv", index=False); print(cal.to_string(index=False))
    # grid for calibration: share of cells where calibrated beats class-weighted
    cg = []
    for vals in itertools.product(*[GRID[k] for k in keys]):
        cfg = {**BASE, **dict(zip(keys, vals))}
        for b in [K, None]:
            a_ = score(cfg, policies(cfg, A.p_base.values, A.p_spline_c.values, b)[pname])
            c_ = score(cfg, policies(cfg, A.p_cw.values, A.p_spline_c.values, b)[pname])
            cg.append(dict(budget="budget" if b else "unconstrained", calibrated=a_, classweighted=c_))
    cg = pd.DataFrame(cg); cgs = cg.groupby("budget").apply(lambda g: pd.Series(dict(
        cal_wins_share=(g.calibrated>g.classweighted).mean(), median_loss=np.median(g.calibrated-g.classweighted),
        median_loss_pct=np.median((g.calibrated-g.classweighted)/g.calibrated.abs())))).round(3)
    cgs.to_csv("calibration_grid.csv"); print(cgs)
    A.to_csv("accounts_used.csv")
