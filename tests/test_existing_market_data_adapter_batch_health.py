from datetime import datetime, timezone

import pandas as pd
import pytest

from data_provider.existing_market_data_adapter import ExistingMarketDataAdapter
from data_provider.market_data_adapter import SignalPermission

pytestmark = pytest.mark.unit


def _fixed_now() -> datetime:
    return datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)


class _MutableManager:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def get_daily_data(self, symbol, start_date=None, end_date=None, days=30):
        return self.frame, "fixture"

    def get_realtime_quote(self, symbol, log_final_failure=False):
        raise AssertionError("quote path is not used in these tests")


def _valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-09-08",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 1000,
            }
        ]
    )


def test_empty_batch_revokes_previous_good_health_instead_of_leaking_it() -> None:
    manager = _MutableManager(_valid_frame())
    adapter = ExistingMarketDataAdapter(manager, now=_fixed_now)

    adapter.get_bars("AAPL", "1d")
    assert adapter.get_provider_health().signal_permission is SignalPermission.NORMAL

    manager.frame = pd.DataFrame()
    assert adapter.get_bars("AAPL", "1d") == []

    health = adapter.get_provider_health()
    assert "MISSING_BAR" in health.quality_flags
    assert health.signal_permission is SignalPermission.BLOCKED


def test_all_invalid_timestamps_become_blocked_batch_evidence() -> None:
    manager = _MutableManager(
        pd.DataFrame(
            [
                {
                    "date": "not-a-date",
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                }
            ]
        )
    )
    adapter = ExistingMarketDataAdapter(manager, now=_fixed_now)

    assert adapter.get_bars("AAPL", "1d") == []

    health = adapter.get_provider_health()
    assert "TIMESTAMP_MISMATCH" in health.quality_flags
    assert "MISSING_BAR" in health.quality_flags
    assert health.signal_permission is SignalPermission.BLOCKED


def test_mixed_valid_and_invalid_timestamp_batch_marks_returned_bar_untrusted() -> None:
    manager = _MutableManager(
        pd.DataFrame(
            [
                {
                    "date": "not-a-date",
                    "open": 99,
                    "high": 100,
                    "low": 98,
                    "close": 99,
                    "volume": 900,
                },
                {
                    "date": "2026-09-08",
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                },
            ]
        )
    )
    adapter = ExistingMarketDataAdapter(manager, now=_fixed_now)

    bars = adapter.get_bars("AAPL", "1d")

    assert len(bars) == 1
    assert "TIMESTAMP_MISMATCH" in bars[0].quality_flags
    assert bars[0].health is not None
    assert bars[0].health.signal_permission is SignalPermission.BLOCKED
    assert adapter.get_provider_health().signal_permission is SignalPermission.BLOCKED
