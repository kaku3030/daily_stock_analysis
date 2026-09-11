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
