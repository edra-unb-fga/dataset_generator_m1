import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('experiments/shared').resolve()))
from colab_budget import check_aggregate_budget, parse_usage


def test_aggregate_cap_includes_prior_attempts_and_rounding():
    usage=parse_usage('Current balance: 156.52 compute units\nUsage rate: 0.00/hr\nActive assignments: 0')
    assert usage['balance']==156.52
    result=check_aggregate_budget(156.52,155.52,3.08,1050,prior_reserve=0)
    assert result['combined_estimated_cu']==pytest.approx(1.9083333333333332)
    with pytest.raises(ValueError,match='Aggregate budget gate'):
        check_aggregate_budget(156.52,152.52,3.5,1050,prior_reserve=0)
    with pytest.raises(ValueError): parse_usage('unavailable')


def test_balance_increase_is_not_silently_treated_as_zero_spend():
    with pytest.raises(ValueError,match='Balance increased'):
        check_aggregate_budget(100,101,1.54,1050,prior_reserve=0)


def test_prior_reserve_protects_against_delayed_balance_updates():
    result=check_aggregate_budget(156.52,156.52,3.08,1050,prior_reserve=1.80)
    assert result['prior_spend_upper_cu']==1.80
    assert result['combined_estimated_cu']==pytest.approx(2.6983333333333333)
    with pytest.raises(ValueError,match='Aggregate budget gate'):
        check_aggregate_budget(156.52,156.52,3.08,1050,prior_reserve=4.11)
    with pytest.raises(ValueError):
        check_aggregate_budget(156.52,156.52,3.08,1050,prior_reserve=-1)


@pytest.mark.parametrize('study', ['balanced-completion', 'balanced-completion-retry'])
def test_completion_supervisor_requires_explicit_budget_baseline(study, tmp_path):
    import subprocess
    script = Path('experiments/blenderproc/studies') / study / 'supervisor.py'
    output = tmp_path / 'must-not-be-created'
    result = subprocess.run([sys.executable, str(script), '--output', str(output)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert '--baseline is required' in result.stderr
    assert not output.exists()


@pytest.mark.parametrize('study', ['balanced-completion', 'balanced-completion-retry'])
def test_completion_watchdog_does_not_require_budget_baseline(study, tmp_path):
    import json
    import subprocess
    script = Path('experiments/blenderproc/studies') / study / 'supervisor.py'
    (tmp_path / 'status.json').write_text(json.dumps({'step': 'closed', 'stop_confirmed': True}))
    result = subprocess.run([sys.executable, str(script), '--output', str(tmp_path),
                             '--watchdog', '--watchdog-seconds', '0'],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
