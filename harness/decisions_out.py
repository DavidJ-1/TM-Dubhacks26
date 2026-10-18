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
TEXT_COLS = ["decision_reason", "offer_label", "receipt_line", "message_en", "message_es"]
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
    lab = dict(eng.ACTION_LABEL)

    rows, opts, converted, new_text = [], [], [], []
    for aid in o.index:
        r, gr = o.loc[aid], g.loc[aid]
        ok = bool(gr.contact_ok) if pd.notna(gr.contact_ok) else False
        open_t = aid in topic.index
        pol = gr.policy_action if isinstance(gr.policy_action, str) else ""
        chan = CHANNEL.get(str(acc.contact_preference.get(aid, "")), "text")
        offer, line, msg_en, msg_es = "", "", "", ""
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
            reason = ("Open support issue, so the only message is about fixing it; the perk reminder is dropped."
                      if conv else f"{lab.get(offer, offer)}: worth sending at realistic save rates and it passed "
                                   "every outreach rule.")
        else:
            br = gr.block_reason if isinstance(gr.block_reason, str) else "not_worth_contacting"
            line = plan_line.get(aid, "")
            if not line and str(r.get("receipt_action", "") or "") in eng.PLAN_MOVES:
                sku = str(r.receipt_skus).split(";")[0]
                save = float(r.receipt_monthly_saving or 0)
                if save > 0:
                    line = f"{names.get(sku, 'Another plan')} would cost ${save:.0f}/mo less for your lines."
            if line and str(r.get("receipt_limited_time", "")) == "True" and "Limited-time" not in line:
                line += " Limited-time plan: check it's still offered before switching."
            decision = "receipt_only" if line else "silent"
            chan = "bill" if line else "none"
            rule = {"bill_change_no_fix": 4, "contacted_this_quarter": 5}.get(
                br, 1 if (r.action_code == "do_nothing" and br != "receipt_only_plan_move") else 2)
            if br == "bill_change_no_fix":
                reason = clean(gr.why_line) or "Bill went up recently and nothing we have offsets it, so no message."
            elif decision == "receipt_only":
                reason = "No message: the cheaper plan is shown on the bill and in the app only."
            elif str(r.get("already_leaving_save_attempt", "")) == "True":
                reason = ("No message: they asked us about moving their number, and a check-in isn't expected to "
                          "pay off at realistic save rates.")
            else:
                reason = "No message: nothing we'd offer pays off at realistic save rates."
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
            saves = float(r.get("receipt_monthly_saving", 0) or 0) if pd.notna(r.get("receipt_monthly_saving")) else 0.0
        label = lab.get(offer, "") if offer else ""
        if offer in FIX and chan != "call":       # digital fix-first: no callback promised
            label = label.replace("fix-first callback", "fix-first message")
        rows.append({"account_id": aid, "decision": decision, "channel": chan, "decided_by_rule": rule,
                     "decision_reason": money_free(clean(reason)), "offer_label": label,
                     "offer_cost_usd": round(cost, 2), "customer_saves_usd_mo": round(saves, 2),
                     "receipt_line": clean(line) if decision == "receipt_only" else "",
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
                             "reason": money_free(clean(c.blocked_or_ineligible_reason)) or "Not eligible.",
                             "net_mid_usd": None})
                continue
            ev = float(c.expected_value)
            if a == offer:
                v, why, seen_pick = "picked", "Sent.", True
            elif a in eng.PLAN_MOVES:
                v, why = "not_sent", "Plan changes are shown on the bill, never sent as a message."
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
    bad = O.reason.fillna("").map(company_money)
    assert not bad.any(), ("company money in options reason", O.loc[bad, "reason"].head(3).tolist())
    assert (O.groupby("account_id").head(1).option_label == "Do nothing").all()
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
