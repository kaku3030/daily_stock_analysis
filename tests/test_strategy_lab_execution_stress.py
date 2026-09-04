from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from src.services.strategy_lab.config import CONFIG_PATH, load_execution_stress_config
from src.services.strategy_lab.execution_stress import (
    ExecutionFragilityLabel,
    ExecutionObservation,
    ExecutionPricePoint,
    ExecutionScenario,
    PositionSide,
    evaluate_execution_stress,
)
# White-box import: the break-even consistency test below deliberately
# plugs an arbitrary (non-scenario-matrix) cost multiplier through the
# same computation path every scenario cell uses, which the public
# evaluate_execution_stress entry point has no way to expose for a
# multiplier outside config.cost_multipliers.
from src.services.strategy_lab.execution_stress import _scenario_gross_and_cost


CONFIG = load_execution_stress_config()


def _point(timestamp: datetime, price: float) -> ExecutionPricePoint:
    return ExecutionPricePoint(timestamp=timestamp, reference_price=price)


def _trade(
    index: int,
    *,
    side: PositionSide = PositionSide.LONG,
    entry: float = 100.0,
    exit: float = 110.0,
    quantity: float = 10.0,
    cost: float = 1.0,
    entry_slippage_bps: float = 0.0,
    exit_slippage_bps: float = 0.0,
    delay1: tuple[float, float] | None = None,
    delay2: tuple[float, float] | None = None,
) -> ExecutionObservation:
    base_t = datetime(2026, 1, 1) + timedelta(days=index)
    entry_signal = base_t
    exit_signal = base_t + timedelta(hours=1)
    entry_prices = {0: _point(base_t, entry)}
    exit_prices = {0: _point(exit_signal, exit)}
    if delay1 is not None:
        e1, x1 = delay1
        entry_prices[1] = _point(base_t + timedelta(hours=1), e1)
        exit_prices[1] = _point(base_t + timedelta(hours=2), x1)
    if delay2 is not None:
        e2, x2 = delay2
        entry_prices[2] = _point(base_t + timedelta(hours=2), e2)
        exit_prices[2] = _point(base_t + timedelta(hours=3), x2)
    return ExecutionObservation(
        side=side,
        quantity=quantity,
        entry_signal_timestamp=entry_signal,
        exit_signal_timestamp=exit_signal,
        entry_prices=entry_prices,
        exit_prices=exit_prices,
        baseline_fee_cost=cost,
        baseline_entry_slippage_bps=entry_slippage_bps,
        baseline_exit_slippage_bps=exit_slippage_bps,
    )


def _robust_trades(count: int = 25) -> tuple[ExecutionObservation, ...]:
    """count LONG winners, unaffected by delay, cheap relative cost -- a
    clean ROBUST baseline with no fragile dimension.
    """

    return tuple(
        _trade(i, delay1=(100.0, 110.0), delay2=(100.0, 110.0)) for i in range(count)
    )


def _scenario_result(result, cost_multiplier: float, delay_bars: int):
    scenario = ExecutionScenario(cost_multiplier=cost_multiplier, delay_bars=delay_bars)
    for scenario_result in result.scenario_results:
        if scenario_result.scenario == scenario:
            return scenario_result
    raise AssertionError(f"scenario {scenario} not found in result")


def test_robust_edge_survives_full_scenario_matrix() -> None:
    trades = _robust_trades()

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert result.fragility_label is ExecutionFragilityLabel.ROBUST
    assert result.trade_count == 25
    assert result.baseline_aggregate_net_pnl == pytest.approx(25 * 99.0)
    # Zero slippage and unchanged delay prices mean cost (1x -> 2x on a $1
    # baseline cost against $99 baseline net) is the only degrading factor:
    # worst cell is (2.0, any delay) with net=98, retention=98/99.
    assert result.worst_retention == pytest.approx(98.0 / 99.0)
    assert result.fragility_score == pytest.approx(1.0 - result.worst_retention)
    assert result.warnings == ()
    baseline_cell = _scenario_result(result, 1.0, 0)
    assert baseline_cell.retention == pytest.approx(1.0)
    assert baseline_cell.aggregate_net_pnl == pytest.approx(result.baseline_aggregate_net_pnl)


def test_cost_fragile_control_isolated_from_delay() -> None:
    """Cost stress alone (delay held unchanged from baseline) drives the
    edge to EXTREME -- isolates the cost dimension as the sole fragility
    driver.
    """

    trades = tuple(
        _trade(
            i,
            entry=100.0,
            exit=101.0,
            quantity=100.0,
            cost=45.0,
            delay1=(100.0, 101.0),
            delay2=(100.0, 101.0),
        )
        for i in range(25)
    )

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert result.baseline_aggregate_net_pnl == pytest.approx(25 * 55.0)
    worst_cell = _scenario_result(result, 2.0, 0)
    assert worst_cell.aggregate_net_pnl == pytest.approx(25 * 10.0)
    assert worst_cell.retention == pytest.approx(250.0 / 1375.0)
    assert result.worst_retention == pytest.approx(250.0 / 1375.0)
    assert result.fragility_label is ExecutionFragilityLabel.EXTREME
    # Delay dimension is untouched (identical prices at every delay), so
    # every delay level's cost-multiplier=2.0 cell should match exactly.
    assert _scenario_result(result, 2.0, 1).retention == pytest.approx(250.0 / 1375.0)
    assert _scenario_result(result, 2.0, 2).retention == pytest.approx(250.0 / 1375.0)


def test_delay_fragile_control_isolated_from_cost() -> None:
    """Delay stress alone (cost=0, so every cost multiplier is a no-op)
    drives the edge to FRAGILE -- isolates the delay dimension as the sole
    fragility driver.
    """

    trades = tuple(
        _trade(
            i,
            entry=100.0,
            exit=110.0,
            quantity=10.0,
            cost=0.0,
            delay1=(100.0, 108.0),
            delay2=(100.0, 104.0),
        )
        for i in range(25)
    )

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert result.baseline_aggregate_net_pnl == pytest.approx(25 * 100.0)
    assert _scenario_result(result, 1.0, 1).retention == pytest.approx(0.8)
    assert _scenario_result(result, 1.0, 2).retention == pytest.approx(0.4)
    # cost=0 means every cost multiplier is a no-op at a fixed delay.
    assert _scenario_result(result, 2.0, 2).retention == pytest.approx(0.4)
    assert result.worst_retention == pytest.approx(0.4)
    assert result.fragility_label is ExecutionFragilityLabel.FRAGILE


def test_combined_cost_and_delay_stress_required_to_break_edge() -> None:
    """Neither 2x cost alone nor +1 bar delay alone pushes retention below
    ROBUST (0.75), but the *joint* (2.0x, +1 bar) cell does -- proves the
    engine actually evaluates the combined scenario, not just the max of
    two independently-evaluated single axes.
    """

    trades = tuple(
        _trade(i, entry=100.0, exit=112.0, quantity=10.0, cost=20.0, delay1=(100.0, 110.0))
        for i in range(25)
    )

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    cost_alone = _scenario_result(result, 2.0, 0)
    delay_alone = _scenario_result(result, 1.0, 1)
    combined = _scenario_result(result, 2.0, 1)

    assert cost_alone.retention == pytest.approx(0.8)
    assert delay_alone.retention == pytest.approx(0.8)
    assert combined.retention == pytest.approx(0.6)
    assert combined.retention < min(cost_alone.retention, delay_alone.retention)

    assert result.worst_retention == pytest.approx(0.6)
    assert result.fragility_label is ExecutionFragilityLabel.MODERATE
    # delay 2 was never supplied for any trade -> unavailable, excluded.
    assert "insufficient_delay_2_price_coverage" in result.warnings
    assert _scenario_result(result, 1.0, 2).retention is None


def test_no_positive_baseline_edge_without_fabricating_score() -> None:
    trades = tuple(
        _trade(i, entry=100.0, exit=95.0, quantity=10.0, cost=1.0) for i in range(25)
    )

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert result.fragility_label is ExecutionFragilityLabel.NO_POSITIVE_BASELINE_EDGE
    assert result.fragility_score is None
    assert result.worst_retention is None
    assert result.baseline_aggregate_net_pnl == pytest.approx(25 * -51.0)
    assert "no_positive_baseline_edge" in " ".join(result.warnings)


def test_insufficient_trade_count_reports_insufficient_data() -> None:
    trades = _robust_trades(count=10)

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert result.fragility_label is ExecutionFragilityLabel.INSUFFICIENT_DATA
    assert result.fragility_score is None
    assert any("insufficient_trade_count" in w for w in result.warnings)


def test_delay_price_coverage_attack_reported_unavailable_not_falsely_safe() -> None:
    """Permanent adversarial fixture: most baseline gross PnL (weighted)
    comes from 26 trades missing delay-2 price data; the small known slice
    (4 trades) has delay-2 present and looks perfect in isolation. The
    engine must report delay-2 as unavailable, not a falsely reassuring
    retention computed from the tiny known remainder.
    """

    large = [
        _trade(i, entry=100.0, exit=101.0, quantity=100.0, cost=1.0, delay1=(100.0, 101.0))
        for i in range(26)
    ]
    small = [
        _trade(
            30 + i,
            entry=100.0,
            exit=101.0,
            quantity=1.0,
            cost=0.01,
            delay1=(100.0, 101.0),
            delay2=(100.0, 101.0),
        )
        for i in range(4)
    ]
    trades = tuple(large + small)

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert result.evidence["delay_price_coverage"][2] == pytest.approx(4.0 / 2604.0)
    assert "insufficient_delay_2_price_coverage" in result.warnings
    for cost_multiplier in CONFIG.cost_multipliers:
        cell = _scenario_result(result, cost_multiplier, 2)
        assert cell.retention is None
        assert cell.trade_count == 0
    # delay 1 is fully covered -- proves the exclusion is delay-2-specific.
    assert "insufficient_delay_1_price_coverage" not in result.warnings
    assert _scenario_result(result, 1.0, 1).retention is not None


def test_delay_retention_uses_matching_cohort_not_full_cohort() -> None:
    """Round-2 blocker (cohort mismatch) permanent regression fixture: 21 of
    25 trades have a delay-1 price point, 4 do not (coverage = 21/25 =
    0.84, clears the 0.80 default gate). Every *covered* trade's delay-1
    price is identical to its own delay-0 price -- zero true execution
    degradation for the entire cohort the engine can actually evaluate.
    retention(delay=1, cost=1.0) must therefore be exactly 1.0. An earlier
    draft measured the stressed numerator (21 trades) against a baseline
    denominator over the *full* 25-trade set, silently conflating the
    4-trade coverage gap with execution degradation and reporting 0.84 --
    a regression here means that bug came back.
    """

    with_delay1 = [
        _trade(i, entry=100.0, exit=101.0, quantity=100.0, cost=1.0, delay1=(100.0, 101.0))
        for i in range(21)
    ]
    without_delay1 = [
        _trade(30 + i, entry=100.0, exit=101.0, quantity=100.0, cost=1.0) for i in range(4)
    ]
    trades = tuple(with_delay1 + without_delay1)

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert result.evidence["delay_price_coverage"][1] == pytest.approx(21.0 / 25.0)
    assert "insufficient_delay_1_price_coverage" not in result.warnings
    assert "delay_1_cohort_baseline_not_positive" not in result.warnings
    cell = _scenario_result(result, 1.0, 1)
    assert cell.trade_count == 21
    assert cell.retention == pytest.approx(1.0)


def test_delay_cohort_baseline_not_positive_reported_unavailable() -> None:
    """The subset of trades with delay-1 data can itself have a
    non-positive reference-execution (delay-0) net PnL even when *both*
    the delay-1 coverage gate passes and the full cohort's baseline is
    positive -- a mix of large winners and larger losers within the
    delay-1 cohort can dominate the absolute-gross-weighted coverage
    calculation while still netting negative. Dividing by that
    non-positive cohort baseline is exactly as undefined as the top-level
    NO_POSITIVE_BASELINE_EDGE case, just scoped to one delay level.
    """

    # Delay-1 cohort (21 trades): 12 big losers + 9 big winners -- large
    # absolute gross (dominates coverage weighting) but nets negative.
    losers_with_delay1 = [
        _trade(i, entry=100.0, exit=50.0, quantity=10.0, cost=1.0, delay1=(100.0, 50.0))
        for i in range(12)
    ]
    winners_with_delay1 = [
        _trade(20 + i, entry=100.0, exit=150.0, quantity=10.0, cost=1.0, delay1=(100.0, 150.0))
        for i in range(9)
    ]
    # No delay-1 data: 4 clean winners, small enough in absolute gross to
    # stay under 20% of the total, but positive enough to keep the *full*
    # cohort's baseline net PnL positive.
    winners_without_delay1 = [
        _trade(40 + i, entry=100.0, exit=200.0, quantity=5.0, cost=0.0) for i in range(4)
    ]
    trades = tuple(losers_with_delay1 + winners_with_delay1 + winners_without_delay1)

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert result.baseline_aggregate_net_pnl == pytest.approx(479.0)
    assert result.evidence["delay_price_coverage"][1] == pytest.approx(0.84)
    assert "insufficient_delay_1_price_coverage" not in result.warnings
    assert result.evidence["delay_cohort_baseline_net_pnl"][1] == pytest.approx(-1521.0)
    assert "delay_1_cohort_baseline_not_positive" in result.warnings
    for cost_multiplier in CONFIG.cost_multipliers:
        cell = _scenario_result(result, cost_multiplier, 1)
        assert cell.retention is None


def test_long_short_slippage_direction_is_symmetric() -> None:
    """Mirrored LONG/SHORT portfolios where delay-driven price movement is
    genuinely adverse for each side (opposite raw price directions) must
    produce the *same* degradation, not opposite-signed ones -- this is the
    test that would catch a "always subtract from exit price" bug (correct
    for LONG, wrong for SHORT).
    """

    long_trades = tuple(
        _trade(
            i, side=PositionSide.LONG, entry=100.0, exit=110.0, cost=0.0, delay1=(102.0, 108.0)
        )
        for i in range(25)
    )
    short_trades = tuple(
        _trade(
            i, side=PositionSide.SHORT, entry=100.0, exit=90.0, cost=0.0, delay1=(98.0, 92.0)
        )
        for i in range(25)
    )

    long_result = evaluate_execution_stress(observations=long_trades, config=CONFIG)
    short_result = evaluate_execution_stress(observations=short_trades, config=CONFIG)

    long_delay_cell = _scenario_result(long_result, 1.0, 1)
    short_delay_cell = _scenario_result(short_result, 1.0, 1)

    assert long_delay_cell.retention == pytest.approx(0.6)
    assert short_delay_cell.retention == pytest.approx(0.6)
    assert long_delay_cell.retention < 1.0
    assert short_delay_cell.retention < 1.0


def test_asymmetric_entry_exit_slippage_is_applied_independently() -> None:
    """Round-3 requirement: entry and exit slippage must be independently
    representable, not a single shared rate -- entry and exit fills are not
    guaranteed to face the same friction. Uses genuinely different
    entry/exit bps and verifies the exact expected PnL math for both a LONG
    and a mirrored SHORT trade, plus that swapping which side carries the
    larger rate changes the result -- proving each rate is applied to its
    own side, not summed/blended into one effective rate.
    """

    t0 = datetime(2026, 1, 1)
    t1 = t0 + timedelta(hours=1)

    long_trade = ExecutionObservation(
        side=PositionSide.LONG,
        quantity=10.0,
        entry_signal_timestamp=t0,
        exit_signal_timestamp=t1,
        entry_prices={0: _point(t0, 100.0)},
        exit_prices={0: _point(t1, 110.0)},
        baseline_fee_cost=0.0,
        baseline_entry_slippage_bps=20.0,
        baseline_exit_slippage_bps=80.0,
    )
    # entry_adjusted = 100*(1+0.002) = 100.2; exit_adjusted = 110*(1-0.008)
    # = 109.12; gross = (109.12-100.2)*10 = 89.2.
    long_gross, long_cost = _scenario_gross_and_cost(long_trade, cost_multiplier=1.0, delay_bars=0)
    assert long_gross == pytest.approx(89.2)
    assert long_cost == pytest.approx(0.0)

    short_trade = ExecutionObservation(
        side=PositionSide.SHORT,
        quantity=10.0,
        entry_signal_timestamp=t0,
        exit_signal_timestamp=t1,
        entry_prices={0: _point(t0, 100.0)},
        exit_prices={0: _point(t1, 90.0)},
        baseline_fee_cost=0.0,
        baseline_entry_slippage_bps=20.0,
        baseline_exit_slippage_bps=80.0,
    )
    # entry_adjusted = 100*(1-0.002) = 99.8; exit_adjusted = 90*(1+0.008) =
    # 90.72; gross = -1*(90.72-99.8)*10 = 90.8.
    short_gross, short_cost = _scenario_gross_and_cost(
        short_trade, cost_multiplier=1.0, delay_bars=0
    )
    assert short_gross == pytest.approx(90.8)
    assert short_cost == pytest.approx(0.0)

    # Swap which side carries the larger rate: entry_adjusted =
    # 100*(1+0.008) = 100.8; exit_adjusted = 110*(1-0.002) = 109.78;
    # gross = (109.78-100.8)*10 = 89.8 -- different from long_gross above,
    # proving entry_slip lands on entry and exit_slip on exit, not a
    # symmetric/blended rate.
    swapped_trade = ExecutionObservation(
        side=PositionSide.LONG,
        quantity=10.0,
        entry_signal_timestamp=t0,
        exit_signal_timestamp=t1,
        entry_prices={0: _point(t0, 100.0)},
        exit_prices={0: _point(t1, 110.0)},
        baseline_fee_cost=0.0,
        baseline_entry_slippage_bps=80.0,
        baseline_exit_slippage_bps=20.0,
    )
    swapped_gross, _ = _scenario_gross_and_cost(swapped_trade, cost_multiplier=1.0, delay_bars=0)
    assert swapped_gross == pytest.approx(89.8)
    assert swapped_gross != pytest.approx(long_gross)


def test_exposure_reconstruction_attack_quantity_is_a_linear_multiplier() -> None:
    """Round-3-style adversarial fixture: quantity is a required, explicit
    input (never inferred from price movement and a caller-supplied PnL).
    Scaling quantity *and* baseline_fee_cost by the same factor across every
    trade (cost is a dollar amount, so it scales with size; the slippage bps
    rates must not be rescaled) must leave every retention ratio and
    the fragility label unchanged -- proving quantity is used exactly as a
    linear PnL unit-conversion factor, not silently reconstructed, ignored,
    or applied non-linearly.
    """

    base_trades = tuple(
        _trade(
            i,
            entry=100.0,
            exit=112.0,
            quantity=10.0,
            cost=20.0,
            entry_slippage_bps=5.0,
            exit_slippage_bps=5.0,
            delay1=(100.0, 110.0),
        )
        for i in range(25)
    )
    scaled_trades = tuple(
        _trade(
            i,
            entry=100.0,
            exit=112.0,
            quantity=10.0 * 37.0,
            cost=20.0 * 37.0,
            entry_slippage_bps=5.0,
            exit_slippage_bps=5.0,
            delay1=(100.0, 110.0),
        )
        for i in range(25)
    )

    base_result = evaluate_execution_stress(observations=base_trades, config=CONFIG)
    scaled_result = evaluate_execution_stress(observations=scaled_trades, config=CONFIG)

    assert scaled_result.fragility_label is base_result.fragility_label
    assert scaled_result.worst_retention == pytest.approx(base_result.worst_retention)
    for cost_multiplier in CONFIG.cost_multipliers:
        for delay_bars in CONFIG.delay_levels:
            base_cell = _scenario_result(base_result, cost_multiplier, delay_bars)
            scaled_cell = _scenario_result(scaled_result, cost_multiplier, delay_bars)
            if base_cell.retention is None:
                assert scaled_cell.retention is None
            else:
                assert scaled_cell.retention == pytest.approx(base_cell.retention)
    assert scaled_result.baseline_aggregate_net_pnl == pytest.approx(
        37.0 * base_result.baseline_aggregate_net_pnl
    )


def test_negative_retention_clamp() -> None:
    """A positive baseline edge whose worst scenario cell flips deeply
    negative must report the *raw*, unclamped (negative) worst_retention,
    while fragility_score stays bounded at exactly 1.0 -- the clamp applies
    only to the derived score, never to the reported evidence value.
    """

    trades = tuple(
        _trade(
            i,
            entry=100.0,
            exit=110.0,
            quantity=10.0,
            cost=1.0,
            delay1=(100.0, 60.0),
        )
        for i in range(25)
    )

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    worst_cell = _scenario_result(result, 2.0, 1)
    assert worst_cell.retention < 0
    assert result.worst_retention == pytest.approx(worst_cell.retention)
    assert result.worst_retention < 0
    assert result.fragility_score == pytest.approx(1.0)
    assert result.fragility_label is ExecutionFragilityLabel.EXTREME


def test_breakeven_cost_multiplier() -> None:
    trades = tuple(
        _trade(i, entry=100.0, exit=112.0, quantity=10.0, cost=20.0) for i in range(25)
    )

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert result.baseline_aggregate_gross_pnl == pytest.approx(25 * 120.0)
    assert result.breakeven_cost_multiplier == pytest.approx((25 * 120.0) / (25 * 20.0))
    assert result.breakeven_cost_multiplier == pytest.approx(6.0)


def test_breakeven_cost_multiplier_is_none_without_cost() -> None:
    trades = tuple(
        _trade(i, entry=100.0, exit=110.0, quantity=10.0, cost=0.0) for i in range(25)
    )

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert result.breakeven_cost_multiplier is None


def test_breakeven_cost_multiplier_with_nonzero_slippage() -> None:
    """Round-2 blocker (break-even formula) permanent regression: cost
    multiplier stresses fee *and* slippage together (see module
    docstring), so an earlier draft's ``gross_at_k1 / fee_cost`` formula --
    which implicitly held slippage frozen at its k=1 value -- overestimated
    the true break-even multiplier whenever slippage is nonzero. Verifies
    both the closed-form value against hand-derived A/F, and that plugging
    the reported break-even multiplier back into the actual reference-delay
    (delay=0) scenario computation reproduces an aggregate net PnL of ~0.
    """

    trades = tuple(
        _trade(
            i,
            entry=100.0,
            exit=110.0,
            quantity=10.0,
            cost=20.0,
            entry_slippage_bps=50.0,
            exit_slippage_bps=50.0,
        )
        for i in range(25)
    )

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    # Hand-derived: raw_gross_i = (110-100)*10 = 100; slippage_loss_i(1x) =
    # 10 * (100*0.005 + 110*0.005) = 10.5; friction_i = 10.5 + 20 = 30.5.
    expected_a = 25 * 100.0
    expected_f = 25 * 30.5
    assert result.breakeven_cost_multiplier == pytest.approx(expected_a / expected_f)
    assert result.breakeven_cost_multiplier == pytest.approx(3.278688524590166)

    # Plug the reported k back into the same (delay=0) computation every
    # scenario cell uses and confirm the aggregate net pnl is ~0 -- proves
    # the closed form actually matches the scenario matrix's own axis.
    k = result.breakeven_cost_multiplier
    net_at_breakeven = sum(
        gross - cost
        for gross, cost in (
            _scenario_gross_and_cost(trade, cost_multiplier=k, delay_bars=0) for trade in trades
        )
    )
    assert net_at_breakeven == pytest.approx(0.0, abs=1e-6)


def test_reference_baseline_has_a_single_computation_path() -> None:
    """Round-2 requirement: (1.0x, 0-bar) is the one realistic reference
    execution, and every baseline/reference aggregate net PnL in the result
    must come from that same computation path -- no second, independently
    derived baseline definition. The top-level baseline and the (1.0, 0)
    scenario cell must agree exactly (not approximately -- they are meant
    to be the literal same numbers, not two formulas that happen to match).
    """

    trades = tuple(
        _trade(
            i,
            entry=100.0,
            exit=112.0,
            quantity=10.0,
            cost=20.0,
            entry_slippage_bps=25.0,
            exit_slippage_bps=25.0,
            delay1=(100.0, 108.0),
        )
        for i in range(25)
    )

    result = evaluate_execution_stress(observations=trades, config=CONFIG)

    reference_cell = _scenario_result(result, 1.0, 0)
    assert reference_cell.aggregate_net_pnl == result.baseline_aggregate_net_pnl
    assert reference_cell.aggregate_gross_pnl == result.baseline_aggregate_gross_pnl
    assert reference_cell.retention == pytest.approx(1.0)
    # Only non-zero delay levels get their own cohort-baseline evidence
    # entry -- delay-0's cohort is the full trade set by construction, so
    # its "cohort baseline" is exactly the top-level baseline already
    # asserted above, not a second value to track separately.
    assert 0 not in result.evidence["delay_cohort_baseline_net_pnl"]


def test_configuration_sensitivity_changes_delay_coverage_eligibility() -> None:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["execution_stress"]["minimum_delay_price_coverage"]["value"] = 0.99
    tightened_path = Path(__file__).with_name("_tightened_execution_stress.tmp.yaml")
    tightened_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    try:
        tightened_config = load_execution_stress_config(tightened_path)
    finally:
        tightened_path.unlink()

    # 21 trades with delay-1 present, 4 without, all equal gross weight ->
    # delay-1 coverage = 21/25 = 0.84: eligible under the 0.80 default,
    # ineligible once tightened to 0.99.
    with_delay1 = [
        _trade(i, entry=100.0, exit=101.0, quantity=100.0, cost=1.0, delay1=(100.0, 101.0))
        for i in range(21)
    ]
    without_delay1 = [
        _trade(30 + i, entry=100.0, exit=101.0, quantity=100.0, cost=1.0) for i in range(4)
    ]
    trades = tuple(with_delay1 + without_delay1)

    default_result = evaluate_execution_stress(observations=trades, config=CONFIG)
    tightened_result = evaluate_execution_stress(observations=trades, config=tightened_config)

    assert _scenario_result(default_result, 1.0, 1).retention is not None
    assert _scenario_result(tightened_result, 1.0, 1).retention is None
    assert "insufficient_delay_1_price_coverage" in tightened_result.warnings


def test_determinism_same_input_same_output() -> None:
    trades = _robust_trades()

    first = evaluate_execution_stress(observations=trades, config=CONFIG)
    second = evaluate_execution_stress(observations=trades, config=CONFIG)

    assert first == second


def test_reorder_invariance() -> None:
    trades = tuple(
        _trade(i, entry=100.0, exit=112.0, quantity=10.0, cost=20.0, delay1=(100.0, 110.0))
        for i in range(25)
    )
    reordered = tuple(reversed(trades))

    original = evaluate_execution_stress(observations=trades, config=CONFIG)
    shuffled = evaluate_execution_stress(observations=reordered, config=CONFIG)

    assert original.fragility_label is shuffled.fragility_label
    assert original.worst_retention == pytest.approx(shuffled.worst_retention)
    assert original.baseline_aggregate_net_pnl == pytest.approx(shuffled.baseline_aggregate_net_pnl)
    for original_cell, shuffled_cell in zip(original.scenario_results, shuffled.scenario_results):
        assert original_cell.scenario == shuffled_cell.scenario
        if original_cell.retention is None:
            assert shuffled_cell.retention is None
        else:
            assert shuffled_cell.retention == pytest.approx(shuffled_cell.retention)


def test_malformed_trades_fail_closed() -> None:
    with pytest.raises(ValueError):
        evaluate_execution_stress(observations=(), config=CONFIG)


def test_malformed_execution_price_point_fails_closed() -> None:
    with pytest.raises(ValueError):
        ExecutionPricePoint(timestamp="not-a-datetime", reference_price=100.0)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        ExecutionPricePoint(timestamp=datetime(2026, 1, 1), reference_price=0.0)

    with pytest.raises(ValueError):
        ExecutionPricePoint(timestamp=datetime(2026, 1, 1), reference_price=float("nan"))


def test_malformed_execution_scenario_fails_closed() -> None:
    with pytest.raises(ValueError):
        ExecutionScenario(cost_multiplier=0.5, delay_bars=0)

    with pytest.raises(ValueError):
        ExecutionScenario(cost_multiplier=1.0, delay_bars=-1)


def test_malformed_execution_observation_fails_closed() -> None:
    t0 = datetime(2026, 1, 1)
    t1 = t0 + timedelta(hours=1)
    valid_entry = {0: _point(t0, 100.0)}
    valid_exit = {0: _point(t1, 110.0)}

    with pytest.raises(ValueError):
        ExecutionObservation(
            side=PositionSide.LONG,
            quantity=0.0,
            entry_signal_timestamp=t0,
            exit_signal_timestamp=t1,
            entry_prices=valid_entry,
            exit_prices=valid_exit,
        )

    with pytest.raises(ValueError):
        ExecutionObservation(
            side=PositionSide.LONG,
            quantity=10.0,
            entry_signal_timestamp=t0,
            exit_signal_timestamp=t1,
            entry_prices=valid_entry,
            exit_prices=valid_exit,
            baseline_fee_cost=-1.0,
        )

    with pytest.raises(ValueError):
        ExecutionObservation(
            side=PositionSide.LONG,
            quantity=10.0,
            entry_signal_timestamp=t0,
            exit_signal_timestamp=t1,
            entry_prices=valid_entry,
            exit_prices=valid_exit,
            baseline_entry_slippage_bps=-1.0,
        )

    with pytest.raises(ValueError):
        ExecutionObservation(
            side=PositionSide.LONG,
            quantity=10.0,
            entry_signal_timestamp=t0,
            exit_signal_timestamp=t1,
            entry_prices=valid_entry,
            exit_prices=valid_exit,
            baseline_exit_slippage_bps=-1.0,
        )

    with pytest.raises(ValueError):
        ExecutionObservation(
            side="diagonal",  # type: ignore[arg-type]
            quantity=10.0,
            entry_signal_timestamp=t0,
            exit_signal_timestamp=t1,
            entry_prices=valid_entry,
            exit_prices=valid_exit,
        )

    # missing the mandatory delay-0 reference price point
    with pytest.raises(ValueError):
        ExecutionObservation(
            side=PositionSide.LONG,
            quantity=10.0,
            entry_signal_timestamp=t0,
            exit_signal_timestamp=t1,
            entry_prices={1: _point(t1, 100.0)},
            exit_prices=valid_exit,
        )

    # causality: executable price precedes its own signal timestamp
    with pytest.raises(ValueError):
        ExecutionObservation(
            side=PositionSide.LONG,
            quantity=10.0,
            entry_signal_timestamp=t1,
            exit_signal_timestamp=t1,
            entry_prices={0: _point(t0, 100.0)},
            exit_prices=valid_exit,
        )

    # causality: delay-1 timestamp precedes delay-0 timestamp
    with pytest.raises(ValueError):
        ExecutionObservation(
            side=PositionSide.LONG,
            quantity=10.0,
            entry_signal_timestamp=t0,
            exit_signal_timestamp=t0,
            entry_prices={0: _point(t1, 100.0), 1: _point(t0, 101.0)},
            exit_prices={0: _point(t1, 110.0)},
        )
