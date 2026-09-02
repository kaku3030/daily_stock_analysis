"""One-shot provider runtime for research-only technical-state publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from data_provider.market_data_adapter import Bar, MarketDataAdapter
from src.utils.sanitize import sanitize_diagnostic_text

from ..realtime_market_data import MarketDataSnapshot, RealtimeMarketDataService
from .config import RuntimeConfig, load_stock_radar_config
from .technical_state import StockRadarTechnicalState, StockRadarTechnicalStateService
from .technical_state_radar import StockRadarTechnicalStateRadar


@dataclass(frozen=True)
class RuntimeDiagnostic:
    symbol: str
    stage: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "stage": self.stage,
            "code": self.code,
            "message": self.message,
        }


class StockRadarProviderRuntime:
    """Read real provider facts once, then persist neutral research state."""

    def __init__(
        self,
        intraday_adapter: MarketDataAdapter,
        daily_adapter: MarketDataAdapter,
        *,
        radar: StockRadarTechnicalStateRadar | None = None,
        state_service: StockRadarTechnicalStateService | None = None,
        config: RuntimeConfig | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        runtime_config = config or load_stock_radar_config().runtime
        self._intraday_adapter = intraday_adapter
        self._daily_adapter = daily_adapter
        self._radar = radar or StockRadarTechnicalStateRadar()
        self._state_service = state_service or StockRadarTechnicalStateService()
        self._config = runtime_config
        self._now = now

    def run(
        self,
        *,
        market: str,
        run_id: str,
        symbols: Sequence[str],
        output_dir: str | Path,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_market = market.strip().lower()
        normalized_run_id = run_id.strip()
        normalized_symbols = tuple(
            dict.fromkeys(str(symbol).strip().upper() for symbol in symbols if str(symbol).strip())
        )
        if normalized_market not in {"cn", "us"}:
            raise ValueError("market must be cn or us")
        if not normalized_run_id:
            raise ValueError("run_id is required")
        if not normalized_symbols:
            raise ValueError("at least one symbol is required")

        effective_as_of = as_of or self._now()
        if effective_as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")

        realtime = RealtimeMarketDataService(
            self._intraday_adapter,
            max_minutes=self._config.minute_history_limit,
            freshness_limit_seconds=self._config.freshness_limit_seconds,
            now=lambda: effective_as_of,
        )
        states: list[StockRadarTechnicalState] = []
        failures: list[RuntimeDiagnostic] = []
        warnings: list[RuntimeDiagnostic] = []
        for symbol in normalized_symbols:
            try:
                seeded = realtime.seed(
                    symbol,
                    start=effective_as_of - timedelta(days=self._config.history_lookback_days),
                    end=effective_as_of,
                    limit=self._config.minute_history_limit,
                )
                if seeded == 0:
                    raise LookupError("provider returned no normalized 1m bars")
                snapshot = realtime.snapshot(symbol, as_of=effective_as_of)
                _require_market(snapshot, normalized_market)
            except Exception as exc:
                failures.append(_diagnostic(symbol, "intraday_history", exc))
                continue

            daily = pd.DataFrame()
            try:
                daily_bars = self._daily_adapter.get_bars(
                    symbol,
                    "1d",
                    end=effective_as_of,
                    limit=self._config.daily_history_limit,
                )
                _require_bar_market(daily_bars, normalized_market)
                daily = _bars_frame(daily_bars)
                if daily.empty:
                    warnings.append(
                        RuntimeDiagnostic(
                            symbol=symbol,
                            stage="daily_history",
                            code="missing_daily_bars",
                            message="daily state remains unknown",
                        )
                    )
            except Exception as exc:
                warnings.append(_diagnostic(symbol, "daily_history", exc))

            try:
                states.append(self._state_service.evaluate(snapshot, daily=daily))
            except Exception as exc:
                failures.append(_diagnostic(symbol, "technical_state", exc))

        runtime_metadata = {
            "requested_count": len(normalized_symbols),
            "evaluated_count": len(states),
            "failed_count": len(failures),
            "warning_count": len(warnings),
            "failures": [item.to_dict() for item in failures],
            "warnings": [item.to_dict() for item in warnings],
            "intraday_adapter": type(self._intraday_adapter).__name__,
            "daily_adapter": type(self._daily_adapter).__name__,
        }
        report = self._radar.publish(
            market=normalized_market,
            run_id=normalized_run_id,
            states=states,
            output_dir=output_dir,
            runtime_metadata=runtime_metadata,
        )
        return report


def _diagnostic(symbol: str, stage: str, exc: Exception) -> RuntimeDiagnostic:
    message = sanitize_diagnostic_text(str(exc), max_length=300) or type(exc).__name__
    return RuntimeDiagnostic(
        symbol=symbol,
        stage=stage,
        code=type(exc).__name__,
        message=message,
    )


def _require_market(snapshot: MarketDataSnapshot, market: str) -> None:
    _require_bar_market(snapshot.minute_bars, market)


def _require_bar_market(bars: Sequence[Bar], market: str) -> None:
    observed = {bar.market for bar in bars}
    if observed and observed != {market}:
        raise ValueError(f"provider market mismatch: expected {market}, observed {sorted(observed)}")


def _bars_frame(bars: Sequence[Bar]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": bar.bar_end,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
    )
