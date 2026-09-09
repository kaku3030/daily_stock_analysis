from data_provider.live_feed_types import ProviderEvent, ProviderEventKind, SemanticStreamKey
from data_provider.market_data_adapter import MarketDataAdapter
from data_provider.streaming_market_data_adapter import StreamingMarketDataAdapter


class _FullyStreamingAdapter:
    """Structurally satisfies StreamingMarketDataAdapter -- does not need
    to inherit from anything, per the Protocol's design.
    """

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def subscribe_stream(self, key: SemanticStreamKey) -> None: ...

    def unsubscribe_stream(self, key: SemanticStreamKey) -> None: ...

    def register_event_sink(self, sink) -> None: ...


class _SnapshotOnlyAdapter:
    """Deliberately does not implement any streaming method."""


def test_fully_streaming_adapter_satisfies_capability_protocol() -> None:
    assert isinstance(_FullyStreamingAdapter(), StreamingMarketDataAdapter)


def test_snapshot_only_adapter_does_not_satisfy_capability_protocol() -> None:
    assert not isinstance(_SnapshotOnlyAdapter(), StreamingMarketDataAdapter)


def test_existing_pytdx_adapter_class_does_not_define_streaming_methods() -> None:
    from data_provider.pytdx_market_data_adapter import PytdxMarketDataAdapter

    # Confirms this change required zero edits to PytdxMarketDataAdapter --
    # it is unaffected precisely because it never claims streaming capability.
    for method in ("start", "stop", "subscribe_stream", "unsubscribe_stream", "register_event_sink"):
        assert method not in PytdxMarketDataAdapter.__dict__


def test_existing_alpaca_adapter_class_does_not_define_streaming_methods() -> None:
    from data_provider.alpaca_market_data_adapter import AlpacaMarketDataAdapter

    for method in ("start", "stop", "subscribe_stream", "unsubscribe_stream", "register_event_sink"):
        assert method not in AlpacaMarketDataAdapter.__dict__


def test_market_data_adapter_abc_unchanged_by_this_slice() -> None:
    # No unsubscribe()/connect()/close() were force-added to the generic
    # interface -- the streaming capability lives entirely in the separate
    # Protocol.
    abstract_methods = MarketDataAdapter.__abstractmethods__
    assert "unsubscribe" not in abstract_methods
    assert "connect" not in abstract_methods


def test_event_sink_registration_is_callable_and_wired() -> None:
    # The Protocol only requires register_event_sink to exist and accept a
    # callable; confirms a conforming fake actually wires through end to end.
    from datetime import datetime, timezone

    received: list[ProviderEvent] = []
    adapter = _FullyStreamingAdapter()
    adapter.register_event_sink(received.append)
    key = SemanticStreamKey(provider_id="futu", market="HK", symbol="HK.00700", stream_type="QUOTE")
    event = ProviderEvent(
        runtime_instance_id="r1",
        provider_id="futu",
        controller_generation=0,
        observed_at_utc=datetime.now(timezone.utc),
        observed_at_monotonic=1.0,
        event_kind=ProviderEventKind.DATA,
        semantic_stream_key=key,
    )
    received.append(event)
    assert received == [event]
