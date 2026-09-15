# Development Progress & Stage Roadmap

**Project**: Telegram Mini App for managing interior finishing and renovation work in Poland.  
**Repository**: `git@github.com:kukhmax/plan_-_estimate.git`  
**Central Entity**: OBIEKT (Project / Site)  
**Stack**: React + TypeScript + Vite + Tailwind CSS | Python + FastAPI + SQLAlchemy 2.x + Alembic + Pydantic v2 + PostgreSQL | aiogram 3.x

---

## Permanent Product Rule: Mobile-First UI

**Canonical UI target is MOBILE FIRST** — Plan & Estimate is a Telegram Mini App intended primarily for on-site use from a smartphone. The frontend remains a web application because Telegram Mini Apps run inside Telegram WebView; there is **no separate desktop-oriented UI**. This rule is permanent and binds every future frontend execution sub-stage. Also codified in `CLAUDE.md`.

- **Primary working viewport**: 320–480 px width.
- **Primary manual acceptance viewports**: 390 px, 412 px.
- Localhost desktop browser usage is primarily a development and debugging environment.

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

**Field-usage principle**: optimize workflows for a contractor standing at a construction site and using the phone with minimal taps — prefer short workflows, large controls, progressive disclosure, secondary actions hidden behind "Opcje" where appropriate, sensible defaults, reuse of previous/default dimensions where safe, and avoiding unnecessary screens and repeated data entry. This principle guides later Stage 5F/5G follow-up work, inspection workflows, photos, defect annotations, estimates, checklists, and reports. The rule is permanently documented; no screens are redesigned in this task.

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
| Stage 7 | Risk Rules Engine | **Completed** | Deterministic risk evaluation, warnings, mitigation requirements, warranty exclusions — owner-verified 2026-09-13 |
| **Stage 8** | **"Co powiedzieć klientowi" (Client Communication Assistant)** | **Completed 2026-09-13** | Deterministic, rule-driven client communication recommendations (PL/RU) from completed-inspection facts — versioned immutable phrase catalog, exact-key selection over materialized Stage 6/7 facts, complete quality matrix, mobile communication cards with evaluate / "Why?" traceability / copy / active-resolved-all history |
| **Stage 9** | **Editable Price Book / Cennik** | **Completed 2026-09-15 (OWNER ACCEPTED; merged to `main` as `96d0518`)** — 9D Completed 2026-09-13 (owner accepted); 9D.1 (mobile shell + Telegram dark theme UX correction) Completed 2026-09-14 (owner accepted; committed `c4cc6b6`); 9E.1 & 9E.2 (market architecture + research catalog) Completed 2026-09-13; 9E.3A (Kraków market research — batch A: preparation/priming/skim/sanding) Completed 2026-09-13 (evidence file only, no seeds); 9E.3B (Kraków market research — batch B: painting/glass fiber/GK) Completed 2026-09-14 (evidence file only, no seeds); 9E.3C (Kraków market research — batch C: reveals / ościeża / glify / szpalety) Completed 2026-09-14 (evidence file only, no seeds); 9E.3D (Kraków market research — batch D: microcement) Completed 2026-09-14 (evidence file only, no seeds); 9E.3E (Kraków market research — batch E: decorative finishes / Venetian) Completed 2026-09-14 (evidence file only, no seeds) — **9E.3 Web Research (Batches A–E) COMPLETE**; **9E.4 (normalization/review of all 51 items) Completed 2026-09-14 (docs-only, no seeds)**; **9E.5 (owner approval) Completed 2026-09-14 (OWNER_APPROVED — all 7 decision groups approved; 44 final implementation candidates: 28 MARKET_SUPPORTED / 16 OWN_PRICE; 7 dropped/merged)**; **9E.6A (price market evidence backend foundation) Completed 2026-09-14 (committed `31540af` — models + migration 0015 + read-only evidence endpoint)**; **9E.6B (mobile price market evidence UI) Implemented 2026-09-14 (read-only compact market evidence on Price Book cards; 44-row catalog load NOT performed — deferred per owner instruction)**; **9E.7 (load approved 44-row catalog + market evidence + nullable price foundation) Implemented 2026-09-15 (44 canonical rows: 28 MARKET_SUPPORTED / 16 OWN_PRICE; 28 market references / 112 sources seeded idempotently; legacy GENERIC seeds retired; migration 0016 makes PriceItem.price nullable — NULL = not set, 0.00 = real zero; full backend 515 tests + frontend 304 tests PASS; committed `097e46c`)**; **9E.7.1 (Price Book add/edit form visibility regression) Implemented 2026-09-15 (opening Add/Edit scrolls the form into view so the editor is actually visible on a 44-row catalog; 2 regression tests; full frontend 306 tests PASS; real-browser 390 px verification PASS; committed `f38cd13`)**; **9E.8 (Price Book mobile UX cleanup) Implemented 2026-09-15 (inline owner-price editor for catalog rows, direct Edytuj/Archiwizuj, dedicated mobile source viewer, label + S/Q UX cleanup; full frontend 323 tests PASS; real-browser 320/390/412 px verification 23/23 PASS; committed 2026-09-15 (`a948f68`, `c82c6ea`, `d1688e1`); owner accepted)**; 9F (final gate) **NOT RUN as a separate execution** — Stage 9 final acceptance completed from accumulated verification evidence and owner acceptance; **Stage 9 COMPLETE** (merged to `main` as `96d0518`) | Contractor base price catalog, labor rates, materials, equipment, difficulty surcharges; owner-editable catalog rows; **not** an estimate (that is Stage 10) — see 9A contract in the Stage Log |
| **Stage 10** | Estimate / Kosztorys | **In Progress — 10A (Surface Work Planning + Estimate Architecture) and 10A.1 (Canonical Architecture Corrections) Completed 2026-09-15 (docs-only; owner accepted; committed together as `6bbc4ce`)**; **10B.1 (Surface Work Plan backend domain) Completed 2026-09-15, owner accepted, committed `3c9751e` (2026-09-16)**; **10B.2 (Surface Work Plan HTTP API + apply-to-room-walls) Implemented 2026-09-16 (uncommitted — awaiting owner acceptance)**; **10C.1 (Compact Surface Card + Opcje progressive disclosure, frontend) Implemented 2026-09-16 (uncommitted — awaiting owner acceptance)** — 10B.3, 10C.2, 10D+ NOT STARTED | Line-item calculation by surface, substrate, and quality tier (S1–S4, Q1–Q4) — see `docs/stage-10-architecture.md` |
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
- **Status**: **Completed** (owner-verified 2026-09-13)
- **Date**: 2026-09-12 → 2026-09-13
- **Scope & Canonical Mapping**:
  - **Execution Sub-Stage 7A (Completed)**: Risk Rules Engine design inspection report — deterministic risk derivation from materialized inspection findings, severity (LOW/MEDIUM/HIGH/CRITICAL), source-finding traceability, mitigation/warranty semantics, and recommended 7B backend scope.
  - **Execution Sub-Stage 7B (Completed)**: Risk Rules Engine — **backend**, owner-verified 2026-09-12.
  - **Execution Sub-Stage 7C (Completed)**: Mobile Risk Evaluation and Risk Cards — **frontend/mobile PL/RU workflow**, owner-verified 2026-09-12.
  - **Execution Sub-Stage 7D.1 (Owner-retest fixes)**: Manual-acceptance defects corrected — mobile room-card overlap, Risk "All" filter semantics, rectangle-room measured-state regression, and reopen MULTI_CHOICE hydration/empty-option_keys regression. See the 7D.1 section below.
  - **Execution Sub-Stage 7D.2 (Final acceptance fixes)**: State-synchronization fixes from owner manual acceptance — rectangle-room measured-state capture (all-or-none L/W/H), immediate inspection question hydration, compound-risk verification (CRACK_RECURRENCE + BOARD_MOVEMENT_CRACK), plus the permanent **two-decimal metric display policy**. See the 7D.2 section below.
  - **Infrastructure hotfix (Completed)**: Docker Compose dev `backend` service now defaults `MOCK_TELEGRAM_AUTH=true` without requiring a `TELEGRAM_BOT_TOKEN`, unblocking live authenticated evaluation in the local stack.
- **Closure**: Owner decision recorded 2026-09-13 — Canonical Stage 7 (Risk Rules Engine) is **COMPLETED**. No remaining work in Stage 7; all Stage 8+ work remains pending explicit project-owner approval.

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
  - Downstream consumption of risks (recommended work, estimates, warranty protocol clauses) — Stages 10/11+.

#### Execution Sub-Stage 7C: Mobile Risk Evaluation and Risk Cards (Completed)
- **Status**: Completed (owner-verified 2026-09-12)
- **Date**: 2026-09-12
- **Scope**:
  - **Explicit risk evaluation UI**: `RiskPanel` embedded in the COMPLETED inspection review step of `InspectionFlow`; "Oceń ryzyka" / "Оценить риски" action invokes `POST /api/projects/{project_id}/rooms/{room_id}/risks/evaluate` with `{inspection_id}` and is **not rendered for DRAFT inspections**; a 409 maps to a localized not-completed message.
  - **Backend-authoritative Risk rendering**: `frontend/src/types/risk.ts` (typed DTO mirror of the Stage 7B schemas — severity, flags, 5 i18n key snapshots, source findings), `frontend/src/api/risks.ts` (`evaluateRisks`, `fetchRisks`, `fetchRiskDetail`). The frontend renders backend-returned risks only — it never determines which risks exist, suppresses overlapping rules, computes severity, or derives `blocks_finishing` / `warranty_exclusion_candidate`.
  - **Risk cards**: severity chip (LOW neutral / MEDIUM amber / HIGH orange / CRITICAL solid red), title via `risk.{slug}.title` dotted key, active/resolved status + `resolved_at`, collapsible "Szczegóły" with explanation / consequence / mitigation, `blocks_finishing` operational warning box ("Nie rozpoczynać / wstrzymać prace do usunienia przyczyny"), `warranty_exclusion_candidate` badge ("Możliwe ograniczenie odpowiedzialności"); no machine keys are exposed (unresolved dotted keys fail safe to empty).
  - **Source traceability ("Dlaczego?")**: renders backend source findings with localized `risk.finding.*` labels and safe value snapshots (bool → Tak/Nie, number → e.g. "3.500 mm", text as-is); evaluate responses carry grouped source findings; a reloaded active list lazy-fetches exactly one `GET .../risks/{risk_id}` per expanded card — no per-risk N+1 on initial load.
  - **Lifecycle & overlap**: Active/Resolved/All filters; resolved risks remain readable and visually de-emphasized (grayed, `resolved_at` shown) with no frontend manual resolution; overlapping risks (CRACK_RECURRENCE + BOARD_MOVEMENT_CRACK) render independently without suppression.
  - **Mobile PL/RU workflow**: single 390px column, wrapping chips, `min-h-11` primary touch targets, wrapping text; PL/RU parity for severity/status/flag/finding labels and the 15 rule text sets (75 keys × 2 locales), verified by locale-parity tests.
- **Files**:
  - Added: `frontend/src/types/risk.ts`, `frontend/src/api/risks.ts`, `frontend/src/components/RiskPanel.tsx`, `frontend/src/components/RiskPanel.test.tsx`.
  - Changed: `frontend/src/components/InspectionFlow.tsx` (embed `RiskPanel` in completed review step), `frontend/src/components/InspectionFlow.test.tsx` (risk API mock + 2 ENTRY tests), `frontend/src/locales/pl.json` + `ru.json` (new `risk` section: UI strings, finding labels, 15 rule objects × 5 fields), `frontend/src/locales/parity.test.ts` (risk-section parity + backend dotted-key coverage).
- **Tests**:
  - Focused: `RiskPanel.test.tsx` (11 — ENTRY, EVALUATION payload/success/localized 409 preserving the view, SEVERITY ×4 distinct with CRITICAL tone, FLAGS, TRACEABILITY one/multi-source + numeric snapshot + no per-card fetch after evaluate + lazy detail on expand, OVERLAP, LIFECYCLE active/resolved/all + re-evaluate refresh, MOBILE touch targets + single column, LOCALIZATION RU + no machine-key leak), `InspectionFlow.test.tsx` (+2 ENTRY — evaluate action only for COMPLETED, hidden for DRAFT), `parity.test.ts` (risk-section PL/RU parity + all 15 rule slugs + 15 finding labels).
  - Full frontend suite: **156 passed, 0 failed** (14 new Stage 7C tests).
  - Full backend suite: **275 passed, 0 failed** (unchanged by 7C).
  - TypeScript strict (`tsc --noEmit`): PASS; `vite build`: PASS; `git diff --check`: PASS.
- **Verification**:
  - ENTRY flow: risk UI only for COMPLETED inspections, DRAFT exposes no evaluation flow, evaluate sends the correct `inspection_id`: PASS.
  - Backend authority: no second risk engine in frontend — only evaluate call, render, and source-finding display: PASS.
  - Evaluation flow: completed → evaluate → backend response → risk list renders; 401/404/409/422/network errors localized, view preserved, retry available: PASS.
  - Risk cards: severity, active/resolved + `resolved_at`, title/explanation/consequence/mitigation, `blocks_finishing`, `warranty_exclusion_candidate`, source findings; no machine keys exposed: PASS.
  - Source traceability: one-source and multi-source risks render, numeric snapshots display safely, no frontend recomputation: PASS.
  - Overlapping risks render independently: PASS.
  - Resolved history: Active/Resolved/All filters, resolved risks readable + de-emphasized, no frontend manual resolution: PASS.
  - Query behavior: initial list is a single `GET /risks` with no per-risk source N+1; detail/source fetch is lazy per expanded card: PASS.
  - Navigation: Telegram BackButton, top Obiekty navigation, Stage 6 inspection and Stage 5 measurement navigation — full frontend regression suite (ProjectWorkspace 25, App 11, RoomList 14, SurfaceList 17, useTelegramWebApp 8, etc.) green: PASS.
  - Mobile: single-column, row wrap, text wrap, ~44 px touch targets, resolved history visually subordinate: PASS.
  - Localization: PL/RU parity, severity/status/flag labels localized, no unintended hardcoded user-facing strings, missing dotted keys fail safe: PASS.
- **Remaining**:
  - Infrastructure Docker Compose hotfix (dev `backend` service passes no `TELEGRAM_BOT_TOKEN`, blocking live authenticated evaluation) — deferred, not started.
  - 7D final manual acceptance — not started (requires owner approval).

#### Execution Sub-Stage 7D.1: Manual Acceptance Defects Corrected and Owner-Retested
- **Status**: Corrections implemented and covered by regression tests; final 7D manual acceptance still ongoing — Canonical Stage 7 remains **In Progress** (not marked Completed).
- **Date**: 2026-09-12
- **Scope** — four manual-acceptance defect groups corrected:
  1. **Mobile room-card overlap**: `RoomList` card layout restructured to a stacked single column (`flex flex-col`) so name, dimensions and the 3-across action grid can never crowd each other; name gets a wrapping `min-w-0 break-words` row, actions live in a dedicated container (`grid grid-cols-3 min-h-11` collapsing to an inline wrapping `sm:flex` row), and every action button keeps a practical `min-h-11` (~44 px) touch target. Regression: `RoomList.test.tsx` stacks/wraps/mobile-target test.
  2. **Risk "All" filter semantics**: `api/risks.ts` now sends `status=all` explicitly (backend defaults to `active`, so dropping the param would silently hide resolved risks); active/resolved/all tabs map to their own list query and filter switching never triggers a re-evaluation. Regression: `RiskPanel.test.tsx` status=all contract test.
  3. **Rectangle-room measured-state regression**: a RECTANGLE room with dimensions but **zero generated walls** (L=4.900 × W=5.000 × H=2.700) is recognized as measured — dimensions and floor/ceiling/wall totals (`24.500 m²` floor, `53.460 m²` walls, `19.800 m` perimeter) render from draft-dimensions, the "not measured / measure" notices do not appear, and wall generation produces exactly 4 walls; CUSTOM-shape rooms are unchanged. Regression: `ProjectWorkspace.test.tsx` Stage 7D.1 D3 test.
  4. **Reopen MULTI_CHOICE hydration / empty-option_keys regression**: after reopening a COMPLETED inspection the editable DRAFT answer state is rebuilt from the backend with the same canonical API→form mapper as a normal Draft load (BOOLEAN→`value_bool`, NUMBER→`value_number`, TEXT→`value_text`, SINGLE_CHOICE→`option_key`, MULTI_CHOICE→`option_keys[]`) — no stale COMPLETED representation leaks into the resumed form and no duplicate mapper exists (`seedAnswersFromDetail` is the single canonical API→form path used by both `loadExisting` and `handleReopen`). Deselecting the last defect chip never emits an empty `option_keys` (the last selected option stays), so the backend's `Question {key} requires option_keys` 422 can no longer be triggered from the resumed review flow; changed selections save the updated `option_keys`. Regression: 3 `InspectionFlow.test.tsx` Stage 7D.1 tests (hydration keeps option_keys, selection change persists updated option_keys, last-chip guard never sends empty option_keys).
- **Files**:
  - Changed: `frontend/src/components/InspectionFlow.tsx` (canonical `seedAnswersFromDetail` mapper; `handleReopen` refetches the inspection and rebuilds answer state; MULTI_CHOICE toggle last-chip guard), `frontend/src/components/InspectionFlow.test.tsx` (+3 regression tests), `frontend/src/components/RoomList.tsx` (D1 mobile card layout), `frontend/src/RoomList.test.tsx` (D1 test), `frontend/src/api/risks.ts` (D2 explicit `status=all`), `frontend/src/components/RiskPanel.test.tsx` (D2 test), `frontend/src/components/ProjectWorkspace.tsx` (D3 measured-state summary from draft dimensions), `frontend/src/ProjectWorkspace.test.tsx` (D3 test).
  - No backend schema/API change; backend MULTI_CHOICE contract verified live (empty `option_keys` is rejected; a correct reopen→full-answer PUT→complete round-trip succeeds).
- **Tests**:
  - Focused: `InspectionFlow.test.tsx` + `RiskPanel.test.tsx` + `RoomList.test.tsx` + `ProjectWorkspace.test.tsx` — **73 passed, 0 failed**.
  - Full frontend suite: **163 passed, 0 failed** (incl. locale-parity).
  - Full backend suite: **275 passed, 0 failed**.
  - TypeScript strict (`tsc --noEmit`): PASS; `vite build`: PASS; `git diff --check`: PASS; no migration changes.
- **Verification**:
  - Mobile room card: stacked layout, wrapped name, 3-col action grid on narrow viewport, ~44 px touch targets: PASS.
  - Risk filters: active→active, resolved→resolved, all→active+resolved with explicit `status=all`; filter switching never re-evaluates: PASS.
  - RECTANGLE room 4.900 × 5.000 × 2.700 with zero walls renders as measured (24.500 m² floor, 53.460 m² walls, 19.800 m perimeter); generation yields exactly 4 walls; CUSTOM unchanged: PASS.
  - Reopen flow: no `requires option_keys` error, answer state rebuilt from backend, last chip cannot produce empty `option_keys`, changed selection persists updated `option_keys`, no fetch loop / no stale COMPLETED / no navigation workaround: PASS.
- **Remaining**:
  - Final 7D manual acceptance walkthrough and owner sign-off — ongoing.
  - Infrastructure Docker Compose hotfix — still deferred, not started.

#### Execution Sub-Stage 7D.2: Final Manual-Acceptance Fixes and Two-Decimal Metric Policy (Completed)
- **Status**: Completed (owner-verified 2026-09-13) — Canonical Stage 7 is **COMPLETED**.
- **Date**: 2026-09-13
- **Scope** — the two manual-acceptance defects plus the final metric presentation policy:
  1. **Rectangle-room measured-state capture (Defect 1)**: partial RECTANGLE L/W/H submission (root cause of rooms silently losing their measured state) is now blocked with the localized message `rooms.dimensions_required` — a RECTANGLE room must be captured all-or-none; entering L/W/H immediately yields the measured state, the Generate 4 walls action produces exactly 4 walls, and a down-level GET refresh preserves dimensions. Regression: `RoomList.test.tsx` (partial-dimension blocks) + `ProjectWorkspace.test.tsx` `create→open→generate` end-to-end Stage 7D.2 test.
  2. **Immediate inspection question hydration (Defect 2)**: `beginInspection` fetches the exact checklist template via `fetchChecklistTemplate(created.template_id)` right after create — the list endpoint returns bare templates (`sections: []`), so a fresh inspection previously rendered 0/0 until leave-and-re-enter. Questions now render immediately with no reload. Regression: 2 `InspectionFlow.test.tsx` tests where the list mock returns a bare template.
  3. **Compound risk verification (Check C)**: `CRACK_RECURRENCE` + `BOARD_MOVEMENT_CRACK` both render independently for a GYPSUM_BOARD completed inspection with `cracks_present` + `board_movement`; compound severity HIGH, `blocks_finishing`, `warranty_exclusion_candidate`, source findings `{CRACK, BOARD_MOVEMENT}`. No risk-engine change was required. Regression: 2 new `backend/tests/test_risks.py` tests.
  4. **Permanent two-decimal metric display policy**: all user-facing construction measurements display exactly 2 decimals (5.000 → 5.00, 4.900 → 4.90, 2.700 → 2.70, 48.600 m² → 48.60 m², 3.000 mm → 3.00 mm, 13.515 m² → 13.52 m²). Implemented centrally in `formatMetric` (`frontend/src/utils/format.ts`, default `decimals = 2`) covering rooms, walls, openings, opening/segment/gross/deduction/net areas, floor/ceiling/perimeter, and area segments; two numeric-snapshot renderers that bypassed the formatter were wrapped (`RiskPanel.tsx` risk source numbers, `InspectionFlow.tsx` finding details); OpeningList live area preview `.toFixed(3)` → `.toFixed(2)`; all numeric inputs moved from `step="0.001"` to `step="0.01"` with existing `inputMode="decimal"` (RoomList ×4, ProjectWorkspace room-edit ×3, SurfaceList ×4, AreaSegmentList ×2, OpeningList ×2).
  - **Storage rule honored**: **no DB migration, no stored-value rewrite** — the backend retains its mm-compatible `Numeric(10,3)` precision and remains Decimal-authoritative (13.515 m² backend → 13.52 m² display only); domain calculations are unchanged.
- **Files**:
  - Changed (7D.2): `frontend/src/components/RoomList.tsx` (all-or-none RECTANGLE validation), `frontend/src/components/InspectionFlow.tsx` (template hydration after create), `frontend/src/locales/pl.json` + `ru.json` (`rooms.dimensions_required`), `backend/tests/test_risks.py` (2 compound-risk tests), `frontend/src/components/InspectionFlow.test.tsx` (2 hydration tests), `frontend/src/RoomList.test.tsx` (3 partial/block tests), `frontend/src/ProjectWorkspace.test.tsx` (end-to-end 7D.2 test).
  - Changed (metric policy): `frontend/src/utils/format.ts`, `frontend/src/components/RiskPanel.tsx`, `frontend/src/components/InspectionFlow.tsx`, `frontend/src/components/OpeningList.tsx`, `frontend/src/components/RoomList.tsx`, `frontend/src/components/ProjectWorkspace.tsx`, `frontend/src/components/SurfaceList.tsx`, `frontend/src/components/AreaSegmentList.tsx`.
  - Added: `frontend/src/utils/format.test.ts` (central two-decimal policy — 4 tests).
  - Updated tests to two-decimal expectations: `RoomList.test.tsx`, `SurfaceList.test.tsx`, `OpeningList.test.tsx`, `AreaSegmentList.test.tsx`, `RiskPanel.test.tsx`, `ProjectWorkspace.test.tsx`; added representative component tests (room 5.000 × 4.900 × 2.700 → 5.00 × 4.90 × 2.70; wall gross 13.515 m² → 13.52 m²). Mock fixtures keep backend 3-decimal values (storage unchanged).
  - No backend source/schema/API change; no migration.
- **Tests**:
  - Full frontend suite (`vitest`): **175 passed, 0 failed** (incl. locale-parity; +6 vs Stage 7D.1's 163).
  - Full backend suite (`pytest`): **277 passed, 0 failed** (+2 Stage 7D.2 compound-risk tests).
  - TypeScript strict (`tsc --noEmit`): PASS; `vite build`: PASS; `git diff --check`: PASS; single Alembic head `0012_create_risk_engine`.
- **Verification**:
  - Measured room displays exactly two decimals (room 5.000 × 4.900 × 2.700 → 5.00 × 4.90 × 2.70): PASS.
  - RECTANGLE create/edit uses `step="0.01"` inputs; partial dims blocked with a localized message; full L/W/H → measured → Generate 4 walls → exactly 4 walls: PASS.
  - Wall 13.515 m² → 13.52 m²; opening 1.800 m² → 1.80 m²; floor 30.090 m² → 30.09 m²; area segment 12.210 m² → 12.21 m²; risk numeric source 3.000 mm → 3.00 mm: PASS.
  - New inspection → Start → questions render immediately (no 0/0, no leave/re-enter): PASS.
  - Complete + evaluate risks; compound CRACK + BOARD_MOVEMENT both visible; HIGH_MOISTURE → CRITICAL → blocks_finishing; UNEVENNESS 2 mm no risk / 3 mm MEDIUM / 4 mm MEDIUM; Active/Resolved/All filters correct: PASS (unchanged domain rules).
  - Mobile PL/RU: single 390px column, wrapping, no new overflow; locale parity green: PASS.
  - Live stack: `docker compose up -d --build` → postgres/backend healthy, frontend running; `/api/health` 200; Alembic single head `0012_create_risk_engine`; `http://localhost:5173` 200 and renders without JS errors in headless Chromium. Infrastructure hotfix live: backend now runs with the `MOCK_TELEGRAM_AUTH=true` dev default (no bot token required) — no `docker compose down -v`, no data loss.
- **Deferred**:
  - Interactive authenticated click-through of the live Telegram flow remains a `DEFERRED_ENVIRONMENT` item (requires the owner's Telegram device / bot token); functional coverage is provided by the integration suites over the same source.
  - Stage 8 ("Co powiedzieć klientowi") — not started; requires explicit owner approval.

### Stage 8: "Co powiedzieć klientowi" (Field Communication Assistant)
- **Status**: **Completed 2026-09-13** — Execution Sub-Stages **8A (architecture / domain contract)**, **8A.1 (architecture correction)**, **8B (backend communication engine, commit `785b629`)**, **8C (mobile-first communication UI)**, **8C.1 (owner-acceptance blocker corrections)**, **8C.2 (numeric precision safety correction)**, **8D (integration / manual acceptance hardening)**, **8D.1 (owner acceptance correction — complete quality communication matrix for all canonical Q/S substrate combinations)** and **8E (final audit & merge readiness)** are all **Completed and owner-accepted 2026-09-13**. Owner re-tested every manual acceptance scenario (8C mobile communication UI, 8C.1 three blocker fixes, 8C.2 numeric precision correction, 8D/8D.1 communication cards render correctly with quality communication for canonical Q/S targets, GYPSUM_BOARD quality cards present, GYPSUM_PLASTER quality cards correct, mobile layout acceptable, Stage 8 integration behavior acceptable) and approved. Change sets were committed in order: **`feat(stage-8): complete mobile communication workflow`** (8C + 8C.1 + 8C.2), **`test(stage-8): verify integrated communication workflow`** (8D + 8D.1), **`docs(stage-8): record quality level technical reference roadmap`** (roadmap note D) and **`docs(stage-8): complete client communication stage`** (8E final audit — docs + README only); all pushed to `stage-8`. **8E final audit** verified: canonical scope ownership (communication only), minimal backend architecture (three entities, no second engine), identity/versioning law, complete quality matrix, mobile PL/RU UX, all four owner-found regressions, traceability, security/ownership, performance, roadmap consistency, full test suites, single migration head, and Docker runtime. **Canonical Stage 8 is Completed**; Stage 9 remains Pending.
- **Date**: 2026-09-13 (8A.1 correction)
- **Stage vision**: Concise, prepared, professional client-communication phrases (PL + RU) derived **deterministically** from factual context — Inspection → Established Facts → Risks → Co powiedzieć klientowi — later extended by Recommended Work / Estimate / Contract (Stage 11+). No LLM/AI/fuzzy/legal generation; stable content keys (`communication.<code>.phrase/.why`) with PL/RU parity; machine codes never shown to the user.
- **8A.1 correction 1 — UI context**: "Co powiedzieć klientowi" belongs to the context of a **specific COMPLETED inspection** and its factual/risk results. Canonical flow: `Inspection → Established Facts → Risks → Co powiedzieć klientowi`. The Stage 8C `CommunicationPanel` is **not** a global/room-level ProjectWorkspace panel; it is reachable from the completed-inspection results workflow, adjacent to / after `RiskPanel` (which it follows in the same inspection context). A future project-wide phrase overview may be added later and is **not** part of Stage 8 MVP.
- **8A.1 correction 2 — no second rule engine**: the Stage 8 selection space is **exact-key matching** over already-evaluated, already-materialized facts — active Risk codes, active `InspectionFinding` keys, `substrate`, `quality_target` — not a condition graph. The proposed `CommunicationRule` + `CommunicationRuleCondition` + operator evaluator (8A draft) is **removed**. Alternatives evaluated:
  - **A — Risk → phrase directly through the existing `RiskRule.communication_key`**: correct base behavior for risk-derived phrases and **used as the seed key**, but alone cannot express Stage 8's categories (8 semantic categories), finding-only phrases (no Risk), quality-level phrases, or the "why" corridor → insufficient alone.
  - **B — Risk → versioned `CommunicationPhrase` mapping, without another condition engine** (chosen): a single versioned reference-data table whose rows are selected by direct trigger-key equality (risk_code / finding_key / substrate / quality_level), plus a thin per-inspection materialized reference. Deterministic by construction, trivially auditable, versioned/historically stable, extensible by adding rows — no operators, no thresholds, no conjunctions, no parallel evaluation path that could diverge from Stage 7.
  - **C — independent `CommunicationRule` + conditions engine (rejected)**: duplicates Stage 7 machinery; a phrase trigger space needs no operator evaluator. Revisit only if a future stage demonstrates compound conditions — which would live in the canonical Stage 7 engine, not a new one.
  - **WHY NOT ANOTHER CONDITION ENGINE**: Stage 7 needs operators because a *risk* is a logical conjunction (multi-finding, `NUMBER_AT_LEAST` thresholds, substrate/target/quality membership). Stage 8 consumes facts **already derived by that engine** (an active Risk is itself the evaluated product) or raw keys (finding_key, substrate, quality_target). Selecting a phrase by exact key equality requires a lookup over versioned reference data, not a general evaluator; a second engine would recompute Stage 7 logic (unacceptable — no Stage 6/7 recomputation, traceability must read materialized state only) for zero behavioral gain.
- **8A.1 decision — Stage 7 `communication_key` role**: each `RiskRule`/materialized `Risk` snapshots `communication_key = risk.<slug>.communication` (one of five auto-derived i18n keys via `risk_service._rule_keys()`; 15 rules, full PL/RU parity; currently dormant in the Stage 7 UI which deliberately does not render it). Stage 8 **consumes, never duplicates** it: risk-derived phrase definitions declare a `seed_key = risk.<slug>.communication` and render the existing Stage 7 PL/RU phrase text (weighted by category/priority; severity/flag emphasis is rendered from Risk fields, not new text). The "why" corridor uses the risk's own snapshotted `explanation/consequence` keys + source `RiskFinding`/`InspectionFinding` value snapshots — never recomputing Stage 6/7 logic. New Stage 8 text exists only in a dedicated `communication.*` locale namespace; `risk.*` keys are **never modified**.
- **8A.1 finding-only strategy**: a simple deterministic mapping `finding_key (+ optional substrate) (+ optional quality_target) → phrase`, implemented as `communication_phrases` rows with finding_key/substrate/quality_level trigger columns; selection = best-match (specificity-descending exact-key lookup). No condition evaluator.
- **8A.1 quality strategy**: explicit deterministic reference data `substrate + quality_target → phrase` (category `QUALITY_EXPECTATION` / `GENERAL`), rows keyed by substrate + quality_level. Where the substrate's scale is not applicable (e.g., `PAINTED`/`OTHER`), the catalog provides `GENERAL` wording. No second engine; a generic evaluator is not justified by two-key equality.
- **8A.1 materialization strategy (compare / decision)**: a full transactional per-phrase recommendation row set with source-link table and value snapshots (Risk-style, option 1) is **rejected as over-engineered** — trigger values already live in Stage 6/7 snapshots, and phrases are not long-lived status entities. Purely recomputed/read-only output (option 0) is **rejected** — a later catalog release would silently change previously shown phrases, violating historical reproducibility. **Decision — hybrid minimal (option 2)**: (a) immutable, versioned **phrase definitions** (`communication_phrases`) deliver determinism, versioning, and historical stability of released content; (b) a **thin per-inspection application record** (`communication_applications`) freezes exactly which (phrase_code, phrase_version) applied at evaluation time, snapshotting the rendering keys, so previously shown phrases never drift. Persisted: phrase definitions + per-inspection applied references + key/version snapshots. **Not persisted**: no value snapshots (already in Stage 6/7), no source-link join table (trigger keys declared on the phrase row; the actual values are read from the already-persisted Risk/Finding rows for the "why" disclosure), no status-family lifecycle beyond `is_active`/`resolved_at` for re-evaluation reconciliation.
- **8A.1 minimal API (inspection-contextual — chosen)**: routes are nested under the inspection, mirroring the existing inspection sub-resource family (`/answers`, `/findings`, `/complete`) and the canonical mobile flow, with the inspection id in the path (no body ambiguity, one substrate/quality/target context per request):
  - `GET /api/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/communications?status=active|all` — materialized communication phrases for one COMPLETED inspection.
  - `POST /api/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/communications/evaluate` — idempotent evaluation/reconciliation (409 unless COMPLETED), returns applied phrases + trigger keys.
  - `GET /api/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/communications/{communication_id}` — single application detail incl. source context for the "why" disclosure (**traceability without frontend/backend Stage 6/7 recomputation**).
  - Rationale vs. room-level family (`/communications?inspection_id=`): inspection-contextual matches the MVP intent (phrases only exist inside a completed-inspection results workflow), removes the `inspection_id` ambiguity/optionality from the query, and keeps POST /evaluate naturally per-inspection; a future project-wide overview adds its own route later (not Stage 8 MVP). No generic CRUD.
- **8A.1 minimal 0013 migration plan (propose only — NOT created; 8B will implement)**: exactly **two** tables (no conditions table, no source-link table, no value snapshots):
  - `communication_phrases` — id UUID pk; code String(120); version Integer; active Boolean default true; category Enum(`communicationcategory`); priority Integer; trigger columns all nullable + indexed: `risk_code String(120)`, `finding_key String(120)`, `substrate Enum(substrate)`, `quality_level Enum(qualitylevel)`; `phrase_key String(255)`; `why_key String(255)`; `seed_key String(255)` nullable (Stage 7 reuse); created_at/updated_at. Unique `(code, version)`; index `(active, category)`.
  - `communication_applications` — id UUID pk; inspection_id FK→inspections.id ON DELETE CASCADE; `phrase_code String(120)`; `phrase_version Integer`; category; priority; `phrase_key`/`why_key`/`seed_key` snapshots; `is_active Boolean`; `resolved_at timestamptz`; position; created_at/updated_at. Unique `(inspection_id, phrase_code, phrase_version)`; index `(inspection_id, is_active)`.
  - Reversible upgrade/downgrade; single Alembic head `0013_create_communication_engine`; reference data materialized by service bootstrap (`build_baseline_communication_phrases`), never Alembic-seeded (ChecklistTemplate/RiskRule pattern).
- **8A mobile-first 8C target**: Completed Inspection → Established Facts → Risks → Co powiedzieć klientowi. Phrase cards are short and immediately usable on site: primary phrase visible immediately; category chip; placeholder copy action; "Why?" / source context progressively disclosed (risk explanation/consequence or finding values via the permanent two-decimal policy). No desktop-specific layouts.
- **Planned execution sub-stages (pending owner approval)**:
  - **8B — Backend communication engine (simplified per 8A.1)**: `backend/app/models/communication.py` (2 models — `CommunicationPhrase`, `CommunicationApplication`), `backend/app/domain/data/communication_phrases.py` (bootstrap reference data — deterministic trigger-keyed mappings incl. risk-derived seed_key reuse, finding-only, and substrate+quality rows), `backend/app/domain/services/communication_service.py` (direct-lookup evaluation + idempotent reconciliation; **no separate rules/condition module**), `backend/app/schemas/communication.py`, `backend/app/api/v1/endpoints/communications.py` (inspection-contextual routes), `backend/app/main.py` router registration, Alembic migration `0013_create_communication_engine`, `backend/tests/test_communications.py`. Gate: focused + full backend suites green; migration reversible; single head; no Stage 7/6 source changes.
  - **8C — Mobile-first communication UI**: `frontend/src/api/communications.ts`, `frontend/src/types/communication.ts`, `frontend/src/components/CommunicationPanel.tsx` (inspection-contextual, after RiskPanel), `communication.*` locale keys (PL/RU parity), Vitest. Gate: frontend suite + `tsc --noEmit` + `vite build` green; mobile regression at 320 / 390 / 412 px; locale parity green.
  - **8D — Stage 6/7 integration + manual acceptance**: wire `CommunicationPanel` into the completed-inspection results workflow in `ProjectWorkspace.tsx` (Established Facts → Risks → Co powiedzieć klientowi); traceability ("why this phrase") pass; owner manual acceptance; no domain-rule changes. Gate: full frontend + backend suites green; live Docker smoke green.
  - **8E — Final verification / docs / commit / merge readiness**: `git diff --check`; docs finalized (Stage 8 → **Completed** only on owner acceptance); one logical commit `feat(stage-8): ...`; push `stage-8`; pre-merge gate; `--no-ff` merge into `main` only after explicit owner approval.
- **Docker refresh rule (8B–8E)**: after tests pass each sub-stage runs `docker compose up -d --build`, then verifies `docker compose ps`, `/api/health`, `http://localhost:5173`, and `alembic current` (next head `0013_create_communication_engine`). `docker compose down -v` is **never** run unless the owner explicitly requests a destructive database reset.
- **8B execution status 2026-09-13**: **Completed (commit `785b629`)[footnote: see git log `feat(stage-8b)`] — implementation and verification passed, pushed to `stage-8`.** Semantics preserved from 8A/8A.1: exact-key selection over materialized facts only; no second rule engine; risk-derived phrases reuse `seed_key = risk.<slug>.communication`; finding-only phrases gated by `covered_finding_ids`; quality phrases exact `substrate + quality_target` with **no automatic generic fallback**. Identity law executed as a **refinement of the 8A.1 sketch**: the field sketch's `unique(inspection_id, phrase_code, phrase_version)` proved insufficient for stable context identity (one inspection may legitimately carry two applications of the same phrase_code at the same version for different factual contexts — e.g., a resolved risk signature and a newly active one), so applications are keyed by `unique(inspection_id, phrase_code, source_signature)` where `source_signature = SHA-256` over the sorted contributing finding UUIDs (reusing Stage 7 `compute_source_signature`), and context-only quality phrases use the constant hash of the empty set. Version preservation on reconciliation: a reused application keeps its UUID, phrase_version, and text-key snapshot from first materialization; disappeared applications are resolved (`is_active = False`, `resolved_at = now`), never deleted; later phrase versions apply only to newly created applications. Reversible migration `0013_create_communication_engine` (extract: `communication_phrases` + `communication_applications` + `communicationcategory` enum; predicate: substrate/qualitylevel enums left intact, owned by 0011) verified on real PostgreSQL: `upgrade 0012→0013`, `downgrade -1` (drops `communicationcategory`, preserves both 0011 enums), re-`upgrade head`. Verification results: focused `test_communications.py` + route-contract **39 passed** (including two Stage 8 §4 regression tests added in 8B verification — compounded `BOARD_MOVEMENT_CRACK` suppresses the `COMM_FIND_BOARD_MOVEMENT` echo while isolated `BOARD_MOVEMENT` keeps its distinct finding-only phrase); full backend suite **311 passed**; frontend vitest **175 passed**; `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` clean; single alembic head `0013_create_communication_engine (head)`; migration cycle on real PostgreSQL PASS (`upgrade head` → `downgrade -1` drops `communicationcategory` while `substrate`/`qualitylevel` enums and all Stage 6/7 tables survive → re-`upgrade head`); Docker `up -d --build` healthy (postgres/backend/frontend, `/api/health` ok, frontend :5173 ok, container `alembic current` = 0013 head); authenticated live smoke passed end-to-end (project → room → GYPSUM_BOARD inspection with `quality_target=Q2` → complete → risks evaluate 2 RISK (`BOARD_MOVEMENT_CRACK`, `CRACK_RECURRENCE`) → communications evaluate **4 phrases** (`COMM_RISK_BOARD_MOVEMENT_CRACK`, `COMM_RISK_CRACK_RECURRENCE`, `COMM_FIND_JOINT_GAP` below-threshold finding phrase, `COMM_QUALITY_GYPSUM_BOARD_Q2`) → list active/all/resolved = 4/4/0 → detail RISK traceability (risk_code + 2 source-finding snapshots) and QUALITY (GYPSUM_BOARD/Q2) → repeat evaluate → idempotent stable application UUIDs → unauthenticated list/evaluate 401). Stage 8 remains **In Progress** (NOT Completed); Stage 9 remains **Pending**; Stages 0–7 remain **Completed**.
- **8C execution status 2026-09-13**: **Implementation complete, verification passed, awaiting owner verification. NOT committed, NOT pushed, NOT started 8D** (per the explicit 8C mandate — no commit/push until the owner approves). Executed the 8A.1 mobile-first UI target: `CommunicationPanel` inside the **completed-inspection results** workflow (`InspectionFlow`), rendered strictly after `RiskPanel`; never rendered for DRAFT; list load is a plain query with default `status=active`, **no auto-evaluate on page load** (evaluation only on explicit tap). Frontend does **not** reproduce any backend selection logic (no risk inference, finding matching, version selection, or recommendation derivation — it consumes only the backend-materialized applications and their snapshot keys). Files: added `frontend/src/components/CommunicationPanel.tsx`, `frontend/src/types/communication.ts`, `frontend/src/api/communications.ts`, `frontend/src/utils/clipboard.ts`, `frontend/src/utils/clipboard.test.ts`, `frontend/src/api/communications.test.ts`, `frontend/src/components/CommunicationPanel.test.tsx`; edited `frontend/src/components/InspectionFlow.tsx` (+ its test) and `frontend/src/locales/pl.json`/`ru.json` (full `communication.*` namespace, PL/RU parity) and `frontend/src/locales/parity.test.ts`. UI behavior: phrase cards show only localization-resolved text (`phrase_key`/`why_key`/seed keys resolved via locale dictionaries; unresolved → neutral localized fallback, **never a raw key**; `phrase_code`/`risk_code`/`finding_key`/machine enums/UUIDs never rendered); category chip localized for all 8 categories with subtle emphasis scoped to decision/agreement; "Dlaczego?"/"Почему?" disclosure **lazy-fetches detail exactly once per card, cached**, with loading/error states inside the disclosure; RISK source renders localized risk title + severity + source-finding rows with value snapshots; FINDING source renders localized label + snapshot (numeric values via the permanent two-decimal policy — e.g. `3.000`→`3.00 mm`, `13.515`→`13.52 mm`); QUALITY source renders substrate + quality target ("Podłoże:"/"Klasa jakości:"); copy uses `navigator.clipboard.writeText` with `textarea`/`execCommand` fallback (no external packages, never throws) + visible success/failure localization + bounded 2.5s timer with unmount cleanup; Active/Resolved/All filters (default Active) are pure list queries and never re-evaluate; resolved cards subdued but readable ("Zakończono …"). Mobile: single-column list, `flex-col`, `flex-wrap` chip rows, `min-h-11`/`min-h-10` touch targets, no horizontal scroll at 320/390/412 px. Verification results: frontend vitest **199 passed** (18 files); `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` clean; backend full regression **311 passed** (unchanged — 8C touches no backend source); Docker `docker compose up -d --build` healthy (postgres/backend/frontend, `/api/health` ok, container `alembic current` = 0013 head, `http://localhost:5173` HTTP 200); authenticated live API smoke of the completed flow PASS — login → project → room → COMPLETED GYPSUM_BOARD Q2 inspection → communications evaluate → 4 applications → list active/all = 4 → detail for all three source kinds (RISK `BOARD_MOVEMENT_CRACK` HIGH + `CRACK_RECURRENCE` MEDIUM, FINDING `COMM_FIND_JOINT_GAP` with `1.500` → `1.50 mm`, QUALITY `COMM_QUALITY_GYPSUM_BOARD_Q2`) — traceability strings and snapshot formatting rendered exactly as the component maps them. **Honest caveat**: a browser / Telegram-device interactive UI click-through was **NOT** performed this session — recorded as `DEFERRED_ENVIRONMENT` (requires the owner's Telegram device / manual walkthrough); functional coverage is provided by the 13 `CommunicationPanel` Vitest cases + 6 API-client contract cases + InspectionFlow regression over the same source. Stage 8 remains **In Progress**; Stage **9 Pending**.

- **8C.2 numeric precision safety correction 2026-09-13**: The 8C.1 report's `sanitizeNumber()` silently **CAPPED** over-precision NUMBER answers to 3 decimal places (`4.7612` → `4.761`), silently altering user-entered measurement data — violating the documented "nothing rounded/changed pre-submission" rule. **Fix (root cause = silent truncation)**: truncation removed. `normalizeNumberInput()` now only trims whitespace and converts `,`→`.` (`4,9`→`4.9`) and never changes digits; `isValidNumberInput()` enforces the backend `Decimal(10,3)` contract as ≤3 fractional digits; `prepareForSubmit()` validates **synchronously, before the saving spinner toggles**, and a violation **blocks save/complete with NO API call**, surfacing the localized `inspections.error_number_precision` ("Maksymalnie 3 miejsca po przecinku." / "Максимум 3 знака после запятой.") both inline under the input (red border) and in the alert banner; the typed value is preserved exactly (never rewritten to fit) and correcting it clears the error immediately. Valid values (`4`, `4.9`, `4.76`, `3.125`) pass unchanged; cleared NUMBER fields remain unanswered (absent rows) per the 8C.1 contract; `saving` now wraps only the real network PUT so a blocked submission never leaves the button disabled. Kept unchanged: `step="any"` + `inputMode="decimal"`, backend `Numeric(10,3)`, 2-decimal display formatting. Files: `frontend/src/components/InspectionFlow.tsx` (helpers, `numberErrors` state, blur-handler `handleBlurNumber`, `prepareAnswersForSubmit`/`prepareForSubmit`, per-field error under NUMBER inputs), `frontend/src/locales/pl.json`/`ru.json` (`inspections.error_number_precision`, PL/RU parity). Regression tests (rewrote the 8C.1 "capped to `4.761`" test into the correction contract): `InspectionFlow.test.tsx` — `4/4.9/4.76/3.125` accepted untouched (`it.each`); `4,9` preserved verbatim while editing and normalized to `4.9` on blur and in the PUT payload; `4.7612` → visible localized error, value preserved as typed (never transformed to `4.761`), Save Draft blocked (no PUT), completion blocked (no PUT / no complete), and correction to `4.761` clears the error and unblocks submission. Verification: focused frontend **33 passed**; full frontend vitest **213 passed (19 files)**; full backend pytest **314 passed** (8C.2 touches no backend source); `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` clean; Docker `docker compose up -d --build` healthy (`/api/health` 200, frontend :5173 200, `alembic current` = `0013_create_communication_engine (head)`). **NOT committed / NOT pushed / 8D not started** — the owner re-tests 8C.1 + 8C.2 before any commit. Root causes were diagnosed from live evidence (Chromium headless validity check, live API probes), fixed at the root, and locked with regression tests; no Stage 6/7/8 architecture was changed.
- **8C FINALIZATION — owner-verified commit + push 2026-09-13**: the owner manually re-tested and **accepted 8C (mobile communication UI), 8C.1 (three blocker fixes), and 8C.2 (numeric precision correction)** — all manual acceptance scenarios PASS (including scenarios A–E above). **Execution sub-stages 8A / 8A.1 / 8B / 8C / 8C.1 / 8C.2 recorded Completed; canonical Stage 8 remains In Progress; 8D and 8E remain pending explicit owner approval; Stage 9 remains Pending.** Full final verification re-run on branch `stage-8`: frontend vitest **213 passed (19 files)**; backend pytest **314 passed**; `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` clean; Docker `docker compose up -d --build` healthy (postgres/backend/frontend, `/api/health` `{"status":"ok"}`, frontend :5173 HTTP 200, container `alembic current` = `0013_create_communication_engine (head)`). The full verified 8C + 8C.1 + 8C.2 change set was committed as a single logical commit **`feat(stage-8): complete mobile communication workflow`** and pushed to `origin/stage-8`; working tree clean; `main` untouched. HTML `type="number"` step-base algorithm — valid values = `base + k·step` where `base = min` (`0.001`) — combined `min="0.001"` with `step="0.01"` so the lattice became `0.001 + 0.01k`; ordinary room dimensions `6 / 4.9 / 4.76 / 4 / 3` all fell off-lattice and native browser validation produced exactly the owner's message ("Please enter a valid value. The two nearest valid values are 5.991 and 6.001." for `6`, `4.891/4.901` for `4.9`, `4.751/4.761` for `4.76`). **Fix**: every decimal measurement input now uses `step="any"` with `min="0.001"` and `inputMode="decimal"` — `RoomList` (length/width/height/custom-height), `ProjectWorkspace`, `SurfaceList`, `OpeningList` (width/height; the integer `quantity` deliberately keeps `step="1"`/`inputMode="numeric"`), `AreaSegmentList` (width/length). Chromium headless repro: OLD config → `validity.stepMismatch=true` for all five values with the exact owner message; NEW config → all `validity.valid=true`.
  - **Input vs display precision policy (permanent)**: INPUT is unrestricted free-form natural decimals (no forced 2dp); STORAGE is authoritative DB `Numeric(10,3)` (backend Decimal `decimal_places=3, max_digits=10`) and the read wire is always the fixed 3dp form (`0` → `0.000`, `3.5` → `3.500`, `3.25` → `3.250`, `3.125` → `3.125`); DISPLAY keeps the existing formatting policy (e.g. `3.13` / `3.13 mm`). Backend precision was NOT reduced and nothing is rounded before submission.
  - **Blocker B — MULTI_CHOICE cannot deselect** (root cause): the frontend kept a guard that refused to remove the last selected chip, and the backend `_validate_answer_payload` rejected `not payload.option_keys` (both `None` and `[]`), so no explicit "none selected" state existed. **Fix**: the guard was removed — tapping a chip toggles it (select adds, deselect removes; the last chip deselects to an explicit `option_keys: []`); the backend guard was narrowed to reject only `payload.option_keys is None`. **Canonical empty-state contract**: unanswered = absent row / `option_keys: null`; explicitly answered "none selected" = `option_keys: []` (persisted as-is, materializes zero findings because `build_finding_specs` iterates only selected keys). No sentinel option was invented; the backend persisted `[]` already at the schema level.
  - **Blocker C — 422 after editing answers (release blocker)** (root cause, live-confirmed): the NUMBER answer input serialized its raw string verbatim, so an empty/cleared value, a `,` comma decimal, or a >3dp value reached Pydantic `Decimal(decimal_places=3)` and produced a **422 whose `detail` is a LIST**; the frontend `http.ts` only surfaced STRING `detail`, so users saw the generic "Request failed (422)" with the 422 body hidden. `422` detail samples captured live: `[{"type":"decimal_parsing","msg":"Input should be a valid decimal"}]` for `value_number:''` and `'4,9'`, and `[{"type":"decimal_max_places","msg":"Decimal input should have no more than 3 decimal places"}]` for `'4.7612'` (both are LIST details; a STRING detail like "Question … requires value_number" from the service layer was never the "Request failed (422)" source). **Fix**: `sanitizeNumber()` on blur (trim, `,`→`.`, cap at 3dp, empty→null); answers whose only fields are null are dropped from the PUT payload (absent row = unanswered — a `value_number:null` row would itself 422); `http.ts` now throws an `ApiError` carrying `status` so a 422 renders the localized `inspections.error_validation` ("Niepoprawne dane. Sprawdź odpowiedzi.") instead of "Request failed (422)". Live completion contract (docker-backed API, CONCRETE template): **5× create → answer → complete → reopen → edit every answer type (BOOLEAN/NUMBER/SINGLE_CHOICE/MULTI_CHOICE/TEXT) → complete, at NUMBER values `0 / 3 / 3.5 / 3.25 / 3.125` → 16 HTTP 200, zero 422, persisted wire `0.000 / 3.000 / 3.500 / 3.250 / 3.125`**; the cycle-4 deselect-all MULTI pass persisted `option_keys: []` and its active findings exclude every deselected defect finding (`DELAMINATION`/`BLOW_HOLES`) while keeping `CRACK`/`UNEVENNESS`.
  - **Regression tests locking all three blockers**: backend `test_inspections.py` +3 (explicit `[]` accepted & persisted; `null` option_keys rejected 422; reopen → deselect-all → recomplete excludes deselected findings) → focused **39 passed**; frontend `InspectionFlow.test.tsx` +8 (NUMBER 4dp capped to `4.761`, natural `3.125` untouched, cleared NUMBER dropped from payload, 422 → localized message, chip toggle `[]→[A]→[]` and `[A]→[A,B]→[B]→[]` ending in explicit `[]`, reopen last-chip deselect → `option_keys: []`, reopen hydration keeps selection, `step` regression) and NEW `RoomList.test.tsx` (2 tests: `step="any"`/`min="0.001"`/`inputMode="decimal"` on dimensions; 6/4.9/4.76 submitted as 6/4.9/4.76) → full frontend **207 passed (19 files)**; full backend **314 passed**; `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` clean.
  - **Downstream (Stage 7 + Stage 8)**: live recompleted inspection → risk evaluate **200 (7 items)** and communication evaluate **200 (7 items)**; `CommunicationPanel` untouched.
  - **Remaining for the owner before 8D — RESOLVED 2026-09-13**: the owner re-tested every scenario — A (room dims `6/4/3`, then `4.9` / `4.76`), B (MULTI_CHOICE tap select/deselect incl. last chip), C (complete → reopen → edit → complete, twice, no 422), D (risks + "Co powiedzieć klientowi" still evaluate after recompletion), and E (8C.2: NUMBER input accepts `4` / `4.9` / `4.76` / `3.125`, normalizes `4,9`→`4.9`, and on `4.7612` shows the localized "Maksymalnie 3 miejsca po przecinku." error while preserving the typed value and blocking save/complete — NO silent truncation to `4.761`) — and **accepted all of 8C, 8C.1, 8C.2**. On approval the owner authorized the commit & push; 8C + 8C.1 + 8C.2 were committed as `feat(stage-8): complete mobile communication workflow` and pushed to `stage-8`.

### 8C remaining before 8D:**owner** re-tests the three blocker scenarios (A: room dimensions 6/4/3 and 4.9/4.76; B: MULTI_CHOICE select/deselect incl. the last chip; C: complete → reopen → edit → complete twice with no 422) plus risk/communication evaluation after recompletion, on a real device / browser (390/412 px, wrapping, touch, PL/RU long-label regressions); on approval the owner reviews the diff and authorizes the commit & push (8C is held uncommitted by explicit mandate).

### 8D execution status 2026-09-13 — integration contract implementation + verification COMPLETE; owner manual acceptance + commit/push PENDING (implementation held UNCOMMITTED, as with 8C).
Added the Stage 6→7→8 cross-layer integration contract **`backend/tests/test_communications_integration.py`** (currently untracked — the only repo change for 8D; **no domain-rule / backend-source / frontend-source changes**). One canonical COMPLETED GYPSUM_BOARD/Q2 inspection drives `InspectionFinding (Stage 6) → Risk (Stage 7) → CommunicationApplication (Stage 8)`, then exercises **two reopen / edit / recomplete cycles** to prove joint lifecycle consistency across all three layers: obsolete rows resolve (`is_active = False`, `resolved_at` set) in every layer, new rows materialize, the same factual context reuses the same UUIDs (`source_signature` identity — e.g. `COMM_RISK_CRACK_RECURRENCE` keeps its original application UUID from pass 1 through cycle 1 and into the resolved slice of cycle 2), historical rows are never physically deleted, `active / resolved / all` filters return consistent slices (`all == active + resolved`), and **traceability detail explains every source kind** without any layer recomputing another layer's responsibility (RISK: `risk_code` + severity + `source_findings` value snapshots; FINDING: label + `value_snapshot` + `is_active`; QUALITY: `substrate` + `quality_level`). The canonical test also locks the **layer-ordering invariant**: before Stage 7 risk evaluation **no RISK-kinded phrase can exist** (only finding-only `COMM_FIND_*` + quality phrases are materialized), and once `BOARD_MOVEMENT_CRACK` risk materializes the compounded suppression displaces the `COMM_FIND_BOARD_MOVEMENT` echo — proving the engine consumes materialized risk rows, never recomputing Stage 6/7 logic. Multi-tenant + auth are locked across all three layer endpoints (401 unauthenticated; 404 foreign-owner, including the communication resolve/detail route). Frontend side of 8D was already delivered in 8C: `InspectionFlow` renders `CommunicationPanel` strictly after `RiskPanel` for COMPLETED inspections only, never for DRAFT (regression-locked in `InspectionFlow.test.tsx`). **Verification results**: focused 8D integration test **6 passed**; full backend pytest **320 passed** (was 314; the +6 are the 8D file's tests); full frontend vitest **213 passed (19 files)** (unchanged — 8D touches no frontend source); `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` clean; Docker `docker compose up -d --build` healthy (postgres/backend healthy, `/api/health` `{"status":"ok"}`, frontend :5173 HTTP 200, container `alembic current` = `0013_create_communication_engine (head)`). **Honest caveat**: the owner-facing 8D manual acceptance — interactive browser / Telegram-device click-through of the completed-flow "Co powiedzieć klientowi" panel and its "Dlaczego?"/"Почему?" traceability disclosure — remains `DEFERRED_ENVIRONMENT` pending the owner's device walkthrough (identical caveat to 8C); functional coverage is provided by the 6 backend integration tests + the 13 `CommunicationPanel` Vitest cases + `InspectionFlow` regression. Stage 8 remains **In Progress** (NOT Completed); Stage 9 remains **Pending**; Stages 0–7 remain **Completed**.

### 8D.1 execution status 2026-09-13 — owner acceptance correction: complete quality communication matrix (implementation + verification COMPLETE; owner retest + commit/push PENDING, held UNCOMMITTED).
Owner acceptance found a coverage gap: `QUALITY_EXPECTATION` communication existed only for a representative subset (`GYPSUM_PLASTER S3`, `GYPSUM_BOARD Q2`, `CONCRETE S4`, `PAINTED S2`) — e.g. `GYPSUM_BOARD + Q3` had no quality card. **Root cause**: the Stage 8 quality catalog was seeded with a subset of the Stage 6 substrate/quality scale matrix, and the engine selects by exact `(substrate, quality_level)` equality, so any combination absent from the catalog produced no QUALITY source. **Fix (no new engine, no migration, no Stage 6 semantics change)**: the catalog now ships the **complete canonical matrix** as exact deterministic mappings — `GYPSUM_BOARD Q1–Q4`, `CONCRETE S1–S4`, `GYPSUM_PLASTER S1–S4`, `CEMENT_LIME_PLASTER S1–S4` (16 combinations; 13 new phrase codes at `version=1`, 3 retained unchanged — released definitions are never mutated). `PAINTED`/`OTHER` get no manufactured scale (Stage 6 imposes no family for them): the released `PAINTED S2` phrase stays, `OTHER` stays phrase-less. Files: `backend/app/domain/data/communication_phrases.py` (+13 `_quality` entries), `frontend/src/locales/pl.json` + `ru.json` (+13 `comm_quality_*.{phrase,why}` each, PL/RU parity), `frontend/src/locales/parity.test.ts` (slug list +13), `backend/tests/test_communications.py` (new `TestCompleteQualityMatrix`: 16 parameterized full-matrix cases — each valid combination yields **exactly one** `QUALITY_EXPECTATION` application, no duplicates, re-evaluation idempotent with stable UUID; 4 cross-scale rejection cases — `GYPSUM_BOARD+S3`, `GYPSUM_PLASTER+Q3`, `CONCRETE+Q2`, `CEMENT_LIME_PLASTER+Q1` → 422 at creation, Stage 6 validation **not** weakened, so no QUALITY application can ever materialize; and `test_no_automatic_generic_quality_fallback` repointed from the now-covered `CONCRETE S3` to `PAINTED S1` — Stage-6-valid yet catalog-absent — proving the engine still never invents a generic phrase). Versioning: new codes are `version=1` bootstrap rows (idempotent `_ensure_bootstrapped`), existing `(code, version)` rows untouched, existing `CommunicationApplication` history stays stable. **Verification**: focused `test_communications.py` + 8D integration **60 passed**; full backend pytest **340 passed** (was 320; +20 = the 16+4 parameterized cases); full frontend vitest **213 passed (19 files)**; `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` clean; Docker `docker compose up -d --build` healthy (postgres/backend healthy, `/api/health` `{"status":"ok"}`, frontend :5173 HTTP 200, container `alembic current` = `0013_create_communication_engine (head)`); **live authenticated API reproduction of the owner case PASS** — GYPSUM_BOARD + Q3 completed inspection → `communications/evaluate` → exactly one QUALITY card `COMM_QUALITY_GYPSUM_BOARD_Q3` (category `QUALITY_EXPECTATION`, source `{kind: QUALITY, substrate: GYPSUM_BOARD, quality_level: Q3}`), and GYPSUM_PLASTER + S3 regression still returns `COMM_QUALITY_GYPSUM_PLASTER_S3`. `KEY` resolution intact (phrase/why dotted keys shipped in both locales; raw backend keys never render — `parity` + `CommunicationPanel` behavior unchanged). No commit / no push / 8E not started / `main` untouched. Stage 8 remains **In Progress**; 8D + 8D.1 await **final owner acceptance**; Stage 9 remains **Pending**.

### 8D / 8D.1 FINALIZATION — owner-accepted + committed + pushed 2026-09-13
The owner manually reviewed and **accepted Stage 8D / 8D.1**: communication cards render correctly; quality communication appears for canonical Q/S targets; GYPSUM_BOARD quality cards are now present; GYPSUM_PLASTER quality cards remain correct; mobile layout acceptable; Stage 8 integration behavior acceptable. On approval the owner authorized the commit and push; the full 8D + 8D.1 change set was committed as **`test(stage-8): verify integrated communication workflow`** and pushed to `origin/stage-8`. **Canonical Stage 8 remains In Progress** (final closure / merge readiness = 8E remains Pending); Stage 9 remains Pending. The following owner-preserved roadmap requirements are recorded for future stages — **do NOT implement now**.

#### ROADMAP NOTE A — PER-SURFACE INSPECTION ENTRY (future stage)
Every physical surface must have its own inspection entry point: **WALL → wall inspection**, **FLOOR → floor inspection**, **CEILING → ceiling inspection**. The inspection remains attached to that exact surface/plane context.

#### ROADMAP NOTE B — STAGE 5G OPTIONS UI (deferred Stage 5G)
The deferred Stage 5G progressive-disclosure surface-card cleanup must eventually place surface actions under **"Opcje"** / equivalent. For WALL, future disclosed actions may include: Badanie ściany; Zdjęcia / defekty; + Drzwi; + Okno; + Inny otwór; Zarządzaj otworami; Edytuj; Archive where applicable. For FLOOR / CEILING: Badanie podłogi / Badanie sufitu; Zdjęcia / defekty; edit/other applicable actions.

#### ROADMAP NOTE C — STAGE 14 PHOTO FIXATION
Stage 14 must attach photos to the exact physical target: Project / Room / WALL / FLOOR / CEILING. Surface photo workflow must support: camera/gallery; multiple photos; note/caption; timestamp; thumbnail; defect annotation directly on photo; normalized x/y annotation coordinates; category; comment; severity/status where Stage 14 design defines them. Future chain: Photo → PhotoAnnotation → Inspection Finding → Risk → Communication → Recommended Work → Estimate → PDF / protocol. **No photo storage or annotation is implemented in Stage 8.**

#### ROADMAP NOTE D — QUALITY LEVEL TECHNICAL REFERENCE (future technical / knowledge base)
Future technical / knowledge-base work must provide detailed reference content for **GYPSUM_BOARD: Q1 / Q2 / Q3 / Q4** and **CONCRETE / GYPSUM_PLASTER / CEMENT_LIME_PLASTER: S1 / S2 / S3 / S4**. For each level record: intended / expected finish result; typical preparation scope; visual expectations; acceptable / unacceptable defects; inspection / acceptance conditions; contractor-facing client explanation; limitations / what the level does **NOT** guarantee; applicable Polish / European technical references where available. Stage 8 communication phrases remain concise client-facing summaries and **must not be treated as the full technical definition**. This future reference content should be reusable by: Inspection; Communication; Estimate; Contracts / protocols; Legal / technical knowledge base; PDF reports. **No technical reference content is implemented in Stage 8.**

### 8E execution status 2026-09-13 — final audit & merge readiness (COMPLETE — Stage 8 CLOSED)
Audit-only closure (no new functionality, no refactors, no migrations). All gates **PASS**:
1. **Scope**: Stage 8 owns communication recommendations only — no pricing, estimate line items, recommended work entities, contracts, warranty/legal conclusions, photo storage, PDF generation, or AI/LLM anywhere in the Stage 8 change set.
2. **Backend architecture**: exactly three entities — `CommunicationPhrase` (`communication_phrases`), `CommunicationApplication` (`communication_applications`), `CommunicationCategory` (`communicationcategory` enum); no second rules engine, no `CommunicationRuleCondition`, no source-link/value-snapshot duplication (single shared `compute_source_signature`, `seed_key` points at Stage 7 content); deterministic exact-key selection only; the engine consumes materialized active `Risk` / `InspectionFinding` rows + inspection substrate/quality target and never re-runs Stage 7 (locked by the integration test layer-ordering invariant).
3. **Identity / versioning**: identity law `(inspection_id, phrase_code, source_signature)` — stable UUID on unchanged context, resolved-never-deleted on obsolete, historical-row reuse on reappearing context, phrase-v1 snapshots never silently mutated to v2, new contexts use the latest active version (all four laws locked by `TestIdentityReconciliation` + the 8D integration file).
4. **Quality matrix**: complete canonical coverage `GYPSUM_BOARD Q1–Q4`, `CONCRETE S1–S4`, `GYPSUM_PLASTER S1–S4`, `CEMENT_LIME_PLASTER S1–S4`; no cross-scale leakage; Stage 6 `assert_quality_scale_valid` remains the source of truth (422 on cross-scale); `PAINTED`/`OTHER` get no manufactured scales; released `PAINTED S2` preserved and documented.
5. **Frontend UX**: Completed Inspection → findings → `RiskPanel` → `CommunicationPanel` → Reopen; panel hidden for DRAFT; explicit evaluate only (no auto-evaluate on load); lazy "Why?" detail (fetched once per card, cached); copy action with localized feedback; active/resolved/all filters; PL/RU parity; no machine keys/codes rendered; mobile-first 320–480 with ~44 px targets, wrapping, no desktop-specific layout.
6. **Owner-found regressions A–D**: numeric inputs accept `4` / `4.9` / `4.76` / `3.125` with `4,9` normalized and no step-lattice bug (`step="any"`); MULTI_CHOICE deselect incl. last → explicit `[]` persists; complete → reopen → edit → complete with no 422; `>3` decimals → localized validation error, value preserved, no API submit until corrected (all locked by dedicated 8C.1/8C.2 tests).
7. **Traceability**: "Why?" explains RISK (materialized risk + Stage 7 source-finding snapshots), FINDING (label/value snapshots), QUALITY (substrate + target) with no recomputation and no raw `risk_code` / `finding_key` / `source_kind` / `phrase_code` / UUID in UI.
8. **Security / ownership**: unauthenticated → 401 across findings/risk/communication layers; foreign project/room/inspection/risk/communication → uniform 404, no existence leaks.
9. **Performance**: risk list grouped, communication list flat (bounded queries), detail fetched lazily, no per-card source fetch on initial render, evaluate bounded — no N+1.
10. **Roadmap consistency**: canonical Stage 0–20 order intact (no numbering drift); preserved notes confirmed — 5F reveals/ościeża, 5G "Opcje" progressive disclosure, per-surface inspection entry (NOTE A), Stage 14 photos + defect annotation (NOTE C), full chain `Photo → PhotoAnnotation → Inspection Finding → Risk → Communication → Recommended Work → Estimate → PDF / protocol` (already includes Communication — no normalization needed), quality-level technical reference (NOTE D).
**Verification**: focused communication + integration **60 passed**; full backend pytest **340 passed**; full frontend Vitest **213 passed (19 files)**; `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` clean; Alembic single head + running `current` = `0013_create_communication_engine (head)` (no migration created in 8E; upgrade/downgrade cycle proven in 8B remains documented); Docker runtime healthy — postgres/backend healthy, `/api/health` `{"status":"ok"}`, frontend :5173 HTTP 200. Documentation finalized: **Stage 8 → Completed 2026-09-13** (owner verified), all sub-stages 8A–8E Completed, roadmap notes A–D preserved, Stage 9 remains **Pending**; README updated to the repo convention (Stages 0–8 Completed, Stages 9–20 pending). Committed as **`docs(stage-8): complete client communication stage`** (docs + README only) and pushed to `stage-8`. NOT merged into `main` — the owner-authorized merge command is reserved for owner approval.

### Stage 9: Editable Price Book / Cennik
- **Status**: **Completed 2026-09-15 (owner accepted; merged to `main` as `96d0518`)** — execution sub-stages 9A (architecture & domain contract), 9B (backend domain, migration & seed infrastructure), 9C (public API + ownership tests) Completed 2026-09-13; 9D (mobile-first price book UI) Completed 2026-09-13 (owner accepted); 9D.1 (mobile shell + Telegram dark theme UX correction) Completed 2026-09-14 (owner accepted; committed `c4cc6b6`); 9E.1 (market price reference & sources architecture) and 9E.2 (research catalog structure) Completed 2026-09-13 (docs-only); 9E.3A–9E.3E (Kraków market research — Batches A–E) Completed 2026-09-13/14 (evidence files only, no seeds); 9E.4 (normalization/review — all 51 items, decisions assigned, owner-decision groups defined) Completed 2026-09-14 (docs-only, no seeds); **9E.5 (owner approval) Completed 2026-09-14 (OWNER_APPROVED — all 7 §16.7 decision groups approved; final implementation-ready catalog: 44 candidates, 28 MARKET_SUPPORTED / 16 OWN_PRICE, 7 dropped/merged)**; **9E.6A (price market evidence backend foundation) Completed 2026-09-14 (committed `31540af`)**; **9E.6B (mobile price market evidence UI) Implemented 2026-09-14 (compact read-only evidence presentation on Price Book cards; 44 approved catalog rows NOT loaded — deferred per owner instruction)**; **9E.7 (load approved 44-row catalog + market evidence + nullable price foundation) Completed 2026-09-15 (committed `097e46c`)**; **9E.7.1 (Price Book add/edit form visibility regression) Implemented 2026-09-15 (committed `f38cd13`)**; **9E.8 (mobile Price Book UX cleanup) Implemented 2026-09-15 (committed `a948f68`, `c82c6ea`, `d1688e1`; owner accepted)**; 9F (final gate) **NOT RUN as a separate execution** — Stage 9 final acceptance completed from accumulated verification evidence and owner acceptance — **Stage 9 COMPLETE**. Stage 9 answers the product question **"What is our current unit price?"** with an owner-editable contractor price catalog (Cennik). **Stage 9 is not an estimate**: canonical Stage 10 (Kosztorys) consumes Price Book prices and is out of Stage 9 scope; no Project/room/inspection/estimate entities are created in Stage 9. Merged into `main` as `96d0518` (2026-09-15); Stage 10 is now In Progress (10A COMPLETE, 10B NOT STARTED); Stages 11–20 remain Pending.
- **Date**: 2026-09-13 (9A)

#### 9A — architecture & domain contract (decision record)

**1. PriceItem responsibility.** A `PriceItem` is one reference-price row: stable semantic `code`, name (`name_key` for seeded / `display_name` for user-created), `category`, `unit`, `price` (Decimal PLN), `currency` (ISO 4217-style code, PLN-only in MVP), optional `quality_level`, `price_scope` (LABOR default), `is_archived`, `created_at` / `updated_at`. It answers "what do we charge per unit for this line of work?" It computes nothing, belongs to no Project, and models no scope-of-work.

**2. Price Book vs Estimate boundary.** Price Book = owner-editable reference data. Stage 10 Estimate computes lines (unit × quantity by surface/substrate/quality tier) and consumes Price Book rows; it must persist a price snapshot at line-creation time (see §9). Stage 9 owns only catalog management; no estimate line items, no recommended-work entities, no contracts.

**3. Units — `PriceUnit` enum M2 / LM / PCS / HOUR / DAY / FLAT.**
- `M2` — metr kwadratowy (m²) — surface work (painting, skimming, preparation).
- `LM` — metr bieżący (mb) — edge / reveal-work lines, friezes.
- `PCS` — sztuka (szt.) — discrete items.
- `HOUR` — roboczogodzina (r-g).
- `DAY` — dniówka (r-d).
- `FLAT` — ryczałt / fixed-price unit (a whole-scope lump-sum line).
**M³ (M3) is explicitly NOT in the enum** — no finishing-trade line needs volumetric pricing; adding it for theoretical completeness would widen the enum without a real line item. Unit validation is enum-level on the backend; unit↔category pairing is deliberately **not** restricted (a hard matrix would block legitimate combinations).

**4. Categories — `PriceCategory` enum, 11 members, substrate-free.** Normalized canonical set covering concrete / gypsum / cement-lime / G-K / painting / glass-fiber / microcement / venetian / preparation / reveals without encoding any substrate into a category name:
- `PREPARATION` — przygotowanie podłoża (gruntowanie, czyszczenie, naprawy).
- `SKIM_COAT` — szpachlowanie / gładź.
- `PLASTER` — tynki (gipsowe, cementowo-wapienne, maszynowe).
- `DRYWALL` — sucha zabudowa / płyty G-K.
- `PAINTING` — malowanie / gruntowanie powłok.
- `GLASS_FIBER` — welon szklany / tkaniny przeciwspękaniowe.
- `MICROCEMENT` — mikrocement (ściany, posadzki, strefy mokre).
- `DECORATIVE` — stiuk wenecki / tynki dekoracyjne.
- `REVEAL` — ościeża / otwory okienne i drzwiowe.
- `MATERIAL` — materiał sprzedawany wg ceny zakupu (wyszczególnienie materiałowe).
- `OTHER` — inna praca.
A substrate is a property of the work item (expressed through the item name and an optional `quality_level`), never a category.

**5. Money precision — INPUT ≠ STORAGE ≠ DISPLAY; DECIMAL only, never float.**
- **STORAGE**: `Numeric(12, 2)` — exactly two decimal places, PLN range. Nothing is rounded before storage and nothing is truncated.
- **API**: price serialized as a string always in the fixed 2-dp wire form (`"45.00"`); Pydantic `Decimal(decimal_places=2)` validates; input with more than 2 decimal places → **422**; a negative value → **422**; `0.00` is valid (a "to jeszcze ustalić" placeholder price). An invalid input is rejected, **never silently rounded/truncated** — the user's typed value is preserved until corrected (mirrors the 8C.2 policy).
- **INPUT UX**: free-form text (`45`, `45,5`, `45,50`), `,`→`.` normalization only, ≤2 dp enforced pre-submit with a localized inline error.
- **DISPLAY**: Polish format `45,00 zł` (comma decimal separator, non-breaking space, zł suffix) — the permanent two-decimals display precedent.

**6. Currency storage — ISO 4217-style code, PLN only.** `currency` is an ISO 4217-style 3-character code stored in a **string column** (`VARCHAR(3)` / `String(3)`) — **no PostgreSQL `PriceCurrency` enum is created**. For MVP the application/API accepts only `"PLN"`, defaults to `"PLN"`, and the UI exposes only PLN, with no FX conversion; currency validation is controlled in application/domain code (not the database), so future EUR support requires no DB enum migration — only an API/validation extension (documented intent, not implemented).

**7. Seed / edit strategy — chosen: lazy per-owner materialization.** The seed catalog is defined in code (deterministic bootstrap, the ChecklistTemplate/Risk/communication pattern). On first Price Book access a user's rows materialize as **their own editable copies** (`owner_id` = the accessing owner, one copy per seed row). The user edits their own copy freely; the seed definition is never mutated; re-bootstrap after edits materializes only rows not yet present (idempotent) and never overwrites user data. **Rejected**: multi-tenant shared rows with a per-user override table (second table + a resolution layer with no MVP benefit), and an empty user catalog filled from scratch (the contractor expects a starter list to edit). Seed prices are starter values — editable suggestions, not enforced rates.
**Bootstrap invariants.** Seeded definitions carry stable semantic codes; the unique identity of an owned row is **`(owner_id, semantic code)`**; bootstrap inserts missing seeded codes for the owner; bootstrap is idempotent; bootstrap **never overwrites owner-edited existing rows**; a later release adding a new seed may create the missing row for an existing owner **without resetting their prior edited rows**. **No seed-version complexity is added.**

**8. Ownership.** Every `PriceItem` carries `owner_id` FK → `users.id` ON DELETE CASCADE (the Project pattern) with index `(owner_id, is_archived)`. Uniform 401 unauthenticated / 404 nonexistent-or-foreign-owner on every route — no existence leaks (established multi-tenant isolation pattern).

**9. Price-history policy — no revision table; Stage 10 snapshot contract recorded.** Stage 9 persists only `created_at` / `updated_at` for catalog changes; **no `price_history` table** is built. **Stage 10 obligation (recorded now)**: every estimate line must persist the consumed price and a full item snapshot at line-creation time, so later Price Book edits never rewrite historical estimate lines. No Stage 10/13 entities exist in Stage 9.

**10. Archiving.** `is_archived` boolean soft-archive (Client/Project/AreaSegment convention), default `false`; the default catalog view filters archived rows out; archived rows remain readable by id and restorable (`PATCH` toggles `is_archived`); future refs remain valid; **archive over hard delete**.

**11. Kraków pricing — strategy (9A) → content (9E).** 9E ships a sourced regional catalog: every row carries a traced source (public price list or the contractor's own current rates) and a date; rows are editable reference suggestions, explicitly non-official (no warranty/legal wording), and never authoritative for an estimate without the owner's confirmation. **No prices are invented in 9A.**

**12. Labor / material scope — `PriceScope` enum, LABOR default.** `LABOR` (robocizna — default; the contractor's primary use case), `MATERIAL` (materials only), `LABOR_AND_MATERIAL` (combined). `price_scope` is a per-item flag; the plain unit price is the primary display value and scope appears as a localized chip when not LABOR. Equipment/difficulty surcharges are canonical Stage 12 and are **not** expressed in Stage 9.

**13. Localization.** Every item carries a stable machine `code` that is **never rendered** (established policy). Seeded names via `name_key` → PL/RU locale dictionaries; user-created rows via `display_name` (user text, no key). Display precedence `display_name` > `name_key`; unresolved → neutral localized fallback — never a raw key, never the code. Category chips and unit labels are localized.

**14. Q/S quality compatibility.** Optional nullable `quality_level` column **reusing** the Stage 6 `qualitylevel` enum (`create_type=False`; the enum remains owned by migration 0011), defined as an **optional pricing/applicability hint** — not a compatibility claim. Canonical contract: **Stage 9 does not own substrate↔quality compatibility** — Stage 6 remains authoritative for inspection `substrate` ↔ quality scale. `Q1–Q4` apply only where a gypsum-board-oriented price item makes commercial/domain sense; `S1–S4` apply only where a surface-finish price item makes commercial/domain sense. Stage 9 must **not duplicate the Stage 6 compatibility engine** and adds **no complex DB compatibility matrix**; Stage 9B may enforce only obvious invalid combinations in domain/service validation and tests. Future Stage 11 mapping is responsible for selecting compatible PriceItems for an inspection/recommended-work context. **No `substrate_id` / substrate enum is added to `PriceItem`** to solve this alone.

**15. Reveals (ościeża) compatibility.** Explicit `REVEAL` category and starter items follow the 5F ościeża work scale: reveal preparation m², reveal skimming m², reveal painting m² — each priced per m² (`M2`); the outer reveal cosmetic edge / reveal-work line priced per mb (`LM`). Per-unit rows cover both m² and mb reveal lines.

**16. Code identity & future Stage 11/13 mapping.** **`(owner_id, code)` is unique** — an explicit future DB invariant. Seeded codes use the `CENNIK_*` prefix (e.g. `CENNIK_MALOWANIE_M2`); user-created items receive a generated stable `CUSTOM_*` code. The user may edit display name, price, scope, etc., but the **semantic `code` is immutable after creation** — this immutability is what makes Stage 11 resolution (recommended work → PriceItem → estimate line) and Stage 13 work-tracking reuse reliable. No Stage 11/13 entities appear in Stage 9.

**17. Mobile-first UX — design (9A) → implementation (9D).** Navigation entry "Cennik" → catalog list (category filter chips row, search box, Active / Archived tabs — all wrapping) → item row (display name, category chip, compact `12,50 zł / m²`) → edit (price, unit, category, optional quality / scope / archived) → save. Primary "Add item" control is full-width / `min-h-11`; row touch targets `min-h-11` (~44 px); search+filters never squeeze rows; no horizontal scroll at 320 / 390 / 412 px; "Opcje" progressive disclosure hosts Archive / Restore; PL long-label regressions; **no desktop-specific layout** (permanent mobile-first rule).

#### 9A — Execution plan 9A → 9F
- **9A (this record)** — architecture & domain contract, documentation-only. Gate: `git diff --check` clean; docs + README consistent; commit `docs(stage-9): define editable price book architecture`; push `-u origin stage-9`; `main` untouched; **no 9B without owner approval**.
- **9B — backend domain**: `backend/app/models/price_item.py` (`PriceItem` + `PriceUnit` / `PriceCategory` / `PriceScope` enums only; `currency` as ISO 4217-style `String(3)`, PLN-only in MVP; `qualitylevel` reused), Alembic `0014_create_price_book` (three enums + `price_items`, reversible, single head 0014), base starter seed (deterministic per-owner materialization, idempotent), `backend/app/schemas/price.py`, domain service. Gate: enum/model contracts; migration cycle on real PostgreSQL (`upgrade 0013→0014`, `downgrade -1`, re-`upgrade head`); focused tests; full backend suite.
- **9C — API + tests**: `backend/app/api/v1/endpoints/pricebook.py` — `GET /api/v1/pricebook` (list; category / archived / search filters), `POST` (create), `GET /{id}`, `PATCH /{id}` (fields and `is_archived` toggle); uniform 401/404. Gate: focused + full backend suites; precision contract (2 dp ok, 3 dp → 422, negative → 422, `0.00` ok); idempotent materialization; archive/restore.
- **9D — mobile-first catalog UI**: `frontend/src/features/pricebook/` (list, filters, search, item edit, add, archive under "Opcje"), `frontend/src/api/pricebook.ts`, `frontend/src/types/price.ts`, `price.*` locale keys PL/RU parity. Gate: Vitest + `tsc --noEmit` + `vite build`; mobile regression 320/390/412 px; locale parity.
- **9E — Kraków-sourced catalog content** (refined 9E.1 plan, §14 below: 9E.1 architecture → 9E.2 research catalog → 9E.3 web research Kraków/Małopolskie → 9E.4 normalization review → 9E.5 owner approval → 9E.6 implementation → 9E.7 load; 9F final audit): sourced / dated / editable / non-official regional rows with localized names (strategy per §11) as additional deterministic seed data. Gate: deterministic + idempotent; no invented prices; parity green.
- **9F — integration & final audit**: stage-wide regressions; scope audit (no estimate/Project coupling); docs → Stage 9 **Completed only on owner acceptance**; README; one logical commit; push; merge readiness reserved for owner approval. **Never** merge into `main` without explicit owner approval.

#### 9A — Contract scope guardrails
- 9A is documentation-only: **no** backend models, **no** migration (0014 is 9B), **no** API, **no** front-end, **no** seed data.
- **No change** to Stage 6/7/8 behavior; no rewrite of communication/risk/checklist modules; `main` stays at the 8997d11 merge.
- Stage 9 status: **In Progress** until owner acceptance after 9F; Stage 10 remains **Pending**.

#### 9B execution status 2026-09-13 — backend domain, migration & seed infrastructure (COMPLETE; committed + pushed to `stage-9`)
**Implemented** (no public API, no frontend, no real catalog — per the 9B contract):
- **`backend/app/models/price_item.py`** — `PriceUnit` (exactly `M2 / LM / PCS / HOUR / DAY / FLAT`), `PriceCategory` (exactly the 11 members `PREPARATION / SKIM_COAT / PLASTER / DRYWALL / PAINTING / GLASS_FIBER / MICROCEMENT / DECORATIVE / REVEAL / MATERIAL / OTHER`), `PriceScope` (`LABOR / MATERIAL / LABOR_AND_MATERIAL`), and `PriceItem` (`price_items` table: id UUID pk; `owner_id` FK → `users.id` ON DELETE CASCADE + index `ix_price_items_owner_id`; `code` String(120); `name_key`/`display_name` nullable String(255); `category` / `unit` / `price_scope` enums; `price` `Numeric(12, 2)`; `currency` `String(3)` default `"PLN"` — **no PriceCurrency enum**, ISO 4217-style string; `quality_level` nullable **reusing** the Stage 6 `qualitylevel` enum as an optional pricing/applicability hint; `is_archived` Boolean default false; `created_at`/`updated_at` timestamptz; `UniqueConstraint(owner_id, code)` = `uq_price_items_owner_code`; composite index `ix_price_items_owner_archived`). No `project_id`/`room_id`/`estimate_id`/`substrate`/workflow/coefficient/revision-version columns (Stage 10/11/13 coupling explicitly excluded).
- **`backend/app/domain/data/price_book_seed.py`** — technical seed infrastructure: frozen `PriceItemSeed` dataclass + `build_technical_baseline_price_items()` returning exactly **4 stable `CENNIK_*` rows** (`CENNIK_PREP_GENERIC_M2` 1.11, `CENNIK_PAINT_GENERIC_M2` 2.22, `CENNIK_REVEAL_GENERIC_M2` 3.33, `CENNIK_REVEAL_GENERIC_LM` 4.44) with `name_key` localization keys and **obvious placeholder, non-market prices** (never described as average Kraków rates — the sourced regional catalog is explicitly deferred to 9E).
- **`backend/app/domain/services/price_book_service.py`** — module validation (`validate_price`: Decimal-only, finite, ≥0, **≤2 decimal places rejected, never silently rounded/truncated** — input value preserved unchanged; `validate_currency`: PLN-only for MVP; `validate_custom_name`: custom rows require a non-blank `display_name`) and `PriceBookService`: `ensure_owner_catalog` (lazy **per-owner** materialization under a module `asyncio.Lock`: only missing `(owner_id, code)` seed rows are inserted; idempotent; owner-edited rows **never overwritten**; later-release seeds insert only their own missing rows — no seed-version complexity), `generate_custom_code` (server-side `CUSTOM_<12 upper-hex>`, unique per owner), `create_custom_item` (service-level helper for tests — **no public create route in 9B**), `update_item` (**no `code` parameter by construction** — the semantic code is immutable after creation), `list_owner_items` (`include_archived` opt-in; ordered by code), `get_owned_item` (owner-isolated; `PriceItemNotFoundError` otherwise). Soft archive only — no destructive lifecycle.
- **`backend/app/domain/exceptions.py`** — `PriceItemNotFoundError` + `PriceBookValidationError`.
- **Alembic `0014_create_price_book`** (parent `0013_create_communication_engine`) — creates DB enum types `pricecategory` / `priceunit` / `pricescope`, table `price_items`, and reuses `qualitylevel` via `create_type=False` (still owned by 0011, deliberately not re-created or dropped); reversible upgrade/downgrade; **single Alembic head `0014_create_price_book`**.
- **`backend/tests/test_price_book.py`** — 34 focused tests (no route tests — no HTTP API in 9B): enum exact members; currency stored as `VARCHAR(3)` string (no DB enum); `Numeric(12,2)` column; `0.00` accepted; negative rejected; `>2` decimal places rejected with value preserved (no silent rounding); `(owner_id, code)` unique via `IntegrityError`; same code allowed for different owners; archived persisted on re-query (`populate_existing`); `owner_id` FK `ondelete="CASCADE"` asserted; seed policies `CENNIK_*`/`name_key`; bootstrap first-run creates all 4 rows; second-run idempotent (0 new); owner edit preserved on re-bootstrap; **monkeypatched hypothetical new seed inserts only its missing row**; no cross-owner leakage; `CUSTOM_*` shape/uniqueness; **code immutability through the update path** (re-read from DB); `quality_level` nullable + persisted + `enum_class is QualityLevel` with DB type name `qualitylevel` (Stage 6 reuse, not duplicated); ownership isolation for get/update/list.
**Verification**: focused `test_price_book.py` **34 passed**; full backend pytest **374 passed** (was 340; +34); `git diff --check` clean; migration cycle **on real PostgreSQL PASS** — entrypoint-applied `upgrade 0013→0014`, explicit `downgrade 0013` confirmed `price_items` dropped + `pricecategory`/`priceunit`/`pricescope` enum types dropped + `qualitylevel` preserved, re-`upgrade head` confirmed the full target schema restored (14 canonical columns, 4 enum types, `uq_price_items_owner_code`, `price_items_owner_id_fkey`, `ix_price_items_owner_id`, `ix_price_items_owner_archived`), running `alembic current` = `0014_create_price_book (head)`; Docker `docker compose up -d --build` healthy (postgres/backend/frontend; `/api/health` `{"status":"ok"}`; frontend :5173 up; container `alembic current` = `0014_create_price_book (head)`); `docker compose down -v` never run. **Deliberately NOT implemented in 9B**: real Kraków market catalog (9E), public API routes (9C), frontend UI (9D), Pydantic schemas (9C boundary), any Stage 10/11/13 entity. Committed as **`feat(stage-9): add editable price book backend domain`** and pushed to `origin/stage-9`; working tree clean; `main` untouched at 8997d11. **Canonical Stage 9 remains In Progress** (9C API owners pending); Stage 10 remains **Pending**.

#### 9C execution status 2026-09-13 — public owner-scoped price book API + ownership tests (COMPLETE; committed + pushed to `stage-9`)
**Implemented** (backend API only — no frontend UI, no real market catalog):
- **`backend/app/schemas/price.py`** — `PriceItemCreate` (`extra="forbid"` so a client-supplied semantic `code` is rejected with 422; required `display_name` max 255, `category`, `unit`, `price: Decimal`; optional `currency` default `"PLN"` max 3, `price_scope` default `LABOR`, `quality_level` nullable), `PriceItemUpdate` (`extra="forbid"`, all fields optional — omitted fields preserved; `quality_level` clear-to-null supported, no `code`/`name_key`/`is_archived` fields by construction), `PriceItemRead` (exact contract fields: `id, code, name_key, display_name, category, unit, price, currency, price_scope, quality_level, is_archived, created_at, updated_at`; money serialized as Decimal → JSON string, never float; `from_attributes=True`), `PriceItemListResponse` (`items` + `total`).
- **`backend/app/api/v1/endpoints/pricebook.py`** — owner-scoped route family over `/api/price-items`: `GET /price-items` (list; **bootstrap-on-access**: calls `ensure_owner_catalog` first so the first list materializes the owner's seed rows, idempotent and never overwriting owner edits), `POST /price-items` (create → server-generated immutable `CUSTOM_<12 upper-hex>` code; 201), `GET /price-items/{id}` (owner-isolated detail; **does not** bootstrap — minimal predictable behavior), `PATCH /price-items/{id}` (partial update via `model_dump(exclude_unset=True)`; omitted fields preserved), `POST /price-items/{id}/archive` + `POST .../restore` (explicit soft lifecycle endpoints following the Clients convention; idempotent; **no DELETE**). Domain validation maps to 404 (`PriceItemNotFoundError`) / 422 (`PriceBookValidationError`) with string detail.
- **`backend/app/domain/services/price_book_service.py`** (extended) — `list_owner_items` rewritten to the filter contract (returning a bare `list[PriceItem]`, preserving the 9B service contract): `archived` `"active"` (default) / `"archived"` / `"all"`; `category` / `unit` / `price_scope` / `quality_level` filters; `search` on `code` / `name_key` / `display_name` (case-insensitive `ilike`); stable deterministic ordering `is_archived → category → coalesce(display_name, name_key) → code`; **no pagination** (`total == len(filtered items)`, derived in the route). `update_item` gains the `_UNSET` sentinel so a PATCH `{"quality_level": null}` clears to null while an omitted field is untouched; blank `display_name` **rejects for custom rows** but **clears a seeded row's display override** (reverting to its `name_key` identity); seeded rows are editable copies (price/display override) but `code`/`name_key` are never mutated. New idempotent `archive_item` / `restore_item` soft-lifecycle methods (owner-isolated via `get_owned_item`).
- **Dependencies/registration** — `get_price_book_service` added to `backend/app/api/deps.py`; `pricebook_router` registered in `backend/app/main.py`.
- **`backend/tests/test_price_book_api.py`** — 38 focused API tests: unauthenticated 401 across all 6 routes; first list bootstraps exactly 4 seed rows for the owner; **seed-edit-survives-rebootstrap** (§14 CRITICAL INVARIANT via HTTP: patch seed price/display → re-list → repeat bootstrap → edits unchanged, still 4 rows); `archived` filters (active=4 / archived=1 / all=5 after one archive); `category`/`unit`/`price_scope`/`quality_level` filters; `search` on code / name_key / display_name; stable deterministic ordering; custom item full lifecycle (POST → `CUSTOM_*` → GET → PATCH price/name → archive → absent from active → visible archived → restore → visible active; code unchanged throughout); archive/restore idempotence; price validation (`0`/`0.00`/`45`/`45.5`/`45.50` accepted canonically; negative / `>2` dp / NaN / Infinity rejected 422); EUR rejected; blank custom display name rejected; unknown enums rejected (422); client cannot supply/alter semantic `code` (422 via `extra="forbid"`); PATCH preserves omitted fields; `quality_level` clear-to-null; seeded display override + clear reverts to `name_key`; **ownership isolation A/B** (A's bootstrap never creates/changes B rows; B sees its OWN seed copies; any B access to A's rows → uniform 404; no existence leaks); unknown id → 404.
**Verification**: focused `test_price_book.py` + `test_price_book_api.py` **72 passed** (34 + 38); full backend pytest **412 passed** (was 374; +38); `git diff --check` clean; **no new migration** — single Alembic head `0014_create_price_book`, local `alembic current` = `0014_create_price_book (head)`; Docker `docker compose up -d --build` healthy (postgres/backend/frontend; `/api/health` `{"status":"ok"}`; container `alembic current` = `0014_create_price_book (head)`); authenticated smoke PASS on docker (mock auth → first list bootstraps 4 `CENNIK_*` rows → seed price/display edit survives re-list → custom create `CUSTOM_*` + client-supplied `code` 422 + negative price 422 → archive → active=4/archived=1/all=5 → restore); `docker compose down -v` never run. **Deliberately NOT implemented in 9C**: frontend price book UI (9D), real Kraków market catalog (9E), any Stage 10/11/13 entity. Committed as **`feat(stage-9): expose owner-scoped price book API`** and pushed to `origin/stage-9`; working tree clean (except staged docs); `main` untouched at 8997d11. **Canonical Stage 9 remains In Progress** (9E real catalog, 9F final gate pending); Stage 10 remains **Pending**.

#### 9D execution status 2026-09-13 — mobile-first editable price book UI (COMPLETE; owner accepted; committed + pushed to `stage-9`)
**Implemented** (frontend only — no backend/domain change, **no** migration, **no** real Kraków market catalog, **no** Stage 10 estimate / Stage 11 mapping):
- **`frontend/src/types/priceItem.ts`** — typed contract mirroring the 9C `PriceItemRead` DTO exactly: `PriceItem` (id, code, name_key, display_name, category, unit, price: string, currency, price_scope, quality_level, is_archived, created_at, updated_at), `PriceItemListResponse`, `PriceItemListParams` (`archived` `"active"`/`"archived"`/`"all"`, `category`, `search`), `PriceItemCreatePayload` / `PriceItemUpdatePayload`, plus single-sourced readonly enum arrays `PRICE_CATEGORIES` (11), `PRICE_UNITS` (6), `PRICE_SCOPES` (3) and `PRICE_QUALITY_LEVELS` (S1–S4, Q1–Q4). No `any` anywhere.
- **`frontend/src/utils/priceFormat.ts`** (+ `priceFormat.test.ts`, 20 cases) — money display **without float arithmetic**: `formatPrice` string-splits on `.` and pads/truncates to exactly two decimals → `"45,50"`, `"0,00"`, em dash for empty; `normalizePriceInput` implements the §8 input contract — accepts `45` / `45.5` / `45.50` / `45,5` / `45,50` / `0` / `0.00` (comma normalized to dot), rejects negative / malformed (`abc`, `45.5.5`, `45.`) / `>2` decimals (`45.555` → `precision`) / empty; returns canonical dot value for the API and a machine `reason` for localized messages. The stored value is never altered by display (no rounding/truncation).
- **`frontend/src/api/priceItems.ts`** — clients.ts-convention typed fetcher: `fetchPriceItems` (omits defaults; passes `archived`, `category`, `search`), `createPriceItem` POST, `updatePriceItem` PATCH, `archivePriceItem` / `restorePriceItem` POST — `getAuthHeaders`, throws `Error`, no `any`.
- **`frontend/src/components/PriceBook.tsx`** — the mobile-first Cennik screen: Active/Archived tabs (`role=tablist`), search + category filter, full-width "Dodaj pozycję" primary (all `min-h-11`, ≥44 px), item cards (name **never** truncated — wrap-safe; price emphasized `45,50 zł / m²`; category, scope chip when `≠ LABOR`, optional quality badge "Klasa Q3", archived badge), "Opcje" progressive disclosure (Edit / Archiwizuj), Restore on archived rows, **no code / name_key / UUID / owner_id ever rendered**, and **no DELETE anywhere**. Seeded identity §5: `display_name` > localized `name_key` (`resolveKey(t, "pricebook.seed.*")` — e.g. "Przygotowanie podłoża – ogólne" / "Материалы — общая подготовка" style) > localized fallback em dash. Edit form §7: display name (custom rows required; seeded rows show `Nazwa bazowa: …` hint and a blank name clears the display override), category / unit / price (text input `inputMode="decimal"`) / scope / optional quality; PLN read-only note; code/name_key never editable. §8 submit guard: invalid price surfaces a localized inline error and blocks the API call; Save disabled while price is invalid (non-empty). Create uses the server response; archive/restore hit the explicit endpoint (`POST .../archive`, `POST .../restore`); all localized states (loading / no items / no archived / no search results / load-save-archive-restore errors) — **no raw 422/500/codes**.
- **`frontend/src/locales/pl.json` / `ru.json`** — full `pricebook.*` namespace (PL + RU), `navigation.pricebook` = "Cennik" / "Прайс"; 11 categories, 6 units, 3 scopes, 8 quality labels ("Klasa S1"…), the four `seed.*` name_keys, currency symbol "zł"; parity locked by `frontend/src/locales/parity.test.ts` (new Stage 9D case: identical PL/RU key structure + every machine enum member is labelable).
- **`frontend/src/App.tsx`** (+ `App.test.tsx`) — third main-nav entry `show-pricebook` in the `grid grid-cols-3` nav ("Cennik"/"Прайс"; **no desktop-only nav**), app section `'pricebook'` renders `<PriceBook />`; App tests gain the `./api/priceItems` mock and a "opens the price book section from the main navigation" case (region `price-book-section`, fetch hit, no crash).
**Spec-compliant verification of §6/§8/§9/§10/§12/§13/§15/§16**: all above covered by `PriceBook.test.tsx` (34 cases) + `priceFormat.test.ts` (20) + `parity.test.ts` + `App.test.tsx` — list/filters/create/edit/money input/archive/restore/error-state UI/mobile (390/412 px core, no horizontal scroll, ≥44 px targets, full-width primaries, long PL/RU wrap safety), PL/RU via locale switch, typed contracts without `any`.
**Verification**: focused 9D frontend **66 passed** (20 priceFormat + 12 App + 34 PriceBook); full frontend vitest **269 passed (21 files)** (was 213; +56 = 20+34 price/PriceBook minus 0, App 12 incl. 1 new); `tsc --noEmit` PASS; `vite build` PASS; full backend pytest **412 passed** (unchanged — 9D touches no backend source); `git diff --check` clean; **no new migration** — single Alembic head `0014_create_price_book`; Docker `docker compose up -d --build` healthy (postgres/backend healthy, `/api/health` `{"status":"ok"}`, frontend :5173 HTTP 200, container `alembic current` = `0014_create_price_book (head)`); **authenticated live smoke PASS on docker** — mock auth → `GET /api/price-items?archived=active` returns the 4 owner seed rows with `name_key` = `pricebook.seed.prep_generic_m2` etc., exactly the dotted keys the UI resolves from the PL/RU dictionaries. `docker compose down -v` never run. **Deliberately NOT implemented in 9D**: real Kraków market catalog (9E), any Stage 10 estimate or Stage 11 mapping, any redesign of unrelated UI. **9D OWNER ACCEPTANCE 2026-09-13**: the owner manually tested the A–O checklist and accepted the implementation — visual/mobile acceptance **PASS**, current Price Book behavior works as expected in the manual workflow; technical seed prices remain intentional placeholders and the real Kraków market catalog remains deferred to 9E. On approval the owner authorized the commit and push; the full 9D change set was committed as **`feat(stage-9): add mobile editable price book`** and pushed to `origin/stage-9`; working tree clean; `main` untouched at 8997d11. **Canonical Stage 9 remains In Progress** (9E real catalog, 9F final gate pending); Stage 10 remains **Pending**.

#### 9E.1 execution status 2026-09-13 — market price reference & sources architecture (COMPLETE; architecture/documentation only — committed + pushed to `stage-9`)
**Scope**: architecture contract for attaching researched **Kraków / Małopolskie** market references and source URLs to Price Book items. **No code, no migration, no frontend, no real Kraków prices.** Real web research is explicitly deferred to 9E.3; this record settles the data model, provenance policy, and the Stage 10/15 compatibility contract.

**Core product invariant — owner price ≠ market evidence.** `PriceItem.price` = the owner's current **editable working/commercial price**. Market research never automatically overwrites `PriceItem.price`; a market reference exists only as supporting context/evidence. The three concepts are kept strictly separate:
`OWNER PRICE != MARKET RANGE != SOURCE QUOTED PRICE`.
A later 9E load / Stage 10 estimate / Stage 15 PDF may *display* market data, but only `PriceItem.price` is authoritative for quoting, estimating, and contracting. Owner edits to `PriceItem.price` remain fully independent of any attached references; refreshing or deleting market references never mutates `PriceItem.price`.

**Relationship model (minimal, two-level).**
`PriceItem 1 → 0..N PriceMarketReference 1 → 1..N PriceSource`.
One market reference summarizes multiple external sources for one regional/unit view; one source belongs to exactly one reference. Owner price stays independent at the root; the estimate/PDF layers can read a compact "reference + its sources" bundle. **PriceSource never mutates PriceItem directly** — all linkage flows through the reference row. Neither table is a root aggregate: ownership is enforced transitively through `PriceItem.owner_id` on every access path (no denormalized `owner_id` on references/sources); a future direct reference endpoint must join through `PriceItem` for the 9C-style uniform-404 owner isolation.

**Entity 1 — `PriceMarketReference`** (`price_market_references`). Genuinely required fields:
- `id` — UUID pk
- `price_item_id` — FK → `price_items.id` ON DELETE CASCADE (isolation via parent)
- `region` — **controlled text**, MVP exact values `"Kraków"` / `"Małopolskie"` / `"Kraków / Małopolskie"` (plain `String`, **no geo tables** — region is a label, not a query dimension in MVP; a future multi-region expansion may normalize proper region entities then, not before)
- `market_min` / `market_max` — `Numeric(12,2)`, **Decimal-only, never float**; research outputs over the observed numeric source contributions, never authoritative tariffs
- `currency` — `String(3)`, PLN-only in MVP, **must be compatible with the linked `PriceItem.currency`**
- `unit` — reuse the Stage 9B `PriceUnit` enum; **must equal the linked `PriceItem.unit`** (the reference range is expressed in the same unit as the owner price; compatibility enforced in service validation)
- `checked_at` — required research date (the "Sprawdzono: YYYY-MM-DD" the UI must surface); market prices age quickly, never shown as current without its date
- `created_at` / `updated_at`

Optional (kept because they carry real meaning): `reference_price` (nullable single "punkt odniesienia" figure when the research legitimately yields a middle value; **not auto-computed** from min/max), `methodology_note` (nullable text — how the range was derived; where quality assumptions and qualitative-only source context are recorded). **Deliberately excluded**: revision/version columns — MVP policy is **re-check in place** (re-run research, update values + refresh `checked_at`); historical research preservation stays a documented future option and is introduced only if clearly justified, not in 9E.

**Entity 2 — `PriceSource`** (`price_sources`, one row per cited evidence item). Genuinely required fields:
- `id` — UUID pk
- `market_reference_id` — FK → `price_market_references.id` ON DELETE CASCADE
- `source_name` — String display text (e.g. "Cennik wykończeniowy Firma X", "Allegro Usługi", "store-wykonczeniowy-krakow.pl")
- `source_type` — controlled `SourceType` DB enum
- `checked_at` — required (each source ages too)
- `created_at`

Optional numeric + provenance fields (the "quoted evidence" set): `source_url` (nullable; **never forced — OWN_PRICE sources carry no URL**), `source_region` (nullable controlled text; may differ from the reference region when an out-of-region source is used for qualitative context), `quoted_price_min` / `quoted_price_max` / `quoted_price_single` (nullable `Numeric(12,2)`; **a source supports exactly one quoting mode** — a single quoted price, OR a quoted range, OR qualitative-context-only with all three null), `quoted_unit` (nullable; the unit the source itself quoted — must be **compatible** with the reference's unit per the normalization rule below, otherwise the source contributes qualitative context only, never numbers), `note` (nullable).

**`SourceType` controlled values (normalized, seven)**:
`CONTRACTOR_PRICE_LIST` (preferred labor evidence), `MARKETPLACE` (services/goods marketplaces), `MANUFACTURER` (system/material manufacturer lists), `MATERIAL_STORE` (distributor/retail material pricing), `INDUSTRY_ARTICLE` (press/industry commentary — qualitative context by default), `OWN_PRICE` (the owner's own internal price rationale/history — **never presented as external market evidence**), `OTHER`.

**Region contract (MVP).** Exact resolved values `"Kraków"`, `"Małopolskie"`, `"Kraków / Małopolskie"` as plain controlled text; region appears on the reference (the researched area) and optionally per source; no normalization tables and no geo FK — deferred unless a future stage adds true multi-region support.

**Date policy.** `checked_at` is required on every market reference **and** every source. Future UI must render "Sprawdzono: YYYY-MM-DD" wherever a reference is shown; stale references are never treated as current without date visibility (an explicit staleness hint is a later UX concern, out of 9E.1 scope).

**Evidence / source-count policy.**
- Every market-derived `PriceMarketReference` requires **≥ 1 source** (enforced at creation).
- For important / high-impact items prefer **3+ independent sources** before the range is treated as representative.
- A **single contractor page is a data point, never a "market average"**; single-source references must say so in a methodology note.
- `MANUFACTURER` / `MATERIAL_STORE` sources support **material/system costs, not labor rates** (labor evidence comes from `CONTRACTOR_PRICE_LIST` / `MARKETPLACE` / local company offers).
- Own/internal values are marked `OWN_PRICE`, distinct from external evidence.
- The source list size is visible with the reference — evidence breadth is never hidden.

**Quoted price / range handling.** Each source contributes in exactly one mode: single quoted price, quoted range, or qualitative context. The reference `market_min`/`market_max` aggregate the numeric contributions of its compatible-unit sources; qualitative-only sources are reflected in `methodology_note` and never inject invented numbers.

**Labor / material separation (critical).**
- `LABOR` items — evidence from contractor price lists, service marketplaces, local company offers.
- `MATERIAL` items — manufacturer/distributor/store prices acceptable.
- `LABOR_AND_MATERIAL` items — a source **must clearly state the combined scope** or it cannot contribute numbers (`methodology_note` records the mismatch otherwise).
- **Never mix labor-only and labor+material values into one market range** — a labor-only source and a labor+material source for the same item are incompatible evidence and must not be averaged together.

**Unit normalization (strict, no auto-conversion).**
- Compare source values only with compatible units: `M2 ↔ m² ↔ m2`; `LM ↔ mb / metr bieżący`; `PCS ↔ szt.`; `HOUR ↔ godz.`; `DAY ↔ dzień`; `FLAT ↔ ryczałt` **only when the scope semantics are sufficiently comparable**.
- **No automatic conversion between FLAT and M2**; no combining of incomparable units; a source quoting an incompatible unit contributes qualitative context only.

**Quality-specific references.** If the linked `PriceItem.quality_level` is set (Q1–Q4 / S1–S4), market evidence should match that quality expectation **when the source wording supports it**. Never infer a Q/S level from vague marketing text; a source that does not specify quality attaches to generic items only or is recorded in `methodology_note` as quality-unspecified.

**Future owner-price vs market UX contract (design only — NOT implemented).** Primary = owner price; secondary = market context:
```
Szpachlowanie 2 warstwy
52,00 zł / m²          ← owner price (authoritative)

Rynek Kraków:
40–55 zł / m²
Punkt odniesienia: 47,50 zł
Sprawdzono: 2026-09-12
Źródła (5)              ← tap → source rows
```
Tapping "Źródła" / "Источники" reveals per source: `source_name`, source type, `checked_at`, quoted price/range if present, external link if `source_url` exists. **No raw DB ids, no codes, no owner_id leaked** (consistent with the 9D card policy).

**Stage 10 compatibility (recorded obligation).** A Stage 10 estimate line **must snapshot the owner price used** at line-creation time. Later market-reference changes must **never silently recalculate** an existing estimate line — the snapshot is the contractual number, exactly as Stage 9A §10 recorded for price-history policy.

**Stage 15 PDF compatibility (supporting evidence only).** An estimate/protocol PDF **may optionally include** the market range, checked date, and a source list/links. Market references are supporting context — **never the contract price authority** and never a substitute for the snapshot owner price in a legal document.

**Refined Stage 9E execution plan (architecture → research → review → implementation).**
- **9E.1** (this record) — market reference / source architecture (docs)
- **9E.2** — research catalog structure: final work-item list to research
- **9E.3** — web research Kraków / Małopolskie: collect dated source evidence
- **9E.4** — normalize and review: unit / scope / quality / labor-material consistency
- **9E.5** — owner review: approve seed values / ranges
- **9E.6** — implementation: migration / model / API / UI / source display as actually needed
- **9E.7** — load approved researched catalog
- **9F** — Stage 9 integration / final audit

**Stage 9E.1 acceptance criteria met**: owner-price-vs-market separation (§1), market-reference entity & required-field decision (§2), source entity & quoting-mode rule (§3), seven controlled `SourceType` values (§3), region contract (§5), checked-date policy (§6), evidence-count policy (§7), quoted price/range handling (§7), labor/material separation (§11), unit compatibility (§12), quality-evidence handling (§13), future source UI (§8–9), Stage 10 estimate snapshot behavior (§10), Stage 15 PDF compatibility (§10), and the real-research execution plan (§14) — all explicitly settled in this record. No code, no migration, no frontend, no real prices. Committed as **`docs(stage-9): define market price source architecture`** and pushed to `origin/stage-9`; working tree clean; `main` untouched at 8997d11. **Deliberately NOT implemented**: real Kraków research (9E.3), research catalog list (9E.2), any Stage 10/11/13 entity, any frontend. **Canonical Stage 9 remains In Progress** (9E.2–9E.7, 9F pending); Stage 10 remains **Pending**.

#### 9E.2 execution status 2026-09-13 — research catalog structure (COMPLETE; docs-only — committed + pushed to `stage-9`)
**Deliverable**: the canonical Kraków / Małopolskie research catalog — **`docs/price-research-catalog.md`** (created this sub-stage; referenced here). It defines **WHAT** 9E.3 will research and contains **no prices and no invented rates**.
- **Catalog**: **51 research items** across 9 groups with stable `CENNIK_*` semantic code proposals, PL + RU labels, Stage 9B category / unit / scope enums, optional quality hints, P1/P2/P3 priority, a per-row **comparability definition** (comparable vs not-comparable evidence) and notes. Groups: Preparation (7), Priming (4, category-mapped to `PREPARATION` — no dedicated enum member), Skim coat / filling (9), Gypsum board / drywall finishing (5), Glass fiber / fleece (3), Painting (7), Reveals / ościeża (6), Microcement (6), Decorative / Venetian (4).
- **Priorities**: P1 = 20 (preparation, priming, skim, sanding, skim+sanding package, GK joint + full-surface, fleece labor, painting standard + ceilings, reveals prep/skim/paint/mb, microcement walls labor+system, classic Venetian) · P2 = 22 · P3 = 9.
- **One scope per item** (§1): no ambiguous rows (e.g. "szpachlowanie"); explicit single/2/3-coat skim, full skim+sanding package, joint treatment vs full-surface, fleece application labor vs with material, painting 2-coat standard.
- **Painting default defined** (§7): standard row = 2 coats, white wall paint, prepared substrate, **labor-only**, per m² — every painting source compared against this default first.
- **Q1–Q4 decision (§5)**: generic commercial rows + optional `quality_level` hints, not four separate items; explicit quality rows (`CENNIK_GK_Q4-01`, `CENNIK_SKIM_SQ-01`) exist only where source wording justifies them (both P3); mapping notes Q1 = joints · Q2 = joints + feathering · Q3 = full-surface · Q4 = full-surface ≥1 mm / strip light.
- **Reveals 5F compatibility (§8)**: m² rows (reveal as surface) vs LM rows (linear reveal work, mb basis) are kept strictly separate — no LM↔M2 interchangeability — and complement the existing 9B seeds `CENNIK_REVEAL_GENERIC_M2` / `_LM`.
- **Microcement system vs labor preserved (§9)**: wall/floor pairs `LABOR` vs `LABOR_AND_MATERIAL` rows; shower zone with membrane and substrate-prep notes.
- **S1–S4 limitation documented (§11, §12)**: contractors do not reliably publish S/Q labels; the catalog uses generic rows and attaches quality **only** on literal source wording — no manufactured S1–S4 market prices.
- **OWN_PRICE candidates (§12)**: `PREP_CLEAN`, `SKIM_LOCAL`, `GK_SCREW`, `PAINT_MASK`, `PAINT_MULTI`, `MC_STAIRS`, `PREP_PROT` — assigned `OWN_PRICE` in 9E.4/9E.5 if 9E.3 finds no market basis; never forced fake market references.
- **Research batches (§14)**: A (prep/priming/skim/sanding — 20 items), B (painting/glass fiber/GK — 15), C (reveals — 6), D (microcement — 6), E (decorative/Venetian — 4). **No web research performed.**
- **Acceptance criteria met (§18)**: list concrete and comparable; no prices invented; labor/material scope explicit per row; units explicit; Q/S ambiguity documented; reveals 5F-compatible; microcement system-vs-labor distinction preserved; decorative/Venetian included; priorities assigned; batches defined; codes proposed. Committed as **`docs(stage-9): define Krakow price research catalog`** and pushed to `origin/stage-9`; working tree clean; `main` untouched at 8997d11. **Deliberately NOT implemented**: any web research (9E.3), prices, migrations, backend/frontend code. **Canonical Stage 9 remains In Progress** (9E.3–9E.7, 9F pending); Stage 10 remains **Pending**.

#### 9E.3A execution status 2026-09-13 — Kraków market research — Batch A: preparation / priming / skim / sanding (COMPLETE; web research + documentation only — committed + pushed to `stage-9`)
**Deliverable**: the Batch A research-evidence file — **`docs/price-research-batch-a.md`** (created this sub-stage; referenced here). It records **verbatim source quotes only** (`checked_at` 2026-09-13; the three load-bearing Kraków anchors — s-szpachlowanie.pl Kraków cennik, malarzkrakow.pl/cennik, kb.pl gruntowanie city table — re-confirmed 2026-09-14). It contains **no seed decisions and no `PriceItem.price` values**.
- **Items researched**: **20 / 20** Batch A catalog items — Preparation (7: PROT, WALLP, SCRAPE, FLEECE, DEGR, MOLD, CLEAN), Priming (4: STD, ADH, HIGH, PAINT), Skim/filling/sanding (9: 1L, 2L, 3L, SAND, PKG, CRACK, CORNER, LOCAL, SQ).
- **Source count**: **40 referenced evidence pages** (37 with usable numeric quotes; 3 qualitative / non-comparable context) — **6 Kraków / Małopolskie-region anchors** (5 Kraków firms + kb.pl Kraków municipal row) and **34 Poland-wide**, incl. 2 outside-target-region supplementary (Warszawa Derty Serwis; Łódź SLIM-POL). Suspected content-network duplication flagged (sccot.pl ↔ itodesign.pl), as are single-publisher pages.
- **Confidence distribution**: **HIGH 6** (PREP_WALLP, PREP_SCRAPE, SKIM_1L, SKIM_2L, SKIM_SAND, SKIM_CORNER) · **MEDIUM 7** (PREP_PROT, PREP_MOLD, PRIM_STD, PRIM_PAINT, SKIM_3L, SKIM_PKG, SKIM_LOCAL) · **LOW 6** (PREP_FLEECE, PREP_DEGR, PRIM_ADH, PRIM_HIGH, SKIM_CRACK, SKIM_SQ) · **INSUFFICIENT 1** (PREP_CLEAN).
- **Insufficient-evidence items**: **1** — CENNIK_PREP_CLEAN-01 (post-sanding substrate vacuuming is never priced standalone; "sprzątanie po remoncie" is non-comparable whole-flat cleaning).
- **Kraków anchors (key figures)**: s-szpachlowanie.pl Kraków skim table — 1 warstwa 35–50 · 2 warstwy 55–75 · szlifowanie 10–16 · narożniki wewn. 12–18 / zewn. 15–22 zł/mb · ubytki punktowo 25–40 · gładź "pod światło boczne / lampy LED" 35–55; malarzkrakow.pl — zabezpieczenie od 5 · gruntowanie od 5 · skrobanie od 10 · zrywanie tapet od 10 zł/m² (net, labor); kb.pl city table — Kraków gruntowanie 7,73 zł/m² brutto (labor, VAT 8%); małopolskie 6,68–7,73.
- **Market results (evidence windows, NOT implementation)**: e.g. SKIM_1L 30–50 · SKIM_2L 35–75 · SKIM_SAND 10–25 · SKIM_PKG 35–70 · SKIM_CORNER 12–22 zł/mb · PREP_WALLP 10–30 · PREP_SCRAPE 10–35 · PRIM_STD L+M 7–15 · PRIM_PAINT L+M 3–15. `reference_price` set only where a central commonly-observed value exists with method stated (never a fake arithmetic average); labor-only and labor+material never mixed; PL nationwide sources marked supplementary; no S1–S4/Q-level inference (SKIM_SQ uses the sources' own wording).
- **OWN_PRICE candidates after research**: **8** — PREP_CLEAN (no market basis), PREP_PROT, PREP_FLEECE, PREP_DEGR (single/bundled), PRIM_ADH, PRIM_HIGH (component/single-source), SKIM_3L (single content-network 3x quote; usually 2x + add-on), SKIM_LOCAL (complex-dependent). No final owner price assigned.
- **Cross-check passed (9E.3A §19)**: traceable ranges, URL-duplication flags, scope-unmixed ranges, compatible units, PL marked, no invented prices, all 20 codes verbatim from the catalog. Company/labor-content caveats: most portals are SEO content pages; the strongest independent set is kb.pl / cenauslug / zleca; no clean "Małopolskie-only" local row beyond kb.pl's voivodeship rows.
- **Verification**: `git diff --check` PASS; committed as **`docs(stage-9): research Krakow preparation and skim prices`** and pushed to `origin/stage-9`; working tree clean; `main` untouched at 8997d11. **Deliberately NOT implemented**: any prices, seeds, migrations, backend/frontend code; 9E.3B (Batch B — painting / glass fiber / GK) and 9E.4 (market-reference building / seed decisions) remain **Pending** — next sub-stage requires explicit owner approval. **Canonical Stage 9 remains In Progress**; Stage 10 remains **Pending**.

#### 9E.3B execution status 2026-09-14 — Kraków market research — Batch B: painting / glass fiber / gypsum board finishing (COMPLETE; web research + documentation only)
**Deliverable**: the Batch B research-evidence file — **`docs/price-research-batch-b.md`** (created this sub-stage; referenced here). It records **verbatim source quotes only** (`checked_at` 2026-09-14; every load-bearing numeric quote re-fetched fresh). It contains **no seed decisions and no `PriceItem.price` values**.
- **Items researched**: **15 / 15** Batch B catalog items — Painting (7: PAINT_2K, PAINT_1K, PAINT_3K, PAINT_CEIL, PAINT_COL, PAINT_MASK, PAINT_MULTI), Glass fiber/fleece (3: GF_FLIZ_L, GF_FLIZ_M, GF_MESH), Gypsum board finishing (5: GK_JOINT, GK_FULL, GK_SCREW, GK_CORNER, GK_Q4).
- **Source count**: **20 numeric evidence pages referenced** + 2 contextual pages — **8 Kraków / regional anchors** (5 Kraków firms — malarzkrakow.pl, kubamalarz.pl, totaldecor.pl, ekipa-krakow, s-szpachlowanie.pl — and 3 Kraków city-/regional tables — cennikremontow.pl ×2, kb.pl Kraków) and **12 Poland-wide**, incl. Kraków city rows inside national pages (kb.network, koszt-wykonczen.pl, cennikremontow.pl) and 1 Małopolskie city row on a national portal (cenauslug.pl, Nowy Sącz). Content-network duplication flagged (kb.network ↔ aikfarby); sccot.pl, daibau.pl, hejmalarz.pl excluded from numerics.
- **Confidence distribution**: **HIGH 1** (PAINT_2K) · **MEDIUM 9** (PAINT_1K, PAINT_3K, PAINT_CEIL, PAINT_COL, GF_MESH, GK_JOINT, GK_FULL, GK_CORNER, GK_Q4) · **LOW 3** (PAINT_MASK, GF_FLIZ_L, GF_FLIZ_M) · **INSUFFICIENT 2** (PAINT_MULTI, GK_SCREW).
- **Insufficient-evidence items**: **2** — CENNIK_PAINT_MULTI-01 (multi-color priced only as surcharge structure — ciemne +8–15 zł/m², kolor +5–15%, tesa cut-ins "dodatkowo płatne" — no standalone m² market price) and CENNIK_GK_SCREW-01 (screw-head filling never priced standalone; always bundled in Q1/Q2 joint rows — betonizm.pl, koszt-wykonczen.pl).
- **Kraków anchors (key figures)**: malarzkrakow.pl — malowanie od 8 (1 warstwa) / od 14 (kolor) / od 5 (maskowanie) zł/m² net, labor; kubamalarz.pl Kraków — 2 warstwy 25–27 zł/m² (partial, scope ambiguous); totaldecor.pl — kolor 18, pełne GK 40 zł/m²; ekipa-krakow — malowanie 10 (flagged low-outlier), narożniki 10 zł/mb; s-szpachlowanie.pl Kraków — narożniki zewn. 15–22 zł/mb; kb.pl city table — Kraków tapetowanie włókniną 64,30 zł/m² brutto (tech-B analog, not tech-A); cennikremontow.pl Kraków — malowanie sufitów 2 warstwy biały 18–32 / kolor 16–22, maskowanie 18,70 zł/m² net, GK szpachlowanie 34–46 zł/m², wtapianie siatki 12–58 zł/m².
- **Market results (evidence windows, NOT implementation)**: PAINT_2K 10–28 (ref 18) · PAINT_1K 8–30 · PAINT_3K 21,80–48 · PAINT_CEIL 16–32 (ref 24) · PAINT_COL 14–30 (ref 20) · PAINT_MASK 5–20 · GF_MESH 12–58 · GK_JOINT 34–46 (explicit Q1/Q2 evidence) · GK_FULL 28–45 (ref 40, explicit Q3 evidence) · GK_CORNER 10–22 zł/mb (ref 18) · GK_Q4 40–80 (explicit Q4 evidence, 2 sources). **Fleece tech gap**: no tech-A (flizelina malarska / włóknina szklana underlay) application-labour market price exists in any checked source → GF_FLIZ_L/GF_FLIZ_M evidence windows left empty, marked OWN_PRICE candidates; tech-B analog (tapeta z włókna szklanego) recorded explicitly labeled — kb.pl 48,82–77 zł/m² brutto (Kraków 64,30), aikfarby.pl Kraków 65,40–74,30 (śr. 69,80), t-tapety 50–80 netto, aikfarby L+M łączny 110–190 zł/m² — never merged into a tech-A range. `reference_price` set only where a central commonly-observed value exists (PAINT_2K 18, PAINT_CEIL 24, PAINT_COL 20, GK_FULL 40, GK_CORNER 18); labor vs labor+material never mixed; strictly LABOR painting rows exclude paint/primer/material; PL nationwide sources marked supplementary; Q-level evidence counted only where the source explicitly states Q1/Q2/Q3/Q4 or an unambiguous Polish technical equivalent (betonizm.pl, koszt-wykonczen.pl).
- **OWN_PRICE candidates after research**: **5** — PAINT_MASK (scope-variant; PCS rows), PAINT_MULTI (surcharge-only structure), GF_FLIZ_L, GF_FLIZ_M (no tech-A market basis), GK_SCREW (always bundled). No final owner price assigned.
- **Explicit Q-level sources**: betonizm.pl — Q1 12–18 zł/mb, Q2 20–30 zł/m², Q3 30–45 zł/m², Q4 60–80 zł/m² "całopowierzchniowe ≥1 mm" (main-table figure; chart conflict 110 flagged in §21); koszt-wykonczen.pl — Q1 15 zł/mb, Q2 18–20 zł/mb (Kraków 24 zł/mb, 30–35 zł/m²), Q3 28–35 zł/m², Q4 40–55 zł/m² (gradacja 220–240).
- **Cross-check passed (9E.3B §19)**: traceable ranges, URL-duplication flags, scope-unmixed ranges, compatible units (unit mismatches flagged, not merged), PL marked, no invented prices, all 15 codes verbatim from the catalog. §21 NORMALIZATION_REVIEW_NOTE flags for 9E.4 (Batch A numbers untouched): (1) SKIM_PKG vs SKIM_1L/2L package-scope check — Kraków component equivalent 65–91 exceeds the 35–70 package band → package likely volume-discounted/component-limited; (2) painting coat-count normalization — 2-coat PAINT_2K default must not double-count PRIM_PAINT/SKIM; cennikremontow 1-coat row internally inconsistent; (3) betonizm Q4 table-vs-chart conflict; (4) GK_JOINT M2 vs LM unit model; (5) cennikremontow "Montaż narożników" cell unit mismatch (22–30 zł/m² for a linear service).
- **Verification**: `git diff --check` PASS; committed as **`docs(stage-9): research Krakow painting and drywall prices`** and pushed to `origin/stage-9`; working tree clean; `main` untouched. **Deliberately NOT implemented**: any prices, seeds, migrations, backend/frontend code; 9E.3C (Batch C — reveals) and 9E.4 (market-reference building / seed decisions) remain **Pending** — next sub-stage requires explicit owner approval. **Canonical Stage 9 remains In Progress**; Stage 10 remains **Pending**.

#### 9E.3C execution status 2026-09-14 — Kraków market research — Batch C: reveals / ościeża / glify / szpalety (COMPLETE; web research + documentation only)
**Deliverable**: the Batch C research-evidence file — **`docs/price-research-batch-c.md`** (created this sub-stage; referenced here). It records **verbatim source quotes only** (`checked_at` 2026-09-14; every load-bearing numeric quote re-fetched fresh). It contains **no seed decisions and no `PriceItem.price` values**.
- **Items researched**: **6 / 6** Batch C catalog items (§9/catalog) — REV_PREP-01 (M2, LABOR, P1), REV_SKIM-01 (M2, LABOR, P1), REV_SAND-01 (M2, LABOR, P2), REV_PAINT-01 (M2, LABOR, P1), REV_WORK_LM-01 (LM, LABOR, P1), REV_PAINT_LM-01 (LM, LABOR, P2).
- **Source count**: **10 numeric evidence pages referenced** + 10 negative-check pages audited (local Kraków/Małopolskie sources all NONE_FOUND for reveal rows) — **0 Kraków firms, 0 Małopolskie pages, 10 Poland-wide**; 1 of the 10 is a regional-zone national calculator mapping (o-okna.com.pl Strefa I = metropolie, incl. Kraków, +20–35%).
- **Confidence distribution**: **HIGH 0** · **MEDIUM 1** (REV_WORK_LM — 4+ independent LABOR per-mb sources cluster 30–110, ref 60) · **LOW 0** · **INSUFFICIENT 5** (REV_PREP, REV_SKIM, REV_SAND, REV_PAINT — no standalone per-m² component rows anywhere; REV_PAINT_LM — LM painting never priced standalone).
- **Market structure finding**: the Polish reveal-finishing market does **not** price component reveal operations per m². Standard modes are (1) **per-mb** (dominant for LABOR obróbka — nowabudowa 58,25; cenausług glify 55–85; kb-family obróbka ościeży 30–70; o-okna 50–110 PCV robocizna), (2) **per piece** (window/door bundles: 250–550 zł/okno, 120–400 zł/skrzydło), (3) **per-m² complete obróbka bundles** (okna-porady/dziennikbudowlany 80–120 zł/m²; nowabudowa door glif m² 113 — S1 467,25 brutto/4,13 m²). Two technologies must not be mixed: szpachlowa/tynkowa obróbka (30–110 zł/mb LABOR) vs prefab szpaleta/profile systems (80–350 zł/mb L+M).
- **Kraków-local negative-result audit**: 10 pages checked with **zero** reveal rows — malarzkrakow.pl, kubamalarz.pl, krakow-malowanie.pl, s-szpachlowanie.pl/szpachlowanie-krakow-cennik (404 → corrected URL), cennikremontow.pl Kraków tab, kb.pl Kraków city tab, cenausług.pl Kraków glify/ocieplenie-ościeży subpages (HTTP 410, dead). Terraglass.com.pl and assystem.com.pl → HTTP 403, excluded/archived.
- **Market results (evidence windows, NOT implementation)**: REV_WORK_LM **30–110 zł/mb** (ref 60) MEDIUM — LABOR only, both window and door contexts, new (S2) and post-installation repair (S4) contexts; REV_PAINT_LM INSUFFICIENT (no standalone row — only full obróbka per-mb or per-piece bundles). **All 4 M2 components INSUFFICIENT** — per-m² evidence exists only as complete bundles (outside canonical component scope) → recorded in §13 cross-unit context table, never merged into M2 ranges.
- **Window vs door**: window=door LM rate equality demonstrated where together (S1 nowabudowa — same 58,25 zł/mb LM for both exceed 30 cm; S8 400 zł/skrzydło = window/door door unit); door-only per-m² glif row (S1 113 zł/m²) is a complete bundle, not a component.
- **New vs repair**: S2 cenausług (new plastering/glifs for windows) and S4 dziennikbudowlany (obróbka po montażu okien) both yield compatible 55–85 / 30–70 zł/mb LABOR bands → LM support does not require merging contexts; no REPAIR_DAMAGE-specific per-mb row exists.
- **OWN_PRICE candidates after research**: **5** — REV_PREP, REV_SKIM, REV_SAND, REV_PAINT (no per-m² component market), REV_PAINT_LM (no standalone LM painting); REV_WORK_LM has a market basis (30–110, ref 60) and is **NOT** a candidate. No final owner price assigned.
- **Stage 5F pricing compatibility (9E.3C §15)**: **PARTIALLY_SUPPORTED** — the **LM** reveal row (REV_WORK_LM) is supported by direct per-mb LABOR market evidence; the **M2** component rows are **not** separately supported (no per-m² component market; only complete obróbka bundles outside scope). Keeping both M2 and LM model survives; M2 rows need owner decisions in 9E.4. Future optional modes identified: per-window/per-door pieces and minimum-charge rows (S8 od 200 zł/skrzydło). No Stage 5F or Price Book architecture change performed (contract).
- **Cross-check passed (9E.3C §22)**: traceable numerics with exact URLs, local-national separation (LOCAL 0, REGIONAL-zone 1, NATIONAL 9), M2/LM never merged, per-piece never converted, window/door recorded, new/repair recorded, LABOR vs L+M never mixed, minimums (od) excluded from ranges, no invented geometry (no assumed window M2), no invented prices. §16 NORMALIZATION_REVIEW_NOTE flags for 9E.4 — Batch A/B items (1)–(5) preserved untouched + new: (6) reveal unit model — M2 components vs LM row; (7) per-m² complete obróbka bundles (80–120; nowabudowa 113) vs component scope; (8) "szpaleta" dual scope (window interior reveal vs prefab window surround element); (9) Kraków-zone LM evidence is calculator-zone mapping (o-okna Strefa I 95–160 robocizna; Kraków +20–35%), not a Kraków firm quote.
- **Verification**: `git diff --check` PASS; committed as **`docs(stage-9): research Krakow reveal prices`** and pushed to `origin/stage-9`; working tree clean; `main` untouched. **Deliberately NOT implemented**: any prices, seeds, migrations, backend/frontend code; 9E.3D (Batch D) and 9E.4 (market-reference building / seed decisions) remain **Pending** — next sub-stage requires explicit owner approval. **Canonical Stage 9 remains In Progress**; Stage 10 remains **Pending**.

#### 9E.3D execution status 2026-09-14 — Kraków market research — Batch D: microcement (COMPLETE; web research + documentation only)
**Deliverable**: the Batch D research-evidence file — **`docs/price-research-batch-d.md`** (created this sub-stage; referenced here). It records **verbatim source quotes only** (`checked_at` 2026-09-14). It contains **no seed decisions and no `PriceItem.price` values**. Research → evidence file → documentation → commit → push chain completed this sub-stage.
- **Items researched**: **6 / 6** Batch D catalog items (§10/catalog — all verbatim from the catalog): CENNIK_MC_WALL_L-01 (schody-adjacent — microcement walls labor; M2, LABOR), CENNIK_MC_WALL_S-01 (walls, full system with material; M2, LABOR_AND_MATERIAL), CENNIK_MC_FLOOR_L-01 (floor labor; M2, LABOR), CENNIK_MC_FLOOR_S-01 (floor full system; M2, LABOR_AND_MATERIAL), CENNIK_MC_SHOWER-01 (shower wet zone, system with hydroizolacja; M2, LABOR_AND_MATERIAL), CENNIK_MC_STAIRS-01 (stairs; M2 canonical, per-step/per-flight record basis; LABOR_AND_MATERIAL).
- **Source count**: **22 referenced pages** used (19 weighted + 3 flag-only) + 8 negative/local-audit pages with no usable per-m² rows — **1 strict Kraków-local anchor** (Monolite Kraków salon), **2 Małopolskie/regional L+M anchors** (Zement pracowniabetonu.pl serving Kraków; JAK Chemia Kraków showroom / Libiąż), 2 Kraków-adjacent producers with material evidence (Conbar; Festfloor national), rest Poland-wide/manufacturer-market overviews (**POLAND_SUPPLEMENTARY ~19**).
- **Confidence distribution**: **HIGH 1** (FLOOR_S — 3+ genuinely comparable local/regional system sources) · **MEDIUM 4** (WALL_L, WALL_S, FLOOR_L, SHOWER) · **LOW 1** (STAIRS — unit basis ambiguity) · **INSUFFICIENT 0**.
- **Market structure finding**: the Polish microcement market predominantly quotes **complete L+M systems ("pod klucz"/"kompleksowo")**, not labor-only. True labor-only pricing exists almost exclusively on national price guides → the two **labor-only rows (WALL_L 100–180, ref 140; FLOOR_L 180–250, ref 220) have NO local (Kraków/Małopolskie) basis** (documented negative audit §4.1) — candidates for OWN_PRICE or regional-coefficient derivation at 9E.4, never derived from complete-system prices.
- **Kraków-local anchor (L+M systems)**: Monolite (single strict Kraków salon) — walls 320–650 (dry-interior core 320–400), floors 320–400 (≤50 m² tier to 400), bathroom walls incl. hydro 450–650, stairs m² 750–950 (stopnica+podstopnica). Regional: Zement pracowniabetonu.pl (floors 350–500 typical; walls 350–400; hydro +40–80 separate), JAK Chemia (walls ow triangle, L+M ~260–320 band).
- **Market results (evidence windows, NOT implementation)**: WALL_S **320–650 lokalny / 250–400 PL** (ref 350) MEDIUM; FLOOR_S **320–400 lokalny / 300–550 PL** (ref 380) HIGH; SHOWER **450–650 lokalny / 380–580 (brutto 380–720) PL** (ref 550) MEDIUM; STAIRS **750–950 m² lokalny / M² 350–900 and per step 400–1300 PL** (ref —) LOW. **All figures evidence windows only — cell dedicated, never assigned as owner prices.**
- **Waterproofing explicit**: hydro included vs separate recorded per source (matrix §15); only SHOWER row is a system-with-membrane row; application-only prices recorded as context, not row evidence.
- **Minimum-job findings (§13)**: 50–80 m² floor minimum systems, <25–30 m² flat-rating, small-area premiums (od 22 000–35 000 zł white-packages); **all recorded as commercial context, never converted to M2 rates**.
- **OWN_PRICE candidates after research**: **0 pure** (all six items have some market evidence); **STAIRS** is a **unit-model + scope-normalization case** (m² vs per step 400–1300 vs per flight 9000–13000 — units never converted), not absence-of-market; **WALL_L / FLOOR_L** (labor-only, no local basis) → strongest OWN_PRICE pressures. No final owner price assigned.
- **Stage 5F / material-system context**: **MATERIAL SYSTEM CONTEXT (§16)** records material-only evidence (34,5–194 zł/m² material, national material echelons 80–300) strictly separate from contractor L+M 250–650 — manufacturer/store prices **never** treated as labor. **FESTFLOOR CONTEXT (§17)**: one explicit manufacturer system reference (national, binder+aggregate finish ~120–190 zł/m² material band) — recorded as a system/materials reference, **not** "the market"; Festfloor-affiliated content network (cementibeton.pl family) flagged and de-weighted.
- **Cross-check passed (9E.3D §20)**: all 6 canonical items researched (codes verbatim from catalog §10); traceable numerics with exact URLs; local-national separation (LOCAL 1 / REGIONAL 2 / NATIONAL per item); LABOR vs L+M vs MATERIAL separated; walls/floors not silently mixed; waterproofing explicit; substrate prep explicit; stairs M2/per-step/per-flight never converted; minimums excluded from ranges; manufacturer prices not treated as labor; derived material cells show formula (`pack ÷ coverage`); no guessed consumption; no invented prices (jak-wykonac.fun S21 content-farm excluded from independent counting). §18 NORMALIZATION_REVIEW_NOTE flags for 9E.4 — Batch A/B items (1)–(5) and Batch C items (6)–(9) preserved untouched + new: (10) labor-only rows have no local basis (OWN_PRICE/regional-coefficient decision); (11) STAIRS unit model — canonical M2 vs per-step vs per-flight; (12) "kompleksowo vs robocizna" quoting-mode mixes in national guides (only labor-origin rows used for WALL_L/FLOOR_L); (13) hydro-included vs hydro-separate VAT/nett-basis consistency (sanitmax explicit brutto 380–720 vs netto figures); (14) L+M system bands embed variable substrate prep — prep treated as included vs billed-extra per source, never merged into system bands; (15) <25–30 m² flat-rating and 50–80 m² floor minimums must not enter M2 rows; (16) "beton ciré" search-term collision with concrete-cutting/ready-mix vendors (§2); (17) topciment.com 403-on-default-fetch (retained via UA-rendered fetch) + dk7-krakow-libertow.pl (403) + loftsurface Kraków realize (404) exclusion/archival; (18) pracowniabetonu.pl vs pracowniabetonu.eu are distinct companies (both kept, neither merged); (19) 10 m² kit packs convert via `pack ÷ coverage` only where the store states pack coverage.
- **Verification**: `git diff --check` PASS; committed as **`docs(stage-9): research Krakow microcement prices`** and pushed to `origin/stage-9`; working tree clean; `main` untouched. **Deliberately NOT implemented**: any prices, seeds, migrations, backend/frontend code; 9E.3E (Batch E — decorative / Venetian) and 9E.4 (market-reference building / seed decisions) remain **Pending** — next sub-stage requires explicit owner approval. **Canonical Stage 9 remains In Progress**; Stage 10 remains **Pending**.

#### 9E.3E execution status 2026-09-14 — Kraków market research — Batch E: decorative finishes / Venetian plaster (COMPLETE; **9E.3 Web Research Batches A–E now COMPLETE**; web research + documentation only)
**Deliverable**: the Batch E research-evidence file — **`docs/price-research-batch-e.md`** (created this sub-stage; referenced here). It records **verbatim source quotes only** (`checked_at` 2026-09-14). It contains **no seed decisions and no `PriceItem.price` values**. This is the final 9E.3 batch: all **51/51 canonical catalog items** now have dated research evidence across Batches A–E.
- **Items researched**: **4 / 4** Batch E catalog items (§11/catalog — all verbatim from the catalog): CENNIK_DEC_VEN-01 (stiuk wenecki — klasyczny; M2, LABOR, P1), CENNIK_DEC_VEN_MAR-01 (efekt marmuru z żyłkowaniem; M2, LABOR, P2), CENNIK_DEC_CONC-01 (efekt betonu / beton architektoniczny; M2, LABOR, P2), CENNIK_DEC_GENERIC-01 (tynk dekoracyjny — ogólny; M2, LABOR, P2).
- **Source count**: **23 referenced pages** (16 weighted + 7 flag/exclusion) — **0 Kraków-local firms with published m² LABOR rates** (dflhome Kraków-Kliny, dekormarmo Kraków audit — both individual quotation / portfolio-only; cenauslug.pl stiuk wenecki/Kraków HTTP 410, cudaarchitektury.pl HTTP 403 content-network), **1 Kraków-local marketplace anchor** (OLX TynkDeko Kraków `od 100 zł/m² — wycena indywidualna`; JS-rendered but text served at check), **2 regional serving-Kraków** (VIAN viandekor.pl — marble 350–550 L+M / concrete 160 L+M, explicit Kraków service cities; KB.pl Kraków-row 405 zł/m² L+M stiuk wenecki, min 10 m², Małopolskie 387–424), **~16 Poland-wide labor guides / system prices / material context**.
- **Confidence distribution**: **HIGH 0** · **MEDIUM 3** (VEN — classic labor 120–150 core from 4 guides, ref 140; CONC — concrete-effect labor 60–150 core from 5 guides, ref 110; GENERIC — structural/glaze labor 40–80 from 4 guides, ref 60) · **LOW 1** (VEN_MAR — veined marble: no Polish veined-LABOR row; only L+M 350–550 by one regionally-served firm + "wyceniamy indywidualnie" (dekor-lux); **reference null**) · **INSUFFICIENT 0**.
- **Market structure finding**: Polish decorative-finish pricing splits into (a) **national labor guides 40–150/300 zł/m² robocizna** (structural → classic-Venetian ladder) and (b) **firm-published L+M system prices 160–550 zł/m²** (concrete-effect 160; Venetian 313–480; veined marble 350–550). Kraków firms publish **no fixed m² labor rates** — decorative work is individually quoted (dflhome / dekor-lux evidence). Big-city premium for Kraków documented by itynki at +15–25% (table +20%).
- **Veining complexity (§13)**: VIAN prices veining inside its **L+M band od 350 → 550** (complexity/color-driven, ~57% spread between simple and complex); dekor-lux prices veined variants **individually** ("wyceniamy inaczej") and notes A4 próbka cannot show veining rhythm; wistalex/ewyposazenie "marmoryzacja/efekt marmuru" labor rows (120–150 / 80–160) are **surrogate, not explicit veining** — kept separate. **No Polish source publishes a fixed veining surcharge % or zł** — none invented.
- **Concrete-vs-microcement guard (§11)**: thin-layer wall-applied concrete effect (1,5–3 mm decorative coating) kept strictly separate from microcement (Batch D MC_*; dekor-lux "Betonus"; konkret "połyskliwy mikrocement 220–380 zł/m² material"), prefab concrete panels (bursatm 200–400 zł/m²), cast-in-situ concrete, resin floors, limewash/wychmurzenia, tadelakt/trawertyn/sahara/japandi/alkantara — an explicit permanent exclusion list for 9E.4/9E.6.
- **Minimum-job / sample findings (§12–13)**: min 10 m² (KB), small-wall premium (VIAN; poilerobocizna 6 m² łazienka +30%, >50 m² −10–15%), sample `≥ 1 m²` required (konkret) / A4 próbka limitation (dekor-lux) — recorded as commercial context, never converted to m² rates, no sample fee invented.
- **Material system context (§14)**: DERIVED MATERIAL CONTEXT with formulas — natural lime Venetian 59–83 zł/m² (`590–830/10 m²`), synthetic acrylic set 30–46 zł/m², Stiuk Wenecki Magnat retail 14–22 zł/m² (140–220/5 kg → 10 m²), concrete-effect dry mix 95–420 zł/m² (18–75 zł/kg × 4,5–5,5 kg/m²), sealing 4–22 zł/m² — manufacturer/store/retail context only, never labor.
- **OWN_PRICE candidates after research**: **CENNIK_DEC_VEN_MAR-01 (veined marble)** — the strongest Batch E candidate (no veined-LABOR market row); derive from own workshop man-hours at 9E.4/9E.5 with S12's 350–550 L+M as sanity window. VEN/CONC/GENERIC have defensible national LABOR ranges (not OWN_PRICE); local (Kraków) coefficients (± big-city premium) remain an owner/9E.4 decision. No new catalog rows proposed (9E.4 owns catalog restructuring).
- **Cross-check passed (9E.3E §19)**: all 4 canonical items researched (codes verbatim from catalog §11); exact URLs; LOCAL (0 priced) vs regional-serving-Kraków (2) vs national (~16) separated; LABOR vs MATERIAL vs L+M separated (labor ranges only from labor-labelled rows; no material-subtraction derivation); classic vs veined Venetian strictly separated (surrogate evidence flagged); concrete effect not mixed with microcement/panels/resin (§11); generic row limited to structural/colored/rustykalny 40–80 (`COMMON_DECORATIVE_CONTEXT` documented — travertine/metallic/stone kept as context); substrate prep documented per source and kept out of labor rows; minimums/small-area/sample excluded from unit ranges; artistic/custom work not normalized (no invented surcharge); no invented prices (content-network clones counted zero); VAT UNKNOWN across sources (no automatic base conversion). §17 NORMALIZATION_REVIEW_NOTE flags for 9E.4 — **Batch A/B items (1)–(5), Batch C items (6)–(9), Batch D items (10)–(19) preserved untouched** + new Batch E items (20)–(29): (20) classic vs veined Venetian kept separate; (21) `stiuk syntetyczny` vs natural lime never priced alike; (22) quoting-mode mixes in national guides (poilerobocizna table = robocizna z materiałem vs intro robocizna) — only labor-labelled rows feed LABOR; (23) generic "tynk dekoracyjny" technology breadth — range only from structural/colored/rustykalny family, GENERIC-01 range-vs-OWN_PRICE decision pending; (24) artistic complexity (veining, szalunek +35–50%, multi-color) documented, never normalized into a premium %; (25) substrate-prep inclusion variance (L+M systems assume "gotowe podłoże"; labor rows exclude prep) — prep belongs to PREP/SKIM Batch A rows; (26) small-job/min-m² pricing recorded as context only (10 m² min, +30% small-wall, >50 m² −10–15%, sample ≥1 m²); (27) concrete-effect vs microcement contamination guard (permanent boundary, §11); (28) KB.pl Kraków city-row is national-portal city mapping (min 10 m² kompleksowa white/gray), L+M sanity window only — same class as Batch C (9)/Batch D notes; (29) content-network duplication (cudaarchitektury/mebloweporady/forummeble one skeleton; `*tynki` family; SEO-poradnik labor guides — count as differing data points, not 4 confirmations; cenauslug 410 / cudaarchitektury 403 archival).
- **Verification**: `git diff --check` PASS; committed as **`docs(stage-9): research Krakow decorative finish prices`** and pushed to `origin/stage-9`; working tree clean; `main` untouched. **Canonical Stage 9 remains In Progress**; **9E.3 Web Research (Batches A–E) is COMPLETE**; **9E.4 (normalization/review) PENDING** — next sub-stage requires explicit owner approval; Stage 10 remains **Pending**. **Deliberately NOT implemented in 9E.3E**: any prices, seeds, migrations, backend/frontend code; no catalog restructuring (deferred to 9E.4); no OWN_PRICE assignments (9E.4/9E.5).

#### 9D.1 execution status 2026-09-14 — mobile shell + Telegram dark theme UX correction (COMPLETE — owner accepted; committed as **`c4cc6b6 fix(stage-9): improve mobile shell and Telegram dark theme`** and pushed to `origin/stage-9`)**
**Context — two owner-reported issues (owner reported at the 9D.2/9D.1 planning review):**
1. **Issue A**: the large authenticated-user diagnostic card ("Telegram zweryfikowany / Telegram User ID / Nazwa użytkownika / UUID") consumed the top of the main page content — the owner asked to remove it from the normal page flow and move account access to a compact footer control.
2. **Issue B (systemic)**: in Telegram dark theme, typed text in form controls (e.g. Price Book → "Dodaj pozycję") was invisible: controls rendered a light/white background while typed text inherited the light Telegram theme text color. Owner asked for a systemic fix across `input`/`select`/`textarea` — not a one-off "Nazwa" input patch and not a global `color: black` forced style.

**Deliverable**: frontend-only correction (no backend, no API contract, no PriceItem model, no seeds, no researched-price values touched). Per the 9D.1 gate the changes were first left uncommitted for the owner's manual Telegram WebView verification; after owner acceptance the full 9D.1 change set (7 modified files + 2 new files below) was committed as **`c4cc6b6 fix(stage-9): improve mobile shell and Telegram dark theme`** and pushed to `origin/stage-9`; working tree clean; `main` untouched.

**Issue A implementation**:
- Removed the `<section aria-label="user-card">` authenticated-user diagnostic card from `frontend/src/App.tsx`.
- Added a compact **app footer** (`aria-label="app-footer"`, bottom of the app supply, below `<main>`) showing the app title and a `min-h-11` **"Konto" / "Аккаунт"** control (`aria-label="open-account"`), themed via `--tg-theme-*` variables. No duplicated auth logic — it consumes the existing `useAuth()` `user` / `isDevAuth` state.
- Created **`frontend/src/components/AccountModal.tsx`** — a lightweight mobile-friendly modal (no new dependency) reusing existing project conventions: `role="dialog"` + `aria-modal="true"`, backdrop-click close, explicit close button (`aria-label="close-account-modal"`, label `t.common.close` "Zamknij"/"Закрыть"), ESC keydown close, no horizontal overflow, `break-all` on the UUID and Telegram User ID, `min-h-11` touch targets, panel themed with `--tg-theme-secondary-bg-color` / `--tg-theme-text-color` / `--tg-theme-hint-color` / `--tg-theme-link-color` / `--tg-control-border-color`. Shows verification badge (Mock Auth / Telegram zweryfikowany), Telegram User ID, username (when present), UUID.
- PL/RU labels added to `frontend/src/locales/pl.json` / `ru.json` (`auth.account`, `auth.account_title`, enforced-enumerated `auth.telegram_verified`, `auth.telegram_user_id`, `auth.username`, `auth.uuid`); parity locked by the new parity test case in `frontend/src/locales/parity.test.ts`.

**Issue B implementation (systemic form-control theming)**:
- Added **8 control theme variables** to `:root` (light) and `html[data-color-scheme='dark']` in `frontend/src/index.css`: `--tg-control-bg-color`, `--tg-control-text-color`, `--tg-control-placeholder-color`, `--tg-control-border-color`, `--tg-control-focus-border-color`, `--tg-control-focus-ring-color`, `--tg-control-disabled-bg-color`, `--tg-control-disabled-text-color` (dark theme: dark `#232e3c` control bg + light `#f5f5f5` text + visible `#4b5f75` border + secondary placeholder + visible focus ring, and vice versa for light). The same variables were added to `DEFAULT_LIGHT_THEME`/`DEFAULT_DARK_THEME` in `frontend/src/hooks/useTelegramWebApp.ts` so `applyTelegramTheme()` applies them at runtime from Telegram themeParams.
- Added **`html { color-scheme: light }`** / **`html[data-color-scheme='dark'] { color-scheme: dark }`** so the browser renders native popups (select dropdowns, autofill) in the matching scheme.
- Added **un-layered systemic rules** in `index.css` (outside any Tailwind `@layer`, so they beat layered utility classes like `bg-white`/`border-slate-200` without touching component markup): `input, select, textarea` bg/text/border/caret; `::placeholder` visibility; `:focus` border + ring; `:disabled`; `:read-only`; `:-webkit-autofill` (1000px inset shadow + `-webkit-text-fill-color` to keep autofill readable in both themes). No `!important`, no global black text. Selects (category/unit/scope/quality in Price Book) inherit the same bg/border/text rules for closed, selected, and disabled states.

**Scope discipline**: UI correction only. No `PriceBook.tsx` behavior changed, no price formatting, no archive/restore, no search/filter, no PriceItem model/schema, no Alembic migration, no seed logic, no researched prices, no canonical-roadmap changes.

**Files**: modified — `frontend/src/App.tsx`, `frontend/src/App.test.tsx`, `frontend/src/hooks/useTelegramWebApp.ts`, `frontend/src/index.css`, `frontend/src/locales/parity.test.ts`, `frontend/src/locales/pl.json`, `frontend/src/locales/ru.json`; new — `frontend/src/components/AccountModal.tsx`, `frontend/src/App.shell.test.tsx`.

**Tests (NEW/EDITED)**:
- **`frontend/src/App.shell.test.tsx`** (8 tests, Stage 9D.1): A) no `user-card`/Telegram ID in the normal page flow and navigation remains first; B) compact `open-account` control exists inside the `contentinfo` footer; C) opening shows verification badge + name + Telegram User ID + username + UUID; D) close restores the underlying page via close button and ESC; E) RU localization (`Аккаунт`, `Данные пользователя`, `Telegram подтверждён`, `Имя пользователя`), RU keeps technical "Telegram User ID"; F) Price Book "Dodaj pozycję" form still opens with all 6 fields and survives account-modal open/close; G) readable light control theme vars (`bg` ≠ `text`); H) readable dark theme control vars (`#232e3c` bg ≠ `#f5f5f5` text, border present).
- **`frontend/src/locales/parity.test.ts`** — new 9D.1 case asserting identical PL/RU `app`/`auth`/`common` key structure + presence of the six 9D.1 account keys.
- **`frontend/src/App.test.tsx`** — completion markers switched from `user-card` content to the `open-account` footer control.

**Verification**: focused vitest run PASS; full frontend vitest **279 passed (22 files)** (was 278 across 22 files; +1 net after adding 8 shell tests and adjusting App tests); `tsc --noEmit` PASS; `vite build` PASS; dev-server smoke PASS (HTTP 200 on `/`); `git diff --check` PASS (two untracked new files included); backend pytest untouched (no backend source changed). Manual Telegram-viewport checks were completed by the owner per the acceptance checklist. **Deliberately NOT implemented**: any backend/API/seed/migration change, any researched market price, any unrelated UI redesign, canonical Stage 9 roadmap changes. **OWNER_ACCEPTANCE: ACCEPTED 2026-09-14** — owner verified in the real Telegram WebView (dark theme inputs/selects readable, typed text visible, large user card gone, footer account control reachable, modal data correct, at ~390/412 px) and authorized the commit; committed as **`c4cc6b6`** and pushed to `origin/stage-9`; working tree clean. **STAGE_9E4: Completed 2026-09-14 (normalization/review — docs-only).** Canonical Stage 9 remains **In Progress**; Stage 10 remains **Pending**.

#### 9E.4 execution status 2026-09-14 — normalize & review the Kraków price research catalog (COMPLETE; documentation only; committed + pushed to `stage-9`)

**Deliverable**: the normalized master review for all **51/51** canonical research items in
`docs/price-research-catalog.md` (new **PART 9E.4**, §16.1–16.7). It assigns exactly one decision to
every item — **MARKET_SUPPORTED (26) / OWN_PRICE (15) / DROP_MERGE_RESTRUCTURE (10)** — preserving the
architectural invariant **`PriceItem.price` (owner/commercial price) ≠ market reference ranges ≠ source
quoted prices**. No prices, seeds, migrations, API, or frontend behavior were changed; the four
technical placeholder seeds from 9B (`CENNIK_PREP_GENERIC_M2` / `CENNIK_PAINT_GENERIC_M2` /
`CENNIK_REVEAL_GENERIC_M2` / `CENNIK_REVEAL_GENERIC_LM`) remain untouched; all 9E.3 raw research
(batches A–E) is preserved verbatim.

- **Decision totals**: MARKET_SUPPORTED **26** · OWN_PRICE **15** · DROP_MERGE_RESTRUCTURE **10** ·
  TOTAL **51**.
- **Master table** (§16.3): one row per item with code, PL name, category, unit, scope, quality
  hint, decision, normalized market_min/max, reference_price, region basis, confidence, source
  count, and a normalization note; `—` used everywhere the evidence does not justify a numeric value
  (no forced prices).
- **OWN_PRICE rationale** (§16.4): (7) normally bundled / internally priced (PREP_PROT, PREP_DEGR,
  PREP_CLEAN, SKIM_LOCAL, GK_SCREW, PAINT_MASK, PAINT_MULTI); (3) technology-specific evidence gap
  (PREP_FLEECE, GF_FLIZ_L, GF_FLIZ_M — tech-B fiberglass wallpaper never substituted for tech-A
  fleece); (3) component-only / custom-premium market (PRIM_ADH, PRIM_HIGH, DEC_VEN_MAR); (2) no
  local (Kraków/Małopolskie) basis for labor-only microcement (MC_WALL_L, MC_FLOOR_L).
- **DROP_MERGE_RESTRUCTURE — proposed structural corrections** (§16.5): SKIM_3L → 2-coat + 3rd-layer
  add-on; SKIM_PKG → re-scoped package or merge into SKIM_2L + SAND (component-sum mismatch 65–91 vs
  35–70); GK_JOINT → LM unit model; REV_PREP/SKIM/SAND/PAINT/PAINT_LM → fold into the single canonical
  LM reveal row (REV_WORK_LM keeps the market band 30–110, ref 60); MC_STAIRS → unit model decision
  (M2 vs per-step vs per-flight); DEC_GENERIC → restrict/rename to structural/rustykalny family or drop.
- **Known-issues resolution map** (§16.6): every previously flagged issue A–G (SKIM package/3-layer/
  cleaning/crack repair; painting coat-count/ceiling/colour/masking/multi-colour; drywall Q1–Q4 unit
  and source conflicts/screw/corner; glass-fiber flizelina vs tech-B; reveal bundle/LM-vs-M2/5F;
  microcement labor-vs-system/hydro/stairs/minimum-jobs/Festfloor; decorative classic/veined/conc/
  generic/material-vs-labor/complexity) is mapped to a decision.
- **Owner decisions required** (§16.7): **7 grouped decision sets** — (1) reveal row structure;
  (2) OWN_PRICE starting rates for the 15 items; (3) SKIM package/layer structure; (4) GK joint unit
  model; (5) MC_STAIRS unit; (6) DEC_GENERIC scope; (7) regional (big-city) pricing policy. These are
  the blocking inputs for 9E.5.
- **Also in this sub-stage**: `docs/development-progress.md` updated (9D.1 marked OWNER_ACCEPTED with
  commit `c4cc6b6`; Stage 9 status rows updated; 9E.4 record added); `docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md`
  gained one concise verified production-deployment + Telegram Menu Button `?v=` cache-busting section.
- **Verification**: `git diff --check` PASS; only documentation files changed (no application code);
  committed as **`docs(stage-9): normalize Krakow price research catalog`** and pushed to
  `origin/stage-9`; working tree clean; `main` untouched. **Deliberately NOT implemented**: any
  PriceItem/seed/migration change (9E.6/9E.7), any API/frontend behavior change, any replacement of
  the four 9B technical placeholder seeds, any invented market prices. **STAGE_9E.5: NOT STARTED** —
  next sub-stage requires explicit owner approval and answers to the §16.7 owner-decision groups.
  Canonical Stage 9 remains **In Progress**; Stage 10 remains **Pending**.

#### 9E.5 execution status 2026-09-14 — owner approval of the normalized catalog (COMPLETE / OWNER_APPROVED; documentation only; committed + pushed to `stage-9`)

**Deliverable**: binding owner answers to all 7 decision groups of 9E.4 §16.7, recorded in
`docs/price-research-catalog.md` (new **PART 9E.5**, §17.1–17.4) and frozen as the final
implementation-ready catalog definition that 9E.6 (implementation / PriceItem seeds) and 9E.7 (load)
must honor.

- **Owner approval record (§17.1, all 7 groups APPROVED)**: (1) **SKIM_3L** — no standalone
  market-priced 3-coat row; base = SKIM_2L + third-coat add-on; (2) **SKIM_PKG** — DROP/MERGE, no
  package PriceItem, Stage 10 composes packages from atomic items; (3) **GK_JOINT** — LM canonical
  unit for linear joint evidence, Q3/Q4 full-surface stays M2, no LM↔M² conversion;
  (4) **GF_FLIZ_L / GF_FLIZ_M** — OWN_PRICE, flizelina malarska kept separate from fiberglass wall
  covering, owner rates supplied separately; (5) **REVEALS** — REV_WORK_LM is the principal
  commercial row, REV_PREP / REV_SKIM / REV_SAND / REV_PAINT / REV_PAINT_LM fold in as internal/helper
  only, Stage 5F geometry keeps both LM and M2, no automatic LM↔M² conversion; (6) **MC_STAIRS** —
  canonical unit PCS / per step, M2/per-flight/per-step observations reference-only, initial owner
  price OWN_PRICE; (7) **DEC_GENERIC** — rename/restrict to tynk strukturalny / rustykalny, never a
  catch-all for Venetian / concrete-effect / microcement or other distinct technologies.
- **Final implementation-ready catalog (§17.2–17.3)**: single source of truth = §16.3 as amended by
  §17.1 decisions; §17.3 disposition table covers all 51 reviewed rows.
- **Recalculated counts (§17.4) — original review vs final implementation set**:
  - Original research catalog (9E.4 review): **51** items — 26 MARKET_SUPPORTED / 15 OWN_PRICE /
    10 DROP_MERGE_RESTRUCTURE.
  - Final implementation PriceItem candidates (post-approval): **44** — **28 MARKET_SUPPORTED** /
    **16 OWN_PRICE**.
  - Dropped (2): SKIM_3L, SKIM_PKG. Folded/merged into REV_WORK_LM (5): REV_PREP, REV_SKIM,
    REV_SAND, REV_PAINT, REV_PAINT_LM. Restructured but retained (3): GK_JOINT → LM (MS),
    MC_STAIRS → PCS/OWN_PRICE, DEC_GENERIC → renamed/restricted (MS).
  - Total check: 44 + 7 = 51. The final implementation count is deliberately **not forced to 51**.
- **Also in this sub-stage**: `docs/development-progress.md` status rows updated (roadmap row and
  Stage Log header now show 9E.5 Completed / OWNER_APPROVED; 9E.6 NOT STARTED).
- **Verification**: `git diff --check` PASS; only documentation files changed — no application code,
  no migration, no seed implementation, no Stage 9E.6 work — and committed as
  **`docs(stage-9): approve normalized price catalog`** and pushed to `origin/stage-9`; working tree
  clean; `main` untouched. The four 9B technical placeholder seeds (`CENNIK_PREP_GENERIC_M2` /
  `CENNIK_PAINT_GENERIC_M2` / `CENNIK_REVEAL_GENERIC_M2` / `CENNIK_REVEAL_GENERIC_LM`) remain
  untouched through 9E.5. **STAGE_9E.6: NOT STARTED** — next sub-stage requires explicit owner
  approval. Canonical Stage 9 remains **In Progress**; Stage 10 remains **Pending**.

#### 9E.6A execution status 2026-09-14 — price market evidence backend foundation (COMPLETE; committed `31540af` on `stage-9`)

**Deliverable**: backend foundation for the market-evidence layer designed in 9E.1 — the
`PriceMarketReference → PriceSource[]` models, the reversible Alembic migration `0015_create_market_evidence`,
owner-scoped domain-service operations, and a read-only evidence endpoint. Per the task contract the 44
approved PriceItem catalog rows were **NOT** loaded here (that is 9E.6B); the four 9B technical placeholder
seeds remain untouched.

- **Models** (`app/models/market_evidence.py`): `SourceType` (7 controlled values), `PriceMarketReference`,
  `PriceSource`. FK chain `price_items` (CASCADE) → `price_market_references` (CASCADE) → `price_sources`;
  money stays `Numeric(12,2)` Decimal end-to-end; unit/currency reuse the Stage 9B contracts; no currency DB
  enum (ISO-style `String(3)`, PLN-only MVP), no revision/version columns (re-check-in-place).
- **Migration** `0015_create_market_evidence` (parent `0014_create_price_book`): creates both tables, the
  `sourcetype` enum, and the FK indexes; reuses the existing `priceunit` enum via `create_type=False`; single
  head; downgrade removes **only** the 9E.6A objects. **Migration cycle PASS** (local dev Postgres):
  upgrade → `0015`; downgrade `0015→0014` (all 6 pre-existing `price_items` rows and the `priceunit` /
  `qualitylevel` / `pricecategory` / `pricescope` enums survive); re-upgrade → `0015`; single head.
- **Service** (`app/domain/services/price_book_service.py`): `validate_amount` (same finite / >=0 / at-most-2dp
  rule set as `validate_price`, never silently rounding), MVP region contract (`Kraków` / `Małopolskie` /
  `Kraków / Małopolskie`), per-source quoting-mode validation (exactly one of SINGLE / RANGE / QUALITATIVE;
  QUALITATIVE requires a non-blank note), `create_market_reference_with_sources` (>=1 source; reference
  unit/currency must equal the parent PriceItem), `get_market_references` (0..N, newest research first),
  `update_market_reference` (re-check-in-place; never touches `PriceItem.price`); `MarketReferenceNotFoundError`
  added to `app/domain/exceptions.py`.
- **API** (`app/api/v1/endpoints/pricebook.py`): `GET /api/price-items/{price_item_id}/market-reference` →
  `{items, total}` with nested sources; Decimal money serialized as JSON strings (never binary floats); missing
  evidence returns `200` + empty list; foreign/unknown items return the uniform `404`; unauthenticated → `401`.
  No public evidence write API in 9E.6A; `PATCH /api/price-items` cannot mutate evidence.
- **Tests** (`tests/test_market_evidence.py`, 46 new focused tests, all PASS): model/DB invariants, Decimal
  exactness, quoting modes, ownership isolation (foreign `404`, unauthenticated `401`, no source leak), API
  serialization, archived-evidence readability, DB-level cascade on hard-deleted items while soft
  archive/restore preserves evidence, and the invariant regression that every evidence create/update leaves
  `PriceItem.price` untouched. Full backend suite: **458 passed, 0 failed**.
- **Also**: `tests/conftest.py` enables `PRAGMA foreign_keys=ON` on the in-memory SQLite engine so the
  documented ON DELETE CASCADE behavior is exercised against a Postgres-shaped constraint set.
- **Deferred**: loading the 44 approved catalog rows (now 9E.7); owner-price/evidence load, seed wiring
  (9E.7); CI/deploy. **Verification**: `git diff --check` PASS; only the 9E.6A backend implementation and
  this record changed — committed as **`feat(stage-9): add price market evidence backend`** (`31540af`) and
  pushed to `origin/stage-9`. **STAGE_9E.6B: NOT STARTED (at that time); STAGE_9E.7: NOT STARTED** — next
  sub-stages require explicit owner approval. Canonical Stage 9 remains **In Progress**; Stage 10
  remains **Pending**.

#### 9E.6B execution status 2026-09-14 — mobile price market evidence UI (IMPLEMENTED; uncommitted — awaiting owner acceptance)

**Deliverable**: compact mobile-first, read-only market-evidence presentation on the existing editable
Price Book. Per the explicit owner instruction for this sub-stage, **9E.6B = the evidence UI**; the 44
approved catalog rows are **NOT** loaded here (deferred to the later 9E load), and the four 9B technical
placeholder seeds remain untouched.

- **Frontend (new)**: `types/marketEvidence.ts` (typed contract mirroring the 9E.6A `PriceMarketReferenceRead`
  / `PriceSourceRead` schemas, money as Decimal JSON strings), `api/marketEvidence.ts` (read-only
  `GET /api/price-items/{id}/market-reference` client), `hooks/useMarketEvidence.ts` (session-scoped
  per-item cache — each item fetched at most once per mount, reused across tab/search/filter re-lists,
  no per-render N+1 loop; failed fetch degrades to a silent `error` entry so the page never breaks),
  `components/PriceBookMarket.tsx` (secondary market summary + progressive sources disclosure),
  `utils/evidenceFormat.ts` (deterministic `DD.MM.YYYY` evidence dates).
- **Frontend (changed)**: `components/PriceBook.tsx` — each card shows a small "Moja cena" / «Моя цена»
  eyebrow above the unchanged owner price (still the only primary value), then a secondary market block:
  localized `Rynek`/«Рынок` range (`formatPrice` 2-dp size `market_min–market_max`, PLN, unit-matching
  the reference), `Sprawdzono`/«Проверено` date, optional `Punkt odniesienia`/«Ориентир` line, and a
  `Źródła (N)`/«Источники (N)` toggle that expands a compact inline source list (name, localized source
  type, region, SINGLE/RANGE quote or QUALITATIVE note, checked date, optional external link with
  `rel="noopener noreferrer"`). No evidence → small muted `Rynek: Brak danych rynkowych` / «Нет рыночных
  данных` state; loading → compact muted line; error → section collapses. `locales/pl.json` + `ru.json`:
  `pricebook.market.*` including the seven localized `SourceType` labels (parity test keeps PL/RU
  structurally identical).
- **Contract preserved**: market evidence is strictly read-only research data. Add/Edit PriceItem forms
  expose **no** market fields; `PATCH /api/price-items` still edits only the owner working price. No
  estimate behavior; no client-side average calculation; market range never transforms into the owner's
  price. No backend bulk endpoint was needed — the existing per-item endpoint makes the UI usable.
- **Tests**: new `PriceBook.market.test.tsx` — **20 focused tests PASS** (owner-price primary, market
  range, checked date, source count, disclosure open/close, SINGLE/RANGE/QUALITATIVE formatting, missing
  URL, URL action, localized source types PL/RU, no-evidence state, optional reference price,
  archived-item evidence, loading state, API-failure resilience, PL↔RU label switch, no market fields in
  Add/Edit forms, owner-price edit unchanged). Existing `PriceBook.test.tsx` untouched and PASS.
- **Verification**: full frontend suite `vitest` **298 passed / 0 failed**; `tsc --noEmit` PASS;
  `vite build` PASS; `git diff --check` PASS. **No backend files changed.** Manual Telegram acceptance at
  390/412 px pending owner review (checklist in the 9E.6B task brief).
- **Deferred**: loading the 44 approved catalog rows; owner-price/evidence seed wiring (9E.7); CI/deploy.
  **STAGE_9E.7: NOT STARTED** — next sub-stage requires explicit owner approval. Canonical Stage 9 remains
  **In Progress**; Stage 10 remains **Pending**.

#### 9E.7 execution status 2026-09-15 — load approved 44-row catalog + market evidence + nullable price (IMPLEMENTED; uncommitted — awaiting owner acceptance)

**Deliverable**: replaces the four 9B *technical placeholder* seeds (`CENNIK_*_GENERIC_*`, prices
1.11/2.22/3.33/4.44) with the owner-approved 44-row catalog and materializes the approved market evidence
for the 28 MARKET_SUPPORTED rows, idempotently. Owner-locked precision policy: **OWNER PRICE ≠ MARKET RANGE ≠
SOURCE QUOTED PRICE** — no market value is ever written into `PriceItem.price`; every canonical row seeds
`price = NULL` ("Do ustalenia" / «Уточняется»), `0.00` remains a real, explicitly set zero (never a "not set"
sentinel), and `reference_price` stays evidence-only.

- **Backend — seed data (new)**: `domain/data/price_book_seed.py` rewritten — `PriceItemSeed`
  (`price: str | None = None`), `PriceSourceSeed`, `MarketReferenceSeed`;
  `build_approved_price_book_items()` → **44 canonical rows (28 MARKET_SUPPORTED / 16 OWN_PRICE)**, each
  `price=None`, `name_key = pricebook.seed.<stem>`, category/unit/scope per catalog §16.3 + 9E.5 decisions;
  quality seeded only for unambiguous single-tier rows (**GK_FULL → Q3**, **GK_Q4 → Q4**; GK_JOINT/SKIM_SQ
  dual hints stay NULL); `build_approved_market_references()` → **28 references / 112 sources**, every URL
  copied verbatim from `docs/price-research-batch-{a..e}.md` + the catalog (a docs-corpus test asserts all
  112); `LEGACY_GENERIC_CODES` (the four 9B GENERIC codes). The Stage 9B
  `build_technical_baseline_price_items()` is deleted.
- **Backend — service (changed)**: `price_book_service.ensure_owner_catalog` extended — inserts missing canonical
  seeds (`price=NULL`), **retires** legacy GENERIC rows once on bootstrap (`is_archived=True`; ids/edits/name_key
  preserved; never deleted), and **reconciles evidence idempotently by content-key** (region + unit + quantized
  min/max/ref + checked_at + methodology_note; per-source top-up by full content tuple — a reference/source is
  never duplicated). Second bootstrap returns `[]` and never overwrites owner edits. The 16 OWN_PRICE rows get
  **no** numeric ranges (UI keeps "Brak danych rynkowych"); GF_FLIZ_L/M and MC_STAIRS carry no authored evidence;
  SKIM_CRACK (LM) and GK_JOINT (LM) preserve their own units with no LM↔M² conversion.
- **Backend — nullable price (9E.7 owner decision, one explicit override)**: new migration
  `alembic/versions/0016_make_price_nullable.py` (over `price_items.price`): NULL allowed = owner commercial
  price not set yet; 0.00 stays a real price; `PriceItemRead.price` becomes nullable in the API JSON; custom
  create still requires an explicit price; PATCH can set a real price later; explicit null via PATCH is a no-op;
  nothing ever converts NULL → 0.00 and no estimate engine reads `PriceItem.price` yet (Stage 10 will reject/flag
  null-priced lines — documented, no code now). Migration cycle verified on dev infra (NOT production): fresh
  scratch DB `plan_estimate_migration_check` on the dev postgres container → `upgrade head` → `downgrade -1` →
  `upgrade head` all PASS, then the scratch DB was dropped. (Revision id renamed to the 25-char
  `0016_make_price_nullable` — the initial working id exceeded `alembic_version.version_num VARCHAR(32)`.)
- **Frontend (changed)**: `types/priceItem.ts` — `PriceItem.price: string | null` (create payload stays
  required); `components/PriceBook.tsx` — a null price renders localized `pricebook.price_not_set`
  ("Do ustalenia" / «Уточняется»), `0.00` renders `0,00 zł` via the existing `formatPrice`, and editing a null
  seed row opens with an empty price field (`item.price ?? ''`) so the owner can enter a price;
  `locales/pl.json` + `ru.json` — the 44 canonical `pricebook.seed.*` keys replace the 4 legacy GENERIC keys
  (values verbatim from catalog §3–§11 row tables; parity test now asserts all 44).
- **Tests**: new `test_price_book_catalog_9e7.py` (catalog seed / bootstrap / evidence seed incl. the
  docs-verbatim URL corpus check / idempotency / owner isolation / API envelope), new
  `test_price_item_nullable_price.py` (null persists, 0.00 ≠ null, PATCH sets a real price on a null seed row,
  no NULL→0 conversions, custom create still requires a price), new `PriceBook.nullprice.test.tsx` (null →
  price_not_set PL/RU, 0.00 → "0,00 zł", editing a null row submits a real price, seeded name_key resolves).
  Focused backend price-book/evidence files: **175 passed**. Full backend suite: **515 passed / 0 failed**.
  Full frontend suite: **304 passed / 0 failed**; `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` PASS.
- **Deferred**: Stage 10 null-priced-line flagging (documented above, no code now); CI/deploy; manual Telegram
  acceptance at 390/412 px pending owner review. **STAGE_9F: NOT STARTED** — the next stage requires explicit
  owner approval. Canonical Stage 9 remains **In Progress**. The 9E.7 change set was committed by the owner as
  **`feat(stage-9): seed approved price catalog and market evidence`** (`097e46c`).

#### 9E.7.1 execution status 2026-09-15 — Price Book add/edit form visibility regression (IMPLEMENTED; uncommitted — awaiting owner acceptance)

**Defect**: the Stage 9E.7 catalog load made the Price Book list 44 rows long, which exposed a UI regression in
the add/edit workflow. The form is rendered *above* the list, so tapping **Opcje → Edytuj** on a card deep in
the catalog opened the editor far above the current scroll position: on a phone the user saw the options panel
close and **nothing else happen**, and Edit appeared to be broken. The form state itself was always correct —
only its visibility was wrong. This affects Edit and Add equally.

- **Frontend (changed)**: `components/PriceBook.tsx` — a `useLayoutEffect` keyed on `showForm` scrolls the form
  into view through a new `formRef` (`scrollIntoView({ behavior: 'smooth', block: 'start' })`). The call is
  optional-chained (`formRef.current?.scrollIntoView?.(...)`) so environments without `scrollIntoView` (jsdom)
  are unaffected. No other behavior, markup, or contract changed; no market/price semantics touched.
- **Tests**: `components/PriceBook.test.tsx` — new focused block **"PriceBook — opened form visibility (Stage
  9E.7.1)"** with **2 regression tests** (form scrolled into view on Edit, and on Add). Each stubs
  `Element.prototype.scrollIntoView` (absent in jsdom) and asserts the call targets the form element. Both were
  confirmed to **FAIL with the effect removed** and PASS with it restored.
- **Verification**: focused PriceBook files (`PriceBook.test.tsx` 36 + `PriceBook.nullprice.test.tsx` 6 +
  `PriceBook.market.test.tsx` 20) **62 passed / 0 failed**; full frontend suite **306 passed / 0 failed**
  (304 → 306); `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` PASS. **No backend file changed.**
- **Manual real-browser verification (390 × 844, headless Chromium over CDP)**: run against an isolated stack — a
  temporary backend on `:8001` pointed at the 9E.7 database `plan_estimate_e71` (migration `0016`, 44 active
  rows, all `price = NULL`) plus a temporary Vite server on `:5174`; the owner's running containers on `:8000` /
  `:5173` were **left untouched** (the long-running `plan_estimate` DB is still on migration `0015` and was not
  modified). Tapping Opcje → Edytuj on the **last of 44 rows** reproduces the defect: without the effect
  `scrollY` stays at `7693` while the form sits at document Y `433` — roughly **7 260 px above the viewport**, so
  it is invisible. With the fix the page smooth-scrolls to `433` and the form top lands at `0`, fully on screen
  (form rect `0–511` inside the 844 viewport); a screenshot confirms the "Edytuj pozycję" heading, every field,
  and the Anuluj / Zapisz buttons are visible, with the edited row's `Nazwa bazowa: …` hint and `mb` unit
  intact.
- **Observed, not changed**: the scroll animates for roughly 1.4 s (smooth) across a ~7 100 px jump; flagged for
  the owner's acceptance rather than altered here.
- **Deferred**: owner manual Telegram acceptance at 390/412 px; Stage 10; CI/deploy. **STAGE_9F: NOT STARTED.**
  Canonical Stage 9 remains **In Progress**. The 9E.7.1 change set was committed and pushed by the owner as
  **`fix(stage-9): make price book editor visible from long catalog`** (`f38cd13` on `stage-9`).

#### 9E.8 execution status 2026-09-15 — Price Book mobile UX cleanup (IMPLEMENTED; OWNER ACCEPTED)

Owner-directed mobile UX cleanup of the Price Book. **Backend, schema, market-evidence data and the approved
44-row catalog were not touched** — no new API, no migration, no data change. The spec's two STOP conditions were
checked and **not triggered**: the inline editor PATCHes only `{ price }` through the existing optional
`PriceItemUpdatePayload`, and the S/Q requirement is met with labelled option groups plus helper text (no
substrate column needed).

- **Frontend (added)**: `components/PriceSourceViewer.tsx` — a mobile bottom-sheet viewer for market sources
  (`role="dialog"`, `aria-modal`, dimmed backdrop tap-to-close, explicit 44 px close button, `Escape` handling,
  Telegram `--tg-theme-*` vars, wrapping source names/notes, tappable source URL). Sources are no longer rendered
  inline inside the card.
- **Frontend (changed)**: `components/PriceBook.tsx` — catalog rows (`name_key !== null`) open a **compact inline
  owner-price editor inside the same card** (`MOJA CENA` / `Cena` / unit read-only with a fixed-unit hint /
  `Anuluj`–`Zapisz`); only the commercial price is editable, all canonical metadata (name, category, unit,
  price_scope, quality, code) is display-only. Save PATCHes the owner price and updates the row in place without
  a reload (no page jump); cancel discards; validation errors render inside the editor. Custom rows keep the full
  add/edit form. The `Opcje` disclosure was replaced by direct `Edytuj` / `Archiwizuj` buttons (archived rows stay
  restore-only). The 9E.7.1 scroll-into-view effect is retained **only** for Add and custom-row edit, which still
  use the global form. The custom form gained an explicit `Kategoria` label and the quality selector is now split
  into labelled `S` / `Q` option groups with explanatory helper text defaulting to `Bez poziomu` — no class is
  ever inferred from the category. `components/PriceBookMarket.tsx` — the source disclosure now opens the viewer,
  keeping the card compact; market range, checked date and reference price are unchanged.
- **Frontend (i18n)**: `locales/pl.json` + `ru.json` — `display_name` → "Nazwa pozycji" / «Название позиции»,
  `price_scope` → "Cena obejmuje" / «Цена включает», plus new `quality_group_s`, `quality_group_q`,
  `quality_helper`, `unit_fixed_hint` and `market.viewer_title` in both locales (backend `PriceScope` enum
  untouched; key parity preserved).
- **Tests**: new `PriceBook — inline catalog price edit (Stage 9E.8)` and `PriceBook — form labels (Stage 9E.8)`
  blocks in `PriceBook.test.tsx` (inline open, no scroll, prefill, explicit 0.00, read-only canonical metadata,
  price-only PATCH, close-on-save, cancel, inline validation, archived restore-only, PL/RU labels, S/Q grouping,
  no inferred class); `PriceBook.nullprice.test.tsx` rewritten for the inline editor; `PriceBook.market.test.tsx`
  extended with viewer open/close, Escape, long-content wrapping and RU viewer-title coverage.
- **Verification**: focused PriceBook files **79 passed / 0 failed**; full frontend suite **323 passed / 0 failed**
  (306 → 323); `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` PASS. **No backend file changed.**
- **Manual real-browser verification (headless Chromium over CDP, 320 / 390 / 412 px)**: run against an isolated
  stack (temporary fixture API on `:8099` + temporary Vite dev server on `:5199`); the owner's containers on
  `:8000` / `:5173` were **left untouched**. **23/23 checks passed at each width**: 46-card catalog renders, no
  horizontal overflow, `Edytuj` on a deep catalog row opens the inline editor inside that card with no page
  movement (`scrollY` unchanged), canonical metadata controls absent, 44 px targets, save closes the editor and
  shows the new price in place, sources open in the viewer with no horizontal scrolling and wrapping content,
  close / Escape return to the same Price Book position, custom rows keep the full form, and archived rows stay
  restore-only.
- **Interpretation flagged for the owner**: per the owner's earlier decision, archived rows remain
  restore-only, so a catalog row on the Archived tab exposes no price editor (spec item 29 "appropriate
  owner-price edit behavior" is read as "no regression to the existing archived affordance"). The inline editor is
  offered on the Active tab.
- **Deferred / NOT done per instruction**: no commit, no push, no deploy — the owner handles Git and Docker.
  Stage 9 — COMPLETE / OWNER ACCEPTED
  Stage 10 — NOT STARTED.  Stage 10; CI/deploy.

### Stage 10A: Surface Work Planning + Estimate Architecture
- **Status**: Completed 2026-09-15 (architecture/documentation only; owner accepted) — **committed together with the 10A.1 corrections as `6bbc4ce`** — **superseded in part by the Stage 10A.1 canonical corrections below (the 10A.1 model text is authoritative)**
- **Date**: 2026-09-15
- **Commit**: `6bbc4ce` — `docs(stage-10): define surface work planning and estimate architecture` (10A + 10A.1 corrections committed together; pushed to `origin/stage-10`)

#### Added:
- `docs/stage-10-architecture.md` — full Stage 10 decision record: product goal, mobile-first UX contract, Work Plan domain (`SurfaceWorkPlan` + `SurfacePlannedWork`), multiple works per surface, substrate/quality ownership with Stage 6 enum reuse, apply-to-all-walls overwrite semantics, floor/ceiling support, Price Book reference relationship, Estimate domain (`Estimate` + `EstimateLine`), line origin, snapshot contract, quantity source+override, price override, NULL owner-price behaviour, labor/material classification (`LABOR/MATERIAL/LABOR_AND_MATERIAL`), materials MVP boundary, Decimal/rounding totals, WorkPlan→Estimate sync, Stage 11 / Stage 14 boundaries, 10A–10I execution plan, and the 18 required architecture decisions D1–D18.

#### Changed:
- `docs/development-progress.md` — Stage 10 roadmap row status → "In Progress — 10A Completed 2026-09-15 (docs-only; uncommitted — awaiting owner acceptance)" (since superseded — the Overview table now documents 10A + 10A.1 committed together as `6bbc4ce`).

#### Database:
- None — documentation-only stage. No Alembic migration. No schema change. New tables proposed for 10B: `surface_work_plans`, `surface_planned_works`, `estimates`, `estimate_lines` (+ enums `planstatus`, `estimatestatus`, `lineorigin`, `quantitysource`).

#### Tests:
- None executed in 10A — no application code. Full verification deferred to 10B onward.

#### Verification:
- `git status` clean before edit; diff limited to the two documentation files; no code/migration/build artifacts touched. STOP per instruction — no commit, no push.

#### Deferred:
- All application implementation (10B–10I), per the 10A execution plan in `docs/stage-10-architecture.md`. No commit/push/deploy.

### Stage 10A.1: Canonical Architecture Corrections (owner decision, pre-acceptance)
- **Status**: Completed 2026-09-15 (documentation only; owner accepted) — **committed together with 10A as `6bbc4ce`**
- **Date**: 2026-09-15
- **Commit**: `6bbc4ce` — `docs(stage-10): define surface work planning and estimate architecture` (10A + 10A.1 corrections committed together; pushed to `origin/stage-10`)

#### Added:
- Seven canonical corrections applied to `docs/stage-10-architecture.md` before owner acceptance:
  1. **Plan per physical surface** — `SurfaceWorkPlan` is 1:0..1 with `Surface` (`surface_id` UNIQUE NOT NULL); substrate/quality per surface; `SurfacePlannedWork` carries `work_plan_id` + `price_item_id` + `position` only (no `surface_id`). Four-wall example (gipsowa S3 / gipsowa S3 / beton S3 / GK Q3) supported natively; "apply to all walls" copies the planning configuration into the other walls' plans.
  2. **Plan quantity override removed** — `SurfacePlannedWork.quantity_override` dropped; canonical flow `Surface geometry → source_quantity → EstimateLine.quantity`; single override layer on the estimate line (`quantity_overridden`).
  3. **Manual lines do not require a PriceItem** — `lineorigin` = `PLANNED_WORK / PRICE_BOOK / MANUAL`; `price_item_id` NULL for MANUAL; manual line supplies description/classification/unit/quantity/unit_price/currency and never touches the Price Book.
  4. **LABOR / MATERIAL are the normal estimate model** — ROBOCIZNA + MATERIAŁY subtotals + RAZEM; `LABOR_AND_MATERIAL` remains supported as an exception/compatibility bucket (no split invented); Stage 9 `PriceScope` unchanged.
  5. **Versioning / regeneration** — no new version per click; DRAFT regenerates in place with explicit preview/confirmation; manual lines and owner overrides preserved; new version only for a meaningful commercial revision of an immutable document.
  6. All §24 decisions (D1–D18), the entity diagram, §26 acceptance scenario, and Appendix A updated; contradictory 10A text removed.

#### Changed:
- `docs/development-progress.md` — Stage 10 roadmap row status now includes the 10A.1 correction.

#### Database:
- None — documentation-only. Proposed 10B tables keep their names (`surface_work_plans`, `surface_planned_works`, `estimates`, `estimate_lines`) but are corrected: `planstatus` enum dropped (no plan status), `lineorigin` three-valued, `source_quantity` + `quantity_overridden` added to estimate lines, `quantity_override` removed from the plan.

#### Tests:
- None executed — no application code.

#### Verification:
- `git diff --check` clean; diff limited to the two documentation files; no code/migration/build artifacts touched. STOP per instruction — no commit, no push, no 10B.

### Stage 10B.1: Surface Work Plan Backend Domain
- **Status**: Implemented 2026-09-15 (backend domain only; **uncommitted — awaiting owner acceptance**; Git operations performed manually by the owner after acceptance)
- **Date**: 2026-09-15
- **Commit**: none yet — owner performs the commit/push after acceptance

#### Added:
- `backend/app/models/work_plan.py` — `SurfaceWorkPlan` (`surface_work_plans`: id UUID pk; `surface_id` FK → `surfaces.id` ON DELETE CASCADE UNIQUE NOT NULL — one plan per surface; `substrate` NOT NULL reusing the Stage 6 `substrate` enum; `quality_target` nullable reusing the Stage 6 `qualitylevel` enum; timestamps; `UniqueConstraint(surface_id)` = `uq_surface_work_plans_surface_id`) and `SurfacePlannedWork` (`surface_planned_works`: id UUID pk; `work_plan_id` FK → `surface_work_plans.id` ON DELETE CASCADE NOT NULL; `price_item_id` FK → `price_items.id` ON DELETE RESTRICT NOT NULL — reference only, no price copy; `position` Integer NOT NULL; timestamps; `UniqueConstraint(work_plan_id, position)` = `uq_surface_planned_works_work_plan_position`; indexes on work_plan_id, price_item_id, and (work_plan_id, position)). Self-contained ORM relationships (only inside the new file; `Surface` model untouched): `SurfaceWorkPlan.planned_works` (cascade all/delete-orphan, ordered by position) ↔ `SurfacePlannedWork.work_plan`, one-way `SurfacePlannedWork.price_item`.
- `backend/app/domain/services/work_plan_service.py` — `SurfaceWorkPlanService`: owner-scoped `get_work_plan` (plan with ordered works + linked price items, or None when the surface is unplanned), `set_plan` (upsert — creates or fully replaces the plan and its works in one atomic commit; substrate/quality validated via the Stage 6 `assert_quality_scale_valid`; an incompatible quality target on a substrate change requires explicit clearing), `replace_planned_works` (replaces only the works of an existing plan, preserving substrate/quality). Ownership resolves through `Surface → Room → Project → Owner` (Project/Room/SurfaceNotFound); every selected PriceItem must be owned and non-archived (archived items rejected for new selection; existing plan rows never mutated by archiving). Works rewritten via immediate DELETE then re-insert with position appended from 0 (avoids the SQLAlchemy insert-before-delete flush collision on the unique position constraint). Duplicate PriceItems allowed per the owner-accepted architecture decision (e.g. two coat rows) — only `UNIQUE(work_plan_id, position)`.
- `backend/app/schemas/work_plan.py` — `OrderedPriceItemSelection` (`price_item_id`; list order defines position; `extra="forbid"`), `SurfaceWorkPlanCreate/Update`, `SurfacePlannedWorkRead`, `SurfaceWorkPlanRead` (`from_attributes=True`).
- `backend/alembic/versions/0017_create_surface_work_plans.py` — migration creating `surface_work_plans` + `surface_planned_works` with reused `substrate`/`qualitylevel` enums (`create_type=False`), named constraints/indexes; reversible downgrade leaves the 0011-owned enum types intact.
- `backend/tests/test_surface_work_plan.py` — 44 focused tests (classes A–U): model/DB invariants, duplicate-PriceItem allowance, deterministic positioning, ownership isolation, S/Q scale compatibility, NULL quality, substrate-change explicit clearing, create/update/atomic-replace, archived-item new-selection rejection vs existing-row survival, reference-only (no price snapshot), NULL-price item valid for planning, per-surface plan independence, unplanned surfaces, cascade deletion, ordered reads, replace-only-works, quality persistence, two-coat rows.

#### Changed:
- `backend/app/models/__init__.py` — exports `SurfaceWorkPlan`, `SurfacePlannedWork`.
- `backend/app/domain/exceptions.py` — added `SurfaceWorkPlanNotFoundError`, `SurfaceWorkPlanValidationError`.

#### Database:
- New migration `0017_create_surface_work_plans` (down_revision `0016_make_price_nullable`): tables `surface_work_plans`, `surface_planned_works`; reused `substrate`/`qualitylevel` enum types; `surface_id` UNIQUE; `UniqueConstraint(work_plan_id, position)`; FK CASCADE (surface, plan) / RESTRICT (price item); indexes on work_plan_id, price_item_id, (work_plan_id, position). Applied to the local dev database: `alembic upgrade head` (0015→0016→0017) PASS; `downgrade -1` PASS (substrate/qualitylevel types preserved); re-`upgrade head` PASS; `alembic current` = `0017_create_surface_work_plans (head)`.

#### Tests:
- Focused `backend/tests/test_surface_work_plan.py`: **44 passed**.
- Full backend pytest: **559 passed** (was 515; +44).
- Frontend regression (untouched by this stage): vitest **328 passed (24 files)**; `tsc --noEmit` PASS; `vite build` PASS.
- `git diff --check` clean.

#### Verification:
- Migration cycle on real PostgreSQL PASS (upgrade 0015→0016→0017; downgrade →0016; re-upgrade →0017; DDL inspection confirms the exact target schema: unique surface constraint, unique (work_plan_id, position), CASCADE/RESTRICT FKs, all three indexes). Owner-decision honored: **no** `UNIQUE(work_plan_id, price_item_id)` — duplicate PriceItems allowed; no architecture-doc change. STOP per instruction — no commit, no push, no 10B.2.

#### Deferred:
- 10B.3+ / 10C+ (per the 10A execution plan in `docs/stage-10-architecture.md`): frontend Work Plan UI and the Estimate (`Estimate` + `EstimateLine`) domain/API. No commit/push/deploy.

### Stage 10B.2: Surface Work Plan HTTP API + Apply to All Walls
- **Status**: Implemented 2026-09-16 (backend HTTP API only; **uncommitted — awaiting owner acceptance**; Git operations performed manually by the owner after acceptance)
- **Date**: 2026-09-16
- **Commit**: none yet — owner performs the commit/push after acceptance

#### Added:
- `backend/app/api/v1/endpoints/work_plans.py` — thin owner-scoped router exposing the plan as a sub-resource of the physical Surface (matching the existing `/projects/{project_id}/rooms/{room_id}/surfaces/...` convention):
  - `GET /api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/work-plan` — returns the plan (substrate, quality_target, ordered planned works each embedding a compact Price Book summary: id/code/name_key/display_name/category/unit/price_scope/price/currency/is_archived/quality_level — no market evidence). **No plan → 404** (`{"detail": "Surface work plan not found"}`), matching the project's existing sub-resource 404 semantics; foreign/owned chains hidden as 404.
  - `PUT .../surfaces/{surface_id}/work-plan` — atomic upsert (`SurfaceWorkPlanUpsert`: `substrate`, `quality_target` nullable, ordered `price_item_ids`) delegating to the accepted 10B.1 `set_plan`: same item ID may repeat (two coat rows), positions appended 0..N-1, archived items rejected for new selection (422), NULL-price items selectable, foreign items hidden (404), S/Q scale validated via `assert_quality_scale_valid` — a substrate change with an incompatible quality value fails (422, no silent S→Q conversion; explicit NULL/quality clear required).
  - `POST .../surfaces/{source_surface_id}/work-plan/apply-to-room-walls` — canonical bulk action, WALL-only and atomic (single transaction, no per-wall commit): validates the source (owned, WALL, active, existing plan, no archived catalog item in the source plan), then copies substrate + quality_target + ordered planned works into every **other active (non-archived) WALL** in the same room as **independent persisted plan rows** (replace semantics). Never copies/changes geometry, openings/deductions, inspections, findings, risks, photos, archive state, or any Price Book row. Returns a compact `SurfaceWorkPlanApplyResult` (`source_surface_id`, `target_count`, `target_surface_ids` in `Surface.position` order, updated `targets` plans) enough for the future 10C confirmation toast. Empty target set → successful `target_count=0`; non-WALL source (FLOOR/CEILING/OTHER) → 422; no source plan → 404; archived item in the source plan rejects the whole batch atomically (source must be updated deliberately first); NULL-price source items copy fine (planning is independent of commercial completeness).
- `backend/tests/test_surface_work_plan_api.py` — 37 focused API tests (unauthenticated 401 ×3, GET A–E, PUT F–P, apply-to-all Q–AG, route-family registration guard).

#### Changed:
- `backend/app/schemas/work_plan.py` — added `SurfaceWorkPlanUpsert`, embedded `SurfacePriceItemSummaryRead` (+ `price_item` on `SurfacePlannedWorkRead`), added `SurfaceWorkPlanApplyResult`. Existing 10B.1 read serialization is unchanged apart from the new optional embedded summary.
- `backend/app/domain/services/work_plan_service.py` — added `apply_to_room_walls`: source validation (WALL, active, plan exists, all source items non-archived) before any mutation, targets selected as other active WALLs ordered by `Surface.position` (NULLS last) then id, per-target upsert via the existing `_rewrite_works`, one commit.
- `backend/app/api/deps.py` — added `get_work_plan_service`.
- `backend/app/main.py` — registered the work-plan router under `/api` (tag `work-plans`).
- `backend/tests/test_surface_work_plan.py` — added `TestV_ApplyToRoomWallsService` (service-level apply-to-all batch atomicity).

#### Database:
- **No new migration.** The accepted 0017 model (`surface_work_plans`, `surface_planned_works`) was sufficient; no schema change was required and none was created.

#### Tests:
- Focused `backend/tests/test_surface_work_plan_api.py`: **37 passed**.
- Focused `backend/tests/test_surface_work_plan.py` (10B.1 + new service atomicity test): **45 passed**.
- Full backend pytest: **597 passed** (was 559; +38 = +37 API + 1 service).
- Frontend untouched by this sub-stage (no frontend files changed; frontend suite not re-run).
- `git diff --check` clean.

#### Verification:
- GET no-plan behavior: 404 (documented above, matches existing sub-resource convention); foreign surface/price item/apply-source hidden as 404 (owner isolation). PUT validation atomic — a failed upsert leaves the previous plan fully intact. Apply-to-all atomic — archived source item rejects the batch with no target mutated (service + API tests). Apply response `target_surface_ids` ordered by `Surface.position`. `README.md` unchanged this sub-stage. STOP per instruction — no commit, no push, no deploy, no 10C.

#### Deferred:
- 10C (frontend Work Plan UI + confirmation dialog) and the Estimate (`Estimate` + `EstimateLine`) domain/API (10B.3+/10C+ per the 10A execution plan). No commit/push/deploy.

### Stage 10C.1: Compact Surface Card + Opcje Progressive Disclosure (frontend)
- **Status**: Implemented 2026-09-16 (frontend only; **uncommitted — awaiting owner acceptance**; Git operations performed manually by the owner after acceptance)
- **Date**: 2026-09-16
- **Commit**: none yet — owner performs the commit/push after acceptance

#### Added:
- `frontend/src/components/SurfaceList.tsx` — compact mobile Surface card with per-card **Opcje progressive disclosure** (UI state only, never persisted; per-card independence via `expandedOptions`):
  - Collapsed card shows identity (name + type badge + archived badge), `Wymiary: W × H m`, the area box (Powierzchnia brutto / − Odliczenia / = Powierzchnia netto, or the requires-dimensions notice), description, a full-width **[ Opcje ]** toggle (relabels **Ukryj opcje** when open, `aria-expanded`), and a full-width **[ Rodzaje prac i jakość ]** button. No action grid is permanently visible.
  - Expanded WALL options reveal the **existing, unchanged** 2-column action grid (Badanie ściany — when the inspection entry point is provided, + Drzwi, + Okno, + Inny otwór, Zarządzaj otworami, Edytuj, Archiwizuj/Przywróć — all still `min-h-11` 44px touch targets) and the OpeningsList toggled by "Zarządzaj otworami". FLOOR/CEILING/OTHER expanded options reveal only Edytuj / Archiwizuj/Przywróć — no opening or inspection controls.
  - Work Plan button is **visual only in 10C.1** — inert, no fetch/substrate/quality/PriceItem selection/save/apply-to-all; component boundary isolates it for enabling in 10C.2 without redesign.
  - Archived surfaces keep the existing archive/restore UX (archived badge + Archiwizuj → Przywróć toggle under Opcje); no lifecycle redesign.
- `frontend/src/locales/pl.json` + `frontend/src/locales/ru.json` — `surfaces.options` / `surfaces.hide_options` / `surfaces.work_types_quality` (PL: Opcje / Ukryj opcje / Rodzaje prac i jakość; RU: Опции / Скрыть опции / Виды работ и качество).
- `frontend/src/locales/parity.test.ts` — PL/RU parity assertion for the `surfaces` block including the three new keys.
- `frontend/src/SurfaceList.test.tsx` — 12 new 10C.1 tests (collapsed-no-grid, expand, collapse, per-card independence, inspection action, add-door, manage-openings, archive, FLOOR no-opening-controls, CEILING no-opening-controls, Work Plan button present, RU localization) over the A–O acceptance matrix; existing tests updated to open Opcje before querying action buttons.

#### Changed:
- `frontend/src/components/SurfaceList.tsx` — added `expandedOptions` state + `toggleOptions`; WALL and non-WALL card branches now hide their action controls behind the Opcje disclosure; quick-add opening / openings toggle / inspection / edit / archive-restore behaviors (aria-labels, handlers, 44px classes) preserved verbatim.
- `frontend/src/SurfaceList.test.tsx` — added `expandOptions()` test helper; adjusted pre-existing interaction tests.
- `frontend/src/ProjectWorkspace.test.tsx` — adjusted the opening-reconciliation, opening archive/restore, opening edit, per-wall openings, and inspection-entry tests to expand the card's Opcje before reaching the action buttons.

#### Database:
- **No backend change, no migration.** Frontend-only sub-stage; no backend files touched.

#### Tests:
- Focused frontend (`SurfaceList`, `ProjectWorkspace`, `OpeningList`, locale parity): **76 passed** (30 + 28 + 12 + 6).
- Full frontend vitest: **340 passed** (24 files), 0 failed.
- `tsc --noEmit` PASS (0 errors); `vite build` PASS.
- `git diff --check` clean.
- Backend suite not run — no backend files changed.

#### Verification:
- Mobile acceptance concept verified at component level: collapsed card keeps identity/type/dimensions/area summary/[Opcje]/[Rodzaje prac i jakość]; expanded Opcje keeps every existing action (inspection navigation, opening creation/management, edit, archive/restore) with 44px touch targets; FLOOR/CEILING expose no opening controls; per-card expansion is independent; RU strings (Опции / Скрыть опции / Виды работ и качество) verified via i18n provider; full-width controls avoid horizontal overflow at 320–480 px. `README.md` unchanged; `docs/development-progress.md` updated per §14 (10C NOT marked complete; 10C.2 NOT started). STOP per instruction — no commit, no push, no deploy, no 10C.2.

#### Deferred:
- 10C.2 (enabling the Rodzaje prac i jakość entry — substrate/quality selection + ordered Price Book work rows + apply-to-all confirmation) and the Estimate (`Estimate` + `EstimateLine`) domain/API per the 10A execution plan. No commit/push/deploy.

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
