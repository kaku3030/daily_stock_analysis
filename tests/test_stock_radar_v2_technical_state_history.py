from datetime import datetime, timedelta, timezone

from data_provider.market_data_adapter import SignalPermission
from src.repositories.stock_radar_technical_state_repo import (
    StockRadarTechnicalStateRepository,
    technical_state_snapshot_to_dict,
)
from src.services.stock_radar_v2.technical_state import StockRadarTechnicalState
from src.services.stock_radar_v2.technical_state_history import (
    compare_technical_states,
    technical_state_evidence,
    technical_state_fingerprint,
)
from src.storage import DatabaseManager
from src.technical.models import (
    DataQuality,
    MultiTimeframeTechnicalResult,
    PriceStructure,
    TimeframeState,
)


NOW = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def _timeframe(timeframe: str, trend: str, *, score: int = 60) -> TimeframeState:
    return TimeframeState(
        timeframe=timeframe,
        trend=trend,
        momentum="neutral",
        volume_state="normal",
        structure_score=score,
        confidence=0.8,
        indicators={"close": 100.0 + score},
        quality=DataQuality(status="ok", bars=80),
    )


def _state(
    *,
    daily: str = "bullish",
    hourly: str = "bullish",
    intraday: str = "bullish",
    permission: SignalPermission = SignalPermission.NORMAL,
    as_of: datetime = NOW,
    score: int = 60,
) -> StockRadarTechnicalState:
    technical = MultiTimeframeTechnicalResult(
        code="NVDA",
        daily=_timeframe("1d", daily, score=score),
        hourly=_timeframe("1h", hourly, score=score),
        intraday=_timeframe("15m", intraday, score=score),
        structure=PriceStructure(
            structure_state="bullish",
            vwap_position="above",
            volume_confirmation="normal",
        ),
        alignment="aligned_bullish" if len({daily, hourly, intraday}) == 1 else "mixed",
        state_summary="research state",
        research_score=score,
    )
    return StockRadarTechnicalState(
        symbol="NVDA",
        as_of=as_of,
        technical=technical,
        data_health_score=95 if permission is SignalPermission.NORMAL else 45,
        signal_permission=permission,
        provider="alpaca",
        feed="iex",
    )


def test_numeric_drift_does_not_create_state_change() -> None:
    previous = technical_state_evidence(_state(score=60))
    current = technical_state_evidence(_state(score=64, as_of=NOW + timedelta(minutes=15)))

    change = compare_technical_states(previous, current)

    assert technical_state_fingerprint(previous) == technical_state_fingerprint(current)
    assert change["state"] == "unchanged"
    assert change["material"] is False


def test_permission_downgrade_is_material_but_cannot_confirm_signal() -> None:
    previous = technical_state_evidence(_state())
    current = technical_state_evidence(_state(permission=SignalPermission.BLOCKED))

    change = compare_technical_states(previous, current)

    assert change["state"] == "permission_downgrade"
    assert change["attention"] == "high"
    assert change["material"] is True
    assert change["can_confirm_signal"] is False


def test_daily_trend_change_is_recorded_without_trade_instruction() -> None:
    previous = technical_state_evidence(_state(daily="bullish"))
    current = technical_state_evidence(_state(daily="bearish"))

    change = compare_technical_states(previous, current)

    assert change["state"] == "daily_trend_change"
    assert "daily_trend_change" in change["changes"]
    assert "action" not in change
    assert "buy" not in change
    assert "sell" not in change


def test_permission_recovery_is_non_material_research_state() -> None:
    previous = technical_state_evidence(_state(permission=SignalPermission.BLOCKED))
    current = technical_state_evidence(_state(permission=SignalPermission.NORMAL))

    change = compare_technical_states(previous, current)

    assert change["state"] == "permission_recovery"
    assert change["attention"] == "low"
    assert change["material"] is False


def test_repository_is_idempotent_and_compares_adjacent_runs(tmp_path) -> None:
    db = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'history.db'}")
    repo = StockRadarTechnicalStateRepository(db)

    assert repo.sync_run("us", "run-1", [_state()]) == 1
    assert repo.sync_run("us", "run-1", [_state()]) == 0
    baseline = technical_state_snapshot_to_dict(repo.list_run("us", "run-1")[0])
    assert baseline["detail"]["baseline"] is True

    next_state = _state(
        daily="bearish",
        hourly="bearish",
        intraday="bearish",
        as_of=NOW + timedelta(days=1),
    )
    assert repo.sync_run("us", "run-2", [next_state]) == 1
    latest = technical_state_snapshot_to_dict(repo.list_run("us", "run-2")[0])

    assert latest["previous_run_id"] == "run-1"
    assert latest["state"] == "daily_trend_change"
    assert latest["material"] is True
