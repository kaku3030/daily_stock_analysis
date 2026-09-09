"""Wave 2 harness hardening self-tests.

These test HARNESS MECHANICS only:
- transport_proxy.py against a local mock TCP echo server (never Futu/OpenD)
- lifecycle_recorder.py append-only/timestamp/thread/origin behavior
- market_gate.py's fail-closed logic
- outage_guard.py's deadlock-prevention guarantee (the mandatory
  regression test for the exact mistake that caused both Wave 2 R0/R1
  blocking incidents)

Nothing here claims anything about real Futu/OpenD semantics -- the mock
echo server proves the proxy forwards bytes and can cut/restore/stop
correctly, nothing more.

Run with:
    python -m pytest test_wave2_hardening.py -v --basetemp=".tmp/pytest_basetemp"
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lifecycle_recorder import LifecycleRecorder  # noqa: E402
from market_gate import is_market_active  # noqa: E402
from outage_guard import ExperimentState, OutageRpcGuard, ProviderRpcForbiddenDuringOutage  # noqa: E402
from recorder import new_run_dir, utc_now_iso  # noqa: E402
from transport_proxy import TransportProxy  # noqa: E402


# --------------------------------------------------------------------------
# Local mock TCP echo target -- NOT Futu/OpenD. Used only to exercise the
# proxy's own byte-forwarding and cut/restore/stop mechanics.
# --------------------------------------------------------------------------


class _EchoServer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(4)
        self.sock.settimeout(0.5)
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket):
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                conn.sendall(data)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def stop(self):
        self._stop = True
        try:
            self.sock.close()
        except Exception:
            pass


@pytest.fixture
def echo_server():
    server = _EchoServer()
    server.start()
    time.sleep(0.1)
    yield server
    server.stop()


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --------------------------------------------------------------------------
# B.3 Proxy cleanup tests
# --------------------------------------------------------------------------


def test_proxy_transparent_forwarding(echo_server):
    proxy = TransportProxy("127.0.0.1", _free_port(), "127.0.0.1", echo_server.port)
    proxy.start()
    time.sleep(0.2)
    try:
        client = socket.create_connection(("127.0.0.1", proxy.listen_port), timeout=5)
        client.sendall(b"hello-through-proxy")
        received = client.recv(4096)
        assert received == b"hello-through-proxy"
        client.close()
    finally:
        proxy.stop()


def test_proxy_cut_refuses_new_connections(echo_server):
    proxy = TransportProxy("127.0.0.1", _free_port(), "127.0.0.1", echo_server.port)
    proxy.start()
    time.sleep(0.2)
    try:
        proxy.cut()
        time.sleep(0.2)
        client = socket.create_connection(("127.0.0.1", proxy.listen_port), timeout=5)
        client.settimeout(1.0)
        # Connection accepted at TCP level but immediately closed by the proxy.
        data = client.recv(4096)
        assert data == b""  # peer closed
        client.close()
    finally:
        proxy.stop()


def test_proxy_cut_closes_active_pair(echo_server):
    proxy = TransportProxy("127.0.0.1", _free_port(), "127.0.0.1", echo_server.port)
    proxy.start()
    time.sleep(0.2)
    try:
        client = socket.create_connection(("127.0.0.1", proxy.listen_port), timeout=5)
        client.sendall(b"ping")
        assert client.recv(4096) == b"ping"
        proxy.cut()
        time.sleep(0.2)
        client.settimeout(1.0)
        # Windows raises ConnectionResetError for an abruptly-closed peer
        # rather than returning b"" from recv(); both are valid evidence
        # that the pair was actually severed.
        try:
            data = client.recv(4096)
            assert data == b""
        except ConnectionResetError:
            pass
        client.close()
    finally:
        proxy.stop()


def test_proxy_restore_allows_new_connections_again(echo_server):
    proxy = TransportProxy("127.0.0.1", _free_port(), "127.0.0.1", echo_server.port)
    proxy.start()
    time.sleep(0.2)
    try:
        proxy.cut()
        time.sleep(0.2)
        proxy.restore()
        time.sleep(0.2)
        client = socket.create_connection(("127.0.0.1", proxy.listen_port), timeout=5)
        client.sendall(b"post-restore")
        assert client.recv(4096) == b"post-restore"
        client.close()
    finally:
        proxy.stop()


def test_proxy_stop_is_idempotent(echo_server):
    proxy = TransportProxy("127.0.0.1", _free_port(), "127.0.0.1", echo_server.port)
    proxy.start()
    time.sleep(0.1)
    proxy.stop()
    proxy.stop()  # must not raise the second time


def test_proxy_cleanup_runs_even_on_exception(echo_server):
    proxy = TransportProxy("127.0.0.1", _free_port(), "127.0.0.1", echo_server.port)
    proxy.start()
    time.sleep(0.1)
    try:
        try:
            raise RuntimeError("simulated experiment failure")
        finally:
            proxy.stop()
    except RuntimeError:
        pass
    # A second stop() after an exception-driven cleanup must still be safe.
    proxy.stop()


def test_proxy_only_touches_its_own_listen_port(echo_server):
    """The proxy must never bind or touch any port other than the one it
    was explicitly constructed with.
    """

    port = _free_port()
    proxy = TransportProxy("127.0.0.1", port, "127.0.0.1", echo_server.port)
    proxy.start()
    time.sleep(0.1)
    try:
        assert proxy.listen_port == port
        assert proxy.upstream_port == echo_server.port
    finally:
        proxy.stop()


# --------------------------------------------------------------------------
# B.4 Lifecycle recorder tests
# --------------------------------------------------------------------------


@pytest.fixture
def tmp_runs_dir(tmp_path):
    d = tmp_path / "runs"
    d.mkdir()
    return d


def test_lifecycle_recorder_monotonic_local_event_seq(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = LifecycleRecorder(run_dir, runtime_run_id="test-run")
    seqs = []
    for _ in range(10):
        rec = recorder.record_lifecycle(event_type="BASELINE_CHECKPOINT", origin="HARNESS")
        seqs.append(rec["local_event_seq"])
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_lifecycle_recorder_utc_aware_timestamps(tmp_runs_dir):
    from datetime import datetime

    run_dir = new_run_dir(tmp_runs_dir)
    recorder = LifecycleRecorder(run_dir, runtime_run_id="test-run")
    rec = recorder.record_lifecycle(event_type="BASELINE_CHECKPOINT", origin="HARNESS")
    parsed = datetime.fromisoformat(rec["observed_at_utc"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_lifecycle_recorder_thread_id_captured(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = LifecycleRecorder(run_dir, runtime_run_id="test-run")
    rec = recorder.record_lifecycle(event_type="BASELINE_CHECKPOINT", origin="HARNESS")
    assert rec["thread_id"] == threading.get_ident()


def test_lifecycle_recorder_rejects_unknown_event_type(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = LifecycleRecorder(run_dir, runtime_run_id="test-run")
    with pytest.raises(ValueError):
        recorder.record_lifecycle(event_type="NOT_A_REAL_EVENT_TYPE", origin="HARNESS")


def test_lifecycle_recorder_rejects_unknown_origin(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = LifecycleRecorder(run_dir, runtime_run_id="test-run")
    with pytest.raises(ValueError):
        recorder.record_lifecycle(event_type="BASELINE_CHECKPOINT", origin="SOMETHING_ELSE")


def test_lifecycle_recorder_append_only_and_no_overwrite(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = LifecycleRecorder(run_dir, runtime_run_id="test-run")
    recorder.record_lifecycle(event_type="BASELINE_CHECKPOINT", origin="HARNESS")
    size_1 = (run_dir / "lifecycle.jsonl").stat().st_size
    recorder.record_lifecycle(event_type="BASELINE_CHECKPOINT", origin="HARNESS")
    size_2 = (run_dir / "lifecycle.jsonl").stat().st_size
    assert size_2 > size_1
    with pytest.raises(FileExistsError):
        LifecycleRecorder(run_dir, runtime_run_id="second-attempt")


def test_lifecycle_recorder_hash_integrity_across_read(tmp_runs_dir):
    import hashlib

    run_dir = new_run_dir(tmp_runs_dir)
    recorder = LifecycleRecorder(run_dir, runtime_run_id="test-run")
    for _ in range(5):
        recorder.record_lifecycle(event_type="BASELINE_CHECKPOINT", origin="HARNESS")
    path = run_dir / "lifecycle.jsonl"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    _ = recorder.read_lifecycle()  # read-back must not mutate the file
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == after


def test_lifecycle_recorder_origin_values(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = LifecycleRecorder(run_dir, runtime_run_id="test-run")
    a = recorder.record_lifecycle(event_type="CONTEXT_CREATE_BEGIN", origin="HARNESS")
    b = recorder.record_lifecycle(event_type="DATA_CALLBACK", origin="PROVIDER_SDK")
    assert a["origin"] == "HARNESS"
    assert b["origin"] == "PROVIDER_SDK"


def test_lifecycle_recorder_records_recovery_state_transitions(tmp_runs_dir):
    """Recovery experiment state transitions (FAULT_INJECTION_BEGIN/END) are
    themselves recordable lifecycle events."""

    run_dir = new_run_dir(tmp_runs_dir)
    recorder = LifecycleRecorder(run_dir, runtime_run_id="test-run")
    recorder.record_lifecycle(event_type="FAULT_INJECTION_BEGIN", origin="HARNESS", raw_payload={"phase": "cut"})
    recorder.record_lifecycle(event_type="FAULT_INJECTION_END", origin="HARNESS", raw_payload={"phase": "restore"})
    events = recorder.read_lifecycle()
    phases = [e["raw_payload"]["phase"] for e in events if e["event_type"] in ("FAULT_INJECTION_BEGIN", "FAULT_INJECTION_END")]
    assert phases == ["cut", "restore"]


# --------------------------------------------------------------------------
# B.5 Market gate test
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state,expected",
    [
        ("MORNING", True),
        ("AFTERNOON", True),
        ("CLOSED", False),
        ("AFTER_HOURS_END", False),
        ("STIB_AFTER_HOURS_BEGIN", False),
        (None, False),
        ("", False),
        ("SOME_UNRECOGNIZED_FUTURE_STATE", False),
    ],
)
def test_market_gate_fails_closed(state, expected):
    assert is_market_active(state) is expected


# --------------------------------------------------------------------------
# B.6 Deadlock regression test (mandatory)
# --------------------------------------------------------------------------


def test_deadlock_regression_outage_guard_rejects_before_entering_sdk():
    """Reproduces, at the harness-mechanics level, the exact mistake that
    caused both Wave 2 R0 (unreachable-port construction) and R1
    (query_subscription during outage) incidents: a synchronous provider
    call issued while transport is down. The guard must reject BEFORE the
    dangerous callable is ever invoked, and the restore() path must remain
    reachable immediately afterward (i.e. the guard itself never blocks).
    """

    guard = OutageRpcGuard()
    guard.transition(ExperimentState.BASELINE)
    guard.transition(ExperimentState.TRANSPORT_CUT)

    dangerous_call_was_entered = {"value": False}

    def dangerous_query_subscription_probe():
        # Simulates the real SDK call that hung in Wave 2 R1. If the guard
        # works, this must never execute.
        dangerous_call_was_entered["value"] = True
        raise AssertionError("should never be reached")

    with pytest.raises(ProviderRpcForbiddenDuringOutage):
        guard.call("query_subscription", dangerous_query_subscription_probe)

    assert dangerous_call_was_entered["value"] is False, "guard must reject BEFORE entering the SDK call"

    # The restore path must remain immediately reachable -- proving the
    # guard itself introduces no blocking of its own.
    start = time.monotonic()
    guard.transition(ExperimentState.RESTORED)
    elapsed = time.monotonic() - start
    assert elapsed < 0.1
    assert guard.state is ExperimentState.RESTORED


def test_deadlock_regression_guard_fails_closed_for_unknown_method_names():
    """The guard must not rely on a caller-maintained allowlist -- an
    unrecognized method name is refused too, not silently permitted.
    """

    guard = OutageRpcGuard()
    guard.transition(ExperimentState.TRANSPORT_CUT)
    with pytest.raises(ProviderRpcForbiddenDuringOutage):
        guard.call("some_future_sdk_method_nobody_added_to_the_list", lambda: 1)


def test_outage_guard_allows_calls_outside_transport_cut():
    guard = OutageRpcGuard()
    guard.transition(ExperimentState.BASELINE)
    result = guard.call("query_subscription", lambda: "ok")
    assert result == "ok"
    guard.transition(ExperimentState.TRANSPORT_CUT)
    guard.transition(ExperimentState.RESTORED)
    result2 = guard.call("query_subscription", lambda: "ok-again")
    assert result2 == "ok-again"


def test_outage_guard_records_transition_history():
    guard = OutageRpcGuard()
    guard.transition(ExperimentState.BASELINE)
    guard.transition(ExperimentState.TRANSPORT_CUT)
    guard.transition(ExperimentState.RESTORED)
    assert guard.transitions == [
        (ExperimentState.IDLE, ExperimentState.BASELINE),
        (ExperimentState.BASELINE, ExperimentState.TRANSPORT_CUT),
        (ExperimentState.TRANSPORT_CUT, ExperimentState.RESTORED),
    ]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
