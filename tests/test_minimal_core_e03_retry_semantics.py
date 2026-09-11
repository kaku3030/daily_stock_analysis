"""Shadow evidence for Minimal Core E03 retry inventory.

These tests do not change production behavior. They pin the current observable
semantics of EfinanceFetcher._fetch_raw_data so a later simplification can be
compared against the existing Tenacity wrapper.
"""

import pytest
import requests
from tenacity import RetryError

from data_provider.base import DataFetchError, unwrap_exception
from data_provider.efinance_fetcher import EfinanceFetcher


def _fetcher() -> EfinanceFetcher:
    # _fetch_raw_data routes to the patched method before any provider I/O.
    return EfinanceFetcher(sleep_min=0.0, sleep_max=0.0)


def test_e03_retryable_exception_is_attempted_once_and_wrapped(monkeypatch):
    fetcher = _fetcher()
    attempts = 0

    def fail(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise requests.exceptions.ConnectionError("shadow transport failure")

    monkeypatch.setattr(fetcher, "_fetch_stock_data", fail)

    with pytest.raises(RetryError) as caught:
        fetcher._fetch_raw_data("600519", "2026-09-01", "2026-09-02")

    assert attempts == 1
    root = unwrap_exception(caught.value)
    assert isinstance(root, requests.exceptions.ConnectionError)
    assert str(root) == "shadow transport failure"


def test_e03_undecorated_shadow_surface_exposes_original_exception(monkeypatch):
    fetcher = _fetcher()

    def fail(*_args, **_kwargs):
        raise requests.exceptions.ConnectionError("shadow transport failure")

    monkeypatch.setattr(fetcher, "_fetch_stock_data", fail)

    # Tenacity uses functools.wraps, so __wrapped__ is the production function
    # body without the retry controller. This is a Shadow comparison only.
    raw_body = EfinanceFetcher._fetch_raw_data.__wrapped__
    with pytest.raises(requests.exceptions.ConnectionError) as caught:
        raw_body(fetcher, "600519", "2026-09-01", "2026-09-02")

    assert str(caught.value) == "shadow transport failure"


def test_e03_non_retryable_semantic_error_is_not_wrapped():
    fetcher = _fetcher()

    # US is intentionally unsupported by Efinance. DataFetchError is not in
    # the retry predicate and therefore represents a semantic no-retry path.
    with pytest.raises(DataFetchError) as caught:
        fetcher._fetch_raw_data("AAPL", "2026-09-01", "2026-09-02")

    assert "不支持美股" in str(caught.value)
