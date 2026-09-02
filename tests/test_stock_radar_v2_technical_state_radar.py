import json
from datetime import datetime, timedelta, timezone

from data_provider.market_data_adapter import SignalPermission
from src.repositories.stock_radar_technical_state_repo import StockRadarTechnicalStateRepository
from src.services.stock_radar_v2.technical_state import StockRadarTechnicalState
from src.services.stock_radar_v2.technical_state_radar import StockRadarTechnicalStateRadar
from src.storage import DatabaseManager
from src.technical.models import (
    DataQuality,
    MultiTimeframeTechnicalResult,
    PriceStructure,
    TimeframeState,
)


NOW = datetime(2026, 9, 2, 8, tzinfo=timezone.utc)


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def _timeframe(timeframe: str, trend: str) -> TimeframeState:
    return TimeframeState(
        timeframe=timeframe,
        trend=trend,
        momentum="neutral",
        volume_state="normal",
        structure_score=60,
        confidence=0.8,
        quality=DataQuality(status="ok", bars=80),
    )


def _state(trend: str = "bullish", *, as_of: datetime = NOW) -> StockRadarTechnicalState:
    technical = MultiTimeframeTechnicalResult(
        code="NVDA",
        daily=_timeframe("1d", trend),
        hourly=_timeframe("1h", trend),
        intraday=_timeframe("15m", trend),
        structure=PriceStructure(structure_state=trend),
        alignment=f"aligned_{trend}",
        state_summary="research state",
        research_score=60,
    )
    return StockRadarTechnicalState(
        symbol="NVDA",
        as_of=as_of,
        technical=technical,
        data_health_score=95,
        signal_permission=SignalPermission.NORMAL,
        provider="alpaca",
        feed="iex",
    )


def test_publish_writes_research_only_json_and_markdown(tmp_path) -> None:
    db = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'radar.db'}")
    radar = StockRadarTechnicalStateRadar(StockRadarTechnicalStateRepository(db))

    result = radar.publish(
        market="us",
        run_id="run-1",
        states=[_state()],
        output_dir=tmp_path,
    )

    payload = json.loads((tmp_path / "us_stock_radar_technical_state_radar.json").read_text("utf-8"))
    markdown = (tmp_path / "us_stock_radar_technical_state_radar.md").read_text("utf-8")
    assert result["inserted"] == 1
    assert payload["research_only"] is True
    assert payload["can_confirm_signal"] is False
    assert payload["rows"][0]["detail"]["baseline"] is True
    assert "不构成交易建议或交易指令" in markdown
    assert "NVDA" in markdown


def test_republish_same_run_is_idempotent_and_keeps_report_row(tmp_path) -> None:
    db = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'radar.db'}")
    radar = StockRadarTechnicalStateRadar(StockRadarTechnicalStateRepository(db))
    arguments = {
        "market": "us",
        "run_id": "run-1",
        "states": [_state()],
        "output_dir": tmp_path,
    }

    radar.publish(**arguments)
    result = radar.publish(**arguments)

    assert result["inserted"] == 0
    assert len(result["rows"]) == 1


def test_adjacent_run_surfaces_material_daily_change_without_notification(tmp_path) -> None:
    db = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'radar.db'}")
    radar = StockRadarTechnicalStateRadar(StockRadarTechnicalStateRepository(db))
    radar.publish(market="us", run_id="run-1", states=[_state()], output_dir=tmp_path)

    result = radar.publish(
        market="us",
        run_id="run-2",
        states=[_state("bearish", as_of=NOW + timedelta(days=1))],
        output_dir=tmp_path,
    )

    assert result["material_count"] == 1
    assert result["rows"][0]["state"] == "daily_trend_change"
    assert not hasattr(radar, "notifier")


def test_empty_run_writes_explicit_empty_report(tmp_path) -> None:
    db = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'radar.db'}")
    radar = StockRadarTechnicalStateRadar(StockRadarTechnicalStateRepository(db))

    result = radar.publish(market="us", run_id="empty", states=[], output_dir=tmp_path)

    assert result["rows"] == []
    assert "暂无技术状态" in (tmp_path / "us_stock_radar_technical_state_radar.md").read_text("utf-8")
