"""Household plan-mix optimizer (tm-offers, scratch / not wired into offers.py). ALL NUMBERS SYNTHETIC.

For every account: enumerate every sandbox plan the whole household is eligible for and that fits it, price it for
the household's line count, and pick the lowest-cost best fit. In the sandbox every line on an account shares one
plan (0 mixed-plan accounts), so the "plan set" is one plan for all n lines (as on a real T-Mobile account).

Eligibility (sandbox `plans` table, same rules as offers._plan_allowed):
  - plans.eligibility (55_plus / partner / community) must equal accounts.discount_group; NULL = open to all;
  - min_lines <= n_lines <= max_lines (max NULL = no max), e.g. Essentials 4 Line Offer 2.0 = 4+ lines.
Fit (keep what the household uses; same thresholds as offers.py so the two never disagree):
  - data: the heaviest line's recent peak must be <= RIGHT_SIZE_CAP_HEADROOM (70%) of a capped plan's data;
  - hotspot: a line using > 0.5 GB/mo needs >= 1.5x that in high-speed hotspot;
  - watch/tablet (connected) lines: plan must support device connections (device_connection_cents not NULL);
    the Beyond-only connected line add-on keeps the household on Experience Beyond;
  - perks: a household with the streaming add-on or >= PERK_MIN_STREAMING_HOURS of streaming keeps every perk
    it has now (target perks must be a superset);
  - Home Internet: no plan restriction in the sandbox (bundle promos have no plan_families), so it is kept as is.
Tier (don't strip a plan the household actually uses just because a cheaper one technically fits; same gates
as offers.right_size_option, so a down-move here is one offers.py would also call right-sizing):
  - same family (incl. discount variants, Essentials <-> 4 Line Offer): free, lowest cost wins;
  - down a family only if every line is light on a premium plan (sandbox misfit rule, um_plan_overpay), or
    Beyond -> More when every line is < 15 GB and < 2 GB hotspot with no watch/tablet lines, streaming add-on or
    Home Internet, or standard More with 4+ lines and no extras -> Essentials 4 Line Offer;
  - Essentials Saver (basic tier) only if every line's peak is <= SAVER_MAX_LINE_PEAK_GB and no watch/tablet lines;
  - up a family only when the current plan doesn't fit (over cap / hotspot), cheapest plan that fits.
The CURRENT plan is judged without the 70% headroom (only "not over cap"), so we never call a plan the customer
already lives on a misfit just because it is close to its cap.
Cost: plan line_prices + extra_line_cents (offer_detectors.plan_price_cents). Add-ons (protection, watch lines,
Home Internet) cost the same on every plan that supports them, so they cancel and are left out.
Ties on price go to the richer plan (higher family rank, then price guarantee, then more perks).
Trade-in: per-line now-vs-wait verdicts from line_tradein.csv (tradein_wait.py output), summarised per account.

Run:  DUBHACKS_DB=vendor/dubhacks/data/sandbox.db python harness/household_optimizer.py --out /tmp/household_opt
      (--inputs DIR with features.csv + line_tradein.csv; default harness/out, else demo_data/)
Reads sandbox.db read-only (offer_detectors.connect_ro). Writes only <out>/household_plan.csv.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offer_detectors as det  # noqa: E402
import offers as O  # noqa: E402

ROOT = HERE.parent
FAMILY_RANK = O.FAMILY_RANK
COLUMNS = ["account_id", "current_plan", "current_monthly", "best_plan", "best_monthly", "monthly_saving",
           "lines_affected", "reason", "tradein_verdict_summary"]


def _inputs_dir(arg: str | None) -> Path:
    cands = [Path(arg)] if arg else []
    if os.environ.get("TM_OUT_DIR"):
        cands.append(Path(os.environ["TM_OUT_DIR"]))
    for d in cands + [HERE / "out", ROOT / "demo_data"]:
        if (d / "features.csv").exists():
            return d
    raise FileNotFoundError("no features.csv in --inputs / TM_OUT_DIR / harness/out / demo_data")


def _perks(p: pd.Series) -> set:
    return {x for x in str(p["perks"] if pd.notna(p["perks"]) else "").split(",") if x}


def _addon_skus(conn) -> pd.Series:
    la = pd.read_sql("select l.account_id, la.addon_sku from line_addons la join lines l using(line_id)", conn)
    aa = pd.read_sql("select account_id, addon_sku from account_addons", conn)
    return pd.concat([la, aa]).groupby("account_id")["addon_sku"].agg(set)


def fits(plan: pd.Series, row: pd.Series, current: bool = False) -> tuple[bool, str]:
    """(fits, why-not). current=True: data judged against the cap itself, not the 70% headroom."""
    if not current:
        if not O._plan_allowed(plan, row["n_lines"], row["discount_group"]):
            return False, "not eligible"
        if not O._fits_usage(plan, row):
            return False, "usage"
    else:
        peak = row["max_line_data_peak_gb"] if pd.notna(row["max_line_data_peak_gb"]) else 0
        if pd.notna(plan["data_cap_gb"]) and peak > plan["data_cap_gb"]:
            return False, "over cap"
    if (row.get("n_connected_lines", 0) or 0) > 0:
        if pd.isna(plan["device_connection_cents"]):
            return False, "no watch/tablet lines"
        if row["needs_beyond_connected"] and plan["family"] != "experience_beyond":
            return False, "Beyond-only connected line"
    if row["keeps_perks"] and not row["cur_perks"] <= _perks(plan):
        return False, "loses perks in use"
    return True, ""


def _rank_key(p: pd.Series, monthly: int, is_current: bool):
    g = p["price_guarantee_years"] if pd.notna(p["price_guarantee_years"]) else 0
    return (monthly, not is_current, -FAMILY_RANK[p["family"]], -g, -len(_perks(p)))


def tier_ok(p: pd.Series, cur: pd.Series, r: pd.Series, cur_ok: bool) -> bool:
    """May the household move from cur to p (see 'Tier' in the module docstring)?"""
    peak = r["max_line_data_peak_gb"] if pd.notna(r["max_line_data_peak_gb"]) else 0
    hs = r["max_line_hotspot_gb"] if pd.notna(r["max_line_hotspot_gb"]) else 0
    conn = (r.get("n_connected_lines", 0) or 0) > 0
    stream = bool(r.get("has_streaming_addon", 0) or 0)
    hint = bool(r.get("has_home_internet", False))
    if p["variant"] == "saver" and (peak > O.CONFIG["SAVER_MAX_LINE_PEAK_GB"] or conn):
        return False
    fp, fc = FAMILY_RANK[p["family"]], FAMILY_RANK[cur["family"]]
    if fp == fc:
        return True
    if fp > fc:
        return not cur_ok
    if bool(r.get("um_plan_overpay", False)):   # sandbox misfit rule: every line light on a premium plan
        return True
    if cur["family"] == "experience_beyond" and p["family"] == "experience_more":
        return peak < 15 and hs < 2 and not conn and not stream and not hint
    if (cur["family"] == "experience_more" and cur["variant"] == "standard" and p["variant"] == "four_line_offer"
            and r["n_lines"] >= 4):
        return not conn and not stream and not hint and hs <= 0.5
    return False


def tradein_summary(lt: pd.DataFrame | None) -> pd.Series:
    if lt is None or lt.empty:
        return pd.Series(dtype=str)
    col = "decision" if "decision" in lt.columns else "wait_verdict"

    def one(g: pd.DataFrame) -> str:
        parts = []
        for dec, n in g[col].astype(str).value_counts().sort_index().items():
            s = f"{n} {dec}"
            if dec.startswith("wait") and "wait_date" in g:
                dates = sorted({str(d)[:7] for d in g.loc[g[col] == dec, "wait_date"].dropna()})
                if dates:
                    s += f" ({', '.join(dates)})"
            parts.append(s)
        return "; ".join(parts)
    return lt.groupby("account_id").apply(one, include_groups=False)


def optimize(facts: pd.DataFrame, plans: pd.DataFrame, lt: pd.DataFrame | None = None,
             addons_by_acct: pd.Series | None = None) -> pd.DataFrame:
    P = plans.set_index("sku", drop=False)
    perk_hours = O.CONFIG.get("PERK_MIN_STREAMING_HOURS", 20.0)
    tsum = tradein_summary(lt)
    rows = []
    for _, r in facts.iterrows():
        r = r.copy()
        cur = P.loc[r["plan_sku"]]
        n = int(r["n_lines"])
        r["cur_perks"] = _perks(cur)
        r["keeps_perks"] = bool((r.get("has_streaming_addon", 0) or 0)
                                or (r.get("streaming_hours_3m_avg", 0) or 0) >= perk_hours)
        skus = addons_by_acct.get(r["account_id"], set()) if addons_by_acct is not None else set()
        r["needs_beyond_connected"] = "TMO-STUB-ADD-LINE-CONNECTED-BEYOND" in skus
        cur_m = O._price(cur, n)
        cur_ok, cur_why = fits(cur, r, current=True)
        options = []
        for _, p in plans.iterrows():
            is_cur = p["sku"] == cur["sku"]
            ok = (is_cur and cur_ok) or (not is_cur and fits(p, r)[0] and tier_ok(p, cur, r, cur_ok))
            if ok:
                options.append((_rank_key(p, O._price(p, n), is_cur), p))
        if not options:   # nothing fits (e.g. extreme hotspot): stay put, flagged
            best, best_m, reason = cur, cur_m, f"no sandbox plan fits ({cur_why or 'usage'}); keep current"
        else:
            options.sort(key=lambda t: t[0])
            best = options[0][1]
            best_m = O._price(best, n)
            if best["sku"] == cur["sku"]:
                reason = "already the lowest-cost plan that fits"
            else:
                bits = []
                if not cur_ok:
                    bits.append(f"current plan doesn't fit ({cur_why})")
                if pd.notna(best["eligibility"]):
                    bits.append(f"{best['eligibility']} discount group")
                if best["min_lines"] > 1:
                    bits.append(f"{n} lines meet {int(best['min_lines'])}+ line rule")
                peak = r["max_line_data_peak_gb"] if pd.notna(r["max_line_data_peak_gb"]) else 0
                bits.append(f"heaviest line peak {peak:.0f} GB"
                            + (f" fits {best['data_cap_gb']:.0f} GB" if pd.notna(best["data_cap_gb"]) else " (unlimited)"))
                gives = []
                if pd.notna(cur["price_guarantee_years"]) and pd.isna(best["price_guarantee_years"]):
                    gives.append("price guarantee")
                if best["hotspot_high_speed_gb"] < cur["hotspot_high_speed_gb"]:
                    gives.append("high-speed hotspot")
                lost = r["cur_perks"] - _perks(best)
                if lost:
                    gives.append("unused perks")
                if gives:
                    bits.append("gives up " + ", ".join(gives))
                if bool(r.get("has_home_internet", False)):
                    bits.append("keeps Home Internet")
                reason = "; ".join(bits)
        rows.append({"account_id": r["account_id"], "current_plan": cur["name"], "current_monthly": cur_m / 100,
                     "best_plan": best["name"], "best_monthly": best_m / 100,
                     "monthly_saving": (cur_m - best_m) / 100,
                     "lines_affected": n if best["sku"] != cur["sku"] else 0, "reason": reason,
                     "tradein_verdict_summary": tsum.get(r["account_id"], "")})
    return pd.DataFrame(rows, columns=COLUMNS)


def build(inputs: str | None = None) -> pd.DataFrame:
    src = _inputs_dir(inputs)
    conn = det.connect_ro()
    cat = det.load_catalog(conn)
    facts = det.build_account_facts(conn)
    facts, _ = det.apply_features_csv(facts, src / "features.csv")
    lt = pd.read_csv(src / "line_tradein.csv") if (src / "line_tradein.csv").exists() else None
    return optimize(facts, cat["plans"], lt, _addon_skus(conn))


def main() -> None:
    ap = argparse.ArgumentParser(description="Household plan-mix optimizer (SYNTHETIC, scratch)")
    ap.add_argument("--out", default="/tmp/household_opt", help="output dir (scratch; never demo_data)")
    ap.add_argument("--inputs", default=None, help="dir with features.csv + line_tradein.csv")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    hp = build(a.inputs)
    hp.to_csv(out / "household_plan.csv", index=False)
    mv = hp[hp.lines_affected > 0]
    print(f"wrote {out / 'household_plan.csv'} ({len(hp)} accounts). {len(mv)} would move: "
          f"{int((mv.monthly_saving > 0).sum())} save (total ${mv.monthly_saving.clip(lower=0).sum():,.0f}/mo), "
          f"{int((mv.monthly_saving < 0).sum())} must step up to fit. ALL NUMBERS SYNTHETIC.")


if __name__ == "__main__":
    main()
