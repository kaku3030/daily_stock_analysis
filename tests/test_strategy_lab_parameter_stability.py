from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from src.services.strategy_lab.config import CONFIG_PATH, load_parameter_stability_config
from src.services.strategy_lab.parameter_stability import (
    MetricDirection,
    ParameterObservation,
    ParameterStabilityLabel,
    ParameterStabilityResult,
    evaluate_parameter_stability,
)


CONFIG = load_parameter_stability_config()


def _grid(pairs: tuple[tuple[float, float], ...]) -> tuple[ParameterObservation, ...]:
    return tuple(ParameterObservation(parameter_value=p, metric_value=m) for p, m in pairs)


# --- A. Stable plateau -------------------------------------------------
# RADAR_ENGINEERING_CONSTITUTION section 16 example: gently degrading
# neighbors around the selected 20-period point.
STABLE_PLATEAU_GRID = _grid(((17, 18.7), (20, 21.9), (22, 20.5), (25, 18.9)))

# --- B. Single-point overfit --------------------------------------------
# RADAR_ENGINEERING_CONSTITUTION section 16 "parameter cliff" example.
SINGLE_POINT_OVERFIT_GRID = _grid(((19, 7.0), (20, 22.0), (21, 5.0)))


def test_stable_plateau_is_detected() -> None:
    result = evaluate_parameter_stability(
        observations=STABLE_PLATEAU_GRID, selected_parameter=20, config=CONFIG
    )

    assert result.stability_label is ParameterStabilityLabel.STABLE_PLATEAU
    assert result.parameter_cliff < CONFIG.cliff_relative_drop_threshold
    assert result.plateau_width == 4
    assert result.selected_within_plateau is True
    assert result.warnings == ()
    assert result.base_metric_value == 21.9
    assert result.best_metric_value == 21.9
    assert result.neighbor_median == 18.9
    assert result.neighbor_worst == 18.7


def test_single_point_overfit_is_flagged_unstable() -> None:
    result = evaluate_parameter_stability(
        observations=SINGLE_POINT_OVERFIT_GRID, selected_parameter=20, config=CONFIG
    )

    assert result.stability_label is ParameterStabilityLabel.UNSTABLE_CLIFF
    assert result.parameter_cliff >= CONFIG.cliff_relative_drop_threshold
    assert result.plateau_width < CONFIG.minimum_plateau_width
    assert "parameter_cliff_detected" in result.warnings


def test_flat_weak_surface_is_stable_but_not_called_good() -> None:
    grid = _grid(((5, 1.8), (7, 2.0), (10, 1.9), (14, 1.7)))

    result = evaluate_parameter_stability(observations=grid, selected_parameter=7, config=CONFIG)

    # Stable shape is allowed...
    assert result.stability_label is ParameterStabilityLabel.STABLE_PLATEAU
    # ...but nothing in the result claims the strategy is profitable or good.
    # The engine only ever reports shape; magnitude judgement is the caller's
    # job via PerformanceReport, which this result type has no field for.
    assert result.base_metric_value == 2.0
    field_names = {f.name for f in fields(ParameterStabilityResult)}
    assert field_names.isdisjoint({"is_good", "trustworthy", "recommended", "verdict"})


def test_sparse_neighborhood_reports_insufficient_data_explicitly() -> None:
    grid = _grid(((20, 22.0), (21, 21.0)))

    result = evaluate_parameter_stability(observations=grid, selected_parameter=20, config=CONFIG)

    assert result.stability_label is ParameterStabilityLabel.INSUFFICIENT_DATA
    assert result.stability_score is None
    assert result.parameter_cliff is None
    assert result.plateau_width is None
    assert any("insufficient_neighborhood" in warning for warning in result.warnings)


def test_configuration_sensitivity_changes_result() -> None:
    # Exercises the real YAML load path end-to-end (not just the dataclass)
    # to prove the threshold genuinely comes from the config file rather
    # than being hard-coded. Written next to this test file instead of the
    # OS temp dir, since some sandboxes restrict pytest's shared tmp_path
    # base directory.
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["parameter_stability"]["plateau_relative_tolerance"]["value"] = 0.99
    tightened_path = Path(__file__).with_name("_tightened_strategy_lab_validation.tmp.yaml")
    tightened_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    try:
        tightened_config = load_parameter_stability_config(tightened_path)
    finally:
        tightened_path.unlink()

    default_result = evaluate_parameter_stability(
        observations=STABLE_PLATEAU_GRID, selected_parameter=20, config=CONFIG
    )
    tightened_result = evaluate_parameter_stability(
        observations=STABLE_PLATEAU_GRID, selected_parameter=20, config=tightened_config
    )

    assert default_result.stability_label is ParameterStabilityLabel.STABLE_PLATEAU
    assert tightened_result.stability_label is ParameterStabilityLabel.NARROW_PEAK
    assert tightened_result.plateau_width < default_result.plateau_width


def test_determinism_same_input_same_output() -> None:
    first = evaluate_parameter_stability(
        observations=STABLE_PLATEAU_GRID, selected_parameter=20, config=CONFIG
    )
    second = evaluate_parameter_stability(
        observations=STABLE_PLATEAU_GRID, selected_parameter=20, config=CONFIG
    )

    assert first == second


def test_adversarial_isolated_spike_is_flagged_unstable() -> None:
    """Permanent adversarial fixture for this module (TASK_BRIEF section 11).

    A synthetic surface built to look excellent at exactly one point and
    poor everywhere around it. If a future change to this engine makes this
    test pass with a stable/plateau label, treat it as a regression per the
    RADAR_ENGINEERING_CONSTITUTION adversarial regression rule -- do not
    merge.
    """

    grid = _grid(((10, -2.0), (15, -3.0), (19, -10.0), (20, 50.0), (21, -8.0), (25, -4.0), (30, -1.0)))

    result = evaluate_parameter_stability(observations=grid, selected_parameter=20, config=CONFIG)

    assert result.stability_label is ParameterStabilityLabel.UNSTABLE_CLIFF
    assert result.plateau_width < CONFIG.minimum_plateau_width


def test_plateau_absolute_tolerance_used_when_base_metric_near_zero() -> None:
    # |base_metric_value| <= plateau_absolute_tolerance: a relative gap
    # (|value-base|/|base|) is undefined/unstable this close to zero, so the
    # engine must fall back to the absolute-gap tolerance instead. (selected
    # is also the neighborhood best here, so base_metric_value ==
    # best_metric_value.)
    grid = _grid(((5, -0.015), (7, -0.01), (10, -0.02), (14, -0.012)))

    result = evaluate_parameter_stability(observations=grid, selected_parameter=7, config=CONFIG)

    assert result.best_metric_value == -0.01
    assert result.plateau_width >= 2
    assert result.stability_label is not ParameterStabilityLabel.INSUFFICIENT_DATA


def test_selected_must_be_within_its_own_plateau_for_stable_label() -> None:
    """Code review fix (round 1): a broad plateau elsewhere in the grid must
    not make an isolated selected point STABLE_PLATEAU.

    selected=20 sits with immediate neighbors (19, 21) that are clearly
    worse than it (14.0 vs. 20.5 -- outside plateau_relative_tolerance, but
    not so far as to trip the parameter-cliff threshold, so this isolates
    the plateau-width mechanism from the cliff mechanism). A separate,
    unrelated group (60..66) sits far away in *parameter* space but is
    deliberately chosen numerically *close to base* (~20.3-20.6) so it does
    pass round-3's two-sided closeness test on its own -- the fixture must
    keep proving round 1's point (local contiguous run, not global longest
    run, determines the label) even though the far group is not excluded by
    closeness alone. The engine must recognize that selected's own
    contiguous run has width 1 (only itself, broken immediately by the 14.0
    neighbors) and must not borrow width from the disconnected far run.
    """

    grid = _grid(
        (
            (19, 14.0),
            (20, 20.5),
            (21, 14.0),
            (60, 20.3),
            (62, 20.6),
            (64, 20.4),
            (66, 20.5),
        )
    )

    result = evaluate_parameter_stability(observations=grid, selected_parameter=20, config=CONFIG)

    assert result.stability_label is not ParameterStabilityLabel.STABLE_PLATEAU
    assert result.stability_label is ParameterStabilityLabel.NARROW_PEAK
    assert result.plateau_width == 1
    # Selected always trivially satisfies tolerance against itself (see
    # module docstring) -- plateau_width, not this flag, is what gates the
    # label.
    assert result.selected_within_plateau is True
    # The far plateau is still visible as evidence...
    assert result.evidence["global_plateau_width"] == 4
    # ...and is called out explicitly rather than silently dropped.
    assert "broad_plateau_exists_but_excludes_selected_parameter" in result.warnings


def test_plateau_closeness_excludes_a_distant_far_better_point() -> None:
    """Code review fix (round 3, blocker 2): plateau membership must be a
    two-sided closeness test, not a one-sided "not much worse than base"
    floor.

    20.0/20.1 sit right next to selected=20.5 and form its genuine local
    plateau. Parameter 50's metric (100.0) is dramatically *better* than
    base, not worse -- under a one-sided floor it would still count as
    "not worse than base" and be merged into the same plateau (as it
    incorrectly was before this fix). A real plateau is about closeness,
    not just non-inferiority, so it must be excluded.
    """

    grid = _grid(((19, 20.0), (20, 20.5), (21, 20.1), (50, 100.0)))

    result = evaluate_parameter_stability(observations=grid, selected_parameter=20, config=CONFIG)

    assert result.stability_label is ParameterStabilityLabel.STABLE_PLATEAU
    assert result.selected_within_plateau is True
    # 3 of 4 points (19, 20, 21) are in the local plateau; the far, dramatically
    # better point (50 -> 100.0) is excluded, so width stays at 3, not 4.
    assert result.plateau_width == 3
    assert result.best_metric_value == 100.0


def test_stability_score_is_invariant_to_distant_unrelated_observations() -> None:
    """Code review fix (round 3, blocker 1): appending unrelated, distant
    parameter observations must not change selected's stability_label,
    local plateau conclusion, parameter_cliff, or stability_score.

    Baseline is STABLE_PLATEAU_GRID (selected=20's real local neighborhood
    is unchanged). The augmented grid adds four scattered, far-away
    observations with varied values (some much higher, some much lower,
    none adjacent to selected in sorted parameter order and none forming a
    plateau connected to selected). Locality invariance requires every
    label-determining quantity to match exactly.
    """

    baseline = evaluate_parameter_stability(
        observations=STABLE_PLATEAU_GRID, selected_parameter=20, config=CONFIG
    )

    augmented_grid = STABLE_PLATEAU_GRID + _grid(
        ((500, 5.0), (600, -3.0), (700, 999.0), (800, 0.001))
    )
    augmented = evaluate_parameter_stability(
        observations=augmented_grid, selected_parameter=20, config=CONFIG
    )

    assert augmented.stability_label is baseline.stability_label
    assert augmented.stability_label is ParameterStabilityLabel.STABLE_PLATEAU
    assert augmented.plateau_width == baseline.plateau_width
    assert augmented.selected_within_plateau == baseline.selected_within_plateau
    assert augmented.parameter_cliff == baseline.parameter_cliff
    assert augmented.stability_score == baseline.stability_score
    # Sanity check that the augmented grid is actually larger, i.e. this
    # isn't trivially passing because nothing was added.
    assert augmented.parameter_count == baseline.parameter_count + 4


def test_direction_as_plain_string_is_validated_not_silently_misinterpreted() -> None:
    """Code review fix (round 3, blocker 3): MetricDirection subclasses str,
    so a plain string equal to a member's value is == but not `is` that
    member. Every internal comparison in this module uses `is`, so passing
    the unconverted string "maximize" must not silently fall through to
    MINIMIZE behavior -- it must be normalized through MetricDirection(...)
    at entry and behave identically to passing the enum member.
    """

    via_enum = evaluate_parameter_stability(
        observations=STABLE_PLATEAU_GRID,
        selected_parameter=20,
        config=CONFIG,
        direction=MetricDirection.MAXIMIZE,
    )
    via_string = evaluate_parameter_stability(
        observations=STABLE_PLATEAU_GRID,
        selected_parameter=20,
        config=CONFIG,
        direction="maximize",
    )

    assert via_string == via_enum
    assert via_string.direction is MetricDirection.MAXIMIZE
    # If direction had silently been left as the raw string and compared
    # with `is` against MetricDirection.MAXIMIZE, best_metric_value would
    # have picked min() instead of max() here.
    assert via_string.best_metric_value == 21.9


def test_direction_invalid_value_fails_closed() -> None:
    with pytest.raises(ValueError):
        evaluate_parameter_stability(
            observations=STABLE_PLATEAU_GRID,
            selected_parameter=20,
            config=CONFIG,
            direction="max",  # typo / not a recognized MetricDirection value
        )


def test_positive_minimize_metric_plateau_is_not_broken_by_sign_flip() -> None:
    """Code review fix (round 4): closeness must not depend on direction.

    Cost-ratio-style MINIMIZE metric, all positive: 9.5 / 10.0 (selected) /
    10.4 -- three values within ~5% of each other, a textbook local
    plateau. The earlier implementation oriented value/base by direction's
    sign before branching on relative-vs-absolute tolerance; under MINIMIZE
    that flipped base=10.0 to -10.0, which is <= 0, so it incorrectly fell
    into the absolute-tolerance branch (default 0.02) and rejected both real
    neighbors (real gaps of 0.5 and 0.4 dwarf a 0.02 absolute tolerance).
    Plateau membership must be a pure magnitude comparison, independent of
    direction.
    """

    grid = _grid(((1, 9.5), (2, 10.0), (3, 10.4)))

    result = evaluate_parameter_stability(
        observations=grid,
        selected_parameter=2,
        config=CONFIG,
        direction=MetricDirection.MINIMIZE,
    )

    assert result.plateau_width == 3
    assert result.selected_within_plateau is True


def test_direction_does_not_change_plateau_closeness() -> None:
    """Code review fix (round 4): MAXIMIZE vs MINIMIZE on the identical
    numeric surface must agree on plateau membership and width -- direction
    may only change which value counts as best/worst and which side of an
    adjacent step counts as a cliff drop.
    """

    result_max = evaluate_parameter_stability(
        observations=STABLE_PLATEAU_GRID,
        selected_parameter=20,
        config=CONFIG,
        direction=MetricDirection.MAXIMIZE,
    )
    result_min = evaluate_parameter_stability(
        observations=STABLE_PLATEAU_GRID,
        selected_parameter=20,
        config=CONFIG,
        direction=MetricDirection.MINIMIZE,
    )

    # Closeness (plateau membership) is identical regardless of direction.
    assert result_max.plateau_width == result_min.plateau_width
    assert result_max.selected_within_plateau == result_min.selected_within_plateau
    assert result_max.evidence["global_plateau_width"] == result_min.evidence["global_plateau_width"]

    # Only direction-dependent semantics (better/worse) are allowed to differ.
    assert result_max.best_metric_value == 21.9  # max of the grid
    assert result_min.best_metric_value == 18.7  # min of the grid
    assert result_max.best_metric_value != result_min.best_metric_value
    assert result_max.parameter_cliff != result_min.parameter_cliff


def test_plateau_membership_anchored_to_selected_not_distant_global_best() -> None:
    """Code review fix (round 2, blocker): plateau membership must be
    measured against the selected/base metric, not the neighborhood's
    global best.

    17/19/21/23 form a genuine local plateau around selected=20 (20.0-20.5
    range). Parameter 100 is a distant, isolated, unrelated observation that
    happens to be the neighborhood's global best (100.0). Under the
    pre-fix, best-anchored tolerance, the plateau_relative_tolerance=0.85
    threshold would have been anchored to 100.0 (=85.0) -- every real local
    point (19.0-20.5) sits far below that, so the local plateau around
    selected would have been entirely excluded and mislabeled. best_metric_value
    must still correctly report 100.0 as an informational field, but it must
    not gate whether selected's own local plateau is recognized.
    """

    grid = _grid(((17, 19.0), (19, 20.0), (20, 20.5), (21, 20.1), (23, 19.3), (100, 100.0)))

    result = evaluate_parameter_stability(observations=grid, selected_parameter=20, config=CONFIG)

    assert result.stability_label is ParameterStabilityLabel.STABLE_PLATEAU
    assert result.best_metric_value == 100.0
    assert result.base_metric_value == 20.5
    assert result.selected_within_plateau is True
    assert result.plateau_width >= CONFIG.minimum_plateau_width


def test_parameter_cliff_not_diluted_by_distant_outliers() -> None:
    """Code review fix: cliff normalization must be local to the selected
    point's immediate neighbors, not the full neighborhood.

    Same 19/20/21 single-point-overfit shape as
    test_single_point_overfit_is_flagged_unstable, plus two extreme,
    far-away outliers (parameter 5 and 200) that are nowhere near selected.
    Under the pre-fix logic, cliff normalization used the *global* neighbor
    dispersion (which these outliers blow up to roughly 670+), driving the
    cliff ratio for the 19/20/21 spike down to ~0.025 -- well under the 0.5
    threshold -- so the known-bad case would have escaped detection. Cliff
    normalization must depend only on the selected point's immediate
    left/right neighbors so this cannot happen.
    """

    grid = _grid(((5, -1000.0), (19, 7.0), (20, 22.0), (21, 5.0), (200, 900.0)))

    result = evaluate_parameter_stability(observations=grid, selected_parameter=20, config=CONFIG)

    assert result.stability_label is ParameterStabilityLabel.UNSTABLE_CLIFF
    assert result.parameter_cliff >= CONFIG.cliff_relative_drop_threshold
    # The outliers still show up in the (informational, non-cliff) global
    # dispersion figure -- only the cliff normalization ignores them.
    assert result.neighbor_dispersion > 100


def test_minimize_direction_stable_plateau_mirrors_maximize_case() -> None:
    # Same shape as STABLE_PLATEAU_GRID, negated: a "lower is better" metric
    # (e.g. drawdown magnitude) where the selected point is still the true
    # best. Proves best_metric_value picks the minimum, not max().
    grid = _grid(((17, -18.7), (20, -21.9), (22, -20.5), (25, -18.9)))

    result = evaluate_parameter_stability(
        observations=grid,
        selected_parameter=20,
        config=CONFIG,
        direction=MetricDirection.MINIMIZE,
    )

    assert result.stability_label is ParameterStabilityLabel.STABLE_PLATEAU
    assert result.best_metric_value == -21.9
    assert result.base_metric_value == -21.9
    assert result.plateau_width == 4


def test_minimize_direction_single_point_overfit_still_flagged_unstable() -> None:
    # Same shape as SINGLE_POINT_OVERFIT_GRID, negated: selected is an
    # isolated *good* (very negative) spike surrounded by much worse
    # (less negative) neighbors under a minimize-is-better metric.
    grid = _grid(((19, -7.0), (20, -22.0), (21, -5.0)))

    result = evaluate_parameter_stability(
        observations=grid,
        selected_parameter=20,
        config=CONFIG,
        direction=MetricDirection.MINIMIZE,
    )

    assert result.stability_label is ParameterStabilityLabel.UNSTABLE_CLIFF
    assert result.best_metric_value == -22.0
    assert result.parameter_cliff >= CONFIG.cliff_relative_drop_threshold


def test_malformed_neighborhood_fails_closed() -> None:
    duplicate_grid = _grid(((20, 1.0), (20, 2.0), (21, 1.5)))
    with pytest.raises(ValueError):
        evaluate_parameter_stability(observations=duplicate_grid, selected_parameter=20, config=CONFIG)

    with pytest.raises(ValueError):
        evaluate_parameter_stability(
            observations=STABLE_PLATEAU_GRID, selected_parameter=999, config=CONFIG
        )

    with pytest.raises(ValueError):
        evaluate_parameter_stability(observations=(), selected_parameter=20, config=CONFIG)
