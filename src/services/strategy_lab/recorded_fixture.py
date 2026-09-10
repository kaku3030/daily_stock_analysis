"""Point-in-time recorded market fixture contracts for Strategy Lab Run B.

Run B is DATA/TEST/SHADOW infrastructure only. Historical provider/source
authority is captured with each fixture and is never reconstructed solely from
the current mutable provider registry. This module does not grant Currentness,
routing, SHADOW_ACTIVE, CORE, LIVE, notification, broker, or trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Mapping

from .replay_baseline import replay
from .replay_contract import (
    EventRecord,
    ReplayResult,
    SourceAuthorityResolution,
    SourceAuthorityResolver,
    aware_utc,
    deep_freeze,
    stable_hash,
)

AUTHORITY_SCHEMA_VERSION = "recorded-authority-v0.1"
FIXTURE_SCHEMA_VERSION = "recorded-market-fixture-v0.1"
AUTHORITY_MODE_EMBEDDED = "EMBEDDED"
REPRESENTATION_NORMALIZED_LICENSED_CSV = "NORMALIZED_FROM_LICENSED_PUBLIC_CSV"

AUTHORITY_DRIFT_NOT_CHECKED = "CURRENT_AUTHORITY_NOT_CHECKED"
AUTHORITY_DRIFT_MATCH = "CURRENT_AUTHORITY_MATCH"
AUTHORITY_DRIFT_MISSING = "CURRENT_AUTHORITY_MISSING"
AUTHORITY_DRIFT_DETECTED = "CURRENT_AUTHORITY_DRIFT"

_AUTHORITY_KEYS = frozenset(
    {
        "schema_version",
        "authority_mode",
        "source_token",
        "endpoint_id",
        "market",
        "adapter_id",
        "upstream_lineage_id",
        "authority_ref",
        "capability_surface",
        "evidence_ref",
        "captured_at",
        "source_commit_sha",
        "source_blob_sha",
        "license_spdx",
        "license_ref",
        "license_blob_sha",
        "digest",
    }
)

_FIXTURE_KEYS = frozenset(
    {
        "schema_version",
        "fixture_id",
        "symbol",
        "interval_label",
        "source_query",
        "query_params",
        "capture_provenance_ref",
        "representation",
        "available_at",
        "observed_at",
        "time_semantics",
        "authority",
        "rows",
        "rows_digest",
        "fixture_digest",
    }
)

_ROW_KEYS = frozenset({"datetime", "open", "high", "low", "close", "volume"})


def _require_exact_keys(payload: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{label} schema mismatch: missing={missing}, extra={extra}")


def _non_empty_trimmed(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a non-empty trimmed string")
    return value


def _parse_aware(value: Any, name: str) -> datetime:
    raw = _non_empty_trimmed(value, name)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO-8601 datetime") from exc
    result = aware_utc(parsed, name)
    assert result is not None
    return result


def _hex_sha(value: Any, name: str, length: int) -> str:
    text = _non_empty_trimmed(value, name)
    if len(text) != length or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{name} must be {length}-char lowercase hex")
    return text


def _validate_numeric_text(value: Any, name: str, *, allow_zero: bool = True) -> str:
    text = _non_empty_trimmed(value, name)
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be finite decimal text") from exc
    if not number.is_finite():
        raise ValueError(f"{name} must be finite decimal text")
    if number < 0 or (not allow_zero and number == 0):
        raise ValueError(f"{name} out of allowed range")
    return text


@dataclass(frozen=True)
class RecordedAuthoritySnapshot:
    schema_version: str
    authority_mode: str
    source_token: str
    endpoint_id: str
    market: str
    adapter_id: str
    upstream_lineage_id: str
    authority_ref: str
    capability_surface: str
    evidence_ref: str
    captured_at: datetime
    source_commit_sha: str
    source_blob_sha: str
    license_spdx: str
    license_ref: str
    license_blob_sha: str
    digest: str

    def __post_init__(self) -> None:
        if self.schema_version != AUTHORITY_SCHEMA_VERSION:
            raise ValueError(f"unsupported authority schema: {self.schema_version}")
        if self.authority_mode != AUTHORITY_MODE_EMBEDDED:
            raise ValueError("Run B A3 supports only embedded capture-time authority")
        for field_name in (
            "source_token",
            "endpoint_id",
            "market",
            "adapter_id",
            "upstream_lineage_id",
            "authority_ref",
            "capability_surface",
            "evidence_ref",
            "license_spdx",
            "license_ref",
        ):
            _non_empty_trimmed(getattr(self, field_name), field_name)
        object.__setattr__(self, "captured_at", aware_utc(self.captured_at, "captured_at"))
        _hex_sha(self.source_commit_sha, "source_commit_sha", 40)
        _hex_sha(self.source_blob_sha, "source_blob_sha", 40)
        _hex_sha(self.license_blob_sha, "license_blob_sha", 40)
        _hex_sha(self.digest, "authority.digest", 64)
        expected = stable_hash(self.digest_payload())
        if self.digest != expected:
            raise ValueError("recorded authority digest mismatch")

    def digest_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authority_mode": self.authority_mode,
            "source_token": self.source_token,
            "endpoint_id": self.endpoint_id,
            "market": self.market,
            "adapter_id": self.adapter_id,
            "upstream_lineage_id": self.upstream_lineage_id,
            "authority_ref": self.authority_ref,
            "capability_surface": self.capability_surface,
            "evidence_ref": self.evidence_ref,
            "captured_at": self.captured_at,
            "source_commit_sha": self.source_commit_sha,
            "source_blob_sha": self.source_blob_sha,
            "license_spdx": self.license_spdx,
            "license_ref": self.license_ref,
            "license_blob_sha": self.license_blob_sha,
        }

    def canonical_payload(self) -> dict[str, Any]:
        return self.digest_payload() | {"digest": self.digest}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RecordedAuthoritySnapshot":
        _require_exact_keys(payload, _AUTHORITY_KEYS, "authority")
        return cls(
            schema_version=payload["schema_version"],
            authority_mode=payload["authority_mode"],
            source_token=payload["source_token"],
            endpoint_id=payload["endpoint_id"],
            market=payload["market"],
            adapter_id=payload["adapter_id"],
            upstream_lineage_id=payload["upstream_lineage_id"],
            authority_ref=payload["authority_ref"],
            capability_surface=payload["capability_surface"],
            evidence_ref=payload["evidence_ref"],
            captured_at=_parse_aware(payload["captured_at"], "authority.captured_at"),
            source_commit_sha=payload["source_commit_sha"],
            source_blob_sha=payload["source_blob_sha"],
            license_spdx=payload["license_spdx"],
            license_ref=payload["license_ref"],
            license_blob_sha=payload["license_blob_sha"],
            digest=payload["digest"],
        )


@dataclass(frozen=True)
class AuthorityDriftDiagnostic:
    status: str
    recorded_authority_digest: str
    current_authority_ref: str | None
    differences: tuple[str, ...]


@dataclass(frozen=True)
class RecordedMarketFixture:
    schema_version: str
    fixture_id: str
    symbol: str
    interval_label: str
    source_query: str
    query_params: Mapping[str, Any]
    capture_provenance_ref: str
    representation: str
    available_at: datetime
    observed_at: datetime
    time_semantics: Mapping[str, Any]
    authority: RecordedAuthoritySnapshot
    rows: tuple[Mapping[str, Any], ...]
    rows_digest: str
    fixture_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != FIXTURE_SCHEMA_VERSION:
            raise ValueError(f"unsupported fixture schema: {self.schema_version}")
        for field_name in (
            "fixture_id",
            "symbol",
            "interval_label",
            "source_query",
            "capture_provenance_ref",
        ):
            _non_empty_trimmed(getattr(self, field_name), field_name)
        if self.representation != REPRESENTATION_NORMALIZED_LICENSED_CSV:
            raise ValueError("unsupported recorded fixture representation")
        object.__setattr__(self, "available_at", aware_utc(self.available_at, "available_at"))
        object.__setattr__(self, "observed_at", aware_utc(self.observed_at, "observed_at"))
        if self.available_at > self.observed_at:
            raise ValueError("available_at cannot be after observed_at")
        if self.authority.captured_at > self.observed_at:
            raise ValueError("authority captured_at cannot be after observed_at")

        object.__setattr__(self, "query_params", deep_freeze(self.query_params))
        object.__setattr__(self, "time_semantics", deep_freeze(self.time_semantics))
        frozen_rows = tuple(deep_freeze(row) for row in self.rows)
        object.__setattr__(self, "rows", frozen_rows)
        if not self.rows:
            raise ValueError("recorded fixture rows must be non-empty")
        for index, row in enumerate(self.rows):
            _require_exact_keys(row, _ROW_KEYS, f"row[{index}]")
            _parse_aware(row["datetime"], f"row[{index}].datetime")
            for field_name in ("open", "high", "low", "close"):
                _validate_numeric_text(row[field_name], f"row[{index}].{field_name}", allow_zero=False)
            _validate_numeric_text(row["volume"], f"row[{index}].volume", allow_zero=True)

        _hex_sha(self.rows_digest, "rows_digest", 64)
        _hex_sha(self.fixture_digest, "fixture_digest", 64)
        expected_rows = stable_hash(self.rows)
        if self.rows_digest != expected_rows:
            raise ValueError("recorded rows digest mismatch")
        expected_fixture = stable_hash(self.digest_payload())
        if self.fixture_digest != expected_fixture:
            raise ValueError("recorded fixture digest mismatch")

    def digest_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fixture_id": self.fixture_id,
            "symbol": self.symbol,
            "interval_label": self.interval_label,
            "source_query": self.source_query,
            "query_params": self.query_params,
            "capture_provenance_ref": self.capture_provenance_ref,
            "representation": self.representation,
            "available_at": self.available_at,
            "observed_at": self.observed_at,
            "time_semantics": self.time_semantics,
            "authority": self.authority.canonical_payload(),
            "rows": self.rows,
            "rows_digest": self.rows_digest,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RecordedMarketFixture":
        if "authority" not in payload:
            raise ValueError("recorded fixture requires capture-time authority")
        _require_exact_keys(payload, _FIXTURE_KEYS, "fixture")
        authority_payload = payload.get("authority")
        if not isinstance(authority_payload, Mapping):
            raise ValueError("recorded fixture requires capture-time authority")
        rows_payload = payload.get("rows")
        if not isinstance(rows_payload, list):
            raise ValueError("recorded fixture rows must be a list")
        return cls(
            schema_version=payload["schema_version"],
            fixture_id=payload["fixture_id"],
            symbol=payload["symbol"],
            interval_label=payload["interval_label"],
            source_query=payload["source_query"],
            query_params=payload["query_params"],
            capture_provenance_ref=payload["capture_provenance_ref"],
            representation=payload["representation"],
            available_at=_parse_aware(payload["available_at"], "available_at"),
            observed_at=_parse_aware(payload["observed_at"], "observed_at"),
            time_semantics=payload["time_semantics"],
            authority=RecordedAuthoritySnapshot.from_mapping(authority_payload),
            rows=tuple(rows_payload),
            rows_digest=payload["rows_digest"],
            fixture_digest=payload["fixture_digest"],
        )

    def historical_authority_resolver(self) -> SourceAuthorityResolver:
        authority = self.authority

        def resolve(source_token: str, endpoint_id: str, market: str) -> SourceAuthorityResolution | None:
            if (
                source_token != authority.source_token
                or endpoint_id != authority.endpoint_id
                or market != authority.market
            ):
                return None
            return SourceAuthorityResolution(
                source_token=authority.source_token,
                endpoint_id=authority.endpoint_id,
                market=authority.market,
                adapter_id=authority.adapter_id,
                upstream_lineage_id=authority.upstream_lineage_id,
                authority_ref=f"{authority.authority_ref}#sha256:{authority.digest}",
            )

        return resolve

    def materialize_events(self) -> tuple[EventRecord, ...]:
        events: list[EventRecord] = []
        authority = self.authority
        timestamp_semantic = self.time_semantics.get("bar_timestamp_semantic", "SOURCE_DECLARED")
        for index, row in enumerate(self.rows):
            event_time = _parse_aware(row["datetime"], f"row[{index}].datetime")
            events.append(
                EventRecord(
                    event_id=(
                        f"recorded:{authority.source_token}:{self.symbol}:"
                        f"{self.interval_label}:{event_time.isoformat()}"
                    ),
                    event_type="RECORDED_MARKET_BAR",
                    entity_id=self.symbol,
                    theme_id=None,
                    occurred_at=event_time,
                    event_time=event_time,
                    published_at=None,
                    available_at=self.available_at,
                    observed_at=self.observed_at,
                    created_at=self.observed_at,
                    source_id=self.source_query,
                    payload={
                        "fixture_id": self.fixture_id,
                        "recorded_authority_digest": authority.digest,
                        "bar_timestamp_semantic": timestamp_semantic,
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                    },
                    trace_id=f"trace:recorded-fixture:{self.fixture_id}",
                    source_kind="PROVIDER",
                    source_token=authority.source_token,
                    endpoint_id=authority.endpoint_id,
                    market=authority.market,
                )
            )
        return tuple(events)


def validate_historical_authority_binding(
    authority: RecordedAuthoritySnapshot,
    resolver: SourceAuthorityResolver,
) -> SourceAuthorityResolution:
    resolution = resolver(authority.source_token, authority.endpoint_id, authority.market)
    expected_ref = f"{authority.authority_ref}#sha256:{authority.digest}"
    if resolution is None:
        raise ValueError("historical authority resolver cannot resolve capture-time binding")
    if (
        resolution.source_token != authority.source_token
        or resolution.endpoint_id != authority.endpoint_id
        or resolution.market != authority.market
        or resolution.adapter_id != authority.adapter_id
        or resolution.upstream_lineage_id != authority.upstream_lineage_id
        or resolution.authority_ref != expected_ref
    ):
        raise ValueError("resolver does not prove capture-time authority")
    return resolution


@dataclass(frozen=True)
class RecordedFixtureReplay:
    replay_result: ReplayResult
    fixture_digest: str
    authority_digest: str
    authority_drift: AuthorityDriftDiagnostic


def diagnose_current_authority(
    authority: RecordedAuthoritySnapshot,
    current_resolver: SourceAuthorityResolver | None,
) -> AuthorityDriftDiagnostic:
    if current_resolver is None:
        return AuthorityDriftDiagnostic(
            status=AUTHORITY_DRIFT_NOT_CHECKED,
            recorded_authority_digest=authority.digest,
            current_authority_ref=None,
            differences=(),
        )
    current = current_resolver(authority.source_token, authority.endpoint_id, authority.market)
    if current is None:
        return AuthorityDriftDiagnostic(
            status=AUTHORITY_DRIFT_MISSING,
            recorded_authority_digest=authority.digest,
            current_authority_ref=None,
            differences=("current_authority_missing",),
        )
    differences = tuple(
        name
        for name, recorded, live in (
            ("source_token", authority.source_token, current.source_token),
            ("endpoint_id", authority.endpoint_id, current.endpoint_id),
            ("market", authority.market, current.market),
            ("adapter_id", authority.adapter_id, current.adapter_id),
            ("upstream_lineage_id", authority.upstream_lineage_id, current.upstream_lineage_id),
        )
        if recorded != live
    )
    return AuthorityDriftDiagnostic(
        status=AUTHORITY_DRIFT_DETECTED if differences else AUTHORITY_DRIFT_MATCH,
        recorded_authority_digest=authority.digest,
        current_authority_ref=current.authority_ref,
        differences=differences,
    )


def replay_recorded_fixture(
    fixture: RecordedMarketFixture,
    decision_clock: datetime,
    *,
    current_authority_resolver: SourceAuthorityResolver | None = None,
    rule_version: str = "run-b-a3-v0.1",
) -> RecordedFixtureReplay:
    historical_resolver = fixture.historical_authority_resolver()
    validate_historical_authority_binding(fixture.authority, historical_resolver)
    result = replay(
        fixture.materialize_events(),
        decision_clock,
        rule_version=rule_version,
        source_authority_resolver=historical_resolver,
    )
    return RecordedFixtureReplay(
        replay_result=result,
        fixture_digest=fixture.fixture_digest,
        authority_digest=fixture.authority.digest,
        authority_drift=diagnose_current_authority(fixture.authority, current_authority_resolver),
    )


def load_recorded_fixture(path: str | Path) -> RecordedMarketFixture:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, Mapping):
        raise ValueError("recorded fixture root must be an object")
    return RecordedMarketFixture.from_mapping(payload)
