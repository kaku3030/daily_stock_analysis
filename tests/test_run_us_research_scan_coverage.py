import json

from scripts import run_us_research_scan
from src.services.screening.models import Pick, ScreenResult


def _payload(**overrides) -> dict:
    payload = {
        "universe_requested_source": "sp500_nasdaq100",
        "universe_source": "sp500_nasdaq100",
        "universe_count": 520,
        "universe_snapshot_count": 500,
        "universe_coverage_ratio": 500 / 520,
        "picks": [{"code": "AAPL"}],
        "degradation": [],
    }
    payload.update(overrides)
    return payload


def test_publication_guard_accepts_complete_combined_universe(monkeypatch) -> None:
    monkeypatch.delenv("US_RESEARCH_REQUIRED_UNIVERSE_SOURCE", raising=False)
    monkeypatch.delenv("US_RESEARCH_MIN_UNIVERSE_SIZE", raising=False)
    monkeypatch.delenv("US_RESEARCH_MIN_UNIVERSE_COVERAGE", raising=False)
    payload = _payload()

    assert run_us_research_scan._apply_universe_publication_guard(payload) is True
    assert payload["publication_status"] == "published"
    assert payload["picks"] == [{"code": "AAPL"}]


def test_publication_guard_suppresses_small_fallback_universe(monkeypatch) -> None:
    monkeypatch.delenv("US_RESEARCH_REQUIRED_UNIVERSE_SOURCE", raising=False)
    monkeypatch.delenv("US_RESEARCH_MIN_UNIVERSE_SIZE", raising=False)
    monkeypatch.delenv("US_RESEARCH_MIN_UNIVERSE_COVERAGE", raising=False)
    payload = _payload(
        universe_source="default",
        universe_count=49,
        universe_snapshot_count=49,
        universe_coverage_ratio=1.0,
    )

    assert run_us_research_scan._apply_universe_publication_guard(payload) is False
    assert payload["publication_status"] == "blocked_low_universe_coverage"
    assert payload["suppressed_candidate_count"] == 1
    assert payload["picks"] == []
    assert any("resolved_source=default" in item for item in payload["publication_block_reasons"])
    assert any("universe_count=49" in item for item in payload["publication_block_reasons"])


def test_blocked_run_writes_diagnostic_report_without_mutating_pool(
    monkeypatch,
    tmp_path,
) -> None:
    result = ScreenResult(
        strategy="us_research_priority",
        market="us",
        snapshot_count=49,
        after_filter_count=43,
        picks=[Pick(rank=1, code="AAPL", name="Apple", final_score=60, screen_score=60)],
        universe_requested_source="sp500_nasdaq100",
        universe_source="default",
        universe_count=49,
        universe_snapshot_count=49,
        universe_coverage_ratio=1.0,
        universe_fallback_used=True,
    )
    sync_calls: list[dict] = []
    monkeypatch.setenv("US_RESEARCH_SCAN_ENABLED", "true")
    monkeypatch.setenv("US_RESEARCH_SCAN_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(run_us_research_scan.Config, "from_env", lambda: object())
    monkeypatch.setattr(run_us_research_scan, "screen", lambda *args, **kwargs: result)
    monkeypatch.setattr(
        run_us_research_scan,
        "_sync_candidate_pool",
        lambda payload, output_dir: sync_calls.append(payload),
    )

    assert run_us_research_scan.main() == 0
    written = json.loads((tmp_path / "us_research_candidates.json").read_text(encoding="utf-8"))
    assert written["publication_status"] == "blocked_low_universe_coverage"
    assert written["picks"] == []
    assert sync_calls == []
