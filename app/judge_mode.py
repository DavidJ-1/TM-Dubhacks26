"""Judge mode: four beats on one engine and one set of numbers.

Every number on these screens comes from the saved run in demo_data/ (the calibrated churn model
and the expected-value offer engine that the Devpost describes). All customers are synthetic.
The judges' sandbox reference score (about 14.6% expected 90-day churn) appears only as a labeled
side note; the live console screens that use it sit in the appendix.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from console_app import COLORS, bubble_html, chart, text_we_would_send
from harness.saved_sms import hindi_and_chinese

PRODUCT = "Two Cakes"
TAGLINE = "Bring the one that says wait."
SANDBOX_REFERENCE_RATE = 0.146  # judges' public reference score, 5,000 accounts, mean 90-day probability

BEATS = (
    "1 · Who's drifting",
    "2 · Why this customer",
    "3 · The one that says wait",
    "4 · Proof",
)

STORIES = (
    ("ACC-PERSONA-04", "Fix it first", "Bill up 14%, open network issues"),
    ("ACC-PERSONA-21", "A check-in, not a discount", "Five-year customer who asked about leaving"),
    ("ACC-PERSONA-38", "Save them money", "Paying full price for a plan they can get cheaper"),
    ("ACC-PERSONA-24", "Say wait: do nothing", "Nine calls, all resolved, happy"),
)

QUIET_REASONS = {
    "happy": "Happy: issues resolved, active, not shopping",
    "open_ticket": "Open support ticket: no marketing until it's fixed",
    "wait_payoff": "Phone still being paid off: honest advice is wait",
    "recent_complaints": "Recent complaints closed: watch, don't sell",
    "low_risk": "Low risk: an offer would be wasted",
    "bill_shock_low_risk": "Bill went up, risk is low: no upsell, no credit",
    "usage_need_held": "Near the plan limit, but a bigger plan isn't worth pushing",
    "shopping_low_risk": "Comparing carriers, but low risk: a pitch could backfire",
}

SIGNAL_TOGGLES = (
    # key, label, applies-if(row), edits
    ("tickets", "Open support tickets", lambda r: float(r.get("unresolved_90d", 0) or 0) > 0,
     {"unresolved_90d": 0, "unresolved_270d": 0, "negative_contacts_90d": 0, "network_contacts_90d": 0}),
    ("port", "Asked us about transferring their number", lambda r: float(r.get("port_out_inquiry", 0) or 0) > 0,
     {"port_out_inquiry": 0}),
    ("comp", "Comparing carriers", lambda r: float(r.get("competitor_research_score", 0) or 0) >= 0.3,
     {"competitor_research_score": 0.0}),
)


# ---------- data ----------------------------------------------------------------------------------


@st.cache_data(show_spinner="Loading the decision run…")
def decisions() -> pd.DataFrame:
    offers = pd.read_csv(ROOT / "demo_data" / "offers.csv")
    scores = pd.read_csv(ROOT / "demo_data" / "churn_scores.csv")
    keep = ["account_id"] + [c for c in scores.columns if c.startswith(("risk_reason_", "stay_reason_"))]
    frame = offers.merge(scores[keep], on="account_id", how="left")
    features = pd.read_csv(ROOT / "demo_data" / "features.csv")
    cols = [c for c in ("account_id", "segment", "tenure_months", "support_90d", "bill_increase_pct") if c in features]
    frame = frame.merge(features[cols], on="account_id", how="left")
    frame["persona"] = frame["account_id"].astype(str).str.startswith("ACC-PERSONA")
    frame["contacted"] = frame["action_code"].astype(str) != "do_nothing"
    return frame


@st.cache_data(show_spinner=False)
def candidates(account_id: str) -> pd.DataFrame:
    table = pd.read_csv(ROOT / "demo_data" / "offer_candidates.csv.gz")
    return table.loc[table["account_id"] == account_id].sort_values("rank")


@st.cache_data(show_spinner=False)
def headline() -> dict:
    """One headline set. Computed from the saved files, not typed in."""
    from sklearn.metrics import roc_auc_score

    frame = decisions()
    regular = frame.loc[~frame["persona"]]
    oof = pd.read_csv(ROOT / "demo_data" / "churn_oof_pred.csv")
    labels = pd.read_csv(ROOT / "demo_data" / "labels.csv")[["account_id", "churn_90d"]]
    joined = oof.merge(labels, on="account_id")
    auc = float(roc_auc_score(joined["churn_90d"], joined["p_churn_90d"]))
    ranked = joined.sort_values("p_churn_90d", ascending=False)
    top = ranked.head(int(round(len(ranked) * 0.10)))
    capture = float(top["churn_90d"].sum() / max(ranked["churn_90d"].sum(), 1))
    deciles = ranked.assign(decile=np.repeat(np.arange(10, 0, -1), int(np.ceil(len(ranked) / 10)))[: len(ranked)])
    share = deciles.groupby("decile")["churn_90d"].sum() / max(ranked["churn_90d"].sum(), 1)
    return {
        "accounts": int(len(frame)),
        "rate": float(regular["p_churn_90d"].mean()),
        "auc": auc,
        "top10_capture": capture,
        "contacted": int(frame["contacted"].sum()),
        "quiet": int((~frame["contacted"]).sum()),
        "decile_share": share.sort_index(),
    }


@st.cache_data(show_spinner=False)
def persona_titles_cached() -> dict:
    import importlib.util

    module = sys.modules.get("tm_ui_data")
    if module is None:
        spec = importlib.util.spec_from_file_location("tm_ui_data", ROOT / "app" / "data.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["tm_ui_data"] = module
        spec.loader.exec_module(module)
    try:
        return module.persona_titles()
    except Exception:  # noqa: BLE001
        return {}


def title_for(account_id: str, titles: dict) -> str:
    if account_id in titles and titles[account_id]:
        return str(titles[account_id])
    return "Customer " + str(account_id).replace("ACC-", "")


def _risk_text(p: float) -> str:
    return f"{p:.1%}" if p >= 0.001 else "<0.1%"


def _metrics_row(h: dict) -> None:
    a, b, c, d = st.columns(4)
    a.metric("Customers scored", f"{h['accounts']:,}")
    b.metric("Expected to leave in 90 days", f"{h['rate']:.1%}", help="Simulated labels calibrated to T-Mobile's public ~1%/month postpaid churn.")
    c.metric("Riskiest 10% hold", f"{h['top10_capture']:.0%} of leavers")
    d.metric("Left alone on purpose", f"{h['quiet']:,}")


# ---------- beat 1 --------------------------------------------------------------------------------


def whos_drifting(titles: dict) -> None:
    h = headline()
    st.subheader("Who's drifting")
    _metrics_row(h)
    st.caption(
        f"Ranking quality (AUC) {h['auc']:.2f} on held-out folds; the best this synthetic data allows is about 0.86. "
        "Why not accuracy? Only about 1% of customers leave each month, so a model that says \"nobody leaves\" "
        "is 99% accurate and catches no one. We measure how well it ranks instead. "
        f"Side note: the judges' sandbox reference score puts 90-day churn at {SANDBOX_REFERENCE_RATE:.1%}; "
        "we use it only as a ranking check."
    )
    left, right = st.columns([1, 1])
    with left:
        share = h["decile_share"]
        fig = go.Figure(
            go.Bar(
                x=[str(i) for i in share.index],
                y=share.values,
                marker_color=[COLORS["magenta"] if i == 10 else "#C8B8C2" for i in share.index],
                hovertemplate="Risk group %{x}<br>%{y:.0%} of leavers<extra></extra>",
            )
        )
        fig.update_layout(title="Where the leavers are (10 = riskiest tenth)", yaxis_tickformat=".0%")
        fig.update_xaxes(title="Risk group, lowest to highest")
        chart(fig, height=360)
    with right:
        frame = decisions()
        flagged = frame.loc[~frame["persona"]].nlargest(int(h["accounts"] * 0.10), "p_churn_90d")
        reasons = flagged["risk_reason_1"].dropna().astype(str)
        top = reasons.value_counts().head(6)[::-1]
        fig = go.Figure(go.Bar(y=top.index, x=top.values, orientation="h", marker_color=COLORS["ink"]))
        fig.update_layout(title="Top reason among the riskiest 10%")
        fig.update_xaxes(title="Customers")
        chart(fig, height=360)
    st.markdown("**Most at risk right now**")
    frame = decisions()
    view = frame.sort_values("p_churn_90d", ascending=False).head(15)
    table = pd.DataFrame(
        {
            "Customer": [title_for(a, titles) for a in view["account_id"]],
            "Risk, 90 days": [_risk_text(p) for p in view["p_churn_90d"]],
            "Top reason": view["risk_reason_1"].fillna("").astype(str),
            "Our decision": view["action"].astype(str).str.capitalize(),
        }
    )
    st.dataframe(table, hide_index=True, width="stretch")
    warm_live()


# ---------- beat 2 --------------------------------------------------------------------------------


@st.cache_resource(show_spinner="Loading the live re-scorer…")
def _live_engine():
    harness_dir = str(ROOT / "harness")
    if harness_dir not in sys.path:
        sys.path.append(harness_dir)  # offer_api imports its sibling modules by bare name
    from harness import offer_api as api
    from harness.churn_scorer import score_account

    features = pd.read_csv(ROOT / "demo_data" / "features.csv").set_index("account_id", drop=False)
    return api, score_account, features


@st.cache_resource(show_spinner="Warming up the live what-if engine…")
def warm_live() -> bool:
    """Load the scorer and offer chooser once, so the first toggle flip on beat 2 is fast."""
    try:
        api, score_account, features = _live_engine()
        account_id = STORIES[0][0]
        p, _r, _s = score_account(features.loc[account_id].to_dict())
        api.choose_offer(api.prepared_row(account_id), p)
        return True
    except Exception:  # noqa: BLE001
        return False


def what_if(account_id: str, edits: dict) -> dict:
    """Re-score with the churn model and re-pick with the real offer chooser. Never raises."""
    try:
        api, score_account, features = _live_engine()
        row = features.loc[account_id].to_dict()
        row.update(edits)
        p, risks, _stays = score_account(row)
        engine_row = api.prepared_row(account_id)
        for key, value in edits.items():
            if key in engine_row.index:
                engine_row[key] = value
        res = api.choose_offer(engine_row, p)
        return {"p": p, "risks": risks, "res": res, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"p": None, "risks": [], "res": None, "error": f"Live re-score unavailable: {type(exc).__name__}: {exc}"}


def _options_table(account_id: str, live: pd.DataFrame | None = None) -> None:
    table = live if live is not None else candidates(account_id)
    if table is None or table.empty:
        return
    view = pd.DataFrame(
        {
            "Option": table["action"].astype(str).str.capitalize(),
            "Eligible": table["eligible"].map(lambda v: "Yes" if bool(v) else "No"),
            "Expected value": table["expected_value"].map(lambda v: f"${float(v):,.0f}" if pd.notna(v) else "—"),
            "Why it won or lost": [
                str(r) if pd.notna(r) and str(r) != "nan" else str(b) if pd.notna(b) else ""
                for r, b in zip(table["reason"], table["blocked_or_ineligible_reason"])
            ],
        }
    )
    st.markdown("**Every option we weighed (doing nothing is always on the list at $0)**")
    st.dataframe(view.head(8), hide_index=True, width="stretch")


def why_this_customer(titles: dict) -> None:
    frame = decisions()
    st.subheader("Why this customer")
    labels = {a: f"{title_for(a, titles)} · {story}" for a, story, _note in STORIES}
    pick = st.radio("Customer", list(labels), format_func=labels.get, horizontal=True, key="jm_pick")
    with st.expander("Or open any of the 5,042 customers"):
        all_ids = frame.sort_values("p_churn_90d", ascending=False)["account_id"].tolist()
        other = st.selectbox(
            "Customer",
            [None, *all_ids],
            format_func=lambda a: "Pick a customer…" if a is None else f"{title_for(a, titles)} · {_risk_text(float(frame.loc[frame.account_id == a, 'p_churn_90d'].iloc[0]))}",
            key="jm_any",
        )
        if other:
            pick = other
    row = frame.loc[frame["account_id"] == pick].iloc[0]

    # what-if toggles: start ON (the fact as it is); switching one off removes it and re-decides live
    applicable = [(k, lab, ed) for k, lab, cond, ed in SIGNAL_TOGGLES if cond(_live_row(pick))]
    edits: dict = {}
    if applicable:
        st.markdown("**What if?** Switch a signal off and the engine re-scores and re-decides live.")
        cols = st.columns(len(applicable))
        for col, (key, label, edit) in zip(cols, applicable):
            if not col.toggle(label, value=True, key=f"jm_t_{pick}_{key}"):
                edits.update(edit)

    risk = float(row["p_churn_90d"])
    action = str(row["action"]).capitalize()
    why = str(row.get("why_this_offer") or "")
    english = str(row.get("message_en") or "")
    spanish = str(row.get("message_es") or "")
    risks = [row.get(f"risk_reason_{i}") for i in (1, 2, 3)]
    live_cands = None
    if edits:
        with st.spinner("Re-scoring…"):
            result = what_if(pick, edits)
        if result["error"]:
            st.warning(result["error"])
        else:
            res = result["res"]
            risk = float(result["p"])
            action = str(res["action"]).capitalize()
            why = str(res.get("why_this_offer") or "")
            english = str(res.get("message_en") or "")
            spanish = str(res.get("message_es") or "")
            risks = result["risks"]
            live_cands = res.get("candidates")
            st.info(f"Live: risk {float(row['p_churn_90d']):.1%} → {risk:.1%}. Decision: {action}.")

    left, right = st.columns([0.95, 1.05])
    with left:
        hindi, chinese = hindi_and_chinese(english) if english and english != "nan" else ("", "")
        text_we_would_send(
            english if english != "nan" else "",
            spanish if spanish != "nan" else "",
            why or "Nothing would help them right now.",
            pick,
            f"jm_send_{pick}_{'live' if edits else 'saved'}",
            hindi=hindi,
            chinese=chinese,
        )
    with right:
        st.markdown(f"### {title_for(pick, titles)}")
        m1, m2 = st.columns(2)
        m1.metric("Risk of leaving, 90 days", _risk_text(risk))
        m2.metric("Decision", action)
        if why:
            st.write(why)
        shown = [r for r in risks if isinstance(r, str) and r]
        if shown:
            st.markdown("**Reasons to leave**")
            for item in shown:
                st.write("· " + item)
        stays = [row.get(f"stay_reason_{i}") for i in (1, 2, 3)]
        stays = [s for s in stays if isinstance(s, str) and s]
        if stays and not edits:
            st.markdown("**Reasons to stay**")
            for item in stays:
                st.write("· " + item)
    _options_table(pick, live_cands)


@st.cache_data(show_spinner=False)
def _features_row(account_id: str) -> dict:
    features = pd.read_csv(ROOT / "demo_data" / "features.csv")
    hit = features.loc[features["account_id"] == account_id]
    return hit.iloc[0].to_dict() if len(hit) else {}


def _live_row(account_id: str) -> dict:
    return _features_row(account_id)


# ---------- beat 3 --------------------------------------------------------------------------------


def says_wait(titles: dict) -> None:
    frame = decisions()
    h = headline()
    st.subheader("The one that says wait")
    st.markdown(
        f"<div style='font-size:3.2rem;font-weight:700;color:{COLORS['magenta']};line-height:1.1'>"
        f"{h['quiet']:,} <span style='font-size:1.4rem;color:{COLORS['ink']}'>of {h['accounts']:,} customers: "
        "we chose not to send anything.</span></div>",
        unsafe_allow_html=True,
    )
    st.caption("Every one of them has a written reason. Doing nothing competes with every offer at $0, and often wins.")
    quiet = frame.loc[~frame["contacted"]]
    counts = quiet["do_nothing_reason"].fillna("other").map(lambda k: QUIET_REASONS.get(k, str(k))).value_counts()[::-1]
    fig = go.Figure(
        go.Bar(
            y=counts.index,
            x=counts.values,
            orientation="h",
            marker_color=COLORS["magenta"],
            text=[f"{v:,}" for v in counts.values],
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(title="Why we stayed quiet", margin=dict(l=16, r=60, t=56, b=40))
    fig.update_xaxes(title="Customers")
    chart(fig, height=380)

    left, right = st.columns(2)
    with left:
        row = frame.loc[frame["account_id"] == "ACC-PERSONA-24"].iloc[0]
        with st.container(border=True):
            st.markdown(f"**{title_for('ACC-PERSONA-24', titles)}**")
            st.write(
                "Nine support contacts in nine months. A \"3+ calls\" rule would panic and send a discount. "
                "Ours reads the rest of the signals."
            )
            st.write(str(row.get("why_this_offer") or ""))
            st.markdown(
                "<div class='phone'><div class='phone-bar'></div>"
                f"<div class='bubble'>{bubble_html('No message. Their phone stays silent.')}</div></div>",
                unsafe_allow_html=True,
            )
            st.caption(f"Risk of leaving, 90 days: {_risk_text(float(row['p_churn_90d']))}")
    with right:
        compared = pd.read_csv(ROOT / "demo_data" / "comparison.csv")
        compared["name"] = compared["strategy"].str.replace(r"^\d+[a-z]?\.\s*", "", regex=True)
        everyone = compared.loc[compared["name"].str.startswith("Discount everyone")].iloc[0]
        ours = compared.loc[compared["name"].str.startswith("Ours")].iloc[0]
        with st.container(border=True):
            st.markdown("**Same assumptions, two strategies (simulated)**")
            a, b = st.columns(2)
            a.metric("Discount everyone: credits", f"${everyone['credit_spend_usd'] / 1000:,.0f}K")
            b.metric("Ours: credits", f"${ours['credit_spend_usd'] / 1000:,.1f}K")
            a.metric("Texts to people not leaving", f"{int(everyone['contacts_to_low_risk']):,}")
            b.metric("Leavers reached", f"{int(ours['churners_reached'])} of {int(everyone['churners_reached'])}")
            st.caption("Ours gives no bill credit to any low-risk customer. Low-risk contacts are fixes, cheaper plans and check-ins.")
        lines = pd.read_csv(ROOT / "demo_data" / "line_tradein.csv", usecols=["wait_verdict"])
        waits = int((lines["wait_verdict"] == "wait").sum())
        with st.container(border=True):
            st.markdown("**And for phones**")
            st.write(
                f"On {waits:,} of {len(lines):,} lines, the honest upgrade advice is \"wait\": "
                "the phone is still being paid off, or a better trade-in moment is coming."
            )


# ---------- beat 4 --------------------------------------------------------------------------------


def proof(strategy_figure) -> None:
    h = headline()
    st.subheader("Proof, and what it isn't")
    st.markdown(
        f"- **Ranking:** AUC {h['auc']:.2f} on held-out folds, close to the ~0.86 the synthetic data allows. "
        f"The riskiest 10% hold {h['top10_capture']:.0%} of leavers.\n"
        "- **Prices are right every time:** every plan and promotion in a message is a real row of the sandbox tables; "
        "all contacted customers were audited for eligibility and dollar amounts.\n"
        "- **Pays at realistic save rates (simulated):** the next engine version breaks even at about a 4.8% save rate; "
        "measured campaigns run about 2% to 11%.\n"
        "- **What it isn't:** the sandbox has no real churn outcomes, so every outcome here is simulated. "
        "The next step is a holdout test with real customers."
    )
    compared = pd.read_csv(ROOT / "demo_data" / "comparison.csv")
    compared = compared.loc[~compared["strategy"].astype(str).str.match(r"^\s*\d+[a-z]\.")]
    st.plotly_chart(strategy_figure(compared), width="stretch", config={"staticPlot": True, "displayModeBar": False})
    view = pd.DataFrame(
        {
            "Strategy": compared["strategy"].str.replace(r"^\d+\.\s*", "", regex=True),
            "Customers contacted": compared["contacted"].map(lambda v: f"{int(v):,}"),
            "Low-risk contacted": compared["contacts_to_low_risk"].map(lambda v: f"{int(v):,}"),
            "Credit spend": compared["credit_spend_usd"].map(lambda v: f"${v:,.0f}"),
            "Leavers reached": compared["churners_reached"].map(lambda v: f"{int(v)}"),
        }
    )
    st.dataframe(view, hide_index=True, width="stretch")
    st.caption("Simulated, with the same assumptions for every strategy. Not measured lift.")
    charts = ((ROOT / "app" / "charts" / "02_cumulative_gain.png", "Cumulative gain vs the 3+ calls rule"),
              (ROOT / "app" / "charts" / "03_calibration.png", "Calibration: does 20% risk mean 20%?"))
    cols = st.columns(2)
    for col, (path, label) in zip(cols, charts):
        with col:
            st.markdown(f"**{label}**")
            if path.exists():
                st.image(str(path), width="stretch")
