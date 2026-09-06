"""Strategy Lab V0.1 -- Temporal Contract Foundation.

Owns aware-datetime validation, UTC canonicalization, deterministic UTC text,
half-open temporal intervals, effective/available temporal evidence, and pure
availability ordering. It answers "is this datetime causally usable, and by
when", never "what does the trading calendar say" or "how do bars map to
time".

Pure compute, stdlib only, and a leaf within the package: no trading
calendar, no market timezone registries, no Data Layer, no repositories or
persistence, no other Strategy Lab engine, and nothing from
``experiment_governance``. That module already implements this exact
validate-canonicalize rule privately (``_require_utc_datetime``); this module
is an independent public implementation, not a refactor or an import of it,
so the closed module stays closed.

The datetime contract
----------------------
Every public datetime input must be an actual ``datetime`` instance with
``tzinfo is not None`` and ``utcoffset() is not None``. A ``str``, an
``int``/``float`` epoch, a naive ``datetime``, or a ``datetime`` carrying a
degenerate ``tzinfo`` whose ``utcoffset()`` returns ``None`` are all rejected
with ``ValueError`` -- never silently accepted, never coerced. Timezone is
never assumed: a naive datetime is not treated as UTC, as local time, or as
any other zone. A caller-provided, correctly aware ``ZoneInfo``-backed
datetime is legal input; this module does not import ``zoneinfo`` itself and
does not branch on any timezone name -- it only asks whether the offset the
caller already attached is well-defined.

Canonicalization always uses ``value.astimezone(timezone.utc)``, never
``value.replace(tzinfo=timezone.utc)``. The two are not interchangeable:
``replace`` overwrites the offset without shifting the wall-clock value,
silently reinterpreting whatever instant the caller meant, whereas
``astimezone`` converts to the same instant expressed in UTC. Two aware
datetimes naming the same instant under different offsets canonicalize to
the same UTC value and therefore compare and format identically.

Canonical text is ``canonical_utc_datetime(value).isoformat(timespec=
"microseconds")`` -- always exactly six fractional digits and a literal
``+00:00`` suffix, never ``Z``. This is a deliberately different convention
from ``src/llm/usage.py``'s seconds-precision, ``Z``-suffixed timestamp text
elsewhere in the repository; the two must not be unified here.

``TemporalInterval`` is half-open: ``[start, end)`` with ``start < end``
strictly enforced, so a single instant can never be a legal interval.
``contains(start)`` is ``True``; ``contains(end)`` is ``False``; two adjacent
intervals ``[a, b)`` and ``[b, c)`` never overlap. ``contains`` validates and
canonicalizes its ``moment`` argument through the same rule as every other
datetime input -- a bare naive datetime is rejected here exactly as it would
be anywhere else in this module.

``TemporalEvidence`` carries ``effective_at`` (the fact's own effective or
attribution instant) and ``available_at`` (the earliest instant a strategy
may legitimately know or use the information). There is deliberately **no**
ordering constraint between them: ``effective_at`` before, equal to, or after
``available_at`` are all legal. Restating whether a producer's timestamps are
honest or accurately attributed -- ``published_at``, ``received_at``,
``recorded_at``, or any provenance judgment about the source -- is explicitly
outside this contract; ``TemporalEvidence`` states two instants and nothing
about who is trusted to have produced them.

``is_available_by(evidence, decision_time)`` is a pure causality query:
``available_at <= decision_time`` returns ``True`` (equality is intentionally
available, not excluded), ``available_at > decision_time`` returns ``False``,
and an invalid ``decision_time`` always raises -- it never degrades to
``False``, because "not yet available" and "the question itself was
malformed" are different failures and must never be confused.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _require_aware_datetime(label: str, value: Any) -> datetime:
    """Validate and canonicalize one datetime input.

    The single choke point for the datetime contract: every public function
    and every dataclass field routes through this. Rejects anything that is
    not an actual ``datetime``, any naive datetime, and any datetime whose
    ``tzinfo`` reports ``utcoffset() is None``. Never assumes a timezone for
    a naive value, and canonicalizes via ``astimezone`` -- never ``replace``.
    """

    if not isinstance(value, datetime):
        raise ValueError(f"{label} must be a datetime, got {value!r}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware, got naive {value!r}")
    return value.astimezone(timezone.utc)


def canonical_utc_datetime(value: datetime) -> datetime:
    """Validate ``value`` and return the equivalent instant in UTC.

    Raises ``ValueError`` for anything that is not an aware ``datetime`` with
    a well-defined ``utcoffset()``. Uses ``astimezone(timezone.utc)``, never
    ``replace(tzinfo=timezone.utc)``, so the returned value names the same
    instant as the input, not a reinterpreted wall-clock reading.
    """

    return _require_aware_datetime("value", value)


def canonical_utc_text(value: datetime) -> str:
    """Deterministic UTC text: microsecond precision, literal ``+00:00``.

    Equivalent to ``canonical_utc_datetime(value).isoformat(timespec=
    "microseconds")``. Always exactly six fractional digits and the fixed
    ``+00:00`` suffix; never ``Z``, and never a different precision.
    """

    return canonical_utc_datetime(value).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class TemporalInterval:
    """A half-open temporal interval ``[start, end)`` in canonical UTC."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        canonical_start = _require_aware_datetime("start", self.start)
        canonical_end = _require_aware_datetime("end", self.end)
        if not canonical_start < canonical_end:
            raise ValueError(
                f"start must be strictly before end ({canonical_start!r} >= "
                f"{canonical_end!r})"
            )
        object.__setattr__(self, "start", canonical_start)
        object.__setattr__(self, "end", canonical_end)

    def contains(self, moment: datetime) -> bool:
        """Whether ``moment`` falls in ``[start, end)``.

        ``moment`` is validated and canonicalized through the same rule as
        every other datetime input in this module -- a naive ``moment`` is
        rejected here exactly as it would be anywhere else.
        """

        canonical_moment = _require_aware_datetime("moment", moment)
        return self.start <= canonical_moment < self.end

    def overlaps(self, other: "TemporalInterval") -> bool:
        """Whether two half-open intervals share any instant.

        Adjacent intervals ``[a, b)`` and ``[b, c)`` do not overlap: the
        boundary instant belongs only to the interval that starts there.
        """

        if not isinstance(other, TemporalInterval):
            raise ValueError(
                f"other must be a TemporalInterval instance, got {other!r}"
            )
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class TemporalEvidence:
    """Two canonical UTC instants: when a fact is effective, and when it may
    legitimately be used.

    No ordering constraint is enforced between ``effective_at`` and
    ``available_at`` -- either may precede, equal, or follow the other.
    Producer timestamp honesty or provenance is out of scope: this dataclass
    states two instants, not a judgment about who is trusted to have
    produced them.
    """

    effective_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "effective_at", _require_aware_datetime("effective_at", self.effective_at)
        )
        object.__setattr__(
            self, "available_at", _require_aware_datetime("available_at", self.available_at)
        )


def is_available_by(evidence: TemporalEvidence, decision_time: datetime) -> bool:
    """Pure causality query: was ``evidence`` available by ``decision_time``?

    ``available_at <= decision_time`` -> ``True`` (equality is intentionally
    available). ``available_at > decision_time`` -> ``False``. An invalid
    ``decision_time`` always raises ``ValueError`` -- it never degrades to
    ``False``, since a malformed question is a different failure than a
    correctly-answered "not yet".
    """

    if not isinstance(evidence, TemporalEvidence):
        raise ValueError(
            f"evidence must be a TemporalEvidence instance, got {evidence!r}"
        )
    canonical_decision_time = _require_aware_datetime("decision_time", decision_time)
    return evidence.available_at <= canonical_decision_time
