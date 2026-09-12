import ast
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "realtime_monitor" / "server.py"


class _KLType:
    K_1M = "K_1M"
    K_5M = "K_5M"
    K_15M = "K_15M"
    K_30M = "K_30M"
    K_60M = "K_60M"
    K_DAY = "K_DAY"


class _Snapshot:
    def __init__(self, update_time="2026-09-10 15:30:00"):
        self._update_time = update_time

    def to_dict(self, orient):
        assert orient == "records"
        return [{"update_time": self._update_time}]


class _ILoc:
    def __init__(self, time_key):
        self._time_key = time_key

    def __getitem__(self, index):
        assert index == -1
        return {"time_key": self._time_key}


class _Bars:
    def __init__(self, time_key):
        self.empty = False
        self.iloc = _ILoc(time_key)


class _QuoteContext:
    def __init__(self, latest_bar_time):
        self.latest_bar_time = latest_bar_time

    def get_market_snapshot(self, symbols):
        assert len(symbols) == 1
        return 0, _Snapshot()

    def request_history_kline(self, symbol, *, start, end, ktype, max_count):
        assert symbol
        assert start <= end
        assert ktype
        assert max_count == 1000
        return 0, _Bars(self.latest_bar_time), None


def _load_currentness_functions():
    """Load only the pure/currentness seam from server.py without optional SDK imports."""
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {
        "_us_session_phase",
        "_expected_latest_trading_date",
        "expected_completed_bar_end",
        "_data_health_check_core",
    }
    nodes = [
        node
        for node in tree.body
        if (
            isinstance(node, ast.FunctionDef) and node.name in wanted
        ) or (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_US_RTH_COMPLETED_BAR_ENDS" for target in node.targets)
        )
    ]
    assert {node.name for node in nodes if isinstance(node, ast.FunctionDef)} == wanted
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {
        "datetime": datetime,
        "timedelta": timedelta,
        "time": time,
        "KLType": _KLType,
        "RET_OK": 0,
        "_fetch_us_trading_days": lambda *args, **kwargs: None,
    }
    exec(compile(module, str(SERVER), "exec"), namespace)
    return namespace


def _check(*, timeframe, latest_bar_time, now_et, trading_day_map):
    functions = _load_currentness_functions()
    return functions["_data_health_check_core"](
        _QuoteContext(latest_bar_time),
        "US.NVDA",
        timeframe,
        now_et=now_et,
        trading_day_map=trading_day_map,
    )


def test_15m_same_date_alone_cannot_prove_currentness():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-10 09:45:00",
        now_et=datetime(2026, 9, 10, 15, 30),
        trading_day_map={"2026-09-10": "WHOLE"},
    )

    assert result["ok"] is False
    assert result["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["reason_codes"] == ["EXPECTED_COMPLETED_BOUNDARY_NOT_REACHED"]


def test_1h_same_date_alone_cannot_prove_currentness():
    result = _check(
        timeframe="1h",
        latest_bar_time="2026-09-10 10:30:00",
        now_et=datetime(2026, 9, 10, 15, 30),
        trading_day_map={"2026-09-10": "WHOLE"},
    )

    assert result["ok"] is False
    assert result["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["reason_codes"] == ["EXPECTED_COMPLETED_BOUNDARY_NOT_REACHED"]


def test_daily_same_expected_trading_date_keeps_existing_ok_semantics():
    result = _check(
        timeframe="1d",
        latest_bar_time="2026-09-10 16:00:00",
        now_et=datetime(2026, 9, 10, 17, 0),
        trading_day_map={"2026-09-10": "WHOLE"},
    )

    assert result["ok"] is True
    assert result["status"] == "OK"
    assert result["reason_codes"] == ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]


def test_premarket_previous_session_alignment_is_not_misclassified_stale():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-11 16:00:00",
        now_et=datetime(2026, 9, 14, 8, 0),
        trading_day_map={
            "2026-09-11": "WHOLE",
            "2026-09-14": "WHOLE",
        },
    )

    assert result["expected_latest_trading_date"] == "2026-09-11"
    assert result["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["status"] != "STALE_OR_MISALIGNED"


def test_older_than_expected_trading_date_remains_stale():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-09 16:00:00",
        now_et=datetime(2026, 9, 10, 15, 30),
        trading_day_map={"2026-09-09": "WHOLE", "2026-09-10": "WHOLE"},
    )

    assert result["ok"] is False
    assert result["status"] == "STALE_OR_MISALIGNED"


@pytest.mark.parametrize("timeframe, now, expected", [
    ("15m", datetime(2026, 9, 10, 9, 44), None),
    ("15m", datetime(2026, 9, 10, 10, 1), time(10, 0)),
    ("15m", datetime(2026, 9, 10, 16, 0), time(16, 0)),
    ("60m", datetime(2026, 9, 10, 15, 59), time(15, 30)),
    ("60m", datetime(2026, 9, 10, 16, 0), time(16, 0)),
])
def test_expected_completed_bar_end_uses_frozen_rth_grids(timeframe, now, expected):
    functions = _load_currentness_functions()
    assert functions["expected_completed_bar_end"](now, timeframe) == expected


def test_half_day_does_not_promote_positive_currentness():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-10 13:00:00",
        now_et=datetime(2026, 9, 10, 16, 0),
        trading_day_map={"2026-09-10": "HALF"},
    )
    assert result["status"] == "CURRENTNESS_UNVERIFIED"


def test_future_bar_date_remains_fail_closed():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-11 16:00:00",
        now_et=datetime(2026, 9, 10, 16, 0),
        trading_day_map={"2026-09-10": "WHOLE", "2026-09-11": "WHOLE"},
    )
    assert result["status"] == "STALE_OR_MISALIGNED"
    assert result["reason_codes"] == ["LATEST_BAR_AHEAD_OF_EXPECTED_SESSION"]


def test_ahead_of_expected_trading_date_remains_fail_closed():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-11 09:45:00",
        now_et=datetime(2026, 9, 10, 15, 30),
        trading_day_map={"2026-09-10": "WHOLE", "2026-09-11": "WHOLE"},
    )

    assert result["ok"] is False
    assert result["status"] == "STALE_OR_MISALIGNED"
    assert result["reason_codes"] == ["LATEST_BAR_AHEAD_OF_EXPECTED_SESSION"]


def test_non_whole_session_type_does_not_create_positive_intraday_boundary():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-11-27 10:00:00",
        now_et=datetime(2026, 11, 27, 12, 0),
        trading_day_map={"2026-11-27": "MORNING"},
    )

    assert result["ok"] is False
    assert result["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["expected_trading_date_type"] == "MORNING"


def test_15m_off_grid_timestamp_fails_closed():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-10 15:29:00",
        now_et=datetime(2026, 9, 10, 15, 31),
        trading_day_map={"2026-09-10": "WHOLE"},
    )
    assert result["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["reason_codes"] == ["TIMESTAMP_OFF_ADMITTED_GRID"]


def test_provider_bar_ahead_of_expected_completed_boundary_fails_closed():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-10 15:45:00",
        now_et=datetime(2026, 9, 10, 15, 31),
        trading_day_map={"2026-09-10": "WHOLE"},
    )
    assert result["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["reason_codes"] == ["PROVIDER_TIMESTAMP_AHEAD_OF_EXPECTED_BOUNDARY"]


def test_60m_after_close_never_expects_1630():
    functions = _load_currentness_functions()
    assert functions["expected_completed_bar_end"](
        datetime(2026, 9, 10, 16, 30), "60m"
    ) == time(16, 0)


def test_extended_hours_bar_data_is_not_authorized_by_after_hours_clock_phase():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-10 16:15:00",
        now_et=datetime(2026, 9, 10, 16, 20),
        trading_day_map={"2026-09-10": "WHOLE"},
    )
    assert result["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["reason_codes"] == ["TIMESTAMP_OFF_ADMITTED_GRID"]


def test_supported_futu_naive_time_key_shape_remains_accepted():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-10 15:30:00",
        now_et=datetime(2026, 9, 10, 15, 31),
        trading_day_map={"2026-09-10": "WHOLE"},
    )
    assert result["ok"] is True
    assert result["reason_codes"] == ["LATEST_COMPLETED_BOUNDARY_PROVEN"]


def test_unsupported_timestamp_shape_fails_closed():
    result = _check(
        timeframe="15m",
        latest_bar_time="2026-09-10T15:30:00Z",
        now_et=datetime(2026, 9, 10, 15, 31),
        trading_day_map={"2026-09-10": "WHOLE"},
    )
    assert result["status"] == "CURRENTNESS_UNVERIFIED"
    assert result["reason_codes"] == ["TIMESTAMP_FORMAT_OR_PROVENANCE_UNSUPPORTED"]
