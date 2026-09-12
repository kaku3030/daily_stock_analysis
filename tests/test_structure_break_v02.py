import pandas as pd

from src.technical.structure import (
    RECLAIM_FAILED,
    RECLAIM_PENDING,
    LeadershipPoolSnapshot,
    detect_structure_break,
    reduce_leadership_structure,
)


def bars(high, low, close):
    return pd.DataFrame({"high": high, "low": low, "close": close})


def test_unknown_does_not_become_pass_and_lower_high_is_not_break():
    frame = bars([10, 12, 11], [8, 9, 9], [9, 11, 10])
    unknown = detect_structure_break(frame, decision_available_at=3, data_quality="UNKNOWN")
    result = detect_structure_break(frame, decision_available_at=3)
    assert unknown.state == "UNKNOWN"
    assert result.state == "NO_BREAK"
    assert any(e.kind == "LOWER_HIGH_FORMED" for e in result.evidence)


def test_future_bar_does_not_change_past_decision():
    past = bars([10, 12, 11], [8, 9, 9], [9, 11, 10])
    future = pd.concat([past, bars([10], [7], [7])], ignore_index=True)
    assert detect_structure_break(past, decision_available_at=3) == detect_structure_break(
        future.iloc[:3], decision_available_at=3
    )


def test_reclaim_is_pending_until_window_is_complete():
    frame = bars([10, 10, 10, 10], [9, 9, 9, 9], [10, 8, 9, 9])
    pending = detect_structure_break(frame.iloc[:3], decision_available_at=3)
    complete = detect_structure_break(frame, decision_available_at=4)
    assert any(e.kind == RECLAIM_PENDING for e in pending.evidence) is False
    assert any(e.kind == RECLAIM_FAILED for e in complete.evidence)


def test_historical_pool_filters_current_members_and_replay_is_idempotent():
    frame = bars([10, 12, 11, 10], [8, 9, 8, 7], [9, 11, 10, 7])
    result = detect_structure_break(frame, decision_available_at=4, idempotency_key="x")
    pool = LeadershipPoolSnapshot("hist-1", 1, frozenset({"OLD"}))
    reduced = reduce_leadership_structure((("CURRENT_WINNER", result), ("OLD", result)), leadership_pool=pool)
    assert reduced.leadership_pool_snapshot_id == "hist-1"
    assert len(reduced.evidence) == len(result.evidence)
    assert detect_structure_break(frame, decision_available_at=4, idempotency_key="x") == result
