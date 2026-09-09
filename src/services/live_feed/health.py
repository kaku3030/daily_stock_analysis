"""LiveFeedHealth -- data structures only, scaffold for Slice 1 (§J).

No aggregation policy is implemented here. Explicit authority separation
(do not blur these -- each answers a different question, at a different
layer, and none should be merged into another):

- ``LiveFeedHealth`` (this module) = realtime transport/subscription/
  liveness FACTS for the Live Feed Reliability contract. Owned by
  LiveFeedController.
- ``data_provider.market_data_adapter.MarketDataHealth`` = provider/
  data-quality facts about a specific Bar/Quote (freshness, completeness,
  cross-check, etc.), feeding `SignalPermission`.
- ``src.services.stock_radar_v2.health.FallbackStateMachine`` = provider
  routing/selection state (PRIMARY vs FALLBACK, debounce, `critical`).
- ``data_provider.realtime_types.CircuitBreaker`` = a generic call-outcome
  debounce/cooldown helper, unaware of connections or subscriptions.
- DecisionEligibility (not implemented anywhere yet) = downstream
  capability/trading-eligibility policy. `LiveFeedHealth` must never
  expose or imply this -- it stops at reporting facts.

See docs/LIVE_FEED_REPO_INTEGRATION_RISKS_V0_1.md for the fuller
discussion of why these four (soon five) concepts stay separate rather
than being unified into one health "God Object".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from data_provider.live_feed_types import (
    BindingStrength,
    ControlPlaneState,
    DeliveryMode,
    FailureClass,
    LifecycleState,
    SemanticStreamKey,
)


@dataclass(frozen=True)
class StreamFeedHealth:
    semantic_stream_key: SemanticStreamKey
    control_plane_state: ControlPlaneState
    delivery_mode: DeliveryMode
    binding_strength: BindingStrength
    last_event_at_utc: datetime | None = None
    last_progress_at_utc: datetime | None = None
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SymbolFeedHealth:
    symbol: str
    streams: tuple[StreamFeedHealth, ...] = ()


@dataclass(frozen=True)
class LiveFeedHealth:
    """Realtime transport/subscription/liveness facts only. No 0-100
    score, no DecisionEligibility field, no aggregation policy -- see
    module docstring.
    """

    lifecycle_state: LifecycleState
    failure_class: FailureClass
    symbols: tuple[SymbolFeedHealth, ...] = ()
    findings: tuple[str, ...] = ()
