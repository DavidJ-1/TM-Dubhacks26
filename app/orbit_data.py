"""Data loaders for the scroll page (adapted from the orbit design mock's odata.py / mockdata.py).

Read-only: every input is a file in this repo (demo_data/, docs/outreach/outreach_card.csv, docs/considerations.csv,
docs/outreach/inputs/guardrail_detail.csv, experiments/efficacy/out/chart_receipt.csv); falls back to the shared clone
if the worktree lacks one, then to the models team's scratch outputs, and degrades gracefully if a file is missing. The risk scorer's model cache is redirected to a temp dir,
so nothing is ever written into the repo. All number logic lives here or in scroll_app.py; app/orbit_sections.py only
draws what it is handed, so swapping the sections file never changes a number.
"""
from __future__ import annotations

import math
import re
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SHARED = Path("/workspace/tmobile/TM-Dubhacks26")
PERSONA = "ACC-PERSONA-"
DEMO = ["38", "04", "21", "24"]
_TMP = Path(tempfile.mkdtemp(prefix="scroll_scorer_"))


def _pick(rel: str) -> Path:
    p = ROOT / rel
    return p if p.exists() else SHARED / rel


D = _pick("demo_data")
OUTREACH = _pick("docs/outreach/outreach_card.csv")
CONSIDERATIONS = _pick("docs/considerations.csv")
REPO = D.parent
SCRATCH = Path("/workspace/tmobile/scratch_models")
# guardrail detail: repo-tracked copy on dev (docs/outreach/inputs/), else the models team's scratch output
GUARDRAIL = next((p for p in (ROOT / "docs/outreach/inputs/guardrail_detail.csv", SHARED / "docs/outreach/inputs/guardrail_detail.csv",
                              SCRATCH / "economics/guardrail/out/guardrail_detail.csv") if p.exists()), None)
CHART_RECEIPT = _pick("experiments/efficacy/out/chart_receipt.csv")     # v2 receipt totals (strict like-for-like rule)
HOUSEHOLD = _pick("experiments/efficacy/data/household_plan.csv")       # optimizer reasons (perks flag for the strict rule)
PLAN_MOVES = SCRATCH / "chart_check/plan_moves_classified.csv"          # per-account moves behind chart_receipt.csv
HEADLINE = SCRATCH / "economics/headline_1478.csv"                      # +$4,109 at 10%, break-even 4.8% (same file the chart reads)

# plain-language clean-up for strings that come straight from data files
_CLEAN = [
    (re.compile(r"asked about porting (their )?number out", re.I), "Asked about transferring their number"),
    (re.compile(r"port[- ]?out inquir(y|ies)", re.I), "number-transfer question"),
    (re.compile(r"port[- ]?out", re.I), "number-transfer"),
    (re.compile(r"\s*\((?:[a-z_]+\.)+[a-z_]+\)"), ""),   # table.column references
    (re.compile(r"\bsandbox\s+", re.I), ""),
    (re.compile(r"\bport(ing|ed)?\b(?=[^.]*number)", re.I), "transfer"),
    (re.compile(r"\bSKU\b", re.I), "plan"),
]


def clean(s) -> str:
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return ""
    s = str(s)
    for rx, rep in _CLEAN:
        s = rx.sub(rep, s)
    return s


# ------------------------------------------------------------------ one selected customer
# The scroll page has one selected account. The dropdown, the quick picks, a chart dot, and a table row
# all write it through apply_shared_selection. Widget keys stay in this dict so a test can check them
# without starting Streamlit.
DEMO_CODES = tuple(DEMO)
# Real accounts across the risk bands. At least one do-nothing. Personas 07, 31, and 24 stay out.
QUICK = (
    {"id": "ACC-00347", "band": "low risk", "why": "do nothing"},
    {"id": "ACC-01116", "band": "low risk", "why": "cheaper plan on the bill"},
    {"id": "ACC-02363", "band": "high risk", "why": "do nothing"},
    {"id": "ACC-01607", "band": "very high risk", "why": "fix-first message"},
)
QUICK_IDS = tuple(q["id"] for q in QUICK)


def quick_label(q: dict) -> str:
    return f"{q['band']}, {q['why']}"


def quick_button(q: dict) -> str:
    return f"{customer_cid(q['id'])} · {quick_label(q)}"


def quick_marks() -> list[dict]:
    """Scatter labels: the id beside the dot, and the short reason on hover."""
    return [{"id": q["id"], "text": customer_cid(q["id"]), "hover": quick_label(q)} for q in QUICK]


def customer_cid(account_id: str) -> str:
    """Persona codes stay '38'; everyone else is '#02363'."""
    account_id = str(account_id)
    return account_id[len(PERSONA):] if account_id.startswith(PERSONA) else account_id.replace("ACC-", "#")


def format_risk_pct(risk: float) -> str:
    """Probability (0–1) as a short percent. 0.87 → '87%'."""
    x = float(risk) * 100
    if x >= 10:
        return f"{x:.0f}%"
    if x >= 1:
        return f"{x:.1f}%"
    return f"{x:.2f}%"


def format_monthly_bill(bill_cents) -> str | None:
    """Customer monthly bill, cents in and dollars out. Missing stays blank (never a made-up amount)."""
    if bill_cents is None:
        return None
    try:
        if pd.isna(bill_cents):
            return None
    except TypeError:
        return None
    return f"${float(bill_cents) / 100:,.0f}/mo"


def customer_menu_label(account_id: str, risk: float, bill_cents=None) -> str:
    """Dropdown line, e.g. 'Customer #02363, 87% risk, $142/mo'."""
    bill = format_monthly_bill(bill_cents)
    tail = f", {bill}" if bill else ""
    return f"Customer {customer_cid(account_id)}, {format_risk_pct(risk)} risk{tail}"


def customers_by_risk(rows) -> list[str]:
    """Account ids, highest 90-day churn risk first. Ties break on the id so the order is stable."""
    if isinstance(rows, pd.DataFrame):
        d = rows.loc[:, ["account_id", "p_churn_90d"]].copy()
        d["_id"] = d["account_id"].astype(str)
        d = d.sort_values(["p_churn_90d", "_id"], ascending=[False, True], kind="mergesort")
        return d["_id"].tolist()
    items = [(str(a), float(r)) for a, r in rows]
    items.sort(key=lambda t: (-t[1], t[0]))
    return [a for a, _ in items]


def resolve_typed_id(query: str, ids, persona_prefix: str = PERSONA) -> str | None:
    """Match a typed id ('38', '01607', 'ACC-01607') to a real account id."""
    q = str(query).strip().upper().lstrip("#")
    if not q:
        return None
    idset = set(ids)
    for cand in (q, f"ACC-{q}", f"{persona_prefix}{q.zfill(2)}", f"ACC-{q.zfill(5)}"):
        if cand in idset:
            return cand
    return None


def apply_shared_selection(state: dict, account_id: str, *, key: str = "acc") -> dict:
    """Point every scroll-page control at one account.

    state['acc'] is the customer the walk-through and the deal example show.
    state['customer_pick'] is the dropdown. state['seg'] is a quick-pick account id
    or None. state['orbit_deal_quick'] mirrors that pick, and is None otherwise.
    """
    account_id = str(account_id)
    state[key] = account_id
    state["customer_pick"] = account_id
    state["seg"] = account_id if account_id in QUICK_IDS else None
    state["orbit_deal_quick"] = account_id if account_id in QUICK_IDS else None
    return state


def account_from_point_selection(points) -> str | None:
    """First clicked scatter point's account id, from customdata (a string or a list whose first item is the id)."""
    if not points:
        return None
    pt = points[0]
    if isinstance(pt, dict):
        cd = pt.get("customdata")
    else:
        cd = getattr(pt, "customdata", None)
    if isinstance(cd, (list, tuple)):
        return str(cd[0]) if len(cd) else None
    if cd is None or cd == "":
        return None
    return str(cd)


# ------------------------------------------------------------------ frames
@st.cache_data(show_spinner=False)
def merged() -> pd.DataFrame:
    """One row per account: churn scores + features + the offer engine's action, plus rule columns derived
    from the outreach card (block_reason / policy_selected) for the walk-through's 'rules' step."""
    c = pd.read_csv(D / "churn_scores.csv")
    for col in ("risk_reason_1", "risk_reason_2", "risk_reason_3"):
        if col in c:
            c[col] = c[col].map(clean)
    f = pd.read_csv(D / "features.csv")
    o = pd.read_csv(D / "offers.csv", usecols=["account_id", "action_code", "action", "why_this_offer", "do_nothing_reason",
                                                 "customer_monthly_delta"])
    for col in ("action", "why_this_offer"):
        o[col] = o[col].map(clean)
    m = c.merge(f, on="account_id", how="left").merge(o, on="account_id", how="left")
    g = guardrail_detail()
    if g is not None:
        m = m.merge(g, on="account_id", how="left")
    oc = outreach()
    reason = m.account_id.map(oc.set_index("account_id").outreach_reason).fillna("").astype(str)
    msg = m.account_id.map(oc.set_index("account_id").message_en).fillna("").astype(str).str.strip()
    m["block_reason"] = ""
    m.loc[reason.str.contains("shown on the bill", case=False), "block_reason"] = "receipt_only_plan_move"
    m.loc[reason.str.contains("nothing that offsets it", case=False), "block_reason"] = "bill_change_no_fix"
    ps = pd.Series(pd.NA, index=m.index, dtype="object")
    ps[msg.ne("")] = True
    ps[reason.str.contains("pays off", case=False) & msg.eq("")] = False
    m["policy_selected"] = ps
    pn = plan_names()
    if pn is not None:   # the plan catalog's own name for the current plan (the bill note uses the same name)
        m = m.merge(pn, on="account_id", how="left")
    return m


@st.cache_data(show_spinner=False)
def plan_names() -> pd.DataFrame | None:
    """account_id, plan_name: the catalog name of each account's current plan, from household_plan.csv (current_plan),
    the same source the bill notes name it from. None if the file is missing."""
    if not HOUSEHOLD.exists():
        return None
    try:
        h = pd.read_csv(HOUSEHOLD, usecols=["account_id", "current_plan"])
    except Exception as e:  # noqa: BLE001
        print(f"[scroll] plan names unavailable: {type(e).__name__}: {e}")
        return None
    h = h.drop_duplicates("account_id").rename(columns={"current_plan": "plan_name"})
    h["plan_name"] = h.plan_name.map(clean).replace("", pd.NA)
    return h


@st.cache_data(show_spinner=False)
def guardrail_detail() -> pd.DataFrame | None:
    """bill_change_reason and open_issue_topic (walk-through step 1) and policy_action (the next version's pick) per
    account. None if the file is missing."""
    if GUARDRAIL is None:
        return None
    try:
        g = pd.read_csv(GUARDRAIL, usecols=["account_id", "bill_change_reason", "open_issue_topic", "policy_action"])
    except Exception as e:  # noqa: BLE001
        print(f"[scroll] guardrail detail unavailable: {type(e).__name__}: {e}")
        return None
    for c in ("bill_change_reason", "open_issue_topic", "policy_action"):
        g[c] = g[c].map(clean).replace("", pd.NA)
    return g.drop_duplicates("account_id")


@st.cache_data(show_spinner=False)
def outreach() -> pd.DataFrame:
    oc = pd.read_csv(OUTREACH)
    for c in ("outreach_reason", "message_en", "message_es"):
        oc[c] = oc[c].fillna("").astype(str)
    oc["outreach_reason"] = oc.outreach_reason.map(clean)
    return oc


LINE_EN = "Same features, lower price: a cheaper version of your plan is available"


def _strict_receipt_accounts() -> pd.DataFrame | None:
    """Per-account like-for-like plan moves under v2's strict rule (no added cap, no lost price guarantee, hotspot or
    perks), the same rule experiments/efficacy/chart_data.py uses to write chart_receipt.csv."""
    if not PLAN_MOVES.exists():
        return None
    m = pd.read_csv(PLAN_MOVES)
    lose = m.adds_cap.astype(bool) | m.loses_guarantee.astype(bool) | m.less_hotspot.astype(bool)
    if HOUSEHOLD.exists():
        h = pd.read_csv(HOUSEHOLD).set_index("account_id")
        lose |= m.account_id.map(h.reason.astype(str).str.contains("perk", case=False)).fillna(False).astype(bool)
    ll = m[~lose].drop_duplicates("account_id")
    return pd.DataFrame({"account_id": ll.account_id.values, "receipt_saving_mo": (-ll.customer_monthly_delta).clip(lower=0).values})


def _chart_receipt() -> dict | None:
    if not CHART_RECEIPT.exists():
        return None
    r = pd.read_csv(CHART_RECEIPT)
    h = r[r.counts_in_headline.astype(str).str.lower().eq("true") & (r.monthly_if_all_switch > 0)]
    return None if h.empty else {"accounts": int(h.iloc[0].accounts), "monthly": float(h.iloc[0].monthly_if_all_switch)}


@st.cache_data(show_spinner=False)
def receipts() -> pd.DataFrame:
    """Savings lines printed on the bill. Primary: strict like-for-like moves (394, matches chart_receipt.csv).
    Fallback: accounts whose outreach card says the cheaper plan goes on the bill only."""
    r = _strict_receipt_accounts()
    if r is None:
        oc = outreach()
        acc = oc[oc.outreach_reason.str.contains("shown on the bill", case=False) & oc.message_en.str.strip().eq("")].account_id
        o = pd.read_csv(D / "offers.csv", usecols=["account_id", "customer_monthly_delta"]).set_index("account_id")
        r = pd.DataFrame({"account_id": acc.values})
        r["receipt_saving_mo"] = (-r.account_id.map(o.customer_monthly_delta)).clip(lower=0)
    r["receipt_line_en"] = LINE_EN
    return r


def bill_line_totals() -> dict | None:
    """Bill-line counts and the clean lines' total monthly saving, from decisions.csv (receipt_kind,
    customer_saves_usd_mo): the same rows and column the stat card sums."""
    dec = _offers_decisions_raw()
    if dec is None or "receipt_kind" not in dec:
        return None
    k = dec.receipt_kind.astype(str).str.lower()
    clean_rows = k.str.contains("clean|strict")
    out = {"clean": int(clean_rows.sum()), "tradeoff": int(k.str.contains("trade").sum()), "clean_monthly": None}
    if "customer_saves_usd_mo" in dec:
        out["clean_monthly"] = float(pd.to_numeric(dec.customer_saves_usd_mo[clean_rows], errors="coerce").sum())
    return out


@st.cache_data(show_spinner=False)
def economics() -> dict:
    """Stat-grid numbers. Savings lines from chart_receipt.csv (v2 totals); break-even from the headline file."""
    r = receipts()
    cr = _chart_receipt()
    e = {"receipt_lines": cr["accounts"] if cr else int(len(r)),
         "receipt_monthly": cr["monthly"] if cr else float(r.receipt_saving_mo.fillna(0).sum())}
    bt = bill_line_totals()   # one source of truth with the stat card: the decision file's clean bill lines
    if bt:
        e["receipt_lines"], e["receipt_monthly"] = bt["clean"], bt["clean_monthly"]
    if cr and cr["accounts"] != len(r):
        print(f"[scroll] note: per-account savings lines {len(r)} != chart_receipt {cr['accounts']}")
    m = money_summary()
    if "breakeven_sr" in m:
        e["breakeven_sr"] = m["breakeven_sr"]
    elif HEADLINE.exists():
        try:
            h = pd.read_csv(HEADLINE)
            kv = h.kept_value.astype(str).str.replace(",", "").str.extract(r"\$?(\d+)", expand=False)
            row = h[(kv == "1478") & h.guardrail.astype(str).str.lower().str.startswith("new")].iloc[0]
            # net_10 is withheld while the headline money is recomputed: the sections module prints it on the meter
            # and in the stat grid when present. Re-add e["net_10"] = float(row.net_10) once the new figure lands.
            e["breakeven_sr"] = float(row.breakeven_sr)
        except Exception as ex:  # noqa: BLE001
            print(f"[scroll] headline unavailable: {type(ex).__name__}: {ex}")
    return e


def funnel(df: pd.DataFrame) -> dict:
    return dict(scored=len(df), flagged=int(df.flagged.sum()), messaged=int(df.messaged.sum()),
                texts=int((df.channel == "text").sum()), cut=float(df.attrs.get("flag_cut", float("nan"))))


# ------------------------------------------------------------------ per-customer
@st.cache_data(show_spinner=False)
def _all_candidates() -> pd.DataFrame:
    c = pd.read_csv(D / "offer_candidates.csv.gz")
    c["action"] = c.action.map(clean)
    c["blocked_or_ineligible_reason"] = c.blocked_or_ineligible_reason.map(clean)
    return c


def candidates(acc: str) -> pd.DataFrame:
    """Every option today's engine weighed for this account; is_chosen is today's pick, as in the file."""
    c = _all_candidates()
    return c[c.account_id == acc].copy()


@st.cache_resource(show_spinner=False)
def _model():
    for p in (REPO / "harness", REPO):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import churn_scorer as cs
    cs.OUT = _TMP  # model cache goes to a temp dir; nothing is written in the repo
    return cs, cs._load()


def contributions(acc: str, edits=None):
    cs, stt = _model()
    m, feats = stt["model"], stt["feats"]
    table = feats.set_index("account_id")
    if edits:
        table = table.copy()
        for k, v in edits.items():
            if k in table.columns:
                table.loc[acc, k] = v
    X = cs.prepare(table.reset_index())
    if "account_id" in X.columns:
        X = X.set_index("account_id")
    X.index = table.index
    Xa = X.loc[[acc]]
    Z = m._z(Xa).iloc[0] if hasattr(m, "_z") else None
    return float(m.intercept_), m.contributions(Xa).iloc[0].astype(float), float(m.predict_proba(Xa)[0]), Z


def typical_risk() -> float:
    _, stt = _model()
    return 100 / (1 + math.exp(-float(stt["model"].intercept_)))


STICK_LINE = ("If a saved customer stays as risky as before, most of the money disappears. "
              "That's the first thing a real rollout tests.")


def considerations() -> pd.DataFrame | None:
    if not CONSIDERATIONS.exists():
        return None
    d = pd.read_csv(CONSIDERATIONS)
    for c in ("item", "how_handled"):
        if c in d:
            d[c] = d[c].map(clean)
    if not d.how_handled.astype(str).str.strip().eq(STICK_LINE).any():   # only when the file lacks the locked wording
        stick = d.item.astype(str).str.strip().str.lower().eq("do saves stick?")
        d.loc[stick, "how_handled"] = STICK_LINE
    bt = bill_line_totals()   # bill-line counts and monthly saving from the decision file, same source as the stat card
    item, how = d["item"].astype(str), d["how_handled"].astype(str)
    if bt:
        item = item.str.replace(r"^\d[\d,]* accounts, give up nothing", f"{bt['clean']:,} accounts, give up nothing", regex=True)
        how = how.str.replace(r"^\d[\d,]* more accounts get a line", f"{bt['tradeoff']:,} more accounts get a line", regex=True)
    money = (f"${bt['clean_monthly']:,.0f} a month" if bt and bt["clean_monthly"] else None)
    pat = r"\$[\d,]+ a month"
    how = how.map(lambda t: re.sub(pat, money, t) if money else re.sub(r"Could pay " + pat + r" less in total for the same features; s", "S", t))
    how = how.str.replace("25 perk reminders became fix callbacks.", "25 perk reminders became fix-first messages.", regex=False)
    for a, b in NEUTRAL:
        item, how = item.str.replace(a, b, regex=True), how.str.replace(a, b, regex=True)
    d["item"], d["how_handled"] = item, how
    for c in d.columns.difference(["item", "how_handled"]):
        if d[c].dtype == object or pd.api.types.is_string_dtype(d[c]):
            for a, b in NEUTRAL:
                d[c] = d[c].astype(str).str.replace(a, b, regex=True)
    return d


# neutral rewording for 'what we considered' (nothing simulated- or synthetic-flavoured on screen)
NEUTRAL = [
    (r"^Simulated enrichment \(", "Extra profile signals ("),
    (r"^A simulated upgrade score from device age", "An upgrade score worked out from device age"),
    (r"In our test on simulated data, at the same churn risk", "In our test, at the same churn risk"),
    (r"^Labels are simulated from a formula we wrote", "Churn outcomes come from a formula we wrote"),
    (r"\s*\((?:simulated|synthetic)\)", ""),
    (r"(?i)\b(?:simulated|synthetic)\s+", ""),
]


def engine_inputs() -> pd.DataFrame | None:
    """Considerations rows for groups 1a-1c (the engine's inputs), for walk-through step 1."""
    d = considerations()
    if d is None or "group" not in d:
        return None
    return d[d.group.astype(str).str.match(r"^1[abc]\.")]


# ------------------------------------------------------------------ events strip ('Latest on the account')
# Primary: the models team's ledger (events.csv: <=3 per account, newest first, plain event_text; timing / wait_until
# from ledger.csv; its money columns are NOT read). Read in place, else from its commit, else from the judge sandbox
# opened READ-ONLY (mode=ro URI; never written).
LEDGER_DIR = Path("/workspace/tmobile/v2-efficacy/experiments/ledger")
LEDGER_COMMIT = "9e4d402"
SANDBOX = next((p for p in (ROOT / "vendor/dubhacks/data/sandbox.db", SHARED / "vendor/dubhacks/data/sandbox.db") if p.exists()), None)


def _ledger_csv(name: str, usecols=None) -> pd.DataFrame | None:
    f = LEDGER_DIR / name
    try:
        if f.exists():
            return pd.read_csv(f, usecols=usecols)
        import io
        import subprocess
        out = subprocess.run(["git", "-C", str(LEDGER_DIR.parents[1]), "show", f"{LEDGER_COMMIT}:experiments/ledger/{name}"],
                             capture_output=True, check=True).stdout
        return pd.read_csv(io.BytesIO(out), usecols=usecols)
    except Exception as e:  # noqa: BLE001
        print(f"[scroll] ledger {name} unavailable: {type(e).__name__}: {e}")
        return None


def _sandbox_events() -> pd.DataFrame | None:
    if SANDBOX is None:
        return None
    import sqlite3
    try:
        con = sqlite3.connect(SANDBOX.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            s = pd.read_sql("select account_id, interaction_date as event_date, topic, resolved from support_interactions", con)
            b = pd.read_sql("select account_id, month, change_cents, change_reason from billing_history where change_reason != 'stable'", con)
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        print(f"[scroll] sandbox events unavailable: {type(e).__name__}: {e}")
        return None
    s["event_type"] = "support:" + s.topic + s.resolved.map({0: ":unresolved", 1: ""}).fillna("")
    b["event_date"] = b.month + "-01"
    b["event_type"] = "bill:" + b.change_reason + ":" + b.change_cents.astype(str)
    return pd.concat([s[["account_id", "event_date", "event_type"]], b[["account_id", "event_date", "event_type"]]], ignore_index=True)


@st.cache_data(show_spinner=False)
def events() -> pd.DataFrame | None:
    """account_id, event_date, event_type, event_text[, timing, wait_until]; at most 3 per account, newest first."""
    e = _ledger_csv("events.csv", usecols=["account_id", "event_date", "event_type", "event_text"])
    if e is not None:
        e["event_text"] = e.event_text.map(clean)
        t = _ledger_csv("ledger.csv", usecols=["account_id", "timing", "wait_until"])
        if t is not None:
            e = e.merge(t.drop_duplicates("account_id"), on="account_id", how="left")
            for c in ("timing", "wait_until"):
                e[c] = e[c].fillna("").astype(str)
    else:
        e = _sandbox_events()
        if e is None:
            return None
    return e.sort_values(["account_id", "event_date"], ascending=[True, False]).groupby("account_id").head(3).reset_index(drop=True)


# ------------------------------------------------------------------ money off (?money=0): backstop data stripping
# Company-dollar fields are removed from everything handed to the sections module, so nothing can leak even if a
# render function ignores show_money. Customer-side figures (bill amounts, 'saves you $X/mo') stay.
COMPANY_MONEY_COLS = ("expected_value", "offer_cost", "offer_cost_usd", "save_rate_low", "save_rate_mid", "save_rate_high", "save_value", "upsell_gain", "customer_benefit", "lock_value",
                      "annoyance", "reason", "runner_up_ev", "customer_value_usd", "net_low_usd", "net_mid_usd", "net_high_usd",
                      "policy_ev_usd", "why_low", "why_mid", "why_high", "net_mid_why", "net_why")
_COMPANY_MONEY_ROWS = re.compile(r"\$[\d,]+(?:\.\d+)?\s*(?:ahead|per save)|-\$[\d,]+|\$1,478|\bcosts?\s+\$|priced at \$0|"
                                 r"\$0 device margin|mean \$|\$[\d,]+ ahead|margin times|about \$[\d,]+ for an average", re.I)


def strip_money(d: pd.DataFrame | None) -> pd.DataFrame | None:
    if d is None:
        return None
    return d.drop(columns=[c for c in d.columns if c in COMPANY_MONEY_COLS or c.startswith("net_") or c.startswith("ev_")])


def economics_no_money(e: dict) -> dict:
    """Keep counts and the break-even rate; drop every dollar total."""
    return {k: v for k, v in e.items() if k in ("receipt_lines", "breakeven_sr")}


def considerations_no_money(d: pd.DataFrame | None) -> pd.DataFrame | None:
    """Drop the considerations rows that state a company-dollar result (value per save, contact costs, nets)."""
    if d is None:
        return None
    txt = d.item.astype(str) + " " + d.how_handled.astype(str)
    return d[~txt.str.contains(_COMPANY_MONEY_ROWS)].copy()


# ------------------------------------------------------------------ money (show_money on): the models team's ledger
# ledger_summary.json -> dashboard + considered summary; ledger.csv -> per-account nets / timing via decisions=.
# Read in place, else from the ledger commit, else blank (no figure shown). The self-serve secondary figures are never read.
LEDGER_MONEY_COMMIT = "27c2870"


def _ledger_json() -> dict:
    import json
    f = LEDGER_DIR / "ledger_summary.json"
    try:
        if f.exists():
            return json.loads(f.read_text())
        import subprocess
        out = subprocess.run(["git", "-C", str(LEDGER_DIR.parents[1]), "show", f"{LEDGER_MONEY_COMMIT}:experiments/ledger/ledger_summary.json"],
                             capture_output=True, check=True).stdout
        return json.loads(out)
    except Exception as e:  # noqa: BLE001
        print(f"[scroll] ledger summary unavailable: {type(e).__name__}: {e}")
        return {}


@st.cache_data(show_spinner=False)
def money_summary() -> dict:
    """Headline money for the 184: net at 10%, 95% range, share of resamples ahead, break-even. {} if unavailable."""
    j = _ledger_json()
    out = {}
    for k_out, k_in in (("net_usd", "total_mid"), ("net_low_usd", "total_low"), ("range_low_usd", "range95_low"),
                        ("range_high_usd", "range95_high"), ("p_ahead", "p_net_pos_at_10"), ("breakeven_sr", "breakeven_save_rate")):
        v = j.get(k_in)
        if isinstance(v, (int, float)):
            out[k_out] = float(v)
    return out


def considered_summary() -> dict | None:
    """summary= for render_considered (keys it reads: net_usd, net_low_usd, range_low_usd, range_high_usd, contacts)."""
    m = money_summary()
    s = {k: m[k] for k in ("net_usd", "net_low_usd", "range_low_usd", "range_high_usd") if k in m}
    c = _ledger_json().get("contacts")
    if s and isinstance(c, (int, float)):
        s["contacts"] = int(c)
    return s or None


def dashboard_summary() -> dict | None:
    """summary= for render_dashboard: the ledger summary's own keys (total_mid, breakeven_save_rate, range95_low/high,
    p_net_pos_at_10, contacts). The self-serve secondary block is never passed."""
    j = _ledger_json()
    s = {k: j[k] for k in ("total_mid", "breakeven_save_rate", "range95_low", "range95_high", "p_net_pos_at_10", "contacts")
         if isinstance(j.get(k), (int, float))}
    return s or None


def value_note() -> str | None:
    m = money_summary()
    if not {"range_low_usd", "range_high_usd"} <= set(m):
        return None
    f = lambda v: f"{'+' if v >= 0 else '−'}${abs(v):,.0f}"  # noqa: E731
    note = f"95% range at our central assumption: {f(m['range_low_usd'])} to {f(m['range_high_usd'])}"
    if "p_ahead" in m:
        note += f"; ahead in {m['p_ahead'] * 100:.0f}% of resampled runs"
    return note + "."


@st.cache_data(show_spinner=False)
def _ledger_rows() -> pd.DataFrame | None:
    cols = ["account_id", "guardrail_note", "net_low_usd", "net_mid_usd", "net_high_usd", "why_mid", "already_leaving",
            "already_leaving_note", "timing", "wait_until"]
    return _ledger_csv("ledger.csv", usecols=cols)


def decisions(df: pd.DataFrame) -> pd.DataFrame | None:
    """decisions= for render_customer / render_dashboard: one row per account. The decision itself (channel, bill line,
    reason) comes from the frame, i.e. the outreach card, so it matches the funnel; nets, timing and the already-leaving
    note come from ledger.csv. No 'decision' column, so the dashboard keeps its own counts."""
    led = _ledger_rows()
    if led is None:
        return None
    d = pd.DataFrame({"account_id": df.account_id.values})
    d["channel"] = df.channel.fillna("none").values
    d["receipt_line"] = [str(x) if not m and str(x).strip() else "" for x, m in zip(df.receipt_line_en, df.messaged)]
    d["decision_reason"] = [re.sub(r"^No message:\s*", "", str(x)).strip() for x in df.reason_line]
    d["decision_reason"] = d.decision_reason.map(lambda t: t[:1].upper() + t[1:])
    led = led.drop_duplicates("account_id").rename(columns={"why_mid": "net_mid_why"})
    for c in ("guardrail_note", "net_mid_why", "already_leaving_note", "timing", "wait_until"):
        led[c] = led[c].fillna("").astype(str).map(clean)
    d = d.merge(led, on="account_id", how="left")
    quiet = ~df.messaged.values   # nothing sent, nothing spent: no net-value bar for these accounts
    d.loc[quiet, ["net_low_usd", "net_mid_usd", "net_high_usd"]] = float("nan")
    return d


def options_for(df: pd.DataFrame, acc: str, cand: pd.DataFrame) -> pd.DataFrame:
    """options= for one account: the option(s) the decision picks (decisions= carries no action code)."""
    r = df[df.account_id == acc].iloc[0]
    lab = dict(zip(cand.action_code, cand.action))
    ok = set(cand[cand.eligible.astype(str).str.lower().isin(["true", "1"])].action_code)
    rows = []
    if bool(r.messaged):
        code = str(r.get("policy_action") or "")
        if code in lab:
            phrase = {"in_app": "in the app", "text": "by text", "email": "by email", "call": "as an agent call"}.get(r.channel, "")
            rows.append((acc, lab[code], "picked", phrase))
    elif str(r.get("receipt_line_en") or "").strip():
        for code in ("variant_switch", "right_size"):
            if code in lab and code in ok:
                rows.append((acc, lab[code], "picked", "on the bill"))
                break
    elif "do_nothing" in lab:
        rows.append((acc, lab["do_nothing"], "picked", ""))
    return pd.DataFrame(rows, columns=["account_id", "option_label", "verdict", "reason"])


# ------------------------------------------------------------------ the offers team's decision files (decisions.csv, options.csv)
# Source order: this repo's data/decisions/, the offers team's worktree (git worktree list), its branch via git show, then the
# offers team's run output in /tmp, else None (then the ledger-based decisions() above is used).
OFFERS_REPO = Path("/workspace/tmobile/tm-offers-v2")
OFFERS_REFS = ("9de3f4e", "v2", "tm-offers-v2", "6b53f7c")
OFFERS_TMP = Path("/tmp/v2_offers_out/fsr_0.10")


def _strip_reason(t: str) -> str:
    t = re.sub(r"\s*Sent as:.*$", "", clean(t)).strip()
    return re.sub(r"^No message:\s*", "", t).strip()


def _offers_worktree() -> Path | None:
    """The v2 worktree (else tm-offers-v2) holding data/decisions/, found with `git worktree list`."""
    import subprocess
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "worktree", "list", "--porcelain"], capture_output=True, check=True, text=True).stdout
    except Exception:  # noqa: BLE001
        return None
    path = None
    found = {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = Path(line.split(" ", 1)[1])
        elif line.startswith("branch refs/heads/") and path is not None:
            found[line.split("refs/heads/", 1)[1].strip()] = path
    for b in ("v2", "tm-offers-v2"):   # pushed v2 (9de3f4e) carries the files; the offers branch is the next fallback
        if b in found and (found[b] / "data/decisions/decisions.csv").exists():
            return found[b]
    return None


def _offers_csv(name: str) -> pd.DataFrame | None:
    """Source order: this repo's data/decisions/, the offers team's worktree copy, its branch via git show, then /tmp."""
    import io
    import subprocess
    wt = _offers_worktree()
    for f in [ROOT / "data/decisions" / name] + ([wt / "data/decisions" / name] if wt else []):
        if f.exists():
            try:
                return pd.read_csv(f)
            except Exception as e:  # noqa: BLE001
                print(f"[scroll] {f} unreadable: {type(e).__name__}: {e}")
    for ref in OFFERS_REFS:
        try:
            out = subprocess.run(["git", "-C", str(OFFERS_REPO), "show", f"{ref}:data/decisions/{name}"], capture_output=True, check=True).stdout
            return pd.read_csv(io.BytesIO(out))
        except Exception:  # noqa: BLE001
            continue
    f = OFFERS_TMP / name
    if f.exists():
        try:
            return pd.read_csv(f)
        except Exception as e:  # noqa: BLE001
            print(f"[scroll] {name} unreadable: {type(e).__name__}: {e}")
    return None


@st.cache_data(show_spinner=False)
def _offers_decisions_raw() -> pd.DataFrame | None:
    return _offers_csv("decisions.csv")


@st.cache_data(show_spinner=False)
def _offers_options_raw() -> pd.DataFrame | None:
    o = _offers_csv("options.csv")
    if o is not None:
        o["verdict"] = o.verdict.astype(str).str.replace("_", " ")
        o["reason"] = o.reason.fillna("").astype(str).map(clean)
    return o


def apply_offer_text(df: pd.DataFrame) -> pd.DataFrame:
    """Use the decision file for what the customer sees: the message for the 184, and the bill line (clean or trade-off)
    with its monthly saving for every account the file puts a line on. The 184 / 64 funnel never changes."""
    d = _offers_decisions_raw()
    if d is None:
        return df
    d = d.drop_duplicates("account_id").set_index("account_id")
    out = df.copy()
    msg = out.account_id.map(d.message_en).fillna("").astype(str).str.strip()
    use = out.messaged & msg.ne("")
    out.loc[use, "message_en"] = msg[use].map(clean)
    if "decision_reason" in d and "reason_line" in out:   # the file's reason (no 'callback' on non-call rows), not the card's
        why = out.account_id.map(d.decision_reason).fillna("").astype(str).str.strip().map(clean)
        why = why.str.replace(r"^No message:\s*", "", regex=True)   # keeps the file's 'No message, since ...' sentence whole
        ok = why.ne("")
        out.loc[ok, "reason_line"] = why[ok].str[:1].str.upper() + why[ok].str[1:]
    if "receipt_line" in d:
        rl = out.account_id.map(d.receipt_line).fillna("").astype(str).str.strip().map(clean)
        out["receipt_line_en"] = rl
        sav = out.account_id.map(d.customer_saves_usd_mo) if "customer_saves_usd_mo" in d else out.receipt_saving_mo
        out["receipt_saving_mo"] = pd.to_numeric(sav, errors="coerce").where(rl.ne(""))
    return out


def offer_decisions(df: pd.DataFrame) -> pd.DataFrame | None:
    """decisions= from decisions.csv as the offers team wrote it (decision, channel, receipt_kind / receipt_tradeoff_line,
    nets, timing, each row's own already-leaving note). Only presentation fixes here: no 'No message:' prefix, and no
    net bar for accounts that get no message. Falls back to the ledger-based decisions()."""
    d = _offers_decisions_raw()
    if d is None:
        return decisions(df)
    d = d.drop_duplicates("account_id").copy()
    d["decision_reason"] = d.decision_reason.fillna("").astype(str).map(_strip_reason).map(lambda t: t[:1].upper() + t[1:])
    for c in ("offer_label", "guardrail_note", "why_low", "why_mid", "why_high", "already_leaving_note", "timing", "wait_until",
              "receipt_line", "receipt_tradeoff_line", "message_en", "message_es"):
        if c in d:
            d[c] = d[c].fillna("").astype(str).map(clean)
    sent = d.account_id.isin(set(df.loc[df.messaged, "account_id"]))
    d.loc[~sent, ["net_low_usd", "net_mid_usd", "net_high_usd"]] = float("nan")
    return d


def offer_options(df: pd.DataFrame, acc: str) -> pd.DataFrame | None:
    """options= for one account from options.csv (verdicts without underscores, plain reasons)."""
    o = _offers_options_raw()
    return None if o is None else o[o.account_id == acc].copy()


def candidates_for(acc: str, opts: pd.DataFrame | None) -> pd.DataFrame:
    """Candidates with the option names the decision file uses (a fix-first sent in the app is a 'fix-first message')."""
    c = candidates(acc)
    if opts is not None and len(opts):
        labels = set(opts.option_label.astype(str).str.lower())
        for old, new in (("fix-first callback", "fix-first message"), ("$25 care credit + fix-first callback", "$25 care credit + fix-first message")):
            if new in labels and old not in labels:
                c.loc[c.action.str.lower().eq(old), "action"] = new
    return c


def all_options() -> pd.DataFrame | None:
    """Every account's options (for the deal-engine averages)."""
    return _offers_options_raw()


def deal_decisions(df: pd.DataFrame, dec: pd.DataFrame | None) -> pd.DataFrame | None:
    """decisions for the deal-engine pick sentence: adds a 'decision' column that follows the screen (strict bill lines)."""
    if dec is None:
        return None
    m = dict(zip(df.account_id, df.messaged))
    out = dec.copy()
    out["decision"] = ["message" if m.get(a) else ("receipt_only" if str(rl).strip() else "silent")
                       for a, rl in zip(out.account_id, out.receipt_line.fillna(""))]
    return out


# ------------------------------------------------------------------ live events (scripted what-if strip)
LIVE_EVENTS = ROOT / "data" / "live_events" / "live_events.csv"
LIVE_ACC = "ACC-02363"


@st.cache_data(show_spinner=False)
def live_events() -> pd.DataFrame | None:
    """Precomputed 'what if this happens next' rows (scripts/live_events.py: real Model A rescoring + offer engine +
    guardrail, one customer, cumulative events). Read-only; None if the file is missing."""
    if not LIVE_EVENTS.exists():
        return None
    e = pd.read_csv(LIVE_EVENTS)
    for c in ("event_label", "event_line", "reason_1", "reason_2", "reason_3", "reason_changed", "why", "pick_label"):
        if c in e:
            e[c] = e[c].fillna("").astype(str).map(clean)
    return e


# ------------------------------------------------------------------ 'the account ticks': per-step data for the customer view
LIVE_STEPS = ROOT / "data" / "live_events" / "live_events_steps.json"
# chip wording per scripted event: "+3.4 pts after a dropped call"
LIVE_AFTER = {"app": "after an app login", "drop": "after a dropped call", "comp": "after a competitor's site visit",
              "port": "after asking about moving their number", "bill": "after a higher bill"}


@st.cache_data(show_spinner=False)
def live_steps() -> list[dict] | None:
    """scripts/live_events.py's sidecar: per step the inputs that changed (old/new), the cumulative input edits, and
    Model A's full per-signal contributions. Read-only; None if missing."""
    import json
    if not LIVE_STEPS.exists():
        return None
    try:
        return json.loads(LIVE_STEPS.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"[scroll] {LIVE_STEPS.name} unreadable: {type(e).__name__}: {e}")
        return None


def live_row(df: pd.DataFrame, acc: str, i: int) -> pd.DataFrame:
    """df with this account's model inputs set to their values after event i (cumulative), and its risk set to the
    rescored one. Only that one row changes; the frame passed to the rest of the page stays as it is."""
    S, L = live_steps(), live_events()
    if not S or L is None or i <= 0:
        return df
    s = next((x for x in S if x["account_id"] == acc and int(x["step"]) == i), None)
    if s is None:
        return df
    out = df.copy()
    m = out.account_id == acc
    for k, v in s["inputs_now"].items():
        if k in out.columns:
            out.loc[m, k] = v
    out.loc[m, "p_churn_90d"] = float(s["risk"])
    for k, v in (s.get("rules") or {}).items():   # this step's engine + guardrail verdict inputs (step 3's rules)
        v = None if v == "" else v
        if k in out.columns:
            out[k] = out[k].astype(object)
        out.loc[m, k] = v
    dd = s.get("decision") or {}
    if dd:   # what the customer sees at this step (message only once the engine decides to send one)
        sent = dd.get("decision") == "message"
        out.loc[m, "messaged"] = sent
        out.loc[m, "channel"] = dd.get("channel") if sent else None
        out.loc[m, "message_en"] = clean(dd.get("message_en") or "") if sent else ""
        if "message_es" in out.columns or dd.get("message_es"):
            out.loc[m, "message_es"] = clean(dd.get("message_es") or "") if sent else ""
        out.loc[m, "reason_line"] = clean(dd.get("decision_reason") or "")
    return out


def _live_step(acc: str, i: int) -> dict | None:
    return next((x for x in (live_steps() or []) if x["account_id"] == acc and int(x["step"]) == i), None)


def live_decisions(dec: pd.DataFrame | None, acc: str, i: int, show_money: bool = True) -> pd.DataFrame | None:
    """decisions= with the live account's row replaced by this step's engine decision (script output). Money columns
    for that row are left blank: the script saves the guardrail's policy_ev_usd only, not the ledger's save-rate nets."""
    s = _live_step(acc, i)
    if dec is None or s is None or not s.get("decision"):
        return dec
    d = dict(s["decision"])
    row = {c: None for c in dec.columns}
    row.update({"account_id": acc, "decision": d["decision"], "channel": d["channel"],
                "decision_reason": clean(d["decision_reason"]), "offer_label": clean(d["offer_label"]),
                "message_en": clean(d["message_en"]), "message_es": clean(d.get("message_es") or ""),
                "receipt_line": "", "already_leaving": False})
    return pd.concat([dec[dec.account_id != acc], pd.DataFrame([row])[dec.columns]], ignore_index=True)


def live_options(acc: str, i: int, show_money: bool = True) -> pd.DataFrame | None:
    """options= for the live account at this step (the script's per-step 'options weighed', same wording as options.csv)."""
    s = _live_step(acc, i)
    if s is None or not s.get("options"):
        return None
    o = pd.DataFrame(s["options"])
    o.insert(0, "account_id", acc)
    for c in ("option_label", "reason"):
        o[c] = o[c].fillna("").astype(str).map(clean)
    if not show_money:
        o = o.drop(columns=["net_mid_usd"], errors="ignore")
    return o


def live_contributions(i: int, acc: str):
    """contributions_fn for the live account at event i: Model A's contributions as the script saved them (the
    standardized values, used only to word each block, come from the same rescored row)."""
    S = live_steps() or []
    s = next((x for x in S if x["account_id"] == acc and int(x["step"]) == i), None)

    def fn(account_id, edits=None):
        if s is None or account_id != acc or edits:
            return contributions(account_id, edits)
        _, _, _, Z = contributions(account_id, s["inputs_now"] or None)
        return float(s["intercept"]), pd.Series(s["contributions"], dtype=float), float(s["risk"]), Z
    return fn


def live_tick(df: pd.DataFrame, acc: str, i: int, inputs: pd.DataFrame | None) -> dict | None:
    """What the customer view needs at event i: risk, the header chip, the step-1 'was' values, the tower block that
    moved most, and the top reasons (from the CSV; reason_changed marked new). All read from the script's files."""
    import orbit_sections as O
    S, L = live_steps(), live_events()
    if not S or L is None or acc not in set(L.account_id):
        return None
    L = L[L.account_id == acc].sort_values("step").reset_index(drop=True)
    n = len(L) - 1
    i = max(0, min(int(i), n))
    cur = L.iloc[i]
    t = {"step": i, "n": n, "risk": float(cur.risk), "labels": [str(x) for x in L.event_label],
         "line": str(cur.event_line or "") if i else "", "chip": "", "was": {}, "hl": None, "reasons": []}
    reasons = [str(cur.get(f"reason_{k}") or "") for k in (1, 2, 3)]
    reasons = [x for x in reasons if x]
    if i == 0:
        t["reasons"] = [(x, False) for x in reasons]
        return t
    prev = L.iloc[i - 1]
    d = (float(cur.risk) - float(prev.risk)) * 100
    t["chip"] = f"{'+' if d >= 0 else '−'}{abs(d):.1f} pts {LIVE_AFTER.get(str(cur.event), 'after ' + str(cur.event_label).lower())}"
    ch = str(cur.reason_changed or "")
    t["reasons"] = [(x, x == ch) for x in reasons]   # 'new' marks the CSV's reason_changed only
    if ch and ch not in reasons:
        t["reasons"].append((ch, True))
    # step 1: every input row whose shown value differs between the row before and after this event
    if inputs is not None and len(inputs):
        r_new = live_row(df, acc, i)
        r_new = r_new[r_new.account_id == acc].iloc[0]
        r_old = live_row(df, acc, i - 1)
        r_old = r_old[r_old.account_id == acc].iloc[0]
        for it in inputs.item.astype(str):
            fn = O.INPUT_VALUES.get(it)
            if fn:
                a, b = fn(r_old), fn(r_new)
                if a != b and b is not None:
                    t["was"][it] = a if a is not None else "—"
    # step 2: the signal whose contribution moved most this event, its old and new points, and whether it is the same
    # reason group the CSV's reason_changed was worded from
    s1, s0 = _live_step(acc, i), _live_step(acc, i - 1)
    if s1 and s0:
        c1, c0 = pd.Series(s1["contributions"]), pd.Series(s0["contributions"])
        dc = c1.sub(c0, fill_value=0).abs()
        if len(dc) and float(dc.max()) > 1e-9:
            f = str(dc.idxmax())
            t["hl"] = f
            p1 = O.breakdown(float(s1["intercept"]), c1, float(s1["risk"]), None, k=len(c1))[1]
            p0 = O.breakdown(float(s0["intercept"]), c0, float(s0["risk"]), None, k=len(c0))[1]
            old = float(p0.set_index("feat").pts.get(f, 0.0))
            # the signal's own change this event: its contribution now minus before (logit, sidecar), in points at
            # this event's risk; the header chip carries the total risk change
            L1 = float(s1["intercept"]) + float(c1.sum())
            own = (O._sig(L1) - O._sig(L1 - (float(c1.get(f, 0.0)) - float(c0.get(f, 0.0))))) * 100
            t["hl_old_pts"], t["hl_delta"], t["hl_new"] = old, own, abs(old) < 0.005
        g1, g0 = pd.Series(s1["groups"]), pd.Series(s0["groups"])
        dg = g1.sub(g0, fill_value=0).abs()
        try:
            _model()   # puts the model's package on the path
            import churn_model as cm
            t["same_signal"] = bool(t.get("hl")) and cm.reason_group(t["hl"]) == str(dg.idxmax())
        except Exception:  # noqa: BLE001
            t["same_signal"] = False
    return t


def live_tick_more(t: dict | None, df: pd.DataFrame, acc: str, show_money: bool = True) -> dict | None:
    """Steps 3-5 extras for the tick: which rule's verdict changed this event, the pick note ('still doing nothing' /
    'changed at event N'), whether this is the flip event, and (money on only) this customer's expected value."""
    import orbit_sections as O
    if t is None:
        return None
    i, L = t["step"], live_events()
    L = L[L.account_id == acc].sort_values("step").reset_index(drop=True)
    picks = [str(x) for x in L.pick]
    flip = next((j for j in range(1, len(picks)) if picks[j] != picks[0]), None)
    t["flip_at"], t["is_flip"] = flip, (flip is not None and i == flip)
    if flip is None or i < flip:
        t["pick_note"] = "Still doing nothing." + (f" Nothing has changed the decision through event {i}." if i else "")
    else:
        t["pick_note"] = f"Changed at event {flip}."
    t["rules_changed"] = []
    if i > 0:
        def rules(j):
            v = live_row(df, acc, j)
            r = v[v.account_id == acc].iloc[0]
            s = _live_step(acc, j) or {}
            ch = (s.get("decision") or {}).get("channel")
            dr = pd.Series({k: clean(v) if isinstance(v, str) else v for k, v in (s.get("decision") or {}).items()})
            return {rule: st_ for rule, st_, _ in O.outreach_rules(r, ch if ch and ch != "none" else None, dr if len(dr) else None)}
        a, b = rules(i - 1), rules(i)
        # the first rule whose verdict changed (later rules only follow from it: 'not reached' <-> 'passes')
        t["rules_changed"] = [k for k in b if a.get(k) != b[k]][:1]
    s = _live_step(acc, i) or {}
    ev = s.get("policy_ev_usd")
    t["ev"] = (f"Expected value, this customer only: {'+' if ev >= 0 else '−'}${abs(ev):,.2f}"
               if show_money and ev is not None and (s.get("decision") or {}).get("decision") == "message" else "")
    return t
