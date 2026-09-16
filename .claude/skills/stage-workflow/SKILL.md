---
name: stage-workflow
description: Implement exactly one explicitly approved development stage without expanding scope. Use when the owner asks to start or continue a numbered stage (e.g. "implement 10C.3").
disable-model-invocation: true
argument-hint: "[stage label and requirements]"
---

# Stage workflow

Implement only the stage described by `$ARGUMENTS`. Follow the canonical workflow from `CLAUDE.md`:

**Stage → Implementation → Automated verification → PASS/FAIL → Owner verification → Commit → Push → Deploy → Production verification**

## Before editing

1. Read `docs/development-progress.md` and run `git log --oneline -5` to confirm the last completed stage.
2. Run `git status --short` and inspect `git diff` — preserve valid uncommitted work.
3. Read only source files, tests, and architecture docs directly relevant to this stage.
4. State before any edit:
   - last completed stage
   - current stage scope (exact boundaries)
   - files to touch
   - tests to run
   - PASS criteria

## During implementation

- Implement the smallest coherent change that satisfies the stage contract.
- Do not refactor unrelated code, implement future stages, or redesign completed stages.
- **Local Docker is prohibited.** Use native tooling: `pytest`, `vitest`, `tsc --noEmit`, `vite build`.
- If a test requires infrastructure unavailable without Docker, report it — do not start containers.
- Mobile-first: all new frontend UI must work at 320–480 px. Cosmetic polish is deferred.

## After implementation

Run `/stage-verify $ARGUMENTS` — do not commit or push from this skill.

Never start the next stage without explicit owner approval.
