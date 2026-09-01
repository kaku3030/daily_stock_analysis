# -*- coding: utf-8 -*-
"""QMT/xtquant read-only 1m adapter for MarketDataAdapter V1."""

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


def normalize_xtquant_symbol(symbol: str) -> str:
    code = (symbol or "").strip().upper()
    if code.endswith((".SH", ".SZ")) and len(code) == 9:
        return code
    if code.startswith(("SH", "SZ")) and len(code) == 8:
        return f"{code[2:]}.{code[:2]}"
    if code.isdigit() and len(code) == 6:
        market = "SH" if code.startswith(("5", "6", "9")) else "SZ"
        return f"{code}.{market}"
    raise ValueError(f"unsupported xtquant symbol: {symbol}")


def _xt_datetime(value: object) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000
        return datetime.fromtimestamp(numeric, tz=timezone.utc).astimezone(CN_ZONE)
    try:
        parsed = pd.to_datetime(value, utc=False)
    except (TypeError, ValueError):
        return None
    result = parsed.to_pydatetime()
    return result.replace(tzinfo=CN_ZONE) if result.tzinfo is None else result.astimezone(CN_ZONE)


class XtquantMarketDataAdapter(MarketDataAdapter):
    """Normalize xtdata history, snapshots, and genuine quote subscriptions."""

    def __init__(
        self,
        xtdata: object,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        session_resolver: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._xtdata = xtdata
        self._now = now
        self._session_resolver = session_resolver
        self._subscription_ids: list[int] = []
        self._last_health = evaluate_health(
            freshness=0,
            completeness=0,
            timestamp=0,
            provider=0,
            continuity=0,
            cross_check=0,
            quality_flags=("NOT_OBSERVED",),
        )

    def _normalize_bar(self, symbol: str, raw: object, *, received_at: datetime) -> Bar:
        row = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw)
        timestamp = _xt_datetime(row.get("time") or row.get("datetime"))
        flags: list[str] = ["NOT_CROSS_CHECKED"]
        if timestamp is None:
            flags.append("TIMESTAMP_MISMATCH")
            timestamp = received_at.astimezone(CN_ZONE)
        bar_end = timestamp + timedelta(minutes=1)
        fields = {name: row.get(name) for name in ("open", "high", "low", "close")}
        volume_value = row.get("volume", row.get("vol"))
        complete = all(pd.notna(value) for value in (*fields.values(), volume_value))
        numeric = {name: float(value) for name, value in fields.items() if pd.notna(value)}
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
            timestamp=1 if "TIMESTAMP_MISMATCH" not in flags else 0,
            provider=1,
            continuity=1,
            cross_check=0.5,
            quality_flags=flags,
        )
        amount_value = row.get("amount")
        return Bar(
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
            provider="xtquant",
            feed="qmt",
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

    def get_latest_quote(self, symbol: str) -> Quote:
        code = normalize_xtquant_symbol(symbol)
        payload = self._xtdata.get_full_tick([code]) or {}
        raw = payload.get(code)
        if not raw:
            raise LookupError(f"no xtquant quote available for {symbol}")
        received_at = self._now()
        source_timestamp = _xt_datetime(raw.get("time"))
        flags: list[str] = []
        if source_timestamp is None:
            flags.append("MISSING_SOURCE_TIMESTAMP")
            source_timestamp = received_at.astimezone(CN_ZONE)
        price = float(raw.get("lastPrice") or raw.get("price") or 0)
        if price <= 0:
            flags.append("NON_POSITIVE_PRICE")
        health = evaluate_health(
            freshness=1,
            completeness=1 if price > 0 else 0,
            timestamp=1 if raw.get("time") is not None else 0.5,
            provider=1,
            continuity=1,
            cross_check=0.5,
            quality_flags=flags,
        )
        self._last_health = health
        bids = raw.get("bidPrice") or []
        asks = raw.get("askPrice") or []
        return Quote(
            symbol=symbol,
            market="cn",
            asset_type="stock",
            price=price,
            provider="xtquant",
            feed="qmt",
            source_timestamp=source_timestamp,
            received_at=received_at,
            session=self.get_session_status("cn"),
            bid=bids[0] if bids else None,
            ask=asks[0] if asks else None,
            volume=raw.get("volume"),
            amount=raw.get("amount"),
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
            raise NotImplementedError("xtquant V1 exposes raw 1m bars only")
        code = normalize_xtquant_symbol(symbol)
        result = self._xtdata.get_market_data_ex(
            [],
            [code],
            period="1m",
            start_time=start.astimezone(CN_ZONE).strftime("%Y%m%d%H%M%S") if start else "",
            end_time=end.astimezone(CN_ZONE).strftime("%Y%m%d%H%M%S") if end else "",
            count=int(limit) if limit is not None else -1,
            dividend_type="none",
            fill_data=False,
        ) or {}
        frame = result.get(code)
        if frame is None or frame.empty:
            return []
        received_at = self._now()
        bars = [self._normalize_bar(symbol, row, received_at=received_at) for _, row in frame.iterrows()]
        bars.sort(key=lambda item: item.bar_start)
        if bars:
            self._last_health = bars[-1].health or self._last_health
        return bars

    def subscribe(
        self,
        symbols: Sequence[str],
        timeframe: str = "1m",
        callback: Optional[BarCallback] = None,
    ) -> None:
        if timeframe != "1m":
            raise NotImplementedError("xtquant V1 subscribes to raw 1m bars only")
        if callback is None:
            raise ValueError("callback is required for xtquant subscriptions")

        created: list[int] = []

        def on_data(payload: object) -> None:
            received_at = self._now()
            for code, rows in dict(payload or {}).items():
                for raw in rows or []:
                    callback(self._normalize_bar(code, raw, received_at=received_at))

        try:
            for symbol in symbols:
                code = normalize_xtquant_symbol(symbol)
                subscription_id = int(
                    self._xtdata.subscribe_quote(code, period="1m", count=0, callback=on_data)
                )
                if subscription_id <= 0:
                    raise RuntimeError(f"xtquant subscription failed for {code}")
                created.append(subscription_id)
        except Exception:
            for subscription_id in created:
                self._xtdata.unsubscribe_quote(subscription_id)
            raise
        self._subscription_ids.extend(created)

    def get_session_status(self, market: str) -> str:
        if market != "cn":
            return "unsupported"
        if self._session_resolver is None:
            return "unknown"
        return str(self._session_resolver(market))

    def get_provider_health(self) -> MarketDataHealth:
        return self._last_health

    def reconnect(self) -> bool:
        connect = getattr(self._xtdata, "connect", None)
        if not callable(connect):
            return False
        try:
            result = connect()
        except Exception:
            return False
        return result is not False
