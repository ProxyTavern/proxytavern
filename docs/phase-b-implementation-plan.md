# Phase B Implementation Plan (Short, AC-Mapped)

Status: ACTIVE  
Date (UTC): 2026-02-26

## Scope for this run
Primary run DoD target:
- Queue pending creation + approve/reject + approve-with-edit working with tests
- SQLite-backed persistence for currently implemented mode/rules/session/queue flows
- AC mapping evidence included
- No regressions to existing `chat.completions` inline flow

## AC Mapping Plan

1. **Queue lifecycle core implementation**
   - Build mode-aware orchestrator (`inline|queued`) for `chat.completions`
   - Persist in-memory session + queue states for deterministic tests
   - Implement queue decision handlers:
     - approve as-is
     - reject
     - approve-with-edit
   - **AC targets:** AC-Q1, AC-Q2, AC-Q3, AC-F1

2. **Auth hardening matrix starter (for this increment)**
   - Keep token verification path explicit in processing API and queue decision API hooks
   - Ensure queue actions are modeled as protected operator actions in code contracts
   - **AC targets:** AC-S1, AC-S4 (partial coverage this run)

3. **Selector validation + deterministic transforms**
   - Introduce selector validator (safe subset) with clear rejection semantics
   - Ensure stable transform output for identical input/rules
   - **AC targets:** AC-R2, AC-R3 (starter implementation + tests where in scope)

4. **Tests and AC evidence**
   - Add focused tests for queue lifecycle and inline non-regression
   - Produce explicit AC-to-test evidence doc
   - **AC targets:** AC-Q1, AC-Q2, AC-Q3, AC-F1

## Small, reviewable commit slices (execution order)
1. `feat(core): add session/queue domain models and mode orchestrator`
2. `feat(queue): add approve/reject/approve-with-edit lifecycle`
3. `test(queue): cover pending creation and decision paths + inline regression`
4. `docs(ac): add acceptance mapping evidence for implemented criteria`

## Out of scope for this run
- Full persistence backend migrations
- Full admin/UI auth middleware and token lifecycle revoke/rotate completion
- ST extension packaging finalization
- Compose/LAN hardening completion
