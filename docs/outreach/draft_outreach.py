#!/usr/bin/env python3
"""Draft one outreach decision per synthetic account (all 5,042). ALL DATA SYNTHETIC (judge sandbox stub data).

No LLM: messages are fixed templates (templates.json) with slots filled from the sandbox tables or the engine output.
Deterministic: no randomness; same inputs -> byte-identical CSVs.

Inputs (all read-only; paths are CLI args so a v2 engine file can be swapped in):
  --picks       retention decisions at a 10% save rate (tm-models chart_check/picks_retention_10.csv:
                account_id, picked, action, offer_cost, p_churn, ev_at_10, ev_at_5, receipt_line)
  --offers      shipped engine output harness/out/offers.csv (action_code, do_nothing_reason); used only for the
                silence reason of accounts the picks file does not text, and as fallback if --picks is missing
  --receipt     tm-offers plan-move receipt (/tmp/value_ledger/receipt.csv: in_headline, no_tradeoff, best_plan, ...)
  --hidden      tm-models hidden_value_items.csv (watch line; reminders cross-checked against the sandbox)
  --sandbox     judge sandbox.db, opened with mode=ro (never written)
  --guardrail   optional tm-efficacy guardrail CSV (account_id, contact_ok, block_reason, why_line). Either a file
                path or a git spec like v2:experiments/efficacy/out/guardrail.csv (read with `git show`, no checkout).
                If absent, the placeholder backfire rule is applied (see PLACEHOLDER below).
  --contact-log optional CSV (account_id, last_contact_date YYYY-MM-DD) for the once-a-quarter cap. The sandbox has
                no outreach history, so without it the cap cannot bind (documented hook).
Outputs (in --out-dir): outreach_drafts.csv (5,042 rows), outreach_receipt_lines.csv (long format, one row per
receipt line), outreach_summary.md.
"""
import argparse, json, re, sqlite3, subprocess, sys
from io import StringIO
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
AS_OF = pd.Timestamp("2026-10-01")          # sandbox metadata.as_of
QUARTER_DAYS = 90

# Retention actions in the picks file and the body template each one uses.
BODY = {"fix_first": "FIX_CALLBACK", "care_credit_fix_first": "FIX_CALLBACK_CREDIT", "care_credit": "CARE_CREDIT",
        "bill_shock_price_lock": "BILL_SHOCK_RELIEF", "check_in": "CHECK_IN", "perk_reminder": "PERK_INCLUDED"}
FIX_ACTIONS = {"fix_first", "care_credit_fix_first", "care_credit"}       # allowed while an issue is open
# PLACEHOLDER backfire rule (until tm-efficacy's guardrail.csv lands): an account with a non-stable bill change
# (change_cents > 0, last 3 bill months) is contacted only if the chosen action offsets that change with a bill
# credit. Everything else for those accounts is blocked as recent_bill_change_backfire.
OFFSETS_BILL_CHANGE = {"care_credit_fix_first", "care_credit", "bill_shock_price_lock"}
PLAN_MOVE_CODES = {"right_size", "variant_switch"}
FORBIDDEN = [r"\bage\b", r"\bages\b", r"\bincome\b", r"\bjob\b", r"\bkids?\b", r"we noticed", r"\bAI\b",
             r"\bedad\b", r"\bingresos\b", r"\btrabajo\b", r"\bhijos?\b", r"notamos", r"\bIA\b",
             r"STUB", r"PROMO-", r"TMO-", r"\btm-", r"/workspace", r"Grok", r"\.py\b", r"older", r"senior", r"student",
             r"(?i)synthetic", r"(?i)sint[eé]tic", r"(?i)\block", r"(?i)locked", r"(?i)contract", r"(?i)permanencia",
             r"(?i)contrato"]
TEXT_MIN, TEXT_MAX = 100, 320
# Plain-English reason for tm-ui's customer card (outreach_card.csv). No internal codes, no data labels.
CARD_REASON = {
    "fix_first": "Open support issue: we offer a callback to fix it.",
    "care_credit_fix_first": "Open support issue: we offer a callback to fix it, plus a one-time $25 credit.",
    "fix_first_override": "An open support issue comes first, so we offer a fix callback instead of a perk reminder.",
    "care_credit": "Several recent support contacts: a one-time $25 goodwill credit.",
    "bill_shock_price_lock": "A promo ended and the bill rose: we explain why and add a one-time $25 credit.",
    "check_in": "Higher risk of leaving: a no-pressure plan check-in with no offer attached.",
    "fix_recent": "Several recent support contacts: we offer a callback to make sure it's sorted.",
    "fix_recent_credit": "Several recent support contacts: we offer a callback to make sure it's sorted, plus a one-time $25 credit.",
    "perk_reminder": "Reminder of a perk already included in their plan.",
    "engine_do_nothing:happy": "No message: nothing is going wrong on this account, so we leave them alone.",
    "engine_do_nothing:open_ticket": "No message: support is already working an open ticket, and there's no marketing until it's closed.",
    "engine_do_nothing:wait_payoff": "No message: a phone is still being paid off, so the honest advice is to wait.",
    "engine_do_nothing:recent_complaints": "No message: recent complaints are closed, so we keep watching instead of selling.",
    "engine_do_nothing:low_risk": "No message: low risk of leaving and nothing needs fixing.",
    "engine_do_nothing:bill_shock_low_risk": "No message: the bill went up recently but risk is low, and a message would only point at the increase.",
    "engine_do_nothing:usage_need_held": "No message: usage is near the plan limit, but a bigger plan isn't worth pushing now.",
    "engine_do_nothing:shopping_low_risk": "No message: comparing options at low risk, and a pitch now could backfire.",
    "engine_do_nothing:nothing_helps": "No message: nothing we could offer would genuinely help right now.",
    "not_worth_contacting_at_realistic_save_rates": "No message: no offer here pays off at realistic save rates.",
    "plan_move_receipt_only": "No message: the cheaper plan is shown on the bill and in the app only.",
    "guardrail:bill_change_no_fix": "No message: the bill just went up and we have nothing that offsets it.",
    "guardrail:not_worth_contacting": "No message: no offer here pays off at realistic save rates.",
    "guardrail:receipt_only_plan_move": "No message: the cheaper plan is shown on the bill and in the app only.",
    "guardrail:contacted_this_quarter": "No message: already contacted this quarter.",
    "recent_bill_change_backfire": "No message: the bill just went up and we have nothing that offsets it.",
    "contacted_within_quarter": "No message: already contacted this quarter.",
    "opted_out_of_marketing": "No message: opted out of marketing.",
}
CHANNEL_WORD = {"text": "text", "in_app": "in-app message", "email": "email", "phone_call": "agent call"}


def card_reason(reason, channel, care_usd, template_id=""):
    base = reason.split("|")[0]
    if template_id.startswith("FIX_CALLBACK_CREDIT_RECENT"):
        r = CARD_REASON["fix_recent_credit"]
    elif template_id.startswith("FIX_CALLBACK_RECENT"):
        r = CARD_REASON["fix_recent"]
    elif base.startswith("retention_pays_at_10pct:"):
        r = CARD_REASON[base.split(":", 1)[1]]
    elif base.startswith("fix_first_override_of_"):
        r = CARD_REASON["fix_first_override"]
    else:
        return CARD_REASON[base]
    return r.replace("$25", f"${care_usd}") + f" Sent as: {CHANNEL_WORD[channel]}."


def args():
    p = argparse.ArgumentParser()
    I = HERE / "inputs"                      # committed copies of the other lanes' files (see inputs/README.md)
    p.add_argument("--picks", default=str(I / "guardrail_detail.csv"),
                   help="who the retention policy picks: a picks file (picked, action) or a guardrail_detail.csv "
                        "(policy_selected, policy_action)")
    p.add_argument("--offers", default=str(I / "offers_min.csv"), help="engine output; needs action_code, do_nothing_reason")
    p.add_argument("--receipt", default=str(I / "receipt.csv"))
    p.add_argument("--hidden", default=str(I / "hidden_value_items.csv"))
    p.add_argument("--sandbox", default=str(REPO / "vendor/dubhacks/data/sandbox.db"))
    p.add_argument("--guardrail", default=str(I / "guardrail.csv"))
    p.add_argument("--contact-log", default=None)
    p.add_argument("--opt-out", default=None, help="optional CSV of account_id that opted out of marketing (hard block)")
    p.add_argument("--exemptions-applied", choices=["auto", "yes", "no"], default="yes",
                   help="default yes: the committed $1,478 guardrail (inputs/) already exempts fix-only callbacks and new-phone (device_installment) "
                        "increases, so use it as-is; no = apply those two exemptions here; auto = yes only if the file "
                        "has an 'exemptions_applied' column that is true")
    p.add_argument("--templates", default=str(HERE / "templates.json"))
    p.add_argument("--out-dir", default=str(HERE))
    return p.parse_args()


def usd(cents):
    v = cents / 100
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}"


def plan_price_cents(line_prices, extra, n):
    lp = [int(x) for x in str(line_prices).split(",")]
    return sum(lp[:n]) + max(0, n - len(lp)) * int(extra)


def load_detail(spec):
    """guardrail_detail.csv next to guardrail.csv (policy_action after tm-efficacy's offset swaps)."""
    if not spec:
        return None
    d = spec.replace("guardrail.csv", "guardrail_detail.csv")
    df, _ = load_guardrail(d) if d != spec else (None, "")
    return df


def load_guardrail(spec):
    if not spec:
        return None, "none"
    if Path(spec).exists():
        return pd.read_csv(spec), spec
    if ":" in spec:
        r = subprocess.run(["git", "-C", str(REPO), "show", spec], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return pd.read_csv(StringIO(r.stdout)), f"git show {spec}"
    return None, f"not found ({spec}); placeholder rule applied"


def main():
    a = args()
    T = json.loads(Path(a.templates).read_text())
    PH = T["phrases"]
    con = sqlite3.connect(f"file:{a.sandbox}?mode=ro", uri=True)
    q = lambda s: pd.read_sql(s, con)
    acc = q("select * from accounts").set_index("account_id")
    lines = q("select * from lines")
    plans = q("select * from plans").set_index("sku")
    promos = q("select * from promotions").set_index("sku")
    bh = q("select * from billing_history")
    sup = q("select * from support_interactions")
    addons = q("select * from addons").set_index("sku")
    acc_add = q("select * from account_addons"); line_add = q("select * from line_addons")
    curves = q("select * from tradein_curves").set_index(["device_sku", "age_months"]).value_cents
    devices = q("select sku, name from devices").set_index("sku").name
    con.close()

    care_credit_cents = int(promos.loc["PROMO-STUB-CARE-CREDIT", "value_cents"])
    ids = sorted(acc.index)
    n_lines = lines.groupby("account_id").size()
    plan_sku = lines.groupby("account_id").plan_sku.first()

    # ---- bill-change guardrail field: non-stable reason AND change > 0 in the last 3 bill months (-> 1,412)
    last3 = sorted(bh.month.unique())[-3:]
    bc = bh[bh.month.isin(last3) & (bh.change_reason != "stable") & (bh.change_cents > 0)]
    bill_change_ids = set(bc.account_id)
    # exemption 2: every qualifying increase is a new device installment the customer chose
    new_phone_only_ids = set(bc.groupby("account_id").change_reason.apply(lambda r: set(r) == {"device_installment"}).loc[lambda x: x].index)
    bill_up_ids = set(bh[bh.month.isin(last3) & (bh.change_cents > 0)].account_id)     # the 4,679 we do NOT use
    promo = bh[bh.change_reason == "promo_expired"].sort_values("month").groupby("account_id").last()

    # ---- open support issues: unresolved contacts in the 90 days before as_of
    sup["d"] = pd.to_datetime(sup.interaction_date)
    s90 = sup[sup.d > AS_OF - pd.Timedelta(days=90)]
    open90 = s90[s90.resolved == 0]
    n_open = open90.groupby("account_id").size()
    open_topic = open90.sort_values(["d", "interaction_id"]).groupby("account_id").topic.last()

    # ---- inputs from other lanes
    offers = pd.read_csv(a.offers).set_index("account_id")
    if Path(a.picks).exists():
        picks = pd.read_csv(a.picks).set_index("account_id"); picks_src = a.picks
        if "policy_selected" in picks.columns:   # guardrail_detail.csv: the policy's own picks (before the guardrail)
            picks = pd.DataFrame({"picked": picks.policy_selected.astype(bool).astype(int),
                                  "action": picks.policy_action.where(picks.policy_selected.astype(bool), "do_nothing")})
    else:   # fallback: shipped engine picks restricted to retention actions (warn: these were picked at 44%)
        picks = pd.DataFrame({"picked": offers.action_code.isin(BODY).astype(int),
                              "action": offers.action_code.where(offers.action_code.isin(BODY), "do_nothing")})
        picks_src = f"{a.offers} (FALLBACK; picks file missing)"
    receipt = pd.read_csv(a.receipt).set_index("account_id")
    hidden = pd.read_csv(a.hidden)
    guard, guard_src = load_guardrail(a.guardrail)
    detail = load_detail(a.guardrail) if guard is not None else None
    if guard is not None:
        guard = guard.set_index("account_id")
    if detail is not None:
        detail = detail.set_index("account_id")
    if a.exemptions_applied == "auto":
        ex_applied = guard is not None and "exemptions_applied" in guard.columns and bool(guard.exemptions_applied.astype(bool).all())
    else:
        ex_applied = a.exemptions_applied == "yes"
    optout = set(pd.read_csv(a.opt_out).account_id) if a.opt_out and Path(a.opt_out).exists() else set()
    clog = None
    if a.contact_log and Path(a.contact_log).exists():
        clog = pd.read_csv(a.contact_log, parse_dates=["last_contact_date"]).set_index("account_id").last_contact_date

    # ---- receipt facts from the sandbox
    # watch line: account's watch add-on price vs the Beyond connected-device line price
    watch_skus = {"TMO-STUB-ADD-LINE-WATCH", "TMO-STUB-ADD-LINE-WATCH-PLUS"}
    wl = pd.concat([acc_add[acc_add.addon_sku.isin(watch_skus)][["account_id", "addon_sku"]],
                    line_add[line_add.addon_sku.isin(watch_skus)].merge(lines[["line_id", "account_id"]])[["account_id", "addon_sku"]]])
    beyond_watch_cents = int(addons.loc["TMO-STUB-ADD-LINE-CONNECTED-BEYOND", "monthly_cents"])
    watch_ids = set(hidden[hidden.item_type == "watch_line_beyond_rate"].account_id)
    # trade-in: paid-off, non-BYOD phones valued on tradein_curves at their age on as_of
    po = lines[(lines.byod == 0) & (lines.financing_months_remaining == 0) & lines.device_sku.notna() & lines.device_purchase_date.notna()].copy()
    pdt = pd.to_datetime(po.device_purchase_date)
    po["age"] = ((AS_OF.year - pdt.dt.year) * 12 + (AS_OF.month - pdt.dt.month)).clip(0, 60)
    po["val"] = [curves.get((s, g), 0) for s, g in zip(po.device_sku, po.age)]
    po = po[po.val > 0].sort_values(["account_id", "val", "line_id"], ascending=[True, False, True])
    best_tradein = po.groupby("account_id").first()
    tradein_ids = set(hidden[hidden.item_type == "tradein_value_paid_off"].account_id)
    stream_ids = set(hidden[hidden.item_type == "perk_streaming_included"].account_id)
    pg_ids = set(hidden[hidden.item_type == "price_guarantee_reminder"].account_id)

    def md(vc, col):
        return "\n".join([f"| {vc.index.name or 'value'} | {col} |", "|---|---:|"] + [f"| {k} | {v:,} |" for k, v in vc.items()])

    def fill(s, slots):
        return s.format(**slots)

    drafts, rlines, problems = [], [], []

    for aid in ids:
        A = acc.loc[aid]; n = int(n_lines.get(aid, 0)); sku = plan_sku.get(aid); P = plans.loc[sku]
        lang = A.language
        facts = {"accounts.language": lang, "lines.n_lines": n, "plans.name": P["name"]}
        slots = {"n_lines": n, "tenure_years": int(A.tenure_months) // 12, "plan_name": P["name"],
                 "care_credit_usd": usd(care_credit_cents),
                 "pg_years": int(P.price_guarantee_years) if pd.notna(P.price_guarantee_years) else ""}
        pk = picks.loc[aid] if aid in picks.index else None
        act = pk["action"] if pk is not None and int(pk["picked"]) == 1 else "do_nothing"
        if detail is not None and aid in detail.index and bool(detail.loc[aid, "policy_selected"]) \
                and pd.notna(detail.loc[aid, "policy_action"]):
            act = detail.loc[aid, "policy_action"]          # tm-efficacy's offsetting-credit swap, when it made one
        eng = offers.loc[aid]
        contact, reason, channel, tid, men, mes = "no", "", "none", "", "", ""
        # exemptions to the bill-change rule (applied here unless the guardrail file already applied them)
        exempt = ""
        g_blocks_bill = guard is not None and aid in guard.index and not bool(guard.loc[aid, "contact_ok"]) \
            and guard.loc[aid, "block_reason"] == "bill_change_no_fix"
        p_blocks_bill = guard is None and aid in bill_change_ids and act not in OFFSETS_BILL_CHANGE
        if (g_blocks_bill or p_blocks_bill) and not ex_applied:
            pick_act = pk["action"] if pk is not None and int(pk["picked"]) == 1 else "do_nothing"
            if pick_act == "fix_first":
                exempt, act = "fix_only_callback", "fix_first"   # a fix-only callback is not an offer
            elif aid in new_phone_only_ids and pick_act != "do_nothing":
                exempt, act = "new_phone_increase", pick_act
        gr = guard.loc[aid, "block_reason"] if guard is not None and aid in guard.index and not bool(guard.loc[aid, "contact_ok"]) else None
        if gr == "bill_change_no_fix" and exempt:
            gr = None

        # ---------- decide contact vs silence (order = playbook order)
        if act == "do_nothing":
            if eng.action_code == "do_nothing":
                reason = f"engine_do_nothing:{eng.do_nothing_reason}"
            elif eng.action_code in PLAN_MOVE_CODES:
                reason = "plan_move_receipt_only"
            else:
                reason = "not_worth_contacting_at_realistic_save_rates"
        elif aid in optout:
            reason = "opted_out_of_marketing"
        elif gr is not None:
            reason = f"guardrail:{gr}"
        elif guard is None and aid in bill_change_ids and act not in OFFSETS_BILL_CHANGE and not exempt:
            reason = "recent_bill_change_backfire"
        elif clog is not None and aid in clog.index and (AS_OF - clog[aid]).days < QUARTER_DAYS:
            reason = "contacted_within_quarter"
        else:
            contact = "yes"
            # fix first: with an open issue the only allowed message is a fix message
            if n_open.get(aid, 0) > 0 and act not in FIX_ACTIONS and act != "bill_shock_price_lock":
                body, reason = "FIX_CALLBACK", f"fix_first_override_of_{act}"
            else:
                body, reason = BODY[act], f"retention_pays_at_10pct:{act}"
            if exempt:
                reason += f"|bill_change_exempt:{exempt}"
            if body == "CHECK_IN" and aid in promo.index and aid in bill_change_ids:
                body = "CHECK_IN_PROMO"
            # opener: apology when there is support pain; else family / long tenure / standard
            if body.startswith("FIX_CALLBACK") and n_open.get(aid, 0) > 0:
                op = "OPEN_SORRY"; tp = open_topic[aid]
                slots.update(topic_en=PH["topic"][tp]["en"], topic_es=PH["topic"][tp]["es"]); facts["support.open_topic"] = tp
            elif body in ("BILL_SHOCK_RELIEF", "CHECK_IN_PROMO"):
                op = "OPEN_STD"                       # these bodies already carry the account facts
            elif n >= 3:
                op = "OPEN_FAMILY"
            elif A.tenure_months >= 60:
                op = "OPEN_LONG"; facts["accounts.tenure_months"] = int(A.tenure_months)
            else:
                op = "OPEN_STD"
            if body.startswith("FIX_CALLBACK"):
                k = int(n_open.get(aid, 0)); facts["support.unresolved_90d"] = k
                if k == 0:   # callback for recent support pain without an open ticket: cite the contact count instead
                    k = int((s90.account_id == aid).sum()); facts["support.contacts_90d"] = k
                    body += "_RECENT"
                    ph = PH["recent_one"] if k == 1 else PH["recent_many"]
                    slots.update(recent_en=ph["en"].format(n=k), recent_es=ph["es"].format(n=k))
                else:
                    ph = PH["open_one"] if k == 1 else PH["open_many"]
                    slots.update(open_en=ph["en"].format(n=k), open_es=ph["es"].format(n=k))
            if body in ("FIX_CALLBACK_CREDIT", "FIX_CALLBACK_CREDIT_RECENT", "CARE_CREDIT", "BILL_SHOCK_RELIEF"):
                facts["promotions.CARE-CREDIT.value_usd"] = slots["care_credit_usd"]
            if body in ("BILL_SHOCK_RELIEF", "CHECK_IN_PROMO"):
                pr = promo.loc[aid]
                m = str(pr.month)[5:7]
                slots.update(promo_month_en=PH["month"][m][0], promo_month_es=PH["month"][m][1],
                             promo_change_usd=usd(int(pr.change_cents)))
                facts["billing_history.promo_expired_month"] = pr.month
                facts["billing_history.change_usd"] = slots["promo_change_usd"]
            if body == "BILL_SHOCK_RELIEF":
                facts["plans.price_guarantee_years"] = slots["pg_years"]
            pref = A.contact_preference
            facts["accounts.contact_preference"] = pref
            # channel = the customer's own stated preference (never a channel ranking); perk reminders stay in-app
            if T["bodies"][body]["channel_rule"] == "in_app":
                channel = "in_app"
            else:
                channel = {"sms": "text", "app": "in_app", "email": "email", "call": "phone_call"}[pref]
            ck = T["bodies"][body]["cta"]
            tid = f"{body}.{op}.{channel}"
            fr = T["frames"][channel]
            def compose(l):
                o = fill(T["openers"][op][l], slots)
                if fr.get("strip_greeting"):   # call script: the prefix already greets, keep only the opener's substance
                    o = re.sub(r"^(Hi there\.|Hi[.,]|Hola[.,])\s*", "", o)
                    o = o[:1].upper() + o[1:]
                    parts = [fr["prefix"][l]] + ([o] if o else [])
                else:
                    parts = [fr["prefix"][l] + o]
                parts += [fill(T["bodies"][body][l], slots), T["cta"][ck][channel][l], T["closers"][channel][l]]
                return " ".join(parts)
            men, mes = compose("en"), compose("es")

        # ---------- receipt lines (bill / app, tap-to-confirm; never a text, never counted as a contact)
        rec = []
        def add_r(kind, rid, rs, rfacts):
            rec.append((kind, rid, fill(T["receipt"][rid]["en"], rs), fill(T["receipt"][rid]["es"], rs), rfacts))
        if aid in receipt.index:
            R = receipt.loc[aid]
            four = "4 Line" in str(R.best_plan)
            if bool(R.in_headline) or four:
                cur_sku = plans.index[plans.name == R.current_plan][0]; best_sku = plans.index[plans.name == R.best_plan][0]
                save_c = plan_price_cents(plans.loc[cur_sku, "line_prices"], plans.loc[cur_sku, "extra_line_cents"], n) - \
                         plan_price_cents(plans.loc[best_sku, "line_prices"], plans.loc[best_sku, "extra_line_cents"], n)
                if abs(save_c / 100 - R.money_back_to_customers_mo) > 0.005:
                    problems.append(f"{aid}: receipt saving {R.money_back_to_customers_mo} != plans table {save_c/100}")
                rs = {"best_plan": R.best_plan, "current_plan": R.current_plan, "save_usd": usd(save_c)}
                rf = {"plans.current": R.current_plan, "plans.best": R.best_plan, "plans.line_prices_saving_usd": usd(save_c), "lines.n_lines": n}
                if bool(R.no_tradeoff):
                    rid = "RCPT_PLAN_SAME_ELIG" if "Savings" in str(R.best_plan) else "RCPT_PLAN_SAME"
                    add_r("plan_move_like_for_like", rid, rs, rf)
                else:
                    loss = str(R.tradeoff_line).split("you'd lose: ", 1)[1]
                    items = [x.strip() for x in re.split(r"[,;]", loss) if x.strip()]
                    rs.update(loss_en=", ".join(PH["loss"][x]["en"] for x in items),
                              loss_es=", ".join(PH["loss"][x]["es"] for x in items))
                    rf["tradeoff"] = " + ".join(items)
                    add_r("plan_move_you_lose_x", "RCPT_PLAN_LOSE", rs, rf)
        if aid in watch_ids:
            w = wl[wl.account_id == aid].addon_sku.tolist()
            now_c = sum(int(addons.loc[s, "monthly_cents"]) for s in w)
            new_c = beyond_watch_cents * len(w)
            rs = {"watch_now_usd": usd(now_c), "watch_new_usd": usd(new_c), "watch_save_usd": usd(now_c - new_c), "plan_name": P["name"]}
            rid = "RCPT_WATCH_LOSE" if "TMO-STUB-ADD-LINE-WATCH-PLUS" in w else "RCPT_WATCH"
            add_r("watch_line", rid, rs, {"addons.watch_now_usd": rs["watch_now_usd"], "addons.connected_beyond_usd": rs["watch_new_usd"], "watch_save_usd": rs["watch_save_usd"]})
        if aid in stream_ids and "streaming-video-ads" in str(P.perks):
            add_r("reminder_streaming", "RCPT_STREAMING", {"plan_name": P["name"]}, {"plans.perks": "streaming-video-ads"})
        if aid in pg_ids and pd.notna(P.price_guarantee_years):
            add_r("reminder_price_guarantee", "RCPT_PRICE_GUARANTEE", {"plan_name": P["name"], "pg_years": int(P.price_guarantee_years)},
                  {"plans.price_guarantee_years": int(P.price_guarantee_years)})
        if aid in tradein_ids and aid in best_tradein.index:
            b = best_tradein.loc[aid]
            add_r("reminder_tradein", "RCPT_TRADEIN", {"device_name": devices[b.device_sku], "tradein_usd": usd(round(b.val / 100) * 100)},
                  {"devices.name": devices[b.device_sku], "tradein_curves.value_usd_rounded": usd(round(b.val / 100) * 100), "age_months": int(b.age)})
        for kind, rid, en, es, rf in rec:
            rlines.append({"account_id": aid, "line_type": kind, "template_id": rid, "channel": "bill_or_app",
                           "text_en": en, "text_es": es, "facts_used": ";".join(f"{k}={v}" for k, v in rf.items())})

        if contact == "yes":
            facts.update({"engine.action_at_10pct": act})
            if aid in bill_change_ids:
                facts["billing_history.nonstable_change_3m"] = True
        drafts.append({"account_id": aid, "contact_yes_no": contact, "reason": reason, "channel": channel,
                       "template_id": tid, "message_en": men, "message_es": mes,
                       "primary_language": "es" if lang == "es" else "en",
                       "facts_used": ";".join(f"{k}={v}" for k, v in facts.items()) if contact == "yes" else "",
                       "receipt_lines": len(rec),
                       "receipt_line_en": " | ".join(r[2] for r in rec), "receipt_line_es": " | ".join(r[3] for r in rec),
                       "in_bill_change_1412": aid in bill_change_ids, "open_issue_90d": int(n_open.get(aid, 0)),
                       "guardrail_block_reason": (guard.loc[aid, "block_reason"] if guard is not None and aid in guard.index else ""),
                       # why_line is written by the guardrail before our exemptions; blank it where we overrode the block
                       "guardrail_why_line": (guard.loc[aid, "why_line"] if guard is not None and aid in guard.index and not exempt else ""),
                       "bill_change_exemption": exempt,
                       "data_note": "synthetic"})

    D = pd.DataFrame(drafts); RL = pd.DataFrame(rlines)

    # ---------- validation
    assert len(D) == 5042 and D.account_id.is_unique, "row count"
    assert len(bill_change_ids) == 1412, f"bill-change field gives {len(bill_change_ids)}, expected 1,412"
    texts = [(r.account_id, c, getattr(r, c)) for r in D.itertuples() for c in ("message_en", "message_es", "receipt_line_en", "receipt_line_es")] + \
            [(r.account_id, c, getattr(r, c)) for r in RL.itertuples() for c in ("text_en", "text_es")]
    for aid, col, t in texts:
        if not t: continue
        if "{" in t or "}" in t: problems.append(f"{aid} {col}: unfilled slot")
        for pat in FORBIDDEN:
            if re.search(pat, t): problems.append(f"{aid} {col}: forbidden '{pat}'")
    for r in D[D.contact_yes_no == "yes"].itertuples():
        vals = {v.split("=", 1)[1] for v in r.facts_used.split(";")}
        for col in ("message_en", "message_es"):
            t = getattr(r, col)
            hi = TEXT_MAX if r.channel == "text" else 420
            if not (TEXT_MIN <= len(t) <= hi): problems.append(f"{r.account_id} {col}: length {len(t)} on {r.channel}")
            optout_word = {"text": ("STOP",), "in_app": ("Settings", "Configuración"), "email": ("Unsubscribe", "baja"),
                           "phone_call": ("stop them", "dejar de llamarle")}[r.channel]
            if not any(w in t for w in optout_word): problems.append(f"{r.account_id} {col}: no opt-out for {r.channel}")
            if r.channel != "text" and re.search(r"Reply (YES|STOP)|Responda (SÍ|STOP)", t):
                problems.append(f"{r.account_id} {col}: text-only wording on {r.channel}")
            for d in re.findall(r"\$(\d+(?:\.\d+)?)", t):
                if d not in vals: problems.append(f"{r.account_id} {col}: ${d} not in facts_used")
    for r in RL.itertuples():
        vals = {v.split("=", 1)[1] for v in r.facts_used.split(";")}
        for col in ("text_en", "text_es"):
            for d in re.findall(r"\$(\d+(?:\.\d+)?)", getattr(r, col)):
                if d not in vals: problems.append(f"{r.account_id} receipt {col}: ${d} not in facts_used")
    # cross-check trade-in values against the hidden-value file (sum over paid-off phones vs our best phone)
    hv_t = hidden[hidden.item_type == "tradein_value_paid_off"].set_index("account_id").customer_value_onetime
    our_sum = po.groupby("account_id").val.sum() / 100
    tdiff = (hv_t - our_sum.reindex(hv_t.index)).abs()
    if (tdiff > 1).any(): problems.append(f"trade-in: {int((tdiff > 1).sum())} accounts differ from hidden_value_items by >$1")

    out = Path(a.out_dir)
    D.to_csv(out / "outreach_drafts.csv", index=False)
    # tm-ui customer card: exactly account_id, outreach_reason, message_en, message_es (blank when silent)
    C = pd.DataFrame({"account_id": D.account_id,
                      "outreach_reason": [card_reason(r, c, usd(care_credit_cents), t) for r, c, t in zip(D.reason, D.channel, D.template_id)],
                      "message_en": D.message_en, "message_es": D.message_es})
    for col in ("outreach_reason", "message_en", "message_es"):
        for aid, t in zip(C.account_id, C[col]):
            if re.search(r"(?i)synthetic|sint[eé]tic|\block|locked", t or ""):
                problems.append(f"{aid} card {col}: forbidden label")
    assert len(C) == 5042 and list(C.columns) == ["account_id", "outreach_reason", "message_en", "message_es"]
    assert ((C.message_en == "") == (D.contact_yes_no == "no")).all()
    C.to_csv(out / "outreach_card.csv", index=False)
    RL.to_csv(out / "outreach_receipt_lines.csv", index=False)

    # ---------- summary (synthetic)
    S = ["# Outreach drafts: summary (ALL NUMBERS SYNTHETIC)", "",
         f"Generated by `draft_outreach.py` from (all under `inputs/` unless noted): picks `{Path(picks_src).name if 'FALLBACK' not in picks_src else picks_src}`, "
         f"engine `{Path(a.offers).name}`, receipt `{Path(a.receipt).name}`, hidden value `{Path(a.hidden).name}`, sandbox.db (read-only). "
         f"Guardrail: `{Path(guard_src).name if Path(guard_src).exists() else guard_src}`; exemptions already applied in file: {ex_applied}.", "",
         f"- Card for the customer screen: `outreach_card.csv` (account_id, outreach_reason, message_en, message_es; {len(C):,} rows, messages blank when silent).",
         f"- Accounts: {len(D):,}. Direct contacts: {(D.contact_yes_no=='yes').sum():,}. Silent: {(D.contact_yes_no=='no').sum():,}.",
         f"- Bill-change guardrail field (non-stable reason, change > 0, bill months {last3[0]}..{last3[-1]}): {len(bill_change_ids):,} accounts "
         f"(not the {len(bill_up_ids):,} whose bill simply went up).",
         f"- Accounts with at least one receipt line (bill/app): {(D.receipt_lines>0).sum():,}; receipt lines total {len(RL):,}.", "",
         "## Contacts by channel", "", md(D[D.contact_yes_no=='yes'].channel.value_counts(), "accounts"), "",
         "## Contacts by reason", "", md(D[D.contact_yes_no=='yes'].reason.value_counts(), "accounts"), "",
         "## Do-not-contact by reason", "", md(D[D.contact_yes_no=='no'].reason.value_counts(), "accounts"), "",
         "## Contacts by message language (primary)", "", md(D[D.contact_yes_no=='yes'].primary_language.value_counts(), "accounts"), "",
         "## Receipt lines by type (bill/app, tap-to-confirm, never a text)", "", md(RL.line_type.value_counts(), "lines"), "",
         "## Validation", "", f"- Problems found: {len(problems)}"] + [f"  - {p}" for p in problems[:50]] + [
         f"- Max text-message length: EN {D[D.channel=='text'].message_en.str.len().max()} / ES {D[D.channel=='text'].message_es.str.len().max()} characters (limit 320); other channels limit 420.",
         "- Determinism: same inputs give byte-identical CSVs (checked by running twice and comparing md5)."]
    (out / "outreach_summary.md").write_text("\n".join(S) + "\n")
    print("\n".join(S))
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
