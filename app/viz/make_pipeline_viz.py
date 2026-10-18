"""Pipeline visualization: sandbox + enrichment -> features -> Model A -> EV engine -> message on a phone.

Writes (all numbers SYNTHETIC; counts computed from harness/out/*.csv at run time, never typed in):
  app/viz/pipeline_flow.html     self-contained (plotly.js inlined), animated: pipeline strip, Sankey funnel
                                 (play button reveals stages left to right), follow-one-customer walkthrough
  app/viz/pipeline_flow.png      1600x900 slide (strip + funnel + phone)
  app/viz/pipeline_customer.png  1600x900 slide (follow-one-customer, final step)
  app/viz/pipeline_stats.json    every count used, with definitions and source file mtimes

Run:  /workspace/tmobile/harness/.venv/bin/python app/viz/make_pipeline_viz.py
Env:  TM_OUT_DIR (default harness/out), TM_VIZ_ACCOUNT (default ACC-PERSONA-04), SANDBOX_DB.
"""
from __future__ import annotations

import json
import os
import sqlite3
import textwrap
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = Path(os.environ.get("TM_OUT_DIR", REPO / "harness" / "out"))
ACCOUNT = os.environ.get("TM_VIZ_ACCOUNT", "ACC-PERSONA-04")

MAGENTA = "#E20074"   # ours
BG = "#1A1220"        # console dark plum
PANEL = "#251A2C"
EDGE = "#3A2C3E"      # console phone-bar
INK = "#F7F1EA"       # console cream
PINK = "#FF8FBF"      # console pink
MUTED = "#B9A9B5"
GREY = "#5A4A5E"
FONT = "Inter, Helvetica Neue, Arial, sans-serif"
SYN = "All customers and numbers are synthetic"

# Held-out Model A figures the team agreed to quote (chart_stats.json overrides 62/64/53 if present).
HELDOUT = {"top10_caught": 0.62, "oracle_top10": 0.64, "rule_rank_top10": 0.53, "auc": 0.853}

ACTION_LABEL = {
    "do_nothing": "Do nothing",
    "fix_first": "Fix-first callback",
    "care_credit_fix_first": "$25 credit + fix-first",
    "care_credit": "$25 care credit",
    "step_up": "Step-up plan",
    "loyalty_credit": "Loyalty credit",
    "keep_your_phone": "Keep-your-phone credit",
    "right_size": "Right-size plan",
    "device_upgrade": "Device upgrade",
}
EXTRA_COLORS = ["#7FD1FF", "#FFD27F", "#8BE0B0", "#C9A0FF", "#FFB3D9", "#7FFFD4", "#F5A97F", "#A0C4FF", "#E0E07F"]
STANDIN_KEYS = {"CARE-CREDIT": "care_credit", "LOYALTY-CREDIT": "loyalty_credit"}  # sandbox promo sku -> action substring
STANDIN = set()          # filled from sandbox promotions.source == 'stub' at run time
ACTION_TEXT = {}         # action_code -> offers.csv 'action' text, filled at run time
SEG_LABEL = {"family": "Family", "single": "Single", "couple": "Couple", "student": "Student",
             "smb": "Small business", "senior": "Senior"}


def is_standin(code: str) -> bool:
    return any(k in str(code) for k in STANDIN)


def alabel(code: str, dagger=True) -> str:
    """Label for an action code; unknown codes fall back to offers.csv's own 'action' text (data-driven)."""
    lab = ACTION_LABEL.get(code) or ACTION_TEXT.get(code) or str(code).replace("_", " ")
    return lab + ("†" if dagger and is_standin(code) else "")


def standin_text(action_text: str) -> str:
    t = str(action_text)
    if ("care credit" in t.lower() and "care_credit" in STANDIN) or ("loyalty credit" in t.lower() and "loyalty_credit" in STANDIN):
        return t + " (judge-provided stand-in)"
    return t


def mtime(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S %Z").strip() or "?"


def wrap(s: str, width: int) -> str:
    return "<br>".join(textwrap.wrap(str(s), width))


def fmt_pct(p: float) -> str:
    return f"{p:.1%}" if p >= 0.01 else f"{p:.2%}"


# ----------------------------------------------------------------------------------------------- data
def load():
    paths = {k: OUT / f"{k}.csv" for k in ("churn_scores", "offers", "offer_candidates", "features", "enrichment")}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise SystemExit(f"missing inputs: {missing}")
    d = {k: pd.read_csv(p) for k, p in paths.items()}
    d["features"] = d["features"][[c for c in d["features"].columns]]
    d["_mtimes"] = {k: mtime(p) for k, p in paths.items()}
    d["_paths"] = {k: str(p) for k, p in paths.items()}
    return d


def sandbox_tables():
    """Row counts read-only from the judge sandbox; None if the DB is not on this machine."""
    cands = [os.environ.get("SANDBOX_DB"), REPO / "dubhacks" / "data" / "sandbox.db",
             REPO.parent / "dubhacks" / "data" / "sandbox.db"]
    for c in cands:
        if c and Path(c).exists():
            conn = sqlite3.connect(Path(c).resolve().as_uri() + "?mode=ro", uri=True)
            names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            counts = {n: conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
            extra = {}
            try:
                extra["stub_promos"] = [r[0] for r in conn.execute("SELECT sku FROM promotions WHERE source = 'stub'")]
                roles = pd.read_sql("SELECT account_id, member_role FROM lines", conn)
                kid = roles[roles["member_role"].isin(["child", "teen"])]
                extra["kid_lines"] = {"child_lines": int((kid["member_role"] == "child").sum()),
                                      "teen_lines": int((kid["member_role"] == "teen").sum()),
                                      "accounts_with_kid_lines": int(kid["account_id"].nunique())}
                extra["kid_by_account"] = kid.groupby(["account_id", "member_role"]).size().unstack(fill_value=0)
            except Exception as e:  # noqa: BLE001
                extra["error"] = str(e)
            conn.close()
            return str(Path(c).resolve()), counts, extra
    return None, {}, {}


def funnel(d):
    cs, of, fe = d["churn_scores"], d["offers"], d["features"]
    seg_col = next((c for c in ("offer_segment", "strategy_segment", "segment") if c in of.columns), None)
    of = of.rename(columns={seg_col: "offer_seg"}) if seg_col else of.assign(offer_seg=pd.NA)
    m = of[["account_id", "action_code", "message_status", "offer_seg"]].merge(
        cs[["account_id", "p_churn_90d"]], on="account_id", how="left").merge(
        fe[["account_id", "segment", "language", "is_persona"]], on="account_id", how="left")
    regular = m[m["is_persona"] == 0]
    cut = float(regular["p_churn_90d"].quantile(0.90))  # churn lane's 'high' = top 10% of regular accounts
    m["flagged"] = m["p_churn_90d"] >= cut
    m["offered"] = m["action_code"] != "do_nothing"
    m["messaged"] = m["message_status"] == "ok"
    m["col3"] = (m["offer_seg"].where(m["offer_seg"].notna(), m["segment"]) if seg_col else m["segment"]).astype(str)
    m.attrs["col3_source"] = f"offers.csv '{seg_col}'" if seg_col else "features.csv household segment"
    m.attrs["col3_head"] = "OFFER SEGMENT" if seg_col else "HOUSEHOLD (offered)"
    return m, cut


# ----------------------------------------------------------------------------------------------- sankey
def sankey_spec(m):
    """Nodes/links in 5 columns: all -> flag -> action -> segment (offered only) -> message status."""
    nodes, links = [], []  # node: dict(label, col, color, n) ; link: (src, tgt, value, stage, color)

    def node(label, col, color, n):
        nodes.append(dict(label=label, col=col, color=color, n=int(n)))
        return len(nodes) - 1

    n_all = len(m)
    i_all = node(f"All accounts  {n_all:,}", 0, "#8A7B84", n_all)
    nf = int(m["flagged"].sum())
    i_flag = node(f"Flagged at-risk  {nf:,}", 1, MAGENTA, nf)
    i_nflag = node(f"Not flagged  {n_all - nf:,}", 1, GREY, n_all - nf)
    links += [(i_all, i_flag, nf, 1, "rgba(226,0,116,0.45)"), (i_all, i_nflag, n_all - nf, 1, "rgba(138,123,132,0.25)")]

    act_order = [a for a in ["care_credit_fix_first", "fix_first", "care_credit", "step_up", "loyalty_credit",
                             "keep_your_phone", "right_size", "device_upgrade"] if (m["action_code"] == a).any()]
    act_order += [a for a in sorted(m["action_code"].unique()) if a not in act_order and a != "do_nothing"]
    act_color = {"care_credit_fix_first": "#FF4DA6", "fix_first": "#F27BB8", "care_credit": "#FFB3D9",
                 "step_up": "#7FD1FF", "loyalty_credit": "#C9A0FF", "keep_your_phone": "#8BE0B0",
                 "right_size": "#FFD27F", "device_upgrade": "#7FFFD4"}
    i_act = {}
    for a in act_order + ["do_nothing"]:
        n = int((m["action_code"] == a).sum())
        col = EDGE if a == "do_nothing" else act_color.get(a, EXTRA_COLORS[len(i_act) % len(EXTRA_COLORS)])
        i_act[a] = node(f"{alabel(a)}  {n:,}", 2, col, n)
    for flag, i_src in ((True, i_flag), (False, i_nflag)):
        sub = m[m["flagged"] == flag]
        for a in act_order + ["do_nothing"]:
            v = int((sub["action_code"] == a).sum())
            if v:
                c = "rgba(90,74,94,0.35)" if a == "do_nothing" else (
                    "rgba(226,0,116,0.45)" if flag else "rgba(127,209,255,0.30)")
                links.append((i_src, i_act[a], v, 2, c))

    off = m[m["offered"]]
    seg_order = list(off["col3"].value_counts().index)
    i_seg = {}
    for s in seg_order:
        n = int((off["col3"] == s).sum())
        i_seg[s] = node(f"{SEG_LABEL.get(s, s.replace('_', ' '))}  {n:,}", 3, "#C9A0DC", n)
    for a in act_order:
        sub = off[off["action_code"] == a]
        for s in seg_order:
            v = int((sub["col3"] == s).sum())
            if v:
                links.append((i_act[a], i_seg[s], v, 3, "rgba(201,160,220,0.28)"))

    msg = m[m["messaged"]]
    n_en, n_es = int((msg["language"] == "en").sum()), int((msg["language"] == "es").sum())
    n_other = len(msg) - n_en - n_es
    i_en = node(f"Message ready, English  {n_en:,}", 4, MAGENTA, n_en)
    i_es = node(f"Message ready, Spanish  {n_es:,}", 4, PINK, n_es)
    i_other = node(f"Message ready, other  {n_other:,}", 4, PINK, n_other) if n_other else None
    nomsg = m[~m["messaged"]]
    i_no = node(f"No message  {len(nomsg):,}", 4, EDGE, len(nomsg))
    for s in seg_order:
        sub = msg[(msg["col3"] == s)]
        for lang, i_t in (("en", i_en), ("es", i_es)):
            v = int((sub["language"] == lang).sum())
            if v:
                links.append((i_seg[s], i_t, v, 4, "rgba(226,0,116,0.40)"))
        if i_other is not None:
            v = int((~sub["language"].isin(["en", "es"])).sum())
            if v:
                links.append((i_seg[s], i_other, v, 4, "rgba(226,0,116,0.40)"))
    # offered but not messaged (validation failed) -> No message, via segment
    for s in seg_order:
        v = int(((off["col3"] == s) & (~off["messaged"])).sum())
        if v:
            links.append((i_seg[s], i_no, v, 4, "rgba(90,74,94,0.35)"))
    v = int(((m["action_code"] == "do_nothing") & (~m["messaged"])).sum())
    if v:
        links.append((i_act["do_nothing"], i_no, v, 4, "rgba(90,74,94,0.35)"))
    v = int(((m["action_code"] == "do_nothing") & (m["messaged"])).sum())
    if v:  # should be 0: do-nothing has no message
        links.append((i_act["do_nothing"], i_en, v, 4, "rgba(255,0,0,0.6)"))

    # fixed positions: x per column, y stacked by size with padding (centres, 0..1 from top)
    xs = {0: 0.001, 1: 0.24, 2: 0.48, 3: 0.72, 4: 0.999}
    for col in range(5):
        idx = [i for i, nd in enumerate(nodes) if nd["col"] == col]
        tot = sum(max(nodes[i]["n"], 1) for i in idx)
        pad = 0.035
        avail = 1 - pad * (len(idx) - 1) - 0.04
        y = 0.02
        for i in idx:
            h = avail * max(nodes[i]["n"], 1) / tot
            nodes[i]["x"], nodes[i]["y"] = xs[col], min(max(y + h / 2, 0.001), 0.999)
            y += h + pad
    return nodes, links


def sankey_trace(nodes, links, stage, domain=None, font_size=13):
    """Stage k shows columns <= k; hidden parts are transparent (positions stay fixed)."""
    show_node = [nd["col"] <= stage for nd in nodes]
    tr = go.Sankey(
        arrangement="fixed",
        domain=domain or dict(x=[0, 1], y=[0, 1]),
        node=dict(
            label=[nd["label"] if s else "" for nd, s in zip(nodes, show_node)],
            color=[nd["color"] if s else "rgba(0,0,0,0)" for nd, s in zip(nodes, show_node)],
            x=[nd["x"] for nd in nodes], y=[nd["y"] for nd in nodes],
            pad=14, thickness=16, line=dict(width=0),
            hovertemplate="%{label}<br>(synthetic)<extra></extra>",
        ),
        link=dict(
            source=[l[0] for l in links], target=[l[1] for l in links], value=[l[2] for l in links],
            color=[l[4] if l[3] <= stage else "rgba(0,0,0,0)" for l in links],
            hovertemplate="%{source.label} → %{target.label}<br>%{value:,} accounts (synthetic)<extra></extra>",
        ),
        textfont=dict(color=INK, size=font_size, family=FONT),
    )
    return tr


STAGE_TITLES = [
    "1 · 5,042 sandbox accounts",
    "2 · Model A flags the riskiest 10%",
    "3 · EV engine: best offer vs do nothing",
    "4 · Who gets an offer, by household",
    "5 · Message drafted in their language",
]


ANN_DEFAULTS = dict(xref="paper", yref="paper", x=0, y=0, xanchor="left", yanchor="top", text="", showarrow=False,
                    align="left", bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)", borderpad=1, opacity=1,
                    xshift=0, yshift=0, visible=True)
SHAPE_DEFAULTS = dict(xref="paper", yref="paper", type="rect", x0=0, x1=0, y0=0, y1=0, path=None,
                      fillcolor="rgba(0,0,0,0)", line=dict(color="rgba(0,0,0,0)", width=0), layer="above",
                      opacity=1, visible=True)


def norm_ann(items, n):
    """Plotly.animate merges annotations by index, so every slot gets every property and lists are padded."""
    out = []
    for a in list(items) + [dict(visible=False)] * (n - len(items)):
        a = a.to_plotly_json() if hasattr(a, "to_plotly_json") else dict(a)
        b = {**ANN_DEFAULTS, **a}
        b["font"] = {"color": INK, "size": 12, "family": FONT, **a.get("font", {})}
        out.append(b)
    return out


def norm_shapes(items, n):
    out = []
    for sh in list(items) + [dict(visible=False)] * (n - len(items)):
        sh = sh.to_plotly_json() if hasattr(sh, "to_plotly_json") else dict(sh)
        b = {**SHAPE_DEFAULTS, **sh}
        b["line"] = {"color": "rgba(0,0,0,0)", "width": 0, "dash": "solid", **sh.get("line", {})}
        if b["type"] != "path":
            b.pop("path")
        out.append(b)
    return out


def arrow_shapes(xa, xb, y, color=MAGENTA):
    """Horizontal arrow xa -> xb at height y, paper coords."""
    hx, hy = 0.006, 0.014
    return [dict(type="line", xref="paper", yref="paper", x0=xa, x1=xb - hx, y0=y, y1=y, line=dict(color=color, width=2)),
            dict(type="path", xref="paper", yref="paper", path=f"M {xb - hx},{y - hy} L {xb},{y} L {xb - hx},{y + hy} Z",
                 fillcolor=color, line=dict(color=color, width=1))]


# ----------------------------------------------------------------------------------------------- strip
def strip_shapes(stats, y0, y1, x0=0.0, x1=1.0, highlight=None, compact=False, plot_h=755):
    """Five pipeline cards with arrows, in paper coords. Returns (shapes, annotations)."""
    st = stats
    cards = [
        ("DATA", "Judge sandbox + enrichment",
         f"{st['sandbox']['n_tables_used']} sandbox tables · {st['sandbox']['rows_used']:,} rows<br>"
         f"accounts, lines (incl. {st['sandbox'].get('kid_lines', {}).get('child_lines', 0) + st['sandbox'].get('kid_lines', {}).get('teen_lines', 0):,} kid lines),<br>usage, bills, support, signals, plans, promos<br>"
         f"+ {st['enrichment']['card_text']}"),
        ("FEATURES", "One row per account",
         f"{st['features']['n_accounts']:,} accounts × {st['features']['n_columns']} features<br>"
         f"support contacts & sentiment, bill shock,<br>promo expiry, plan fit, device age,<br>competitor research, tenure"),
        ("MODEL A", "Churn score + reasons",
         f"p(churn in 90 days) per account<br>top-3 reasons at risk / to stay<br>"
         f"held-out: top 10% catches {st['heldout']['top10_caught']:.0%}<br>"
         f"of churners (oracle {st['heldout']['oracle_top10']:.0%}, rule {st['heldout']['rule_rank_top10']:.0%}) · AUC {st['heldout']['auc']:.3f}"),
        ("EV ENGINE", "Offers vs do nothing (Model B)",
         f"{st['ev']['n_actions']} actions scored per account<br>EV = save value − cost − annoyance<br>"
         f"eligibility from sandbox promo rules<br>do nothing wins for {st['funnel']['do_nothing']:,}"),
        ("MESSAGE", "Personalized text, EN / ES",
         f"{st['funnel']['messaged']:,} messages drafted + validated<br>amounts re-checked vs sandbox<br>"
         f"no income, job or kid details in text<br>reply STOP to opt out"),
    ]
    shapes, ann = [], []
    n = len(cards)
    gap = 0.018
    w = (x1 - x0 - gap * (n - 1)) / n
    for k, (tag, title, body) in enumerate(cards):
        cx0 = x0 + k * (w + gap)
        hi = highlight is None or highlight == k
        border = MAGENTA if (highlight == k) else (EDGE if not hi else "#6A5A6E")
        shapes.append(dict(type="rect", xref="paper", yref="paper", x0=cx0, x1=cx0 + w, y0=y0, y1=y1,
                           fillcolor=PANEL if hi else "#1E1524", line=dict(color=border, width=2 if highlight == k else 1),
                           layer="below"))
        op = 1.0 if hi else 0.35
        ann.append(dict(xref="paper", yref="paper", x=cx0 + 0.008, y=y1 - 12 / plot_h, xanchor="left", yanchor="top",
                        text=f"<b>{tag}</b>", showarrow=False, font=dict(color=MAGENTA, size=12, family=FONT), opacity=op))
        ann.append(dict(xref="paper", yref="paper", x=cx0 + 0.008, y=y1 - 34 / plot_h, xanchor="left", yanchor="top",
                        text=f"<b>{title}</b>", showarrow=False, font=dict(color=INK, size=14, family=FONT), opacity=op))
        if not compact:
            ann.append(dict(xref="paper", yref="paper", x=cx0 + 0.008, y=y1 - 62 / plot_h, xanchor="left", yanchor="top",
                            text=body, showarrow=False, align="left",
                            font=dict(color=MUTED, size=11, family=FONT), opacity=op))
        if k < n - 1:
            ax = cx0 + w
            shapes += arrow_shapes(ax + 0.002, ax + gap - 0.002, (y0 + y1) / 2)
    return shapes, ann


# ----------------------------------------------------------------------------------------------- phone
def _rr(x0, y0, x1, y1, rx, ry, small=None):
    """Rounded rect path (paper coords). small = (rx, ry) for the bottom-left corner (chat-bubble tail)."""
    sx, sy = small or (rx, ry)
    return (f"M {x0 + sx},{y0} L {x1 - rx},{y0} Q {x1},{y0} {x1},{y0 + ry} L {x1},{y1 - ry} Q {x1},{y1} {x1 - rx},{y1} "
            f"L {x0 + rx},{y1} Q {x0},{y1} {x0},{y1 - ry} L {x0},{y0 + sy} Q {x0},{y0} {x0 + sx},{y0} Z")


def phone_shapes(px0, py0, pw, ph, bubbles, header="T-Mobile", lang_tags=None, plot_w=1540, plot_h=730, size=12):
    """Console-style phone: rounded dark plum body, pill bar, cream bubbles (16/16/16/4 px corners)."""
    shapes, ann = [], []
    ux, uy = 1 / plot_w, 1 / plot_h   # one pixel in paper units
    shapes.append(dict(type="path", xref="paper", yref="paper", path=_rr(px0, py0, px0 + pw, py0 + ph, 28 * ux, 28 * uy),
                       fillcolor="#120C17", line=dict(color=EDGE, width=3)))
    shapes.append(dict(type="path", xref="paper", yref="paper",
                       path=_rr(px0 + 48 * ux * 0 + pw * 0.35, py0 + ph - 22 * uy, px0 + pw * 0.65, py0 + ph - 14 * uy, 4 * ux, 4 * uy),
                       fillcolor=EDGE, line=dict(width=0)))
    ann.append(dict(xref="paper", yref="paper", x=px0 + pw / 2, y=py0 + ph - 34 * uy, yanchor="top", xanchor="center",
                    text=f"<b>{header}</b>", showarrow=False, font=dict(color=PINK, size=14, family=FONT)))
    ann.append(dict(xref="paper", yref="paper", x=px0 + pw / 2, y=py0 + ph - 54 * uy, yanchor="top", xanchor="center",
                    text="Text message · synthetic", showarrow=False, font=dict(color=MUTED, size=9, family=FONT)))
    y = py0 + ph - 84 * uy
    line_px = size * 1.35
    for k, b in enumerate(bubbles):
        if lang_tags:
            ann.append(dict(xref="paper", yref="paper", x=px0 + 16 * ux, y=y, xanchor="left", yanchor="top",
                            text=lang_tags[k], showarrow=False, font=dict(color=MUTED, size=10, family=FONT)))
            y -= 20 * uy
        nl = b.count("<br>") + 1
        h = (nl * line_px + 20) * uy
        bx0, bx1 = px0 + 14 * ux, px0 + pw - 14 * ux
        shapes.append(dict(type="path", xref="paper", yref="paper", path=_rr(bx0, y - h, bx1, y, 16 * ux, 16 * uy, small=(4 * ux, 4 * uy)),
                           fillcolor=INK, line=dict(width=0)))
        ann.append(dict(xref="paper", yref="paper", x=bx0 + 12 * ux, y=y - 10 * uy, xanchor="left", yanchor="top", text=b,
                        showarrow=False, align="left", font=dict(color=BG, size=size, family=FONT)))
        y -= h + 22 * uy
    shapes.append(dict(type="path", xref="paper", yref="paper",
                       path=_rr(px0 + pw * 0.36, py0 + 12 * uy, px0 + pw * 0.64, py0 + 17 * uy, 2 * ux, 2 * uy),
                       fillcolor=EDGE, line=dict(width=0)))
    return shapes, ann


# ----------------------------------------------------------------------------------------------- customer
def customer_story(d, m, cut):
    a = ACCOUNT
    cs = d["churn_scores"].set_index("account_id").loc[a]
    of = d["offers"].set_index("account_id").loc[a]
    fe = d["features"].set_index("account_id").loc[a]
    en = d["enrichment"].set_index("account_id").loc[a] if a in set(d["enrichment"]["account_id"]) else None
    oc = d["offer_candidates"][d["offer_candidates"]["account_id"] == a].copy()
    rank = int(cs["risk_rank"])
    p = float(cs["p_churn_90d"])
    flagged = p >= cut

    def g(s, k, default="n/a"):
        return s[k] if (s is not None and k in s.index and pd.notna(s[k])) else default

    signals = [
        f"{SEG_LABEL.get(fe['segment'], fe['segment'])} household, {int(fe['n_lines'])} lines, {int(fe['tenure_months'])} months with us",
        f"Plan {str(fe['plan_sku']).replace('TMO-STUB-PLAN-', '').title()}, last bill ${fe['last_bill_cents'] / 100:,.2f} "
        f"({fe['bill_increase_pct']:+.0%} vs prior avg)" + (", promo just ended" if fe.get("promo_expired_recent", 0) == 1 else ""),
        f"{int(fe['support_90d'])} support contacts in 90 days ({int(fe['unresolved_90d'])} unresolved, "
        f"{int(fe['network_contacts_90d'])} network), avg sentiment {fe['avg_sentiment_90d']:+.2f}",
        f"Competitor research score {fe['competitor_research_score']:.2f} · {int(fe['app_sessions_30d'])} app sessions in 30 days",
        f"Prefers {fe['contact_preference']} · language {str(fe['language']).upper()}",
    ]
    kid = d.get("_kid")
    if kid is not None:
        kr = kid.loc[a] if a in kid.index else None
        nc = int(kr.get("child", 0)) if kr is not None else 0
        nt = int(kr.get("teen", 0)) if kr is not None else 0
        signals.append(f"Kid lines on the account: {nc} child, {nt} teen  [sandbox lines.member_role]")
    # tagged drivers from tm-offers (offers.csv 'drivers': 'group:signal;...'), when present
    drivers = []
    if "drivers" in of.index and pd.notna(of["drivers"]) and str(of["drivers"]).strip():
        for item in str(of["drivers"]).split(";"):
            item = item.strip()
            if ":" in item:
                grp, sig = item.split(":", 1)
                drivers.append((grp.strip(), sig.strip()))
    ecols = set(en.index) if en is not None else set()
    enrich = []
    if "recent_job_change" in ecols:
        enrich.append(f"Recent job change: {'yes' if int(g(en, 'recent_job_change', 0)) == 1 else 'no'}  [enrichment (simulated), BLS base rate]")
    else:
        enrich.append("Recent job change: planned enrichment (not in enrichment.csv yet)")
    if "income_band" in ecols:
        enrich.append(f"Income band: {g(en, 'income_band')}  [enrichment (simulated), ACS national distribution]")
    else:
        enrich.append("Income band: planned enrichment (not in enrichment.csv yet)")
    enrich.append("Finer kid age band: planned enrichment (kid lines themselves are real sandbox data, step 1)")
    if "next_plan_sku" in ecols and pd.notna(g(en, "next_plan_sku", None)):
        enrich.append(f"Next plan up: {str(g(en, 'next_plan_sku')).replace('TMO-STUB-PLAN-', '').title()}"
                      + (f", +${float(g(en, 'step_up_cost_cents', 0)) / 100:,.0f}/mo" if g(en, 'step_up_cost_cents', None) is not None else "")
                      + "  [sandbox plans table]")
    enrich.append("Used only to pick the offer. Never written into the message.")
    oc["label"] = oc["action"]
    elig = oc[oc["eligible"] == True].sort_values("expected_value")  # noqa: E712
    inel = oc[oc["eligible"] != True]  # noqa: E712
    story = dict(
        account_id=a, rank=rank, n=len(d["churn_scores"]), p=p, flagged=bool(flagged), cut=cut,
        risk=[cs[f"risk_reason_{i}"] for i in (1, 2, 3) if pd.notna(cs.get(f"risk_reason_{i}"))],
        stay=[cs[f"stay_reason_{i}"] for i in (1, 2, 3) if pd.notna(cs.get(f"stay_reason_{i}"))],
        signals=signals, enrich=enrich, drivers=drivers,
        elig=[(standin_text(r["action"]), float(r["expected_value"]), bool(r["is_chosen"])) for _, r in elig.iterrows()],
        inel=[(r["action"], str(r["reason"]).replace("Not eligible: ", "")) for _, r in inel.iterrows()],
        chosen=standin_text(of["action"]), chosen_code=str(of["action_code"]), ev=float(of["expected_value"]),
        runner=standin_text(of["runner_up_action"]), runner_ev=float(of["runner_up_ev"]) if pd.notna(of["runner_up_ev"]) else None,
        reason=str(of["reason"]), message_en=str(of["message_en"]) if pd.notna(of["message_en"]) else "",
        message_es=str(of["message_es"]) if pd.notna(of["message_es"]) else "", message_status=str(of["message_status"]),
        language=str(fe["language"]), contact_pref=str(fe["contact_preference"]),
        customer_value=float(of["customer_value_usd"]),
    )
    return story


CUST_STEPS = ["Signals", "Enrichment", "Model A", "EV engine", "Message"]


def customer_frame(story, step):
    """Layout pieces for step 0..4 of the follow-one-customer view."""
    shapes, ann = [], []
    # step track across the top (left 64%)
    x0, x1 = 0.02, 0.64
    n = len(CUST_STEPS)
    for k, name in enumerate(CUST_STEPS):
        cx = x0 + (x1 - x0) * k / (n - 1)
        done = k <= step
        shapes.append(dict(type="circle", xref="paper", yref="paper", x0=cx - 0.012, x1=cx + 0.012, y0=0.80 - 0.021,
                           y1=0.80 + 0.021, fillcolor=MAGENTA if done else BG,
                           line=dict(color=MAGENTA if done else GREY, width=2)))
        ann.append(dict(xref="paper", yref="paper", x=cx, y=0.80, xanchor="center", yanchor="middle", text=f"<b>{k + 1}</b>", showarrow=False,
                        font=dict(color=INK if done else MUTED, size=12, family=FONT)))
        ann.append(dict(xref="paper", yref="paper", x=cx, y=0.745, xanchor="center", yanchor="middle", text=name, showarrow=False,
                        font=dict(color=INK if k == step else MUTED, size=13, family=FONT)))
        if k < n - 1:
            nx = x0 + (x1 - x0) * (k + 1) / (n - 1)
            shapes.append(dict(type="line", xref="paper", yref="paper", x0=cx + 0.014, x1=nx - 0.014, y0=0.80, y1=0.80,
                               line=dict(color=MAGENTA if k < step else GREY, width=2)))
    # detail panel
    shapes.append(dict(type="rect", xref="paper", yref="paper", x0=0.02, x1=0.64, y0=0.06, y1=0.70,
                       fillcolor=PANEL, line=dict(color=EDGE, width=1), layer="below"))

    def head(t, sub=""):
        ann.append(dict(xref="paper", yref="paper", x=0.035, y=0.68, xanchor="left", yanchor="top",
                        text=f"<b>{t}</b>" + (f"<span style='color:{MUTED}'>  {sub}</span>" if sub else ""),
                        showarrow=False, font=dict(color=INK, size=17, family=FONT)))

    def lines(items, y=0.60, size=13, color=INK, bullet="•", width=88):
        txt = "<br>".join(f"{bullet} {wrap(i, width).replace('<br>', '<br>   ')}" for i in items)
        ann.append(dict(xref="paper", yref="paper", x=0.035, y=y, xanchor="left", yanchor="top", text=txt,
                        showarrow=False, align="left", font=dict(color=color, size=size, family=FONT)))

    s = story
    show_bars = False
    if step == 0:
        head("What the sandbox already knows", "real sandbox fields, synthetic customer")
        lines(s["signals"], size=14)
        if s.get("drivers"):
            tag = {"commerce": "#7FD1FF", "customer": PINK, "live": "#FFD27F"}
            txt = " ".join(f"<span style='color:{tag.get(gname.split('(')[0], '#C9A0DC')}'>[{gname}]</span> {sig.replace('_', ' ')}"
                           for gname, sig in s["drivers"])
            ann.append(dict(xref="paper", yref="paper", x=0.035, y=0.24, xanchor="left", yanchor="top",
                            text="<b>Tagged drivers (tm-offers)</b><br>" + wrap(txt, 200), showarrow=False, align="left",
                            font=dict(color=INK, size=12, family=FONT)))
    elif step == 1:
        head("Enrichment", "context for choosing the deal")
        lines(s["enrich"][:-1], size=14)
        ann.append(dict(xref="paper", yref="paper", x=0.035, y=0.16, xanchor="left", yanchor="top",
                        text=f"<b>{s['enrich'][-1]}</b>", showarrow=False, font=dict(color=MAGENTA, size=14, family=FONT)))
    elif step == 2:
        head("Model A: churn score + reasons", "tm-churn churn_scores.csv, synthetic labels")
        ann.append(dict(xref="paper", yref="paper", x=0.035, y=0.60, xanchor="left", yanchor="top",
                        text=f"<b>{fmt_pct(s['p'])}</b>", showarrow=False, font=dict(color=MAGENTA, size=44, family=FONT)))
        ann.append(dict(xref="paper", yref="paper", x=0.20, y=0.585, xanchor="left", yanchor="top",
                        text=f"chance of leaving in 90 days (synthetic)<br>rank {s['rank']:,} of {s['n']:,} · "
                             f"{'FLAGGED: top 10% cut is ' + fmt_pct(s['cut']) if s['flagged'] else 'not flagged (cut ' + fmt_pct(s['cut']) + ')'}",
                        showarrow=False, align="left", font=dict(color=INK, size=13, family=FONT)))
        ann.append(dict(xref="paper", yref="paper", x=0.035, y=0.45, xanchor="left", yanchor="top",
                        text="<b>Why they might leave</b>", showarrow=False, font=dict(color=MAGENTA, size=14, family=FONT)))
        lines(s["risk"], y=0.41, size=13, width=40)
        ann.append(dict(xref="paper", yref="paper", x=0.34, y=0.45, xanchor="left", yanchor="top",
                        text="<b>Why they might stay</b>", showarrow=False, font=dict(color="#7FD1FF", size=14, family=FONT)))
        ann.append(dict(xref="paper", yref="paper", x=0.34, y=0.41, xanchor="left", yanchor="top",
                        text="<br>".join(f"• {wrap(t, 38)}" for t in s["stay"]), showarrow=False, align="left",
                        font=dict(color=INK, size=13, family=FONT)))
    elif step == 3:
        head("EV engine: every eligible offer vs doing nothing", "simulated $, synthetic")
        show_bars = True
        if s["inel"]:
            ann.append(dict(xref="paper", yref="paper", x=0.035, y=0.24, xanchor="left", yanchor="top",
                            text="<b>Not eligible</b><br>" + "<br>".join(
                                f"{a}: {wrap(r, 70 - len(a)).replace('<br>', ' ')}" for a, r in s["inel"]),
                            showarrow=False, align="left", font=dict(color=MUTED, size=11, family=FONT)))
    else:
        head(f"Chosen: {s['chosen']}", f"EV ${s['ev']:,.2f} (simulated)")
        lines([wrap(s["reason"], 86).replace("<br>", " ")], size=14)
        ann.append(dict(xref="paper", yref="paper", x=0.035, y=0.44, xanchor="left", yanchor="top",
                        text=(f"Runner-up: {s['runner']} (EV ${s['runner_ev']:,.2f})<br>" if s["runner_ev"] is not None else "")
                        + f"Message status: <b>{s['message_status']}</b> (dollar amounts re-checked vs sandbox)<br>"
                          f"Channel preference: {s['contact_pref']} · language {s['language'].upper()}<br>"
                          f"Nothing about income, job or kids appears in the text.",
                        showarrow=False, align="left", font=dict(color=INK, size=13, family=FONT)))
        recap = [f"Signals: {s['risk'][0] if s['risk'] else 'n/a'}",
                 f"Model A: {fmt_pct(s['p'])} chance of leaving, rank {s['rank']:,} of {s['n']:,}"
                 + (" → flagged (top 10%)" if s["flagged"] else " → not flagged"),
                 f"EV engine: {len(s['elig']) - 1} eligible offers scored; chosen EV ${s['ev']:,.2f} vs do nothing $0.00",
                 "Message: the exact offers.csv text, shown on the phone →"]
        ann.append(dict(xref="paper", yref="paper", x=0.035, y=0.27, xanchor="left", yanchor="top",
                        text="<b>The whole path</b><br>" + "<br>".join(f"{i + 1}. {t}" for i, t in enumerate(recap)),
                        showarrow=False, align="left", font=dict(color=MUTED, size=13, family=FONT)))
    # phone
    if step >= 4 and s["message_en"]:
        bub = [wrap(s["message_en"], 40), wrap(s["message_es"], 40)]
        tags = ["English (their language)" if s["language"] == "en" else "English",
                "Español" + (" (their language)" if s["language"] == "es" else "")]
    else:
        bub, tags = [], None
    ps, pa = phone_shapes(0.70, 0.04, 0.26, 0.86, bub, lang_tags=tags, plot_w=1540, plot_h=708)
    if not bub:
        pa.append(dict(xref="paper", yref="paper", x=0.83, y=0.47, xanchor="center", yanchor="middle", align="center", text="waiting for<br>the EV engine…",
                       showarrow=False, font=dict(color=MUTED, size=13, family=FONT)))
    return shapes + ps, ann + pa, show_bars


def bars_trace(story, visible):
    labels = ["do nothing"] + [a for a, ev, c in story["elig"] if a != "do nothing"]
    evs = [0.0] + [ev for a, ev, c in story["elig"] if a != "do nothing"]
    colors = [GREY] + [MAGENTA if c else "#7FD1FF" for a, ev, c in story["elig"] if a != "do nothing"]
    return go.Bar(x=evs if visible else [0] * len(evs), y=labels, orientation="h", marker_color=colors,
                  text=[f"${v:,.2f}" for v in evs] if visible else [""] * len(evs), textposition="outside",
                  textfont=dict(color=INK, size=12, family=FONT), cliponaxis=False,
                  hovertemplate="%{y}: EV $%{x:,.2f} (simulated)<extra></extra>", xaxis="x", yaxis="y",
                  showlegend=False, opacity=1 if visible else 0)


def esc_dollars(fig):
    """Plotly/kaleido may treat text with two '$' as LaTeX; use the HTML entity instead."""
    def fix(a):
        if a.text and "$" in a.text:
            a.text = a.text.replace("$", "&#36;")
    fig.for_each_annotation(fix)
    for fr in fig.frames or []:
        for a in fr.layout.annotations or []:
            fix(a)
    return fig


def base_layout(title, w=1600, h=900, top=120):
    return go.Layout(
        width=w, height=h, paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=INK, family=FONT),
        margin=dict(l=30, r=30, t=top, b=72),
        title=dict(text=title, x=0.02, y=0.985, yanchor="top", font=dict(size=24, color=INK, family=FONT)),
    )


def banner(y=1.0):
    return [dict(xref="paper", yref="paper", x=1.0, y=1.0, xanchor="right", yanchor="bottom", yshift=58,
                 text=f"<b>  {SYN.upper()}  </b>", showarrow=False, bgcolor=MAGENTA,
                 font=dict(color="white", size=14, family=FONT), borderpad=6)]


def footnote(text):
    return dict(xref="paper", yref="paper", x=0.0, y=0, yshift=-66, xanchor="left", yanchor="bottom", text=text,
                showarrow=False, font=dict(color=MUTED, size=11, family=FONT), align="left")


def customer_fig(story, static_step=None):
    title = (f"Follow one customer: {story['account_id']} "
             f"<span style='font-size:15px;color:{MUTED}'>(synthetic persona)</span>")
    foot = footnote("Synthetic customer from the judge sandbox. Model A = tm-churn churn_scores.csv. EVs = Model B (tm-offers offer_candidates.csv), "
                    "simulated: save value − cost − annoyance.<br>† / stand-in = judge-provided stand-in credit (sandbox promo source 'stub'). "
                    "Message = exact message_en / message_es.")
    steps = range(5) if static_step is None else [static_step]
    frames = []
    for k in steps:
        sh, an, bars = customer_frame(story, k)
        frames.append(go.Frame(name=CUST_STEPS[k], data=[bars_trace(story, bars)],
                               layout=go.Layout(shapes=sh, annotations=an + banner() + [foot],
                                                xaxis=dict(visible=bars), yaxis=dict(visible=bars))))
    na = max(len(f.layout.annotations) for f in frames)
    ns = max(len(f.layout.shapes) for f in frames)
    for f in frames:
        f.layout.annotations = norm_ann(f.layout.annotations, na)
        f.layout.shapes = norm_shapes(f.layout.shapes, ns)
    first = frames[0]
    lay = base_layout(title)
    lay.update(
        xaxis=dict(domain=[0.20, 0.52], anchor="y", showgrid=False, zeroline=True, zerolinecolor=GREY,
                   tickfont=dict(color=MUTED), tickprefix="$", range=[0, max([e for _, e, _ in story["elig"]] + [1]) * 1.25]),
        yaxis=dict(domain=[0.30, 0.62], anchor="x", tickfont=dict(color=INK, size=12), automargin=True),
        shapes=first.layout.shapes, annotations=first.layout.annotations,
    )
    lay.xaxis.visible = first.layout.xaxis.visible
    lay.yaxis.visible = first.layout.yaxis.visible
    fig = go.Figure(data=first.data, layout=lay)
    if static_step is None:
        fig.frames = frames
        fig.update_layout(
            updatemenus=[dict(type="buttons", showactive=False, x=0.02, y=0.90, xanchor="left", yanchor="top",
                              direction="left", bgcolor=PANEL, bordercolor=MAGENTA, font=dict(color=INK),
                              buttons=[dict(label="▶  Play", method="animate",
                                            args=[None, dict(frame=dict(duration=2600, redraw=True),
                                                             transition=dict(duration=0), fromcurrent=True)])])],
            sliders=[dict(active=0, x=0.12, y=0.915, len=0.52, xanchor="left", yanchor="top", pad=dict(t=0, b=0),
                          currentvalue=dict(visible=False), font=dict(color=MUTED), bgcolor=PANEL,
                          activebgcolor=MAGENTA, bordercolor=GREY, tickcolor=BG,
                          steps=[dict(label="", method="animate",
                                      args=[[s], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                                                      transition=dict(duration=0))]) for s in CUST_STEPS])])
    return esc_dollars(fig)


def funnel_fig(nodes, links, stats, animated=True):
    title = ("Who we text, and why: 5,042 synthetic accounts through the pipeline "
             f"<span style='font-size:15px;color:{MUTED}'>(synthetic)</span>")
    foot = footnote(f"Flagged = Model A p(churn 90d) ≥ {stats['funnel']['flag_cut']:.4f}, the top 10% of the 5,000 regular "
                    "accounts (churn lane's cut; 42 personas scored on the same cut). Offer = offers.csv action ≠ do nothing. "
                    "Message ready = message_status 'ok' (drafted + validated, nothing sent). Language = account preference.<br>"
                    f"Model A = tm-churn churn_scores.csv · actions = Model B (tm-offers offers.csv) · column 4 = {stats['funnel']['col3_source']} · "
                    "† judge-provided stand-in credit (sandbox promo source 'stub').")
    lay = base_layout(title)
    stage_ann = lambda k: [dict(xref="paper", yref="paper", x=0.02, y=1.0, yshift=18, xanchor="left", yanchor="bottom",
                                text=STAGE_TITLES[k], showarrow=False, font=dict(color=MAGENTA, size=16, family=FONT))]
    stage_heads = lambda k: [dict(xref="paper", yref="paper", x=x, y=1.0, yshift=-2, xanchor=xa, yanchor="bottom",
                                  text=t, showarrow=False, font=dict(color=MUTED if i > k else INK, size=12, family=FONT))
                             for i, (x, xa, t) in enumerate([(0.0, "left", "ACCOUNTS"), (0.24, "center", "MODEL A FLAG"),
                                                             (0.48, "center", "CHOSEN ACTION"), (0.72, "center", stats["funnel"]["col3_head"]),
                                                             (1.0, "right", "MESSAGE")])]
    if not animated:
        lay.update(annotations=banner() + [foot] + stage_heads(4))
        return go.Figure(data=[sankey_trace(nodes, links, 4, domain=dict(x=[0, 1], y=[0, 0.96]))], layout=lay)
    frames = [go.Frame(name=str(k), data=[sankey_trace(nodes, links, k, domain=dict(x=[0, 1], y=[0, 0.96]))],
                       layout=go.Layout(annotations=norm_ann(banner() + [foot] + stage_ann(k) + stage_heads(k), 8)))
              for k in range(5)]
    lay.update(annotations=frames[-1].layout.annotations,
               updatemenus=[dict(type="buttons", showactive=False, x=0.98, y=1.0, yanchor="bottom", xanchor="right", pad=dict(b=22),
                                 direction="left", bgcolor=PANEL, bordercolor=MAGENTA, font=dict(color=INK),
                                 buttons=[dict(label="▶  Play", method="animate",
                                               args=[[str(k) for k in range(5)], dict(frame=dict(duration=1600, redraw=True),
                                                                transition=dict(duration=0), mode="immediate")]),
                                          dict(label="Show all", method="animate",
                                               args=[["4"], dict(mode="immediate", frame=dict(duration=0, redraw=True))])])])
    fig = go.Figure(data=frames[-1].data, layout=lay, frames=frames)
    return fig


def strip_fig(stats):
    lay = base_layout("The pipeline: from T-Mobile's sandbox to a text that doesn't feel weird", h=420, top=110)
    sh, an = strip_shapes(stats, 0.02, 0.98, plot_h=420 - 110 - 72)
    lay.update(shapes=sh, annotations=an + banner(), xaxis=dict(visible=False), yaxis=dict(visible=False))
    return go.Figure(layout=lay)


def slide_fig(nodes, links, stats, story):
    """1600x900 static: strip top, funnel bottom-left, phone bottom-right."""
    lay = base_layout("From sandbox to SMS: one retention pipeline "
                      f"<span style='font-size:15px;color:{MUTED}'>(all synthetic)</span>", top=95)
    sh, an = strip_shapes(stats, 0.70, 0.99, plot_h=733)
    tr = sankey_trace(nodes, links, 4, domain=dict(x=[0.0, 0.70], y=[0.0, 0.58]), font_size=11)
    bub = [wrap(story["message_en"], 32)] if story["message_en"] else []
    ps, pa = phone_shapes(0.80, 0.0, 0.19, 0.62, bub, lang_tags=[f"{story['account_id']} (synthetic)"], plot_w=1540, plot_h=733)
    heads = [dict(xref="paper", yref="paper", x=x, y=0.615, xanchor=xa, yanchor="bottom", text=t, showarrow=False,
                  font=dict(color=MUTED, size=11, family=FONT))
             for x, xa, t in [(0.0, "left", "ACCOUNTS"), (0.168, "center", "MODEL A FLAG"), (0.336, "center", "CHOSEN ACTION"),
                              (0.504, "center", stats["funnel"]["col3_head"]), (0.70, "right", "MESSAGE")]]
    foot = footnote(f"Synthetic. Model A = tm-churn churn_scores.csv; flagged = its top 10% (p ≥ {stats['funnel']['flag_cut']:.3f}). Actions = Model B (tm-offers). "
                    "Message ready = drafted + validated, nothing sent. † judge-provided stand-in credit.<br>Held-out Model A: top 10% catches 62% of "
                    "churners (oracle 64%, 3+ calls rule 53%), AUC 0.853.")
    lay.update(shapes=sh + ps + arrow_shapes(0.725, 0.79, 0.31), annotations=an + pa + heads + banner() + [foot])
    return go.Figure(data=[tr], layout=lay)


def enrich_card_text(e):
    c = set(e.columns)
    have = [n for k, n in (("recent_job_change", "job change"), ("income_band", "income band")) if k in c]
    txt = "enrichment (simulated): " + ", ".join(have) if have else "enrichment: planned"
    return txt + ";<br>finer kid age band: planned"


def whatif_data(d, m):
    """'What if X% accept' from Model A (churn_scores.csv) + Model B (offers.csv / offer_candidates.csv) only."""
    oc = d["offer_candidates"]
    ch = oc[oc["is_chosen"] == True][["account_id", "save_rate", "offer_cost"]]  # noqa: E712
    of = d["offers"][["account_id", "action_code", "customer_value_usd"]]
    cs = d["churn_scores"][["account_id", "p_churn_90d"]]
    x = of.merge(cs, on="account_id").merge(ch, on="account_id", how="left")
    off = x[x["action_code"] != "do_nothing"].fillna({"save_rate": 0.0, "offer_cost": 0.0})
    base = float(x["p_churn_90d"].sum())
    save1 = float((off["p_churn_90d"] * off["save_rate"]).sum())
    val1 = float((off["p_churn_90d"] * off["save_rate"] * off["customer_value_usd"]).sum())
    cost1 = float(off["offer_cost"].sum())
    grid = [round(k * 0.05, 2) for k in range(21)]
    rows = [dict(accept=a, averted=a * save1, churn_rate=(base - a * save1) / len(x), retained_value=a * val1,
                 offer_cost=a * cost1) for a in grid]
    return dict(n_accounts=int(len(x)), n_offered=int(len(off)), expected_churners_all=base,
                expected_churners_offered=float(off["p_churn_90d"].sum()), baseline_churn_rate=base / len(x),
                averted_at_100=save1, retained_value_at_100=val1, offer_cost_at_100=cost1, grid=rows, default=0.25,
                definition="averted(a) = a x sum over offered accounts of p_churn_90d (Model A) x save_rate of the chosen "
                           "action (Model B); value(a) = a x sum p x save_rate x customer_value_usd; cost(a) = a x sum offer_cost. "
                           "Linear in a by assumption.")


def whatif_fig(w):
    grid = w["grid"]
    xs = [r["accept"] for r in grid]
    lay = base_layout("What if X% of offers are accepted? "
                      f"<span style='font-size:15px;color:{PINK}'>Projected, illustrative assumption (synthetic)</span>", h=600, top=110)
    lay.update(xaxis=dict(domain=[0.0, 0.55], title="Share of offers accepted", tickformat=".0%", gridcolor=EDGE,
                          color=MUTED, range=[-0.02, 1.02], zeroline=False),
               yaxis=dict(domain=[0.0, 1.0], title="Churners averted in 90 days (expected)", gridcolor=EDGE, color=MUTED,
                          zeroline=False, rangemode="tozero"))
    line = go.Scatter(x=xs, y=[r["averted"] for r in grid], mode="lines", line=dict(color=MAGENTA, width=4),
                      hovertemplate="%{x:.0%} accept → %{y:.1f} averted (projected, synthetic)<extra></extra>", showlegend=False)
    foot = footnote("Engine: Model A + Model B (tm-offers). Model A = tm-churn churn_scores.csv; save_rate, offer_cost, customer_value from "
                    "offer_candidates.csv / offers.csv. Assumes each accepted offer saves a would-be churner at Model B's save_rate,<br>"
                    "linear in acceptance; who gets an offer is fixed. Not measured. Dollars are PROVISIONAL and synthetic.")

    def frame_parts(r):
        pt = go.Scatter(x=[r["accept"]], y=[r["averted"]], mode="markers", marker=dict(size=16, color=PINK, line=dict(color=INK, width=2)),
                        hoverinfo="skip", showlegend=False)
        big = [
            (0.92, f"<b>{r['accept']:.0%}</b> of {w['n_offered']:,} offers accepted", INK, 20),
            (0.74, f"<b>{r['averted']:.1f}</b> churners averted", MAGENTA, 30),
            (0.60, f"of {w['expected_churners_all']:.1f} expected across {w['n_accounts']:,} accounts", MUTED, 14),
            (0.44, f"90-day churn <b>{w['baseline_churn_rate']:.2%}</b> → <b>{r['churn_rate']:.2%}</b>", INK, 20),
            (0.26, f"retained value ${r['retained_value']:,.0f} − offer cost ${r['offer_cost']:,.0f}", INK, 15),
            (0.17, f"= net ${r['retained_value'] - r['offer_cost']:,.0f}  PROVISIONAL", PINK, 15),
        ]
        an = [dict(xref="paper", yref="paper", x=0.62, y=y, xanchor="left", yanchor="middle", text=t, showarrow=False,
                   font=dict(color=c, size=sz, family=FONT)) for y, t, c, sz in big]
        vline = dict(type="line", xref="x", yref="paper", x0=r["accept"], x1=r["accept"], y0=0, y1=1,
                     line=dict(color=PINK, width=1, dash="dot"))
        return pt, an, [vline]

    frames = []
    for r in grid:
        pt, an, sh = frame_parts(r)
        frames.append(go.Frame(name=f"{r['accept']:.2f}", data=[line, pt],
                               layout=go.Layout(annotations=norm_ann(an + banner() + [foot], 8), shapes=norm_shapes(sh, 1))))
    d0 = next(f for f in frames if f.name == f"{w['default']:.2f}")
    lay.update(annotations=d0.layout.annotations, shapes=d0.layout.shapes,
               sliders=[dict(active=xs.index(w["default"]), x=0.0, len=0.55, y=-0.19, yanchor="top", pad=dict(t=0),
                             currentvalue=dict(prefix="Acceptance: ", font=dict(color=INK)), font=dict(color=MUTED),
                             bgcolor=PANEL, activebgcolor=MAGENTA, bordercolor=GREY, tickcolor=MUTED,
                             steps=[dict(label=f"{a:.0%}" if round(a * 100) % 20 == 0 else "", method="animate",
                                         args=[[f"{a:.2f}"], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                                                                  transition=dict(duration=0))]) for a in xs])])
    lay.margin.b = 190
    for f in frames:
        for a in f.layout.annotations:
            if a.text and a.text.startswith("Engine:"):
                a.yshift = -186
    for a in lay.annotations:
        if a.text and a.text.startswith("Engine:"):
            a.yshift = -186
    return esc_dollars(go.Figure(data=d0.data, layout=lay, frames=frames))


# ----------------------------------------------------------------------------------------------- main
def main():
    d = load()
    m, cut = funnel(d)
    db_path, tcounts, sbx = sandbox_tables()
    for sku in sbx.get("stub_promos", []):
        for k, code in STANDIN_KEYS.items():
            if k in sku:
                STANDIN.add(code)
    ACTION_TEXT.update(d["offers"].groupby("action_code")["action"].agg(lambda x: x.mode().iat[0]).to_dict())
    d["_kid"] = sbx.get("kid_by_account")
    d["_sbx"] = sbx
    used = ["accounts", "account_signals", "lines", "plans", "devices", "usage_monthly", "billing_history",
            "support_interactions", "account_addons", "line_addons", "addons", "promotions", "tradein_curves"]
    used_present = {t: tcounts[t] for t in used if t in tcounts}

    cs_path = REPO / "app" / "charts" / "chart_stats.json"
    held = dict(HELDOUT)
    if cs_path.exists():
        g = json.loads(cs_path.read_text()).get("gain", {})
        for k in ("oracle_top10", "rule_rank_top10"):
            if k in g:
                held[k] = round(g[k], 2)
        if "model_top10" in g:
            held["top10_caught"] = round(g["model_top10"], 2)

    off = m[m["offered"]]
    msg = m[m["messaged"]]
    oc = d["offer_candidates"]
    stats = {
        "note": SYN + ". Counts computed from harness/out CSVs at build time.",
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " America/Los_Angeles",
        "inputs": {k: {"path": d["_paths"][k], "mtime": d["_mtimes"][k]} for k in d["_paths"]},
        "sandbox": {"db": db_path, "tables_all": tcounts, "tables_used": used_present,
                    "n_tables_used": len(used_present) or len(used), "rows_used": int(sum(used_present.values())),
                    "source": "row counts read read-only from sandbox.db" if db_path else "sandbox.db not found"},
        "enrichment": {
            "columns": [c for c in d["enrichment"].columns if c != "account_id"],
            "recent_job_change": int(d["enrichment"]["recent_job_change"].sum()) if "recent_job_change" in d["enrichment"] else None,
            "family_plan": int(d["enrichment"]["is_family_plan"].sum()) if "is_family_plan" in d["enrichment"] else None,
            "likely_kid": int(d["enrichment"]["likely_kid_flag"].sum()) if "likely_kid_flag" in d["enrichment"] else None,
            "kid_age_band": d["enrichment"]["kid_age_band"].value_counts().to_dict() if "kid_age_band" in d["enrichment"] else None,
            "income_band": d["enrichment"]["income_band"].value_counts().to_dict() if "income_band" in d["enrichment"] else None,
            "card_text": enrich_card_text(d["enrichment"]),
            "provenance": "harness/enrichment.py docstring: job change + income synthetic (BLS JOLTS / ACS B19001 marginals); "
                          "family plan + kid lines/age band derived from real sandbox lines.member_role.",
        },
        "features": {"n_accounts": int(len(d["features"])), "n_columns": int(d["features"].shape[1] - 1)},
        "heldout": held,
        "ev": {"n_actions": int(oc["action"].nunique()), "actions": sorted(oc["action"].unique().tolist()),
               "n_candidate_rows": int(len(oc)), "n_eligible_rows": int((oc["eligible"] == True).sum())},  # noqa: E712
        "funnel": {
            "all_accounts": int(len(m)),
            "regular_accounts": int((m["is_persona"] == 0).sum()), "persona_accounts": int((m["is_persona"] == 1).sum()),
            "flag_definition": "p_churn_90d >= 90th percentile of the 5,000 regular (non-persona) accounts; same 'high = top 10%' cut as harness/churn_model.py persona check",
            "flag_cut": cut,
            "flagged": int(m["flagged"].sum()), "flagged_regular": int((m["flagged"] & (m["is_persona"] == 0)).sum()),
            "not_flagged": int((~m["flagged"]).sum()),
            "offered": int(m["offered"].sum()), "do_nothing": int((~m["offered"]).sum()),
            "offered_flagged": int((m["offered"] & m["flagged"]).sum()),
            "offered_not_flagged": int((m["offered"] & ~m["flagged"]).sum()),
            "by_action": m["action_code"].value_counts().to_dict(),
            "by_action_flagged": m[m["flagged"]]["action_code"].value_counts().to_dict(),
            "by_action_not_flagged": m[~m["flagged"]]["action_code"].value_counts().to_dict(),
            "offered_by_segment": off["segment"].value_counts().to_dict(),
            "col3_source": m.attrs["col3_source"], "col3_head": m.attrs["col3_head"],
            "offered_by_col3": off["col3"].value_counts().to_dict(),
            "action_by_segment": {a: g["segment"].value_counts().to_dict() for a, g in off.groupby("action_code")},
            "messaged_definition": "offers.csv message_status == 'ok' (message drafted and validated against sandbox amounts; nothing is sent)",
            "messaged": int(len(msg)), "message_status_counts": m["message_status"].value_counts().to_dict(),
            "messaged_by_language": msg["language"].value_counts().to_dict(),
            "offered_not_messaged": int((m["offered"] & ~m["messaged"]).sum()),
        },
        "sankey_links": [],
    }
    nodes, links = sankey_spec(m)
    stats["sankey_links"] = [{"from": nodes[s]["label"], "to": nodes[t]["label"], "value": v} for s, t, v, _, _ in links]
    stats["sandbox"]["kid_lines"] = sbx.get("kid_lines")
    stats["sandbox"]["stub_promos"] = sbx.get("stub_promos")
    stats["standin_actions"] = sorted(STANDIN)
    wi = whatif_data(d, m)
    stats["whatif"] = wi
    story = customer_story(d, m, cut)
    stats["traced_customer"] = {k: v for k, v in story.items() if k not in ("signals", "enrich")}
    stats["traced_customer"]["signals_shown"] = story["signals"]
    stats["traced_customer"]["enrichment_shown"] = story["enrich"]

    # ---- figures
    f_strip, f_funnel, f_cust = strip_fig(stats), funnel_fig(nodes, links, stats), customer_fig(story)
    f_whatif = whatif_fig(wi)
    cfg = dict(displaylogo=False, responsive=False)
    parts = [pio.to_html(f_strip, include_plotlyjs="inline", full_html=False, config=cfg, div_id="strip"),
             pio.to_html(f_funnel, include_plotlyjs=False, full_html=False, config=cfg, div_id="funnel",
                         auto_play=False),
             pio.to_html(f_cust, include_plotlyjs=False, full_html=False, config=cfg, div_id="customer",
                         auto_play=False),
             pio.to_html(f_whatif, include_plotlyjs=False, full_html=False, config=cfg, div_id="whatif",
                         auto_play=False)]
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>TM retention pipeline (synthetic)</title>
<style>body{{background:{BG};color:{INK};font-family:{FONT};margin:0}}
.wrap{{width:1600px;margin:0 auto}} .sec{{margin:0 0 28px 0}}
.top{{background:{MAGENTA};color:#fff;text-align:center;font-weight:700;padding:10px;letter-spacing:.06em;position:sticky;top:0;z-index:9}}
h2{{font-weight:600;color:{MUTED};font-size:14px;letter-spacing:.12em;margin:22px 30px 4px}}</style></head>
<body><div class="top">{SYN.upper()} · every count below is computed from synthetic CSVs · policy dollars are PROVISIONAL</div>
<div class="wrap"><h2>01 · PIPELINE</h2><div class="sec">{parts[0]}</div>
<h2>02 · FUNNEL (press Play)</h2><div class="sec" id="s-funnel">{parts[1]}</div>
<h2>03 · FOLLOW ONE CUSTOMER (press Play)</h2><div class="sec" id="s-customer">{parts[2]}</div>
<h2>04 · WHAT IF (drag the slider)</h2><div class="sec" id="s-whatif">{parts[3]}</div></div></body></html>"""
    assert "with autopay" not in html.lower(), "never write 'with AutoPay'"
    (HERE / "pipeline_flow.html").write_text(html, encoding="utf-8")

    pio.write_image(slide_fig(nodes, links, stats, story), HERE / "pipeline_flow.png", width=1600, height=900, scale=1)
    pio.write_image(customer_fig(story, static_step=4), HERE / "pipeline_customer.png", width=1600, height=900, scale=1)
    (HERE / "pipeline_stats.json").write_text(json.dumps(stats, indent=1, default=str), encoding="utf-8")
    print(json.dumps(stats["funnel"], indent=1, default=str))
    print("wrote", HERE / "pipeline_flow.html", HERE / "pipeline_flow.png", HERE / "pipeline_customer.png")


if __name__ == "__main__":
    main()
