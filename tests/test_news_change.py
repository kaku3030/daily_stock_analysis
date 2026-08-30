# -*- coding: utf-8 -*-

from src.services.screening.news_change import (
    build_event_snapshot,
    compare_event_snapshots,
    text_fingerprint,
)


def test_superficial_rewording_has_same_deterministic_fingerprint() -> None:
    assert text_fingerprint("AI demand remains strong") == text_fingerprint("Strong AI demand continues")


def test_change_detection_classifies_new_missing_and_unchanged() -> None:
    previous = build_event_snapshot(
        {"llm_catalysts": ["AI demand remains strong"], "llm_risks": ["export restrictions"]}
    )
    unchanged = build_event_snapshot(
        {"llm_catalysts": ["Strong AI demand continues"], "llm_risks": ["export restrictions"]}
    )
    assert compare_event_snapshots(previous, unchanged)["state"] == "unchanged"

    current = build_event_snapshot(
        {"llm_catalysts": ["new hyperscaler order"], "llm_risks": ["DOJ investigation"]}
    )
    change = compare_event_snapshots(previous, current)
    assert [row["type"] for row in change["new_catalysts"]] == ["new_catalyst"]
    assert change["new_risks"][0]["severity"] == "high"
    assert {row["category"] for row in change["resolved_or_missing"]} == {"catalyst", "risk"}
    assert change["attention"] == "high"


def test_first_snapshot_is_non_alerting_baseline() -> None:
    current = build_event_snapshot({"llm_catalysts": ["new product"]})
    change = compare_event_snapshots(None, current)
    assert change["baseline"] is True
    assert change["state"] == "unchanged"
    assert change["attention"] == "none"

