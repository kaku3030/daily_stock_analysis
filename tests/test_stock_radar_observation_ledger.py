import pytest

from src.services.stock_radar_v2 import (
    LatencyTrace,
    Observation,
    ObservationLedger,
    SourceEventAtQuality,
    ValidationQueue,
)


def test_blocked_and_rejected_are_observable_and_replay_is_idempotent():
    ledger = ObservationLedger()
    blocked = Observation("b", "BLOCKED", portfolio_block_reasons=("DQ_UNKNOWN",))
    rejected = Observation("r", "REJECTED", canonical_permission="DENY")
    assert ledger.append(blocked) is blocked
    assert ledger.append(blocked) is blocked
    ledger.append(rejected)
    assert [item.detector_status for item in ledger.records()] == ["BLOCKED", "REJECTED"]


def test_unknown_source_event_does_not_create_catalyst_latency():
    trace = LatencyTrace(data_received_at=2, detected_at=5)
    assert trace.source_event_at_quality is SourceEventAtQuality.UNKNOWN
    assert trace.catalyst_latency() is None


def test_timestamp_order_and_latency_split():
    trace = LatencyTrace(
        data_received_at=2,
        knowledge_available_at=3,
        detected_at=5,
        strategy_decided_at=7,
        risk_decided_at=8,
        execution_ready_at=9,
    )
    assert trace.system_latency() == 3
    assert trace.policy_wait() == 4
    assert trace.execution_ready_at - trace.data_received_at > trace.system_latency()
    assert trace.system_latency() + trace.policy_wait() == trace.execution_ready_at - trace.data_received_at
    with pytest.raises(ValueError):
        LatencyTrace(data_received_at=4, detected_at=3)


def test_latency_segments_do_not_bridge_missing_timestamps():
    trace = LatencyTrace(data_received_at=2, strategy_decided_at=7, execution_ready_at=9)
    assert trace.system_latency() is None
    assert trace.policy_wait() is None


def test_source_event_at_quality_rejects_raw_strings():
    with pytest.raises(TypeError):
        LatencyTrace(source_event_at=1, source_event_at_quality="EXACT")


def test_serialization_is_stable_and_validation_queue_contract_is_unchanged():
    item = Observation("x", "UNKNOWN", evidence_ids=("e2", "e1"))
    assert item.serialize() == item.serialize()
    assert '"portfolio_block_reasons":[]' in item.serialize()
    with pytest.raises(ValueError):
        ValidationQueue().enqueue(signal_id="s", signal_type="t", signal_state="rejected")
