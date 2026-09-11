# To Tickets

把 spec、issue 或已收敛讨论拆成适合独立 agent context 执行的 tracer-bullet tickets。规则真源是 `AGENTS.md`；执行细节参考 `docs/ai-collaboration-architecture.md`。

## Usage

```text
/to-tickets <spec | issue | current plan>
```

## Core Rule

每个 ticket 必须是**窄而完整的纵向切片**：完成后有一个可验证行为，而不是“先改 schema、再改 service、再补 tests”这种横向分层。

## Process

### 1. Gather authoritative context

读取 source spec/issue 和必要的 ADR、schema、测试 prior art。不要把整个仓库或完整历史聊天重新塞进 context。

### 2. Draft the dependency graph

为每个 ticket 写：

- `Title`
- `What it delivers`
- `Blocked by`
- `Acceptance criteria`
- `Risk / compatibility constraints`
- `Evidence required`

无 blocker 的 ticket 构成当前 frontier，可以并行；有 blocker 的只能在前置完成并验证后开始。

### 3. Size for fresh context

一个 ticket 应该：

- 能在一个 fresh agent context 内完成；
- 不需要重新讨论上游已经冻结的设计；
- 自带足够 pointer，下一 session 无需重放整段聊天；
- 有最高 practical test seam；
- 能独立验证并安全回滚。

如果 ticket 同时包含多个独立行为，继续拆分。如果拆完后每个 ticket 都只能改一个层而无法独立验证，说明切片过细，重新组合成纵向 slice。

### 4. Wide-refactor exception

机械性、全仓 blast-radius 变更使用：

`expand -> migrate batches -> contract`

每一步明确 blocker，尽量让 CI 在中间状态保持绿色。不要为了符合“纵向切片”而制造不可合并的半成品。

### 5. Ticket template

```markdown
# <NN>: <Title>

## What To Build
<从可观察行为描述该切片>

## Blocked By
<ticket ids or None>

## Acceptance Criteria
- [ ] ...

## Constraints
- frozen contract / compatibility / runtime-data semantics

## Validation
- seam:
- commands / CI evidence expected:

## Rollback
- ...
```

### 6. Publish

- 用户指定 GitHub issue tracker 时：在获得创建/修改 issue 的授权后，一 ticket 一 issue，按依赖顺序发布。
- 本地规划时：一 ticket 一文件，放在 `.claude/reviews/tickets/<feature>/`。
- 不建立一份巨大的 combined ticket 文档；依赖关系需要可单独消费。

## Completion Gate

拆分完成时必须满足：

- 每个验收条件都被至少一个 ticket 覆盖；
- 不存在循环 blocker；
- frontier 明确；
- 每个 ticket 能在 fresh context 中理解；
- 高风险语义没有被拆到无人负责的缝隙中；
- spec 中的 Out of Scope 没被偷偷重新引入。

## Next Step

从 frontier 选择 ticket，以 fresh context 执行 `/implement-ticket`。完成并验证后再解锁后继 ticket。
