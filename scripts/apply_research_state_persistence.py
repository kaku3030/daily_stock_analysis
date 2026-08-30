from pathlib import Path

WORKFLOW = Path('.github/workflows/00-daily-analysis.yml')
text = WORKFLOW.read_text(encoding='utf-8')

checkout = """      - name: 检出代码\n        uses: actions/checkout@v5\n"""
restore = """      - name: 检出代码\n        uses: actions/checkout@v5\n\n      - name: 创建研究状态目录\n        run: mkdir -p data\n\n      - name: 恢复研究状态数据库\n        id: research-state-restore\n        uses: actions/cache/restore@v4\n        with:\n          path: |\n            data/stock_analysis.db\n            data/stock_analysis.db-wal\n            data/stock_analysis.db-shm\n          key: research-state-v1-${{ runner.os }}-${{ github.run_id }}\n          restore-keys: |\n            research-state-v1-${{ runner.os }}-\n\n      - name: 校验恢复的研究状态数据库\n        if: steps.research-state-restore.outputs.cache-matched-key != ''\n        run: |\n          python - <<'PY'\n          import sqlite3\n          from pathlib import Path\n\n          db = Path('data/stock_analysis.db')\n          if not db.exists():\n              print('ℹ️ 研究状态缓存未包含主数据库文件，按空状态继续')\n              raise SystemExit(0)\n\n          try:\n              with sqlite3.connect(db) as connection:\n                  result = connection.execute('PRAGMA quick_check').fetchone()[0]\n              if str(result).lower() != 'ok':\n                  raise RuntimeError(f'PRAGMA quick_check={result}')\n              print('✅ 研究状态数据库恢复完成且 quick_check=ok')\n          except Exception as exc:\n              print(f'⚠️ 恢复的研究状态数据库不可用，将从空状态继续: {exc}')\n              for suffix in ('', '-wal', '-shm'):\n                  path = Path(f'{db}{suffix}')\n                  if path.exists():\n                      path.unlink()\n          PY\n"""

if 'id: research-state-restore' not in text:
    if checkout not in text:
        raise SystemExit('checkout anchor not found')
    text = text.replace(checkout, restore, 1)

upload_anchor = """      - name: 上传分析报告\n        uses: actions/upload-artifact@v6\n"""
save_steps = """      - name: 整理并校验研究状态数据库\n        if: always() && hashFiles('data/stock_analysis.db') != ''\n        run: |\n          python - <<'PY'\n          import sqlite3\n          from pathlib import Path\n\n          db = Path('data/stock_analysis.db')\n          try:\n              with sqlite3.connect(db) as connection:\n                  connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')\n                  result = connection.execute('PRAGMA quick_check').fetchone()[0]\n              if str(result).lower() != 'ok':\n                  raise RuntimeError(f'PRAGMA quick_check={result}')\n              print('✅ 研究状态数据库 checkpoint 完成且 quick_check=ok')\n          except Exception as exc:\n              print(f'⚠️ 研究状态数据库校验失败，本轮不保存损坏状态: {exc}')\n              for suffix in ('', '-wal', '-shm'):\n                  path = Path(f'{db}{suffix}')\n                  if path.exists():\n                      path.unlink()\n          PY\n\n      - name: 保存研究状态数据库\n        if: always() && hashFiles('data/stock_analysis.db') != ''\n        uses: actions/cache/save@v4\n        with:\n          path: |\n            data/stock_analysis.db\n            data/stock_analysis.db-wal\n            data/stock_analysis.db-shm\n          key: research-state-v1-${{ runner.os }}-${{ github.run_id }}\n\n      - name: 上传分析报告\n        uses: actions/upload-artifact@v6\n"""

if 'uses: actions/cache/save@v4' not in text:
    if upload_anchor not in text:
        raise SystemExit('upload anchor not found')
    text = text.replace(upload_anchor, save_steps, 1)

required = [
    'actions/cache/restore@v4',
    'PRAGMA quick_check',
    'PRAGMA wal_checkpoint(TRUNCATE)',
    'actions/cache/save@v4',
    'research-state-v1-${{ runner.os }}-${{ github.run_id }}',
]
missing = [needle for needle in required if needle not in text]
if missing:
    raise SystemExit(f'missing expected workflow fragments: {missing}')

WORKFLOW.write_text(text, encoding='utf-8')
print('research state persistence patch applied')
