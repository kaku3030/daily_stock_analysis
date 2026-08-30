import pandas as pd

from src.services.screening import snapshot_us
from src.services.screening.strategy import load_all_strategies


def test_combined_us_universe_is_deduplicated(monkeypatch) -> None:
    monkeypatch.setattr(snapshot_us, "_fetch_sp500_tickers", lambda: ["AAPL", "MSFT", "BRK-B"])
    monkeypatch.setattr(snapshot_us, "_fetch_nasdaq100_tickers", lambda: ["AAPL", "NVDA", "MSFT"])
    assert snapshot_us.fetch_us_universe("sp500_nasdaq100") == ["AAPL", "BRK-B", "MSFT", "NVDA"]


def test_nasdaq_parser_accepts_ticker_column(monkeypatch) -> None:
    monkeypatch.setattr(pd, "read_html", lambda _: [pd.DataFrame({"Ticker": ["AAPL", "BRK.B"]})])
    assert snapshot_us._fetch_nasdaq100_tickers() == ["AAPL", "BRK-B"]


def test_us_research_strategy_declares_us_scope() -> None:
    strategies = load_all_strategies()
    strategy = strategies["us_research_priority"]
    assert strategy.screening.market_scope == ["us"]
    assert strategy.screening.max_output == 10
