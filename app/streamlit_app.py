"""T-Mobile churn + upsell harness: demo UI (tm-ui lane).

Run:  streamlit run app/streamlit_app.py
Reads harness/out/*.csv when present (LANES.md contracts), else app/mock/*.csv.
ALL CUSTOMERS ARE SYNTHETIC (judge sandbox + mock scoring).
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import load_all, merged, persona_titles, truthy, upgrade_flag_cols  # noqa: E402
from messages import action_label, normalize_action, render_message  # noqa: E402

MAGENTA = "#E20074"
st.set_page_config(page_title="Churn + Upsell Harness (synthetic)", page_icon="📱", layout="wide")

st.markdown(f"""
<style>
.synth-banner {{position: sticky; top: 2.8rem; z-index: 999; background: {MAGENTA}; color: white;
  padding: .45rem 1rem; border-radius: 8px; font-weight: 700; text-align: center; margin-bottom: .8rem;}}
.src {{display:inline-block; font-size:.7rem; font-weight:700; padding:1px 7px; border-radius:10px;
  margin-right:6px; color:white; text-transform:uppercase; letter-spacing:.04em}}
.src-commerce {{background:#1f77b4}} .src-customer {{background:#2ca02c}} .src-live {{background:#ff7f0e}}
.sig-row {{padding:4px 0; border-bottom:1px solid #eee; font-size:.92rem}}
.offer-box {{border:2px solid {MAGENTA}; border-radius:12px; padding:14px 16px; background:#fff0f7}}
.wait-box {{border:2px solid #555; border-radius:12px; padding:14px 16px; background:#f4f4f4}}
.phone {{width:290px; margin:auto; border:12px solid #111; border-radius:38px; background:#f2f2f7;
  min-height:470px; padding:30px 12px 18px; box-shadow:0 8px 24px rgba(0,0,0,.25); position:relative}}
.notch {{position:absolute; top:6px; left:50%; transform:translateX(-50%); width:90px; height:18px;
  background:#111; border-radius:10px}}
.sender {{text-align:center; font-size:.75rem; color:#666; margin-bottom:10px}}
.bubble {{background:#e5e5ea; color:#000; border-radius:18px; padding:10px 13px; font-size:.86rem;
  line-height:1.3; max-width:88%;}}
.nomsg {{text-align:center; color:#777; margin-top:150px; font-size:.9rem}}
.tag {{display:inline-block; background:#eee; border-radius:10px; padding:1px 8px; margin:2px; font-size:.78rem}}
</style>
<div class="synth-banner">⚠️ All customers are synthetic: T-Mobile judge sandbox data with simulated scores. Not real customers.</div>
""", unsafe_allow_html=True)

data = load_all()
PERSONAS = persona_titles()
df = merged(data)
flag_cols = upgrade_flag_cols(data["offers"].df)
if "action_code" in df:  # tm-offers machine code; falls back to the human-readable action
    df["action_key"] = df["action_code"].fillna(df.get("action")).map(normalize_action)
elif "action" in df:
    df["action_key"] = df["action"].map(normalize_action)

# Column names = tm-data's harness/out/features.csv. Source grouping is a UI choice:
# commerce = plan/bill/device/financing, customer = profile + support history, live = latest signals snapshot.
SIGNALS = {  # column -> (source, label, kind)
    "plan_sku": ("commerce", "Plan", "plan"), "n_lines": ("commerce", "Lines", "int"),
    "last_bill_cents": ("commerce", "Latest monthly bill", "cents"),
    "bill_change_3m_pct": ("commerce", "Bill change vs prior 3 mo", "pct"),
    "promo_expired_recent": ("commerce", "Promo credit expired recently", "yesno"),
    "installment_ended_recent": ("commerce", "Phone just paid off", "yesno"),
    "min_financing_months_left_financed": ("commerce", "Financing months left", "int"),
    "max_device_age_months": ("commerce", "Oldest phone (months)", "int"),
    "n_lines_over_cap_3m": ("commerce", "Lines over plan data cap", "int"),
    "segment": ("customer", "Segment", "str"), "tenure_months": ("customer", "Tenure (months)", "int"),
    "language": ("customer", "Language", "str"), "contact_preference": ("customer", "Contact preference", "str"),
    "autopay": ("customer", "AutoPay", "yesno"),
    "support_90d": ("customer", "Support contacts (90d)", "int"), "unresolved_90d": ("customer", "Unresolved (90d)", "int"),
    "avg_sentiment_90d": ("customer", "Avg support sentiment (90d, -1..1)", "float"),
    "network_contacts_90d": ("customer", "Network complaints (90d)", "int"),
    "cancel_inquiries_270d": ("customer", "Cancellation inquiries (270d)", "int"),
    "competitor_research_score": ("live", "Competitor research score (0..1)", "float"),
    "port_out_inquiry": ("live", "Port-out inquiry", "yesno"),
    "app_sessions_30d": ("live", "T-Life app sessions (30d)", "int"),
    "data_growth_pct": ("live", "Data use growth", "pct"),
}

# ---------------- sidebar ----------------
with st.sidebar:
    st.markdown("### 📱 Churn + Upsell Harness")
    page = st.radio("Screen", ["Insights", "Who's at risk this week", "Customer card", "Charts"], key="page")
    st.divider()
    st.caption("Data sources (auto-switch to real outputs when they land)")
    for n, l in data.items():
        icon = {"real": "🟢 real", "mock": "🟡 mock", "missing": "🔴 missing"}[l.source]
        st.caption(f"**{n}.csv**: {icon}")
        if l.note:
            st.caption(f"↳ {l.note}")
    if st.button("Reload data"):
        st.rerun()
    st.caption("<span class='src src-commerce'>commerce</span><span class='src src-customer'>customer</span>"
               "<span class='src src-live'>live</span>", unsafe_allow_html=True)
any_mock = any(l.source != "real" for k, l in data.items() if k in ("churn_scores", "offers"))


def mock_note():
    parts = []
    if data["churn_scores"].source != "real":
        parts.append("churn scores and reasons are **mock** until Model A (tm-churn) lands")
    if data["offers"].source != "real":
        parts.append("offers are **mock** until Model B (tm-offers) lands")
    if parts:
        st.info("Heads-up: " + "; ".join(parts) + ".", icon="🧪")


def fmt_prob(p) -> str:
    """Adaptive precision: 74% / 5.2% / 0.05% / <0.01%."""
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "n/a"
    if p >= 0.1:
        return f"{p:.0%}"
    if p >= 0.01:
        return f"{p:.1%}"
    if p >= 0.0001:
        return f"{p * 100:.2g}%"
    return "<0.01%"


def flag_label(c: str) -> str:
    return c.removeprefix("um_").removeprefix("upgrade_").replace("_", " ")


def open_card(acc: str):
    st.session_state["account"] = acc
    st.session_state["page"] = "Customer card"


# ---------------- Insights ----------------
def held_out_gain() -> dict | None:
    """Held-out Model A gain stats written by app/charts/make_charts.py (None if missing or not out-of-fold)."""
    import json
    p = Path(__file__).resolve().parent / "charts" / "chart_stats.json"
    try:
        s = json.loads(p.read_text())
        g = s.get("gain") or {}
        if "model_top10" not in g or not str(s.get("score_note", "")).startswith("Holdout"):
            return None
        return g
    except Exception:  # noqa: BLE001
        return None


def insights():
    st.title("Insights from T-Mobile's own sandbox data")
    st.caption("Judge-provided sandbox: 5,000 synthetic households, 12 months of usage, billing and support. "
               "Churn figures are **sandbox scoring** (real outcomes are private to the judges).")
    c1, c2, c3, c4 = st.columns(4)
    _cs = data["churn_scores"].df
    _cs = _cs[~_cs.account_id.astype(str).str.startswith("ACC-PERSONA")]
    c1.metric("Expected to churn in 90 days (Model A, synthetic)", f"{_cs.p_churn_90d.mean():.1%}",
              help="Model A, calibrated to ~1%/month (synthetic). The judge sandbox's raw toy score averages 14.6%.")
    gain = held_out_gain()
    if gain is not None:
        c2.metric("Churners caught by calling the riskiest 10%", f"{gain['model_top10']:.0%}",
                  help="Model A held-out (5-fold out-of-fold) scores on synthetic labels"
                       + (f"; oracle {gain['oracle_top10']:.0%}" if gain.get("oracle_top10") is not None else "")
                       + (f", support-calls ranking {gain['rule_rank_top10']:.0%}" if gain.get("rule_rank_top10") is not None else "")
                       + ". All data synthetic.")
    else:
        c2.metric("Churners in riskiest 20% of accounts", "61%", help="Targeting beats blanket discounts")
    c3.metric("Asked about cancelling", "346 accounts")
    c4.metric("Promo expired recently", "553 accounts")

    st.subheader("What drives churn (sandbox scoring)")
    drivers = pd.DataFrame([
        ("Support contacts (90d)", "0", 4), ("Support contacts (90d)", "3", 18), ("Support contacts (90d)", "5+", 54),
        ("Competitor research", "score 0", 5), ("Competitor research", "score 0.75+", 50),
        ("Bill change", "flat / down", 10), ("Bill change", "up >5%", 23),
        ("Port-out inquiry", "no", 14), ("Port-out inquiry", "yes", 41),
        ("Tenure", "<1 year", 16.7), ("Tenure", "3+ years", 12.8),
    ], columns=["driver", "group", "churn_pct"])
    chart = alt.Chart(drivers).mark_bar(color=MAGENTA).encode(
        x=alt.X("churn_pct:Q", title="90-day churn % (sandbox scoring, synthetic)"),
        y=alt.Y("group:N", title=None, sort=None),
        row=alt.Row("driver:N", title=None, sort=None, header=alt.Header(labelAngle=0, labelAlign="left")),
        tooltip=["driver", "group", "churn_pct"]).properties(height=alt.Step(18), width=520).resolve_scale(y="independent")
    st.altair_chart(chart)
    st.caption("Source: plan doc 'Useful data' headline stats, computed with the sandbox's own scoring pipeline on 5,000 accounts.")

    f, lab = data["features"], data["labels"]
    if f.source == "real" and lab.source == "real" and "churn_90d" in lab.df and "support_90d" in f.df:
        with st.expander("Live check: computed from tm-data's harness/out files (synthetic labels)"):
            j = f.df.merge(lab.df[["account_id", "churn_90d"]], on="account_id")
            j = j[~j.account_id.str.startswith("ACC-PERSONA")]
            j["support bucket"] = pd.cut(j.support_90d, [-1, 0, 2, 4, 999], labels=["0", "1-2", "3-4", "5+"])
            t = j.groupby("support bucket", observed=True).churn_90d.agg(["mean", "size"]).reset_index()
            t["churn_pct"] = t["mean"] * 100
            st.metric("Synthetic 90-day churn rate (labels.csv)", f"{j.churn_90d.mean():.1%}", help=f"{len(j):,} non-persona accounts")
            st.altair_chart(alt.Chart(t).mark_bar(color=MAGENTA).encode(
                x=alt.X("support bucket:N", sort=None, title="Support contacts in 90 days"),
                y=alt.Y("churn_pct:Q", title="90-day churn % (synthetic labels)"), tooltip=["support bucket", "churn_pct", "size"]
            ).properties(height=220), width="stretch")
            st.caption("labels.csv churn_90d is tm-data's synthetic label (calibrated per LANES.md). Not real outcomes.")

    a, b = st.columns(2)
    with a:
        st.subheader("Myth-buster")
        st.markdown("AutoPay, the Home Internet bundle and segment **barely change churn**. "
                    "People stay because nothing is going wrong: no unresolved support, a steady bill, not shopping around.")
        st.subheader("Upgrade moments in the data")
        um = pd.DataFrame([("Phone just paid off", 240), ("Usage up 30%+ (lines)", 188),
                           ("Over plan cap (lines)", 234), ("Phone 3+ years old (lines)", 800)], columns=["moment", "count"])
        st.altair_chart(alt.Chart(um).mark_bar(color="#555").encode(
            x=alt.X("count:Q", title="count (synthetic sandbox)"), y=alt.Y("moment:N", sort="-x", title=None)).properties(height=160),
            width="stretch")
    with b:
        st.subheader("This week's decisions")
        mock_note()
        if len(df) and "action_key" in df:
            mix = df.groupby("action_key").size().reset_index(name="accounts")
            mix["action"] = mix.action_key.map(action_label)
            st.altair_chart(alt.Chart(mix).mark_bar().encode(
                x=alt.X("accounts:Q"), y=alt.Y("action:N", sort="-x", title=None),
                color=alt.condition(alt.datum.action_key == "do_nothing", alt.value("#555"), alt.value(MAGENTA))
            ).properties(height=200), width="stretch")
            dn = int((df.action_key == "do_nothing").sum())
            st.markdown(f"**{dn} of {len(df)}** scored accounts get **no offer**: the engine says *wait* when an offer's "
                        "expected value is below zero.")
    st.caption("Everyone will build the chatbot. This is the one that says wait.")


# ---------------- At-risk list ----------------
def at_risk():
    st.title("Who's at risk this week")
    mock_note()
    if not len(df):
        st.warning("No churn scores loaded.")
        return
    c1, c2, c3 = st.columns([1, 1, 2])
    top_n = c1.slider("Show top", 5, max(5, len(df)), min(25, len(df)))
    min_p = c2.slider("Min 90-day churn risk", 0.0, 1.0, 0.0, 0.05)
    acts = sorted(df["action_key"].dropna().unique()) if "action_key" in df else []
    pick = c3.multiselect("Action", acts, default=acts, format_func=action_label)
    v = df[(df.p_churn_90d >= min_p)]
    if acts:
        v = v[v.action_key.isin(pick)]
    v = v.head(top_n)
    show = pd.DataFrame({
        "Rank": v.risk_rank, "Account": v.account_id,
        "Segment": v.get("segment", ""), "Risk (90d)": v.p_churn_90d * 100,
        "Top reason": v.risk_reason_1, "Action": v.get("action_key", pd.Series(dtype=str)).map(action_label),
        "Expected value ($)": v.get("expected_value"),
    })
    if flag_cols:
        show["Upgrade moment"] = v[flag_cols].apply(
            lambda r: ", ".join(flag_label(c) for c in flag_cols if truthy(r.get(c))), axis=1)
    ev = st.dataframe(show, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                      column_config={"Risk (90d)": st.column_config.ProgressColumn("Risk (90d)", format="%.1f%%", min_value=0, max_value=100),
                                     "Expected value ($)": st.column_config.NumberColumn(format="$%.0f")}, key="risk_table")
    st.caption("Risk = simulated 90-day churn probability. Expected value = p_churn × save rate × customer value − offer cost − annoyance (synthetic).")
    rows = ev.selection.rows if ev and hasattr(ev, "selection") else []
    if rows:
        acc = show.iloc[rows[0]]["Account"]
        st.button(f"Open customer card for {acc} →", on_click=open_card, args=(acc,), type="primary")
    else:
        st.caption("Select a row to open its customer card.")


# ---------------- Customer card ----------------
def fmt(col, val):
    if val is None or (not isinstance(val, str) and pd.isna(val)):
        return "n/a"
    kind = SIGNALS.get(col, (None, None, "auto"))[2]
    try:
        if kind == "yesno":
            return "yes" if int(val) else "no"
        if kind == "cents":
            return f"${float(val) / 100:,.2f}"
        if kind == "pct":
            pv = round(float(val) * 100)
            return f"{pv:+d}%" if pv else "0%"
        if kind == "int":
            return f"{int(round(float(val)))}"
        if kind == "plan":
            return html.escape(str(val).replace("TMO-STUB-PLAN-", "").replace("-", " ").title())
    except (TypeError, ValueError):
        pass
    if isinstance(val, float):
        return f"{val:,.2f}".rstrip("0").rstrip(".")
    return html.escape(str(val))


def phone(msg: str | None, lang: str, missing: bool = False) -> str:
    sender = "T-Mobile · Text Message"
    if msg is None and missing:
        inner = ("<div class='nomsg'><b>" + ("Sin texto en este idioma" if lang == "es" else "No text for this language yet")
                 + "</b></div>")
    elif msg is None:
        inner = ("<div class='nomsg'>🤫<br><b>No message sent</b><br>" +
                 ("El motor decidió esperar." if lang == "es" else "The engine decided to wait.") + "</div>")
    else:
        inner = f"<div class='bubble'>{html.escape(msg)}</div>"
    return f"<div class='phone'><div class='notch'></div><div class='sender'>{sender}</div>{inner}</div>"


def customer_card():
    st.title("Customer card")
    mock_note()
    if not len(df):
        st.warning("No accounts loaded.")
        return
    ids = df.account_id.tolist()
    cur = st.session_state.get("account", ids[0])
    acc = st.selectbox("Account", ids, index=ids.index(cur) if cur in ids else 0,
                       format_func=lambda a: f"#{int(df.loc[df.account_id == a, 'risk_rank'].iloc[0])} · {a}")
    st.session_state["account"] = acc
    r = df[df.account_id == acc].iloc[0]
    note = PERSONAS.get(acc)
    hdr = f"**{acc}** · {r.get('segment', '')} · {fmt('tenure_months', r.get('tenure_months'))} months · synthetic customer"
    st.markdown(hdr + (f"  \n_{html.escape(str(note))}_" if isinstance(note, str) and note else ""))

    m1, m2, m3 = st.columns(3)
    m1.metric("90-day churn risk (simulated)", fmt_prob(r.p_churn_90d))
    m2.metric("Risk rank", f"#{int(r.risk_rank)} of {len(df)}")
    m3.metric("Expected value of action (synthetic)", f"${float(r.get('expected_value', 0) or 0):,.0f}")

    left, mid, right = st.columns([1.15, 1.1, 1])
    with left:
        st.subheader("Signals")
        for src in ("commerce", "customer", "live"):
            rows = [(c, lab) for c, (s, lab, _k) in SIGNALS.items() if s == src and c in r.index]
            if not rows:
                continue
            st.markdown(f"<span class='src src-{src}'>{src}</span>", unsafe_allow_html=True)
            st.markdown("".join(f"<div class='sig-row'><span class='src src-{src}' style='opacity:.35'>{src[0]}</span>"
                                f"{lab}: <b>{fmt(c, r[c])}</b></div>" for c, lab in rows), unsafe_allow_html=True)
        if not any(c in r.index for c in SIGNALS):
            st.caption("No feature columns loaded (features.csv).")
    with mid:
        st.subheader("Why at risk")
        for i in (1, 2, 3):
            t = r.get(f"risk_reason_{i}")
            if isinstance(t, str) and t:
                st.markdown(f"🔺 {html.escape(t)}")
        st.subheader("Why they'd stay")
        for i in (1, 2, 3):
            t = r.get(f"stay_reason_{i}")
            if isinstance(t, str) and t:
                st.markdown(f"🟢 {html.escape(t)}")
        st.subheader("Decision")
        k = r.get("action_key", "do_nothing")
        reason = html.escape(str(r.get("reason", "")))
        if k == "do_nothing":
            st.markdown(f"<div class='wait-box'><b>✋ Do nothing: the one that says wait</b><br>{reason}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='offer-box'><b>🎯 {action_label(k)}</b><br>{reason}<br>"
                        f"<small>Expected value ${float(r.get('expected_value', 0) or 0):,.0f} (synthetic)</small></div>",
                        unsafe_allow_html=True)
        if truthy(r.get("also_fix_first")) and k != "fix_first_callback":
            st.markdown("➕ Also: fix-first callback for the open issue")
        ru = r.get("runner_up_action")
        if isinstance(ru, str) and ru:
            ru_txt = f"Runner-up: {action_label(ru)} (EV ${float(r.get('runner_up_ev', 0) or 0):,.0f}, synthetic)"
            st.caption(ru_txt.replace("$", "\\$"))
        flags = [flag_label(c) for c in flag_cols if truthy(r.get(c))]
        if flags:
            st.markdown("**Upgrade moments:** " + "".join(f"<span class='tag'>{html.escape(f)}</span>" for f in flags),
                        unsafe_allow_html=True)
    with right:
        st.subheader("Outgoing text")
        default = "es" if str(r.get("language", "en")) == "es" else "en"
        lang = st.radio("Language", ["en", "es"], index=["en", "es"].index(default), horizontal=True,
                        format_func=lambda x: {"en": "English", "es": "Español"}[x], key=f"lang_{acc}")
        col = f"message_{lang}"
        src = "none"
        if k == "do_nothing":
            msg = None
        elif col in r.index:  # tm-offers' tailored text, shown verbatim
            v = r.get(col)
            msg = v.strip() if isinstance(v, str) and v.strip() else None
            src = "offers.csv" if msg else "missing"
        else:  # columns missing: fall back to app/messages.py templates
            msg = render_message(k, lang, r.get("tenure_months"))
            src = "template" if msg else "none"
        st.markdown(phone(msg, lang, missing=src == "missing"), unsafe_allow_html=True)
        src_note = {"offers.csv": "Text from tm-offers (offers.csv).", "template": "_template_",
                    "none": "", "missing": f"offers.csv has no {col} for this row."}[src]
        st.caption(f"Channel preference: {fmt('contact_preference', r.get('contact_preference'))}. "
                   f"Mockup only, nothing is sent. {src_note}")


# ---------------- Charts ----------------
CHART_DIR = Path(__file__).resolve().parent / "charts"
CHARTS = [  # file, title, stats key
    ("01_risk_value_quadrant.png", "1 · Prioritization: risk vs value", "quadrant"),
    ("02_cumulative_gain.png", "2 · Cumulative gain vs the 3+ support-contacts rule", "gain"),
    ("03_calibration.png", "3 · Calibration", "calibration"),
    ("04_modelC_qini.png", "4 · Model C: uplift (Qini) curve", "qini"),
    ("05_modelC_policy_value.png", "5 · Model C: policy value", "policy"),
    ("06_learning_curve.png", "6 · Benchmark learning curve", "learning"),
]


def charts():
    import json
    import subprocess
    st.title("Charts")
    st.caption("Slide-ready PNGs (1600×900) in app/charts/, regenerated from harness/out with "
               "`python app/charts/make_charts.py`. All data synthetic.")
    if st.button("Regenerate charts from current outputs"):
        with st.spinner("Rendering…"):
            r = subprocess.run([sys.executable, str(CHART_DIR / "make_charts.py")], capture_output=True, text=True, timeout=300)
        (st.success if r.returncode == 0 else st.error)("Charts regenerated." if r.returncode == 0 else r.stderr[-2000:])
    stats_p = CHART_DIR / "chart_stats.json"
    stats = json.loads(stats_p.read_text()) if stats_p.exists() else {}
    for fname, title, key in CHARTS:
        st.subheader(title)
        info = stats.get(key) or {}
        img = CHART_DIR / fname
        if isinstance(info, dict) and info.get("placeholder"):
            st.warning(f"**{info.get('waiting', 'Waiting on inputs')}**. {info.get('expects', '')}".replace("\n", " "), icon="⏳")
            if img.exists():
                with st.expander("Placeholder PNG"):
                    st.image(str(img))
            continue
        if img.exists():
            if key == "quadrant":
                a, b = st.columns([1.6, 1])
                a.image(str(img))
                with b:
                    st.markdown("**Top 20 at risk**")
                    t = df.sort_values("risk_rank").head(20)
                    st.dataframe(pd.DataFrame({
                        "#": t.risk_rank.astype(int), "Account": t.account_id, "Risk": t.p_churn_90d.map(fmt_prob),
                        "Action": t.get("action_key", pd.Series(dtype=str)).map(action_label)}),
                        hide_index=True, height=420, width="stretch")
            else:
                st.image(str(img))
        else:
            st.info("Not generated yet. Click Regenerate.")
    if stats.get("sources"):
        st.caption("Chart inputs: " + ", ".join(f"{k} = {v[0]}" for k, v in stats["sources"].items()))


{"Insights": insights, "Who's at risk this week": at_risk, "Customer card": customer_card, "Charts": charts}[page]()
