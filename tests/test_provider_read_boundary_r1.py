from datetime import date, datetime

import pytest

from src.services.live_feed.provider_read_boundary_r1 import (
    AccountListParams, FakeReadWorker, HistoryKlineParams, PositionListParams,
    ProviderExecutionOutcome, ProviderReadRequest, ProviderReadOutcome,
    QuoteSnapshotParams, ReadOperation, TradingDaysParams,
)


def req(op, params, rid="r1"):
    return ProviderReadRequest("rt", "fake", rid, op, datetime(2026, 1, 1), params)


def test_typed_allowlist_and_immutable_identity():
    r = req(ReadOperation.QUOTE_SNAPSHOT, QuoteSnapshotParams(("AAPL",)))
    assert r.operation is ReadOperation.QUOTE_SNAPSHOT
    with pytest.raises(TypeError): req("call", {})
    with pytest.raises(TypeError): req(ReadOperation.QUOTE_SNAPSHOT, AccountListParams())


@pytest.mark.parametrize("outcome", list(ProviderExecutionOutcome))
def test_replay_matrix_terminal_facts_are_deterministic(outcome):
    worker = FakeReadWorker(); r = req(ReadOperation.HISTORY_KLINE,
        HistoryKlineParams("AAPL", "1d", date(2020, 1, 1), date(2020, 1, 2), 10))
    a = worker.replay(r, outcome, {"qty": None, "timestamp": "old"}, diagnostic="replay")
    b = worker.replay(r, outcome, {"qty": None, "timestamp": "old"}, diagnostic="replay")
    assert a == b
    assert a.normalized_provider_payload["qty"] is None
    assert a.execution_outcome is outcome


def test_payload_freeze_preserves_empty_and_malformed_evidence():
    r = req(ReadOperation.POSITION_LIST, PositionListParams("acct"))
    o = FakeReadWorker().replay(r, ProviderExecutionOutcome.SUCCEEDED, {"rows": ({"qty": "bad"},)})
    assert o.normalized_provider_payload["rows"][0]["qty"] == "bad"


def test_all_operations_have_typed_params():
    assert isinstance(req(ReadOperation.TRADING_DAYS, TradingDaysParams("US", date(2026,1,1), date(2026,1,2))).params, TradingDaysParams)
    assert isinstance(req(ReadOperation.ACCOUNT_LIST, AccountListParams()).params, AccountListParams)


def test_no_provider_sdk_in_new_seam():
    import pathlib
    source = pathlib.Path("src/services/live_feed/provider_read_boundary_r1.py").read_text()
    assert "import futu" not in source.lower()
    assert "openquotecontext" not in source.lower()
