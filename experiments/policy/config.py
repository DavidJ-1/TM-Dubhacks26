"""ONE place for every policy-evaluator assumption. ALL NUMBERS SYNTHETIC.
Tags: [repo] = copied from harness/offers.py CONFIG; [research] = notes_market.md / notes_upsell.md; [ours] = our assumption."""
BASE = dict(
    HORIZON_MONTHS=24,          # [repo] VALUE_HORIZON_MONTHS: months of margin a save is worth
    SERVICE_MARGIN=0.50,        # [repo] share of monthly service revenue kept
    SAVE_RATE_MULT=1.0,         # [ours] multiplier on the repo's per-action save rates (on/off target, repo values)
    COST_MULT=1.0,              # [ours] multiplier on every offer cost (credits, callbacks, lost revenue)
    ANNOYANCE_MULT=1.0,         # [repo] per-action contact/annoyance $ (2-6), multiplier [ours]
    UPGRADE_BASE_RATE_Q=0.039,  # [research] AT&T/VZ postpaid upgrades 3-4.7%/quarter (notes_upsell §2); model scores
                                #   (simulated upgrade_90d base 6.4%) are rescaled to this mean
    UPSELL_LIFT=1.0,            # [ours] P(take upsell | contacted) = min(1, LIFT * rescaled P(upgrade)); the repo's
                                #   own P_ACCEPT (step_up 0.25, family 0.20) is ~5x the research base rate
    UPSELL_SAVE_RATE=0.0,       # [research] notes_upsell implication 1: upsell is NOT modeled as reducing churn
    BACKFIRE_REL=0.67,          # [research-derived, ours] upsell on an account raises its churn prob by this relative
                                #   amount (Ascarza 2016: plan-change nudge took 3-mo churn 6%->10%, +67%; that was a
                                #   downgrade nudge, so applying it to upsell is our extrapolation)
    CUSTOMER_BENEFIT_WEIGHT=0.0,# [ours] company-$ view: customer savings are NOT counted as company value
                                #   (repo uses 0.5 "trust value"; shown as a side scenario)
    BUDGET_FRAC=0.10,           # [ours] contact budget = 10% of 5,000 accounts = 500
    HIGH_RISK_FRAC=0.10,        # [research] guardrail: no upsell to top churn decile ...
    SUPPORT_BLOCK=3,            # [research] ... or to accounts with >=3 support contacts in 90d (variant: 5)
)
GRID = dict(                    # sensitivity sweep, full factorial (729 cells)
    SAVE_RATE_MULT=[0.5, 1.0, 1.5],
    COST_MULT=[0.5, 1.0, 2.0],
    SERVICE_MARGIN=[0.3, 0.5, 0.7],
    HORIZON_MONTHS=[12, 24, 36],
    UPSELL_LIFT=[0.5, 1.0, 2.0],
    BACKFIRE_REL=[0.0, 0.33, 0.67],
)
TEAMMATE = dict(                # [ours] mapping of teammates' console offers onto the same evaluator
    care_credit=dict(cost=25.0, ann=3.0, sr_on=0.25, sr_off=0.05),      # repo care_credit rates; on-target = >=3 support 90d
    loyalty_credit=dict(cost=60.0, ann=3.0, sr_on=0.12, sr_off=0.05),   # $5/mo x 12; on-target = port-out/competitor>=0.6
)
EMP = dict(CLV=200.0, delta=10.0, phi=1.0, alpha=6.0, beta=14.0)  # Verbraken et al. 2013 default churn-EMP parameters
