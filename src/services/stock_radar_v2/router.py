"""Debounced V2 routing over provider-neutral MarketDataAdapter V1."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from time import monotonic
from typing import Callable, Optional, Sequence, TypeVar

from data_provider.market_data_adapter import (
    Bar,
    BarCallback,
    MarketDataAdapter,
    MarketDataHealth,
    Quote,
    SignalPermission,
)

from .health import FailureKind, FallbackStateMachine, ProviderMode


T = TypeVar("T", Quote, list[Bar])


class DebouncedMarketDataRouter(MarketDataAdapter):
    """Use fallback only after V2 thresholds; never emulate streaming."""

    def __init__(
        self,
        primary: MarketDataAdapter,
        fallback: MarketDataAdapter,
        state: FallbackStateMachine,
        *,
        now: Callable[[], datetime],
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._state = state
        self._now = now
        self._clock = clock

    @staticmethod
    def _usable(value: Quote | Bar) -> bool:
        return value.health is not None and value.health.signal_permission is not SignalPermission.BLOCKED

    @staticmethod
    def _failure_kind(exc: BaseException) -> FailureKind:
        if isinstance(exc, TimeoutError):
            return FailureKind.TIMEOUT
        if isinstance(exc, PermissionError):
            return FailureKind.AUTH
        if isinstance(exc, ConnectionError):
            return FailureKind.CONNECTION
        if isinstance(exc, LookupError):
            return FailureKind.EMPTY
        if isinstance(exc, (ValueError, TypeError)):
            return FailureKind.PARSE
        return FailureKind.OTHER

    def _primary_call(self, call: Callable[[], T]) -> T:
        started = self._clock()
        try:
            value = call()
            if isinstance(value, list):
                if not value:
                    raise LookupError("primary returned no bars")
                if not all(self._usable(item) for item in value):
                    raise ValueError("primary returned blocked bar health")
            elif not self._usable(value):
                raise ValueError("primary returned blocked quote health")
            return value
        except Exception as exc:
            elapsed = max(0.0, self._clock() - started)
            decision = self._state.record_failure(
                self._failure_kind(exc),
                observed_at=self._now(),
                elapsed_seconds=elapsed,
                error_code=str(getattr(exc, "code", "") or "") or None,
            )
            if decision.mode is ProviderMode.FALLBACK:
                raise _FallbackRequired from exc
            raise

    def _route(self, primary_call: Callable[[], T], fallback_call: Callable[[], T]) -> T:
        if self._state.mode is ProviderMode.PRIMARY:
            try:
                value = self._primary_call(primary_call)
            except _FallbackRequired:
                return self._marked_fallback(fallback_call())
            self._state.record_success()
            return value

        if self._state.health_check_due(self._now()):
            try:
                value = self._primary_call(primary_call)
            except Exception:
                self._state.record_recovery_probe(False, observed_at=self._now())
            else:
                decision = self._state.record_recovery_probe(True, observed_at=self._now())
                if decision.mode is ProviderMode.PRIMARY:
                    return value
        return self._marked_fallback(fallback_call())

    def _marked_fallback(self, value: T) -> T:
        def mark(item: Quote | Bar) -> Quote | Bar:
            health = item.health
            if health is not None:
                health = replace(
                    health,
                    quality_flags=tuple(
                        dict.fromkeys((*health.quality_flags, "FALLBACK_PROVIDER"))
                    ),
                )
            return replace(
                item,
                health=health,
                quality_flags=tuple(
                    dict.fromkeys((*item.quality_flags, "FALLBACK_PROVIDER"))
                ),
                fallback_from=self._state.primary_name,
                fallback_reason=self._state.fallback_reason,
            )

        if isinstance(value, list):
            return [mark(item) for item in value]  # type: ignore[return-value]
        return mark(value)  # type: ignore[return-value]

    def get_latest_quote(self, symbol: str) -> Quote:
        return self._route(
            lambda: self._primary.get_latest_quote(symbol),
            lambda: self._fallback.get_latest_quote(symbol),
        )

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[Bar]:
        return self._route(
            lambda: self._primary.get_bars(symbol, timeframe, start=start, end=end, limit=limit),
            lambda: self._fallback.get_bars(symbol, timeframe, start=start, end=end, limit=limit),
        )

    def subscribe(
        self,
        symbols: Sequence[str],
        timeframe: str = "1m",
        callback: Optional[BarCallback] = None,
    ) -> None:
        try:
            self._primary.subscribe(symbols, timeframe=timeframe, callback=callback)
        except Exception as exc:
            self._state.record_failure(
                FailureKind.SUBSCRIPTION,
                observed_at=self._now(),
                error_code=str(getattr(exc, "code", "") or "") or None,
            )
            raise

    def get_session_status(self, market: str) -> str:
        adapter = self._primary if self._state.mode is ProviderMode.PRIMARY else self._fallback
        return adapter.get_session_status(market)

    def get_provider_health(self) -> MarketDataHealth:
        adapter = self._primary if self._state.mode is ProviderMode.PRIMARY else self._fallback
        return adapter.get_provider_health()

    def reconnect(self) -> bool:
        return self._primary.reconnect()


class _FallbackRequired(RuntimeError):
    pass
