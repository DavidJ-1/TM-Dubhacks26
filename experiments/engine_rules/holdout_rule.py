"""Rule 3: deterministic random holdout among contact_ok accounts.

Held-out accounts get NO text. Measure lift as churn(treated contact_ok) - churn(held-out contact_ok); both groups
passed the same rules, so the split is random and the comparison is fair.

Sizing (tm-models proofloop/RESULTS.md, ALL NUMBERS SYNTHETIC): 20% is the largest tested non-50/50 share. On our
5,042 demo accounts no split can prove a 20% churn cut (20% holdout: ~16-19% power), so the holdout is a launch
design, not a demo result. At 500k accounts a 20% holdout detects about a 5.9% relative churn cut (5% holdout: 11%).

Membership is a pure function of (seed, account_id): sha256(f"{seed}:{account_id}") -> uniform [0,1) -> held out if
< share. It does not depend on row order, on which other accounts are eligible, or on the run, so an account stays in
the same arm across reruns and as contact_ok changes.
"""
from __future__ import annotations
import hashlib
import pandas as pd

SEED = 2026
HOLDOUT_SHARE = 0.20
HOLDOUT_NOTE = "held out: no text; lift = treated vs holdout churn"


def hash_uniform(account_id, seed: int = SEED) -> float:
    h = hashlib.sha256(f"{seed}:{account_id}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def assign_holdout(account_ids, contact_ok, share: float = HOLDOUT_SHARE, seed: int = SEED) -> pd.Series:
    """Boolean Series aligned to account_ids: True = held out (contact_ok and hash < share)."""
    ids = pd.Index(account_ids)
    u = pd.Series([hash_uniform(a, seed) for a in ids], index=ids)
    ok = pd.Series(list(contact_ok), index=ids).astype(bool)
    return (ok & (u < share)).rename("holdout")
