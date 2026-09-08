# Git & Release Workflow

## 1. Iterative Stage Discipline
- Development proceeds strictly in **isolated, sequential stages** (Stage 0, Stage 1, Stage 2, ...).
- **One Stage = One Logical Commit**: Every completed stage corresponds to exactly one clean git commit and immediate push.
- **Never start Stage X+1 automatically**: Always wait for explicit review and instruction before embarking on the subsequent stage.
- **Preserve Prior Work**: Never refactor or alter working modules from previous stages unless required for the current stage's contract.

## 2. Pre-Implementation Checklist
Before writing code for any stage:
1. Re-read `GEMINI.md` and all `.agents/rules/*.md` files.
2. Inspect the current state of the repository (`git status`, file structure).
3. Review changes from all previous stages.
4. If the stage is non-trivial, produce a concise implementation plan before writing code.

## 3. Verification Protocol (The Gatekeeper)
A stage is strictly **INCOMPLETE** until all of the following conditions pass:
1. **Automated Tests**: All backend `pytest` and frontend `vitest` tests pass with zero failures.
2. **Typecheck & Linting**: `mypy`/`ruff` for Python and `tsc --noEmit` for TypeScript pass without errors.
3. **Build**: Frontend `vite build` succeeds without warnings/errors where applicable.
4. **Manual Verification**: Functional walkthrough confirms features work end-to-end.
5. **Git Review**: Working tree is clean, untracked unwanted files are absent.
6. **Documentation**: `docs/development-progress.md` is updated with the stage details.

### If Verification Fails:
- **STOP immediately**.
- Do NOT commit.
- Do NOT push to remote.
- Do NOT proceed to the next stage.
- Reproduce the failure.
- Add a regression test where possible.
- Make the smallest coherent fix.
- Re-run the entire verification suite from the beginning.

## 4. Git Review & Commit Procedure

### Step 1: Status and Diff Inspection
```bash
git status
git diff --stat
git diff
```

### Step 2: Forbidden Files Check
Verify that none of the following are staged or present in the diff:
- `.env` or any file containing API tokens/secrets
- SQLite, PostgreSQL dump, or any local database files
- Uploaded client images / photos
- Generated PDF documents
- `node_modules/`, `dist/`, `.vite/`
- `__pycache__/`, `*.pyc`, `.pytest_cache/`
- IDE config files (`.idea/`, `.vscode/`, `.DS_Store`, `.directory`)

### Step 3: Update Development Progress
Update `docs/development-progress.md` with:
- Summary of changes
- Database migrations added/applied
- Test results
- Manual verification notes

### Step 4: Commit with Standardized Template
```bash
git commit -m "$(cat << 'EOF'
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
EOF
)"
```
Allowed commit types: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`.

### Step 5: Post-Commit Inspection & Push
```bash
git log -1 --stat
git push origin <current-branch>
```

### Step 6: Final Report Format
After push succeeds, present the completion report:
- **Branch**: `<branch-name>`
- **Commit Hash**: `<commit-hash>`
- **Commit Title**: `<commit-title>`
- **Tests Passed**: `<test-count-and-status>`
- **Manual PASS Status**: `PASS` (with brief notes)
- **Push Result**: `SUCCESS` to `git@github.com:kukhmax/plan_-_estimate.git`
