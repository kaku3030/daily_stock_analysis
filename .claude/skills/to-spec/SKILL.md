# To Spec

把已经讨论清楚的需求、issue 或研究结论整理成可执行 spec。规则真源是 `AGENTS.md`；执行细节参考 `docs/ai-collaboration-architecture.md`。

## Usage

```text
/to-spec <issue | topic | current conversation>
```

## Intent

这是**整理已经获得的决定**，不是重新开启一轮无限访谈。只有真正影响契约、测试 seam 或风险边界的 UNKNOWN 才需要回问。

## Process

### 1. Resolve the source and baseline

- 读取用户指定的 issue / PR / 讨论 / 文档及其必要上下文。
- 只探索与当前需求有关的代码、schema、配置、测试和专题文档。
- 使用仓库现有 domain vocabulary；已有 ADR/冻结规则优先。
- 不把容易过时的文件路径或实现细节当成产品契约，除非它本身就是冻结接口。

### 2. Identify the highest useful test seam

优先复用现有 seam。定义“完成后什么外部行为可以证明需求成立”。

高风险 runtime/data 需求还要声明：

- UNKNOWN 如何处理；
- timestamp/timezone/currentness 的来源与语义；
- fallback / restart / persistence / compatibility 行为；
- 哪些失败必须 fail-loud。

### 3. Write the spec

使用以下结构：

```markdown
# <Feature / Fix> Spec

## Problem Statement
<从用户/系统行为角度描述问题>

## Desired Behavior
<完成后可观察到的行为>

## Scope
- In scope:
- Out of scope:

## Contracts And Decisions
- API / schema / state / data semantics / compatibility decisions
- frozen constraints and invariants

## Acceptance Criteria
- [ ] 可验证行为 1
- [ ] 可验证行为 2

## Testing Decisions
- highest practical seam
- prior art / fixture / replay strategy
- adversarial or boundary cases

## Risks And Rollback
- risks:
- rollback:

## Open Questions
- 只保留真正阻断实施的 UNKNOWN；没有则写 None
```

### 4. Completion gate

Spec 完成必须满足：

- 问题与期望行为不矛盾；
- 每个关键决定只有一个明确口径；
- 验收条件可观察、可测试；
- Out of Scope 明确，防止 implementation phase 重新设计；
- 不把未经验证的假设伪装成决定；
- blocker UNKNOWN 已显式列出。

### 5. Persist without duplication

优先把 spec 放在用户指定的 issue/文档位置。若只是工作草案，保存到 `.claude/reviews/specs/<slug>.md`；需要长期治理或团队协作时，再根据用户确认发布到 GitHub issue 或正式 `docs/`。

不要同时在多处复制同一份 spec。其它位置只放 pointer。

## Next Step

Spec 已闭合后进入 `/to-tickets`。若需求很小且满足 Fast Path 条件，可跳过 ticket 拆分，直接进入 `/implement-ticket` 或 `/fix-issue`。
