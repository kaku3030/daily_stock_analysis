import pytest

from src.services.stock_radar_v2.confidence import (
    assess_portfolio_confidence,
    calculate_signal_confidence,
)
from src.services.stock_radar_v2.notifications import RadarNotifier


def _portfolio_components(score: float) -> dict[str, float]:
    return {
        "data_health": score,
        "diversification": score,
        "liquidity": score,
        "drawdown_resilience": score,
    }


@pytest.mark.parametrize(
    ("score", "level", "gate"),
    [
        (80, "L0", "ALLOW_RESEARCH_FLOW"),
        (60, "L1", "WATCH_PORTFOLIO_RISK"),
        (40, "L2", "RESTRICT_NEW_POSITION"),
        (39.99, "L3", "BLOCK_NEW_POSITION"),
    ],
)
def test_portfolio_confidence_levels_and_l3_gate(score, level, gate) -> None:
    result = assess_portfolio_confidence(_portfolio_components(score))
    assert result.portfolio_confidence == score
    assert result.level == level
    assert result.risk_gate == gate


def test_portfolio_risk_does_not_mutate_signal_state_or_confidence() -> None:
    signal = {"state": "confirmed", "signal_confidence": 86.5}
    before = dict(signal)
    events = []

    portfolio = assess_portfolio_confidence(
        _portfolio_components(20),
        notifier=RadarNotifier(events.append),
    )

    assert signal == before
    assert portfolio.risk_gate == "BLOCK_NEW_POSITION"
    assert [event.event_type for event in events] == ["portfolio_risk_alert"]


def test_signal_confidence_is_calculated_independently() -> None:
    result = calculate_signal_confidence(
        {"data_quality": 90, "evidence_quality": 80, "consistency": 70}
    )
    assert result.score == 81.5


def test_confidence_rejects_out_of_range_components() -> None:
    with pytest.raises(ValueError, match="between 0 and 100"):
        assess_portfolio_confidence(_portfolio_components(101))
