# Handoff

把当前 session 压缩成下一位 agent / 下一 context 可以立即继续的 execution packet。规则真源是 `AGENTS.md`；执行细节参考 `docs/ai-collaboration-architecture.md`。

## Usage

```text
/handoff <next-session focus>
```

## Core Rule

Handoff 不是聊天摘要，也不是项目历史备份。已经存在于 issue/spec/ADR/PR/diff/test artifact 中的内容只放 pointer，不重复粘贴。

## Process

### 1. Identify the continuation unit

明确下一 session 到底要继续：

- 哪个 ticket / issue / PR；
- 当前目标；
- 当前 phase；
- 最后一个已验证 baseline。

如果没有清楚的 continuation unit，先把当前工作收敛到一个可执行边界再 handoff。

### 2. Write the packet

```markdown
# Handoff: <focus>

## Objective
<下一 session 要完成什么>

## Verified Baseline
- commit / PR / ticket:
- last passing evidence:

## Current State
- completed:
- in progress:
- UNKNOWN / blockers:

## Frozen Decisions
- 只列下一步必须知道、且尚未在 durable artifact 中表达的决定

## Pointers
- spec / issue / ADR / PR / test / relevant docs

## Next Executable Action
1. ...
2. ...

## Suggested Skills
- /implement-ticket
- /diagnose-bug
- /analyze-pr
<按实际需要选择>

## Risks
- ...
```

### 3. Token discipline

- 不粘贴大日志；只引用 artifact/path/URL 与关键行。
- 不复制完整 diff；引用 commit/PR。
- 不重复 `AGENTS.md` 规则；只写 pointer。
- 不重复 spec 已冻结的决定。
- 删除已经完成且对下一 action 无影响的历史。

### 4. Security

不得写入 token、API key、cookie、密码、私密账号数据或未经脱敏的请求头。必须保留的敏感证据只描述位置和访问方式，不复制内容。

## Completion Gate

Fresh agent 只读取 handoff + pointers 后，应能回答：

1. 我现在要做什么？
2. 从哪个已验证状态开始？
3. 哪些决定已经冻结，不能重开？
4. 什么仍是 UNKNOWN？
5. 下一条可执行命令/动作是什么？

若回答不了，handoff 还没有完成。
