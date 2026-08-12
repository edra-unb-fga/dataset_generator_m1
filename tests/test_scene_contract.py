import numpy as np

from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.backgrounds import BackgroundSynthesizer
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.models import OutputConfig, RunConfig, SamplingConfig
from dataset_generator_m1.scene import ScenePlanner, SceneRenderer


def small_resolved():
    resolved = load_profile("examples/configs/manometro_minimal.yaml")
    profile = resolved.profile.model_copy(
        update={
            "output": OutputConfig(image_size=(256, 160), image_format="png"),
            "run": RunConfig(label="scene-test", num_images=1, seed=19, max_candidate_attempts=3),
            "sampling": SamplingConfig(
                instances_per_image=(1, 1),
                foreground_size=(0.18, 0.18),
                bbox_spacing=0.01,
                placement_attempts=20,
                min_visible_bbox_fraction=0.70,
            ),
        }
    )
    return resolved.model_copy(update={"profile": profile})


def test_scene_uses_one_global_homography_and_boxes_visible_masks() -> None:
    resolved = small_resolved()
    catalog = build_asset_catalog(resolved)
    planner = ScenePlanner(resolved, catalog)
    plan = planner.plan(slot=0, candidate_attempt=0)
    background = BackgroundSynthesizer(catalog, resolved.recipes).synthesize(
        plan.recipe_id,
        plan.canvas_size,
        np.random.default_rng(4),
    )

    rendered = SceneRenderer(resolved).render(plan, background)

    assert rendered.image.shape == (160, 256, 3)
    assert rendered.annotations
    assert rendered.coverage_fraction == 1.0
    assert len({annotation.instance_id for annotation in rendered.annotations}) == len(rendered.annotations)
    assert len(rendered.full_coverages) == len(rendered.visible_coverages) == len(rendered.annotations)
    for annotation, mask, full in zip(rendered.annotations, rendered.visible_coverages, rendered.full_coverages):
        ys, xs = np.where(mask > 8)
        assert annotation.bbox == (int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1))
        assert np.allclose(annotation.asset_to_output, rendered.scene_to_output @ annotation.asset_to_scene)
        assert np.array_equal(mask, full)


def test_geometry_plan_isolated_from_appearance_configuration() -> None:
    resolved = small_resolved()
    catalog = build_asset_catalog(resolved)
    planner = ScenePlanner(resolved, catalog)

    first = planner.plan(slot=3, candidate_attempt=1)
    appearance_changed = resolved.profile.model_copy(update={"appearance": resolved.profile.appearance.model_copy(update={"background": ()})})
    second = ScenePlanner(resolved.model_copy(update={"profile": appearance_changed}), catalog).plan(slot=3, candidate_attempt=1)

    assert first.geometry_signature() == second.geometry_signature()
