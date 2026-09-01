# -*- coding: utf-8 -*-
"""Health-aware primary/fallback routing for read-only market data."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Optional, Sequence

from .base import DataFetchError
from .market_data_adapter import (
    Bar,
    BarCallback,
    MarketDataAdapter,
    MarketDataHealth,
    Quote,
    SignalPermission,
)


class MarketDataRouter(MarketDataAdapter):
    """Route snapshots and bars without disguising polling as streaming."""

    def __init__(
        self,
        primary: MarketDataAdapter,
        fallback: MarketDataAdapter,
        *,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
        fallback_exceptions: tuple[type[BaseException], ...] = (
            DataFetchError,
            ConnectionError,
            TimeoutError,
            OSError,
            LookupError,
            RuntimeError,
        ),
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_name = primary_name
        self._fallback_name = fallback_name
        self._fallback_exceptions = fallback_exceptions
        self._last_health = primary.get_provider_health()

    @staticmethod
    def _usable(health: Optional[MarketDataHealth]) -> bool:
        return health is not None and health.signal_permission is not SignalPermission.BLOCKED

    def _mark_fallback(self, item: Bar | Quote, reason: str) -> Bar | Quote:
        health = item.health
        if health is not None:
            flags = tuple(dict.fromkeys((*health.quality_flags, "FALLBACK_PROVIDER")))
            health = replace(health, quality_flags=flags)
        return replace(
            item,
            health=health,
            quality_flags=tuple(dict.fromkeys((*item.quality_flags, "FALLBACK_PROVIDER"))),
            fallback_from=self._primary_name,
            fallback_reason=reason,
        )

    def get_latest_quote(self, symbol: str) -> Quote:
        reason = ""
        try:
            quote = self._primary.get_latest_quote(symbol)
            if self._usable(quote.health):
                self._last_health = quote.health
                return quote
            reason = "primary_health_blocked"
        except self._fallback_exceptions as exc:
            reason = f"primary_error:{type(exc).__name__}"

        quote = self._fallback.get_latest_quote(symbol)
        marked = self._mark_fallback(quote, reason)
        self._last_health = marked.health or self._fallback.get_provider_health()
        return marked

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[Bar]:
        reason = ""
        try:
            bars = self._primary.get_bars(symbol, timeframe, start=start, end=end, limit=limit)
            if bars and all(self._usable(bar.health) for bar in bars):
                self._last_health = bars[-1].health or self._primary.get_provider_health()
                return bars
            reason = "primary_empty" if not bars else "primary_health_blocked"
        except self._fallback_exceptions as exc:
            reason = f"primary_error:{type(exc).__name__}"

        bars = self._fallback.get_bars(symbol, timeframe, start=start, end=end, limit=limit)
        marked = [self._mark_fallback(bar, reason) for bar in bars]
        if marked:
            self._last_health = marked[-1].health or self._fallback.get_provider_health()
        return marked

    def subscribe(
        self,
        symbols: Sequence[str],
        timeframe: str = "1m",
        callback: Optional[BarCallback] = None,
    ) -> None:
        """Use the primary's genuine subscription; never poll the fallback."""

        self._primary.subscribe(symbols, timeframe=timeframe, callback=callback)

    def get_session_status(self, market: str) -> str:
        status = self._primary.get_session_status(market)
        if status not in {"unknown", "unsupported", ""}:
            return status
        return self._fallback.get_session_status(market)

    def get_provider_health(self) -> MarketDataHealth:
        return self._last_health

    def reconnect(self) -> bool:
        return self._primary.reconnect()
