from datetime import datetime, timezone
from dataclasses import replace

import pytest

from src.services.live_feed.provider_read_boundary_r1 import (
    ProviderReadRequest, QuoteSnapshotParams, ReadOperation,
)
from src.services.live_feed.provider_read_boundary_r2_s1 import FakeQuoteSnapshotAdapter
from src.services.live_feed.provider_worker_contracts import ProviderExecutionOutcome
from src.services.live_feed.commands import ProviderCommandType
from src.services.live_feed.provider_worker_supervisor import ProviderWorkerSupervisor
from tests.test_provider_worker_child_boundary import _config


def _fast_config():
    return replace(
        _config(),
        command_timeout_seconds={kind: 0.2 for kind in ProviderCommandType},
    )


def _request(operation=ReadOperation.QUOTE_SNAPSHOT):
    params = QuoteSnapshotParams(("AAPL",)) if operation is ReadOperation.QUOTE_SNAPSHOT else object()
    return ProviderReadRequest("r", "fake", "read-1", operation, datetime.now(timezone.utc), params)


def test_quote_snapshot_uses_existing_child_seam_and_preserves_payload():
    sup = ProviderWorkerSupervisor(runtime_instance_id="r", provider_id="fake", config=_config())
    try:
        sup.start_generation()
        payload = {"symbol": "AAPL", "timestamp": "future-or-stale-or-missing"}
        out = FakeQuoteSnapshotAdapter(sup).execute(_request(), snapshot=payload)
        assert out.execution_outcome is ProviderExecutionOutcome.SUCCEEDED
        assert {k: out.normalized_provider_payload[k] for k in payload} == payload
        assert out.normalized_provider_payload["timestamp"] == payload["timestamp"]
        assert out.normalized_provider_payload["child_pid"] != __import__("os").getpid()
    finally:
        sup.shutdown()


def test_r2_s1_rejects_non_quote_before_execution():
    sup = ProviderWorkerSupervisor(runtime_instance_id="r", provider_id="fake", config=_config())
    try:
        with pytest.raises((TypeError, ValueError)):
            FakeQuoteSnapshotAdapter(sup).execute(_request(ReadOperation.HISTORY_KLINE))
    finally:
        sup.shutdown()


@pytest.mark.parametrize(
    ("behavior", "expected"),
    [
        ("provider_rejected", ProviderExecutionOutcome.PROVIDER_REJECTED),
        ("exception", ProviderExecutionOutcome.PROVIDER_EXCEPTION),
    ],
)
def test_quote_snapshot_preserves_provider_terminal_evidence(behavior, expected):
    sup = ProviderWorkerSupervisor(runtime_instance_id="r", provider_id="fake", config=_config())
    try:
        sup.start_generation()
        out = FakeQuoteSnapshotAdapter(sup).execute(_request(), behavior=behavior)
        assert out.execution_outcome is expected
        if behavior == "provider_rejected":
            assert out.provider_error_code == "SIMULATED_REJECT"
            assert out.provider_error_message == "simulated provider-style rejection"
        else:
            assert out.diagnostic_reason == "simulated child exception: boom"
    finally:
        sup.shutdown()


@pytest.mark.parametrize(
    "behavior",
    ["hang", "malformed_frame"],
)
def test_quote_snapshot_supervisor_owns_timeout_and_protocol_terminal_outcomes(behavior):
    sup = ProviderWorkerSupervisor(runtime_instance_id="r", provider_id="fake", config=_fast_config())
    try:
        sup.start_generation()
        out = FakeQuoteSnapshotAdapter(sup).execute(_request(), behavior=behavior)
        expected = (
            ProviderExecutionOutcome.TIMEOUT
            if behavior == "hang"
            else ProviderExecutionOutcome.PROTOCOL_ERROR
        )
        assert out.execution_outcome is expected
        assert out.execution_outcome not in {
            ProviderExecutionOutcome.PROVIDER_REJECTED,
            ProviderExecutionOutcome.PROVIDER_EXCEPTION,
        }
    finally:
        sup.shutdown()


@pytest.mark.parametrize("timestamp", [None, "stale", "future"])
def test_quote_snapshot_timestamp_is_payload_only(timestamp):
    sup = ProviderWorkerSupervisor(runtime_instance_id="r", provider_id="fake", config=_config())
    try:
        sup.start_generation()
        payload = {"symbol": "AAPL"}
        if timestamp is not None:
            payload["timestamp"] = timestamp
        out = FakeQuoteSnapshotAdapter(sup).execute(_request(), snapshot=payload)
        assert out.execution_outcome is ProviderExecutionOutcome.SUCCEEDED
        assert dict(out.normalized_provider_payload) == {
            "echo": "read-1", "child_pid": out.normalized_provider_payload["child_pid"], **payload,
        }
        assert "currentness" not in out.normalized_provider_payload
        assert "freshness" not in out.normalized_provider_payload
    finally:
        sup.shutdown()
