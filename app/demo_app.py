"""One demo for judging. The Retention Console is the live path. David's saved run is the opener.

Live screens read the judge sandbox. The landing and the model-evidence screen read his
saved files (app/data.py, demo_data/, app/charts/, app/viz/) and stay labeled synthetic.
Those files are not inputs to Overview or Projections. app/streamlit_app.py is not imported:
it draws its own app at import time. make run-ui still starts it unchanged.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from console_app import (  # noqa: E402
    action_page,
    apply_css,
    get_console,
    overview,
    projections,
    queue,
    targeting_page,
    text_we_would_send,
    upgrades_page,
)
from harness.notify import default_topic  # noqa: E402
from harness.saved_sms import hindi_and_chinese  # noqa: E402

DEFAULT_TOPIC = "tm-dubhacks26-lf3reo19tv"

SYNTHETIC = "synthetic saved run"
BADGE = "synthetic, not the live judge score"
CARDS = (
    ("ACC-PERSONA-38", "Save them money", "Household plan fit"),
    ("ACC-PERSONA-04", "Fix it first", "Fix what is broken, then one credit"),
    ("ACC-PERSONA-21", "A check-in, not a discount", "They asked about leaving"),
    ("ACC-PERSONA-24", "Restraint: do nothing", "A happy caller is not an offer"),
)
SCREENS = (
    "1 · Landing",
    "2 · Who's at risk",
    "3 · Why this customer",
    "4 · What we do",
    "5 · Grow",
    "6 · Model evidence",
    "7 · Projections",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_DATA = _load("tm_ui_data", APP / "data.py")
_MESSAGES = _load("tm_ui_messages", APP / "messages.py")


def _badge() -> None:
    st.caption(BADGE)


@st.cache_data(show_spinner="Loading the saved offer run…")
def saved_offers() -> tuple[pd.DataFrame, dict, bool]:
    """David's tracked demo_data run, through app/data.py. Not the live console score."""
    loaded = _DATA.load_all()
    frame = _DATA.merged(loaded)
    action = frame["action_code"] if "action_code" in frame.columns else frame.get("action")
    frame = frame.copy()
    frame["action_key"] = action.map(_MESSAGES.normalize_action)
    return frame, _DATA.persona_titles(), _DATA.is_mock(loaded)


def _story_card(frame: pd.DataFrame, titles: dict, account_id: str, story: str, note: str, index: int, key: str) -> None:
    rows = frame.loc[frame["account_id"] == account_id]
    st.markdown(f"**{index}. {story}**")
    st.caption(note)
    if rows.empty:
        st.warning(f"{account_id} is not in the saved offer run.")
        return
    row = rows.iloc[0]
    title = titles.get(account_id) or account_id
    action = _MESSAGES.action_label(row.get("action_key"))
    why = str(row.get("why_this_offer") or "").strip()
    if why == "nan":
        why = ""
    english = str(row.get("message_en") or "")
    hindi, chinese = hindi_and_chinese(english)
    text_we_would_send(
        english,
        str(row.get("message_es") or ""),
        why or "Nothing would help them right now.",
        account_id,
        key,
        hindi=hindi,
        chinese=chinese,
    )
    st.markdown(f"**{title}**")
    st.caption(f"{account_id} · {row.get('segment', '')} · {action}")
    if why:
        st.write(why)
    risks = [row.get(f"risk_reason_{i}") for i in (1, 2, 3)]
    stays, _dropped = _DATA.clean_stays(row)
    if any(isinstance(item, str) and item for item in risks):
        st.markdown("**Reasons to leave**")
        for item in risks:
            if isinstance(item, str) and item:
                st.write("· " + item)
    if stays:
        st.markdown("**Reasons to stay**")
        for item in stays:
            st.write("· " + item)
    st.caption(f"Churn risk, 90 days, from the saved file: {float(row['p_churn_90d']):.1%}. Not the live judge score.")


def _how_it_decides(frame: pd.DataFrame) -> None:
    st.subheader("How it decides")
    _badge()
    st.caption("Counts from the saved offer run. This is the shape of the pipeline, not a measured save rate.")
    regular = frame.loc[~frame["account_id"].astype(str).str.startswith("ACC-PERSONA")]
    cut = float(regular["p_churn_90d"].quantile(0.90)) if len(regular) else 1.0
    flagged = frame["p_churn_90d"] >= cut
    contact = frame["action_key"] != "do_nothing"
    ready = frame.get("message_en", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip()
    ready = contact & ~ready.isin(["", "nan"])
    steps = st.columns(5)
    steps[0].metric("1 · Accounts", f"{len(frame):,}")
    steps[1].metric("2 · Flagged, top 10%", f"{int(flagged.sum()):,}")
    steps[2].metric("3 · Get a decision", f"{int(contact.sum()):,}")
    steps[3].metric("4 · Left alone", f"{int((~contact).sum()):,}")
    steps[4].metric("5 · Drafts ready", f"{int(ready.sum()):,}")
    reasons = (
        frame.loc[flagged, "risk_reason_1"].fillna("").astype(str)
        if "risk_reason_1" in frame.columns
        else pd.Series(dtype=str)
    )
    reasons = reasons.loc[reasons.str.strip() != ""]
    if len(reasons):
        st.caption("Most common reason on the flagged accounts, from the saved file.")
        st.dataframe(
            reasons.value_counts().head(5).rename_axis("reason").reset_index(name="accounts"),
            hide_index=True,
            width="stretch",
        )


def landing_page() -> None:
    st.subheader("Four customers, four decisions")
    _badge()
    st.write(
        "Same saved pipeline, including staying silent. "
        "The live judge sandbox starts on the next screen. This opener does not change those numbers."
    )
    frame, titles, mock = saved_offers()
    if mock:
        st.error("The saved sandbox run was not found, so this opener is the small placeholder file.")
    _how_it_decides(frame)
    st.divider()
    st.subheader("Text messages")
    st.caption("One draft for each opener. Nothing is sent until you click.")
    for index, (account_id, story, note) in enumerate(CARDS, start=1):
        with st.container(border=True):
            _story_card(frame, titles, account_id, story, note, index, f"send_land_{account_id}")
    st.divider()
    st.subheader("Open any customer")
    _badge()
    labels = {
        account_id: (
            f"{account_id} · {segment} · {float(risk):.1%}"
        )
        for account_id, segment, risk in zip(
            frame["account_id"], frame.get("segment", pd.Series("", index=frame.index)), frame["p_churn_90d"], strict=True
        )
    }
    short = [account_id for account_id, _story, _note in CARDS if account_id in labels]
    full = st.checkbox(f"Search all {len(labels):,}", key="demo_lookup_all")
    options = list(labels) if full else short
    pick = st.selectbox(
        "Customer",
        [None, *options],
        format_func=lambda account_id: "Pick a customer…" if account_id is None else labels[account_id],
        key="demo_lookup",
    )
    if pick:
        with st.container(border=True):
            _story_card(frame, titles, pick, "Customer lookup", "Saved offer run", 0, f"send_lookup_{pick}")


def whos_at_risk(console) -> None:
    st.caption("Live judge sandbox. Personas stay in the queue. Population charts below use the 5,000 non-persona accounts.")
    overview(console)
    st.divider()
    queue(console)


_SHORT_STRATEGY = {
    "Do nothing": "Do nothing",
    "Discount everyone": "Discount everyone",
    "3+ support calls rule": "3+ support calls",
    "Top 10% risk score only": "Top 10% risk",
    "Ours": "Ours",
}


def _k_dollars(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value) / 1000:.0f}K"


def strategy_figure(compared: pd.DataFrame) -> go.Figure:
    """Fixed bar chart. Built here from comparison.csv. David's chart files stay untouched."""
    frame = compared.copy()
    frame["name"] = frame["strategy"].str.replace(r"^\d+\.\s*", "", regex=True)
    frame["label"] = frame["name"].map(lambda name: _SHORT_STRATEGY.get(name, name))
    values = frame["net_value_usd"].astype(float)
    low = float(values.min())
    high = float(values.max())
    span = max(high - low, 1.0)
    pad = span * 0.18
    figure = go.Figure(
        go.Bar(
            y=frame["label"],
            x=values,
            orientation="h",
            text=[_k_dollars(value) for value in values],
            textposition="outside",
            cliponaxis=False,
            marker_color=["#8A7B84" if value < 0 else "#E20074" for value in values],
            hoverinfo="skip",
        )
    )
    figure.update_layout(
        title="Same assumptions, different strategies",
        margin=dict(l=170, r=72, t=48, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#1A1220", size=14),
        height=360,
        xaxis=dict(
            title="Simulated net value",
            range=[low - pad, high + pad],
            fixedrange=True,
            tickmode="array",
            tickvals=[-80000, -40000, 0, 40000],
            ticktext=["$-80K", "$-40K", "$0", "$40K"],
            zeroline=True,
            zerolinecolor="#1A1220",
        ),
        yaxis=dict(
            title=None,
            fixedrange=True,
            automargin=True,
            categoryorder="array",
            categoryarray=list(frame["label"])[::-1],
        ),
    )
    return figure


def _comparison_chart() -> None:
    path = ROOT / "demo_data" / "comparison.csv"
    st.markdown("**Same assumptions, different strategies**")
    _badge()
    if not path.exists():
        st.caption("comparison.csv is not in this checkout.")
        return
    compared = pd.read_csv(path)
    compared = compared.loc[~compared["strategy"].astype(str).str.match(r"^\s*\d+[a-z]\.")]
    st.plotly_chart(strategy_figure(compared), width="stretch", config={"staticPlot": True, "displayModeBar": False})
    show = compared.copy()
    show["Strategy"] = show["strategy"].str.replace(r"^\d+\.\s*", "", regex=True)
    show = show[["Strategy", "contacted", "churners_reached", "net_value_usd"]]
    show["net_value_usd"] = show["net_value_usd"].map(lambda value: f"${value:,.0f}")
    st.dataframe(
        show,
        hide_index=True,
        width="stretch",
        column_config={"Strategy": st.column_config.TextColumn("Strategy", width=280)},
    )
    st.caption(
        "Simulated net value from demo_data/comparison.csv. "
        "Scored with assumed acceptance. This is not measured lift, and it is not the Projections screen."
    )


def _trial_table() -> None:
    path = ROOT / "harness" / "model_c_artifacts" / "policy_eval.csv"
    st.markdown("**Simulated 50k-account trial**")
    if not path.exists():
        st.caption("policy_eval.csv is not in this checkout.")
        return
    trial = pd.read_csv(path)
    view = trial[["policy", "n_contacted", "churners_saved_dr", "net_value_no_upsell_dr_usd"]].copy()
    view["churners_saved_dr"] = view["churners_saved_dr"].map(lambda value: f"{value:.1f}")
    view["net_value_no_upsell_dr_usd"] = view["net_value_no_upsell_dr_usd"].map(lambda value: f"${value:,.0f}")
    view = view.rename(
        columns={
            "policy": "Policy",
            "n_contacted": "Contacted on the test split",
            "churners_saved_dr": "Churners saved (doubly robust)",
            "net_value_no_upsell_dr_usd": "Net value, no upsell",
        }
    )
    st.dataframe(view, hide_index=True, width="stretch")
    note = str(trial["data_note"].iloc[0]) if "data_note" in trial.columns and len(trial) else ""
    st.caption(note[:420] if note else "Synthetic simulated trial. Not measured lift.")


def evidence_page() -> None:
    st.subheader("Model evidence (synthetic data)")
    _badge()
    st.write(
        "These charts are the saved model checks. They use simulated labels. "
        "They are not the live Overview, and they are not fed into Projections."
    )
    charts = (
        (APP / "charts" / "02_cumulative_gain.png", "Cumulative gain"),
        (APP / "charts" / "03_calibration.png", "Calibration"),
    )
    for path, title in charts:
        st.markdown(f"**{title}**")
        if path.exists():
            st.image(str(path), width="stretch")
        else:
            st.caption(f"{path.name} is not in this checkout.")
    _comparison_chart()
    _trial_table()
    st.divider()
    st.markdown("**Pipeline**")
    viz = APP / "viz" / "pipeline_flow.html"
    st.caption("Saved animation: sandbox data, churn risk, priced actions, and a text. Synthetic.")
    if viz.exists():
        st.iframe(viz, height=900)
    else:
        st.caption("pipeline_flow.html is not in this checkout.")


def send_sidebar() -> None:
    """Seed the controls, then send only on a click.

    Precedence for the seed: process environment, then .env (loaded by notify),
    then the in-app topic. An empty SEND_BACKEND still turns ntfy on.
    """
    explicit = os.environ.get("SEND_BACKEND", "").strip().lower()
    default_on = explicit != "dryrun"
    topic_default = default_topic() or DEFAULT_TOPIC
    on = st.sidebar.toggle("Send texts via ntfy", value=default_on)
    topic = st.sidebar.text_input("ntfy topic", value=topic_default).strip() or DEFAULT_TOPIC
    st.sidebar.caption(f"Install the ntfy app and subscribe to {topic}.")
    st.session_state["send_backend"] = "ntfy" if on else "dryrun"
    st.session_state["send_topic"] = topic


def main() -> None:
    st.set_page_config(page_title="Retention demo", layout="wide")
    apply_css()
    st.title("Retention demo")
    st.caption("DubHacks '26 · T-Mobile track")
    page = st.sidebar.radio("Screen", SCREENS)
    send_sidebar()
    st.sidebar.caption("Landing and Model evidence use the saved run. Every other screen is the live sandbox.")
    if page.startswith("1"):
        landing_page()
        return
    if page.startswith("6"):
        evidence_page()
        return
    try:
        console = get_console()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()
    if page.startswith("2"):
        whos_at_risk(console)
    elif page.startswith("3"):
        action_page(console)
    elif page.startswith("4"):
        targeting_page(console)
    elif page.startswith("5"):
        upgrades_page(console)
    else:
        projections(console)


if __name__ == "__main__":
    main()
