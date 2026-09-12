"""Regression tests for the bundle-level Currentness aggregation fix.

get_primary_market_bundle_health() used to collapse every non-OK child
status (CURRENTNESS_UNVERIFIED, and every core error-shaped status) into a
single "STALE_OR_MISALIGNED" label. These tests pin the precedence
reduction that replaced that collapse:

    DATA_UNAVAILABLE-tier > STALE_OR_MISALIGNED > CURRENTNESS_UNVERIFIED > OK

_data_health_check_core() itself is not touched by the fix and is not
re-tested here -- see test_realtime_monitor_currentness_negative.py for its
own regression coverage. build_ai_invocation_plan() and
compare_analysis_states() are exercised directly (unmodified) to prove
their existing generic non-OK gates keep behaving identically once
CURRENTNESS_UNVERIFIED starts propagating distinctly.

realtime_monitor.server is never imported directly: its module scope pulls
in optional runtime SDKs (anthropic/openai/mcp/futu) that a CI test runner
need not install. Instead this mirrors the AST-extraction isolation pattern
already used by test_realtime_monitor_currentness_negative.py: parse the
source, pull out just the bundle-aggregation seam, and exec it into a
minimal namespace.
"""

import ast
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "realtime_monitor" / "server.py"

_WANTED_FUNCTIONS = {
    "clean_json_value",
    "_bundle_status_tier",
    "_reduce_bundle_status",
    "get_primary_market_bundle_health",
    "build_ai_invocation_plan",
    "compare_analysis_states",
}
_WANTED_ASSIGNMENTS = {"_BUNDLE_STATUS_TIER_RANK"}

# Names get_primary_market_bundle_health() calls out to but that this seam
# does not extract (they touch the quote-context SDK / disk / network).
# Pre-declared so monkeypatch.setattr(server, name, fake) has an existing
# attribute to replace in each test.
_EXTERNAL_DEPENDENCIES = (
    "get_primary_market_bundle",
    "get_quote_ctx",
    "_fetch_us_trading_days",
    "_us_eastern_now",
    "_data_health_check_core",
)


class _LoadedModule:
    """Thin attribute-style view over the exec() namespace dict.

    Must wrap the *same* dict object passed as `exec`'s globals (not a copy)
    so that monkeypatch.setattr(server, name, fake) actually changes what
    the extracted functions see when they look up that name as a global.
    """

    def __init__(self, namespace):
        object.__setattr__(self, "_namespace", namespace)

    def __getattr__(self, name):
        try:
            return self._namespace[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self._namespace[name] = value

    def __delattr__(self, name):
        del self._namespace[name]


def _load_bundle_functions():
    """Load only the bundle-aggregation seam from server.py, without the
    module's optional runtime SDK imports (anthropic/openai/mcp/futu)."""
    source = SERVER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _WANTED_FUNCTIONS:
            node.decorator_list = []
            nodes.append(node)
        elif (isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in _WANTED_ASSIGNMENTS):
            nodes.append(node)
    found_names = {
        node.name if isinstance(node, ast.FunctionDef) else node.targets[0].id
        for node in nodes
    }
    assert found_names == _WANTED_FUNCTIONS | _WANTED_ASSIGNMENTS, found_names
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "math": math,
        "json": json,
        "datetime": datetime,
        "timedelta": timedelta,
        **{name: None for name in _EXTERNAL_DEPENDENCIES},
    }
    exec(compile(module, str(SERVER_PATH), "exec"), namespace)
    return _LoadedModule(namespace)


server = _load_bundle_functions()


# ---------------------------------------------------------------------------
# Pure helper unit tests
# ---------------------------------------------------------------------------

def test_bundle_status_tier_passes_through_known_currentness_values():
    assert server._bundle_status_tier("OK") == "OK"
    assert server._bundle_status_tier("STALE_OR_MISALIGNED") == "STALE_OR_MISALIGNED"
    assert server._bundle_status_tier("CURRENTNESS_UNVERIFIED") == "CURRENTNESS_UNVERIFIED"


@pytest.mark.parametrize("raw_status", [
    "DATA_UNAVAILABLE",
    "SNAPSHOT_ERROR",
    "SNAPSHOT_EMPTY",
    "BAR_ERROR",
    "BAR_EMPTY",
    "UNSUPPORTED_TIMEFRAME",
    "CALENDAR_UNAVAILABLE",
    "SOME_FUTURE_UNKNOWN_STATUS",
])
def test_bundle_status_tier_buckets_error_shaped_and_unknown_statuses_as_unavailable(raw_status):
    assert server._bundle_status_tier(raw_status) == "DATA_UNAVAILABLE"


def test_reduce_bundle_status_precedence_order():
    assert server._reduce_bundle_status(["OK", "OK", "OK"]) == "OK"
    assert server._reduce_bundle_status(["OK", "CURRENTNESS_UNVERIFIED"]) == "CURRENTNESS_UNVERIFIED"
    assert server._reduce_bundle_status(
        ["STALE_OR_MISALIGNED", "CURRENTNESS_UNVERIFIED"]
    ) == "STALE_OR_MISALIGNED"
    assert server._reduce_bundle_status(
        ["DATA_UNAVAILABLE", "STALE_OR_MISALIGNED", "CURRENTNESS_UNVERIFIED", "OK"]
    ) == "DATA_UNAVAILABLE"


def test_reduce_bundle_status_empty_is_data_unavailable():
    assert server._reduce_bundle_status([]) == "DATA_UNAVAILABLE"


# ---------------------------------------------------------------------------
# get_primary_market_bundle_health() end-to-end aggregation, with the
# quote-context / bundle-fetch / core-authority calls monkeypatched so the
# test controls exactly what each child timeframe reports.
# ---------------------------------------------------------------------------

class _FakeQuoteCtx:
    def close(self):
        pass


def _bars(ok=True):
    return {"ok": ok, "data": [{"time_key": "2026-09-10 15:30:00"}]}


def _quote(ok=True):
    return {"ok": ok, "snapshot_time": "2026-09-10 15:30:00"}


def _core_result(status, reason_codes=None):
    result = {"ok": status == "OK", "status": status}
    if reason_codes is not None:
        result["reason_codes"] = reason_codes
    return result


def _install_common_mocks(monkeypatch, bundle_positions):
    monkeypatch.setattr(
        server, "get_primary_market_bundle",
        lambda count=60: {"ok": True, "positions": bundle_positions},
    )
    monkeypatch.setattr(server, "get_quote_ctx", lambda: _FakeQuoteCtx())
    monkeypatch.setattr(
        server, "_fetch_us_trading_days",
        lambda q, start_date, end_date: {"2026-09-10": "WHOLE"},
    )
    monkeypatch.setattr(
        server, "_us_eastern_now", lambda: datetime(2026, 9, 10, 15, 30)
    )


def _core_by_timeframe(mapping):
    """mapping: {(symbol, api_timeframe): core_result_dict}"""
    def fake_core(q, symbol, timeframe, now_et=None, trading_day_map=None,
                  calendar_unavailable=False):
        return mapping[(symbol, timeframe)]
    return fake_core


def test_regression_1_all_ok(monkeypatch):
    positions = {
        "US.NVDA": {
            "quote_summary": _quote(),
            "bars": {"daily": _bars(), "hourly": _bars(), "15m": _bars()},
        },
    }
    _install_common_mocks(monkeypatch, positions)
    monkeypatch.setattr(server, "_data_health_check_core", _core_by_timeframe({
        ("US.NVDA", "1d"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "1h"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "15m"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
    }))

    result = server.get_primary_market_bundle_health(count=60)

    assert result["ok"] is True
    assert result["health"]["US.NVDA"]["status"] == "OK"
    assert result["overall_status"] == "OK"


def test_regression_2_intraday_unverified_alone_does_not_become_stale(monkeypatch):
    positions = {
        "US.NVDA": {
            "quote_summary": _quote(),
            "bars": {"daily": _bars(), "hourly": _bars(), "15m": _bars()},
        },
    }
    _install_common_mocks(monkeypatch, positions)
    monkeypatch.setattr(server, "_data_health_check_core", _core_by_timeframe({
        ("US.NVDA", "1d"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "1h"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "15m"): _core_result("CURRENTNESS_UNVERIFIED", ["INTRADAY_PROGRESS_NOT_PROVEN"]),
    }))

    result = server.get_primary_market_bundle_health(count=60)

    assert result["health"]["US.NVDA"]["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["overall_status"] == "CURRENTNESS_UNVERIFIED"
    assert "INTRADAY_PROGRESS_NOT_PROVEN" in result["health"]["US.NVDA"]["reason_codes"]


def test_regression_3_real_staleness_outranks_unverified(monkeypatch):
    positions = {
        "US.NVDA": {
            "quote_summary": _quote(),
            "bars": {"daily": _bars(), "hourly": _bars(), "15m": _bars()},
        },
    }
    _install_common_mocks(monkeypatch, positions)
    monkeypatch.setattr(server, "_data_health_check_core", _core_by_timeframe({
        ("US.NVDA", "1d"): _core_result("STALE_OR_MISALIGNED", ["LATEST_BAR_BEFORE_EXPECTED_SESSION"]),
        ("US.NVDA", "1h"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "15m"): _core_result("CURRENTNESS_UNVERIFIED", ["INTRADAY_PROGRESS_NOT_PROVEN"]),
    }))

    result = server.get_primary_market_bundle_health(count=60)

    assert result["health"]["US.NVDA"]["status"] == "STALE_OR_MISALIGNED"
    assert result["overall_status"] == "STALE_OR_MISALIGNED"


def test_regression_4_missing_components_is_data_unavailable(monkeypatch):
    positions = {
        "US.NVDA": {
            "quote_summary": _quote(),
            "bars": {"daily": _bars(ok=False), "hourly": _bars(), "15m": _bars()},
        },
    }
    _install_common_mocks(monkeypatch, positions)
    monkeypatch.setattr(server, "_data_health_check_core", _core_by_timeframe({
        ("US.NVDA", "1h"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "15m"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
    }))

    result = server.get_primary_market_bundle_health(count=60)

    assert result["health"]["US.NVDA"]["status"] == "DATA_UNAVAILABLE"
    assert result["overall_status"] == "DATA_UNAVAILABLE"
    assert "BARS_UNAVAILABLE" in result["health"]["US.NVDA"]["reason_codes"]


@pytest.mark.parametrize("error_status", [
    "SNAPSHOT_ERROR", "SNAPSHOT_EMPTY", "BAR_ERROR", "BAR_EMPTY",
    "UNSUPPORTED_TIMEFRAME", "CALENDAR_UNAVAILABLE",
])
def test_regression_5_core_error_shaped_status_lands_in_unavailable_tier_not_stale(
    monkeypatch, error_status,
):
    positions = {
        "US.NVDA": {
            "quote_summary": _quote(),
            "bars": {"daily": _bars(), "hourly": _bars(), "15m": _bars()},
        },
    }
    _install_common_mocks(monkeypatch, positions)
    monkeypatch.setattr(server, "_data_health_check_core", _core_by_timeframe({
        ("US.NVDA", "1d"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "1h"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "15m"): _core_result(error_status),  # no native reason_codes
    }))

    result = server.get_primary_market_bundle_health(count=60)

    assert result["health"]["US.NVDA"]["status"] == "DATA_UNAVAILABLE"
    assert result["overall_status"] == "DATA_UNAVAILABLE"
    # regression 10: traceability preserved for the newly surfaced error tier
    assert error_status in result["health"]["US.NVDA"]["reason_codes"]


def test_regression_6_multi_symbol_unverified_plus_ok_is_overall_unverified(monkeypatch):
    positions = {
        "US.NVDA": {
            "quote_summary": _quote(),
            "bars": {"daily": _bars(), "hourly": _bars(), "15m": _bars()},
        },
        "US.AAPL": {
            "quote_summary": _quote(),
            "bars": {"daily": _bars(), "hourly": _bars(), "15m": _bars()},
        },
    }
    _install_common_mocks(monkeypatch, positions)
    monkeypatch.setattr(server, "_data_health_check_core", _core_by_timeframe({
        ("US.NVDA", "1d"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "1h"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "15m"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.AAPL", "1d"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.AAPL", "1h"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.AAPL", "15m"): _core_result("CURRENTNESS_UNVERIFIED", ["INTRADAY_PROGRESS_NOT_PROVEN"]),
    }))

    result = server.get_primary_market_bundle_health(count=60)

    assert result["health"]["US.NVDA"]["status"] == "OK"
    assert result["health"]["US.AAPL"]["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["overall_status"] == "CURRENTNESS_UNVERIFIED"


def test_regression_7_multi_symbol_unverified_plus_unavailable_is_overall_unavailable(monkeypatch):
    positions = {
        "US.NVDA": {
            "quote_summary": _quote(),
            "bars": {"daily": _bars(), "hourly": _bars(), "15m": _bars()},
        },
        "US.AAPL": {
            "quote_summary": _quote(ok=False),
            "bars": {"daily": _bars(), "hourly": _bars(), "15m": _bars()},
        },
    }
    _install_common_mocks(monkeypatch, positions)
    monkeypatch.setattr(server, "_data_health_check_core", _core_by_timeframe({
        ("US.NVDA", "1d"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "1h"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.NVDA", "15m"): _core_result("CURRENTNESS_UNVERIFIED", ["INTRADAY_PROGRESS_NOT_PROVEN"]),
        ("US.AAPL", "1d"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.AAPL", "1h"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
        ("US.AAPL", "15m"): _core_result("OK", ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]),
    }))

    result = server.get_primary_market_bundle_health(count=60)

    assert result["health"]["US.NVDA"]["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["health"]["US.AAPL"]["status"] == "DATA_UNAVAILABLE"
    assert result["overall_status"] == "DATA_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Downstream generic non-OK gates: unchanged behavior once
# CURRENTNESS_UNVERIFIED propagates distinctly (proves #6/#5 from the
# consumer audit stay fail-closed).
# ---------------------------------------------------------------------------

def _analysis_state_item(status):
    return {
        "data_health": {"status": status},
        "timeframe_state": {
            "daily": {"state": "NEUTRAL"},
            "hourly": {"state": "NEUTRAL"},
            "15m": {"state": "NEUTRAL"},
            "overall": "INDETERMINATE",
        },
    }


def test_regression_8_ai_invocation_plan_routes_unverified_to_data_quality_only():
    analysis_state = {
        "analysis_state": {"US.NVDA": _analysis_state_item("CURRENTNESS_UNVERIFIED")},
    }
    actionable_events = [{
        "symbol": "US.NVDA",
        "event_type": "DATA_HEALTH_CHANGED",
        "severity": "HIGH",
        "previous": "OK",
        "current": "CURRENTNESS_UNVERIFIED",
        "reason": "Data health changed from OK to CURRENTNESS_UNVERIFIED.",
        "timestamp": "2026-09-10T15:30:00",
    }]

    plan = server.build_ai_invocation_plan(actionable_events, analysis_state)

    assert plan["ok"] is True
    assert plan["should_invoke_ai"] is True
    assert plan["requests"][0]["analysis_mode"] == "DATA_QUALITY_ONLY"
    assert plan["requests"][0]["context_scope"] == "DATA_QUALITY_ONLY"


@pytest.mark.parametrize("non_ok_status", ["STALE_OR_MISALIGNED", "CURRENTNESS_UNVERIFIED"])
def test_regression_9_data_health_changed_event_severity_unchanged(non_ok_status):
    previous = {
        "ok": True,
        "snapshot_time": "2026-09-10T15:00:00",
        "analysis_state": {"US.NVDA": _analysis_state_item("OK")},
    }
    current = {
        "ok": True,
        "snapshot_time": "2026-09-10T15:15:00",
        "analysis_state": {"US.NVDA": _analysis_state_item(non_ok_status)},
    }

    result = server.compare_analysis_states(previous, current)

    assert result["ok"] is True
    health_events = [e for e in result["events"] if e["event_type"] == "DATA_HEALTH_CHANGED"]
    assert len(health_events) == 1
    assert health_events[0]["severity"] == "HIGH"
    assert health_events[0]["current"] == non_ok_status
