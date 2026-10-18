"""Build the in-memory console: scores, reasons, offers, and upgrade moments."""

from __future__ import annotations

import math

import pandas as pd

from harness import data, messages, moments, offers, stats
from harness.config import AS_OF, RETENTION_SKUS, db_path
from harness.model_a import ChurnModel, explain


def _none(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _line_record(row: dict) -> dict:
    age = _none(row["age_months"])
    cap = _none(row["data_cap_gb"])
    usage = _none(row["usage_3m_gb"])
    return {
        "line_id": row["line_id"],
        "member_label": row["member_label"],
        "member_role": row["member_role"],
        "byod": bool(row["byod"]),
        "device_sku": _none(row["device_sku"]),
        "device_name": _none(row["device_name"]),
        "device_tier": _none(row["device_tier"]),
        "age_months": None if age is None else int(age),
        "financing_balance_cents": int(row["financing_balance_cents"] or 0),
        "financing_months_remaining": int(row["financing_months_remaining"] or 0),
        "monthly_installment_cents": int(row["monthly_installment_cents"] or 0),
        "tradein_eligible": bool(row["tradein_eligible"]),
        "plan_sku": row["plan_sku"],
        "plan_name": row["plan_name"],
        "plan_family": row["plan_family"],
        "plan_variant": row["plan_variant"],
        "plan_tier": row["plan_tier"],
        "line_prices": row["line_prices"],
        "plan_eligibility": _none(row["plan_eligibility"]),
        "data_cap_gb": None if cap is None else int(cap),
        "usage_3m_gb": None if usage is None else float(usage),
    }


def _plans(lines: list[dict]) -> list[dict]:
    seen = set()
    plans = []
    for line in lines:
        if line["plan_sku"] in seen:
            continue
        seen.add(line["plan_sku"])
        plans.append(
            {
                "plan_family": line["plan_family"],
                "plan_variant": line["plan_variant"],
                "line_prices": line["line_prices"],
                "plan_eligibility": line["plan_eligibility"],
            }
        )
    return plans


class Console:
    def __init__(self, frame: pd.DataFrame, details: dict[str, dict], metadata: dict, promos: list[dict], model: ChurnModel):
        self.frame = frame
        self.details = details
        self.metadata = metadata
        self.promos = promos
        self.model = model
        self.stats = stats.population_stats(frame)
        self.metrics = model.metrics
        self.as_of = metadata.get("as_of", AS_OF.isoformat())
        self.retention_promos = [promo for promo in promos if promo["sku"] in RETENTION_SKUS]

    def account(self, account_id: str) -> dict:
        return self.details[account_id]

    def queue(self, personas_only: bool = False) -> pd.DataFrame:
        frame = self.frame
        if personas_only:
            frame = frame.loc[frame["is_persona"] == 1]
        return frame.sort_values(["model_p", "account_id"], ascending=[False, True])


def build_console(path=None) -> Console:
    source = path or db_path()
    conn = data.connect(source)
    try:
        metadata = data.load_metadata(conn)
        accounts = data.load_accounts(conn)
        lines = data.load_lines(conn)
        promos = data.load_promotions(conn)
        devices = data.load_devices(conn)
        curves = data.load_tradein(conn)
        personas = data.load_personas(conn)
        billing = data.load_billing_flags(conn)
        topics = data.load_support_topics(conn)
        addons = data.load_addon_flags(conn)
    finally:
        conn.close()

    model = ChurnModel(accounts)
    frame = model.frame
    frame = frame.merge(billing, on="account_id", how="left")
    frame = frame.merge(addons, on="account_id", how="left")
    frame = frame.merge(personas, on="account_id", how="left")
    frame["promo_expired_recent"] = frame["promo_expired_recent"].fillna(0).astype(int)
    frame["installment_ended_recent"] = frame["installment_ended_recent"].fillna(0).astype(int)
    frame["has_home_internet"] = frame["has_home_internet"].fillna(0).astype(int)
    frame["has_streaming"] = frame["has_streaming"].fillna(0).astype(int)
    if not topics.empty:
        top = topics.sort_values(["n", "topic"], ascending=[False, True]).drop_duplicates("account_id")
        frame = frame.merge(top.rename(columns={"topic": "top_topic", "n": "top_topic_n"}), on="account_id", how="left")
    else:
        frame["top_topic"] = None
        frame["top_topic_n"] = 0
    frame["top_topic_n"] = frame["top_topic_n"].fillna(0).astype(int)

    line_map: dict[str, list[dict]] = {}
    for account_id, group in lines.groupby("account_id", sort=False):
        line_map[account_id] = [_line_record(row) for row in group.to_dict("records")]

    device_names = dict(zip(devices["sku"], devices["name"], strict=True))
    listed = set()
    for promo in promos:
        if promo["device_skus"]:
            listed.update(promo["device_skus"].split(","))
    candidates = devices.loc[(devices["status"] == "current") & (devices["sku"].isin(listed))].to_dict("records")

    details: dict[str, dict] = {}
    action_choice = []
    action_name = []
    upgrade_when = []
    top_leave = []
    for record in frame.to_dict("records"):
        account_lines = line_map.get(record["account_id"], [])
        account = _account_dict(record)
        facts = offers.empty_cart_facts(
            account,
            _plans(account_lines),
            n_lines=len(account_lines),
            oldest_age=_oldest(account_lines),
        )
        action = offers.choose_outreach(account, promos, facts, device_names)
        moment = moments.detect_moment(account, account_lines, curves, promos, candidates, device_names)
        leave, stay, contributions = explain(model, pd.Series(record))
        message = messages.draft(account, action, moment)
        detail = {
            **account,
            "title": _none(record.get("title")),
            "scenario": _none(record.get("scenario")),
            "theme": _none(record.get("primary_theme")),
            "lines": account_lines,
            "leave": leave,
            "stay": stay,
            "contributions": contributions,
            "action": action,
            "moment": moment,
            "message": message,
        }
        details[account["account_id"]] = detail
        action_choice.append(action["choice"])
        action_name.append(action["name"])
        upgrade_when.append(moment["when"] if moment else "none")
        top_leave.append(leave[0] if leave else "")

    frame = frame.copy()
    frame["action_choice"] = action_choice
    frame["action_name"] = action_name
    frame["upgrade_when"] = upgrade_when
    frame["top_leave"] = top_leave
    frame["rank"] = frame["model_p"].rank(ascending=False, method="min").astype(int)
    return Console(frame, details, metadata, promos, model)


def _oldest(lines: list[dict]) -> int | None:
    ages = [line["age_months"] for line in lines if line["age_months"] is not None]
    return max(ages) if ages else None


def _account_dict(record: dict) -> dict:
    return {
        "account_id": record["account_id"],
        "segment": record["segment"],
        "tenure_months": int(record["tenure_months"]),
        "language": record["language"],
        "contact_preference": record["contact_preference"],
        "credit_tier": record["credit_tier"],
        "autopay": int(record["autopay"]),
        "discount_group": _none(record["discount_group"]),
        "is_persona": int(record["is_persona"]),
        "support_90d": int(record["support_90d"]),
        "avg_sentiment": float(record["avg_sentiment"]),
        "competitor_research": float(record["competitor_research"]),
        "port_out_inquiry": int(record["port_out_inquiry"]),
        "app_sessions_30d": int(record["app_sessions_30d"]),
        "cancellation_inquiries": int(record["cancellation_inquiries"]),
        "bill_increase_pct": float(record["bill_increase_pct"]),
        "last_bill_cents": int(record["last_bill_cents"] or 0),
        "plan_misfit_share": float(record["plan_misfit_share"]),
        "sandbox_p": float(record["sandbox_p"]),
        "model_p": float(record["model_p"]),
        "top_topic": _none(record.get("top_topic")),
        "top_topic_n": int(record.get("top_topic_n") or 0),
        "promo_expired_recent": int(record["promo_expired_recent"]),
        "installment_ended_recent": int(record["installment_ended_recent"]),
        "has_home_internet": int(record["has_home_internet"]),
        "has_streaming": int(record["has_streaming"]),
    }
