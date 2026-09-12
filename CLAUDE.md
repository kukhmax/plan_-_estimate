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

## Mobile-First UI (permanent product rule)

Plan & Estimate is a Telegram Mini App intended primarily for on-site use from a smartphone. The frontend remains a web application because Telegram Mini Apps run inside Telegram WebView, but there is **no separate desktop-oriented UI**: the canonical UI target is **MOBILE FIRST**.

- **Primary working viewport**: 320–480 px width.
- **Primary manual acceptance viewports**: 390 px and 412 px.
- Localhost desktop browser usage is primarily a development and debugging environment.

Rules:

1. Mobile layout is authoritative.
2. New UI must be designed first for approximately 390–412 px.
3. Every primary action must remain usable at 320 px minimum width unless a component has an explicitly documented exception.
4. No horizontal page scrolling.
5. Text, badges, and labels must wrap safely.
6. Long names must never collide with action buttons.
7. Prefer vertical stacking over squeezing controls horizontally.
8. Primary actions should normally use full available width where appropriate.
9. Touch targets should be approximately >=44 px for important interactive controls.
10. Avoid tiny icon-only controls for important actions unless their meaning is unambiguous.
11. Forms must use mobile-appropriate input behavior: `inputMode="decimal"` for decimal measurements, `inputMode="numeric"` where appropriate, and correct textarea/select/button sizing.
12. Telegram WebView navigation is authoritative: Telegram BackButton, application breadcrumbs/back hierarchy, and no desktop-only navigation dependency.
13. Do NOT spend development effort creating desktop-specific layouts unless explicitly requested by the project owner.
14. Responsive desktop behavior may remain functional, but desktop visual optimization is NOT an acceptance criterion.
15. Avoid adding `sm:`/`md:`/`lg:` layout changes merely to make the desktop version prettier when they complicate the mobile layout.
16. Every frontend execution sub-stage must include mobile regression verification.
17. For UI-heavy stages, acceptance must explicitly check: 390 px, 412 px, wrapping, overflow, touch targets, and long PL/RU translations.
18. Polish and Russian localization must be tested because Russian labels may be materially longer than Polish labels.

**Field-usage principle**: optimize workflows for a contractor standing at a construction site and using the phone with minimal taps — prefer short workflows, large controls, progressive disclosure, secondary actions hidden behind "Opcje" where appropriate, sensible defaults, reuse of previous/default dimensions where safe, and avoiding unnecessary screens and repeated data entry. This principle should guide later Stage 5F/5G follow-up work, inspection workflows, photos, defect annotations, estimates, checklists, and reports.

## ROADMAP IMMUTABILITY

- The 21-stage sequence (Stage 0 to Stage 20) in `docs/development-progress.md` is the canonical product roadmap confirmed by the project owner.
- Claude Code must never renumber, reorder, insert, remove, rename, merge, or split canonical product stages.
- Implementation sub-stages (such as 5A, 5B, 5C) may be used only within the same canonical product stage and must strictly preserve the parent stage's scope and ordering.
- Historical Git commit labels (such as `feat(stage-5a)`) reflect past development iterations and do not override or redefine the canonical stage mapping.
- Explicit project-owner approval is strictly required to change this roadmap or to start any new stage.

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
