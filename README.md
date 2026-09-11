# Plan & Estimate

Telegram Mini App for managing interior finishing and renovation work in Poland (*prace wykończeniowe i remontowe*).

## Implementation status

### Canonical Stages 0–5 (Completed)

- **Stage 0**: Engineering workflow, architectural invariants, and domain rules (`GEMINI.md`, `.agents/rules/`).
- **Stage 1**: Application infrastructure, Docker PostgreSQL 16, FastAPI backend, React Vite frontend, aiogram bot skeleton.
- **Stage 2**: Telegram Mini App authentication and integration hardening:
  - Backend cryptographic HMAC-SHA256 signature and freshness validation of raw `initData`.
  - User model, database migration, and JWT sessions.
  - Official Telegram WebApp runtime shell (`ready()`, `expand()`).
  - Real Telegram `initData` forwarded unchanged; browser mock authentication strictly gated to local dev.
  - Telegram theme adaptation via dynamic CSS custom properties and viewport height tracking.
  - Native Telegram `BackButton` integrated with application navigation hierarchy.
  - Localized Polish and Russian authentication failure states.
- **Stage 3**: Client management with owner isolation, search, active/archive filtering, and PL/RU localization.
- **Stage 4**: Project / Obiekt central aggregate root with status lifecycle, optional Client association, and owner isolation.
- **Stage 5**: Rooms, surfaces and measurements — Room and Surface hierarchy with semantic types (`WALL`, `CEILING`, `FLOOR`, `OTHER`), metric room/wall dimensions, opening subtraction with net area totals, rectangle wall generation and custom sequential wall entry, composite floor/ceiling geometry (base + adjustments), practical mobile measurement workflow, and PL/RU localization. Owner-accepted final manual acceptance (2026-09-11).

Implementation is complete through **Canonical Stage 5**. **Stage 6** (Inspection Checklist Engine) is in progress — backend engine (6B) and mobile inspection workflow (6C) complete, final acceptance (6D) pending. Stages 7–20 are pending.

## Domain hierarchy

```text
Owner
  └── Project / Obiekt
        ├── optional Client
        └── Room
              └── Surface
```

Project / Obiekt is the central aggregate root. Room access resolves through its Project, and Surface access resolves through its Room and Project to the authenticated owner.

## Repository structure

```text
.
├── backend/             # FastAPI, SQLAlchemy, Alembic, Pydantic, pytest
├── frontend/            # React, TypeScript, Vite, Tailwind CSS, Vitest
├── bot/                 # aiogram Telegram bot bootstrap
├── docs/                # Development roadmap and stage history
├── .agents/rules/       # Architecture, domain, frontend, backend, and Git rules
├── .claude/skills/      # Repository stage workflow skills
├── CLAUDE.md            # Claude Code repository instructions
├── GEMINI.md             # Permanent engineering and domain rules
└── docker-compose.yml   # Local PostgreSQL and backend services
```

## Development workflow

Every change follows the repository stage gate:

```text
Stage
→ Implementation
→ Tests
→ PASS/FAIL
→ Commit
→ Push
```

See [`docs/development-progress.md`](docs/development-progress.md) for the detailed roadmap, completed stages, test totals, and deferred work. `CLAUDE.md`, `GEMINI.md`, and `.agents/rules/` are the implementation authority.

## Local browser development

Browser development uses PostgreSQL and the backend in Docker, plus the Vite frontend locally.

1. Create a local environment file from the committed example. Keep all real credentials in the untracked `.env` file only.

   ```bash
   cp .env.example .env
   ```

2. Start PostgreSQL and the backend with backend mock authentication explicitly enabled.

   ```bash
   MOCK_TELEGRAM_AUTH=true docker compose up -d postgres backend
   ```

3. Apply migrations when the database is new or the migration head changes.

   ```bash
   docker compose exec backend alembic upgrade head
   ```

4. Install frontend dependencies and start Vite with browser mock authentication and the local backend URL.

   ```bash
   npm --prefix frontend install
   VITE_DEV_MOCK_AUTH=true VITE_API_URL=http://localhost:8000 npm --prefix frontend run dev
   ```

5. Open [`http://localhost:5173`](http://localhost:5173). The backend health endpoint is available at [`http://localhost:8000/api/health`](http://localhost:8000/api/health).

`MOCK_TELEGRAM_AUTH=true` allows the backend development-only mock identity. `VITE_DEV_MOCK_AUTH=true` allows the frontend to request that identity when real Telegram `initData` is unavailable. Mock authentication must never be enabled in production.

## Verification commands

Run commands from the repository root:

```bash
backend/.venv/bin/pytest backend/tests
npm --prefix frontend test -- --run
frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit
npm --prefix frontend run build
git diff --check
```

## Telegram Mini App development

Real Telegram testing requires:

- a Telegram bot configured outside the repository;
- an HTTPS-accessible frontend opened by Telegram;
- an HTTPS-accessible backend when required by the chosen deployment topology;
- real Telegram Mini App `initData` delivered by the official client;
- `MOCK_TELEGRAM_AUTH=false` and `VITE_DEV_MOCK_AUTH=false`.

The frontend shell loads the official Telegram WebApp runtime, calls `ready()` and `expand()`, and forwards raw real `initData` unchanged to the backend for validation. It fails safely when the runtime or authentication data is unavailable. No production hosting or deployment topology is defined yet, and real tokens or credentials must never be committed.
