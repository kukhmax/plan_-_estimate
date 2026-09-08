# Development Progress & Stage Roadmap

**Project**: Telegram Mini App for managing interior finishing and renovation work in Poland.  
**Repository**: `git@github.com:kukhmax/plan_-_estimate.git`  
**Central Entity**: OBIEKT (Project / Site)  
**Stack**: React + TypeScript + Vite + Tailwind CSS | Python + FastAPI + SQLAlchemy 2.x + Alembic + Pydantic v2 + PostgreSQL | aiogram 3.x

---

## Roadmap Overview

| Stage | Title | Status | Primary Focus |
| :--- | :--- | :--- | :--- |
| **Stage 0** | **Engineering Workflow & Architecture Rules** | **Completed** | Foundation rules, `.gitignore`, `.agents/rules/`, `GEMINI.md`, progress tracker |
| Stage 1 | Project Scaffolding & CI Foundation | Pending | Backend FastAPI boilerplate, Frontend Vite React setup, PostgreSQL connection |
| Stage 2 | Core Domain Models & Database Migrations | Pending | User, Client, Obiekt, Room, Surface, Substrate, Quality models & Alembic |
| Stage 3 | Price Book & Estimation Engine | Pending | Deterministic price book, unit calculations, material/labor breakdown |
| Stage 4 | Substrate Inspection & Risk Engine | Pending | Moisture, adhesion, surface diagnostic rules & technical warnings |
| Stage 5 | Telegram Mini App Shell & Auth | Pending | Telegram WebApp SDK, initData HMAC-SHA256 validation, theme adaptation |
| Stage 6 | Room Measurements & Surface Manager UI | Pending | Interactive room dimension inputs, openings subtraction, surface totals |
| Stage 7 | Estimates & Quotation UI | Pending | Estimate generator, PDF export preparation, client approval flow |
| Stage 8 | Technical Protocols & Handover | Pending | Acceptance protocols (stan zero, roboty zanikające, protokół końcowy) |
| Stage 9 | Contracts & Legal Knowledge Modules | Pending | Contract generator, standard clauses, client communication phrases |
| Stage 10 | Offline Drafts & S3 Photo Storage | Pending | IndexedDB offline drafts sync, S3 photo attachments |

---

## Stage Log

### Stage 0: Engineering Workflow & Architecture Rules
- **Status**: Completed
- **Date**: 2026-09-08
- **Commit**: `chore(stage-0): establish project engineering workflow and architecture rules`

#### Added:
- Master operational guide: `GEMINI.md` covering full project context, core domains, stack, and rules.
- Modular rule files in `.agents/rules/`:
  - `architecture.md` (clean architecture, thin controllers, UUID PKs, UTC timestamps, deterministic risk engine).
  - `backend.md` (FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2, aiogram 3.x, initData HMAC validation, no Redis/no AI).
  - `frontend.md` (React, TypeScript strict, Vite, Tailwind CSS, i18n PL/RU, zero hardcoded prices/legal content, IndexedDB).
  - `domain-construction.md` (Polish construction specifics: Obiekt, S1-S4, Q1-Q4/PSG1-PSG4, substrates, work types, risk engine).
  - `git-workflow.md` (iterative discipline, gatekeeper verification, single commit per stage, push checklist).
- Documentation tracker: `docs/development-progress.md`.

#### Changed:
- `.gitignore`: extended with full coverage for Python virtualenvs, Node/Vite outputs, databases, media uploads, PDFs, and IDE/OS files.

#### Database:
- None (Stage 0 - rules and configuration setup).

#### Tests:
- Manual verification of repository configuration and rule consistency.

#### Verification:
- Rule structure validated against all project constraints.
- `.gitignore` verified to exclude `.env`, tokens, local databases, photos, PDFs, `node_modules`, `dist`, `__pycache__`, and IDE files.
- Stage transition rule verified: Stage 1 will not start automatically.

#### Deferred:
- Application source code implementation deferred to subsequent stages.

---

## Stage Log Template for Future Stages

```markdown
### Stage X: [Stage Name]
- **Status**: [Planned | In Progress | Completed]
- **Date**: YYYY-MM-DD
- **Commit**: `type(stage-X): short description`

#### Added:
- ...

#### Changed:
- ...

#### Database:
- Migrations: [e.g. alembic/versions/xxxx_create_obiekt_table.py]
- Tables: [e.g. users, obiekty, rooms]

#### Tests:
- Backend: `pytest` (X passed, 0 failed)
- Frontend: `vitest` (X passed, 0 failed)

#### Verification:
- Automated test run: PASS
- Typecheck (`tsc`, `mypy`/`ruff`): PASS
- Build (`vite build`): PASS
- Manual verification in browser/Telegram WebApp: PASS

#### Deferred:
- ...
```
