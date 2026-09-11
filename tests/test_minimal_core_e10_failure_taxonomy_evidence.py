"""Shadow evidence for Minimal Core E10 failure-taxonomy consolidation.

This test does not define a new production taxonomy and does not alter retry,
fallback, cooldown, routing, or provider ownership. It only records whether two
existing provider-local HTTP failure classifiers currently agree on a narrow
set of shared transport categories.

If this evidence later supports consolidation, the production change still
requires a separate governed design/implementation review.
"""

from __future__ import annotations

import requests

from data_provider.akshare_fetcher import _classify_realtime_http_error
from data_provider.efinance_fetcher import _classify_eastmoney_error


def _category_pair(exc: Exception) -> tuple[str, str]:
    ef_category, _ = _classify_eastmoney_error(exc)
    ak_category, _ = _classify_realtime_http_error(exc)
    return ef_category, ak_category


def test_e10_shared_transport_categories_are_currently_equivalent() -> None:
    cases = [
        (ConnectionError("RemoteDisconnected: remote end closed connection without response"), "remote_disconnect"),
        (requests.exceptions.Timeout("read timeout"), "timeout"),
        (RuntimeError("HTTP 429 Too Many Requests"), "rate_limit_or_anti_bot"),
        (requests.exceptions.RequestException("generic request failure"), "request_error"),
        (ValueError("unclassified provider failure"), "unknown_request_error"),
    ]

    for exc, expected in cases:
        assert _category_pair(exc) == (expected, expected)


def test_e10_classifier_messages_preserve_native_detail() -> None:
    marker = "provider-native-marker-7f2d"
    exc = requests.exceptions.RequestException(marker)

    ef_category, ef_detail = _classify_eastmoney_error(exc)
    ak_category, ak_detail = _classify_realtime_http_error(exc)

    assert ef_category == "request_error"
    assert ak_category == "request_error"
    assert marker in ef_detail
    assert marker in ak_detail
