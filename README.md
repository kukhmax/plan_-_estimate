# Plan & Estimate

Telegram Mini App for planning and estimating interior finishing and renovation work in Poland (*prace wykończeniowe i remontowe*). The UI is fully localized in Polish and Russian (PL/RU).

The core workflow, front to back:

```text
Client
  → Project / Obiekt
      → Room
          → Surface (WALL / FLOOR / CEILING)
              → Opening (DOOR / WINDOW / OTHER) + reveal geometry
              → Inspection (substrate checklist) → Findings → Risks → Work Recommendations
                  → explicit owner acceptance → appended to Surface Work Plan
          → Surface Work Plan (substrate, quality, ordered Price Book works)
      → Price Book (owner catalog, editable, market evidence)
      → Estimate (line-item kosztorys generated from the plans above)
```

`Project / Obiekt` is the central aggregate root: every Room, Surface, Opening, Work Plan, and Estimate resolves back to it and to its owner.

## Implemented capabilities

### Clients

Private-person and company clients, phone, email, NIP, Telegram username (contact field only — unrelated to Telegram Mini App authentication), create/edit/archive/restore, search and filtering, owner isolation.

### Projects / Rooms / Surfaces / Openings

- Project (Obiekt) management with status and optional Client association.
- Rooms with metric dimensions; Surfaces with semantic types `WALL` / `FLOOR` / `CEILING` / `OTHER`, canonical one Floor and one Ceiling per room.
- Openings (`DOOR` / `WINDOW` / `OTHER`) with net-area deduction from their parent wall.
- Area segments (composite floor/ceiling geometry: base + ADD/SUBTRACT adjustments).
- Opening reveal geometry (ościeża): per-side enable/depth, backend-derived reveal length and area. **Reveal area never changes the wall's own net area** — it is tracked and estimated entirely separately.

### Surface Work Planning

One ordered Work Plan per physical surface: substrate, quality target (S1–S4 / Q1–Q4), an ordered list of Price Book works (duplicates allowed, e.g. two coats), reorder/remove, "Zapisz dla wszystkich ścian" (copy one wall's plan to every other wall in the room), and inline creation of a missing Price Book work directly from the picker. `REVEAL`-category work is not offered here — it belongs under a specific opening (below); a legacy reveal occurrence already saved on a Surface plan stays visible with guidance, cannot be duplicated or copied to other walls, and is an unresolved quantity in the Estimate until moved or set explicitly.

### Reveal Work Planning

Per-opening ordered Price Book work selection (category `REVEAL`), reorder/remove/duplicates, "Zapisz dla wszystkich ościeży" (atomic bulk apply to every other eligible reveal-enabled opening in the room — the ordered work selection only, never geometry), and inline creation of a missing REVEAL work from the picker. `LM` (running metre) items price the reveal length; `M2` items price the reveal area. Surface and opening-reveal planning are separate: each opening keeps its own works and coefficients. Missing or incomplete reveal geometry (e.g. no reveal side selected) stays an unresolved quantity and blocks Estimate finalization; the opening form requires at least one reveal side when reveal calculation is enabled.

### Price coefficients (Współczynniki)

Explicit, owner-selected corrections of the base **LABOR** price for execution conditions that differ from what the Price Book price assumes (full model: [Model wyceny](#model-wyceny-jakość-powierzchni-współczynniki-i-dopłaty) below). They are **not** quality classes: S1–S4 and Q1–Q4 / PSG1–PSG4 remain quality targets, never coefficients.

- Assigned per planned-work occurrence (Surface or opening reveal), never automatically; `MATERIAL` / `LABOR_AND_MATERIAL` items take no coefficient.
- Default single-select groups: **Wysokość pracy**, **Dostęp do powierzchni**, **Złożoność powierzchni**, **Organizacja pracy**. Each has an explicit `0%` base option, which is a real recorded choice — different from **Brak** (no selection).
- Groups combine **additively** with exact Decimal arithmetic: `effective = base × (1 + Σ%)`, never compounded; a combined correction above +50% shows an informational (non-blocking) warning.
- The owner can create, edit, archive and restore groups/options (Cennik → Współczynniki); every default has a PL/RU description shown via an info button. Owner edits always take precedence over built-in translations.

### Inspections, Risks & Work Recommendations

### Inspections, Risks & Work Recommendations

A Surface (or a ROOM/FLOOR/CEILING plane) can be inspected: a versioned substrate-diagnostic checklist records factual findings (moisture, cracks, unevenness, substrate condition, and more). Completed findings feed a deterministic Risk Rules engine (no AI/LLM) that flags technical risks with severity, explanation, mitigation, and warranty-exclusion guidance, and a client-communication phrase catalog (PL/RU) for explaining them. A small, explicit `WorkRecommendationRule` catalog then maps specific fired Risk Rules (and, where useful, findings) to a suggested Price Book work; the owner explicitly evaluates ("Oceń zalecenia") and, per recommendation, accepts it ("Dodaj do prac") — with a manual Price Book fallback when no item currently resolves — or dismisses it. **A recommendation is never a planned work by itself**: nothing is appended to the Surface Work Plan until the owner explicitly accepts it, and accepting one never silently regenerates the Estimate — the existing "Sprawdź zmiany" / "Aktualizuj kosztorys" flow remains the only way to bring an Estimate DRAFT up to date. Starting a new Inspection on a surface that already has a saved Work Plan reuses its substrate/quality instead of asking the same setup questions again.

### Price Book (Cennik)

Owner-scoped, editable catalog with market/reference evidence shown for context only — market data never silently overwrites the owner's own price. An unset price is `NULL` ("Do ustalenia" / "Уточняется"), distinct from an explicit `0.00`. Owner-created custom items and inline-created items (from either picker above) are ordinary Price Book rows with no hidden special-casing.

### Estimate (Kosztorys)

- Generated per project from the current Surface and Reveal Work Plans; grouped summary view plus atomic per-line drill-down with room/surface/opening provenance.
- Authoritative backend-computed totals; per-line quantity and price overrides with explicit reset; grouped bulk price editing; freeform manual lines (add/edit/delete, no Price Book row required).
- Regeneration is always explicit: **"Sprawdź zmiany"** shows a mutation-free preview of what changed across every room, then **"Aktualizuj kosztorys"** confirms it. Nothing ever regenerates silently.
- `NULL` price blocks finalization; an explicit `0.00` does not.
- Each planned-work line stores its coefficient provenance (base price and the selected coefficients). A manual price override replaces the calculated price but keeps that provenance; **"Przywróć cenę z cennika"** recalculates from the *current* base price and *current* coefficients.
- Manual price and quantity overrides survive re-saving a Work Plan (lines are matched logically, not only by the non-durable occurrence id); `FINAL` / `ACCEPTED` estimates are never changed.
- **"Finalizuj kosztorys"** transitions a DRAFT to an immutable `FINAL` snapshot; a further commercial revision is made by generating the next DRAFT version, which is a **fresh** generation from the current plans (manual lines and overrides are not copied forward). Historical `FINAL` versions are never mutated by later planning changes.

## Snapshot model

**An Estimate is a point-in-time snapshot, not a live view.** Editing a Room, Surface, Opening, or Work Plan never rewrites an existing Estimate. To bring a DRAFT estimate up to date with current plans, the owner must explicitly:

```text
Sprawdź zmiany  →  review the preview  →  Aktualizuj kosztorys
```

`FINAL` estimates are permanent historical records: later Price Book or planning edits never change an already-finalized total.

## Price / quantity semantics

- `NULL` price = unresolved ("Do ustalenia" / "Уточняется"); `0.00` = a real, explicit zero price. Never conflated.
- Market/reference price data is informational only and never silently substitutes the owner's own price.
- Quantity source by context: WALL `M2` → wall net area; FLOOR/CEILING `M2` → the authoritative plane area; REVEAL `M2` → reveal area; REVEAL `LM` → reveal length.
- The `PriceUnit.LM` API/database enum value is unchanged; the UI localizes its label as **mb** (PL) / **м.п.** (RU).

## Tech stack

**Frontend**: React 18, TypeScript 5, Vite 5, Tailwind CSS 3, Vitest — Telegram Mini App WebView.
**Backend**: FastAPI, SQLAlchemy 2.x (async), Pydantic v2, Alembic, PostgreSQL 16, served by Python 3.12.
**Bot**: aiogram 3.x (Telegram bot bootstrap).
**Infrastructure**: Docker Compose for local development; production runs on an Oracle Cloud VM behind Caddy (TLS termination / reverse proxy) with Cloudflare in front of the domain (see [`docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md`](docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md)).

## Repository structure

```text
.
├── backend/             # FastAPI, SQLAlchemy, Alembic, Pydantic, pytest
├── frontend/            # React, TypeScript, Vite, Tailwind CSS, Vitest
├── bot/                 # aiogram Telegram bot bootstrap
├── docs/                # Development roadmap, stage architecture, and deployment runbook
├── .agents/rules/       # Architecture, domain, frontend, backend, and Git rules
├── .claude/skills/      # Repository stage workflow skills
├── CLAUDE.md            # Claude Code repository instructions
├── GEMINI.md            # Permanent engineering and domain rules
└── docker-compose.yml   # Local PostgreSQL, backend, and frontend services
```

## Local development

One command starts the complete local stack in Docker: PostgreSQL 16, the FastAPI backend, and the React/Vite frontend.

1. Create a local environment file from the committed example. Keep all real credentials in the untracked `.env` file only.

   ```bash
   cp .env.example .env
   ```

2. Build and start the stack. The backend waits for PostgreSQL to be healthy, applies any pending Alembic migrations automatically (`alembic upgrade head`), then starts uvicorn. The frontend starts only after the backend is healthy.

   ```bash
   docker compose up -d --build
   ```

3. Open the frontend at [`http://localhost:5173`](http://localhost:5173) and sign in with browser mock authentication. The backend OpenAPI docs are at [`http://localhost:8000/docs`](http://localhost:8000/docs) and the health endpoint is **`http://localhost:8000/api/health`** (not `/health`).

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

**The `backend` service has no source bind mount** — its image is built with `COPY . .`, so a backend code change requires an explicit rebuild before it's picked up:

```bash
docker compose build backend
docker compose up -d backend
```

(The `frontend` service *is* bind-mounted with hot reload, so frontend changes apply immediately.)

`MOCK_TELEGRAM_AUTH=true` (the development default in compose) allows the backend development-only mock identity, so the browser mock-auth flow works without a Telegram bot token. `VITE_DEV_MOCK_AUTH=true` allows the frontend to request that identity when real Telegram `initData` is unavailable. Mock authentication must never be enabled in production.

The PostgreSQL data lives in the named `postgres_data` volume and survives `docker compose down` and `docker compose up -d`. `docker compose down -v` permanently deletes the volume and all database data — never run it when you want to keep local data.

## Database / migrations

Schema changes are Alembic migrations under `backend/alembic/versions/`; the current head is:

```
0022_work_recommendations
```

Migrations apply automatically on container start (`alembic upgrade head`, see above). No credentials or connection strings are stored in this repository — `DATABASE_URL` and all secrets live only in the untracked `.env` file.

## Testing

Run from the repository root:

```bash
backend/.venv/bin/pytest backend/tests
npm --prefix frontend test -- --run
frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit
npm --prefix frontend run build
git diff --check
```

## Production overview

```text
GitHub  →  Oracle Cloud VM  →  Docker Compose  →  Caddy (TLS, :80/:443)
                                                      ├─ nginx (production frontend build)
                                                      └─ FastAPI backend
                                                          └─ PostgreSQL (internal network only)
                          (Cloudflare in front of the public domain)
```

Only Caddy publishes ports on the host; PostgreSQL and the backend stay on the internal Docker network. Full step-by-step deployment procedure, migration handling, and rollback notes: [`docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md`](docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md). No secrets, tokens, or credentials are documented here or in that runbook — they are configured directly on the production host.

## Development workflow

Every change follows the repository stage gate:

```text
Stage → Implementation → Tests → PASS/FAIL → Owner acceptance → Commit → [owner approval] → Push
```

See [`docs/development-progress.md`](docs/development-progress.md) for the detailed roadmap, completed stages, test totals, and deferred work. `CLAUDE.md`, `GEMINI.md`, and `.agents/rules/` are the implementation authority.

## Roadmap / status

- **Stages 0–9**: COMPLETE (engineering foundation, auth, Clients, Projects, Rooms/Surfaces/measurements, Inspection Checklist Engine, Risk Rules Engine, Client Communication Assistant, editable Price Book).
- **Stage 10 (Estimate / Kosztorys)**: **COMPLETE — OWNER ACCEPTED** after the final real-Telegram production walkthrough. See [`docs/stage-10-architecture.md`](docs/stage-10-architecture.md) and [`docs/development-progress.md`](docs/development-progress.md) for the full sub-stage history.
- **Stage 11 (Inspection → recommended work → Estimate)**: **COMPLETE — OWNER ACCEPTED** after production deployment and the real Telegram Mini App owner walkthrough; integrated into `main`. See [`docs/stage-11-architecture.md`](docs/stage-11-architecture.md) and [`docs/development-progress.md`](docs/development-progress.md) for the full sub-stage history.
- **Stage 12 (Price coefficients)**: **COMPLETE — OWNER ACCEPTED** (12A–12H plus owner-walkthrough corrections). Deployed to production from `stage-12` at `d60390b` (migration head `0026_coefficient_descriptions`); the real Telegram Mini App production walkthrough passed. Not yet merged to `main`. See [`docs/stage-12-architecture.md`](docs/stage-12-architecture.md) and [`docs/development-progress.md`](docs/development-progress.md).
- Stages 13–20: pending, not started.

## Telegram Mini App development

Real Telegram testing requires:

- a Telegram bot configured outside the repository;
- an HTTPS-accessible frontend opened by Telegram;
- an HTTPS-accessible backend when required by the chosen deployment topology;
- real Telegram Mini App `initData` delivered by the official client;
- `MOCK_TELEGRAM_AUTH=false` and `VITE_DEV_MOCK_AUTH=false`.

The frontend shell loads the official Telegram WebApp runtime, calls `ready()` and `expand()`, and forwards raw real `initData` unchanged to the backend for validation. It fails safely when the runtime or authentication data is unavailable.


=================================================
=================================================

## Model wyceny: jakość powierzchni, współczynniki i dopłaty

System rozdziela cztery niezależne elementy wyceny:

1. **Standard jakości powierzchni** (`quality_target`: S1–S4, Q1–Q4 /
   PSG1–PSG4) — jaki efekt końcowy ma zostać osiągnięty.
2. **Operacje technologiczne** (PriceItems w planie prac) — co faktycznie
   trzeba wykonać, żeby ten efekt osiągnąć.
3. **Współczynniki ceny** (dla konkretnego wystąpienia planned work) — w
   jakich warunkach dana operacja jest wykonywana.
4. **Dopłaty i korekty komercyjne** (dla całego zlecenia) — warunki
   handlowe i koszty dotyczące całego zlecenia.

Nie należy zastępować dodatkowej operacji technologicznej współczynnikiem
procentowym.

### 1. Standard Wykończenia Powierzchni S1–S4

**Wewnętrzna klasyfikacja wykonawcy.**

S1–S4 jest wewnętrzną klasyfikacją wykonawcy dla powierzchni ciągłych,
np. tynków i betonu. Nie jest oznaczeniem klasy jakości według Polskiej
Normy ani żadnej innej normy.

S1 — Przygotowanie podstawowe
Powierzchnia przygotowana technicznie do kolejnej przewidzianej operacji.
Nie oznacza pełnego standardu powierzchni gotowej do malowania.

S2 — Standard malarski
Typowy standard powierzchni przygotowanej do zwykłego malowania
wnętrz farbą matową w normalnych warunkach użytkowych i przy świetle
rozproszonym.

S3 — Podwyższony standard wizualny
Podwyższona jednorodność wizualna dla bardziej wymagających wnętrz,
dużych jednolitych powierzchni lub bardziej wymagających warunków
oświetleniowych.

S4 — Indywidualnie uzgodniony standard premium
Standard dla powierzchni o szczególnych wymaganiach wizualnych,
uzgadnianych przed rozpoczęciem prac, w tym warunków oświetleniowych.

S1–S4 określa standard wykończenia powierzchni, a nie jej geometrię.
Nie określa pionu, poziomu, płaszczyzny ani kątów i nie przypisuje
żadnych tolerancji milimetrowych.

Geometria powierzchni jest oceniana i rozliczana oddzielnie.

S1–S4 NIE jest współczynnikiem ceny i nie ma domyślnego procentu.
Docelowo Stage 13 mapuje quality target na wymagane operacje
technologiczne / PriceItems.

Dla zabudowy gipsowo-kartonowej stosowane są oddzielnie poziomy
Q1–Q4 / PSG1–PSG4 — odrębny, branżowy system poziomów jakości. Nie należy
utożsamiać ich z wewnętrzną klasyfikacją S1–S4. Q1–Q4 / PSG1–PSG4 również
nie są współczynnikami ceny.

### 2. Cena bazowa

Cena PriceItem jest ceną bazową dla określonej operacji.

Cena bazowa powinna odpowiadać normalnym warunkom przyjętym przez
właściciela cennika.

Współczynnik służy wyłącznie do korekty ceny bazowej, gdy warunki
wykonania konkretnej pracy odbiegają od warunków założonych w cenie
bazowej.

Nie wolno stosować współczynnika, jeżeli dane utrudnienie zostało już
uwzględnione w cenie bazowej.

### 3. Współczynniki ceny

**Definicja:** współczynnik to korekta ceny bazowej robocizny wynikająca
z warunków wykonania, które odbiegają od warunków założonych przez
właściciela w cenie bazowej PriceItem.

Współczynnik NIE jest dodatkową operacją technologiczną.

Współczynniki dotyczą wyłącznie robocizny.

Nie zmieniają ceny materiałów.

Dla pozycji LABOR_AND_MATERIAL przypisanie współczynników pozostaje
niedozwolone w v1, ponieważ system nie zna wiarygodnego podziału ceny
na robociznę i materiał.

Współczynniki przypisywane są jawnie przez użytkownika do konkretnego
wystąpienia planned work.

Inspection, Risk Rules i Recommendations nie przypisują współczynników
automatycznie.

Domyślny katalog v1 zawiera cztery grupy opisane poniżej. Każda grupa jest
typu SINGLE_SELECT (dla jednego wystąpienia pracy można wybrać najwyżej
jedną opcję z grupy). Opcja 0% w każdej grupie jest opcją bazową
(`is_base=true`). Opcje z różnych grup można łączyć.

#### WYSOKOSC_PRACY

Standardowa — 0%
Podwyższona — +15%
Wysoka — +25%

Koryguje cenę, gdy wysokość powoduje rzeczywisty spadek wydajności
konkretnej pracy.

Koszt rusztowania, podestu, wynajmu sprzętu itp. nie jest częścią tego
współczynnika i powinien być rozliczony oddzielnie.

#### DOSTEP_DO_POWIERZCHNI

Swobodny — 0%
Utrudniony — +10%
Bardzo utrudniony — +20%

Dotyczy ograniczenia dostępu pozostającego podczas wykonywania pracy.

Jednorazowe przesunięcie mebli lub wyposażenia nie jest podstawą do
zastosowania tego współczynnika i powinno być rozliczane jako oddzielna
operacja, jeżeli jest płatne.

#### ZLOZONOSC_POWIERZCHNI

Standardowa — 0%
Złożona — +10%
Bardzo złożona — +20%

Dotyczy spadku wydajności wynikającego z kształtu, rozdrobnienia,
liczby małych fragmentów, dojść, krawędzi lub częstych zmian kierunku
pracy.

Nie należy używać współczynnika do ponownego wyceniania elementów,
które zostały już ujęte jako oddzielne PriceItems, np. ościeży,
narożników lub innych oddzielnie mierzonych prac.

#### ORGANIZACJA_PRACY

Ciągła — 0%
Ograniczona — +10%
Etapowa / przerywana — +20%

Dotyczy spadku wydajności spowodowanego organizacją realizacji,
np. ograniczonymi godzinami dostępu, pracą w czynnym obiekcie,
wielokrotnym udostępnianiem stref lub koniecznością regularnego
przerywania i wznawiania pracy.

Nie obejmuje dodatkowych czynności takich jak zabezpieczenie,
przenoszenie wyposażenia lub dodatkowe sprzątanie, jeśli są one
rozliczane oddzielnie.

#### Czego domyślny katalog celowo NIE zawiera

- grup jakości S1–S4 / Q1–Q4 / PSG1–PSG4 (to quality target, nie
  współczynnik),
- domyślnych ujemnych współczynników,
- współczynnika umeblowania,
- współczynnika sufitu,
- współczynnika koloru,
- współczynnika małego zlecenia,
- współczynnika pilności / pracy nocnej / weekendowej (to dopłaty
  dotyczące zlecenia, patrz punkt 10).

Właściciel może samodzielnie dodawać własne grupy i opcje oraz edytować
lub archiwizować domyślne.

### 4. Poziom bazowy 0%

Opcja 0% jest rzeczywistą opcją katalogu z `is_base=true`.

Wybranie np. "Standardowa 0%" zapisuje świadomą decyzję użytkownika
i jej provenance.

Nie jest to to samo co brak wyboru (`Brak`).

Brak wyboru nie zapisuje CoefficientOption.

### 5. Obliczanie współczynników

Współczynniki z różnych grup sumują się addytywnie.

Nie są kapitalizowane / mnożone jeden przez drugi.

effective_unit_price =
base_unit_price × (1 + suma_procentów)

Przykład:

Cena bazowa: 40,00 zł/m²

Wysokość: +15%
Dostęp: +10%
Złożoność: +10%

Łączna korekta: +35%

40,00 × 1,35 = 54,00 zł/m²

Obliczenia używają Decimal, nigdy float.

Zaokrąglenie ceny następuje zgodnie z zasadami Estimate Engine
do 0,01 zł.

### 6. Wysoka łączna korekta

System nie blokuje wysokiej korekty.

Jeżeli suma współczynników przekracza +50%, UI powinno pokazać
ostrzeżenie:

"Wysoka łączna korekta ceny (+X%).
Sprawdź, czy wybrane współczynniki opisują niezależne utrudnienia oraz
czy ich wpływ nie został już uwzględniony w cenie bazowej lub innych
pozycjach kosztorysu."

Ostrzeżenie jest informacyjne.
Nie jest błędem walidacji i nie wymaga dodatkowego potwierdzenia.

### 7. Opisy współczynników

CoefficientGroup i CoefficientOption mogą posiadać edytowalne pole
`description` (dodawane w Stage 12G).

Dla grup i opcji tworzonych przez właściciela opis jest opcjonalny.
Domyślne grupy i opcje dostarczane przez aplikację muszą mieć
szczegółowe opisy.

Opis powinien wyjaśniać:

- co oznacza współczynnik,
- kiedy go stosować,
- typowe przykłady,
- kiedy go NIE stosować,
- ryzyko podwójnego naliczenia kosztu.

W mobilnym UI obok grupy i opcji, które mają opis, dostępna jest ikona
informacji (obszar dotyku co najmniej 44 px; nie jest to mały tooltip
wyświetlany po najechaniu kursorem).

Po jej naciśnięciu otwierany jest mobilny bottom sheet / modal
z opisem. Strona pod spodem nie reaguje na dotyk, dopóki opis jest
otwarty. Otwarcie opisu nigdy nie zmienia planu prac.

Opis jest pomocą decyzyjną, a nie automatyczną regułą wyceny.

### 8. Ujemne współczynniki

Model danych dopuszcza współczynniki ujemne.

Aplikacja nie dostarcza jednak domyślnych ujemnych współczynników.

Właściciel może utworzyć własny współczynnik, np. dla powtarzalnej,
wysokowydajnej realizacji, jeśli odpowiada to jego modelowi cenowemu.

System nie przyznaje automatycznych rabatów za duży metraż.

### 9. Co NIE jest współczynnikiem

Dodatkowa operacja technologiczna powinna być PriceItem, a nie
współczynnikiem.

Przykłady:

- dodatkowa warstwa gładzi,
- dodatkowa warstwa farby,
- gruntowanie,
- naprawa pęknięcia,
- usuwanie pleśni lub tłustych zabrudzeń,
- włóknina / siatka / fiberglass,
- ościeża,
- dodatkowe narożniki,
- zabezpieczenie,
- przenoszenie wyposażenia.

S1–S4 oraz Q1–Q4 / PSG1–PSG4 również nie są współczynnikami.

### 10. Dopłaty i korekty komercyjne

Współczynnik planned work nie powinien zastępować dopłat dotyczących
całego zlecenia lub warunków handlowych.

Przykłady przyszłych Dopłat:

- minimalna wartość / mały zakres zlecenia,
- praca nocna,
- praca weekendowa,
- dojazd,
- rusztowanie / wynajem sprzętu.

Rabaty handlowe, negocjacje, stały klient lub duży kontrakt również
nie powinny być automatycznie modelowane jako warunki technologiczne
konkretnej pracy.

W v1 fixed surcharge może nadal być reprezentowany przez manual
EstimateLine.

Rozbudowany mechanizm Dopłat pozostaje osobnym przyszłym zakresem.

### 11. Zasada przeciw podwójnemu naliczaniu

Każdy koszt powinien mieć jedno uzasadnienie.

Jeżeli utrudnienie:
- jest już zawarte w cenie bazowej — nie dodawaj współczynnika;
- jest osobną operacją — użyj PriceItem;
- zmniejsza wydajność istniejącej operacji — użyj współczynnika;
- dotyczy całego zlecenia lub warunków handlowych — użyj Dopłaty /
  korekty komercyjnej.

Współczynniki z różnych grup mogą być łączone tylko wtedy, gdy opisują
niezależne przyczyny spadku wydajności.
