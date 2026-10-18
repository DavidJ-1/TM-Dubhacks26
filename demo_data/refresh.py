"""Copy the latest pipeline outputs from harness/out/ into demo_data/ (tracked, so a fresh clone shows real output).

All customers and numbers are SYNTHETIC (judge sandbox stub data + simulated labels/enrichment).
Run from anywhere: python demo_data/refresh.py
offer_candidates.csv is ~16 MB raw, so it is stored gzipped (pandas reads .csv.gz directly).
"""
from __future__ import annotations

import gzip
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "harness" / "out"
PLAIN = ["churn_scores.csv", "offers.csv", "features.csv", "labels.csv", "enrichment.csv", "line_tradein.csv",
         "churn_oof_pred.csv", "upgrade_scores.csv"]
GZIPPED = ["offer_candidates.csv"]
MAX_BYTES = 10 * 1024 * 1024


def main() -> None:
    for name in PLAIN:
        src = OUT / name
        if not src.exists():
            print(f"skip {name} (not in harness/out)")
            continue
        if src.stat().st_size > MAX_BYTES:
            raise SystemExit(f"{name} is over 10 MB; add it to GZIPPED instead")
        shutil.copy2(src, HERE / name)
        print(f"copied {name}")
    for name in GZIPPED:
        src = OUT / name
        if not src.exists():
            print(f"skip {name} (not in harness/out)")
            continue
        with src.open("rb") as fi, gzip.GzipFile(HERE / f"{name}.gz", "wb", compresslevel=9, mtime=0) as fo:
            shutil.copyfileobj(fi, fo)
        print(f"gzipped {name} -> {name}.gz")


if __name__ == "__main__":
    main()
