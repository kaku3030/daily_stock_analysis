# -*- coding: utf-8 -*-

from src.services.screening.news_change import compare_event_snapshots, event_items


def test_first_observation_is_baseline_not_alert() -> None:
    result = compare_event_snapshots(None, {"catalysts": ["AI demand strong"], "risks": ["export restrictions"]})
    assert result["state"] == "baseline"
    assert result["new_catalysts"] == []
    assert result["new_risks"] == []


def test_exact_repeated_event_is_unchanged() -> None:
    previous = {"catalysts": ["AI demand strong"], "risks": []}
    current = {"catalysts": ["AI demand strong"], "risks": []}
    result = compare_event_snapshots(previous, current)
    assert result["state"] == "unchanged"


def test_new_risk_has_priority_over_new_catalyst() -> None:
    previous = {"catalysts": ["AI demand strong"], "risks": []}
    current = {"catalysts": ["AI demand strong", "new hyperscaler order"], "risks": ["regulatory investigation"]}
    result = compare_event_snapshots(previous, current)
    assert result["state"] == "new_risk"
    assert len(result["new_catalysts"]) == 1
    assert len(result["new_risks"]) == 1


def test_missing_current_evidence_does_not_claim_resolution() -> None:
    previous = {"catalysts": [], "risks": ["regulatory investigation"]}
    result = compare_event_snapshots(previous, {"catalysts": [], "risks": [], "news_evidence": []})
    assert result["state"] == "unchanged"
    assert result["resolved_or_missing"] == []


def test_duplicate_items_are_deduplicated_by_fingerprint() -> None:
    items = event_items(["AI demand strong", "AI demand strong", "  AI demand strong  "])
    assert len(items) == 1
