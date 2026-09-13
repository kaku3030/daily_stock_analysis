"""Offline market-data capture into governed research capsules.

Adapters may download bytes outside this module.  This boundary accepts only a
recorded CSV payload and explicit provenance; it never polls a provider.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime
from io import StringIO

from .research_dataset import LateEventPolicy, ResearchDataEvent, ResearchDatasetCapsule
from .temporal_contract import canonical_utc_datetime


@dataclass(frozen=True)
class MarketDataCapture:
    source_id: str
    endpoint_id: str
    adapter_version: str
    market: str
    retrieved_at: datetime
    available_at: datetime
    timezone: str
    adjustment: str
    csv_text: str

    def to_capsule(self, dataset_id: str, dataset_version: str) -> ResearchDatasetCapsule:
        if not all(isinstance(v, str) and v.strip() for v in (self.source_id, self.endpoint_id, self.adapter_version, self.market, self.timezone, self.adjustment, self.csv_text)):
            raise ValueError("capture provenance fields and csv_text must be non-empty")
        rows = list(csv.DictReader(StringIO(self.csv_text)))
        if not rows or not {"symbol", "date", "open", "high", "low", "close", "volume"}.issubset(rows[0]):
            raise ValueError("CSV must contain symbol,date,open,high,low,close,volume")
        observed = canonical_utc_datetime(self.retrieved_at)
        available = canonical_utc_datetime(self.available_at)
        events = []
        for pos, row in enumerate(rows):
            raw = ",".join(f"{k}={row[k]}" for k in sorted(row))
            digest = hashlib.sha256(raw.encode()).hexdigest()
            event_id = hashlib.sha256(f"{self.source_id}:{self.endpoint_id}:{digest}".encode()).hexdigest()
            effective = canonical_utc_datetime(datetime.fromisoformat(row["date"]).replace(tzinfo=observed.tzinfo))
            events.append(ResearchDataEvent(event_id, f"{row['symbol']}:{row['date']}", digest, effective, available, observed, pos))
        return ResearchDatasetCapsule(dataset_id, dataset_version, self.source_id, self.adapter_version, LateEventPolicy.DROP, tuple(events))
