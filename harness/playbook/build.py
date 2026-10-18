"""Join the console's sandbox accounts to the playbook. Does not write offer-engine files."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from harness.config import AS_OF, db_path
from harness.data import connect
from harness.playbook.decide import decide
from harness.playbook.rules import ASSUMPTION_CREDIT_CENTS
from harness.playbook.segments import assign_bands, grid


@dataclass
class Playbook:
    frame: pd.DataFrame
    grid: pd.DataFrame
    decisions: dict[str, dict]

    def decision(self, account_id: str) -> dict:
        return self.decisions[account_id]

    def ranked(self) -> pd.DataFrame:
        """Risk times value. Not a dollar outcome. Do-nothing rows sort after everyone else."""
        rows = []
        for record in self.frame.to_dict("records"):
            decision = self.decisions[record["account_id"]]
            outbound = decision["action"] != "DO NOTHING"
            rows.append(
                {
                    "account_id": record["account_id"],
                    "risk_band": record["risk_band"],
                    "value_band": record["value_band"],
                    "priority_cell": bool(record["priority_cell"]),
                    "model_p": float(record["model_p"]),
                    "sandbox_p": float(record["sandbox_p"]),
                    "value_score_cents": float(record["value_score"]),
                    "rank_score": float(record["model_p"]) * float(record["value_score"]),
                    "trigger": decision["trigger"],
                    "action": decision["action"],
                    "offer": decision["offer_name"],
                    "why": decision["why"],
                    "rejected_next": decision["rejected"],
                    "reason_1": decision["reasons"][0]["text"],
                    "reason_1_source": decision["reasons"][0]["source"],
                    "reason_2": decision["reasons"][1]["text"],
                    "reason_2_source": decision["reasons"][1]["source"],
                    "reason_3": decision["reasons"][2]["text"],
                    "reason_3_source": decision["reasons"][2]["source"],
                    "outbound": outbound,
                }
            )
        table = pd.DataFrame(rows)
        table = table.sort_values(["outbound", "rank_score", "account_id"], ascending=[False, False, True])
        return table.reset_index(drop=True)


def load_unresolved(path=None) -> dict[str, int]:
    source = path or db_path()
    conn = connect(source)
    try:
        rows = conn.execute(
            """
            SELECT account_id,
              SUM(CASE WHEN resolved = 0 AND interaction_date >= date(?, '-90 day') THEN 1 ELSE 0 END)
            FROM support_interactions
            GROUP BY account_id
            """,
            (AS_OF.isoformat(),),
        )
        return {account_id: int(count or 0) for account_id, count in rows}
    finally:
        conn.close()


def load_catalog(path=None) -> list[dict]:
    source = path or db_path()
    conn = connect(source)
    try:
        rows = conn.execute(
            "SELECT sku, name, family, line_prices, data_cap_gb, eligibility, min_lines, max_lines FROM plans"
        )
        return [dict(row) for row in rows]
    finally:
        conn.close()


def build_playbook(console, assumption_credit_cents: int | None = None) -> Playbook:
    unresolved = load_unresolved()
    catalog = load_catalog()
    line_counts = {account_id: len(detail["lines"]) for account_id, detail in console.details.items()}
    frame = console.frame.copy()
    frame["n_lines"] = frame["account_id"].map(line_counts).fillna(1).astype(int)
    labeled = assign_bands(frame)
    credit = ASSUMPTION_CREDIT_CENTS if assumption_credit_cents is None else int(assumption_credit_cents)
    decisions: dict[str, dict] = {}
    lookup = labeled.set_index("account_id")
    for account_id, detail in console.details.items():
        row = lookup.loc[account_id]
        decisions[account_id] = decide(
            {
                "account": detail,
                "lines": detail["lines"],
                "promos": console.promos,
                "catalog_plans": catalog,
                "device_names": {},
                "curves": None,
                "candidates": [],
                "moment": detail.get("moment"),
                "unresolved_90d": unresolved.get(account_id, 0),
                "risk_band": row["risk_band"],
                "value_band": row["value_band"],
                "assumption_credit_cents": credit,
            }
        )
    return Playbook(labeled, grid(labeled), decisions)
