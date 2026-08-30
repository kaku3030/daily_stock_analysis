# -*- coding: utf-8 -*-
"""Persistent research candidate pool."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    inspect,
    select,
    text,
)

from src.schemas.research_financials import extract_financial_snapshot
from src.storage import Base, DatabaseManager, utc_naive_now

WATCH_AFTER_MISSES = 2
RETIRE_AFTER_MISSES = 5


class CandidatePoolRecord(Base):
    __tablename__ = "research_candidate_pool"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    name = Column(String(128), default="")
    grade = Column(String(1), nullable=False, default="D", index=True)
    score = Column(Float, nullable=False, default=0.0, index=True)
    status = Column(String(16), nullable=False, default="active", index=True)
    industry = Column(String(128), default="")
    industry_rank = Column(Integer)
    industry_change_pct = Column(Float)
    industry_heat_score = Column(Float)
    board_heat_score = Column(Float)
    board_heat_latest_score = Column(Float)
    board_heat_trend_score = Column(Float)
    board_heat_persistence_score = Column(Float)
    board_heat_cooling_score = Column(Float)
    board_heat_observations = Column(Integer)
    board_heat_state = Column(String(64), default="")
    board_heat_summary = Column(Text, default="")
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    market_cap = Column(Float)
    financial_snapshot_json = Column(Text, default="{}")
    financial_data_confidence = Column(String(16), nullable=False, default="none", index=True)
    financial_data_updated_at = Column(DateTime)
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
    missed_runs = Column(Integer, nullable=False, default=0, index=True)
    grade_changed_at = Column(DateTime)
    status_changed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utc_naive_now)
    updated_at = Column(DateTime, nullable=False, default=utc_naive_now, onupdate=utc_naive_now)

    __table_args__ = (
        UniqueConstraint("market", "code", name="uix_research_candidate_market_code"),
        Index("ix_research_candidate_market_status_score", "market", "status", "score"),
    )


class CandidateFinancialSnapshotRecord(Base):
    """Point-in-time financial evidence captured at a screening run."""

    __tablename__ = "research_candidate_financial_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    run_id = Column(String(128), nullable=False, index=True)
    captured_at = Column(DateTime, nullable=False, default=utc_naive_now, index=True)
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    market_cap = Column(Float)
    confidence = Column(String(16), nullable=False, default="none", index=True)
    snapshot_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        UniqueConstraint(
            "market",
            "code",
            "run_id",
            name="uix_research_financial_snapshot_run",
        ),
        Index(
            "ix_research_financial_snapshot_symbol_time",
            "market",
            "code",
            "captured_at",
        ),
    )


@dataclass(frozen=True)
class CandidatePoolSyncStats:
    inserted: int = 0
    updated: int = 0
    aged: int = 0
    watching: int = 0
    retired: int = 0
    reactivated: int = 0
    financial_snapshots: int = 0


def candidate_grade(score: float) -> str:
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


def _safe_json_loads(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    value = _optional_float(value)
    return int(value) if value is not None else None


def candidate_to_dict(record: CandidatePoolRecord) -> Dict[str, Any]:
    def _iso(value):
        return value.isoformat() if value is not None else None

    return {
        "market": record.market,
        "code": record.code,
        "name": record.name or "",
        "grade": record.grade,
        "score": float(record.score or 0.0),
        "status": record.status,
        "industry": record.industry or "",
        "industry_rank": record.industry_rank,
        "industry_change_pct": record.industry_change_pct,
        "industry_heat_score": record.industry_heat_score,
        "board_heat_score": record.board_heat_score,
        "board_heat_latest_score": record.board_heat_latest_score,
        "board_heat_trend_score": record.board_heat_trend_score,
        "board_heat_persistence_score": record.board_heat_persistence_score,
        "board_heat_cooling_score": record.board_heat_cooling_score,
        "board_heat_observations": record.board_heat_observations,
        "board_heat_state": record.board_heat_state or "",
        "board_heat_summary": record.board_heat_summary or "",
        "pe_ratio": record.pe_ratio,
        "pb_ratio": record.pb_ratio,
        "market_cap": record.market_cap,
        "financial_snapshot": _safe_json_loads(record.financial_snapshot_json, {}),
        "financial_data_confidence": record.financial_data_confidence or "none",
        "financial_data_updated_at": _iso(record.financial_data_updated_at),
        "source_strategy": record.source_strategy or "",
        "source_run_id": record.source_run_id or "",
        "ranking_reason": record.ranking_reason or "",
        "risk_summary": record.risk_summary or "",
        "factor_scores": _safe_json_loads(record.factor_scores_json, {}),
        "catalysts": _safe_json_loads(record.catalysts_json, []),
        "risks": _safe_json_loads(record.risks_json, []),
        "first_selected_at": _iso(record.first_selected_at),
        "last_selected_at": _iso(record.last_selected_at),
        "selected_count": int(record.selected_count or 0),
        "missed_runs": int(record.missed_runs or 0),
        "grade_changed_at": _iso(record.grade_changed_at),
        "status_changed_at": _iso(record.status_changed_at),
    }


class CandidatePoolRepository:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()
        CandidatePoolRecord.__table__.create(self.db._engine, checkfirst=True)
        CandidateFinancialSnapshotRecord.__table__.create(self.db._engine, checkfirst=True)
        self._ensure_additive_columns()

    def _ensure_additive_columns(self) -> None:
        if self.db._engine.url.get_backend_name() != "sqlite":
            return
        existing = {
            column["name"]
            for column in inspect(self.db._engine).get_columns(CandidatePoolRecord.__tablename__)
        }
        additions = {
            "missed_runs": "INTEGER NOT NULL DEFAULT 0",
            "grade_changed_at": "DATETIME",
            "status_changed_at": "DATETIME",
            "industry_rank": "INTEGER",
            "industry_change_pct": "FLOAT",
            "industry_heat_score": "FLOAT",
            "board_heat_score": "FLOAT",
            "board_heat_latest_score": "FLOAT",
            "board_heat_trend_score": "FLOAT",
            "board_heat_persistence_score": "FLOAT",
            "board_heat_cooling_score": "FLOAT",
            "board_heat_observations": "INTEGER",
            "board_heat_state": "VARCHAR(64) DEFAULT ''",
            "board_heat_summary": "TEXT DEFAULT ''",
            "pe_ratio": "FLOAT",
            "pb_ratio": "FLOAT",
            "market_cap": "FLOAT",
            "financial_snapshot_json": "TEXT DEFAULT '{}'",
            "financial_data_confidence": "VARCHAR(16) NOT NULL DEFAULT 'none'",
            "financial_data_updated_at": "DATETIME",
        }
        with self.db._engine.begin() as connection:
            for column, column_sql in additions.items():
                if column not in existing:
                    connection.execute(
                        text(
                            f"ALTER TABLE {CandidatePoolRecord.__tablename__} "
                            f"ADD COLUMN {column} {column_sql}"
                        )
                    )

    @staticmethod
    def _can_age_absent_candidates(
        payload: Dict[str, Any],
        selected_codes: set[str],
    ) -> bool:
        return bool(
            selected_codes
            and int(payload.get("snapshot_count") or 0) > 0
            and not payload.get("source_errors")
        )

    def sync_from_screen_result(self, payload: Dict[str, Any]) -> CandidatePoolSyncStats:
        market = str(payload.get("market") or "us").strip().lower()
        strategy = str(payload.get("strategy") or "")
        run_id = str(payload.get("run_id") or "")
        picks: Iterable[Dict[str, Any]] = payload.get("picks") or []
        picks = list(picks)
        selected_codes = {
            str(pick.get("code") or "").strip().upper()
            for pick in picks
            if str(pick.get("code") or "").strip()
        }
        selected_at = utc_naive_now()

        def _sync(session) -> CandidatePoolSyncStats:
            inserted = updated = aged = watching = retired = reactivated = 0
            financial_snapshots = 0
            for pick in picks:
                code = str(pick.get("code") or "").strip().upper()
                if not code:
                    continue
                score = float(pick.get("final_score") or 0.0)
                new_grade = candidate_grade(score)
                record = session.execute(
                    select(CandidatePoolRecord).where(
                        CandidatePoolRecord.market == market,
                        CandidatePoolRecord.code == code,
                    )
                ).scalar_one_or_none()

                values = {
                    "name": str(pick.get("name") or ""),
                    "grade": new_grade,
                    "score": score,
                    "status": "active",
                    "industry": str(pick.get("industry") or ""),
                    "source_strategy": strategy,
                    "source_run_id": run_id,
                    "ranking_reason": str(
                        pick.get("ranking_reason") or pick.get("llm_thesis") or ""
                    ),
                    "risk_summary": str(pick.get("risk_summary") or ""),
                    "factor_scores_json": _json(pick.get("factor_scores"), {}),
                    "catalysts_json": _json(pick.get("llm_catalysts"), []),
                    "risks_json": _json(pick.get("llm_risks"), []),
                    "last_selected_at": selected_at,
                    "updated_at": selected_at,
                    "missed_runs": 0,
                }
                metric_values = {
                    "industry_rank": _optional_int(pick.get("industry_rank")),
                    "industry_change_pct": _optional_float(pick.get("industry_change_pct")),
                    "industry_heat_score": _optional_float(pick.get("industry_heat_score")),
                    "board_heat_score": _optional_float(pick.get("board_heat_score")),
                    "board_heat_latest_score": _optional_float(pick.get("board_heat_latest_score")),
                    "board_heat_trend_score": _optional_float(pick.get("board_heat_trend_score")),
                    "board_heat_persistence_score": _optional_float(pick.get("board_heat_persistence_score")),
                    "board_heat_cooling_score": _optional_float(pick.get("board_heat_cooling_score")),
                    "board_heat_observations": _optional_int(pick.get("board_heat_observations")),
                }
                values.update(
                    {key: value for key, value in metric_values.items() if value is not None}
                )
                for key in ("board_heat_state", "board_heat_summary"):
                    value = str(pick.get(key) or "").strip()
                    if value:
                        values[key] = value

                financial = extract_financial_snapshot(pick)
                pe_ratio = _optional_float(pick.get("pe_ratio"))
                pb_ratio = _optional_float(pick.get("pb_ratio"))
                market_cap = _optional_float(pick.get("total_mv"))
                has_financial_evidence = financial.get("confidence") != "none"
                if has_financial_evidence:
                    values.update(
                        {
                            "financial_snapshot_json": _json(financial, {}),
                            "financial_data_confidence": str(financial["confidence"]),
                            "financial_data_updated_at": selected_at,
                        }
                    )
                    if pe_ratio is not None:
                        values["pe_ratio"] = pe_ratio
                    if pb_ratio is not None:
                        values["pb_ratio"] = pb_ratio
                    if market_cap is not None:
                        values["market_cap"] = market_cap

                if record is None:
                    values.setdefault("financial_snapshot_json", "{}")
                    values.setdefault("financial_data_confidence", "none")
                    session.add(
                        CandidatePoolRecord(
                            market=market,
                            code=code,
                            first_selected_at=selected_at,
                            selected_count=1,
                            created_at=selected_at,
                            grade_changed_at=selected_at,
                            status_changed_at=selected_at,
                            **values,
                        )
                    )
                    inserted += 1
                else:
                    if record.grade != new_grade:
                        record.grade_changed_at = selected_at
                    if record.status != "active":
                        record.status_changed_at = selected_at
                        reactivated += 1
                    for key, value in values.items():
                        setattr(record, key, value)
                    record.selected_count = int(record.selected_count or 0) + 1
                    updated += 1

                if has_financial_evidence and run_id:
                    existing_snapshot = session.execute(
                        select(CandidateFinancialSnapshotRecord).where(
                            CandidateFinancialSnapshotRecord.market == market,
                            CandidateFinancialSnapshotRecord.code == code,
                            CandidateFinancialSnapshotRecord.run_id == run_id,
                        )
                    ).scalar_one_or_none()
                    if existing_snapshot is None:
                        session.add(
                            CandidateFinancialSnapshotRecord(
                                market=market,
                                code=code,
                                run_id=run_id,
                                captured_at=selected_at,
                                pe_ratio=pe_ratio,
                                pb_ratio=pb_ratio,
                                market_cap=market_cap,
                                confidence=str(financial["confidence"]),
                                snapshot_json=_json(financial, {}),
                            )
                        )
                        financial_snapshots += 1

            if self._can_age_absent_candidates(payload, selected_codes):
                absent = session.execute(
                    select(CandidatePoolRecord).where(
                        CandidatePoolRecord.market == market,
                        CandidatePoolRecord.code.not_in(selected_codes),
                        CandidatePoolRecord.status.in_(("active", "watching")),
                    )
                ).scalars().all()
                for record in absent:
                    record.missed_runs = int(record.missed_runs or 0) + 1
                    record.updated_at = selected_at
                    aged += 1
                    if record.missed_runs >= RETIRE_AFTER_MISSES:
                        new_status = "retired"
                    elif record.missed_runs >= WATCH_AFTER_MISSES:
                        new_status = "watching"
                    else:
                        new_status = record.status
                    if new_status != record.status:
                        record.status = new_status
                        record.status_changed_at = selected_at
                        watching += int(new_status == "watching")
                        retired += int(new_status == "retired")

            return CandidatePoolSyncStats(
                inserted=inserted,
                updated=updated,
                aged=aged,
                watching=watching,
                retired=retired,
                reactivated=reactivated,
                financial_snapshots=financial_snapshots,
            )

        return self.db._run_write_transaction("sync research candidate pool", _sync)

    def list_candidates(
        self,
        market: Optional[str] = None,
        include_retired: bool = True,
        limit: int = 200,
    ) -> List[CandidatePoolRecord]:
        with self.db.get_session() as session:
            statement = select(CandidatePoolRecord)
            if market:
                statement = statement.where(
                    CandidatePoolRecord.market == market.strip().lower()
                )
            if not include_retired:
                statement = statement.where(CandidatePoolRecord.status != "retired")
            rows = list(session.execute(statement).scalars().all())
            status_order = {"active": 0, "watching": 1, "retired": 2}
            rows.sort(
                key=lambda row: (
                    status_order.get(row.status, 9),
                    -float(row.score or 0.0),
                    -(
                        row.last_selected_at.timestamp()
                        if row.last_selected_at
                        else 0.0
                    ),
                )
            )
            return rows[: max(1, limit)]

    def list_active(
        self,
        market: Optional[str] = None,
        limit: int = 100,
    ) -> List[CandidatePoolRecord]:
        return [
            record
            for record in self.list_candidates(market, False, limit * 2)
            if record.status == "active"
        ][:limit]

    def list_financial_snapshots(
        self,
        market: str,
        code: str,
        limit: int = 20,
    ) -> List[CandidateFinancialSnapshotRecord]:
        with self.db.get_session() as session:
            return list(
                session.execute(
                    select(CandidateFinancialSnapshotRecord)
                    .where(
                        CandidateFinancialSnapshotRecord.market == market.strip().lower(),
                        CandidateFinancialSnapshotRecord.code == code.strip().upper(),
                    )
                    .order_by(CandidateFinancialSnapshotRecord.captured_at.desc())
                    .limit(max(1, limit))
                ).scalars().all()
            )

    def get(self, market: str, code: str) -> Optional[CandidatePoolRecord]:
        with self.db.get_session() as session:
            return session.execute(
                select(CandidatePoolRecord).where(
                    CandidatePoolRecord.market == market.strip().lower(),
                    CandidatePoolRecord.code == code.strip().upper(),
                )
            ).scalar_one_or_none()
