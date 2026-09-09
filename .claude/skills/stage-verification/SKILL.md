---
name: stage-verification
description: Verify, document, commit, and push one completed development stage. Use after implementation is ready for its PASS or FAIL gate.
disable-model-invocation: true
argument-hint: "[stage]"
---

# Stage verification

Verify only the implemented stage identified by `$ARGUMENTS`.

1. Confirm the stage scope and inspect `git status` plus staged and unstaged `git diff`.
2. Run the smallest focused test suite that proves the stage behavior.
3. Run relevant backend and frontend regression suites.
4. When frontend code is in scope, run the TypeScript typecheck and production build. Manually exercise user-facing behavior when applicable.
5. Run `git diff --check` and inspect the complete diff for scope, generated files, credentials, and unrelated changes.
6. If any required check fails, report **FAIL**, make no commit or push, and do not start another stage. Fix only failures belonging to the current stage, then rerun verification from the beginning.
7. Only after all checks pass, update `docs/development-progress.md` with the exact stage changes, test counts, verification results, and deferred work.
8. Inspect the final status and diff, then report the stage result, tests, changed files, and proposed commit message before committing.
9. On **PASS** only, create one logical stage commit using the repository commit format and push the current branch to its existing remote.
10. Confirm the commit and push result, then stop. Never begin the next stage without explicit user approval.

Never use destructive Git operations or bypass hooks. Never commit or push a stage whose verification result is FAIL.
