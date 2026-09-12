import pytest

from src.services.stock_radar_v2 import (
    LatencyTrace,
    Observation,
    ObservationLedger,
    SourceEventAtQuality,
    ValidationQueue,
    InterruptedReason,
    MarketExecutionConstraint,
    ShadowExecutionRecord,
    interrupted,
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


def test_interrupted_reasons_are_stable_and_not_thesis_or_price_invalidation():
    payload = interrupted(InterruptedReason.DATA_QUALITY_LOSS)
    assert payload == {"status": "INTERRUPTED", "reason": "DATA_QUALITY_LOSS"}
    assert "INVALID" not in payload["reason"]


def test_shadow_execution_requires_causal_time_and_rejects_same_bar_hindsight():
    with pytest.raises(ValueError):
        ShadowExecutionRecord("same", 10, 10, 100, 1, 1, False, "f1", "s1", 0,
                              decision_available_at=10, confirmed_at=10, bar_end_at=10)
    record = ShadowExecutionRecord("next", 10, 11, 101, 1, 1, False, "f1", "s1", 100,
                                   decision_available_at=10, confirmed_at=10, bar_end_at=10)
    assert record.simulated_fill_at == 11


def test_partial_fill_and_unknown_executable_time_remain_auditable():
    record = ShadowExecutionRecord(
        "partial", 10, None, None, 3, 5, True, "f1", "s1", None,
        constraints=(MarketExecutionConstraint.QUEUE_OR_LIQUIDITY,),
    )
    assert record.remainder_qty == 2
    assert record.to_dict()["simulated_fill_at"] is None
    assert record.to_dict()["constraints"] == ["QUEUE_OR_LIQUIDITY"]


def test_interrupted_failure_has_no_fill_and_replay_is_stable():
    record = ShadowExecutionRecord(
        "dq", 10, None, None, 0, 5, False, "f1", "s1", None,
        interrupted_reason=InterruptedReason.PROVIDER_OR_RUNTIME_FAILURE,
    )
    assert record.serialize() == record.serialize()
    assert record.interrupted_reason is InterruptedReason.PROVIDER_OR_RUNTIME_FAILURE
