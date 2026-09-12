"""Permanent regression tests for Slice A evidence-string type integrity.

This is a narrow Harvest hardening test. It does not extend the public
Provider Worker contract or introduce runtime worker behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.services.live_feed.commands import ProviderCommand, ProviderCommandType
from src.services.live_feed.provider_worker_contracts import (
    ProviderExecutionOutcome,
    ResolvedProviderCommandOutcome,
)


NOW_UTC = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _command() -> ProviderCommand:
    return ProviderCommand(
        runtime_instance_id="runtime-1",
        provider_id="futu",
        controller_generation=0,
        desired_registry_revision=7,
        command_id="cmd-1",
        command_type=ProviderCommandType.SUBSCRIBE,
        created_at=NOW_UTC,
    )


def _outcome(**overrides) -> ResolvedProviderCommandOutcome:
    values = {
        "runtime_instance_id": "runtime-1",
        "provider_id": "futu",
        "worker_generation": 1,
        "command": _command(),
        "outcome": ProviderExecutionOutcome.SUCCEEDED,
        "dispatched_at_monotonic_ns": 1_000,
        "terminal_observed_at_monotonic_ns": 2_000,
        "terminal_at_utc": NOW_UTC,
    }
    values.update(overrides)
    return ResolvedProviderCommandOutcome(**values)


@pytest.mark.parametrize(
    "field_name",
    ("provider_error_code", "provider_error_message", "diagnostic_reason"),
)
def test_optional_evidence_string_fields_accept_none_and_strings(field_name: str) -> None:
    assert getattr(_outcome(**{field_name: None}), field_name) is None
    assert getattr(_outcome(**{field_name: "evidence"}), field_name) == "evidence"
    # Empty strings remain strings; non-blank semantics were not part of the
    # frozen field contract and are deliberately not invented by this repair.
    assert getattr(_outcome(**{field_name: ""}), field_name) == ""


@pytest.mark.parametrize(
    "field_name",
    ("provider_error_code", "provider_error_message", "diagnostic_reason"),
)
@pytest.mark.parametrize(
    "bad_value",
    (0, 1, True, False, b"bytes", [], {}, object()),
)
def test_optional_evidence_string_fields_reject_non_strings(
    field_name: str, bad_value: object
) -> None:
    with pytest.raises(ValueError, match=rf"^{field_name} must be a str when present$"):
        _outcome(**{field_name: bad_value})
