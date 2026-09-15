# Plan & Estimate

Telegram Mini App for managing interior finishing and renovation work in Poland (*prace wykończeniowe i remontowe*).

## Implementation status

### Canonical Stages 0–9 (Completed)

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
- **Stage 6**: Inspection Checklist Engine — substrate diagnostics with versioned immutable checklist templates (concrete, gypsum plaster, cement-lime plaster, gypsum board, painted, other), room-scoped inspections with four targets (WALL surface, FLOOR, CEILING, room-level), typed answers (BOOLEAN / NUMBER / TEXT / SINGLE_CHOICE / MULTI_CHOICE), quality-scale validation (S1–S4, Q1–Q4, optional for painted/other), factual backend findings only (no risk/price/warranty), mobile PL/RU workflow, and owner-accepted final manual acceptance (2026-09-12).
- **Stage 7**: Risk Rules Engine — deterministic, rule-driven technical risk evaluation over completed-inspection findings with a versioned immutable rule catalog (15 rules, 8 condition operators), severity (LOW/MEDIUM/HIGH/CRITICAL), `blocks_finishing` and `warranty_exclusion_candidate` flags, source-finding traceability, resolved risk history, mobile PL/RU risk cards with Active/Resolved/All filters, and a permanent **two-decimal metric display policy** (5.000 → 5.00, 13.515 m² → 13.52 m² display only — backend retains full precision). Owner-accepted final manual acceptance (2026-09-13).
- **Stage 8**: Client Communication Assistant ("Co powiedzieć klientowi") — deterministic, rule-driven communication recommendations consumed from completed-inspection facts with a versioned immutable phrase catalog (no second rules engine). Three exact-key sources: RISK-derived (reusing Stage 7 seeds), FINDING-only, and a complete QUALITY substrate/quality-target matrix (GYPSUM_BOARD Q1–Q4, CONCRETE/GYPSUM_PLASTER/CEMENT_LIME_PLASTER S1–S4). Stable application identity (inspection, phrase code, source signature) with resolved history preserved, active/resolved/all filters, mobile PL/RU communication cards with explicit evaluate, lazy "Why?" traceability, copy-to-clipboard, and script-verified Stage 6→7→8 lifecycle. Owner-accepted final manual acceptance (2026-09-13).
- **Stage 9**: Editable Price Book (Cennik) — owner-scoped contractor price catalog with a canonical catalog of 44 active items (28 MARKET_SUPPORTED / 16 OWN_PRICE), all owner-adjustable from the mobile UI. Explicit price semantics: an unset price stays NULL ("Do ustalenia" / "Уточняется"), while an explicit zero is a real 0.00. Price items carry labor / material / combined scope; market evidence is stored separately and never overwrites the owner's price — 28 Kraków/Małopolskie market references backed by 112 evidence sources, browsable in a dedicated mobile source viewer. Owner-accepted and merged into `main` (2026-09-15).

Implementation is complete through **Canonical Stage 9**. **Canonical Stage 10 (Estimate / Kosztorys) is In Progress** — see below; Stages 11–20 are pending.

### Canonical Stage 10 (In Progress)

Stage 10 (Estimate / Kosztorys): **10A COMPLETE — 10B NOT STARTED**.

Stage 10A is complete as **architecture / planning only** (`docs/stage-10-architecture.md`) — no Stage 10 runtime functionality is implemented yet. The owner-accepted direction for 10B:

- a per-surface work plan (`Surface` → `SurfaceWorkPlan`) holding the substrate and target quality, with multiple ordered planned works per surface (`SurfacePlannedWork`);
- "apply to all walls" copies/replaces the planning configuration only — geometry, openings/deductions, inspections, findings, risks, and photos are never copied or changed;
- labor / material separation (ROBOCIZNA / MATERIAŁY) with the Price Book supplying the suggested commercial price;
- the estimate snapshots commercial prices and quantities at generation time; manual estimate lines are supported and never modify the Price Book;
- regeneration of a DRAFT estimate is explicit and owner-confirmed — no silent WorkPlan → Estimate synchronization.

Stage 10B (application implementation) has not started.

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
└── docker-compose.yml   # Local PostgreSQL, backend, and frontend services
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

One command starts the complete local development stack in Docker: PostgreSQL 16, the FastAPI backend, and the React/Vite frontend.

1. Create a local environment file from the committed example. Keep all real credentials in the untracked `.env` file only.

   ```bash
   cp .env.example .env
   ```

2. Build and start the stack. The backend waits for PostgreSQL to be healthy, applies any pending Alembic migrations automatically (`alembic upgrade head`), then starts uvicorn. The frontend starts only after the backend is healthy.

   ```bash
   docker compose up -d --build
   ```

3. Open the frontend at [`http://localhost:5173`](http://localhost:5173) and sign in with browser mock authentication. The backend [OpenAPI](http://localhost:8000/docs) and health endpoint are at [`http://localhost:8000`](http://localhost:8000) / [`http://localhost:8000/api/health`](http://localhost:8000/api/health).

Ports: `5173` frontend (Vite dev server), `8000` backend (FastAPI/uvicorn), `5432` PostgreSQL.

Useful commands:

```bash
docker compose ps                 # service status and health
docker compose logs -f backend    # follow backend logs
docker compose logs -f frontend   # follow frontend logs
docker compose restart            # restart the stack
docker compose down               # stop containers (database volume is kept)
docker compose up -d              # start again with the same data
```

`MOCK_TELEGRAM_AUTH=true` (the development default in compose) allows the backend development-only mock identity, so the browser mock-auth flow works without a Telegram bot token. `VITE_DEV_MOCK_AUTH=true` allows the frontend to request that identity when real Telegram `initData` is unavailable. Mock authentication must never be enabled in production.

The PostgreSQL data lives in the named `postgres_data` volume and survives `docker compose down` and `docker compose up -d`. `docker compose down -v` permanently deletes the volume and all database data — never run it when you want to keep local data.

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
