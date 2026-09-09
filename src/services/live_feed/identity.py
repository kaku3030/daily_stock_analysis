"""Identity model (frozen contract §4) -- explicit, non-conflated counters.

`runtime_instance_id`, `controller_generation`, `desired_registry_revision`,
`stream_subscription_epoch`, and command identifiers must never substitute
for one another. This module defines the standalone value types; the
registry (registry.py) owns its own revision/epoch counters directly since
they are simple monotonic integers scoped to registry mutation, and
`ControllerGeneration` is exposed here because the controller advances it
independently of any registry mutation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


def new_runtime_instance_id() -> str:
    """Random UUID per controller/runtime instance -- not durable business
    identity, never persisted as live truth.
    """

    return str(uuid.uuid4())


def new_command_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class ControllerGeneration:
    """Controller-owned recovery/transport-incarnation counter.

    This is NOT: a Futu OpenQuoteContext object identity, a Futu SDK
    conn_id, or a counter that advances per SDK-private retry attempt
    (see FUTU_SEMANTIC_CONTRACT_V0_1.md and the Futu implementation spec
    §A5/§B1 for the evidence behind this separation). This slice defines
    only the value type and its controlled advancement method -- exact
    Futu reconnect-generation allocation policy is out of scope here.
    """

    value: int

    @staticmethod
    def initial() -> "ControllerGeneration":
        return ControllerGeneration(0)

    def advance(self) -> "ControllerGeneration":
        return ControllerGeneration(self.value + 1)
