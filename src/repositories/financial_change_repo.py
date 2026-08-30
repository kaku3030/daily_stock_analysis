# -*- coding: utf-8 -*-
"""Persistence for deterministic candidate financial change observations."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint, select

from src.repositories.candidate_pool_repo import CandidateFinancialSnapshotRecord
from src.services.screening.financial_change import compare_financial_snapshots
from src.storage import Base, DatabaseManager, utc_naive_now


class CandidateFinancialChangeRecord(Base):
    __tablename__ = "research_candidate_financial_changes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    run_id = Column(String(128), nullable=False, index=True)
    previous_run_id = Column(String(128), default="")
    observed_at = Column(DateTime, nullable=False, default=utc_naive_now, index=True)
    state = Column(String(32), nullable=False, default="stable", index=True)
    attention = Column(String(16), nullable=False, default="none", index=True)
    earnings_trend = Column(String(32), nullable=False, default="unknown", index=True)
    valuation_trend = Column(String(32), nullable=False, default="unknown", index=True)
    guidance_changed = Column(Boolean, nullable=False, default=False)
    change_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utc_naive_now)

    __table_args__ = (
        UniqueConstraint(
            "market",
            "code",
            "run_id",
            name="uix_research_financial_change_run",
        ),
        Index(
            "ix_research_financial_change_symbol_time",
            "market",
            "code",
            "observed_at",
        ),
    )


def financial_change_to_dict(record: CandidateFinancialChangeRecord) -> dict[str, Any]:
    try:
        detail = json.loads(record.change_json or "{}")
    except (TypeError, ValueError):
        detail = {}
    return {
        "market": record.market,
        "code": record.code,
        "run_id": record.run_id,
        "previous_run_id": record.previous_run_id or "",
        "observed_at": record.observed_at.isoformat() if record.observed_at else None,
        "state": record.state,
        "attention": record.attention,
        "earnings_trend": record.earnings_trend,
        "valuation_trend": record.valuation_trend,
        "guidance_changed": bool(record.guidance_changed),
        "detail": detail,
    }


class CandidateFinancialChangeRepository:
    def __init__(self, db_manager: DatabaseManager | None = None):
        self.db = db_manager or DatabaseManager.get_instance()
        CandidateFinancialChangeRecord.__table__.create(self.db._engine, checkfirst=True)

    def sync_run(self, market: str, run_id: str) -> int:
        market = market.strip().lower()
        run_id = run_id.strip()
        if not run_id:
            return 0

        def _sync(session) -> int:
            inserted = 0
            current_rows = list(
                session.execute(
                    select(CandidateFinancialSnapshotRecord).where(
                        CandidateFinancialSnapshotRecord.market == market,
                        CandidateFinancialSnapshotRecord.run_id == run_id,
                    )
                ).scalars().all()
            )
            for current in current_rows:
                existing = session.execute(
                    select(CandidateFinancialChangeRecord).where(
                        CandidateFinancialChangeRecord.market == market,
                        CandidateFinancialChangeRecord.code == current.code,
                        CandidateFinancialChangeRecord.run_id == run_id,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue

                previous = session.execute(
                    select(CandidateFinancialSnapshotRecord)
                    .where(
                        CandidateFinancialSnapshotRecord.market == market,
                        CandidateFinancialSnapshotRecord.code == current.code,
                        CandidateFinancialSnapshotRecord.run_id != run_id,
                        CandidateFinancialSnapshotRecord.captured_at <= current.captured_at,
                    )
                    .order_by(
                        CandidateFinancialSnapshotRecord.captured_at.desc(),
                        CandidateFinancialSnapshotRecord.id.desc(),
                    )
                    .limit(1)
                ).scalar_one_or_none()

                comparison = compare_financial_snapshots(
                    _snapshot(previous),
                    _snapshot(current),
                )
                session.add(
                    CandidateFinancialChangeRecord(
                        market=market,
                        code=current.code,
                        run_id=run_id,
                        previous_run_id=previous.run_id if previous is not None else "",
                        observed_at=current.captured_at,
                        state=str(comparison.get("state") or "stable"),
                        attention=str(comparison.get("attention") or "none"),
                        earnings_trend=str(comparison.get("earnings_trend") or "unknown"),
                        valuation_trend=str(comparison.get("valuation_trend") or "unknown"),
                        guidance_changed=bool(comparison.get("guidance_changed")),
                        change_json=json.dumps(
                            comparison,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            default=str,
                        ),
                    )
                )
                inserted += 1
            return inserted

        return self.db._run_write_transaction("sync research financial changes", _sync)

    def list_latest(self, market: str, limit: int = 200) -> list[CandidateFinancialChangeRecord]:
        market = market.strip().lower()
        with self.db.get_session() as session:
            rows = list(
                session.execute(
                    select(CandidateFinancialChangeRecord)
                    .where(CandidateFinancialChangeRecord.market == market)
                    .order_by(
                        CandidateFinancialChangeRecord.observed_at.desc(),
                        CandidateFinancialChangeRecord.id.desc(),
                    )
                ).scalars().all()
            )
        latest: list[CandidateFinancialChangeRecord] = []
        seen: set[str] = set()
        for row in rows:
            if row.code in seen:
                continue
            latest.append(row)
            seen.add(row.code)
            if len(latest) >= max(1, limit):
                break
        return latest


def _snapshot(record: CandidateFinancialSnapshotRecord | None) -> dict[str, Any] | None:
    if record is None:
        return None
    try:
        value = json.loads(record.snapshot_json or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
