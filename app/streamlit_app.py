"""T-Mobile churn + upsell: lean demo app (tm-ui lane). ALL CUSTOMERS AND NUMBERS ARE SYNTHETIC.

Run:  streamlit run app/streamlit_app.py
Tabs: Pipeline (embeds app/viz/pipeline_flow.html) · Four customers · Browse.
Data: harness/out/ -> demo_data/ -> app/mock/ (mock is flagged with a banner). See app/data.py.
One churn number everywhere: churn_scores.csv p_churn_90d (Model A).
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

APP = Path(__file__).resolve().parent
REPO = APP.parent
sys.path.insert(0, str(APP))
from data import clean_stays, is_mock, load_all, merged, persona_titles  # noqa: E402
from messages import action_label, normalize_action  # noqa: E402

MAGENTA = "#E20074"
# Dashboard: show app/charts/06_upgrade_or_wait.png only once tm-strategy signs off on its post-8:50 figures.
SHOW_UPGRADE_WAIT = False
GITHUB_VIZ = "https://github.com/DavidJ-1/TM-Dubhacks26/blob/dev/app/viz/pipeline_flow.html"
st.set_page_config(page_title="T-Mobile Next Best Moment (synthetic)", page_icon="📱", layout="wide")
st.markdown(f"""
<style>
.block-container {{padding-top: 2rem; max-width: 1450px}}
.why {{font-size:1.45rem; line-height:1.35; font-weight:600; color:#1F2328; border-left:5px solid {MAGENTA};
  padding:.2rem 0 .2rem .8rem; margin:.3rem 0 .8rem}}
.kicker {{color:{MAGENTA}; font-weight:700; letter-spacing:.05em; text-transform:uppercase; font-size:.78rem}}
.chip {{display:inline-block; border-radius:12px; padding:2px 10px; margin:2px 4px 2px 0; font-size:.82rem}}
.risk {{background:#FDECF4; color:#9B0050}} .stay {{background:#EAF6EE; color:#1B5E20}}
.phone {{width:280px; margin:auto; border:1px solid #D0D7DE; border-radius:28px; background:#FFFFFF;
  min-height:400px; padding:22px 14px 16px; box-shadow:0 4px 16px rgba(31,35,40,.10)}}
.sender {{text-align:center; font-size:.74rem; color:#57606A; margin-bottom:12px; border-bottom:1px solid #EEF0F2; padding-bottom:8px}}
.bubble {{background:#F1F3F5; color:#1F2328; border-radius:16px; padding:10px 13px; font-size:.88rem; line-height:1.35}}
.nomsg {{text-align:center; color:#6E7781; margin-top:120px; font-size:.95rem}}
.whatif {{border:1px solid #F3B6D2; border-radius:10px; padding:8px 12px; background:#FFF5FA; font-size:.92rem}}
.how {{background:#F6F7F9; border-radius:10px; padding:.6rem 1rem; font-size:.95rem; color:#1F2328}}
.how b {{color:{MAGENTA}}}
</style>
""", unsafe_allow_html=True)
st.info("**All customers are synthetic:** T-Mobile judge sandbox data with simulated scores. Not real customers.", icon="⚠️")

data = load_all()
MOCK = is_mock(data)
if MOCK:
    bad = ", ".join(f"{k}.csv" for k in ("churn_scores", "offers", "features", "labels") if data[k].source != "real")
    st.error(f"🧪 MOCK DATA: {bad} not found in harness/out/ or demo_data/, so this app shows the 48-account "
             "placeholder mock, not the real 5,000-account run.")
PERSONAS = persona_titles()
df = merged(data)
if "action_code" in df:
    df["action_key"] = df["action_code"].fillna(df.get("action")).map(normalize_action)
elif "action" in df:
    df["action_key"] = df["action"].map(normalize_action)
NONP = df[~df.account_id.astype(str).str.startswith("ACC-PERSONA")]


def fmt_prob(p) -> str:
    """One format everywhere: 19.7% / 5.4% / 0.32%."""
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "n/a"
    if p >= 0.01:
        return f"{p:.1%}"
    return f"{p * 100:.2f}%" if p >= 0.0001 else "<0.01%"


def money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    return "—" if pd.isna(v) else f"${v:,.0f}"


with st.sidebar:
    st.markdown("### 📱 Next Best Moment")
    st.caption("Data sources (from the loader, synthetic)")
    for n in ("churn_scores", "offers", "features", "labels", "offer_candidates"):
        l = data[n]
        icon = {"real": "🟢 real", "mock": "🟡 mock", "missing": "⚪ missing"}[l.source]
        where = Path(l.path).parent.name if l.path else ""
        st.caption(f"**{n}**: {icon}" + (f" ({where}/)" if where else ""))


tab1, tabj, tab2, tab3 = st.tabs(["Dashboard", "Customer journey", "Four customers", "Pipeline visual"])

# ---------------- Customer journey (HTML built by another worker; embedded as-is) ----------------
with tabj:
    _journey = REPO / "app" / "viz" / "customer_journey.html"
    if _journey.exists():
        components.html(_journey.read_text(encoding="utf-8", errors="replace"), height=820, scrolling=False)
        st.caption("All customers are synthetic.")
    else:
        st.info("Journey view loading…")

# ---------------- TAB 2: Four customers ----------------
CARDS = [  # account, story we intend, action codes that fit the story (demo script v2 order)
    ("ACC-PERSONA-38", "Save them money", {"variant_switch", "right_size", "right_size_plan"}),
    ("ACC-PERSONA-04", "Fix it first", {"care_credit_fix_first", "fix_first", "fix_first_callback"}),
    ("ACC-PERSONA-21", "A check-in, not a discount", {"check_in"}),
    ("ACC-PERSONA-24", "Restraint: do nothing", {"do_nothing"}),
]
TOGGLES = [  # key, label, relevant-if, edits applied to features.csv / engine row
    # Toggles start ON (the fact as it is in the data); switching one OFF removes that fact and re-decides.
    ("tickets", "Open support tickets", lambda r: float(r.get("unresolved_90d", 0) or 0) > 0
     or float(r.get("negative_contacts_90d", 0) or 0) > 0,
     {"unresolved_90d": 0, "unresolved_270d": 0, "negative_contacts_90d": 0, "network_contacts_90d": 0}),
    ("port", "Port-out inquiry", lambda r: float(r.get("port_out_inquiry", 0) or 0) > 0, {"port_out_inquiry": 0}),
    ("comp", "Comparing carriers", lambda r: float(r.get("competitor_research_score", 0) or 0) >= 0.3,
     {"competitor_research_score": 0.0}),
]


def phone(msg: str | None, lang: str) -> str:
    if msg:
        inner = f"<div class='bubble'>{html.escape(msg)}</div>"
    else:
        inner = ("<div class='nomsg'>🤫<br><b>" + ("No se envía mensaje" if lang == "es" else "No message sent")
                 + "</b><br>" + ("Decidimos esperar." if lang == "es" else "We decided to wait.") + "</div>")
    return f"<div class='phone'><div class='sender'>T-Mobile · Text Message</div>{inner}</div>"


def _monthly_from_text(t: str) -> str:
    t = str(t or "")
    m = re.search(r"saves? \$(\d+(?:\.\d+)?)/mo", t)
    if m:
        return f"saves ${float(m.group(1)):,.0f}/mo"
    m = re.search(r"\$(\d+(?:\.\d+)?)/mo(?:nth)? more", t)
    if m:
        return f"pays ${float(m.group(1)):,.0f}/mo more"
    return "—"


def options_table(acc: str, cands: pd.DataFrame | None = None, msg_en: str | None = None) -> tuple[pd.DataFrame, str]:
    oc = data["offer_candidates"].df if cands is None else cands
    c = oc[oc.account_id == acc].copy() if len(oc) else oc
    if not len(c):
        return pd.DataFrame(), ""
    chosen_col = "is_winner" if "is_winner" in c else "is_chosen"
    c["_chosen"] = c[chosen_col].astype(str).str.lower().isin(("true", "1"))
    c["_elig"] = c["eligible"].astype(str).str.lower().isin(("true", "1"))
    elig, inel = c[c._elig], c[~c._elig]
    c = pd.concat([elig.sort_values("rank"), inel.head(max(0, 6 - len(elig)))])
    rows, tips = [], []
    msg_prices = None
    om = df[df.account_id == acc]
    if msg_en is None and len(om) and isinstance(om.iloc[0].get("message_en"), str):
        msg_en = om.iloc[0]["message_en"]
    if isinstance(msg_en, str):
        m = re.search(r"\$(\d+(?:\.\d+)?)/month instead of \$(\d+(?:\.\d+)?)", msg_en)
        if m:
            msg_prices = (float(m.group(1)), float(m.group(2)))
    for _, r in c.iterrows():
        code = r["action_code"]
        name = action_label(code) if normalize_action(code) in _KNOWN else str(r.get("action", code))
        cost = r["cost_to_tmobile"] if "cost_to_tmobile" in c else r.get("offer_cost")
        if "customer_monthly_delta" in c and pd.notna(r.get("customer_monthly_delta")):
            d = float(r["customer_monthly_delta"])
            cust = "no change" if d == 0 else (f"saves ${-d:,.0f}/mo" if d < 0 else f"pays ${d:,.0f}/mo more")
        else:  # plain plan-price change (never the model's customer_benefit estimate)
            cust = "no change" if code == "do_nothing" else _monthly_from_text(r.get("reason"))
            if r._chosen and msg_prices:
                new, old = msg_prices
                txt = f"saves ${old - new:,.0f}/mo (${old:,.0f} → ${new:,.0f})" if old > new else f"pays ${new - old:,.0f}/mo more"
                if cust not in ("—", txt.split(" (")[0]):
                    txt += " ⚠ text/engine differ"
                cust = txt
        if r._chosen:
            why = "✅ Our pick"
        elif "why_not_chosen" in c and isinstance(r.get("why_not_chosen"), str) and r["why_not_chosen"]:
            why = r["why_not_chosen"]
        elif not r._elig:
            why = "Not eligible: " + str(r.get("blocked_or_ineligible_reason") or "rule not met")
        elif code == "do_nothing":
            why = "We'd stay silent, but a contact helps here"
        elif "below zero" in str(r.get("reason", "")):
            why = "Costs more than it's likely to save"
        else:
            why = "Less value for the customer and for us than our pick"
        rows.append({"Option": name, "Cost to T-Mobile": money(cost) if r._elig else "—",
                     "Customer": cust if r._elig else "—", "Why not": why})
        evv = r["ev"] if "ev" in c else r.get("expected_value")
        if r._elig and pd.notna(evv):
            tips.append(f"{name}: expected value {money(evv)}")
    return pd.DataFrame(rows), "Expected value per option (synthetic, internal only): " + "; ".join(tips)


_KNOWN = set(__import__("messages").ACTION_LABELS)


@st.cache_resource(show_spinner="Loading the offer engine (one time, ~6 s)…")
def engine():
    """tm-offers' engine frame for the demo accounts, built exactly as harness/offers.py main() does (synthetic)."""
    import numpy as np
    for p in (str(REPO), str(REPO / "harness")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import offer_detectors as det
    import offers as O
    conn = det.connect_ro()
    cat = det.load_catalog(conn)
    facts = det.build_account_facts(conn)
    facts, _ = det.apply_features_csv(facts, O.OUT_DIR / "features.csv")
    facts, _ = det.apply_enrichment(facts, O.OUT_DIR / "enrichment.csv")
    churn, _src = O.load_churn_scores(facts)
    d = facts.merge(churn, on="account_id", how="left")
    d = d[d.account_id.isin([a for a, _s, _c in CARDS])].copy()
    plans = cat["plans"]
    d["all_low_use_premium_any"] = d["um_plan_overpay"]
    d["um_plan_overpay"] = [bool(r["um_plan_overpay"] or O.right_size_option(r, plans) is not None
                                 or O.variant_option(r, plans) is not None) for _, r in d.iterrows()]
    d["upgrade_moment"] = d[det.UPGRADE_MOMENT_COLS].any(axis=1)
    gs = None
    if O.CONFIG.get("UPGRADE_GATE"):
        import upgrade_gate as ug
        gs = ug.load()
    if gs is not None:
        d = d.merge(gs[["account_id", "upgrade_pct", "in_top15"]], on="account_id", how="left")
        d["in_top15"] = d["in_top15"].fillna(False).astype(bool)
    else:
        d["upgrade_pct"], d["in_top15"] = np.nan, True
    d["upgrade_candidate"] = d["upgrade_moment"] & d["in_top15"]
    lt = pd.read_csv(O.OUT_DIR / "line_tradein.csv")
    tv = lt[(lt["net_now_cents"] > 0) | ((lt["financing_balance_cents"] == 0) & (lt["tradein_value_now_cents"] > 0))]
    d["n_tradein_value_lines"] = d["account_id"].map(tv.groupby("account_id").size()).fillna(0).astype(int)
    return O, cat, d.set_index("account_id")


@st.cache_resource(show_spinner="Loading the offer engine (one time, ~7 s)…")
def offer_api():
    """tm-offers' per-account chooser (harness/offer_api.py: prepared_row + choose_offer). Read-only, synthetic."""
    import os
    if data["offers"].source == "real":  # engine reads the same run the cards show (offers.OUT_DIR honours TM_OUT_DIR)
        os.environ.setdefault("TM_OUT_DIR", str(Path(data["offers"].path).parent))
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from harness import offer_api as api
    api.prepared_row(CARDS[0][0])  # warm the engine cache once
    return api


def what_if(acc: str, edits: dict) -> dict:
    """Re-score with Model A (score_account), re-pick with tm-offers' real chooser. Never raises."""
    out = {"p": None, "risks": [], "action": None, "why": None, "via": None, "error": None, "res": None}
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from harness.churn_scorer import score_account
        f = data["features"].df
        row = f[f.account_id == acc].iloc[0].to_dict()
        row.update(edits)
        out["p"], out["risks"], _stays = score_account(row)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"re-score unavailable ({type(e).__name__}: {e})"
        return out
    try:
        api = offer_api()
        er = api.prepared_row(acc)
        for k, v in edits.items():
            if k in er.index:
                er[k] = v
        res = api.choose_offer(er, out["p"])
        out.update(res=res, action=res["action_code"], why=res.get("why_this_offer"), via="harness.offer_api.choose_offer")
    except Exception as e:  # noqa: BLE001
        try:  # older engine without offer_api: same chooser functions, called directly
            O, cat, frame = engine()
            er = frame.loc[acc].copy()
            er["account_id"] = acc
            for k, v in edits.items():
                if k in er.index:
                    er[k] = v
            er["p_churn_90d"] = out["p"]
            ev = O.evaluate_account(er, cat["promotions"], cat["plans"])
            a = O.pick(ev["res"])[0]
            out.update(action=a, why=O.why_this_offer(a, er, ev), via="offers.evaluate_account + pick")
        except Exception as e2:  # noqa: BLE001
            out["error"] = f"decision re-pick needs offers engine hook ({type(e).__name__} / {type(e2).__name__})"
    return out


def key_facts(r) -> str:
    """Verifiable facts straight from features.csv (synthetic), so the why-line can be checked on screen."""
    def n(c):
        try:
            return float(r.get(c))
        except (TypeError, ValueError):
            return float("nan")
    bits = []
    if pd.notna(n("support_270d")):
        sent = n("avg_sentiment")
        bits.append(f"{int(n('support_270d'))} support contacts in 270 days, {int(n('unresolved_270d') or 0)} unresolved"
                    + (f", avg sentiment {sent:+.2f}" if pd.notna(sent) and n("support_270d") > 0 else ""))
    if pd.notna(n("port_out_inquiry")):
        bits.append("asked about porting out" if n("port_out_inquiry") > 0 else "no port-out inquiry")
    if pd.notna(n("competitor_research_score")):
        bits.append(f"shopping score {n('competitor_research_score'):.2f}")
    if pd.notna(n("bill_change_3m_pct")):
        bits.append(f"bill {n('bill_change_3m_pct'):+.0%} vs prior 3 mo")
    return "Facts: " + " · ".join(bits) + " (synthetic)" if bits else ""


def card(acc: str, story: str, fits: set, idx: int):
    if acc not in set(df.account_id):
        st.warning(f"{acc} is not in the loaded data.")
        return
    r = df[df.account_id == acc].iloc[0]
    k = r.get("action_key", "do_nothing")
    title = PERSONAS.get(acc, "")
    st.markdown(f"<div class='kicker'>Customer {idx} · {html.escape(story)}</div>", unsafe_allow_html=True)
    h1, h2 = st.columns([3, 1])
    h1.markdown(f"#### {html.escape(title) or acc}  \n`{acc}` · {r.get('segment', '')} · "
                f"{int(r.get('tenure_months', 0) or 0) // 12} yrs with us · synthetic customer")
    h2.metric("Churn risk, 90 days", fmt_prob(r.p_churn_90d),
              help="Model A, churn_scores.csv p_churn_90d: the single churn number used on every screen (synthetic).")
    why_ph = st.empty()
    warn_ph = st.empty()
    left, right = st.columns([2.4, 1])
    with left:
        dec_ph = st.empty()
        chips_ph = st.empty()
        st.caption(key_facts(r))
        opt_hdr, tbl_ph = st.empty(), st.empty()
        st.markdown("**What if?** Switch a fact off and our models re-decide live.")
        rel = [(key, lab, ed) for key, lab, cond, ed in TOGGLES if cond(r)]
        if not rel:
            st.caption("Nothing to switch off: no open tickets, no port-out inquiry, not comparing carriers.")
        edits = {}
        cols = st.columns(max(1, len(rel)))
        for (key, lab, ed), c in zip(rel, cols):
            if not c.toggle(lab, value=True, key=f"t_{acc}_{key}"):
                edits.update(ed)
        w = what_if(acc, edits) if edits else None
        res = (w or {}).get("res") or None
        if w is not None:
            if w["p"] is None:
                st.markdown(f"<div class='whatif'>{html.escape(w['error'])}</div>", unsafe_allow_html=True)
            else:
                line = f"Risk {fmt_prob(r.p_churn_90d)} → <b>{fmt_prob(w['p'])}</b>"
                if w["action"]:
                    na = normalize_action(w["action"])
                    line += f" · decision {'flips to' if na != normalize_action(k) else 'stays'} <b>{html.escape(action_label(na))}</b>"
                else:
                    line += f" · {html.escape(w['error'] or '')}"
                st.markdown(f"<div class='whatif'>{line}</div>", unsafe_allow_html=True)
                st.caption(f"Live: Model A re-score, then tm-offers' chooser ({w['via'] or 'n/a'}). Synthetic.")
    # fill the placeholders from the live result if a toggle is on, else from offers.csv
    risks = [r.get(f"risk_reason_{i}") for i in (1, 2, 3)]
    stays, _dropped = clean_stays(r)
    if w and w.get("p") is not None and w.get("risks"):
        risks = w["risks"]
        rr = r.copy()
        for kk, vv in edits.items():
            rr[kk] = vv
        for i in (1, 2, 3):
            rr[f"risk_reason_{i}"] = risks[i - 1] if i <= len(risks) else None
        stays, _dropped = clean_stays(rr)
    chips = "".join(f"<span class='chip risk'>▲ {html.escape(x)}</span>" for x in risks if isinstance(x, str) and x)
    chips += "".join(f"<span class='chip stay'>● {html.escape(x)}</span>" for x in stays)
    chips_ph.markdown(chips, unsafe_allow_html=True)
    k_now = normalize_action(w["action"]) if (w and w.get("action")) else k
    why = (w.get("why") if (w and w.get("why")) else
           (r.get("why_this_offer") if isinstance(r.get("why_this_offer"), str) else str(r.get("reason", ""))))
    why_ph.markdown(f"<div class='why'>{html.escape(why)}</div>", unsafe_allow_html=True)
    if not edits and normalize_action(k) not in {normalize_action(x) for x in fits}:
        warn_ph.error(f"Engine picked **{action_label(k)}**, which doesn't match this card's story ({story}).")
    dec_ph.markdown(f"**Decision: {action_label(k_now)}**" + ("  _(what-if)_" if edits and w and w.get("action") else ""))
    if res is not None:
        cand = res["candidates"].copy()
        cand["account_id"] = acc
        tbl, tip = options_table(acc, cand, res.get("message_en"))
    else:
        tbl, tip = options_table(acc)
    opt_hdr.markdown("**Options we considered**" + ("  _(what-if)_" if res is not None else ""), help=tip or None)
    if len(tbl):
        tbl_ph.dataframe(tbl, hide_index=True, width="stretch", column_config={
            "Option": st.column_config.TextColumn(width=190),
            "Cost to T-Mobile": st.column_config.TextColumn("Cost to us", width=80),
            "Customer": st.column_config.TextColumn("Customer saves / pays", width=190),
            "Why not": st.column_config.TextColumn(width="large")})
    else:
        tbl_ph.caption("offer_candidates.csv not loaded.")
    with right:
        lang_default = "es" if str(r.get("language", "en")) == "es" else "en"
        lang = st.radio("Text language", ["en", "es"], index=["en", "es"].index(lang_default), horizontal=True,
                        format_func=lambda x: {"en": "English", "es": "Español"}[x], key=f"lang_{acc}")
        msg = res.get(f"message_{lang}") if res is not None else r.get(f"message_{lang}")
        msg = msg.strip() if (k_now != "do_nothing" and isinstance(msg, str) and msg.strip()) else None
        st.markdown(phone(msg, lang), unsafe_allow_html=True)
        st.caption(("What-if text from tm-offers' message builder." if res is not None else "Exact text from offers.csv.")
                   + " Mockup only, nothing is sent.")


with tab2:
    st.markdown("### Four customers, four different right answers")
    st.caption("Same pipeline, different decision for each customer, including staying silent. All synthetic.")
    for i, (acc, story, fits) in enumerate(CARDS, 1):
        with st.container(border=True):
            card(acc, story, fits, i)

# ---------------- TAB 1: Dashboard ----------------
with tab1:
    import plotly.express as px
    import plotly.graph_objects as go
    st.markdown("<div class='how'><b>How it works:</b> Sandbox data → <b>Model A</b> churn risk + plain reasons → "
                "<b>Model B</b> picks the best offer, or do nothing → a text in English or Spanish. "
                "All numbers synthetic.</div>", unsafe_allow_html=True)
    st.write("")
    D = df.copy()
    nonp_p = NONP.p_churn_90d
    cut = float(nonp_p.quantile(0.90)) if len(nonp_p) else 1.0
    D["flagged"] = D.p_churn_90d >= cut
    D["contact"] = D.get("action_key", pd.Series("do_nothing", index=D.index)) != "do_nothing"
    has_msg = D.get("message_en", pd.Series("", index=D.index)).fillna("").astype(str).str.strip() != ""
    D["msg"] = D.contact & has_msg
    n_acc, n_flag, n_msg = len(D), int(D.flagged.sum()), int(D.msg.sum())
    n_dn = int((~D.contact).sum())
    n_msg_nonflag = int((D.msg & ~D.flagged).sum())
    lab = data["labels"].df
    catch, auc, catch_src = None, None, ""
    if len(lab) and "churn_90d" in lab:
        oof = data["churn_oof_pred"]
        src = oof.df if oof.source == "real" else NONP[["account_id", "p_churn_90d"]]
        catch_src = "held-out (out-of-fold)" if oof.source == "real" else "in-sample"
        j = src.merge(lab[["account_id", "churn_90d"]], on="account_id")
        j = j[~j.account_id.astype(str).str.startswith("ACC-PERSONA")].sort_values("p_churn_90d", ascending=False)
        catch = j.head(int(len(j) * 0.10)).churn_90d.sum() / max(1, j.churn_90d.sum())
        try:
            from sklearn.metrics import roc_auc_score
            auc = roc_auc_score(j.churn_90d, j.p_churn_90d)
        except Exception:  # noqa: BLE001
            auc = None
    k = st.columns(6)
    k[0].metric("Accounts", f"{n_acc:,}", help="Judge sandbox accounts incl. 42 personas (synthetic).")
    k[1].metric("Flagged at-risk", f"{n_flag:,}", help=f"Model A risk ≥ {fmt_prob(cut)}: the top 10% of regular accounts (synthetic).")
    k[2].metric("Top-10% catch", f"{catch:.0%}" if catch is not None else "n/a",
                help=f"Share of churners in the riskiest 10%, {catch_src} scores vs synthetic labels"
                     + (f"; AUC {auc:.3f}" if auc is not None else "") + ".")
    k[3].metric("Messages ready", f"{n_msg:,}", help="Accounts with an action and an EN/ES text in offers.csv (synthetic).")
    k[4].metric("Do nothing", f"{n_dn:,}", help="Accounts we deliberately leave alone (synthetic).")
    k[5].metric("Texts, not at risk", f"{n_msg_nonflag:,}",
                help="Customers below the risk flag who still get a text: money-saving, fix-first, or a plan upgrade (synthetic).")
    try:
        from streamlit_extras.metric_cards import style_metric_cards
        style_metric_cards(border_left_color=MAGENTA, background_color="#FFFFFF", border_color="#E5E7EB", box_shadow=False)
    except Exception:  # noqa: BLE001
        pass

    g1, g2 = st.columns(2)
    with g1, st.container(border=True):
        st.markdown("**From 5,000+ accounts to a handful of texts**")
        STEP = {"step_up", "step_up_plan"}
        D["upsell_nf"] = ~D.flagged & D.action_key.isin(STEP) if "action_key" in D else False
        fo = int((D.flagged & D.contact).sum()); fd = int((D.flagged & ~D.contact).sum())
        su = int(D.upsell_nf.sum())
        # "usage-based" only if EVERY step-up to a not-at-risk customer states a usage reason in offers.csv `reason`
        _usage_re = r"data cap|hotspot|near (?:their|the) (?:data )?(?:limit|cap)|over (?:the |their )?(?:plan )?(?:data )?cap|usage|\bGB\b"
        _ur = D.loc[D.upsell_nf, "reason"].fillna("").astype(str) if "reason" in D else pd.Series(dtype=str)
        UPS = "Plan upgrades, usage-based" if su and _ur.str.contains(_usage_re, case=False, regex=True).all() else "Plan upgrades"
        no = int((~D.flagged & D.contact & ~D.upsell_nf).sum()); nd = int((~D.flagged & ~D.contact).sum())
        m3 = int((D.msg & ~D.upsell_nf).sum()); m4 = int((D.msg & D.upsell_nf).sum())
        mo = m3 + m4
        labels_ = [f"All accounts {n_acc:,}", f"Flagged at-risk {n_flag:,}", f"Not flagged {n_acc - n_flag:,}",
                   f"Offer / contact {fo + no:,}", f"{UPS} {su:,}", f"Do nothing {fd + nd:,}",
                   f"Text ready {mo:,}"]
        fig = go.Figure(go.Sankey(
            node=dict(label=labels_, pad=18, thickness=16,
                      color=["#6E7781", MAGENTA, "#AFB8C1", MAGENTA, "#8250DF", "#AFB8C1", MAGENTA]),
            link=dict(source=[0, 0, 1, 1, 2, 2, 2, 3, 4], target=[1, 2, 3, 5, 3, 4, 5, 6, 6],
                      value=[n_flag, n_acc - n_flag, fo, fd, no, su, nd, m3, m4],
                      color=["rgba(226,0,116,.25)", "rgba(175,184,193,.35)", "rgba(226,0,116,.25)",
                             "rgba(175,184,193,.35)", "rgba(226,0,116,.18)", "rgba(130,80,223,.25)",
                             "rgba(175,184,193,.35)", "rgba(226,0,116,.25)", "rgba(130,80,223,.25)"])))
        fig.update_layout(template="plotly_white", height=380, margin=dict(l=8, r=8, t=8, b=8), font=dict(size=13, color="#1F2328"))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Why more texts ({mo:,}) than flags ({n_flag:,}): customers who aren't at risk still get a text when "
                   f"it helps them: {no:,} money-saving or fix-first contacts, plus {su:,} {UPS.lower()}"
                   + (" (near their data cap or using hotspot)" if "usage" in UPS else "")
                   + f". {fd:,} flagged customers get nothing because no offer is worth it. Synthetic.")
    with g2, st.container(border=True):
        st.markdown("**What we decided for each account**")
        if "action_key" in D:
            D["mix_label"] = D.action_key.map(action_label)
            D.loc[D.upsell_nf, "mix_label"] = f"{UPS} (not at risk)"
            mix = D.groupby("mix_label").size().reset_index(name="accounts").rename(columns={"mix_label": "action"})
            mix["kind"] = mix.action.map(lambda a: "Do nothing" if a == action_label("do_nothing")
                                         else ("Upsell" if a.startswith("Plan upgrades") else "Contact"))
            fig = px.bar(mix.sort_values("accounts"), x="accounts", y="action", orientation="h", color="kind",
                         color_discrete_map={"Do nothing": "#8C959F", "Contact": MAGENTA, "Upsell": "#8250DF"}, template="plotly_white",
                         text="accounts")
            fig.update_layout(height=380, margin=dict(l=8, r=40, t=8, b=8), showlegend=False,
                              xaxis_title="accounts (synthetic)", yaxis_title=None,
                              xaxis=dict(range=[0, float(mix.accounts.max()) * 1.15]))
            fig.update_traces(textposition="outside", cliponaxis=False)
            st.plotly_chart(fig, use_container_width=True)
    with st.container(border=True):
        st.markdown("**Same assumptions, different strategies (simulated)**")
        src_dir = Path(data["offers"].path).parent if data["offers"].path else REPO / "demo_data"
        cp = src_dir / "comparison.csv" if (src_dir / "comparison.csv").exists() else None
        same_run, n_ours, n_ours_cmp = True, int(D.contact.sum()), None
        if cp is not None:
            try:
                _c = pd.read_csv(cp)
                _o = _c[_c.strategy.str.contains("Ours")]
                n_ours_cmp = int(_o.contacted.iloc[0]) if len(_o) else None
                same_run = n_ours_cmp is None or n_ours_cmp == n_ours
            except Exception:  # noqa: BLE001
                same_run = False
        if cp is not None and not same_run:
            st.warning(f"comparison pending: comparison.csv was built from a different engine run "
                       f"({n_ours_cmp:,} contacts for 'Ours') than the offers.csv shown here ({n_ours:,}). "
                       "Not mixing runs.", icon="⏳")
        elif cp is not None:
            try:
                cmp_ = pd.read_csv(cp)
                cmp_["Strategy"] = cmp_.strategy.str.replace(r"^\d+\.\s*", "", regex=True)
                cmp_["ours"] = cmp_.Strategy.str.startswith("Ours")
                ca, cb = st.columns([1.1, 1])
                with ca:
                    fig = px.bar(cmp_, x="net_value_usd", y="Strategy", orientation="h", template="plotly_white",
                                 color="ours", color_discrete_map={True: MAGENTA, False: "#AFB8C1"},
                                 text=cmp_.net_value_usd.map(lambda v: f"${v:,.0f}"))
                    fig.add_vline(x=0, line_color="#57606A", line_width=1)
                    fig.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8), showlegend=False,
                                      xaxis_title="simulated net value, $ (synthetic)", yaxis_title=None,
                                      yaxis=dict(autorange="reversed"))
                    fig.update_traces(textposition="inside", insidetextanchor="middle", textfont_color="white")
                    st.plotly_chart(fig, use_container_width=True)
                with cb:
                    st.dataframe(pd.DataFrame({
                        "Contacts to low-risk customers": cmp_[next(c for c in ("contacts_to_low_risk", "unneeded_contacts") if c in cmp_)].astype(int),
                        "Credits $": cmp_.credit_spend_usd.map(lambda v: f"${v:,.0f}"),
                        "Strategy": cmp_.Strategy, "Churners reached": cmp_.churners_reached.astype(int),
                        "Net value (simulated)": cmp_.net_value_usd.map(lambda v: f"${v:,.0f}")}),
                        hide_index=True, width="stretch")
                    st.caption("All synthetic. Contacts to low-risk customers = people contacted who weren't going to churn.")
            except Exception as e:  # noqa: BLE001
                st.caption(f"comparison pending ({type(e).__name__})")
        else:
            st.caption("comparison pending")
        st.caption("Scored with our assumed acceptance rates; we don't claim lift until a holdout test.")
    g3, g4 = st.columns(2)
    with g3, st.container(border=True):
        st.markdown("**Churn risk across accounts (Model A)**")
        h = NONP.assign(pct=NONP.p_churn_90d * 100)
        fig = px.histogram(h, x="pct", nbins=60, template="plotly_white", color_discrete_sequence=["#AFB8C1"])
        fig.add_vline(x=cut * 100, line_color=MAGENTA, line_width=2, annotation_text=f"flag: top 10% (≥ {fmt_prob(cut)})",
                      annotation_position="top right", annotation_font_color=MAGENTA)
        fig.update_layout(height=330, margin=dict(l=8, r=8, t=8, b=8), xaxis_title="90-day churn risk, % (synthetic)",
                          yaxis_title="accounts", bargap=0.05)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Most customers are low risk; the average is {fmt_prob(nonp_p.mean())}. Synthetic.")
    with g4, st.container(border=True):
        uw = APP / "charts" / "06_upgrade_or_wait.png"
        if SHOW_UPGRADE_WAIT and uw.exists():
            st.markdown("**Upgrade now or wait?**")
            st.image(str(uw), use_container_width=True)
            st.caption("Trade-in value vs remaining phone balance, from line_tradein.csv. Synthetic.")
        else:
            st.markdown("**Top reason each flagged customer is at risk (Model A)**")
            fl = D[D.flagged & ~D.account_id.astype(str).str.startswith("ACC-PERSONA")]
            rr = fl.risk_reason_1.fillna("").str.replace(r"\d+(\.\d+)?", "#", regex=True)
            rr = rr.str.replace(r"\(score #\)", "", regex=True).str.replace("# unresolved support contact in", "# unresolved support contacts in").str.strip()
            t = rr[rr != ""].value_counts().head(8).reset_index()
            t.columns = ["reason", "accounts"]
            t["reason"] = t.reason.str.replace("#", "N")
            fig = px.bar(t.sort_values("accounts"), x="accounts", y="reason", orientation="h", template="plotly_white",
                         color_discrete_sequence=[MAGENTA], text="accounts")
            fig.update_layout(height=330, margin=dict(l=8, r=8, t=8, b=8), xaxis_title="flagged accounts (synthetic)", yaxis_title=None)
            fig.update_traces(textposition="outside", cliponaxis=False)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("churn_scores.csv risk_reason_1 for the flagged top 10% (N = a count in the reason). Synthetic.")

    with st.expander("Explore: drivers of churn and the at-risk list (synthetic)"):

        f, lab = data["features"].df, data["labels"].df
        fn = f[~f.account_id.astype(str).str.startswith("ACC-PERSONA")] if len(f) else f
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Expected 90-day churn (Model A)", fmt_prob(NONP.p_churn_90d.mean()) if len(NONP) else "n/a",
                  help=f"Mean churn_scores.csv p_churn_90d over {len(NONP):,} non-persona accounts (synthetic). "
                       "The judge sandbox's raw toy score averages 14.6%.")
        oof = data["churn_oof_pred"]
        if len(lab) and "churn_90d" in lab:
            src = oof.df if oof.source == "real" else NONP[["account_id", "p_churn_90d"]]
            j = src.merge(lab[["account_id", "churn_90d"]], on="account_id")
            j = j[~j.account_id.astype(str).str.startswith("ACC-PERSONA")].sort_values("p_churn_90d", ascending=False)
            top = j.head(int(len(j) * 0.10))
            cap = top.churn_90d.sum() / max(1, j.churn_90d.sum())
            c2.metric("Churners caught in the riskiest 10%", f"{cap:.0%}",
                      help=("Model A out-of-fold scores (churn_oof_pred.csv)" if oof.source == "real"
                            else "Model A in-sample scores (no out-of-fold file loaded)") + " vs labels.csv churn_90d. Synthetic.")
        if "cancel_inquiries_270d" in fn:
            c3.metric("Asked about cancelling (270d)", f"{int((fn.cancel_inquiries_270d > 0).sum()):,} accounts",
                      help="features.csv cancel_inquiries_270d > 0, non-persona (synthetic)")
        if "promo_expired_recent" in fn:
            c4.metric("Promo expired recently", f"{int((fn.promo_expired_recent > 0).sum()):,} accounts",
                      help="features.csv promo_expired_recent, non-persona (synthetic)")

        if len(fn) and len(lab) and "churn_90d" in lab:
            j = fn.merge(lab[["account_id", "churn_90d"]], on="account_id")
            parts = []
            for name, col, bins, labels in [
                ("Support contacts (90d)", "support_90d", [-1, 0, 2, 4, 999], ["0", "1-2", "3-4", "5+"]),
                ("Competitor research", "competitor_research_score", [-1, 0.25, 0.5, 0.75, 9], ["<0.25", "0.25-0.5", "0.5-0.75", "0.75+"]),
                ("Bill change (3 mo)", "bill_change_3m_pct", [-9, 0.0, 0.05, 99], ["flat / down", "up 0-5%", "up >5%"]),
                ("Port-out inquiry", "port_out_inquiry", [-1, 0, 9], ["no", "yes"]),
                ("Tenure", "tenure_months", [-1, 12, 36, 9999], ["<1 yr", "1-3 yrs", "3+ yrs"]),
            ]:
                if col in j:
                    g = j.groupby(pd.cut(j[col], bins, labels=labels), observed=True).churn_90d.agg(["mean", "size"]).reset_index()
                    g.columns = ["group", "rate", "n"]
                    g["driver"], g["churn_pct"] = name, g["rate"] * 100
                    parts.append(g)
            if parts:
                st.markdown("**What drives churn: synthetic 90-day churn rate by bucket** (features.csv × labels.csv)")
                t = pd.concat(parts)
                st.altair_chart(alt.Chart(t).mark_bar(color=MAGENTA).encode(
                    x=alt.X("churn_pct:Q", title="90-day churn % (synthetic labels)"),
                    y=alt.Y("group:N", title=None, sort=None),
                    row=alt.Row("driver:N", title=None, sort=None, header=alt.Header(labelAngle=0, labelAlign="left")),
                    tooltip=["driver", "group", alt.Tooltip("churn_pct:Q", format=".1f"), "n"]
                ).properties(height=alt.Step(16), width=520).resolve_scale(y="independent"))

        st.markdown("### Who's at risk this week")
        if len(df):
            n = st.slider("Show top", 5, min(200, len(df)), min(20, len(df)))
            v = df.sort_values("risk_rank").head(n)
            st.dataframe(pd.DataFrame({
                "Rank": v.risk_rank.astype(int), "Account": v.account_id, "Segment": v.get("segment", ""),
                "Risk (90d)": v.p_churn_90d.map(fmt_prob), "Top reason": v.risk_reason_1,
                "Decision": v.get("action_key", pd.Series(dtype=str)).map(action_label)}),
                hide_index=True, width="stretch", height=380)
            if "action_key" in df:
                dn = int((df.action_key == "do_nothing").sum())
                st.caption(f"{dn:,} of {len(df):,} accounts get no contact at all. Risk = Model A churn_scores.csv. "
                           "Note: texts also go to customers who aren't high-risk (money-saving and fix-first texts), "
                           "so the message count is not a subset of the flagged at-risk count. Synthetic.")



# ---------------- TAB 3: Pipeline visual ----------------
with tab3:
    st.markdown('### Pipeline visual')
    viz = APP / "viz" / "pipeline_flow.html"
    st.caption(f"The whole system on one page: sandbox data → Model A churn score → every eligible action priced, "
               f"with do nothing as a real option → a text in their language. File: [`app/viz/pipeline_flow.html`]({GITHUB_VIZ}) "
               "(opens offline in any browser). All synthetic.")
    if viz.exists():
        components.html(viz.read_text(encoding="utf-8", errors="replace"), height=900, scrolling=True)
    else:
        st.warning("app/viz/pipeline_flow.html not found. Build it with app/viz/make_pipeline_viz.py.")

st.divider()
_dirs = sorted({str(Path(l.path).parent.relative_to(REPO)) if l.path and Path(l.path).is_relative_to(REPO) else (l.path or "missing")
                for k, l in data.items() if k in ("churn_scores", "offers", "features", "labels", "offer_candidates")})
st.caption("Data source: " + ", ".join(f"`{d}/`" for d in _dirs) + (" (MOCK)" if MOCK else "") + ". All customers and numbers are synthetic.")
