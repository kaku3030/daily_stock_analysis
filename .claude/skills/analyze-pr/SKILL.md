# Analyze PR

分析 GitHub Pull Request，评估必要性、描述完整性、验证证据、主要风险与是否可合入。优先遵循 `AGENTS.md` 和 `.github/PULL_REQUEST_TEMPLATE.md`；执行架构参考 `docs/ai-collaboration-architecture.md`。

## Usage

```text
/analyze-pr <pr_number>
```

## Step 1: Resolve repository and baseline

禁止硬编码历史 owner/repo：

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
git status --short
git fetch --all --prune
# 仅当工作区干净且可 fast-forward 时：
git pull --ff-only
```

仓库无法确认时 fail-loud。存在本地风险状态时不 stash/reset/强制切分支；使用 origin/main、PR head 和 GitHub diff 做分析。

## Step 2: Pull the smallest useful evidence first

```bash
gh pr view <pr_number> --repo "$REPO"
gh pr checks <pr_number> --repo "$REPO"
gh pr diff <pr_number> --repo "$REPO"
```

只有需要理解讨论或失败原因时再拉 comments / failed logs。不要默认 checkout PR，也不要默认重跑完整本地 suite。

优先级：`CI result -> diff -> targeted logs/tests -> broader local verification`。

## Step 3: Check PR contract

检查 title 与 `.github/PULL_REQUEST_TEMPLATE.md`，至少覆盖：

- PR Type
- Background And Problem
- Scope Of Change
- Issue / spec link
- Verification Commands And Results
- Visual Evidence（报告/UI 变化时）
- Compatibility And Risk
- Rollback Plan

第三方模型/API、fallback、配置迁移等变更还要确认官方来源、兼容窗口、旧配置行为和最小回滚路径。

## Step 4: Review on three independent axes

三个轴分别下结论，不用一个总分相互抵消。

### A. Standards

检查：

- `AGENTS.md` / repo documented conventions；
- scope 是否最小；
- API/schema/client compatibility；
- security / secrets；
- fallback / notification / deploy / config docs；
- duplicated logic、speculative abstraction、shotgun edits 等明显 maintainability smells；
- tooling 已自动强制的格式问题不重复当成人工 blocker。

### B. Spec

找到 originating issue/spec/ticket，检查：

- 缺失或只部分实现的 requirement；
- diff 中未被请求的 scope creep；
- 表面实现但行为与 acceptance criteria 不符；
- 已冻结设计是否被 implementation phase 偷偷重开。

无 spec 时明确报告 `no spec available`，不要自己补一个想象的 spec。

### C. Runtime / Data Semantics

当 PR 触及对应路径时检查：

- timestamp / timezone / market-session boundary / currentness；
- provider capability / entitlement / subscription / fallback；
- UNKNOWN 是否被默认值或静默路径吞掉；
- restart / continuity / reconciliation / persistence；
- portfolio/runtime truth；
- enum/state transition/schema meaning；
- replay fixture 与 production path 是否语义一致。

不相关时该轴写 `N/A`，不要制造无关 findings。

## Step 5: Validate proportionally

CI 已覆盖并且证据足够时直接引用；只有 gap 存在时做最小补充验证。

- 后端：targeted pytest / `./scripts/ci_gate.sh` / py_compile，按影响面选择。
- Web：lint + build，必要时 API 联调。
- Desktop：先 Web，再 Electron/build path。
- AI governance：`python scripts/check_ai_assets.py`。

验证必须直接证明 PR 的关键 acceptance/risk，不以“跑了很多测试”代替语义证据。

## Output

保存到 `.claude/reviews/prs/pr-<number>.md`：

```markdown
# PR #<number> Analysis

## Standards Findings
- [severity] file:line - finding - evidence

## Spec Findings
- [severity] requirement - finding - evidence

## Runtime / Data Semantics Findings
- [severity] contract - finding - evidence

## Summary
- necessity:
- scope:
- description completeness:
- validation:
- merge readiness:

## Validation Evidence
- baseline:
- CI:
- targeted verification:
- unverified / UNKNOWN:

## Compatibility And Risk

## Rollback

## Draft Review Comment
```

严重问题优先给出 file/line 或明确 contract/evidence；不要用篇幅淹没 blocker。

## Allowed Auto-Actions

- 拉取 PR 元数据、diff、comments、CI 和失败日志；
- 安全 fetch/pull；
- 阅读仓库内容；
- 运行必要的非破坏性 targeted verification；
- 生成本地 review 文档。

## Actions Requiring Confirmation

遵循 `AGENTS.md`。发布评论、Approve、Request Changes、merge/close、commit/push 等外部写动作必须有用户明确授权。
