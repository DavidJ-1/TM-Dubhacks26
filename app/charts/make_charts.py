"""Slide-ready charts for the demo (tm-ui lane). ALL DATA SYNTHETIC.

One command (from repo root):  python app/charts/make_charts.py
Reads harness/out/*.csv (falls back to app/mock/*.csv through app/data.py) and writes 1600x900 PNGs
to app/charts/. Charts whose inputs don't exist yet are written as clearly-marked placeholders.

Inputs
  01 quadrant / 01b top-20 : churn_scores.csv (p_churn_90d, risk_rank, risk_reason_1) + offers.csv (action[_code])
                             + features.csv (last_bill_cents)
  02 cumulative gain       : churn_scores.csv + labels.csv (churn_90d, p_true_90d = oracle) + features.csv (support_90d)
  03 calibration           : same as 02. If a holdout file exists (harness/out/*holdout*.csv or *oof*.csv with
                             account_id, p_churn_90d) it is used instead of the all-accounts scores.
  04 Model C uplift/Qini   : harness/model_c_artifacts/uplift_curve.csv (+ uplift_auuc.csv), IPW cum_incremental_saves
  05 Model C policy value  : harness/model_c_artifacts/policy_eval.csv, doubly-robust *_dr columns
                             Both are final by default; TM_MODELC_PLACEHOLDER=1 forces placeholders.
  06 learning curve        : harness/bench/*.csv or /workspace/tmobile/bench-scratch/*learning*.csv
                             expected columns: model, n_train, metric, value
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
APP = HERE.parent
REPO = APP.parent
sys.path.insert(0, str(APP))
from data import load_all, out_dirs  # noqa: E402
from messages import action_label, normalize_action  # noqa: E402

MAGENTA, DARK, GREY, LIGHT = "#E20074", "#1F1F1F", "#8A8A8A", "#D9D9D9"
ACTION_COLORS = {
    "do_nothing": "#B5B5B5", "fix_first_callback": "#4B4B4B", "care_credit_25": MAGENTA,
    "loyalty_credit": "#F27BB5", "keep_phone_credit": "#7A0041", "right_size_plan": "#1F77B4",
    "step_up_plan": "#FF9F1C", "device_upgrade": "#2CA58D", "care_credit_fix_first": "#A0005A",
}
FOOT = "All data synthetic: judge sandbox (fictional households) + simulated labels/scores. Not real T-Mobile customers."
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 15, "axes.titleweight": "bold",
    "axes.labelsize": 12, "xtick.labelsize": 10.5, "ytick.labelsize": 10.5, "legend.fontsize": 10.5,
    "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": GREY, "axes.labelcolor": DARK,
    "xtick.color": DARK, "ytick.color": DARK, "axes.titlelocation": "left", "axes.titlepad": 12,
    "figure.facecolor": "white", "savefig.facecolor": "white",
})
SIZE, DPI = (8, 4.5), 200  # 1600 x 900 px


def fig(sub=1, **kw):
    f, ax = plt.subplots(1, sub, figsize=SIZE, dpi=DPI, **kw)
    return f, ax


def save(f, name, note=""):
    import textwrap
    lines = [FOOT] + (textwrap.wrap(note, 140) if note else [])
    f.text(0.01, 0.012, "\n".join(lines), fontsize=7.5, color=GREY, ha="left", va="bottom", linespacing=1.4)
    f.subplots_adjust(bottom=max(0.19, 0.14 + 0.032 * len(lines)))
    p = HERE / name
    f.savefig(p, dpi=DPI)  # fixed canvas: exactly 1600x900
    plt.close(f)
    print("wrote", p.relative_to(REPO))
    return p


def placeholder(name, title, waiting, expects):
    f, ax = fig()
    ax.axis("off")
    ax.text(0.0, 0.92, title, fontsize=17, fontweight="bold", color=DARK, transform=ax.transAxes)
    ax.text(0.5, 0.55, waiting, fontsize=20, color=MAGENTA, ha="center", fontweight="bold", transform=ax.transAxes)
    ax.text(0.5, 0.32, expects, fontsize=10, color=GREY, ha="center", va="top", transform=ax.transAxes, wrap=True)
    save(f, name, "PLACEHOLDER")
    return {"placeholder": True, "expects": expects, "waiting": waiting}


def esc(t: str) -> str:
    """Stop matplotlib mathtext from eating dollar signs."""
    return str(t).replace("$", r"\$")


def tickpct(x, _=None):
    return f"{x:.0%}" if x >= 0.01 or x == 0 else f"{x:.1%}"


def pct(x, _=None):
    return f"{x:.0%}" if x >= 0.1 or x == 0 else (f"{x:.1%}" if x >= 0.01 else f"{x:.2%}")


MODEL_C_DIRS = [REPO / "harness" / "model_c_artifacts"]  # committed final Model C CSVs (preferred)


def find_csv(patterns: list[str], prefer: list[Path] | None = None) -> Path | None:
    dirs = list(prefer or [])
    for d in out_dirs():
        dirs += [d, d / "charts"]
    for d in dirs:
        for pat in patterns:
            hits = sorted(glob.glob(str(d / pat)), key=lambda p: Path(p).stat().st_mtime, reverse=True)
            if hits:
                return Path(hits[0])
    return None


# ------------------------------------------------------------------ data
def base_frame(data) -> pd.DataFrame:
    c = data["churn_scores"].df.copy()
    o = data["offers"].df
    f = data["features"].df
    lab = data["labels"].df
    keep_o = [x for x in ["account_id", "action", "action_code", "expected_value", "customer_value_usd"] if x in o]
    df = c.merge(o[keep_o], on="account_id", how="left")
    keep_f = [x for x in ["account_id", "last_bill_cents", "support_90d", "segment"] if x in f]
    df = df.merge(f[keep_f], on="account_id", how="left")
    keep_l = [x for x in ["account_id", "churn_90d", "p_true_90d"] if x in lab]
    df = df.merge(lab[keep_l], on="account_id", how="left")
    src = df["action_code"].fillna(df["action"]) if "action_code" in df else df.get("action", "do_nothing")
    df["action_key"] = pd.Series(src).map(normalize_action)
    df["is_persona"] = df.account_id.str.startswith("ACC-PERSONA")
    return df


# ------------------------------------------------------------------ 01 quadrant
QUAD_LABEL = {"care_credit_fix_first": "$25 credit + fix-first", "care_credit_25": "$25 care credit"}


def chart_quadrant(df):
    d = df[~df.is_persona].dropna(subset=["p_churn_90d", "last_bill_cents"]).copy()
    d["bill"] = d.last_bill_cents / 100
    xcut = d.p_churn_90d.quantile(0.90)  # top 10% risk
    ycut = d.bill.median()
    f, ax = fig()
    order = d.action_key.value_counts().index.tolist()
    if "do_nothing" in order:  # draw grey first, offers on top
        order.remove("do_nothing")
        order = ["do_nothing"] + order[::-1]
    for a in order:
        s = d[d.action_key == a]
        ax.scatter(s.p_churn_90d, s.bill, s=9 if a == "do_nothing" else 16, alpha=0.45 if a == "do_nothing" else 0.85,
                   color=ACTION_COLORS.get(a, GREY), label=esc(f"{QUAD_LABEL.get(a, action_label(a))} ({len(s):,})"), linewidths=0, zorder=2 if a == "do_nothing" else 3)
    ax.set_xscale("log")
    ax.set_xlim(max(d.p_churn_90d.min() * 0.8, 1e-4), 1)
    ax.set_ylim(0, d.bill.quantile(0.995) * 1.05)
    ax.axvline(xcut, color=DARK, lw=1, ls="--", zorder=1)
    ax.axhline(ycut, color=DARK, lw=1, ls="--", zorder=1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(tickpct))
    ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("${x:,.0f}"))
    ax.set_xlabel("Predicted 90-day churn risk (log scale)")
    ax.set_ylabel("Monthly bill")
    ymax = ax.get_ylim()[1]
    kw = dict(fontsize=9.5, fontweight="bold", va="top", zorder=6,
              bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85))
    ax.text(xcut * 1.08, ymax * 0.98, "SAVE-THEM ZONE\nhigh risk · high value", color=MAGENTA, **kw)
    ax.text(xcut * 1.08, ycut * 0.96, "FIX CHEAPLY\nhigh risk · lower value", color=DARK, **kw)
    ax.text(ax.get_xlim()[0] * 1.15, ymax * 0.98, "GROW / UPSELL WHEN TIMELY\nlow risk · high value", color=DARK, **kw)
    ax.text(ax.get_xlim()[0] * 1.15, ycut * 0.96, "DO-NOTHING ZONE\nlow risk · lower value", color=GREY, **kw)
    save_zone = d[(d.p_churn_90d >= xcut) & (d.bill >= ycut)]
    ax.set_title(f"Who to call: {len(save_zone):,} save-them accounts out of {len(d):,}")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, markerscale=1.6, title="Chosen action",
              fontsize=9, title_fontsize=10)
    f.subplots_adjust(right=0.72, left=0.09, top=0.89)
    stats = dict(n=len(d), xcut=xcut, ycut=ycut, save_zone=len(save_zone),
                 mix=d.action_key.value_counts().to_dict(),
                 save_zone_offer_share=float((save_zone.action_key != "do_nothing").mean()) if len(save_zone) else 0)
    save(f, "01_risk_value_quadrant.png", esc(f"Cut lines: top-10% risk ({pct(xcut)}), median bill (${ycut:,.0f})."))
    return stats


def top20(df) -> pd.DataFrame:
    d = df.sort_values("risk_rank").head(20)
    return pd.DataFrame({
        "Rank": d.risk_rank.astype(int), "Account": d.account_id, "Risk": d.p_churn_90d.map(lambda v: pct(v)),
        "Bill": (d.last_bill_cents / 100).map(lambda v: f"${v:,.0f}" if pd.notna(v) else ""),
        "Top reason": d.risk_reason_1.fillna(""), "Action": d.action_key.map(action_label),
    })


def chart_top20(df):
    t = top20(df)
    f, ax = fig()
    ax.axis("off")
    ax.set_title("Top 20 at-risk accounts this week")
    t2 = t.copy()
    t2["Top reason"] = t2["Top reason"].str.slice(0, 42)
    t2["Action"] = t2["Action"].str.replace("callback", "", regex=False).str.strip()
    tb = ax.table(cellText=t2.values, colLabels=t2.columns, loc="upper left", cellLoc="left", colLoc="left",
                  colWidths=[0.055, 0.12, 0.06, 0.06, 0.39, 0.315], bbox=[0, 0, 1, 1])
    tb.auto_set_font_size(False)
    tb.set_fontsize(8.2)
    for (r, c), cell in tb.get_celld().items():
        cell.set_edgecolor(LIGHT)
        cell.set_linewidth(0.5)
        if r == 0:
            cell.set_facecolor(MAGENTA)
            cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold")
        elif r % 2 == 0:
            cell.set_facecolor("#FBEAF3")
        if r > 0 and c == 5 and t2.iloc[r - 1]["Action"] == action_label("do_nothing"):
            cell.get_text().set_color(GREY)
    f.subplots_adjust(top=0.88, left=0.03, right=0.97, bottom=0.12)
    save(f, "01b_top20_at_risk.png")
    return t


# ------------------------------------------------------------------ 02 gain
def gain_curve(y, score, rng=None):
    order = np.argsort(-score, kind="stable") if rng is None else np.lexsort((rng.random(len(score)), -score))
    yy = np.asarray(y)[order]
    x = np.arange(1, len(yy) + 1) / len(yy)
    return np.r_[0, x], np.r_[0, np.cumsum(yy) / yy.sum()]


def chart_gain(df):
    d = df[~df.is_persona].dropna(subset=["churn_90d", "p_churn_90d"])
    if not len(d) or d.churn_90d.sum() == 0:
        return placeholder("02_cumulative_gain.png", "Cumulative gain", "Waiting on labels.csv", "needs churn_90d")
    y = d.churn_90d.values.astype(int)
    rng = np.random.default_rng(42)
    f, ax = fig()
    stats = {"n": len(d), "churners": int(y.sum())}

    def at(xs, ys, q):
        return float(np.interp(q, xs, ys))

    if "p_true_90d" in d:
        xs, ys = gain_curve(y, d.p_true_90d.values)
        ax.plot(xs, ys, color=GREY, lw=1.5, ls=":", label=f"Oracle (true synthetic p): top 10% → {at(xs, ys, .1):.0%}")
        stats["oracle_top10"] = at(xs, ys, .1)
    xs, ys = gain_curve(y, d.p_churn_90d.values)
    ax.plot(xs, ys, color=MAGENTA, lw=3, label=f"Model A: top 10% → {at(xs, ys, .1):.0%} of churners")
    stats["model_top10"], stats["model_top20"] = at(xs, ys, .1), at(xs, ys, .2)
    if "support_90d" in d:
        xr, yr = gain_curve(y, d.support_90d.values.astype(float), rng)
        ax.plot(xr, yr, color=DARK, lw=2, label=f"Support-contacts ranking: top 10% → {at(xr, yr, .1):.0%}")
        flag = d.support_90d >= 3
        px, py = flag.mean(), y[flag.values].sum() / y.sum()
        ax.scatter([px], [py], s=70, color=DARK, zorder=5)
        ax.annotate(f"'3+ support contacts' rule\ncontacts {px:.0%}, catches {py:.0%}", (px, py), xytext=(px + 0.08, py - 0.17),
                    fontsize=10, arrowprops=dict(arrowstyle="-", color=DARK, lw=0.8))
        stats.update(rule_share=float(px), rule_caught=float(py), rule_rank_top10=at(xr, yr, .1),
                     model_at_rule_share=at(xs, ys, px))
    ax.plot([0, 1], [0, 1], color=LIGHT, lw=1.5, ls="--", label="Random outreach")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Share of accounts contacted (ranked by score)")
    ax.set_ylabel("Share of churners caught")
    ax.set_title(f"Call 10%, catch {stats['model_top10']:.0%} of churners")
    ax.legend(loc="lower right", frameon=False)
    f.subplots_adjust(left=0.09, top=0.88)
    save(f, "02_cumulative_gain.png", f"{len(d):,} accounts, {int(y.sum())} simulated churners. {SCORE_NOTE}")
    return stats


# ------------------------------------------------------------------ 03 calibration
def chart_calibration(df):
    d = df[~df.is_persona].dropna(subset=["churn_90d", "p_churn_90d"]).copy()
    if not len(d):
        return placeholder("03_calibration.png", "Calibration", "Waiting on labels.csv", "needs churn_90d")
    d["bucket"] = pd.qcut(d.p_churn_90d.rank(method="first"), 10, labels=False)
    g = d.groupby("bucket").agg(pred=("p_churn_90d", "mean"), obs=("churn_90d", "mean"), n=("churn_90d", "size")).reset_index()
    ece = float((g.n * (g.pred - g.obs).abs()).sum() / g.n.sum())
    f, ax = fig()
    x = np.arange(10)
    w = 0.38
    ax.bar(x - w / 2, g.pred, w, color=MAGENTA, label="Predicted (mean)")
    ax.bar(x + w / 2, g.obs, w, color=DARK, label="Actual (simulated)")
    ax.set_xticks(x, [f"{i + 1}" for i in x])
    ax.set_xlabel("Risk bucket (deciles of predicted risk, 1 = lowest)")
    ax.set_ylabel("90-day churn rate")
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(tickpct))
    top = g.iloc[-1]
    ax.annotate(f"top decile: {pct(top.pred)} predicted\nvs {pct(top.obs)} actual", (9, max(top.pred, top.obs)),
                xytext=(6.0, max(top.pred, top.obs) * 0.7), fontsize=10.5, arrowprops=dict(arrowstyle="-", color=DARK, lw=0.8))
    ax.set_title(f"Calibration: predicted vs actual  (ECE = {ece * 100:.2f} pts)")
    ax.legend(loc="upper left", frameon=False)
    f.subplots_adjust(left=0.1, top=0.88)
    save(f, "03_calibration.png", f"10 equal-count buckets of {len(g) and int(g.n.iloc[0])} accounts. {SCORE_NOTE}")
    return dict(ece=ece, buckets=g.round(4).to_dict("records"))


# ------------------------------------------------------------------ 04/05 Model C
# Model C is final (tm-offers 6705fb9). Charts are drawn from harness/model_c_artifacts/ whenever the CSVs exist.
# Set TM_MODELC_PLACEHOLDER=1 to force placeholders (e.g. while tm-offers reruns). TM_MODELC_FINAL is no longer needed.
import os  # noqa: E402
MODEL_C_FORCE_PLACEHOLDER = os.environ.get("TM_MODELC_PLACEHOLDER") == "1"
MODELB_PINK, MODELC_COL, MODELA_COL, RULE_COL = MAGENTA, "#1F5FAD", "#9A9A9A", "#3A3A3A"
CIRC_NOTE = ("PROVISIONAL: test split too small to rank policies reliably; figures may change. Simulated randomized trial on the test split: effects are grounded in our own save-rate assumptions "
             "(partly circular), not measured lift.")
POLICY_ORDER = ["Model B EV chooser", "Model C T-learner", "Offer to everyone", "3+ calls rule", "Random", "Do nothing",
                "Oracle (reference)"]


def _col(df, *names):
    low = {c.lower(): c for c in df.columns}
    for n in names:
        if n in low:
            return low[n]
    for n in names:
        for lc, c in low.items():
            if n in lc:
                return c
    return None


def short_policy(v) -> str:
    s = str(v).lower()
    for keys, name in [(["oracle"], "Oracle (reference)"), (["model b", "ev chooser", "expected value"], "Model B EV chooser"),
                       (["model c", "uplift policy", "t-learner"], "Model C T-learner"), (["model a", "churn risk"], "Model A risk ranking"),
                       (["every", "blanket"], "Offer to everyone"), (["3+", "rule"], "3+ calls rule"), (["random"], "Random"),
                       (["nothing", "no outreach"], "Do nothing")]:
        if any(k in s for k in keys):
            return name
    return str(v)


def _money(v, plus=True):
    if abs(v) < 500:
        return "~$0"
    sgn = "-" if v < 0 else ("+" if plus else "")
    return f"{sgn}${abs(v) / 1000:,.1f}k"


def chart_qini():
    title = "Uplift (Qini) curves"
    p = find_csv(["*uplift*curve*.csv", "*uplift_curve*.csv", "*qini*.csv"], prefer=MODEL_C_DIRS)
    expects = ("Expected: harness/model_c_artifacts/uplift_curve.csv with policy_or_model, frac_targeted, "
               "cum_incremental_saves")
    if p is not None and MODEL_C_FORCE_PLACEHOLDER:
        return placeholder("04_modelC_qini.png", title, "Placeholder forced", f"TM_MODELC_PLACEHOLDER=1 (input: {p.name}).")
    if p is None:
        return placeholder("04_modelC_qini.png", title, "Waiting on Model C", expects)
    q = pd.read_csv(p)
    xc = _col(q, "frac_targeted", "share_targeted", "fraction_targeted", "share", "frac", "n_targeted", "targeted")
    yc = _col(q, "cum_incremental_saves", "incremental_saves", "qini", "uplift")
    gc = _col(q, "policy_or_model", "model", "policy", "curve", "series")
    if xc is None or yc is None or gc is None:
        return placeholder("04_modelC_qini.png", title, "Model C CSV found, columns not recognized", f"{p.name}: {list(q.columns)}")
    auuc = {}
    ap = p.parent / "uplift_auuc.csv"
    if ap.exists():
        a = pd.read_csv(ap)
        ac, av = _col(a, "policy_or_model", "model", "policy"), _col(a, "qini_area_ipw", "qini_area", "auuc")
        if ac and av:
            auuc = {short_policy(k): float(v) for k, v in zip(a[ac], a[av])}
    style = {  # name: (color, lw, ls, zorder)
        "Model B EV chooser": (MODELB_PINK, 3.0, "-", 6), "Model C T-learner": (MODELC_COL, 2.6, "-", 5),
        "Model A risk ranking": (MODELA_COL, 1.8, "-", 3), "3+ calls rule": (RULE_COL, 1.8, "-", 4),
        "Oracle (reference)": (DARK, 1.6, ":", 2), "Random": ("#BDBDBD", 1.6, "--", 1),
    }
    order = ["Model B EV chooser", "Model C T-learner", "Model A risk ranking", "3+ calls rule", "Oracle (reference)", "Random"]
    q["series_name"] = q[gc].map(short_policy)
    f, ax = fig()
    curves = {}
    for name in order + sorted(set(q.series_name) - set(order)):
        s = q[q.series_name == name].sort_values(xc)
        if not len(s):
            continue
        xs = s[xc] / (s[xc].max() if s[xc].max() > 1 else 1)
        col, lw, ls, z = style.get(name, (GREY, 1.5, "-", 2))
        lab = name.replace("3+ calls rule", "3+ support calls rule").replace("Model C T-learner", "Model C uplift (T-learner)")
        if name in auuc:
            lab += f"  (Qini area {auuc[name]:.1f})"
        ax.plot(xs, s[yc], color=col, lw=lw, ls=ls, zorder=z, label=lab)
        curves[name] = dict(at10=float(np.interp(0.1, xs, s[yc])), at20=float(np.interp(0.2, xs, s[yc])), max=float(s[yc].max()))
    ax.axhline(0, color=GREY, lw=0.6, alpha=0.6)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Share of test accounts targeted (each policy's own ranking)")
    ax.set_ylabel("Cumulative incremental saves\n(IPW estimate, simulated trial)")
    ax.set_title("Who is persuadable? Incremental saves by share targeted (provisional)")
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    f.subplots_adjust(left=0.11, right=0.97, top=0.88)
    save(f, "04_modelC_qini.png", esc(f"{CIRC_NOTE} Qini area = IPW, from uplift_auuc.csv. Source: {p.parent.name}/{p.name} (tm-offers)."))
    return {"file": str(p), "y": yc, "auuc_ipw": auuc, "curves": curves}


def chart_policy():
    title = "Policy value"
    p = find_csv(["policy_eval.csv", "*policy*value*.csv", "*policy_eval*.csv", "*policies*.csv"], prefer=MODEL_C_DIRS)
    expects = "Expected: harness/model_c_artifacts/policy_eval.csv with policy + *_dr_usd columns"
    if p is not None and MODEL_C_FORCE_PLACEHOLDER:
        return placeholder("05_modelC_policy_value.png", title, "Placeholder forced", f"TM_MODELC_PLACEHOLDER=1 (input: {p.name}).")
    if p is None:
        return placeholder("05_modelC_policy_value.png", title, "Waiting on Model C", expects)
    t = pd.read_csv(p)
    need = ["policy", "net_value_no_upsell_dr_usd", "net_value_with_upsell_dr_usd", "churners_saved_dr", "cost_per_save_dr_usd"]
    if not set(need) <= set(t.columns):
        return placeholder("05_modelC_policy_value.png", title, "Model C CSV found, DR columns missing", f"{p.name}: {list(t.columns)}")
    t = t.assign(name=t.policy.map(short_policy))
    t["_o"] = t.name.map(lambda n: POLICY_ORDER.index(n) if n in POLICY_ORDER else 50)
    t = t.sort_values("_o").reset_index(drop=True)
    main_c, up_c = "net_value_no_upsell_dr_usd", "net_value_with_upsell_dr_usd"
    f, ax = fig()
    y = np.arange(len(t))
    h = 0.38
    rows = []
    for i, r in t.iterrows():
        n = r["name"]
        if n == "Model B EV chooser":
            col, hatch, ec = MODELB_PINK, None, "none"
        elif n == "Model C T-learner":
            col, hatch, ec = MODELC_COL, None, "none"
        elif n.startswith("Oracle"):
            col, hatch, ec = "#EDEDED", "////", "#9A9A9A"
        else:
            col, hatch, ec = "#7A7A7A", None, "none"
        ax.barh(i - h / 2, r[main_c], h, color=col, hatch=hatch, edgecolor=ec, lw=0.6, zorder=3)
        ax.barh(i + h / 2, r[up_c], h, color=col, alpha=0.35 if not n.startswith("Oracle") else 1.0, hatch=hatch,
                edgecolor=ec, lw=0.6, zorder=3)
        rows.append(dict(policy=r.policy, label=n, net_value_no_upsell_dr_usd=r[main_c], net_value_with_upsell_dr_usd=r[up_c],
                         churners_saved_dr=r.churners_saved_dr, cost_per_save_dr_usd=r.cost_per_save_dr_usd,
                         n_contacted=r.get("n_contacted")))
    lo = min(0, t[[main_c, up_c]].min().min())
    hi = max(0, t[[main_c, up_c]].max().max())
    span = hi - lo
    xtxt = hi + span * 0.04
    for i, r in t.iterrows():
        if r["name"] == "Do nothing":
            lab = "$0 (baseline: no offers)"
        else:
            cps = f"${r.cost_per_save_dr_usd:,.0f}/save" if pd.notna(r.cost_per_save_dr_usd) else "n/a"
            lab = (f"{_money(r[main_c])}  |  {_money(r[up_c])} w/ upsell\n"
                   f"{r.churners_saved_dr:.1f} saves · {cps}")
        ax.text(xtxt, i, esc(lab), va="center", ha="left", fontsize=8.6, color=DARK, linespacing=1.25,
                fontweight="bold" if r["name"] == "Model B EV chooser" else "normal")
    ax.set_yticks(y, t.name)
    for tl in ax.get_yticklabels():
        if tl.get_text() == "Model B EV chooser":
            tl.set_fontweight("bold")
            tl.set_color(MODELB_PINK)
    ax.invert_yaxis()
    ax.axvline(0, color=GREY, lw=0.8, zorder=2)
    ax.grid(axis="x", color=LIGHT, lw=0.6, alpha=0.7, zorder=0)
    ax.set_xlim(lo - span * 0.04, hi + span * 0.62)
    ax.set_xticks([v for v in ax.get_xticks() if lo - span * 0.04 <= v <= hi * 1.001])
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: _money(v, plus=False) if v else "$0"))
    ax.set_xlabel("Net value, 24-month margin minus offer cost (doubly-robust estimate)")
    ax.set_title("Targeted offers vs blanket policies (provisional)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#7A7A7A", label="Retention only"), Patch(color="#7A7A7A", alpha=0.35, label="With upsell")],
              frameon=False, loc="lower left", fontsize=8, handlelength=1.2, borderaxespad=0.2)
    f.subplots_adjust(left=0.25, right=0.98, top=0.9)
    n_test = int(t.n_test_accounts.iloc[0]) if "n_test_accounts" in t else None
    reps = int(t.trial_replicates.iloc[0]) if "trial_replicates" in t else None
    save(f, "05_modelC_policy_value.png",
         esc(f"{CIRC_NOTE} DR estimates, {n_test:,} test accounts x {reps} re-randomized cohorts. "
             f"Oracle uses the hidden simulated effects (reference only). Source: {p.parent.name}/{p.name} (tm-offers)."))
    return {"file": str(p), "estimator": "doubly_robust", "table": rows}


# ------------------------------------------------------------------ 06 learning curve
LC_LABELS = {"logreg_core22": "Logistic regression, 22 core features (Model A)",
             "logreg_unweighted": "Logistic regression, all 58 features", "hgb_sigmoid": "Gradient-boosted trees"}
LC_COLORS = {"logreg_core22": MAGENTA, "logreg_unweighted": "#4A4A4A", "hgb_sigmoid": "#A0A0A0"}
LC_SOURCE = {"real_5k": "trained on real 5k", "synthetic_50k": "trained on synthetic 50k"}


def _plot_learning(t: pd.DataFrame, src: str):
    from matplotlib.lines import Line2D
    met = next((m for m in ["auc", "roc_auc"] if m in set(t.metric)), t.metric.iloc[0])
    s = t[t.metric == met].copy()
    if "train_source" not in s:
        s["train_source"] = "real_5k"
    models = [m for m in LC_LABELS if m in set(s.model)] or sorted(s.model.unique())[:3]
    s = s[s.model.isin(models)]
    f, ax = fig()
    out = {}
    for m in models[::-1]:  # lead model drawn last (on top)
        col = LC_COLORS.get(m, GREY)
        lead = m == "logreg_core22"
        for srcname, g in s[s.model == m].groupby("train_source"):
            g = g.groupby("n_train").agg(value=("value", "mean"), sd=("sd", "mean") if "sd" in g else ("value", "std")).reset_index()
            ls = "--" if "synth" in srcname else "-"
            ax.plot(g.n_train, g.value, color=col, lw=2.8 if lead else 1.6, ls=ls, marker="o", ms=4 if lead else 3,
                    zorder=6 if lead else 4)
            if lead and g.sd.notna().any():
                ax.fill_between(g.n_train, g.value - g.sd.fillna(0), g.value + g.sd.fillna(0), color=col,
                                alpha=0.14, lw=0, zorder=2)
            out[f"{m}|{srcname}"] = {"n_min": int(g.n_train.iloc[0]), "auc_min_n": round(float(g.value.iloc[0]), 4),
                                     "sd_min_n": round(float(g.sd.iloc[0]), 4),
                                     "n_max": int(g.n_train.iloc[-1]), "auc_max_n": round(float(g.value.iloc[-1]), 4),
                                     "sd_max_n": round(float(g.sd.iloc[-1]), 4)}
    ceiling = None
    cp = Path(src).parent / "ceilings.csv" if Path(src).is_absolute() else REPO / "harness" / "bench" / "out" / "ceilings.csv"
    if cp.exists():
        c = pd.read_csv(cp)
        c = c[c.target == "churn_90d"]
        if len(c):
            ceiling = float(c.oracle_auc.iloc[0])
            ax.axhline(ceiling, color=DARK, lw=1, ls=":", zorder=3)
            ax.text(s.n_train.min(), ceiling + 0.004, f"Ceiling: oracle AUC {ceiling:.3f} (true simulated probabilities)",
                    fontsize=9, color=DARK, va="bottom", ha="left")
    ax.set_xscale("log")
    ticks = [250, 500, 1000, 2500, 5000, 10000, 25000, 50000]
    ax.set_xticks([x for x in ticks if s.n_train.min() <= x <= s.n_train.max()])
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1000:g}k" if v >= 1000 else f"{v:g}"))
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ld = s[s.model == "logreg_core22"]
    lo = max(0.55, min(s.value.min(), (ld.value - ld.get("sd", 0)).min() if len(ld) else 1) - 0.04)
    ax.set_ylim(lo, max(ceiling or 0, s.value.max()) + 0.03)
    ax.grid(axis="y", color=LIGHT, lw=0.6, alpha=0.7)
    ax.set_xlabel("Training accounts (log scale)")
    ax.set_ylabel("ROC AUC, 90-day churn")
    ax.set_title("How much data do the models need?")
    h1 = [Line2D([], [], color=LC_COLORS.get(m, GREY), lw=2.8 if m == "logreg_core22" else 1.6, label=LC_LABELS.get(m, m))
          for m in models]
    h2 = [Line2D([], [], color=DARK, lw=1.6, ls="-", label="Trained on 5k sandbox accounts"),
          Line2D([], [], color=DARK, lw=1.6, ls="--", label="Trained on synthetic 50k (tested on real 5k)")]
    leg = ax.legend(handles=h1, frameon=False, loc="lower right", fontsize=8.6)
    ax.add_artist(leg)
    ax.legend(handles=h2, frameon=False, loc="lower left", fontsize=8.6)
    f.subplots_adjust(left=0.1, right=0.97, top=0.9)
    save(f, "06_learning_curve.png",
         f"Real 5k: trained on n sandbox accounts, scored on a 25% holdout (10 seeds). Synthetic 50k: trained on n of tm-data's "
         f"Gaussian-copula synthetic accounts, scored on all 5,000 sandbox accounts (3-10 seeds). Labels in both come from our "
         f"own simulated recipe, so this is a pipeline check, not real-world accuracy. Points above the ceiling are noise: on the same real rows the oracle scores 0.864 and the model 0.869 (difference +0.005, 95% CI -0.003 to +0.015). Pink band = +/-1 sd for the Model A logistic regression. Source: {Path(src).name} (tm-bench).")
    return {"file": str(src), "metric": met, "ceiling": ceiling, "series": out}


def chart_learning():
    expects = ("Expected: harness/bench/out/learning_curve_long.csv\n(target, train_source, model, n_train, metric, value, sd;"
               " filtered to target == churn_90d)\nor harness/bench/*.csv with model, n_train, metric, value")
    long_csv = REPO / "harness" / "bench" / "out" / "learning_curve_long.csv"
    cands = ([long_csv] if long_csv.exists() else []) + [Path(c) for c in sorted(glob.glob(str(REPO / "harness" / "bench" / "*.csv")))] + \
        [Path(c) for c in sorted(glob.glob("/workspace/tmobile/bench-scratch/*learning*.csv"))]
    for c in cands:
        try:
            t = pd.read_csv(c)
        except Exception:  # noqa: BLE001
            continue
        t.columns = [x.lower() for x in t.columns]
        if not {"model", "n_train", "value"} <= set(t.columns):
            continue
        if "target" in t:
            t = t[t.target == "churn_90d"]
        if "metric" not in t:
            t["metric"] = "score"
        if len(t):
            return _plot_learning(t, str(c))
    return placeholder("06_learning_curve.png", "Benchmark learning curve", "Waiting on tm-bench", expects)


# ------------------------------------------------------------------ main
SCORE_NOTE = ""


def main():
    global SCORE_NOTE
    data = load_all()
    df = base_frame(data)
    hold = find_csv(["*holdout*pred*.csv", "*oof*.csv", "*holdout*scores*.csv"])
    eval_df = df
    if hold is not None:
        h = pd.read_csv(hold)
        if {"account_id", "p_churn_90d"} <= set(h.columns):
            eval_df = df.drop(columns="p_churn_90d").merge(h[["account_id", "p_churn_90d"]], on="account_id")
            SCORE_NOTE = f"Holdout scores: {hold.name}."
    if not SCORE_NOTE:
        SCORE_NOTE = "Scores on all accounts (incl. training rows); see model card for holdout metrics."
    out = {"sources": {k: (v.source, v.path) for k, v in data.items()}, "score_note": SCORE_NOTE}
    out["quadrant"] = chart_quadrant(df)
    chart_top20(df)
    out["gain"] = chart_gain(eval_df)
    out["calibration"] = chart_calibration(eval_df)
    out["qini"] = chart_qini()
    out["policy"] = chart_policy()
    out["learning"] = chart_learning()
    import json
    (HERE / "chart_stats.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "calibration"}, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()
