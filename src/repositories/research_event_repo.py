# -*- coding: utf-8 -*-
"""Persistence for point-in-time research news/catalyst evidence."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint, select

from src.services.screening.news_change import build_event_evidence, compare_event_evidence
from src.storage import Base, DatabaseManager, utc_naive_now


class ResearchEventSnapshotRecord(Base):
    __tablename__ = "research_candidate_event_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    run_id = Column(String(128), nullable=False, index=True)
    previous_run_id = Column(String(128), default="")
    observed_at = Column(DateTime, nullable=False, default=utc_naive_now, index=True)
    state = Column(String(32), nullable=False, default="unchanged", index=True)
    attention = Column(String(16), nullable=False, default="none", index=True)
    material = Column(Boolean, nullable=False, default=False, index=True)
    evidence_json = Column(Text, nullable=False, default="{}")
    change_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utc_naive_now)

    __table_args__ = (
        UniqueConstraint(
            "market",
            "code",
            "run_id",
            name="uix_research_event_snapshot_run",
        ),
        Index(
            "ix_research_event_snapshot_symbol_time",
            "market",
            "code",
            "observed_at",
        ),
    )


def research_event_snapshot_to_dict(record: ResearchEventSnapshotRecord) -> dict[str, Any]:
    evidence = _load_dict(record.evidence_json)
    detail = _load_dict(record.change_json)
    return {
        "market": record.market,
        "code": record.code,
        "run_id": record.run_id,
        "previous_run_id": record.previous_run_id or "",
        "observed_at": record.observed_at.isoformat() if record.observed_at else None,
        "state": record.state,
        "attention": record.attention,
        "material": bool(record.material),
        "evidence": evidence,
        "detail": detail,
    }


class ResearchEventSnapshotRepository:
    def __init__(self, db_manager: DatabaseManager | None = None):
        self.db = db_manager or DatabaseManager.get_instance()
        ResearchEventSnapshotRecord.__table__.create(self.db._engine, checkfirst=True)

    def sync_run(
        self,
        market: str,
        run_id: str,
        picks: list[dict[str, Any]],
    ) -> int:
        market = market.strip().lower()
        run_id = run_id.strip()
        if not run_id:
            return 0
        observed_at = utc_naive_now()

        def _sync(session) -> int:
            inserted = 0
            for pick in picks:
                code = str(pick.get("code") or "").strip().upper()
                if not code:
                    continue
                existing = session.execute(
                    select(ResearchEventSnapshotRecord).where(
                        ResearchEventSnapshotRecord.market == market,
                        ResearchEventSnapshotRecord.code == code,
                        ResearchEventSnapshotRecord.run_id == run_id,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue

                current_evidence = build_event_evidence(pick)
                previous = session.execute(
                    select(ResearchEventSnapshotRecord)
                    .where(
                        ResearchEventSnapshotRecord.market == market,
                        ResearchEventSnapshotRecord.code == code,
                        ResearchEventSnapshotRecord.run_id != run_id,
                        ResearchEventSnapshotRecord.observed_at <= observed_at,
                    )
                    .order_by(
                        ResearchEventSnapshotRecord.observed_at.desc(),
                        ResearchEventSnapshotRecord.id.desc(),
                    )
                    .limit(1)
                ).scalar_one_or_none()
                previous_evidence = _load_dict(previous.evidence_json) if previous is not None else None
                change = compare_event_evidence(previous_evidence, current_evidence)

                session.add(
                    ResearchEventSnapshotRecord(
                        market=market,
                        code=code,
                        run_id=run_id,
                        previous_run_id=previous.run_id if previous is not None else "",
                        observed_at=observed_at,
                        state=str(change.get("state") or "unchanged"),
                        attention=str(change.get("attention") or "none"),
                        material=bool(change.get("material")),
                        evidence_json=_json(current_evidence),
                        change_json=_json(change),
                    )
                )
                inserted += 1
            return inserted

        return self.db._run_write_transaction("sync research event snapshots", _sync)

    def list_run(self, market: str, run_id: str) -> list[ResearchEventSnapshotRecord]:
        market = market.strip().lower()
        run_id = run_id.strip()
        if not run_id:
            return []
        with self.db.get_session() as session:
            return list(
                session.execute(
                    select(ResearchEventSnapshotRecord)
                    .where(
                        ResearchEventSnapshotRecord.market == market,
                        ResearchEventSnapshotRecord.run_id == run_id,
                    )
                    .order_by(
                        ResearchEventSnapshotRecord.material.desc(),
                        ResearchEventSnapshotRecord.code.asc(),
                    )
                ).scalars().all()
            )

    def latest_map(
        self,
        market: str,
        *,
        limit: int = 200,
    ) -> dict[str, ResearchEventSnapshotRecord]:
        market = market.strip().lower()
        with self.db.get_session() as session:
            rows = list(
                session.execute(
                    select(ResearchEventSnapshotRecord)
                    .where(ResearchEventSnapshotRecord.market == market)
                    .order_by(
                        ResearchEventSnapshotRecord.observed_at.desc(),
                        ResearchEventSnapshotRecord.id.desc(),
                    )
                ).scalars().all()
            )
        result: dict[str, ResearchEventSnapshotRecord] = {}
        for row in rows:
            if row.code in result:
                continue
            result[row.code] = row
            if len(result) >= max(1, limit):
                break
        return result

    def latest_change_map(self, market: str, *, limit: int = 200) -> dict[str, dict[str, Any]]:
        return {
            code: research_event_snapshot_to_dict(record).get("detail") or {}
            for code, record in self.latest_map(market, limit=limit).items()
        }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _load_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}
