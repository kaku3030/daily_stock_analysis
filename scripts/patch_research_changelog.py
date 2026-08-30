from pathlib import Path

path = Path('docs/CHANGELOG.md')
text = path.read_text(encoding='utf-8')
marker = '## [Unreleased]\n\n'
entries = [
    '- [新功能] 美股研究扫描结果持久化为长期候选池，记录 A/B/C/D 研究等级、入选历史、研究上下文与 active/watching/retired 生命周期。',
    '- [新功能] 美股研究扫描新增行业研究雷达，聚合候选质量、持续入选与可用 industry/board heat 数据，并在市场层数据缺失时退化为 candidate_only。',
    '- [新功能] 美股候选池新增财报与估值快照及按 run_id 保存的历史证据，缺失数据不会覆盖上一轮有效财务状态。',
    '- [新功能] 新增相邻有效财务快照变化检测，分离盈利趋势、估值趋势与管理层指引变化，并输出财务变化雷达。',
    '- [新功能] 新增研究优先级事件流，将候选等级、行业强度、财务变化与催化/风险线索融合为研究注意力排序，不生成交易指令。',
    '- [改进] 研究优先级新增事件升级、反转、指引变化与恢复 transition gate，抑制重复提醒并输出 research_priority_alerts。',
    '- [新功能] 研究事件提醒可显式接入现有 NotificationService，复用 alert 路由、severity、dedup、cooldown 与多渠道发送诊断，默认不自动发送。',
    '- [改进] 新增 `US Research Stateful Scan` GitHub Actions 工作流，通过 SQLite quick_check、WAL checkpoint 与 GitHub Cache 在独立 runner 间保存候选池、财务快照和研究事件历史，并提供无 API 调用的缓存往返测试。',
]

if marker not in text:
    raise SystemExit('Unreleased marker not found')
missing = [entry for entry in entries if entry not in text]
if not missing:
    print('research changelog already up to date')
    raise SystemExit(0)
text = text.replace(marker, marker + '\n'.join(missing) + '\n', 1)
path.write_text(text, encoding='utf-8')
print(f'added {len(missing)} research changelog entries')
