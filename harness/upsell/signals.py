"""Tier 1 facts from the sandbox, and Tier 2 signals from one seeded share.

Tier 2 is synthetic, opted-in, and illustrative. The generator does not use a
published base rate. Household kid lines come from harness/enrichment.py.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from harness import enrichment
from harness.config import AS_OF, db_path
from harness.data import connect
from harness.labels import uniform
from harness.upsell.config import SYNTHETIC_BADGE, SYNTHETIC_EVENTS, SYNTHETIC_SEED, SYNTHETIC_SHARE

OUT = Path(__file__).resolve().parents[1] / "out" / "life_signals.csv"
# Last three usage months before the sandbox as-of date.
USAGE_MONTHS = ("2026-07", "2026-08", "2026-09")


def generate(account_ids: pd.Series, child_ids: set[str]) -> pd.DataFrame:
    """One synthetic event for a seeded share of accounts. Same ids and seed, same rows."""
    ids = pd.Series(list(account_ids), dtype=object)
    gate = uniform(SYNTHETIC_SEED, ids)
    choice = uniform(f"{SYNTHETIC_SEED}:event", ids)
    rows = []
    for account_id, keep, pick in zip(ids, gate, choice, strict=True):
        if float(keep) >= SYNTHETIC_SHARE:
            continue
        options = [event for event in SYNTHETIC_EVENTS if event != "kid_turning_13" or account_id in child_ids]
        if not options:
            options = [event for event in SYNTHETIC_EVENTS if event != "kid_turning_13"]
        index = min(int(float(pick) * len(options)), len(options) - 1)
        rows.append(
            {
                "account_id": account_id,
                "synthetic_event": options[index],
                "label": SYNTHETIC_BADGE,
            }
        )
    columns = ["account_id", "synthetic_event", "label"]
    return pd.DataFrame(rows, columns=columns)


def load_usage(path=None) -> pd.DataFrame:
    """Per account: months near the cap, and whether data, hotspot, or streaming grew."""
    conn = connect(path or db_path())
    try:
        frame = pd.read_sql_query(
            """
            SELECT l.account_id, l.line_id, u.month, u.data_gb, u.hotspot_gb, u.streaming_hours,
                   p.data_cap_gb
            FROM usage_monthly u
            JOIN lines l USING (line_id)
            JOIN plans p ON p.sku = l.plan_sku
            WHERE u.month >= ? AND u.month <= ?
            """,
            conn,
            params=(USAGE_MONTHS[0], USAGE_MONTHS[-1]),
        )
    finally:
        conn.close()
    if frame.empty:
        return pd.DataFrame(columns=["account_id", "near_cap_months", "usage_growth", "growth_detail"])
    from harness.upsell.config import CAP_RATIO, GROWTH_RATIO

    frame["near"] = frame["data_cap_gb"].notna() & (frame["data_gb"] + 1e-9 >= CAP_RATIO * frame["data_cap_gb"])
    near = frame.groupby(["account_id", "line_id"])["near"].sum().groupby("account_id").max()
    ordered = frame.sort_values(["line_id", "month"])
    size = ordered.groupby("line_id")["month"].transform("size")
    comparable = ordered.loc[size >= 2]
    latest = comparable.loc[~comparable.duplicated("line_id", keep="last")].set_index("line_id")
    prior = comparable.loc[comparable.duplicated("line_id", keep="last")]
    prior_mean = prior.groupby("line_id")[["data_gb", "hotspot_gb", "streaming_hours"]].mean()
    shared = latest.index.intersection(prior_mean.index)
    latest = latest.loc[shared]
    prior_mean = prior_mean.loc[shared]
    label = pd.Series("", index=shared, dtype=object)
    for column, name in (("data_gb", "data"), ("hotspot_gb", "hotspot"), ("streaming_hours", "streaming")):
        base = prior_mean[column]
        grew = (base > 0) & (latest[column] >= GROWTH_RATIO * base) & (label == "")
        label = label.mask(grew, name)
    pairs = pd.DataFrame({"account_id": latest["account_id"].to_numpy(), "label": label.to_numpy()})
    pairs = pairs.loc[pairs["label"] != ""]
    detail = pairs.groupby("account_id")["label"].agg(lambda values: ", ".join(sorted(set(values))))
    accounts = frame["account_id"].drop_duplicates()
    out = pd.DataFrame({"account_id": accounts.to_numpy()})
    out["near_cap_months"] = out["account_id"].map(near).fillna(0).astype(int)
    out["growth_detail"] = out["account_id"].map(detail).fillna("")
    out["usage_growth"] = out["growth_detail"] != ""
    return out.reset_index(drop=True)


def load_late_payments(path=None) -> dict[str, int]:
    """The sandbox change_reason list has no late-payment value. This stays zero unless one appears."""
    conn = connect(path or db_path())
    try:
        rows = conn.execute(
            """
            SELECT account_id, COUNT(*)
            FROM billing_history
            WHERE lower(change_reason) LIKE '%late%'
            GROUP BY account_id
            """
        )
        return {account_id: int(count) for account_id, count in rows}
    finally:
        conn.close()


def child_accounts(console) -> set[str]:
    """Reuse enrichment's child band (member role child -> 0-12). Ages are not in the sandbox."""
    frame = _household_input(console)
    household = enrichment.household(frame)
    household["account_id"] = frame["account_id"].to_numpy()
    band = household["kid_age_band"] == "0-12"
    return set(household.loc[band, "account_id"])


def _household_input(console) -> pd.DataFrame:
    counts = {account_id: len(detail["lines"]) for account_id, detail in console.details.items()}
    frame = console.frame
    return pd.DataFrame(
        {
            "account_id": frame["account_id"],
            "n_lines": frame["account_id"].map(counts).fillna(1).astype(int),
            "segment": frame["segment"],
            "promo_expired_recent": frame["promo_expired_recent"],
        }
    )


def write_signals(console, destination: Path | None = None) -> pd.DataFrame:
    """Write the seeded Tier 2 rows. Every row carries the synthetic badge."""
    signals = generate(console.frame["account_id"], child_accounts(console))
    target = destination or OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    signals.to_csv(target, index=False)
    return signals


def main() -> None:
    from harness.engine import build_console

    signals = write_signals(build_console())
    print(
        f"wrote {OUT} seeded_accounts={len(signals)} label={SYNTHETIC_BADGE!r} "
        f"as_of={AS_OF.isoformat()} [synthetic, consented, illustrative]"
    )


if __name__ == "__main__":
    main()
