from datetime import datetime, timezone

import pytest

from src.services.live_feed.commands import ProviderCommand, ProviderCommandType
from src.services.live_feed.controller import LiveFeedController
from src.services.live_feed.provider_worker_contracts import ProviderExecutionOutcome
from src.services.live_feed.provider_worker_executor_adapter import (
    AdapterBusyError,
    ProviderWorkerExecutorAdapter,
    dispatch_one_command,
)


class _LocalAdapter:
    def __init__(self, fail=False):
        self.fail = fail
        self.accepted = []

    def submit(self, command):
        if self.fail:
            raise AdapterBusyError("busy")
        self.accepted.append(command)


def _controller():
    from src.services.live_feed.commands import FakeProviderCommandExecutor
    return LiveFeedController(runtime_instance_id="r", provider_id="p", command_executor=FakeProviderCommandExecutor())


def test_a_local_rejection_retains_queue_head():
    controller = _controller()
    command = controller.submit_command(ProviderCommandType.DIAGNOSTIC)
    with pytest.raises(AdapterBusyError):
        dispatch_one_command(controller, _LocalAdapter(fail=True))
    assert controller.peek_command_for_worker() == command


def test_b_c_dispatches_one_exact_head_without_bulk_drain():
    controller = _controller()
    first = controller.submit_command(ProviderCommandType.DIAGNOSTIC)
    second = controller.submit_command(ProviderCommandType.CLOSE)
    adapter = _LocalAdapter()
    assert dispatch_one_command(controller, adapter)
    assert adapter.accepted == [first]
    assert controller.peek_command_for_worker() == second


def test_projection_only_success_is_true_and_sink_failure_is_diagnostic():
    received = []
    adapter = ProviderWorkerExecutorAdapter.__new__(ProviderWorkerExecutorAdapter)
    adapter._result_sink = lambda result: (_ for _ in ()).throw(RuntimeError("sink"))
    import threading
    adapter._diagnostic_lock = threading.Lock()
    adapter._diagnostics = []
    outcome = type("Outcome", (), {
        "command": ProviderCommand("r", "p", 1, 1, "c", ProviderCommandType.DIAGNOSTIC, datetime.now(timezone.utc)),
        "outcome": ProviderExecutionOutcome.TIMEOUT,
        "terminal_at_utc": datetime.now(timezone.utc),
        "provider_error_message": None,
        "diagnostic_reason": "timeout",
        "normalized_provider_payload": None,
    })()
    adapter._deliver(outcome)
    assert adapter.diagnostics and not received
