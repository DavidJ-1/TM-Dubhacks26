"""Overpaying-account figure (tm-offers, v2). ALL NUMBERS SYNTHETIC (sandbox stub accounts, not T-Mobile data).

Reproduces the household plan-mix optimizer's count (harness/household_optimizer.py, from tm-offers-wip d3adf09):
accounts whose lowest-cost best-fit sandbox plan is cheaper than today's plan (same fit, perk, watch/tablet,
Home Internet and tier gates as offers.py). Counts ACCOUNTS, not households (the sandbox has no household id).
Prints the breakdown by move, the limited_time 4 Line Offer share, and the company-side revenue given up at
3% and 13% acceptance (cited range for proactive cheaper-plan offers; see harness/offers.py P_ACCEPT).
Sandbox read-only (mode=ro via offer_detectors.connect_ro).

Run:  DUBHACKS_DB=vendor/dubhacks/data/sandbox.db python scripts/overpaying_accounts.py [--inputs DIR]
      (DIR with features.csv [+ line_tradein.csv]; default TM_OUT_DIR, harness/out, else demo_data/)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import household_optimizer as hh  # noqa: E402
import offer_detectors as det  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default=None)
    a = ap.parse_args(argv)
    hp = hh.build(a.inputs)
    plans = det.load_catalog(det.connect_ro())["plans"].set_index("name")
    mv = hp[(hp.lines_affected > 0) & (hp.monthly_saving > 0)].copy()
    mv["target_status"] = mv.best_plan.map(plans["status"])
    tot = mv.monthly_saving.sum()
    print(f"[SYNTHETIC] overpaying accounts: {len(mv)} save ${tot:,.0f}/mo if all switch "
          f"({int(((hp.lines_affected > 0) & (hp.monthly_saving < 0)).sum())} others must step up to fit)")
    g = mv.groupby(["current_plan", "best_plan", "target_status"]).agg(accounts=("account_id", "size"),
                                                                       monthly_saving=("monthly_saving", "sum"))
    print(g.to_string())
    lt = mv[mv.target_status == "limited_time"]
    print(f"of which target a limited_time plan (Essentials 4 Line Offer 2.0): {len(lt)} accounts, "
          f"${lt.monthly_saving.sum():,.0f}/mo; excluding them: {len(mv) - len(lt)} accounts, "
          f"${tot - lt.monthly_saving.sum():,.0f}/mo")
    for pa in (0.03, 0.13):
        print(f"expected revenue given up at {pa:.0%} acceptance: ${tot * pa:,.0f}/mo (${tot * pa * 12:,.0f}/yr)")
    return mv


if __name__ == "__main__":
    main()
