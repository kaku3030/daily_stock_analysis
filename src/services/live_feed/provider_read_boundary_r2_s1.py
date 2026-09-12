"""R2-S1 fake QUOTE_SNAPSHOT adapter over the existing child-only seam."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .provider_read_boundary_r1 import ProviderReadOutcome, ProviderReadRequest, ReadOperation
from .provider_worker_contracts import ProviderExecutionOutcome
from .provider_worker_supervisor import ProviderWorkerSupervisor


class FakeQuoteSnapshotAdapter:
    """Typed R2-S1 adapter; it never imports or calls a provider SDK."""

    def __init__(self, supervisor: ProviderWorkerSupervisor) -> None:
        self._supervisor = supervisor

    def execute(
        self, request: ProviderReadRequest, *, behavior: str = "success",
        snapshot: Mapping[str, Any] | None = None,
    ) -> ProviderReadOutcome:
        if request.operation is not ReadOperation.QUOTE_SNAPSHOT:
            raise ValueError("R2-S1 accepts QUOTE_SNAPSHOT only")
        command = self._command_for(request)
        resolved = self._supervisor.submit_command(command, payload={
            "behavior": behavior,
            "read_operation": ReadOperation.QUOTE_SNAPSHOT.value,
            "symbols": list(request.params.symbols),
            "snapshot": dict(snapshot) if snapshot is not None else {},
        })
        return ProviderReadOutcome(
            request.runtime_instance_id, request.provider_id,
            resolved.worker_generation, request, resolved.outcome,
            resolved.dispatched_at_monotonic_ns,
            resolved.terminal_observed_at_monotonic_ns,
            resolved.terminal_at_utc, resolved.provider_error_code,
            resolved.provider_error_message, resolved.normalized_provider_payload,
            resolved.diagnostic_reason,
        )

    @staticmethod
    def _command_for(request: ProviderReadRequest):
        from .commands import ProviderCommand, ProviderCommandType
        return ProviderCommand(
            request.runtime_instance_id, request.provider_id, 0, 0,
            request.request_id, ProviderCommandType.DIAGNOSTIC,
            request.created_at_utc,
        )
