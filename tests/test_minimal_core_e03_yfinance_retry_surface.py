"""Shadow evidence for Minimal Core E03 YFinance retry semantics.

This test records current behavior only. It does not change retry counts,
provider routing, or fallback policy.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from data_provider.base import DataFetchError
from data_provider.yfinance_fetcher import YfinanceFetcher


def test_e03_yfinance_transport_error_is_wrapped_before_tenacity_can_retry(monkeypatch) -> None:
    calls = {"count": 0}

    def failing_download(**_kwargs):
        calls["count"] += 1
        raise ConnectionError("synthetic yfinance transport failure")

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=failing_download))

    fetcher = YfinanceFetcher()

    with pytest.raises(DataFetchError) as exc_info:
        fetcher._fetch_raw_data("AAPL", "2026-09-01", "2026-09-10")

    # Current function body converts the retryable transport exception into
    # DataFetchError, while the decorator retries only ConnectionError/TimeoutError.
    # Therefore the configured stop_after_attempt(3) does not produce a second
    # download call on this ordinary wrapped path.
    assert calls["count"] == 1
    assert isinstance(exc_info.value.__cause__, ConnectionError)
    assert "synthetic yfinance transport failure" in str(exc_info.value)


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("timeout", TimeoutError("synthetic timeout")),
        ("provider_data_fetch", DataFetchError("provider body failure")),
        ("non_transport", ValueError("synthetic parser failure")),
    ],
)
def test_e03_yfinance_shadow_matrix_is_single_call_and_preserves_surface(
    monkeypatch, label, payload
) -> None:
    calls = {"count": 0}

    def failing_download(**_kwargs):
        calls["count"] += 1
        raise payload

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=failing_download))
    fetcher = YfinanceFetcher()

    with pytest.raises(DataFetchError) as exc_info:
        fetcher._fetch_raw_data("AAPL", "2026-09-01", "2026-09-10")

    assert calls["count"] == 1, label
    if isinstance(payload, DataFetchError):
        assert exc_info.value is payload
    else:
        assert exc_info.value.__cause__ is payload
        assert type(exc_info.value.__cause__) is type(payload)


def test_e03_yfinance_empty_no_data_is_data_fetch_error_without_retry(monkeypatch) -> None:
    calls = {"count": 0}

    def empty_download(**_kwargs):
        calls["count"] += 1
        return __import__("pandas").DataFrame()

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=empty_download))
    with pytest.raises(DataFetchError, match="未查询到"):
        YfinanceFetcher()._fetch_raw_data("AAPL", "2026-09-01", "2026-09-10")
    assert calls["count"] == 1
