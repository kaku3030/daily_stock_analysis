"""Shadow evidence for Minimal Core E10 failure-taxonomy consolidation.

This test does not define a new production taxonomy and does not alter retry,
fallback, cooldown, routing, or provider ownership. It records both the shared
transport-classification seam and the current divergences between provider-local
classifiers so a future simplification cannot assume stronger equivalence than
we have actually proved.
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
        (RuntimeError("ProtocolError: connection broken by peer"), "remote_disconnect"),
        (requests.exceptions.Timeout("read timeout"), "timeout"),
        (requests.exceptions.ReadTimeout("read timed out"), "timeout"),
        (requests.exceptions.ConnectTimeout("connect timeout"), "timeout"),
        (RuntimeError("HTTP 429 Too Many Requests"), "rate_limit_or_anti_bot"),
        (RuntimeError("HTTP 403 Forbidden"), "rate_limit_or_anti_bot"),
        (RuntimeError("请求频率限制"), "rate_limit_or_anti_bot"),
        (requests.exceptions.RequestException("generic request failure"), "request_error"),
        (ValueError("unclassified provider failure"), "unknown_request_error"),
    ]

    for exc, expected in cases:
        assert _category_pair(exc) == (expected, expected)


def test_e10_chunked_encoding_is_a_current_classifier_divergence() -> None:
    exc = requests.exceptions.ChunkedEncodingError("chunkedencodingerror")

    # AkShare explicitly lists chunkedencodingerror in its remote-disconnect
    # keyword set. Efinance currently falls through to the generic
    # RequestException category. This is exactly the kind of edge that makes
    # a blind shared-helper deletion unsafe.
    assert _category_pair(exc) == ("request_error", "remote_disconnect")


def test_e10_classifier_messages_preserve_native_detail() -> None:
    marker = "provider-native-marker-7f2d"
    exc = requests.exceptions.RequestException(marker)

    ef_category, ef_detail = _classify_eastmoney_error(exc)
    ak_category, ak_detail = _classify_realtime_http_error(exc)

    assert ef_category == "request_error"
    assert ak_category == "request_error"
    assert marker in ef_detail
    assert marker in ak_detail


def test_e10_empty_exception_detail_is_a_current_diagnostic_divergence() -> None:
    exc = ValueError("")

    ef_category, ef_detail = _classify_eastmoney_error(exc)
    ak_category, ak_detail = _classify_realtime_http_error(exc)

    assert ef_category == "unknown_request_error"
    assert ak_category == "unknown_request_error"
    assert ef_detail == ""
    assert ak_detail == "ValueError"
