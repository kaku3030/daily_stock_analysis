from dataclasses import fields
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.services.strategy_lab.config import CONFIG_PATH, load_edge_concentration_config
from src.services.strategy_lab.edge_concentration import (
    EdgeConcentrationResult,
    EdgeFragilityLabel,
    TradeObservation,
    evaluate_edge_concentration,
)


CONFIG = load_edge_concentration_config()


def _trade(
    pnl: float,
    symbol: str | None = None,
    month_index: int = 0,
    sector: str | None = None,
    regime: str | None = None,
) -> TradeObservation:
    return TradeObservation(
        pnl=pnl,
        symbol=symbol,
        timestamp=datetime(2026, 1 + (month_index % 12), 1 + (month_index // 12)),
        sector=sector,
        regime=regime,
    )


def _diversified_winners(count: int = 25, pnl: float = 10.0) -> tuple[TradeObservation, ...]:
    """count winning trades, each pnl, spread across count distinct symbols
    and 5 equal-size groups of months/sectors/regimes -- a clean, evenly
    spread baseline with (by construction) zero concentration on every
    dimension.
    """

    return tuple(
        _trade(
            pnl,
            symbol=f"SYM{i}",
            month_index=i // 5,
            sector=f"SEC{i // 5}",
            regime=f"REG{i // 5}",
        )
        for i in range(count)
    )


def test_diversified_edge_is_labeled_diversified_with_exact_ratios() -> None:
    trades = _diversified_winners()

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.fragility_label is EdgeFragilityLabel.DIVERSIFIED
    assert result.fragility_score == pytest.approx(0.0, abs=1e-9)
    assert result.trade_count == 25
    assert result.positive_trade_count == 25
    assert result.gross_positive_pnl == 250.0

    # Every dimension is a perfectly even partition by construction, so raw
    # HHI equals its own floor (1/N) and normalized HHI is ~0 (floating
    # point division introduces noise on the order of 1e-17).
    assert result.trade_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.month_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.symbol_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.sector_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.regime_hhi_normalized == pytest.approx(0.0, abs=1e-9)

    # Explanatory evidence ratios: top1_count=max(1,ceil(25*0.01))=1,
    # top5_count=max(1,ceil(25*0.05))=2; each trade/symbol pnl=10.
    assert result.top_1pct_contribution == pytest.approx(10 / 250)
    assert result.top_5pct_contribution == pytest.approx(20 / 250)
    # 5 months of 5 trades each = 50 per month.
    assert result.top_month_contribution == pytest.approx(50 / 250)
    assert result.top_3_months_contribution == pytest.approx(150 / 250)
    assert result.top_symbol_contribution == pytest.approx(10 / 250)
    assert result.top_5_symbols_contribution == pytest.approx(50 / 250)
    assert result.top_sector_contribution == pytest.approx(50 / 250)
    assert result.top_regime_contribution == pytest.approx(50 / 250)

    assert result.symbol_missing_positive_pnl_share == 0.0
    assert result.sector_missing_positive_pnl_share == 0.0
    assert result.regime_missing_positive_pnl_share == 0.0
    assert result.symbol_metadata_coverage == 1.0
    assert result.sector_metadata_coverage == 1.0
    assert result.regime_metadata_coverage == 1.0
    assert result.warnings == ()


def test_single_dominant_trade_is_labeled_extreme() -> None:
    """24 tiny winners (pnl=1) plus one dominant winner (pnl=1000), spread
    across otherwise-diversified symbols/months/sectors/regimes so only the
    trade dimension is concentrated -- isolates trade_hhi_normalized as the
    driver of the EXTREME label.
    """

    small = [
        _trade(1.0, symbol=f"SYM{i}", month_index=i // 5, sector=f"SEC{i // 5}", regime=f"REG{i // 5}")
        for i in range(24)
    ]
    dominant = _trade(1000.0, symbol="SYM24", month_index=4, sector="SEC4", regime="REG4")
    trades = tuple(small) + (dominant,)

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    gross_positive_pnl = 24 * 1.0 + 1000.0
    expected_hhi = 24 * (1.0 / gross_positive_pnl) ** 2 + (1000.0 / gross_positive_pnl) ** 2
    expected_normalized = (expected_hhi - 1 / 25) / (1 - 1 / 25)

    assert result.gross_positive_pnl == pytest.approx(gross_positive_pnl)
    assert result.trade_hhi == pytest.approx(expected_hhi)
    assert result.trade_hhi_normalized == pytest.approx(expected_normalized)
    assert result.fragility_score == result.trade_hhi_normalized
    assert result.fragility_label is EdgeFragilityLabel.EXTREME


def test_no_winning_trades_reports_no_positive_edge_without_fabricating_score() -> None:
    trades = tuple(_trade(-5.0, symbol=f"SYM{i}", month_index=i) for i in range(20))

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.fragility_label is EdgeFragilityLabel.NO_POSITIVE_EDGE
    assert result.fragility_score is None
    assert result.gross_positive_pnl == 0.0
    assert result.positive_trade_count == 0
    assert "no_positive_edge" in " ".join(result.warnings)


def test_no_positive_edge_takes_precedence_over_insufficient_trade_count() -> None:
    """Code review fix (blocker 2): the frozen rule is
    GrossPositivePnL == 0 -> NO_POSITIVE_EDGE, unconditionally -- it is not
    a sample-size problem more trades would fix, so it must not be shadowed
    by the minimum_trade_count gate. 5 trades (far below
    minimum_trade_count=20), all losing.
    """

    trades = tuple(_trade(-10.0, symbol=f"SYM{i}", month_index=i) for i in range(5))

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.fragility_label is EdgeFragilityLabel.NO_POSITIVE_EDGE
    assert result.fragility_score is None
    assert result.gross_positive_pnl == 0.0
    assert result.trade_count == 5
    assert not any("insufficient_trade_count" in w for w in result.warnings)


def test_too_few_total_trades_is_insufficient_data() -> None:
    trades = tuple(_trade(10.0, symbol=f"SYM{i}", month_index=i) for i in range(10))

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.fragility_label is EdgeFragilityLabel.INSUFFICIENT_DATA
    assert result.fragility_score is None
    assert any("insufficient_trade_count" in w for w in result.warnings)


def test_too_few_winning_trades_is_insufficient_data_even_with_enough_total() -> None:
    # 20 total trades (>= minimum_trade_count) but only 3 winners
    # (< minimum_positive_trade_count=5): enough overall sample, not enough
    # winners to trust Top-N%/HHI.
    winners = [_trade(10.0, symbol=f"W{i}", month_index=i) for i in range(3)]
    losers = [_trade(-5.0, symbol=f"L{i}", month_index=i) for i in range(17)]
    trades = tuple(winners + losers)

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.fragility_label is EdgeFragilityLabel.INSUFFICIENT_DATA
    assert result.fragility_score is None
    # Descriptive evidence is still reported even though the score is not.
    assert result.trade_count == 20
    assert result.positive_trade_count == 3
    assert result.gross_positive_pnl == pytest.approx(30.0)
    assert any("insufficient_positive_trade_count" in w for w in result.warnings)


def test_metadata_coverage_attack_sector_reported_unavailable_not_falsely_safe() -> None:
    """Permanent adversarial fixture (TASK requirement): most positive PnL is
    missing sector metadata; the small *known* slice happens to be spread
    across many distinct sectors and would look diversified in isolation.
    The engine must report the sector dimension as unavailable -- not as a
    falsely reassuring low concentration figure -- and must exclude it from
    the Fragility Score. If a future change makes this fixture's sector
    metrics come back as real (non-None) numbers instead of unavailable,
    treat it as a regression: do not merge.
    """

    equal_pnl = 10.0
    # 26 trades with sector=None (86.7% of gross positive PnL missing).
    missing = [
        _trade(equal_pnl, symbol=f"MISS{i}", month_index=i % 6, sector=None, regime=f"REG{i % 5}")
        for i in range(26)
    ]
    # 4 trades with distinct known sectors (13.3% known) -- looks diversified
    # if you only look at the known slice.
    known = [
        _trade(equal_pnl, symbol=f"KNOWN{i}", month_index=i, sector=f"SEC{i}", regime=f"REG{i}")
        for i in range(4)
    ]
    trades = tuple(missing + known)

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.sector_metadata_coverage == pytest.approx(4 / 30)
    assert result.sector_missing_positive_pnl_share == pytest.approx(26 / 30)
    assert result.sector_hhi is None
    assert result.sector_hhi_normalized is None
    assert result.top_sector_contribution is None
    assert "insufficient_sector_metadata" in result.warnings
    # Regime is fully known in this fixture -- proves the exclusion is
    # dimension-specific, not a blanket failure of the whole evaluation.
    assert result.regime_metadata_coverage == 1.0
    assert result.regime_hhi is not None


def test_symbol_metadata_coverage_attack_reported_unavailable_not_falsely_safe() -> None:
    """Permanent adversarial fixture (Round 3 requirement): most positive PnL
    is missing symbol metadata; the small *known* slice happens to be spread
    across many distinct symbols and would look diversified in isolation.
    The engine must report the symbol dimension as unavailable -- not as a
    falsely reassuring low concentration figure -- and must exclude it from
    the Fragility Score. Mirrors the sector attack fixture above.
    """

    equal_pnl = 10.0
    # 26 trades with symbol=None (86.7% of gross positive PnL missing).
    missing = [
        _trade(equal_pnl, symbol=None, month_index=i % 6, sector=f"SEC{i % 5}", regime=f"REG{i % 5}")
        for i in range(26)
    ]
    # 4 trades with distinct known symbols (13.3% known) -- looks diversified
    # if you only look at the known slice.
    known = [
        _trade(equal_pnl, symbol=f"KNOWN{i}", month_index=i, sector=f"KSEC{i}", regime=f"KREG{i}")
        for i in range(4)
    ]
    trades = tuple(missing + known)

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.symbol_metadata_coverage == pytest.approx(4 / 30)
    assert result.symbol_missing_positive_pnl_share == pytest.approx(26 / 30)
    assert result.symbol_hhi is None
    assert result.symbol_hhi_normalized is None
    assert result.top_symbol_contribution is None
    assert result.top_5_symbols_contribution is None
    assert "insufficient_symbol_metadata" in result.warnings
    # Sector is fully known in this fixture (30 distinct labels) -- proves
    # the exclusion is symbol-specific, not a blanket evaluation failure.
    assert result.sector_metadata_coverage == 1.0
    assert result.sector_hhi is not None


def test_all_symbol_missing_trade_and_month_concentration_still_scored() -> None:
    """Round 3 blocker: symbol is optional dimension metadata -- the frozen
    minimal input contract is only timestamp + pnl. When every trade is
    missing symbol, only the symbol dimension must become unavailable;
    trade/month concentration (and any other populated dimension) must keep
    scoring normally, not be blocked by the missing symbol.
    """

    trades = tuple(
        _trade(10.0, symbol=None, month_index=i // 5, sector=f"SEC{i // 5}", regime=f"REG{i // 5}")
        for i in range(25)
    )

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.symbol_metadata_coverage == 0.0
    assert result.symbol_missing_positive_pnl_share == 1.0
    assert result.symbol_hhi is None
    assert result.symbol_hhi_normalized is None
    assert result.top_symbol_contribution is None
    assert result.top_5_symbols_contribution is None
    assert "insufficient_symbol_metadata" in result.warnings

    # trade/month are unaffected -- both perfectly diversified by
    # construction (25 equal-pnl trades, 5 equal-size month groups).
    assert result.trade_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.month_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.fragility_label is not EdgeFragilityLabel.INSUFFICIENT_DATA
    assert result.fragility_score is not None
    # sector/regime are fully known here and also diversified -- proves the
    # exclusion is symbol-specific, not a blanket failure of the whole
    # evaluation.
    assert result.sector_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.regime_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.fragility_score == pytest.approx(0.0, abs=1e-9)


def test_non_finite_aggregate_pnl_fails_closed() -> None:
    """Recommended fail-closed hardening (Round 3): if Gross Positive PnL (or
    a grouped-dimension pnl sum) overflows to inf/nan during aggregation,
    refuse to produce a concentration score rather than silently propagating
    a non-finite value into HHI/contribution math. Each individual pnl here
    is finite on its own (passes TradeObservation's per-trade check) --
    only the *sum* overflows float64.
    """

    huge = 1.0e308
    trades = (
        _trade(huge, symbol="A", month_index=0),
        _trade(huge, symbol="B", month_index=1),
    )

    with pytest.raises(ValueError):
        evaluate_edge_concentration(trades=trades, config=CONFIG)


def test_sufficient_sector_coverage_still_reports_nonzero_missing_share() -> None:
    # 18 known + 2 missing = 90% coverage, above the 80% minimum -- sector
    # should be scored, but the small missing slice must still be reported
    # honestly, not rounded away to zero.
    known = [
        _trade(10.0, symbol=f"K{i}", month_index=i % 6, sector=f"SEC{i % 3}", regime=f"REG{i % 3}")
        for i in range(18)
    ]
    missing = [
        _trade(10.0, symbol=f"M{i}", month_index=i, sector=None, regime=f"REG{i % 3}")
        for i in range(2)
    ]
    trades = tuple(known + missing)

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.sector_metadata_coverage == pytest.approx(0.9)
    assert result.sector_missing_positive_pnl_share == pytest.approx(0.1)
    assert result.sector_hhi is not None
    assert result.sector_hhi_normalized is not None
    assert not any("insufficient_sector_metadata" in w for w in result.warnings)


def test_eligible_sector_hhi_uses_known_metadata_conditional_distribution() -> None:
    """Code review fix (blocker 1): once sector is eligible, its HHI must be
    computed as group_pnl / known_positive_pnl (a proper distribution that
    sums to 1 over the known groups), not group_pnl / GrossPositivePnL.

    GrossPositivePnL=100: sector A=70, B=10 (known, 80% coverage -- exactly
    at the eligibility floor), 20 missing. Using GrossPositivePnL as the HHI
    denominator would give shares 0.70/0.10 (summing to 0.80, not 1),
    raw HHI=0.50, and -- because the normalization floor 1/N=0.5 assumes a
    proper distribution -- a normalized HHI of exactly 0, i.e. "perfectly
    diversified" despite A outweighing B seven to one. The correct
    known-conditional shares are 0.875/0.125 (of the known 80), giving
    normalized HHI = 0.5625: genuinely concentrated, not false-safe.
    """

    trades = (
        _trade(35.0, symbol="A1", month_index=0, sector="A", regime="R1"),
        _trade(35.0, symbol="A2", month_index=1, sector="A", regime="R2"),
        _trade(10.0, symbol="B1", month_index=2, sector="B", regime="R3"),
        _trade(10.0, symbol="M1", month_index=3, sector=None, regime="R4"),
        _trade(10.0, symbol="M2", month_index=4, sector=None, regime="R5"),
    ) + tuple(_trade(-1.0, symbol=f"LOSS{i}", month_index=i) for i in range(15))

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.gross_positive_pnl == pytest.approx(100.0)
    assert result.sector_metadata_coverage == pytest.approx(0.8)
    assert result.sector_hhi is not None
    assert result.sector_hhi == pytest.approx(0.78125)
    assert result.sector_hhi_normalized == pytest.approx(0.5625)
    assert result.sector_hhi_normalized != pytest.approx(0.0, abs=1e-9)
    # top_sector_contribution keeps GrossPositivePnL as its denominator
    # (a different, still-gross-denominated question) -- unaffected by the
    # HHI-denominator fix.
    assert result.top_sector_contribution == pytest.approx(0.70)
    # trade/month/symbol/regime are all a bijection with these same 5
    # trades here (each trade has a distinct month/symbol/regime), so they
    # all normalize to the same, much lower value -- sector is the clear
    # weakest-link driver of the Fragility Score.
    assert result.fragility_score == pytest.approx(0.5625)


def test_loss_and_zero_padding_cannot_lower_reported_concentration() -> None:
    """Code review requirement: appending zero/negative-PnL trades must not
    change any concentration figure, HHI, fragility_score, or label --
    Top-N% populations and every ratio's denominator are sized off
    positive_trade_count / Gross Positive PnL alone, which padding cannot
    touch.

    This invariance holds for two *concentration results* -- both the
    baseline (25 trades) and the augmented sample (65 trades) are already
    well past minimum_trade_count=20, so this test does not (and is not
    meant to) say anything about padding a sample across an eligibility
    boundary (e.g. from below minimum_trade_count to at/above it), where a
    label change is the expected, desired effect of genuinely having more
    evaluable data, not a concentration-dilution failure.
    """

    small = [
        _trade(1.0, symbol=f"SYM{i}", month_index=i // 5, sector=f"SEC{i // 5}", regime=f"REG{i // 5}")
        for i in range(24)
    ]
    dominant = _trade(1000.0, symbol="SYM24", month_index=4, sector="SEC4", regime="REG4")
    baseline_trades = tuple(small) + (dominant,)

    baseline = evaluate_edge_concentration(trades=baseline_trades, config=CONFIG)

    padding = tuple(
        _trade(-50.0 if i % 2 else 0.0, symbol=f"PAD{i}", month_index=i, sector=f"PADSEC{i}", regime=f"PADREG{i}")
        for i in range(40)
    )
    augmented = evaluate_edge_concentration(trades=baseline_trades + padding, config=CONFIG)

    assert augmented.trade_count == baseline.trade_count + 40
    assert augmented.positive_trade_count == baseline.positive_trade_count
    assert augmented.gross_positive_pnl == baseline.gross_positive_pnl
    assert augmented.fragility_score == baseline.fragility_score
    assert augmented.fragility_label is baseline.fragility_label
    assert augmented.trade_hhi_normalized == baseline.trade_hhi_normalized
    assert augmented.month_hhi_normalized == baseline.month_hhi_normalized
    assert augmented.symbol_hhi_normalized == baseline.symbol_hhi_normalized
    assert augmented.sector_hhi_normalized == baseline.sector_hhi_normalized
    assert augmented.regime_hhi_normalized == baseline.regime_hhi_normalized
    assert augmented.top_1pct_contribution == baseline.top_1pct_contribution
    assert augmented.top_5pct_contribution == baseline.top_5pct_contribution
    assert augmented.top_symbol_contribution == baseline.top_symbol_contribution
    assert augmented.warnings == baseline.warnings


def test_single_symbol_normalized_hhi_is_exactly_one_no_division_by_zero() -> None:
    """N=1 edge case: when a dimension has exactly one group, raw HHI equals
    1.0 and its theoretical floor (1/N) also equals 1.0, so the general
    normalization formula ((hhi-floor)/(1-floor)) divides by zero. This must
    short-circuit to 1.0 rather than raising.
    """

    trades = tuple(
        _trade(10.0, symbol="ONLYSYM", month_index=i // 5, sector=f"SEC{i // 5}", regime=f"REG{i // 5}")
        for i in range(25)
    )

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.symbol_hhi_normalized == 1.0
    assert result.fragility_score == 1.0
    assert result.fragility_label is EdgeFragilityLabel.EXTREME


def test_one_lucky_month_drives_extreme_label() -> None:
    """Permanent adversarial fixture: 25 winning trades, equal pnl, all
    distinct symbols and spread across 5 equal-size sector/regime groups
    (diversified on every other dimension) but all in the *same* calendar
    month. Isolates month_hhi_normalized (N=1 -> 1.0) as the sole driver of
    the weakest-link Fragility Score.
    """

    trades = tuple(
        _trade(10.0, symbol=f"SYM{i}", month_index=0, sector=f"SEC{i % 5}", regime=f"REG{i % 5}")
        for i in range(25)
    )

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.month_hhi_normalized == 1.0
    assert result.fragility_score == 1.0
    assert result.fragility_label is EdgeFragilityLabel.EXTREME
    assert result.trade_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.symbol_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.sector_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.regime_hhi_normalized == pytest.approx(0.0, abs=1e-9)


def test_one_lucky_sector_drives_extreme_label() -> None:
    """Permanent adversarial fixture: 25 winning trades, equal pnl, all
    distinct symbols/months and spread across 5 equal-size regime groups
    (diversified on every other dimension), but all in the *same* sector
    (100% coverage). Isolates sector_hhi_normalized (N=1 -> 1.0) as the sole
    driver of the weakest-link Fragility Score.
    """

    trades = tuple(
        _trade(10.0, symbol=f"SYM{i}", month_index=i % 5, sector="ONLYSEC", regime=f"REG{i % 5}")
        for i in range(25)
    )

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.sector_metadata_coverage == 1.0
    assert result.sector_hhi_normalized == 1.0
    assert result.fragility_score == 1.0
    assert result.fragility_label is EdgeFragilityLabel.EXTREME
    assert result.trade_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.symbol_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.month_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.regime_hhi_normalized == pytest.approx(0.0, abs=1e-9)


def test_one_lucky_regime_drives_extreme_label() -> None:
    """Permanent adversarial fixture: mirror of the lucky-sector case for
    regime. 25 winning trades, equal pnl, all distinct symbols/months and
    spread across 5 equal-size sector groups, but all in the *same* regime
    (100% coverage). Isolates regime_hhi_normalized (N=1 -> 1.0) as the sole
    driver of the weakest-link Fragility Score.
    """

    trades = tuple(
        _trade(10.0, symbol=f"SYM{i}", month_index=i % 5, sector=f"SEC{i % 5}", regime="ONLYREG")
        for i in range(25)
    )

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.regime_metadata_coverage == 1.0
    assert result.regime_hhi_normalized == 1.0
    assert result.fragility_score == 1.0
    assert result.fragility_label is EdgeFragilityLabel.EXTREME
    assert result.trade_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.symbol_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.month_hhi_normalized == pytest.approx(0.0, abs=1e-9)
    assert result.sector_hhi_normalized == pytest.approx(0.0, abs=1e-9)


def test_diversified_label_does_not_imply_profitability() -> None:
    """Validation/Performance separation: a perfectly diversified profit
    concentration (DIVERSIFIED) says nothing about whether the strategy is
    net profitable. This module has no field asserting "good" and must not
    be swayed by large losing trades, which never enter a positive-PnL
    ratio.
    """

    winners = _diversified_winners()  # gross positive pnl = 250
    heavy_losers = tuple(_trade(-200.0, symbol=f"LOSS{i}", month_index=i) for i in range(5))
    trades = winners + heavy_losers

    result = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert result.fragility_label is EdgeFragilityLabel.DIVERSIFIED
    assert result.gross_positive_pnl == 250.0  # unaffected by losses
    net_pnl = sum(t.pnl for t in trades)
    assert net_pnl < 0  # strategy is a net loser despite being "diversified"

    field_names = {f.name for f in fields(EdgeConcentrationResult)}
    assert field_names.isdisjoint({"is_good", "profitable", "recommended", "verdict"})


def test_configuration_sensitivity_changes_sector_eligibility() -> None:
    # Exercises the real YAML load path end-to-end. 90% sector coverage is
    # eligible under the default 80% minimum; tightening the minimum to 95%
    # must flip it to ineligible.
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["edge_concentration"]["minimum_metadata_coverage"]["value"] = 0.95
    tightened_path = Path(__file__).with_name("_tightened_edge_concentration.tmp.yaml")
    tightened_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    try:
        tightened_config = load_edge_concentration_config(tightened_path)
    finally:
        tightened_path.unlink()

    known = [
        _trade(10.0, symbol=f"K{i}", month_index=i % 6, sector=f"SEC{i % 3}", regime=f"REG{i % 3}")
        for i in range(18)
    ]
    missing = [
        _trade(10.0, symbol=f"M{i}", month_index=i, sector=None, regime=f"REG{i % 3}")
        for i in range(2)
    ]
    trades = tuple(known + missing)

    default_result = evaluate_edge_concentration(trades=trades, config=CONFIG)
    tightened_result = evaluate_edge_concentration(trades=trades, config=tightened_config)

    assert default_result.sector_hhi is not None
    assert tightened_result.sector_hhi is None
    assert "insufficient_sector_metadata" in tightened_result.warnings


def test_determinism_same_input_same_output() -> None:
    trades = _diversified_winners()

    first = evaluate_edge_concentration(trades=trades, config=CONFIG)
    second = evaluate_edge_concentration(trades=trades, config=CONFIG)

    assert first == second


_FLOAT_RESULT_FIELDS = (
    "gross_positive_pnl",
    "fragility_score",
    "top_1pct_contribution",
    "top_5pct_contribution",
    "top_month_contribution",
    "top_3_months_contribution",
    "top_symbol_contribution",
    "top_5_symbols_contribution",
    "top_sector_contribution",
    "top_regime_contribution",
    "trade_hhi",
    "trade_hhi_normalized",
    "month_hhi",
    "month_hhi_normalized",
    "symbol_hhi",
    "symbol_hhi_normalized",
    "sector_hhi",
    "sector_hhi_normalized",
    "regime_hhi",
    "regime_hhi_normalized",
    "symbol_missing_positive_pnl_share",
    "sector_missing_positive_pnl_share",
    "regime_missing_positive_pnl_share",
    "symbol_metadata_coverage",
    "sector_metadata_coverage",
    "regime_metadata_coverage",
    "symbol_metadata_trade_count_coverage",
    "sector_metadata_trade_count_coverage",
    "regime_metadata_trade_count_coverage",
)


def _assert_equivalent_ignoring_float_noise(
    a: EdgeConcentrationResult, b: EdgeConcentrationResult
) -> None:
    assert a.trade_count == b.trade_count
    assert a.positive_trade_count == b.positive_trade_count
    assert a.fragility_label is b.fragility_label
    assert a.warnings == b.warnings
    for name in _FLOAT_RESULT_FIELDS:
        va, vb = getattr(a, name), getattr(b, name)
        if va is None or vb is None:
            assert va is None and vb is None, f"{name}: {va!r} vs {vb!r}"
        else:
            assert va == pytest.approx(vb), f"{name}: {va!r} vs {vb!r}"


def test_reorder_invariance() -> None:
    """Code review requirement: shuffling the input trade order must not
    change fragility_label/score, any contribution ratio, any HHI, or
    coverage -- every computation here groups by key or sums, neither of
    which cares about input order. Floating-point summation is not strictly
    order-independent, so numeric fields are compared with pytest.approx
    rather than exact equality.
    """

    small = [
        _trade(1.0, symbol=f"SYM{i}", month_index=i // 5, sector=f"SEC{i // 5}", regime=f"REG{i // 5}")
        for i in range(24)
    ]
    dominant = _trade(1000.0, symbol="SYM24", month_index=4, sector="SEC4", regime="REG4")
    trades = tuple(small) + (dominant,)
    reordered = tuple(reversed(trades))

    original = evaluate_edge_concentration(trades=trades, config=CONFIG)
    shuffled = evaluate_edge_concentration(trades=reordered, config=CONFIG)

    _assert_equivalent_ignoring_float_noise(original, shuffled)


def test_malformed_trades_fail_closed() -> None:
    with pytest.raises(ValueError):
        evaluate_edge_concentration(trades=(), config=CONFIG)

    with pytest.raises(ValueError):
        TradeObservation(pnl=10.0, symbol="", timestamp=datetime(2026, 1, 1))

    with pytest.raises(ValueError):
        TradeObservation(pnl=10.0, symbol="SYM", timestamp=datetime(2026, 1, 1), sector="")

    with pytest.raises(ValueError):
        TradeObservation(pnl=float("nan"), symbol="SYM", timestamp=datetime(2026, 1, 1))

    with pytest.raises(ValueError):
        TradeObservation(pnl=10.0, symbol="SYM", timestamp=datetime(2026, 1, 1), holding_period=-1.0)
