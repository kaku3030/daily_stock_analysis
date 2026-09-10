"""Persistent validation queue and non-mutating QA/calibration summaries."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from .config import StockRadarConfig, load_stock_radar_config
from .notifications import RadarNotifier


VALID_OUTCOMES = frozenset({"pending", "passed", "failed"})


def _canonical_utc_iso(value: datetime | None, *, field_name: str) -> str:
    """Return an aware datetime as canonical UTC ISO text.

    Validation timestamps participate in ordered time-range queries, so new
    persistence owns one clock domain. Naive/ambiguous datetimes and supplied
    non-datetime values fail closed rather than being silently interpreted.
    """

    timestamp = datetime.now(timezone.utc) if value is None else value
    if not isinstance(timestamp, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if timestamp.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    try:
        offset = timestamp.utcoffset()
    except Exception as exc:  # pragma: no cover - defensive broken tzinfo
        raise ValueError(f"{field_name} has an unusable timezone offset") from exc
    if offset is None:
        raise ValueError(f"{field_name} must have a usable timezone offset")
    return timestamp.astimezone(timezone.utc).isoformat()


def _require_stored_absolute_timestamp(value: Any, *, field_name: str) -> None:
    """Prove a stored ISO timestamp represents an absolute instant.

    Pre-repair versions could persist caller-supplied aware offsets *or* naive
    datetimes verbatim. SQLite ``julianday`` handles aware offsets correctly,
    but it also accepts a timezone-less timestamp using an implicit convention.
    That would turn an unknowable legacy instant into apparently valid QA
    evidence. Validate the historical text first and refuse ambiguous rows.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must contain an ISO timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a parseable ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} is timezone-naive and cannot be assigned to a reporting day")
    try:
        offset = parsed.utcoffset()
    except Exception as exc:  # pragma: no cover - defensive broken tzinfo
        raise ValueError(f"{field_name} has an unusable timezone offset") from exc
    if offset is None:
        raise ValueError(f"{field_name} must have a usable timezone offset")


@dataclass(frozen=True)
class ValidationItem:
    validation_id: str
    signal_id: str
    signal_type: str
    signal_state: str
    outcome: str
    evidence: Mapping[str, Any]
    created_at: str
    resolved_at: str | None


class ValidationQueue:
    """SQLite-backed queue; outcomes never alter the source signal record."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database))
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS stock_radar_validation_queue (
                validation_id TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                signal_state TEXT NOT NULL,
                outcome TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_stock_radar_validation_type_time
                ON stock_radar_validation_queue(signal_type, created_at DESC);
            CREATE TABLE IF NOT EXISTS stock_radar_calibration_reviews (
                review_id TEXT PRIMARY KEY,
                signal_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                failure_count INTEGER NOT NULL,
                candidate_version TEXT,
                requires_manual_promotion INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

    def enqueue(
        self,
        *,
        signal_id: str,
        signal_type: str,
        signal_state: str,
        evidence: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> ValidationItem:
        if str(signal_state).lower() != "confirmed":
            raise ValueError("only Confirmed signals enter the Validation Queue")
        timestamp = _canonical_utc_iso(created_at, field_name="created_at")
        validation_id = uuid4().hex
        self._connection.execute(
            """
            INSERT INTO stock_radar_validation_queue
                (validation_id, signal_id, signal_type, signal_state, outcome,
                 evidence_json, created_at, resolved_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, NULL)
            """,
            (
                validation_id,
                str(signal_id),
                str(signal_type),
                "confirmed",
                json.dumps(dict(evidence or {}), ensure_ascii=False, sort_keys=True),
                timestamp,
            ),
        )
        self._connection.commit()
        return self.get(validation_id)

    def resolve(
        self,
        validation_id: str,
        outcome: str,
        *,
        evidence: Mapping[str, Any] | None = None,
        resolved_at: datetime | None = None,
    ) -> ValidationItem:
        normalized = str(outcome).lower()
        if normalized not in {"passed", "failed"}:
            raise ValueError("resolved outcome must be passed or failed")
        current = self.get(validation_id)
        merged_evidence = dict(current.evidence)
        merged_evidence.update(dict(evidence or {}))
        resolved_timestamp = _canonical_utc_iso(resolved_at, field_name="resolved_at")
        self._connection.execute(
            """
            UPDATE stock_radar_validation_queue
            SET outcome = ?, evidence_json = ?, resolved_at = ?
            WHERE validation_id = ?
            """,
            (
                normalized,
                json.dumps(merged_evidence, ensure_ascii=False, sort_keys=True),
                resolved_timestamp,
                validation_id,
            ),
        )
        self._connection.commit()
        return self.get(validation_id)

    def get(self, validation_id: str) -> ValidationItem:
        row = self._connection.execute(
            "SELECT * FROM stock_radar_validation_queue WHERE validation_id = ?",
            (validation_id,),
        ).fetchone()
        if row is None:
            raise KeyError(validation_id)
        return self._item(row)

    def recent_confirmed(self, signal_type: str, *, limit: int) -> list[ValidationItem]:
        rows = self._connection.execute(
            """
            SELECT * FROM stock_radar_validation_queue
            WHERE signal_type = ? AND signal_state = 'confirmed' AND outcome != 'pending'
            ORDER BY COALESCE(resolved_at, created_at) DESC, validation_id DESC
            LIMIT ?
            """,
            (str(signal_type), int(limit)),
        ).fetchall()
        return [self._item(row) for row in rows]

    def resolved_count(self, signal_type: str) -> int:
        row = self._connection.execute(
            """
            SELECT COUNT(*) AS count FROM stock_radar_validation_queue
            WHERE signal_type = ? AND signal_state = 'confirmed' AND outcome != 'pending'
            """,
            (str(signal_type),),
        ).fetchone()
        return int(row["count"])

    def signal_types(self) -> list[str]:
        rows = self._connection.execute(
            """
            SELECT DISTINCT signal_type FROM stock_radar_validation_queue
            WHERE signal_type != '' ORDER BY signal_type
            """
        ).fetchall()
        return [str(row["signal_type"]) for row in rows]

    def calibration_reviews(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT * FROM stock_radar_calibration_reviews
            ORDER BY created_at DESC, review_id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def enqueue_calibration_review(
        self,
        *,
        signal_type: str,
        reason: str,
        sample_count: int,
        failure_count: int,
        candidate_version: str | None,
    ) -> str:
        review_id = uuid4().hex
        self._connection.execute(
            """
            INSERT INTO stock_radar_calibration_reviews
                (review_id, signal_type, reason, sample_count, failure_count,
                 candidate_version, requires_manual_promotion, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                review_id,
                signal_type,
                reason,
                sample_count,
                failure_count,
                candidate_version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._connection.commit()
        return review_id

    @staticmethod
    def _item(row: sqlite3.Row) -> ValidationItem:
        return ValidationItem(
            validation_id=str(row["validation_id"]),
            signal_id=str(row["signal_id"]),
            signal_type=str(row["signal_type"]),
            signal_state=str(row["signal_state"]),
            outcome=str(row["outcome"]),
            evidence=json.loads(row["evidence_json"]),
            created_at=str(row["created_at"]),
            resolved_at=str(row["resolved_at"]) if row["resolved_at"] else None,
        )


class DailyQA:
    def __init__(self, queue: ValidationQueue) -> None:
        self.queue = queue

    def summarize(
        self,
        signal_type: str,
        *,
        day: date | None = None,
        timezone_name: str = "UTC",
    ) -> dict[str, Any]:
        """Summarize one reporting local calendar day over timestamped rows.

        New ValidationQueue timestamps are canonical UTC ISO text. Older rows
        may contain equivalent aware ISO timestamps with non-UTC offsets, so
        membership is compared as an instant via SQLite ``julianday`` rather
        than by lexical timestamp text. Historical rows without absolute-time
        semantics are rejected instead of being silently localized by SQLite.
        """

        zone = ZoneInfo(timezone_name)
        target_day = day or datetime.now(zone).date()
        local_start = datetime.combine(target_day, time.min, tzinfo=zone)
        local_end = datetime.combine(target_day + timedelta(days=1), time.min, tzinfo=zone)
        start_utc = local_start.astimezone(timezone.utc).isoformat()
        end_utc = local_end.astimezone(timezone.utc).isoformat()
        target = target_day.isoformat()

        legacy_rows = self.queue._connection.execute(
            """
            SELECT validation_id, created_at FROM stock_radar_validation_queue
            WHERE signal_type = ?
            """,
            (signal_type,),
        ).fetchall()
        for row in legacy_rows:
            try:
                _require_stored_absolute_timestamp(
                    row["created_at"],
                    field_name=f"created_at[{row['validation_id']}]",
                )
                sqlite_instant = self.queue._connection.execute(
                    "SELECT julianday(?) AS instant",
                    (row["created_at"],),
                ).fetchone()["instant"]
                if sqlite_instant is None:
                    raise ValueError(
                        f"created_at[{row['validation_id']}] cannot be parsed by SQLite julianday"
                    )
            except ValueError as exc:
                raise ValueError(
                    "DailyQA cannot safely summarize a signal type containing ambiguous legacy timestamps"
                ) from exc

        rows = self.queue._connection.execute(
            """
            SELECT outcome, COUNT(*) AS count FROM stock_radar_validation_queue
            WHERE signal_type = ?
              AND julianday(created_at) >= julianday(?)
              AND julianday(created_at) < julianday(?)
            GROUP BY outcome
            """,
            (signal_type, start_utc, end_utc),
        ).fetchall()
        counts = {str(row["outcome"]): int(row["count"]) for row in rows}
        return {
            "signal_type": signal_type,
            "day": target,
            "pending": counts.get("pending", 0),
            "passed": counts.get("passed", 0),
            "failed": counts.get("failed", 0),
            "total": sum(counts.values()),
        }


class WeeklyCalibration:
    """Create human review candidates without changing production weights."""

    def __init__(
        self,
        queue: ValidationQueue,
        config: StockRadarConfig | None = None,
        *,
        notifier: RadarNotifier | None = None,
    ) -> None:
        self.queue = queue
        self.config = config or load_stock_radar_config()
        self.notifier = notifier or RadarNotifier()

    def evaluate(
        self,
        signal_type: str,
        *,
        production_weights: Mapping[str, float],
    ) -> dict[str, Any]:
        weights_before = deepcopy(dict(production_weights))
        recent = self.queue.recent_confirmed(
            signal_type,
            limit=self.config.qa.same_type_window,
        )
        failures = sum(item.outcome == "failed" for item in recent)
        sample_count = self.queue.resolved_count(signal_type)
        alert = (
            len(recent) == self.config.qa.same_type_window
            and failures >= self.config.qa.failure_alert_count
        )
        candidate_version = (
            f"{signal_type}-candidate-{datetime.now(timezone.utc).date().isoformat()}"
            if sample_count >= self.config.qa.minimum_samples_for_weight_candidate
            else None
        )
        review_id = None
        if alert:
            reason = f"recent_{len(recent)}_confirmed_failures={failures}"
            review_id = self.queue.enqueue_calibration_review(
                signal_type=signal_type,
                reason=reason,
                sample_count=sample_count,
                failure_count=failures,
                candidate_version=candidate_version,
            )
            self.notifier.notify(
                "signal_qa_alert",
                {
                    "signal_type": signal_type,
                    "recent_window": len(recent),
                    "failure_count": failures,
                    "review_id": review_id,
                    "weight_change_eligible": (
                        sample_count >= self.config.qa.minimum_samples_for_weight_candidate
                    ),
                    "requires_manual_promotion": True,
                },
            )
        if dict(production_weights) != weights_before:
            raise RuntimeError("production weights were mutated during QA")
        return {
            "signal_type": signal_type,
            "sample_count": sample_count,
            "recent_window": len(recent),
            "recent_failures": failures,
            "qa_alert": alert,
            "calibration_review_id": review_id,
            "weight_change_eligible": (
                sample_count >= self.config.qa.minimum_samples_for_weight_candidate
            ),
            "candidate_version": candidate_version,
            "requires_validation": bool(candidate_version),
            "requires_manual_promotion": bool(candidate_version),
            "production_weights_changed": False,
        }
