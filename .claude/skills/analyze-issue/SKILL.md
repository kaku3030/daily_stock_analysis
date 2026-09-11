# Analyze Issue

分析 GitHub Issue，判断其真实性、优先级、仓库责任边界与建议动作。优先遵循仓库根目录 `AGENTS.md`；协作流程参考 `docs/ai-collaboration-architecture.md`。

## Usage

```text
/analyze-issue <issue_number>
```

## Step 1: Resolve repository and baseline

禁止硬编码历史 owner/repo。先解析当前仓库：

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
git status --short
git fetch --all --prune
# 仅当工作区干净且当前分支可 fast-forward 时：
git pull --ff-only
```

- 仓库身份无法确认时 fail-loud，不猜测 fallback repository。
- 如存在本地改动、冲突、未跟踪风险文件、无 upstream 或无法 fast-forward，不执行 stash/reset/强制切分支；使用已 fetch 的远端 refs 做分析。
- Evidence 中记录本地 HEAD、使用的远端基线，以及未更新工作树的原因（如有）。

## Step 2: Fetch issue evidence

```bash
gh issue view <issue_number> --repo "$REPO"
gh issue view <issue_number> --repo "$REPO" --comments
```

Bug 优先检查：

- 版本/commit baseline；
- 运行环境；
- 最小复现步骤；
- 原始日志/错误/时间戳；
- 是否仍能在当前 main 复现。

## Step 3: Answer the core questions

1. 版本是否明确？
2. 问题是否真实且可验证？
3. 是否属于本仓库责任边界？
4. 是否值得现在处理？
5. 是否需要进入 `/diagnose-bug`，还是已有足够证据直接走 Fast Path？

## Step 4: Read the smallest authoritative surface

只读取定性 issue 所必需的代码、配置、测试、schema、workflow 和专题文档。

- API / schema / provider / fallback / report / notification / auth / schedule / desktop 等问题必须明确影响路径。
- 怀疑已修复时，以当前代码/测试/CI 证据为准，不只看 issue 描述。
- timestamp/currentness/provider/restart 等高风险语义若仍为 UNKNOWN，不用“看起来合理”的默认值补齐。

## Step 5: Classify and route

至少给出：

- `版本基线`：最新 / 非最新 / 未提供
- `是否合理`：是 / 否 + 理由
- `是否是 issue`：是 / 否 + 理由
- `结论`：`成立 / 部分成立 / 不成立`
- `分类`：`bug / feature / docs / question / external`
- `优先级`：`P0 / P1 / P2 / P3`
- `难度`：`easy / medium / hard`
- `建议动作`：`立即修复 / diagnose-bug / to-spec / 排期 / 文档澄清 / 关闭`
- `执行路径`：`Fast Path / Deep Path`

Routing：

- 清楚、低风险、已有 test seam -> `/fix-issue` 或 `/implement-ticket`
- 难复现/根因不明 -> `/diagnose-bug`
- 有新契约/跨模块/未决设计 -> `/to-spec`

## Step 6: Persist analysis

保存到 `.claude/reviews/issues/issue-<number>.md`：

```markdown
# Issue #<number> Analysis

**Status**: Pending Review

## Summary
- baseline:
- conclusion:
- category:
- priority:
- difficulty:
- route:

## Evidence
- repository / baseline:
- issue evidence:
- code/test/workflow evidence:

## Impact Scope
- modules:
- runtime paths:

## Root Cause / Main Reasoning

## Proposed Handling

## Risks And Rollback

## Draft Reply
```

## Allowed Auto-Actions

- 拉取 issue 详情与评论；
- `git fetch --all --prune`，以及满足安全条件时 `git pull --ff-only`；
- 阅读相关仓库内容；
- 运行非破坏性验证；
- 生成本地分析文档。

## Actions Requiring Confirmation

遵循 `AGENTS.md`。尤其在执行 label/comment/close、commit/push、创建 PR 或其它外部写操作前，必须有用户明确授权。
