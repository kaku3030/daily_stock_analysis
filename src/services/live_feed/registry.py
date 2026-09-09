"""Desired subscription registry -- authoritative intent state only.

Single writer owns mutation (enforced by an internal lock, not by trusting
callers). This registry never calls any provider SDK and never
reconciles against actual provider state -- it is bookkeeping for what the
controller *wants*, per frozen contract §4/§12 (`desired_registry_revision`,
`stream_subscription_epoch`).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from data_provider.live_feed_types import BindingStrength, ControlPlaneState, SemanticStreamKey


@dataclass(frozen=True)
class DesiredRegistryEntry:
    semantic_stream_key: SemanticStreamKey
    stream_subscription_epoch: int
    control_plane_state: ControlPlaneState
    binding_strength: BindingStrength


@dataclass(frozen=True)
class DesiredRegistrySnapshot:
    revision: int
    entries: tuple[DesiredRegistryEntry, ...]


def _sort_key(entry: DesiredRegistryEntry) -> tuple:
    key = entry.semantic_stream_key
    return (
        key.provider_id,
        key.market,
        key.symbol,
        key.stream_type,
        key.timeframe or "",
        key.session_mode or "",
        key.adjustment_mode or "",
        key.feed or "",
    )


class DesiredSubscriptionRegistry:
    """Provider-neutral desired subscription registry. Single writer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._revision = 0
        self._entries: dict[SemanticStreamKey, DesiredRegistryEntry] = {}
        # Epoch memory persists across remove() so that a later
        # readd_new_incarnation() for the same key keeps counting forward
        # rather than resetting -- a remove+re-add cycle is exactly the
        # "new incarnation" scenario the epoch exists to track (CASE 32).
        self._last_epoch_by_key: dict[SemanticStreamKey, int] = {}

    def add_desired(self, key: SemanticStreamKey) -> DesiredRegistrySnapshot:
        """Add `key` as desired. No-op (no revision bump) if already desired."""

        with self._lock:
            if key in self._entries:
                return self._snapshot_locked()
            epoch = self._last_epoch_by_key.get(key, 1) or 1
            self._entries[key] = DesiredRegistryEntry(
                semantic_stream_key=key,
                stream_subscription_epoch=epoch,
                control_plane_state=ControlPlaneState.DESIRED,
                binding_strength=BindingStrength.UNVERIFIED,
            )
            self._last_epoch_by_key[key] = epoch
            self._revision += 1
            return self._snapshot_locked()

    def remove_desired(self, key: SemanticStreamKey) -> DesiredRegistrySnapshot:
        """Remove `key` from desired. No-op (no revision bump) if absent."""

        with self._lock:
            if key not in self._entries:
                return self._snapshot_locked()
            del self._entries[key]
            self._revision += 1
            return self._snapshot_locked()

    def readd_new_incarnation(self, key: SemanticStreamKey) -> DesiredRegistrySnapshot:
        """Re-add `key` as a NEW controller intent incarnation.

        Bumps `stream_subscription_epoch` regardless of whether `key` was
        previously present -- this is the only registry operation that
        advances the epoch, per frozen contract §4
        (`stream_subscription_epoch`: "increment when controller intent
        creates a new subscription incarnation"). This does not claim any
        provider-side binding -- `binding_strength` resets to UNVERIFIED.
        """

        with self._lock:
            prior_epoch = self._last_epoch_by_key.get(key, 0)
            new_epoch = prior_epoch + 1
            self._entries[key] = DesiredRegistryEntry(
                semantic_stream_key=key,
                stream_subscription_epoch=new_epoch,
                control_plane_state=ControlPlaneState.DESIRED,
                binding_strength=BindingStrength.UNVERIFIED,
            )
            self._last_epoch_by_key[key] = new_epoch
            self._revision += 1
            return self._snapshot_locked()

    def set_control_plane_state(
        self, key: SemanticStreamKey, state: ControlPlaneState, *, binding_strength: BindingStrength | None = None
    ) -> DesiredRegistrySnapshot:
        """Annotate provider-observed control-plane state on existing intent.

        Raises KeyError if `key` is not currently desired -- this only
        annotates an existing intent, it does not create one. Because this is
        provider observation rather than desired-intent mutation, it MUST NOT
        advance `desired_registry_revision`.
        """

        with self._lock:
            entry = self._entries[key]
            self._entries[key] = DesiredRegistryEntry(
                semantic_stream_key=entry.semantic_stream_key,
                stream_subscription_epoch=entry.stream_subscription_epoch,
                control_plane_state=state,
                binding_strength=binding_strength if binding_strength is not None else entry.binding_strength,
            )
            return self._snapshot_locked()

    def snapshot(self) -> DesiredRegistrySnapshot:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> DesiredRegistrySnapshot:
        entries = tuple(sorted(self._entries.values(), key=_sort_key))
        return DesiredRegistrySnapshot(revision=self._revision, entries=entries)
