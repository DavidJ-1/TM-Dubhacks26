"""decisions.csv + options.csv for the demo UI (v2, tm-design spec). Numbers are synthetic (sandbox stub data); that
label stays out of every on-screen text column (David's rule). No LLM: every line comes from fields or fixed templates.

decisions.csv (one row per account, keyed like docs/outreach/outreach_card.csv), OUR columns:
  account_id, decision {message, receipt_only, silent}, channel {text, in_app, email, call, bill, none},
  decided_by_rule (OUTREACH_PLAYBOOK.md section 1 numbering; see harness/RULEBOOK.md), decision_reason, offer_label,
  offer_cost_usd, customer_saves_usd_mo, receipt_line, message_en, message_es.
  tm-models' per-account ledger (guardrail_result/note, save_rate_*/net_*/why_*, already_leaving(+note), in_holdout,
  event_* / timing / wait_until) is JOINED on account_id from experiments/ledger/ (or TM_LEDGER_PER_ACCOUNT); we do
  not compute those columns. Missing file -> those columns are absent (reported as pending).
options.csv: account_id, option_label (do nothing always first), verdict {picked, not_sent, ruled_out}, reason,
  net_mid_usd (engine expected net at the 10% field save rate; blank when ruled out).

Contact set (Grok Bot's final call): tm-models' 184 policy picks (guardrail contact_ok True). If the account has an
open (unresolved, last 90 days) support contact, the message is fix-first and any perk mention is dropped. Message text:
the outreach card's channel wording when it already matches the final offer, else our fixed fix-first templates.
Run: TM_OUT_DIR=<dir> python harness/decisions_out.py
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import offers as eng  # noqa: E402
import offer_detectors as det  # noqa: E402

POLICY_GUARDRAIL = Path(os.environ.get("TM_POLICY_GUARDRAIL",
                                       ROOT / "experiments/engine_rules/out/demo/guardrail_detail.csv"))
OUTREACH_DIR = Path(os.environ.get("TM_OUTREACH_DIR", "/workspace/tmobile/TM-Dubhacks26/docs/outreach"))
# tm-models' ledger is read from the v2 working tree at build time (not a pinned commit); env TM_LEDGER_DIR overrides,
# then this repo's experiments/ledger/ is the fallback. TM_LEDGER_PER_ACCOUNT names one file directly.
V2_LEDGER_DIR = Path(os.environ.get("TM_LEDGER_DIR", "/workspace/tmobile/v2-efficacy/experiments/ledger"))
LEDGER_DIR = ROOT / "experiments" / "ledger"
FIX = ("fix_first", "care_credit_fix_first")
CHANNEL = {"sms": "text", "app": "in_app", "email": "email", "call": "call"}
TOPIC_EN = {"billing": "your bill", "network": "your coverage", "device": "your phone",
            "plan_change": "your plan change", "cancellation_inquiry": "your account"}
TOPIC_ES = {"billing": "su factura", "network": "su cobertura", "device": "su teléfono",
            "plan_change": "su cambio de plan", "cancellation_inquiry": "su cuenta"}
FIX_EN = {
    "text": "T-Mobile: We're sorry the issue with {t} is still open. Our team is working on your open request. No "
            "sales pitch, no plan change. Reply YES to get updates here. Reply STOP to opt out.",
    "in_app": "We're sorry the issue with {t} is still open. Our team is working on your open request. Tap to see "
              "updates. No sales pitch, no plan change. Turn off these notes anytime in Settings.",
    "email": "We're sorry the issue with {t} is still open. Our team is working on your open request. Reply to this "
             "email with anything we should know. No sales pitch, no plan change. Unsubscribe anytime below.",
    "call": "Hi, this is T-Mobile calling about the open issue with {t}. We'd like to get it fixed today. No sales "
            "pitch, no plan change. If you'd rather not get calls like this, we can stop them.",
}
FIX_ES = {
    "text": "T-Mobile: Lamentamos que el problema con {t} siga abierto. Nuestro equipo está trabajando en su "
            "solicitud abierta. Sin ventas ni cambios de plan. Responda SÍ para recibir novedades aquí. Responda STOP "
            "para no recibir más.",
    "in_app": "Lamentamos que el problema con {t} siga abierto. Nuestro equipo está trabajando en su solicitud "
              "abierta. Toque para ver novedades. Sin ventas ni cambios de plan. Desactive estas notas cuando quiera en "
              "Ajustes.",
    "email": "Lamentamos que el problema con {t} siga abierto. Nuestro equipo está trabajando en su solicitud "
             "abierta. Responda a este correo con cualquier dato útil. Sin ventas ni cambios de plan. Puede darse de "
             "baja abajo.",
    "call": "Hola, le llamamos de T-Mobile por el problema abierto con {t}. Queremos resolverlo hoy. Sin ventas ni "
            "cambios de plan. Si prefiere no recibir llamadas como esta, podemos dejar de hacerlas.",
}
TEXT_COLS = ["decision_reason", "offer_label", "receipt_line", "receipt_tradeoff_line", "message_en", "message_es"]
FORBIDDEN = re.compile(r"(?i)flat \$?1,?478|synthetic|simulated|\btm-|grok|persona|stub|PROMO-|TMO-|/workspace|/tmp|\.csv|\bEV\b|"
                       r"model a\b|model b\b|david|sandbox|codename|anthropic|openai|claude")
PERK = re.compile(r"(?i)perk|streaming|incluido con|included with")


def clean(s) -> str:
    s = "" if s is None or (isinstance(s, float) and pd.isna(s)) else str(s)
    s = re.sub(r"\s*\([^()]*(?:synthetic|simulated)[^()]*\)", "", s, flags=re.I)
    s = re.sub(r"(?i)\s*(?:synthetic|simulated)(?:/simulated)?", "", s)
    s = re.sub(r"\bEV\b", "expected net", s)
    s = re.sub(r"(?i)\bsandbox\b", "account", s)
    s = re.sub(r"(?i)\bno-income upgrade model's\b", "upgrade score's", s)
    s = re.sub(r"\b(?:TMO|PROMO)-STUB-[A-Z0-9-]+", "", s)
    return re.sub(r"\s{2,}", " ", s).strip()


# 'Show money' off switch: reason/note text carries no company-money figures (net, cost, value, credits we pay).
# Allowed '$' only in the customer's own bill / savings phrasing; money lives in numeric columns.
CUSTOMER_MONEY = re.compile(r"(?i)bill went up \$[\d,.]+|\+\$[\d,.]+/mo is [\d.]+% of the \$[\d,.]+ bill|"
                            r"saves? you \$[\d,.]+(?:/mo)?|\$[\d,.]+/mo (?:less|cheaper)")
MONEY_TEXT_COLS = ["decision_reason", "guardrail_note", "already_leaving_note"]


def money_free(s: str) -> str:
    s = re.sub(r"\$[\d,.]+ (care )?credit", lambda m: "care credit" if m.group(1) else "one-time credit", s)
    s = re.sub(r"\(one-time credit, price-guarantee fact\)", "(one-time credit and price-guarantee fact)", s)
    return s


def company_money(s) -> bool:
    return "$" in CUSTOMER_MONEY.sub("", str(s))


# ---- plain, short reasons (tm-design: one sentence, <=15 words, no column names, no jargon, no "callback" off-call)
def msg_reason(offer: str, chan: str, conv: bool) -> str:
    if conv:
        return "Their open issue comes first, so we'll help fix it instead of a perk note."
    if offer in FIX:
        credit = offer == "care_credit_fix_first"
        if chan == "call":
            return ("A callback to fix their open issue plus a one-time credit is likely worth it."
                    if credit else "A callback to fix their open issue is likely worth it.")
        return ("We'll help fix it and add a one-time credit; likely worth it."
                if credit else "We'll help fix their open issue, which is likely worth it.")
    return {"check_in": "A no-pressure plan check-in is likely worth it and passed every rule.",
            "bill_shock_price_lock": "A credit for their recent bill jump is likely worth it.",
            "perk_reminder": "A reminder about a perk they already have is likely worth it.",
            }.get(offer, "This message is likely worth it and passed every outreach rule.")


PLAIN = [  # first matching clause wins; matched on the raw engine text (first clause of a ';' list)
    (r"no bill credits below", "Not likely enough to leave for a credit to make sense."),
    (r"no usage need", "Their usage doesn't call for a bigger plan."),
    (r"no unused streaming perk", "No unused streaming perk to point out."),
    (r"no cheaper discount variant", "No cheaper version of their plan that they qualify for."),
    (r"no bill shock", "Their bill hasn't jumped recently."),
    (r"no cheaper plan fits", "No cheaper plan fits how they use their lines."),
    (r"still paying off a phone", "They're still paying off their phone."),
    (r"trade-in-eligible", "They don't have a paid-off phone to trade in."),
    (r"months tenure", "They haven't been with us long enough for this yet."),
    (r"no open or network issue", "There's no open issue to fix."),
    (r"support contacts in", "Not enough recent support contacts for this to apply."),
    (r"no shopping", "No sign they're thinking of leaving."),
    (r"Home Internet", "Home Internet doesn't fit this account."),
    (r"not a family plan", "This isn't a family plan."),
    (r"child/teen line \(|no child", "There's no child or teen line on the account."),
    (r"family plan with a child", "The family upgrade already covers this move."),
    (r"upgrade gate", "Not among the customers most ready for a new phone."),
    (r"highest-risk", "They're at high risk of leaving, so they get care, not a sale."),
    (r"contacted support .* times", "They contacted support recently, so we fix things before selling."),
    (r"top plan family", "They're already on our top plan."),
    (r"no price guarantee", "Their plan has no price guarantee to point out."),
    (r"replaced by bill-shock relief", "The bill-jump credit already covers this."),
    (r"needs both the care credit", "This needs both a credit-worthy issue and an open problem."),
    (r"care-credit rule", "They don't meet the rule for a care credit."),
    (r"bill-shock guardrail", "Their bill just jumped, so we hold off on selling."),
    (r"affordability", "It would raise their bill by too much."),
    (r"cheaper eligible version", "A cheaper version of their own plan comes first."),
    (r"shopping / port-out|top driver", "They seem to be shopping around, so we don't sell to them."),
    (r"open support|fix first|open .*issue", "Their open issue comes first."),
    (r"backfire", "A cheaper-plan nudge could backfire given how their usage is changing."),
    (r"disabled|not offered|off in", "This option is turned off."),
]


def plain_reason(raw) -> str:
    s = "" if raw is None or (isinstance(raw, float) and pd.isna(raw)) else str(raw)
    s = re.sub(r"^blocked:\s*", "", s)
    s = re.sub(r"^upsell guardrail:\s*", "", s)
    for pat, out in PLAIN:
        if re.search(pat, s, flags=re.I):
            return out
    return "Not a fit for this account."


GN_REWRITE = [  # tm-models' guardrail_note shortened in OUR joined copy only (their file is untouched)
    (r"^Bill went up when a promo ended and we have nothing that offsets it, so we stay quiet\.$",
     "Bill rose when a promo ended and nothing offsets it, so we stay quiet."),
    (r"^Bill went up when a promo ended, so the message only offers to fix their open (.+) issue, with no sales pitch\.$",
     r"Promo ended and bill rose, so we only help fix their \1 issue."),
    (r"^Bill went up when a promo ended, so the message comes with a credit that offsets it\.$",
     "Promo ended and bill rose, so the message includes an offsetting credit."),
    (r"^Bill went up for a new phone payment they chose, so that doesn't hold a message back\.$",
     "Bill rose from a new phone they chose, so we can still message."),
    (r"^Bill went up for a new phone payment and we have nothing that offsets it, so we stay quiet\.$",
     "Bill rose from a new phone payment and nothing offsets it, so we stay quiet."),
    (r"^Bill went up for a new phone payment, so the message only offers to fix their open (.+) issue, with no sales pitch\.$",
     r"New phone payment raised the bill, so we only help fix their \1 issue."),
    (r"^Bill went up for a new phone payment, so the message comes with a credit that offsets it\.$",
     "New phone payment raised the bill, so the message includes an offsetting credit."),
    (r"^Bill went up after a phone payment plan changed and we have nothing that offsets it, so we stay quiet\.$",
     "Phone payment change raised the bill and nothing offsets it, so we stay quiet."),
    (r"^Bill went up after a phone payment plan changed, so the message only offers to fix their open (.+) issue, with no sales pitch\.$",
     r"Phone payment change raised the bill, so we only help fix their \1 issue."),
]


def short_note(s) -> str:
    s = "" if s is None or (isinstance(s, float) and pd.isna(s)) else str(s)
    for pat, rep in GN_REWRITE:
        s2 = re.sub(pat, rep, s)
        if s2 != s:
            return s2
    return s


IDENT = re.compile(r"\b[a-z]+_[a-z_]+\b|\b[a-z]+\.[a-z_]+\b|\(")


def reason_problem(s, call_ok: bool = False) -> str:
    """'' if s is one plain sentence <=15 words with no identifiers/parentheses (and no callback off-call)."""
    s = str(s)
    if not s:
        return ""
    if len(s.split()) > 15:
        return "more than 15 words"
    if "." in s.rstrip(".") and not re.search(r"\d\.\d", s):
        return "more than one sentence"
    if IDENT.search(s):
        return "identifier or parentheses"
    if not call_ok and re.search(r"(?i)callback", s):
        return "callback on a non-call row"
    return ""


def ledger_file() -> Path | None:
    p = os.environ.get("TM_LEDGER_PER_ACCOUNT")
    if p:
        return Path(p) if Path(p).exists() else None
    for d in (V2_LEDGER_DIR, LEDGER_DIR):
        if (d / "ledger.csv").exists():
            return d / "ledger.csv"
        if d.exists():
            for f in sorted(d.rglob("*.csv")):
                cols = pd.read_csv(f, nrows=0).columns
                if "account_id" in cols and "guardrail_result" in cols:
                    return f
    return None


def ledger_commit(lf: Path | None) -> str:
    """v2 commit the ledger file was at when we built (+ ' (uncommitted edits)' if the working copy differs)."""
    if lf is None:
        return "PENDING"
    import subprocess
    try:
        h = subprocess.run(["git", "-C", str(lf.parent), "log", "-1", "--format=%h", "--", lf.name],
                           capture_output=True, text=True, timeout=20).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(lf.parent), "status", "--porcelain", "--", lf.name],
                               capture_output=True, text=True, timeout=20).stdout.strip()
        return (h or "untracked") + (" (uncommitted edits)" if dirty else "")
    except Exception:
        return "unknown"


def load_events(lf: Path | None) -> pd.DataFrame:
    """Newest event per account from tm-models' events.csv (newest first), plus the count (max 3)."""
    if lf is None or not (lf.parent / "events.csv").exists():
        return pd.DataFrame(columns=["account_id"])
    E = pd.read_csv(lf.parent / "events.csv")
    n = E.groupby("account_id").size().rename("event_count")
    return E.groupby("account_id").head(1).merge(n, on="account_id")


# Channel vs promise: only an agent call may say we'll call. Digital fix-first messages promise a fix, not a call.
NO_CALL = [
    ("A specialist can call to make sure everything is sorted, at a time that works for you.",
     "Our team will make sure everything is sorted."),
    ("A specialist can call you to fix it at a time that works for you.", "Our team is working on your open request."),
    ("A specialist can call you to fix it, and", "Our team is working on your open request, and"),
    ("Reply YES and we'll call when it suits you.", "Reply YES and we'll set up the review."),
    ("Reply YES to set up the call.", "Reply YES to get started."),
    ("Tap to set up the call.", "Tap to get started."),
    ("Use the link below to pick a time, or reply to this email.", "Use the link below to get started, or reply to this email."),
    ("Un especialista puede llamarle para confirmar que todo quedó resuelto, cuando le convenga.",
     "Nuestro equipo se asegurará de que todo quede resuelto."),
    ("Un especialista puede llamarle para solucionarlo cuando le convenga.", "Nuestro equipo está trabajando en su solicitud abierta."),
    ("Un especialista puede llamarle para solucionarlo y", "Nuestro equipo está trabajando en su solicitud abierta y"),
    ("Responda SÍ y le llamamos cuando le convenga.", "Responda SÍ y programamos la revisión."),
    ("Responda SÍ para agendar la llamada.", "Responda SÍ para empezar."),
    ("Toque para agendar la llamada.", "Toque para empezar."),
    ("Use el enlace de abajo para elegir un horario o responda a este correo.", "Use el enlace de abajo para empezar o responda a este correo."),
]
CALL_PROMISE = re.compile(r"(?i)\bcall|llam|callback|pick a time|elegir un horario")


def no_call(txt: str) -> str:
    for a, b in NO_CALL:
        txt = txt.replace(a, b)
    return txt


def sandbox_facts():
    con = det.connect_ro()
    acc = pd.read_sql("SELECT account_id, contact_preference, language FROM accounts", con).set_index("account_id")
    sup = pd.read_sql("SELECT account_id, interaction_date, topic, resolved FROM support_interactions", con)
    as_of = pd.Timestamp(str(det.as_of(con)))
    sup["interaction_date"] = pd.to_datetime(sup.interaction_date)
    op = sup[(sup.resolved == 0) & (sup.interaction_date >= as_of - pd.Timedelta(days=90))]
    topic = op.sort_values("interaction_date").groupby("account_id").topic.last()
    return acc, topic


# Strict bill-line rule (agreed): like-for-like plan AND the customer loses nothing (value_ledger receipt.csv,
# like_for_like & no_tradeoff; tm-offers-ledger c8f5224): 394 accounts, $4,600/mo. Snapshot committed here.
STRICT_RECEIPT = Path(os.environ.get("TM_STRICT_RECEIPT", ROOT / "data/decisions/strict_receipt.csv"))
# Trade-off bill lines: every "you'd lose X" plan-move line in the data = 110 accounts (outreach_receipt_lines
# plan_move_you_lose_x). The locked ledger flags 94 of them like_for_like; the other 16 (Experience More -> Essentials 4
# Line) carry the same "you'd lose" line there with like_for_like False. A cheaper plan that gives something up is still
# shown on the bill with an explicit "you'd lose" line. Nobody goes silent for losing something.
TRADEOFF_RECEIPT = Path(os.environ.get("TM_TRADEOFF_RECEIPT", ROOT / "data/decisions/tradeoff_receipt.csv"))
AL_NOTE_OPEN = "Asked us about moving their number. We still reach out because fixing their open issue is worth it."
STALE_LEDGER = {"9e4d402", "f9629d6"}   # tm-models: money in these ledger commits is not the headline (27c2870 is)


def build(out: Path):
    o = pd.read_csv(out / "offers.csv").set_index("account_id")
    cands = pd.read_csv(out / "offer_candidates.csv")
    g = pd.read_csv(POLICY_GUARDRAIL).set_index("account_id").reindex(o.index)
    acc, topic = sandbox_facts()
    card = pd.read_csv(OUTREACH_DIR / "outreach_card.csv").set_index("account_id") \
        if (OUTREACH_DIR / "outreach_card.csv").exists() else None
    rl = pd.read_csv(OUTREACH_DIR / "outreach_receipt_lines.csv") \
        if (OUTREACH_DIR / "outreach_receipt_lines.csv").exists() else None
    plan_line = (rl[rl.line_type.str.startswith("plan_move")].groupby("account_id").text_en.first()
                 if rl is not None else pd.Series(dtype=str))
    names = dict(pd.read_sql("SELECT sku, name FROM plans", det.connect_ro()).values)
    C = cands.set_index(["account_id", "action_code"])
    strict = pd.read_csv(STRICT_RECEIPT).set_index("account_id")
    trade = pd.read_csv(TRADEOFF_RECEIPT).set_index("account_id")
    lose_x = set(rl.account_id[rl.line_type == "plan_move_you_lose_x"]) if rl is not None else set()
    plan_line = plan_line[plan_line.index.isin(strict.index)]   # only the strict like-for-like bill text
    lab = dict(eng.ACTION_LABEL)

    rows, opts, converted, new_text = [], [], [], []
    for aid in o.index:
        r, gr = o.loc[aid], g.loc[aid]
        ok = bool(gr.contact_ok) if pd.notna(gr.contact_ok) else False
        open_t = aid in topic.index
        pol = gr.policy_action if isinstance(gr.policy_action, str) else ""
        chan = CHANNEL.get(str(acc.contact_preference.get(aid, "")), "text")
        offer, line, tline, msg_en, msg_es = "", "", "", "", ""
        if ok:
            decision = "message"
            # open ticket: fix-first only; a perk reminder becomes a fix-first message with the perk dropped.
            # The bill-shock relief (forced rule, a $25 credit) and fix types are kept as picked.
            conv = open_t and pol not in FIX and pol != "bill_shock_price_lock"
            offer = "fix_first" if conv else pol
            rule = 6 if conv else 2
            cm_en = card.message_en.get(aid) if card is not None else None
            cm_es = card.message_es.get(aid) if card is not None else None
            if isinstance(cm_en, str) and cm_en and not PERK.search(cm_en) if conv else isinstance(cm_en, str) and cm_en:
                msg_en, msg_es = cm_en, cm_es
            else:
                tp = topic.get(aid, "billing")
                msg_en = FIX_EN[chan].format(t=TOPIC_EN.get(tp, "your account"))
                msg_es = FIX_ES[chan].format(t=TOPIC_ES.get(tp, "su cuenta"))
                new_text.append(aid)
            if chan != "call":
                msg_en, msg_es = no_call(msg_en), no_call(msg_es)
            if conv:
                converted.append(aid)
            reason = msg_reason(offer, chan, conv)
        else:
            br = gr.block_reason if isinstance(gr.block_reason, str) else "not_worth_contacting"
            line, other_plan, tline = "", "", ""
            if aid in strict.index:     # strict rule only: same features, lower price, nothing lost
                line = plan_line.get(aid, "") or f"Same features, lower price: {strict.savings_line[aid]}."
                if str(r.get("receipt_limited_time", "")) == "True" and "Limited-time" not in line:
                    line += " Limited-time plan: check it's still offered before switching."
            elif aid in trade.index:
                tr = trade.loc[aid]
                lose = str(tr.tradeoff_line).split("you'd lose:", 1)[-1].strip().rstrip(".")
                tline = f"Could pay ${float(tr.customer_saves_usd_mo):.0f}/mo less on {tr.best_plan}, but you'd lose {lose}."
            elif aid in lose_x or str(r.get("receipt_action", "") or "") in eng.PLAN_MOVES:
                other_plan = "not_same"
            decision = "receipt_only" if (line or tline) else "silent"
            chan = "bill" if (line or tline) else "none"
            rule = {"bill_change_no_fix": 4, "contacted_this_quarter": 5}.get(
                br, 1 if (r.action_code == "do_nothing" and br != "receipt_only_plan_move") else 2)
            if br == "bill_change_no_fix":
                why = str(gr.why_line)
                rose = ("Bill rose after a new phone payment" if "phone" in why
                        else "Bill rose recently" if "recently" in why else "Bill rose after a promo ended")
                reason = (f"{rose}; a cheaper plan is on the bill." if line
                          else f"{rose}; a cheaper plan with tradeoffs is on the bill." if tline
                          else f"{rose}, and nothing we have offsets it.")
            elif decision == "receipt_only" and tline:
                reason = "No message; a cheaper plan and what they'd lose show on the bill."
            elif decision == "receipt_only":
                reason = "No message; the cheaper plan shows on the bill and in the app."
            elif other_plan:
                reason = "A cheaper plan exists but isn't like-for-like, so we don't suggest it."
            elif str(r.get("already_leaving_save_attempt", "")) == "True":
                reason = "They asked about leaving, and a check-in isn't likely to pay off."
            else:
                reason = "No message, since nothing we could offer is likely to pay off."
        cost, saves = 0.0, 0.0
        if offer:
            if (aid, offer) in C.index:
                cr = C.loc[(aid, offer)]
                cost = float(cr.offer_cost or 0)
                d = cr.customer_monthly_delta
                saves = round(-float(d), 2) if pd.notna(d) and float(d) < 0 else 0.0
            elif offer == "fix_first":
                cost = float(eng.CONFIG["FIX_FIRST_CALLBACK_COST"])
        elif decision == "receipt_only":
            saves = float((strict if line else trade).customer_saves_usd_mo[aid])
        label = lab.get(offer, "") if offer else ""
        if offer in FIX and chan != "call":       # digital fix-first: no callback promised
            label = label.replace("fix-first callback", "fix-first message")
        rows.append({"account_id": aid, "decision": decision, "channel": chan, "decided_by_rule": rule,
                     "decision_reason": money_free(clean(reason)), "offer_label": label,
                     "offer_cost_usd": round(cost, 2), "customer_saves_usd_mo": round(saves, 2),
                     "receipt_line": clean(line) if decision == "receipt_only" else "",
                     "receipt_kind": "clean" if line else ("tradeoff" if tline else ""),
                     "receipt_tradeoff_line": clean(tline),
                     "message_en": clean(msg_en), "message_es": clean(msg_es), "_offer": offer})
        # ---- options weighed (do nothing first)
        opts.append({"account_id": aid, "option_label": "Do nothing",
                     "verdict": "not_sent" if decision == "message" else "picked",
                     "reason": "Baseline: no message, no cost." if decision == "message"
                     else money_free(clean(reason)),
                     "net_mid_usd": 0.0})
        sub = cands[cands.account_id == aid]
        seen_pick = False
        for _, c in sub.sort_values("expected_value", ascending=False).iterrows():
            a = c.action_code
            if a == "do_nothing":
                continue
            olab = lab.get(a, a)
            if a in FIX and chan != "call":
                olab = olab.replace("fix-first callback", "fix-first message")
            if str(c.eligible) != "True":
                opts.append({"account_id": aid, "option_label": olab, "verdict": "ruled_out",
                             "reason": plain_reason(c.blocked_or_ineligible_reason),
                             "net_mid_usd": None})
                continue
            ev = float(c.expected_value)
            if a == offer:
                v, why, seen_pick = "picked", "Sent.", True
            elif a in eng.PLAN_MOVES:
                v, why = "not_sent", ("Shown on the bill only: same features, lower price." if line
                                      else "Shown on the bill with what they'd lose." if tline
                                      else "Not suggested: not a like-for-like match." if aid not in strict.index
                                      else "Plan changes are shown on the bill, never sent as a message.")
            elif open_t and a not in FIX:
                v, why = "not_sent", "Open support issue: only a fix message is allowed."
            elif ev <= 0:
                v, why = "not_sent", "Expected to cost more than it brings back."
            elif ok:
                v, why = "not_sent", "One message per account; another option was sent."
            else:
                v, why = "not_sent", "Didn't pass the outreach rules for a message."
            opts.append({"account_id": aid, "option_label": olab, "verdict": v, "reason": why,
                         "net_mid_usd": round(ev, 2)})
        if offer and not seen_pick:   # sent option not among engine candidates (shouldn't happen) -> still listed
            opts.append({"account_id": aid, "option_label": label, "verdict": "picked", "reason": "Sent.",
                         "net_mid_usd": None})
    D = pd.DataFrame(rows)
    O = pd.DataFrame(opts)
    lf = ledger_file()
    lhash = ledger_commit(lf)
    if lf is not None:
        L = pd.read_csv(lf)
        keep = [c for c in L.columns if c not in D.columns or c == "account_id"]
        E = load_events(lf)
        D = L[keep].merge(D, on="account_id", how="right") if False else D.merge(L[keep], on="account_id", how="left")
        if len(E):
            D = D.merge(E, on="account_id", how="left")
        D = D.set_index("account_id").loc[L.account_id].reset_index()   # keep tm-models' ids and order
        assert ((D.guardrail_result == "pass") == (D.decision == "message")).all(), "ledger pass != our message set"
    if "guardrail_note" in D.columns:
        D["guardrail_note"] = D.guardrail_note.map(short_note)
    if "already_leaving_note" in D.columns:      # Grok Bot's wording for messaged already-leaving accounts with an open issue
        al = (D.decision == "message") & (D.already_leaving.astype(str) == "True")
        D.loc[al & D.account_id.isin(topic.index), "already_leaving_note"] = AL_NOTE_OPEN
    offer_code = D.pop("_offer")              # popped after the reorder so it stays aligned
    # ---- checks
    assert len(D) == len(o) and D.account_id.is_unique
    if card is not None:
        assert set(D.account_id) == set(card.index), "decisions.csv keys differ from outreach_card.csv"
    assert (D.decision == "message").sum() == int(g.contact_ok.fillna(False).sum())
    assert not D[D.decision != "message"].message_en.astype(bool).any()
    for c in TEXT_COLS:
        bad = D[c].astype(str).str.contains(FORBIDDEN)
        assert not bad.any(), (c, D.loc[bad, c].head(3).tolist())
    for c in ("message_en", "message_es", "offer_label"):
        bad = (D.channel != "call") & D[c].astype(str).str.contains(CALL_PROMISE)
        assert not bad.any(), ("call promised on a non-call channel", c, D.loc[bad, "account_id"].head(5).tolist())
    bad = O.reason.astype(str).str.contains(FORBIDDEN)
    assert not bad.any(), O.loc[bad, "reason"].head(3).tolist()
    for c in [c for c in MONEY_TEXT_COLS if c in D.columns]:
        bad = D[c].fillna("").map(company_money)
        assert not bad.any(), ("company money in text", c, D.loc[bad, c].head(3).tolist())
    for c in [c for c in ("decision_reason", "guardrail_note") if c in D.columns]:
        probs = [reason_problem(s, ch == "call") for s, ch in zip(D[c].fillna(""), D.channel)]
        bad = [(a, s, p) for a, s, p in zip(D.account_id, D[c], probs) if p]
        assert not bad, (c, bad[:3])
    ob = O.reason.fillna("").map(reason_problem)
    assert not ob.astype(bool).any(), O.loc[ob.astype(bool), "reason"].head(3).tolist()
    bad = O.reason.fillna("").map(company_money)
    assert not bad.any(), ("company money in options reason", O.loc[bad, "reason"].head(3).tolist())
    assert (O.groupby("account_id").head(1).option_label == "Do nothing").all()
    sent = set(D.account_id[D.decision == "message"])
    clean_ro = set(D.account_id[D.receipt_kind == "clean"])
    trade_ro = set(D.account_id[D.receipt_kind == "tradeoff"])
    assert clean_ro == set(strict.index) - sent, "strict set not fully on the bill"
    assert trade_ro == set(trade.index) - sent - set(strict.index), "trade-off set not fully on the bill"
    assert set(D.account_id[D.decision == "receipt_only"]) == clean_ro | trade_ro
    assert (D.loc[D.receipt_kind == "tradeoff", "receipt_line"] == "").all()
    assert (D.loc[D.receipt_kind == "tradeoff", "receipt_tradeoff_line"] != "").all()
    assert (D.loc[D.receipt_kind != "tradeoff", "receipt_tradeoff_line"] == "").all()
    assert set(O.loc[O.verdict == "ruled_out", "net_mid_usd"].dropna()) == set()
    info = {"converted": converted, "new_text": new_text, "ledger": lf, "ledger_commit": lhash,
            "money_pending": lf is None or lhash.split(" ")[0] in STALE_LEDGER,
            "digital_fix_first": D.loc[offer_code.isin(FIX).values & (D.channel != "call").values,
                                       "account_id"].tolist()}
    return D, O, info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("TM_OUT_DIR", str(HERE / "out")))
    a = ap.parse_args(argv)
    out = Path(a.out)
    D, O, info = build(out)
    D.to_csv(out / "decisions.csv", index=False)
    O.to_csv(out / "options.csv", index=False)
    pd.Series(info["digital_fix_first"], name="account_id").to_csv(out / "fix_first_digital.csv", index=False)
    print(f"decisions.csv {len(D)} rows {D.decision.value_counts().to_dict()}; channels "
          f"{D[D.decision == 'message'].channel.value_counts().to_dict()}; options.csv {len(O)} rows; "
          f"perk->fix-first {len(info['converted'])}; digital fix-first {len(info['digital_fix_first'])}; "
          f"ledger {info['ledger'] or 'PENDING'} @ {info['ledger_commit']}"
          f"{' (money PENDING: stale ledger commit)' if info['money_pending'] else ''}")
    return D, O, info


if __name__ == "__main__":
    main()
