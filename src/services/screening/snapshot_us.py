# -*- coding: utf-8 -*-
# Derived from AlphaSift revision 9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf.
# Licensed under Apache-2.0 and modified for daily_stock_analysis.
"""US equity snapshot via yfinance.

US snapshot provider for the screening L1 pipeline. Fetches a configurable
equity universe and returns the standard snapshot DataFrame schema.

HK is not supported yet: there is no HK universe source or ticker
configuration path, so ``market="hk"`` is rejected at the pipeline level
rather than silently screening the US pool.
"""

import logging
import os
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_NASDAQ100_WIKI_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
_NASDAQ100_COMPANIES_URL = "https://www.nasdaq.com/solutions/nasdaq-100/companies"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_UNIVERSE_CACHE_VERSION = 1
_UNIVERSE_HTTP_TIMEOUT_SECONDS = 20.0
_UNIVERSE_CACHE_MAX_AGE_HOURS = 24 * 7
_VALUATION_CACHE_VERSION = 1
_VALUATION_CACHE_MAX_AGE_HOURS = 24 * 7

_DEFAULT_US_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B",
    "AVGO", "JPM", "LLY", "V", "MA", "UNH", "XOM", "COST", "HD", "PG",
    "JNJ", "ABBV", "WMT", "NFLX", "BAC", "KO", "CRM", "CVX", "MRK",
    "PEP", "AMD", "TMO", "LIN", "ACN", "CSCO", "MCD", "ABT", "ADBE",
    "WFC", "GE", "DHR", "TXN", "PM", "ISRG", "MS", "NEE", "INTU",
    "DIS", "QCOM", "CAT", "NOW",
]


@dataclass(frozen=True)
class USUniverseResolution:
    """Resolved US ticker universe plus provenance for coverage validation."""

    tickers: list[str]
    requested_source: str
    resolved_source: str
    fallback_used: bool = False
    errors: tuple[str, ...] = ()


def fetch_us_universe(source: str = "auto") -> list[str]:
    """Return a list of US equity tickers.

    Sources:
        sp500   — scrape S&P 500 from Wikipedia
        nasdaq100 — scrape NASDAQ-100 from Wikipedia
        sp500_nasdaq100 — merge both universes and remove duplicates
        env     — read SCREENING_US_TICKERS (comma-separated)
        default — hardcoded top-50 US large-caps
        auto    — configured source → matching cache → sp500 → env → default
    """
    return resolve_us_universe(source).tickers


def resolve_us_universe(source: str = "auto") -> USUniverseResolution:
    """Resolve a US equity universe without hiding fallback provenance."""
    src = source.lower().strip()
    if src == "auto":
        configured = os.getenv("SCREENING_US_UNIVERSE_SOURCE", "sp500_nasdaq100").strip().lower()
        requested = configured or "sp500_nasdaq100"
        errors: list[str] = []
        try:
            tickers = _fetch_us_universe_source(requested)
            _validate_universe_size(requested, tickers)
            _write_universe_cache(requested, tickers)
            return USUniverseResolution(tickers, requested, requested)
        except Exception as exc:
            errors.append(f"{requested}: {exc}")

        cached = _read_universe_cache(requested)
        if cached:
            return USUniverseResolution(
                cached,
                requested,
                f"cache:{requested}",
                fallback_used=True,
                errors=tuple(errors),
            )

        for fallback in ("sp500", "env", "default"):
            if fallback == requested:
                continue
            try:
                tickers = _fetch_us_universe_source(fallback)
                if tickers:
                    logger.warning(
                        "US universe %s unavailable; falling back to %s (%d tickers)",
                        requested,
                        fallback,
                        len(tickers),
                    )
                    return USUniverseResolution(
                        tickers,
                        requested,
                        fallback,
                        fallback_used=True,
                        errors=tuple(errors),
                    )
            except Exception as exc:
                errors.append(f"{fallback}: {exc}")
        return USUniverseResolution(
            list(_DEFAULT_US_UNIVERSE),
            requested,
            "default",
            fallback_used=True,
            errors=tuple(errors),
        )

    tickers = _fetch_us_universe_source(src)
    return USUniverseResolution(tickers, src, src)


def _fetch_us_universe_source(src: str) -> list[str]:
    if src == "sp500":
        return _fetch_sp500_tickers()
    elif src == "nasdaq100":
        return _fetch_nasdaq100_tickers()
    elif src in {"sp500_nasdaq100", "combined"}:
        return sorted(set(_fetch_sp500_tickers()) | set(_fetch_nasdaq100_tickers()))
    elif src == "env":
        raw = os.getenv("SCREENING_US_TICKERS", "").strip()
        if not raw:
            raise ValueError("SCREENING_US_TICKERS not set")
        return [t.strip() for t in raw.split(",") if t.strip()]
    elif src == "default":
        return list(_DEFAULT_US_UNIVERSE)
    else:
        raise ValueError(f"Unknown US universe source: {src}")


def _fetch_sp500_tickers() -> list[str]:
    tables = _read_html_tables(_SP500_WIKI_URL)
    for tbl in tables:
        if "Symbol" in tbl.columns:
            return sorted(tbl["Symbol"].dropna().str.strip().str.replace(".", "-", regex=False).tolist())
    raise RuntimeError("Could not find Symbol column in S&P 500 Wikipedia table")


def _fetch_nasdaq100_tickers() -> list[str]:
    official_error: Exception | None = None
    try:
        return _fetch_nasdaq100_official_tickers()
    except Exception as exc:
        official_error = exc

    tables = _read_html_tables(_NASDAQ100_WIKI_URL)
    for table in tables:
        symbol_column = next(
            (column for column in table.columns if str(column).strip().lower() in {"ticker", "symbol"}),
            None,
        )
        if symbol_column is not None:
            return sorted(
                table[symbol_column]
                .dropna()
                .astype(str)
                .str.strip()
                .str.replace(".", "-", regex=False)
                .tolist()
            )
    raise RuntimeError(
        "Could not resolve Nasdaq-100 constituents from Nasdaq or Wikipedia: "
        f"nasdaq={official_error}; wikipedia=ticker column missing"
    )


def _fetch_nasdaq100_official_tickers() -> list[str]:
    html = _fetch_html_text(_NASDAQ100_COMPANIES_URL)
    script_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in script_blocks:
        try:
            payload = json.loads(unescape(block).strip())
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for candidate in _walk_json_objects(payload):
            if candidate.get("name") != "Nasdaq-100 Company Breakdown":
                continue
            items = candidate.get("itemListElement")
            if not isinstance(items, list):
                continue
            tickers = sorted({
                str(item.get("description") or "").strip().upper().replace(".", "-")
                for item in items
                if isinstance(item, dict)
                and re.fullmatch(
                    r"[A-Z][A-Z0-9.-]{0,9}",
                    str(item.get("description") or "").strip().upper(),
                )
            })
            if len(tickers) >= 90:
                return tickers
    raise RuntimeError("Nasdaq-100 structured company list missing or incomplete")


def _walk_json_objects(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_json_objects(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_json_objects(nested)


def _read_html_tables(url: str) -> list[pd.DataFrame]:
    """Read index tables with an explicit user agent and bounded retries."""
    return pd.read_html(StringIO(_fetch_html_text(url)))


def _fetch_html_text(url: str) -> str:
    """Fetch one public index page with an explicit user agent and retries."""
    retries = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retries))
        response = session.get(
            url,
            headers={"User-Agent": "daily_stock_analysis/US-research-universe"},
            timeout=_UNIVERSE_HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    return response.text


def _universe_cache_path() -> Path:
    configured = os.getenv("SCREENING_US_UNIVERSE_CACHE_PATH", "").strip()
    return Path(configured) if configured else _PROJECT_ROOT / "data" / "us_universe.last_good.json"


def _write_universe_cache(source: str, tickers: list[str]) -> None:
    if not tickers:
        return
    path = _universe_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _UNIVERSE_CACHE_VERSION,
            "source": source,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "tickers": sorted(set(tickers)),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not persist US universe cache %s: %s", path, exc)


def _validate_universe_size(source: str, tickers: list[str]) -> None:
    minimums = {
        "sp500": 450,
        "nasdaq100": 90,
        "sp500_nasdaq100": 400,
        "combined": 400,
    }
    minimum = minimums.get(source, 1)
    if len(tickers) < minimum:
        raise RuntimeError(
            f"universe source {source} returned {len(tickers)} tickers; minimum={minimum}"
        )


def _read_universe_cache(source: str) -> list[str]:
    path = _universe_cache_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != _UNIVERSE_CACHE_VERSION or payload.get("source") != source:
            return []
        captured_at = datetime.fromisoformat(str(payload["captured_at"]).replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - captured_at.astimezone(timezone.utc)).total_seconds() / 3600
        max_age = max(
            0.0,
            float(os.getenv("SCREENING_US_UNIVERSE_CACHE_MAX_AGE_HOURS", _UNIVERSE_CACHE_MAX_AGE_HOURS)),
        )
        if age_hours > max_age:
            return []
        tickers = sorted({
            str(item).strip()
            for item in payload.get("tickers", [])
            if str(item).strip()
        })
        _validate_universe_size(source, tickers)
        return tickers
    except (FileNotFoundError, KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        return []


def fetch_us_snapshot(
    tickers: list[str] | None = None,
    *,
    universe_source: str = "auto",
    max_workers: int = 8,
) -> pd.DataFrame:
    """Fetch a US equity snapshot in the screening schema.

    Uses yfinance to fetch current data for each ticker. Returns a
    DataFrame matching the standard snapshot columns: code, name, price,
    change_pct, amount, total_mv, pe_ratio, pb_ratio, volume_ratio,
    turnover_rate, industry.
    """
    import yfinance as yf

    if tickers is None:
        resolution = resolve_us_universe(universe_source)
        tickers = resolution.tickers
    else:
        resolution = USUniverseResolution(list(tickers), "explicit", "explicit")

    logger.info("Fetching US snapshot for %d tickers", len(tickers))

    hist_end = pd.Timestamp.now().normalize()
    hist_start = hist_end - pd.Timedelta(days=30)
    data = yf.download(
        tickers,
        start=hist_start.strftime("%Y-%m-%d"),
        end=hist_end.strftime("%Y-%m-%d"),
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    rows = []

    def _process_ticker(ticker: str) -> dict | None:
        try:
            if len(tickers) == 1:
                hist = data.copy()
                if isinstance(hist.columns, pd.MultiIndex):
                    hist.columns = hist.columns.droplevel("Ticker")
            else:
                if ticker not in data.columns.get_level_values(0):
                    return None
                hist = data[ticker].copy()
            if hist.empty:
                return None

            hist = hist[hist["Close"].notna()]
            if len(hist) < 2:
                return None

            latest = hist.iloc[-1]
            prev = hist.iloc[-2]
            price = float(latest["Close"])
            prev_close = float(prev["Close"])
            volume = float(latest["Volume"])
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

            vol_20d = float(hist["Volume"].tail(20).mean())
            volume_ratio = (volume / vol_20d) if vol_20d > 0 else 1.0

            info = yf.Ticker(ticker).fast_info
            market_cap = getattr(info, "market_cap", None) or 0
            shares = getattr(info, "shares", None) or 0
            turnover_rate = (volume / shares * 100) if shares > 0 else 0.0

            return {
                "code": ticker,
                "name": ticker,
                "price": price,
                "change_pct": round(change_pct, 2),
                "amount": round(volume * price, 0),
                "total_mv": market_cap,
                "circ_mv": market_cap,
                "pe_ratio": None,
                "pb_ratio": None,
                "volume_ratio": round(volume_ratio, 2),
                "turnover_rate": round(turnover_rate, 4),
                "industry": "",
            }
        except Exception as e:
            logger.debug("Failed to process %s: %s", ticker, e)
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process_ticker, t): t for t in tickers}
        for future in as_completed(futures):
            result = future.result()
            if result:
                rows.append(result)

    if not rows:
        raise RuntimeError("yfinance returned no valid data for any ticker")

    df = pd.DataFrame(rows)

    numeric_cols = [
        "price", "change_pct", "amount", "total_mv", "circ_mv",
        "pe_ratio", "pb_ratio", "volume_ratio", "turnover_rate",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["price"])
    df = df[df["price"] > 0]

    valuation_sources = _enrich_info_fields(df)

    df.attrs["snapshot_source"] = "yfinance"
    df.attrs["universe_requested_source"] = resolution.requested_source
    df.attrs["universe_source"] = resolution.resolved_source
    df.attrs["universe_count"] = len(tickers)
    df.attrs["universe_snapshot_count"] = len(df)
    df.attrs["universe_coverage_ratio"] = round(len(df) / len(tickers), 6) if tickers else 0.0
    df.attrs["universe_fallback_used"] = resolution.fallback_used
    df.attrs["universe_errors"] = list(resolution.errors)
    df.attrs["valuation_sources"] = valuation_sources
    logger.info("US snapshot: %d rows from yfinance", len(df))
    return df


def _enrich_info_fields(df: pd.DataFrame) -> dict[str, object]:
    """Best-effort live enrichment with a bounded last-known-good valuation fallback."""
    import yfinance as yf

    needs_pe = df["pe_ratio"].isna().sum() > len(df) * 0.5
    if not needs_pe:
        return _valuation_source_counts(df, live_fields={})

    cache = _read_valuation_cache()
    live_fields: dict[str, set[str]] = {"pe_ratio": set(), "pb_ratio": set()}
    request_errors = 0

    for idx in df.index:
        ticker = str(df.at[idx, "code"] or "").strip().upper()
        try:
            info = yf.Ticker(ticker).info
            if pd.isna(df.at[idx, "pe_ratio"]) or df.at[idx, "pe_ratio"] == 0:
                df.at[idx, "pe_ratio"] = info.get("trailingPE")
            if pd.isna(df.at[idx, "pb_ratio"]) or df.at[idx, "pb_ratio"] == 0:
                df.at[idx, "pb_ratio"] = info.get("priceToBook")
            if not df.at[idx, "industry"]:
                df.at[idx, "industry"] = info.get("industry", "")
            if not df.at[idx, "name"] or df.at[idx, "name"] == ticker:
                df.at[idx, "name"] = info.get("shortName", ticker)
        except Exception as exc:
            request_errors += 1
            logger.debug("US valuation enrichment failed for %s: %s", ticker, exc)

        entry = cache.get(ticker)
        if not isinstance(entry, dict):
            entry = {}
            cache[ticker] = entry
        for field in ("pe_ratio", "pb_ratio"):
            value = _finite_number(df.at[idx, field])
            if value is not None:
                df.at[idx, field] = value
                live_fields[field].add(ticker)
                entry[field] = {
                    "value": value,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }
                continue
            cached_value = _cached_valuation(entry.get(field))
            if cached_value is not None:
                df.at[idx, field] = cached_value

    _write_valuation_cache(cache)
    stats = _valuation_source_counts(df, live_fields=live_fields)
    stats["request_errors"] = request_errors
    logger.info(
        "US valuation enrichment: pe_ratio live=%d cached=%d missing=%d; "
        "pb_ratio live=%d cached=%d missing=%d; request_errors=%d",
        stats["pe_ratio"]["live"],
        stats["pe_ratio"]["cached"],
        stats["pe_ratio"]["missing"],
        stats["pb_ratio"]["live"],
        stats["pb_ratio"]["cached"],
        stats["pb_ratio"]["missing"],
        request_errors,
    )
    return stats


def _valuation_cache_path() -> Path:
    return _PROJECT_ROOT / "data" / "us_valuation.last_good.json"


def _read_valuation_cache() -> dict[str, dict]:
    try:
        payload = json.loads(_valuation_cache_path().read_text(encoding="utf-8"))
        if payload.get("version") != _VALUATION_CACHE_VERSION:
            return {}
        entries = payload.get("entries")
        return entries if isinstance(entries, dict) else {}
    except (FileNotFoundError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _write_valuation_cache(entries: dict[str, dict]) -> None:
    path = _valuation_cache_path()
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _VALUATION_CACHE_VERSION, "entries": entries}
        temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(path)
    except Exception as exc:
        logger.warning("Could not persist US valuation cache %s: %s", path, exc)
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _cached_valuation(value: object) -> float | None:
    if not isinstance(value, dict):
        return None
    number = _finite_number(value.get("value"))
    if number is None:
        return None
    try:
        captured_at = datetime.fromisoformat(str(value["captured_at"]).replace("Z", "+00:00"))
        age_hours = (
            datetime.now(timezone.utc) - captured_at.astimezone(timezone.utc)
        ).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        return None
    return number if 0 <= age_hours <= _VALUATION_CACHE_MAX_AGE_HOURS else None


def _valuation_source_counts(
    df: pd.DataFrame,
    *,
    live_fields: dict[str, set[str]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    codes = df["code"].astype(str).str.upper()
    for field in ("pe_ratio", "pb_ratio"):
        available = pd.to_numeric(df[field], errors="coerce").notna()
        live = codes.isin(live_fields.get(field, set())) & available
        result[field] = {
            "live": int(live.sum()),
            "cached": int((available & ~live).sum()),
            "missing": int((~available).sum()),
        }
    return result


def _finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_daily_history_yfinance(
    ticker: str,
    *,
    lookback_days: int = 120,
) -> pd.DataFrame:
    """Fetch daily OHLCV history for a US ticker via yfinance.

    Returns a DataFrame with columns: date, open, high, low, close, volume
    matching the schema expected by the daily enrichment logic.
    """
    import yfinance as yf

    end = pd.Timestamp.now().normalize()
    start = end - pd.Timedelta(days=max(lookback_days * 2, 180))
    hist = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if hist is None or hist.empty:
        raise RuntimeError(f"yfinance daily history empty for {ticker}")

    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = hist.columns.droplevel("Ticker")

    hist = hist.tail(max(lookback_days, 30)).copy()
    hist = hist.rename(columns={
        "Open": "开盘", "High": "最高", "Low": "最低",
        "Close": "收盘", "Volume": "成交量",
    })
    hist.index.name = "日期"
    hist = hist.reset_index()
    return hist
