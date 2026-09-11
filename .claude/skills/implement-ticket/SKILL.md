# Implement Ticket

在 fresh context 中实现一个已经收敛的 ticket/spec slice。规则真源是 `AGENTS.md`；执行细节参考 `docs/ai-collaboration-architecture.md`。

## Usage

```text
/implement-ticket <ticket | issue | spec slice>
```

## Intent

Implementation phase 的职责是**实现已经决定的行为**，不是重新设计需求。发现真正阻断的 spec contradiction 时才停下来升级；普通实现选择在已有契约内完成。

## Process

### 1. Load only the execution packet

必须读取：

- ticket/spec 本体；
- `AGENTS.md`；
- ticket pointer 指向的相关 ADR/专题文档；
- 当前实现与最接近的 tests / fixtures / schemas。

不要为了“保险”重放完整聊天历史或读取无关模块。

### 2. Verify blockers and baseline

- 所有 blocker 必须已完成且其关键证据可见；否则停止并报告。
- 记录 base commit / PR head。
- 如需 GitHub CLI，动态解析仓库，不使用历史 hard-coded repo name：

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
```

### 3. Pin the acceptance seam

实施前先写下：

```text
Behavior to prove:
Highest practical seam:
Red/green or before/after signal:
```

Bug ticket 优先先跑 `/diagnose-bug` 或复用其 red-capable loop。Feature ticket 优先先建立能证明 acceptance criterion 的测试/fixture/可观察证据。

### 4. Implement the minimum complete slice

- 复用现有模块、配置、schema 与测试模式。
- 同一个契约只在一个权威层修正，避免各入口分别 patch。
- 保持兼容性和现有 fallback 语义，除非 ticket 明确修改它们。
- 不顺手做 unrelated refactor。
- 新增配置、CLI/API、通知、报告、部署或用户可见行为时，按 `AGENTS.md` 同步相关文档/`.env.example`/CHANGELOG。

### 5. Validate in escalating order

先跑最窄、最快、最能证明行为的检查，再扩大到仓库验证矩阵要求的范围：

1. targeted test / replay / fixture；
2. affected module checks；
3. `AGENTS.md` 要求的 CI/build matrix；
4. 只有存在跨层风险时才扩大到更广测试。

不要用“全套测试跑过”替代对 ticket acceptance criterion 的直接证明。

### 6. Self-review before handoff

逐项确认：

- Spec: 是否完整实现 ticket，没有 scope creep；
- Standards: 是否符合 `AGENTS.md` 与现有约定；
- Runtime/Data Semantics: 是否保留 UNKNOWN、timestamp/currentness、provider/fallback、restart/persistence 等相关语义；
- Tests: 是否覆盖真实风险 seam；
- Docs: 是否只有一个权威解释位置；
- Rollback: 是否明确。

### 7. Deliver evidence

交付至少包含：

```markdown
## Changes
## Acceptance Evidence
## Validation
## Unverified / UNKNOWN
## Risks
## Rollback
## Next Unblocked Tickets
```

如果需要 commit/push/PR，遵循 `AGENTS.md` 的确认规则。不要因为 implementation 完成就自动执行发布动作。

## Fast-Path Rule

对于低风险、小范围、无新契约的任务，可以由 `/analyze-issue` 直接进入本 skill；不强制为了流程完整而制造 spec/ticket 文档。
