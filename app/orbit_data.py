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
    return m


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


@st.cache_data(show_spinner=False)
def economics() -> dict:
    """Stat-grid numbers. Savings lines from chart_receipt.csv (v2 totals); break-even from the headline file."""
    r = receipts()
    cr = _chart_receipt()
    e = {"receipt_lines": cr["accounts"] if cr else int(len(r)),
         "receipt_monthly": cr["monthly"] if cr else float(r.receipt_saving_mo.fillna(0).sum())}
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
    dec = _offers_decisions_raw()   # bill-line counts come from the decision file's receipt_kind, not the doc's old ones
    if dec is not None and "receipt_kind" in dec:
        k = dec.receipt_kind.astype(str).str.lower()
        n_clean = int(k.str.contains("clean|strict").sum())
        n_trade = int(k.str.contains("trade").sum())
        d["item"] = d["item"].astype(str).str.replace(r"^\d[\d,]* accounts, give up nothing", f"{n_clean:,} accounts, give up nothing", regex=True)
        d["how_handled"] = d["how_handled"].astype(str).str.replace(r"^\d[\d,]* more accounts get a line", f"{n_trade:,} more accounts get a line", regex=True)
    return d


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
        why = why.str.replace(r"^No message[:;,]\s*", "", regex=True)
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
              "receipt_line", "receipt_tradeoff_line", "message_en"):
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
