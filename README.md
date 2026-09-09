# Plan & Estimate

Telegram Mini App for managing interior finishing and renovation work in Poland (*prace wykończeniowe i remontowe*).

## Implemented through Stage 4

- Telegram Mini App authentication backend with cryptographic `initData` validation.
- Browser development mock authentication.
- Client management.
- Project / Obiekt management with an optional Project → Client association.
- Room management nested under Projects.
- Surface management nested under Rooms, including semantic surface types.
- Polish and Russian UI localization.
- Owner isolation across Client, Project, Room, and Surface access.
- Active/archive filtering with archive and restore flows.

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

The frontend shell loads the official Telegram WebApp runtime and falls back safely when that runtime is unavailable. No production hosting or deployment topology is defined yet, and real tokens or credentials must never be committed.
