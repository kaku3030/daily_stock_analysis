# -*- coding: utf-8 -*-
"""Persistence for research-priority event snapshots."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, select

from src.storage import Base, DatabaseManager, utc_naive_now


class ResearchPriorityEventRecord(Base):
    __tablename__ = "research_priority_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    run_id = Column(String(128), nullable=False, index=True)
    observed_at = Column(DateTime, nullable=False, default=utc_naive_now, index=True)
    priority_level = Column(String(16), nullable=False, index=True)
    priority_score = Column(Float, nullable=False, default=0.0, index=True)
    event_type = Column(String(32), nullable=False, default="priority_refresh", index=True)
    research_tone = Column(String(32), nullable=False, default="neutral", index=True)
    notification_ready = Column(Boolean, nullable=False, default=False, index=True)
    event_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utc_naive_now)

    __table_args__ = (
        UniqueConstraint("market", "code", "run_id", name="uix_research_priority_event_run"),
        Index("ix_research_priority_event_symbol_time", "market", "code", "observed_at"),
    )


def research_priority_event_to_dict(record: ResearchPriorityEventRecord) -> dict[str, Any]:
    try:
        payload = json.loads(record.event_json or "{}")
    except (TypeError, ValueError):
        payload = {}
    return {
        "market": record.market,
        "code": record.code,
        "run_id": record.run_id,
        "observed_at": record.observed_at.isoformat() if record.observed_at else None,
        "priority_level": record.priority_level,
        "priority_score": float(record.priority_score or 0.0),
        "event_type": record.event_type,
        "research_tone": record.research_tone,
        "notification_ready": bool(record.notification_ready),
        "detail": payload,
    }


class ResearchPriorityEventRepository:
    def __init__(self, db_manager: DatabaseManager | None = None):
        self.db = db_manager or DatabaseManager.get_instance()
        ResearchPriorityEventRecord.__table__.create(self.db._engine, checkfirst=True)

    def sync_run(self, market: str, run_id: str, events: list[dict[str, Any]]) -> int:
        market = market.strip().lower()
        run_id = run_id.strip()
        if not run_id:
            return 0
        observed_at = utc_naive_now()

        def _sync(session) -> int:
            inserted = 0
            for event in events:
                code = str(event.get("code") or "").strip().upper()
                if not code:
                    continue
                existing = session.execute(
                    select(ResearchPriorityEventRecord).where(
                        ResearchPriorityEventRecord.market == market,
                        ResearchPriorityEventRecord.code == code,
                        ResearchPriorityEventRecord.run_id == run_id,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                session.add(ResearchPriorityEventRecord(
                    market=market,
                    code=code,
                    run_id=run_id,
                    observed_at=observed_at,
                    priority_level=str(event.get("priority_level") or "low"),
                    priority_score=float(event.get("priority_score") or 0.0),
                    event_type=str(event.get("event_type") or "priority_refresh"),
                    research_tone=str(event.get("research_tone") or "neutral"),
                    notification_ready=bool(event.get("notification_ready")),
                    event_json=json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str),
                ))
                inserted += 1
            return inserted

        return self.db._run_write_transaction("sync research priority events", _sync)

    def list_latest(self, market: str, limit: int = 200) -> list[ResearchPriorityEventRecord]:
        return list(self.latest_map(market, limit=limit).values())

    def latest_map(
        self,
        market: str,
        *,
        exclude_run_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, ResearchPriorityEventRecord]:
        market = market.strip().lower()
        with self.db.get_session() as session:
            query = select(ResearchPriorityEventRecord).where(ResearchPriorityEventRecord.market == market)
            if exclude_run_id:
                query = query.where(ResearchPriorityEventRecord.run_id != exclude_run_id)
            rows = list(session.execute(
                query.order_by(
                    ResearchPriorityEventRecord.observed_at.desc(),
                    ResearchPriorityEventRecord.id.desc(),
                )
            ).scalars().all())
        latest: dict[str, ResearchPriorityEventRecord] = {}
        for row in rows:
            if row.code in latest:
                continue
            latest[row.code] = row
            if len(latest) >= max(1, limit):
                break
        return latest

    def latest_payload_map(
        self,
        market: str,
        *,
        exclude_run_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for code, record in self.latest_map(market, exclude_run_id=exclude_run_id, limit=limit).items():
            serialized = research_priority_event_to_dict(record)
            detail = serialized.get("detail")
            result[code] = detail if isinstance(detail, dict) else serialized
        return result
