# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@GEMINI.md
@.agents/rules/architecture.md
@.agents/rules/backend.md
@.agents/rules/frontend.md
@.agents/rules/domain-construction.md
@.agents/rules/git-workflow.md

## Instruction authority

The imported files are the source of truth for project architecture, domain rules, coding standards, and release discipline. Keep this file concise and Claude-specific; do not duplicate those rules here.

## Architecture at a glance

- The monorepo contains a FastAPI/SQLAlchemy backend, a React/TypeScript Mini App, and an aiogram bot.
- Backend request flow is thin API endpoint → domain service → async persistence, with Pydantic schemas at API boundaries.
- Frontend API contracts mirror backend schemas; user-facing strings belong in PL/RU locale dictionaries.
- `PROJECT / OBIEKT` is the central aggregate root. Rooms, surfaces, measurements, inspections, and downstream records must anchor to `project_id` as defined by the imported architecture rules.

## Common commands

Run commands from the repository root unless noted otherwise.

```bash
# Infrastructure
docker compose up -d postgres

# Backend development and tests
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
backend/.venv/bin/pytest backend/tests
backend/.venv/bin/pytest backend/tests/test_clients.py
backend/.venv/bin/pytest backend/tests/test_clients.py::test_create_private_person

# Frontend development, tests, typecheck, and build
npm --prefix frontend run dev
npm --prefix frontend test -- --run
frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit
npm --prefix frontend run build
```

## Mandatory stage workflow

Follow this sequence exactly:

**Stage → Implementation → Tests → PASS/FAIL → Commit → Push**

1. Work only on the stage explicitly requested by the user.
2. Before editing, determine the last completed stage from `docs/development-progress.md` and Git history. Inspect `git status`, `git diff`, and `git log --oneline -10`.
3. Inspect only plans, source files, and tests relevant to the current stage. Do not re-analyze or scan the entire repository without a stage-specific need.
4. Preserve the existing implementation and valid uncommitted work. Do not replace working code merely because another tool or model created it.
5. State the already completed work, remaining work, files to touch, tests to run, and PASS criteria before implementation.
6. Implement the smallest coherent change for the requested stage. Do not refactor unrelated code.
7. Run focused tests first, then relevant regressions, typechecks, builds, and manual checks where applicable.
8. Report **PASS** or **FAIL**. On FAIL, do not commit, push, or begin another stage.
9. On PASS, update `docs/development-progress.md`, inspect the complete diff, create one logical stage commit, and push the current branch.
10. Stop after the push. Starting the next stage always requires explicit user approval.

Never run destructive Git operations—including `git reset --hard`, `git clean`, force-push, branch deletion, or commands that discard uncommitted changes—without explicit user approval for that exact operation.
