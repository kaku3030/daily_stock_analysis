import ast
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "realtime_monitor" / "server.py"
PRODUCTION_BASELINE = "ef27aec4d8f5cb89093399081fcd5e750473f99c"


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
    def __init__(self, time_key=None, *, empty=False):
        self.empty = empty
        self.iloc = _ILoc(time_key)


class _QuoteContext:
    def __init__(self, latest_bar_time, *, history_ret=0, history_empty=False):
        self.latest_bar_time = latest_bar_time
        self.history_ret = history_ret
        self.history_empty = history_empty

    def get_market_snapshot(self, symbols):
        assert len(symbols) == 1
        return 0, _Snapshot()

    def request_history_kline(self, symbol, *, start, end, ktype, max_count):
        assert symbol
        assert start <= end
        assert ktype
        assert max_count == 1000
        if self.history_ret != 0:
            return self.history_ret, "history_error", None
        return 0, _Bars(self.latest_bar_time, empty=self.history_empty), None


def _load_production_currentness_functions():
    """Execute the pinned production Currentness function bodies directly.

    This is an exact source-characterization seam: no Currentness rule is copied
    or re-expressed here. It intentionally mirrors the merged regression seam in
    tests/test_realtime_monitor_currentness_negative.py while avoiding optional
    runtime/SDK imports.
    """
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {
        "_us_session_phase",
        "_expected_latest_trading_date",
        "_data_health_check_core",
    }
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert {node.name for node in nodes} == wanted
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


def _run_existing(fixture):
    functions = _load_production_currentness_functions()
    return functions["_data_health_check_core"](
        _QuoteContext(
            fixture.get("latest_bar_time"),
            history_ret=fixture.get("history_ret", 0),
            history_empty=fixture.get("history_empty", False),
        ),
        fixture.get("symbol", "US.NVDA"),
        fixture["timeframe"],
        now_et=fixture["now_et"],
        trading_day_map=fixture["trading_day_map"],
    )


PROTECTED_FIELDS = (
    "ok",
    "status",
    "reason_codes",
    "latest_bar_time",
    "expected_latest_trading_date",
    "expected_trading_date_type",
    "session_phase",
    "now_et",
)


def _protected_projection(result):
    """Project only governed differential fields; add no new semantics."""
    return {field: result.get(field) for field in PROTECTED_FIELDS}


def _classify(existing, shadow_projection):
    """Bounded first-stage differential classification.

    The current Shadow side is intentionally only a protected-field projection.
    A future semantic candidate must replace this projection explicitly and earn
    its own review; this harness must not manufacture Currentness behavior.
    """
    return "MATCH" if _protected_projection(existing) == shadow_projection else "SHADOW_REGRESSION"


FIXTURES = [
    {
        "fixture_id": "US_PREOPEN_01",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-11 16:00:00",
        "now_et": datetime(2026, 9, 14, 8, 0),
        "trading_day_map": {"2026-09-11": "WHOLE", "2026-09-14": "WHOLE"},
        "expect": {
            "status": "CURRENTNESS_UNVERIFIED",
            "expected_latest_trading_date": "2026-09-11",
        },
    },
    {
        "fixture_id": "US_INTRADAY_15M_02",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-10 09:45:00",
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {"2026-09-10": "WHOLE"},
        "expect": {
            "ok": False,
            "status": "CURRENTNESS_UNVERIFIED",
            "reason_codes": ["INTRADAY_PROGRESS_NOT_PROVEN"],
        },
    },
    {
        "fixture_id": "US_INTRADAY_1H_03",
        "timeframe": "1h",
        "latest_bar_time": "2026-09-10 10:30:00",
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {"2026-09-10": "WHOLE"},
        "expect": {
            "ok": False,
            "status": "CURRENTNESS_UNVERIFIED",
            "reason_codes": ["INTRADAY_PROGRESS_NOT_PROVEN"],
        },
    },
    {
        "fixture_id": "US_DAILY_04",
        "timeframe": "1d",
        "latest_bar_time": "2026-09-10 16:00:00",
        "now_et": datetime(2026, 9, 10, 17, 0),
        "trading_day_map": {"2026-09-10": "WHOLE"},
        "expect": {
            "ok": True,
            "status": "OK",
            "reason_codes": ["LATEST_BAR_MATCHES_EXPECTED_SESSION"],
        },
    },
    {
        "fixture_id": "US_OLDER_05",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-09 16:00:00",
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {"2026-09-09": "WHOLE", "2026-09-10": "WHOLE"},
        "expect": {
            "ok": False,
            "status": "STALE_OR_MISALIGNED",
            "reason_codes": ["LATEST_BAR_BEFORE_EXPECTED_SESSION"],
        },
    },
    {
        "fixture_id": "US_AHEAD_06",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-11 09:45:00",
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {"2026-09-10": "WHOLE", "2026-09-11": "WHOLE"},
        "expect": {
            "ok": False,
            "status": "STALE_OR_MISALIGNED",
            "reason_codes": ["LATEST_BAR_AHEAD_OF_EXPECTED_SESSION"],
        },
    },
    {
        "fixture_id": "US_CALENDAR_EMPTY_07",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-10 09:45:00",
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {},
        "expect": {"ok": False},
    },
    {
        "fixture_id": "US_WEEKEND_HOLIDAY_08",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-04 16:00:00",
        "now_et": datetime(2026, 9, 7, 12, 0),
        "trading_day_map": {"2026-09-04": "WHOLE", "2026-09-08": "WHOLE"},
        "expect": {"expected_latest_trading_date": "2026-09-04"},
    },
    {
        "fixture_id": "US_DST_09",
        "timeframe": "15m",
        "latest_bar_time": "2026-03-09 09:45:00",
        "now_et": datetime(2026, 3, 9, 10, 0),
        "trading_day_map": {"2026-03-09": "WHOLE"},
        "expect": {
            "status": "CURRENTNESS_UNVERIFIED",
            "reason_codes": ["INTRADAY_PROGRESS_NOT_PROVEN"],
        },
    },
    {
        "fixture_id": "US_HALF_DAY_10",
        "timeframe": "15m",
        "latest_bar_time": "2026-11-27 10:00:00",
        "now_et": datetime(2026, 11, 27, 12, 0),
        "trading_day_map": {"2026-11-27": "MORNING"},
        "expect": {
            "ok": False,
            "status": "CURRENTNESS_UNVERIFIED",
            "expected_trading_date_type": "MORNING",
        },
    },
    {
        "fixture_id": "US_MISSING_INVALID_11",
        "timeframe": "15m",
        "latest_bar_time": None,
        "history_empty": True,
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {"2026-09-10": "WHOLE"},
        "expect": {"ok": False},
    },
]


@pytest.mark.parametrize("fixture", FIXTURES, ids=[item["fixture_id"] for item in FIXTURES])
def test_e01_existing_characterization_and_protected_projection(fixture):
    existing = _run_existing(fixture)

    for key, expected in fixture["expect"].items():
        assert existing.get(key) == expected, (
            fixture["fixture_id"], key, expected, existing.get(key), existing
        )

    shadow_projection = _protected_projection(existing)
    assert _classify(existing, shadow_projection) == "MATCH"

    # Protected fields stay explicit even when the production result represents
    # absence/UNKNOWN with None. The harness must not normalize them away.
    assert set(shadow_projection) == set(PROTECTED_FIELDS)
