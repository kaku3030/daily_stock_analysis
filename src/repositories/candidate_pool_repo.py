# -*- coding: utf-8 -*-
"""Persistent research candidate pool.

The candidate pool is intentionally small and stateful: each screening run refreshes
current research metadata for selected symbols while preserving first/last selection
timestamps and selection counts.  Absence from one scan does not delete a candidate;
retirement/decay rules belong to a later phase.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, select

from src.storage import Base, DatabaseManager, utc_naive_now


class CandidatePoolRecord(Base):
    """Current state for one symbol in the research candidate pool."""

    __tablename__ = "research_candidate_pool"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    name = Column(String(128), default="")
    grade = Column(String(1), nullable=False, default="D", index=True)
    score = Column(Float, nullable=False, default=0.0, index=True)
    status = Column(String(16), nullable=False, default="active", index=True)
    industry = Column(String(128), default="")
    source_strategy = Column(String(64), default="", index=True)
    source_run_id = Column(String(128), default="", index=True)
    ranking_reason = Column(Text, default="")
    risk_summary = Column(Text, default="")
    factor_scores_json = Column(Text, default="{}")
    catalysts_json = Column(Text, default="[]")
    risks_json = Column(Text, default="[]")
    first_selected_at = Column(DateTime, nullable=False, default=utc_naive_now, index=True)
    last_selected_at = Column(DateTime, nullable=False, default=utc_naive_now, index=True)
    selected_count = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=utc_naive_now)
    updated_at = Column(DateTime, nullable=False, default=utc_naive_now, onupdate=utc_naive_now)

    __table_args__ = (
        UniqueConstraint("market", "code", name="uix_research_candidate_market_code"),
        Index("ix_research_candidate_market_status_score", "market", "status", "score"),
    )


@dataclass(frozen=True)
class CandidatePoolSyncStats:
    inserted: int = 0
    updated: int = 0


def candidate_grade(score: float) -> str:
    """Map the 0-100 research score to the agreed A/B/C/D research grade."""

    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def _json(value: Any, fallback: Any) -> str:
    if value is None:
        value = fallback
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


class CandidatePoolRepository:
    """Read/write access for the persistent research candidate pool."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()
        # This model intentionally lives outside storage.py to keep the phase-one
        # change isolated.  Explicit checkfirst creation also covers processes that
        # instantiated DatabaseManager before importing this repository module.
        CandidatePoolRecord.__table__.create(self.db._engine, checkfirst=True)

    def sync_from_screen_result(self, payload: Dict[str, Any]) -> CandidatePoolSyncStats:
        """Upsert selected picks without removing candidates absent from this run."""

        market = str(payload.get("market") or "us").strip().lower()
        strategy = str(payload.get("strategy") or "")
        run_id = str(payload.get("run_id") or "")
        picks: Iterable[Dict[str, Any]] = payload.get("picks") or []
        selected_at = utc_naive_now()

        def _sync(session) -> CandidatePoolSyncStats:
            inserted = 0
            updated = 0
            for pick in picks:
                code = str(pick.get("code") or "").strip().upper()
                if not code:
                    continue
                score = float(pick.get("final_score") or 0.0)
                record = session.execute(
                    select(CandidatePoolRecord).where(
                        CandidatePoolRecord.market == market,
                        CandidatePoolRecord.code == code,
                    )
                ).scalar_one_or_none()

                values = {
                    "name": str(pick.get("name") or ""),
                    "grade": candidate_grade(score),
                    "score": score,
                    "status": "active",
                    "industry": str(pick.get("industry") or ""),
                    "source_strategy": strategy,
                    "source_run_id": run_id,
                    "ranking_reason": str(pick.get("ranking_reason") or pick.get("llm_thesis") or ""),
                    "risk_summary": str(pick.get("risk_summary") or ""),
                    "factor_scores_json": _json(pick.get("factor_scores"), {}),
                    "catalysts_json": _json(pick.get("llm_catalysts"), []),
                    "risks_json": _json(pick.get("llm_risks"), []),
                    "last_selected_at": selected_at,
                    "updated_at": selected_at,
                }

                if record is None:
                    session.add(
                        CandidatePoolRecord(
                            market=market,
                            code=code,
                            first_selected_at=selected_at,
                            selected_count=1,
                            created_at=selected_at,
                            **values,
                        )
                    )
                    inserted += 1
                    continue

                for key, value in values.items():
                    setattr(record, key, value)
                record.selected_count = int(record.selected_count or 0) + 1
                updated += 1

            return CandidatePoolSyncStats(inserted=inserted, updated=updated)

        return self.db._run_write_transaction("sync research candidate pool", _sync)

    def list_active(self, market: Optional[str] = None, limit: int = 100) -> List[CandidatePoolRecord]:
        """Return active candidates ordered by grade/score freshness."""

        with self.db.get_session() as session:
            statement = select(CandidatePoolRecord).where(CandidatePoolRecord.status == "active")
            if market:
                statement = statement.where(CandidatePoolRecord.market == market.strip().lower())
            statement = statement.order_by(
                CandidatePoolRecord.score.desc(),
                CandidatePoolRecord.last_selected_at.desc(),
            ).limit(max(1, limit))
            return list(session.execute(statement).scalars().all())

    def get(self, market: str, code: str) -> Optional[CandidatePoolRecord]:
        """Return one candidate by market and symbol."""

        with self.db.get_session() as session:
            return session.execute(
                select(CandidatePoolRecord).where(
                    CandidatePoolRecord.market == market.strip().lower(),
                    CandidatePoolRecord.code == code.strip().upper(),
                )
            ).scalar_one_or_none()
