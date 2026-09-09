# -*- coding: utf-8 -*-
"""Live Feed Reliability V0.1 -- provider-neutral core types.

Contracts only: no provider SDK calls, no trading/execution behavior, no
LIVE-qualification logic. These types are consumed by the streaming
capability boundary (streaming_market_data_adapter.py) and by the
LiveFeedController (src/services/live_feed/). See
docs/LIVE_FEED_RELIABILITY_CONTRACT_V0_1.md for the frozen design these
types implement.

A ProviderEvent is evidence only -- it never carries authoritative LIVE
truth. That determination belongs solely to the controller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class SemanticStreamKey:
    """Semantic identity of a data stream -- not connection identity.

    Only fields already justified by the frozen contract (§6) are
    included. Equality/hash are the dataclass-generated structural ones,
    which are deterministic by construction.
    """

    provider_id: str
    market: str
    symbol: str
    stream_type: str
    timeframe: str | None = None
    session_mode: str | None = None
    adjustment_mode: str | None = None
    feed: str | None = None


class ProviderEventKind(str, Enum):
    DATA = "DATA"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    SUBSCRIPTION_RESULT = "SUBSCRIPTION_RESULT"
    ERROR = "ERROR"
    ENTITLEMENT = "ENTITLEMENT"
    HEARTBEAT = "HEARTBEAT"
    TRANSPORT_RECONNECTING = "TRANSPORT_RECONNECTING"


class DeliveryMode(str, Enum):
    REALTIME = "REALTIME"
    DELAYED = "DELAYED"
    UNKNOWN = "UNKNOWN"


class BindingStrength(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class ControlPlaneState(str, Enum):
    """Control-plane subscription facts only -- never a LIVE state."""

    DESIRED = "DESIRED"
    REQUESTED = "REQUESTED"
    ACKED = "ACKED"
    REJECTED = "REJECTED"
    INCARNATION_BOUND = "INCARNATION_BOUND"
    INCARNATION_UNVERIFIED = "INCARNATION_UNVERIFIED"


class LifecycleState(str, Enum):
    """Public state machine (frozen contract §2).

    LIVE exists here as a named state so downstream code can reference it,
    but no code in this Slice 1 foundation may produce a transition into
    it -- see LiveFeedController's invariant test.
    """

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    SUBSCRIBING = "SUBSCRIBING"
    LIVE = "LIVE"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"


class FailureClass(str, Enum):
    """Recovery-policy classification, kept independent of LifecycleState."""

    TRANSIENT = "TRANSIENT"
    REQUIRES_INTERVENTION = "REQUIRES_INTERVENTION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ProviderEvent:
    """Immutable evidence envelope for one provider-observed fact.

    `local_enqueue_seq` is unknown at construction time (it is assigned by
    the controller's ingress queue on enqueue) and is filled in via
    ``dataclasses.replace`` when the event is accepted -- see
    LiveFeedController.submit_event. Every other field is set by whoever
    constructs the event.

    `payload` and `diagnostic_fields` should be passed as already-read-only
    mappings (``types.MappingProxyType``); this type does not deep-copy or
    validate them, so a caller that hands over a mutable dict is
    responsible for not mutating it afterward.
    """

    runtime_instance_id: str
    provider_id: str
    controller_generation: int
    observed_at_utc: datetime
    observed_at_monotonic: float
    event_kind: ProviderEventKind
    local_enqueue_seq: int | None = None
    semantic_stream_key: SemanticStreamKey | None = None
    provider_context_id: str | None = None
    provider_connection_attempt_id: str | None = None
    payload: Mapping[str, Any] | None = None
    provider_timestamp_raw: str | None = None
    delivery_mode: DeliveryMode = DeliveryMode.UNKNOWN
    progress_identity_candidate: str | None = None
    provenance: str | None = None
    diagnostic_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


_JSON_LIKE_PRIMITIVES = (str, int, float, bool, type(None))


@dataclass(frozen=True)
class OpaqueUnsupportedPayload:
    """Explicit, deterministic marker for a payload value `freeze_normalized_payload`
    could not safely freeze (some provider-native mutable object that is
    neither a JSON-like mapping/sequence nor a primitive). The original
    mutable object is deliberately NOT retained here -- only its type name,
    so it can never become authoritative evidence read later by the writer.
    """

    type_name: str


def freeze_normalized_payload(value: Any) -> Any:
    """Recursively convert `value` into a deep-enough-immutable, JSON-like
    structure safe to hand to the writer as authoritative evidence
    (frozen contract §16 concurrency rules; Slice 1 repair F6).

    Supported: mappings -> ``MappingProxyType`` of recursively-frozen
    values; lists/tuples -> tuples of recursively-frozen values;
    str/int/float/bool/None pass through unchanged. Anything else
    (a provider-native mutable object, e.g.) is replaced with
    `OpaqueUnsupportedPayload` rather than retained by reference -- this is
    a narrow JSON-like freeze, not a general-purpose deep-copy/serializer.
    """

    if isinstance(value, _JSON_LIKE_PRIMITIVES):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze_normalized_payload(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_normalized_payload(item) for item in value)
    return OpaqueUnsupportedPayload(type_name=type(value).__name__)
