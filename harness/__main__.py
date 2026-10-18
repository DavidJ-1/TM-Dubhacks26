"""Print the headline sandbox figures. `python -m harness`."""

from harness.engine import build_console


def main() -> None:
    console = build_console()
    stats = console.stats
    print(f"as_of {console.as_of}  accounts {stats['accounts']}")
    print(f"expected 90-day churn {stats['expected_churn_rate']:.3%}")
    top = stats["concentration"]["top_20"]
    print(f"top 20% share of expected churners {top['share_of_expected_churners']:.1%}")
    for band in stats["support_bins"]:
        print(f"  support {band['bin']:>2}  n={band['n']:5}  {band['expected_churn']:.1%}")
    print(console.metrics["label_note"])
    print(f"holdout AUC {console.metrics['holdout_auc']:.3f}")


if __name__ == "__main__":
    main()
