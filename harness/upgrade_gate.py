"""Upgrade-propensity gate for Model B (tm-offers). ALL SYNTHETIC.

Uses tm-bench's NO-INCOME upgrade model (harness/bench, commit b948e20): tier "a features.csv + domain"
(prepare() features + domain ratios; NO job change, NO income band), lr_tuned, trained on the synthetic 250k
(out/scaled_250k) and scored on the 5,042 real accounts. Bench reports top-15% capture 44.1% on the real 5k.
The income_band variant (tier b2) is deliberately NOT used.

    python harness/upgrade_gate.py          # writes harness/out/upgrade_scores.csv (cached; offers.py reuses it)

Output: account_id, p_upgrade_90d, upgrade_pct (percentile among the 5,000 non-persona real accounts; personas
are placed on that same scale), in_top15 (upgrade_pct >= 85).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = HERE / "out" / "upgrade_scores.csv"
TOP_PCT = 15
TIER = "a features.csv + domain"
SOURCE = "synthetic_250k"


def score() -> pd.DataFrame:
    from harness.bench import bench as B
    from harness.bench import upgrade_improve as U
    fr = pd.read_csv(B.DEFAULT_FEATURES).merge(pd.read_csv(U.ENRICH).drop(columns=["n_lines"], errors="ignore"),
                                                on="account_id", validate="1:1")
    d = U.SCALED[SOURCE]
    F = pd.read_csv(d / "features_scaled.csv")
    hh = d / "household_scaled.csv"
    if not set(U.HOUSE[:3]) <= set(F.columns) and hh.exists():
        F = F.merge(pd.read_csv(hh).drop(columns=["n_lines"], errors="ignore"), on="account_id", validate="1:1")
    lab = pd.read_csv(d / "labels_scaled.csv")
    Xs, base = U.build([("real", fr), (SOURCE, F)])
    cols = U.tiers(base)[TIER]
    assert not any("income" in c or "job" in c for c in cols), "no-income tier must not use income / job"
    m = U.MODELS["lr_tuned"](cols).fit(Xs[SOURCE][cols], lab[U.T].values.astype(int))
    p = m.predict_proba(Xs["real"][cols])[:, 1]
    reg = (fr["is_persona"] == 0).values
    pop = np.sort(p[reg])
    pct = (np.searchsorted(pop, p, side="left") + np.searchsorted(pop, p, side="right")) / 2 / len(pop) * 100
    out = pd.DataFrame({"account_id": fr["account_id"], "p_upgrade_90d": p.round(5), "upgrade_pct": pct.round(2)})
    out["in_top15"] = out["upgrade_pct"] >= 100 - TOP_PCT
    out["model"] = f"bench {TIER} | lr_tuned | trained on {SOURCE} (no income, no job change)"
    out["data_note"] = "synthetic/simulated"
    return out


def load(rebuild: bool = False) -> pd.DataFrame | None:
    """Cached scores; None if they can't be built (offers.py then falls back to detectors + EV only)."""
    feats = HERE / "out" / "features.csv"
    if OUT.exists() and not rebuild and (not feats.exists() or OUT.stat().st_mtime >= feats.stat().st_mtime):
        return pd.read_csv(OUT)
    try:
        s = score()
    except Exception as e:  # noqa: BLE001
        print(f"upgrade gate unavailable ({type(e).__name__}: {e}); falling back to detectors + EV")
        return None
    s.to_csv(OUT, index=False)
    return s


if __name__ == "__main__":
    s = load(rebuild=True)
    if s is not None:
        print(f"wrote {OUT}: {int(s.in_top15.sum())} accounts in the top {TOP_PCT}%")
