# Engineering Workflow & Permanent Architecture Rules

Repository:
git@github.com:kukhmax/plan_-_estimate.git

---

## 1. Project Overview & Domain Context

**Project**: Telegram Mini App for managing interior finishing and renovation work in Poland (*prace wykończeniowe i remontowe*).

### Central Aggregate Root:
**PROJECT / OBIEKT** is the central entity. All rooms, surfaces, inspections, photos, measurements, risk logs, estimates, contracts, and acceptance protocols anchor back to an Obiekt (`project_id`).

### MVP User Model:
- One owner user initially (the finishing contractor / master craftsman).
- Architecture and schema must be multi-tenant ready from day one (every root entity includes an `owner_id` foreign key referencing `User.id`).

### Core Domains:
1. **Clients (`Klienci`)**: B2C homeowners & B2B developers/investors.
2. **Projects (`Obiekty / Projekty`)**: Central entity (address, developer stage, conditions).
3. **Rooms (`Pomieszczenia`)**: Living room, bathroom, kitchen, hallway, bedrooms, etc.
4. **Walls and Ceilings (`Ściany i Sufity / Płaszczyzny`)**: Individual planes, partitions, slants, niches.
5. **Measurements (`Pomiary`)**: Metric dimensions, net wall/ceiling areas, openings subtraction.
6. **Substrate Inspections (`Badania Podłoża`)**: Moisture, adhesion, absorption, flatness.
7. **Photos (`Zdjęcia`)**: Before/after, defects, progress, concealed works (*roboty zanikające*).
8. **Risks (`Ryzyka`)**: Deterministic technical warnings, risk score, mitigation requirements.
9. **Quality Levels (`Klasy Jakości`)**: Agreed standards (S1-S4, Q1-Q4 / PSG1-PSG4).
10. **Price Book (`Katalog Cen`)**: Contractor base prices, labor rates, materials, surcharges.
11. **Estimates (`Kosztorysy`)**: Line-item calculations by surface, substrate, and quality tier.
12. **Contracts (`Umowy`)**: Legally binding agreements, stages, deadlines, payments, warranties.
13. **Technical Protocols (`Protokoły Techniczne`)**: Site handover, concealed works, final acceptance.
14. **Work Execution (`Realizacja Prac`)**: Task tracking, checklists, technological drying times.
15. **Legal Knowledge (`Baza Wiedzy`)**: Polish Building Law, ITB guidelines, Polish/EU Norms.
16. **Client Phrases (`Zwroty i Komunikacja`)**: Ready-to-use professional explanations for clients.
17. **Scheduling (`Harmonogramowanie`)**: Work stages, technological breaks (*przerwy technologiczne*).

### Work Types (Technologie Prac):
- Szpachlowanie / gładź (gipsowa, polimerowa, maszynowa, bezpyłowa)
- Włóknina szklana (welon szklany przeciwspękaniowy 40-50 g/m²)
- Malowanie (gruntujące, podkładowe, nawierzchniowe - wałek / agregat hydrodynamiczny)
- Mikrocement (ściany, posadzki, strefy mokre)
- Stiuk wenecki i tynki dekoracyjne

### Substrates (Podłoża):
- Beton (monolityczny, prefabrykowany)
- Tynk gipsowy
- Tynk cementowo-wapienny
- Płyta g-k / sucha zabudowa
- Stara gładź (old skim coat)
- Stara farba (old paint - dyspersyjna, lateksowa, olejna/lamperia)
- Płytki ceramiczne (tile)
- Inne (other - gazobeton, silikat, ceramika)

### Quality Standards:
- **Tynki i beton**: Klasy S1 – S4
- **Płyty g-k / sucha zabudowa**: Klasy Q1 – Q4 / PSG1 – PSG4

### Languages:
- **Application UI**: Dual language support (PL + RU).
- **Client-facing documents**: Default strictly to **PL** (Polish) for legal compliance in Poland.

---

## 2. Technical Stack

- **Frontend**: React 18+, TypeScript (strict mode), Vite, Tailwind CSS, Vitest.
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2, pytest.
- **Database**: PostgreSQL.
- **Telegram Bot**: aiogram 3.x.
- **Storage (planned)**: S3-compatible object storage for photos; IndexedDB for offline drafts.
- **PDF (planned)**: Jinja2 + WeasyPrint for printable estimates, contracts, and protocols.

---

## 3. Architecture & Coding Invariants

1. **UUID Primary Keys**: All database entities must use UUIDv4 as primary keys.
2. **UTC Timestamps**: All timestamps must be stored in UTC (`created_at`, `updated_at`).
3. **Thin API Routes**: FastAPI routes only authenticate, parse input via Pydantic, call domain services, and return typed schemas. No business logic in routes.
4. **Service / Domain Layer Separation**: Business calculations, risk evaluations, and state transitions reside strictly in `domain/services` and `domain/rules`.
5. **Typed API Contracts**: Strict Pydantic v2 models on backend; corresponding TypeScript interfaces on frontend.
6. **Alembic Migrations**: Every database schema change requires an Alembic migration script.
7. **Deterministic Risk Decisions**: Technical risks, substrate warnings, and warranty exclusions must be 100% deterministic and rule-driven. No AI/LLM hallucinations.
8. **Never Hardcode Prices**: No prices, labor rates, or financial formulas in React components. All pricing comes from the backend Price Book.
9. **Never Hardcode Legal Content**: No Polish Building Law quotes, ITB guidelines, or legal disclaimers in React components. Retrieved from backend domain knowledge.
10. **i18n Outside Business Logic**: UI strings must reside in locale dictionaries (`pl.json`, `ru.json`). No raw user-facing strings in code.
11. **Secrets Security**: Passwords, tokens, database URLs, and Telegram bot keys strictly via environment variables. Never commit `.env` or credentials.
12. **Telegram initData Validation**: Telegram Mini App `initData` must be cryptographically validated on the backend using HMAC-SHA256 with the bot token.
13. **MVP Constraints**:
    - **No Redis**: Use PostgreSQL or in-memory caching for MVP.
    - **No AI / LLMs**: Rule engines only for MVP.
14. **Error Handling**: Do not silently ignore errors (`except Exception: pass` is prohibited). Return structured error envelopes.
15. **Small Coherent Changes**: Make the smallest coherent change necessary per stage. Never implement future stages early.

---

## 4. Development Workflow & Lifecycle

### Development Model:
- Iterative, stage-by-stage development.
- One small logical stage at a time.
- Every stage must be independently testable.
- Do not implement future stages early.
- Preserve working functionality from previous stages.
- Make the smallest coherent change necessary.

### Before Every Stage:
1. Read `GEMINI.md` and applicable `.agents/rules/*.md` files.
2. Inspect the current repository (`git status`, directory tree).
3. Review the implementation from previous stages.
4. Do not rewrite working modules unnecessarily.
5. Produce a short implementation plan before coding when the stage is non-trivial.

### Verification (The Gatekeeper):
A stage is **NOT** complete until all of the following pass:
- Required automated tests pass (`pytest`, `vitest`).
- Typecheck and build pass where applicable (`tsc`, `vite build`, `mypy`/`ruff`).
- Manual verification passes.
- Git review is clean.
- Commit succeeds.
- Push to GitHub succeeds.

### If Any Verification Fails:
- **STOP immediately**.
- Do not commit.
- Do not push.
- Do not start the next stage.
- Reproduce the failure.
- Add a regression test where possible.
- Make the smallest fix.
- Rerun verification from scratch.

---

## 5. Git Workflow

### Before Commit:
```bash
git status
git diff --stat
git diff
```

### Never Commit:
- `.env` and `.env.*` (except `.env.example`)
- Secrets, private keys, tokens
- Local database files (`*.sqlite`, `*.db`, dumps)
- Uploaded photos and user media
- Generated PDFs
- `node_modules/`
- `dist/`, `build/`
- `__pycache__/`, `*.pyc`, `.pytest_cache/`
- Temporary IDE files (`.idea/`, `.vscode/`, `.DS_Store`, `.directory`)

### Update:
Update `docs/development-progress.md` before committing.

### Exactly One Logical Commit per Completed Stage:

**Commit format:**
```
<type>(stage-X): short stage description

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

### After Commit:
```bash
git log -1 --stat
```

Then push current branch to:
`kukhmax/plan_-_estimate`

### Report Format:
- **Branch**: `<branch-name>`
- **Commit Hash**: `<commit-hash>`
- **Commit Title**: `<commit-title>`
- **Tests Passed**: `<count and status>`
- **Manual PASS Status**: `PASS` (with notes)
- **Push Result**: `<push status>`

### Strict Gate:
**Never start Stage X+1 automatically.** Always stop and wait for user approval.

---

## 6. Rule Files Reference (`.agents/rules/`)
- [Architecture & Design](file:///home/m/Projects/plan_estimate/.agents/rules/architecture.md)
- [Backend Engineering](file:///home/m/Projects/plan_estimate/.agents/rules/backend.md)
- [Frontend Engineering](file:///home/m/Projects/plan_estimate/.agents/rules/frontend.md)
- [Polish Construction Domain](file:///home/m/Projects/plan_estimate/.agents/rules/domain-construction.md)
- [Git & Release Workflow](file:///home/m/Projects/plan_estimate/.agents/rules/git-workflow.md)


# Do not request or introduce external API keys before the stage that actually requires the external service.
