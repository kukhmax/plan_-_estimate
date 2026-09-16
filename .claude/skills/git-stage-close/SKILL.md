---
name: git-stage-close
description: Safely inspect, stage, and commit an accepted stage after verification has passed. Push requires explicit owner approval — do not push autonomously.
disable-model-invocation: true
argument-hint: "[stage label]"
---

# Git stage close

Only call this skill after `/stage-verify` has reported **PASS** for the stage in `$ARGUMENTS`.

## Pre-commit checks

Run all of the following before staging files:

```bash
git status --short
git --no-pager diff --check
git --no-pager diff --stat
git --no-pager diff --cached --check
git --no-pager diff --cached --stat
```

All checks must be clean. If `--check` reports whitespace errors, fix them first.

## Forbidden files

Abort if the diff contains any of:
- `.env` or files with secrets/tokens
- `node_modules/`, `dist/`, `.vite/`
- `__pycache__/`, `*.pyc`, `.pytest_cache/`
- `*.sqlite`, `*.db`, database dumps
- `.idea/`, `.vscode/`, `.DS_Store`
- Generated PDFs or uploaded media

## Commit format

```
<type>(stage-X): <short stage description>

Added:
- ...

Changed:
- ...

Database:
- ...

Tests:
- ...

Verification:
- ...

Deferred:
- ...
```

Allowed types: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`.

## After commit

Run `git log -1 --stat` and report the commit hash and title.

## Push

**Requires explicit owner approval.** State the proposed push command and wait for approval:

```bash
git push origin <branch>
```

Never push automatically. Never use `--force` or `--force-with-lease`.
