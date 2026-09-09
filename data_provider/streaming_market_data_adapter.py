# -*- coding: utf-8 -*-
"""Explicit streaming-provider capability boundary.

`MarketDataAdapter` (market_data_adapter.py) stays the generic interface
every provider implements for snapshot/history/subscribe. It is
deliberately NOT widened here -- doing so would force every existing
implementation (including the two that already document that they cannot
stream: PytdxMarketDataAdapter, ExistingMarketDataAdapter) to grow
meaningless `NotImplementedError` methods.

Instead, streaming mechanics genuinely richer than the base `subscribe()`
callback (start/stop lifecycle, per-stream subscribe/unsubscribe keyed by
SemanticStreamKey, and an explicit ProviderEvent sink) are expressed as a
separate, structurally-checked capability. A provider adapter satisfies
this Protocol only if it actually implements all of its methods --
nothing needs to inherit from it, and nothing needs to be told about it
to remain unaffected.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from .live_feed_types import ProviderEvent, SemanticStreamKey


@runtime_checkable
class StreamingMarketDataAdapter(Protocol):
    """Capability boundary for providers that can genuinely stream.

    Detect it with ``isinstance(adapter, StreamingMarketDataAdapter)``.
    A snapshot/history-only adapter that does not define these methods
    simply does not satisfy the Protocol -- no forced stub required.
    """

    def start(self) -> None:
        """Establish whatever transport/session the provider needs."""

    def stop(self) -> None:
        """Tear down transport/session. Must not raise on repeated calls."""

    def subscribe_stream(self, key: SemanticStreamKey) -> None:
        """Request the provider begin pushing events for this stream."""

    def unsubscribe_stream(self, key: SemanticStreamKey) -> None:
        """Request the provider stop pushing events for this stream."""

    def register_event_sink(self, sink: Callable[[ProviderEvent], None]) -> None:
        """Register where normalized ProviderEvents should be delivered.

        The sink must be treated as nonblocking-only by the adapter: it
        exists to hand events to a controller's ingress queue, not to run
        arbitrary work on the adapter's own callback thread.
        """
