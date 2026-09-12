from datetime import datetime, timezone

import pytest

from src.services.live_feed.provider_read_boundary_r1 import (
    ProviderReadRequest, QuoteSnapshotParams, ReadOperation,
)
from src.services.live_feed.provider_read_boundary_r2_s1 import FakeQuoteSnapshotAdapter
from src.services.live_feed.provider_worker_contracts import ProviderExecutionOutcome
from src.services.live_feed.provider_worker_supervisor import ProviderWorkerSupervisor
from tests.test_provider_worker_child_boundary import _config


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
