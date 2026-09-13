from datetime import datetime, timezone

from src.services.strategy_lab.market_data_capture import MarketDataCapture


def test_offline_capture_freezes_csv_with_explicit_provenance():
    capture = MarketDataCapture("baostock", "history-k", "baostock-adapter-v1", "CN", datetime(2026, 9, 13, tzinfo=timezone.utc), datetime(2026, 9, 13, tzinfo=timezone.utc), "Asia/Shanghai", "unadjusted", "symbol,date,open,high,low,close,volume\nsh.600000,2020-01-02,1,2,1,2,3\n")
    capsule = capture.to_capsule("cn-eod", "v1")
    assert capsule.source_id == "baostock"
    assert len(capsule.events) == 1
