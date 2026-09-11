# MCI-E01 — Currentness Differential Replay Specification

**Initiative:** Minimal Core V0.2  
**Owner for production promotion:** `AI_MONITOR/CONTROL_TOWER`  
**Fixture/evidence contributor:** `RADAR/PERCEPTION_DATA_INTELLIGENCE`  
**Mode:** Shadow / differential only  
**Production behavior change:** none

## 1. Question

Can Stock Razor express Currentness with a smaller, pure, deterministic semantic core while preserving or improving every governed status/reason behavior?

This experiment does **not** assume the answer is yes. It exists to make simplification falsifiable.

## 2. Non-goals

E01 does not:

- change provider workers;
- change polling/subscription behavior;
- change market calendars;
- change Portfolio state;
- ask an LLM whether data is stale;
- add a second Currentness owner;
- change production statuses/reason codes merely to make a new model match;
- promote a state-machine dependency;
- compress evidence.

## 3. Canonical comparison

For every fixture `F`:

```text
                 ┌→ existing_currentness(F) ─→ ExistingResult
Fixture F ───────┤
                 └→ shadow_currentness(F)   ─→ ShadowResult

ExistingResult vs ShadowResult
        ↓
field-by-field semantic diff
```

The existing implementation is the behavioral baseline **except** where a fixture reproduces an already accepted bug. An intentional behavior difference therefore requires an explicit finding; the Shadow implementation cannot redefine expected behavior silently.

## 4. Proposed pure input contract

Research shape only:

```python
CurrentnessInput(
    market,
    instrument,
    request_time,
    latest_timestamp,
    timestamp_quality,
    provider_status,
    entitlement_status,
    subscription_status,
    expected_session,
    observed_session,
    timeframe,
)
```

Fields may be reduced after fixture analysis. Do not add a field unless it changes semantic output.

### Input rules

- timestamps are timezone-aware or explicitly marked UNKNOWN/invalid;
- absence is represented explicitly, never as a fabricated zero/epoch;
- provider/entitlement/subscription findings are observations, not silently converted to Currentness success;
- raw evidence remains outside and retrievable by the authoritative runtime.

## 5. Proposed result contract

Research shape only:

```python
CurrentnessResult(
    status,
    reason_codes,
    expected_session,
    observed_session,
    latest_timestamp,
    evidence_quality,
)
```

Required properties:

- deterministic for the same normalized input;
- JSON-serializable;
- no provider/network calls;
- no wall-clock read inside the evaluator;
- no persistence;
- no AI/model call;
- no notification;
- no Portfolio mutation;
- no fallback from UNKNOWN to guessed values.

## 6. Protected semantics

The differential harness must always compare/protect:

- status (`OK`, `DATA_UNAVAILABLE`, `STALE_OR_MISALIGNED`, or governed successors);
- reason codes;
- expected session identity/date;
- observed/latest timestamp;
- missing timestamp behavior;
- timezone/session interpretation;
- provider availability evidence;
- entitlement/subscription evidence if in scope;
- `UNKNOWN`/indeterminate values.

A result is not equivalent merely because both return the same top-level status if their reason/evidence semantics differ.

## 7. Fixture matrix V0.1

| ID | Market phase | Observation | Core assertion |
| --- | --- | --- | --- |
| C001 | pre-open | previous valid session bar | do not mark stale solely because today's session has not opened |
| C002 | open | current-session bar | current when timestamp/session rules are satisfied |
| C003 | open | previous-session bar | stale/misaligned once current-session evidence is required |
| C004 | intraday | timestamp missing | never `OK` by inference |
| C005 | intraday | malformed timestamp | explicit unavailable/invalid path; no guessed parse |
| C006 | intraday | future timestamp | fail-loud/misaligned; never silently accepted |
| C007 | lunch break | last bar before break | market-specific session semantics; no wall-clock-only stale classification |
| C008 | resume after lunch | no new bar yet | expected behavior fixed by authoritative session/currentness rule |
| C009 | post-close | valid closing/last-session bar | do not require nonexistent after-hours bars |
| C010 | weekend | last trading-session bar | calendar-aware; weekend gap alone is not stale |
| C011 | holiday | last trading-session bar | calendar-aware; holiday gap alone is not stale |
| C012 | timezone boundary | valid market-local session | use explicit market timezone/session identity |
| C013 | provider delayed | timestamp behind expected session | stale/misaligned with traceable reason |
| C014 | provider disconnected | no fresh observation | availability/currentness semantics remain explicit |
| C015 | reconnect | valid current evidence returns | transition must not erase audit history/reconciliation needs |
| C016 | entitlement lost | timestamps may appear cached | entitlement failure cannot be masked by old data |
| C017 | subscription unknown | observation incomplete | UNKNOWN remains explicit; no success inference |
| C018 | daily OK / hourly missing / 15m OK | partial timeframe | aggregate health must not collapse missing timeframe into OK |
| C019 | daily/hourly/15m all valid | complete evidence | overall currentness/health is determinate |
| C020 | bar date ahead of expected | provider/timezone anomaly | stale/misaligned/fail-loud path with reason |

## 8. Market-specific fixture requirements

### A-share

Fixtures must cover at minimum:

- pre-open;
- morning session;
- lunch break;
- afternoon resume;
- close;
- weekend;
- exchange holiday;
- market-local date vs Japan-host date difference where relevant.

### US market

Fixtures must cover at minimum:

- premarket vs regular-session semantic boundary where the data stream contract distinguishes them;
- regular open;
- regular close;
- weekend/holiday;
- DST boundary;
- market timezone vs Japan runtime timezone.

Do not force A-share session rules onto US data or vice versa.

## 9. Sequence fixtures

Single snapshots are insufficient for lifecycle bugs. Replay sequences should include:

### S01 — Normal day

```text
PRE_OPEN → OPEN → BAR → BAR → CLOSE
```

### S02 — Missing timestamp recovery

```text
OPEN → TIMESTAMP_MISSING → VALID_BAR → VALID_BAR
```

Invariant: a later valid bar may restore currentness, but the earlier unknown/missing event is not rewritten out of history.

### S03 — Disconnect/reconnect

```text
VALID → DISCONNECT → NO_DATA → RECONNECT → VALID
```

Invariant: reconnect does not imply currentness until valid evidence arrives/reconciles.

### S04 — Lunch/session boundary

```text
MORNING_BAR → LUNCH → RESUME → NEW_BAR
```

Invariant: lunch does not generate a false stale transition merely because elapsed wall-clock time exceeds a bar interval.

### S05 — Entitlement degradation

```text
VALID → ENTITLEMENT_LOST → CACHED/OLD_DATA → ENTITLEMENT_RESTORED → VALID
```

Invariant: cached timestamps cannot conceal entitlement truth.

### S06 — Restart

```text
VALID → PROCESS_STOP → PROCESS_START → RESTORED_STATE → NEW_EVIDENCE
```

Invariant: restored runtime state does not assert freshness beyond its evidence timestamp; reconciliation precedes authoritative upgrade when required.

## 10. Differential output

For each fixture/step record:

```yaml
fixture_id: C001
existing:
  status: ...
  reason_codes: [...]
shadow:
  status: ...
  reason_codes: [...]
diff:
  status_equal: true|false
  reasons_equal: true|false
  protected_fields_equal: true|false
classification: MATCH | EXISTING_BUG_CANDIDATE | SHADOW_REGRESSION | SPEC_GAP
```

No diff is silently normalized away.

## 11. Generated/stateful extension (E04 bridge)

After deterministic fixtures pass, a generated sequence harness may combine actions such as:

- advance market clock;
- cross a session boundary;
- emit/miss/future-date a bar;
- disconnect/reconnect provider;
- lose/restore entitlement;
- stop/restart runtime.

Invariants are checked after every action.

Hypothesis is only a candidate implementation. The experiment must first prove generated sequences add useful edge-case discovery before adding it to production/test dependencies.

## 12. Metrics

Record before/after:

- branch count in semantic evaluator;
- number of authoritative Currentness state owners;
- number of files required to understand/test one Currentness rule change;
- lines/relevant context read;
- approximate model input tokens for a representative Currentness task;
- test fixture count;
- differential mismatch count;
- hidden fallback count;
- replay determinism;
- mean time to isolate a deliberately seeded Currentness defect, if practical.

## 13. Promotion gates

### Gate A — semantic equivalence

All accepted baseline fixtures match status + reason semantics, except explicit accepted bug fixes.

### Gate B — adversarial safety

Missing/future timestamps, closed sessions, timezone differences, provider loss, entitlement/subscription issues and restart sequences pass.

### Gate C — simplicity

At least one meaningful semantic-complexity/read-set metric improves. Merely moving code to another file does not pass.

### Gate D — ownership

There remains exactly one production Currentness authority under AI Monitor.

### Gate E — rollback

Shadow implementation can be removed without migration or canonical-state repair.

### Gate F — no model authority

No LLM/model participates in the Currentness determination.

## 14. Stop conditions

Reject or redesign the Shadow candidate if:

- reason/evidence semantics become less expressive;
- UNKNOWN is collapsed;
- a new library increases indirection more than branches it removes;
- the evaluator needs hidden I/O;
- market-specific differences become magic special cases rather than explicit inputs/rules;
- read-set does not improve;
- replay becomes less deterministic.

## 15. Handoff

**Next implementation task is not a production refactor.** It is to build the differential fixture/harness around the existing behavior, then implement the smallest Shadow evaluator needed to compare against it.

Sync targets:

- `AI_MONITOR/HARVEST`
- `AI_MONITOR/CONTROL_TOWER`
- `RADAR/PERCEPTION_DATA_INTELLIGENCE`
- `RADAR/CONTROL_TOWER` for visibility

Production promotion requires a separate governed decision after evidence is available.
