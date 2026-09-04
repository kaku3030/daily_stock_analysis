"""Cost / Execution Stress Test Foundation.

Answers a narrower question than "is this strategy good": if commissions
are higher, entry/exit price slippage (including spread) is worse, or
fills are delayed by one or two bars, than assumed, does the strategy's
edge survive -- and by how much? Strategy-independent; it consumes a
caller-supplied sequence of per-trade execution observations and never
reads PerformanceReport fields itself. This is Signal Edge vs Execution
Edge separation: the module has no opinion on whether the underlying
signal is good, only on how much of its realized edge survives
worse-than-assumed execution.

The frozen minimal input per trade is ``side`` + ``quantity`` + signal
timestamps + a delay-0 (baseline) entry/exit price point + a fee estimate
+ independent entry/exit slippage friction estimates. Additional +1/+2
bar delay price points are optional -- missing them degrades only the
delay dimensions that need them, it never blocks the (1.0x, 0-bar)
reference evaluation.

``quantity`` is a required, explicit, positive input (never inferred from
price movement and realized PnL). An earlier draft of this module proposed
deriving an implicit "unit exposure" from ``baseline_pnl / price_move``,
which was rejected: besides being undefined for a zero-price-move trade, it
would have silently reconstructed a position size the module has no
business inferring. ``quantity`` here is a *unit-conversion* value only --
identical across every scenario for a given trade, never compared or ranked
across trades, never used to reward or penalize a strategy for how large a
position it took. That is what keeps this outside Position Sizing Engine
territory: this module answers "does this trade's own historical price
movement, converted through its own already-realized size, survive worse
execution", not "is this a good size to trade."

The engine computes PnL itself from price and quantity -- callers do not
supply a pre-computed ``baseline_pnl``:

    gross_pnl = side_sign * (exit_price - entry_price) * quantity
    net_pnl   = gross_pnl - cost

``ExecutionPricePoint.reference_price`` is, by contract, a *causal,
executable, pre-slippage* reference price -- e.g. the actual traded price
at that bar, with no slippage assumption baked into it. The engine is what
applies slippage on top of it (see below); a caller must not pre-adjust a
reference price for assumed slippage, or slippage is counted twice. If a
venue's bid-ask spread produces price-based degradation that is not
already reflected in ``reference_price`` itself, that degradation belongs
in ``baseline_entry_slippage_bps`` / ``baseline_exit_slippage_bps``, never
folded into ``baseline_fee_cost`` -- the two frictions are modeled through
entirely different mechanisms (a price adjustment vs. a currency
subtraction) and must not double-count the same real-world cost.
``baseline_fee_cost`` remains explicit monetary commission/fees only, full
stop -- it has no role in modeling spread or any other price-based
degradation.

Execution friction has two independent components, deliberately modeled
differently because they are different things:

- **Fee** (``baseline_fee_cost``) is explicit monetary commission/fees only
  -- a direct PnL-currency amount, scaled linearly by the cost multiplier
  ``k``: ``cost(k) = k * baseline_fee_cost``. This is pure subtraction --
  it never touches a price, so it is structurally immune to long/short
  sign bugs. It must never include slippage or spread; those are the
  engine's job to model via price adjustment, not the caller's job to fold
  into a currency figure.
- **Slippage** (``baseline_entry_slippage_bps`` and
  ``baseline_exit_slippage_bps``, adverse price impact -- this is also
  where bid-ask spread crossing belongs, per the frozen requirement's own
  "slippage/spread" pairing) are two *independently representable*
  basis-points rates -- entry and exit fills are not guaranteed to face the
  same friction, so the frozen execution model requires them separately,
  not a single shared rate. Both are scaled by ``k`` and applied to a
  *reference price* in the direction that is actually adverse for the
  position's side -- getting this backwards for one side is exactly the
  bug class this module is built to prevent. For a LONG (buy to open, sell
  to close), adverse slippage means a *worse* (higher) entry fill and a
  *worse* (lower) exit fill; a SHORT is the mirror image (worse = lower
  entry, worse = higher exit, since a short sells first and buys back
  later):

      LONG:  entry_adjusted = entry_reference * (1 + k * entry_slip)
             exit_adjusted  = exit_reference  * (1 - k * exit_slip)
      SHORT: entry_adjusted = entry_reference * (1 - k * entry_slip)
             exit_adjusted  = exit_reference  * (1 + k * exit_slip)

  where ``entry_slip = baseline_entry_slippage_bps / 10_000`` and
  ``exit_slip = baseline_exit_slippage_bps / 10_000``. Both sides use the
  *same* ``gross_pnl = side_sign * (exit_adjusted - entry_adjusted) *
  quantity`` formula afterward -- there is no side-specific PnL formula,
  only a side-specific price-adjustment direction, which is what makes a
  "subtract slippage from exit price" style bug (correct for LONG, wrong
  for SHORT) structurally impossible here.

The scenario matrix is cost_multipliers x delay_levels (V0.1 default
``{1.0, 1.5, 2.0} x {0, 1, 2}`` bars). ``(1.0x, 0 bars)`` is the *one*
realistic reference execution -- delay-0 reference prices, 1x entry/exit
slippage, 1x fee -- not a zero-friction fantasy baseline: ``baseline_fee_cost``
and both slippage rates are still applied at their unscaled (k=1.0)
values, because real execution never has zero friction. Every aggregate
baseline/reference net PnL used anywhere in this module -- the top-level
eligibility gate, each delay level's own retention denominator, and the
break-even solve -- is derived from this one ``(1.0x, 0 bars)`` computation
path (``_scenario_gross_and_cost`` at ``cost_multiplier=1.0,
delay_bars=0``, or an algebraic combination of two evaluations of that same
function). There is deliberately no second, independently-implemented
"baseline" formula anywhere in this module.

Missing delay-price data is never treated as zero slippage. A trade
without a supplied price point at a given delay is excluded from that
delay level's *entire* cohort -- both the stressed numerator and its own
reference-execution denominator -- it never falls back to the baseline
(0-bar) price, and it never has its stressed PnL measured against a
denominator that still includes trades the numerator dropped. For each
delay level ``d``, let ``C_d`` be the set of trades with a price point at
``d`` (``C_0`` is always every trade, since delay-0 is mandatory input).
Retention at ``(k, d)`` is

    retention(k, d) = (sum of net_pnl(k, d) over C_d) / (sum of net_pnl(1.0, 0) over C_d)

-- the *same* cohort ``C_d`` on both sides. An earlier draft of this module
computed the denominator over the full trade set regardless of ``d``, which
silently conflated "some trades lack delay data" with "execution degraded"
-- a delay level where every *available* trade showed zero true
degradation was still reported as a lower retention purely because of the
coverage gap. Two independent conditions gate a delay level's
availability, checked in this order:

- **Coverage**: the fraction of *absolute* baseline (1.0x, 0-bar) gross PnL
  (over the *full* trade set, not ``C_d``) held by trades in ``C_d`` --
  absolute value because both large winners and large losers losing their
  delay data equally threaten the sample's representativeness. Below the
  configured minimum, every scenario cell at that delay level comes back
  ``retention=None`` with an ``insufficient_delay_{d}_price_coverage``
  warning.
- **Cohort baseline positivity**: even once coverage clears, ``C_d``'s own
  reference-execution net PnL (the denominator above) must itself be
  positive -- dividing by a non-positive cohort baseline is exactly as
  undefined as the top-level ``NO_POSITIVE_BASELINE_EDGE`` case, just
  scoped to one delay level's subset of trades. If it is not, every
  scenario cell at that delay level comes back ``retention=None`` with a
  ``delay_{d}_cohort_baseline_not_positive`` warning, rather than dividing
  by a non-positive number.

Execution Fragility Score is ``1 - clamp(worst_retention, 0, 1)`` where
``worst_retention`` is the minimum retention ratio across every *eligible*
scenario cell (available delay levels only) -- a weakest-link aggregation
across the whole matrix, not the max of two independently-evaluated single
axes (which would understate risk by never checking the actual joint
cost+delay scenario). ``worst_retention`` itself is reported unclamped and
may be negative; only the derived ``fragility_score`` is bounded to
``[0, 1]``.

Two "cannot compute a trustworthy score" states are checked, in this fixed
order, before any real label is produced:

- ``NO_POSITIVE_BASELINE_EDGE`` (checked first, regardless of trade count):
  the aggregate baseline (1.0x, 0-bar) net PnL over the *full* trade set is
  not positive. Retention is a ratio against that baseline; dividing by a
  non-positive number is undefined, not "perfectly robust" and not a
  sample-size problem.
- ``INSUFFICIENT_DATA``: too few trades to trust the aggregate.

Break-even cost multiplier answers "at what cost multiplier does the
(delay-0) reference-execution net PnL cross zero", using the fact that
``net_pnl(k, 0)`` is exactly linear in ``k`` even with independent
entry/exit slippage rates: per trade, ``gross_pnl(k, 0) = raw_gross - k *
slippage_loss(1x)`` where ``slippage_loss(1x) = quantity * (entry_reference
* entry_slip_rate + exit_reference * exit_slip_rate)`` (both slippage rates
scale with ``k`` too, per this module's own design, since ``k`` stresses
fee *and* slippage together), so ``net_pnl(k, 0) = raw_gross - k *
(slippage_loss(1x) + baseline_fee_cost) = A - k*F`` for constants ``A``
(raw, frictionless gross PnL) and ``F`` (total 1x friction: slippage loss
plus fee). An earlier draft computed break-even as ``gross_pnl(k=1) /
baseline_fee_cost``, which implicitly assumed slippage stayed frozen at its
k=1 value while only fee scaled -- a materially different, smaller-magnitude
question than the actual scenario matrix's own k-axis (where slippage
scales with k exactly like fee does), and numerically overestimated the
true break-even multiplier whenever either slippage rate is nonzero. ``A``
and ``F`` are
derived, not reimplemented, from two evaluations of the same
``_scenario_gross_and_cost`` used for every scenario cell (at
``cost_multiplier=0.0`` and ``cost_multiplier=1.0``, both at ``delay_bars=0``):
``A`` is the gross PnL at zero friction, and ``F = A - net_pnl(1.0, 0)``.
``break_even_cost_multiplier = A / F`` is defined only when ``F > 0``
(cost-only in the sense that it solves along the existing delay-0
reference row of the matrix, not a hypothetical fee-only axis that does
not otherwise exist in this module); it is evidence-only, never gates the
score, and is not an optimizer over the delay dimension.

This module performs a structural, input-integrity causality check --
delayed execution timestamps may not precede their signal timestamp, and
delay-N execution timestamps may not precede delay-(N-1)'s -- inside
``ExecutionObservation.__post_init__``. This is not a substitute for a
future Hard Gate: it only rejects internally-inconsistent input at
construction time; it does not verify anything about the real market or
read any external data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any, Mapping, Sequence

from .config import ExecutionStressConfig


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class ExecutionFragilityLabel(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    NO_POSITIVE_BASELINE_EDGE = "no_positive_baseline_edge"
    ROBUST = "robust"
    MODERATE = "moderate"
    FRAGILE = "fragile"
    EXTREME = "extreme"


@dataclass(frozen=True)
class ExecutionPricePoint:
    """A causal, executable, pre-slippage reference price at a point in
    time. The engine -- not the caller -- applies slippage on top of
    ``reference_price``; pre-adjusting it for assumed slippage would double
    count that friction.
    """

    timestamp: datetime
    reference_price: float

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if not isfinite(self.reference_price) or self.reference_price <= 0:
            raise ValueError("reference_price must be a positive finite value")


@dataclass(frozen=True)
class ExecutionObservation:
    side: PositionSide
    quantity: float
    entry_signal_timestamp: datetime
    exit_signal_timestamp: datetime
    entry_prices: Mapping[int, ExecutionPricePoint]
    exit_prices: Mapping[int, ExecutionPricePoint]
    baseline_fee_cost: float = 0.0
    baseline_entry_slippage_bps: float = 0.0
    baseline_exit_slippage_bps: float = 0.0

    def __post_init__(self) -> None:
        try:
            side = PositionSide(self.side)
        except ValueError as exc:
            raise ValueError(f"side must be a valid PositionSide, got {self.side!r}") from exc
        object.__setattr__(self, "side", side)

        if not isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError("quantity must be a positive finite value")
        if not isinstance(self.entry_signal_timestamp, datetime):
            raise ValueError("entry_signal_timestamp must be a datetime")
        if not isinstance(self.exit_signal_timestamp, datetime):
            raise ValueError("exit_signal_timestamp must be a datetime")
        if not isfinite(self.baseline_fee_cost) or self.baseline_fee_cost < 0:
            raise ValueError("baseline_fee_cost must be a non-negative finite value")
        if not isfinite(self.baseline_entry_slippage_bps) or self.baseline_entry_slippage_bps < 0:
            raise ValueError("baseline_entry_slippage_bps must be a non-negative finite value")
        if not isfinite(self.baseline_exit_slippage_bps) or self.baseline_exit_slippage_bps < 0:
            raise ValueError("baseline_exit_slippage_bps must be a non-negative finite value")

        for label, prices, signal_timestamp in (
            ("entry", self.entry_prices, self.entry_signal_timestamp),
            ("exit", self.exit_prices, self.exit_signal_timestamp),
        ):
            if not prices or 0 not in prices:
                raise ValueError(f"{label}_prices must contain a price point at delay 0")
            for delay, point in prices.items():
                if not isinstance(delay, int) or delay < 0:
                    raise ValueError(f"{label}_prices keys must be non-negative integers")
                if not isinstance(point, ExecutionPricePoint):
                    raise ValueError(f"{label}_prices values must be ExecutionPricePoint")
                if point.timestamp < signal_timestamp:
                    raise ValueError(
                        f"{label} execution timestamp at delay {delay} precedes "
                        f"the {label} signal timestamp (look-ahead-adjacent input)"
                    )
            ordered_delays = sorted(prices)
            for earlier, later in zip(ordered_delays, ordered_delays[1:]):
                if prices[later].timestamp < prices[earlier].timestamp:
                    raise ValueError(
                        f"{label}_prices timestamps must be non-decreasing with delay "
                        f"(delay {later} precedes delay {earlier})"
                    )


@dataclass(frozen=True)
class ExecutionScenario:
    cost_multiplier: float
    delay_bars: int

    def __post_init__(self) -> None:
        if not isfinite(self.cost_multiplier) or self.cost_multiplier < 1.0:
            raise ValueError("cost_multiplier must be a finite value >= 1.0")
        if not isinstance(self.delay_bars, int) or self.delay_bars < 0:
            raise ValueError("delay_bars must be a non-negative integer")


@dataclass(frozen=True)
class ExecutionScenarioResult:
    scenario: ExecutionScenario
    trade_count: int
    aggregate_gross_pnl: float | None = None
    aggregate_cost: float | None = None
    aggregate_net_pnl: float | None = None
    retention: float | None = None


@dataclass(frozen=True)
class ExecutionStressResult:
    trade_count: int
    fragility_label: ExecutionFragilityLabel
    warnings: tuple[str, ...]
    baseline_aggregate_gross_pnl: float | None = None
    baseline_aggregate_net_pnl: float | None = None
    scenario_results: tuple[ExecutionScenarioResult, ...] = ()
    worst_retention: float | None = None
    fragility_score: float | None = None
    breakeven_cost_multiplier: float | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)


def evaluate_execution_stress(
    *,
    observations: Sequence[ExecutionObservation],
    config: ExecutionStressConfig,
) -> ExecutionStressResult:
    """Evaluate how much of a strategy's execution edge survives cost and
    delay stress.

    ``observations`` is the full set of trades for the evaluation window.
    Raises ``ValueError`` if ``observations`` is empty.

    Gate precedence (checked in this fixed order):

    - empty ``observations`` -> ``ValueError``.
    - aggregate baseline (1.0x, 0-bar) net PnL over the full trade set <= 0
      -> ``NO_POSITIVE_BASELINE_EDGE``, ``fragility_score`` is ``None``.
    - too few trades -> ``INSUFFICIENT_DATA``, ``fragility_score`` is
      ``None``.
    - otherwise, a real label (``ROBUST``/``MODERATE``/``FRAGILE``/
      ``EXTREME``) is produced from the full scenario matrix, with each
      delay level's retention denominated against its own eligible
      cohort's reference-execution net PnL (see module docstring).
    """

    if not observations:
        raise ValueError("observations must not be empty")

    trade_count = len(observations)

    # The one reference-execution computation path: (1.0x, 0-bar) for every
    # trade. Every baseline/denominator in this function is derived from
    # this list -- there is no second, independently-implemented formula.
    reference_cells = [
        _scenario_gross_and_cost(obs, cost_multiplier=1.0, delay_bars=0) for obs in observations
    ]
    baseline_aggregate_gross_pnl = sum(gross for gross, _cost in reference_cells)
    baseline_aggregate_cost = sum(cost for _gross, cost in reference_cells)
    baseline_aggregate_net_pnl = baseline_aggregate_gross_pnl - baseline_aggregate_cost
    if not isfinite(baseline_aggregate_gross_pnl) or not isfinite(baseline_aggregate_net_pnl):
        raise ValueError(
            "baseline pnl aggregation overflowed to a non-finite value; "
            "refusing to generate an execution stress score"
        )

    if baseline_aggregate_net_pnl <= 0:
        return ExecutionStressResult(
            trade_count=trade_count,
            fragility_label=ExecutionFragilityLabel.NO_POSITIVE_BASELINE_EDGE,
            warnings=(
                "no_positive_baseline_edge: baseline aggregate net pnl is not "
                "positive, execution retention is undefined",
            ),
            baseline_aggregate_gross_pnl=baseline_aggregate_gross_pnl,
            baseline_aggregate_net_pnl=baseline_aggregate_net_pnl,
        )

    if trade_count < config.minimum_trade_count:
        return ExecutionStressResult(
            trade_count=trade_count,
            fragility_label=ExecutionFragilityLabel.INSUFFICIENT_DATA,
            warnings=(
                f"insufficient_trade_count: have {trade_count}, "
                f"need at least {config.minimum_trade_count}",
            ),
            baseline_aggregate_gross_pnl=baseline_aggregate_gross_pnl,
            baseline_aggregate_net_pnl=baseline_aggregate_net_pnl,
        )

    warnings: list[str] = []
    evidence: dict[str, Any] = {}

    total_abs_baseline_gross = sum(abs(gross) for gross, _cost in reference_cells)
    delay_coverage: dict[int, float] = {}
    # Per-delay-level cohort C_d's own reference-execution (1.0x, 0-bar) net
    # PnL -- the retention denominator for that delay level. C_0 is every
    # trade by construction, so its cohort baseline is exactly
    # baseline_aggregate_net_pnl (no separate computation needed).
    delay_cohort_baseline_net: dict[int, float] = {0: baseline_aggregate_net_pnl}
    for delay_bars in sorted(config.delay_levels):
        if delay_bars == 0:
            continue
        eligible_indices = [
            index
            for index, obs in enumerate(observations)
            if delay_bars in obs.entry_prices and delay_bars in obs.exit_prices
        ]
        eligible_abs_gross = sum(abs(reference_cells[index][0]) for index in eligible_indices)
        coverage = (
            eligible_abs_gross / total_abs_baseline_gross if total_abs_baseline_gross > 0 else 0.0
        )
        delay_coverage[delay_bars] = coverage
        cohort_baseline_net = sum(
            reference_cells[index][0] - reference_cells[index][1] for index in eligible_indices
        )
        delay_cohort_baseline_net[delay_bars] = cohort_baseline_net

        if coverage < config.minimum_delay_price_coverage:
            warnings.append(f"insufficient_delay_{delay_bars}_price_coverage")
        elif cohort_baseline_net <= 0:
            warnings.append(f"delay_{delay_bars}_cohort_baseline_not_positive")
    evidence["delay_price_coverage"] = dict(delay_coverage)
    evidence["delay_cohort_baseline_net_pnl"] = {
        delay_bars: value for delay_bars, value in delay_cohort_baseline_net.items() if delay_bars != 0
    }

    scenario_results: list[ExecutionScenarioResult] = []
    retentions: list[float] = []
    for delay_bars in sorted(config.delay_levels):
        if delay_bars == 0:
            delay_available = True
        else:
            coverage_ok = (
                delay_coverage.get(delay_bars, 0.0) >= config.minimum_delay_price_coverage
            )
            cohort_baseline = delay_cohort_baseline_net.get(delay_bars)
            delay_available = coverage_ok and cohort_baseline is not None and cohort_baseline > 0
        cohort_baseline_net = delay_cohort_baseline_net.get(delay_bars)

        for cost_multiplier in sorted(config.cost_multipliers):
            scenario = ExecutionScenario(cost_multiplier=cost_multiplier, delay_bars=delay_bars)
            if not delay_available:
                scenario_results.append(ExecutionScenarioResult(scenario=scenario, trade_count=0))
                continue

            if delay_bars == 0 and cost_multiplier == 1.0:
                # The reference-execution cell IS reference_cells / the
                # already-computed baseline aggregates -- reuse them
                # directly rather than re-summing the same per-trade values
                # a second time, so this cell is bit-for-bit, not just
                # numerically, identical to baseline_aggregate_net_pnl.
                agg_gross = baseline_aggregate_gross_pnl
                agg_cost = baseline_aggregate_cost
                agg_net = baseline_aggregate_net_pnl
                eligible_count = trade_count
            else:
                agg_gross = 0.0
                agg_cost = 0.0
                eligible_count = 0
                for obs in observations:
                    if delay_bars not in obs.entry_prices or delay_bars not in obs.exit_prices:
                        continue
                    gross, cost = _scenario_gross_and_cost(
                        obs, cost_multiplier=cost_multiplier, delay_bars=delay_bars
                    )
                    agg_gross += gross
                    agg_cost += cost
                    eligible_count += 1
                agg_net = agg_gross - agg_cost
                if not isfinite(agg_gross) or not isfinite(agg_net):
                    raise ValueError(
                        "scenario pnl aggregation overflowed to a non-finite value; "
                        "refusing to generate an execution stress score"
                    )
            # Same cohort on both sides of the ratio -- see module docstring.
            retention = agg_net / cohort_baseline_net
            scenario_results.append(
                ExecutionScenarioResult(
                    scenario=scenario,
                    trade_count=eligible_count,
                    aggregate_gross_pnl=agg_gross,
                    aggregate_cost=agg_cost,
                    aggregate_net_pnl=agg_net,
                    retention=retention,
                )
            )
            retentions.append(retention)

    # (1.0x, 0-bar) is always available (delay 0 is mandatory input, and its
    # cohort baseline is baseline_aggregate_net_pnl which the gate above
    # already confirmed is positive), so retentions always has at least
    # len(cost_multipliers) entries here.
    worst_retention = min(retentions)
    fragility_score = 1.0 - min(1.0, max(0.0, worst_retention))

    if worst_retention < config.fragile_retention_floor:
        label = ExecutionFragilityLabel.EXTREME
    elif worst_retention < config.moderate_retention_floor:
        label = ExecutionFragilityLabel.FRAGILE
    elif worst_retention < config.robust_retention_floor:
        label = ExecutionFragilityLabel.MODERATE
    else:
        label = ExecutionFragilityLabel.ROBUST

    # Break-even: A - k*F = 0 => k = A/F, where A is the raw (zero-friction)
    # gross PnL and F is total 1x friction (slippage loss + fee). Both are
    # derived from two evaluations of the same _scenario_gross_and_cost used
    # for every other cell in this function (k=0 and k=1, both at delay 0)
    # -- not a separately reimplemented price formula.
    aggregate_raw_gross = sum(
        _scenario_gross_and_cost(obs, cost_multiplier=0.0, delay_bars=0)[0] for obs in observations
    )
    if not isfinite(aggregate_raw_gross):
        raise ValueError(
            "raw gross pnl aggregation overflowed to a non-finite value; "
            "refusing to generate an execution stress score"
        )
    aggregate_friction = aggregate_raw_gross - baseline_aggregate_net_pnl
    breakeven_cost_multiplier = (
        aggregate_raw_gross / aggregate_friction if aggregate_friction > 0 else None
    )

    return ExecutionStressResult(
        trade_count=trade_count,
        fragility_label=label,
        warnings=tuple(warnings),
        baseline_aggregate_gross_pnl=baseline_aggregate_gross_pnl,
        baseline_aggregate_net_pnl=baseline_aggregate_net_pnl,
        scenario_results=tuple(scenario_results),
        worst_retention=worst_retention,
        fragility_score=fragility_score,
        breakeven_cost_multiplier=breakeven_cost_multiplier,
        evidence=evidence,
    )


def _side_sign(side: PositionSide) -> float:
    return 1.0 if side is PositionSide.LONG else -1.0


def _scenario_gross_and_cost(
    observation: ExecutionObservation,
    *,
    cost_multiplier: float,
    delay_bars: int,
) -> tuple[float, float]:
    """Direction-correct gross PnL and cost for one (cost, delay) cell.

    This is the single computation path for every reference/baseline value
    in this module -- the top-level gate, each delay level's cohort
    denominator, and the break-even solve are all derived from calls to
    this same function, never a second reimplementation of the price math.

    Slippage is applied to the *reference price at that delay* in the
    direction that is actually adverse for the position's side -- see the
    module docstring's LONG/SHORT table. The same
    ``side_sign * (exit - entry) * quantity`` formula is used for both
    sides afterward; only the price-adjustment direction differs by side.
    ``cost_multiplier=0.0`` yields the raw, zero-friction gross PnL (no
    slippage, no cost) -- used by the break-even solve, not part of the
    approved scenario matrix itself (``ExecutionScenario`` still requires
    ``cost_multiplier >= 1.0``).
    """

    entry_point = observation.entry_prices[delay_bars]
    exit_point = observation.exit_prices[delay_bars]
    entry_slip = cost_multiplier * observation.baseline_entry_slippage_bps / 10_000.0
    exit_slip = cost_multiplier * observation.baseline_exit_slippage_bps / 10_000.0

    if observation.side is PositionSide.LONG:
        entry_adjusted = entry_point.reference_price * (1.0 + entry_slip)
        exit_adjusted = exit_point.reference_price * (1.0 - exit_slip)
    else:
        entry_adjusted = entry_point.reference_price * (1.0 - entry_slip)
        exit_adjusted = exit_point.reference_price * (1.0 + exit_slip)

    sign = _side_sign(observation.side)
    gross_pnl = sign * (exit_adjusted - entry_adjusted) * observation.quantity
    cost = cost_multiplier * observation.baseline_fee_cost
    return gross_pnl, cost
