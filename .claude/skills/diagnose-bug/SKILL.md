# Diagnose Bug

用于难复现 bug、性能回归、时序/currentness、provider/fallback、状态恢复等问题。规则真源始终是仓库根目录 `AGENTS.md`；执行细节参考 `docs/ai-collaboration-architecture.md`。

## Usage

```text
/diagnose-bug <issue | symptom | failing path>
```

## Core Rule

先建立能抓住**用户所描述症状**的 tight feedback loop，再建立根因假设。没有可验证的红灯信号，不把猜测当结论。

## Process

### 1. Pin baseline

- 记录当前代码/PR/commit 基线。
- 读取最小必要的代码、测试、配置、schema、workflow 与相关 ADR/专题文档。
- 如需 GitHub CLI，动态解析仓库：

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
```

仓库身份无法确认时停止，不对历史仓库名做 fallback。

### 2. Build the red-capable loop

按成本从低到高优先选择：

1. 已有 failing test；
2. 最小 unit/integration test；
3. CLI/HTTP fixture replay；
4. captured payload/event replay；
5. throwaway harness；
6. differential old/new comparison；
7. property/fuzz/stress loop；
8. 必要时受控 HITL。

完成标准：能给出**一个已实际运行过的命令或可重复步骤**，它会在该 bug 出现时失败、修复后变绿，并且尽量快、确定、可无人值守。

如果无法建立 loop：明确列出尝试过什么、缺什么证据，并停止向“根因已确认”升级。

### 3. Reproduce and minimise

- 确认 loop 捕获的是原始症状，而不是附近的另一个错误。
- 一次删除一个输入、配置、调用层或依赖，持续重跑。
- 缩到最小仍失败的场景；保留它作为回归测试候选。

### 4. Rank hypotheses

生成 3–5 个可证伪假设，按概率/证据排序。每个假设写成：

```text
If <cause>, then <probe/change> should produce <observable prediction>.
```

优先测试能最大幅缩小搜索空间的假设，而不是最容易修改代码的假设。

### 5. Instrument one variable at a time

- 优先 debugger/REPL/现有 telemetry；其次是边界处的定向日志。
- 临时日志统一使用唯一前缀，例如 `[DEBUG-a4f2]`，方便完整清理。
- 性能问题先量化 baseline，再改代码。
- timestamp/currentness/provider 问题必须记录原始时间字段、时区、来源、转换结果和 UNKNOWN 路径，避免“看起来合理”的推断。

### 6. Convert evidence into a fix contract

根因成立后，输出：

- `Reproduction`
- `Root Cause`
- `Why Existing Checks Missed It`
- `Minimal Fix Boundary`
- `Regression Seam`
- `Runtime/Data Semantics Risk`
- `Rollback`

若用户要求继续实现，可交给 `/fix-issue` 或 `/implement-ticket`；不要在诊断阶段顺手扩大重构。

### 7. Cleanup

完成前确认：

- 原始 loop 已转绿；
- 回归测试存在，或明确记录为什么当前架构缺少正确 test seam；
- 临时 debug instrumentation 已清理；
- throwaway harness 已删除或明确标注为 debug fixture；
- 根因与关键证据已写入 issue/PR/分析文档中的一个权威位置。

## Stock Razor High-Risk Branches

涉及以下语义时，诊断必须 fail-loud，不用默认值掩盖 UNKNOWN：

- timestamp / timezone / currentness；
- provider capability / entitlement / subscription；
- fallback / fail-open / fail-closed；
- restart / continuity / reconciliation；
- portfolio/runtime truth；
- schema enum / state transition；
- report date / market-session boundary。
