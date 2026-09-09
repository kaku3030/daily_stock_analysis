# -*- coding: utf-8 -*-
"""Concrete Futu/Moomoo streaming provider adapter (Slice 2 -- Repair R1).

Implements `StreamingMarketDataAdapter` (streaming_market_data_adapter.py)
for the Futu SDK. This module owns ALL Futu-specific mechanics: creating
and closing `OpenQuoteContext`, registering SDK callback handlers,
normalizing raw callback payloads into immutable `ProviderEvent`s, and
issuing subscribe/unsubscribe calls. It does NOT decide LiveFeed
lifecycle, DecisionEligibility, or AI eligibility, and it never promotes
itself to LIVE -- all of that stays with `LiveFeedController`.

Repair R1 fixes two identity findings from the adversarial review:

- REPAIR 1 (DATA epoch attribution): DATA callbacks used to stamp
  `stream_subscription_epoch` from a mutable `_local_epoch_by_key` cache,
  overwritten on every `subscribe_stream()` call. A callback physically
  originating from an old, already-unsubscribed incarnation could be
  silently relabeled with whatever epoch the key was MOST RECENTLY
  resubscribed under. Futu provides no authoritative per-callback
  incarnation marker (empirically confirmed -- see
  FUTU_SEMANTIC_CONTRACT_V0_1.md), so DATA events now always carry
  `stream_subscription_epoch=None` ("no verified claim") rather than a
  fabricated value. The controller (Slice 2 Repair R1) records any
  resulting stream-health fact with `binding_strength=UNVERIFIED`,
  unconditionally, for exactly this reason -- see controller.py.
  `SUBSCRIPTION_RESULT` events remain command-bound (the exact epoch the
  SUBSCRIBE/UNSUBSCRIBE command itself carried) and are unaffected.
- REPAIR 2/3 (immutable per-context generation binding): a single mutable
  `self._connect_ctx`, shared by every callback regardless of which
  physical `OpenQuoteContext` incarnation produced them, is gone. Each
  `start()` call now freezes one `_ContextIncarnation` and closes every
  handler/callback for THAT specific context over that one immutable
  object (via closures built in `start()`/`_default_context_factory`/
  `_make_quote_handler`/`_make_kline_handler`) -- old-context callbacks
  can never be relabeled with a newer generation, because they were never
  reading a shared mutable value in the first place. `start()` also now
  retires (`.close()`s) any existing context BEFORE constructing the new
  one, always on the caller's thread (the provider-command worker,
  never the writer, never a callback).

Every method here (`start`, `stop`, `subscribe_stream`, `unsubscribe_stream`)
may call a synchronous, potentially-blocking Futu SDK operation
(`FUTU_SEMANTIC_CONTRACT_V0_1.md` §2 BLOCKING). **These methods must only
ever be called from a dedicated provider-command worker thread** (see
`src/services/live_feed/futu_executor.py`), never from
`LiveFeedController.process_pending`.

Callback handlers registered on the SDK context do only bounded, minimal
work: normalize the raw row into a `ProviderEvent` and hand it to the
registered sink. No provider SDK calls, no registry mutation, no
lifecycle mutation happen inside a callback.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Callable

from .live_feed_types import (
    DeliveryMode,
    ProviderEvent,
    ProviderEventKind,
    SemanticStreamKey,
    freeze_normalized_payload,
)

EventSink = Callable[[ProviderEvent], None]


@dataclass(frozen=True)
class _ContextIncarnation:
    """Immutable identity for exactly ONE physical `OpenQuoteContext`
    incarnation, minted once in `set_connect_identity()`/`start()` and
    closed over by every handler/callback created for that context. This
    object is never mutated and never shared/rebound across incarnations
    -- that immutability is what makes old-context callbacks structurally
    incapable of being relabeled with a newer controller generation.
    """

    runtime_instance_id: str
    provider_id: str
    controller_generation: int
    adapter_context_id: str


def _default_context_factory(*, host: str, port: int, adapter: "FutuStreamingAdapter", incarnation: _ContextIncarnation):
    """Builds a real `futu.OpenQuoteContext` subclass whose `on_disconnect`/
    `on_api_socket_reconnected` overrides close over THIS `incarnation`
    object specifically (captured by the enclosing function call, not read
    from any mutable adapter attribute at callback time). Imports `futu`
    lazily so this module can be imported (and its non-SDK helpers
    exercised) even in environments without the SDK installed -- tests
    always inject a fake factory and never reach this function.
    """

    import futu as ft

    class _RecordingContext(ft.OpenQuoteContext):
        def on_disconnect(self, conn_id, reason, msg):
            adapter._on_provider_disconnect(incarnation, conn_id, reason, msg)
            return super().on_disconnect(conn_id, reason, msg)

        def on_api_socket_reconnected(self, *args, **kwargs):
            adapter._on_provider_transport_reconnected(incarnation)
            return super().on_api_socket_reconnected(*args, **kwargs)

    return _RecordingContext(host=host, port=port)


class FutuStreamingAdapter:
    """Structurally satisfies `StreamingMarketDataAdapter`. Owns exactly
    one `OpenQuoteContext` at a time between `start()`/`stop()`.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 11111,
        context_factory: Callable[..., object] = _default_context_factory,
        now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        now_monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._context_factory = context_factory
        self._now_utc = now_utc
        self._now_monotonic = now_monotonic or _default_monotonic()

        self._sink: EventSink | None = None
        self._ctx = None
        # Set by set_connect_identity(), consumed (and cleared) by the next
        # start() call -- this is the ONLY place a not-yet-bound identity
        # is held; once start() runs, it is frozen into `_active_incarnation`
        # and into the closures of every handler for that context.
        self._pending_incarnation: _ContextIncarnation | None = None
        # The incarnation bound to the CURRENTLY active context, if any --
        # used only by subscribe_stream/unsubscribe_stream, which always
        # act on "whatever is current" by construction (a synchronous SDK
        # call against self._ctx can only ever target the live context).
        self._active_incarnation: _ContextIncarnation | None = None
        self._lock = threading.Lock()

    def register_event_sink(self, sink: EventSink) -> None:
        self._sink = sink

    def set_connect_identity(self, *, runtime_instance_id: str, provider_id: str, controller_generation: int) -> None:
        """Called by `FutuProviderCommandExecutor` immediately before
        `start()`. Mints one immutable `_ContextIncarnation` -- `start()`
        consumes it exactly once and binds every subsequent callback for
        that context to this frozen value, never to whatever this method
        is called with next.
        """

        with self._lock:
            self._pending_incarnation = _ContextIncarnation(
                runtime_instance_id=runtime_instance_id,
                provider_id=provider_id,
                controller_generation=controller_generation,
                adapter_context_id=str(uuid.uuid4())[:8],
            )

    # ---- StreamingMarketDataAdapter surface (blocking; worker-thread only) ----

    def start(self) -> None:
        """Retires any existing context (REPAIR 3 -- always on this
        caller's thread, i.e. the provider worker, never the writer/a
        callback), then constructs a fresh `OpenQuoteContext` -- POTENTIALLY
        BLOCKING (confirmed: hangs indefinitely against an unreachable
        port in the tested SDK version). Must only run on the
        provider-command worker thread.
        """

        with self._lock:
            incarnation = self._pending_incarnation
            if incarnation is None:
                raise RuntimeError("start() called before set_connect_identity()")
            self._pending_incarnation = None
            old_ctx = self._ctx
            self._ctx = None
            self._active_incarnation = None

        if old_ctx is not None:
            old_ctx.close()  # retire the old physical context before creating a new one

        ctx = self._context_factory(host=self._host, port=self._port, adapter=self, incarnation=incarnation)
        ctx.set_handler(_make_quote_handler(self, incarnation))
        ctx.set_handler(_make_kline_handler(self, incarnation))
        with self._lock:
            self._ctx = ctx
            self._active_incarnation = incarnation
        self._emit(
            incarnation,
            event_kind=ProviderEventKind.CONNECTED,
            diagnostic_fields={"adapter_context_id": incarnation.adapter_context_id},
        )

    def stop(self) -> None:
        """Closes the current context -- may block briefly; never call
        from the writer. Idempotent/safe no-op if no context exists.
        """

        with self._lock:
            ctx = self._ctx
            self._ctx = None
            self._active_incarnation = None
        if ctx is not None:
            ctx.close()

    def subscribe_stream(self, key: SemanticStreamKey, *, stream_subscription_epoch: int | None = None) -> None:
        """POTENTIALLY BLOCKING -- worker-thread only. `stream_subscription_epoch`
        here is exactly the value the issuing SUBSCRIBE command carried
        (command-bound, not looked up from any cache) -- the resulting
        SUBSCRIPTION_RESULT event legitimately claims that exact epoch.
        """

        import futu as ft

        with self._lock:
            ctx = self._ctx
            incarnation = self._active_incarnation
        if ctx is None or incarnation is None:
            raise RuntimeError("subscribe_stream called before start()")
        subtype = getattr(ft.SubType, key.stream_type)
        ret, err = ctx.subscribe([key.symbol], [subtype], subscribe_push=True)
        self._emit(
            incarnation,
            event_kind=ProviderEventKind.SUBSCRIPTION_RESULT,
            semantic_stream_key=key,
            stream_subscription_epoch=stream_subscription_epoch,
            diagnostic_fields={"ret": ret, "succeeded": ret == 0, "error": None if ret == 0 else str(err)},
        )
        if ret != 0:
            raise RuntimeError(f"Futu subscribe failed for {key!r}: {err!r}")

    def unsubscribe_stream(self, key: SemanticStreamKey, *, stream_subscription_epoch: int | None = None) -> None:
        """POTENTIALLY BLOCKING -- worker-thread only. Per the empirical
        contract, a successful return here is NOT a callback-drain
        barrier -- callers must not assume no further DATA callbacks for
        `key` will arrive after this returns.
        """

        import futu as ft

        with self._lock:
            ctx = self._ctx
            incarnation = self._active_incarnation
        if ctx is None or incarnation is None:
            raise RuntimeError("unsubscribe_stream called before start()")
        subtype = getattr(ft.SubType, key.stream_type)
        ret, err = ctx.unsubscribe([key.symbol], [subtype])
        self._emit(
            incarnation,
            event_kind=ProviderEventKind.SUBSCRIPTION_RESULT,
            semantic_stream_key=key,
            stream_subscription_epoch=stream_subscription_epoch,
            diagnostic_fields={"ret": ret, "succeeded": ret == 0, "error": None if ret == 0 else str(err), "action": "unsubscribe"},
        )
        if ret != 0:
            raise RuntimeError(f"Futu unsubscribe failed for {key!r}: {err!r}")

    # ---- SDK callback surface (minimal, bounded work only) ----
    # Every callback below receives its context's immutable `incarnation`
    # via closure (never reads a shared mutable adapter attribute) -- see
    # module docstring REPAIR 2/3.

    def _on_provider_disconnect(self, incarnation: _ContextIncarnation, conn_id, reason, msg) -> None:
        """`conn_id` is recorded as a diagnostic field only (Futu SDK
        conn_id is DIAGNOSTIC_ONLY, never authoritative identity).
        """

        self._emit(
            incarnation,
            event_kind=ProviderEventKind.DISCONNECTED,
            diagnostic_fields={"provider_conn_id": conn_id, "reason": str(reason), "msg": str(msg)},
        )

    def _on_provider_transport_reconnected(self, incarnation: _ContextIncarnation) -> None:
        """SDK-private auto-reconnect (+ internal auto-resubscribe)
        evidence only -- TRANSPORT_RECONNECTING specifically so the
        controller cannot mistake it for controller recovery completion
        (frozen contract §13). Still bound to the OLD incarnation if this
        fires on an old context -- it is the controller's job (not this
        adapter's) to recognize that as stale relative to its own current
        generation; this adapter never "helpfully" upgrades it.
        """

        self._emit(
            incarnation, event_kind=ProviderEventKind.TRANSPORT_RECONNECTING, diagnostic_fields={"source": "sdk_auto_resubscribe"}
        )

    def _on_quote_rows(self, incarnation: _ContextIncarnation, rows: list[dict]) -> None:
        for row in rows:
            key = SemanticStreamKey(
                provider_id=incarnation.provider_id,
                market=_market_from_symbol(row.get("code")),
                symbol=row.get("code"),
                stream_type="QUOTE",
            )
            self._emit(
                incarnation,
                event_kind=ProviderEventKind.DATA,
                semantic_stream_key=key,
                # REPAIR 1: never claim a subscription epoch for DATA --
                # Futu gives no causal per-callback incarnation proof.
                stream_subscription_epoch=None,
                provider_timestamp_raw=row.get("data_time"),
                delivery_mode=DeliveryMode.UNKNOWN,
                payload=row,
            )

    def _on_kline_rows(self, incarnation: _ContextIncarnation, rows: list[dict]) -> None:
        for row in rows:
            key = SemanticStreamKey(
                provider_id=incarnation.provider_id,
                market=_market_from_symbol(row.get("code")),
                symbol=row.get("code"),
                stream_type="K_1M",
            )
            self._emit(
                incarnation,
                event_kind=ProviderEventKind.DATA,
                semantic_stream_key=key,
                stream_subscription_epoch=None,  # REPAIR 1: same as QUOTE, no verified claim
                provider_timestamp_raw=row.get("time_key"),
                progress_identity_candidate=row.get("time_key"),
                delivery_mode=DeliveryMode.UNKNOWN,
                payload=row,
            )

    # ---- shared emit path ----

    def _emit(
        self,
        incarnation: _ContextIncarnation,
        *,
        event_kind: ProviderEventKind,
        semantic_stream_key: SemanticStreamKey | None = None,
        stream_subscription_epoch: int | None = None,
        provider_timestamp_raw: str | None = None,
        progress_identity_candidate: str | None = None,
        delivery_mode: DeliveryMode = DeliveryMode.UNKNOWN,
        payload: dict | None = None,
        diagnostic_fields: dict | None = None,
    ) -> None:
        sink = self._sink
        if sink is None:
            return
        event = ProviderEvent(
            runtime_instance_id=incarnation.runtime_instance_id,
            provider_id=incarnation.provider_id,
            controller_generation=incarnation.controller_generation,
            observed_at_utc=self._now_utc(),
            observed_at_monotonic=self._now_monotonic(),
            event_kind=event_kind,
            semantic_stream_key=semantic_stream_key,
            stream_subscription_epoch=stream_subscription_epoch,
            provider_context_id=incarnation.adapter_context_id,
            payload=freeze_normalized_payload(payload) if payload is not None else None,
            provider_timestamp_raw=provider_timestamp_raw,
            delivery_mode=delivery_mode,
            progress_identity_candidate=progress_identity_candidate,
            diagnostic_fields=freeze_normalized_payload(diagnostic_fields) if diagnostic_fields else MappingProxyType({}),
        )
        sink(event)


def _market_from_symbol(symbol: str | None) -> str:
    if not symbol or "." not in symbol:
        return "UNKNOWN"
    return symbol.split(".", 1)[0]


def _default_monotonic() -> Callable[[], float]:
    import time

    return time.monotonic


def _make_quote_handler(adapter: FutuStreamingAdapter, incarnation: _ContextIncarnation):
    import futu as ft

    class _H(ft.StockQuoteHandlerBase):
        def on_recv_rsp(self, rsp_pb):
            ret_code, data = super().on_recv_rsp(rsp_pb)
            if ret_code != ft.RET_OK:
                return ft.RET_ERROR, data
            adapter._on_quote_rows(incarnation, data.to_dict(orient="records"))
            return ft.RET_OK, data

    return _H()


def _make_kline_handler(adapter: FutuStreamingAdapter, incarnation: _ContextIncarnation):
    import futu as ft

    class _H(ft.CurKlineHandlerBase):
        def on_recv_rsp(self, rsp_pb):
            ret_code, data = super().on_recv_rsp(rsp_pb)
            if ret_code != ft.RET_OK:
                return ft.RET_ERROR, data
            adapter._on_kline_rows(incarnation, data.to_dict(orient="records"))
            return ft.RET_OK, data

    return _H()
