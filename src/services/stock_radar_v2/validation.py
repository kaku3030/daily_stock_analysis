"""Persistent validation queue and non-mutating QA/calibration summaries."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .config import StockRadarConfig, load_stock_radar_config
from .notifications import RadarNotifier


VALID_OUTCOMES = frozenset({"pending", "passed", "failed"})


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
        timestamp = (created_at or datetime.now(timezone.utc)).isoformat()
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
        self._connection.execute(
            """
            UPDATE stock_radar_validation_queue
            SET outcome = ?, evidence_json = ?, resolved_at = ?
            WHERE validation_id = ?
            """,
            (
                normalized,
                json.dumps(merged_evidence, ensure_ascii=False, sort_keys=True),
                (resolved_at or datetime.now(timezone.utc)).isoformat(),
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

    def summarize(self, signal_type: str, *, day: date | None = None) -> dict[str, Any]:
        target = (day or datetime.now(timezone.utc).date()).isoformat()
        rows = self.queue._connection.execute(
            """
            SELECT outcome, COUNT(*) AS count FROM stock_radar_validation_queue
            WHERE signal_type = ? AND substr(created_at, 1, 10) = ?
            GROUP BY outcome
            """,
            (signal_type, target),
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
