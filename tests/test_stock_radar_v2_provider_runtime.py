import json
from datetime import datetime, timedelta, timezone

from data_provider.market_data_adapter import Bar, MarketDataAdapter, evaluate_health
from src.repositories.stock_radar_technical_state_repo import StockRadarTechnicalStateRepository
from src.services.stock_radar_v2.config import RuntimeConfig
from src.services.stock_radar_v2.provider_runtime import StockRadarProviderRuntime
from src.services.stock_radar_v2.technical_state_radar import StockRadarTechnicalStateRadar
from src.storage import DatabaseManager


NOW = datetime(2026, 9, 1, 14, 30, tzinfo=timezone.utc)
START = NOW - timedelta(minutes=60)
HEALTHY = evaluate_health(
    freshness=1,
    completeness=1,
    timestamp=1,
    provider=1,
    continuity=1,
    cross_check=1,
)
RUNTIME_CONFIG = RuntimeConfig(
    minute_history_limit=60,
    history_lookback_days=30,
    daily_history_limit=80,
    freshness_limit_seconds=120,
)


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def _minute(symbol: str, index: int, *, market: str = "us") -> Bar:
    start = START + timedelta(minutes=index)
    return Bar(
        symbol=symbol,
        market=market,
        asset_type="stock",
        timeframe="1m",
        bar_start=start,
        bar_end=start + timedelta(minutes=1),
        open=100 + index / 10,
        high=101 + index / 10,
        low=99 + index / 10,
        close=100.5 + index / 10,
        volume=1000 + index,
        provider="alpaca",
        feed="iex",
        source_timestamp=start + timedelta(minutes=1),
        received_at=start + timedelta(minutes=1),
        session="regular",
        is_closed=True,
        is_complete=True,
        health=HEALTHY,
    )


def _daily(symbol: str, index: int, *, market: str = "us") -> Bar:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc) + timedelta(days=index)
    return Bar(
        symbol=symbol,
        market=market,
        asset_type="stock",
        timeframe="1d",
        bar_start=start,
        bar_end=start,
        open=100 + index,
        high=101 + index,
        low=99 + index,
        close=100.5 + index,
        volume=1000 + index,
        provider="existing",
        source_timestamp=start,
        received_at=NOW,
        session="closed",
        is_closed=True,
        is_complete=True,
        health=HEALTHY,
    )


class FakeAdapter(MarketDataAdapter):
    def __init__(self, *, daily: bool = False, empty=(), error=(), market: str = "us"):
        self.daily = daily
        self.empty = set(empty)
        self.error = set(error)
        self.market = market
        self.calls = []

    def get_latest_quote(self, symbol):
        raise NotImplementedError

    def get_bars(self, symbol, timeframe, start=None, end=None, limit=None):
        self.calls.append((symbol, timeframe, start, end, limit))
        if symbol in self.error:
            raise RuntimeError("token=secret-value https://provider.invalid/private")
        if symbol in self.empty:
            return []
        if self.daily:
            return [_daily(symbol, index, market=self.market) for index in range(80)]
        return [_minute(symbol, index, market=self.market) for index in range(60)]

    def subscribe(self, symbols, timeframe="1m", callback=None):
        raise NotImplementedError

    def get_session_status(self, market):
        return "closed"

    def get_provider_health(self):
        return HEALTHY

    def reconnect(self):
        return False


def _runtime(tmp_path, intraday, daily) -> StockRadarProviderRuntime:
    db = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'runtime.db'}")
    radar = StockRadarTechnicalStateRadar(StockRadarTechnicalStateRepository(db))
    return StockRadarProviderRuntime(
        intraday,
        daily,
        radar=radar,
        config=RUNTIME_CONFIG,
        now=lambda: NOW,
    )


def test_runtime_reads_provider_facts_and_publishes_research_report(tmp_path) -> None:
    intraday = FakeAdapter()
    runtime = _runtime(tmp_path, intraday, FakeAdapter(daily=True))

    result = runtime.run(
        market="us",
        run_id="run-1",
        symbols=["nvda", "NVDA"],
        output_dir=tmp_path,
        as_of=NOW,
    )

    payload = json.loads((tmp_path / "us_stock_radar_technical_state_radar.json").read_text("utf-8"))
    assert result["inserted"] == 1
    assert result["runtime"]["requested_count"] == 1
    assert result["runtime"]["evaluated_count"] == 1
    assert payload["rows"][0]["evidence"]["technical"]["daily"]["trend"] == "bullish"
    assert payload["research_only"] is True
    assert payload["can_confirm_signal"] is False
    assert intraday.calls[0][2] == NOW - timedelta(days=30)


def test_missing_daily_history_degrades_to_unknown_without_dropping_symbol(tmp_path) -> None:
    runtime = _runtime(tmp_path, FakeAdapter(), FakeAdapter(daily=True, empty={"NVDA"}))

    result = runtime.run(
        market="us",
        run_id="run-1",
        symbols=["NVDA"],
        output_dir=tmp_path,
        as_of=NOW,
    )

    assert result["runtime"]["evaluated_count"] == 1
    assert result["runtime"]["warning_count"] == 1
    assert result["runtime"]["warnings"][0]["code"] == "missing_daily_bars"
    assert result["rows"][0]["evidence"]["technical"]["daily"]["trend"] == "unknown"


def test_one_symbol_failure_is_sanitized_and_does_not_block_other_symbols(tmp_path) -> None:
    runtime = _runtime(tmp_path, FakeAdapter(error={"BAD"}), FakeAdapter(daily=True))

    result = runtime.run(
        market="us",
        run_id="run-1",
        symbols=["NVDA", "BAD"],
        output_dir=tmp_path,
        as_of=NOW,
    )

    assert result["runtime"]["evaluated_count"] == 1
    assert result["runtime"]["failed_count"] == 1
    failure = result["runtime"]["failures"][0]
    assert failure["symbol"] == "BAD"
    assert "secret-value" not in failure["message"]
    assert "provider.invalid" not in failure["message"]


def test_market_mismatch_is_rejected_without_persisting_fake_state(tmp_path) -> None:
    runtime = _runtime(tmp_path, FakeAdapter(market="cn"), FakeAdapter(daily=True))

    result = runtime.run(
        market="us",
        run_id="run-1",
        symbols=["NVDA"],
        output_dir=tmp_path,
        as_of=NOW,
    )

    assert result["runtime"]["failed_count"] == 1
    assert result["runtime"]["evaluated_count"] == 0
    assert result["rows"] == []


def test_repeating_same_run_remains_idempotent(tmp_path) -> None:
    runtime = _runtime(tmp_path, FakeAdapter(), FakeAdapter(daily=True))
    arguments = {
        "market": "us",
        "run_id": "run-1",
        "symbols": ["NVDA"],
        "output_dir": tmp_path,
        "as_of": NOW,
    }

    runtime.run(**arguments)
    result = runtime.run(**arguments)

    assert result["inserted"] == 0
    assert len(result["rows"]) == 1
