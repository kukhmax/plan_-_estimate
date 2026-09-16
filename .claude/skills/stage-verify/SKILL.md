---
name: stage-verify
description: Run the narrowest relevant tests first, then required full suites, typecheck, build, and diff checks for one completed stage. Use after implementation is ready.
disable-model-invocation: true
argument-hint: "[stage label]"
---

# Stage verification

Verify the stage identified by `$ARGUMENTS`. Stop immediately on any failure — do not commit or push.

## Verification sequence

1. **Inspect state**: `git status --short`, `git diff --stat`, `git diff --check`
2. **Focused tests first**: run only tests that directly cover the stage behavior
3. **Backend regression** (if backend files changed): `backend/.venv/bin/pytest backend/tests -q`
4. **Frontend regression** (if frontend files changed): `npm --prefix frontend test -- --run`
5. **Typecheck** (if frontend changed): `frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit`
6. **Production build** (if frontend changed): `npm --prefix frontend run build`
7. **Diff gate**: `git --no-pager diff --check` — must be clean
8. **Scope check**: confirm diff contains no unrelated changes, no secrets, no generated files

## On PASS

1. Update `docs/development-progress.md` with stage status, test counts, and deferred work.
2. Report: stage result, tests passed, files changed, proposed commit message.
3. Call `/git-stage-close` to proceed with commit.

## On FAIL

- Report **FAIL** with exact error.
- Make no commit, no push, do not advance to the next stage.
- Fix only failures belonging to this stage, then rerun verification from step 1.

**Local Docker is prohibited.** If infrastructure is unavailable, report it — do not start containers.
