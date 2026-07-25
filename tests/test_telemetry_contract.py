from dataset_generator_m1.telemetry import MetricsAggregator, StageTimer


def test_stage_timer_accepts_a_fake_monotonic_clock() -> None:
    values = iter((100, 225))
    timings: dict[str, int] = {}

    with StageTimer(timings, "decode", clock=lambda: next(values)):
        pass

    assert timings == {"decode": 125}


def test_metrics_include_mix_object_rejections_and_rejection_cost() -> None:
    metrics = MetricsAggregator(
        target=4,
        configured_recipe_weights={"direct": 1.0, "mix": 3.0},
        configured_foreground_group_weights={"gauges": 1.0},
    )
    metrics.record_rejection(
        {"reason": "BackgroundSynthesisError", "stage_timings_ns": {"background_synthesis": 20}}
    )
    metrics.record_sample(
        {
            "attempted_instances": 2,
            "intentional_negative": False,
            "annotations": [{"class_name": "dial", "source_group": "gauges"}],
            "rejected_instances": [{"reason": "outside_frame"}],
            "background": {
                "recipe_id": "mix",
                "node_timings_ns": {"blend": 30},
                "qa": {"luminance_std": 0.2},
                "warnings": ["high_edge_seam"],
            },
            "stage_timings_ns": {"scene_render": 40},
        }
    )

    summary = metrics.summary()

    assert summary["object_attempts"] == 2
    assert summary["object_rejections"] == 1
    assert summary["rejection_cost_ns"]["BackgroundSynthesisError"] == 20
    assert summary["recipe_mix"]["mix"]["configured_fraction"] == 0.75
    assert summary["recipe_mix"]["mix"]["observed_fraction"] == 1.0
    assert summary["foreground_group_mix"]["gauges"]["configured_fraction"] == 1.0
    assert summary["stage_timings"]["background.node.blend"]["p95_ns"] == 30
    assert summary["background_warnings"] == {"high_edge_seam": 1}
