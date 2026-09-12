import ast
import json
import subprocess
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "realtime_monitor" / "server.py"
PRODUCTION_BASELINE = "ef27aec4d8f5cb89093399081fcd5e750473f99c"
ARTIFACT = ROOT / "tests" / "fixtures" / "e01_existing_vs_shadow_11row.json"


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
    """Execute function bodies from the executable, pinned source revision."""
    source = subprocess.check_output(
        ["git", "show", f"{PRODUCTION_BASELINE}:realtime_monitor/server.py"],
        cwd=ROOT, text=True, encoding="utf-8",
    )
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
    return {field: result.get(field) for field in PROTECTED_FIELDS}


def _run_shadow_semantic_reducer(fixture, existing):
    """Research-only reduced semantic candidate.

    The candidate deliberately does not own provider/history failure paths or
    calendar acquisition. It consumes explicit fixture evidence plus the two
    production pure helpers that already own US session/calendar interpretation.
    Cases outside that narrow reducer surface are SPEC_GAP rather than copied.

    Non-semantic transport/display metadata (latest_bar_time / now_et) is passed
    through from the characterized Existing result so this experiment measures
    the decision surface rather than inventing a second formatting owner.
    """
    if fixture.get("history_empty") or fixture.get("history_ret", 0) != 0:
        return "SPEC_GAP", None
    if not fixture.get("trading_day_map"):
        return "SPEC_GAP", None

    functions = _load_production_currentness_functions()
    now_et = fixture["now_et"]
    trading_day_map = fixture["trading_day_map"]
    session_phase = functions["_us_session_phase"](now_et)
    expected_date = functions["_expected_latest_trading_date"](
        now_et, trading_day_map.keys()
    )
    if expected_date is None:
        return "SPEC_GAP", None

    latest_bar_time = fixture.get("latest_bar_time")
    if not isinstance(latest_bar_time, str) or len(latest_bar_time) < 10:
        return "SPEC_GAP", None

    latest_date = latest_bar_time[:10]
    expected_type = trading_day_map.get(expected_date)

    if latest_date < expected_date:
        ok = False
        status = "STALE_OR_MISALIGNED"
        reason_codes = ["LATEST_BAR_BEFORE_EXPECTED_SESSION"]
    elif latest_date > expected_date:
        ok = False
        status = "STALE_OR_MISALIGNED"
        reason_codes = ["LATEST_BAR_AHEAD_OF_EXPECTED_SESSION"]
    elif fixture["timeframe"] in ("1d", "day"):
        ok = True
        status = "OK"
        reason_codes = ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]
    else:
        ok = False
        status = "CURRENTNESS_UNVERIFIED"
        reason_codes = ["INTRADAY_PROGRESS_NOT_PROVEN"]

    candidate = {
        "ok": ok,
        "status": status,
        "reason_codes": reason_codes,
        "latest_bar_time": existing.get("latest_bar_time"),
        "expected_latest_trading_date": expected_date,
        "expected_trading_date_type": expected_type,
        "session_phase": session_phase,
        "now_et": existing.get("now_et"),
    }
    return "MATCH" if _protected_projection(existing) == candidate else "SHADOW_REGRESSION", candidate


FIXTURES = [
    {
        "fixture_id": "US_PREOPEN_01",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-11 16:00:00",
        "now_et": datetime(2026, 9, 14, 8, 0),
        "trading_day_map": {"2026-09-11": "WHOLE", "2026-09-14": "WHOLE"},
        "expect": {"status": "CURRENTNESS_UNVERIFIED", "expected_latest_trading_date": "2026-09-11"},
        "candidate_classification": "MATCH",
    },
    {
        "fixture_id": "US_INTRADAY_15M_02",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-10 09:45:00",
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {"2026-09-10": "WHOLE"},
        "expect": {"ok": False, "status": "CURRENTNESS_UNVERIFIED", "reason_codes": ["INTRADAY_PROGRESS_NOT_PROVEN"]},
        "candidate_classification": "MATCH",
    },
    {
        "fixture_id": "US_INTRADAY_1H_03",
        "timeframe": "1h",
        "latest_bar_time": "2026-09-10 10:30:00",
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {"2026-09-10": "WHOLE"},
        "expect": {"ok": False, "status": "CURRENTNESS_UNVERIFIED", "reason_codes": ["INTRADAY_PROGRESS_NOT_PROVEN"]},
        "candidate_classification": "MATCH",
    },
    {
        "fixture_id": "US_DAILY_04",
        "timeframe": "1d",
        "latest_bar_time": "2026-09-10 16:00:00",
        "now_et": datetime(2026, 9, 10, 17, 0),
        "trading_day_map": {"2026-09-10": "WHOLE"},
        "expect": {"ok": True, "status": "OK", "reason_codes": ["LATEST_BAR_MATCHES_EXPECTED_SESSION"]},
        "candidate_classification": "MATCH",
    },
    {
        "fixture_id": "US_OLDER_05",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-09 16:00:00",
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {"2026-09-09": "WHOLE", "2026-09-10": "WHOLE"},
        "expect": {"ok": False, "status": "STALE_OR_MISALIGNED", "reason_codes": ["LATEST_BAR_BEFORE_EXPECTED_SESSION"]},
        "candidate_classification": "MATCH",
    },
    {
        "fixture_id": "US_AHEAD_06",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-11 09:45:00",
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {"2026-09-10": "WHOLE", "2026-09-11": "WHOLE"},
        "expect": {"ok": False, "status": "STALE_OR_MISALIGNED", "reason_codes": ["LATEST_BAR_AHEAD_OF_EXPECTED_SESSION"]},
        "candidate_classification": "MATCH",
    },
    {
        "fixture_id": "US_CALENDAR_EMPTY_07",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-10 09:45:00",
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {},
        "expect": {"ok": False},
        "candidate_classification": "SPEC_GAP",
    },
    {
        "fixture_id": "US_WEEKEND_HOLIDAY_08",
        "timeframe": "15m",
        "latest_bar_time": "2026-09-04 16:00:00",
        "now_et": datetime(2026, 9, 7, 12, 0),
        "trading_day_map": {"2026-09-04": "WHOLE", "2026-09-08": "WHOLE"},
        "expect": {"expected_latest_trading_date": "2026-09-04"},
        "candidate_classification": "MATCH",
    },
    {
        "fixture_id": "US_DST_09",
        "timeframe": "15m",
        "latest_bar_time": "2026-03-09 09:45:00",
        "now_et": datetime(2026, 3, 9, 10, 0),
        "trading_day_map": {"2026-03-09": "WHOLE"},
        "expect": {"status": "CURRENTNESS_UNVERIFIED", "reason_codes": ["INTRADAY_PROGRESS_NOT_PROVEN"]},
        "candidate_classification": "MATCH",
    },
    {
        "fixture_id": "US_HALF_DAY_10",
        "timeframe": "15m",
        "latest_bar_time": "2026-11-27 10:00:00",
        "now_et": datetime(2026, 11, 27, 12, 0),
        "trading_day_map": {"2026-11-27": "MORNING"},
        "expect": {"ok": False, "status": "CURRENTNESS_UNVERIFIED", "expected_trading_date_type": "MORNING"},
        "candidate_classification": "MATCH",
    },
    {
        "fixture_id": "US_MISSING_INVALID_11",
        "timeframe": "15m",
        "latest_bar_time": None,
        "history_empty": True,
        "now_et": datetime(2026, 9, 10, 15, 30),
        "trading_day_map": {"2026-09-10": "WHOLE"},
        "expect": {"ok": False},
        "candidate_classification": "SPEC_GAP",
    },
]


@pytest.mark.parametrize("fixture", FIXTURES, ids=[item["fixture_id"] for item in FIXTURES])
def test_e01_existing_characterization_and_reduced_shadow_candidate(fixture):
    existing = _run_existing(fixture)

    for key, expected in fixture["expect"].items():
        assert existing.get(key) == expected, (
            fixture["fixture_id"], key, expected, existing.get(key), existing
        )

    classification, candidate = _run_shadow_semantic_reducer(fixture, existing)
    assert classification == fixture["candidate_classification"]

    if classification == "MATCH":
        assert candidate == _protected_projection(existing)
        assert set(candidate) == set(PROTECTED_FIELDS)
    else:
        assert classification == "SPEC_GAP"
        assert candidate is None
    # Protected fields stay explicit even when the production result represents
    # absence/UNKNOWN with None. The harness must not normalize them away.
    assert set(candidate or _protected_projection(existing)) == set(PROTECTED_FIELDS)


def test_e01_independent_artifact_has_11_rows_and_evidence_accounting():
    rows = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert rows["source_revision"] == PRODUCTION_BASELINE
    assert rows["calendar_identity"] == "fixture.trading_day_map"
    assert rows["source_identity"] == "US.NVDA / fixture"
    assert len(rows["rows"]) == 11
    assert {row["classification"] for row in rows["rows"]} == {"MATCH", "SPEC_GAP"}
    assert sum(row["classification"] == "MATCH" for row in rows["rows"]) == 9
    assert sum(row["classification"] == "SPEC_GAP" for row in rows["rows"]) == 2
    assert rows["unknown_or_absence_rows"] == ["US_CALENDAR_EMPTY_07", "US_MISSING_INVALID_11"]


def test_e06_semantic_owner_read_set_is_measured():
    source = SERVER.read_text(encoding="utf-8")
    owner = "_data_health_check_core"
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == owner)
    reads = sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)})
    assert set(["now_et", "trading_day_map", "timeframe", "latest_bar_time"]).issubset(reads)
    evidence = json.loads(ARTIFACT.read_text(encoding="utf-8"))["e06"]
    assert evidence["semantic_owner"] == "realtime_monitor.server._data_health_check_core"
    assert evidence["read_set"] == ["latest_bar_time", "now_et", "timeframe", "trading_day_map"]
    assert evidence["net_complexity_result"] == "SMALLER"



def _load_candidate_currentness_functions():
    """Execute the candidate Currentness seam from the checked-out PR head."""
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
            and any(
                isinstance(target, ast.Name)
                and target.id == "_US_RTH_COMPLETED_BAR_ENDS"
                for target in node.targets
            )
        )
    ]
    assert {node.name for node in nodes if isinstance(node, ast.FunctionDef)} == wanted
    namespace = {
        "datetime": datetime,
        "timedelta": timedelta,
        "time": time,
        "KLType": _KLType,
        "RET_OK": 0,
        "_fetch_us_trading_days": lambda *args, **kwargs: None,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SERVER), "exec"), namespace)
    return namespace


def _run_candidate(fixture):
    functions = _load_candidate_currentness_functions()
    return functions["_data_health_check_core"](
        _QuoteContext(
            fixture.get("latest_bar_time"),
            history_ret=fixture.get("history_ret", 0),
            history_empty=fixture.get("history_empty", False),
        ),
        fixture.get("symbol", "US.NVDA"),
        fixture["timeframe"],
        now_et=fixture["now_et"],
        trading_day_map=fixture.get("trading_day_map"),
        calendar_unavailable=fixture.get("calendar_unavailable", False),
    )


POSITIVE_CURRENTNESS_FIXTURES = [
    ("K15_EXACT", "15m", "2026-09-10 15:30:00", datetime(2026, 9, 10, 15, 31), {"2026-09-10": "WHOLE"}, "OK", "LATEST_COMPLETED_BOUNDARY_PROVEN"),
    ("K15_ONE_BEHIND", "15m", "2026-09-10 15:15:00", datetime(2026, 9, 10, 15, 31), {"2026-09-10": "WHOLE"}, "CURRENTNESS_UNVERIFIED", "EXPECTED_COMPLETED_BOUNDARY_NOT_REACHED"),
    ("K15_SAME_DATE_STALE", "15m", "2026-09-10 09:45:00", datetime(2026, 9, 10, 15, 30), {"2026-09-10": "WHOLE"}, "CURRENTNESS_UNVERIFIED", "EXPECTED_COMPLETED_BOUNDARY_NOT_REACHED"),
    ("K15_OFF_GRID", "15m", "2026-09-10 15:29:00", datetime(2026, 9, 10, 15, 31), {"2026-09-10": "WHOLE"}, "CURRENTNESS_UNVERIFIED", "TIMESTAMP_OFF_ADMITTED_GRID"),
    ("K15_CLOSE", "15m", "2026-09-10 16:00:00", datetime(2026, 9, 10, 16, 5), {"2026-09-10": "WHOLE"}, "OK", "LATEST_COMPLETED_BOUNDARY_PROVEN"),
    ("K60_1530", "60m", "2026-09-10 15:30:00", datetime(2026, 9, 10, 15, 59), {"2026-09-10": "WHOLE"}, "OK", "LATEST_COMPLETED_BOUNDARY_PROVEN"),
    ("K60_CLOSE_STUB", "60m", "2026-09-10 16:00:00", datetime(2026, 9, 10, 16, 5), {"2026-09-10": "WHOLE"}, "OK", "LATEST_COMPLETED_BOUNDARY_PROVEN"),
    ("K60_MISSING_STUB", "60m", "2026-09-10 15:30:00", datetime(2026, 9, 10, 16, 5), {"2026-09-10": "WHOLE"}, "CURRENTNESS_UNVERIFIED", "EXPECTED_COMPLETED_BOUNDARY_NOT_REACHED"),
    ("K60_OFF_GRID", "60m", "2026-09-10 16:30:00", datetime(2026, 9, 10, 16, 35), {"2026-09-10": "WHOLE"}, "CURRENTNESS_UNVERIFIED", "TIMESTAMP_OFF_ADMITTED_GRID"),
    ("HALF_DAY", "15m", "2026-11-27 10:00:00", datetime(2026, 11, 27, 12, 0), {"2026-11-27": "MORNING"}, "CURRENTNESS_UNVERIFIED", "UNSUPPORTED_SESSION_SCOPE"),
    ("PREMARKET", "15m", "2026-09-09 16:00:00", datetime(2026, 9, 10, 8, 0), {"2026-09-09": "WHOLE", "2026-09-10": "WHOLE"}, "CURRENTNESS_UNVERIFIED", "UNSUPPORTED_SESSION_SCOPE"),
    ("EXTENDED_BAR", "15m", "2026-09-10 16:15:00", datetime(2026, 9, 10, 16, 20), {"2026-09-10": "WHOLE"}, "CURRENTNESS_UNVERIFIED", "TIMESTAMP_OFF_ADMITTED_GRID"),
    ("AHEAD_BOUNDARY", "15m", "2026-09-10 15:45:00", datetime(2026, 9, 10, 15, 31), {"2026-09-10": "WHOLE"}, "CURRENTNESS_UNVERIFIED", "PROVIDER_TIMESTAMP_AHEAD_OF_EXPECTED_BOUNDARY"),
    ("BAD_TIMESTAMP_SHAPE", "15m", "2026-09-10T15:30:00Z", datetime(2026, 9, 10, 15, 31), {"2026-09-10": "WHOLE"}, "CURRENTNESS_UNVERIFIED", "TIMESTAMP_FORMAT_OR_PROVENANCE_UNSUPPORTED"),
]


@pytest.mark.parametrize(
    "fixture_id,timeframe,latest_bar_time,now_et,trading_day_map,status,reason",
    POSITIVE_CURRENTNESS_FIXTURES,
    ids=[row[0] for row in POSITIVE_CURRENTNESS_FIXTURES],
)
def test_e01_positive_currentness_candidate_adversarial_matrix(
    fixture_id, timeframe, latest_bar_time, now_et, trading_day_map, status, reason
):
    result = _run_candidate({
        "fixture_id": fixture_id,
        "timeframe": timeframe,
        "latest_bar_time": latest_bar_time,
        "now_et": now_et,
        "trading_day_map": trading_day_map,
    })
    assert result["status"] == status
    assert result["ok"] is (status == "OK")
    assert result["reason_codes"] == [reason]


def test_e01_calendar_unavailable_stays_fail_closed():
    result = _run_candidate({
        "timeframe": "15m",
        "latest_bar_time": "2026-09-10 15:30:00",
        "now_et": datetime(2026, 9, 10, 15, 31),
        "trading_day_map": None,
        "calendar_unavailable": True,
    })
    assert result["ok"] is False
    assert result["status"] == "CALENDAR_UNAVAILABLE"
    assert result["reason_codes"] == ["TRADING_CALENDAR_UNAVAILABLE"]


def test_e01_k60_closing_stub_makes_1630_unreachable():
    functions = _load_candidate_currentness_functions()
    for minute in (0, 5, 30, 59):
        assert functions["expected_completed_bar_end"](
            datetime(2026, 9, 10, 16, minute), "60m"
        ) == time(16, 0)
