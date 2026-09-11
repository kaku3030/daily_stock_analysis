# Repository Claude Skills

本目录存放仓库级协作 skills，属于版本库资产。

- 规则真源：仓库根目录 `AGENTS.md`
- 执行架构：`docs/ai-collaboration-architecture.md`
- 兼容入口：根目录 `CLAUDE.md`（应为指向 `AGENTS.md` 的软链接）
- 本目录中的 skill 必须与 `AGENTS.md` 保持一致
- `.claude/reviews/` 属于本地分析产物，不作为规则真源

## Accelerated Workflow

### Fast Path

```text
/analyze-issue
   -> /diagnose-bug      # hard/uncertain bugs only
   -> /fix-issue or /implement-ticket
   -> /analyze-pr
```

适用于范围清楚、低风险、无新跨模块契约的变更。

### Deep Path

```text
/to-spec
   -> /to-tickets
   -> fresh context per ticket
   -> /implement-ticket
   -> /analyze-pr
```

长 session 中断时使用 `/handoff`，让下一 context 只读取 continuation packet 与其 pointers，而不是重放完整聊天。

## Skills

- `analyze-issue`：判断 issue 是否成立、优先级、责任边界与下一动作。
- `diagnose-bug`：先建立 tight red-capable loop，再最小化、证伪假设并形成根因证据。
- `fix-issue`：基于已确认 issue 做最小修复与验证。
- `to-spec`：把已讨论内容收敛成可测试、可执行的 spec。
- `to-tickets`：把 spec 拆成有 blocking edges 的 tracer-bullet vertical slices。
- `implement-ticket`：以 fresh context 实现一个 ticket，不重新打开已冻结设计。
- `analyze-pr`：分 Standards / Spec / Runtime-Data Semantics 三轴审查 PR。
- `handoff`：生成紧凑 continuation packet，减少跨 session context/token 负担。

## Context Discipline

优先使用 pointer + progressive disclosure：`AGENTS.md` 只承载全局规则和入口；专题细节留在对应 docs/ADR/spec/issue 中按需读取。代码、测试、schema、配置和 CI 属于 executable truth，不在多个 skill 中复制其内容。

仓库身份不得硬编码为历史 owner/repo；需要 `gh` 时动态解析当前仓库。无法确认仓库身份时 fail-loud。

如果未来需要兼容其他 agent 目录（如 `.agents/skills/` 或 `.github/skills/`），应先明确单一真源，再通过脚本或镜像同步，而不是手工长期维护多份同义内容。
