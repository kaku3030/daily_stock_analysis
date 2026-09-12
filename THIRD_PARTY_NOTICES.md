# Third-Party Notices

This repository includes software or workflow material derived from third-party projects. The following notices apply to the files identified below.

## AlphaSift

- Project: AlphaSift
- Source: https://github.com/ZhuLinsen/alphasift
- Referenced revision: `9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf`
- License: Apache License 2.0
- Included and modified files: `src/services/screening/**/*.py` and
  `src/services/screening/strategies/*.yaml`
- License copy: `src/services/screening/LICENSE`

The included code has been modified and integrated into
`daily_stock_analysis`. Per-file headers identify the source revision and
modification status.

## mattpocock/skills

- Project: `mattpocock/skills`
- Source: https://github.com/mattpocock/skills
- License: MIT
- Copyright: Copyright (c) 2026 Matt Pocock
- Adapted concepts: context pointers, progressive disclosure, tracer-bullet tickets, phase boundaries, tight debugging loops, handoff packets, and separated review axes.
- Local adaptations: `docs/ai-collaboration-architecture.md` and selected repository collaboration skills under `.claude/skills/`.

The Stock Razor workflow is an adaptation to this repository's existing
`AGENTS.md` governance and is not a verbatim vendoring of the upstream skill
set. The upstream MIT license permits use and modification subject to its
notice requirements.
