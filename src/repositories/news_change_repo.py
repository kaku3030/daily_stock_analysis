# -*- coding: utf-8 -*-
"""Point-in-time persistence for research catalyst/risk evidence."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint, select

from src.services.screening.news_change import compare_event_snapshots
from src.storage import Base, DatabaseManager, utc_naive_now


class CandidateEventSnapshotRecord(Base):
    __tablename__ = "research_candidate_event_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    run_id = Column(String(128), nullable=False, index=True)
    captured_at = Column(DateTime, nullable=False, default=utc_naive_now, index=True)
    snapshot_json = Column(Text, nullable=False, default="{}")
    change_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        UniqueConstraint("market", "code", "run_id", name="uix_research_event_snapshot_run"),
        Index("ix_research_event_snapshot_symbol_time", "market", "code", "captured_at"),
    )


def event_snapshot_to_dict(record: CandidateEventSnapshotRecord) -> dict[str, Any]:
    try:
        snapshot = json.loads(record.snapshot_json or "{}")
    except (TypeError, ValueError):
        snapshot = {}
    try:
        change = json.loads(record.change_json or "{}")
    except (TypeError, ValueError):
        change = {}
    return {
        "market": record.market,
        "code": record.code,
        "run_id": record.run_id,
        "captured_at": record.captured_at.isoformat() if record.captured_at else None,
        "snapshot": snapshot,
        "change": change,
    }


class CandidateEventSnapshotRepository:
    def __init__(self, db_manager: DatabaseManager | None = None):
        self.db = db_manager or DatabaseManager.get_instance()
        CandidateEventSnapshotRecord.__table__.create(self.db._engine, checkfirst=True)

    def sync_run(self, market: str, run_id: str, candidates: list[dict[str, Any]]) -> int:
        market = market.strip().lower()
        run_id = run_id.strip()
        if not run_id:
            return 0

        def _sync(session) -> int:
            inserted = 0
            for candidate in candidates:
                code = str(candidate.get("code") or "").strip()
                if not code:
                    continue
                existing = session.execute(select(CandidateEventSnapshotRecord).where(
                    CandidateEventSnapshotRecord.market == market,
                    CandidateEventSnapshotRecord.code == code,
                    CandidateEventSnapshotRecord.run_id == run_id,
                )).scalar_one_or_none()
                if existing is not None:
                    continue
                previous = session.execute(
                    select(CandidateEventSnapshotRecord).where(
                        CandidateEventSnapshotRecord.market == market,
                        CandidateEventSnapshotRecord.code == code,
                        CandidateEventSnapshotRecord.run_id != run_id,
                    ).order_by(CandidateEventSnapshotRecord.captured_at.desc(), CandidateEventSnapshotRecord.id.desc()).limit(1)
                ).scalar_one_or_none()
                previous_snapshot = _load(previous.snapshot_json) if previous is not None else None
                snapshot = {
                    "catalysts": candidate.get("catalysts") if isinstance(candidate.get("catalysts"), list) else [],
                    "risks": candidate.get("risks") if isinstance(candidate.get("risks"), list) else [],
                    "news_evidence": candidate.get("dsa_news") or [],
                }
                change = compare_event_snapshots(previous_snapshot, snapshot)
                session.add(CandidateEventSnapshotRecord(
                    market=market,
                    code=code,
                    run_id=run_id,
                    snapshot_json=json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), default=str),
                    change_json=json.dumps(change, ensure_ascii=False, separators=(",", ":"), default=str),
                ))
                inserted += 1
            return inserted

        return self.db._run_write_transaction("sync research event snapshots", _sync)

    def latest_map(self, market: str) -> dict[str, dict[str, Any]]:
        market = market.strip().lower()
        with self.db.get_session() as session:
            rows = list(session.execute(
                select(CandidateEventSnapshotRecord).where(CandidateEventSnapshotRecord.market == market)
                .order_by(CandidateEventSnapshotRecord.captured_at.desc(), CandidateEventSnapshotRecord.id.desc())
            ).scalars().all())
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.code not in result:
                result[row.code] = event_snapshot_to_dict(row)
        return result


def _load(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
