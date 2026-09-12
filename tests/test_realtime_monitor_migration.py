import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "realtime_monitor" / "server.py"


def test_realtime_monitor_keeps_core_contracts_and_excludes_local_account():
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "284852703845583110" not in source
    assert "STOCK_RAZOR_PRIMARY_US_ACCOUNT_ID" in source
    assert {
        "get_portfolio_state",
        "build_market_regime_state",
        "build_relative_strength_state",
        "compare_analysis_states",
        "apply_event_suppression",
        "build_decision_envelope",
        "build_notification_intent",
        "render_notification_message",
        "build_decision_journal_entry",
        "append_decision_journal_entry",
    } <= functions


def test_product_boundaries_exist_without_moving_existing_implementations():
    for boundary in ("shared", "radar", "realtime_monitor", "strategy_lab", "infra"):
        assert (ROOT / boundary / "README.md").is_file()

    assert (ROOT / "src" / "services" / "stock_radar_v2").is_dir()
    assert (ROOT / "src" / "services" / "strategy_lab").is_dir()
