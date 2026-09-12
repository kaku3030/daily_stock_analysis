"""R2-S2 fake HISTORY_KLINE adapter over the existing child-only seam."""

from __future__ import annotations

from typing import Any, Mapping

from .provider_read_boundary_r1 import (
    ProviderReadOutcome,
    ProviderReadRequest,
    ReadOperation,
)
from .provider_worker_supervisor import ProviderWorkerSupervisor


class FakeHistoryKlineAdapter:
    """Typed R2-S2 adapter; it never imports or calls a provider SDK."""

    def __init__(self, supervisor: ProviderWorkerSupervisor) -> None:
        self._supervisor = supervisor

    def execute(
        self,
        request: ProviderReadRequest,
        *,
        behavior: str = "success",
        bars: Mapping[str, Any] | None = None,
    ) -> ProviderReadOutcome:
        if request.operation is not ReadOperation.HISTORY_KLINE:
            raise ValueError("R2-S2 accepts HISTORY_KLINE only")
        params = request.params
        command = self._command_for(request)
        resolved = self._supervisor.submit_command(command, payload={
            "behavior": behavior,
            "read_operation": ReadOperation.HISTORY_KLINE.value,
            "symbol": params.symbol,
            "timeframe": params.timeframe,
            "start": params.start.isoformat(),
            "end": params.end.isoformat(),
            "max_count": params.max_count,
            "bars": dict(bars) if bars is not None else {},
        })
        return ProviderReadOutcome(
            request.runtime_instance_id,
            request.provider_id,
            resolved.worker_generation,
            request,
            resolved.outcome,
            resolved.dispatched_at_monotonic_ns,
            resolved.terminal_observed_at_monotonic_ns,
            resolved.terminal_at_utc,
            resolved.provider_error_code,
            resolved.provider_error_message,
            resolved.normalized_provider_payload,
            resolved.diagnostic_reason,
        )

    @staticmethod
    def _command_for(request: ProviderReadRequest):
        from .commands import ProviderCommand, ProviderCommandType

        return ProviderCommand(
            request.runtime_instance_id,
            request.provider_id,
            0,
            0,
            request.request_id,
            ProviderCommandType.DIAGNOSTIC,
            request.created_at_utc,
        )
