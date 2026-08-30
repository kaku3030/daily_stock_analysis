# -*- coding: utf-8 -*-
"""Point-in-time candidate event evidence and deterministic change observations."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint, select

from src.services.screening.news_change import build_event_snapshot, compare_event_snapshots
from src.storage import Base, DatabaseManager, utc_naive_now


class CandidateEventSnapshotRecord(Base):
    __tablename__ = "research_candidate_event_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    run_id = Column(String(128), nullable=False, index=True)
    captured_at = Column(DateTime, nullable=False, default=utc_naive_now, index=True)
    catalysts_json = Column(Text, nullable=False, default="[]")
    risks_json = Column(Text, nullable=False, default="[]")
    news_evidence_json = Column(Text, nullable=False, default="[]")
    fingerprints_json = Column(Text, nullable=False, default="{}")
    change_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        UniqueConstraint("market", "code", "run_id", name="uix_research_event_snapshot_run"),
        Index("ix_research_event_snapshot_symbol_time", "market", "code", "captured_at"),
    )


def event_snapshot_to_dict(record: CandidateEventSnapshotRecord) -> dict[str, Any]:
    snapshot = _snapshot(record)
    change = _loads(record.change_json, {})
    return {
        "market": record.market,
        "code": record.code,
        "run_id": record.run_id,
        "captured_at": record.captured_at.isoformat() if record.captured_at else None,
        **snapshot,
        "change": change,
    }


class CandidateEventSnapshotRepository:
    def __init__(self, db_manager: DatabaseManager | None = None):
        self.db = db_manager or DatabaseManager.get_instance()
        CandidateEventSnapshotRecord.__table__.create(self.db._engine, checkfirst=True)

    def sync_run(self, payload: dict[str, Any]) -> int:
        market = str(payload.get("market") or "us").strip().lower()
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            return 0
        captured_at = utc_naive_now()

        def _sync(session) -> int:
            inserted = 0
            for candidate in payload.get("picks") or []:
                code = str(candidate.get("code") or "").strip().upper()
                if not code:
                    continue
                existing = session.execute(
                    select(CandidateEventSnapshotRecord).where(
                        CandidateEventSnapshotRecord.market == market,
                        CandidateEventSnapshotRecord.code == code,
                        CandidateEventSnapshotRecord.run_id == run_id,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                previous = session.execute(
                    select(CandidateEventSnapshotRecord)
                    .where(
                        CandidateEventSnapshotRecord.market == market,
                        CandidateEventSnapshotRecord.code == code,
                        CandidateEventSnapshotRecord.run_id != run_id,
                    )
                    .order_by(
                        CandidateEventSnapshotRecord.captured_at.desc(),
                        CandidateEventSnapshotRecord.id.desc(),
                    )
                    .limit(1)
                ).scalar_one_or_none()
                snapshot = build_event_snapshot(candidate)
                change = compare_event_snapshots(_snapshot(previous) if previous else None, snapshot)
                session.add(
                    CandidateEventSnapshotRecord(
                        market=market,
                        code=code,
                        run_id=run_id,
                        captured_at=captured_at,
                        catalysts_json=_dumps(snapshot["catalysts"]),
                        risks_json=_dumps(snapshot["risks"]),
                        news_evidence_json=_dumps(snapshot["news_evidence"]),
                        fingerprints_json=_dumps(snapshot["fingerprints"]),
                        change_json=_dumps(change),
                    )
                )
                inserted += 1
            return inserted

        return self.db._run_write_transaction("sync research event snapshots", _sync)

    def list_latest(self, market: str, limit: int = 200) -> list[CandidateEventSnapshotRecord]:
        with self.db.get_session() as session:
            rows = list(
                session.execute(
                    select(CandidateEventSnapshotRecord)
                    .where(CandidateEventSnapshotRecord.market == market.strip().lower())
                    .order_by(
                        CandidateEventSnapshotRecord.captured_at.desc(),
                        CandidateEventSnapshotRecord.id.desc(),
                    )
                ).scalars().all()
            )
        latest: list[CandidateEventSnapshotRecord] = []
        seen: set[str] = set()
        for row in rows:
            if row.code in seen:
                continue
            latest.append(row)
            seen.add(row.code)
            if len(latest) >= max(1, limit):
                break
        return latest


def _snapshot(record: CandidateEventSnapshotRecord) -> dict[str, Any]:
    return {
        "catalysts": _loads(record.catalysts_json, []),
        "risks": _loads(record.risks_json, []),
        "news_evidence": _loads(record.news_evidence_json, []),
        "fingerprints": _loads(record.fingerprints_json, {}),
    }


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

