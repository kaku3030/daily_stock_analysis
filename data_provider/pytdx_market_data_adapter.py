# -*- coding: utf-8 -*-
"""PyTDX read-only 1m adapter for MarketDataAdapter V1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from .market_data_adapter import (
    Bar,
    BarCallback,
    MarketDataAdapter,
    MarketDataHealth,
    Quote,
    evaluate_health,
)


CN_ZONE = ZoneInfo("Asia/Shanghai")
PYTDX_1MIN_CATEGORY = 8


class PytdxMarketDataAdapter(MarketDataAdapter):
    """Normalize PyTDX minute bars while preserving their minute timestamps.

    PyTDX is request/response, so V1 intentionally does not advertise a
    streaming subscription. The adapter is also restricted to mainland China.
    """

    def __init__(
        self,
        fetcher: object,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        session_resolver: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._fetcher = fetcher
        self._now = now
        self._session_resolver = session_resolver
        self._last_health = evaluate_health(
            freshness=0,
            completeness=0,
            timestamp=0,
            provider=0,
            continuity=0,
            cross_check=0,
            quality_flags=("NOT_OBSERVED",),
        )

    def get_latest_quote(self, symbol: str) -> Quote:
        raw = self._fetcher.get_realtime_quote(symbol)
        if not raw:
            raise LookupError(f"no PyTDX quote available for {symbol}")
        received_at = self._now()
        price = float(raw.get("price") or 0)
        flags = ["MISSING_SOURCE_TIMESTAMP"]
        if price <= 0:
            flags.append("NON_POSITIVE_PRICE")
        health = evaluate_health(
            freshness=1,
            completeness=1 if price > 0 else 0,
            timestamp=0.5,
            provider=1,
            continuity=1,
            cross_check=0.5,
            quality_flags=flags,
        )
        self._last_health = health
        return Quote(
            symbol=symbol,
            market="cn",
            asset_type="stock",
            price=price,
            provider="pytdx",
            feed="tdx_cn",
            source_timestamp=received_at,
            received_at=received_at,
            session=self.get_session_status("cn"),
            volume=raw.get("volume"),
            amount=raw.get("amount"),
            bid=(raw.get("bid_prices") or [None])[0],
            ask=(raw.get("ask_prices") or [None])[0],
            health=health,
            quality_flags=health.quality_flags,
        )

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[Bar]:
        if timeframe != "1m":
            raise NotImplementedError("PyTDX V1 exposes raw 1m bars only")
        count = min(max(int(limit or 800), 1), 800)
        market_code, normalized_code = self._fetcher._get_market_code(symbol)
        received_at = self._now()
        with self._fetcher._pytdx_session() as api:
            raw = api.get_security_bars(PYTDX_1MIN_CATEGORY, market_code, normalized_code, 0, count) or []
            frame = api.to_df(raw) if raw else pd.DataFrame()
        if frame.empty:
            return []

        result: list[Bar] = []
        frame = frame.sort_values("datetime")
        for _, row in frame.iterrows():
            parsed = pd.to_datetime(row.get("datetime"), errors="coerce")
            if pd.isna(parsed):
                continue
            timestamp = parsed.to_pydatetime()
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=CN_ZONE)
            else:
                timestamp = timestamp.astimezone(CN_ZONE)
            if start and timestamp < start.astimezone(CN_ZONE):
                continue
            if end and timestamp >= end.astimezone(CN_ZONE):
                continue

            bar_end = timestamp + timedelta(minutes=1)
            values = {name: row.get(name) for name in ("open", "high", "low", "close")}
            volume_value = row.get("vol", row.get("volume"))
            complete = all(pd.notna(value) for value in (*values.values(), volume_value))
            flags: list[str] = ["NOT_CROSS_CHECKED"]
            numeric = {name: float(value) for name, value in values.items() if pd.notna(value)}
            volume = float(volume_value) if pd.notna(volume_value) else 0.0
            if not complete:
                flags.append("PARTIAL_BAR")
            if complete and not (
                numeric["low"] <= numeric["open"] <= numeric["high"]
                and numeric["low"] <= numeric["close"] <= numeric["high"]
            ):
                flags.append("INVALID_OHLC")
            if volume < 0:
                flags.append("NEGATIVE_VOLUME")
            closed = received_at.astimezone(CN_ZONE) >= bar_end
            if not closed:
                flags.append("PARTIAL_BAR")
            health = evaluate_health(
                freshness=1,
                completeness=1 if complete else 0.5,
                timestamp=1,
                provider=1,
                continuity=1,
                cross_check=0.5,
                quality_flags=flags,
            )
            amount_value = row.get("amount")
            result.append(
                Bar(
                    symbol=symbol,
                    market="cn",
                    asset_type="stock",
                    timeframe="1m",
                    bar_start=timestamp,
                    bar_end=bar_end,
                    open=numeric.get("open", 0),
                    high=numeric.get("high", 0),
                    low=numeric.get("low", 0),
                    close=numeric.get("close", 0),
                    volume=volume,
                    amount=float(amount_value) if pd.notna(amount_value) else None,
                    provider="pytdx",
                    feed="tdx_cn",
                    session="regular",
                    source_timestamp=bar_end,
                    received_at=received_at,
                    is_closed=closed,
                    is_complete=complete and closed,
                    latency_ms=max(0, int((received_at - bar_end.astimezone(timezone.utc)).total_seconds() * 1000)),
                    freshness_ms=max(0, int((received_at - bar_end.astimezone(timezone.utc)).total_seconds() * 1000)),
                    health=health,
                    quality_flags=health.quality_flags,
                )
            )
        if result:
            self._last_health = result[-1].health or self._last_health
        return result

    def subscribe(
        self,
        symbols: Sequence[str],
        timeframe: str = "1m",
        callback: Optional[BarCallback] = None,
    ) -> None:
        raise NotImplementedError("PyTDX V1 does not provide streaming subscriptions")

    def get_session_status(self, market: str) -> str:
        if market != "cn":
            return "unsupported"
        if self._session_resolver is None:
            return "unknown"
        return str(self._session_resolver(market))

    def get_provider_health(self) -> MarketDataHealth:
        return self._last_health

    def reconnect(self) -> bool:
        return False
