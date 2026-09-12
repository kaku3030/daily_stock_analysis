import copy

import pytest

from tools.research.e07_projection import E07CompressionIneligible, project_layer_b, protected_snapshot


def corpus():
    return [
        {"fixture_id": "provider-unknown", "provider": "akshare", "status": "UNKNOWN", "entitlement": "INDETERMINATE", "reason_codes": ["DATA_UNAVAILABLE"], "narrative": "x\nx"},
        {"fixture_id": "decision", "gate_result": "PASS", "candidate_status": "SHADOW", "reason_code": "CURRENT", "risk_flags": ["LOW"], "narrative": "ok"},
        {"fixture_id": "risk", "reason_codes": ["STALE_OR_MISALIGNED", "DATA_UNAVAILABLE"], "risk_flags": ["ENTITLEMENT"], "narrative": "diagnostic\ndiagnostic"},
        {"fixture_id": "portfolio", "portfolio": {"quantity": 2, "cost": 10, "available": 1, "frozen": 1}, "narrative": "must pass through"},
        {"fixture_id": "time", "event_time": "2026-09-12T09:30:00+08:00", "available_at": "2026-09-12T09:31:00+08:00", "provider_timestamp": "2026-09-12T09:30:02+08:00", "status": "CURRENT", "narrative": "ok"},
    ]


@pytest.mark.parametrize("payload", corpus())
def test_protected_fields_and_raw_reference_survive(payload):
    original = copy.deepcopy(payload)
    projected = project_layer_b(payload, raw_ref="sha256:fixture")
    assert projected["raw_ref"] == "sha256:fixture"
    view = projected.get("payload", {}) if projected["projection"] == "passthrough" else projected["protected"]
    assert all(view.get(key) == value for key, value in protected_snapshot(payload).items())
    assert payload == original


def test_portfolio_truth_is_passthrough():
    result = project_layer_b(corpus()[3], raw_ref="raw/portfolio.json")
    assert result["projection"] == "passthrough"


@pytest.mark.parametrize("payload", [{"provider": {"status": "UNKNOWN"}}, {"arbitrary": 1}])
def test_unsupported_or_ambiguous_schema_fails_loud(payload):
    with pytest.raises(E07CompressionIneligible):
        project_layer_b(payload, raw_ref="raw/x")
