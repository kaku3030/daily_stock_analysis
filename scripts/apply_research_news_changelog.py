from pathlib import Path

path = Path("docs/CHANGELOG.md")
text = path.read_text(encoding="utf-8")
entry = "- [新功能] 美股研究新增新闻 / 催化剂变化雷达，按 run_id 持久化事件证据并用确定性归一与近似去重识别新增催化、新风险和重复旧闻；缺失线索不会自动解释为风险解除，并接入研究优先级与提醒 transition gate。"
anchor = "- [改进] 新增 `US Research Stateful Scan` GitHub Actions 工作流，通过 SQLite quick_check、WAL checkpoint 与 GitHub Cache 在独立 runner 间保存候选池、财务快照和研究事件历史，并提供无 API 调用的缓存往返测试。"
if entry in text:
    print("CHANGELOG entry already present")
    raise SystemExit(0)
if anchor not in text:
    raise SystemExit("expected Unreleased research anchor not found")
text = text.replace(anchor, anchor + "\n" + entry, 1)
path.write_text(text, encoding="utf-8")
print("CHANGELOG entry inserted")
