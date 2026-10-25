from dataset_generator_m1.runstore import _sanitized_invocation


def test_run_boundary_sanitizes_guided_and_windows_invocations():
    assert _sanitized_invocation(("start", "--config", "/private/user/composer.yaml")) == [
        "start", "--config", "composer.yaml"
    ]
    assert _sanitized_invocation(("generate", "--config", r"C:\private\user\composer.yaml"))[-1] == "composer.yaml"
