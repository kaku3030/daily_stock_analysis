"""Bounded US intraday data adapter with explicit partial-bar metadata."""

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_INTERVAL_MINUTES = {"15m": 15, "60m": 60, "1h": 60}
_DEFAULT_PERIOD = {"15m": "60d", "60m": "730d", "1h": "730d"}


@dataclass
class IntradayBars:
    data: pd.DataFrame
    interval: str
    source: str
    is_partial_bar: bool
    as_of: Optional[str]
    cache_hit: bool = False


def _cache_dir() -> Path:
    return Path(os.getenv("TECHNICAL_INTRADAY_CACHE_DIR", "data/technical/intraday"))


def _cache_paths(symbol: str, interval: str) -> tuple[Path, Path]:
    safe_symbol = "".join(char for char in symbol.upper() if char.isalnum() or char in "-_")
    base = _cache_dir() / f"{safe_symbol}.{interval}"
    return Path(f"{base}.csv"), Path(f"{base}.json")


def _read_cache(symbol: str, interval: str, ttl_seconds: float) -> Optional[IntradayBars]:
    csv_path, metadata_path = _cache_paths(symbol, interval)
    if not csv_path.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if time.time() - float(metadata["written_at"]) > ttl_seconds:
            return None
        frame = pd.read_csv(csv_path, parse_dates=["date"])
        return IntradayBars(
            data=frame,
            interval=interval,
            source=str(metadata.get("source", "yfinance_cache")),
            is_partial_bar=bool(metadata.get("is_partial_bar")),
            as_of=metadata.get("as_of"),
            cache_hit=True,
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(symbol: str, result: IntradayBars) -> None:
    csv_path, metadata_path = _cache_paths(symbol, result.interval)
    try:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        result.data.to_csv(csv_path, index=False)
        metadata_path.write_text(
            json.dumps(
                {
                    "written_at": time.time(),
                    "source": result.source,
                    "is_partial_bar": result.is_partial_bar,
                    "as_of": result.as_of,
                }
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Unable to write intraday cache for %s: %s", symbol, exc)


def _normalize_download(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = result.columns.get_level_values(0)
    result = result.reset_index()
    result.columns = [str(column).lower().replace("datetime", "date") for column in result.columns]
    if "date" not in result.columns and "index" in result.columns:
        result = result.rename(columns={"index": "date"})
    keep = ["date", "open", "high", "low", "close", "volume"]
    return result[[column for column in keep if column in result.columns]].dropna(subset=["close"])


def _is_partial(frame: pd.DataFrame, interval: str, now: Optional[pd.Timestamp] = None) -> bool:
    if frame.empty or "date" not in frame.columns:
        return False
    latest = pd.Timestamp(frame.iloc[-1]["date"])
    current = now or pd.Timestamp.now(tz=latest.tz)
    if latest.tzinfo is None and current.tzinfo is not None:
        current = current.tz_localize(None)
    return current < latest + pd.Timedelta(minutes=_INTERVAL_MINUTES[interval])


def fetch_yfinance_intraday(
    symbol: str,
    interval: str,
    *,
    period: Optional[str] = None,
    cache_ttl_seconds: float = 300,
    force_refresh: bool = False,
) -> IntradayBars:
    normalized_interval = "60m" if interval == "1h" else interval
    if normalized_interval not in _INTERVAL_MINUTES:
        raise ValueError(f"Unsupported intraday interval: {interval}")
    if not force_refresh:
        cached = _read_cache(symbol, normalized_interval, cache_ttl_seconds)
        if cached is not None:
            return cached

    import yfinance as yf

    raw = yf.download(
        symbol,
        period=period or _DEFAULT_PERIOD[normalized_interval],
        interval=normalized_interval,
        auto_adjust=True,
        progress=False,
        prepost=False,
        threads=False,
    )
    frame = _normalize_download(raw)
    if frame.empty:
        raise RuntimeError(f"yfinance returned no {normalized_interval} bars for {symbol}")
    partial = _is_partial(frame, normalized_interval)
    result = IntradayBars(
        data=frame,
        interval=normalized_interval,
        source="yfinance",
        is_partial_bar=partial,
        as_of=str(frame.iloc[-1]["date"]),
    )
    _write_cache(symbol, result)
    return result


def fetch_us_multitimeframe(symbol: str) -> tuple[IntradayBars, IntradayBars]:
    """Fetch 1h and 15m bars independently so one interval can fail alone."""
    return fetch_yfinance_intraday(symbol, "60m"), fetch_yfinance_intraday(symbol, "15m")
