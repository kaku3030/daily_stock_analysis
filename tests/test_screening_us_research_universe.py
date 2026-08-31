import json

import pandas as pd

from src.services.screening import snapshot_us
from src.services.screening.config import Config
from src.services.screening.strategy import load_all_strategies


def test_combined_us_universe_is_deduplicated(monkeypatch) -> None:
    monkeypatch.setattr(snapshot_us, "_fetch_sp500_tickers", lambda: ["AAPL", "MSFT", "BRK-B"])
    monkeypatch.setattr(snapshot_us, "_fetch_nasdaq100_tickers", lambda: ["AAPL", "NVDA", "MSFT"])
    assert snapshot_us.fetch_us_universe("sp500_nasdaq100") == ["AAPL", "BRK-B", "MSFT", "NVDA"]


def test_nasdaq_parser_accepts_ticker_column(monkeypatch) -> None:
    monkeypatch.setattr(
        snapshot_us,
        "_fetch_nasdaq100_official_tickers",
        lambda: (_ for _ in ()).throw(RuntimeError("official unavailable")),
    )
    monkeypatch.setattr(
        snapshot_us,
        "_read_html_tables",
        lambda _: [pd.DataFrame({"Ticker": ["AAPL", "BRK.B"]})],
    )
    assert snapshot_us._fetch_nasdaq100_tickers() == ["AAPL", "BRK-B"]


def test_nasdaq_official_parser_reads_structured_company_list(monkeypatch) -> None:
    items = [
        {"@type": "ListItem", "position": index, "description": f"T{index:02d}"}
        for index in range(1, 101)
    ]
    html = (
        '<script type="application/ld+json">'
        + json.dumps({"name": "Nasdaq-100 Company Breakdown", "itemListElement": items})
        + "</script>"
    )
    monkeypatch.setattr(snapshot_us, "_fetch_html_text", lambda _: html)

    tickers = snapshot_us._fetch_nasdaq100_official_tickers()

    assert len(tickers) == 100
    assert tickers[0] == "T01"
    assert "T100" in tickers


def test_auto_universe_records_fallback_instead_of_hiding_it(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCREENING_US_UNIVERSE_SOURCE", "sp500_nasdaq100")
    monkeypatch.setenv("SCREENING_US_UNIVERSE_CACHE_PATH", str(tmp_path / "missing.json"))

    def fake_fetch(source: str) -> list[str]:
        if source == "sp500_nasdaq100":
            raise RuntimeError("combined unavailable")
        if source == "sp500":
            return ["AAPL", "MSFT"]
        raise AssertionError(source)

    monkeypatch.setattr(snapshot_us, "_fetch_us_universe_source", fake_fetch)
    resolution = snapshot_us.resolve_us_universe("auto")

    assert resolution.tickers == ["AAPL", "MSFT"]
    assert resolution.requested_source == "sp500_nasdaq100"
    assert resolution.resolved_source == "sp500"
    assert resolution.fallback_used is True
    assert resolution.errors == ("sp500_nasdaq100: combined unavailable",)


def test_auto_universe_uses_recent_matching_cache_before_smaller_fallback(
    monkeypatch,
    tmp_path,
) -> None:
    cache_path = tmp_path / "us-universe.json"
    monkeypatch.setenv("SCREENING_US_UNIVERSE_SOURCE", "sp500_nasdaq100")
    monkeypatch.setenv("SCREENING_US_UNIVERSE_CACHE_PATH", str(cache_path))
    expected = [f"TICKER{i:03d}" for i in range(450)]
    snapshot_us._write_universe_cache("sp500_nasdaq100", expected)
    monkeypatch.setattr(
        snapshot_us,
        "_fetch_us_universe_source",
        lambda source: (_ for _ in ()).throw(RuntimeError(f"{source} unavailable")),
    )

    resolution = snapshot_us.resolve_us_universe("auto")

    assert resolution.tickers == expected
    assert resolution.resolved_source == "cache:sp500_nasdaq100"
    assert resolution.fallback_used is True


def test_us_research_strategy_declares_us_scope() -> None:
    strategies = load_all_strategies(Config().strategies_dir)
    strategy = strategies["us_research_priority"]
    assert strategy.screening.market_scope == ["us"]
    assert strategy.screening.max_output == 10
