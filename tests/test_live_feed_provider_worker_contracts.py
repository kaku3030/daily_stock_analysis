"""Mechanical contract tests for Provider Worker Supervisor V0.1 -- Slice A.

Anti-shrink tests pin exact enum member names/order/values and exact
dataclass field names/order for every frozen shape, so the contract cannot
silently drift. Validation tests prove the frozen invariants fail closed.
Negative architecture tests prove no process/provider runtime behavior
leaked into the contract module.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as _dt
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import pytest

from data_provider.live_feed_types import OpaqueUnsupportedPayload
from src.services.live_feed.commands import ProviderCommand, ProviderCommandType
from src.services.live_feed.provider_worker_contracts import (
    ProviderExceptionDisposition,
    ProviderExecutionOutcome,
    ProviderWorkerEvidenceKind,
    ProviderWorkerLifecycleEvidence,
    ProviderWorkerSupervisorConfig,
    ResolvedProviderCommandOutcome,
)

# ---------------------------------------------------------------------------
# Shared builders
# ---------------------------------------------------------------------------

NOW_UTC = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)

ALL_COMMAND_TYPES = tuple(ProviderCommandType)


def _command(
    *,
    runtime_instance_id: str = "runtime-1",
    provider_id: str = "futu",
    controller_generation: int = 0,
    command_type: ProviderCommandType = ProviderCommandType.SUBSCRIBE,
) -> ProviderCommand:
    return ProviderCommand(
        runtime_instance_id=runtime_instance_id,
        provider_id=provider_id,
        controller_generation=controller_generation,
        desired_registry_revision=7,
        command_id="cmd-1",
        command_type=command_type,
        created_at=NOW_UTC,
    )


def _valid_outcome(**overrides) -> ResolvedProviderCommandOutcome:
    fields_dict = dict(
        runtime_instance_id="runtime-1",
        provider_id="futu",
        worker_generation=1,
        command=_command(),
        outcome=ProviderExecutionOutcome.SUCCEEDED,
        dispatched_at_monotonic_ns=1_000,
        terminal_observed_at_monotonic_ns=2_000,
        terminal_at_utc=NOW_UTC,
    )
    fields_dict.update(overrides)
    return ResolvedProviderCommandOutcome(**fields_dict)


def _valid_lifecycle(**overrides) -> ProviderWorkerLifecycleEvidence:
    fields_dict = dict(
        runtime_instance_id="runtime-1",
        provider_id="futu",
        worker_generation=1,
        kind=ProviderWorkerEvidenceKind.WORKER_RUNTIME_READY,
        observed_at_monotonic_ns=5_000,
        observed_at_utc=NOW_UTC,
    )
    fields_dict.update(overrides)
    return ProviderWorkerLifecycleEvidence(**fields_dict)


def _valid_config(**overrides) -> ProviderWorkerSupervisorConfig:
    fields_dict = dict(
        startup_timeout_seconds=30.0,
        command_timeout_seconds={command_type: 15.0 for command_type in ALL_COMMAND_TYPES},
        graceful_shutdown_timeout_seconds=5.0,
        terminate_join_timeout_seconds=2.0,
        kill_join_timeout_seconds=2.0,
        parent_command_queue_capacity=128,
        child_data_queue_capacity=1024,
        child_priority_queue_capacity=256,
        supervisor_inbox_capacity=512,
        max_frame_bytes=65536,
        protocol_version=1,
    )
    fields_dict.update(overrides)
    return ProviderWorkerSupervisorConfig(**fields_dict)


def _all_types_config() -> dict:
    return {command_type: 15.0 for command_type in ALL_COMMAND_TYPES}


# ---------------------------------------------------------------------------
# Exact enum shape (names / order / values) -- anti-shrink
# ---------------------------------------------------------------------------


def test_provider_execution_outcome_exact_shape() -> None:
    expected = (
        ("SUCCEEDED", "SUCCEEDED"),
        ("PROVIDER_REJECTED", "PROVIDER_REJECTED"),
        ("PROVIDER_EXCEPTION", "PROVIDER_EXCEPTION"),
        ("TIMEOUT", "TIMEOUT"),
        ("WORKER_EXITED", "WORKER_EXITED"),
        ("PROTOCOL_ERROR", "PROTOCOL_ERROR"),
        ("CANCELLED_SHUTDOWN", "CANCELLED_SHUTDOWN"),
        ("CANCELLED_GENERATION_INVALIDATED", "CANCELLED_GENERATION_INVALIDATED"),
    )
    assert [(m.name, m.value) for m in ProviderExecutionOutcome] == list(expected)
    # no aliases: every member name maps to a unique value
    assert len({m.value for m in ProviderExecutionOutcome}) == len(list(ProviderExecutionOutcome))


def test_provider_worker_evidence_kind_exact_shape() -> None:
    expected = (
        ("WORKER_RUNTIME_STARTED", "WORKER_RUNTIME_STARTED"),
        ("WORKER_RUNTIME_READY", "WORKER_RUNTIME_READY"),
        ("WORKER_INIT_FAILED", "WORKER_INIT_FAILED"),
        ("WORKER_STARTUP_TIMEOUT", "WORKER_STARTUP_TIMEOUT"),
        ("WORKER_EXITED", "WORKER_EXITED"),
        ("WORKER_TIMEOUT_KILLED", "WORKER_TIMEOUT_KILLED"),
        ("WORKER_PROTOCOL_FATAL", "WORKER_PROTOCOL_FATAL"),
        ("WORKER_KILL_FAILED", "WORKER_KILL_FAILED"),
        ("WORKER_SHUTDOWN_COMPLETED", "WORKER_SHUTDOWN_COMPLETED"),
    )
    assert [(m.name, m.value) for m in ProviderWorkerEvidenceKind] == list(expected)
    assert len({m.value for m in ProviderWorkerEvidenceKind}) == len(list(ProviderWorkerEvidenceKind))


def test_provider_exception_disposition_exact_shape() -> None:
    expected = (
        ("WORKER_REUSABLE", "WORKER_REUSABLE"),
        ("GENERATION_FATAL", "GENERATION_FATAL"),
    )
    assert [(m.name, m.value) for m in ProviderExceptionDisposition] == list(expected)
    assert len({m.value for m in ProviderExceptionDisposition}) == len(list(ProviderExceptionDisposition))


# ---------------------------------------------------------------------------
# Exact dataclass field names / order -- anti-shrink
# ---------------------------------------------------------------------------


def test_resolved_outcome_exact_field_order() -> None:
    assert [f.name for f in fields(ResolvedProviderCommandOutcome)] == [
        "runtime_instance_id",
        "provider_id",
        "worker_generation",
        "command",
        "outcome",
        "dispatched_at_monotonic_ns",
        "terminal_observed_at_monotonic_ns",
        "terminal_at_utc",
        "provider_error_code",
        "provider_error_message",
        "normalized_provider_payload",
        "diagnostic_reason",
        "local_enqueue_seq",
    ]


def test_lifecycle_evidence_exact_field_order() -> None:
    assert [f.name for f in fields(ProviderWorkerLifecycleEvidence)] == [
        "runtime_instance_id",
        "provider_id",
        "worker_generation",
        "kind",
        "observed_at_monotonic_ns",
        "observed_at_utc",
        "process_pid",
        "exit_code",
        "diagnostic_reason",
        "local_enqueue_seq",
    ]


def test_supervisor_config_exact_field_order() -> None:
    assert [f.name for f in fields(ProviderWorkerSupervisorConfig)] == [
        "startup_timeout_seconds",
        "command_timeout_seconds",
        "graceful_shutdown_timeout_seconds",
        "terminate_join_timeout_seconds",
        "kill_join_timeout_seconds",
        "parent_command_queue_capacity",
        "child_data_queue_capacity",
        "child_priority_queue_capacity",
        "supervisor_inbox_capacity",
        "max_frame_bytes",
        "protocol_version",
    ]


def test_all_three_dataclasses_are_frozen() -> None:
    outcome = _valid_outcome()
    lifecycle = _valid_lifecycle()
    config = _valid_config()
    with pytest.raises(FrozenInstanceError):
        outcome.outcome = ProviderExecutionOutcome.TIMEOUT  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        lifecycle.kind = ProviderWorkerEvidenceKind.WORKER_EXITED  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        config.protocol_version = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Public export set (module + package re-export) -- anti-shrink
# ---------------------------------------------------------------------------


def test_module_public_export_set_exact() -> None:
    import src.services.live_feed.provider_worker_contracts as module

    assert module.__all__ == [
        "ProviderExceptionDisposition",
        "ProviderExecutionOutcome",
        "ProviderWorkerEvidenceKind",
        "ProviderWorkerLifecycleEvidence",
        "ProviderWorkerSupervisorConfig",
        "ResolvedProviderCommandOutcome",
    ]


def test_package_re_exports_provider_worker_contracts() -> None:
    import src.services.live_feed as live_feed

    for name in (
        "ProviderExceptionDisposition",
        "ProviderExecutionOutcome",
        "ProviderWorkerEvidenceKind",
        "ProviderWorkerLifecycleEvidence",
        "ProviderWorkerSupervisorConfig",
        "ResolvedProviderCommandOutcome",
    ):
        assert name in live_feed.__all__
        assert getattr(live_feed, name) is getattr(
            __import__("src.services.live_feed.provider_worker_contracts", fromlist=[name]), name
        )


# ---------------------------------------------------------------------------
# Identity / generation / clock validation (both domain types)
# ---------------------------------------------------------------------------


def test_blank_identities_rejected() -> None:
    with pytest.raises(ValueError):
        _valid_outcome(runtime_instance_id="   ")
    with pytest.raises(ValueError):
        _valid_outcome(provider_id="")
    with pytest.raises(ValueError):
        _valid_lifecycle(runtime_instance_id="  ")
    with pytest.raises(ValueError):
        _valid_lifecycle(provider_id="")


def test_worker_generation_must_be_positive_and_not_bool() -> None:
    for bad in (0, -1):
        with pytest.raises(ValueError):
            _valid_outcome(worker_generation=bad)
        with pytest.raises(ValueError):
            _valid_lifecycle(worker_generation=bad)
    with pytest.raises(ValueError):
        _valid_outcome(worker_generation=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _valid_lifecycle(worker_generation=False)  # type: ignore[arg-type]


def test_negative_monotonic_timestamp_rejected() -> None:
    with pytest.raises(ValueError):
        _valid_outcome(terminal_observed_at_monotonic_ns=-1)
    with pytest.raises(ValueError):
        _valid_outcome(dispatched_at_monotonic_ns=-5)
    with pytest.raises(ValueError):
        _valid_lifecycle(observed_at_monotonic_ns=-1)
    with pytest.raises(ValueError):
        _valid_outcome(terminal_observed_at_monotonic_ns=True)  # type: ignore[arg-type]


def test_naive_datetime_rejected() -> None:
    naive = datetime(2026, 9, 9, 12, 0, 0)
    with pytest.raises(ValueError):
        _valid_outcome(terminal_at_utc=naive)
    with pytest.raises(ValueError):
        _valid_lifecycle(observed_at_utc=naive)


def test_aware_datetime_with_unusable_utcoffset_rejected() -> None:
    class _UnusableTz(_dt.tzinfo):
        def utcoffset(self, dt):  # type: ignore[no-untyped-def]
            return None

    with pytest.raises(ValueError):
        _valid_outcome(terminal_at_utc=datetime(2026, 9, 9, 12, 0, tzinfo=_UnusableTz()))
    with pytest.raises(ValueError):
        _valid_lifecycle(observed_at_utc=datetime(2026, 9, 9, 12, 0, tzinfo=_UnusableTz()))


def test_non_utc_aware_datetime_is_accepted_and_canonicalizable() -> None:
    # Aware with a usable offset (EST) is acceptable; it must be canonicalizable to UTC.
    est = timezone(timedelta(hours=-5))
    outcome = _valid_outcome(terminal_at_utc=datetime(2026, 9, 9, 7, 0, 0, tzinfo=est))
    assert outcome.terminal_at_utc.astimezone(timezone.utc).hour == 12


def test_local_enqueue_seq_none_or_positive_only() -> None:
    # Pre-ingress (None) is the default and is valid.
    assert _valid_outcome().local_enqueue_seq is None
    assert _valid_lifecycle().local_enqueue_seq is None
    # Positive stamped values are permitted (dataclasses.replace revalidates).
    assert _valid_outcome(local_enqueue_seq=1).local_enqueue_seq == 1
    assert _valid_lifecycle(local_enqueue_seq=42).local_enqueue_seq == 42
    # Negative / zero / bool are rejected, never silently accepted.
    for bad in (0, -1, True):  # type: ignore[assignment]
        with pytest.raises(ValueError):
            _valid_outcome(local_enqueue_seq=bad)
        with pytest.raises(ValueError):
            _valid_lifecycle(local_enqueue_seq=bad)


def test_replace_stamping_revalidates() -> None:
    import dataclasses

    outcome = _valid_outcome()
    stamped = dataclasses.replace(outcome, local_enqueue_seq=7)
    assert stamped.local_enqueue_seq == 7
    with pytest.raises(ValueError):
        dataclasses.replace(outcome, local_enqueue_seq=-7)


# ---------------------------------------------------------------------------
# ResolvedProviderCommandOutcome invariants
# ---------------------------------------------------------------------------


def test_outcome_rejects_non_provider_command() -> None:
    with pytest.raises(ValueError):
        _valid_outcome(command="not-a-command")  # type: ignore[arg-type]


def test_outcome_rejects_cross_context_identity_mismatch() -> None:
    with pytest.raises(ValueError):
        _valid_outcome(runtime_instance_id="other-runtime")  # command says runtime-1
    with pytest.raises(ValueError):
        _valid_outcome(provider_id="xtquant")  # command says futu


def test_outcome_rejects_raw_string_enum_values() -> None:
    with pytest.raises(ValueError):
        _valid_outcome(outcome="SUCCEEDED")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _valid_lifecycle(kind="WORKER_RUNTIME_READY")  # type: ignore[arg-type]


def test_outcome_requires_dispatched_for_executed_outcomes() -> None:
    for outcome in (
        ProviderExecutionOutcome.SUCCEEDED,
        ProviderExecutionOutcome.PROVIDER_REJECTED,
        ProviderExecutionOutcome.PROVIDER_EXCEPTION,
        ProviderExecutionOutcome.TIMEOUT,
        ProviderExecutionOutcome.WORKER_EXITED,
        ProviderExecutionOutcome.PROTOCOL_ERROR,
    ):
        with pytest.raises(ValueError):
            _valid_outcome(outcome=outcome, dispatched_at_monotonic_ns=None)


def test_outcome_allows_missing_dispatch_only_for_never_dispatched_cancellations() -> None:
    for outcome in (
        ProviderExecutionOutcome.CANCELLED_SHUTDOWN,
        ProviderExecutionOutcome.CANCELLED_GENERATION_INVALIDATED,
    ):
        result = _valid_outcome(outcome=outcome, dispatched_at_monotonic_ns=None)
        assert result.outcome is outcome


def test_outcome_terminal_must_not_precede_dispatched() -> None:
    with pytest.raises(ValueError):
        _valid_outcome(
            dispatched_at_monotonic_ns=5_000,
            terminal_observed_at_monotonic_ns=4_000,
        )


def test_outcome_requires_payload_to_be_mapping_and_frozen() -> None:
    with pytest.raises(ValueError):
        _valid_outcome(normalized_provider_payload=[1, 2, 3])  # type: ignore[arg-type]
    result = _valid_outcome(normalized_provider_payload={"a": 1})
    assert isinstance(result.normalized_provider_payload, Mapping)
    assert isinstance(result.normalized_provider_payload, MappingProxyType)


# ---------------------------------------------------------------------------
# Payload immutability (freeze §16 / Brief §6)
# ---------------------------------------------------------------------------


def test_nested_payload_caller_mutation_cannot_alter_stored_evidence() -> None:
    payload: dict = {"nested": {"list": [1, 2, {"deep": "x"}]}}
    result = _valid_outcome(normalized_provider_payload=payload)
    # Mutate every caller alias afterward.
    payload["nested"]["list"].append(999)
    payload["nested"]["list"][2]["deep"] = "mutated"
    payload["new_key"] = "leaked"
    stored = result.normalized_provider_payload
    assert stored["nested"]["list"] == (1, 2, stored["nested"]["list"][2])
    assert stored["nested"]["list"][2]["deep"] == "x"
    assert "new_key" not in stored
    # stored remains read-only at every nesting level
    with pytest.raises(TypeError):
        stored["nested"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        stored["nested"]["list"] = ()  # type: ignore[index]


def test_unsupported_provider_native_object_becomes_opaque_marker() -> None:
    class _ProviderNative:
        pass

    result = _valid_outcome(normalized_provider_payload={"native": _ProviderNative()})
    marker = result.normalized_provider_payload["native"]
    assert isinstance(marker, OpaqueUnsupportedPayload)
    assert marker.type_name == "_ProviderNative"


# ---------------------------------------------------------------------------
# ProviderWorkerLifecycleEvidence invariants
# ---------------------------------------------------------------------------


def test_lifecycle_pid_must_be_positive_and_not_bool() -> None:
    for bad in (0, -1, True):  # type: ignore[assignment]
        with pytest.raises(ValueError):
            _valid_lifecycle(process_pid=bad)


def test_lifecycle_exit_code_diagnostic_allows_any_int_but_not_bool() -> None:
    # negative / zero / positive all valid diagnostics
    assert _valid_lifecycle(exit_code=-9).exit_code == -9
    assert _valid_lifecycle(exit_code=0).exit_code == 0
    assert _valid_lifecycle(exit_code=1).exit_code == 1
    with pytest.raises(ValueError):
        _valid_lifecycle(exit_code=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _valid_lifecycle(exit_code=1.5)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Supervisor config invariants
# ---------------------------------------------------------------------------


def test_config_valid_and_immutable_mapping() -> None:
    config = _valid_config()
    assert config.command_timeout_seconds == _all_types_config()
    assert isinstance(config.command_timeout_seconds, MappingProxyType)
    with pytest.raises(TypeError):
        config.command_timeout_seconds[ProviderCommandType.CONNECT] = 99.0  # type: ignore[index]


def test_config_timeout_finite_and_positive() -> None:
    for bad in (0.0, -1.0, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            _valid_config(startup_timeout_seconds=bad)
        with pytest.raises(ValueError):
            _valid_config(graceful_shutdown_timeout_seconds=bad)
        with pytest.raises(ValueError):
            _valid_config(terminate_join_timeout_seconds=bad)
        with pytest.raises(ValueError):
            _valid_config(kill_join_timeout_seconds=bad)
        with pytest.raises(ValueError):
            _valid_config(command_timeout_seconds={t: bad for t in ALL_COMMAND_TYPES})


def test_config_bool_rejected_for_integer_fields() -> None:
    for field_name in (
        "parent_command_queue_capacity",
        "child_data_queue_capacity",
        "child_priority_queue_capacity",
        "supervisor_inbox_capacity",
        "max_frame_bytes",
        "protocol_version",
    ):
        with pytest.raises(ValueError):
            _valid_config(**{field_name: True})  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            _valid_config(**{field_name: False})  # type: ignore[arg-type]


def test_config_capacity_protocol_must_be_positive_int() -> None:
    for field_name in (
        "parent_command_queue_capacity",
        "child_data_queue_capacity",
        "child_priority_queue_capacity",
        "supervisor_inbox_capacity",
        "max_frame_bytes",
    ):
        for bad in (0, -1):
            with pytest.raises(ValueError):
                _valid_config(**{field_name: bad})
        with pytest.raises(ValueError):
            _valid_config(**{field_name: 1.5})  # type: ignore[arg-type]
    for bad in (0, -1):
        with pytest.raises(ValueError):
            _valid_config(protocol_version=bad)


def test_config_command_timeout_missing_member_rejected() -> None:
    mapping = _all_types_config()
    del mapping[ProviderCommandType.CLOSE]
    with pytest.raises(ValueError) as excinfo:
        _valid_config(command_timeout_seconds=mapping)
    assert "CLOSE" in str(excinfo.value)


def test_config_command_timeout_raw_string_key_rejected() -> None:
    # All keys as raw strings (hash-equal to the enum members). None is a
    # ProviderCommandType instance, so construction must fail closed rather
    # than coercing by value.
    mapping = {t.value: 15.0 for t in ALL_COMMAND_TYPES}
    with pytest.raises(ValueError):
        _valid_config(command_timeout_seconds=mapping)  # type: ignore[arg-type]


def test_config_command_timeout_foreign_enum_key_rejected() -> None:
    # A foreign str-Enum member is NOT a ProviderCommandType instance -- it
    # must be rejected as a foreign key rather than coerced by value. Its
    # value ("HACK") does not collide with any real member name.
    from enum import Enum

    class _ForeignCommandType(str, Enum):
        HACK = "HACK"

    mapping = _all_types_config()
    mapping[_ForeignCommandType.HACK] = 15.0  # type: ignore[assignment]
    with pytest.raises(ValueError):
        _valid_config(command_timeout_seconds=mapping)


def test_config_caller_mutation_of_source_mapping_cannot_change_config() -> None:
    source = _all_types_config()
    config = _valid_config(command_timeout_seconds=source)
    source[ProviderCommandType.CONNECT] = 999.0
    source["injected"] = 1.0  # type: ignore[index]
    assert config.command_timeout_seconds[ProviderCommandType.CONNECT] == 15.0
    assert "injected" not in config.command_timeout_seconds


def test_config_no_default_values_and_no_shared_state_between_instances() -> None:
    config_a = _valid_config(command_timeout_seconds={t: 5.0 for t in ALL_COMMAND_TYPES})
    config_b = _valid_config(command_timeout_seconds={t: 9.0 for t in ALL_COMMAND_TYPES})
    # no shared mapping object across instances
    assert config_a.command_timeout_seconds is not config_b.command_timeout_seconds
    assert config_a.command_timeout_seconds[ProviderCommandType.CONNECT] == 5.0
    assert config_b.command_timeout_seconds[ProviderCommandType.CONNECT] == 9.0
    # every config field is required (no default)
    for f in fields(ProviderWorkerSupervisorConfig):
        assert f.default is dataclasses.MISSING
        assert f.default_factory is dataclasses.MISSING


# ---------------------------------------------------------------------------
# Deterministic equality / serialization behavior
# ---------------------------------------------------------------------------


def test_equal_construction_yields_equal_objects() -> None:
    a = _valid_outcome(normalized_provider_payload={"x": [1, 2]})
    b = _valid_outcome(normalized_provider_payload={"x": [1, 2]})
    assert a == b
    assert repr(a) == repr(b)


def test_config_equal_construction_yields_equal_objects() -> None:
    assert _valid_config() == _valid_config()


# ---------------------------------------------------------------------------
# Negative architecture tests (AST import/usage boundary)
# ---------------------------------------------------------------------------

FORBIDDEN_IMPORT_TOKENS = (
    "multiprocessing",
    "subprocess",
    "futu",
    "threading",
    "socket",
)


def test_contract_module_imports_no_runtime_or_provider_modules() -> None:
    module_path = Path(__file__).resolve().parents[1] / "src" / "services" / "live_feed" / "provider_worker_contracts.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
            for alias in node.names:
                imported.add(alias.name)
    for token in FORBIDDEN_IMPORT_TOKENS:
        assert token not in imported, f"forbidden import leaked into Slice A: {token}"


def test_contract_module_imports_only_expected_sources() -> None:
    module_path = Path(__file__).resolve().parents[1] / "src" / "services" / "live_feed" / "provider_worker_contracts.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # relative `from .commands import X` has node.module == "commands"
            root = (node.module or "").split(".")[0]
            if root:
                imported.add(root)
    # Allowed roots: stdlib + data_provider (freeze_normalized_payload) +
    # the sibling commands module. Everything else is a boundary violation.
    assert imported <= {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "math",
        "types",
        "typing",
        "data_provider",
        "commands",
    }


def test_contract_module_has_no_runtime_mechanism_call_sites() -> None:
    module_path = Path(__file__).resolve().parents[1] / "src" / "services" / "live_feed" / "provider_worker_contracts.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    source = module_path.read_text(encoding="utf-8")
    for token in ("Process(", "Popen", "spawn", "Pipe(", "Queue(", "Thread(", "exec("):
        assert token not in source, f"runtime mechanism call site leaked into Slice A: {token}"
