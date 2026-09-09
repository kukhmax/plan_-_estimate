---
name: stage-implementation
description: Implement exactly one explicitly approved development stage while preserving prior work. Use when the user asks to start or continue a numbered stage.
disable-model-invocation: true
argument-hint: "[stage and requirements]"
---

# Stage implementation

Implement only the explicitly approved stage described by `$ARGUMENTS`.

1. Determine the last completed stage from `docs/development-progress.md` and `git log --oneline -10`.
2. Run `git status`, inspect staged and unstaged `git diff`, and preserve valid uncommitted work.
3. Read `GEMINI.md`, the applicable `.agents/rules/*.md` files, the current-stage plan, and only source files and tests directly relevant to the requested stage.
4. Before editing, report:
   - last completed stage;
   - current stage;
   - already completed work;
   - remaining work;
   - files to touch;
   - tests to run;
   - PASS criteria.
5. Implement the smallest coherent change that completes the requested stage. Preserve existing behavior and avoid unrelated refactoring.
6. Do not implement future-stage functionality, redesign completed stages, or start the next stage.
7. When implementation is ready, stop and use `/stage-verification` for the same stage. Do not commit or push from this skill.

If the requested stage is missing or ambiguous, ask the user to identify it before editing.
