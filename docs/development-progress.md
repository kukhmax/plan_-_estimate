# Development Progress & Stage Roadmap

**Project**: Telegram Mini App for managing interior finishing and renovation work in Poland.  
**Repository**: `git@github.com:kukhmax/plan_-_estimate.git`  
**Central Entity**: OBIEKT (Project / Site)  
**Stack**: React + TypeScript + Vite + Tailwind CSS | Python + FastAPI + SQLAlchemy 2.x + Alembic + Pydantic v2 + PostgreSQL | aiogram 3.x

---

## Roadmap Overview

| Stage | Title | Status | Primary Focus |
| :--- | :--- | :--- | :--- |
| **Stage 0** | **Engineering/project rules** | **Completed** | Master rules (`GEMINI.md`, `.agents/rules/`), `.gitignore`, development progress tracker |
| **Stage 1** | **Project skeleton/infrastructure** | **Completed** | Monorepo skeleton (FastAPI, React+Vite, aiogram 3, Docker Compose, PostgreSQL 16) |
| **Stage 2** | **Telegram Mini App authentication/integration** | **Completed** | HMAC-SHA256 `initData` validation, User model, JWT sessions, mock gating, runtime shell, theme adaptation, viewport stability, and BackButton |
| **Stage 3** | **Clients** | **Completed** | Client CRUD with soft archive, search, owner isolation, i18n (PL/RU), verification coverage |
| **Stage 4** | **Projects / Obiekty** | **Completed** | Central aggregate root: Project model, address fields, status lifecycle, optional Client link, owner isolation |
| **Stage 5** | **Rooms, surfaces and measurements** | **Completed** | Room and Surface hierarchy, room measurements, openings subtraction, net area totals, practical mobile measurement workflow, composite floor/ceiling geometry, and owner-accepted final manual acceptance |
| **Stage 6** | **Inspection Checklist Engine** | **Completed** | Substrate diagnostics, checklist questions, versioned templates, typed answers, factual findings, WALL/FLOOR/CEILING/room-level targets, quality-scale validation, and owner-accepted final manual acceptance |
| Stage 7 | Risk Rules Engine | In Progress | Deterministic risk evaluation, warnings, mitigation requirements, warranty exclusions |
| Stage 8 | "Co powiedzieć klientowi" | Pending | Ready-to-use professional explanations and client communication scripts (PL/RU) |
| Stage 9 | Editable Price Book | Pending | Contractor base price catalog, labor rates, materials, equipment, difficulty surcharges |
| Stage 10 | Estimate / Kosztorys | Pending | Line-item calculation by surface, substrate, and quality tier (S1–S4, Q1–Q4) |
| Stage 11 | Inspection → recommended work → add to estimate | Pending | Automatic mapping from inspection findings to scope of work and estimate line items |
| Stage 12 | Price coefficients | Pending | Multipliers for difficulty, height, surface condition, urgency, and logistics |
| Stage 13 | Technological workflows | Pending | Work sequencing, technological breaks, drying times, stage tracking |
| Stage 14 | Photo Fixation & Defect Annotations | Pending | Photo attachments (Project/Room, WALL/FLOOR/CEILING, camera/gallery, multiple per target, notes, thumbnails, S3 abstraction, metadata separate from binaries) and tap-to-annotate defects (normalized x/y, category, comment, severity, status) — see "Roadmap Detail — Stage 14" |
| Stage 15 | Documents / PDF | Pending | Printable estimate, contract, and technical protocol generation (Jinja2 + WeasyPrint) |
| Stage 16 | Contracts and protective protocols | Pending | Binding contract generator, site handover protocol, concealed works, final acceptance |
| Stage 17 | Legal knowledge base + situation search | Pending | Polish Building Law, ITB conditions, PN-EN norms, legal situation lookup |
| Stage 18 | Calendar and Telegram reminders | Pending | Schedule management, milestone reminders, technological break notifications |
| Stage 19 | Offline drafts | Pending | IndexedDB offline draft storage for basements/no-signal areas, sync engine |
| Stage 20 | Full MVP audit and end-to-end object scenario | Pending | End-to-end walkthrough: client → project → inspection → estimate → contract → handover |

---

## Roadmap Detail — Stage 14: Photo Fixation & Defect Annotations (Planned Scope)

> Planned scope for the existing canonical **Stage 14**. No new canonical stage number is created and the canonical Stage 0–20 order is unchanged. This is future roadmap intent, **not** functionality implemented during Stage 5.

### Photo attachments
- Attachment context: Project / Room, `WALL` surface, `FLOOR`, `CEILING`.
- Capture methods: camera capture and gallery/file upload.
- Multiple photos per target.
- Description / notes and timestamps.
- Thumbnails.
- S3-compatible object-storage abstraction.
- Metadata stored separately from binary image data.

### Defect annotations
- User taps a point on the photo to place an annotation.
- Normalized `x` / `y` coordinates (resolution-independent).
- Multiple annotations per photo.
- Defect category, comment, severity, status.

Candidate defect categories may later include: crack, detachment, moisture, unevenness, mechanical damage, other. This candidate enum must **not** be frozen prematurely in implementation documentation.

### Future integration chain (documented intent, not implemented in Stage 5)

```
Photo / PhotoAnnotation
→ Inspection Checklist Finding
→ Risk Rules Engine
→ Recommended Work
→ Estimate
→ PDF / protective protocol
```

Clarifications:
- This dependency chain is forward integration intent recorded at Stage 5 closure. No element of it is implemented today.
- **Stage 6** (Inspection Checklist Engine) should design inspection findings so they can later reference photos/annotations, but Stage 6 must **not** implement photo storage.
- **Stage 7** (Risk Rules Engine) may later consume annotated defects as risk inputs.
- **Stage 11** (Inspection → recommended work → estimate) may later convert annotated/checklist findings into recommended work.
- **Stage 15** (Documents / PDF) may later embed selected photos/annotations into generated documents.
- **Stage 20** (Full MVP audit) should include the photo/defect workflow in its end-to-end audit scenario.

---

## Historical Commit & Stage Identifier Mapping

> **Important Historical Note**: During earlier development and iterative stage reconciliation, some completed Git commits and prompts used temporary execution sub-stage labels (such as Stage 3B, 3C, 4A–4F, 5A–5C). In accordance with the immutable repository governance rules, git history is never rewritten. The table below documents the authoritative mapping from historical Git commits to the canonical 21-stage product roadmap (Stages 0–20):

| Historical Git Commits / Sub-Stages | Canonical Product Stage | Mapping Description |
| :--- | :--- | :--- |
| `6c05c99` (`chore(stage-0)`) | **Stage 0** — Engineering/project rules | Foundation workflow rules, architecture standards, directory layout |
| `3165661` (`feat(stage-1)`) | **Stage 1** — Project skeleton/infrastructure | Backend, frontend, bot scaffolding, Docker Compose, PostgreSQL |
| `d8127ce` (`feat(stage-2)`), `a2787fa` (`feat(stage-5a)`), `df91132` (`feat(stage-5b)`), `0208572` (`fix(dev)`), `4ff8e1b` (`feat(stage-5c)`) | **Stage 2** — Telegram Mini App authentication/integration | Core Telegram `initData` HMAC-SHA256 validation, User model, JWT auth, and subsequent Telegram WebApp runtime shell, theme adaptation, viewport stability, and BackButton integration hardening |
| `45e4b99` (`feat(stage-3)`), `22df7fe` (`test(stage-3b)`), `07f4f1b` (`docs(stage-3c)`) | **Stage 3** — Clients | Client CRUD, soft archive, search, owner isolation, i18n PL/RU, verification coverage, Claude guidance |
| `12fcdd0` (`feat(stage-4a)`), `39f389a` (`feat(stage-4b)`) | **Stage 4** — Projects / Obiekty | Project / Obiekt aggregate root domain model, status lifecycle, optional Client association, owner isolation |
| `baa95e7` (`feat(stage-4c)`), `c56c767` (`feat(stage-4d)`), `542ed15` (`feat(stage-4e)`), `cfcbbcc` (`docs(stage-4f)`) | **Stage 5** — Rooms, surfaces and measurements (Partial) | Room and Surface domain models, semantic surface types (`WALL`, `CEILING`, `FLOOR`, `OTHER`), hierarchy navigation UI (`Project → Room → Surface`), metric room/surface measurements, openings subtraction, and net area totals (execution sub-stages 5A–5D). |

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

### Stage 4C: Room Backend Domain
- **Status**: Completed
- **Date**: 2026-09-09
- **Commit**: `feat(stage-4c): implement Room backend domain`

#### Added:
- `backend/app/models/room.py`: minimal Room entity with UUID identity, required Project foreign key, name, optional description, archive state, and UTC timestamps.
- `backend/app/schemas/room.py`: typed create, update, read, and list contracts without measurement or Surface fields.
- `backend/app/domain/services/room_service.py`: Project-owned Room create, list, read, update, archive, and restore operations.
- `backend/app/api/v1/endpoints/rooms.py`: authenticated Project-nested Room routes with strict 404 tenant isolation.
- `backend/alembic/versions/0005_create_rooms_table.py`: reversible Room table migration with Project cascade deletion and Project/archive indexes.
- `backend/tests/test_rooms.py`: 12 focused API, persistence, filtering, membership, validation, and owner-isolation tests.

#### Changed:
- Registered the Room model for SQLAlchemy metadata and Alembic discovery.
- Added the Room service dependency and mounted Room routes under `/api/projects/{project_id}/rooms`.
- Added `RoomNotFoundError` for Project-scoped missing-resource handling.

#### Database:
- Migration `0005_create_rooms_table.py` applied to PostgreSQL from `0004_add_project_client`.
- Alembic revision chain has one head: `0005_create_rooms`; metadata drift check reports no pending operations.

#### Tests:
- Focused Room suite: 12 passed, 0 failed.
- Complete Project suite: 20 passed, 0 failed.
- Existing Client suite: 18 passed, 0 failed.
- Full backend regression suite: 59 passed, 0 failed.

#### Verification:
- Room create, list, read, update, archive, restore, multiple-Room handling, Project membership, and active/archive filtering: PASS.
- Parent Project ownership is validated before every Room operation: PASS.
- Foreign and missing Projects return indistinguishable Project 404 responses: PASS.
- Foreign, wrong-Project, and missing Rooms return indistinguishable Room 404 responses inside an owned Project: PASS.
- Missing UUIDs return 404; malformed Project and Room UUIDs return 422: PASS.
- Alembic upgrade from `0004_add_project_client` to `0005_create_rooms`: PASS.
- Alembic applied-head and metadata consistency checks: PASS.
- `git diff --check`: PASS.
- Scope review found no Surfaces, measurements, Room frontend, inspections, estimates, or Stage 4D implementation: PASS.
- Manual UI verification: not applicable to this backend-only stage; API behavior is covered by end-to-end ASGI tests.

#### Deferred:
- Surfaces, measurements and calculations, Room frontend, inspections, estimates, and all Stage 4D functionality.

---

### Stage 4D: Surface Backend Domain
- **Status**: Completed
- **Date**: 2026-09-09
- **Commit**: `feat(stage-4d): implement Surface backend domain`

#### Added:
- `backend/app/models/surface.py`: Room-owned Surface entity with UUID identity, semantic `WALL` / `CEILING` / `FLOOR` / `OTHER` type, optional description, archive state, and UTC timestamps.
- `backend/app/schemas/surface.py`: typed create, update, read, and list contracts with constrained Surface type validation.
- `backend/app/domain/services/surface_service.py`: transitive owner-scoped create, list, read, update, archive, and restore operations.
- `backend/app/api/v1/endpoints/surfaces.py`: authenticated Project/Room-nested Surface routes with hierarchical 404 isolation.
- `backend/alembic/versions/0006_create_surfaces_table.py`: reversible Surface table and enum migration with Room cascade deletion and Room/archive indexes.
- `backend/tests/test_surfaces.py`: 15 focused API, persistence, filtering, enum, membership, and transitive owner-isolation tests.

#### Changed:
- Registered the Surface model for SQLAlchemy metadata and Alembic discovery.
- Added the Surface service dependency and mounted Surface routes under `/api/projects/{project_id}/rooms/{room_id}/surfaces`.
- Added `SurfaceNotFoundError` for Room-scoped missing-resource handling.

#### Database:
- Migration `0006_create_surfaces_table.py` applied to PostgreSQL from `0005_create_rooms`.
- Alembic revision chain has one head: `0006_create_surfaces`; metadata drift check reports no pending operations.

#### Tests:
- Focused Surface suite: 15 passed, 0 failed.
- Complete Room suite: 12 passed, 0 failed.
- Complete Project suite: 20 passed, 0 failed.
- Existing Client relationship suite: 18 passed, 0 failed.
- Full backend regression suite: 74 passed, 0 failed.

#### Verification:
- Surface create for all four supported types, list, read, update, archive, restore, multiple-Surface handling, Room membership, relationship persistence, and active/archive filtering: PASS.
- Access resolves in order through authenticated owner, Project, Room, and Surface membership: PASS.
- Foreign and missing Projects return indistinguishable Project 404 responses: PASS.
- Foreign and missing Rooms return indistinguishable Room 404 responses inside an owned Project: PASS.
- Foreign, wrong-Room, and missing Surfaces return indistinguishable Surface 404 responses inside an owned Room: PASS.
- Unsupported Surface types are rejected on create and update with 422: PASS.
- Alembic upgrade from `0005_create_rooms` to `0006_create_surfaces`: PASS.
- Alembic applied-head and metadata consistency checks: PASS.
- `git diff --check`: PASS.
- Scope review found no substrate/material state, measurements, areas, openings, deductions, frontend, or Stage 4E implementation: PASS.
- Manual UI verification: not applicable to this backend-only stage; API behavior is covered by end-to-end ASGI tests.

#### Deferred:
- Substrate inspections and risks, measurements and calculations, Surface frontend, and all Stage 4E functionality.

---

### Stage 4E: Project / Room / Surface Frontend Foundation
- **Status**: Completed
- **Date**: 2026-09-09
- **Commit**: `feat(stage-4e): add Project hierarchy frontend`

#### Added:
- Typed frontend contracts and API modules for Project, Room, and Surface list, read, create, update, archive, and restore operations.
- `ProjectWorkspace`, `RoomList`, and `SurfaceList` components implementing the mobile-first `Client → Project → Room → Surface` workflow.
- Project assignment display for existing Clients, explicit Project lifecycle selection, and semantic `WALL` / `CEILING` / `FLOOR` / `OTHER` Surface type selection.
- Focused React tests covering Project/Client display, create and hierarchy navigation, Room create/open/archive, Surface create/type/archive/restore, and archived filters.
- Matching Polish and Russian locale entries for navigation, forms, hierarchy states, actions, validation, and feedback.

#### Changed:
- Added Clients/Projects navigation to the authenticated application shell while preserving the existing Client workflow.
- Persisted the authentication token before rendering authenticated hierarchy components, preventing initial API requests from racing token storage.
- Added regression coverage confirming successful authentication stores the access token.

#### Database:
- None; Stage 4E uses the existing Project, Room, Surface, and Client APIs without schema or migration changes.

#### Tests:
- Focused Stage 4E frontend suite: 10 passed, 0 failed.
- Full frontend suite: 18 passed, 0 failed.
- Relevant backend Client/Project/Room/Surface regression suite: 65 passed, 0 failed.
- TypeScript strict typecheck: PASS (0 errors).
- Frontend production build: PASS (46 modules transformed).

#### Verification:
- Project list/create/open/edit/archive/restore and assigned-Client display: PASS.
- Nested Room list/create/open/edit/archive/restore and active/archive filtering: PASS.
- Nested Surface list/create/edit/archive/restore, semantic type selection, and active/archive filtering: PASS.
- `Projects → Project → Rooms → Room → Surfaces` hierarchy navigation and breadcrumbs: PASS.
- Loading, empty, API error, create/update success, and archived states: PASS.
- Mobile Chromium walkthrough at 390×844, including real frontend/backend requests and zero console errors: PASS.
- `git diff --check`: PASS.
- Scope review found no measurement, inspection, substrate, pricing, legal, estimate, or Stage 4F functionality: PASS.

#### Deferred:
- Measurements, substrate inspections, estimates, and all Stage 4F functionality remain deferred pending explicit approval.

---

### Stage 4F: Project / Room / Surface Foundation Final Integration
- **Status**: Completed
- **Date**: 2026-09-09
- **Commit**: `docs(stage-4f): complete Stage 4 integration verification`

#### Added:
- Final Stage 4 integration record covering the complete owner-scoped Project, optional Client association, Room, Surface, and frontend hierarchy.
- Consolidated Stage 4A–4F commit ledger and final automated/manual verification totals.

#### Changed:
- Marked the Stage 4 roadmap entry completed after the full hierarchy passed integration, migration, architecture, regression, and browser verification.
- No product source, tests, dependencies, schemas, or migrations changed during Stage 4F.

#### Database:
- Alembic revisions form one linear chain from `0003_create_projects` through `0006_create_surfaces`, with `0006_create_surfaces` as the sole applied head.
- Git history confirms each Stage 4 migration was added once in its owning stage and no previous migration was rewritten.
- `alembic check` reports no model/schema drift or pending upgrade operations.

#### Tests:
- Focused Stage 4 Project/Room/Surface backend suite: 47 passed, 0 failed.
- Focused Stage 4 hierarchy frontend suite: 10 passed, 0 failed.
- Complete backend suite: 74 passed, 0 failed.
- Complete frontend suite: 18 passed, 0 failed.
- TypeScript strict typecheck: PASS (0 errors).
- Frontend production build: PASS (46 modules transformed).

#### Verification:
- Project CRUD, lifecycle status, archive/restore, owner isolation, and optional same-owner Client association: PASS.
- Room CRUD, Project relationship, archive/restore, and owner isolation through Project: PASS.
- Surface CRUD, Room relationship, all supported semantic types, archive/restore, and transitive owner isolation: PASS.
- API routes remain thin; persistence, ownership checks, and lifecycle changes remain in domain services: PASS.
- Project, Room, and Surface models use UUID identities and UTC-aware timestamp conventions: PASS.
- Child entities store only direct hierarchy foreign keys; no Client, Project, or Room domain data is duplicated: PASS.
- Mobile Chromium walkthrough of `Projects → Project → Rooms → Room → Surfaces` at 390×844, including Client assignment, edits, filters, archive/restore, and zero console errors: PASS.
- Frontend runtime dependencies are unchanged; `git diff --check` and forbidden-file review: PASS.
- Scope review found no measurement, inspection, substrate, estimate, pricing, legal, Stage 5, or later-stage functionality: PASS.

#### Stage 4 Commits:
- Stage 4A: `12fcdd0` — `feat(stage-4a): implement Project backend domain`.
- Stage 4B: `39f389a` — `feat(stage-4b): link projects to clients`.
- Stage 4C: `baa95e7` — `feat(stage-4c): implement Room backend domain`.
- Stage 4D: `c56c767` — `feat(stage-4d): implement Surface backend domain`.
- Stage 4E: `542ed15` — `feat(stage-4e): add Project hierarchy frontend`.
- Stage 4F: `docs(stage-4f): complete Stage 4 integration verification` (this verification commit).

#### Deferred:
- Stage 5 and all measurement, inspection, risk, estimate, pricing, legal, protocol, storage, and later-stage functionality require separate explicit approval.

---

### Stage 5A: README Refresh & Telegram Mini App Shell Foundation
- **Status**: Completed
- **Date**: 2026-09-09
- **Commit**: `feat(stage-5a): add Telegram Mini App shell`

#### Added:
- Official Telegram WebApp runtime loading in the frontend HTML shell without adding a package dependency.
- Reusable `useTelegramWebApp` hook that safely detects `window.Telegram?.WebApp`, exposes availability and `initData`, and calls `ready()` and `expand()` only when the runtime is available.
- Focused hook coverage for browsers without Telegram and for runtime initialization when Telegram is available.

#### Changed:
- Refreshed `README.md` to describe the implemented application through Stage 4, its owner-scoped hierarchy, repository structure, stage workflow, verification commands, and local browser setup.
- Documented real Telegram development prerequisites, required environment flags, the absence of a defined production topology, and the prohibition on production mock authentication and committed credentials.
- Updated `useAuth` to consume centralized Telegram WebApp access while preserving real `initData`, browser mock authentication, token persistence, PL/RU localization, and the Stage 4 UI.
- Strengthened authentication component tests to assert the browser mock payload and Telegram runtime initialization.

#### Database:
- None; no backend authentication, schema, model, or migration changes were required.

#### Tests:
- Focused Stage 5A frontend suite: 5 passed, 0 failed.
- Backend authentication regression suite: 8 passed, 0 failed.
- Focused Stage 4 hierarchy frontend regression suite: 10 passed, 0 failed.
- Complete frontend suite: 20 passed, 0 failed.
- TypeScript strict typecheck: PASS (0 errors).
- Frontend production build: PASS (46 modules transformed).

#### Verification:
- Browser without the Telegram runtime returns an unavailable shell with empty `initData`: PASS.
- Available Telegram runtime exposes `initData` and receives one `ready()` and one `expand()` call: PASS.
- Existing browser mock authentication still submits `mock`, while Telegram mode submits the runtime `initData`: PASS.
- Mobile Chromium walkthrough at 390×844 completed `Projects → Project → Rooms → Room → Surfaces` with mock authentication and zero console errors: PASS.
- README commands, paths, environment flags, local URLs, and Telegram prerequisites match the repository: PASS.
- README secret review found no real tokens, credentials, private keys, or invented deployment details: PASS.
- Scope review found no backend rewrite, dependency change, Stage 4 UI redesign, BackButton, theme integration, or Stage 5B+ implementation: PASS.
- `git diff --check` and forbidden-file review: PASS.

#### Deferred:
- Stage 5B authentication work, Telegram BackButton and theme integration, speculative WebApp APIs, and production deployment remain deferred pending explicit approval.

---

### Stage 5B: Real Telegram WebApp Authentication Flow
- **Status**: Completed
- **Date**: 2026-09-10
- **Commit**: `feat(stage-5b): connect Telegram WebApp authentication`

#### Added:
- Typed frontend authentication request failures that retain only the backend error code and status needed for safe UI decisions.
- Focused API and component coverage for unchanged raw `initData`, explicit browser mock gating, empty Telegram data, localized failures, JWT persistence, and remount behavior.
- Polish and Russian messages for unavailable Telegram, missing `initData`, invalid signatures, expired data, unavailable backend, and generic request failures.

#### Changed:
- Real Telegram `initData` now flows unchanged from the Stage 5A WebApp hook through the existing Stage 2 authentication endpoint.
- Browser mock authentication now requires both Vite development mode and the explicit `VITE_DEV_MOCK_AUTH=true` flag; production builds cannot initiate the mock path.
- Authentication failures now render stable localized messages instead of backend-provided text, preventing raw Telegram data or backend details from reaching the UI.
- JWT persistence remains before authenticated application state is published, preserving protected-request ordering and the existing remount reauthentication behavior.

#### Database:
- None; Stage 2 backend validation, user provisioning, JWT issuance, models, schemas, and migrations are unchanged.

#### Tests:
- Focused Telegram frontend authentication suite: 14 passed, 0 failed.
- Backend authentication suite: 8 passed, 0 failed.
- Complete backend suite: 74 passed, 0 failed.
- Complete frontend suite: 29 passed, 0 failed.
- TypeScript strict typecheck: PASS (0 errors).
- Frontend production build: PASS (46 modules transformed).

#### Verification:
- Raw `initData` remains unchanged in the frontend request and is parsed, HMAC-SHA256 verified, and freshness-checked only by the backend: PASS.
- `initDataUnsafe` is not used as authentication proof or accessed by production authentication code: PASS.
- Mock auth requires explicit frontend development configuration and remains rejected by the backend outside development: PASS.
- No raw Telegram `initData` logging or user-facing disclosure was found: PASS.
- Complete backend regressions preserve unauthenticated 401 responses and cross-owner 404 isolation for Client, Project, Room, and Surface access: PASS.
- JWT storage occurs before authenticated child components can issue protected requests; `/api/me` succeeds with the issued JWT: PASS.
- Mobile Chromium mock-auth walkthrough completed `Projects → Project → Rooms → Room → Surfaces` at 390×844 with zero console errors: PASS.
- Mobile Chromium with a present Telegram runtime and empty `initData` issued zero auth requests, showed the localized error, and produced zero console errors: PASS.
- `git diff --check`, forbidden-file review, and scope review: PASS.

#### Deferred:
- Telegram theme adaptation, BackButton integration, refresh tokens, speculative WebApp APIs, deployment, and all Stage 5C functionality remain deferred pending explicit approval.

---

### Stage 5C: Telegram Theme, Viewport & BackButton Integration
- **Status**: Completed
- **Date**: 2026-09-10
- **Commit**: `feat(stage-5c): integrate Telegram theme, viewport, and BackButton`

> Note: Historically tracked as Stage 5C execution sub-stage, functionally associated with original product Stage 2 Telegram integration hardening.

#### Added:
- Typed Telegram WebApp interfaces in `frontend/src/types/telegram.ts`: `TelegramThemeParams`, `TelegramBackButton`, and WebApp event handlers (`onEvent`, `offEvent`).
- CSS custom properties in `frontend/src/index.css` and `frontend/src/hooks/useTelegramWebApp.ts` with `--tg-theme-*` and `--tg-viewport-*` variables, with safe light and dark fallbacks for browser development and incomplete test mocks.
- Dynamic `themeChanged` and `viewportChanged` event listeners in `useTelegramWebApp` that update custom properties in real-time without reloading the page, with guaranteed listener cleanup on unmount.
- Reusable `useTelegramBackButton` hook abstraction in `frontend/src/hooks/useTelegramWebApp.ts` ensuring safe browser execution, prevention of duplicate click callbacks across rerenders, and cleanup upon hiding or unmounting.
- Connected native Telegram `BackButton` to `ProjectWorkspace.tsx` navigation hierarchy (hidden at top-level clients and projects, visible on project detail, visible on room detail, navigating back up the aggregate root hierarchy).
- Focused unit and integration tests in `useTelegramWebApp.test.ts`, `ProjectWorkspace.test.tsx`, and `App.test.tsx`.

#### Changed:
- `frontend/src/App.tsx`: applied `--tg-theme-*` and `--tg-viewport-stable-height` styling to the application shell, header, cards, navigation, and language switcher while preserving mobile and desktop responsiveness.
- `frontend/src/hooks/useTelegramWebApp.ts`: exposed `colorScheme`, `themeParams`, `viewportHeight`, `viewportStableHeight`, and `isExpanded` state alongside `isAvailable` and `initData`.
- `frontend/src/components/ProjectWorkspace.tsx`: connected `useTelegramBackButton` hook to `selectedProject` and `selectedRoom` navigation state.

#### Database:
- None; no backend models, schemas, or migrations were required.

#### Tests:
- Focused Telegram theme, viewport, and BackButton suite: 13 passed, 0 failed.
- Backend authentication regression suite: 8 passed, 0 failed.
- Complete frontend suite: 37 passed, 0 failed.
- Complete backend suite: 74 passed, 0 failed.
- TypeScript strict typecheck: PASS (0 errors).
- Frontend production build: PASS (46 modules transformed).

#### Verification:
- Browser fallback verified: default theme custom properties apply without Telegram runtime, BackButton calls do not throw, breadcrumb navigation works: PASS.
- Real `initData` forwarding, backend HMAC validation, and JWT session flow remain intact: PASS.
- Developer mock authentication remains impossible in production builds and requires explicit flags: PASS.
- Native BackButton hierarchy verified: hidden at top level (clients, projects), visible on project detail (returns to projects), visible on room detail (returns to parent project): PASS.
- Lifecycle safety verified: no duplicate event listeners on rerenders, clean deregistration on hide and unmount: PASS.
- Zero console logs, sensitive data leaks, or unhandled exceptions: PASS.
- `git diff --check`: PASS.

#### Deferred:
- Room metric measurements, openings subtraction, and surface area totals in Canonical Stage 5, followed by all subsequent canonical stages (Stages 6–20), remain deferred pending explicit project-owner approval.

---

### Canonical Stage 5: Rooms, Surfaces and Measurements
- **Status**: Completed
- **Scope & Canonical Mapping**:
  - **Implemented (partial)**: Room and Surface backend domain entities, PostgreSQL migrations (`0005_create_rooms_table.py`, `0006_create_surfaces_table.py`), hierarchical API routes, semantic surface types (`WALL`, `CEILING`, `FLOOR`, `OTHER`), owner isolation, active/archive filtering, and mobile-first `Projects → Project → Rooms → Room → Surfaces` frontend workspace (completed under historical commits `baa95e7`, `c56c767`, `542ed15`, `cfcbbcc`).
  - **Execution Sub-Stage 5A (Completed)**: Room physical dimensions (`length`, `width`, `height`), individual `WALL` surface dimensions (`width`, `height`), deterministic rectangular room gross geometry (`floor_area`, `ceiling_area`, `total_wall_area`, `wall_area_length`, `wall_area_width`, `perimeter`), surface gross area calculations, high-precision `sa.Numeric(10, 3)` / `Decimal` arithmetic, forward Alembic migration `0007_add_measurement_dimensions.py`, backward compatibility, and owner isolation.
  - **Execution Sub-Stage 5B (Completed)**: First-class `Opening` entity attached to `WALL` surfaces, opening single/total area calculations, wall deduction and net area, over-deduction protection, aggregate surface totals via zero-N+1 subqueries, and transitive owner isolation.
  - **Execution Sub-Stage 5C (Completed)**: Room measurement, wall/surface measurement, and opening management frontend UI with ephemeral previews, dependent state reconciliation, and dual-language PL/RU localization.
  - **Execution Sub-Stage 5D (Completed)**: Practical mobile measurement workflow — decimal/numeric input modes, direct room dimension entry, prominent `Gross − Deductions = Net` totals hierarchy, streamlined opening entry, and PL/RU localization.
  - **Execution Sub-Stage 5D.1A (Completed)**: Surface positional ordering and wall generation — nullable `surfaces.position` (`ORDER BY position ASC NULLS LAST`), non-destructive `POST .../surfaces/generate` (422 / 409 / idempotent no-op), deterministic wall-derived room totals (`wall_count`, perimeter from wall widths, Σ gross, deductions, net) with zero N+1, rectangle vs custom sequential wall-entry frontend modes (frontend-only, not persisted), direct `+ Drzwi / + Okno / + Inny otwór` quick actions with type pre-selection, and custom/irregular rooms reporting `floor_area = None` / `ceiling_area = None`.
  - **Execution Sub-Stage 5D.1A.1 (Completed)**: Room creation measurement workflow refinement — shape decision (RECTANGLE / CUSTOM) moved to the moment of room creation, immediately after the room name; RECTANGLE keeps `length`/`width`/`height` (Decimal 0.001 behavior preserved); CUSTOM drops fake rectangular dims and stores only the default wall height into `Room.height` (prefilled 2.700 m, per-room override); new custom walls prefill that height and individual walls may still override; opening dimension defaults per type (DOOR / WINDOW) stored as per-project localStorage workflow state (never a DB column, never bulk-updating existing openings, OTHER never inherits); PL/RU parity maintained; composite floor/ceiling geometry still deferred to 5D.1B.
  - **Execution Sub-Stage 5D.1A.2 (Completed)**: Custom-room measurement-entry hotfix — the unmeasured-room CTA now routes by shape: RECTANGLE keeps "Wprowadź wymiary" (existing L/W/H room editor); CUSTOM shows "Rozpocznij pomiar ścian" and enters the sequential custom-wall workflow directly (never the L/W/H editor, first wall length autofocused), using `Room.height` as the default wall height with per-wall override, and keeping `Room.length`/`width` null. Per-room measurement mode is preserved as frontend-only workflow state (new `hooks/roomMeasurementMode.ts`, keyed per roomId in localStorage, written on room create/edit, read on room open, with guarded missing/corrupt-storage fallback to shape inference). No backend schema/domain change; composite floor/ceiling geometry deferred to 5D.1B.
  - **Execution Sub-Stage 5D.1B (Completed)**: Composite floor and ceiling geometry — one reusable `AreaSegment` entity (`areaplane` FLOOR/CEILING, `areaoperation` ADD/SUBTRACT, `Numeric(10,3)` width/height, position, label, archived flag) with per-plane effective `net = base_area + Σ ADD − Σ SUBTRACT` where `base_area = L × W` for a RECTANGLE room (zero for a CUSTOM room), negative rejected 422 on create/update/restore using the same effective total, archived excluded; room totals resolve each plane independently (active segments → base + adjustments, rectangle no-segments → L×W base, custom no-segments → None, segments-only irregular rooms still report planes); visible retroactive `Razem: X.XXX m²` floor/ceiling badges plus `Powierzchnia bazowa` / `Korekty` breakdown driven by backend-authoritative plane totals (no second calculation engine in the frontend); `add-{plane}-rectangle` / `add-{plane}-subtraction` presets, inline edit, archive/restore, and `onMeasurementChanged` room-total refresh without full reload; Alembic migration `0010_create_area_segments_table.py` (parent `0009_add_surface_position`, reversal verified); zero N+1 via a single grouped segment query per project in `list_rooms`; PL/RU parity maintained. **Hotfix 5D.1B.2**: rectangle plane totals now fold the room `L × W` base into the effective area and negative-net guard (a lone `SUBTRACT 0.700 × 0.800` against `3.700 × 3.300` yields `11.650`, never rejected as `0.000 − 0.560`); the area-segments list response exposes per-plane `{base_area, adjustment_area, net_area}` so the frontend displays backend-computed totals.
  - **Execution Sub-Stage 5E.1 (Completed)**: Mobile/navigation cleanup hotfix — removed the redundant rectangle/custom wall-input mode toggle (mode now derived from the room's measured shape), rebuilt the wall surface card as a mobile action grid with 44 px touch targets, larger/wrapped action buttons across segment/opening/room lists, and a top-level **Obiekty** nav reset that always returns to the project list even from deep Room → Surface views (`resetSignal` prop on `ProjectWorkspace`); removed the now-unused `mode_rectangle` / `mode_custom` locale keys (PL/RU parity 198/198); frontend-only, no DB migration.
  - **Execution Sub-Stage 5E (Completed / Owner Acceptance)**: Final manual acceptance of the canonical `5 × 4 × 2.7` m room scenario — room creation (RECTANGLE), wall generation, opening subtraction, net totals, and composite floor/ceiling geometry — accepted by the project owner on 2026-09-11.
- **Gate**: Canonical Stage 5 is **COMPLETED** — real measurements, openings subtraction, surface totals, mobile workflow, and the owner-accepted final manual acceptance are all delivered. No remaining work in Stage 5.

#### Execution Sub-Stage 5A: Room Measurement Domain & Backend Foundation
- **Status**: Completed
- **Date**: 2026-09-10
- **Scope**:
  - Added physical room dimensions: `length`, `width`, `height` in meters using `sa.Numeric(10, 3)` / Python `Decimal` (millimeter precision).
  - Added individual `WALL` surface dimensions: `width`, `height` in meters using `sa.Numeric(10, 3)` / Python `Decimal`.
  - Implemented pure domain calculation rules in `app/domain/rules/room_geometry.py` without database or web dependencies:
    - Floor gross area ($L \times W$) and ceiling gross area ($L \times W$)
    - Total wall gross area ($2 \times (L + W) \times H$)
    - Wall length area ($L \times H$) and wall width area ($W \times H$)
    - Room perimeter ($2 \times (L + W)$)
    - Surface gross area for individual `WALL` surfaces ($\text{width} \times \text{height}$)
    - Mathematical identity verified: 4 individual walls ($5\times 2.7 = 13.5\text{ m}^2$, $4\times 2.7 = 10.8\text{ m}^2$, $5\times 2.7 = 13.5\text{ m}^2$, $4\times 2.7 = 10.8\text{ m}^2$) sum to $48.600\text{ m}^2$, matching calculated room `total_wall_area`.
  - Zero redundant columns persisted; all geometric totals are computed dynamically in Pydantic read schemas.
  - Reversible Alembic migration `0007_add_measurement_dimensions.py` adding nullable dimension columns to `rooms` and `surfaces`.
  - Full backward compatibility: existing rooms and surfaces without dimensions remain valid; missing dimensions yield `None` calculations.
  - Owner isolation preserved across Project → Room → Surface hierarchy (foreign access returns 404, unauthenticated returns 401).

#### Sub-Stage 5A Database:
- Migration: `backend/alembic/versions/0007_add_measurement_dimensions.py` (parent: `0006_create_surfaces`).
- Columns added: `rooms.length`, `rooms.width`, `rooms.height`, `surfaces.width`, `surfaces.height` (all `sa.Numeric(10, 3)` nullable).

#### Sub-Stage 5A Tests:
- Focused measurement suite (`test_room_measurements.py`): 26 passed, 0 failed.
- Room suite (`test_rooms.py`): 12 passed, 0 failed.
- Surface suite (`test_surfaces.py`): 15 passed, 0 failed.
- Full backend test suite: 100 passed, 0 failed.
- Full frontend test suite: 37 passed, 0 failed.
- TypeScript strict typecheck: PASS (0 errors).
- Frontend production build: PASS (46 modules transformed).
- `git diff --check`: PASS.

#### Sub-Stage 5A Verification:
- Dimension validation (zeros rejected, negatives rejected, precision > 3 rejected with 422): PASS.
- Canonical room geometry ($5.000 \times 4.000 \times 2.700\text{ m}$): PASS.
- 4-wall surface area sum identity ($48.600\text{ m}^2$): PASS.
- Migration linear upgrade, downgrade -1, re-upgrade: PASS.
- Owner isolation & 404 security: PASS.
- Pre-existing room/surface backward compatibility: PASS.

#### Execution Sub-Stage 5B: Openings, Deductions & Net Surface Area
- **Status**: Completed
- **Date**: 2026-09-10
- **Scope**:
  - Added first-class `Opening` entity attached strictly to `WALL` surfaces (`opening_type` in `DOOR`, `WINDOW`, `OTHER`).
  - High-precision dimensions in meters using `sa.Numeric(10, 3)` and Python `Decimal` (`width`, `height`, integer `quantity >= 1`).
  - Implemented pure domain opening area calculations in `app/domain/rules/room_geometry.py`:
    - `single_area = (width * height).quantize(Decimal("0.001"))`
    - `total_area = (width * height * quantity).quantize(Decimal("0.001"))`
    - Wall deduction area = sum of active opening deductions
    - Wall net area = `gross_area - deduction_area` (strictly non-negative; zero when deductions equal gross area)
    - Non-WALL surfaces (`FLOOR`, `CEILING`, `OTHER`) return `None` for deductions and net area.
  - Geometry integrity & over-deduction protection:
    - Prevented creating, updating, or restoring openings where deductions would exceed gross wall area (`DeductionExceedsGrossAreaError` -> HTTP 422).
    - Prevented shrinking wall surface dimensions smaller than existing active deductions (`DeductionExceedsGrossAreaError` -> HTTP 422).
    - Persisted state remains completely unchanged on rejected write operations.
  - Canonical acceptance room verified:
    - Room: $5.000 \times 4.000 \times 2.700\text{ m}$
    - Wall 1: $13.500\text{ m}^2$ gross, Door $0.900 \times 2.000\text{ m}$ ($1.800\text{ m}^2$), net $11.700\text{ m}^2$
    - Wall 2: $10.800\text{ m}^2$ gross, Window $1.500 \times 1.400\text{ m}$ ($2.100\text{ m}^2$), net $8.700\text{ m}^2$
    - Wall 3: $13.500\text{ m}^2$ gross, net $13.500\text{ m}^2$
    - Wall 4: $10.800\text{ m}^2$ gross, net $10.800\text{ m}^2$
    - Total gross wall area: $48.600\text{ m}^2$
    - Total deductions: $3.900\text{ m}^2$
    - Total net wall area: $44.700\text{ m}^2$ ($48.600 - 3.900 = 44.700\text{ m}^2$)
  - Room aggregation architecture:
    - Child-dependent totals calculated strictly in domain/service aggregation layer with zero N+1 queries.
    - `SurfaceService.list_surfaces` and `RoomService.list_rooms` use aggregated PostgreSQL subqueries outer-joined in single roundtrips.
    - Composite index `ix_openings_surface_archived(surface_id, is_archived)` for high query efficiency.
  - Archive/restore behavior:
    - Archiving opening excludes it from deductions and restores net wall area.
    - Restoring opening re-includes it in deductions, blocked if wall shrunk in between.
    - In multiple-opening setups, archiving one updates deductions accurately.
  - Transitive owner isolation across 4 levels (`Owner → Project → Room → Surface → Opening`):
    - Foreign/mismatched IDs return uniform 404 responses.
    - Unauthenticated requests return 401.

#### Sub-Stage 5B Database:
- Migration: `backend/alembic/versions/0008_create_openings_table.py` (parent: `0007_add_measurement_dimensions`).
- Table created: `openings` with enum `openingtype` (`DOOR`, `WINDOW`, `OTHER`), UUID PK, `surface_id` FK with `ON DELETE CASCADE`, `width`, `height`, `quantity`, `description`, `is_archived`, UTC timestamps, and index `ix_openings_surface_archived`.
- Reversibility verified via `downgrade -1` and `upgrade head` cycle against PostgreSQL.

#### Sub-Stage 5B Tests:
- Focused opening suite (`test_openings.py`): 23 passed, 0 failed.
- Targeted measurement & hierarchy suites (`test_openings.py`, `test_room_measurements.py`, `test_surfaces.py`, `test_rooms.py`): 76 passed, 0 failed.
- Full backend test suite: 123 passed, 0 failed.
- Full frontend test suite: 37 passed, 0 failed.
- TypeScript strict typecheck: PASS (0 errors).
- Frontend production build: PASS (46 modules transformed).
- `git diff --check`: PASS (0 errors).

#### Sub-Stage 5B Verification:
- Opening domain rules & WALL-only restriction: PASS.
- Decimal opening area & net surface calculations: PASS.
- Geometry integrity & over-deduction protection on all write paths: PASS.
- Canonical room verification ($48.600 - 3.900 = 44.700\text{ m}^2$): PASS.
- Query performance & zero N+1 patterns: PASS.
- Reversible migration `0008_create_openings_table.py`: PASS.
- 4-level security and owner isolation: PASS.
- Archive / restore edge cases (Scenarios A, B, C): PASS.
- Backward compatibility: PASS.

#### Remaining Canonical Stage 5 Work (as recorded after Sub-Stage 5B):
- Execution Sub-Stage 5E: Final manual acceptance test (original 5 × 4 × 2.7 room scenario) — resolved 2026-09-11 by owner acceptance; Canonical Stage 5 is **Completed**.

#### Execution Sub-Stage 5C: Measurement Frontend UI
- **Status**: Completed
- **Date**: 2026-09-10
- **Scope**:
  - Room measurement UI:
    - Optional metric dimension inputs (`length`, `width`, `height` in meters with `0.001` step precision).
    - Natural numerical inputs supported (`5`, `4`, `2.7`, `0.9`); blank values serialize to `null` instead of `0`.
    - Responsive room calculations summary card rendering refreshed backend-authoritative metrics: floor area (`m²`), ceiling area (`m²`), perimeter (`m`), total gross wall area (`m²`), total deduction area (`m²`), and net wall area (`m²`).
    - Unmeasured rooms render a clear placeholder badge without fabricating geometry.
    - In-place room dimension editing directly inside room detail view with live update upon save.
  - Wall / Surface measurement UI:
    - Optional surface dimensions (`width`, `height` in meters).
    - Gross area, deduction area, and net wall area display derived strictly from backend responses.
    - Clear informative notice for `WALL` surfaces without dimensions prompting dimension entry before opening management is accessible.
    - Opening management strictly restricted to measured `WALL` surfaces (`FLOOR`, `CEILING`, `OTHER` do not expose openings).
  - Opening management UI (`OpeningList`):
    - First-class opening management attached strictly to measured `WALL` surfaces (`DOOR`, `WINDOW`, `OTHER`).
    - Inputs for dimensions (`width`, `height`), unit quantity (`quantity >= 1`), optional name, and description.
    - Live client-side preview for single opening area and total area during form editing (ephemeral UX-only).
    - Multi-unit badge indicator (`×N`) and distinct metric formatting (`formatMetric`).
    - Non-destructive inline error banner capturing backend HTTP 422 over-deduction validation errors (`DeductionExceedsGrossAreaError`), preserving user form input intact for correction.
    - Soft archive and restore support with include-archived toggle.
  - Dependent state reconciliation without browser reload:
    - Unidirectional callback chain: `OpeningList.onOpeningChanged` → `SurfaceList.load()` + `onMeasurementChanged` → `ProjectWorkspace.fetchRoom()`.
    - Verified across Opening CREATE, UPDATE, ARCHIVE, RESTORE, WALL dimension updates, and ROOM dimension updates.
  - Canonical Room UI scenario verified:
    - Room 5.000 × 4.000 × 2.700 m (Floor: 20.000 m², Ceiling: 20.000 m², Perimeter: 18.000 m, Gross walls: 48.600 m²).
    - Wall 1: 5.000 × 2.700 m (Gross: 13.500 m²), Door: 0.900 × 2.000 m (1.800 m²), Wall 1 Net: 11.700 m².
    - Wall 2: 4.000 × 2.700 m (Gross: 10.800 m²), Window: 1.500 × 1.400 m (2.100 m²), Wall 2 Net: 8.700 m².
    - Room aggregate totals: Deductions: 3.900 m², Net walls: 44.700 m².
  - Full dual-language PL / RU localization:
    - 155 translation keys perfectly mirrored between `pl.json` and `ru.json`.
    - Zero hardcoded user-facing strings in component JSX.
  - Mobile Telegram Mini App layout verification:
    - Tested for mobile viewport (390×844): no horizontal overflow, multi-column metric cards adapt smoothly, touch-friendly buttons, Telegram `BackButton` hierarchical integration preserved.

#### Sub-Stage 5C Database:
- None; consumed existing Stage 5A and Stage 5B backend schemas and APIs without migration changes.

#### Sub-Stage 5C Tests:
- Focused Stage 5C measurement frontend tests: 29 passed, 0 failed.
  - `OpeningList.test.tsx`: 8 passed.
  - `SurfaceList.test.tsx`: 6 passed.
  - `RoomList.test.tsx`: 5 passed.
  - `ProjectWorkspace.test.tsx`: 10 passed.
- Full frontend test suite (`vitest --run`): 56 passed across 8 test files, 0 failed.
- Full backend regression suite (`pytest backend/tests`): 123 passed across 8 test files, 0 failed.
- TypeScript strict typecheck (`tsc -p frontend/tsconfig.json --noEmit`): PASS (0 errors).
- Frontend production build (`vite build`): PASS (49 modules transformed, 217.52 kB JS / 16.46 kB CSS).
- `git diff --check`: PASS (0 whitespace errors).

#### Sub-Stage 5C Verification:
- Room measurement UX (optional inputs, blank to null, decimal precision, calculation summary card, in-place edit): PASS.
- Surface measurement UX (dimensions, gross/deduction/net displays, dimension requirement gating): PASS.
- Opening management UX (create, edit, archive, restore, multi-unit quantity, 422 over-deduction error preservation): PASS.
- Ephemeral preview vs backend authoritative source of truth: PASS.
- Multi-level dependent state refresh without page reload: PASS.
- Dual-language PL/RU localization and mirrored key audit: PASS.
- Canonical room geometry UI representation ($48.600 - 3.900 = 44.700\text{ m}^2$): PASS.
- Mobile viewport layout analysis (390×844): PASS.
- Scope review confirmed zero out-of-scope work: PASS.

#### Execution Sub-Stage 5D: Practical Measurement Workflow / UX Refinement
- **Status**: Completed
- **Date**: 2026-09-10
- **Scope**:
  - Decimal mobile input modes:
    - `inputMode="decimal"` on all metric dimension inputs — room `length`/`width`/`height` (both quick-create and in-place edit forms) and surface `width`/`height` — bringing up the numeric keypad on mobile.
    - `inputMode="numeric"` on opening `quantity` for whole-number keypad entry.
  - Direct "enter room dimensions" action:
    - Unmeasured rooms now render a prominent `+ Wprowadź wymiary` (PL) / `+ Ввести размеры` (RU) call-to-action button (`measure-room-action`) that opens the in-place room dimension edit form directly, replacing the previous dead-end notice.
  - Prominent net wall area hierarchy:
    - Room calculations summary reorganized into a two-tier layout: a primary highlighted `Net wall area` card (emerald emphasis) with a `Gross − Deductions = Net` breakdown line, and a secondary compact three-card grid for floor area, ceiling area, and perimeter.
  - Wall arithmetic hierarchy in SurfaceList:
    - Measured `WALL` surfaces render a `Gross − Deductions = Net` three-column box with the net value emphasized on an emerald chip; non-WALL surfaces show a compact single gross area line.
  - Streamlined opening entry:
    - Optional name/description fields grouped under a clearly labeled `Opcjonalne szczegóły` (PL) / `Дополнительные данные` (RU) secondary section with a divider, keeping the primary dimension form focused and mobile-friendly.
  - Dual-language PL / RU localization:
    - 157 translation keys perfectly mirrored between `pl.json` and `ru.json` (added `enter_dimensions`, `optional_details`).
  - No backend/domain changes: consumes existing Stage 5A/5B/5C schemas and APIs.

#### Sub-Stage 5D Database:
- None; consumed existing Stage 5A and Stage 5B backend schemas and APIs without migration changes.

#### Sub-Stage 5D Tests:
- Focused Stage 5D frontend tests: 28 passed, 0 failed.
  - `ProjectWorkspace.test.tsx`: 12 passed (incl. `measure-room-action` opens edit form with `inputMode="decimal"`).
  - `SurfaceList.test.tsx`: 7 passed (incl. gross − deduction = net hierarchy + `inputMode="decimal"`).
  - `OpeningList.test.tsx`: 9 passed (incl. decimal/numeric inputMode + optional details section).
- Full frontend test suite (`vitest --run`): 59 passed across 8 test files, 0 failed.
- Full backend regression suite (`pytest backend/tests`): 123 passed across 8 test files, 0 failed.
- TypeScript strict typecheck (`tsc -p frontend/tsconfig.json --noEmit`): PASS (0 errors).
- Frontend production build (`vite build`): PASS (49 modules transformed).
- `git diff --check`: PASS (0 whitespace errors).

#### Sub-Stage 5D Verification:
- Mobile decimal/numeric input modes (`inputMode` attributes): PASS.
- Direct room dimension entry from unmeasured notice (`measure-room-action`): PASS.
- Room totals hierarchy (Net wall area prominent, `Gross − Deductions = Net`): PASS.
- Wall arithmetic hierarchy (`Gross − Deductions = Net`, non-wall compact gross): PASS.
- Streamlined opening entry (optional details grouped secondary section): PASS.
- PL/RU localization and mirrored key audit (157/157): PASS.
- Backend regression and scope review (zero backend/domain changes): PASS.
- Telegram BackButton / theme integration preserved (untouched by this sub-stage): PASS.

#### Execution Sub-Stage 5D.1A: Wall Generation & Custom Shape Measurements
- **Status**: Completed (implementation verified)
- **Date**: 2026-09-10
- **Scope**:
  - **Surface positional ordering**: nullable `surfaces.position` column (reversible migration `0009_add_surface_position`) and surface listing ordered `position ASC NULLS LAST, created_at DESC`; legacy null-position surfaces remain valid and sort last; no uniqueness constraint (positions are a presentation hint).
  - **Non-destructive canonical wall generation**: `POST /api/projects/{project_id}/rooms/{room_id}/surfaces/generate` returns the 4 canonical rectangle walls from room `length × width × height` — Wall1/Wall3 = `length × height`, Wall2/Wall4 = `width × height`, positions 0–3, all `surface_type=WALL`. Domain layer uses language-neutral names; floor/ceiling are never auto-generated. Generation rules:
    - (A) room missing `length` / `width` / `height` → 422;
    - (B) no active WALLs → create exactly 4 canonical walls;
    - (C) active walls already equal the canonical set → idempotent no-op returning existing walls;
    - (D) any other configuration → 409 Conflict, modifying nothing.
  - **Wall-derived room totals**: pure-rule `calculate_wall_derived_totals` + `resolve_room_totals` aggregate measured WALL surfaces — `wall_count`, `perimeter = Σ widths`, `total_wall_area = Σ gross`, `total_deduction_area`, `net_wall_area` — with zero-N+1 queries in `RoomService`. Custom/irregular rooms report `floor_area = None` and `ceiling_area = None` (never fabricated); rectangles without walls keep formula geometry (`wall_count = 0`).
  - **Canonical acceptance values**: surface-derived totals exactly match the formula — perimeter `18.000`, gross `48.600`, door `0.900 × 2.000 → 1.800` + window `1.500 × 1.400 → 2.100` deductions → net `44.700`.
  - **Frontend wall input modes** (`PROSTOKĄT` / RECTANGLE vs `DOWOLNY KSZTAŁT` / CUSTOM — frontend state only, not persisted, no CAD/polygon editing):
    - Rectangle mode exposes `Wygeneruj 4 ściany` (generate action) when the room has dimensions; a generation conflict (409) is surfaced without hiding existing walls.
    - Custom mode provides sequential wall entry — the next empty row is UI state only and never persisted; submitting a row sends one real `WALL` with positional ordering, default height from `Room.height`, and an `Inna wysokość` override that sets `Surface.height`; no phantom/empty/zero-width requests.
    - Direct `+ Drzwi / + Okno / + Inny otwór` quick actions on every measured wall card open the opening form with the type pre-selected (`OpeningList.initialType`); no room-level openings.
  - **Room summary additions**: `wall_count` display; custom rooms render floor/ceiling as `—` (via `formatMetric`), with perimeter and totals derived from measured walls.
  - **i18n**: 168 mirrored PL/RU keys (+11 new).

#### Sub-Stage 5D.1A Database:
- Migration: `backend/alembic/versions/0009_add_surface_position.py` (parent: `0008_create_openings_table`).
- Column added: `surfaces.position` (`sa.Integer()`, nullable); downgrade drops the column (verified reversible on dev Postgres).

#### Sub-Stage 5D.1A Tests:
- Focused backend wall generation suite (`tests/test_wall_generation.py`): 20 passed, 0 failed (canonical generation, idempotent no-op, 422 missing dims, 409 conflict with nothing modified, archived walls ignored, legacy null-position walls, canonical door+window totals, custom irregular room `floor_area`/`ceiling_area` None, rectangle-without-walls, nulls-last ordering, response shapes, owner isolation). Added verification-time regression: negative `position` rejected (422) and null `position` accepted (`tests/test_surfaces.py`).
- Full backend test suite (`pytest backend/tests`): 144 passed across 8 test files, 0 failed.
- Focused frontend Stage 5D.1A tests: 11 new (generate action + no duplication, idempotent repeat keeps 4 walls, 409 surfaced, sequential create, no phantom request, default height, height override, quick-action type pre-selection and Door→Window switching without duplicate forms, room-detail generate, wall_count + custom floor/ceiling `—`).
- Full frontend test suite (`vitest --run`): 70 passed across 8 test files, 0 failed.
- TypeScript strict typecheck (`tsc -p frontend/tsconfig.json --noEmit`): PASS (0 errors).
- Frontend production build (`vite build`): PASS (49 modules transformed).
- Locale parity audit (PL/RU): 168/168 keys, 0 missing.
- `git diff --check`: PASS (0 whitespace errors).

#### Sub-Stage 5D.1A Verification:
- Wall generation creates exactly 4 canonical walls (positions 0–3, dims matching the room) without touching existing work: PASS.
- Actual verification totals (room 5 × 4 × 2.7): generated walls 13.500 / 10.800 / 13.500 / 10.800 m²; wall_count 4; perimeter 18.000; gross 48.600; door 1.800 + window 2.100 → deductions 3.900; net 44.700. Custom 5-wall room: widths 5.000/4.000/3.500/6.000/2.500, wall_count 5, perimeter 21.000, gross 59.050, deductions 1.800, net 57.250, floor/ceiling None.
- Generation conflict (409) modifies nothing and is surfaced in the UI: PASS.
- Custom sequential wall entry never persists empty rows (no phantom request): PASS.
- Default wall height from room and `Inna wysokość` override: PASS.
- Quick actions pre-select the opening type on the measured wall card: PASS.
- Custom/irregular room floor & ceiling unavailable (`None` → `—`), perimeter from wall widths: PASS.
- PL/RU mirrored keys (168/168): PASS.
- Backend regression and scope review (no 5D.1B / 5E / Stage 6 work started): PASS.

#### Execution Sub-Stage 5D.1B: Composite Floor & Ceiling Geometry
- **Status**: Completed
- **Date**: 2026-09-11
- **Scope**:
  - Added one reusable `AreaSegment` entity (no separate FloorSegment/CeilingSegment models): `room_id` FK (ON DELETE CASCADE), `plane` enum `areaplane` (`FLOOR` / `CEILING`), `operation` enum `areaoperation` (`ADD` / `SUBTRACT`), `width` / `height` as `sa.Numeric(10, 3)` (`Decimal`), nullable `position` and `label`, `is_archived`, UTC timestamps, composite index `ix_area_segments_room_plane_archived (room_id, plane, is_archived)`.
  - Pure domain rules in `app/domain/rules/room_geometry.py`:
    - `segment_area = width × height` quantized to `0.001 m²`
    - `calculate_plane_base_area(length, width)` → `L × W` for a RECTANGLE room, `None` for a CUSTOM room.
    - Per plane (base-aware): `base_area = L × W` (RECTANGLE) or `0` (CUSTOM); `additive_area = Σ active ADD`, `subtraction_area = Σ active SUBTRACT`, `net_area = base_area + additive − subtraction`.
    - Zero net allowed; negative net rejected (`NegativeNetAreaError` → HTTP 422 on create/update/restore) using the **same** base-aware effective total (a RECTANGLE subtraction may deduct from the room base); archived segments always excluded.
  - Room total resolution (`resolve_room_totals`):
    - A plane with active segments → effective `net_area` (base + adjustments).
    - A RECTANGLE plane with no segments → existing formula `L × W` base (never `0.000`).
    - A CUSTOM (no dims) plane with no segments → `None`.
    - FLOOR and CEILING resolved independently; a segments-only branch lets an irregular room measured purely as composite planes still yield calculations (never fabricates rectangular `L × W`).
  - `RoomService.list_rooms` aggregates active segments in a single grouped query per project (zero N+1, constant query count); `get_room` loads both planes in one query.
  - API `/api/projects/{project}/rooms/{room}/area-segments`: list (with `?plane=` filter, `?include_archived=`), create, get, patch, archive, restore. Pydantic v2 DTOs validate `Decimal gt=0`, `decimal_places=3`, `max_digits=10`; owner isolation intact (foreign → 404, unauthenticated → 401).
  - Frontend `AreaSegmentList`: independent PODŁOGA and SUFIT sections, each with `[+ Dodaj prostokąt]` (presets `ADD`) and `[+ Dodaj odjęcie]` (presets `SUBTRACT`), inline add/edit form (`inputMode="decimal"` width/length + optional label), rows with operation badge / label / `width × height = area`, `Razem: X.XXX m²` badge, archive/restore, and `onMeasurementChanged` refresh of room totals without a full reload. Mobile-friendly (no horizontal scroll, no CAD).
  - PL/RU locale parity preserved (198/198 keys).

#### Sub-Stage 5D.1B Database:
- Migration: `backend/alembic/versions/0010_create_area_segments_table.py` (parent: `0009_add_surface_position`).
- Table created: `area_segments` with enums `areaplane` / `areaoperation` (inline `sa.Enum` columns, `DROP TYPE IF EXISTS` on downgrade), UUID PK, `room_id` FK with `ON DELETE CASCADE`, `width`/`height` `Numeric(10,3)`, `is_archived` default `false`, UTC timestamps, and indexes `ix_area_segments_room_id` + `ix_area_segments_room_plane_archived`.
- Single Alembic head (`0010_create_area_segments_table`); linear upgrade / downgrade -1 / re-upgrade cycle verified against PostgreSQL.

#### Sub-Stage 5D.1B Tests:
- Focused area-segment backend suite (`test_area_segments.py`): 21 passed, 0 failed.
- Full backend test suite: 165 passed, 0 failed.
- Focused frontend area-segment suite (`AreaSegmentList.test.tsx`): 13 passed, 0 failed.
- Full frontend test suite: 101 passed, 0 failed.
- TypeScript strict typecheck: PASS (0 errors).
- Frontend production build: PASS.
- Locale parity PL/RU: 198/198 keys mirrored.
- `git diff --check`: PASS.

#### Sub-Stage 5D.1B Verification:
- AreaSegment model (one entity, plane/operation enums, Numeric(10,3), archived excluded, owner isolation): PASS.
- ADD / SUBTRACT / net = ADD − SUBTRACT calculations, zero allowed, negative rejected on create/update/restore, DB unchanged on rejected writes: PASS.
- Plane independence (FLOOR mutations never affect CEILING total and vice versa): PASS.
- Room rules (rectangle → L×W fallback, custom no-segments → None, active segments → segment value, one plane segments + other plane independent fallback/None, no fabricated rectangle for irregular rooms): PASS.
- Archive removes from totals / restore re-adds / restore fails safely on negative net: PASS.
- Migration 0010 (follows 0009, clean upgrade/downgrade -1/re-upgrade, enums removed/recreated, single head): PASS.
- Performance (zero N+1, constant-query list_rooms aggregation): PASS.
- Frontend (independent sections, operation presets, add/edit/archive/restore, totals refresh without full reload, mobile layout, PL/RU parity): PASS.
- Regression (rectangle wall generation, custom walls, openings/deductions, room mode routing, Telegram BackButton, 5A–5D.1A.2 suites green): PASS.

#### Execution Sub-Stage 5D.1B.2 (Hotfix): Rectangle Base-Area Semantics
- **Status**: Completed
- **Date**: 2026-09-11
- **Problem**: Rectangle plane totals were computed from active segments only, ignoring the room `L × W` base — a rectangle with zero segments showed `total = 0.000`, and a lone `SUBTRACT 0.700 × 0.800` was rejected as `0.000 − 0.560 < 0`. The frontend duplicated the segment-only calculation as its display source.
- **Calculation fix (backend authoritative)**:
  - `calculate_plane_base_area(length, width)` returns `L × W` for RECTANGLE, `None` for CUSTOM.
  - `calculate_plane_totals(segments, base_area=None)` computes `net = base_area + Σ ADD − Σ SUBTRACT`; the negative guard uses the same effective total. `PlaneAreaTotals` gains `base_area`.
  - `area_segment_service._assert_plane_net_non_negative` loads the room base, so create/update/restore of a SUBTRACT may deduct from the rectangle base.
  - `room_service._load_plane_segment_totals` / `list_rooms` fold the base into room `calculations.floor_area` / `ceiling_area`; removed the dead `_plane_totals_from_segments`.
  - `AreaSegmentListResponse` gains `planes: {FLOOR, CEILING} → {base_area, adjustment_area, net_area}` (adjustment = ADD − SUBTRACT).
  - **No DB migration** — pure calculation + response DTO; Alembic head remains `0010`.
- **UI fix**: `AreaSegmentList` renders the backend-provided per-plane summary (`Powierzchnia bazowa` / `Korekty` / `Razem`) instead of computing totals; a rectangle never shows `0.000` for a known base, and a CUSTOM room shows no base row and no fabricated total. Added `base_area` / `adjustments` locale keys (PL/RU).
- **Verified examples**: `3.700 × 3.300` → base `12.210`; SUBTRACT `0.700 × 0.800` → `11.650`; ADD `1.000 × 0.500` → `12.710`; SUBTRACT `4.000 × 4.000` (16 > 12.210) → 422; FLOOR adjustment leaves CEILING at `12.210`; archive/restore recalculates against base (`11.650 → 12.210 → 11.650`); CUSTOM unchanged (no base, no segments → `None`, segments → `ADD − SUBTRACT` only).

#### Execution Sub-Stage 5E.1 (Hotfix): Mobile/Navigation Cleanup
- **Status**: Completed
- **Date**: 2026-09-11
- **Scope** (owner-verified manually, safety checks re-run before commit):
  - Removed the redundant rectangle/custom wall-input mode toggle from `SurfaceList` (`mode-rectangle` / `mode-custom`); wall mode is now derived per room from its measured shape via `resolveRoomMeasurementMode`, so a CUSTOM room lands directly in the sequential custom-wall entry workflow (no intermediate shape tap, no generic `add-surface` control).
  - Rebuilt the wall surface card for mobile: header badges, dimensions, `Gross − Deductions = Net` summary panel, then a 2-column action grid with `min-h-11` (44 px) touch targets for quick openings (door/window/other), manage-openings toggle, edit, and archive/restore; non-wall surfaces keep a compact inline action row.
  - Increased touch-target size and wrap behavior on action buttons across `AreaSegmentList`, `OpeningList`, and `RoomList` (`py-1.5`, `rounded-lg`, `flex-wrap`).
  - Top-level **Obiekty** nav now always returns to the project list even from deep Project → Room → Surface views: `ProjectWorkspace` accepts a `resetSignal` prop (bumped on each "Obiekty" tap) that collapses selected project/room and closes forms; regression test locks the behavior.
  - Removed now-unused `surfaces.mode_rectangle` / `surfaces.mode_custom` locale keys from both PL and RU; parity preserved (198/198).
- **No backend / DB change** — frontend-only workflow and layout cleanup; Alembic head remains `0010`.

#### Sub-Stage 5E.1 Tests:
- Full frontend test suite: 112 passed, 0 failed.
- TypeScript strict typecheck: PASS (0 errors).
- Frontend production build: PASS.
- Locale parity PL/RU: 198/198 keys mirrored.
- `git diff --check`: PASS.

#### Sub-Stage 5E.1 Verification:
- Top-level Obiekty nav collapses deep room/surface views back to the project list: PASS.
- Custom-room walls enter the sequential entry workflow directly, defaulting to `Room.height`, without the mode toggle: PASS.
- Mobile wall card action grid renders with 44 px touch targets: PASS.
- Removed locale keys absent from source and both dictionaries: PASS.
- Regression (rectangle wall generation, custom walls, openings/deductions, area segments, room mode routing, Telegram BackButton): PASS.

#### Execution Sub-Stage 5E (Owner Acceptance): Final Manual Acceptance
- **Status**: Completed
- **Date**: 2026-09-11
- **Scope**: Final manual acceptance of the canonical `5 × 4 × 2.7` m room scenario — RECTANGLE room creation, 4-wall generation, opening subtraction (`gross − deductions = net`), composite floor/ceiling geometry, and mobile measurement navigation.
- **Closure**: Owner decision recorded 2026-09-11 — Canonical Stage 5 (Rooms, Surfaces and Measurements) is **COMPLETED**. No remaining work in Stage 5.

#### Stage 5 Follow-Up Backlog (Approved, Not Scheduled)
- **Status**: Approved follow-up backlog — Canonical Stage 5 remains **COMPLETED**; these items are recorded for future scheduling only and do not reopen, renumber, merge, or alter the scope of Canonical Stage 5 (0–20 numbering unchanged).
- **Date**: 2026-09-11

##### 5F — Opening Reveals / Ościeża
- **Purpose**: Measure and calculate window/door reveals for future preparation, painting, and estimate calculations.
- **Planned scope**:
  - Reveal calculation belongs to `Opening`, not a fake `Surface`.
  - Supported reveal sides: `left`, `right`, `top`, `bottom`.
  - User can enable only physically existing sides.
  - Reveal depth/width entered in meters.
  - Backend-authoritative derived totals: total reveal length `[m]` and total reveal area `[m²]`.
  - Typical window default may use `left + right + top` when the bottom is a sill, but side selection must remain explicit/flexible.
  - Door and window reveals aggregated separately.
- **Future Room summary** (planned):
  - `Ościeża`: `Okna` — total length m / total area m²; `Drzwi` — total length m / total area m²; `Razem` — total length m / total area m².
- **Future Estimate integration** (planned): reveal totals may feed preparation, filling/plastering, painting, corner beads / `narożniki`, and other opening-related work.

##### 5G — Compact Wall Card Actions
- **Purpose**: Reduce visual clutter on mobile wall cards.
- **Planned behavior**:
  - Default wall card: dimensions, `Gross`, `Openings/Deductions`, `Net`, compact opening counters where useful, and a single `"Opcje"` / `"Опции"` button. Collapsed by default.
  - On tap: `"Opcje"` → `"Ukryj opcje"` / `"Скрыть опции"`.
  - Expanded actions may include: `+ Door`, `+ Window`, `+ Other opening`, Manage openings, Inspection (Stage 6), Edit, Archive. Stage 14 may later add a Photo/Documentation action.
- **Requirements**: controls remain inside the wall card; mobile-first 390/412 px; touch-friendly actions; hide controls, not useful wall metrics; frontend-only expand/collapse state (no DB persistence required).

##### Roadmap Relationships
- **Stage 6C** should account for the future compact wall action menu so the Inspection entry point can later coexist with 5G without redesign.
- **Stage 10/11** may consume reveal totals.
- **Stage 14** may later add a photo action to the same compact wall actions.

---

### Canonical Stage 6: Inspection Checklist Engine
- **Status**: Completed
- **Date**: 2026-09-12
- **Scope & Canonical Mapping**:
  - **Execution Sub-Stage 6A (Completed)**: Inspection Checklist Engine domain design — INSPECTION ONLY diagnostic engine (substrate inspection before finishing), 19-section design report; no photo storage, no price/work mapping (deferred to Stages 7/11/14).
  - **Execution Sub-Stage 6B (Completed)**: Inspection Checklist Engine — **backend** (versioned immutable checklist catalog + inspection records).
  - **Execution Sub-Stage 6C (Completed)**: Inspection Checklist Engine — **mobile frontend** (inspection entry points, list, dynamic checklist, draft/review/complete/reopen, backend-authoritative findings, N+1-free list, mobile PL/RU workflow).
  - **Execution Sub-Stage 6D (Completed)**: Final manual acceptance / integration verification — owner manually accepted scenarios A–J on 2026-09-12 (WALL GYPSUM_BOARD Q3 with all five answer types, save-draft and reopen restore, Review/Complete with backend factual findings only, reopen/recomplete without duplicates; FLOOR CONCRETE S1–S4; CEILING separation from FLOOR; room-level inspection; PAINTED/OTHER optional quality; history/archive/restore; navigation and Telegram BackButton; mobile 390/844 + 412 px PL/RU).
- **Closure**: Owner decision recorded 2026-09-12 — Canonical Stage 6 (Inspection Checklist Engine) is **COMPLETED**. No remaining work in Stage 6; all Stage 7+ work remains pending explicit project-owner approval.

#### Execution Sub-Stage 6B: Inspection Checklist Engine — Backend
- **Status**: Completed
- **Date**: 2026-09-11
- **Scope**:
  - **Versioned immutable checklist catalog** (`ChecklistTemplate` / `ChecklistSection` / `ChecklistQuestion` / `ChecklistOption`): named `(code, version)` unique constraint, copy-on-write versioning, idempotent DB-reset-safe Python bootstrap (`ChecklistService._ensure_bootstrapped` — one existence query per access, inserts only missing versions, `asyncio.Lock`-serialized), read-only API (no mutation routes) so released template snapshots and their translation keys are immutable; `Inspection.template_id` stays bound to the exact version chosen at inspection start.
  - **Inspection engine** (`Inspection` / `InspectionAnswer` / `InspectionFinding`): room-scoped inspections under `/api/projects/{project_id}/rooms/{room_id}/inspections` with four valid targets — (A) a specific `WALL` surface, (B) `FLOOR` plane, (C) `CEILING` plane, (D) room-level (both `surface_id` and `plane` null); the only rejected combination is both set; non-WALL surface targets rejected 422; owner isolation uniform (foreign → 404, unauthenticated → 401).
  - **Typed answers** (`AnswerType` BOOLEAN / NUMBER / TEXT / SINGLE_CHOICE / MULTI_CHOICE) stored in exact typed columns (`value_bool`, `value_number` Numeric(10,3), `value_text` String(4096), `option_key`, `option_keys` JSON); replace-set PUT semantics (previous answers dropped, incoming set becomes whole state, atomic via DELETE+flush+INSERT); unknown question / wrong option / wrong value shape / duplicate question rejected 422; edits frozen once COMPLETED.
  - **Factual findings** (`InspectionFinding`): materialize ONLY from explicit `finding_key` on a question or option (BOOL true / NUMBER present / non-empty TEXT / selected SINGLE_CHOICE option / each selected keyed MULTI_CHOICE option); a positive NUMBER alone is never a generic finding; `value_snapshot` JSON captures the factual value at materialization.
  - **Finding lifecycle**: reconciliation identity `(question_id, finding_key)` — same source reuses a stable UUID (refreshed snapshot/source), two distinct questions sharing a finding_key stay distinct findings, disappeared sources become `is_active = False` with `resolved_at` set and are never physically deleted; `answer_id`/`question_id` use `ON DELETE SET NULL` for downstream `PhotoAnnotation.finding_id` compatibility (Stage 14).
  - **Quality-scale validation** (`assert_quality_scale_valid`): `GYPSUM_BOARD` → `Q1`–`Q4`; `CONCRETE` / `GYPSUM_PLASTER` / `CEMENT_LIME_PLASTER` → `S1`–`S4`; `PAINTED` / `OTHER` unrestricted (quality target optional); PSG aliases are not stored as separate DB values.
  - **State lifecycle**: `DRAFT → COMPLETED → reopen → DRAFT`; `completed_at` set/cleared; re-completion re-reconciles findings; archive/restore convention (soft `is_archived`, default listing excludes archived).
  - **Initial templates**: 6 baseline templates (substrate-concrete, substrate-gypsum-plaster, substrate-cement-lime-plaster, substrate-gypsum-board with extra `drywall_joints` section, substrate-painted, substrate-other) covering general condition, cracking (CRACK), unevenness (UNEVENNESS), loose/dusty/oily substrate, delamination/blow-holes/efflorescence/mold, high moisture, weak adhesion, and notes.
- **Database**:
  - Migration: `backend/alembic/versions/0011_create_inspection_engine.py` (parent `0010_create_area_segments_table`; sole Alembic head).
  - Tables created: `checklist_templates`, `checklist_sections`, `checklist_questions`, `checklist_options`, `inspections`, `inspection_answers`, `inspection_findings`; enums `substrate`, `qualitylevel`, `answertype`, `inspectionstatus`; `inspections.plane` reuses the `areaplane` type owned by migration 0010 (`create_type=False`, never duplicated); `inspections.status` server default quoted `'DRAFT'`.
  - Reversibility: `downgrade -1` then `upgrade head` verified on real PostgreSQL; downgrade drops tables child-first + recreatable enum types and leaves `areaplane` to 0010; all seven tables restored after the cycle.
- **Tests**:
  - Focused Stage 6B suites: 60 passed, 0 failed (`test_inspection_rules.py` — quality scale + finding materialization; `test_inspection_routes.py` — OpenAPI contract: checklist family GET-only + 8-path inspection family + security; `test_inspections.py` — template catalog/idempotency, all four target modes, both-set rejection, non-WALL rejection, cross-room surface rejection, substrate/template mismatch, quality-scale enforcement, typed answers, replace-set atomicity, complete → findings, stable-UUID reconcile, duplicate-source distinct findings, archive/restore, state transitions, owner isolation).
  - Full backend suite: 235 passed, 0 failed.
  - `git diff --check`: PASS; all changed source lines ≤ 100 chars; single Alembic head confirmed; DB at head `0011`.
  - Frontend untouched by 6B (no frontend changes; Stage 6 frontend is 6C).
- **Verification**:
  - Target model A–D inspectable and reject-only-both-set: PASS.
  - Template bootstrap idempotent, no duplicate rows, unique `(code, version)`, old `Inspection.template_id` keeps its version, no mutation API, immutable translation keys: PASS.
  - All five answer types persisted in exact typed columns, MULTI_CHOICE as JSON, invalid/unknown/duplicate answers rejected 422, replace-set atomic, COMPLETED blocks edits: PASS.
  - Finding semantics explicit-only, `(question_id, finding_key)` identity, stable UUID reuse, distinct sources distinct, inactive + resolved_at, never deleted, PhotoAnnotation FK compat: PASS.
  - Quality validation per substrate family, PSG not stored separately: PASS.
  - State lifecycle transitions, completed_at, re-complete reconcile, archive/restore: PASS.
  - Route family matches OpenAPI contract tests; every route requires auth: PASS.
  - Migration 0011 parent 0010, single head, upgrade → downgrade -1 → upgrade clean on PostgreSQL, areaplane not duplicated, all seven tables restored: PASS.
  - Regression: focused + full backend suites green, `git diff --check` clean, no Stage 7 or preview of later stages: PASS.
- **Deferred**:
  - Execution Sub-Stage 6D completed 2026-09-12 (owner manual acceptance PASS); all Stage 7+ work remains pending explicit project-owner approval.

#### Execution Sub-Stage 6C: Inspection Checklist Engine — Mobile Frontend
- **Status**: Completed
- **Date**: 2026-09-11
- **Scope**:
  - **Inspection entry points** (four targets): WALL surface (per-wall `Badanie ściany` in `SurfaceList`), FLOOR plane, CEILING plane, and room-level — all routed through `ProjectWorkspace` room inspection panel with a single modular entry; no duplicate/conflicting controls; Stage 5 measurement workflows untouched.
  - **Inspection list** (`InspectionList`): cards render only data already present in the list response (substrate, status badge, quality target, completed date); **no per-card findings fetches** — N cards render with zero extra findings requests; findings are fetched only when opening/viewing an inspection.
  - **Backend finding authority**: the frontend has **no mirror** of backend `build_finding_specs`; before completion the Review step is a factual answer summary (`Podsumowanie odpowiedzi` / `Сводка ответов`) showing substrate, quality target, questions and current answers — it never claims persisted findings; after `POST .../complete` the frontend fetches and renders the actual backend `InspectionFinding` records; completion failure preserves local review state.
  - **Start flow** (substrate → quality → create): `GYPSUM_BOARD` → Q1–Q4; `CONCRETE`/`GYPSUM_PLASTER`/`CEMENT_LIME_PLASTER` → S1–S4; `PAINTED`/`OTHER` → quality optional with S1–S4 and Q1–Q4 both allowed, skip made explicit via an optional-quality hint; API always sends canonical `Q1`–`Q4` (PSG aliases never sent).
  - **Dynamic checklist** (`InspectionFlow`): questions/options render from backend template data + i18n dotted keys (no hardcoded domain questions in JSX); all five answer types round-trip — BOOLEAN, SINGLE_CHOICE, MULTI_CHOICE, NUMBER (`inputMode="decimal"`, comma→dot normalization), TEXT; unanswered questions never create findings.
  - **Draft / review / complete / reopen lifecycle**: create DRAFT → answer → explicit Save Draft (`PUT .../answers` replace-set) → resume/open DRAFT prefilled from backend → Review Answers → Complete (PUT answers then `POST .../complete` → backend materializes findings → fetch findings → completed read-only view) → completed answers read-only → reopen restores editable DRAFT.
  - **Findings UI**: completed inspection shows only factual backend findings (label + value snapshot); no severity, risk score, mitigation, warranty exclusions, recommended work, or price/estimate actions (Stage 7+).
  - **Navigation / mobile**: Telegram BackButton hierarchy (form → flow → list → room → rooms → project) preserved and regression-tested; top-level Obiekty navigation valid; single-column ~390px layout with wrapping controls and ~44px touch targets.
- **Tests**:
  - Focused 6C suites: InspectionFlow 14, InspectionList 9, locale parity 2 — all passed (entry targets, quality scale routing incl. canonical Q1–Q4 payload, all five answer types, save-draft payload, resume prefill, review-shows-answers-not-findings, complete → backend findings, completion-failure preserves state, reopen, completed read-only, N+1 regression, PL/RU parity).
  - Full frontend suite: 142 passed, 0 failed (13 files).
  - Full backend suite: 235 passed, 0 failed (unchanged by 6C).
  - TypeScript strict: PASS; `vite build`: PASS; `git diff --check`: PASS.
- **Verification**:
  - Four entry targets send correct payloads (surface_id / plane FLOOR|CEILING / both null), no duplicate controls, Stage 5 workflows regression-green: PASS.
  - Inspection list renders multiple cards with zero per-card findings requests; findings fetched only on open/view: PASS.
  - No frontend finding-materialization mirror remains (grep-clean); review wording is answer review, not persisted findings: PASS.
  - Quality family routing per substrate; PAINTED/OTHER optional with explicit skip; canonical Q1–Q4 sent to API: PASS.
  - All five answer types render from template + i18n and round-trip; no hardcoded questions in JSX: PASS.
  - Draft → save → resume → review → complete → backend findings → read-only → reopen lifecycle, completion-failure state preserved: PASS.
  - Completed view displays only factual backend findings; no Stage 7 severity/risk/mitigation/warranty/price: PASS.
  - BackButton hierarchy, Obiekty navigation, mobile single-column layout and ~44px targets regression-green: PASS.
  - PL/RU parity incl. new review/quality labels; template key resolution fails safely (falls back to the dotted key) when unavailable: PASS.
- **Deferred**:
  - Execution Sub-Stage 6D completed 2026-09-12 (owner manual acceptance PASS); all Stage 7+ work remains pending explicit project-owner approval.

#### Execution Sub-Stage 6D: Final Manual Acceptance / Integration Verification
- **Status**: Completed
- **Date**: 2026-09-12
- **Scope**: Owner manual acceptance of the complete inspection checklist workflow (backend + mobile) across scenarios A–J before canonical Stage 6 closure.
- **Manual acceptance scenarios**:
  - **A — WALL inspection (GYPSUM_BOARD, Q3)**: only Q1–Q4 quality options offered, Q3 selected, drywall-specific questions (joints / board movement / fasteners) plus general-condition questions rendered, all five answer types (BOOLEAN / SINGLE_CHOICE / MULTI_CHOICE / NUMBER / TEXT) exercised, representative factual defects entered (crack = yes, board movement = yes, unevenness = 5 mm, notes text), Save Draft, leave and reopen — DRAFT listed, saved answers restored, substrate and Q3 restored, no answers lost: PASS.
  - **B — Review / Complete**: review shows answers only (never claims frontend-generated findings), substrate and quality target shown, values readable; Complete → status COMPLETED, answers read-only, actual findings returned from backend appear, factual only; no risk severity, no risk score, no recommended work, no warranty language, no estimate/pricing: PASS.
  - **C — Reopen / Recomplete**: reopened, crack yes → no changed, completed again — returns to COMPLETED, removed factual condition no longer active, remaining findings correct, no duplicated findings, UI no crash: PASS.
  - **D — FLOOR inspection (CONCRETE)**: target is floor (not room/wall), quality offers S1–S4, checklist works, draft/save/complete works: PASS.
  - **E — CEILING inspection**: target is ceiling, remains separate from FLOOR inspection, completing it does not modify the floor inspection: PASS.
  - **F — Room-level inspection**: neither WALL/FLOOR/CEILING incorrectly selected, general inspection creatable, draft and completion work, appears only in room-level inspection list: PASS.
  - **G — PAINTED / OTHER**: quality target clearly optional, user may skip, S1–S4 and Q1–Q4 both available if desired, no forced family validation appears in UI: PASS.
  - **H — History / Archive**: inspection history/cards readable, DRAFT vs COMPLETED visually distinct, archive works, show-archived works, restore works, no unrelated-target inspections leak into the selected target list: PASS.
  - **I — Navigation**: Room → inspection list → inspection flow → Back → inspection list → Back → room; Telegram BackButton hierarchy; top Obiekty navigation still returns to object list; Stage 5 Room/Surface measurement navigation still works: PASS.
  - **J — Mobile (390×844, 412 px)**: no horizontal scroll, substrate buttons comfortably tappable, quality controls fit, multi-choice wraps, NUMBER input opens numeric/decimal keyboard hint, textarea usable, Save Draft / Review / Complete accessible, findings readable, wall measurement UI remains usable, PL/RU switch works, no visible console/runtime errors: PASS.
- **Verification**:
  - Owner manual acceptance PASS (2026-09-12) across scenarios A–J.
  - Full backend suite: 235 passed, 0 failed (regression re-run).
  - Full frontend suite: 142 passed, 0 failed (regression re-run).
  - TypeScript strict: PASS; `vite build`: PASS; `git diff --check`: PASS.
  - Migration head unchanged: `0011_create_inspection_engine`.
- **Deferred**:
  - All Stage 7+ work remains pending explicit project-owner approval.

---

### Canonical Stage 7: Risk Rules Engine
- **Status**: In Progress
- **Date**: 2026-09-12
- **Scope & Canonical Mapping**:
  - **Execution Sub-Stage 7A (Completed)**: Risk Rules Engine design inspection report — deterministic risk derivation from materialized inspection findings, severity (LOW/MEDIUM/HIGH/CRITICAL), source-finding traceability, mitigation/warranty semantics, and recommended 7B backend scope.
  - **Execution Sub-Stage 7B (Completed)**: Risk Rules Engine — **backend**, owner-verified 2026-09-12. Stage 7 is NOT yet marked Completed (7C/7D remain).
- **Closure**: Not yet — pending Execution Sub-Stage 7C (frontend/mobile Risk UI) and 7D (final manual acceptance).

#### Execution Sub-Stage 7B: Risk Rules Engine — Backend (Completed)
- **Status**: Completed (owner-verified 2026-09-12)
- **Date**: 2026-09-12
- **Scope**:
  - **Versioned immutable rule catalog** (`RiskRule` / `RiskRuleCondition`): named `(code, version)` unique constraint, 15 initial deterministic rules (CRACK_RECURRENCE, BOARD_MOVEMENT_CRACK, MOISTURE_BLOCK_FINISHING, WEAK_ADHESION_PREP, LOOSE_SUBSTRATE_REMOVAL, DUSTY_SUBSTRATE_PRIME, OILY_SUBSTRATE_DEGREASE, MOLD_TREATMENT_BEFORE_FINISH, DELAMINATION_REPAIR, UNEVENNESS_PREP_INCREASED, JOINT_TAPE_MISSING_REWORK, FASTENER_CORROSION_FIX, JOINT_GAP_FILLING, EFFLORESCENCE_CAUSE_CHECK, BLOW_HOLES_FILLING) with severity, `blocks_finishing`, `warranty_exclusion_candidate`, optional substrate restriction, and 5 i18n keys each; idempotent DB-reset-safe bootstrap (`RiskService._ensure_bootstrapped`, `asyncio.Lock`-serialized); no CRUD API (catalog is reference data).
  - **8 condition operators** (all-AND within a rule): `FINDING_PRESENT`, `FINDING_ABSENT`, `NUMBER_AT_LEAST`, `NUMBER_AT_MOST`, `SUBSTRATE_IN`, `SUBSTRATE_NOT_IN`, `TARGET_IN`, `QUALITY_IN`; numeric thresholds (e.g. UNEVENNESS ≥ 3 mm, JOINT_GAP ≥ 2 mm) are **initial domain defaults** stored in condition `value_json`, tunable as reference data; malformed/missing numeric snapshots fail safely (rule does not fire).
  - **Deterministic evaluation** (`domain/rules/risk_rules.py`): pure engine over inspection substrate/quality/target + active findings; overlapping rules may all fire (no hidden suppression); source signature = SHA-256 over sorted source finding UUIDs (order-independent, part of the stable risk identity).
  - **Risk materialization** (`Risk` / `RiskFinding`): room- and inspection-scoped rows under `/api/projects/{project_id}/rooms/{room_id}/risks`; identity `(inspection_id, rule_code, source_signature)` enforced by a unique constraint — identical inspection state always yields the same row with a stable UUID; risk rows carry `risk_code`/`rule_code`/`rule_version`, severity, 5 i18n key snapshots, `blocks_finishing`, `warranty_exclusion_candidate`, `is_active`/`resolved_at`, and ordered `source_findings` links that snapshot finding key + value even if the source finding FK later goes NULL.
  - **Reconciliation on evaluate**: `POST .../risks/evaluate` is idempotent; a reused identity keeps its UUID and its original `rule_version`/text-key snapshot (version preservation), only refreshing activity state and source-finding links; previously confirmed risks absent from the new evaluation become `is_active = False` with `resolved_at` set and are never deleted; evaluation rejected 409 unless the inspection is COMPLETED (no DB writes on rejection).
  - **API contract**: `GET .../risks` (filters: `inspection_id`, `surface_id`, `plane`, `status=active|resolved|all`), `GET .../risks/{risk_id}` (detail with source findings), `POST .../risks/evaluate` (idempotent, returns active risks with source findings); owner isolation uniform (foreign → 404, unauthenticated → 401); grouped source-finding loading (no N+1 on batch evaluate).
- **Database**:
  - Migration: `backend/alembic/versions/0012_create_risk_engine.py` (parent `0011_create_inspection_engine`; sole Alembic head).
  - Tables created: `risk_rules`, `risk_rule_conditions`, `risks`, `risk_findings`; enums `riskseverity`, `riskconditionoperator`; `risk_rules.substrate` reuses the `substrate` type owned by migration 0011 (`create_type=False`); unique `(code, version)` on rules, unique `(inspection_id, rule_code, source_signature)` on risks, unique `(risk_id, finding_id)` on links.
  - Reversibility: `downgrade -1` then `upgrade head` verified on real PostgreSQL; downgrade drops tables child-first + enum types and leaves `substrate` to 0011; all four tables restored after the cycle.
- **Tests**:
  - Focused Stage 7B suites: `test_risk_rules.py` (23 unit — signature order-independence, target derivation, all 8 operators, AND semantics, numeric thresholds, malformed-snapshot fail-safe, overlapping-rule independence), `test_risk_routes.py` (3 — OpenAPI route family + methods + auth), `test_risks.py` (14 — expected-risk set for a full answer set, moisture CRITICAL/blocking, drywall JOINT_TAPE_MISSING_REWORK, DRAFT 409, unknown 404, evaluate idempotency + stable UUIDs, reopen/recomplete reuse + resolution never-deleted, later-rule-version immutability of materialized risks, rejected DRAFT evaluation leaves risk state unchanged, active/resolved/all filters, traceable source findings, owner isolation, 401).
  - Full backend suite: 275 passed, 0 failed (40 new Stage 7B tests).
  - Full frontend suite: 142 passed, 0 failed (unchanged by 7B); TypeScript strict: PASS; `vite build`: PASS.
  - `git diff --check`: PASS; single Alembic head `0012_create_risk_engine`; migration upgrade → downgrade -1 → upgrade cycle verified on real PostgreSQL.
- **Verification**:
  - 15-rule catalog bootstraps idempotently; conditions stored as reference data; thresholds are initial domain defaults: PASS.
  - Deterministic evaluation: identical state → identical risk set + stable UUIDs; overlapping rules independent; malformed numeric snapshot fails safe: PASS.
  - COMPLETED-only gate (DRAFT → 409, rejected evaluation creates/mutates nothing), idempotent evaluate, stable-identity reuse, version preservation (a later `(code, version)` rule release does not silently mutate an existing historical Risk row or its `rule_version`/severity snapshot), resolved-never-deleted history: PASS.
  - Source-finding traceability via `risk_findings` snapshots (key + value, finding FK SET NULL-safe): PASS.
  - Route family matches OpenAPI contract tests; every route requires auth; foreign owner → 404: PASS.
  - Migration 0012 parent 0011, single head, reversible on PostgreSQL, `substrate` not duplicated: PASS.
  - Regression: full backend + frontend suites green, `git diff --check` clean, no Stage 8 work: PASS.
  - Live runtime: backend dev container on :8000 rebuilt and restarted with the Stage 7B code; the three risk routes confirmed in live OpenAPI and HTTP (unauthenticated access → 401, route mounted). Full authenticated live evaluation is `DEFERRED_ENVIRONMENT`: the dev compose `backend` service passes no `TELEGRAM_BOT_TOKEN`, so `/api/auth/telegram` refuses even with `MOCK_TELEGRAM_AUTH=true` (the auth service requires a configured bot token). No infra/compose change was made for Stage 7B; end-to-end evaluation is covered by the integration suite running the same app over ASGI transport.
- **Deferred**:
  - Stage 7 frontend (risk display / warnings UI) — not started (requires owner approval after 7B verification).
  - Downstream consumption of risks (recommended work, estimates, warranty protocol clauses) — Stages 10/11+.

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
