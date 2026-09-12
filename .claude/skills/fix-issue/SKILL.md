# Fix Issue

基于已确认 issue 或 diagnosis 结果做最小修复，并补齐 acceptance evidence、验证、风险与回滚。规则真源是 `AGENTS.md`；执行架构参考 `docs/ai-collaboration-architecture.md`。

## Usage

```text
/fix-issue <issue_number>
```

## Prerequisites

优先先完成 `/analyze-issue`。根因不明、复现不稳定或涉及时序/currentness/provider 等复杂路径时，先执行 `/diagnose-bug`。

## Step 1: Resolve repository and analysis baseline

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
git status --short
git fetch --all --prune
# 仅当工作区干净且可 fast-forward 时：
git pull --ff-only
```

禁止硬编码历史 repository。仓库身份无法确认时 fail-loud。

检查 `.claude/reviews/issues/issue-<number>.md` 或用户指定 diagnosis/spec；如果不存在，先补齐最小成立性与影响边界。不要在 implementation 阶段重新设计已经冻结的 contract。

## Step 2: Pin the proving seam

实施前明确：

```text
Exact symptom / desired behavior:
Highest practical test seam:
Red-capable loop or before/after evidence:
```

Bug 有正确 seam 时，先让 regression test 或 replay 在修复前失败。若不存在正确 seam，明确记录 architecture gap，不用浅层 test 制造假安全感。

## Step 3: Implement the minimum contract-level fix

- 优先修复最上游、最权威的 contract，而不是在多个 caller 逐个 patch。
- 复用现有 module/config/schema/test fixture。
- 保持默认行为与 compatibility/fallback，除非 issue 明确要求变化。
- 不夹带 unrelated refactor。
- 用户可见行为、配置语义、CLI/API、部署、通知、报告结构变化按 `AGENTS.md` 同步 docs / `.env.example` / `docs/CHANGELOG.md`。
- timestamp/currentness/provider/restart/portfolio truth 等高风险语义必须保留 UNKNOWN/fail-loud 约束，不用方便的默认值消除不确定性。

## Step 4: Validate narrowly, then widen as required

顺序：

1. 原始 repro / tight loop；
2. regression test / targeted fixture；
3. affected-module checks；
4. `AGENTS.md` 验证矩阵要求的更广 CI/build。

如无法完成某项验证，记录原因、UNKNOWN 与风险。不要用未运行的命令冒充 evidence。

## Step 5: Update analysis artifact

在 `.claude/reviews/issues/issue-<number>.md` 追加：

```markdown
## Fix Implementation

### Changes Made
- ...

### Acceptance Evidence
- original symptom:
- proof after fix:

### Validation
- executed:
- not executed / UNKNOWN:

### Risks
- ...

### Rollback
- ...
```

## Step 6: Self-review

交付前检查三个轴：

- **Standards**：是否符合 `AGENTS.md`、兼容性和最小改动原则；
- **Spec**：是否真正解决 issue，且无 scope creep；
- **Runtime / Data Semantics**：相关时是否正确处理 timestamp/currentness/provider/fallback/restart/persistence/schema meaning。

随后可使用 `/analyze-pr` 做独立审查。

## Allowed Auto-Actions

- 阅读和分析代码；
- 安全 fetch/pull；
- 实施当前 issue 直接需要的最小修复；
- 运行非破坏性验证；
- 更新本地 analysis artifact。

## Actions Requiring Confirmation

遵循 `AGENTS.md`。切换/创建分支、commit、push、创建 PR、回复或关闭 issue 等写操作需要用户明确授权。
