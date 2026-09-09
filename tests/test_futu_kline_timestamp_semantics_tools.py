from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FUTU_TOOLS = ROOT / "tools" / "provider_semantics" / "futu"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, FUTU_TOOLS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyzer = _load("futu_kline_semantics_analyzer", "analyze_kline_timestamp_semantics.py")
live_probe = _load("futu_kline_timestamp_probe", "kline_timestamp_probe.py")
snapshot_probe = _load("futu_kline_snapshot_probe", "kline_snapshot_probe.py")


def _event(stream: str, key: str, observed_utc: str, close: float, seq: int):
    return {
        "stream_type": stream,
        "observed_at_utc": observed_utc,
        "monotonic_ns": seq,
        "raw_payload": {
            "time_key": key,
            "open": 100.0,
            "close": close,
            "high": max(100.0, close),
            "low": min(100.0, close),
            "volume": seq,
            "turnover": seq * 100.0,
        },
    }


def test_k60_rth_0930_end_boundary_candidate_is_mechanically_visible() -> None:
    events = [
        _event("K_60M", "2026-09-09 10:30:00", "2026-09-09T13:30:01+00:00", 101.0, 1),
        _event("K_60M", "2026-09-09 11:30:00", "2026-09-09T14:30:02+00:00", 102.0, 2),
    ]
    result = analyzer.analyze_live_events(events)["K_60M"]
    assert result["alignment_candidates"]["rth_0930_anchor_minute_30_matches_all"] is True
    assert result["alignment_candidates"]["clock_hour_anchor_minute_00_matches_all"] is False
    assert result["first_callback_minus_time_key_seconds_summary"]["median"] < -3500
    assert abs(result["first_callback_minus_candidate_period_start_if_key_is_end_seconds_summary"]["median"]) < 5
    assert result["sequence_observations"]["consecutive_key_gap_seconds"] == [3600.0]
    assert result["adjudication"] == "MECHANICAL_OBSERVATION_ONLY"


def test_k60_clock_hour_alignment_is_reported_without_semantic_promotion() -> None:
    events = [
        _event("K_60M", "2026-09-09 10:00:00", "2026-09-09T14:00:01+00:00", 101.0, 1),
        _event("K_60M", "2026-09-09 11:00:00", "2026-09-09T15:00:01+00:00", 102.0, 2),
    ]
    result = analyzer.analyze_live_events(events)["K_60M"]
    assert result["alignment_candidates"]["rth_0930_anchor_minute_30_matches_all"] is False
    assert result["alignment_candidates"]["clock_hour_anchor_minute_00_matches_all"] is True
    assert result["adjudication"] == "MECHANICAL_OBSERVATION_ONLY"


def test_repeated_same_key_material_change_is_forming_mutation_candidate() -> None:
    events = [
        _event("K_15M", "2026-09-09 10:00:00", "2026-09-09T13:45:01+00:00", 100.5, 1),
        _event("K_15M", "2026-09-09 10:00:00", "2026-09-09T13:50:01+00:00", 101.0, 2),
        _event("K_15M", "2026-09-09 10:00:00", "2026-09-09T13:55:01+00:00", 101.5, 3),
    ]
    result = analyzer.analyze_live_events(events)["K_15M"]
    assert result["forming_mutation_key_count"] == 1
    assert result["per_key"][0]["callback_count"] == 3
    assert result["per_key"][0]["distinct_material_payload_count"] == 3
    assert result["alignment_candidates"]["rth_0930_vs_clock_quarter_discriminating"] is False


def test_non_nominal_final_gap_is_reported_not_normalized_away() -> None:
    events = [
        _event("K_60M", "2025-11-28 10:30:00", "2025-11-28T14:30:01+00:00", 101.0, 1),
        _event("K_60M", "2025-11-28 11:30:00", "2025-11-28T15:30:01+00:00", 102.0, 2),
        _event("K_60M", "2025-11-28 12:30:00", "2025-11-28T16:30:01+00:00", 103.0, 3),
        _event("K_60M", "2025-11-28 13:00:00", "2025-11-28T17:00:01+00:00", 104.0, 4),
    ]
    sequence = analyzer.analyze_live_events(events)["K_60M"]["sequence_observations"]
    assert sequence["consecutive_key_gap_seconds"] == [3600.0, 3600.0, 1800.0]
    assert sequence["all_consecutive_gaps_equal_nominal_interval"] is False
    assert sequence["non_nominal_gap_seconds"] == [1800.0]
    assert sequence["last_time_key"].endswith("13:00:00-05:00")
    assert sequence["adjudication"] == "MECHANICAL_OBSERVATION_ONLY"


def test_history_same_key_mutation_is_only_a_candidate_not_auto_verified() -> None:
    document = {
        "observations": [
            {
                "requested_operation": "history",
                "requested_ktype": "K_15M",
                "result": {
                    "completed": True,
                    "timed_out": False,
                    "child_result": {
                        "status": "OK",
                        "raw_rows": [
                            {"time_key": "2026-09-09 10:00:00", "open": 100.0, "close": 100.5, "high": 101.0, "low": 99.5, "volume": 100, "turnover": 10000},
                        ],
                    },
                },
            },
            {
                "requested_operation": "history",
                "requested_ktype": "K_15M",
                "result": {
                    "completed": True,
                    "timed_out": False,
                    "child_result": {
                        "status": "OK",
                        "raw_rows": [
                            {"time_key": "2026-09-09 10:00:00", "open": 100.0, "close": 101.5, "high": 102.0, "low": 99.5, "volume": 150, "turnover": 15100},
                        ],
                    },
                },
            },
        ]
    }
    result = analyzer.analyze_snapshot_document(document)["history:K_15M"]
    assert result["same_time_key_material_mutation"]["2026-09-09 10:00:00"] is True
    assert result["forming_bar_evidence_candidate"] == "PRESENT_IF_HISTORY_SAME_KEY_MUTATES"
    assert result["adjudication"] == "MECHANICAL_OBSERVATION_ONLY"


def test_history_full_sequence_is_preserved_for_half_day_review() -> None:
    rows = [
        {"time_key": "2025-11-28 10:30:00", "open": 100, "close": 101, "high": 101, "low": 99, "volume": 1, "turnover": 100},
        {"time_key": "2025-11-28 11:30:00", "open": 101, "close": 102, "high": 102, "low": 100, "volume": 2, "turnover": 200},
        {"time_key": "2025-11-28 12:30:00", "open": 102, "close": 103, "high": 103, "low": 101, "volume": 3, "turnover": 300},
        {"time_key": "2025-11-28 13:00:00", "open": 103, "close": 104, "high": 104, "low": 102, "volume": 4, "turnover": 400},
    ]
    document = {
        "observations": [
            {
                "requested_operation": "history",
                "requested_ktype": "K_60M",
                "result": {
                    "completed": True,
                    "timed_out": False,
                    "child_result": {"status": "OK", "raw_rows": rows},
                },
            }
        ]
    }
    result = analyzer.analyze_snapshot_document(document)["history:K_60M"]
    assert result["sample_time_keys"] == [[row["time_key"] for row in rows]]
    sequence = result["sample_sequence_observations"][0]
    assert sequence["consecutive_key_gap_seconds"] == [3600.0, 3600.0, 1800.0]
    assert sequence["non_nominal_gap_seconds"] == [1800.0]
    assert result["adjudication"] == "MECHANICAL_OBSERVATION_ONLY"


def test_timed_out_snapshot_is_excluded_from_semantic_comparison() -> None:
    document = {
        "observations": [
            {
                "requested_operation": "current",
                "requested_ktype": "K_60M",
                "result": {
                    "completed": False,
                    "timed_out": True,
                    "child_result": None,
                },
            }
        ]
    }
    assert analyzer.analyze_snapshot_document(document) == {}


def test_snapshot_child_result_survives_incidental_sdk_stdout_noise() -> None:
    payload = {"status": "OK", "raw_rows": [{"time_key": "2026-09-09 10:30:00"}]}
    stdout = "OpenD connected\nprovider debug line\n" + snapshot_probe.RESULT_SENTINEL + snapshot_probe.json.dumps(payload)
    parsed, noise = snapshot_probe._parse_child_stdout(stdout)
    assert parsed == payload
    assert noise == "OpenD connected\nprovider debug line"


def test_last_sentinel_wins_if_sdk_or_wrapper_emits_multiple_structured_lines() -> None:
    first = snapshot_probe.RESULT_SENTINEL + snapshot_probe.json.dumps({"status": "EARLY"})
    second = snapshot_probe.RESULT_SENTINEL + snapshot_probe.json.dumps({"status": "OK"})
    parsed, noise = snapshot_probe._parse_child_stdout(first + "\nnoise\n" + second)
    assert parsed == {"status": "OK"}
    assert noise == "noise"


def test_capture_tools_parse_without_importing_futu_sdk() -> None:
    live = live_probe.parse_args(["--duration", "60", "--session", "RTH"])
    snap = snapshot_probe.parse_args(["--repeat", "1", "--session", "RTH"])
    assert live.duration == 60
    assert live.session == "RTH"
    assert snap.repeat == 1
    assert snap.session == "RTH"
    assert snap.operations == "both"
    assert snap.history_trade_date is None


def test_snapshot_probe_supports_history_only_explicit_trade_date() -> None:
    args = snapshot_probe.parse_args([
        "--operations", "history",
        "--history-trade-date", "2025-11-28",
        "--repeat", "1",
    ])
    assert args.operations == "history"
    assert args.history_trade_date == "2025-11-28"
    assert snapshot_probe._selected_operations(args.operations) == ("history",)


def test_snapshot_probe_rejects_malformed_history_trade_date() -> None:
    with pytest.raises(SystemExit):
        snapshot_probe.parse_args(["--history-trade-date", "11/28/2025"])


def test_live_probe_does_not_offer_sync_snapshot_interval_anymore() -> None:
    args = live_probe.parse_args(["--duration", "60"])
    assert not hasattr(args, "snapshot_interval")
