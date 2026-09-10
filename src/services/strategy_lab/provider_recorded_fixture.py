"""A4b provider-recorded fixture binding for Strategy Lab research.

This module bridges only verified A4 raw-capture evidence into a deterministic
provider-recorded historical fixture.  It deliberately does *not* weaken A3's
static/licensed GitHub-source RecordedMarketFixture specialization, and it does
not establish Currentness, routing, session truth, SHADOW_ACTIVE, CORE, LIVE,
strategy, broker, BUY/SELL, or trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from src.services.a_share_intraday_semantics import CN_INTRADAY_ENDPOINT_EXTENSIONS
from src.services.a_share_provider_lineage import CN_REALTIME_SOURCE_LINEAGE

from .raw_capture import (
    NormalizationLineage,
    SealedRawCapture,
    build_row_normalization_lineage,
)
from .recorded_fixture import _ROW_KEYS, _decimal_text, _parse_aware, _require_exact_keys
from .replay_contract import (
    EventRecord,
    SourceAuthorityResolution,
    SourceAuthorityResolver,
    aware_utc,
    deep_freeze,
    stable_hash,
)

CAPTURED_PROVIDER_AUTHORITY_SCHEMA_VERSION = "captured-provider-authority-v0.1"
PROVIDER_RECORDED_FIXTURE_SCHEMA_VERSION = "provider-recorded-fixture-v0.1"
NORMALIZER_VERSION = "canonical-aware-ohlcv-v0.1"
NORMALIZER_SPEC = {
    "input": ["datetime", "open", "high", "low", "close", "volume"],
    "datetime": "timezone-aware ISO-8601; normalized to UTC",
    "numeric": "finite decimal text; OHLC > 0; volume >= 0; no numeric coercion",
    "session_semantics": "NOT_CLAIMED",
}
NORMALIZER_SHA256 = stable_hash(NORMALIZER_SPEC)

# V0.1 is intentionally pinned to the exact accepted A0/A1 authority source
# versions reviewed before this slice.  A future authority revision requires a
# new contract version rather than silently reinterpreting old captured evidence.
A0_AUTHORITY_SOURCE_REF = (
    "github://kaku3030/stock-razor/src/services/a_share_provider_lineage.py"
    "?ref=54250eba6eb64362ea8ac55c383ad6a589ca59ad"
    "#blob=0fb48eb3a0c0d4050623d625b6695f3229d56d5d"
)
A1_AUTHORITY_SOURCE_REF = (
    "github://kaku3030/stock-razor/src/services/a_share_intraday_semantics.py"
    "?ref=37c07fdce2cb1e30283bbb83f1e58a23bca55c1d"
    "#blob=d366e5bd0a6b3b6cf1830b6bc9fdbaf93e64b91c"
)
A0_ACCEPTED_REGISTRY_DIGEST = "7e05f0c57287b61fafe502d5a1b355a80106a7f8ad102c3fedf78db5dc356e3e"
A1_ACCEPTED_EXTENSION_DIGEST = "e703ed7fbc512a84c848bd021ec6b1b5e44fb41595d4c5a297bb7e40b68d24f2"


def _trimmed(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a non-empty trimmed string")
    return value


def _hex(value: Any, name: str, length: int = 64) -> str:
    text = _trimmed(value, name)
    if len(text) != length or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{name} must be {length}-char lowercase hex")
    return text


def _authority_registry_payload() -> dict[str, Mapping[str, object]]:
    return {
        token: CN_REALTIME_SOURCE_LINEAGE[token].to_dict()
        for token in sorted(CN_REALTIME_SOURCE_LINEAGE)
    }


def _intraday_extension_payload() -> dict[str, list[str]]:
    return {
        token: sorted(CN_INTRADAY_ENDPOINT_EXTENSIONS[token])
        for token in sorted(CN_INTRADAY_ENDPOINT_EXTENSIONS)
    }


def _assert_capture_authority_sources_still_match_accepted_versions() -> None:
    """Guard only the *capture* factory, never historical replay/load.

    Historical evidence must remain replayable after current authority drifts.
    New capture, however, must not claim the old A0/A1 source refs if the live
    in-repository authority has moved.
    """

    if stable_hash(_authority_registry_payload()) != A0_ACCEPTED_REGISTRY_DIGEST:
        raise RuntimeError("A0 provider authority changed; bump captured-authority contract")
    if stable_hash(_intraday_extension_payload()) != A1_ACCEPTED_EXTENSION_DIGEST:
        raise RuntimeError("A1 intraday authority changed; bump captured-authority contract")


@dataclass(frozen=True)
class CapturedProviderAuthorityEvidence:
    schema_version: str
    source_token: str
    endpoint_id: str
    market: str
    adapter_id: str
    upstream_lineage_id: str
    captured_at: datetime
    raw_artifact_sha256: str
    capture_id: str
    observation_id: str
    a0_authority_source_ref: str
    a1_authority_source_ref: str
    digest: str

    def __post_init__(self) -> None:
        if self.schema_version != CAPTURED_PROVIDER_AUTHORITY_SCHEMA_VERSION:
            raise ValueError(f"unsupported captured provider authority: {self.schema_version}")
        for name in (
            "source_token",
            "endpoint_id",
            "market",
            "adapter_id",
            "upstream_lineage_id",
            "capture_id",
            "observation_id",
            "a0_authority_source_ref",
            "a1_authority_source_ref",
        ):
            _trimmed(getattr(self, name), name)
        if self.market != "cn":
            raise ValueError("A4b V0.2 first slice supports A-share market='cn' only")
        captured = aware_utc(self.captured_at, "captured_at")
        assert captured is not None
        object.__setattr__(self, "captured_at", captured)
        _hex(self.raw_artifact_sha256, "raw_artifact_sha256")
        _hex(self.digest, "captured authority digest")
        if self.a0_authority_source_ref != A0_AUTHORITY_SOURCE_REF:
            raise ValueError("captured authority does not pin accepted A0 source version")
        if self.a1_authority_source_ref != A1_AUTHORITY_SOURCE_REF:
            raise ValueError("captured authority does not pin accepted A1 source version")
        if self.digest != stable_hash(self.digest_payload()):
            raise ValueError("captured provider authority digest mismatch")

    def digest_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_token": self.source_token,
            "endpoint_id": self.endpoint_id,
            "market": self.market,
            "adapter_id": self.adapter_id,
            "upstream_lineage_id": self.upstream_lineage_id,
            "captured_at": self.captured_at,
            "raw_artifact_sha256": self.raw_artifact_sha256,
            "capture_id": self.capture_id,
            "observation_id": self.observation_id,
            "a0_authority_source_ref": self.a0_authority_source_ref,
            "a1_authority_source_ref": self.a1_authority_source_ref,
        }

    def canonical_payload(self) -> dict[str, Any]:
        return self.digest_payload() | {"digest": self.digest}

    def historical_resolver(self) -> SourceAuthorityResolver:
        authority = self

        def resolve(source_token: str, endpoint_id: str, market: str) -> SourceAuthorityResolution | None:
            if (source_token, endpoint_id, market) != (
                authority.source_token,
                authority.endpoint_id,
                authority.market,
            ):
                return None
            return SourceAuthorityResolution(
                source_token=authority.source_token,
                endpoint_id=authority.endpoint_id,
                market=authority.market,
                adapter_id=authority.adapter_id,
                upstream_lineage_id=authority.upstream_lineage_id,
                authority_ref=f"captured-provider-authority:sha256:{authority.digest}",
            )

        return resolve


def capture_current_a_share_provider_authority(
    sealed: SealedRawCapture,
    *,
    observation_id: str,
    source_token: str,
    endpoint_id: str,
    market: str = "cn",
) -> CapturedProviderAuthorityEvidence:
    """Explicit capture-time factory; never called implicitly by conversion/replay."""

    if not isinstance(sealed, SealedRawCapture):
        raise ValueError("captured authority requires a verified SealedRawCapture")
    _assert_capture_authority_sources_still_match_accepted_versions()
    artifact = sealed.artifact
    _, observed_at = sealed.pit_binding(observation_id)
    lineage = CN_REALTIME_SOURCE_LINEAGE.get(source_token)
    if lineage is None or market not in lineage.markets:
        raise ValueError("source token is not admitted by accepted A0 authority")
    allowed = CN_INTRADAY_ENDPOINT_EXTENSIONS.get(source_token, frozenset())
    if endpoint_id not in allowed:
        raise ValueError("source endpoint is not admitted by accepted A1 intraday authority")

    payload = {
        "schema_version": CAPTURED_PROVIDER_AUTHORITY_SCHEMA_VERSION,
        "source_token": source_token,
        "endpoint_id": endpoint_id,
        "market": market,
        "adapter_id": lineage.adapter_id,
        "upstream_lineage_id": lineage.upstream_lineage_id,
        "captured_at": observed_at,
        "raw_artifact_sha256": sealed.manifest.artifact_sha256,
        "capture_id": artifact.capture_id,
        "observation_id": observation_id,
        "a0_authority_source_ref": A0_AUTHORITY_SOURCE_REF,
        "a1_authority_source_ref": A1_AUTHORITY_SOURCE_REF,
    }
    return CapturedProviderAuthorityEvidence(**payload, digest=stable_hash(payload))


@dataclass(frozen=True)
class ProviderAuthorityDriftDiagnostic:
    status: str
    differences: tuple[str, ...]
    recorded_authority_digest: str


def diagnose_current_provider_authority(
    authority: CapturedProviderAuthorityEvidence,
) -> ProviderAuthorityDriftDiagnostic:
    """Current registry is diagnostic-only; it cannot rewrite historical authority."""

    lineage = CN_REALTIME_SOURCE_LINEAGE.get(authority.source_token)
    if lineage is None:
        return ProviderAuthorityDriftDiagnostic(
            status="CURRENT_AUTHORITY_MISSING",
            differences=("source_token",),
            recorded_authority_digest=authority.digest,
        )
    differences: list[str] = []
    if authority.market not in lineage.markets:
        differences.append("market")
    if lineage.adapter_id != authority.adapter_id:
        differences.append("adapter_id")
    if lineage.upstream_lineage_id != authority.upstream_lineage_id:
        differences.append("upstream_lineage_id")
    allowed = CN_INTRADAY_ENDPOINT_EXTENSIONS.get(authority.source_token, frozenset())
    if authority.endpoint_id not in allowed:
        differences.append("endpoint_id")
    return ProviderAuthorityDriftDiagnostic(
        status="CURRENT_AUTHORITY_DRIFT" if differences else "CURRENT_AUTHORITY_MATCH",
        differences=tuple(sorted(differences)),
        recorded_authority_digest=authority.digest,
    )


def _canonical_row(raw_row: Mapping[str, Any], index: int) -> Mapping[str, str]:
    """Reuse A3's accepted OHLCV primitives without weakening its source contract."""

    _require_exact_keys(raw_row, _ROW_KEYS, f"raw_row[{index}]")
    event_time = _parse_aware(raw_row["datetime"], f"raw_row[{index}].datetime")
    open_px = _decimal_text(raw_row["open"], f"raw_row[{index}].open", allow_zero=False)
    high_px = _decimal_text(raw_row["high"], f"raw_row[{index}].high", allow_zero=False)
    low_px = _decimal_text(raw_row["low"], f"raw_row[{index}].low", allow_zero=False)
    close_px = _decimal_text(raw_row["close"], f"raw_row[{index}].close", allow_zero=False)
    _decimal_text(raw_row["volume"], f"raw_row[{index}].volume", allow_zero=True)
    if high_px < low_px or high_px < open_px or high_px < close_px:
        raise ValueError(f"raw_row[{index}] invalid OHLC envelope")
    if low_px > open_px or low_px > close_px:
        raise ValueError(f"raw_row[{index}] invalid OHLC envelope")
    canonical_time = event_time.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return deep_freeze(
        {
            "datetime": canonical_time,
            "open": raw_row["open"],
            "high": raw_row["high"],
            "low": raw_row["low"],
            "close": raw_row["close"],
            "volume": raw_row["volume"],
        }
    )


def _lineage_payload(lineage: NormalizationLineage) -> Mapping[str, str]:
    return deep_freeze(lineage.digest_payload() | {"lineage_digest": lineage.lineage_digest})


@dataclass(frozen=True)
class ProviderRecordedMarketFixture:
    schema_version: str
    fixture_id: str
    symbol: str
    interval_label: str
    available_at: datetime
    observed_at: datetime
    authority: CapturedProviderAuthorityEvidence
    raw_artifact_sha256: str
    capture_id: str
    observation_id: str
    normalizer_version: str
    normalizer_sha256: str
    rows: tuple[Mapping[str, str], ...]
    row_lineages: tuple[Mapping[str, str], ...]
    rows_digest: str
    row_lineages_digest: str
    fixture_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != PROVIDER_RECORDED_FIXTURE_SCHEMA_VERSION:
            raise ValueError(f"unsupported provider-recorded fixture: {self.schema_version}")
        for name in ("fixture_id", "symbol", "interval_label", "capture_id", "observation_id", "normalizer_version"):
            _trimmed(getattr(self, name), name)
        available = aware_utc(self.available_at, "available_at")
        observed = aware_utc(self.observed_at, "observed_at")
        assert available is not None and observed is not None
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "observed_at", observed)
        if available > observed:
            raise ValueError("available_at cannot be after observed_at")
        _hex(self.raw_artifact_sha256, "raw_artifact_sha256")
        _hex(self.normalizer_sha256, "normalizer_sha256")
        _hex(self.rows_digest, "rows_digest")
        _hex(self.row_lineages_digest, "row_lineages_digest")
        _hex(self.fixture_digest, "fixture_digest")
        if self.normalizer_version != NORMALIZER_VERSION or self.normalizer_sha256 != NORMALIZER_SHA256:
            raise ValueError("provider-recorded fixture normalizer identity mismatch")
        if self.raw_artifact_sha256 != self.authority.raw_artifact_sha256:
            raise ValueError("fixture raw artifact does not match captured authority")
        if self.capture_id != self.authority.capture_id or self.observation_id != self.authority.observation_id:
            raise ValueError("fixture capture/observation does not match captured authority")
        if self.observed_at != self.authority.captured_at:
            raise ValueError("fixture observed_at must equal captured authority time")

        rows = tuple(deep_freeze(row) for row in self.rows)
        lineages = tuple(deep_freeze(lineage) for lineage in self.row_lineages)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "row_lineages", lineages)
        if not rows:
            raise ValueError("provider-recorded fixture requires at least one normalized row")
        if len(rows) != len(lineages):
            raise ValueError("normalized rows require one-to-one normalization lineage")

        previous_time: datetime | None = None
        seen_lineage: set[str] = set()
        for index, (row, lineage) in enumerate(zip(rows, lineages)):
            canonical = _canonical_row(row, index)
            if dict(canonical) != dict(row):
                raise ValueError("normalized row is not canonical")
            event_time = _parse_aware(row["datetime"], f"row[{index}].datetime")
            if event_time > available:
                raise ValueError("normalized row event time cannot be after available_at")
            if previous_time is not None and event_time <= previous_time:
                raise ValueError("normalized row datetimes must be strictly increasing")
            previous_time = event_time

            expected_path = f"observations[{self.observation_id}].raw_payload.raw_rows[{index}]"
            required = {
                "schema_version",
                "artifact_sha256",
                "capture_id",
                "observation_id",
                "raw_path",
                "normalizer_version",
                "normalizer_sha256",
                "derived_event_id",
                "lineage_digest",
            }
            if set(lineage) != required:
                raise ValueError("normalization lineage schema mismatch")
            if lineage["artifact_sha256"] != self.raw_artifact_sha256:
                raise ValueError("normalization lineage raw artifact mismatch")
            if lineage["capture_id"] != self.capture_id or lineage["observation_id"] != self.observation_id:
                raise ValueError("normalization lineage capture binding mismatch")
            if lineage["raw_path"] != expected_path:
                raise ValueError("normalization lineage row order/path mismatch")
            if lineage["normalizer_version"] != self.normalizer_version or lineage["normalizer_sha256"] != self.normalizer_sha256:
                raise ValueError("normalization lineage normalizer mismatch")
            derived_id = self.derived_event_id(index, event_time)
            if lineage["derived_event_id"] != derived_id:
                raise ValueError("normalization lineage derived event mismatch")
            expected_digest = stable_hash({key: lineage[key] for key in lineage if key != "lineage_digest"})
            if lineage["lineage_digest"] != expected_digest:
                raise ValueError("normalization lineage digest mismatch")
            if lineage["lineage_digest"] in seen_lineage:
                raise ValueError("duplicate normalization lineage")
            seen_lineage.add(lineage["lineage_digest"])

        if self.rows_digest != stable_hash(rows):
            raise ValueError("provider-recorded rows digest mismatch")
        if self.row_lineages_digest != stable_hash(lineages):
            raise ValueError("provider-recorded lineage digest mismatch")
        if self.fixture_digest != stable_hash(self.digest_payload()):
            raise ValueError("provider-recorded fixture digest mismatch")

    def derived_event_id(self, index: int, event_time: datetime) -> str:
        return f"provider-recorded:{self.fixture_id}:{index}:{event_time.isoformat()}"

    def source_id(self) -> str:
        return f"provider://{self.authority.market}/{self.authority.source_token}/{self.authority.endpoint_id}"

    def digest_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fixture_id": self.fixture_id,
            "symbol": self.symbol,
            "interval_label": self.interval_label,
            "available_at": self.available_at,
            "observed_at": self.observed_at,
            "authority": self.authority.canonical_payload(),
            "raw_artifact_sha256": self.raw_artifact_sha256,
            "capture_id": self.capture_id,
            "observation_id": self.observation_id,
            "normalizer_version": self.normalizer_version,
            "normalizer_sha256": self.normalizer_sha256,
            "rows": self.rows,
            "row_lineages": self.row_lineages,
            "rows_digest": self.rows_digest,
            "row_lineages_digest": self.row_lineages_digest,
        }

    def historical_authority_resolver(self) -> SourceAuthorityResolver:
        return self.authority.historical_resolver()

    def materialize_events(self) -> tuple[EventRecord, ...]:
        events: list[EventRecord] = []
        for index, (row, lineage) in enumerate(zip(self.rows, self.row_lineages)):
            event_time = _parse_aware(row["datetime"], f"row[{index}].datetime")
            events.append(
                EventRecord(
                    event_id=self.derived_event_id(index, event_time),
                    event_type="PROVIDER_RECORDED_MARKET_BAR",
                    entity_id=self.symbol,
                    theme_id=None,
                    occurred_at=event_time,
                    event_time=event_time,
                    published_at=None,
                    available_at=self.available_at,
                    observed_at=self.observed_at,
                    created_at=self.observed_at,
                    source_id=self.source_id(),
                    payload={
                        "provider_authority_digest": self.authority.digest,
                        "raw_artifact_sha256": self.raw_artifact_sha256,
                        "capture_id": self.capture_id,
                        "observation_id": self.observation_id,
                        "normalization_lineage_digest": lineage["lineage_digest"],
                        "normalizer_version": self.normalizer_version,
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "entry_gate": "CLOSED",
                    },
                    trace_id=f"trace:provider-recorded:{self.fixture_id}",
                    source_kind="PROVIDER",
                    source_token=self.authority.source_token,
                    endpoint_id=self.authority.endpoint_id,
                    market=self.authority.market,
                )
            )
        return tuple(events)


def convert_sealed_capture_to_provider_fixture(
    sealed: SealedRawCapture,
    *,
    observation_id: str,
    authority: CapturedProviderAuthorityEvidence,
    fixture_id: str,
) -> ProviderRecordedMarketFixture:
    """Pure deterministic A4b conversion for already-canonical aware OHLCV rows."""

    if not isinstance(sealed, SealedRawCapture):
        raise ValueError("provider fixture conversion requires verified SealedRawCapture")
    artifact = sealed.artifact
    available_at, observed_at = sealed.pit_binding(observation_id)
    observation = artifact.observation(observation_id)
    if authority.raw_artifact_sha256 != sealed.manifest.artifact_sha256:
        raise ValueError("captured authority is bound to a different raw artifact")
    if authority.capture_id != artifact.capture_id or authority.observation_id != observation_id:
        raise ValueError("captured authority is bound to a different capture/observation")
    if authority.captured_at != observed_at:
        raise ValueError("captured authority time does not match verified A4 observation")
    payload = observation.raw_payload
    if not isinstance(payload, Mapping):
        raise ValueError("verified observation raw payload must be an object")
    raw_rows = payload.get("raw_rows")
    if not isinstance(raw_rows, tuple) or not raw_rows:
        raise ValueError("verified observation must contain non-empty raw_rows")

    rows: list[Mapping[str, str]] = []
    lineages: list[Mapping[str, str]] = []
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            raise ValueError(f"raw row[{index}] must be an object")
        row = _canonical_row(raw_row, index)
        event_time = _parse_aware(row["datetime"], f"raw_row[{index}].datetime")
        if event_time > available_at:
            raise ValueError("raw row event time cannot be after verified available_at")
        derived_event_id = f"provider-recorded:{fixture_id}:{index}:{event_time.isoformat()}"
        lineage = build_row_normalization_lineage(
            sealed,
            observation_id=observation_id,
            row_index=index,
            normalizer_version=NORMALIZER_VERSION,
            normalizer_sha256=NORMALIZER_SHA256,
            derived_event_id=derived_event_id,
            expected_artifact_sha256=sealed.manifest.artifact_sha256,
        )
        rows.append(row)
        lineages.append(_lineage_payload(lineage))

    rows_tuple = tuple(rows)
    lineages_tuple = tuple(lineages)
    base = {
        "schema_version": PROVIDER_RECORDED_FIXTURE_SCHEMA_VERSION,
        "fixture_id": _trimmed(fixture_id, "fixture_id"),
        "symbol": observation.symbol,
        "interval_label": observation.ktype,
        "available_at": available_at,
        "observed_at": observed_at,
        "authority": authority,
        "raw_artifact_sha256": sealed.manifest.artifact_sha256,
        "capture_id": artifact.capture_id,
        "observation_id": observation_id,
        "normalizer_version": NORMALIZER_VERSION,
        "normalizer_sha256": NORMALIZER_SHA256,
        "rows": rows_tuple,
        "row_lineages": lineages_tuple,
        "rows_digest": stable_hash(rows_tuple),
        "row_lineages_digest": stable_hash(lineages_tuple),
    }
    digest_payload = {
        **base,
        "authority": authority.canonical_payload(),
    }
    return ProviderRecordedMarketFixture(**base, fixture_digest=stable_hash(digest_payload))
