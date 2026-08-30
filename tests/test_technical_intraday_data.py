import pandas as pd

from src.technical.intraday_data import _is_partial, _normalize_download


def test_normalize_download_flattens_yfinance_columns() -> None:
    columns = pd.MultiIndex.from_tuples(
        [(name, "NVDA") for name in ("Open", "High", "Low", "Close", "Volume")]
    )
    frame = pd.DataFrame([[1, 2, 0.5, 1.5, 100]], columns=columns, index=pd.DatetimeIndex(["2026-08-28"]))
    result = _normalize_download(frame)
    assert list(result.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_partial_bar_uses_bar_end_time() -> None:
    frame = pd.DataFrame({"date": [pd.Timestamp("2026-08-28 10:00:00")], "close": [100]})
    assert _is_partial(frame, "15m", pd.Timestamp("2026-08-28 10:10:00")) is True
    assert _is_partial(frame, "15m", pd.Timestamp("2026-08-28 10:16:00")) is False
