"""EMP (Verbraken et al. 2013, churn EMP with Beta(6,14) acceptance) + engine loss breakdown. SYNTHETIC."""
import numpy as np, pandas as pd
from scipy.stats import beta as B
from sklearn.metrics import roc_auc_score
import policy_eval as P
from config import BASE, EMP
A = P.A; y = A.y.values
def emp(y, s, CLV=EMP["CLV"], d=EMP["delta"], f=EMP["phi"], a=EMP["alpha"], b=EMP["beta"], ng=2000):
    """EMP per customer and profit-optimal contact fraction. Profit(k,g) = CLV*(g*(1-d/CLV)-f/CLV)*TP_k/N - (d+f)*FP_k/N
    (Verbraken 2013 eq. with pi0*F0 = TP/N, pi1*F1 = FP/N); integrate max_k over g ~ Beta(a,b)."""
    o = np.argsort(-s, kind="stable"); tp = np.r_[0, np.cumsum(y[o])]; fp = np.r_[0, np.cumsum(1-y[o])]; n = len(y)
    g = B.ppf((np.arange(ng)+0.5)/ng, a, b)  # quantile grid = equal-weight integration over h(gamma)
    prof = (CLV*(g[:,None]*(1-d/CLV) - f/CLV))*tp[None,:]/n - (d+f)*fp[None,:]/n
    k = prof.argmax(1); return prof.max(1).mean(), (k/n).mean()
def topcap(y,s,fr=.1):
    k=int(len(y)*fr); return y[np.argsort(-s,kind="stable")[:k]].sum()/y.sum()
V = (A.V0*BASE["SERVICE_MARGIN"]*BASE["HORIZON_MONTHS"]).values
out=[]
for n,c in [("baseline LR (incl. port-out/competitor)","p_base"),("compliant spline LR","p_spline_c"),("class-weighted LR","p_cw"),("oracle p_true (ceiling)","p_true")]:
    s=A[c].values; e,fr=emp(y,s); e2,fr2=emp(y,s,CLV=float(np.median(V)))
    out.append(dict(model=n, AUC=round(roc_auc_score(y,s),4), top10_capture=round(topcap(y,s),3),
        EMP_default_usd=round(e,3), EMP_opt_contact_frac=round(fr,4),
        EMP_ourCLV_usd=round(e2,3), EMP_ourCLV_opt_frac=round(fr2,4)))
E=pd.DataFrame(out); E.to_csv("emp_results.csv",index=False); print(E.to_string(index=False)); print("our CLV median",np.median(V))
# engine breakdown under evaluator (true probs)
rows=P.rows; evt=P.ev_rows(BASE,A.p_true.values,P.UQ_TRUE); e=rows.engine_pick.values
br=pd.DataFrame({"action":rows.action_code[e],"ev_true":evt[e],"engine_ev":rows.engine_ev[e]}).groupby("action").agg(n=("ev_true","size"),true_net=("ev_true","sum"),engine_claimed=("engine_ev","sum"),neg_ev_contacts=("ev_true",lambda x:(x<0).sum())).round(0)
br.to_csv("engine_breakdown.csv"); print(br)
