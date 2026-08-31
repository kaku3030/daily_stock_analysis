import json
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.services.screening import snapshot_us
from src.services.screening import pipeline as screening_pipeline
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


def test_valuation_enrichment_uses_recent_cache_and_reports_expired_missing(
    monkeypatch,
    tmp_path,
) -> None:
    cache_path = tmp_path / "valuation.json"
    monkeypatch.setattr(snapshot_us, "_valuation_cache_path", lambda: cache_path)
    cache_path.write_text(json.dumps({
        "version": 1,
        "entries": {
            "AAPL": {
                "pe_ratio": {
                    "value": 31.5,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                },
                "pb_ratio": {
                    "value": 8.0,
                    "captured_at": (
                        datetime.now(timezone.utc) - timedelta(days=8)
                    ).isoformat(),
                },
            },
        },
    }), encoding="utf-8")

    class FailingTicker:
        @property
        def info(self):
            raise RuntimeError("rate limited")

    monkeypatch.setattr("yfinance.Ticker", lambda _: FailingTicker())
    frame = pd.DataFrame([{
        "code": "AAPL",
        "name": "AAPL",
        "pe_ratio": None,
        "pb_ratio": None,
        "industry": "",
    }])

    stats = snapshot_us._enrich_info_fields(frame)

    assert frame.at[0, "pe_ratio"] == 31.5
    assert pd.isna(frame.at[0, "pb_ratio"])
    assert stats == {
        "pe_ratio": {"live": 0, "cached": 1, "missing": 0},
        "pb_ratio": {"live": 0, "cached": 0, "missing": 1},
        "request_errors": 1,
    }


def test_valuation_enrichment_persists_live_values(monkeypatch, tmp_path) -> None:
    cache_path = tmp_path / "valuation.json"
    monkeypatch.setattr(snapshot_us, "_valuation_cache_path", lambda: cache_path)

    class LiveTicker:
        info = {
            "trailingPE": 25.0,
            "priceToBook": 6.0,
            "industry": "Technology",
            "shortName": "Apple",
        }

    monkeypatch.setattr("yfinance.Ticker", lambda _: LiveTicker())
    frame = pd.DataFrame([{
        "code": "AAPL",
        "name": "AAPL",
        "pe_ratio": None,
        "pb_ratio": None,
        "industry": "",
    }])

    stats = snapshot_us._enrich_info_fields(frame)
    payload = json.loads(cache_path.read_text(encoding="utf-8"))

    assert stats["pe_ratio"] == {"live": 1, "cached": 0, "missing": 0}
    assert stats["pb_ratio"] == {"live": 1, "cached": 0, "missing": 0}
    assert payload["entries"]["AAPL"]["pe_ratio"]["value"] == 25.0
    assert payload["entries"]["AAPL"]["pb_ratio"]["value"] == 6.0


def test_us_research_strategy_declares_us_scope() -> None:
    strategies = load_all_strategies(Config().strategies_dir)
    strategy = strategies["us_research_priority"]
    assert strategy.screening.market_scope == ["us"]
    assert strategy.screening.max_output == 10
    assert strategy.screening.hard_filters.pe_ttm_min is None
    assert strategy.screening.hard_filters.pe_ttm_max is None
    assert strategy.screening.hard_filters.pb_min is None
    assert strategy.screening.hard_filters.pb_max is None


def test_us_research_keeps_candidates_when_valuation_is_unavailable(monkeypatch, caplog) -> None:
    snapshot = pd.DataFrame([
        {
            "code": "AAPL",
            "name": "Apple",
            "price": 200.0,
            "change_pct": 1.0,
            "amount": 500_000_000.0,
            "total_mv": 3_000_000_000_000.0,
            "pe_ratio": None,
            "pb_ratio": None,
            "volume_ratio": 1.2,
            "turnover_rate": 0.5,
        },
        {
            "code": "MSFT",
            "name": "Microsoft",
            "price": 400.0,
            "change_pct": 0.5,
            "amount": 400_000_000.0,
            "total_mv": 2_500_000_000_000.0,
            "pe_ratio": None,
            "pb_ratio": None,
            "volume_ratio": 1.1,
            "turnover_rate": 0.4,
        },
    ])
    snapshot.attrs.update({
        "snapshot_source": "yfinance",
        "source_errors": [],
        "fallback_used": False,
        "universe_requested_source": "sp500_nasdaq100",
        "universe_source": "sp500_nasdaq100",
        "universe_count": 2,
        "universe_snapshot_count": 2,
        "universe_coverage_ratio": 1.0,
        "universe_fallback_used": False,
        "universe_errors": [],
        "valuation_sources": {
            "pe_ratio": {"live": 0, "cached": 0, "missing": 2},
            "pb_ratio": {"live": 0, "cached": 0, "missing": 2},
            "request_errors": 2,
        },
    })
    monkeypatch.setattr(
        screening_pipeline,
        "fetch_snapshot_with_fallback",
        lambda *args, **kwargs: snapshot.copy(),
    )

    with caplog.at_level(logging.INFO, logger="src.services.screening.pipeline"):
        result = screening_pipeline.screen(
            "us_research_priority",
            market="us",
            max_output=2,
            use_llm=False,
            config=Config(
                post_analyzers=[],
                risk_enabled=False,
                portfolio_diversity_enabled=False,
                daily_enrich_enabled=False,
            ),
        )

    assert result.after_filter_count == 2
    assert [pick.code for pick in result.picks] == ["AAPL", "MSFT"]
    assert "US snapshot valuation coverage: pe_ratio=0/2 (0.0%), pb_ratio=0/2 (0.0%)" in result.degradation
    assert "US snapshot valuation coverage: pe_ratio=0/2 (0.0%), pb_ratio=0/2 (0.0%)" in caplog.text
    source_note = (
        "US snapshot valuation sources: pe_ratio=live 0, cached 0, missing 2; "
        "pb_ratio=live 0, cached 0, missing 2; request_errors=2"
    )
    assert source_note in result.degradation
    assert source_note in caplog.text
    assert result.valuation_health == {
        "status": "critical",
        "confidence": "low",
        "effective_coverage_ratio": 0.0,
        "live_coverage_ratio": 0.0,
        "request_error_ratio": 1.0,
        "request_errors": 2,
    }


def test_us_valuation_health_distinguishes_cached_resilience_from_live_failure() -> None:
    frame = pd.DataFrame({"code": [f"T{index}" for index in range(10)]})
    frame.attrs["valuation_sources"] = {
        "pe_ratio": {"live": 1, "cached": 7, "missing": 2},
        "pb_ratio": {"live": 1, "cached": 7, "missing": 2},
        "request_errors": 9,
    }

    health = screening_pipeline._us_valuation_health(frame)

    assert health["status"] == "critical"
    assert health["confidence"] == "low"
    assert health["effective_coverage_ratio"] == 0.8
    assert health["live_coverage_ratio"] == 0.1

    frame.attrs["valuation_sources"] = {
        "pe_ratio": {"live": 8, "cached": 1, "missing": 1},
        "pb_ratio": {"live": 8, "cached": 1, "missing": 1},
        "request_errors": 1,
    }
    assert screening_pipeline._us_valuation_health(frame)["confidence"] == "medium"

    frame.attrs["valuation_sources"] = {
        "pe_ratio": {"live": 10, "cached": 0, "missing": 0},
        "pb_ratio": {"live": 10, "cached": 0, "missing": 0},
        "request_errors": 0,
    }
    assert screening_pipeline._us_valuation_health(frame)["confidence"] == "high"
