"""Join sandbox accounts to one upsell each. Tier 2 is optional and stays off this frame's callers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from harness.playbook.build import load_unresolved
from harness.playbook.segments import assign_bands
from harness.upsell.catalog import load_catalog, prepare
from harness.upsell.config import BILL_JUMP_PCT, DISPLAY_COLUMNS, SATISFIED_TENURE_MONTHS, SYNTHETIC_BADGE, UPGRADE_PUSH_BLOCKED
from harness.upsell.decide import decide
from harness.upsell.signals import child_accounts, generate, load_late_payments, load_usage


@dataclass
class Upsell:
    frame: pd.DataFrame
    real: dict[str, dict]
    with_synthetic: dict[str, dict]
    seeded_accounts: int

    def decisions(self, include_synthetic: bool) -> dict[str, dict]:
        return self.with_synthetic if include_synthetic else self.real

    def decision(self, account_id: str, include_synthetic: bool = False) -> dict:
        return self.decisions(include_synthetic)[account_id]

    def ranked(self, include_synthetic: bool = False) -> pd.DataFrame:
        rows = []
        chosen = self.decisions(include_synthetic)
        for record in self.frame.to_dict("records"):
            decision = chosen[record["account_id"]]
            outbound = bool(decision["send"])
            rows.append(
                {
                    "account_id": record["account_id"],
                    "trigger": decision["trigger"],
                    "action": decision["action"],
                    "offer": decision["offer_name"],
                    "monthly_difference": decision["diff_cents"],
                    "data_source": decision["data_source"],
                    "tier": decision["tier"],
                    "badge": decision["badge"],
                    "rejected": decision["rejected"],
                    "rule_id": decision["rule_id"],
                    "outbound": outbound,
                    "_sort": float(record["readiness"]) if outbound else 0.0,
                }
            )
        table = pd.DataFrame(rows)
        table = table.sort_values(["outbound", "_sort", "account_id"], ascending=[False, False, True])
        table = table.drop(columns=["_sort"])
        return table.reset_index(drop=True)

    def counts(self, include_synthetic: bool = False) -> pd.DataFrame:
        ranked = self.ranked(include_synthetic)
        rows = []
        for trigger, group in ranked.groupby("trigger", sort=False):
            tier2 = bool((group["tier"] == "tier2").any())
            rows.append(
                {
                    "trigger": trigger,
                    "accounts": int(len(group)),
                    "badge": SYNTHETIC_BADGE if tier2 else "",
                }
            )
        return pd.DataFrame(rows)


def display_frame(ranked: pd.DataFrame) -> pd.DataFrame:
    """Columns the screen may show. Readiness is only a sort key and is dropped here."""
    columns = [name for name in DISPLAY_COLUMNS if name in ranked.columns]
    return ranked[columns]


def build_upsell(console) -> Upsell:
    usage = load_usage().set_index("account_id")
    late = load_late_payments()
    unresolved = load_unresolved()
    children = child_accounts(console)
    synthetic = generate(console.frame["account_id"], children).set_index("account_id")
    catalog = load_catalog()
    upgrade_p = _upgrade_scores()
    counts = {account_id: len(detail["lines"]) for account_id, detail in console.details.items()}
    frame = console.frame.copy()
    frame["n_lines"] = frame["account_id"].map(counts).fillna(1).astype(int)
    labeled = assign_bands(frame)
    lookup = labeled.set_index("account_id")
    real: dict[str, dict] = {}
    both: dict[str, dict] = {}
    readiness = {}
    for account_id, detail in console.details.items():
        row = lookup.loc[account_id]
        usage_row = usage.loc[account_id] if account_id in usage.index else None
        event = synthetic.at[account_id, "synthetic_event"] if account_id in synthetic.index else None
        candidates = prepare(detail, detail["lines"], catalog, console.promos, detail.get("moment"))
        ctx = {
            "account": detail,
            "lines": detail["lines"],
            "unresolved_90d": unresolved.get(account_id, 0),
            "risk_band": row["risk_band"],
            "late_payments": late.get(account_id, 0),
            "near_cap_months": int(usage_row["near_cap_months"]) if usage_row is not None else 0,
            "usage_growth": bool(usage_row["usage_growth"]) if usage_row is not None else False,
            "growth_detail": usage_row["growth_detail"] if usage_row is not None else "",
            "paid_off_eligible": candidates["paid_off_eligible"],
            "moment": detail.get("moment"),
            "student_graduating": candidates["student_graduating"],
            "synthetic_event": None if event is None or (isinstance(event, float)) else event,
            "candidates": candidates,
            "upgrade_blocked_ids": UPGRADE_PUSH_BLOCKED,
        }
        propensity = upgrade_p.get(account_id)
        real[account_id] = decide(ctx, include_synthetic=False)
        both[account_id] = decide(ctx, include_synthetic=True)
        steady = float(detail.get("bill_increase_pct") or 0) <= BILL_JUMP_PCT
        satisfied = 1.0 if int(ctx["unresolved_90d"]) == 0 and steady and int(detail.get("tenure_months") or 0) >= SATISFIED_TENURE_MONTHS else 0.0
        afford = 0.0 if real[account_id]["trigger"] == "Negative affordability" else 1.0
        readiness[account_id] = satisfied * afford * (float(propensity) if propensity is not None else 1.0)
    labeled = labeled.copy()
    labeled["readiness"] = labeled["account_id"].map(readiness).fillna(0.0)
    return Upsell(labeled, real, both, int(len(synthetic)))


def _upgrade_scores() -> dict[str, float]:
    """Teammate upgrade-propensity file, when it is already built. Missing scores do not block the demo."""
    try:
        from harness.upgrade_gate import load

        scores = load(rebuild=False)
    except Exception:
        return {}
    if scores is None or "p_upgrade_90d" not in getattr(scores, "columns", []):
        return {}
    return {row.account_id: float(row.p_upgrade_90d) for row in scores.itertuples(index=False)}
