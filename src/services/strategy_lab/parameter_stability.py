"""Parameter Stability Engine.

Answers a narrower question than "is this strategy good": does the observed
edge at a selected parameter persist across its parameter neighborhood, or
does it collapse off a single lucky point? Strategy-independent; it consumes
a caller-supplied parameter grid and metric summaries and never reads
PerformanceReport fields itself.

Parameter Plateau > Best Parameter. A broad, gently-degrading neighborhood is
treated as materially more trustworthy than one isolated spike, regardless of
how large that spike's metric value is. This module reports the *shape* of
the parameter surface only; it makes no claim about whether that surface is
profitable. A flat, weak surface can legitimately be reported STABLE_PLATEAU
-- callers must judge magnitude (e.g. via PerformanceReport) separately.

STABLE_PLATEAU requires the *selected* parameter itself to sit inside a
qualifying contiguous plateau -- a broad plateau elsewhere in the neighborhood
does not make an isolated selected point stable. The Parameter Cliff check
only ever looks at the selected point's immediate left/right neighbors, so a
distant extreme observation cannot dilute or mask a local single-point spike.

Plateau membership is measured relative to the *selected/base* parameter's
own metric, not the neighborhood's global best. The question this engine
answers is "is the selected parameter's edge stable in its own
neighborhood", not "is the selected parameter close to the best point
anywhere in the grid" -- a distant, unrelated, isolated best observation
must not be able to invalidate a real local plateau that surrounds the
selected parameter. ``best_metric_value`` remains a purely informational
output/evidence field; it never gates plateau membership or the label. A
direct consequence: the selected point always trivially satisfies tolerance
against itself, so ``selected_within_plateau`` is always True and
``plateau_width`` is always at least 1 once the neighborhood is large enough
to evaluate at all -- ``plateau_width < minimum_plateau_width`` (i.e.
whether any *neighboring* points also qualify) is what actually drives the
NARROW_PEAK/STABLE_PLATEAU distinction.

Plateau membership is a *closeness* test, not a one-sided floor: a point
counts as part of selected's plateau only if its relative gap from the base
metric (``|value - base| / |base|``) is within tolerance. A point
dramatically *better* than base -- e.g. a distant, isolated best observation
elsewhere in the grid -- is excluded exactly like a point dramatically
worse; "close to selected" is not the same question as "not much worse than
selected", and only the former is a real plateau.

Closeness ("near/far") and direction ("better/worse") are different
questions, and plateau membership depends only on the first. Whether a
point is *near* the base metric is a magnitude comparison and needs no
sign information at all; it is computed identically regardless of
``direction`` (MAXIMIZE and MINIMIZE always produce the same
plateau_width/selected_within_plateau for the same numeric surface).
Flipping value/base by direction's sign before that comparison -- as an
earlier version of this module did -- was a real bug: a positive MINIMIZE
metric like a cost ratio (base=10.0) would flip to -10.0, incorrectly fall
into the near-zero absolute-tolerance branch, and reject genuinely close
neighbors (9.5, 10.4). ``direction`` only ever affects ``best_metric_value``,
``neighbor_worst``, and ``parameter_cliff`` -- never plateau membership.

Every quantity that determines ``stability_score`` and ``stability_label``
is strictly local to the selected point's own contiguous neighborhood:
``plateau_width`` (the local run) and ``parameter_cliff`` (the immediate
left/right neighbors) never depend on how many other, unrelated
observations exist elsewhere in the supplied grid, nor on the grid's total
size. Concretely, ``stability_score`` normalizes plateau width against a
fixed, configured saturation width, never against ``len(observations)`` --
appending distant, unrelated parameter observations must never change
selected's stability_label, plateau conclusion, or parameter_cliff
(locality invariance). Fields that *do* summarize the whole supplied grid
(``best_metric_value``, ``neighbor_median``, ``neighbor_worst``,
``neighbor_dispersion``, ``evidence["global_plateau_width"]``) are
deliberately informational only and never feed the label.

Metrics may be either "higher is better" (e.g. CAGR) or "lower is better"
(e.g. a cost ratio); pass ``direction`` accordingly. Direction must match
how the metric is actually represented, not assumed from its usual meaning:
e.g. max drawdown is commonly reported as a negative percentage where less
negative (numerically larger) is better, which is MAXIMIZE, not MINIMIZE --
only a drawdown reported as a positive magnitude, where smaller is better,
is MINIMIZE. Every reported value (base/best/neighbor_worst/etc.) is always
the true, un-negated metric -- direction only changes which value counts as
"best" and which side of an adjacent step counts as a "drop".

``direction`` is validated through ``MetricDirection(direction)`` at entry.
``MetricDirection`` subclasses ``str``, so a plain string equal to a
member's value (e.g. ``"maximize"``) is == but not `is` that member --
every internal comparison in this module uses ``is``, so an unconverted
string would silently compare unequal and fall through to MINIMIZE
behavior. Converting through the enum constructor first also rejects any
unrecognized value with ``ValueError`` instead of silently misinterpreting
it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from statistics import median, pstdev
from typing import Any, Mapping, Sequence

from .config import ParameterStabilityConfig


class MetricDirection(str, Enum):
    """Which direction of a metric's own value scale counts as "better".

    Determined by how the metric is actually represented, never assumed
    from what the metric conceptually measures. A max-drawdown metric
    stored as a negative percentage (e.g. -8.0 for -8%) is MAXIMIZE, since
    a less-negative value (closer to zero, e.g. -3.0) is better -- the same
    drawdown stored as a positive magnitude (e.g. 8.0) is MINIMIZE. Inspect
    the caller's actual sign convention before choosing.
    """

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class ParameterStabilityLabel(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    UNSTABLE_CLIFF = "unstable_cliff"
    NARROW_PEAK = "narrow_peak"
    FRAGILE = "fragile"
    STABLE_PLATEAU = "stable_plateau"


@dataclass(frozen=True)
class ParameterObservation:
    parameter_value: float
    metric_value: float

    def __post_init__(self) -> None:
        if not isfinite(self.parameter_value):
            raise ValueError("parameter_value must be finite")
        if not isfinite(self.metric_value):
            raise ValueError("metric_value must be finite")


@dataclass(frozen=True)
class ParameterStabilityResult:
    parameter_count: int
    selected_parameter: float
    direction: MetricDirection
    stability_label: ParameterStabilityLabel
    warnings: tuple[str, ...]
    base_metric_value: float | None = None
    best_metric_value: float | None = None
    neighbor_median: float | None = None
    neighbor_worst: float | None = None
    neighbor_dispersion: float | None = None
    parameter_cliff: float | None = None
    plateau_width: int | None = None
    selected_within_plateau: bool | None = None
    stability_score: float | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)


def evaluate_parameter_stability(
    *,
    observations: Sequence[ParameterObservation],
    selected_parameter: float,
    config: ParameterStabilityConfig,
    direction: MetricDirection = MetricDirection.MAXIMIZE,
) -> ParameterStabilityResult:
    """Evaluate a parameter neighborhood around one selected/base parameter.

    ``observations`` is the full neighborhood grid (selected point included),
    e.g. breakout periods 15/17/20/22/25/30 with their backtest metric for
    each. Raises ``ValueError`` on malformed input (duplicate parameter
    values, or a selected_parameter absent from the grid) rather than
    silently guessing. Too few observations is not malformed -- it is
    reported as ParameterStabilityLabel.INSUFFICIENT_DATA with no fabricated
    score, per the sparse-neighborhood requirement.

    ``plateau_width`` is the length of the contiguous in-tolerance run that
    *contains the selected parameter* -- not the longest run anywhere in the
    neighborhood. A broad plateau elsewhere in the grid is exposed only via
    ``evidence["global_plateau_width"]`` and never upgrades the label on its
    own. Tolerance is measured against the selected point's own metric
    (``base_metric_value``), not the neighborhood's global best -- a
    distant, unrelated best observation elsewhere in the grid must not be
    able to shrink or invalidate a real local plateau around the selected
    parameter. ``best_metric_value`` is reported for information only.
    Membership is a two-sided closeness test: a point far *better* than base
    is excluded just like one far worse. Closeness is a pure magnitude
    comparison and does not depend on ``direction`` -- MAXIMIZE and MINIMIZE
    always agree on plateau_width/selected_within_plateau for the same
    numeric surface; direction only ever changes best_metric_value,
    neighbor_worst, and parameter_cliff.

    ``direction`` is converted through ``MetricDirection(direction)``
    before use, so a plain string like ``"maximize"`` resolves to the
    correct enum member (rather than silently comparing unequal to
    ``MetricDirection.MAXIMIZE`` via ``is`` and falling through to MINIMIZE
    behavior); an unrecognized value raises ``ValueError`` immediately
    (fail closed).
    """

    direction = MetricDirection(direction)

    if not observations:
        raise ValueError("observations must not be empty")

    ordered = tuple(sorted(observations, key=lambda point: point.parameter_value))
    parameter_values = tuple(point.parameter_value for point in ordered)
    if len(set(parameter_values)) != len(parameter_values):
        raise ValueError("observations must not contain duplicate parameter_value entries")

    matches = [index for index, value in enumerate(parameter_values) if value == selected_parameter]
    if not matches:
        raise ValueError("selected_parameter must be present among observations")
    selected_index = matches[0]

    total_points = len(ordered)
    evidence: dict[str, Any] = {
        "parameter_values": parameter_values,
        "metric_values": tuple(point.metric_value for point in ordered),
        "selected_index": selected_index,
    }

    if total_points < config.minimum_neighborhood_size:
        return ParameterStabilityResult(
            parameter_count=total_points,
            selected_parameter=selected_parameter,
            direction=direction,
            stability_label=ParameterStabilityLabel.INSUFFICIENT_DATA,
            warnings=(
                f"insufficient_neighborhood: have {total_points} points, "
                f"need at least {config.minimum_neighborhood_size}",
            ),
            evidence=evidence,
        )

    metric_values = tuple(point.metric_value for point in ordered)
    base_metric_value = metric_values[selected_index]
    best_metric_value = (
        max(metric_values) if direction is MetricDirection.MAXIMIZE else min(metric_values)
    )
    neighbor_values = metric_values[:selected_index] + metric_values[selected_index + 1 :]
    neighbor_median = median(neighbor_values)
    neighbor_worst = (
        min(neighbor_values) if direction is MetricDirection.MAXIMIZE else max(neighbor_values)
    )
    neighbor_dispersion = pstdev(neighbor_values) if len(neighbor_values) > 1 else 0.0

    parameter_cliff = _adjacent_cliff(
        metric_values=metric_values,
        selected_index=selected_index,
        base_metric_value=base_metric_value,
        config=config,
        direction=direction,
    )

    in_plateau = tuple(
        _within_plateau_tolerance(value, base_metric_value, config) for value in metric_values
    )
    plateau_width = _local_plateau_width(in_plateau, selected_index)
    selected_within_plateau = in_plateau[selected_index]
    evidence["global_plateau_width"] = _longest_run(in_plateau)

    # Locality invariance: normalize against a fixed, configured saturation
    # width, never against total_points -- appending unrelated distant
    # observations must not change selected's score or label.
    plateau_fraction = min(1.0, plateau_width / config.plateau_score_saturation_width)
    cliff_component = min(1.0, parameter_cliff / config.cliff_relative_drop_threshold)
    stability_score = max(0.0, min(1.0, 0.5 * plateau_fraction + 0.5 * (1 - cliff_component)))

    cliff_triggered = parameter_cliff >= config.cliff_relative_drop_threshold
    warnings: list[str] = []

    if cliff_triggered:
        label = ParameterStabilityLabel.UNSTABLE_CLIFF
        warnings.append("parameter_cliff_detected")
    elif plateau_width < config.minimum_plateau_width:
        label = ParameterStabilityLabel.NARROW_PEAK
        warnings.append("narrow_or_isolated_peak")
        if evidence["global_plateau_width"] >= config.minimum_plateau_width:
            warnings.append("broad_plateau_exists_but_excludes_selected_parameter")
    elif stability_score >= config.stability_score_stable_floor:
        label = ParameterStabilityLabel.STABLE_PLATEAU
    elif stability_score < config.stability_score_fragile_ceiling:
        label = ParameterStabilityLabel.FRAGILE
        warnings.append("low_stability_score")
    else:
        label = ParameterStabilityLabel.NARROW_PEAK
        warnings.append("plateau_below_stable_floor")

    return ParameterStabilityResult(
        parameter_count=total_points,
        selected_parameter=selected_parameter,
        direction=direction,
        stability_label=label,
        warnings=tuple(warnings),
        base_metric_value=base_metric_value,
        best_metric_value=best_metric_value,
        neighbor_median=neighbor_median,
        neighbor_worst=neighbor_worst,
        neighbor_dispersion=neighbor_dispersion,
        parameter_cliff=parameter_cliff,
        plateau_width=plateau_width,
        selected_within_plateau=selected_within_plateau,
        stability_score=stability_score,
        evidence=evidence,
    )


def _adjacent_cliff(
    *,
    metric_values: tuple[float, ...],
    selected_index: int,
    base_metric_value: float,
    config: ParameterStabilityConfig,
    direction: MetricDirection,
) -> float:
    """Cliff ratio from the selected point to its immediate neighbors only.

    Deliberately local: normalization uses only the one or two adjacent
    observations (never the full neighborhood), so a distant extreme point
    elsewhere in the grid cannot dilute the scale and mask a real local
    spike.
    """

    adjacent_values: list[float] = []
    if selected_index > 0:
        adjacent_values.append(metric_values[selected_index - 1])
    if selected_index < len(metric_values) - 1:
        adjacent_values.append(metric_values[selected_index + 1])
    if not adjacent_values:
        return 0.0

    local_dispersion = pstdev(adjacent_values) if len(adjacent_values) > 1 else 0.0
    scale = max(abs(base_metric_value), local_dispersion, config.cliff_minimum_scale)
    sign = 1.0 if direction is MetricDirection.MAXIMIZE else -1.0
    drops = [sign * (base_metric_value - value) / scale for value in adjacent_values]
    return max(0.0, max(drops))


def _within_plateau_tolerance(
    value: float,
    reference_metric_value: float,
    config: ParameterStabilityConfig,
) -> bool:
    """Is ``value`` *close to* ``reference_metric_value`` (both sides)?

    ``reference_metric_value`` is always the selected/base point's own
    metric, never the neighborhood's global best -- see the module
    docstring. This is a symmetric closeness test, not a one-sided "not
    much worse than reference" floor: a value far *better* than the
    reference is excluded exactly like one far worse, so a distant,
    unrelated, dramatically-better observation elsewhere in the grid cannot
    be mistaken for the same local plateau. The selected point is always
    compared against itself here, so it always trivially passes.

    Deliberately takes no ``direction``: closeness ("is this point near
    selected") and direction ("is better bigger or smaller") are different
    questions. Flipping the sign of a positive MINIMIZE metric before
    comparing it against a positive/negative-branch split would wrongly
    push it into the absolute-tolerance branch and reject real, close
    neighbors (e.g. a cost-ratio base of 10.0 becoming -10.0 and losing its
    real 9.5/10.4 neighbors). Comparing raw magnitude via
    ``relative_gap = |value - reference| / |reference|`` needs no sign
    information at all, so MAXIMIZE and MINIMIZE always produce identical
    plateau membership for the same numeric surface -- direction only ever
    changes best_metric_value, neighbor_worst, and parameter_cliff.
    """

    if abs(reference_metric_value) <= config.plateau_absolute_tolerance:
        # Reference itself sits inside the absolute-tolerance band around
        # zero, where a relative gap is undefined/unstable (division by a
        # near-zero denominator) -- compare absolute distance instead.
        return abs(reference_metric_value - value) <= config.plateau_absolute_tolerance
    relative_gap = abs(value - reference_metric_value) / abs(reference_metric_value)
    return relative_gap <= (1.0 - config.plateau_relative_tolerance)


def _local_plateau_width(flags: Sequence[bool], index: int) -> int:
    """Length of the contiguous in-tolerance run that contains ``index``.

    Returns 0 when the point at ``index`` is not itself in-tolerance -- a
    plateau elsewhere in the grid never counts toward the selected point's
    own stability.
    """

    if not flags[index]:
        return 0
    width = 1
    cursor = index - 1
    while cursor >= 0 and flags[cursor]:
        width += 1
        cursor -= 1
    cursor = index + 1
    while cursor < len(flags) and flags[cursor]:
        width += 1
        cursor += 1
    return width


def _longest_run(flags: Sequence[bool]) -> int:
    longest = 0
    current = 0
    for flag in flags:
        if flag:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest
