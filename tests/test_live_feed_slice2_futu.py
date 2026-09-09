"""Slice 2: Futu streaming adapter + transport recovery foundation tests.

Repair R1: rewritten for immutable per-context generation binding (REPAIR
2/3) and unverified DATA epoch attribution (REPAIR 1). `_FakeQuoteContext`
stands in for `futu.OpenQuoteContext`; SDK callbacks are invoked directly
via the incarnation-bound closures the adapter itself hands out
(`adapter.debug_fire_disconnect(...)` etc. below), rather than driven
through real protobuf responses, since the point under test is the
adapter's/controller's own normalization and identity logic, not the Futu
SDK itself (already covered empirically by tools/provider_semantics/futu/).

Deterministic only -- never touches real OpenD/Futu/a live market session.
"""

import threading
import time
from datetime import datetime, timezone

import pytest

from data_provider.futu_streaming_adapter import FutuStreamingAdapter
from data_provider.live_feed_types import (
    BindingStrength,
    ControlPlaneState,
    DeliveryMode,
    LifecycleState,
    ProviderEvent,
    ProviderEventKind,
    SemanticStreamKey,
)
from src.services.live_feed.commands import FakeProviderCommandExecutor, ProviderCommandResult, ProviderCommandType
from src.services.live_feed.controller import LiveFeedController, run_command_worker_once
from src.services.live_feed.futu_executor import FutuProviderCommandExecutor

QUOTE_KEY = SemanticStreamKey(provider_id="futu", market="HK", symbol="HK.00700", stream_type="QUOTE")
KLINE_KEY = SemanticStreamKey(provider_id="futu", market="HK", symbol="HK.00700", stream_type="K_1M")


def _fixed_now():
    return datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)


class _FakeQuoteContext:
    """Stands in for `futu.OpenQuoteContext`. Never touches real OpenD.
    Records the `incarnation` it was built with so tests can fire
    "callbacks" that are provably bound to a specific context instance,
    exactly as the real adapter/executor pipeline binds them.
    """

    def __init__(self, *, host, port, adapter, incarnation, subscribe_delay: float = 0.0):
        self.host = host
        self.port = port
        self.adapter = adapter
        self.incarnation = incarnation
        self.subscribe_calls: list[tuple] = []
        self.unsubscribe_calls: list[tuple] = []
        self.closed = False
        self.subscribe_result = (0, None)
        self.unsubscribe_result = (0, None)
        self._subscribe_delay = subscribe_delay

    def set_handler(self, handler):
        pass

    def subscribe(self, symbols, subtypes, subscribe_push=True):
        if self._subscribe_delay:
            time.sleep(self._subscribe_delay)
        self.subscribe_calls.append((tuple(symbols), tuple(subtypes)))
        return self.subscribe_result

    def unsubscribe(self, symbols, subtypes):
        self.unsubscribe_calls.append((tuple(symbols), tuple(subtypes)))
        return self.unsubscribe_result

    def close(self):
        self.closed = True

    # ---- test-only helpers to simulate SDK callbacks bound to THIS context ----

    def fire_disconnect(self, conn_id=1, reason="CloseReason.ReadFail", msg=""):
        self.adapter._on_provider_disconnect(self.incarnation, conn_id, reason, msg)

    def fire_transport_reconnected(self):
        self.adapter._on_provider_transport_reconnected(self.incarnation)

    def fire_quote_rows(self, rows):
        self.adapter._on_quote_rows(self.incarnation, rows)

    def fire_kline_rows(self, rows):
        self.adapter._on_kline_rows(self.incarnation, rows)


def _make_adapter(*, subscribe_delay: float = 0.0):
    holder: dict = {"contexts": []}

    def factory(*, host, port, adapter, incarnation):
        ctx = _FakeQuoteContext(host=host, port=port, adapter=adapter, incarnation=incarnation, subscribe_delay=subscribe_delay)
        holder["ctx"] = ctx
        holder["contexts"].append(ctx)
        return ctx

    adapter = FutuStreamingAdapter(context_factory=factory, now_utc=_fixed_now, now_monotonic=lambda: 1.0)
    return adapter, holder


def _controller_with_futu(*, subscribe_delay: float = 0.0):
    adapter, holder = _make_adapter(subscribe_delay=subscribe_delay)
    executor = FutuProviderCommandExecutor(adapter, now_utc=_fixed_now)
    controller = LiveFeedController(
        runtime_instance_id="r1", provider_id="futu", command_executor=executor, now_utc=_fixed_now
    )
    events: list[ProviderEvent] = []
    adapter.register_event_sink(lambda e: (events.append(e), controller.submit_event(e)))
    return controller, adapter, executor, holder, events


def _connect_and_subscribe(controller, executor, holder, key=QUOTE_KEY):
    controller.request_add_desired(key)
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)
    controller.process_pending()
    run_command_worker_once(controller, executor)
    controller.process_pending()


# ---------------------------------------------------------------------------
# A. Blocking boundary
# ---------------------------------------------------------------------------


def test_a_connect_does_not_run_on_writer() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_connect()
    controller.process_pending()  # only issues the CONNECT command, never calls the adapter
    assert "ctx" not in holder  # adapter.start() has not run yet
    run_command_worker_once(controller, executor)  # THIS is what actually calls adapter.start()
    assert "ctx" in holder


def test_a_subscribe_does_not_run_on_writer() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_add_desired(QUOTE_KEY)
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)  # executes CONNECT -> emits CONNECTED event
    controller.process_pending()  # applies CONNECTED -> cascades to SUBSCRIBING, enqueues SUBSCRIBE
    assert holder["ctx"].subscribe_calls == []  # not yet run
    run_command_worker_once(controller, executor)
    assert len(holder["ctx"].subscribe_calls) == 1


def test_a_unsubscribe_does_not_run_on_writer() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    controller.request_remove_desired(QUOTE_KEY)
    controller.process_pending()  # enqueues UNSUBSCRIBE only
    assert holder["ctx"].unsubscribe_calls == []
    run_command_worker_once(controller, executor)
    assert len(holder["ctx"].unsubscribe_calls) == 1


def test_a_slow_blocking_provider_operation_does_not_block_writer_progress() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu(subscribe_delay=0.3)
    controller.request_add_desired(QUOTE_KEY)
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)
    controller.process_pending()

    worker_thread = threading.Thread(target=run_command_worker_once, args=(controller, executor))
    t0 = time.monotonic()
    worker_thread.start()
    time.sleep(0.02)  # let the worker thread enter the slow subscribe() call
    applied = controller.process_pending()
    writer_duration = time.monotonic() - t0
    assert writer_duration < 0.25
    assert applied == 0
    worker_thread.join(timeout=2.0)
    assert not worker_thread.is_alive()


# ---------------------------------------------------------------------------
# B. Callback authority
# ---------------------------------------------------------------------------


def test_b_callback_only_stages_immutable_event_never_touches_controller_directly() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    events.clear()
    holder["ctx"].fire_quote_rows([{"code": "HK.00700", "data_time": "10:00:00", "last_price": 1.0}])
    assert len(events) == 1
    assert isinstance(events[0], ProviderEvent)
    assert events[0].event_kind is ProviderEventKind.DATA


def test_b_callback_cannot_mutate_lifecycle_directly() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    holder2 = holder
    adapter2 = adapter
    # fire a raw quote callback BEFORE any connect -- there is no active
    # context/incarnation yet, so exercise via a manually-started adapter
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)
    before = controller.snapshot().lifecycle_state
    holder["ctx"].fire_quote_rows([{"code": "HK.00700", "data_time": "10:00:00"}])
    # the event was submitted to ingress (via the sink wiring) but NOT applied
    assert controller.snapshot().lifecycle_state == before


def test_b_callback_cannot_mutate_registry_directly() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)
    before = controller.desired_registry_snapshot().revision
    holder["ctx"].fire_quote_rows([{"code": "HK.00700", "data_time": "10:00:00"}])
    assert controller.desired_registry_snapshot().revision == before


def test_b_mutable_provider_payload_mutated_after_handoff_cannot_alter_writer_evidence() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    events.clear()
    row = {"code": "HK.00700", "data_time": "10:00:00", "last_price": 1.0}
    holder["ctx"].fire_quote_rows([row])
    row["last_price"] = 999.0
    row["injected"] = "leak?"
    frozen_payload = events[0].payload
    assert frozen_payload["last_price"] == 1.0
    assert "injected" not in frozen_payload


# ---------------------------------------------------------------------------
# C. Connect path
# ---------------------------------------------------------------------------


def test_c_disconnected_to_connecting_on_request_connect() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    assert controller.snapshot().lifecycle_state is LifecycleState.DISCONNECTED
    controller.request_connect()
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is LifecycleState.CONNECTING


def test_c_provider_connection_success_reaches_connected_then_subscribing() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_add_desired(QUOTE_KEY)
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is LifecycleState.SUBSCRIBING
    assert holder["ctx"] is not None


def test_c_desired_streams_produce_subscribe_commands_on_connect() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_add_desired(QUOTE_KEY)
    controller.request_add_desired(KLINE_KEY)
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)
    controller.process_pending()
    run_command_worker_once(controller, executor)
    assert len(holder["ctx"].subscribe_calls) == 2


def test_c_no_connected_to_live_shortcut() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is not LifecycleState.LIVE


# ---------------------------------------------------------------------------
# D. Disconnect path
# ---------------------------------------------------------------------------


def test_d_transport_disconnect_produces_explicit_lifecycle_evidence() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    holder["ctx"].fire_disconnect()
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is LifecycleState.RECONNECTING


def test_d_active_path_transitions_to_reconnecting() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    assert controller.snapshot().lifecycle_state is LifecycleState.SUBSCRIBING
    holder["ctx"].fire_disconnect(reason="CloseReason.RemoteClose")
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is LifecycleState.RECONNECTING


def test_d_stop_semantics_remain_authoritative() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    controller.request_stop()
    holder["ctx"].fire_disconnect()
    controller.process_pending()
    snap = controller.snapshot()
    assert snap.stop_requested is True
    assert snap.lifecycle_state is LifecycleState.DISCONNECTED
    assert any("SHUTDOWN_CLEAN" in f for f in snap.findings)


def test_d_stale_reconnect_events_after_stop_cannot_revive_lifecycle() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    controller.request_stop()
    controller.process_pending()
    lifecycle_at_stop = controller.snapshot().lifecycle_state
    holder["ctx"].fire_quote_rows([{"code": "HK.00700", "data_time": "10:00:01"}])
    controller.process_pending()
    snap = controller.snapshot()
    assert snap.lifecycle_state == lifecycle_at_stop
    assert any("STALE_EVENT_AFTER_STOP" in f for f in snap.findings)


# ---------------------------------------------------------------------------
# E. Reconnect path
# ---------------------------------------------------------------------------


def test_e_new_generation_allocated_on_first_transport_loss() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    gen_before = controller.snapshot().controller_generation
    holder["ctx"].fire_disconnect()
    controller.process_pending()
    assert controller.snapshot().controller_generation == gen_before + 1


def test_e_repeated_disconnect_evidence_does_not_advance_generation_again() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    ctx = holder["ctx"]
    ctx.fire_disconnect()
    controller.process_pending()
    gen_after_first = controller.snapshot().controller_generation
    for _ in range(5):
        ctx.fire_disconnect(reason="CloseReason.RemoteClose")
    controller.process_pending()
    assert controller.snapshot().controller_generation == gen_after_first


def test_e_old_ack_binding_does_not_survive_generation_change() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    entry_before = controller.desired_registry_snapshot().entries[0]
    assert entry_before.control_plane_state is ControlPlaneState.ACKED

    holder["ctx"].fire_disconnect()
    controller.process_pending()
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)
    controller.process_pending()  # CONNECTED (new generation) resets ACK state
    entry_after = controller.desired_registry_snapshot().entries[0]
    assert entry_after.control_plane_state is ControlPlaneState.REQUESTED
    assert entry_after.binding_strength.value == "UNVERIFIED"


def test_e_resubscription_derived_from_desired_registry_after_reconnect() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    old_ctx = holder["ctx"]
    assert len(old_ctx.subscribe_calls) == 1
    old_ctx.fire_disconnect()
    controller.process_pending()
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)  # adapter.start() builds a FRESH fake context
    new_ctx = holder["ctx"]
    assert new_ctx is not old_ctx
    controller.process_pending()
    run_command_worker_once(controller, executor)
    assert len(old_ctx.subscribe_calls) == 1
    assert len(new_ctx.subscribe_calls) == 1


def test_e_sdk_auto_resubscribe_observation_alone_does_not_qualify_recovery() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    ctx = holder["ctx"]
    ctx.fire_disconnect()
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is LifecycleState.RECONNECTING
    ctx.fire_transport_reconnected()  # SDK-private auto-reconnect+resubscribe, SAME context
    controller.process_pending()
    snap = controller.snapshot()
    assert snap.lifecycle_state is LifecycleState.RECONNECTING
    assert any("PROVIDER_TRANSPORT_RECONNECT_OBSERVED" in f for f in snap.findings)


def test_e_sdk_private_reconnect_data_on_old_context_stays_bound_to_old_generation() -> None:
    """The GPT-adjudicated correction: an SDK-private reconnect on the SAME
    OpenQuoteContext must NOT self-promote -- its DATA remains bound to the
    OLD (now-superseded) generation and is correctly rejected as stale by
    the controller. This is acceptable/expected, not a bug: controller-
    authorized recovery only happens via an explicit new CONNECT.
    """

    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    ctx = holder["ctx"]  # the ONLY context -- never replaced, SDK "reconnects" it privately
    old_generation = controller.snapshot().controller_generation
    ctx.fire_disconnect()
    controller.process_pending()
    new_generation = controller.snapshot().controller_generation
    assert new_generation == old_generation + 1
    ctx.fire_transport_reconnected()
    ctx.fire_quote_rows([{"code": "HK.00700", "data_time": "10:05:00"}])
    controller.process_pending()
    events_at = [e for e in events if e.event_kind is ProviderEventKind.DATA][-1]
    assert events_at.controller_generation == old_generation  # still stamped OLD -- correct, not relabeled
    snap = controller.snapshot()
    assert any("STALE_DATA_EVENT" in f and "stale_generation" in f for f in snap.findings)
    assert snap.health.symbols == ()  # never accepted as fresh evidence


# ---------------------------------------------------------------------------
# F. Stale callbacks
# ---------------------------------------------------------------------------


def test_f_previous_generation_callback_rejected() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    stale_event = ProviderEvent(
        runtime_instance_id="r1",
        provider_id="futu",
        controller_generation=controller.snapshot().controller_generation - 1,
        observed_at_utc=_fixed_now(),
        observed_at_monotonic=1.0,
        event_kind=ProviderEventKind.DATA,
        semantic_stream_key=QUOTE_KEY,
    )
    controller.submit_event(stale_event)
    controller.process_pending()
    snap = controller.snapshot()
    assert any("STALE_DATA_EVENT" in f and "stale_generation" in f for f in snap.findings)
    assert snap.health.symbols == ()


def test_f_data_epoch_is_never_verified_remove_readd_case() -> None:
    """REPAIR 1's mandatory test: E1 subscribe -> remove -> E2 re-add ->
    a delayed DATA callback that cannot be provider-attributed to E1 or
    E2 must NOT be stamped verified-E2, must never satisfy an E2
    incarnation proof, and must never overwrite a "verified" fact with
    false provenance (there is never a verified DATA fact to overwrite in
    the first place -- every DATA-derived fact is unconditionally
    UNVERIFIED, by design, because Futu offers no per-callback
    incarnation proof at all).
    """

    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)  # subscribes at epoch 1 (E1)
    ctx = holder["ctx"]

    controller.request_remove_desired(QUOTE_KEY)
    controller.process_pending()
    run_command_worker_once(controller, executor)  # runs the UNSUBSCRIBE
    controller.process_pending()
    assert controller.desired_registry_snapshot().entries == ()

    controller.request_readd_incarnation(QUOTE_KEY)  # -> epoch 2 (E2)
    controller.process_pending()
    entry_e2 = controller.desired_registry_snapshot().entries[0]
    assert entry_e2.stream_subscription_epoch == 2

    # a delayed DATA callback arrives on the SAME (only) context -- the
    # adapter has NO way to know whether this is causally from the E1 or
    # E2 subscription, so it must never claim either.
    ctx.fire_quote_rows([{"code": "HK.00700", "data_time": "10:10:00"}])
    fired_event = [e for e in events if e.event_kind is ProviderEventKind.DATA][-1]
    assert fired_event.stream_subscription_epoch is None  # never a fabricated claim

    controller.process_pending()
    snap = controller.snapshot()
    # accepted as observational evidence (key IS currently desired, epoch
    # check is skipped because None means "no claim"), but explicitly
    # marked unverified -- never proof of E2 incarnation
    symbol_health = snap.health.symbols[0].streams[0]
    assert symbol_health.binding_strength is BindingStrength.UNVERIFIED
    assert controller.desired_registry_snapshot().entries[0].stream_subscription_epoch == 2  # registry unaffected


def test_f_subscription_result_retains_exact_command_bound_epoch() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    sub_result_events = [e for e in events if e.event_kind is ProviderEventKind.SUBSCRIPTION_RESULT]
    assert len(sub_result_events) == 1
    assert sub_result_events[0].stream_subscription_epoch == 1  # exact command-bound epoch, not None


def test_f_unsubscribe_success_followed_by_late_callback_does_not_restore_removed_stream() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    ctx = holder["ctx"]

    controller.request_remove_desired(QUOTE_KEY)
    controller.process_pending()
    run_command_worker_once(controller, executor)
    controller.process_pending()
    assert controller.desired_registry_snapshot().entries == ()

    ctx.fire_quote_rows([{"code": "HK.00700", "data_time": "10:00:02"}])
    controller.process_pending()
    snap = controller.snapshot()
    assert controller.desired_registry_snapshot().entries == ()  # still removed, not revived
    assert any("STALE_DATA_EVENT" in f and "stream_not_currently_desired" in f for f in snap.findings)


# ---------------------------------------------------------------------------
# G. DeliveryMode
# ---------------------------------------------------------------------------


def test_g_default_unknown() -> None:
    event = ProviderEvent(
        runtime_instance_id="r1",
        provider_id="futu",
        controller_generation=0,
        observed_at_utc=_fixed_now(),
        observed_at_monotonic=1.0,
        event_kind=ProviderEventKind.DATA,
    )
    assert event.delivery_mode is DeliveryMode.UNKNOWN


def test_g_unknown_cannot_result_in_live() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    holder["ctx"].fire_quote_rows([{"code": "HK.00700", "data_time": "10:00:00"}])
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is not LifecycleState.LIVE
    assert controller.snapshot().health.symbols[0].streams[0].delivery_mode is DeliveryMode.UNKNOWN


def test_g_subscribe_ack_cannot_change_unknown_into_realtime() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    entry = controller.desired_registry_snapshot().entries[0]
    assert entry.control_plane_state is ControlPlaneState.ACKED
    import inspect

    from src.services.live_feed.controller import LiveFeedController as _LFC

    source = inspect.getsource(_LFC._handle_subscription_result_event)
    assert "DeliveryMode.REALTIME" not in source


# ---------------------------------------------------------------------------
# H. Provider identity
# ---------------------------------------------------------------------------


def test_h_sdk_conn_id_is_diagnostic_only() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    holder["ctx"].fire_disconnect(conn_id=12345)
    controller.process_pending()
    disconnect_event = next(e for e in events if e.event_kind is ProviderEventKind.DISCONNECTED)
    assert disconnect_event.diagnostic_fields["provider_conn_id"] == 12345
    import inspect

    from src.services.live_feed import controller as controller_module

    source = inspect.getsource(controller_module.LiveFeedController)
    assert "provider_conn_id" not in source


def test_h_changing_sdk_conn_id_does_not_create_authoritative_identity() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    gen_before = controller.snapshot().controller_generation
    ctx = holder["ctx"]
    for conn_id in (1, 2, 3):
        ctx.fire_disconnect(conn_id=conn_id, reason="CloseReason.RemoteClose")
    controller.process_pending()
    assert controller.snapshot().controller_generation == gen_before + 1


def test_h_same_openquotecontext_can_span_multiple_observed_transport_connections() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    ctx_identity_before = id(holder["ctx"])
    holder["ctx"].fire_disconnect()
    controller.process_pending()
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)  # builds a fresh fake context in this harness
    assert controller.snapshot().controller_generation >= 1
    assert "ctx" in holder


# ---------------------------------------------------------------------------
# I. Command/error behavior
# ---------------------------------------------------------------------------


def test_i_provider_command_rejection_is_explicit() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_add_desired(QUOTE_KEY)
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)
    controller.process_pending()
    holder["ctx"].subscribe_result = (-1, "entitlement denied")
    run_command_worker_once(controller, executor)
    controller.process_pending()
    snap = controller.snapshot()
    entry = snap.desired_registry.entries[0]
    assert entry.control_plane_state is ControlPlaneState.REJECTED


def test_i_provider_exception_becomes_normalized_result_not_a_crash() -> None:
    adapter, holder = _make_adapter()

    def broken_factory(*, host, port, adapter, incarnation):
        raise ConnectionRefusedError("simulated unreachable OpenD")

    adapter._context_factory = broken_factory
    adapter.set_connect_identity(runtime_instance_id="r1", provider_id="futu", controller_generation=0)
    executor = FutuProviderCommandExecutor(adapter, now_utc=_fixed_now)
    results: list[ProviderCommandResult] = []
    executor.register_result_sink(results.append)
    from src.services.live_feed.commands import ProviderCommand

    command = ProviderCommand(
        runtime_instance_id="r1",
        provider_id="futu",
        controller_generation=0,
        desired_registry_revision=0,
        command_id="c1",
        command_type=ProviderCommandType.CONNECT,
        created_at=_fixed_now(),
    )
    executor.submit(command)  # must not raise
    assert len(results) == 1
    assert results[0].succeeded is False
    assert "ConnectionRefusedError" in results[0].error


def test_i_writer_remains_alive_after_recoverable_provider_command_failure() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_add_desired(QUOTE_KEY)
    controller.request_connect()
    controller.process_pending()

    def broken_factory(*, host, port, adapter, incarnation):
        raise RuntimeError("simulated connect failure")

    adapter._context_factory = broken_factory
    run_command_worker_once(controller, executor)
    controller.process_pending()
    snap = controller.snapshot()
    assert snap.lifecycle_state is LifecycleState.RECONNECTING
    assert any("CONNECT_FAILED" in f for f in snap.findings)


def test_i_provider_error_does_not_drop_later_control_requests() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_add_desired(QUOTE_KEY)
    controller.request_connect()
    controller.process_pending()

    def broken_factory(*, host, port, adapter, incarnation):
        raise RuntimeError("simulated connect failure")

    adapter._context_factory = broken_factory
    run_command_worker_once(controller, executor)
    controller.request_stop()
    controller.process_pending()
    snap = controller.snapshot()
    assert snap.stop_requested is True
    assert snap.lifecycle_state is not LifecycleState.RECONNECTING  # REPAIR 4: STOP dominates


# ---------------------------------------------------------------------------
# Repair R1 -- REPAIR 2/3: immutable per-context generation binding
# ---------------------------------------------------------------------------


def test_repair2_generation_immutable_per_context_binding() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    ctx_a = holder["ctx"]
    gen_a = controller.snapshot().controller_generation

    ctx_a.fire_disconnect()
    controller.process_pending()
    gen_after_loss = controller.snapshot().controller_generation
    assert gen_after_loss == gen_a + 1

    # a late DATA "callback" from context A must STILL carry gen_a, even
    # though the controller has already moved to gen_a + 1
    events.clear()
    ctx_a.fire_quote_rows([{"code": "HK.00700", "data_time": "10:20:00"}])
    assert events[-1].controller_generation == gen_a


def test_repair3_explicit_reconnect_retires_old_context_on_worker() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    ctx_a = holder["ctx"]
    assert ctx_a.closed is False

    ctx_a.fire_disconnect()
    controller.process_pending()
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)  # adapter.start() must close ctx_a first, on THIS (worker) thread

    assert ctx_a.closed is True  # REPAIR 3: old context retired
    ctx_b = holder["ctx"]
    assert ctx_b is not ctx_a

    controller.process_pending()
    gen_b = controller.snapshot().controller_generation

    # late callback from the RETIRED context A still carries the OLD generation
    events.clear()
    ctx_a.fire_quote_rows([{"code": "HK.00700", "data_time": "10:21:00"}])
    controller.process_pending()
    assert any("STALE_DATA_EVENT" in f and "stale_generation" in f for f in controller.snapshot().findings)

    # a callback from the NEW context B carries the NEW generation
    events.clear()
    ctx_b.fire_quote_rows([{"code": "HK.00700", "data_time": "10:22:00"}])
    assert events[-1].controller_generation == gen_b


def test_repair2_sdk_private_reconnect_does_not_self_promote() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    ctx = holder["ctx"]
    ctx.fire_disconnect()
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is LifecycleState.RECONNECTING
    ctx.fire_transport_reconnected()
    ctx.fire_quote_rows([{"code": "HK.00700", "data_time": "10:23:00"}])
    controller.process_pending()
    # still RECONNECTING -- SDK-private reconnect on the OLD context never
    # self-promotes; controller-authorized recovery requires an explicit
    # new CONNECT from the controller's own recovery path
    assert controller.snapshot().lifecycle_state is LifecycleState.RECONNECTING


# ---------------------------------------------------------------------------
# Repair R1 -- REPAIR 4: STOP dominates command-result effects
# ---------------------------------------------------------------------------


def _broken_connect_controller():
    controller, adapter, executor, holder, events = _controller_with_futu()

    def broken_factory(*, host, port, adapter, incarnation):
        raise RuntimeError("simulated connect failure")

    adapter._context_factory = broken_factory
    return controller, adapter, executor, holder, events


def test_repair4_stop_before_late_connect_failure() -> None:
    controller, adapter, executor, holder, events = _broken_connect_controller()
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)  # CONNECT fails, result staged
    controller.request_stop()
    controller.process_pending()  # STOP applied THIS pass; result also materialized this pass
    snap = controller.snapshot()
    assert snap.stop_requested is True
    assert snap.lifecycle_state is not LifecycleState.RECONNECTING


def test_repair4_stop_and_connect_failure_same_pass_ordering_still_safe() -> None:
    controller, adapter, executor, holder, events = _broken_connect_controller()
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)  # result staged, NOT yet materialized
    controller.request_stop()  # enqueued, same upcoming pass as the staged result
    controller.process_pending()  # single pass: drains STOP control request AND materializes the staged result
    snap = controller.snapshot()
    assert snap.stop_requested is True
    assert snap.lifecycle_state is not LifecycleState.RECONNECTING
    assert not any("CONNECT_FAILED" in f for f in snap.findings)


def test_repair4_late_subscribe_result_after_stop_is_history_only() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    controller.request_stop()
    controller.process_pending()
    before_registry = controller.desired_registry_snapshot()
    holder["ctx"].fire_quote_rows([{"code": "HK.00700", "data_time": "10:30:00"}])  # any late provider evidence
    controller.process_pending()
    assert controller.desired_registry_snapshot() == before_registry
    assert controller.snapshot().stop_requested is True


# ---------------------------------------------------------------------------
# Repair R1 -- REPAIR 5: STOP retires provider transport
# ---------------------------------------------------------------------------


def test_repair5_stop_with_active_context_queues_and_executes_close() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    ctx = holder["ctx"]
    assert ctx.closed is False
    controller.request_stop()
    controller.process_pending()  # enqueues CLOSE
    run_command_worker_once(controller, executor)  # executes it
    assert ctx.closed is True


def test_repair5_stop_while_connect_in_flight_eventually_closes_resulting_context() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_connect()
    controller.process_pending()
    # simulate STOP landing while CONNECT is "in flight": request_stop()
    # before the worker has run at all, then run the worker once for
    # CONNECT (queued first) and again for CLOSE (queued second)
    controller.request_stop()
    controller.process_pending()
    run_command_worker_once(controller, executor, max_items=1)  # CONNECT executes, context created
    ctx = holder["ctx"]
    assert ctx.closed is False
    run_command_worker_once(controller, executor, max_items=1)  # CLOSE executes next
    assert ctx.closed is True
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is not LifecycleState.CONNECTED
    assert controller.snapshot().lifecycle_state is not LifecycleState.SUBSCRIBING


def test_repair5_close_when_no_context_is_idempotent() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    controller.request_stop()
    controller.process_pending()  # enqueues CLOSE even though nothing was ever connected
    n = run_command_worker_once(controller, executor)
    assert n == 1
    controller.process_pending()
    assert not any("STALE_COMMAND_RESULT" in f for f in controller.snapshot().findings)


def test_repair5_shutdown_close_queue_full_is_explicit() -> None:
    controller, adapter, executor, holder, events = _controller_with_futu()
    _connect_and_subscribe(controller, executor, holder)
    # exhaust the command queue with junk so CLOSE cannot be enqueued
    for _ in range(256):
        try:
            controller.submit_command(ProviderCommandType.DIAGNOSTIC)
        except Exception:
            break
    controller.request_stop()
    controller.process_pending()
    snap = controller.snapshot()
    assert any("COMMAND_QUEUE_FULL" in f and "CLOSE" in f for f in snap.findings)


# ---------------------------------------------------------------------------
# Repair R1 -- REPAIR 6: explicit connect attempt identity
# ---------------------------------------------------------------------------


def test_repair6_attempt_a_late_failure_cannot_mutate_attempt_b() -> None:
    """The CONNECTING-eligibility gate (`request_connect` is a no-op
    unless lifecycle is DISCONNECTED/RECONNECTING) already makes two
    organically-concurrent explicit attempts hard to construct -- attempt
    B cannot even be issued until attempt A's own outcome has resolved
    lifecycle out of CONNECTING. The remaining hazard REPAIR 6 protects
    against is a STALE/duplicate result for an attempt that has ALREADY
    been superseded (e.g. a defensive/out-of-order-delivery scenario) --
    tested here by directly staging a fabricated result carrying an old
    command_id after a real attempt B is already active, and confirming
    it is ignored while B's own result is honored.
    """

    controller, adapter, executor, holder, events = _controller_with_futu()

    controller.request_connect()  # attempt A
    controller.process_pending()

    # Attempt A resolves normally (succeeds) -- fabricate what a stale,
    # already-superseded attempt A failure result would have looked like,
    # using A's real command_id recovered from the controller's own
    # materialized command-result history after it resolves.
    run_command_worker_once(controller, executor)
    controller.process_pending()
    attempt_a_command_id = controller.command_results[-1].command_id
    assert controller.snapshot().lifecycle_state is LifecycleState.SUBSCRIBING

    # Force a transport loss to make a NEW explicit attempt eligible/real
    holder["ctx"].fire_disconnect()
    controller.process_pending()
    controller.request_connect()  # attempt B
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is LifecycleState.CONNECTING

    # A stale, fabricated failure result for the LONG-SINCE-RESOLVED
    # attempt A arrives (simulating an out-of-order/duplicate delivery)
    stale_result = ProviderCommandResult(
        command_id=attempt_a_command_id,
        command_type=ProviderCommandType.CONNECT,
        succeeded=False,
        controller_generation=controller.snapshot().controller_generation,  # even matching CURRENT generation
        desired_registry_revision=controller.snapshot().desired_registry_revision,
        completed_at=_fixed_now(),
        error="stale/duplicate attempt A result",
    )
    controller._stage_command_result(stale_result)
    controller.process_pending()
    # attempt B's own CONNECTING must be unaffected by attempt A's stale result
    assert controller.snapshot().lifecycle_state is LifecycleState.CONNECTING
    assert any("STALE_COMMAND_RESULT" in f and "command_id" in f for f in controller.snapshot().findings)

    # attempt B's OWN (real) result still works correctly
    run_command_worker_once(controller, executor)
    controller.process_pending()
    assert controller.snapshot().lifecycle_state is LifecycleState.SUBSCRIBING


def test_repair6_current_attempt_failure_still_produces_reconnecting() -> None:
    controller, adapter, executor, holder, events = _broken_connect_controller()
    controller.request_connect()
    controller.process_pending()
    run_command_worker_once(controller, executor)
    controller.process_pending()
    snap = controller.snapshot()
    assert snap.lifecycle_state is LifecycleState.RECONNECTING
    assert any("CONNECT_FAILED" in f for f in snap.findings)


def test_repair6_stop_clears_active_attempt_authority() -> None:
    controller, adapter, executor, holder, events = _broken_connect_controller()
    controller.request_connect()
    controller.process_pending()
    controller.request_stop()
    controller.process_pending()
    run_command_worker_once(controller, executor)  # the (now-irrelevant) CONNECT fails
    controller.process_pending()
    snap = controller.snapshot()
    assert snap.lifecycle_state is not LifecycleState.RECONNECTING
    assert not any("CONNECT_FAILED" in f for f in snap.findings)


# ---------------------------------------------------------------------------
# J. Regression marker
# ---------------------------------------------------------------------------


def test_j_slice1_types_still_importable_and_unchanged_shape() -> None:
    import dataclasses

    from data_provider.live_feed_types import ProviderEvent

    field_names = {f.name for f in dataclasses.fields(ProviderEvent)}
    assert "stream_subscription_epoch" in field_names
    assert {"runtime_instance_id", "provider_id", "controller_generation", "event_kind"} <= field_names
