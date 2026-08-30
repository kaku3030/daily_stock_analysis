from src.analyzer import GeminiAnalyzer


def test_research_output_mode_uses_selection_prompt(monkeypatch) -> None:
    analyzer = object.__new__(GeminiAnalyzer)
    analyzer._resolved_prompt_state = {
        "skill_instructions": "",
        "default_skill_policy": "",
        "use_legacy_default_prompt": False,
    }
    analyzer._skill_instructions_override = None
    analyzer._default_skill_policy_override = None
    analyzer._use_legacy_default_prompt_override = None
    monkeypatch.setenv("ANALYSIS_OUTPUT_MODE", "research")
    prompt = analyzer._get_analysis_system_prompt("zh", stock_code="NVDA")
    assert "选股研究仪表盘" in prompt
    assert "operation_advice 固定输出“观望”" in prompt
    assert "不输出真实仓位建议" in prompt
