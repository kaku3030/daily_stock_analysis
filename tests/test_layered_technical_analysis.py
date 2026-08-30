import pandas as pd

from src.technical.indicators import calculate_indicators
from src.technical.technical_analyzer import TechnicalAnalyzer
from src.stock_analyzer import StockTrendAnalyzer


def _bars(count: int = 80, *, rising: bool = True) -> pd.DataFrame:
    direction = 1 if rising else -1
    close = [100 + direction * index * 0.5 for index in range(count)]
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=count, freq="D"),
            "open": close,
            "high": [value + 1 for value in close],
            "low": [value - 1 for value in close],
            "close": close,
            "volume": [1000 + index * 10 for index in range(count)],
        }
    )


def test_indicator_layer_calculates_without_trade_signal_columns() -> None:
    result = calculate_indicators(_bars(), include_vwap=True)
    assert {"ma20", "macd", "rsi14", "atr14", "vwap", "supertrend"}.issubset(result.columns)
    assert "buy_signal" not in result.columns
    assert "sell_signal" not in result.columns


def test_missing_lower_timeframes_degrade_without_inventing_state() -> None:
    result = TechnicalAnalyzer().analyze("NVDA", _bars())
    assert result.daily.trend == "bullish"
    assert result.hourly.trend == "unknown"
    assert result.intraday.trend == "unknown"
    assert "1h_data_missing" in result.risk_flags
    assert "15m_data_missing" in result.risk_flags
    assert 0 <= result.research_score <= 100


def test_partial_intraday_bar_caps_confidence() -> None:
    bars = _bars()
    result = TechnicalAnalyzer().analyze("NVDA", bars, bars, bars, intraday_partial=True)
    assert result.intraday.quality.is_partial_bar is True
    assert result.intraday.confidence <= 0.65
    assert "15m_partial_bar" in result.risk_flags
    assert not hasattr(result, "buy_signal")


def test_legacy_analyzer_exposes_neutral_research_state() -> None:
    result = StockTrendAnalyzer().analyze(_bars(), "NVDA")
    assert result.buy_signal is not None
    assert result.research_state["daily"]["trend"] == "bullish"
    assert result.research_state["hourly"]["trend"] == "unknown"
