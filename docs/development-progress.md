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
| **Stage 2** | **Telegram Mini App Authentication** | **Completed** | Backend authentication foundation: cryptographic HMAC-SHA256 `initData` validation, User model and migration, JWT session, development mock protection |
| **Stage 3** | **Client Management** | **Completed** | Client CRUD with soft archive, search, owner isolation, i18n (PL/RU) |
| **Stage 3B** | **Client Module Verification** | **Completed** | Expanded search, archive-filter, and owner-isolation regression coverage |
| **Stage 3C** | **Claude Code Instructions & Roadmap Consistency** | **Completed** | Claude Code guidance, stage skills, dependency-safe roadmap |
| **Stage 4** | **Project / Room / Surface Foundation** | **Completed** | Owner-isolated Project, optional Client association, Room, Surface, frontend hierarchy, and final integration verification |
| **Stage 5** | **Telegram Mini App Shell & Auth** | **Completed** | Parent execution stage for official Telegram WebApp runtime, authentication, theme adaptation, and native navigation integration (functional hardening for original Stage 2 Telegram integration) |
| **Stage 5A** | **README Refresh & Telegram Mini App Shell Foundation** | **Completed** | Official WebApp runtime, centralized access, `ready()`, `expand()`, and preserved browser development flow |
| **Stage 5B** | **Real Telegram WebApp Authentication Flow** | **Completed** | Raw real `initData` forwarding, backend-only validation, explicit development mock gating, JWT ordering, localized failures |
| **Stage 5C** | **Telegram Theme, Viewport & BackButton Integration** | **Completed** | Telegram theme adaptation, viewport stability, and native BackButton hierarchy navigation (Stage 2 functional hardening) |
| Stage 6 | Room Measurements & Surface Manager | Pending | Interactive room dimensions, openings subtraction, and surface totals |
| Stage 7 | Substrate Inspection & Risk Engine | Pending | Project/surface-anchored diagnostics, deterministic risks, and technical warnings |
| Stage 8 | Estimates & Quotation | Pending | Estimate generator, PDF export preparation, and client approval flow |
| Stage 9 | Technical Protocols & Handover | Pending | Acceptance protocols (stan zero, roboty zanikające, protokół końcowy) |
| Stage 10 | Contracts & Legal Knowledge | Pending | Contract generator, standard clauses, and client communication phrases |
| Stage 11 | Offline Drafts & S3 Photo Storage | Pending | IndexedDB offline draft synchronization and S3 photo attachments |

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
- All Stage 6 (room measurements and surface manager) and subsequent product modules remain deferred pending explicit project-owner instruction.

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
