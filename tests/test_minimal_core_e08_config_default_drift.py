"""Shadow evidence for Minimal Core E08 config-default duplication.

The test only compares fields whose current defaults are intended to represent
the same fact across runtime constants, UI registry metadata, and .env.example.
It intentionally excludes fields such as STOCK_LIST where runtime default and
UI/example seed have different semantics.
"""

from __future__ import annotations

from pathlib import Path

from src.core.config_registry import _FIELD_DEFINITIONS
from src.llm.backend_registry import LITELLM_BACKEND_ID
from src.llm.local_cli_backend import (
    DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY,
    DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY,
    DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES,
    DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS,
)


_SHADOW_DEFAULTS = {
    "GENERATION_BACKEND": str(LITELLM_BACKEND_ID),
    "GENERATION_BACKEND_TIMEOUT_SECONDS": str(DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS),
    "GENERATION_BACKEND_MAX_OUTPUT_BYTES": str(DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES),
    "GENERATION_BACKEND_MAX_CONCURRENCY": str(DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY),
    "LOCAL_CLI_BACKEND_MAX_CONCURRENCY": str(DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY),
}


def _env_example_values() -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / ".env.example"
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_e08_shared_backend_defaults_do_not_drift_across_surfaces() -> None:
    env_values = _env_example_values()

    for field_name, runtime_default in _SHADOW_DEFAULTS.items():
        assert str(_FIELD_DEFINITIONS[field_name]["default_value"]) == runtime_default
        assert env_values[field_name] == runtime_default


def test_e08_imported_constant_shadow_has_no_behavioral_delta_for_surface_defaults() -> None:
    """Model registry/example projection from the existing runtime owner only."""
    env_values = _env_example_values()
    current = {
        field: (str(_FIELD_DEFINITIONS[field]["default_value"]), env_values[field])
        for field in _SHADOW_DEFAULTS
    }
    imported_constant_shadow = {
        field: (value, value) for field, value in _SHADOW_DEFAULTS.items()
    }
    assert current == imported_constant_shadow


def test_e08_protected_roles_reject_imported_constant_collapse() -> None:
    """Empty runtime fallback and UI/example seed are intentionally different."""
    assert _FIELD_DEFINITIONS["STOCK_LIST"]["default_value"]
    assert _FIELD_DEFINITIONS["STOCK_LIST"]["validation"] == {"min_items": 1}
    assert _FIELD_DEFINITIONS["GENERATION_FALLBACK_BACKEND"]["default_value"] == "litellm"


def test_e08_stock_list_is_not_falsely_treated_as_one_shared_runtime_default() -> None:
    env_values = _env_example_values()

    # Registry and .env.example intentionally provide the same seed/example.
    # Runtime Config resolution, however, defaults STOCK_LIST to empty and
    # validates that an operator configured at least one symbol. This test
    # records the distinction so a future one-schema refactor cannot silently
    # turn an example seed into an authoritative runtime fallback.
    assert _FIELD_DEFINITIONS["STOCK_LIST"]["default_value"] == "600519,300750,002594"
    assert env_values["STOCK_LIST"] == "600519,300750,002594"
