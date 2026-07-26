from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import resolve_worker_count


def test_explicit_and_composer_worker_policies_share_one_resolver() -> None:
    resolved = load_profile("examples/configs/landing_minimal.yaml")
    assert resolve_worker_count(None, resolved) == 1
    assert resolve_worker_count(3, resolved) == 3
    assert resolve_worker_count("auto", resolved) >= 1
