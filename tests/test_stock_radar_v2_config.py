from pathlib import Path

import yaml

from src.services.stock_radar_v2.config import CONFIG_PATH, load_stock_radar_config


def test_locked_mvp_defaults_load_from_yaml() -> None:
    config = load_stock_radar_config()
    assert config.fallback.fail_count == 3
    assert config.fallback.recovery_success_count == 3
    assert config.fallback.health_check_interval_seconds == 60
    assert config.fallback.cooldown_seconds == 300
    assert config.critical.timeout_count == 5
    assert config.critical.timeout_seconds == 5
    assert config.critical.empty_or_parse_count == 3
    assert config.critical.closed_bar_integrity_count == 2
    assert config.confidence.portfolio_levels == (80, 60, 40)
    assert config.qa.same_type_window == 10
    assert config.qa.failure_alert_count == 7
    assert config.qa.minimum_samples_for_weight_candidate == 30
    assert config.qa.auto_update_production_weights is False


def test_key_defaults_include_change_control_metadata() -> None:
    raw = yaml.safe_load(Path(CONFIG_PATH).read_text(encoding="utf-8"))
    items = [
        *raw["fallback"].values(),
        *raw["critical"].values(),
        *raw["confidence"]["portfolio_levels"].values(),
        *raw["confidence"]["signal_weights"].values(),
        *raw["confidence"]["portfolio_weights"].values(),
        raw["qa"]["same_type_window"],
        raw["qa"]["failure_alert_count"],
        raw["qa"]["minimum_samples_for_weight_candidate"],
        raw["qa"]["auto_update_production_weights"],
    ]
    for item in items:
        assert {"value", "reason", "evidence", "introduced_in", "last_changed"} <= set(item)
