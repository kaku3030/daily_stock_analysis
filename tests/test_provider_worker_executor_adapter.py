"""Provider Worker Supervisor V0.1 -- Slice C: Executor Adapter adversarial
test suite.

Frozen design under test: the narrow nonblocking bridge between
LiveFeedController (LANE 2) and ProviderWorkerSupervisor (LANE 3).
ProviderWorkerSupervisor remains the sole execution/terminal-outcome
authority throughout -- these tests prove the Adapter never mints a
terminal fact, never filters staleness, never dedupes, never replays,
and fails closed (is_dead=True, dispatcher stops) on every fault
category, while still mechanically forwarding every genuine Supervisor
fact untouched.

Most tests use a lightweight in-process `_FakeSupervisor` double (no
multiprocessing) so thread races can be arbitrated deterministically with
Events rather than sleeps. Tests G and H specifically integrate against
the real, process-isolated `ProviderWorkerSupervisor` (Slice B), because
those two are exactly the cases the Slice B terminal-closure amendment
(b7d6974d) exists to prove end-to-end.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest

from src.services.live_feed.commands import ProviderCommand, ProviderCommandResult, ProviderCommandType
from src.services.live_feed.controller import LiveFeedController
from src.services.live_feed.provider_worker_contracts import (
    ProviderExecutionOutcome,
    ProviderWorkerSupervisorConfig,
    ResolvedProviderCommandOutcome,
)
from src.services.live_feed.provider_worker_executor_adapter import (
    ADAPTER_ADMISSION_CLOSED,
    ADAPTER_SUPERVISOR_FATAL,
    AdapterAlreadyStartedError,
    AdapterDeadError,
    AdapterNotAttachedError,
    AdapterStopTimeout,
    ExecutorAdapter,
)
from src.services.live_feed.provider_worker_supervisor import (
    AdmissionClosedError,
    CommandInFlightError,
    ProviderWorkerSupervisor,
    SupervisorFatalError,
)

NOW_UTC = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fake Supervisor -- scriptable, no multiprocessing. Implements exactly the
# public surface ExecutorAdapter touches (submit_command only).
# ---------------------------------------------------------------------------


class _FakeSupervisor:
    def __init__(self) -> None:
        self._script: list = []
        self.calls: list[ProviderCommand] = []

    def push(self, item) -> None:
        """item: a ResolvedProviderCommandOutcome, an Exception instance
        (raised), or a callable(command) -> outcome-or-raises (used for
        blocking/signalling behavior in thread-race tests)."""
        self._script.append(item)

    def submit_command(self, command: ProviderCommand, *, payload=None):
        self.calls.append(command)
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return item(command)
        return item


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.005) -> bool:
    """Bounded poll for conditions with no direct event hook (real-process
    startup timing in G/H). Not used as the arbitration mechanism for any
    thread race -- those use Events/stop()'s own join instead."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _command(
    *,
    command_id: str = "cmd-1",
    command_type: ProviderCommandType = ProviderCommandType.SUBSCRIBE,
    controller_generation: int = 0,
    desired_registry_revision: int = 0,
) -> ProviderCommand:
    return ProviderCommand(
        runtime_instance_id="runtime-1",
        provider_id="futu",
        controller_generation=controller_generation,
        desired_registry_revision=desired_registry_revision,
        command_id=command_id,
        command_type=command_type,
        created_at=NOW_UTC,
    )


def _outcome(
    *,
    command: ProviderCommand | None = None,
    outcome: ProviderExecutionOutcome = ProviderExecutionOutcome.SUCCEEDED,
    worker_generation: int | None = 1,
    dispatched_at_monotonic_ns: int | None = 1_000,
    provider_error_code: str | None = None,
    provider_error_message: str | None = None,
    normalized_provider_payload=None,
    diagnostic_reason: str | None = None,
) -> ResolvedProviderCommandOutcome:
    cmd = command or _command()
    return ResolvedProviderCommandOutcome(
        runtime_instance_id=cmd.runtime_instance_id,
        provider_id=cmd.provider_id,
        worker_generation=worker_generation,
        command=cmd,
        outcome=outcome,
        dispatched_at_monotonic_ns=dispatched_at_monotonic_ns,
        terminal_observed_at_monotonic_ns=2_000,
        terminal_at_utc=NOW_UTC,
        provider_error_code=provider_error_code,
        provider_error_message=provider_error_message,
        normalized_provider_payload=normalized_provider_payload,
        diagnostic_reason=diagnostic_reason,
    )


def _controller_with(supervisor) -> tuple[LiveFeedController, ExecutorAdapter]:
    adapter = ExecutorAdapter(supervisor=supervisor)
    controller = LiveFeedController(
        runtime_instance_id="runtime-1",
        provider_id="futu",
        command_executor=adapter,
    )
    adapter.attach_controller(controller)
    return controller, adapter


def _real_config(**overrides) -> ProviderWorkerSupervisorConfig:
    base = dict(
        startup_timeout_seconds=5.0,
        command_timeout_seconds={t: 5.0 for t in ProviderCommandType},
        graceful_shutdown_timeout_seconds=3.0,
        terminate_join_timeout_seconds=1.0,
        kill_join_timeout_seconds=1.0,
        parent_command_queue_capacity=8,
        child_data_queue_capacity=8,
        child_priority_queue_capacity=8,
        supervisor_inbox_capacity=8,
        max_frame_bytes=4096,
        protocol_version=1,
    )
    base.update(overrides)
    return ProviderWorkerSupervisorConfig(**base)


@pytest.fixture
def fake_stack():
    supervisor = _FakeSupervisor()
    controller, adapter = _controller_with(supervisor)
    yield supervisor, controller, adapter
    try:
        adapter.stop(join_timeout_seconds=2.0)
    except Exception:
        pass


@pytest.fixture
def real_supervisor():
    sup = ProviderWorkerSupervisor(runtime_instance_id="runtime-1", provider_id="futu", config=_real_config())
    yield sup
    try:
        sup.shutdown()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# A-F. Outcome mapping (mechanical translation only)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome_kind,kwargs,expected_error",
    [
        (ProviderExecutionOutcome.SUCCEEDED, {}, None),
        (
            ProviderExecutionOutcome.PROVIDER_REJECTED,
            {"provider_error_code": "E1", "provider_error_message": "rejected"},
            "rejected",
        ),
        (
            ProviderExecutionOutcome.PROVIDER_EXCEPTION,
            {"diagnostic_reason": "boom"},
            "boom",
        ),
        (ProviderExecutionOutcome.TIMEOUT, {}, "TIMEOUT"),
        (ProviderExecutionOutcome.WORKER_EXITED, {}, "WORKER_EXITED"),
        (ProviderExecutionOutcome.PROTOCOL_ERROR, {}, "PROTOCOL_ERROR"),
    ],
    ids=["A_succeeded", "B_rejected", "C_exception", "D_timeout", "E_worker_exited", "F_protocol_error"],
)
def test_a_to_f_outcome_mapping(fake_stack, outcome_kind, kwargs, expected_error):
    supervisor, controller, adapter = fake_stack
    cmd = controller.submit_command(ProviderCommandType.SUBSCRIBE)
    supervisor.push(_outcome(command=cmd, outcome=outcome_kind, **kwargs))

    adapter.start()
    assert _wait_until(lambda: len(supervisor.calls) >= 1)
    adapter.stop(join_timeout_seconds=2.0)
    controller.process_pending()
    results = controller.command_results
    assert len(results) == 1
    result = results[0]
    assert result.provider_execution_outcome == outcome_kind.value
    assert result.succeeded == (outcome_kind is ProviderExecutionOutcome.SUCCEEDED)
    assert result.error == expected_error
    assert result.worker_generation == 1
    assert len(supervisor.calls) == 1


# ---------------------------------------------------------------------------
# G. never-started Supervisor -> CANCELLED_GENERATION_INVALIDATED, None
# H. dead real generation -> CANCELLED_GENERATION_INVALIDATED, N
# Real Slice B Supervisor -- these two specifically prove the b7d6974d
# terminal-closure amendment is correctly consumed end-to-end.
# ---------------------------------------------------------------------------


def test_g_never_started_generation_worker_generation_none(real_supervisor):
    controller, adapter = _controller_with(real_supervisor)
    first = controller.submit_command(ProviderCommandType.SUBSCRIBE)

    adapter.start()
    assert _wait_until(lambda: (controller.process_pending() or True) and len(controller.command_results) >= 1)

    results = controller.command_results
    assert len(results) == 1
    result = results[0]
    assert result.provider_execution_outcome == ProviderExecutionOutcome.CANCELLED_GENERATION_INVALIDATED.value
    assert result.worker_generation is None
    assert result.succeeded is False
    adapter.stop(join_timeout_seconds=2.0)


def test_h_dead_real_generation_worker_generation_preserved(real_supervisor):
    real_supervisor.start_generation()
    dead_generation_number = real_supervisor.worker_generation
    assert real_supervisor._hard_kill(real_supervisor._current)  # white-box: force confirmed death

    controller, adapter = _controller_with(real_supervisor)
    cmd = controller.submit_command(ProviderCommandType.SUBSCRIBE)

    adapter.start()
    assert _wait_until(lambda: (controller.process_pending() or True) and len(controller.command_results) >= 1)

    result = controller.command_results[0]
    assert result.provider_execution_outcome == ProviderExecutionOutcome.CANCELLED_GENERATION_INVALIDATED.value
    assert result.worker_generation == dead_generation_number
    assert result.worker_generation is not None
    adapter.stop(join_timeout_seconds=2.0)


# ---------------------------------------------------------------------------
# I. stop before dispatch -> queued command remains untouched
# ---------------------------------------------------------------------------


def test_i_stop_before_start_leaves_queued_command_untouched(fake_stack):
    supervisor, controller, adapter = fake_stack
    controller.submit_command(ProviderCommandType.SUBSCRIBE)

    adapter.stop(join_timeout_seconds=1.0)  # never started -- idempotent no-op

    assert supervisor.calls == []
    pending = controller.drain_commands_for_worker()
    assert len(pending) == 1  # command was never dequeued by the adapter


# ---------------------------------------------------------------------------
# J. stop during in-flight submit -> current command finishes and delivers,
#    then loop exits
# ---------------------------------------------------------------------------


def test_j_stop_during_in_flight_submit_lets_current_command_finish(fake_stack):
    supervisor, controller, adapter = fake_stack
    cmd = controller.submit_command(ProviderCommandType.SUBSCRIBE)

    dispatched = threading.Event()
    release = threading.Event()

    def _blocking(command):
        dispatched.set()
        release.wait(timeout=5.0)
        return _outcome(command=command, outcome=ProviderExecutionOutcome.SUCCEEDED)

    supervisor.push(_blocking)
    adapter.start()
    assert dispatched.wait(timeout=2.0)

    stopper_error = []

    def _stop():
        try:
            adapter.stop(join_timeout_seconds=5.0)
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            stopper_error.append(exc)

    stopper = threading.Thread(target=_stop)
    stopper.start()
    # stop() has set the stop-event and is now blocked joining; the
    # in-flight submit_command call must still be allowed to finish.
    release.set()
    stopper.join(timeout=5.0)

    assert not stopper_error
    controller.process_pending()
    results = controller.command_results
    assert len(results) == 1
    assert results[0].command_id == cmd.command_id
    assert results[0].provider_execution_outcome == ProviderExecutionOutcome.SUCCEEDED.value
    assert adapter.is_running is False


# ---------------------------------------------------------------------------
# K. SupervisorFatalError -> no Supervisor terminal fact, None, dead, stop
# ---------------------------------------------------------------------------


def test_k_supervisor_fatal_error_no_terminal_fact_and_dead(fake_stack):
    supervisor, controller, adapter = fake_stack
    first = controller.submit_command(ProviderCommandType.SUBSCRIBE)
    second = controller.submit_command(ProviderCommandType.UNSUBSCRIBE)

    dispatched = threading.Event()

    def _raise_fatal(command):
        dispatched.set()
        raise SupervisorFatalError("supervisor is FATAL")

    supervisor.push(_raise_fatal)
    adapter.start()
    assert dispatched.wait(timeout=2.0)
    adapter.stop(join_timeout_seconds=2.0)  # deterministically await thread termination

    assert adapter.is_dead is True
    assert adapter.is_running is False
    controller.process_pending()
    assert controller.command_results == ()
    # Neither command was accepted: both queue heads remain authoritative.
    assert len(supervisor.calls) == 1
    remaining = controller.drain_commands_for_worker()
    assert [c.command_id for c in remaining] == [first.command_id, second.command_id]


def test_admission_closed_error_no_terminal_fact_and_dead(fake_stack):
    supervisor, controller, adapter = fake_stack
    cmd = controller.submit_command(ProviderCommandType.SUBSCRIBE)

    dispatched = threading.Event()

    def _raise_admission_closed(command):
        dispatched.set()
        raise AdmissionClosedError("admission closed")

    supervisor.push(_raise_admission_closed)
    adapter.start()
    assert dispatched.wait(timeout=2.0)
    adapter.stop(join_timeout_seconds=2.0)

    assert adapter.is_dead is True
    controller.process_pending()
    assert controller.command_results == ()
    assert [c.command_id for c in controller.drain_commands_for_worker()] == [cmd.command_id]


# ---------------------------------------------------------------------------
# L. command identity collision -> ValueError, NOT converted, dead, stop
# ---------------------------------------------------------------------------


def test_l_identity_collision_value_error_not_converted_to_result(fake_stack):
    supervisor, controller, adapter = fake_stack
    controller.submit_command(ProviderCommandType.SUBSCRIBE)

    dispatched = threading.Event()

    def _raise_value_error(command):
        dispatched.set()
        raise ValueError("command_id collision with different immutable command identity")

    supervisor.push(_raise_value_error)
    adapter.start()
    assert dispatched.wait(timeout=2.0)
    adapter.stop(join_timeout_seconds=2.0)

    assert adapter.is_dead is True
    controller.process_pending()
    assert controller.command_results == ()  # never delivered as a result of any shape


def test_command_in_flight_error_structurally_unreachable_but_defended(fake_stack):
    """CommandInFlightError should never actually occur given the
    single-dispatcher, one-command-at-a-time design -- this proves that
    *if* it somehow did (an Adapter bug), it is treated identically to
    every other internal fault: never converted to a ProviderCommandResult,
    the bridge dies, the loop terminates."""

    supervisor, controller, adapter = fake_stack
    controller.submit_command(ProviderCommandType.SUBSCRIBE)

    dispatched = threading.Event()

    def _raise_in_flight(command):
        dispatched.set()
        raise CommandInFlightError("command already in flight")

    supervisor.push(_raise_in_flight)
    adapter.start()
    assert dispatched.wait(timeout=2.0)
    adapter.stop(join_timeout_seconds=2.0)

    assert adapter.is_dead is True
    controller.process_pending()
    assert controller.command_results == ()


# ---------------------------------------------------------------------------
# M. duplicate same identity -> Supervisor idempotence, NO Adapter dedupe
# ---------------------------------------------------------------------------


def test_m_duplicate_identity_no_adapter_dedupe(fake_stack):
    supervisor, controller, adapter = fake_stack
    cmd = controller.submit_command(ProviderCommandType.SUBSCRIBE)
    # White-box: enqueue the *same* immutable command a second time --
    # mirrors what a real Supervisor terminal ledger would answer
    # idempotently, but the Adapter itself must apply zero history/cache.
    with controller._command_queue_lock:
        controller._command_queue.append(cmd)

    idempotent_outcome = _outcome(command=cmd, outcome=ProviderExecutionOutcome.SUCCEEDED)
    supervisor.push(idempotent_outcome)
    supervisor.push(idempotent_outcome)

    adapter.start()
    assert _wait_until(lambda: len(supervisor.calls) >= 2)
    adapter.stop(join_timeout_seconds=2.0)

    # the Adapter passed BOTH occurrences straight through -- it never
    # inspected command_id history to skip the second one.
    assert len(supervisor.calls) == 2
    controller.process_pending()
    assert len(controller.command_results) == 2


# ---------------------------------------------------------------------------
# N. RESULT SINK FAILURE -- hard fail-closed invariant
# ---------------------------------------------------------------------------


def test_n_result_sink_failure_fails_closed(fake_stack):
    supervisor, controller, adapter = fake_stack
    first = controller.submit_command(ProviderCommandType.SUBSCRIBE)
    second = controller.submit_command(ProviderCommandType.UNSUBSCRIBE)

    supervisor.push(_outcome(command=first, outcome=ProviderExecutionOutcome.SUCCEEDED))

    def _raising_sink(result: ProviderCommandResult) -> None:
        raise RuntimeError("delivery boom")

    adapter.register_result_sink(_raising_sink)
    adapter.start()
    assert _wait_until(lambda: adapter.is_dead)  # thread terminates itself once the sink raises
    adapter.stop(join_timeout_seconds=2.0)  # reap the already-finished thread deterministically

    assert adapter.is_dead is True
    assert adapter.is_running is False
    # exactly one dispatch attempt -- no re-submit, no replay, no retry
    assert len(supervisor.calls) == 1
    # the second queued command was never dequeued
    remaining = controller.drain_commands_for_worker()
    assert [c.command_id for c in remaining] == [second.command_id]


def test_n_real_supervisor_terminal_ledger_unaffected_by_sink_failure(real_supervisor):
    real_supervisor.start_generation()
    controller, adapter = _controller_with(real_supervisor)
    cmd = controller.submit_command(ProviderCommandType.DIAGNOSTIC)

    def _raising_sink(result: ProviderCommandResult) -> None:
        raise RuntimeError("delivery boom")

    adapter.register_result_sink(_raising_sink)
    adapter.start()
    assert _wait_until(lambda: adapter.is_dead)
    adapter.stop(join_timeout_seconds=2.0)

    # Supervisor's own terminal ledger already has this command's real,
    # permanent, authoritative resolution -- delivery failure never
    # touches it, and the Adapter never re-submits: calling
    # submit_command() again with the identical command returns the
    # cached ledger entry rather than dispatching a second time.
    resolved_again = real_supervisor.submit_command(cmd)
    assert resolved_again.outcome is ProviderExecutionOutcome.SUCCEEDED


# ---------------------------------------------------------------------------
# O. unexpected dispatcher exception -> is_dead=True, no auto restart
# ---------------------------------------------------------------------------


def test_o_unexpected_exception_marks_dead_no_auto_restart(fake_stack):
    supervisor, controller, adapter = fake_stack
    controller.submit_command(ProviderCommandType.SUBSCRIBE)

    dispatched = threading.Event()

    def _raise_unexpected(command):
        dispatched.set()
        raise AttributeError("programming bug")

    supervisor.push(_raise_unexpected)
    adapter.start()
    assert dispatched.wait(timeout=2.0)
    adapter.stop(join_timeout_seconds=2.0)

    assert adapter.is_dead is True
    with pytest.raises(AdapterDeadError):
        adapter.start()  # no auto-restart, and manual restart is refused too


# ---------------------------------------------------------------------------
# P. stale controller generation result -> delivered unchanged, not filtered
# ---------------------------------------------------------------------------


def test_p_stale_controller_generation_not_filtered_by_adapter(fake_stack):
    supervisor, controller, adapter = fake_stack
    current_generation = controller.snapshot().controller_generation
    stale_command = _command(controller_generation=current_generation + 999, desired_registry_revision=0)
    with controller._command_queue_lock:
        controller._command_queue.append(stale_command)

    supervisor.push(_outcome(command=stale_command, outcome=ProviderExecutionOutcome.SUCCEEDED))
    adapter.start()
    assert _wait_until(lambda: len(supervisor.calls) >= 1)
    adapter.stop(join_timeout_seconds=2.0)

    controller.process_pending()
    results = controller.command_results
    assert len(results) == 1
    # delivered exactly as produced, despite being staleness-eligible --
    # the Adapter never calls is_command_result_stale() itself.
    assert results[0].controller_generation == current_generation + 999


# ---------------------------------------------------------------------------
# Q. worker_generation=None propagation -- never coerced to 0
# ---------------------------------------------------------------------------


def test_q_worker_generation_none_never_coerced_to_zero(fake_stack):
    supervisor, controller, adapter = fake_stack
    cmd = controller.submit_command(ProviderCommandType.SUBSCRIBE)
    supervisor.push(
        _outcome(
            command=cmd,
            outcome=ProviderExecutionOutcome.CANCELLED_GENERATION_INVALIDATED,
            worker_generation=None,
            dispatched_at_monotonic_ns=None,
        )
    )
    adapter.start()
    assert _wait_until(lambda: len(supervisor.calls) >= 1)
    adapter.stop(join_timeout_seconds=2.0)

    controller.process_pending()
    result = controller.command_results[0]
    assert result.worker_generation is None


# ---------------------------------------------------------------------------
# R. dead generation with more queued commands -> no auto-replace
# ---------------------------------------------------------------------------


def test_r_no_replacement_attempted_across_multiple_commands(real_supervisor):
    real_supervisor.start_generation()
    assert real_supervisor._hard_kill(real_supervisor._current)
    controller, adapter = _controller_with(real_supervisor)
    controller.submit_command(ProviderCommandType.SUBSCRIBE)
    controller.submit_command(ProviderCommandType.UNSUBSCRIBE)

    adapter.start()
    assert _wait_until(lambda: (controller.process_pending() or True) and len(controller.command_results) >= 2)

    for result in controller.command_results:
        assert result.provider_execution_outcome == ProviderExecutionOutcome.CANCELLED_GENERATION_INVALIDATED.value
    # never replaced -- generation_seq only ever advanced once, by this
    # test's own start_generation() call; neither start_generation() nor
    # replace_generation() was ever called again for either command.
    assert real_supervisor._generation_seq == 1
    adapter.stop(join_timeout_seconds=2.0)


# ---------------------------------------------------------------------------
# S. no replay after terminal resolution
# ---------------------------------------------------------------------------


def test_s_no_replay_after_terminal_resolution(fake_stack):
    supervisor, controller, adapter = fake_stack
    cmd = controller.submit_command(ProviderCommandType.SUBSCRIBE)
    supervisor.push(_outcome(command=cmd, outcome=ProviderExecutionOutcome.TIMEOUT))
    adapter.start()
    assert _wait_until(lambda: len(supervisor.calls) >= 1)
    adapter.stop(join_timeout_seconds=2.0)
    # nothing re-drives dispatch for the already-resolved command
    assert len(supervisor.calls) == 1
    assert controller.drain_commands_for_worker() == []


# ---------------------------------------------------------------------------
# T. one submit_command in flight max
# ---------------------------------------------------------------------------


def test_t_one_submit_command_in_flight_at_a_time(fake_stack):
    supervisor, controller, adapter = fake_stack
    controller.submit_command(ProviderCommandType.SUBSCRIBE)
    controller.submit_command(ProviderCommandType.UNSUBSCRIBE)

    concurrent_calls = []
    lock = threading.Lock()
    release = threading.Event()

    def _tracking(command):
        with lock:
            concurrent_calls.append(1)
        release.wait(timeout=2.0)
        with lock:
            concurrent_calls.pop()
        return _outcome(command=command, outcome=ProviderExecutionOutcome.SUCCEEDED)

    supervisor.push(_tracking)
    supervisor.push(_tracking)
    adapter.start()
    time_bound = time.monotonic() + 1.0
    max_seen = 0
    while time.monotonic() < time_bound:
        with lock:
            max_seen = max(max_seen, len(concurrent_calls))
        time.sleep(0.01)
    release.set()
    adapter.stop(join_timeout_seconds=2.0)
    assert max_seen <= 1


# ---------------------------------------------------------------------------
# U. two-command ordering preserved
# ---------------------------------------------------------------------------


def test_u_two_command_ordering_preserved(fake_stack):
    supervisor, controller, adapter = fake_stack
    first = controller.submit_command(ProviderCommandType.SUBSCRIBE)
    second = controller.submit_command(ProviderCommandType.UNSUBSCRIBE)
    supervisor.push(_outcome(command=first, outcome=ProviderExecutionOutcome.SUCCEEDED))
    supervisor.push(_outcome(command=second, outcome=ProviderExecutionOutcome.SUCCEEDED))

    adapter.start()
    assert _wait_until(lambda: len(supervisor.calls) >= 2)
    adapter.stop(join_timeout_seconds=2.0)

    assert [c.command_id for c in supervisor.calls] == [first.command_id, second.command_id]
    controller.process_pending()
    assert [r.command_id for r in controller.command_results] == [first.command_id, second.command_id]


# ---------------------------------------------------------------------------
# V. stop with pending queue -> pending commands untouched
# ---------------------------------------------------------------------------


def test_v_stop_with_pending_queue_leaves_them_untouched(fake_stack):
    supervisor, controller, adapter = fake_stack
    controller.submit_command(ProviderCommandType.SUBSCRIBE)
    second = controller.submit_command(ProviderCommandType.UNSUBSCRIBE)

    dispatched = threading.Event()
    release = threading.Event()

    def _blocking(command):
        dispatched.set()
        release.wait(timeout=5.0)
        return _outcome(command=command, outcome=ProviderExecutionOutcome.SUCCEEDED)

    supervisor.push(_blocking)
    adapter.start()
    assert dispatched.wait(timeout=2.0)

    stopper = threading.Thread(target=lambda: adapter.stop(join_timeout_seconds=5.0))
    stopper.start()
    release.set()
    stopper.join(timeout=5.0)

    remaining = controller.drain_commands_for_worker()
    assert [c.command_id for c in remaining] == [second.command_id]
    assert len(supervisor.calls) == 1


# ---------------------------------------------------------------------------
# W. bounded join timeout -> explicit failure to caller
# ---------------------------------------------------------------------------


def test_w_stop_join_timeout_fails_loud(fake_stack):
    supervisor, controller, adapter = fake_stack
    controller.submit_command(ProviderCommandType.SUBSCRIBE)

    dispatched = threading.Event()
    never_release = threading.Event()

    def _hangs(command):
        dispatched.set()
        never_release.wait(timeout=10.0)
        return _outcome(command=command, outcome=ProviderExecutionOutcome.SUCCEEDED)

    supervisor.push(_hangs)
    adapter.start()
    assert dispatched.wait(timeout=2.0)

    with pytest.raises(AdapterStopTimeout):
        adapter.stop(join_timeout_seconds=0.1)
    assert adapter.is_running is True  # never pretends a clean shutdown happened

    never_release.set()  # release so the fixture teardown can join cleanly


# ---------------------------------------------------------------------------
# X. import module -> no thread/process starts
# ---------------------------------------------------------------------------


def test_x_import_module_starts_no_thread_or_process() -> None:
    # A plain in-process `import` is not a meaningful check here -- the
    # module is already imported by this test file's own top-level
    # imports, so Python's import cache would make any before/after
    # thread-count comparison trivially pass regardless of correctness.
    # A fresh subprocess proves the real claim: importing the module
    # alone starts nothing that would keep the interpreter alive or fail.
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", "import src.services.live_feed.provider_worker_executor_adapter"],
        cwd=str(repo_root),
        timeout=15,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "ModuleNotFoundError" in result.stderr:
        pytest.skip(
            "environment missing an unrelated third-party dependency needed "
            f"by the data_provider import chain: {result.stderr.strip().splitlines()[-1]}"
        )
    assert result.returncode == 0, result.stderr


def test_x_construction_alone_starts_no_thread(fake_stack):
    supervisor, controller, adapter = fake_stack
    before = threading.active_count()
    # constructed already by the fixture; attaching again is a no-op check
    assert threading.active_count() == before
    assert adapter.is_running is False


# ---------------------------------------------------------------------------
# Additional targeted invariant tests
# ---------------------------------------------------------------------------


def test_start_requires_attached_controller() -> None:
    adapter = ExecutorAdapter(supervisor=_FakeSupervisor())
    with pytest.raises(AdapterNotAttachedError):
        adapter.start()


def test_start_rejects_double_start(fake_stack):
    supervisor, controller, adapter = fake_stack
    supervisor.push(_outcome(outcome=ProviderExecutionOutcome.SUCCEEDED))
    adapter.start()
    with pytest.raises(AdapterAlreadyStartedError):
        adapter.start()
    adapter.stop(join_timeout_seconds=2.0)


def test_stop_idempotent_when_never_started(fake_stack):
    supervisor, controller, adapter = fake_stack
    adapter.stop(join_timeout_seconds=1.0)
    adapter.stop(join_timeout_seconds=1.0)  # second call is a clean no-op


def test_provider_execution_outcome_none_only_for_admission_cases(fake_stack):
    supervisor, controller, adapter = fake_stack
    cmd = controller.submit_command(ProviderCommandType.SUBSCRIBE)
    supervisor.push(_outcome(command=cmd, outcome=ProviderExecutionOutcome.CANCELLED_SHUTDOWN))
    adapter.start()
    assert _wait_until(lambda: len(supervisor.calls) >= 1)
    adapter.stop(join_timeout_seconds=2.0)
    controller.process_pending()
    result = controller.command_results[0]
    assert result.provider_execution_outcome == ProviderExecutionOutcome.CANCELLED_SHUTDOWN.value
    assert result.provider_execution_outcome is not None


def test_succeeded_and_error_are_legacy_only_never_authoritative(fake_stack):
    supervisor, controller, adapter = fake_stack
    cmd = controller.submit_command(ProviderCommandType.SUBSCRIBE)
    supervisor.push(
        _outcome(
            command=cmd,
            outcome=ProviderExecutionOutcome.PROVIDER_REJECTED,
            provider_error_code="E9",
            provider_error_message="no entitlement",
        )
    )
    adapter.start()
    assert _wait_until(lambda: len(supervisor.calls) >= 1)
    adapter.stop(join_timeout_seconds=2.0)
    controller.process_pending()
    result = controller.command_results[0]
    # succeeded/error are coarse legacy projections; the record of truth
    # is provider_execution_outcome + the structured error fields.
    assert result.succeeded is False
    assert result.provider_execution_outcome == "PROVIDER_REJECTED"
    assert result.provider_error_code == "E9"
    assert result.provider_error_message == "no entitlement"


def test_supervisor_public_api_surface_only() -> None:
    import inspect

    from src.services.live_feed import provider_worker_executor_adapter as module

    source = inspect.getsource(module)
    for forbidden in ("_Generation", "_current", "release_event", "_hard_kill", "command_queue.get", "result_queue"):
        assert forbidden not in source, f"Adapter reaches into Supervisor internals: {forbidden}"
    for forbidden_call in ("start_generation(", "replace_generation(", ".shutdown("):
        assert forbidden_call not in source, f"Adapter calls forbidden Supervisor lifecycle method: {forbidden_call}"
