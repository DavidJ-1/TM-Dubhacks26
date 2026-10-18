"""Rule 1: do-not-contact guardrail + one plain-English why_line per account.
ALL NUMBERS SYNTHETIC (sandbox stub accounts + simulated labels; not T-Mobile customer data). The word stays out of the
emitted columns on purpose (David: no such label in product output); it lives only in comments and README.md.

Ported from tm-models scratch (economics/guardrail/guardrail.py, itself a copy of experiments/efficacy/guardrail.py
with the NEW bill-change rule). No dependency on scratch paths.

Rules, highest priority first (first one that applies wins; contact_ok is True only when none applies):
 1 bill_change_no_fix      recent (last 3 billed months) non-'stable' bill increase. NEW rule: increases that come
                           only from a new phone the customer chose (change_reason=device_installment) do NOT block,
                           and fix-only contacts (fix_first) are always allowed. Otherwise contact only with a credit
                           that offsets the increase (swap to the best positive-EV offsetting credit if one exists).
 2 receipt_only_plan_move  cheaper-plan / plan-variant moves are never texts; they go on the bill/receipt only.
 3 contacted_this_quarter  at most one proactive contact per 90 days (hook: optional proactive_contacts.csv).
 4 not_worth_contacting    not picked by the policy (default: retention-only, re-picked at a 10% true save rate,
                           kept-account value $1,478 = engine value x 19.338/24).

policy="retention10" reproduces scratch exactly on demo_data: 184 ok, 4,041 not worth, 499 receipt-only, 318 blocked.
policy="engine" applies rules 1-3 to the engine's OWN picks (offers.csv action_code != do_nothing) instead of rule 4's
re-pick, e.g. to audit tm-offers' gated v2 engine.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np, pandas as pd

_q = (1 - 0.0099) / 1.10 ** (1 / 12)                       # monthly survival x monthly discount (RESEARCH.md s13b)
V_SCALE_1478 = _q * (1 - _q ** 24) / (1 - _q) / 24          # 19.338 / 24 = 0.8057; $1,835 flat -> $1,478
DECIDE_SAVE_RATE = 0.10
FATIGUE_DAYS = 90
UPSELL = {"step_up", "family_upgrade", "device_upgrade", "home_internet_bundle"}
PLAN_MOVES = {"right_size", "variant_switch"}
OFFSETS = {"bill_shock_price_lock", "loyalty_credit", "care_credit", "care_credit_fix_first", "keep_your_phone"}
TOPIC = {"billing": "billing issue", "device": "phone issue", "plan_change": "plan change issue",
         "network": "coverage issue", "cancellation_inquiry": "account issue"}
BANNED = r"income|job|kid|child|tailor|persona|synthetic|simulated|ACC-|TMO-|PROMO-|STUB|sandbox|\$0(?![.,]\d)"
OUT_COLS = ["account_id", "contact_ok", "block_reason", "why_line"]


@dataclass
class GuardrailConfig:
    rule: str = "new"                 # "new" (exemptions above) or "old" (efficacy/guardrail.py as committed)
    value_scale: float = V_SCALE_1478 # 1.0 = engine's flat 24 mo x 50% ($1,835 basis)
    save_rate_scale: object = "auto"  # "auto": 10% / risk-weighted save rate of the engine's picks (unscaled
                                      #   demo_data candidates). Use 1.0 for tm-offers v2 candidates, which are
                                      #   already field-scaled to FIELD_SAVE_RATE=0.10.
    policy: str = "retention10"       # or "engine"


def load_sandbox(conn):
    """Read-only sandbox tables the guardrail needs (conn must be opened mode=ro)."""
    as_of = pd.Timestamp(conn.execute("SELECT value FROM metadata WHERE key='as_of'").fetchone()[0])
    bh = pd.read_sql("select account_id, month, change_cents, change_reason from billing_history", conn)
    sup = pd.read_sql("select account_id, interaction_date, topic, resolved from support_interactions", conn)
    plans = pd.read_sql("select sku, name, price_guarantee_years, data_cap_gb, hotspot_high_speed_gb, hotspot_unlimited "
                        "from plans", conn).set_index("sku")
    return as_of, bh, sup, plans


def _money(cents):
    c = abs(cents)
    return f"${c / 100:,.2f}" if c < 1000 else f"${c / 100:,.0f}"


def run_guardrail(feats: pd.DataFrame, offers: pd.DataFrame, cand: pd.DataFrame, sandbox, cfg=GuardrailConfig(),
                  proactive_contacts: pd.DataFrame | None = None):
    """feats/offers indexed by account_id; cand = offer_candidates rows; sandbox = load_sandbox(conn).
    Returns (detail DataFrame one row per account, summary dict)."""
    assert cfg.rule in ("new", "old") and cfg.policy in ("retention10", "engine")
    AS_OF, bh, sup, plans = sandbox
    ids = feats.index
    assert ids.is_unique

    # ---- rule 1 input: recent real bill increases
    last3 = sorted(bh.month.unique())[-3:]
    bc = bh[bh.month.isin(last3) & (bh.change_reason != "stable") & (bh.change_cents > 0)]
    bc_last = bc.sort_values("month").groupby("account_id").last()
    bill_change = pd.Series(ids.isin(bc_last.index), index=ids)
    bc_blk = bc if cfg.rule == "old" else bc[bc.change_reason != "device_installment"]
    bc_blk_last = bc_blk.sort_values("month").groupby("account_id").last()
    blocking = pd.Series(ids.isin(bc_blk_last.index), index=ids)
    allowed_extra = set() if cfg.rule == "old" else {"fix_first"}

    # ---- open service issue (most recent unresolved, 90 d)
    sup = sup.copy(); sup["interaction_date"] = pd.to_datetime(sup.interaction_date)
    op = sup[(sup.resolved == 0) & (sup.interaction_date >= AS_OF - pd.to_timedelta(90, unit="D"))]
    open_topic = op.sort_values("interaction_date").groupby("account_id").topic.last().map(TOPIC).reindex(ids)

    # ---- EV per eligible action (same accounting as the room's chart check)
    el = cand[cand.eligible.astype(str) == "True"].copy()
    el = el[el.action_code != "do_nothing"]
    el["p"] = el.account_id.map(offers.p_churn_90d)
    el["V"] = el.account_id.map(offers.customer_value_usd) * cfg.value_scale
    ch = el[el.is_chosen.astype(str) == "True"]
    if cfg.save_rate_scale == "auto":
        base_rate = (ch.p * ch.save_rate).sum() / ch.p.sum(); scale = DECIDE_SAVE_RATE / base_rate
    else:
        base_rate = float("nan"); scale = float(cfg.save_rate_scale)
    el["ev"] = el.p * np.minimum(1, el.save_rate * scale) * el.V - el.offer_cost - el.annoyance
    rt = el[~el.action_code.isin(UPSELL)].copy()

    if cfg.policy == "retention10":       # rule 4 policy: best positive-EV non-upsell action per account
        pick = rt.sort_values("ev", ascending=False).drop_duplicates("account_id")
        pick = pick[pick.ev > 0].set_index("account_id")
    else:                                  # the engine's own picks, whatever their EV under our accounting
        eng = offers[offers.action_code != "do_nothing"]
        k = el.set_index(["account_id", "action_code"])
        pick = pd.DataFrame({"action_code": eng.action_code.values}, index=eng.index)
        pick.index.name = "account_id"
        pick["ev"] = [k.ev.get((a, c), np.nan) for a, c in zip(pick.index, pick.action_code)]
        pick["ev"] = pick.ev.fillna(0.0)
        pick["forced"] = offers.pick_override.reindex(pick.index).fillna("").astype(str).values \
            if "pick_override" in offers else ""
    n_policy = len(pick)
    pick["swapped_from"] = ""
    bc_ids = set(bc_blk_last.index)
    need = [a for a in pick.index if a in bc_ids and pick.action_code[a] not in (OFFSETS | allowed_extra)]
    alt = rt[rt.account_id.isin(need) & rt.action_code.isin(OFFSETS) & (rt.ev > 0)] \
        .sort_values("ev", ascending=False).drop_duplicates("account_id").set_index("account_id")
    alt["swapped_from"] = pick.action_code.reindex(alt.index)
    for c in pick.columns:
        if c not in alt: alt[c] = pick[c].reindex(alt.index)
    policy_ev_total = float(pick.ev.sum())
    pick = pd.concat([pick.drop(index=alt.index), alt[pick.columns]])
    n_swapped = len(alt)
    picked_plan_moves = pick.action_code.isin(PLAN_MOVES)
    selected = pd.Series(ids.isin(pick.index), index=ids)
    action = pick.action_code.reindex(ids)

    # ---- eligibility facts
    elig = el.groupby("account_id").action_code.agg(set).reindex(ids).apply(lambda s: s if isinstance(s, set) else set())
    has_offset_offer = elig.apply(lambda s: bool(s & OFFSETS))
    fix_eligible = elig.apply(lambda s: "fix_first" in s or "care_credit_fix_first" in s)
    bsl = el[el.action_code == "bill_shock_price_lock"].set_index("account_id").customer_monthly_delta

    name2sku = {v: k for k, v in plans.name.items()}
    pm = el[el.action_code.isin(PLAN_MOVES)].copy()
    pm["to_name"] = pm.reason.str.extract(r"move to (.+?) \(")[0]
    pm["to_sku"] = pm.to_name.map(name2sku)
    pm["from_sku"] = pm.account_id.map(feats.plan_sku)
    pm = pm[pm.to_sku.notna() & pm.from_sku.notna()]

    def gives_up(r):
        f, t = plans.loc[r.from_sku], plans.loc[r.to_sku]
        nz = lambda x: 0.0 if pd.isna(x) else float(x)
        lost = []
        if nz(t.price_guarantee_years) < nz(f.price_guarantee_years): lost.append("your price guarantee")
        if pd.notna(t.data_cap_gb) and pd.isna(f.data_cap_gb): lost.append("unlimited data")
        if nz(t.hotspot_high_speed_gb) < nz(f.hotspot_high_speed_gb): lost.append("high-speed hotspot")
        return " and ".join(lost[:2])
    pm["gives_up"] = pm.apply(gives_up, axis=1) if len(pm) else ""
    pm["saving"] = -pm.customer_monthly_delta
    pm = pm.sort_values(["gives_up", "saving"], key=lambda s: s.ne("") if s.name == "gives_up" else -s) \
           .drop_duplicates("account_id").set_index("account_id")
    has_plan_move = pd.Series(ids.isin(pm.index), index=ids)

    recent_contact = pd.Series(False, index=ids)
    if proactive_contacts is not None and len(proactive_contacts):
        d = pd.to_datetime(proactive_contacts.set_index("account_id").last_proactive_contact_date).reindex(ids)
        recent_contact = (AS_OF - d).dt.days.lt(FATIGUE_DAYS).fillna(False).astype(bool)

    def bill_phrase(a, src=None):
        r = (bc_last if src is None else src).loc[a]; amt = _money(r.change_cents)
        return {"promo_expired": f"Your bill went up {amt} when a promo ended",
                "device_installment": f"Your bill went up {amt} with a new phone payment",
                "installment_ended": f"Your bill went up {amt} recently"}.get(r.change_reason, f"Your bill went up {amt}")

    def receipt_phrase(a):
        r = pm.loc[a]; s = f"${r.saving:,.0f}/mo"
        if r.gives_up:
            return f"A plan {s} cheaper is on your bill; it gives up {r.gives_up}, so we won't push it."
        return f"A plan with the same features for {s} less is on your bill. Switch only if you want to."

    def contact_line(a):
        act = action[a]; t = open_topic.get(a); bc_ = bill_change[a]
        issue = t if isinstance(t, str) else None
        if act == "bill_shock_price_lock":
            extra = " and $5 off a month" if bsl.get(a, 0) < 0 else ""
            return f"{bill_phrase(a)}. Here's a one-time $25 credit{extra} to help offset it."
        if act == "loyalty_credit":
            if bc_: return f"{bill_phrase(a)}. Here's $5 off each month to help offset it."
            return f"Thanks for {int(feats.tenure_months[a] // 12)} years with us. Here's $5 off each month."
        if act == "keep_your_phone":
            if bc_: return f"{bill_phrase(a)}. Keep your paid-off phone and get $20 off a month for 6 months."
            return "Your phone is paid off. Keep it and get $20 off a month for 6 months."
        if act == "care_credit_fix_first":
            what = f"your open {issue}" if issue else "your recent issue"
            if bc_: return f"{bill_phrase(a)}. We'll call to fix {what} and add a one-time $25 credit."
            return f"We'll call to fix {what} first, and a one-time $25 credit is on us for the hassle."
        if act == "care_credit":
            if issue and fix_eligible[a]:
                return f"We're following up to fix your open {issue}, and a one-time $25 credit is on us for the trouble."
            if bc_: return f"{bill_phrase(a)}. A one-time $25 credit is on us for the recent trouble."
            return "Sorry for the recent trouble with your account. A one-time $25 credit is on us."
        if act == "fix_first":
            what = f"your open {issue}" if issue else "your recent support request"
            return f"We'd like to call and get {what} fixed. No sales pitch, no plan change."
        if act == "check_in":
            return "A quick check that your plan still fits how you use it. Nothing changes unless you ask."
        if act == "perk_reminder":
            return "Your plan already includes a streaming perk. Here's how to turn it on, at no extra cost."
        if act in ("step_up", "family_upgrade", "device_upgrade", "home_internet_bundle"):   # engine-mode only
            return {"step_up": "A plan with more of what you use is available. Nothing changes unless you ask.",
                    "family_upgrade": "Adding a line may cost less on your plan than you'd expect. Only if you want it.",
                    "device_upgrade": "Your phone qualifies for an upgrade offer. Nothing changes unless you ask.",
                    "home_internet_bundle": "Home Internet can be added to your account. Only if you want it."}[act]
        raise ValueError(act)

    rows = []
    for a in ids:
        bc_, sel = bool(blocking[a]), bool(selected[a])
        issue = open_topic.get(a); issue = issue if isinstance(issue, str) else None
        if sel and bc_ and action[a] not in (OFFSETS | allowed_extra):
            reason = "bill_change_no_fix"
        elif not sel and bc_ and not has_offset_offer[a]:
            reason = "bill_change_no_fix"
        elif sel and action[a] in PLAN_MOVES:                    # never happens for retention10 (asserted below)
            reason = "receipt_only_plan_move"
        elif not sel and has_plan_move[a]:
            reason = "receipt_only_plan_move"
        elif recent_contact[a]:
            reason = "contacted_this_quarter"
        elif not sel:
            reason = "not_worth_contacting"
        else:
            reason = ""
        if reason == "":
            line = contact_line(a)
        elif reason == "bill_change_no_fix":
            gu = pm.gives_up.get(a, "")
            tail = ((f" A cheaper plan is on your bill; it gives up {gu}." if gu else
                     " A lower-cost plan option is on your bill if you want it.") if has_plan_move[a]
                    else " We have no offer that lowers it right now, so we won't message you about it.")
            line = bill_phrase(a, bc_blk_last) + "." + tail
        elif reason == "receipt_only_plan_move":
            line = receipt_phrase(a)
        elif reason == "contacted_this_quarter":
            line = "We already reached out this quarter, so we'll hold off on more messages until next quarter."
        else:
            line = ("Nothing we'd offer right now beats leaving your account as is. Your open "
                    f"{issue} stays with support." if issue else
                    "Nothing we'd offer right now beats leaving your account as is.")
        rows.append(dict(account_id=a, contact_ok=reason == "", block_reason=reason, why_line=line,
                         bill_change_reason=bc_last.change_reason.get(a, ""),
                         bill_change_usd=(bc_last.change_cents.get(a, 0) or 0) / 100,
                         blocking_bill_change=bc_, policy_selected=sel, policy_action=action[a] if sel else "",
                         policy_ev_usd=round(float(pick.ev.get(a, 0.0)), 2), has_offset_offer=bool(has_offset_offer[a]),
                         receipt_plan_move=bool(has_plan_move[a]), receipt_saving_mo=pm.saving.get(a, 0.0),
                         receipt_gives_up=pm.gives_up.get(a, ""), open_issue_topic=issue or ""))
    G = pd.DataFrame(rows)
    G["swapped_from"] = G.account_id.map(pick.swapped_from).fillna("")
    if cfg.policy == "retention10":
        assert not picked_plan_moves.any()
    # ---- checks
    assert len(G) == len(ids) and G.account_id.is_unique
    assert (G.why_line.str.len() <= 140).all(), G.loc[G.why_line.str.len() > 140, "why_line"].tolist()[:5]
    bad = G.why_line.str.contains(BANNED, case=False)
    assert not bad.any(), G.loc[bad, "why_line"].unique()[:8]
    assert (G.contact_ok == (G.block_reason == "")).all()
    summary = dict(rule=cfg.rule, policy=cfg.policy, value_scale=cfg.value_scale, save_rate_scale=scale,
                   base_rate=base_rate, n_policy=n_policy, n_swapped=n_swapped, policy_ev=policy_ev_total,
                   blocking_accounts=int(blocking.sum()), bill_change_accounts=int(bill_change.sum()),
                   contact_ok=int(G.contact_ok.sum()),
                   block_reasons={k: int(v) for k, v in G.block_reason.replace("", "(contact ok)").value_counts().items()},
                   contacted_ev=float(G[G.contact_ok].policy_ev_usd.sum()))
    return G, summary
