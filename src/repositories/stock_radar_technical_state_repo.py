# -*- coding: utf-8 -*-
"""Point-in-time persistence for Stock Radar multi-timeframe state."""

from __future__ import annotations

import json
from datetime import timezone
from typing import Any, Sequence

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint, select

from src.services.stock_radar_v2.technical_state import StockRadarTechnicalState
from src.services.stock_radar_v2.technical_state_history import (
    compare_technical_states,
    technical_state_evidence,
    technical_state_fingerprint,
)
from src.storage import Base, DatabaseManager, utc_naive_now


class StockRadarTechnicalStateRecord(Base):
    __tablename__ = "stock_radar_technical_state_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    run_id = Column(String(128), nullable=False, index=True)
    previous_run_id = Column(String(128), default="")
    observed_at = Column(DateTime, nullable=False, default=utc_naive_now, index=True)
    state = Column(String(40), nullable=False, default="unchanged", index=True)
    attention = Column(String(16), nullable=False, default="none", index=True)
    material = Column(Boolean, nullable=False, default=False, index=True)
    fingerprint = Column(String(40), nullable=False, default="", index=True)
    evidence_json = Column(Text, nullable=False, default="{}")
    change_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utc_naive_now)

    __table_args__ = (
        UniqueConstraint("market", "code", "run_id", name="uix_stock_radar_technical_state_run"),
        Index("ix_stock_radar_technical_state_symbol_time", "market", "code", "observed_at"),
    )


def technical_state_snapshot_to_dict(record: StockRadarTechnicalStateRecord) -> dict[str, Any]:
    return {
        "market": record.market,
        "code": record.code,
        "run_id": record.run_id,
        "previous_run_id": record.previous_run_id or "",
        "observed_at": record.observed_at.isoformat() if record.observed_at else None,
        "state": record.state,
        "attention": record.attention,
        "material": bool(record.material),
        "fingerprint": record.fingerprint,
        "evidence": _load_dict(record.evidence_json),
        "detail": _load_dict(record.change_json),
    }


class StockRadarTechnicalStateRepository:
    def __init__(self, db_manager: DatabaseManager | None = None):
        self.db = db_manager or DatabaseManager.get_instance()
        StockRadarTechnicalStateRecord.__table__.create(self.db._engine, checkfirst=True)

    def sync_run(
        self,
        market: str,
        run_id: str,
        states: Sequence[StockRadarTechnicalState],
    ) -> int:
        market = market.strip().lower()
        run_id = run_id.strip()
        if not market or not run_id:
            return 0

        def _sync(session) -> int:
            inserted = 0
            for state in states:
                code = state.symbol.strip().upper()
                if not code:
                    continue
                existing = session.execute(
                    select(StockRadarTechnicalStateRecord).where(
                        StockRadarTechnicalStateRecord.market == market,
                        StockRadarTechnicalStateRecord.code == code,
                        StockRadarTechnicalStateRecord.run_id == run_id,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue

                evidence = technical_state_evidence(state)
                observed_at = (
                    state.as_of.astimezone(timezone.utc).replace(tzinfo=None)
                    if state.as_of.tzinfo
                    else state.as_of
                )
                previous = session.execute(
                    select(StockRadarTechnicalStateRecord)
                    .where(
                        StockRadarTechnicalStateRecord.market == market,
                        StockRadarTechnicalStateRecord.code == code,
                        StockRadarTechnicalStateRecord.run_id != run_id,
                        StockRadarTechnicalStateRecord.observed_at <= observed_at,
                    )
                    .order_by(
                        StockRadarTechnicalStateRecord.observed_at.desc(),
                        StockRadarTechnicalStateRecord.id.desc(),
                    )
                    .limit(1)
                ).scalar_one_or_none()
                previous_evidence = _load_dict(previous.evidence_json) if previous is not None else None
                change = compare_technical_states(previous_evidence, evidence)
                session.add(
                    StockRadarTechnicalStateRecord(
                        market=market,
                        code=code,
                        run_id=run_id,
                        previous_run_id=previous.run_id if previous is not None else "",
                        observed_at=observed_at,
                        state=str(change["state"]),
                        attention=str(change["attention"]),
                        material=bool(change["material"]),
                        fingerprint=technical_state_fingerprint(evidence),
                        evidence_json=_json(evidence),
                        change_json=_json(change),
                    )
                )
                inserted += 1
            return inserted

        return self.db._run_write_transaction("sync stock radar technical states", _sync)

    def list_run(self, market: str, run_id: str) -> list[StockRadarTechnicalStateRecord]:
        with self.db.get_session() as session:
            return list(
                session.execute(
                    select(StockRadarTechnicalStateRecord)
                    .where(
                        StockRadarTechnicalStateRecord.market == market.strip().lower(),
                        StockRadarTechnicalStateRecord.run_id == run_id.strip(),
                    )
                    .order_by(
                        StockRadarTechnicalStateRecord.material.desc(),
                        StockRadarTechnicalStateRecord.code.asc(),
                    )
                ).scalars().all()
            )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _load_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}
