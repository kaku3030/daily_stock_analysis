from dataclasses import replace
from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest

from src.services.live_feed.commands import ProviderCommandType
from src.services.live_feed.provider_read_boundary_r1 import (
    HistoryKlineParams,
    ProviderReadRequest,
    ReadOperation,
    QuoteSnapshotParams,
)
from src.services.live_feed.provider_read_boundary_r2_s2 import FakeHistoryKlineAdapter
from src.services.live_feed.provider_worker_contracts import ProviderExecutionOutcome
from src.services.live_feed.provider_worker_supervisor import ProviderWorkerSupervisor
from tests.test_provider_worker_child_boundary import _config


def _fast_config():
    return replace(_config(), command_timeout_seconds={kind: 0.2 for kind in ProviderCommandType})


def _request(operation=ReadOperation.HISTORY_KLINE):
    params = (
        HistoryKlineParams("AAPL", "1d", date(2026, 1, 1), date(2026, 1, 2), 10)
        if operation is ReadOperation.HISTORY_KLINE
        else QuoteSnapshotParams(("AAPL",))
    )
    return ProviderReadRequest("r", "fake", "history-1", operation, datetime.now(timezone.utc), params)


def test_history_kline_success_preserves_transport_payload_only():
    sup = ProviderWorkerSupervisor(runtime_instance_id="r", provider_id="fake", config=_config())
    try:
        sup.start_generation()
        out = FakeHistoryKlineAdapter(sup).execute(_request(), bars={"rows": [{"timestamp": "stale-or-future"}]})
        assert out.execution_outcome is ProviderExecutionOutcome.SUCCEEDED
        assert out.normalized_provider_payload["rows"][0]["timestamp"] == "stale-or-future"
        assert "currentness" not in out.normalized_provider_payload
        assert "actionability" not in out.normalized_provider_payload
    finally:
        sup.shutdown()


@pytest.mark.parametrize(
    ("behavior", "expected"),
    [
        ("provider_rejected", ProviderExecutionOutcome.PROVIDER_REJECTED),
        ("exception", ProviderExecutionOutcome.PROVIDER_EXCEPTION),
        ("hang", ProviderExecutionOutcome.TIMEOUT),
        ("malformed_frame", ProviderExecutionOutcome.PROTOCOL_ERROR),
    ],
)
def test_history_kline_preserves_terminal_outcome_without_retry(behavior, expected):
    sup = ProviderWorkerSupervisor(runtime_instance_id="r", provider_id="fake", config=_fast_config())
    try:
        sup.start_generation()
        adapter = FakeHistoryKlineAdapter(sup)
        submit = Mock(wraps=sup.submit_command)
        sup.submit_command = submit
        out = adapter.execute(_request(), behavior=behavior)
        assert out.execution_outcome is expected
        assert submit.call_count == 1
    finally:
        sup.shutdown()


def test_history_kline_rejects_other_read_operation_before_child_dispatch():
    sup = ProviderWorkerSupervisor(runtime_instance_id="r", provider_id="fake", config=_config())
    try:
        with pytest.raises(ValueError, match="HISTORY_KLINE only"):
            FakeHistoryKlineAdapter(sup).execute(_request(ReadOperation.QUOTE_SNAPSHOT))
    finally:
        sup.shutdown()
