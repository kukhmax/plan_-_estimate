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
| **Stage 1** | **Project Scaffolding & CI Foundation** | **Completed** | Minimal working monorepo skeleton (FastAPI, React+Vite, aiogram 3, Docker Compose) |
| **Stage 2** | **Telegram Mini App Authentication** | **Completed** | Cryptographic HMAC-SHA256 initData validation, User model & migration, JWT session, dev mock mode |
| **Stage 3** | **Client Management** | **Completed** | Client CRUD with soft archive, search, owner isolation, i18n (PL/RU) |
| **Stage 3B** | **Client Module Verification** | **Completed** | Expanded search, archive-filter, and owner-isolation regression coverage |
| **Stage 3C** | **Claude Code Instructions & Roadmap Consistency** | **Completed** | Claude Code guidance, stage skills, dependency-safe roadmap |
| Stage 4 | Project / Room / Surface Foundation | In Progress | Stages 4A-4B Project backend and Client association completed; rooms, surfaces, and downstream `project_id` anchoring pending |
| Stage 5 | Telegram Mini App Shell & Auth | Pending | Telegram WebApp SDK, initData HMAC-SHA256 validation, theme adaptation |
| Stage 6 | Room Measurements & Surface Manager UI | Pending | Interactive room dimension inputs, openings subtraction, surface totals |
| Stage 7 | Substrate Inspection & Risk Engine | Pending | Project/surface-anchored diagnostics, deterministic risks, and technical warnings |
| Stage 8 | Estimates & Quotation UI | Pending | Estimate generator, PDF export preparation, client approval flow |
| Stage 9 | Technical Protocols & Handover | Pending | Acceptance protocols (stan zero, roboty zanikające, protokół końcowy) |
| Stage 10 | Contracts & Legal Knowledge Modules | Pending | Contract generator, standard clauses, client communication phrases |
| Stage 11 | Offline Drafts & S3 Photo Storage | Pending | IndexedDB offline drafts sync, S3 photo attachments |

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

### Stage 1: Bootstrap Application Infrastructure
- **Status**: Completed
- **Date**: 2026-09-08
- **Commit**: `feat(stage-1): bootstrap application infrastructure`

#### Added:
- Backend:
  - `backend/app/main.py` FastAPI entrypoint with CORS and `/api/health` router.
  - `backend/app/api/v1/endpoints/health.py` returning `{"status": "ok"}`.
  - `backend/app/core/config.py` with Pydantic v2 `BaseSettings`.
  - `backend/app/core/database.py` with SQLAlchemy 2.x async engine and DeclarativeBase.
  - `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako` for async migrations.
  - `backend/Dockerfile` and `backend/.dockerignore` for containerized backend execution.
  - `backend/tests/conftest.py` and `backend/tests/test_health.py` testing GET `/api/health`.
  - `backend/pyproject.toml` and `backend/requirements.txt`.
- Frontend:
  - `frontend/src/App.tsx` displaying "Renovation App" / "Frontend is running".
  - `frontend/src/App.test.tsx` Vitest testing DOM rendering.
  - `frontend/src/main.tsx`, `frontend/src/index.css` with Tailwind CSS directives.
  - `frontend/vite.config.ts`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/tsconfig.json`.
  - `frontend/package.json`.
- Bot:
  - `bot/main.py` aiogram 3.x async polling bootstrap (no business logic).
  - `bot/bot/config.py` reading bot token from environment.
  - `bot/bot/handlers.py` with minimal `/start` command router.
  - `bot/pyproject.toml` and `bot/requirements.txt`.
- Infrastructure & Docker:
  - `docker-compose.yml` defining PostgreSQL 16 Alpine container with healthcheck and backend container (no Redis).
  - `.env.example` defining database, bot, and app variables.

#### Changed:
- `README.md` updated with exact commands for DB startup, backend startup, backend tests, frontend startup, frontend tests, and production build.

#### Database:
- PostgreSQL 16 container definition in `docker-compose.yml`.

#### Tests:
- Backend: `pytest` passed (1 passed in 0.03s).
- Frontend: `vitest --run` passed (1 passed in 3.33s).
- Frontend Typecheck: `tsc -p frontend/tsconfig.json --noEmit` passed (0 errors).
- Frontend Build: `tsc && vite build` passed (built in 3.83s).
- Bot: syntax and import check passed.

#### Verification:
1. Backend tests: PASS (1 passed).
2. Frontend tests: PASS (1 passed).
3. Frontend typecheck: PASS (0 errors).
4. Frontend build: PASS (production bundle built).
5. Health endpoint manual check: PASS (`GET /api/health` returns HTTP 200 `{"status": "ok"}`).

#### Deferred:
- Domain entities (Clients, Projects, Obiekty, Rooms), Telegram authentication, estimate calculation, and PDF/storage deferred to subsequent stages.

---

### Stage 2: Telegram Mini App Authentication
- **Status**: Completed
- **Date**: 2026-09-08
- **Commit**: `feat(stage-2): implement Telegram Mini App authentication`

#### Added:
- Backend:
  - `backend/app/domain/services/auth_service.py`: `TelegramAuthService` domain service implementing initData validation, user provisioning, re-login user reuse, and JWT token issuance.
  - `backend/app/models/user.py`: `User` model with UUIDv4 primary key, unique BigInteger `telegram_user_id`, username, first/last names, language_code, UTC timestamps.
  - `backend/alembic/versions/0001_create_users_table.py`: Database migration for `users` table and indexes.
  - `backend/app/core/security.py`: HMAC-SHA256 signature verification of raw `initData`, `auth_date` freshness check, constant-time compare, and JWT session generation/decoding (`pyjwt`).
  - `backend/app/schemas/auth.py`: Pydantic v2 schemas (`TelegramAuthRequest`, `TelegramAuthResponse`, `UserRead`).
  - `backend/app/api/deps.py`: `get_current_user` and `get_auth_service` dependencies.
  - `backend/app/api/v1/endpoints/auth.py`: Ultra-thin endpoints `POST /api/auth/telegram` and `GET /api/me`.
  - `backend/tests/test_auth.py`: 8 automated tests covering valid signature, invalid signature, expired data, missing data, dev mock login, reload user reuse, production mock rejection, and protected `GET /api/me`.
- Frontend:
  - `frontend/src/types/telegram.ts` & `frontend/src/types/auth.ts`: Strict TypeScript definitions for Telegram WebApp and authentication models.
  - `frontend/src/api/auth.ts`: Typed API client for `POST /api/auth/telegram` and `GET /api/me`.
  - `frontend/src/hooks/useAuth.ts`: Custom hook extracting `window.Telegram.WebApp.initData`, providing dev mock fallback outside Telegram, managing authentication state.
  - `frontend/src/App.tsx`: Displays verified user card with name, Telegram ID, username, language, and system UUID. In mock mode, displays prominent amber `DEV AUTH BANNER`.
  - `frontend/src/App.test.tsx`: Vitest tests for dev mock mode banner, verified Telegram user display, and error handling.
- Configuration:
  - `.env.example`: added `MOCK_TELEGRAM_AUTH`, `TELEGRAM_AUTH_MAX_AGE_SECONDS`, `JWT_SECRET_KEY`, `VITE_DEV_MOCK_AUTH`.

#### Changed:
- `backend/app/main.py`: mounted auth router under `/api`.
- `backend/alembic/env.py`: imported `app.models` to ensure schema reflection.
- `backend/pyproject.toml` & `backend/requirements.txt`: added `pyjwt` and `aiosqlite`.

#### Database:
- Migrations: `backend/alembic/versions/0001_create_users_table.py` applied to PostgreSQL.
- Tables: `users` (id UUID PK, telegram_user_id BIGINT UNIQUE, username, first_name, last_name, language_code, created_at, updated_at).

#### Tests:
- Backend: `pytest` passed (9 passed in 0.31s).
- Frontend: `vitest --run` passed (3 passed in 2.88s).
- Frontend Typecheck: `tsc -p frontend/tsconfig.json --noEmit` passed (0 errors).
- Frontend Build: `tsc && vite build` passed (built in 3.48s).

#### Verification:
1. Valid Telegram signature creates/retrieves user and returns JWT: PASS.
2. Tampered signature rejected with 401 `INVALID_TELEGRAM_SIGNATURE`: PASS.
3. Expired initData rejected with 401 `TELEGRAM_AUTH_EXPIRED`: PASS.
4. Missing initData/hash rejected with 400 `MISSING_TELEGRAM_DATA`: PASS.
5. Dev mock mode functions when `APP_ENV=development` and `MOCK_TELEGRAM_AUTH=true`: PASS.
6. Dev mock mode strictly rejected with 403 `MOCK_AUTH_DISALLOWED_IN_PRODUCTION` when `APP_ENV=production`: PASS.
7. Reloading / re-authenticating reuses the same user record: PASS.
8. `GET /api/me` returns authenticated user profile with Bearer token: PASS.
9. Frontend renders prominent amber `DEV AUTH BANNER` in mock mode: PASS.
10. Alembic migration applied to PostgreSQL database: PASS.

#### Deferred:
- Clients, Projects, Obiekty, Rooms, Estimates, Protocols deferred to subsequent stages.

---

---

### Stage 3: Client Management
- **Status**: Completed
- **Date**: 2026-09-09
- **Commit**: `feat(stage-3): implement client management with owner isolation and search`

#### Added:
- Backend:
  - `backend/app/models/client.py`: `Client` model with `ClientType` enum (`PRIVATE_PERSON`, `COMPANY`), soft archive (`is_archived`), `owner_user_id` FK → `users.id`, search-optimized indexes.
  - `backend/app/domain/exceptions.py`: `ClientNotFoundError` for strict 404 tenant isolation.
  - `backend/app/domain/services/client_service.py`: `ClientService` with `list_clients` (search + archive filter), `get_client`, `create_client`, `update_client`, `archive_client`, `restore_client`. Owner isolation enforced on every query.
  - `backend/app/schemas/client.py`: Pydantic v2 `ClientCreate`, `ClientUpdate`, `ClientRead`, `ClientListResponse` with `@model_validator` enforcing business rules (`PRIVATE_PERSON` needs name, `COMPANY` needs `company_name`).
  - `backend/app/api/v1/endpoints/clients.py`: Thin routes for `GET /api/clients`, `POST /api/clients`, `GET /api/clients/{id}`, `PATCH /api/clients/{id}`, `POST /api/clients/{id}/archive`, `POST /api/clients/{id}/restore`.
  - `backend/alembic/versions/0002_create_clients_table.py`: Migration for `clients` table with `clienttype` enum, indexes, and FK.
  - `backend/tests/test_clients.py`: 10 tests — create private person, create company, company validation, private person validation, edit, archive, restore, search, owner isolation, unauthenticated access.
- Frontend:
  - `frontend/src/types/client.ts`: TypeScript interfaces for `ClientType`, `ClientListResponse`, `ClientCreatePayload`, `ClientUpdatePayload`.
  - `frontend/src/api/clients.ts`: API module (`fetchClients`, `fetchClient`, `createClient`, `updateClient`, `archiveClient`, `restoreClient`).
  - `frontend/src/locales/pl.json` & `frontend/src/locales/ru.json`: Full locale dictionaries for app, auth, and clients sections.
  - `frontend/src/hooks/useI18n.tsx`: `I18nProvider` context + `useI18n` hook with `localStorage` locale persistence.
  - `frontend/src/components/ClientList.tsx`: Mobile-first component with search input, archived filter toggle, add client form (with client-side validation), archive/restore actions per client.
  - `frontend/src/ClientList.test.tsx`: 5 Vitest tests for empty state, list render, archived badge, form toggle, and validation.

#### Changed:
- `backend/app/models/__init__.py`: added `Client` export.
- `backend/app/api/deps.py`: added `get_client_service` dependency factory.
- `backend/app/main.py`: mounted clients router under `/api`.
- `frontend/src/App.tsx`: wrapped in `I18nProvider`, uses `t.*` for all strings, exposes PL/RU language switcher, renders `ClientList` when authenticated, persists JWT to `localStorage`.
- `frontend/src/App.test.tsx`: added clients API mock.

#### Database:
- Migration `0002_create_clients_table.py` applied to PostgreSQL.
- Tables: `clients` (id UUID PK, owner_user_id FK, client_type enum, optional name/contact fields, is_archived, timestamps).
- Enum: `clienttype` (PRIVATE_PERSON, COMPANY).

#### Tests:
- Backend: `pytest` passed (19 passed in 1.23s).
- Frontend: `vitest --run` passed (8 passed).
- Frontend Typecheck: `tsc --noEmit` passed (0 errors).
- Frontend Build: `vite build` passed (built in 4.26s).

#### Verification:
1. Create PRIVATE_PERSON client: PASS.
2. Create COMPANY client: PASS.
3. COMPANY without company_name rejected (422): PASS.
4. PRIVATE_PERSON without any name rejected (422): PASS.
5. Edit client with PATCH: PASS.
6. Archive client hidden from default list, visible with include_archived=true: PASS.
7. Restore archived client returns to active list: PASS.
8. Search by first name and company name: PASS.
9. Cross-owner access returns 404 (not 403): PASS.
10. Unauthenticated access returns 401: PASS.
11. Alembic migration applied to PostgreSQL: PASS.

#### Deferred:
- Projects (Obiekty), Rooms, Surfaces, Measurements, Estimates, Protocols, Photos deferred to subsequent stages.

---

### Stage 3B: Client Module Verification
- **Status**: Completed
- **Date**: 2026-09-09
- **Commit**: `22df7fe` — `test(stage-3b): complete client module verification`

#### Changed:
- `backend/tests/test_clients.py`: expanded client API coverage from 10 to 18 tests.
- Split search verification across first name, last name, company name, and phone.
- Added explicit active/archive filtering and strict 404 owner-isolation checks for GET, PATCH, archive, and restore operations.

#### Database:
- None.

#### Tests:
- Backend client tests: 18 passed.
- Full backend suite: 27 passed.
- Frontend tests: 8 passed.
- TypeScript typecheck: PASS.
- Frontend production build: PASS.

#### Verification:
- `git diff --check`: PASS.
- Commit `22df7fe` pushed to `origin/main`.

#### Deferred:
- No new application functionality was introduced; subsequent domain modules remain deferred.

---

### Stage 3C: Claude Code Instructions and Roadmap Consistency
- **Status**: Completed
- **Date**: 2026-09-09
- **Commit**: `docs(stage-3c): add Claude Code workflow guidance`

#### Added:
- Root `CLAUDE.md` importing the existing Gemini and Antigravity rules while defining Claude Code commands and stage safeguards.
- Project-local `/stage-implementation` and `/stage-verification` workflow skills.

#### Changed:
- Recorded the completed Stage 3B verification results and commit.
- Reordered future roadmap dependencies so Project / Obiekt, Room, and Surface foundations exist before Substrate Inspection and its risk engine.

#### Database:
- None.

#### Tests:
- No application tests required; Stage 3C changes only documentation and Claude Code configuration.

#### Verification:
- Imported instruction paths exist: PASS.
- Skill frontmatter validation: PASS.
- Application source unchanged: PASS.
- `git diff --check`: PASS.

#### Deferred:
- Stage 4 Project / Room / Surface Foundation requires explicit user approval and was not started.

---

### Stage 4A: Project / Obiekt Backend Domain
- **Status**: Completed
- **Date**: 2026-09-09
- **Commit**: `feat(stage-4a): implement Project backend domain`

#### Added:
- `backend/app/models/project.py`: owner-scoped `Project` aggregate root with UUID identity, UTC timestamps, practical address fields, description, lifecycle status, and independent archive state.
- `backend/app/schemas/project.py`: typed create, update, read, and list contracts with minimal field validation.
- `backend/app/domain/services/project_service.py`: owner-isolated create, list, read, update, archive, and restore operations.
- `backend/app/api/v1/endpoints/projects.py`: thin authenticated Project CRUD routes with strict 404 tenant isolation.
- `backend/alembic/versions/0003_create_projects_table.py`: reversible Project table and `projectstatus` enum migration.
- `backend/tests/test_projects.py`: 12 focused API and persistence tests.

#### Changed:
- Registered the Project model for SQLAlchemy metadata and Alembic discovery.
- Added the Project service dependency and mounted Project routes at `/api/projects`.
- Added `ProjectNotFoundError` for owner-isolated missing-resource handling.

#### Database:
- Migration `0003_create_projects_table.py` applied to PostgreSQL.
- Table: `projects` with owner FK, project details, `PLANNING` / `IN_PROGRESS` / `COMPLETED` lifecycle status, archive state, and timestamps.
- Alembic revision chain has one head: `0003_create_projects`; metadata drift check reports no pending operations.

#### Tests:
- Focused Project tests: 12 passed, 0 failed.
- Full backend regression suite: 39 passed, 0 failed.

#### Verification:
- Project create, list, read, update, archive, restore, active/archive filtering, and field persistence: PASS.
- Owner list isolation and foreign-owner GET, PATCH, archive, and restore returning 404: PASS.
- Missing UUID returns 404; malformed UUID and invalid lifecycle status return 422: PASS.
- Alembic upgrade from `0002_create_clients` to `0003_create_projects`: PASS.
- Alembic applied-head and metadata consistency checks: PASS.
- `git diff --check`: PASS.
- Scope review found no Client relationship, Room, Surface, frontend, Telegram UI, or future-stage implementation: PASS.
- Manual UI verification: not applicable to this backend-only stage; API behavior is covered by end-to-end ASGI tests.

#### Deferred:
- Project-to-Client relationships, Rooms, Surfaces, Measurements, Inspections, Estimates, frontend Project UI, Telegram UI, and all Stage 4B functionality.

---

### Stage 4B: Project ↔ Client Relationship
- **Status**: Completed
- **Date**: 2026-09-09
- **Commit**: `feat(stage-4b): link projects to clients`

#### Added:
- `backend/alembic/versions/0004_add_project_client_id.py`: nullable, indexed `projects.client_id` foreign key with `ON DELETE SET NULL`.
- Optional `client_id` support in Project create, update, read, and list contracts without duplicating Client data.
- Owner-scoped Client validation in `ProjectService` without a circular service dependency.
- Focused coverage for unassigned Projects, create/assign/change/remove operations, persistence, archived Clients, and tenant non-disclosure.

#### Changed:
- Project creation and update validate that an assigned Client belongs to the authenticated Project owner.
- Project API maps both missing and foreign Client references to the same 404 response.
- Project test coverage expanded from 12 to 20 tests.

#### Database:
- Migration `0004_add_project_client_id.py` applied to PostgreSQL.
- Alembic revision chain has one head: `0004_add_project_client`; metadata drift check reports no pending operations.

#### Tests:
- Focused Project ↔ Client relationship suite: 9 passed, 0 failed.
- Existing Client suite: 18 passed, 0 failed.
- Complete Project suite: 20 passed, 0 failed.
- Full backend regression suite: 47 passed, 0 failed.

#### Verification:
- Project without Client and Project created with Client: PASS.
- Assign, change, remove, and persisted Client association: PASS.
- Missing and foreign Clients return indistinguishable 404 responses on relationship operations: PASS.
- Foreign and missing Projects return indistinguishable 404 responses before Client validation: PASS.
- Archived Clients remain assignable and existing associations persist, matching current soft-archive conventions: PASS.
- Alembic upgrade from `0003_create_projects` to `0004_add_project_client`: PASS.
- Alembic applied-head and metadata consistency checks: PASS.
- `git diff --check`: PASS.
- Scope review found no Rooms, Surfaces, frontend, Client redesign, or future-stage implementation: PASS.
- Manual UI verification: not applicable to this backend-only stage; API behavior is covered by end-to-end ASGI tests.

#### Deferred:
- Rooms, Surfaces, Measurements, Inspections, Estimates, Project frontend, Telegram UI, and all Stage 4C functionality.

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
