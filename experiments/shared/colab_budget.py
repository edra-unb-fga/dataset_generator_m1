"""Conservative aggregate Colab budget checks for sequential study sessions."""
import math
import re


def parse_usage(text):
    rate=re.search(r'Usage rate:\s*([0-9]+(?:\.[0-9]+)?)/hr',text)
    balance=re.search(r'Current balance:\s*([0-9]+(?:\.[0-9]+)?) compute units',text)
    assignments=re.search(r'Active assignments:\s*(\d+)',text)
    if not rate or not balance or not assignments:
        raise ValueError('Cannot verify account usage snapshot')
    result={'rate':float(rate.group(1)), 'balance':float(balance.group(1)), 'assignments':int(assignments.group(1))}
    if not all(math.isfinite(result[x]) for x in ('rate','balance')):
        raise ValueError('Nonfinite usage')
    return result


def check_aggregate_budget(baseline, current, rate, seconds, *, prior_reserve, hard_cap=5.0):
    if not all(math.isfinite(x) for x in (baseline,current,rate,seconds,prior_reserve,hard_cap)) or rate <= 0 or seconds <= 0 or prior_reserve < 0 or hard_cap <= 0:
        raise ValueError('Invalid budget inputs')
    if current > baseline + .01:
        raise ValueError('Balance increased since baseline; cumulative spend cannot be verified')
    # Two 2-decimal balance readings may each round by half a cent.
    observed=max(0.0,baseline-current)+.01
    spent=max(observed,prior_reserve)
    estimate=rate*seconds/3600
    if spent+estimate > hard_cap:
        raise ValueError(f'Aggregate budget gate failed: {spent:.3f} spent + {estimate:.3f} estimated > {hard_cap:.3f} CU')
    return {'observed_spend_with_rounding_cu':observed,'explicit_prior_reserve_cu':prior_reserve,'prior_spend_upper_cu':spent,'future_estimated_cu':estimate,'combined_estimated_cu':spent+estimate,'hard_cap_cu':hard_cap}
