"""Retention Console. Streamlit UI over the Python scoring engine. No JavaScript frontend."""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from harness.engine import build_console
from harness.messages import draft, outbound_title
from harness.draft_lang import LANGUAGES, clean_draft, selected_draft
from harness.notify import send, will_send
from harness.playbook.send import frequency_open, record_send
from harness.playbook.rules import ASSUMPTION_CREDIT_CENTS, FREQUENCY_CAP_DAYS, RULES, VALUE_FORMULA
from harness.upsell.config import INCLUDE_SYNTHETIC_DEFAULT, SYNTHETIC_BADGE
from harness.projections import acceptance_curve, project, upgrade_curve

DEFAULT_SAVE_RATE = 0.10  # the save rate the Devpost uses; measured campaigns are about 2-11%
BREAK_EVEN_SAVE_RATE = 0.048  # Devpost / docs: next-version engine breaks even at about 4.8% (simulated)

PINNED = [
    "ACC-PERSONA-04",
    "ACC-PERSONA-24",
    "ACC-PERSONA-23",
    "ACC-PERSONA-10",
    "ACC-PERSONA-21",
    "ACC-PERSONA-22",
    "ACC-PERSONA-25",
    "ACC-PERSONA-27",
    "ACC-PERSONA-28",
    "ACC-PERSONA-30",
]

COLORS = {
    "ink": "#1A1220",
    "magenta": "#E20074",
    "paper": "#F7F1EA",
    "line": "#E4D9CF",
    "good": "#1F7A4D",
    "risk": "#E20074",
}


def dollars(cents: int | None) -> str:
    if cents is None:
        return "n/a"
    return f"${cents / 100:,.2f}"


def bubble_html(text) -> str:
    """Escape a draft for the phone bubble. `$` becomes an entity so markdown never renders math."""
    return html.escape(str(text)).replace("$", "&#36;")


def show(text) -> str:
    """Streamlit markdown treats a pair of $ signs as code. Keep amounts as text."""
    if text is None:
        return ""
    return str(text).replace("$", "\\$")


@st.cache_resource(show_spinner="Scoring the sandbox…")
def get_console():
    return build_console()


@st.cache_resource(show_spinner="Building the targeting playbook…")
def get_playbook():
    from harness.playbook.build import build_playbook

    return build_playbook(get_console())


@st.cache_data(show_spinner="Building upgrades and life moments…")
def get_upsell():
    from harness.upsell.build import build_upsell

    return build_upsell(get_console())


def apply_css() -> None:
    st.markdown(
        """
        <style>
          .stApp { background: #F7F1EA; color: #1A1220; }
          header[data-testid="stHeader"] { background: #F7F1EA; }
          section.main > div.block-container { padding-top: 2.75rem; }
          .banner {
            background: #1A1220; color: #F7F1EA; padding: 10px 14px; border-radius: 8px;
            font-size: 0.95rem; margin-bottom: 12px;
          }
          .banner strong { color: #FF8FBF; }
          .phone {
            width: 320px; max-width: 100%; background: #1A1220; border-radius: 28px;
            padding: 18px 14px 22px; margin-top: 8px;
          }
          .phone-bar { height: 8px; width: 96px; border-radius: 8px; background: #3A2C3E; margin: 0 auto 14px; }
          .bubble {
            background: #F7F1EA; color: #1A1220; border-radius: 16px 16px 16px 4px;
            padding: 12px 14px; white-space: pre-wrap; font-size: 0.92rem; line-height: 1.4;
          }
          .quiet { color: #C8B8C2; font-size: 0.9rem; padding: 8px 4px 4px; }
          div[data-testid="stMetric"] {
            background: white; border: 1px solid #E4D9CF; border-radius: 10px; padding: 8px 12px;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def banner() -> None:
    st.markdown(
        "<div class='banner'><strong>Synthetic data.</strong> "
        "Customers, prices, and promotions are the T-Mobile hackathon sandbox "
        "(stub data as of 2026-10-01). This is not a real customer file and not an official offer.</div>",
        unsafe_allow_html=True,
    )


def chart(fig: go.Figure, height: int = 400) -> None:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color=COLORS["ink"],
        margin=dict(l=16, r=28, t=56, b=48),
        height=height,
    )
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    st.plotly_chart(fig, width="stretch")


def selected_rows(event) -> list[int]:
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    rows = getattr(selection, "rows", None) if selection is not None else None
    if rows is None and isinstance(selection, dict):
        rows = selection.get("rows")
    return list(rows or [])


def ensure_selection(console) -> str:
    if "account_id" not in st.session_state or st.session_state.account_id not in console.details:
        st.session_state.account_id = "ACC-PERSONA-04"
    return st.session_state.account_id


def overview(console) -> None:
    stats = console.stats
    rate = stats["expected_churn_rate"]
    top20 = stats["concentration"]["top_20"]
    support = {row["bin"]: row for row in stats["support_bins"]}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expected 90-day churn", f"{rate:.1%}", help=stats["population_note"])
    c2.metric("Top 20% share of expected churners", f"{top20['share_of_expected_churners']:.0%}")
    c3.metric("5+ support contacts", f"{support['5+']['expected_churn']:.0%}", help=f"n={support['5+']['n']}")
    c4.metric("0 support contacts", f"{support['0']['expected_churn']:.0%}", help=f"n={support['0']['n']}")
    st.caption(
        f"Sandbox scoring on {stats['accounts']:,} non-persona accounts. "
        "These are mean probabilities from the public reference model, not observed churn. "
        f"Holdout AUC of our logistic model against a seeded draw from that score: "
        f"{console.metrics['holdout_auc']:.2f}. {console.metrics['label_note']}"
    )

    left, right = st.columns(2)
    with left:
        support_frame = pd.DataFrame(stats["support_bins"])
        fig = go.Figure(
            go.Bar(
                x=support_frame["bin"],
                y=support_frame["expected_churn"],
                marker_color=COLORS["magenta"],
                customdata=support_frame["n"],
                hovertemplate="Support contacts %{x}<br>Expected churn %{y:.1%}<br>n=%{customdata}<extra></extra>",
            )
        )
        fig.update_layout(title="Expected churn by support contacts (90 days)", yaxis_tickformat=".0%", yaxis_title=None)
        fig.update_xaxes(title="Contacts in the last 90 days")
        chart(fig)
        st.caption("Support counts are rows in support_interactions. They are not a model score we invented.")
    with right:
        deciles = pd.DataFrame(stats["deciles"])
        fig = go.Figure(
            go.Bar(
                x=deciles["decile"].astype(str),
                y=deciles["share_of_expected_churners"],
                marker_color="#1A1220",
                hovertemplate="Risk decile %{x}<br>Share of expected churners %{y:.1%}<extra></extra>",
            )
        )
        fig.update_layout(
            title="Where expected churners sit (1 = lowest risk)",
            yaxis_tickformat=".0%",
        )
        chart(fig)
        st.caption(
            f"The riskiest 10% average {stats['concentration']['top_10']['mean_risk']:.0%} "
            f"and hold {stats['concentration']['top_10']['share_of_expected_churners']:.0%} of expected churners."
        )

    drivers = pd.DataFrame(
        [
            {"driver": "Competitor research 0.75+", **stats["competitor_high"]},
            {"driver": "Competitor research 0", **stats["competitor_zero"]},
            {"driver": "Bill up more than 5%", **stats["bill_up"]},
            {"driver": "Bill within 5%", **stats["bill_flat"]},
            {"driver": "Port-out inquiry", **stats["port_yes"]},
            {"driver": "No port-out inquiry", **stats["port_no"]},
            {"driver": "Tenure under 12 months", **stats["tenure_short"]},
            {"driver": "Tenure 36+ months", **stats["tenure_long"]},
            {"driver": "Autopay off", **stats["autopay_off"]},
            {"driver": "Autopay on", **stats["autopay_on"]},
            {"driver": "Home Internet", **stats["home_internet"]},
            {"driver": "No Home Internet", **stats["no_home_internet"]},
        ]
    )
    fig = go.Figure(
        go.Bar(
            y=drivers["driver"],
            x=drivers["expected_churn"],
            orientation="h",
            marker_color=["#E20074" if i % 2 == 0 else "#8A7B84" for i in range(len(drivers))],
            customdata=drivers["n"],
            hovertemplate="%{y}<br>%{x:.1%} expected churn<br>n=%{customdata}<extra></extra>",
        )
    )
    fig.update_layout(title="Other slices of the same sandbox score", xaxis_tickformat=".0%")
    chart(fig, height=560)
    st.caption(
        "Autopay, Home Internet, and segment barely separate this book. "
        "The gap that matters is friction: support, shopping around, a bill jump, a port-out inquiry."
    )
    segment_frame = pd.DataFrame(stats["segments"])
    segment_frame["expected_churn"] = segment_frame["expected_churn"].map(lambda value: f"{value:.1%}")
    st.dataframe(segment_frame, hide_index=True, width="stretch")
    k1, k2, k3 = st.columns(3)
    k1.metric("Cancellation inquiry, ever", f"{stats['cancellation_accounts']:,} accounts")
    k2.metric("Promo expired, last 3 billing months", f"{stats['promo_expired_recent']:,}")
    k3.metric("Installment ended, last 3 billing months", f"{stats['installment_ended_recent']:,}")
    st.caption(
        f"Catalog has {len(console.promos)} promotions. "
        f"{len(console.retention_promos)} are retention offers (source = stub): "
        + ", ".join(promo["name"] for promo in console.retention_promos)
        + ". Money in the database is cents. Financing is 24 months. Data as of "
        + f"{console.as_of}."
    )


def _position_from_state(state) -> int | None:
    """Row index from a dataframe selection. A cell click counts; the grid highlights those without a checkbox."""
    if state is None:
        return None
    rows = selected_rows(state)
    if rows:
        return int(rows[0])
    selection = getattr(state, "selection", None)
    if selection is None and isinstance(state, dict):
        selection = state.get("selection")
    cells = getattr(selection, "cells", None) if selection is not None else None
    if cells is None and isinstance(selection, dict):
        cells = selection.get("cells")
    if not cells:
        return None
    cell = cells[0]
    return int(cell[0])


def _open_click_position() -> int | None:
    click = st.session_state.get("queue_open_click")
    if not click:
        return None
    row = click["row"] if isinstance(click, dict) else getattr(click, "row", None)
    if row is None:
        return None
    return int(row)


def _table_account(show: pd.DataFrame) -> tuple[str | None, int | None]:
    """Account for the queue row the user just opened or selected."""
    position = _open_click_position()
    if position is None:
        position = _position_from_state(st.session_state.get("risk_queue"))
    if position is None or position < 0 or position >= len(show):
        return None, None
    return str(show.iloc[position]["account_id"]), position


def queue(console) -> None:
    c1, c2 = st.columns([2, 1])
    with c1:
        query = st.text_input("Filter by account id or persona title", "")
    with c2:
        personas_only = st.checkbox("Persona accounts only", value=False)
    frame = console.queue(personas_only=personas_only)
    if query.strip():
        needle = query.strip().lower()
        title = frame["title"].fillna("").str.lower()
        frame = frame.loc[frame["account_id"].str.lower().str.contains(needle) | title.str.contains(needle)]
    show = frame[
        ["rank", "account_id", "segment", "model_p", "sandbox_p", "support_90d", "action_name", "upgrade_when", "top_leave"]
    ].reset_index(drop=True)
    table_account, table_row = _table_account(show)
    applied = st.session_state.get("queue_applied_row")
    if table_account and table_row != applied:
        st.session_state.queue_applied_row = table_row
        st.session_state.account_id = table_account
        st.session_state.queue_account_pick = table_account
    account_id = ensure_selection(console)
    visible = show["account_id"].tolist()
    if account_id not in visible and visible:
        account_id = visible[0]
        st.session_state.account_id = account_id
    if "queue_account_pick" not in st.session_state or st.session_state.queue_account_pick not in visible:
        st.session_state.queue_account_pick = account_id
    account_id = st.selectbox("Show this account", visible, key="queue_account_pick")
    st.session_state.account_id = account_id
    display = show.copy()
    display["model_p"] = display["model_p"].map(lambda value: f"{value:.1%}")
    display["sandbox_p"] = display["sandbox_p"].map(lambda value: f"{value:.1%}")
    display.insert(0, "open", "Open")
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode=["single-row", "single-cell"],
        key="risk_queue",
        height=420,
        column_config={
            "open": st.column_config.ButtonColumn(
                "Open",
                help="Show this account's reasons",
                width="small",
                pinned=True,
                type="primary",
                key="queue_open_click",
            ),
        },
    )
    st.caption("Click Open on a row, or use the account menu. The reasons below follow that account.")
    detail = console.account(account_id)
    st.subheader(account_id)
    if detail.get("title"):
        st.caption(detail["title"])
    m1, m2, m3 = st.columns(3)
    m1.metric("Model A risk", f"{detail['model_p']:.1%}")
    m2.metric("Sandbox score", f"{detail['sandbox_p']:.1%}")
    m3.metric("Support contacts, 90 days", int(detail["support_90d"]))
    left, right = st.columns(2)
    with left:
        st.markdown("**Reasons to leave**")
        for reason in detail["leave"]:
            st.write("· " + reason)
    with right:
        st.markdown("**Reasons to stay**")
        for reason in detail["stay"]:
            st.write("· " + reason)
    contrib = pd.DataFrame(detail["contributions"])
    fig = go.Figure(
        go.Bar(
            y=contrib["label"],
            x=contrib["contribution"],
            orientation="h",
            marker_color=[COLORS["risk"] if value > 0 else COLORS["good"] for value in contrib["contribution"]],
        )
    )
    fig.update_layout(title="Model A contribution (coefficient × standardized value)")
    chart(fig, height=480)


def _delivery() -> tuple[str | None, str | None]:
    """Sidebar choice from the demo. Unset means the env-var backend."""
    if "send_backend" not in st.session_state:
        return None, None
    topic = str(st.session_state.get("send_topic") or "").strip()
    return str(st.session_state.get("send_backend") or "dryrun"), topic


def _subscribe_line() -> str:
    _backend, topic = _delivery()
    shown = topic or "tm-dubhacks26-lf3reo19tv"
    return f"Install the ntfy app and subscribe to {shown}."


def text_we_would_send(
    english: str,
    spanish: str,
    why: str,
    account_id: str,
    key: str,
    hindi: str = "",
    chinese: str = "",
) -> None:
    """One language at a time. Send posts only the language selected in the radio."""
    st.subheader("Text message we'd send")
    texts = {
        "en": clean_draft(english),
        "es": clean_draft(spanish),
        "hi": clean_draft(hindi),
        "zh": clean_draft(chinese),
    }
    if not any(texts.values()):
        st.write(f"No message sent, here's why: {why}")
        return
    labels = [name for _code, name in LANGUAGES]
    choice = st.radio("Language", labels, horizontal=True, key=f"{key}_lang")
    body = selected_draft(texts, choice)
    st.markdown(
        "<div class='phone'><div class='phone-bar'></div>"
        f"<div class='quiet'>{html.escape(choice)}</div>"
        f"<div class='bubble'>{bubble_html(body) if body else '—'}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    _send_to_my_phone({"why": why}, {"text": body}, account_id, key=key)


def _send_to_my_phone(action: dict, message: dict, account_id: str | None = None, key: str | None = None) -> None:
    if not message.get("text"):
        st.write(f"No message sent, here's why: {action['why']}")
        return
    backend, topic = _delivery()
    st.caption(_subscribe_line())
    button_key = key or f"send_{account_id or 'next'}"
    if st.button("Send to my phone", key=button_key):
        live = will_send(backend, topic) if backend is not None else will_send()
        if account_id and live and not frequency_open(account_id):
            st.toast(f"Frequency cap: one nudge per {FREQUENCY_CAP_DAYS} days. Nothing sent.")
            return
        if backend is None:
            result = send(message["text"])
        else:
            result = send(message["text"], backend=backend, topic=topic)
        if result.get("hint"):
            st.caption(result["hint"])
        if result.get("sent") and account_id:
            record_send(account_id)
        if result.get("backend") == "dryrun" or not result.get("sent"):
            if result.get("ok"):
                st.toast("Preview only. Nothing was sent.")
                st.info(result.get("message") or "")
            else:
                st.toast(result.get("detail") or "Send failed.")
        else:
            st.toast("Sent to your phone." if result.get("ok") else result.get("detail") or "Send failed.")


def action_page(console) -> None:
    options = PINNED + sorted(set(console.details) - set(PINNED))
    current = ensure_selection(console)
    choice = st.selectbox(
        "Customer",
        options,
        index=options.index(current) if current in options else 0,
        format_func=lambda account_id: _label(console, account_id),
    )
    st.session_state.account_id = choice
    detail = console.account(choice)
    action = detail["action"]
    moment = detail["moment"]
    message = detail["message"]
    drafted = {
        language: draft({**detail, "language": language}, action, moment).get("text") or ""
        for language in ("en", "es", "hi", "zh")
    }
    text_we_would_send(
        drafted["en"],
        drafted["es"],
        action["why"],
        choice,
        f"send_action_{choice}",
        hindi=drafted["hi"],
        chinese=drafted["zh"],
    )

    left, right = st.columns([1.15, 0.85])
    with left:
        st.subheader(outbound_title(action, moment, detail))
        st.write(show(action["why"]))
        st.caption(show(action["formula"]))
        considered = pd.DataFrame(action["considered"])
        if not considered.empty:
            view = considered.copy()
            view["cost"] = view["cost_cents"].map(dollars)
            view["score"] = view["net_cents"].map(dollars)
            st.markdown("**Offers considered**")
            st.dataframe(
                view[["name", "eligible", "cost", "score", "fit_reason", "reasons"]],
                hide_index=True,
                width="stretch",
            )
        st.markdown("**Upgrade moment**")
        if moment is None:
            st.write("No paid-off phone, no usage over the plan cap, and no phone 36 months or older.")
        else:
            st.write(show(moment["headline"]))
            st.caption(show(moment.get("assumption", "")))
            st.write(show(moment.get("battery_note", "")))
            st.caption(show(moment.get("condition_note", "")))
            triggers = ", ".join(moment["triggers"])
            st.write(f"Triggers: {triggers}.")
            if moment.get("usage_3m_gb") is not None and moment.get("data_cap_gb"):
                st.write(
                    f"Recent usage {float(moment['usage_3m_gb']):.1f} GB versus a {int(moment['data_cap_gb'])} GB cap."
                )
            promo = moment.get("promo")
            if promo:
                st.write(
                    show(
                        f"One device promo: {promo['name']} ({dollars(promo['savings_cents'])}) "
                        f"on {promo['device_name']}. A second device promo is not applied."
                    )
                )
                st.write(
                    show(
                        f"Good-condition trade-in {dollars(moment.get('tradein_value_cents'))}. "
                        f"Balance charged today {dollars(moment.get('balance_cents'))}. "
                        f"Net after we subtract the promo {dollars(moment.get('net_cents'))}. "
                        "Net subtracts the promo."
                    )
                )
            elif moment.get("when") == "now":
                st.write("No device promotion is eligible on a single trade-in plus one new phone.")
    with right:
        customer_card(detail, message)


def _label(console, account_id: str) -> str:
    detail = console.account(account_id)
    title = detail.get("title") or detail["segment"]
    return f"{account_id} · {title} · {detail['model_p']:.0%}"


def customer_card(detail: dict, message: dict) -> None:
    st.markdown("**Customer card**")
    st.write(
        f"{detail['segment']} · {detail['tenure_months']} months · {detail['credit_tier']} · "
        f"prefers {detail['contact_preference']} · language {detail['language']}"
    )
    st.write(
        show(
            f"Latest bill {dollars(detail['last_bill_cents'])}. "
            f"Bill vs prior average {detail['bill_increase_pct'] * 100:.0f}%. "
            f"Autopay {'on' if detail['autopay'] else 'off'}."
        )
    )
    if detail.get("top_topic"):
        st.write(
            f"Most common support topic in 90 days: {detail['top_topic']} ({detail['top_topic_n']}). "
            f"Average sentiment {detail['avg_sentiment']:.2f}."
        )
    if detail.get("scenario"):
        st.caption(detail["scenario"])
    lines = pd.DataFrame(detail["lines"])
    if not lines.empty:
        line_table = lines[["member_label", "device_name", "age_months", "financing_balance_cents", "plan_name", "usage_3m_gb"]].copy()
        line_table["balance"] = line_table["financing_balance_cents"].map(dollars)
        st.dataframe(
            line_table[["member_label", "device_name", "age_months", "balance", "plan_name", "usage_3m_gb"]],
            hide_index=True,
            width="stretch",
        )


def projections(console) -> None:
    st.subheader("Projected, illustrative assumptions")
    st.write(
        "Projected, illustrative assumptions. The curves below are arithmetic on today's scores. "
        "They are not measured offer responses, not a before/after test, and not a retrained model."
    )
    population = console.frame.loc[console.frame["is_persona"] == 0]
    a, c = st.columns(2)
    save_rate = a.slider(
        "Save rate: share of contacted at-risk customers we keep",
        0.0,
        0.30,
        DEFAULT_SAVE_RATE,
        0.005,
        format="%.3f",
        help="Measured retention campaigns land around 2% to 11%. 10% is the rate the Devpost uses.",
    )
    upgrade_rate = c.slider("Upgrade acceptance among upgrade-now accounts", 0.0, 1.0, 0.2, 0.05)
    outcome = project(population, save_rate, 1.0, upgrade_rate)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sandbox reference score, 90-day churn", f"{outcome['baseline_rate']:.1%}")
    m2.metric("Projected, at this save rate", f"{outcome['projected_rate']:.1%}")
    m3.metric("Expected customers kept", f"{outcome['expected_saves']:.0f}")
    m4.metric("Projected upgrades", f"{outcome['projected_upgrades']:.0f}")
    if save_rate >= BREAK_EVEN_SAVE_RATE:
        st.success(
            f"{save_rate:.1%} is above the ~{BREAK_EVEN_SAVE_RATE:.1%} break-even, so retention messages pay for themselves (simulated)."
        )
    else:
        st.warning(
            f"{save_rate:.1%} is below the ~{BREAK_EVEN_SAVE_RATE:.1%} break-even. At this rate, sending costs more than it saves, "
            "so the right call is to send less and do nothing more often (simulated)."
        )
    st.caption(
        "The baseline is the sandbox reference score (the judges' toy score), not our calibrated model. "
        "Who gets contacted stays fixed; the sliders only change the arithmetic. "
        f"Offers in that fixed list: {outcome['targeted_offers']:,}. "
        f"Upgrade-now accounts in the 5,000: {outcome['upgrade_now_accounts']:,}."
    )
    curve = acceptance_curve(population, 1.0, points=31)
    curve = curve.assign(save_rate=curve["acceptance"] * 0.30 / 0.8)
    curve["projected_churn_rate"] = [
        project(population, rate, 1.0, 0.0)["projected_rate"] for rate in curve["save_rate"]
    ]
    fig = go.Figure()
    fig.add_vrect(
        x0=0.02,
        x1=0.11,
        fillcolor="#E4D9CF",
        opacity=0.5,
        line_width=0,
        annotation_text="Measured campaigns, 2-11%",
        annotation_position="top left",
    )
    fig.add_trace(
        go.Scatter(
            x=curve["save_rate"],
            y=curve["projected_churn_rate"],
            mode="lines",
            name="Projected churn",
            line=dict(color=COLORS["magenta"], width=3),
        )
    )
    fig.add_hline(
        y=outcome["baseline_rate"],
        line_dash="dot",
        line_color="#1A1220",
        annotation_text="Sandbox reference score",
        annotation_position="top right",
    )
    fig.add_vline(
        x=BREAK_EVEN_SAVE_RATE,
        line_dash="dash",
        line_color="#1F7A4D",
        line_width=2,
        annotation_text=f"Break-even ~{BREAK_EVEN_SAVE_RATE:.1%}",
        annotation_position="bottom right",
    )
    fig.add_vline(x=save_rate, line_dash="dot", line_color="#8A7B84")
    fig.update_xaxes(range=[0, 0.30], tickformat=".0%", title="Save rate")
    fig.update_yaxes(tickformat=".1%", title="Expected 90-day churn")
    fig.update_layout(title="Projected churn by save rate (illustrative)", showlegend=False)
    chart(fig)
    lifts = upgrade_curve(population)
    fig = go.Figure(
        go.Scatter(
            x=lifts["upgrade_acceptance"],
            y=lifts["projected_upgrades"],
            mode="lines",
            line=dict(color="#1A1220", width=3),
        )
    )
    fig.add_vline(x=upgrade_rate, line_dash="dot", line_color=COLORS["magenta"])
    fig.update_xaxes(range=[-0.02, 1.02], tickformat=".0%", title="Upgrade acceptance")
    fig.update_yaxes(title="Projected upgrades")
    fig.update_layout(title="Projected upgrades (illustrative)")
    chart(fig)
    st.markdown(
        f"""
        **Assumptions on this screen**
        - Save rate is the share of contacted at-risk customers who stay because we reached out. Default 10%, the rate in our Devpost. Real retention campaigns have measured about 2% to 11%.
        - Break-even (~{BREAK_EVEN_SAVE_RATE:.1%}) is where our engine's retention messages stop paying for their credits and contact cost (simulated, from the strategy comparison). Below it, sending less is the honest answer.
        - Upgrade acceptance applies only to accounts whose detector says upgrade now (paid off, over the cap, or an old phone, and the timing rule says now).
        - None of this is measured. A holdout test with real customers is the next step.
        """
    )


def _playbook_message(decision: dict, credit_cents: int, language: str) -> str:
    text = decision["message_en"] if language != "es" else decision["message_es"]
    if decision.get("offer_is_assumption"):
        text = text.replace(f"{decision['offer_cents']} cents", f"{int(credit_cents)} cents")
    return text


def targeting_page(console) -> None:
    playbook = get_playbook()
    st.subheader("Targeting playbook")
    st.caption(VALUE_FORMULA)
    st.caption(
        f"Product setting: at most one outbound nudge per customer per {FREQUENCY_CAP_DAYS} days. "
        "This screen does not show projected churn or dollar outcomes."
    )
    credit = st.number_input(
        "Assumption credit (cents). Not a T-Mobile price.",
        min_value=0,
        max_value=100_000,
        value=ASSUMPTION_CREDIT_CENTS,
        step=500,
    )
    priority = playbook.grid.loc[playbook.grid["priority"]].iloc[0]
    st.markdown(
        f"**Priority cell: {priority['risk_label']} × {priority['value_label']}.** "
        f"{int(priority['accounts']):,} accounts, "
        f"{priority['expected_churners']:.0f} expected churners from the sandbox score."
    )
    heat = playbook.grid.pivot(index="risk_label", columns="value_label", values="accounts")
    heat = heat.reindex(index=["Top 10% risk", "10–30% risk", "Rest"])
    fig = go.Figure(
        go.Heatmap(
            z=heat.values,
            x=list(heat.columns),
            y=list(heat.index),
            colorscale=[[0, "#F7F1EA"], [1, "#E20074"]],
            text=heat.values,
            texttemplate="%{text}",
            hovertemplate="%{y} × %{x}<br>%{z} accounts<extra></extra>",
        )
    )
    fig.update_layout(title="Accounts by risk band and value")
    chart(fig, height=320)
    counts = playbook.grid.copy()
    counts["expected_churners"] = counts["expected_churners"].map(lambda value: f"{value:.1f}")
    st.dataframe(
        counts[["risk_label", "value_label", "accounts", "expected_churners", "priority"]],
        hide_index=True,
        width="stretch",
    )
    st.markdown("**Rules, first match wins**")
    st.dataframe(pd.DataFrame(RULES)[["when", "action", "offer", "channel"]], hide_index=True, width="stretch")

    ranked = playbook.ranked()
    st.markdown("**Ranked targets**")
    st.caption("Rank score is Model A risk times the value score. It is not a projected save.")
    show = ranked.head(200).copy()
    show["model_p"] = show["model_p"].map(lambda value: f"{value:.1%}")
    show["value_score_cents"] = show["value_score_cents"].map(lambda value: f"{value:,.0f}¢")
    show["rank_score"] = show["rank_score"].map(lambda value: f"{value:,.0f}")
    st.dataframe(
        show[
            [
                "account_id",
                "risk_band",
                "value_band",
                "trigger",
                "action",
                "offer",
                "reason_1",
                "reason_1_source",
                "rejected_next",
            ]
        ],
        hide_index=True,
        width="stretch",
        height=360,
    )
    st.download_button(
        "Download the full target list (CSV)",
        ranked.to_csv(index=False).encode("utf-8"),
        file_name="targeting_playbook.csv",
        mime="text/csv",
    )

    options = [row.account_id for row in ranked.itertuples()]
    choice = st.selectbox("One customer", options, index=0)
    decision = playbook.decision(choice)
    st.markdown(f"**{choice}** · {decision['action']}")
    st.write(decision["why"])
    row = playbook.frame.set_index("account_id").loc[choice]
    columns = st.columns(2)
    columns[0].metric("Segment", f"{row['risk_band']} / {row['value_band']}")
    columns[1].metric("Channel", decision["channel"])
    st.write(f"Trigger: {decision['trigger']}")
    st.write(f"Rule: {decision['rule_id']}")
    offer_cents = int(credit) if decision.get("offer_is_assumption") else decision.get("offer_cents")
    offer_text = decision["offer_name"]
    if offer_cents is not None:
        offer_text += f" · {dollars(int(offer_cents))}"
        if decision.get("offer_is_assumption"):
            offer_text += " (assumption, not a T-Mobile price)"
    st.write(f"Offer: {offer_text}")
    if decision.get("assumption_note"):
        st.caption(decision["assumption_note"])
    st.write(f"Why the next action was rejected: {decision['rejected']}")
    st.markdown("**Top reasons**")
    for reason in decision["reasons"]:
        if reason["text"]:
            st.write(f"· {reason['text']} ({reason['source']})")
    english = _playbook_message(decision, int(credit), "en")
    spanish = _playbook_message(decision, int(credit), "es")
    st.markdown("**Draft**")
    st.markdown(
        "<div class='phone'><div class='phone-bar'></div>"
        f"<div class='quiet'>English</div><div class='bubble'>{bubble_html(english)}</div>"
        f"<div class='quiet'>Español</div><div class='bubble'>{bubble_html(spanish)}</div>"
        "<div class='quiet'>On-screen mockup. Nothing is sent from this phone.</div></div>",
        unsafe_allow_html=True,
    )


def upgrades_page(console) -> None:
    from harness.upsell.build import display_frame

    upsell = get_upsell()
    st.subheader("Upgrades & life moments")
    st.caption("Real data only is the default. Tier 2 is a seeded consented signal, and it stays off this screen until the toggle is on.")
    include = st.toggle("With synthetic life-event signals", value=INCLUDE_SYNTHETIC_DEFAULT)
    if include:
        st.markdown(f"**{SYNTHETIC_BADGE}**")
        st.caption(f"Seeded accounts: {upsell.seeded_accounts:,}. Counts only. An earlier real trigger or a guardrail still wins.")
    else:
        st.caption("Real data only.")
    counts = upsell.counts(include)
    st.markdown("**Counts per trigger**")
    st.dataframe(counts, hide_index=True, width="stretch")
    ranked = upsell.ranked(include)
    shown = display_frame(ranked).head(200).copy()
    if "monthly_difference" in shown.columns:
        shown["monthly_difference"] = shown["monthly_difference"].map(
            lambda value: "n/a" if value is None or (isinstance(value, float) and pd.isna(value)) else dollars(int(value))
        )
    st.markdown("**Ranked targets**")
    st.caption("Order is satisfaction, affordability, and the signal, with the upgrade-propensity score when that file is already built. This list is not a projected save.")
    st.dataframe(
        shown,
        hide_index=True,
        width="stretch",
        height=360,
        column_config={
            "rejected": st.column_config.TextColumn(
                "rejected",
                width=420,
                help="Why the runner-up was rejected",
            ),
        },
    )
    export = display_frame(ranked)
    st.download_button(
        "Download the target list (CSV)",
        export.to_csv(index=False).encode("utf-8"),
        file_name="upgrades_life_moments.csv",
        mime="text/csv",
    )
    choice = st.selectbox("One customer", list(ranked["account_id"]), index=0, key="upsell_account")
    decision = upsell.decision(choice, include)
    if decision["send"]:
        text_we_would_send(
            decision["message_en"],
            decision["message_es"],
            decision["why"],
            choice,
            f"send_grow_{choice}",
            hindi=decision.get("message_hi") or "",
            chinese=decision.get("message_zh") or "",
        )
    else:
        st.subheader("Text message we'd send")
        st.write(f"No message sent, here's why: {decision['why']}")
    st.markdown(f"**{choice}** · {decision['action']}")
    if decision["badge"]:
        st.markdown(f"**{decision['badge']}**")
    st.write(decision["why"])
    diff = decision["diff_cents"]
    st.write(f"Trigger: {decision['trigger']}")
    st.write(f"Monthly difference: {'n/a' if diff is None else dollars(int(diff))}")
    offer = decision["offer_name"]
    if decision.get("promo_savings_cents"):
        offer += f" · promo savings {dollars(int(decision['promo_savings_cents']))} subtracted by us"
    st.write(f"Offer: {offer}")
    st.write(f"Data source: {decision['data_source']}")
    st.write(f"Why the runner-up was rejected: {decision['rejected']}")
    if decision.get("assumption_note"):
        st.caption(decision["assumption_note"])


def main() -> None:
    st.set_page_config(page_title="Retention Console", layout="wide")
    apply_css()
    banner()
    try:
        console = get_console()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()
    st.title("Retention Console")
    st.caption("DubHacks '26 · T-Mobile track")
    page = st.sidebar.radio(
        "Screen",
        ["Overview", "At-risk queue", "Next best action", "Targeting playbook", "Upgrades & life moments", "Projections"],
    )
    st.sidebar.caption("Synthetic sandbox data. Money is cents until it is shown as dollars.")
    if page == "Overview":
        overview(console)
    elif page == "At-risk queue":
        queue(console)
    elif page == "Next best action":
        action_page(console)
    elif page == "Targeting playbook":
        targeting_page(console)
    elif page == "Upgrades & life moments":
        upgrades_page(console)
    else:
        projections(console)


if __name__ == "__main__":
    main()
