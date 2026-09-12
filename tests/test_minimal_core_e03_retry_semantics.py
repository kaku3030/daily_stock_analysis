"""Shadow evidence for Minimal Core E03 retry inventory.

These tests do not change production behavior. They pin the current observable
semantics of EfinanceFetcher._fetch_raw_data so a later simplification can be
compared against the existing Tenacity wrapper.
"""

import pytest
import requests
import pandas as pd
from tenacity import RetryError

from data_provider.base import DataFetchError, DataFetcherManager, unwrap_exception
from data_provider.akshare_fetcher import AkshareFetcher
from data_provider.base import RateLimitError
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


def test_e03_akshare_transport_retry_is_distinct_from_provider_fallback(monkeypatch):
    fetcher = AkshareFetcher(sleep_min=0.0, sleep_max=0.0)
    calls = []

    def eastmoney(*_args):
        calls.append("eastmoney")
        raise ConnectionError("eastmoney transient")

    def sina(*_args):
        calls.append("sina")
        return pd.DataFrame({"date": ["2026-09-01"], "close": [1.0]})

    monkeypatch.setattr(fetcher, "_fetch_stock_data_em", eastmoney)
    monkeypatch.setattr(fetcher, "_fetch_stock_data_sina", sina)
    monkeypatch.setattr(fetcher, "_fetch_stock_data_tx", lambda *_args: pd.DataFrame())

    result = fetcher._fetch_stock_data("600519", "2026-09-01", "2026-09-02")
    assert not result.empty
    assert calls == ["eastmoney", "sina"]


def test_e03_manager_retry_respects_attempt_and_total_budget(monkeypatch):
    class Config:
        fundamental_retry_max = 3

    manager = DataFetcherManager(fetchers=[])
    outcomes = iter([("first", "timeout", 400), ("second", "connection", 700), ("ok", None, 1)])
    calls = []

    monkeypatch.setattr(manager, "_get_fundamental_config", lambda: Config())

    def fake_timeout(task, remaining, task_name):
        calls.append((remaining, task_name))
        return next(outcomes)

    monkeypatch.setattr(manager, "_run_with_timeout", fake_timeout)
    result, error, elapsed = manager._run_with_retry(lambda: None, 1.0, "e03")
    assert (result, error, elapsed) == (None, "connection", 1100)
    assert len(calls) == 2
    assert calls[1][0] == pytest.approx(0.6)


def test_e03_manager_semantic_failures_are_not_promoted_by_retry(monkeypatch):
    class Config:
        fundamental_retry_max = 3

    manager = DataFetcherManager(fetchers=[])
    calls = 0
    monkeypatch.setattr(manager, "_get_fundamental_config", lambda: Config())

    def semantic_failure(task, remaining, task_name):
        nonlocal calls
        calls += 1
        return None, "AUTH_ERROR", 1

    monkeypatch.setattr(manager, "_run_with_timeout", semantic_failure)
    result, error, elapsed = manager._run_with_retry(lambda: None, 1.0, "auth")
    assert result is None
    assert error == "AUTH_ERROR"
    assert calls == 3
    assert elapsed == 3


@pytest.mark.parametrize(
    "failure",
    [
        requests.exceptions.ConnectionError("connection"),
        TimeoutError("timeout"),
        requests.exceptions.RequestException("request"),
        RateLimitError("rate limit"),
        DataFetchError("provider data failure"),
    ],
    ids=["connection", "timeout", "request", "rate-limit", "data-fetch"],
)
def test_e03_efinance_action_matrix_is_one_call_and_preserves_root(monkeypatch, failure):
    fetcher = _fetcher()
    attempts = 0

    def fail(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise failure

    monkeypatch.setattr(fetcher, "_fetch_stock_data", fail)
    started = __import__("time").monotonic()
    with pytest.raises(Exception) as caught:
        fetcher._fetch_raw_data("600519", "2026-09-01", "2026-09-02")

    assert attempts == 1
    assert __import__("time").monotonic() - started < 1.0
    if isinstance(failure, (ConnectionError, TimeoutError, requests.exceptions.RequestException)):
        assert isinstance(caught.value, RetryError)
        assert unwrap_exception(caught.value) is failure
    else:
        assert caught.value is failure
