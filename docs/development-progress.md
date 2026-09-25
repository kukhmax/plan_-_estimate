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
| **Stage 10** | Estimate / Kosztorys | **COMPLETE — OWNER ACCEPTED (2026-09-20) after the final real-Telegram production walkthrough; Stage 10H closure verdict: STAGE 10H COMPLETE / STAGE 10 COMPLETE** — 10A (Surface Work Planning + Estimate Architecture) and 10A.1 (Canonical Architecture Corrections) Completed 2026-09-15 (docs-only; owner accepted; committed together as `6bbc4ce`)**; **10B.1 (Surface Work Plan backend domain) Completed 2026-09-15, owner accepted, committed `3c9751e` (2026-09-16)**; **10B.2 (Surface Work Plan HTTP API + apply-to-room-walls) Completed 2026-09-16, committed `86de66d`**; **10C.1 (Compact Surface Card + Opcje progressive disclosure) Completed 2026-09-16 — OWNER ACCEPTED after real Telegram production retest**; **10C.1A (Canonical Floor/Ceiling Surfaces) Completed 2026-09-16 — OWNER ACCEPTED, committed `a6c50c5`**; **10C.1B (Floor/Ceiling Mobile UI Parity) Completed 2026-09-16 — OWNER ACCEPTED, committed `0ca24a2`**; **10C.1C (Telegram Owner Acceptance Fixes) Completed 2026-09-16 — OWNER ACCEPTED, committed `d9d9265`**; **10C.2A (WorkPlan Editor Shell + Existing Plan Loading) Completed 2026-09-16 — OWNER ACCEPTED after real Telegram retest**; **10C.2B (Frontend Price Book Picker + backend contract correction) Completed 2026-09-16 — OWNER ACCEPTED after real Telegram retest (cosmetic polish deferred to final UI/UX polish)**; **10C.2C (Planned Work Ordering) Completed 2026-09-16 — OWNER ACCEPTED after real Telegram retest**; **10C.2D (Final Integration Verification) Completed 2026-09-16 — OWNER ACCEPTED (no implementation changes required; 36/36 focused + 420/420 full frontend tests PASS; tsc + Vite build PASS; cosmetic UI polish deferred to final UI/UX polish stage); **10C.2 = COMPLETE**; **10C.3 (Apply Work Plan to All Walls) Completed 2026-09-16 — OWNER ACCEPTED after real Telegram retest, committed `e68a67b`; 10C = COMPLETE**; **Stage 5F (Opening Reveals / Ościeża) Completed 2026-09-17 — OWNER ACCEPTED, committed `22afddc`, migration `0019_add_opening_reveals`**; **Architecture revision D19 (per-opening `OpeningRevealPlannedWork`) approved 2026-09-17 — docs only, corrected stage sequence 10D–10H defined in `docs/stage-10-architecture.md`** — **10D (Estimate Domain Foundation) OWNER ACCEPTED 2026-09-17, committed `acd56e5`**: migration `0020_create_estimates` (estimates, estimate_lines, opening_reveal_planned_works tables; new enums estimatestatus/lineorigin/quantitysource; reuses priceunit/pricescope); models Estimate, EstimateLine, OpeningRevealPlannedWork; services EstimateService (generate_estimate, regenerate_draft, finalize, add_manual_line, recalculate_totals) + OpeningRevealWorkService (get_works, set_works, clear_works); 51 focused tests + 704 full backend tests PASS; **10E (Estimate HTTP API) OWNER ACCEPTED 2026-09-17**: 9 Estimate endpoints (list, get, generate/409-on-active-DRAFT, regenerate-preview, regenerate, add-manual-line, patch-line, delete-line, finalize) + 3 Opening Reveal Work endpoints (GET/PUT/DELETE with full nested path validation); schemas estimate.py + reveal_work.py; EstimateService extended (list_estimates, get_estimate_detail, preview_regeneration, patch_line, delete_manual_line); EstimateDraftExistsError; structured regeneration preview (LineChangeEntry); price override reset (reset_price_override); quantity override reset (reset_quantity_override); single-currency manual line guard; 71 focused API tests + 775 full backend tests PASS; **10F (Estimate Hardening) COMPLETED 2026-09-17**: 85 adversarial hardening tests in `test_estimates_hardening.py` (80 original + 5 concurrency correction tests); 17 test classes (F01–F17); concurrency race resolved — `generate_estimate` now acquires `SELECT ... FOR UPDATE` on the Project row via `_lock_project` before DRAFT check and version calculation (owner decision: Option A); 860 full backend tests PASS; migration head: 0020_create_estimates (single head); all 9 estimate + 3 reveal-work routes verified; git diff --check CLEAN; files changed: `estimate_service.py` (+`_lock_project`), `test_estimates_hardening.py` (+7 F14 tests); **10G.1 (Estimate Mobile UI: Entry + Version List + Draft Creation) OWNER ACCEPTED 2026-09-17, committed `1aff6d0`**; **10G.2 (Estimate Mobile UI: Grouped Line Detail + Compact Provenance) COMPLETE 2026-09-18 — OWNER ACCEPTED after final real-browser retest**: EstimateShell grouped view (selectedGroupKey=null) + atomic drill-down (selectedGroupKey set); presentation-only grouping by getGroupKey (planned::price_item_id::scope::unit::surface|reveal, manual::line_id); BigInt exact decimal arithmetic (decimalArithmetic.ts — no Number/parseFloat/toFixed/Math.round); group cards: description (resolveKey), scope badge, origin badge, aggregated quantity (same-unit), uniform unit_price (if no override), sum amount (if all known, else "—"), line count badge (>1), override amber indicator; explicit Back button "← Wróć do kosztorysu" / "← Назад к смете" (min-h-[44px]); backend read-model enrichment EstimateService.get_estimate_read_with_provenance (batch-loads Room/Surface/Opening in 3 queries, enriches EstimateLineRead with room_name+surface_name+surface_type_value+opening_name+opening_type_value — live at read time, works for historical estimates); EstimateLineRead schema +5 optional-and-nullable presentation fields; **runtime crash correction**: getSurfaceDisplayName and provenance helpers hardened against presentation metadata that is `undefined` (omitted) as well as `null` — real owner browser stack trace (`Cannot read properties of undefined (reading 'trim')`) reproduced and fixed; **final compact provenance UX** (owner-requested polish): removed labeled Pomieszczenie:/Powierzchnia:/Otwór: rows in favor of a single compact "room — surface — opening" string inline beside the origin/scope badges (e.g. `pokoj 1 — Ściana 1`), wrapping naturally at 390px, missing pieces omitted (never invented); **deterministic surface card tint**: subtle FNV-1a hash of `surface_id` → fixed 6-color pastel palette, stable regardless of line order, neutral white for lines without a surface_id; i18n +group_lines_count +group_has_overrides +detail_back (provenance_room/provenance_surface/provenance_opening keys retired from UI use, left in locale files); 16 decimalArithmetic tests + 122 EstimateShell tests (grouped view, drill-down, provenance compaction, surface tint determinism, crash regression) = 617 full frontend tests PASS; 74 focused backend Estimate API tests + 863 full backend tests PASS; tsc PASS; Vite build PASS; no migration; deferred: quantity/price editing, reset overrides, manual lines, regeneration, finalize (10G.3+); **10G.3A (Estimate Price and Quantity Editing) COMPLETE 2026-09-18 — OWNER ACCEPTED after final real-browser retest**: atomic per-line editing (quantity + unit_price, DRAFT-only) via existing PATCH EstimateLine endpoint — exact decimal strings only (no Number/parseFloat/toFixed/Math.round), explicit `unit_price: null` ("Cena do ustalenia" / "Цена уточняется") distinct from `0.00`, `reset_quantity_override`/`reset_price_override` (price reset hidden for MANUAL lines — no PriceBook source, backend `EstimateValidationError`/422); group-level bulk price editing on top of the 10G.2 grouping key — "Ustaw cenę dla wszystkich"/"Установить цену для всех" applies one unit_price to every line in `group.lines` (uniform/mixed/all-NULL prefill, never inventing a common value for mixed groups) via the same atomic PATCH endpoint called once per line (no bulk backend endpoint), stop-on-first-failure + mandatory authoritative refetch on both success and partial failure (never reports false success); "Przywróć ceny z cennika"/"Восстановить цены из прайса" group reset-to-PriceBook, hidden for MANUAL groups; no group-level quantity editing (quantities remain per-surface/geometry); final owner-requested placement polish — "Opcje" (group card) and "Edytuj" (atomic line card) relocated to the upper-right of each card's header row beside the title/badges (`flex items-start` header row, `flex-1 min-w-0` content + `shrink-0` action button, siblings not nested, to preserve mobile wrapping at 320–480px with no horizontal overflow); i18n +12 group-price keys (PL/RU) +11 line-edit keys (PL/RU); no backend changes, no migration; 186 focused EstimateShell tests + 681/681 full frontend suite PASS; tsc PASS; Vite build PASS; `git diff --check` CLEAN; **10G.3B (Estimate Change Preview and Explicit Regeneration) COMPLETE 2026-09-18 — OWNER ACCEPTED after final real-browser multi-room retest**: "Sprawdź zmiany"/"Проверить изменения" (DRAFT-only, whole-project, shared header — not per-group) calls the existing Stage 10E `regenerate-preview` endpoint (strictly read-only, never mutates); structured diff rendered by backend-authoritative `change_type` (Dodano/Usunięto/Zmieniono — ADDED/REMOVED/UPDATED), zero-change state ("Kosztorys jest aktualny."), override indicators (Ilość/Cena zmieniona ręcznie) so the owner knows regeneration will preserve an existing override; explicit "Aktualizuj kosztorys"/"Anuluj" gate — preview never auto-regenerates, only confirmation calls `regenerate`; stop-on-first-failure-equivalent safety (inline localized error, recoverable context, retry, mandatory authoritative refetch) mirrors the 10G.3A group-price-edit pattern; **preview provenance follow-up** (owner-requested day-of correction): extended `LineChangeEntry`/`LineChangeEntryRead` with room_name/surface_name/surface_type_value/opening_name/opening_type_value, resolved via a new bounded `_enrich_change_provenance` helper (Surface+Room+Opening batch-loaded in ≤3 queries regardless of change count, reused by both `preview_regeneration` and `_do_regenerate` — analogous to the accepted 10G.2 `get_estimate_read_with_provenance` enrichment, never fabricating a name for a REMOVED entry whose source no longer resolves); frontend reused (not duplicated) the existing `compactProvenanceLabel`/`provenanceSurfaceLabel`/`provenanceOpeningLabel` helpers via a shared structural `ProvenanceSource` type; **owner-retest correction #1 (real-browser runtime bugs, both fixed same day)**: (a) preview provenance appeared missing at runtime — root-caused to the owner's local Docker backend container serving a stale pre-enrichment image (`backend` service has no bind mount, `COPY . .` at build time) — no application code defect, code verified correct via live HTTP-level tests; (b) genuine frontend bug — the estimate header "Razem" total read the stale `estimate` summary prop (handed down once by the parent) instead of the freshly-refetched `detail` state, so it never reflected post-regeneration (or post-price-edit) totals; fixed via `headerSource = detail ?? estimate` covering version/status/name/total/currency, falling back to the prop only before the first successful fetch; **owner-retest correction #2 (real-browser CEILING-quantity bug)**: canonical FLOOR/CEILING surfaces (Stage 10C.1A) store no width/height, so `_surface_net_area` computed `None` → `0.000 M2` for CEILING/FLOOR M2 planned work instead of the authoritative Room-plane area; fixed by dispatching FLOOR/CEILING to a new `_plane_net_area` helper that mirrors `AreaSegmentService._plane_summaries` exactly (Room.length×Room.width base + active AreaSegment ADD/SUBTRACT totals via the same `calculate_plane_base_area`/`calculate_plane_totals` rule functions — no duplicated formula, no fake dimensions), applied uniformly to initial generation, regeneration, and preview; WALL net-area/opening-deduction behavior unchanged and confirmed unaffected (openings remain WALL-only); NULL-price/quantity independence preserved (0.000 M2 was never a valid substitute for an unresolved price); no migration (Room.length/width and AreaSegment already existed) — 25 new/updated focused backend tests (preview provenance, multi-room, total-recalculation, FLOOR/CEILING A–J matrix) + 235 focused Estimate tests + 888/888 full backend suite PASS; 39 new frontend tests (preview/confirm/provenance/header-total regressions) + 231 focused EstimateShell tests + 726/726 full frontend suite PASS; tsc PASS; Vite build PASS; `git diff --check` CLEAN; deferred: manual-line creation, FINAL v2 lifecycle (10G.3C+); **10G.3C (Manual Estimate Lines) COMPLETE 2026-09-19 — OWNER ACCEPTED after final real-browser retest**: owner-created MANUAL EstimateLine support built entirely on the existing, unchanged Stage 10E `POST/DELETE .../estimates/{id}/lines[/{line_id}]` contract — **zero backend changes**; "+ Dodaj pozycję"/"+ Добавить позицию" (DRAFT-only, shared header area, not per-group/room) opens a progressive-disclosure form (description literal text — never resolveKey'd, never written to PriceBook; scope restricted to LABOR/MATERIAL — LABOR_AND_MATERIAL excluded since the backend rejects it for manual lines; unit reuses the existing `PRICE_UNITS`/`t.pricebook.units` Price Book infrastructure for all 6 backend values; raw decimal quantity/price strings, no Number/parseFloat/toFixed/Math.round; explicit `unit_price: null` "Cena do ustalenia" distinct from `"0.00"`; currency always the estimate's own authoritative value, never user-editable); creation triggers the same no-optimistic-insert authoritative refetch pattern as every other Stage 10G.3 mutation; deletion ("Usuń pozycję", MANUAL-only, DRAFT-only, backend-enforced) requires explicit confirmation ("Usunąć tę pozycję ze szkicu kosztorysu?"); existing 10G.3A atomic editor and 10G.2 MANUAL-singleton grouping both worked unmodified for owner-created lines; manual-line survival across regeneration verified backend-owned (`preserved_manual`), no frontend preservation logic added; **accepted incidental fix**: shared `apiRequest` HTTP client threw on any `204 No Content` response (no prior caller had ever hit one) — the existing DELETE endpoint is a 204, so this genuine frontend-only gap (not a backend contract issue) was fixed with a dedicated regression test, kept as accepted 10G.3C scope; owner real-browser acceptance covered numeric price, NULL price, atomic edit (250→300 PLN), delete confirmation, real HTTP 204 delete (manually validating the fix, total 7335.68→7035.68 PLN), and full regeneration-survival (manual LM line preserved unresolved alongside a new regenerated FLOOR line, total reaching 10795.68 PLN); 42 new focused frontend tests (235 focused backend unchanged/still green) + 273 focused EstimateShell tests + 769/769 full frontend suite PASS; tsc PASS; Vite build PASS; `git diff --check` CLEAN; no migration; deferred: FINAL/version lifecycle (10G.3D); **10G.3D (Estimate Finalization and Version Lifecycle) COMPLETE 2026-09-19 — OWNER ACCEPTED after full real-browser lifecycle retest**: built entirely on the existing, unchanged Stage 10E/10F lifecycle contract — **zero backend changes**; "Finalizuj kosztorys"/"Зафиксировать смету" (DRAFT-only, shared header area) requires explicit confirmation before calling the existing `POST .../finalize`, never triggered by navigation; backend remains authoritative for the unresolved-NULL-price precondition (422) — frontend never precomputes finalization validity; on success, authoritative refetch updates the status badge to Finalny/FINAL and every mutation control (Dodaj pozycję, Sprawdź zmiany, group Opcje, atomic Edytuj, manual Usuń pozycję, Finalizuj itself) disappears — all of this was already correctly gated by the pre-existing `detail.status === 'DRAFT'` checks from 10G.3A–10G.3C, only the new Finalizuj button needed the same gate; read-only drill-down (quantity/price/amount/provenance/grouping/surface tints) remains fully available for FINAL; **create-next-version ("Utwórz nową wersję") was already fully implemented since 10G.1** in `EstimateList.tsx` — reconfirmed, not rebuilt; version switching verified state-isolation-safe by construction (traced `ProjectWorkspace.tsx`: `selectedEstimate` only ever goes non-null from the version list, which only renders when it is null, so `EstimateShell` is always fully unmounted between different estimates — no `key` prop or extra reset logic needed); **owner-accepted canonical version semantics** (documented here so it is never later treated as a bug): FINAL is a frozen, byte-for-byte-immutable historical snapshot; creating a new version performs **fresh generation from the CURRENT project Work Plan** (confirmed by code inspection: generation never reads the previous Estimate's lines at all) — MANUAL EstimateLines, quantity overrides, and price overrides from the previous version are **NOT** automatically copied forward; unresolved PriceBook items return to "Do ustalenia" on the new version as expected; carry-forward (if ever wanted) is an explicit future product decision, not implicit generation behavior; **owner-retest correction (same day)**: the finalize endpoint's unresolved-price rejection ("Cannot finalize: N line(s) have no price set...") was shown to the owner as raw untranslated English — fixed with a narrow `extractUnresolvedPriceCount` regex match (`/^Cannot finalize: (\d+) line/`) feeding a localized, count-templated PL/RU message ("N pozycji nie ma ustalonej ceny." / "У N позиций не указана цена."), while any non-matching error (malformed shape, unrelated 409/422, network/non-Error) safely falls through to the pre-existing fallback path unchanged — never misclassified, never inventing a count; **real owner lifecycle acceptance**: DRAFT blocked from finalizing with unresolved NULL prices (localized, correct count shown) → resolved → V1 FINAL (total 13152.10 PLN) → Work Plan changed (Gładź reduced, new "Zdzieranie starych powłok malarskich" work added) → reopened FINAL V1 unchanged (same total, old work intact, new work absent, no mutation controls) → "Utwórz nową wersję" → DRAFT V2 freshly generated from current Work Plan (Gładź 136.208 M2/8 positions in V1 → 66.612 M2/4 positions in V2; new work 69.596 M2 × 15.00 PLN = 1043.94 PLN/4 positions appeared; V1's manual line and overrides correctly absent) → finalize blocked (5 unresolved positions reported) → resolved → V2 FINAL (total 10501.64 PLN) → V2 mutation controls correctly disappeared; 3 new backend contract-verification tests (zero backend code changes) + 238 focused Estimate tests PASS; 28 new frontend tests (23 lifecycle + 5 error-UX correction) + 301 focused EstimateShell tests + 797/797 full frontend suite PASS; tsc PASS; Vite build PASS; `git diff --check` CLEAN; no migration; **10G.4 (Reveal Work Planning, Bulk Apply, Inline Price Book Creation, Client Contact Details, Mobile Surface Card Polish) COMPLETE 2026-09-20 — OWNER ACCEPTED after full real-browser retest across every sub-round**: closed the Stage 10G completeness-audit gap (reveal work planning UI never existed despite full backend support since 10D/10E) and accumulated every owner-requested correction from that point through final acceptance. **Reveal Work Planning**: `RevealWorkPlanEditor.tsx` (per-opening ordered `PriceCategory.REVEAL` selection, duplicate/reorder/remove, backend-authoritative geometry display only, no optimistic save — always an authoritative refetch), surfaced from `OpeningList.tsx` gated on `reveal_enabled`. **Bulk Apply**: new atomic `OpeningRevealWorkService.apply_to_room_openings` + `POST .../reveal-works/apply-to-room-openings` (room-scoped, source excluded from targets, eligible target = same room + `reveal_enabled` + not archived + parent surface not archived — the last condition was a gap I found and fixed mid-implementation by cross-referencing every other "active opening" query in the codebase; any archived PriceItem anywhere in the source selection rejects the *whole* batch atomically, never partial; geometry/quantities never copied, only the ordered PriceItem selection) with a frontend confirm-panel showing a real fetched eligible-target count (never invented) and a distinct destructive-clearing wording when the source selection is empty. **Inline Price Book creation**: shared `PriceItemForm.tsx` extracted byte-for-byte from the existing Cennik add/edit form (zero behavior change to Cennik, all 84 pre-existing tests pass unmodified) and reused from both the Reveal picker (category locked to REVEAL) and the Surface Work Plan picker (category left open — that picker already spans every category with no restriction); "+ Dodaj nową pracę do cennika" persists through the normal Price Book API and adds the returned item straight into the current draft — never auto-saves the Work Plan. **Nullable PriceBook price correction** (supersedes the original Stage 9E.7 restriction, owner-directed): `PriceItemCreate.price` widened to `Decimal | None` (an on-site owner can create a row before a price is agreed) and `PriceBookService.update_item`'s `price` param converted to the `_UNSET`-sentinel pattern already used for `quality_level`, so an explicit `"price": null` via PATCH now genuinely re-nulls an already-priced row instead of silently no-op'ing; `0.00` remains a fully distinct explicit price in both directions; shared `PriceItemForm` "Cena do ustalenia" checkbox (mirrors the existing Estimate-editor unresolved-price toggle) drives both create and edit; a NULL-priced planned/reveal work item confirmed end-to-end to produce a real non-zero `EstimateLine.quantity` with `unit_price`/`amount` both NULL, and `finalize()` still blocks on it exactly like any other unresolved price — Estimate generation code itself required zero changes. **Empty DRAFT Estimate recovery** (real owner data-loss scare, root-caused not a bug): a project's Estimate v1 had legitimately generated with zero lines because it ran before any rooms/Work Plans existed (snapshot semantics, correctly preserved) — but `EstimateShell.tsx`'s empty-lines branch early-returned *before* the shared `regenerationSection`/`manualLineSection`/`finalizeSection` were reached, so an empty DRAFT had no way to reach "Sprawdź zmiany" even though the backend fully supported regenerating it; fixed by moving the empty-lines check to a single unified branch placed *after* those three shared sections are computed, so an empty DRAFT now reaches the exact same explicit regeneration/manual-line/finalize actions a non-empty DRAFT already has — immutable (FINAL/ACCEPTED/ARCHIVED) empty estimates remain untouched (no controls). **Client contact details**: new nullable `telegram_username` column (migration `0021_client_telegram`, additive, single head) normalized to canonical `"@username"` form (trim, optional leading `@`, empty → NULL) via a `model_validator` matching this schema file's own existing idiom; also discovered and completed a pre-existing gap — the Client UI had no Edit action at all (`updateClient`/`t.clients.edit` existed but were never wired to any button) — added the minimal missing "Edytuj" affordance reusing the existing Add form; client card now shows NIP/phone/email/Telegram only when present (never an empty "NIP: —" label), compact and mobile-safe. **Mobile surface-card polish** (owner-reviewed, iterated to final form): every WALL card now gets its own deterministic per-`surface_id` tint (the existing Stage 10G.2 FNV-1a hash palette, extracted into shared `utils/surfaceColorTint.ts` and reused rather than duplicated) instead of one flat color, so adjacent walls are visually distinct; FLOOR (warm/sand `orange-50`) and CEILING (cool gray-blue `slate-100`) get their own stable semantic tints in `AreaSegmentList.tsx` (the sole FLOOR/CEILING representation — canonical planes never render inside `SurfaceList`'s own card list); "Opcje" moved from a full-width button below the calculation panel into a compact 44px control in the card header's upper-right (old duplicate removed from both the WALL and OTHER branches); the deduction row now explains *what* is being deducted from already-fetched active Opening data ("Odliczenia (okno 2.50 × 1.40)" / "(2 × okno)" / "(okno + drzwi)" for ≤6 mixed openings, compact generic count beyond that) — the numeric value itself is always the unchanged backend `deduction_area`; a new "Ościeża" row sums existing per-opening `reveal_total_length`/`reveal_total_area` via exact decimal-string arithmetic (never recomputes reveal geometry, never touches wall net area) and is hidden entirely when no opening on that wall has reveals enabled; the internal `PriceUnit.LM` enum is untouched everywhere — only its *display* is now consistently "mb" (PL) / "пог. м" (RU) via the single already-centralized `t.pricebook.units.LM` map, applied to the two reveal-length displays that had been missed (`OpeningList.tsx`, `RevealWorkPlanEditor.tsx`) as well as the new Ościeża row. **Files**: 8 new (`api/revealWorks.ts`, `components/RevealWorkPlanEditor.tsx`, `components/PriceItemForm.tsx`, `types/revealWork.ts`, `utils/surfaceColorTint.ts`, `utils/surfaceTypeTint.ts`, `alembic/versions/0021_client_telegram.py`, plus test file `RevealWorkPlanEditor.test.tsx`) + 30 modified across backend services/schemas/endpoints, frontend components/types/locales, and their test files. **Verification**: 927/927 full backend suite PASS (443 focused across every touched domain); 913/913 full frontend suite PASS; tsc PASS; Vite build PASS; `git diff --check` CLEAN; Alembic: single head `0021_client_telegram`, linear unbroken chain from `0001_create_users`; **Stage 10G = COMPLETE**; **Stage 10G final completeness audit (2026-09-20, read-only, no code/doc changes at audit time): STAGE_10G_COMPLETE** — capability matrix (items A–AR: Estimate navigation, grouped/atomic views, provenance, quantity/price override+reset, grouped bulk price edit, manual lines, regeneration preview/confirm, multi-room refresh, WALL/FLOOR/CEILING/REVEAL-LM/REVEAL-M2 quantity correctness, reveal work planning+bulk apply, inline PriceBook creation from both pickers, NULL/0.00 PriceBook creation, authoritative totals, finalize blocking, immutable FINAL, next-version, empty-DRAFT recovery, mobile/localization) all IMPLEMENTED, zero MISSING/PARTIAL; the two items the original architecture text (§15/roadmap) described but were never built — a scope subtotal footer (Robocizna/Materiały/Mieszane/Razem) and a *proactive* (pre-attempt) unresolved-price counter — were explicitly re-classified as **NON-BLOCKING presentation backlog**, not gaps: never raised as blocking across four full owner-acceptance rounds, the functional requirements they'd serve (per-line scope visibility, accurate finalize-blocking with a correct count) are already met by existing per-line scope badges and the reactive, localized, owner-accepted finalize-rejection count; **Stage 10H pre-implementation audit (2026-09-20, read-only)** confirmed 10H's canonical purpose is a verification+owner-walkthrough gate only (no new functionality required per `docs/stage-10-architecture.md` §23/§26), independently re-verified every Stage 10A→10G commit hash actually exists in history with matching messages, re-confirmed by direct code read that `PriceUnit.LM → QuantitySource.REVEAL_LENGTH` / `PriceUnit.M2 → QuantitySource.REVEAL_AREA` and that `apply_to_room_openings` never touches `Opening` geometry columns, live-imported the FastAPI app to enumerate its actual OpenAPI routes (all Surface/Reveal Work Plan + Estimate owner-facing operations confirmed publicly routed, no frontend/backend route mismatch), and found one minor test-completeness (not functional) gap — no dedicated test asserts an explicit `0.00`-priced line does not block finalize (provably correct by construction: `finalize()`'s guard is a single `unit_price is None` check) — decision: **10H_READY_FOR_FINAL_VERIFICATION**, no code changes required; **Stage 10H automated Final Gate (2026-09-20)**: full backend suite **927/927 PASS**, full frontend suite **913/913 PASS**, `tsc --noEmit` PASS, `vite build` PASS, `git diff --check` PASS, Alembic single head `0021_client_telegram` (linear chain, no duplicate revisions), no accidental generated/build files tracked, live OpenAPI route enumeration re-confirmed at gate time — **Stage 10H — Automated Final Gate PASS; awaiting owner walkthrough** (canonical §26 acceptance scenario) before Stage 10 is declared CLOSED; this documentation-sync pass also rewrote `README.md` to reflect actual current capabilities (Clients/Projects/Rooms/Surfaces/Openings/reveal geometry/Surface+Reveal Work Planning/Price Book/Estimate, snapshot model, price/quantity semantics, actual tech-stack versions, actual local-Docker workflow incl. the no-bind-mount-on-backend rebuild requirement, actual production topology — Oracle Cloud VM + Caddy + Cloudflare, no secrets — and accurate roadmap status), with **zero application code changes** in this pass; **Stage 10H owner walkthrough (2026-09-20): ISSUES FOUND** — a real Telegram production walkthrough against a freshly reset database surfaced six UX defects after the automated Final Gate had already passed: (1) Client card phone/email/Telegram contact fields were static, non-actionable text; (2) hardcoded `text-slate-900`/`-700`/`-500` on several page-level (non-card) headings/breadcrumbs/labels became invisible dark-on-dark in Telegram's real dark theme; (3) `RoomList.tsx`'s room-card calculations summary gated its entire display on formula L/W/H dimensions, so a CUSTOM/free-form room with real backend-computed wall/segment totals still showed "Brak wprowadzonych wymiarów"; (4) the expanded per-wall openings/options panel had no bottom collapse action, forcing a scroll back to the top; (5) the Surface/Reveal Work Plan editors had no bottom close action, forcing a scroll back to the top once several planned works were selected; (6) the three Estimate header actions (Sprawdź zmiany/+ Dodaj pozycję/Finalizuj) were unnecessarily tall with two of the three sharing an identical color, and Estimate group cards had no visual differentiation. **Stage 10H.1: Owner Walkthrough Corrections implemented and automated verification PASS, awaiting Telegram retest.** Fixes (frontend-only, no backend/migration changes): (1) `ClientList.tsx` — tap-to-call `tel:` link (sanitized to digits + optional leading `+`), tap-to-open `https://t.me/<username>` (stored value's canonical single leading `@` stripped), tap-to-copy e-mail via the existing `copyTextToClipboard` util reusing the established Stage 8C `CommunicationPanel` self-clearing confirmation pattern; (2) systematic audit of every Stage 10 owner-workflow screen distinguishing bare page-background text from intentional white/tinted cards — replaced hardcoded slate classes with `text-[var(--tg-theme-text-color)]`/`text-[var(--tg-theme-hint-color)]` only on the confirmed-bare elements (`ProjectWorkspace.tsx` breadcrumb nav + 2 headings, `ClientList.tsx`/`RoomList.tsx`/`SurfaceList.tsx`/`AreaSegmentList.tsx` section titles), leaving every heading already inside a white/tinted card (and the mid-gray hint-toned body text) untouched — no light-theme regression (`--tg-theme-text-color` light value is bit-identical to `slate-900`); (3) `RoomList.tsx` card summary now shows backend `room.calculations` totals whenever they exist, independent of formula L/W/H, mirroring the already-correct gating pattern in `ProjectWorkspace.tsx`'s room-detail view (root-caused via a dedicated trace: backend `resolve_room_totals`/`RoomRead`/canonical-plane provisioning were already fully correct — this was a frontend-only rendering-condition bug); (4) `SurfaceList.tsx` WALL Opcje panel gained a bottom "Ukryj opcje" action reusing the exact same `toggleOptions` handler/state (no new state), min-h-11, full width, visible only while expanded; (5) `SurfaceWorkPlanEditor.tsx` and `RevealWorkPlanEditor.tsx` each gained a bottom "Zamknij" action reusing the exact same `onClose` handler (no new state, no save-on-close); (6) `EstimateShell.tsx` — the three DRAFT action buttons' collapsed state now renders without the surrounding white-card padding/border/shadow (card chrome reserved for the open panel), cutting the collapsed vertical footprint by roughly a third while keeping the full min-h-[44px]/w-full touch target, and gained distinct subtle backgrounds (`bg-blue-50` check-changes, `bg-violet-50` add-manual-line, `bg-emerald-50` finalize, previously two of the three shared the same blue); Estimate group cards reuse the existing Stage 10G.2/10G.4 `surfaceCardTint` FNV-1a hash palette (already used for Surface cards), keyed by the group's own stable `key` (never array index), so each group gets a deterministic subtle tint while scope badges/Opcje/amounts remain unchanged. **Verification**: 16 new focused frontend tests added across `ClientList`, `RoomList`, `SurfaceList`, `AreaSegmentList`, `ProjectWorkspace`, `SurfaceWorkPlanEditor`, `RevealWorkPlanEditor`, and `EstimateShell` test files; full frontend suite **929/929 PASS**; `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` CLEAN; no backend files touched, so the full backend suite was not re-run (still 927/927 as of the prior Final Gate) — **Stage 10 remains NOT CLOSED, awaiting the owner's Telegram retest of these six corrections**; **Stage 10H.1 Telegram retest (2026-09-20): PARTIAL PASS** — two remaining presentation regressions found: (a) the Project/Object white details card's `Adres:`/`Status:`/`Klient:` values were invisible in real Telegram dark theme, and (b) a CUSTOM room's list card still only showed wall gross area, never floor/ceiling. **Stage 10H.2** — (a) root-caused: the `dd` value elements in `ProjectWorkspace.tsx`'s `project-detail` card had no explicit text color at all, so they silently inherited `body`'s Telegram-theme-driven color (light in dark theme) despite sitting on an intentionally always-white card; fixed by giving them an explicit `text-slate-900` (the labels already had an explicit `text-slate-500` and were never affected); confirms the Stage 10H.1 rule was correctly "bare page → theme variable" but incompletely applied to this one white-card value, not a case of over-applying theme variables inside cards; (b) `RoomList.tsx`'s room-card summary rebuilt as a list of independently-gated parts (dimensions, `floor_area`, `ceiling_area`, `total_wall_area`), each rendered only when its backend `room.calculations` field is non-null — so RECTANGLE and CUSTOM rooms alike now show every authoritative value that actually exists, in the existing canonical PL/RU labels, never fabricating a `0` for a genuinely-null field; no backend change (floor/ceiling totals were already computed and sent, per the Stage 10H.1 Issue-3 trace — this was a frontend presentation gap only). 5 new focused frontend tests (project-detail card contrast, CUSTOM room floor+ceiling+wall summary, null-value omission, RECTANGLE room summary with all four rows) + full frontend suite **933/933 PASS**; tsc PASS; Vite build PASS; `git diff --check` CLEAN; backend unchanged (still 927/927 from the prior Final Gate); production deployed (commit `c812eaa`) and **owner Telegram retest: PASS** — both remaining Stage 10H.1 presentation regressions (dark-theme project-detail card values, CUSTOM room floor/ceiling preview) confirmed fixed in the real Telegram Mini App, and the four Stage 10H.1 corrections accepted in the prior retest round remain accepted. **STAGE 10H OWNER ACCEPTANCE: PASS.**

**Stage 10H final closure gate (2026-09-20):**
- Stage 10H.1: automated verification PASS; first Telegram retest **PARTIAL PASS** — of six owner-reported UX issues, four accepted outright (actionable client contact fields, dark-theme bare-page text contrast, bottom "Ukryj opcje"/"Zamknij" collapse actions, compact Estimate actions + deterministic group tint) and two presentation regressions (dark-theme project-detail card values; CUSTOM room floor/ceiling preview) carried forward to Stage 10H.2.
- Stage 10H.2: fixed the two carried-forward regressions — the project-detail white card's address/status/client values now use an explicit dark color instead of silently inheriting the page's theme-driven color; the CUSTOM room card now displays authoritative `floor_area`/`ceiling_area`/`total_wall_area` alongside `total_wall_area`-only before. Frontend 933/933 PASS; tsc PASS; Vite build PASS; `git diff --check` PASS; deployed to production; **owner Telegram retest: PASS**.
- Backend: **927/927 PASS** (unchanged since the Stage 10H Final Gate — Stage 10H.1/10H.2 were frontend-only).
- Frontend (final): **933/933 PASS**.
- TypeScript (`tsc --noEmit`): **PASS**.
- Vite production build: **PASS**.
- Alembic: single head `0021_client_telegram`, linear unbroken chain from `0001_create_users`.
- Production: **PASS** (deployed and serving the accepted build).
- Real Telegram owner walkthrough: **PASS**.

**Final verdict: STAGE 10H: COMPLETE. STAGE 10: COMPLETE / OWNER ACCEPTED.**

**Stage 10 canonical decisions (preserved, still in force for all future stages that touch Estimate/PriceBook data):**
- Estimate is snapshot-based: each version is a point-in-time generation from the current Work Plan, never silently synchronized with later Work Plan changes.
- Regeneration is always explicit — "Sprawdź zmiany" (preview, read-only) then an explicit confirm; nothing recalculates automatically.
- `unit_price: null` means unresolved / "Do ustalenia" ("Цена уточняется"), strictly distinct from an explicit `0.00`.
- A market/reference price shown in the Price Book never silently substitutes for the owner's own price.
- A FINAL Estimate is immutable; historical Estimate versions are preserved and remain readable (including their original provenance) after a new version is generated.
- Reveal (ościeże) geometry is computed and stored independently of WALL net/gross area and opening deductions — reveal totals never feed back into wall area math.
- `PriceUnit.LM` reveal work quantifies by reveal length (`QuantitySource.REVEAL_LENGTH`); `PriceUnit.M2` reveal work quantifies by reveal area (`QuantitySource.REVEAL_AREA`).
- Work planning exists at two independent levels: per-Surface (`SurfaceWorkPlan`) and per-Opening/reveal (`OpeningRevealPlannedWork`).
- An owner-created inline PriceItem (from either the Surface Work Plan picker or the Reveal picker) is a normal, fully-editable PriceBook entity — not a special estimate-only record.

**Non-blocking backlog (preserved, none promoted into Stage 11):**
- **ARCHIVED RECORD HARD DELETE — DEFERRED.** Current behavior: archive/restore remains the only supported lifecycle for Client/Project/Room/Surface/Opening/Work Plan/Estimate-adjacent records; nothing is ever hard-deleted today. Future hard-delete work must first define an explicit dependency/safety matrix across `Client → Project → Room → Surface → Opening → Work Plans → Estimate provenance/history`, and must never silently destroy a historical Estimate snapshot, its provenance, or any other dependent record. This is **not** a Stage 10 blocker and is **not** assigned to Stage 11 — the canonical roadmap does not require it there.
- Proactive (pre-attempt) unresolved-price counter on the Estimate view (currently only a reactive, localized, owner-accepted finalize-rejection count exists).
- Scope subtotal footer (Robocizna/Materiały/Mieszane/Razem) on the Estimate view.
- Seeded-row compact Price Book price editor re-null toggle (parity with the full `PriceItemForm`'s "Cena do ustalenia" checkbox).
- Stage 5G compact Surface Card Actions polish, if still recorded elsewhere as outstanding.

| Line-item calculation by surface, substrate, and quality tier (S1–S4, Q1–Q4) — see `docs/stage-10-architecture.md` |
| Stage 11 |
 Inspection → recommended work → add to estimate | **COMPLETE — OWNER ACCEPTED — INTEGRATED TO MAIN (2026-09-21)** after production deployment (`b8de1dc`) and the real Telegram Mini App owner walkthrough; merged to `main` by fast-forward as `73493d7` — 11A (read-only architecture audit) PASS 2026-09-20 (mapped existing Stage 6/7/9/10 domains, no gaps requiring destructive change); owner reviewed and approved decisions D1 (Opening/reveal recommendations deferred — no `opening_id` added to `Inspection`), D2 (ROOM-level results advisory-only, no auto-target-guessing), D3 (hybrid PriceItem resolution — stable `PriceItem.code` primary, manual fallback, market/reference price never substituted), D4 (`WorkRecommendationRule` is a separate small mapping catalog, not synonymous with `RiskRule` — Stage 7 remains the sole condition/risk authority), D5 (recommendation acceptance is one atomic explicit backend command, never a frontend read-modify-write of the WorkPlan); **11B.0 (contract verification + architecture specification) COMPLETE 2026-09-20 — documentation-only sub-stage, its full deliverable is this specification** — direct code/test verification (`work_plan_service.py`/`opening_reveal_work_service.py`'s `_rewrite_works`, and the existing `TestJ_AtomicReplace::test_replacing_works_deletes_old_rows` regression test) confirmed `SurfacePlannedWork.id`/`OpeningRevealPlannedWork.id` are **not durable** across ordinary WorkPlan edits (every write unconditionally deletes and recreates every child row) — this rules out a naive `recommendation_id` FK on the planned-work row and is documented, with the corrected semantic-provenance design, in `docs/stage-11-architecture.md`; canonical architecture document written (`WorkRecommendationRule`/`WorkRecommendation` schema, materialization contract, accept-command contract, dismiss/reconsider lifecycle, explicit Estimate non-interference invariant, mobile interaction contract, revised substage plan 11B.0→11B.1→11B.2→11C→11D→11E); **no application code, tests, or migrations touched in 11A/11B.0** — documentation-only; **11B.1 (recommendation catalog + persistence) COMPLETE 2026-09-20** — implements ONLY the persistence foundation per the canonical `docs/stage-11-architecture.md` contract, nothing beyond it: new models `WorkRecommendationRule` (pure lookup — `trigger_type` RISK_RULE/FINDING, `trigger_code`, `recommended_work_code` as a semantic `PriceItem.code` string, never a FK) and `WorkRecommendation` (materialized record; identity `(inspection_id, trigger_code, source_signature)` — the exact shape of `Risk`'s own identity; denormalized `room_id`/`surface_id`/`target_kind` target snapshot; audit-only nullable `rule_id`/`risk_id`/`finding_id`, all `ON DELETE SET NULL` so normal archive/resolve behavior never destroys recommendation history; lifecycle `status` PENDING/ACCEPTED/DISMISSED plus `is_active`/`resolved_at` mirroring `Risk`; `resolved_price_item_id`/`accepted_at`/`dismissed_at`; **deliberately no `accepted_planned_work_id`** per the 11B.0-verified planned-work row-ID instability); migration `0022_work_recommendations` (upgrade/downgrade/re-upgrade all verified against the real local Postgres instance, single Alembic head); minimal persistence-level `WorkRecommendationService` (`materialize_one`/`get_by_identity` only — no evaluation endpoint, no accept-to-WorkPlan mutation, no dismiss/reconsider endpoints, no Estimate change, no Opening/reveal, no ROOM→Surface selection, no frontend/UI — all correctly deferred to 11B.2/11C/11D); 21 focused tests (`test_work_recommendations.py`) covering both trigger types, semantic-code-not-FK, deterministic identity reuse and its DB-constraint enforcement, same-work-code-from-different-signatures, WALL/canonical-FLOOR/canonical-CEILING/ROOM targeting, the absence of any Opening field, all three lifecycle statuses, active/resolved reactivation, nullable `resolved_price_item_id` before acceptance, NULL-price-item referenceability, an explicit Stage 6/7 non-regression guard, and (added during final verification) one-trigger-recommends-three-independent-works and RiskRule/Finding trigger-type disambiguation; **final-verification correction (2026-09-20, same day)**: the initially-implemented `WorkRecommendation` unique identity `(inspection_id, trigger_code, source_signature)` was found to be a blocking cardinality bug before commit — `compute_source_signature` identifies only the source evidence and has no knowledge of `recommended_work_code`, so a single trigger legitimately mapping to several suggested works (e.g. a poor substrate recommending a primer AND a leveling compound) would have had its 2nd/3rd recommendation silently treated as "already materialized" and never created at all (not merely a constraint violation — silent data loss); corrected to the full `(inspection_id, trigger_type, trigger_code, source_signature, recommended_work_code)` identity — `trigger_type` also included so a `RiskRule.code` and an `InspectionFinding.finding_key` can never accidentally collide purely by string coincidence between the two independent vocabularies; `WorkRecommendationService.get_by_identity`/`materialize_one` updated to match; migration `0022_work_recommendations` corrected in place (re-verified: downgrade → upgrade clean, constraint columns confirmed at the Postgres catalog level) — no second migration created since 0022 was still unpushed; 2 new adversarial regression tests added (three-recommendations-from-one-trigger, and a deliberately colliding RiskRule-code/finding_key pair proving `trigger_type` disambiguates); full backend suite **948/948 PASS** (927 prior + 21 focused, zero regressions); Alembic single head `0022_work_recommendations`, upgrade/downgrade/re-upgrade verified against the real local Postgres instance; `git diff --check` CLEAN; only backend files touched, no frontend changes; Stage 10 remains **COMPLETE / OWNER ACCEPTED**, unaffected. **11B.2 (materialization/list/dismiss/reconsider lifecycle) COMPLETE 2026-09-20** — explicit, deterministic, idempotent room-wide reconciliation per `docs/stage-11-architecture.md`: `POST /api/projects/{project_id}/rooms/{room_id}/work-recommendations/evaluate` reconciles ALL currently active `Risk`/`InspectionFinding` (COMPLETED inspections only) rows in a room against the active `WorkRecommendationRule` catalog in one atomic commit, mirroring `RiskService._reconcile_risks`'s materialize/reuse/resolve-never-delete idiom, extended with the multi-work-per-trigger and sticky-lifecycle invariants (a PENDING row already active is left completely untouched — no gratuitous `updated_at` bump; DISMISSED and ACCEPTED are never reset to PENDING by re-evaluation; a source disappearing sets `is_active=False`+`resolved_at` without ever touching `status`, so `PENDING+inactive`/`DISMISSED+inactive`/`ACCEPTED+inactive` are all valid historical states; the same identity reappearing reactivates the existing row while preserving whatever lifecycle status it already had; a genuinely new `source_signature` always creates a new row, leaving the old one as untouched history); `GET /api/projects/{project_id}/rooms/{room_id}/work-recommendations` (query `activity=active|resolved|all`) never materializes or mutates, and attaches a read-time-only `current_price_item` PriceBook resolution preview (owner's current `PriceItem` by `code`, never the persisted `resolved_price_item_id` acceptance snapshot, never a market/reference price, NULL/`0.00`/archived states all preserved exactly as-is); `POST .../work-recommendations/{id}/dismiss` (PENDING→DISMISSED, idempotent if already DISMISSED, 409 if ACCEPTED) and `.../reconsider` (DISMISSED→PENDING, idempotent if already PENDING, 409 if ACCEPTED, never fabricates `is_active=true` — only evaluation can reactivate from real source evidence) are explicit owner commands, ownership-chain-validated (cross-project/cross-owner access rejected with 404, never trusting a bare `recommendation_id`); target derivation reuses `derive_target_type`+the existing read-only `find_active_plane_surface` helper for canonical FLOOR/CEILING (no surface ever created during evaluation — fails safe/skips if a canonical plane surface is structurally missing, which should not happen since Stage 10C.1A provisions it at room creation); ROOM-level results remain advisory-only (`surface_id=None`, no fabricated target); still zero Opening targets, zero WorkPlan/Estimate mutation of any kind, zero new migration (schema unchanged from `0022_work_recommendations`). 59 new focused tests (`test_work_recommendation_evaluation.py` ×21 covering materialization A–G and lifecycle reconciliation H–R plus target derivation AF–AJ; `test_work_recommendation_api.py` ×17 covering command/list/ownership S–AE plus 3 direct HTTP-level evaluate-endpoint wiring checks, including a 405 on `GET .../evaluate`) — full backend suite **986/986 PASS** (948 prior + 38 new — 21 evaluation + 17 API), zero regressions; **final-verification pass (2026-09-20, same day)**: 11 additional adversarial regression tests added after direct re-inspection of the reconciliation implementation confirmed (no bug found, but the invariant had no dedicated test) — room-vs-room isolation (evaluating Room A's resolved source never touches Room B's still-active recommendation, including its `updated_at`), multi-inspection selective resolution within one room (removing Inspection A's source resolves only its own recommendation, never Inspection B's, even sharing identical trigger_type/trigger_code/recommended_work_code — `inspection_id`+`source_signature` alone separate them), inactive-`Risk`-never-materializes and historical-resolved-`Risk`-cannot-rematerialize, all four `InspectionFinding` source filters (active+COMPLETED participates; active+DRAFT does not; inactive does not; a different room's finding does not), reconciliation provably never touches `accepted_at`/`resolved_price_item_id` on an ACCEPTED row or `dismissed_at` on a DISMISSED row across repeated evaluate/resolve/reactivate cycles, and cross-owner PriceItem isolation at read time (Owner A's recommendation never resolves Owner B's same-code PriceItem). Also verified directly by code/route inspection (no test needed): each of `evaluate_recommendations`/`dismiss`/`reconsider` owns exactly one commit boundary (no partial mid-evaluation commits); the live FastAPI route table was enumerated and confirmed all four routes registered correctly under the canonical `/api` prefix (never `/api/v1`) with no path-ordering ambiguity between the room-scoped `.../work-recommendations`/`.../evaluate` routes and the flat `.../work-recommendations/{id}/dismiss`/`.../reconsider` routes; archived-vs-missing-vs-current PriceItem representation in `current_price_item` was confirmed already unambiguous, no schema change needed. Full backend suite **997/997 PASS** (986 prior + 11 new), zero regressions; Alembic current == heads == `0022_work_recommendations` (single head, no new migration); `git diff --check` CLEAN; no frontend files changed. **11C.0 (read-only WorkPlan atomic-acceptance contract audit) COMPLETE 2026-09-20** — no code changes; confirmed all three existing WorkPlan write methods (`set_plan`/`replace_planned_works`/`apply_to_room_walls`) commit internally and are therefore unreusable as-is by acceptance; reconfirmed `SurfacePlannedWork.id` non-durability; identified the exact minimal no-commit append primitive needed; identified two distinct required row locks (recommendation, then plan) mirroring the existing `EstimateService._lock_project` precedent; flagged two factual corrections needed in `docs/stage-11-architecture.md` (409→404 for missing plan; a REVEAL-category guard would be new, not a reused Stage 10 invariant) — both now corrected in 11C.1 below. **11C.1 (atomic recommendation acceptance) COMPLETE 2026-09-20** — `POST /api/projects/{project_id}/work-recommendations/{recommendation_id}/accept`: locks the `WorkRecommendation` row (`SELECT ... FOR UPDATE OF work_recommendations`, never the joined Room/Project rows) first, then the target `SurfaceWorkPlan` row second (fixed, never-inverted order); resolves the `PriceItem` fresh at accept time (semantic `owner_id`+`recommended_work_code`, or an explicit owner-supplied `price_item_id` override that may carry a different code — `recommended_work_code` itself is never overwritten); validates archived (rejected, existing Stage 10 rule) and a new Stage-11-only REVEAL-category rejection (lives solely in `WorkRecommendationService._resolve_accept_price_item`, never in `SurfaceWorkPlanService` — the existing permissive Stage 10 manual Work Plan picker is completely unchanged and still accepts REVEAL items); appends exactly one `SurfacePlannedWork` via a new additive-only `SurfaceWorkPlanService.append_one_planned_work_no_commit` primitive (computes `MAX(position)+1` fresh from the database while the plan row is locked, never calls `_rewrite_works`, never deletes/renumbers any existing row, never touches substrate/quality_target) — the existing `set_plan`/`replace_planned_works`/`apply_to_room_walls` full-replace behavior is entirely unchanged; sets `status=ACCEPTED`+`resolved_price_item_id`+`accepted_at` in the SAME transaction as the append, with exactly **one** final `db.commit()`; ACCEPTED is idempotent (repeat accept, even with a different manual `price_item_id`, returns the original unchanged snapshot, never a second append); DISMISSED rejected (409, existing `WorkRecommendationStateError`); ROOM-target rejected (422, new minimal `WorkRecommendationTargetError` — no existing exception fit this failure category); missing `SurfaceWorkPlan` rejected (404, existing `SurfaceWorkPlanNotFoundError` — never auto-created, never invents substrate/quality_target); PENDING+inactive/resolved is still accepted as-is per the already-settled architecture decision (acceptance never touches `is_active`/`resolved_at` — only evaluation does); zero Estimate/EstimateLine interaction. **Real-concurrency proof, not just reasoning**: a standalone script ran two genuinely concurrent `accept_recommendation` calls for the same recommendation against the actual local PostgreSQL instance (not the SQLite test harness) — the query log directly showed the second request's row-lock acquisition blocking until the first committed, after which it correctly took the idempotent no-op path; exactly one `SurfacePlannedWork` row resulted. This exact proof cannot run inside the pytest suite (SQLite's single shared test connection has no real row-level locking and silently no-ops `FOR UPDATE`) — the pytest suite instead proves the equivalent *sequential* outcome (repeat-accept-never-duplicates; different recommendations on the same plan never collide on position), explicitly documented as such in the test file's own module docstring rather than claiming a false concurrency guarantee. 91 new focused tests (`test_work_recommendation_accept.py` ×38 covering the full success/idempotency/duplicate/invalid-state/PriceItem/rollback/no-Estimate matrix; `test_work_recommendation_api.py` +11 covering accept endpoint wiring and the full ownership chain — recommendation-from-another-project, recommendation-owned-by-another-owner, manual-PriceItem-from-another-owner, and the valid chain succeeding); full backend suite **1046/1046 PASS** (986 prior + a net 60 covering both files' additions — see exact per-file counts above), zero regressions; Alembic current == heads == `0022_work_recommendations` (single head, no new migration — none was needed); `git diff --check` CLEAN; no frontend files changed; `docs/stage-11-architecture.md` corrected in place for the two factual mismatches identified in 11C.0 (409→404 for missing plan; 422→404 for missing PriceItem reusing the existing `PriceItemNotFoundError`) and extended with the actual-implementation description of the append primitive, the two-lock ordering, and the REVEAL guard's Stage-11-only scope — no other section redesigned. **11C.1 final-verification pass (2026-09-20, same day)**: re-derived every concurrency/lock-ordering/idempotency claim directly from the committed code (not from memory) and additionally proved, against the real local PostgreSQL instance, the second required concurrency scenario — two different recommendations targeting the SAME `SurfaceWorkPlan` accepted genuinely concurrently (an injected delay forced real blocking on the plan-row lock, confirmed via query-log evidence) — resulting in exactly 2 planned works with distinct, correctly ordered positions and no `IntegrityError`, complementing the already-proven same-recommendation race; 3 further regression tests added to close explicitly-requested gaps (repeat-accept-after-manual-fallback keeps the original manual item; optional-body `{}` and explicit `{"price_item_id": null}` both resolve semantically identically to an omitted body); one existing test strengthened to assert the exact preserved `resolved_at` timestamp rather than merely "not None" (surfaced and fixed a SQLite-test-harness timezone-naive-comparison artifact, not a product bug). Corrected counts: `test_work_recommendation_accept.py` **39** tests, `test_work_recommendation_api.py` accept-related subset **13** tests; full backend suite **1049/1049 PASS** (1046 prior + 3 new), zero regressions; Alembic current == heads == `0022_work_recommendations` unchanged; `git diff --check` CLEAN; working tree scope unchanged (8 modified + 1 new test file, no frontend/Estimate/migration files touched). **11C.2 (acceptance gap audit) COMPLETE 2026-09-20 — read-only audit, no code/test/doc changes required — Result: NO_GAPS**: confirmed the complete Stage-11C backend acceptance contract across explicit recommendation lifecycle (PENDING/ACCEPTED/DISMISSED transitions, including DISMISSED+inactive reconsider never reactivating source activity, and ACCEPTED surviving both later source resolution and later source reactivation); actionable WALL/canonical-FLOOR/canonical-CEILING targets vs. advisory-only ROOM targets (no Surface ever silently created); atomic recommendation acceptance (`WorkRecommendation` row lock → `SurfaceWorkPlan` row lock → `MAX(position)` → append/flush → recommendation snapshot → one commit, never reversed, no intermediate commit); deterministic additive position assignment; idempotent repeat acceptance (including after a manual-fallback override); duplicate `PriceItem` occurrences across different recommendations permitted by design; rollback atomicity; semantic + manual `PriceItem` resolution (ownership-scoped, `recommended_work_code` never overwritten); archived/NULL/`0.00` price handling preserved exactly; REVEAL rejection confirmed Stage-11-only (the existing Stage 10 manual Work Plan picker still accepts REVEAL items, regression-tested); ownership isolation (cross-project/cross-owner recommendation and manual `PriceItem` access both rejected); zero Estimate/EstimateLine mutation; Stage-10 `set_plan`/`replace_planned_works`/`apply_to_room_walls`/`_rewrite_works`/`_resolve_owned_items` confirmed unchanged by direct re-read against the pushed 11C.1 commit. Verification evidence: recommendation-related coverage **120 tests across 4 files** (`test_work_recommendations.py`, `test_work_recommendation_evaluation.py`, `test_work_recommendation_api.py`, `test_work_recommendation_accept.py`), all directly exercising the contract rather than relying on code inspection alone; full backend baseline from 11C.1 **1049/1049 PASS**; real PostgreSQL same-recommendation concurrency proof **PASS**; real PostgreSQL same-plan/different-recommendation concurrency proof **PASS**; Alembic single head **`0022_work_recommendations`** unchanged, no migration required; **no runtime gaps, no test gaps, no documentation gaps found**. `docs/stage-11-architecture.md` required no changes (no factual contradiction discovered during this audit). **Stage 11C backend acceptance (11C.0 + 11C.1 + 11C.2) is now COMPLETE.** **11D.0 (mobile UI contract audit) COMPLETE 2026-09-20 — read-only, no code changes**: traced the actual existing frontend flow (Project → Room → Surface → Inspection → completed inspection results → `RiskPanel`/`CommunicationPanel` → `SurfaceWorkPlanEditor` ("Rodzaje prac i jakość") → `EstimateShell`/"Sprawdź zmiany"), confirmed zero existing recommendation frontend support, and defined the integration contract: recommendations render inside the existing completed-inspection results section (alongside `RiskPanel`/`CommunicationPanel`, never a new screen or modal), evaluation stays an explicit user action mirroring `RiskPanel`'s own "Ewaluuj/Reewaluuj" precedent (never on plain render), ROOM targets are advisory-only with no Surface guessing, and Stage 10's `SurfaceWorkPlanEditor` picker/save mutation is never reused directly — acceptance (11D.2) will call the dedicated Stage 11 `/accept` endpoint through a small standalone selection widget instead. Owner-approved decisions: (1) a small standalone recommendation PriceItem selection widget for 11D.2, not a refactor of the existing Stage-10 picker; (2) Stage 11D uses informational Estimate-staleness messaging only, no cross-screen navigation to `EstimateShell`. Split into **11D.1** (API client + types + read/evaluate/dismiss/reconsider lifecycle panel) and **11D.2** (acceptance + manual PriceItem fallback + price/archived/REVEAL edge cases + Estimate-staleness messaging + final mobile hardening). **11D.1 (recommendation panel foundation) COMPLETE 2026-09-20**: new `frontend/src/types/workRecommendation.ts` (mirrors `WorkRecommendationRead`/`WorkRecommendationListResponse`/`WorkRecommendationEvaluateResponse` exactly, reusing the existing `SurfacePriceItemSummaryRead` type; `status` and `is_active` kept as independent fields, never collapsed) and `frontend/src/api/workRecommendations.ts` (plain `apiRequest` pattern identical to `risks.ts`, no react-query/state library introduced; deliberately does not implement `acceptWorkRecommendation` yet); new `RecommendationPanel.tsx` component modeled directly on `RiskPanel`/`CommunicationPanel` (evaluate/reevaluate button, active/resolved/all activity tabs using the canonical backend query values, per-recommendation "Opcje" progressive-disclosure toggle revealing PENDING→dismiss or DISMISSED→reconsider, no lifecycle action rendered for ACCEPTED), wired into `InspectionFlow.tsx`'s completed-results section directly between `RiskPanel` and `CommunicationPanel`; list results are fetched room-wide then filtered client-side to the current `inspection_id` (the backend list/evaluate endpoints are room-scoped, not inspection-scoped, since evaluation reconciles the whole room); card rendering reuses existing conventions verbatim (`t.pricebook.price_not_set` = "Do ustalenia" for NULL price, explicit "0,00 zł" for a real zero price, `t.pricebook.archived_badge` for an archived current PriceItem, a compact "Brak pozycji cennika dla tej pracy." state when no PriceItem currently resolves, and an independent "Nieaktualne"/"Nieaktualne od {date}" badge for `is_active=false` regardless of lifecycle `status`); ROOM-target recommendations render as a purely informational card (no Surface guessed, no accept action — accept does not exist yet in 11D.1 regardless of target). New PL/RU locale keys added under `recommendations.*` (33 keys each, verified identical key sets via the repository's existing locale parity test). Explicitly NOT implemented in 11D.1 (deferred to 11D.2 per the approved split): accept action, manual PriceItem fallback/picker, WorkPlan refresh, Estimate-staleness messaging, REVEAL/archived/missing-item accept-time UX. 21 new focused tests (`RecommendationPanel.test.tsx`) covering initial-GET-only/no-auto-evaluate, explicit evaluate + list refresh, PENDING/ACCEPTED/DISMISSED rendering, inactive/resolved shown independently of an ACCEPTED status, all three activity tabs sent explicitly, NULL vs. explicit-zero price, missing/archived current PriceItem, dismiss, reconsider (including that a reconsidered-but-still-inactive recommendation never falsely shows active), request-pending double-submit protection, localized error rendering, ROOM advisory rendering, an explicit assertion that no accept action exists anywhere in the 11D.1 panel, spy-verified proof that no `SurfaceWorkPlan`/`Estimate` API function is ever called by this panel, and a mobile touch-target/single-column structural regression mirroring `RiskPanel.test.tsx`; 2 `InspectionFlow.test.tsx` assertions extended to confirm the recommendation section renders only for COMPLETED inspections and never for a DRAFT. **11D.1 final-verification pass (2026-09-20, same day)**: re-derived type parity against the actual backend Pydantic schemas field-by-field (EXACT match, including the reused `SurfacePriceItemSummaryRead`), traced every call site of `evaluateWorkRecommendations` (exactly one, the button's own `onClick`) and confirmed mount/filter-switch/dismiss/reconsider never call it, confirmed status and `is_active` badges are derived from strictly independent fields with no cross-inference, confirmed `ROOM` detection uses the authoritative `target_kind` field rather than inferring from a missing `surface_id`, and confirmed via `ProjectWorkspace.tsx`'s own singleton `activeInspection`/`inspectionTarget` state (with a remount-forcing `key`) that only one `InspectionFlow` — and therefore only one `RecommendationPanel` — can ever be mounted at a time, ruling out duplicate room-wide panels; found and fixed two orphan locale keys (`archived_notice`, `target_room`, defined but never referenced) by removing them, and one under-used key (`error_conflict`) by wiring it into the existing error-mapping helper for the "already-accepted" 409 dismiss/reconsider conflict (previously fell through to a generic fallback message); added 2 regression tests closing gaps found during verification (PENDING+inactive lifecycle/activity independence combination; the newly-wired already-accepted 409 conflict message) — `RecommendationPanel.test.tsx` now has **23 tests**. Full frontend suite re-run **956/956 PASS** (34 files, includes the existing locale parity test, confirmed OK via a fresh key-set diff); `tsc --noEmit` **PASS**; production `vite build` **PASS** (89 modules); `git diff --check` CLEAN; scope re-confirmed as exactly the expected files — no backend, no migration, no `SurfaceWorkPlanEditor`/`EstimateShell` changes. Evaluation triggered from any one surface's completed-inspection panel is honestly disclosed as room-wide in the hint copy itself ("Oceń zalecane prace dla całego pomieszczenia…"), matching the backend's actual room-wide reconciliation contract. **11D.2 (acceptance + manual fallback + Estimate-staleness messaging + final mobile hardening) IMPLEMENTED / AUTOMATED VERIFICATION PASS 2026-09-20** — NOT yet owner-accepted, manual local/mobile walkthrough still pending: added `acceptWorkRecommendation(projectId, recommendationId, {price_item_id?})` to `frontend/src/api/workRecommendations.ts` (always POSTs a body — `{}` for semantic resolution, `{price_item_id}` for manual override — mirroring the backend's own three-equivalent-forms contract) and a matching `WorkRecommendationAcceptRequest` type; `RecommendationPanel` now shows **"Dodaj do prac"** for a PENDING, actionable (WALL/FLOOR/CEILING, never ROOM) recommendation whose `current_price_item` currently resolves, is not archived, and is not REVEAL-category — clicking it calls the accept endpoint directly and never fetches/mutates the `SurfaceWorkPlan` itself (backend owns the atomic append); NULL and `0.00` prices both keep acceptance enabled (strict `=== null` check, no truthiness collapse); when the item is missing, archived, or REVEAL, the primary action is hidden (never presented as if it could succeed) and a **"Wybierz pozycję ręcznie"** button opens a new small standalone `frontend/src/components/RecommendationPriceItemPicker.tsx` (163 lines) — deliberately NOT a refactor of `SurfaceWorkPlanEditor`'s picker/draft/mutation state per the 11D.0-approved decision — which fetches active owner PriceItems via the existing `fetchPriceItems` client, excludes REVEAL category items, permits NULL-price and `0.00`-price items, requires an explicit tap-to-select-then-confirm interaction (never accepts on the first tap, to avoid accidental mobile mis-taps), and reports the chosen id back through the same `acceptWorkRecommendation` call (never a second, different mutation path). On success the recommendation becomes ACCEPTED, the accept action disappears, and a transient, session-local success line is shown — **"Praca dodana do planu. Kosztorys nie został jeszcze zaktualizowany."** — informational only, never navigating to, previewing, or regenerating the Estimate (owner decision: no cross-screen navigation in 11D). Per-recommendation pending state (reused from 11D.1's dismiss/reconsider mechanism) disables the accept button, the fallback picker's selection/confirm controls, and prevents duplicate submits while a request is in flight. Error mapping added a dedicated `ApiError`-status-based helper distinguishing the two distinct backend 404s (`"Target surface has no work plan yet"` → localized setup guidance **"Najpierw skonfiguruj „Rodzaje prac i jakość” dla tej powierzchni."**, vs. any other 404 → the existing generic not-found text), 409 (lifecycle conflict — the existing `error_conflict` wording was generalized from its 11D.1 accepted-only phrasing to cover any lifecycle conflict, since accept's own 409 is a different underlying state) and 422 (validation) into new localized, non-raw-exception text; no automatic retry on any error. Explicitly honored 11D.1 regressions: initial mount and activity-filter switching still never evaluate; dismiss/reconsider/lifecycle-activity independence/ROOM-advisory-no-guessing all re-verified unchanged; no duplicate room-wide panel risk (unchanged singleton `InspectionFlow` mounting, confirmed again). `current_price_item` on ordinary list/reload responses is still never mislabeled as the historical accepted snapshot — the success message is purely transient session feedback from this panel's own action, never re-derived or re-shown after a reload (dedicated regression test). New PL/RU locale keys added under `recommendations.*` (accept/accepting/accept_success/action_unavailable/fallback_button/missing_work_plan/error_accept/error_invalid_selection/picker_* — 11 new keys each, verified identical key sets and zero orphans). 66 new/changed focused tests: `RecommendationPanel.test.tsx` grew from 23 to 43 (one obsolete 11D.1 invariant test — "no accept action anywhere" — was retired since 11D.2 intentionally supersedes it, replaced with a PENDING-vs-ACCEPTED side-by-side check; 21 new acceptance tests covering the actionable/NULL/zero/missing/archived/REVEAL matrix, the full fallback-picker flow including REVEAL exclusion and NULL/zero support, double-submit protection, 404/409/422 mapping, and the accepted-snapshot-safety regression); new `RecommendationPriceItemPicker.test.tsx` (9 tests: load, search, REVEAL exclusion, NULL/zero display, select-then-confirm, disabled-while-submitting, cancel-never-confirms, touch targets); new `workRecommendations.test.ts` (3 tests: exact route/method/body for both semantic and manual-id forms, response parsing) following the existing `workPlans.test.ts` API-test convention; `InspectionFlow.test.tsx` mocks extended with `acceptWorkRecommendation`/`fetchPriceItems` (33 tests unchanged, still green). Full frontend suite **988/988 PASS** (36 files, up from 34). **11D.2 final-verification pass (2026-09-20, same day)**: re-derived the accept API contract directly from the live backend endpoint code (exact route/method/body/response, all three 404 detail strings read verbatim); confirmed the `canAcceptNormally`/`needsFallback` predicates never touch `summary.price` at all (zero truthiness-collapse risk for NULL/0.00 by construction, not just by test); confirmed via `ProjectWorkspace.tsx`'s mutually-exclusive `activeInspection` branch that `InspectionFlow`/`RecommendationPanel` and `SurfaceList`/`SurfaceWorkPlanEditor` can never be visible at the same time, so no stale-WorkPlan-editor risk exists (not merely "acceptable" — structurally impossible, and the editor still fresh-fetches on its own next mount regardless); classified the missing-WorkPlan 404 discriminator (`ApiError.status===404 && message==='Target surface has no work plan yet'`) as ACCEPTABLE_BUT_COUPLED — an exact literal-string match with safe graceful degradation on drift (falls back to the generic not-found text, never crashes or leaks raw text), identical in kind to the already-accepted Stage-10 `isSurfaceWorkPlanMissing` precedent (also unguarded by any backend-side string-locking test) — judged not to warrant a backend change. Found and closed 2 real test gaps: a non-`ApiError` network-failure path (e.g. `TypeError: Failed to fetch`) had no dedicated test proving it degrades to the same generic localized message while leaving the UI usable; the 409-conflict test didn't verify prior lifecycle state survives a failed accept untouched (no optimistic update exists to roll back, confirmed by both code trace and the new assertion). `RecommendationPanel.test.tsx` grew from 43 to **44** tests; full frontend suite re-run **989/989 PASS** (36 files); `tsc --noEmit` **PASS**; production `vite build` **PASS** (90 modules); `git diff --check` CLEAN; scope re-confirmed frontend-only — no backend, no migration, no `SurfaceWorkPlanEditor`/`EstimateShell` changes. `RecommendationPanel.tsx` 493 lines / `RecommendationPriceItemPicker.tsx` 163 lines — judged still coherent and comparable to `CommunicationPanel.tsx` (601 lines), no further extraction needed. **Manual local/mobile acceptance walkthrough (390px/412px, PL+RU) still required before Stage 11D can be marked owner-accepted; **Stage 11D.2 manual acceptance (2026-09-21) found a functional gap: `work_recommendation_rules` was empty in the real dev database — Stage 11B.1's own substage plan said to "seed a handful of rule mappings" but the actual 11B.1 delivery implemented only the persistence foundation, never real catalog rows (only test fixtures ever inserted synthetic rows), so every real "Oceń zalecenia" click returned zero recommendations regardless of which risks/findings fired; confirmed by direct read-only inspection of the running dev Postgres (0 rows in `work_recommendation_rules` and `work_recommendations`) against the owner's actual completed WALL inspection (5 real active Stage 7 risks: `CRACK_RECURRENCE`, `UNEVENNESS_PREP_INCREASED`, `DUSTY_SUBSTRATE_PRIME`, `EFFLORESCENCE_CAUSE_CHECK`, `WEAK_ADHESION_PREP`) — not a runtime defect, a genuine catalog gap.** **Stage 11B.1.1 (baseline WorkRecommendationRule catalog) COMPLETE 2026-09-21** — closes that gap with an explicit, owner-verified, HIGH-confidence-only baseline: audited all 15 Stage 7 baseline risk rules (`app/domain/data/risk_rules.py`) against the 45-item canonical PriceBook seed catalog (`app/domain/data/price_book_seed.py`), classifying each candidate mapping HIGH/MEDIUM/NONE by whether an existing `PriceItem`'s own PL locale description is a direct semantic match for the risk's mitigation text; only the four owner-approved HIGH mappings were implemented — `DUSTY_SUBSTRATE_PRIME → CENNIK_PRIM_STD-01`, `WEAK_ADHESION_PREP → CENNIK_PRIM_ADH-01`, `UNEVENNESS_PREP_INCREASED → CENNIK_SKIM_LOCAL-01`, `CRACK_RECURRENCE → CENNIK_SKIM_CRACK-01` (all `trigger_type = RISK_RULE`, none `FINDING`, verified against the catalog's actual PL names, e.g. `CENNIK_PRIM_ADH-01` = "Gruntowanie gruntem kontaktowym adhezyjnym" — a direct match for weak-adhesion priming); `EFFLORESCENCE_CAUSE_CHECK` is **intentionally left unmapped** — its mitigation calls for a salt-blocking treatment with no matching PriceItem in the current catalog, and the owner explicitly declined the plausible `CENNIK_PREP_SCRAPE-01` (paint/skim-coat scraping) substitute as not semantically representing moisture/salt-cause treatment; several additional HIGH-confidence candidates found during the audit (`OILY_SUBSTRATE_DEGREASE → CENNIK_PREP_DEGR-01`, `MOLD_TREATMENT_BEFORE_FINISH → CENNIK_PREP_MOLD-01`, `JOINT_TAPE_MISSING_REWORK → CENNIK_GK_JOINT-01`) and six MEDIUM/compound-action candidates (`BOARD_MOVEMENT_CRACK`, `LOOSE_SUBSTRATE_REMOVAL`, `DELAMINATION_REPAIR`, `FASTENER_CORROSION_FIX`, `JOINT_GAP_FILLING`, `BLOW_HOLES_FILLING`) plus one further NONE (`MOISTURE_BLOCK_FINISHING` — its mitigation is "wait, don't work yet", not a workable item) were deliberately left out of this pass pending explicit owner approval (documented in `app/domain/data/work_recommendation_rules.py`'s module docstring). Seeding architecture mirrors `RiskService._ensure_bootstrapped` exactly: a new `app/domain/data/work_recommendation_rules.py` baseline data module plus a `WorkRecommendationService._ensure_bootstrapped()` method (lazy, idempotent, keyed on the table's own `(trigger_type, trigger_code, recommended_work_code)` unique constraint, no version field needed since `WorkRecommendationRule` has none) called from both `evaluate_recommendations` and `list_recommendations` — the established Stage 7 convention is lazy application-bootstrap, not an Alembic data migration, and this stays consistent with it; no migration created, Alembic single head unchanged (`0022_work_recommendations`). `recommended_work_code` remains a semantic string only — no owner_id, no PriceItem FK, no price snapshot on the rule row; resolution against the current owner's PriceBook stays entirely at evaluate/accept time, and a `NULL`/`0.00` PriceItem price is proven (by test) to never block materialization. Separately addressed the zero-result UX ambiguity flagged during the same manual acceptance: `RecommendationPanel` previously showed the identical static "Brak zaleceń" text both before any evaluation and after an explicit successful evaluation returned zero, making the primary action look like it silently did nothing; added session-local-only `hasEvaluated` state (never persisted) so a successful zero-result evaluation now shows "Nie znaleziono zaleceń dla zakończonych badań" / "Для завершённых обследований рекомендации не найдены" instead, scoped to the `active` tab only; the untouched pre-evaluation and evaluation-error states are unchanged; `RiskPanel`/`CommunicationPanel` were deliberately left untouched (same static-message pattern, out of scope for this fix). Tests: 16 new backend tests (`test_work_recommendation_baseline_catalog.py` — baseline data shape/no-duplicates/EFFLORESCENCE-excluded/canonical-code-membership, bootstrap idempotency/never-overwrites-existing, bootstrap-triggered-by-evaluate-and-list, and an integration suite reproducing the owner's exact real scenario proving exactly 4/5 recommendations materialize with `EFFLORESCENCE_CAUSE_CHECK` correctly absent and NULL-price non-blocking); full backend suite **1065/1065 PASS** (up from 1049); 4 new frontend tests (`RecommendationPanel.test.tsx` — untouched pre-evaluation text, distinct post-evaluation zero-result text, error state never shows the zero-result text, a later non-empty evaluate replaces the message) — full frontend suite **999/999 PASS** (up from 995, still 36 files); `tsc --noEmit` PASS; production `vite build` PASS (90 modules); `git diff --check` CLEAN. **Manual Stage 11D.2 acceptance remains pending** — the owner should restart the backend (or otherwise trigger the next `evaluate`/`list` recommendations call, which lazily bootstraps the baseline with no manual seed command or Docker involved) and re-run "Oceń zalecenia" on the same real inspection, now expecting exactly 4 recommendations, never 5; **Manual acceptance then found a further, Stage-10-scoped gap: accepting `CRACK_RECURRENCE` produced an Estimate line showing a misleading `0.000 mb` (unresolved MANUAL quantity, no Surface length geometry exists) that could pass finalize once priced — fixed as `Stage 10H.1` (see its dedicated section below): FINAL now also blocks on unresolved MANUAL quantity, and the Estimate UI shows "Ilość do ustalenia" instead of a bare 0.000; `CENNIK_SKIM_LOCAL-01`'s own full-surface-vs-local-repair quantity semantics remain a separate, deliberately deferred product decision.** A follow-up manual UX defect (#4) then found the same 0.000-fallback issue still present in the Estimate's main card/list view (only the drilled-down detail view had been fixed); closed with a shared `quantityDisplay` helper covering both render paths — **owner manually accepted the complete quantity-hardening flow 2026-09-21 (unresolved display parity in both views, manual 4.5 entry, reset, and independent price/quantity FINAL blocking all verified end-to-end)**; see `Stage 10H.1` below for full detail. **11D.2 (recommendation acceptance UI + manual fallback picker) COMPLETE — OWNER ACCEPTED 2026-09-21**, integrated together with the approved Manual UX Defect #1 fix (new-surface-inspection WorkPlan substrate/quality inheritance), Stage 11B.1.1 (baseline recommendation catalog), and Stage 10H.1 (unresolved manual quantity hardening) in one verified commit `b8de1dc` (`feat(stage-11): complete recommendation acceptance UI`), pushed to `origin/stage-11`. **11E.0 (final release-readiness audit) COMPLETE — PASS 2026-09-21**: full read-only audit of the entire Stage 11 contract (11B.1/11B.2/11C/11D lifecycle, ownership/security, API/type parity, negative/boundary checks, mobile structural review) found zero blockers; full backend suite 1081/1081 PASS, full frontend suite 1016/1016 PASS, `tsc`/`vite build` PASS, single Alembic head `0022_work_recommendations` confirmed (local dev DB `current == heads`), `git diff --check` CLEAN — no code changed during the audit. **11E.1 (production deployment + Telegram owner walkthrough) COMPLETE — OWNER ACCEPTED 2026-09-21**: this session's own SSH access to the production Oracle Cloud host was denied by the permission system, so the deploy itself (build, `docker compose -f docker-compose.prod.yml up -d`, Alembic auto-migration on backend startup, and the Telegram Menu Button cache-buster update) was performed directly by the project owner following `docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md`; the owner reported and this document records: production runtime commit `b8de1dc` deployed; `alembic current == heads == 0022_work_recommendations`; PostgreSQL/backend/frontend/Caddy containers healthy; `https://plan-estimate.pl` HTTPS + `/api/health` PASS with no 5xx; Telegram Menu Button WebApp URL updated to `https://plan-estimate.pl/?v=b8de1dc` and verified. The subsequent real Telegram Mini App walkthrough verified the full canonical chain end-to-end on production: existing SurfaceWorkPlan substrate/quality preserved and correctly reused by a new surface inspection (skipping the redundant setup questions); Stage 7 risks and findings produced Stage 11 recommendations via the baseline catalog; recommendation cards rendered correctly in the real Telegram mobile WebView; explicit "Dodaj do prac" moved a recommendation PENDING → ACCEPTED and additively appended the work to the existing SurfaceWorkPlan without touching other planned work; the existing Estimate did not silently update; explicit "Sprawdź zmiany" detected the new planned work, with the preview correctly showing "Remont pęknięć (rozszycie, wypełnienie)" as an unresolved LM quantity rather than a fake `0.000`; explicit regeneration added it to a new DRAFT version; the main estimate card and the detailed line view both correctly displayed "Ilość do ustalenia / mb"; the owner set an explicit `4.500 LM` override via the existing line-edit control, which persisted and displayed correctly; finalize was correctly rejected because unresolved prices remained (the estimate stayed DRAFT); no automatic Estimate mutation/regeneration occurred anywhere in the recommendation-acceptance flow; and real Telegram mobile rendering showed no observed horizontal overflow or overlapping controls on the tested screens. **STAGE 11 STATUS: COMPLETE — OWNER ACCEPTED — INTEGRATED TO MAIN (2026-09-21).** The canonical chain (`Inspection → Finding/Risk result → Work Recommendation → explicit owner acceptance → existing Surface WorkPlan → explicit Estimate preview/regeneration`) is fully implemented end-to-end in production, with the `RECOMMENDATION != PLANNED WORK` invariant preserved throughout (recommendations never silently become planned work; the Estimate is never silently regenerated). Deliberately preserved, not-yet-addressed backlog (none promoted into this closure): opening/reveal recommendation support; the `UNEVENNESS_PREP_INCREASED`/`CENNIK_SKIM_LOCAL-01` local-vs-full-Surface-M2 quantity product-policy question; the `OILY_SUBSTRATE_DEGREASE`, `MOLD_TREATMENT_BEFORE_FINISHING`, and `JOINT_TAPE_MISSING_REWORK` recommendation-rule mapping candidates found during the Stage 11B.1.1 audit; the cosmetic duplicated-finalize-error-wording cleanup; physical hard-delete dependency/safety work; and Stage 5G compact Surface Card Actions polish. **Stage 12 remains NOT STARTED.** | Automatic mapping from inspection findings to scope of work and estimate line items — see `docs/stage-11-architecture.md` |
| Stage 12 | Price coefficients | **Stage 12: COMPLETE · Implementation COMPLETE · Automated verification PASS · Local owner walkthrough PASS · Production deployment PASS · Telegram production walkthrough PASS · OWNER ACCEPTED: PASS** — Sub-stages: 12A audit COMPLETE; 12B architecture COMPLETE; 12C coefficient catalog persistence/bootstrap/API COMPLETE; 12D occurrence-specific WorkPlan assignments COMPLETE; 12E Estimate coefficient calculation/snapshot/preview/regeneration COMPLETE; 12F mobile coefficient/catalog UI COMPLETE; 12G canonical business model/default groups/descriptions/localization COMPLETE; 12H automated/adversarial verification COMPLETE. History follows: 12A (read-only architecture audit) COMPLETE 2026-09-21 (no code changed; conceptual model, snapshot semantics, override interaction, scope, multi-coefficient combination, fixed-surcharge distinction, labor/material eligibility, ownership, and Stage 11 compatibility all analyzed against the actual current `PriceItem`/`SurfaceWorkPlan`/`EstimateLine` architecture; zero existing coefficient functionality found; D1–D10 candidate decisions proposed for owner review); **12B (architecture specification) COMPLETE 2026-09-21 — documentation only, no application code/migration/branch created** — owner approved D1–D11 (percentage representation; single-planned-work-occurrence scope organized into `SINGLE_SELECT` groups/levels; labor-only, `LABOR_AND_MATERIAL` rejected in v1 absent an existing labor/material price split; additive-not-compounding combination; manual override remains authoritative and wins over any calculated value; a separate owner-editable catalog, not a second Price Book; assignment lives inside the existing "Rodzaje prac i jakość" WorkPlan editor via a "Współczynnik" control; legacy `EstimateLine` rows get honest `NULL` provenance, never a fabricated `0%`; fixed surcharges stay architecturally distinct from percentage coefficients and reuse the existing MANUAL line mechanism unchanged; coefficients are applied only by explicit owner action, never automatically from an Inspection/Risk/Recommendation; a group's `0%` "base" option is a per-owner catalog fact, never a universal hardcode) recorded as canonical in `docs/stage-12-architecture.md`; resolved the critical durable-planned-work-assignment problem (Stage 11B.0 already proved `SurfacePlannedWork.id`/`OpeningRevealPlannedWork.id` are non-durable across ordinary full-replace WorkPlan edits) by recommending coefficient assignment travel **inside the same atomic WorkPlan replace payload/operation** as the work selection itself, rather than any FK expected to survive independently — requires zero change to Stage 10's already-verified delete-recreate contract; recommended snapshot representation is a new nullable `EstimateLine.base_unit_price` + nullable `coefficient_snapshot` JSON, with `unit_price` keeping its exact current meaning unchanged; recommended default-catalog bootstrap mirrors Stage 11's own lazy/idempotent `_ensure_bootstrapped` pattern (not an Alembic data seed), explicitly without seeding any final Q/S/PSG percentage yet; Q/S/PSG business definitions and their default percentage adjustments are explicitly deferred to a separate, later-gated, owner-approved sub-stage (12G) — every percentage/example value anywhere in the specification is illustrative only, never presented as an approved default; refined sub-stage plan 12C (coefficient catalog persistence) → 12D (durable assignment) → 12E (Estimate snapshot/calculation) → 12F (mobile UI) → 12G (Q/S/PSG definition) → 12H (hardening + owner acceptance + production deployment). **12C (coefficient catalog persistence/API/bootstrap) IMPLEMENTED 2026-09-21 on branch `stage-12`** — catalog persistence only, per the 12B contract: no planned-work assignment (12D), no `EstimateLine` snapshot/calculation (12E), no frontend, no fixed-surcharge catalog, no Q/S/PSG percentage seeded. New `CoefficientGroup`/`CoefficientOption` models (`backend/app/models/price_coefficient.py`) mirror `PriceItem`'s proven shape: owner-scoped, server-generated immutable `CUSTOM_*` codes (never client-supplied — `extra="forbid"` schemas reject a smuggled `code`), `SINGLE_SELECT` the only implemented `selection_mode`, `percentage` an exact `Numeric(6,3)` Decimal delta (never a multiplier, never a float), and an explicit `is_base` boolean column (not inferred from `percentage == 0`, per D11). The "at most one active base option per group" invariant is enforced at the service layer (`_clear_other_base_options`, atomic replacement on a new/updated `is_base=True` selection — never a two-step reject-then-reselect dance) rather than a DB constraint, consistent with this codebase's existing cross-row-invariant convention; archiving the current base option never auto-promotes another (explicit application only, D10), and an archived option's historical `is_base` state is never retroactively rewritten by a later active selection elsewhere in the group. Archive/restore is soft and explicit (no hard delete); a `CoefficientGroup` list/detail read model eager-loads its `options` in one extra query (no N+1), with archived options filtered at the API/schema layer rather than by mutating the ORM's `cascade="all, delete-orphan"` relationship collection (which would have marked filtered-out rows for deletion on the next flush — caught during implementation, not shipped). Bootstrap (`PriceCoefficientService.ensure_owner_catalog`) mirrors `WorkRecommendationService._ensure_bootstrapped` exactly: lazy, idempotent, no Alembic data seed; `app/domain/data/price_coefficients.py`'s `build_baseline_price_coefficients()` intentionally returns `[]` — the mechanism is fully implemented and tested (via a monkeypatched fake baseline, never real catalog data) but installs nothing in production until Stage 12G defines and the owner approves real default groups/options; a dedicated test (`test_shipped_baseline_has_no_entries`) guards this gate directly. API: `GET/POST /api/price-coefficient-groups`, `GET/PATCH/{id}/archive/{id}/restore` per group, `POST .../options` nested under a group (an option must belong to a specific group at creation), and flat `PATCH/{id}/archive/{id}/restore` for options thereafter (ownership resolved via join to the parent group, never a bare option id) — mirrors `pricebook.py`'s exact thin-controller shape. Two real async-session bugs were found and fixed during implementation, both instances of a pattern this codebase had already hit once before (`EstimateService.generate_estimate`'s own documented "avoid lazy-loading a relationship on a freshly-flushed object" precedent): (1) `selectinload` does not refresh an already-populated relationship collection on an identity-mapped object across separate `execute()` calls in the same session — fixed by adding `execution_options(populate_existing=True)` to every eager-loading query; (2) a freshly created/flushed object's untouched collection relationship can require a genuine (and, in an async session, disallowed) lazy load on first access post-commit — fixed by never touching `.options` on a bare service-returned object at the API layer, always re-fetching with eager loading first (mirroring the pattern already used for update/archive/restore). Migration `0023_price_coefficients` (parent `0022_work_recommendations`) verified upgrade → downgrade → re-upgrade clean against the real local Postgres instance; single Alembic head; no existing Stage 9/10/11 table altered; no owner-specific data seed. 92 new focused tests (`test_price_coefficients.py` — model/DB invariants, exact-Decimal percentage validation incl. `-100`/`>500`/excess-precision boundaries, group/option CRUD, immutable codes, archive/restore, owner isolation, and the full base-option invariant matrix; `test_price_coefficient_bootstrap.py` — bootstrap mechanism idempotency/no-duplicates/edit-preservation/no-reactivation/per-owner independence via an injected fake baseline, plus a guard that the real production baseline is empty; `test_price_coefficients_api.py` — HTTP-level CRUD, nested active-catalog read model, ordering, validation, immutable/duplicate codes, base-option replacement, and cross-owner 404 isolation) all PASS. Adversarial review performed explicitly for: owner_id spoofing (structurally impossible — never client-supplied, `extra="forbid"`), cross-owner group/option access (tested), attaching an option to another owner's group (tested), archived-row reactivation by bootstrap (tested), duplicate bootstrap rows (tested), code mutation (structurally impossible — no `code` field on any Update schema/service signature), a second simultaneous active base option (tested, cannot occur), invalid Decimal/float leakage (tested), a hidden hard-delete endpoint (none exists), unapproved Q/S values (none seeded, guarded by test), and WorkPlan/`EstimateLine`/`WorkRecommendation` leakage into this sub-stage (grep-verified: zero functional references, only two design-precedent comments citing the Stage 11 bootstrap pattern by name). **12D (planned-work coefficient assignments) IMPLEMENTED 2026-09-21 on branch `stage-12`** — per the approved Option C architecture, a coefficient selection is assigned to one specific planned-work OCCURRENCE (never to a `PriceItem`/Surface/Room/Project), has no durable identity of its own, and is validated in full BEFORE any mutation, then deleted/recreated atomically together with its parent occurrence row on every ordinary WorkPlan/Reveal replace — requiring zero change to Stage 10's already-verified delete-recreate contract. New join tables `surface_planned_work_coefficient_assignments` and `opening_reveal_planned_work_coefficient_assignments` (migration `0024_coefficient_assignments`, parent `0023_price_coefficients`; `ondelete="CASCADE"` to their parent occurrence row, `ondelete="RESTRICT"` to `coefficient_options` since options are only ever soft-archived) store no percentage/price snapshot — that is Stage 12E's job entirely. `PriceCoefficientService.resolve_assignment_options` is the single shared pre-mutation validator both `SurfaceWorkPlanService` and `OpeningRevealWorkService` call: rejects a non-`LABOR` `price_scope` (`MATERIAL`/`LABOR_AND_MATERIAL` items may still be planned with an empty coefficient selection — only *assigning* a coefficient is scope-gated), a duplicate option id, two options from the same `SINGLE_SELECT` group, an archived option, or an option whose group is archived; resolves cross-owner/nonexistent ids to the uniform `CoefficientOptionNotFoundError` 404. Contract extension is purely additive on both HTTP payloads: `SurfaceWorkPlanUpsert`/`RevealWorkSetRequest` gain an optional `planned_works: list[OrderedPriceItemSelection] | None` (each carrying `coefficient_option_ids`) alongside the original `price_item_ids: list[uuid.UUID]`, mutually exclusive via a `model_validator`; every existing client sending only `price_item_ids` is unaffected (110 pre-existing WorkPlan/Reveal tests pass unchanged). `OpeningRevealWorkService.set_works`'s public signature stays a bare `price_item_ids: list[uuid.UUID]` plus a new optional parallel `coefficient_option_ids: list[list[uuid.UUID]] | None` parameter — an additive extension chosen specifically to avoid retyping 59 existing internal call sites across `test_estimates*.py`. Read model: `SurfacePlannedWorkRead`/`RevealWorkItemRead` gain `coefficient_options: list[PlannedWorkCoefficientOptionRead]` (id/group_id/group_code/code/display_name/percentage/is_base — no arithmetic anywhere in this schema), populated via plain Python `@property` accessors (`SurfacePlannedWork.coefficient_options`, `OpeningRevealPlannedWork.coefficient_options`, `CoefficientOption.group_code`) so the existing "one top-level `model_validate` cascades everything" pattern needed no manual schema construction; ordering is deterministic (`group.position`, then `option.position`, then id as a tie-breaker) regardless of client submission order. `apply_to_room_walls`/`apply_to_room_openings` now copy each source occurrence's coefficient selection to every target, rejecting the whole batch atomically if the source references an archived option or archived group (mirrors the existing archived-`PriceItem` rejection). A real SQLAlchemy async-session bug was found and fixed during implementation: the pre-existing "raw bulk `DELETE` + ORM `.clear()`" replace pattern started emitting a spurious "0 rows matched" `SAWarning` once a second cascade level (`coefficient_assignments`) was added beneath `SurfacePlannedWork`, because the ORM's own delete-orphan cascade tried to re-delete grandchild rows the raw statement (and the DB's `ON DELETE CASCADE`) had already removed; fixed by resetting `plan.planned_works` via `sqlalchemy.orm.attributes.set_committed_value(plan, "planned_works", [])` instead of `.clear()`, which forgets the old, already eager-loaded objects without walking the cascade (verified clean with `-W error::sqlalchemy.exc.SAWarning`). Migration `0024_coefficient_assignments` verified upgrade → downgrade → re-upgrade clean against the real local Postgres instance (index names shortened twice during implementation to fit PostgreSQL's 63-byte identifier limit, and the revision id itself shortened to fit `alembic_version`'s `VARCHAR(32)` column); single Alembic head; no existing Stage 9/10/11/12C table altered. 33 new focused tests (`test_planned_work_coefficient_assignments.py` — Surface HTTP contract: no-coefficient/one-coefficient/base-0%-persists/multiple-groups/duplicate-option-rejected/two-SINGLE_SELECT-rejected/archived-option-rejected/archived-group-rejected/cross-owner-rejected/MATERIAL-rejected/LABOR_AND_MATERIAL-rejected/MATERIAL-with-empty-coefficients-still-valid/duplicate-PriceItem-occurrences-independent/deterministic-ordering/replacement-recreates/changing-option-replaces/invalid-replacement-leaves-old-state-unchanged/both-fields-rejected; apply-to-room-walls coefficient copy + archived-source rejection; Reveal service-layer equivalents (legacy-call-unaffected, one-coefficient, archived-option-rejected, cross-owner-rejected, MATERIAL-rejected, duplicate-occurrence-independent, replacement-recreates, mismatched-parallel-array-length-rejected) plus Reveal HTTP contract and apply-to-room-openings coefficient copy) all PASS; full backend regression 1206/1206 PASS (1173 pre-12D baseline + 33 new), zero SAWarnings. Adversarial review performed explicitly for: assignment keyed by occurrence not `PriceItem` (by construction — the assignment FK is to the occurrence row), child-ID durability assumptions (none made — Option C never relies on old occurrence ids surviving), partial delete before validation (validation runs fully before any `DELETE`/mutation in both `_resolve_owned_items`/`_resolve_items`), cross-owner option (tested, 404), archived option/group (tested, 422), duplicate option (tested, 422), two `SINGLE_SELECT` options (tested, 422), `MATERIAL`/`LABOR_AND_MATERIAL` coefficient assignment (tested, 422; empty-selection planning tested, 200), zero/base option dropped (tested — persists and round-trips with `is_base=True`), duplicate `PriceItem` occurrence collapse (tested — independent per-occurrence selections), Apply-to-all losing coefficients (tested — copies; archived-source rejects atomically), Reveal inconsistency (implemented with full parity, additive-only signature), old frontend payload breakage (frontend types are structurally additive-only — no `coefficient_options` consumption exists yet, so no frontend change was required or made), N+1 reads (none introduced — `resolve_assignment_options` and eager-load chains are per-replace, not per-row), coefficient arithmetic accidentally introduced early (none — `resolve_assignment_options` performs zero arithmetic), Estimate touched accidentally (no `EstimateLine`/`EstimateService` file touched), guessed Q/S percentages introduced (none — the only percentages anywhere are test fixtures). **12E (Estimate coefficient snapshot/calculation/preview/regeneration/override/reset) IMPLEMENTED 2026-09-21 on branch `stage-12`** — integrates Stage 12D planned-work coefficient assignments into the existing Stage 10 Estimate engine directly; no second pricing system. Canonical chain: `PriceItem.price` (base) adjusted by the ADDITIVE sum of selected percentages, never compounded — `effective = base * (1 + Σ percentages / 100)`, quantized ONCE at the end to the existing 0.01 money precision (`_calculate_effective_unit_price`); e.g. base 40.00 with +10%/+20% → 52.00, never 40×1.10×1.20=52.80. `EstimateLine` gains two nullable columns (migration `0025_estimate_line_coefficients`, parent `0024_coefficient_assignments`): `base_unit_price` (PriceItem.price captured at generation/regeneration time) and `coefficient_snapshot` (JSONB on PostgreSQL / plain JSON on SQLite via `with_variant` — the repository's first JSON column) holding an immutable, Decimal-safe (percentage stored as a string, never float) list of `{group_id, group_code, group_name, option_id, option_code, option_name, percentage, is_base}` facts, deterministically ordered (group.position, option.position, id tie-break) independent of catalog rename/re-percentage/archive afterward (tested). `unit_price` keeps its exact pre-12E meaning (the effective, commercially-used price) — never repurposed into a base price. NULL base (Sec 9) stays NULL even with coefficients selected (the coefficient configuration is still snapshotted — it explains intent even when price is unresolved); a resolved 0.00 base (Sec 10) stays 0.00 regardless of valid coefficients, never converted to NULL. Legacy pre-12E lines get honest NULL for both new columns — no migration data rewrite, no fabricated `[]`/copied-from-`unit_price` values; existing historical Estimate totals are byte-for-byte unaffected. Defense-in-depth (Sec 11): a coefficient-bearing occurrence whose `PriceItem.price_scope` was edited to `MATERIAL`/`LABOR_AND_MATERIAL` after assignment (12D only gates *new* assignments, and `price_scope` is mutable via the Price Book) raises `EstimateValidationError` at calculation time rather than silently pricing a corrupt state (tested). Aggregate-percentage safety (Sec 8): the calculator rejects (never silently clamps) any selection whose summed percentage would produce a negative effective multiplier (`Σp < -100%`), independent of the current base value, while `Σp == -100%` correctly yields an explicit 0.00 — this only runs when a base price exists, since NULL base performs no arithmetic to protect. Surface and Reveal share the exact same `_resolve_occurrence_pricing`/`_calculate_effective_unit_price` helpers (parity by construction, tested both ways); coefficients alter unit price only, never quantity (tested). Preview (`preview_regeneration`) is the SAME existing diff mechanism, extended (not duplicated): `_snapshot_would_change` now also compares `base_unit_price`/`coefficient_snapshot` unconditionally — even for a `price_override=True` line — so a live configuration drift is flagged without ever implying the owner's pinned price would be silently replaced; `LineChangeEntry`/`LineChangeEntryRead` gain additive `old_/new_base_unit_price` and `old_/new_coefficient_snapshot` fields. Because Stage 12D occurrence ids are never durable across a WorkPlan/Reveal replace (Option C, unchanged since Stage 10/11B.0), changing which coefficients are assigned to an occurrence necessarily recreates that occurrence with a new id — so preview/regenerate correctly report this as ADDED+REMOVED, not UPDATED, matching the pre-existing Stage 10 behavior for any planned-work edit; only a live catalog-side change (percentage/rename/archive on an already-assigned option, or `PriceItem.price` itself) with the SAME occurrence id produces an UPDATED entry. Regeneration (`_do_regenerate`/`regenerate_draft`) recomputes `base_unit_price`/`coefficient_snapshot`/`unit_price` from CURRENT live state on every touched line, exactly like the pre-existing quantity/description/price refresh it already performed; manual overrides and quantity overrides continue to survive regeneration unchanged. Manual price override (`patch_line` with `unit_price`) replaces only the effective `unit_price` and never touches `base_unit_price`/`coefficient_snapshot` — provenance survives an override untouched, by simply never being written in that code path (tested: override then live coefficient/base change leaves the override's displayed price untouched). Reset price override (`patch_line` with `reset_price_override=True`) is the Stage 12 behavior change: it now re-resolves the LIVE occurrence via the new `_load_current_occurrence` helper (dispatching on `opening_id`/`planned_work_id`/`plan_id` provenance to `SurfacePlannedWork` or `OpeningRevealPlannedWork`), re-reads its CURRENT `PriceItem.price` and CURRENT coefficient assignments/percentages, and writes a fresh base/coefficient snapshot before computing the new effective price — never the historical snapshot, never a bare `PriceItem.price` reload when coefficients are configured (tested: unchanged config, changed base, changed percentage, NULL base, zero base, base-option 0% preserved, Surface provenance, Reveal provenance). When the occurrence itself no longer exists (its WorkPlan/Reveal was edited since generation, so the old occurrence id is genuinely gone — not an error), reset honestly falls back to a bare `PriceItem.price` reload with `coefficient_snapshot=None` (not a fabricated `[]`) rather than guessing a selection it cannot determine — documented and tested explicitly. MANUAL lines (Sec 22) and the dormant, currently-unused `PRICE_BOOK` origin (Sec 23, confirmed via grep to have zero call sites) are completely unaffected: no code path ever writes `base_unit_price`/`coefficient_snapshot` for them, and `reset_price_override` on a MANUAL line still raises exactly as before. FINAL/ACCEPTED immutability (Sec 24) and the existing NULL/zero finalization-blocking rules are unchanged and re-verified: a finalized Estimate's coefficient-priced lines are never touched by a later live catalog or `PriceItem.price` change (tested). API contract: `EstimateLineRead`/`LineChangeEntryRead` gain the same fields additively (nullable/optional); every existing client remains compatible. 47 new focused tests (`test_estimate_coefficient_pricing.py` — calculation matrix incl. no-compounding, `-100%` boundary exactly zero, `<-100%` rejected, large positive, ROUND_HALF_UP rounding boundary, no float leakage; snapshot content/determinism/immutability-from-live-catalog-rename/percentage-change/archive; LABOR defense-in-depth; Surface/Reveal parity incl. quantity-unaffected and duplicate-occurrence independence; preview detecting base-price/percentage/selection/add/remove changes and never mutating the estimate; regeneration capturing current configuration; override preserving provenance and surviving live coefficient changes; reset using current base/coefficients/percentage across NULL/zero/base-option/Surface/Reveal/occurrence-recreated-fallback; MANUAL/PRICE_BOOK non-interference; finalization regression incl. FINAL-immutability-from-live-catalog-change) all PASS; full backend regression 1253/1253 PASS (1206 pre-12E baseline + 47 new), zero SAWarnings; frontend regression (1016 tests, `tsc --noEmit`, `vite build`) all PASS with only additive, optional `base_unit_price`/`coefficient_snapshot`/`CoefficientSnapshotEntry` TypeScript type additions (no UI implementation, no component changes). Migration `0025_estimate_line_coefficients` verified upgrade → downgrade → re-upgrade clean against the real local Postgres instance; single Alembic head; no existing Stage 9/10/11/12 table/column altered; no historical data rewrite. Adversarial review performed explicitly for: compounded percentages (impossible by construction — single multiplier, one summation), float conversion (none — percentage always serialized as a Decimal string), multiple rounding points (one `quantize()` call, at the end), NULL→zero / zero→NULL substitution (both tested, both impossible by construction), market/reference price substitution (base is always `PriceItem.price` directly), coefficient snapshot reading the live catalog post-generation (impossible — snapshot is pre-serialized plain dicts, tested against rename/percentage/archive), archived catalog destroying historical explanation (tested — survives), manual override erasing snapshot (tested — survives), reset using a stale snapshot or returning raw `PriceItem.price` while coefficients are live and resolvable (tested — always re-resolves current state; documented honest fallback only when the occurrence itself is gone), MATERIAL/mixed corrupt coefficient state silently priced (tested — raises), Surface/Reveal inconsistency (shared helpers, tested both), duplicate `PriceItem` occurrence collapse (tested — independent), quantity accidentally affected (tested — untouched), preview mutating the Estimate (verified — no commit call in `preview_regeneration`), regeneration happening silently (impossible — only the explicit `regenerate_draft` endpoint path calls `_do_regenerate`), FINAL/ACCEPTED mutation (tested — never), legacy rows fabricated with fake coefficient provenance (impossible — nullable columns, no migration data seed), MANUAL lines receiving coefficient metadata (tested — never), PRICE_BOOK lines receiving occurrence coefficients (impossible — no such code path exists), Q/S values seeded (none — only test-fixture percentages exist anywhere in this diff). **12F (coefficient management mobile UI) COMPLETE 2026-09-24 — owner accepted, pushed to `origin/stage-12` (`c5e4f78` feat + `ba1f592` refactor lazy-load); not deployed, not merged to `main`** — frontend only, no backend change. Initial implementation by other agents (Antigravity/Trae), interrupted during TypeScript fixes; recovered and completed without rewriting. Added: coefficient catalog types/API client (`types/coefficient.ts`, `api/coefficients.ts`); exact BigInt decimal helpers (`utils/coefficientCalculations.ts` — additive sum, never compounded, ROUND_HALF_UP to 0.01 matching the backend, NULL base stays unresolved); `CoefficientAssignmentModal` (bottom sheet: one `SINGLE_SELECT` radio list per active group with an explicit "Brak" = no option id, distinct from an explicit `is_base` 0% option whose real id is preserved; live base/total/effective preview; sticky Anuluj/Zastosuj footer; Zastosuj writes only the local draft occurrence, and persistence stays on the existing outer atomic "Zapisz" WorkPlan/Reveal replace, sending `planned_works` when any occurrence has coefficients and the legacy `price_item_ids` otherwise); a "Współczynnik" action on LABOR occurrences only in `SurfaceWorkPlanEditor` and `RevealWorkPlanEditor`, with per-draft-occurrence state keyed by the local draft key (never by non-durable planned-work ids) so duplicate PriceItem occurrences stay independent, plus coefficient-aware dirty tracking and a compact summary badge; a minimal `CoefficientCatalogManager` as a Price Book "Współczynniki" tab (group/option create, rename, archive/restore, is_base); `EstimateShell` stored-snapshot provenance (base price, each group/option adjustment, additive total), a "Cena ręczna" badge that keeps manual price overrides distinct, and coefficient change lines in the regeneration preview; PL/RU keys with parity tests. Recovery fixes: 6 leftover TS errors (unused `CoefficientSnapshotEntry`/`OrderedPriceItemSelection` imports, missing `RevealWorkItemRead` import); the modal's Apply button is now disabled while the catalog is loading or failed (applying then would have silently wiped the occurrence's existing selection); the modal's load effect is now keyed by id content, not array identity (so a parent re-render no longer refetches and resets the local selection); modal option rows and catalog buttons raised to >=44px; catalog group/option rows stacked so long names wrap instead of colliding with actions at 320px; Polish decimal comma normalized in the percentage input; trailing whitespace. Tests: 25 new Stage 12F tests (modal semantics, Surface/Reveal draft-only Apply, planned_works payload, explicit-base persistence, duplicate-occurrence independence, legacy fallback when all coefficients are cleared, catalog manager, Price Book tab, Estimate snapshot/override/preview) on top of 16 calculation tests and 9 parity tests; full frontend suite 1058/1058 PASS (39 files); `tsc --noEmit` clean; `vite build` succeeds. Bundle: 12F grew the single JS chunk 473.58 → 506.03 kB (Vite size; expected growth, no new dependency — largest contributor `CoefficientCatalogManager` +12.5 kB), tripping Vite's >500 kB advisory; resolved by lazy-loading only `CoefficientCatalogManager` from the Price Book "Współczynniki" tab (main chunk 494.90 kB / gzip 130.00 kB, lazy chunk 12.61 kB / gzip 2.34 kB, warning gone, `chunkSizeWarningLimit` unchanged, ~5 kB headroom left). Known minor pre-existing behavior: the catalog manager renders its empty state for one frame before its first fetch starts (`loading` initializes to `false`); left unchanged. Mobile: rendered in an isolated mocked-API harness with headless Chromium at 320/390/412/480px, PL and RU, with long names: no horizontal overflow, all buttons/radio rows >=44px, modal footer reachable, modal body scrolls inside the overlay. Deferred: inline "+ Dodaj współczynnik" creation inside the modal (architecture §16 recommendation; catalog management lives on the Price Book tab); real-device Telegram WebView acceptance. **12G (canonical pricing model) — BUSINESS MODEL DEFINED 2026-09-24 (documentation only; implementation pending owner approval)**: recorded in `README.md` ("Model wyceny", Polish, user-facing) and `docs/stage-12-architecture.md` §27 (authoritative; earlier sections reconciled). Four separate concepts: surface quality target, technological operations (PriceItems), per-occurrence price coefficients, and order-level surcharges/commercial adjustments, plus an explicit anti-double-counting rule. `S1–S4` is defined as the contractor's internal "Standard Wykończenia Powierzchni" (not a Polish norm, finish quality not geometry, no millimetre tolerances); `Q1–Q4`/`PSG1–PSG4` stays a separate gypsum-board system. Neither is ever a percentage coefficient (the 12B anticipation of a `QUALITY` coefficient group is withdrawn); Stage 13 will map `quality_target` to required operations. A coefficient is defined as a LABOR-only correction for execution conditions that differ from those assumed in the base price. The approved v1 default catalog has four `SINGLE_SELECT` groups, each with an explicit `is_base` 0% option: `WYSOKOSC_PRACY` 0/+15/+25%, `DOSTEP_DO_POWIERZCHNI` 0/+10/+20%, `ZLOZONOSC_POWIERZCHNI` 0/+10/+20%, `ORGANIZACJA_PRACY` 0/+10/+20%. There are no quality, furniture, ceiling, colour, small-job or urgency groups and no negative defaults. Calculation is unchanged: additive Decimal, 40.00 × 1.35 = 54.00. Pending 12G implementation scope: seed the v1 catalog with descriptions via the existing lazy bootstrap; add nullable, owner-editable `CoefficientGroup.description`/`CoefficientOption.description` (migration); a mobile description bottom sheet (≥44 px, no hover tooltip, never mutates the WorkPlan); a non-blocking UI warning when the total correction exceeds +50% (canonical PL copy in §27.6). No surcharge architecture is added (manual `EstimateLine` remains the v1 fixed-surcharge path). 12G documentation committed and pushed as `35e5b70`. **12G IMPLEMENTATION (2026-09-24, on branch `stage-12`, pending owner review/commit)**: Backend: nullable, owner-editable `description` (Text) on `CoefficientGroup`/`CoefficientOption`. Migration `0026_coefficient_descriptions` (parent `0025_estimate_line_coefficients`) verified from an empty database through upgrade → downgrade → re-upgrade in a throwaway local PostgreSQL database, with a single Alembic head. Create/read/update schemas and the existing CRUD API expose it: on PATCH, an omitted field is unchanged and null/blank clears it; max 4000 characters; owner isolation unchanged. Descriptions are never a pricing input and never enter the Estimate snapshot. `app/domain/data/price_coefficients.py` now ships the approved v1 catalog (§27.3): exactly 4 SINGLE_SELECT groups and 12 options with Polish names and practical descriptions, one explicit 0% `is_base` option per group, no quality/negative/surcharge/commercial groups. Names are seeded as `display_name`, because the Estimate snapshot stores the resolved label verbatim. The existing lazy bootstrap inserts missing rows only and never rewrites an owner's name, description, percentage, base choice or archive state. It now also sets group positions to catalog order, and never creates a second active base when a default base option is missing from a group whose owner already chose a base. Frontend: description create/edit in `CoefficientCatalogManager` (groups and options). In `CoefficientAssignmentModal`, an accessible 44 px info control appears only where a description exists and opens a read-only bottom sheet (internal scroll; blocks the modal underneath; never changes the selection, the draft or persistence). A non-blocking PL/RU warning appears when the exact-decimal additive total exceeds +50% (new `isPercentageAbove` helper; absent at exactly +50%; never disables Zastosuj). Tests: new `test_price_coefficient_defaults.py` (21) plus updated empty-baseline tests; frontend +14 tests (catalog, modal, Surface/Reveal no-persist, helper). Mobile: mocked-API headless harness at 320/390/412/480 px, PL/RU: no overflow, touch targets ≥ 44 px, sheet/footer reachable. Localization pass: PL/RU `coefficients.builtin` locale entries hold the program catalog's names and descriptions. The PL block is byte-identical to the backend seed, enforced by a backend test. `utils/coefficientLabels.ts` shows the active-locale translation only while a stored value still equals the canonical program text for its stable group/option code. Otherwise, as with an owner edit, a cleared description or an owner-created row, the stored value is shown as-is. Edit forms prefill stored values. Estimate snapshots are unchanged and still render stored labels verbatim. The hardcoded percentage placeholder was moved to `coefficients.percentage_placeholder`. The catalog's initial `loading` is now `true`, so no one-frame empty state before the first response. **Backlog (not done here, owner decision): bundle size.** The main chunk is 510.13 kB (gzip 135.42 kB), up from 499.93 kB because the PL/RU built-in coefficient text lives in the main-bundle locale files. Vite's >500 kB advisory is back. The build still succeeds; `chunkSizeWarningLimit`, `manualChunks` and dependencies are unchanged. Broader screen-level code splitting (e.g. Price Book, Estimate) should be a separate deliberate task. **Deferred, pre-existing:** `alembic check` reports model/migration drift unrelated to Stage 12G: the `communication_phrases` table missing from the Alembic metadata, and column comments present only in the models. Migration `0026` adds no drift of its own. 12G committed and pushed as `f2adb96`. **12H ADVERSARIAL VERIFICATION (2026-09-24, pending owner review, uncommitted)**: no functional Stage 12 bug found. New `backend/tests/test_stage12h_adversarial.py` covers:
- full replace with reordered, removed and added duplicate occurrences (selections follow the logical occurrence, no orphan assignment rows, repeated saves stable);
- a legacy `price_item_ids` save clearing earlier coefficients;
- Reveal LABOR_AND_MATERIAL rejection, per-opening independence, and unchanged LM/M2 quantities;
- apply-to-all copying duplicates, explicit base and multi-group selections per occurrence without touching geometry, and atomic rejection on an archived source option;
- the exact base-100 Decimal matrix, fractional +12.345% HALF_UP, `NULL`/0 bases and the below −100% rejection;
- DRAFT snapshots unaffected by description, base-status, archive and Price Book edits;
- reset after all coefficients were removed;
- FINAL rejecting override, reset, regenerate and preview;
- an archived assignment staying readable and priced, rejected on re-save and repairable;
- FK RESTRICT blocking hard delete;
- cross-owner restore returning 404;
- Stage 11 acceptance preserving existing coefficients.
Frontend: modal repair path (an archived option dropped on Zastosuj) and the +50.001% warning boundary. **Metadata drift introduced by Stage 12 was fixed (model metadata only, no migration or DB change):** the assignment-table indexes now use the explicit short names that migration 0024 created (the models previously implied auto-generated names beyond 63 bytes, so autogenerate saw a drop/add); the 0026 `description` columns lost their model-only `comment=`. Remaining `alembic check` drift is pre-existing or convention-only: the `communication_*` tables are missing from the metadata, and model-only column comments (Stage 11 and Stage 12C/12E follow the same convention). Migration chain 0022 → 0026 was stepped up, down to 0022 and back to head in a throwaway PostgreSQL database; single head `0026_coefficient_descriptions`. Mobile harness: 7 views × 320/390/412/480 px × PL/RU all passed. Frontend 1089/1089; tsc clean; build unchanged (main chunk 510.13 kB, accepted warning). 12H committed and pushed as `1cbdfee`. **Owner walkthrough corrections (2026-09-25, uncommitted, pending owner review):** (1) UX: compact one-open-at-a-time accordions in `CoefficientAssignmentModal` (collapsed summary shows the selected option and %, BAZA for an explicit base, "Brak"/— for no selection) and in `CoefficientCatalogManager` (collapsed summary shows the plural-aware option count plus "Baza: name %" or a no-base note; the open group resets on tab switch and whenever it leaves the list). (2) Reveal planning placement (Stage 10 D19 enforced): reveal work (stable `PriceCategory.REVEAL`) is planned per opening via `OpeningRevealPlannedWork`, where each opening's own reveal geometry and coefficients apply; the Surface picker had simply never been restricted. The Surface picker and its inline Price Book form no longer offer REVEAL. `SurfaceWorkPlanService` rejects new REVEAL occurrences on a Surface plan: existing (legacy) ones may be kept, re-saved and removed, but never added, and never moved or deleted automatically. The Stage 11 test that pinned the old permissive contract was updated. Apply-to-all refuses to copy a legacy REVEAL occurrence to other walls. The UI shows a legacy note on such an occurrence, and the guard error is localized PL/RU. Estimate: a legacy Surface REVEAL occurrence resolves to an unresolved quantity (MANUAL, NULL) for every unit. That blocks finalization until the owner moves it to the opening, removes it or overrides the quantity. It never gets the wall's net area (the old M2 behavior) and never a Surface aggregate, which could silently double-count per-opening lines. A shared `_resolve_surface_quantity` serves generate, regenerate and preview. An earlier uncommitted aggregate approach was withdrawn in favour of this. Coefficients are deliberately not synchronized between Surface and opening occurrences: each opening keeps its own. Example: window 5.500 mb, base 20.00, +15% → 23.00 → 126.50 PLN; door 5.100 mb with no coefficient → 20.00 → 102.00 PLN. New `backend/tests/test_reveal_planning_placement.py` (10 tests). No schema or migration change. (3) Regeneration override-loss fix: regenerate and preview paired existing lines only by `planned_work_id`, but every WorkPlan or reveal-work save recreates occurrences with new ids. So any re-save (e.g. a coefficient change) turned the line into REMOVED + ADDED and silently dropped the owner's manual price and quantity overrides. A shared `_match_existing_lines` now pairs by exact id first, then by logical key (surface, opening, PriceItem), with duplicates paired by order. Regenerate re-points the matched line to the current occurrence, so a later reset reads live data. Preview uses the same pairing and mutates nothing. Price and quantity overrides now survive, while base_unit_price and coefficient_snapshot are refreshed. Walkthrough: 5.500 mb, manual 30.00 kept after +15% → +25% (165.00), and reset → 25.00 (137.50). Tests that pinned the old ADDED + REMOVED diff were updated (4 in `test_estimate_coefficient_pricing.py`, 1 in `test_estimates_api.py`). New `backend/tests/test_regeneration_override_preservation.py` (12 tests). (4) Reveal geometry guard: an opening-reveal line whose reveal geometry cannot be derived (reveals enabled but no side selected, or missing depth on legacy data) kept a REVEAL_LENGTH/REVEAL_AREA source with a 0.000 placeholder. It was not flagged unresolved, so the Estimate could be finalized with a silent zero. A shared `_resolve_reveal_quantity` (used by generate, regenerate and preview) now makes it unresolved (MANUAL, NULL), which blocks finalization until the geometry is fixed or the quantity is set explicitly. The opening form also requires at least one reveal side when reveal calculation is enabled (PL/RU message). New `backend/tests/test_reveal_geometry_unresolved.py` (8 tests). (5) Owner UX polish: the project "Kosztorys" entry is an amber accent card; inside the Surface options, existing opening cards come first and the "+ Dodaj otwór" button and form come after them; "Prace na ościeżach" is a strong orange-700/white full-width action (same toggle and editor). No schema or migration change. **Owner-walkthrough corrections completed before release** (all above plus): compact accordions in the coefficient catalog and the assignment modal; coefficient help/info bottom sheet; Surface vs opening-reveal planning separation hardened (new REVEAL work cannot be planned as Surface work); existing opening cards above the new-opening controls; prominent "Prace na ościeżach" action; project "Kosztorys" navigation accent; reveal LM/M2 quantity handling; invalid or incomplete reveal geometry is unresolved instead of a silent 0; at least one reveal side required in the UI; Estimate logical matching no longer relies solely on the non-durable planned_work_id; manual price and quantity overrides survive a WorkPlan full-replace; reset uses the current base price plus current coefficients; opening-card actions ≥44 px and responsive at 320–480 px (actions wrap below the info when needed). **Final pre-release verification (2026-09-25):** backend 1337 passed; frontend 1111/1111; TypeScript PASS; Vite build PASS; git diff --check PASS; mobile 320/390/412/480 px, PL + RU, no horizontal overflow, ≥44 px for touched action controls (mocked-API headless harness; real Telegram walkthrough pending). Migration chain unchanged since 12G: 0023 → 0024 → 0025 → 0026 (head `0026_coefficient_descriptions`); the walkthrough fixes added no schema change or migration. **Known non-blocking / deferred:** accepted Vite >500 kB main-chunk warning; pre-existing Alembic metadata drift; broader screen-level lazy loading; Stage 13 technological workflows remain separate; fixed/order-level surcharge architecture remains future work. **Production release and owner acceptance (2026-09-25):** release commit `d60390b` deployed from `stage-12`; production migrations 0023 → 0026 applied successfully (DB head `0026_coefficient_descriptions`); backend healthy and frontend running after deployment; the real Telegram Mini App owner walkthrough matched the accepted local behavior. Production deployment PASS · Telegram production walkthrough PASS · OWNER ACCEPTED: PASS · **Stage 12: COMPLETE.** Not yet merged to `main`. | Owner-controlled labor-price coefficients (percentage-based, additive, explicit per-planned-work-occurrence selection) — see `docs/stage-12-architecture.md` |
| Stage 13 | Technological workflows | **IN PROGRESS** — Stage 13A — architecture/audit COMPLETE; D1–D13 approved (`docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md`; D13 = stable `occurrence_key` introduced in 13B / migration 0027; no code, no migration yet); next: 13B on owner approval | Work sequencing, technological breaks, drying times, stage tracking |
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
  - **Execution Sub-Stage 5F (OWNER ACCEPTED 2026-09-17)**: Opening Reveals / Ościeża — optional reveal (ościeże) measurement for WINDOW and DOOR openings (depth, left/right/top/bottom sides); backend-authoritative reveal calculations (length = sum of enabled edge lengths, area = length × depth, multiplied by quantity); reveal does NOT alter opening deduction or wall net area; room aggregates for window reveals, door reveals, and combined reveals; compact "Oblicz ościeża" toggle in opening form (PL/RU); reveal totals shown on opening cards and in Obliczenia pomieszczenia; Alembic migration `0019_add_opening_reveals` (6 nullable/defaulted columns); 22 focused tests PASS; 653 backend + 436 frontend tests PASS; tsc + Vite build PASS. Committed `22afddc`. Real Telegram owner acceptance: reveal enable/disable ✓, geometry calculations ✓, room aggregates ✓, wall deduction/net area unchanged ✓. **Deferred**: estimate integration, Price Book items, Stage 14 photos.
- **Gate**: Canonical Stage 5 is **COMPLETED** including Stage 5F (reveals). All sub-stages owner-accepted.

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
- **Status / scheduling**: **DEFERRED** — execute after completion of Stage 10C; no implementation started.
- **Purpose**: Measure window/door reveal length and area for future preparation, painting, and estimate integration.
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
  - `POST .../surfaces/{source_surface_id}/work-plan/apply-to-room-walls` — canonical backend for Stage 10C.3's “Zapisz dla wszystkich ścian” / “Сохранить для всех стен” action; WALL-only and atomic (single transaction, no per-wall commit): validates the source (owned, WALL, active, existing plan, no archived catalog item in the source plan), then copies substrate + quality_target + ordered planned works into every **other active (non-archived) WALL** in the same room as **independent persisted plan rows** (replace semantics). Never copies/changes geometry, openings/deductions, inspections, findings, risks, photos, archive state, or any Price Book row. Returns a compact `SurfaceWorkPlanApplyResult` (`source_surface_id`, `target_count`, `target_surface_ids` in `Surface.position` order, updated `targets` plans) enough for the future 10C confirmation toast. Empty target set → successful `target_count=0`; non-WALL source (FLOOR/CEILING/OTHER) → 422; no source plan → 404; archived item in the source plan rejects the whole batch atomically (source must be updated deliberately first); NULL-price source items copy fine (planning is independent of commercial completeness).
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
- **Status**: Completed 2026-09-16 (frontend; **OWNER ACCEPTED** after real Telegram production retest of 10C.1 plus corrective sub-stages 10C.1A–10C.1C)
- **Date**: 2026-09-16
- **Commit**: `da9246d` — `feat(stage-10): add compact surface card options` (initial 10C.1 implementation; accepted corrections culminated in `d9d9265`)

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
- Mobile acceptance concept verified at component level: collapsed card keeps identity/type/dimensions/area summary/[Opcje]/[Rodzaje prac i jakość]; expanded Opcje keeps every existing action (inspection navigation, opening creation/management, edit, archive/restore) with 44px touch targets; FLOOR/CEILING expose no opening controls; per-card expansion is independent; RU strings (Опции / Скрыть опции / Виды работ и качество) verified via i18n provider; full-width controls avoid horizontal overflow at 320–480 px. Real Telegram production retest completed after 10C.1A–10C.1C: **OWNER ACCEPTED**. `README.md` unchanged.

#### Deferred:
- **Historical next-step note:** Stage 10C.2 was originally described broadly as the Surface Work Plan Editor. The current owner-approved breakdown is authoritative: 10C.2A → 10C.2B → 10C.2C → 10C.2D, followed by **10C.3 — Apply Work Plan to All Walls**. Apply-to-all is not owned by generic 10C.2.

### Stage 10C.1A: Canonical Floor/Ceiling Surfaces (owner corrective sub-stage)
- **Status**: Completed 2026-09-16 (backend; **OWNER ACCEPTED**; committed `a6c50c5`)
- **Date**: 2026-09-16
- **Commit**: `a6c50c5` — `feat(stage-10): add canonical floor and ceiling surfaces` (owner commit)
- **Why**: discovered during 10C.1 acceptance — WALLs are real `Surface` rows but FLOOR/CEILING existed only as room-scoped `AreaSegment` planes, so Stage 10B `SurfaceWorkPlan` had no stable `Surface.id` for floor/ceiling. 10C.1A makes FLOOR and CEILING canonical physical `Surface` entities. Full record: §25A in `docs/stage-10-architecture.md`.

#### Added:
- `backend/app/domain/services/canonical_planes.py` — idempotent canonical plane provisioning: `CANONICAL_FLOOR_NAME="Floor"`, `CANONICAL_CEILING_NAME="Ceiling"`, `CANONICAL_FLOOR_POSITION=100`, `CANONICAL_CEILING_POSITION=101`; `ensure_canonical_plane_surfaces(db, room_id)` reuses the single active plane surface or creates it (raises `CanonicalPlaneConflictError` on duplicates).
- `backend/alembic/versions/0018_canonical_plane_surfaces.py` — reversible migration (down_revision `0017_create_surface_work_plans`): (1) provision/reuse canonical Floor/Ceiling per room (aborts with an explicit room message on duplicate active planes — never merges user rows); (2) add nullable `area_segments.surface_id`; (3) backfill every segment to exactly one canonical surface; (4) FK `fk_area_segments_surface_id` (`ON DELETE CASCADE`) + index `ix_area_segments_surface_id` + NOT NULL; (5) partial unique index `uq_surfaces_active_plane_per_room (room_id, surface_type)` filtered to active FLOOR/CEILING. Downgrade removes only canonical-signature rows (type + Floor/Ceiling name + position 100/101, active), preserving reused user rows.
- `backend/app/domain/exceptions.py` — `CanonicalPlaneConflictError`, `CanonicalPlaneMissingError`, `AreaSegmentSurfaceMismatchError`.
- `backend/tests/test_canonical_planes.py` — 23-test matrix covering the owner A–X acceptance set (provisioning A/B, stable IDs C, idempotence D, wall generation E, segment→surface resolution F/G, identical measurement math H/J/W, cross-room K, WALL L, plane/type mismatch M, owner isolation N, response `surface_id` O, WorkPlan on canonical FLOOR/CEILING P/Q, independent plans R, legacy-room provisioning T, reuse U, backfill reference V, duplicate-plane create/archive/restore/retype guards 409).

#### Changed:
- `backend/app/models/surface.py` — partial unique index `uq_surfaces_active_plane_per_room` (dual-dialect `sqlite_where` + `postgresql_where`) so one active FLOOR + one active CEILING per room while archive/restore of legacy plane rows stays possible.
- `backend/app/models/area_segment.py` — added `surface_id` (UUID FK → `surfaces.id`, `ON DELETE CASCADE`, NOT NULL, indexed); `room_id` retained.
- `backend/app/domain/services/room_service.py` — `create_room` provisions canonical FLOOR+CEILING surfaces (idempotent).
- `backend/app/domain/services/surface_service.py` — plane-type guards: create rejects a second active same-plane (409); update rejects retyping a plane or onto an occupied plane type (409); canonical planes cannot be archived (409); restore rejects a plane that would collide with an active one (409).
- `backend/app/domain/services/area_segment_service.py` — `_resolve_plane_surface`: resolves canonical from `room_id + plane` when `surface_id` omitted (`CanonicalPlaneMissingError` if absent); validates provided `surface_id` (belongs to the room, type matches plane — else `AreaSegmentSurfaceMismatchError`, 409). Client-supplied `surface_id` is never trusted without validation.
- `backend/app/schemas/area_segment.py` — `AreaSegmentCreate.surface_id` (optional) + `AreaSegmentRead.surface_id`.
- `backend/app/api/v1/endpoints/surfaces.py` + `area_segments.py` — map the three new domain exceptions to 409.
- `backend/tests/test_surfaces.py`, `test_openings.py`, `test_inspections.py`, `test_wall_generation.py` — adjusted for canonical planes (counts, canonical ids, WALL/OTHER parametrization, canonical-preserving wall generation assertions).

#### Database:
- **Migration `0018_canonical_plane_surfaces`** — new: `area_segments.surface_id` (FK + index + NOT NULL), partial unique index `uq_surfaces_active_plane_per_room`, canonical Floor/Ceiling rows per room + area_segment backfill. Reversible.

#### Tests:
- Focused backend (`tests/test_canonical_planes.py`): **23 passed**; full backend pytest: **618 passed** (0 failed).
- Alembic migration cycle on **real PostgreSQL** PASS: `0017 → 0018` (every room exactly 1 active FLOOR + 1 CEILING; Kuchnia segment linked to reused "Custom Floor", Łazienka to reused "Custom Sufit"; NOT NULL/FK/unique index verified), `0018 → 0017` (canonical-created rows removed, reused user rows + archived "Old Floor" preserved, column/index/FK dropped), `0017 → 0018` re-upgrade (no duplicates; reused surfaces keep stable IDs; segments relink), duplicate-active-plane room → migration aborts with an explicit message and full rollback (no merge). Scratch DBs dropped after verification.
- Frontend vitest: **340 passed** (24 files); `tsc --noEmit` PASS; `vite build` PASS; `git diff --check` clean.

#### Verification:
- Measurement math numerically identical before/after (BASE + ADD − SUBTRACT plane totals unchanged; openings only on WALLs); API remains compatible (plane resolved from `room_id + plane`, optional `surface_id` in requests/responses); WorkPlan GET/PUT works on canonical floor/ceiling `Surface.id` with no WorkPlan schema change and no Floor/Ceiling plan models. Owner isolation (404) and segment→surface cross-room/WALL/mismatch rejections (409) covered by tests. Real Telegram production retest confirmed canonical Podłoga/Sufit cards remain, duplicate generic FLOOR/CEILING cards are absent, and WALL cards remain correct: **OWNER ACCEPTED**. `README.md` unchanged; `docs/stage-10-architecture.md` §25A + this log entry record the stage.

#### Deferred:
- **Next active sub-stage: 10C.2 — Surface Work Plan Editor. NOT STARTED.**

### Stage 10C.1B: Floor/Ceiling Mobile UI Parity (owner corrective sub-stage)
- **Status**: Completed 2026-09-16 (frontend; **OWNER ACCEPTED** after real Telegram production retest)
- **Date**: 2026-09-16
- **Commit**: `0ca24a2` — `fix(stage-10): add floor and ceiling work plan controls` (owner commit)
- **Why**: accepted issue from 10C.1 — WALL cards expose `[ Opcje ]` + `[ Rodzaje prac i jakość ]`, but the FLOOR/CEILING measurement cards rendered their measurement actions permanently and lacked both top-level controls. 10C.1B closes the floor/ceiling parity gap only.

#### Added:
- `frontend/src/components/AreaSegmentList.tsx` — FLOOR and CEILING measurement cards now show the same two full-width top-level controls as WALL cards (both `w-full min-h-11` = 44px touch targets):
  - `[ Opcje ]` / `[ Ukryj opcje ]` toggle (`aria-expanded`, default collapsed) per plane, reusing the existing `surfaces.options` / `surfaces.hide_options` PL/RU keys — no new translation keys.
  - `[ Rodzaje prac i jakość ]` button reusing `surfaces.work_types_quality` (PL/RU); **functionally inert in 10C.1B** (10C.2 activates it), `aria-label = work-plan-<surfaceId>` matching the WALL card convention so 10C.2 can consume `surface_id` directly.
  - Existing measurement behavior is preserved verbatim but relocated under `Opcje (expanded only): `+ Dodaj prostokąt` / `+ Dodaj odjęcie`, the ADD/SUBTRACT segment form/dialogs, per-segment edit/archive, and the empty-state copy. Collapsed card keeps identity + `Razem` total + base-area/Korekty summary.
- `frontend/src/types/areaSegment.ts` — `AreaSegmentType.surface_id?: string | null` mirroring backend 10C.1A `AreaSegmentRead`.
- `frontend/src/AreaSegmentList.test.tsx` — 9 new parity tests covering the A–O acceptance matrix; existing 16 interaction tests updated (expanded Opcje first) rather than weakened.

#### Changed:
- `frontend/src/components/AreaSegmentList.tsx` — **canonical Surface ID resolution**: the component now also calls `fetchSurfaces(projectId, roomId)` and resolves the active FLOOR/CEILING `Surface` rows by `surface_type` (Stage 10C.1A canonical entities), independent of `AreaSegment` rows — so identity works for **zero-segment rooms; no `AreaSegment.id`, `room_id`, or synthetic ID is ever used as Surface identity**. If the surfaces fetch fails the Work Plan entry stays hidden rather than fabricating an ID. Disclosure state is keyed per plane (`expandedOptions` keyed by `FLOOR`/`CEILING`), so FLOOR and CEILING disclosure are independent. `ProjectWorkspace` wiring is unchanged.

#### Database:
- **None** — no schema change, no migration; backend untouched in this sub-stage.

#### Tests:
- Focused frontend (`AreaSegmentList.test.tsx`): **25 passed** (16 preserved + 9 new A–O matrix: A/B FLOOR Opcje + Rodzaje prac i jakość, C FLOOR WorkPlan binds canonical FLOOR id, D/E/F hidden→visible→collapse, G/H CEILING controls, I canonical CEILING id, J/K hidden→visible, L/M independent disclosure independence, N/O zero-segment identity still correct; P/Q/R EU preserved by existing ADD/SUBTRACT/totals tests; S untouched by the unchanged `SurfaceList` suite).
- Full frontend vitest: **349 passed** (24 files), 0 failed.
- `tsc --noEmit` PASS (0 errors); `vite build` PASS; `git diff --check` clean.
- Backend pytest not run — no backend files changed.

#### Verification:
- Mobile acceptance verified at component level: full-width top-level controls (`w-full`), 44px touch targets (`min-h-11`), `flex-wrap` ADD/SUBTRACT rows and wrapping full-width buttons eliminate horizontal scroll at 320–480 px, PL and RU labels (`Rodzaje prac i jakość` / `Виды работ и качество`, `Ukryj opcje` / `Скрыть опции`) wrap safely, ADD/SUBTRACT remain usable when expanded, light/dark theme handling unchanged from the existing card convention. Real Telegram production retest confirmed Opcje works and Rodzaje prac i jakość entry points remain present: **OWNER ACCEPTED**. `README.md` unchanged.

#### Deferred:
- **Next active sub-stage: 10C.2 — Surface Work Plan Editor. NOT STARTED.**

### Stage 10C.1C: Telegram Owner Acceptance Fixes (owner corrective sub-stage)
- **Status**: Completed 2026-09-16 (findings 1–3 frontend-only; **OWNER ACCEPTED** after real Telegram production retest; finding 4 remains deferred at the delete-policy decision gate)
- **Date**: 2026-09-16
- **Commit**: `d9d9265` — `fix(stage-10): resolve Telegram owner acceptance issues` (owner commit)
- **Why**: owner acceptance found unreadable Telegram dark-theme form controls, raw 422 validation text, and duplicate generic FLOOR/CEILING cards; permanent deletion was also requested but required dependency and retention-policy analysis before implementation.

#### Finding 1 — Telegram dark-theme form controls:
- `frontend/src/index.css` — the reusable `input`/`select`/`textarea` rule now makes the established `--tg-control-*` theme variables authoritative with `!important`, which is required because Vite's production CSS is unlayered and Tailwind appearance classes such as `bg-white` otherwise outrank element selectors. Placeholder, focus, disabled/read-only, caret, and browser autofill companions remain centralized.
- `frontend/src/hooks/useTelegramWebApp.ts` — dark control placeholder/disabled text changed from `#708499` (3.57:1 on `#232e3c`) to `#94a8bc` (WCAG-readable); the general Telegram hint color is unchanged. Light and dark application still set `data-color-scheme` and all control variables.
- `frontend/src/darkThemeControls.test.tsx` — systemic CSS precedence, theme-variable application, Opening controls under the dark pipeline, distinct borders, and WCAG control/placeholder contrast are regression-covered. This is CSS/jsdom coverage, not a claim of Telegram rendering.

#### Finding 2 — structured and localized 422 errors:
- `frontend/src/api/http.ts` — FastAPI error extraction now preserves string detail, wrapped `detail.message`, and Pydantic `detail[]` messages (including field paths); only an actually empty/unusable response falls back to `Request failed (<status>)`. Known opening-domain phrases receive stable frontend error codes without weakening backend validation.
- `frontend/src/utils/apiErrors.ts` + `frontend/src/components/OpeningList.tsx` — opening create/update/archive/restore failures pass through one localizer. The gross-area conflict and known Pydantic validation phrases are localized; unknown structured detail remains visible; generic PL/RU fallback is used only when the 422 response supplies no useful detail. Failed submissions retain entered values and repeated invalid submissions keep showing the meaningful error.
- `frontend/src/locales/pl.json` + `ru.json` — added exact PL/RU opening-area conflict copy plus validation messages. The owner example (`0.9 × 2.07207 × 11`) keeps the backend's three-decimal constraint and now reports the localized decimal-place message instead of raw `Request failed (422)`.
- `frontend/src/api/http.test.ts` + `OpeningList.test.tsx` — cover Pydantic arrays, known domain coding/localization, exact PL/RU copy, repeated rejection, empty-detail fallback, and preservation of unknown structured validation detail.

#### Finding 3 — single FLOOR/CEILING visual representation:
- `frontend/src/components/SurfaceList.tsx` — canonical FLOOR/CEILING rows are filtered only from generic-card presentation. Full fetched state still drives wall counting/naming and canonical rows remain unchanged in the backend/API.
- `frontend/src/SurfaceList.test.tsx` — verifies mixed and plane-only rooms, no generic plane cards, unchanged WALL dimensions/net area/actions/edit/archive behavior, and stable wall numbering.
- Existing `AreaSegmentList` coverage verifies that its Podłoga/Sufit cards remain the sole visual representation and their Work Plan buttons use the real canonical FLOOR/CEILING `Surface.id`, including zero-segment rooms and independent plane disclosure.

#### Finding 4 — permanent deletion decision gate (not implemented):
- No DELETE endpoint, service, UI action, confirmation, migration, or backend change was added. Physical deletion needs an explicit product decision because several current foreign keys cascade domain/audit history or silently detach references.
- Current ownership-safe archive/restore paths were reviewed. Active rows must remain ineligible for permanent deletion. Canonical FLOOR/CEILING rows are already protected from archive by `CanonicalPlaneConflictError` → HTTP 409, and restore rejects active-plane collisions; presentation filtering does not alter those invariants.

| Entity | Current dependency effect if physically deleted | Safety classification | Required policy/change before implementation |
|---|---|---|---|
| Project | Cascades Rooms and their Surfaces, Openings, AreaSegments, Inspections, Risks, Work Plans, and descendants | `NOT_APPROPRIATE_TO_HARD_DELETE` | Decide retention policy; if ever allowed, require owner scope, archived state, strict dependency/emptiness guard, 409 mapping, and confirmation |
| Room | Cascades Surfaces, AreaSegments, Inspections, Risks, and descendants | `NOT_APPROPRIATE_TO_HARD_DELETE` | Decide whether room measurement/inspection history may ever be erased; otherwise keep archive-only |
| Surface | Cascades Openings, AreaSegments, surface Inspections, Work Plan, and planned works | `BLOCK_IF_REFERENCED`; canonical FLOOR/CEILING: `NOT_APPROPRIATE_TO_HARD_DELETE` | Canonical deletion must remain forbidden; any non-canonical delete needs archived-and-empty guards and clear 409 conflicts |
| Opening | No inbound FK found; leaf row, but deletion erases net-area measurement history | `SAFE_NOW` at FK level only | Approve history erasure, then add owner-scoped archived-only delete plus confirmation |
| AreaSegment | No inbound FK found; leaf row, but deletion erases plane measurement history | `SAFE_NOW` at FK level only | Approve history erasure, then add owner-scoped archived-only delete plus confirmation |
| Client | Referencing `Project.client_id` uses `SET NULL`, silently detaching projects | `BLOCK_IF_REFERENCED` | Reject referenced clients with 409 rather than relying on `SET NULL`; permit only archived, unreferenced clients if approved |
| PriceItem | Planned work references use `RESTRICT`; market references/sources currently cascade | `BLOCK_IF_REFERENCED` | Preserve planned-work restriction as 409 and decide whether market evidence may ever be cascade-deleted |

#### Database:
- **None** — no backend source, schema, migration, validation constraint, or persisted identity changed. `README.md` unchanged.

#### Tests:
- Focused frontend (6 files: dark controls, Telegram theme hook, HTTP errors, OpeningList, SurfaceList, AreaSegmentList): **96 passed**, 0 failed.
- Full frontend vitest: **370 passed** (26 files), 0 failed. Existing asynchronous React `act(...)` warnings in three `App.test.tsx` cases remain non-failing and outside this corrective scope.
- `tsc --noEmit` PASS; `vite build` PASS; production CSS assertion PASS; `git diff --check` clean.
- Backend pytest not run — no backend files changed, as required by the corrective scope.

#### Verification:
- Local headless Chromium against the current Vite stylesheet passed the light/dark fixture for input, select, textarea, placeholder, and disabled control colors; the error element remained present.
- **Real Telegram production retest — OWNER ACCEPTED**: dark-theme input text is readable; structured/localized 422 errors work; repeated invalid submissions no longer degrade to raw `Request failed (422)`; duplicate generic FLOOR/CEILING cards are gone; canonical Podłoga/Sufit cards remain; WALL cards remain correct; Opcje works; Rodzaje prac i jakość entry points remain present.
- Findings 1–3: **PASS and OWNER ACCEPTED**. Finding 4 remained stopped before implementation because the DELETE Safety Matrix exposes material retention and cascade-policy decisions.

#### Deferred:
1. **Permanent hard-delete for archived entities** — not implemented; requires an entity-specific safe deletion policy based on the established DELETE Safety Matrix and must not introduce destructive cascades.
2. **Stage 5F — Opening Reveals / Ościeża** — execute after completion of Stage 10C; measure window/door reveal length and area for future estimate integration.

#### Current Stage 10 status:
- **Stage 10C.2A — WorkPlan Editor Shell + Existing Plan Loading: completed and OWNER ACCEPTED after real Telegram retest.** Stage 10C.2 is not complete.
- **Stage 10C.2B — Frontend Price Book Picker: completed and OWNER ACCEPTED after real Telegram retest (cosmetic picker/card polish deferred to final UI/UX polish).** Stage 10C.2 is not complete.
- **Stage 10C.2C — Planned Work Ordering: completed and OWNER ACCEPTED after real Telegram retest.** Stage 10C.2 is not complete.
- **Stage 10C.2D — Final Integration Verification: completed and OWNER ACCEPTED (no implementation changes; 420/420 tests PASS). 10C.2 = COMPLETE.**
- **Stage 10C.3 — Apply Work Plan to All Walls: completed and OWNER ACCEPTED after real Telegram retest, committed `e68a67b`. 10C = COMPLETE.**
- **Stage 5F — Opening Reveals / Ościeża** is now unblocked; proceed when owner approves.

### Stage 10C.2A: WorkPlan Editor Shell + Existing Plan Loading (frontend)
- **Status**: Completed 2026-09-16 (frontend; **OWNER ACCEPTED** after real Telegram retest)
- **Date**: 2026-09-16
- **Commits**: `e8470ab` (editor shell) and `f53f9b1` (surface-name localization correction).

#### Added:
- `frontend/src/types/workPlan.ts` — strict frontend mirrors of `SurfaceWorkPlanRead`, ordered `SurfacePlannedWorkRead`, nullable embedded Price Item summaries/prices, and the full-replacement `SurfaceWorkPlanUpsert` payload.
- `frontend/src/api/workPlans.ts` — exact per-surface GET/PUT adapter for `/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/work-plan`; only the exact `404 + "Surface work plan not found"` contract is treated as an absent plan.
- `frontend/src/components/SurfaceWorkPlanEditor.tsx` — one reusable mobile editor for WALL/FLOOR/CEILING with guarded loading/retry/error states, no-plan empty draft, substrate and contextual quality selectors, ordered read-only planned-work preview, and explicit Save.
- `frontend/src/api/workPlans.test.ts` + `frontend/src/SurfaceWorkPlanEditor.test.tsx` — API URL/body/no-plan contract and editor loading/hydration/error/retry/quality/preview/save/stale-response regressions.
- Matching `work_plan` PL/RU locale blocks for editor-specific copy.

#### Changed:
- `frontend/src/components/SurfaceList.tsx` — activates the existing WALL/OTHER entry button with `aria-expanded`/`aria-controls`; editor state remains independent from per-card `Opcje` state. Each editor receives the exact row's real `Surface.id`; generic FLOOR/CEILING cards remain filtered.
- `frontend/src/components/AreaSegmentList.tsx` — activates FLOOR/CEILING entry buttons with the already-resolved canonical plane `Surface.id`; no segment, room, replacement, or synthetic identity is used. Measurement `Opcje` state remains independent.
- Save sends the edited `substrate`/nullable `quality_target` plus every loaded `price_item_id` in unchanged occurrence order, including duplicates, because PUT is full replacement. Opening, closing, and unchanged state never PUT. A failed PUT retains the full draft/list; success rehydrates from the canonical response.
- Quality options are S1–S4 for concrete/gypsum plaster/cement-lime plaster and Q1–Q4 for gypsum board. PAINTED/OTHER remain unrestricted per the accepted backend contract, but changing to either clears the previous S/Q target synchronously; no S↔Q conversion occurs.
- Planned-work rows remain in response order and are keyed by occurrence ID. Nullable/archived embedded items remain visible; a NULL owner price renders “Do ustalenia” / “Уточняется” and is never replaced by market evidence.
- `frontend/src/SurfaceList.test.tsx`, `frontend/src/AreaSegmentList.test.tsx`, and `frontend/src/locales/parity.test.ts` now cover exact IDs, open/close, `Opcje` independence, canonical plane filtering, and PL/RU parity.

#### Database:
- **None** — no backend, schema, model, service, API, or migration change was required. The accepted 10B.2 GET/full-replacement PUT contract is sufficient.

#### Tests:
- Focused frontend (WorkPlan API/editor, SurfaceList, AreaSegmentList, locale parity): **78 passed** (5 files), 0 failed.
- Full frontend Vitest: **383 passed** (28 files), 0 failed.
- Strict TypeScript (`tsc --noEmit`): **PASS** (0 errors).
- Production Vite build: **PASS** (77 modules transformed).
- Backend pytest not run — no backend files changed.
- `git diff --check`: **PASS**.

#### Verification:
- Automated acceptance covers exact no-plan 404/no auto-create, other-404 error + Retry, late-response isolation, S/Q/null behavior, deterministic incompatible-quality clearing, ordered/duplicate preview, unavailable/archived/null-price rows, exact full-list PUT preservation, successful rehydration, failed-save draft retention, WALL/FLOOR/CEILING canonical identity, and `Opcje` independence.
- Mobile/theme structure uses only vertical full-width controls, `min-w-0`, wrapping/break-word rows, and `min-h-11` actions with centralized Telegram light/dark control variables; no desktop breakpoint or new CSS was added. PL/RU locale parity passes.
- The initial shell verification could not claim a seeded end-to-end Telegram walkthrough. The later localization-correction runtime walkthrough passed at 390 px / 412 px, and the final real Telegram/mobile retest was **OWNER ACCEPTED**.
- Scope review: `README.md`, backend, migrations, Stage 5F, permanent delete, apply-to-room-walls UI, Estimate calculations, and 10C.2B/10C.2C/10C.2D are unchanged/not implemented.

#### Owner-acceptance localization correction (2026-09-16; OWNER ACCEPTED):
- Owner Telegram verification passed editor opening, substrate-specific S/Q scales, save/rehydration, and dark-theme readability, but found persisted technical names such as `Wall 1` rendered directly in Russian.
- Added one presentation-only display-name rule for exact generated WALL names and canonical FLOOR/CEILING names. PL renders `Ściana N` / `Podłoga` / `Sufit`; RU renders `Стена N` / `Пол` / `Потолок`. Arbitrary custom names remain unchanged; persisted `Surface.name` and authoritative `Surface.id` are untouched.
- `SurfaceList`, `AreaSegmentList`, inspection handoff labels, and WorkPlan subtitles now use the same display rule. FLOOR/CEILING remain represented only by their existing AreaSegment cards; no generic duplicates or synthetic IDs were introduced.
- Focused frontend localization/identity tests: **76 passed** (4 files), 0 failed. Full frontend Vitest: **391 passed** (29 files), 0 failed. Strict TypeScript: **PASS**. Production Vite build: **PASS** (78 modules transformed).
- Runtime Chromium walkthrough: **PASS** at 390 px and 412 px for PL/RU generated WALL names, custom-name preservation, localized WALL/FLOOR/CEILING WorkPlan subtitles, canonical IDs, no generic plane duplicates, no horizontal overflow, and no browser runtime errors.
- Backend tests not run because backend diff is empty. No schema/migration or README change. **OWNER ACCEPTED after final real Telegram retest.**

#### Deferred:
1. **10C.2B frontend picker** — contract blocker resolved and remains the next execution scope, but is not implemented in this correction; **10C.2C/10C.2D** remain unstarted.
2. **Stage 10C.3 — Apply Work Plan to All Walls** — existing backend endpoint remains intentionally unexposed in 10C.2A. The future WALL-only **„Zapisz dla wszystkich ścian” / „Сохранить для всех стен”** action uses the selected active WALL as source and applies to every other ACTIVE WALL in the same Room. It copies/replaces only `substrate`, `quality_target`, and ordered planned works. It never modifies Surface identity, dimensions, geometry, openings, deductions, AreaSegments, inspections, inspection answers, findings, risks, communication, photos/defects, archive state, or Estimate data.
3. **Estimate calculations (`Estimate` / `EstimateLine`)** — not implemented.
4. **Stage 5F Opening Reveals / Ościeża** — remains deferred until completion of Stage 10C; **permanent hard-delete** remains separately deferred under the previously accepted decision.

### Stage 10C.2B prerequisite: WorkPlan archived-reference contract correction (backend)
- **Status**: Implemented and verified 2026-09-16; frontend Price Book picker **NOT STARTED**; Stage 10C.2B is not complete.
- **Migration**: None.

#### Corrected contract:
- Active `PriceItem` rows with `LABOR`, `MATERIAL`, or `LABOR_AND_MATERIAL` scope are all valid WorkPlan references. Scope does not change planning validity; mixed Estimate splitting remains forbidden and unimplemented.
- A new WorkPlan cannot reference an archived PriceItem. On full replacement of an existing WorkPlan, each archived `price_item_id` may be retained or reordered only up to its persisted occurrence count on that same plan. Its count may decrease to zero, but can never increase after archival; once removed, it cannot be re-added while archived.
- Active duplicates, exact payload order, owner isolation, and NULL owner prices remain unchanged. GET continues embedding archived referenced PriceItem summaries for the frontend preview.
- `apply-to-room-walls` remains deliberately stricter: an archived source item rejects the entire operation before any target mutation, so an archived reference is never introduced onto another wall.

#### Verification:
- Focused WorkPlan domain/service tests: **56 passed**, 0 failed.
- Focused WorkPlan API tests: **39 passed**, 0 failed; 8 existing FastAPI/Starlette HTTP 422 deprecation warnings.
- Full backend pytest: **631 passed**, 0 failed; 36 existing FastAPI/Starlette HTTP 422 deprecation warnings.
- No frontend, schema, migration, Estimate, apply-to-all UI, Stage 5F, permanent-delete, or README implementation change.

### Stage 10C.2B: Frontend Price Book Picker (frontend)
- **Status**: Completed 2026-09-16 (frontend; **OWNER ACCEPTED** after real Telegram retest; cosmetic picker/card polish deferred to final UI/UX polish); Stage 10C.2 is not complete.
- **Migration**: None.

#### Delivered:
- `SurfaceWorkPlanEditor.tsx` now supports full Price Book picker:
  - "+ Dodaj pracę" / "+ Добавить работу" button opens inline Price Book picker modal/panel.
  - Loads owner active price items in a single request via existing `fetchPriceItems({ archived: 'active' })` client.
  - Supports `LABOR`, `MATERIAL`, and `LABOR_AND_MATERIAL` price scopes.
  - Archived price items excluded from new selection picker candidates.
  - NULL owner price is valid and displayed as localized "Do ustalenia" / "Уточняется"; market price is never substituted.
  - Client-side search across localized name, code, category, scope, unit.
  - Selecting an item appends a new independent occurrence to the local draft (duplicates permitted and distinct).
  - Draft occurrences support individual removal ("Usuń" / "Убрать") without touching catalog items.
  - Preserves exact occurrence order and duplicate IDs in full-replacement PUT payload.
  - Existing archived occurrences remain visible with archived badge and can be saved or removed.
  - Failed save preserves the entire local draft; successful save rehydrates canonical plan and clears dirty state.
  - Unified across canonical WALL, FLOOR, and CEILING surfaces (`Surface.id`).
  - Mobile-first (320–480 px, >=44 px touch targets, no horizontal scrolling, safe wrapping).

#### Verification:
- Focused `SurfaceWorkPlanEditor.test.tsx`: **27 passed** (including 17 new picker tests).
- Full frontend Vitest: **411 passed** across 29 test files (0 failed).
- TypeScript typecheck (`tsc --noEmit`): PASS (0 errors).
- Vite production build (`vite build`): PASS.
- Backend diff: EMPTY (preceding contract correction already passed full 631 backend tests).
- `git diff --check`: PASS.

### Stage 10C.2C: Planned Work Ordering (frontend)
- **Status**: Implemented and verified 2026-09-16 (awaiting owner verification); Stage 10C.2 is not complete.
- **Migration**: None.

#### Delivered:
- `SurfaceWorkPlanEditor.tsx` now supports simple mobile ordering controls for planned-work occurrences:
  - Each occurrence in the draft list includes ↑ (move up) and ↓ (move down) buttons.
  - ↑ moves the specific occurrence one position up; disabled for the first item (`index === 0`).
  - ↓ moves the specific occurrence one position down; disabled for the last item (`index === draftOccurrences.length - 1`).
  - Moving an occurrence modifies the local draft only; no API calls are made during reordering.
  - Reordering marks the draft dirty and enables the Save button.
  - Duplicate PriceItem occurrences remain completely independent; moving one duplicate does not affect the other.
  - Archived occurrences in the plan can also be reordered.
  - Underlying PriceItem catalog rows are never modified.
  - Save (`putSurfaceWorkPlan`) sends `price_item_ids` in the exact visible reordered sequence with duplicate IDs preserved.
  - Successful save rehydrates the server canonical plan order and clears dirty state.
  - Failed save retains the reordered local draft without losing user changes.
  - Mobile controls sized for touch targets (>=44px height) without causing horizontal scrolling.
  - Localized with `move_up` and `move_down` in PL and RU.

#### Verification:
- Focused `SurfaceWorkPlanEditor.test.tsx`: **36 passed** (including 9 new ordering tests).
- Full frontend Vitest: **420 passed** across 29 test files (0 failed).
- TypeScript typecheck (`tsc --noEmit`): PASS (0 errors).
- Vite production build (`vite build`): PASS.
- Backend diff: EMPTY (no backend changes needed).
- `git diff --check`: PASS.

### Stage 10C.3: Apply Work Plan to All Walls (frontend)
- **Status**: Completed 2026-09-16 — **OWNER ACCEPTED** after real Telegram retest; committed `e68a67b`; **Stage 10C = COMPLETE**.
- **Migration**: None.

#### Delivered:
- `frontend/src/types/workPlan.ts` — `SurfaceWorkPlanApplyResult` type added (`source_surface_id`, `target_count`, `target_surface_ids`, `targets`).
- `frontend/src/api/workPlans.ts` — `applyWorkPlanToRoomWalls(projectId, roomId, surfaceId)` POSTs to `.../work-plan/apply-to-room-walls`.
- `frontend/src/locales/pl.json` / `ru.json` — 6 new `work_plan.*` keys: `apply_to_walls`, `apply_confirm`, `apply_confirm_yes`, `applying`, `apply_success`, `apply_error`.
- `frontend/src/components/SurfaceWorkPlanEditor.tsx`:
  - New optional props: `isWall?: boolean` (default `false`), `otherActiveWallCount?: number` (default `0`).
  - `ApplyState` type: `'idle' | 'confirming' | 'applying' | 'success' | 'error'`.
  - Inline `ApplyState` machine rendered below the Save button; only visible when `isWall && hasPlan`.
  - `idle`: "Zapisz dla wszystkich ścian" / "Сохранить для всех стен" button, full width.
  - `confirming`: count confirmation panel with Kopiuj / cancel; shows `otherActiveWallCount`.
  - `applying`: `<p role="status">` spinner text.
  - `success`: applied count + dismiss.
  - `error`: error text + dismiss back to idle.
  - FLOOR/CEILING/OTHER surfaces: `isWall=false` (default) — button never appears.
- `frontend/src/components/SurfaceList.tsx` — WALL-branch `SurfaceWorkPlanEditor` now receives `isWall={true}` and `otherActiveWallCount={activeWallCount - 1}`.

#### Tests:
- `frontend/src/api/workPlans.test.ts` — 1 new test (POST to apply-to-room-walls, no body).
- `frontend/src/SurfaceList.test.tsx` — mock updated with `applyWorkPlanToRoomWalls: vi.fn()`.
- `frontend/src/SurfaceWorkPlanEditor.test.tsx` — 7 new tests: button shown for WALL with plan; button hidden for non-WALL; button hidden when no plan; click shows confirmation with count; cancel returns to idle; confirm calls API + shows success; error shows + dismiss returns to idle.

#### Verification:
- Focused tests: **85 passed** (44 editor + 37 list + 4 API) across 3 files.
- Full frontend Vitest: **429 passed** across 29 test files (0 failed).
- TypeScript typecheck (`tsc --noEmit`): PASS (0 errors).
- Vite production build (`vite build`): PASS.
- Backend diff: EMPTY (backend endpoint already existed from Stage 10B.2).
- `git diff --check`: PASS.

#### Deferred:
- Owner manual Telegram acceptance at 390/412 px.
- Cosmetic polish (button styling, success toast animation) — deferred to final UI/UX polish stage.
- Stage 10D (Estimate calculation) — next stage, not started.

### Stage 10H.1: Unresolved Manual Quantity Safety (Estimate FINAL hardening; discovered via Stage 11 integration)
- **Status**: Completed 2026-09-21 — not yet owner-accepted; part of the same Stage-11 manual-acceptance walkthrough that surfaced it.
- **Migration**: None. No schema/field change — the existing `EstimateLine.quantity_source`/`source_quantity`/`quantity_overridden` fields already fully encode the distinction; this closes a validation/display gap only.

#### Discovered defect (manual Stage-11 acceptance, 2026-09-21):
Accepting the `CRACK_RECURRENCE` recommendation (`CENNIK_SKIM_CRACK-01`, unit LM) appended a `SurfacePlannedWork` row that generated an `EstimateLine` with `quantity_source=MANUAL`, `source_quantity=NULL`, `quantity_overridden=False`, and a stored `Decimal("0.000")` fallback — a Stage 10 design that is deliberate and tested (`test_non_m2_item_gets_manual_quantity_source`), since no length geometry exists anywhere for a plain Surface (unlike an Opening's reveal, which has real `REVEAL_LENGTH`/`REVEAL_AREA` geometry). The Estimate UI displayed this indistinguishably from a genuine, confirmed zero quantity, and `EstimateService.finalize()` only ever checked `unit_price IS NULL` — a `0.000`-fallback LM line could finalize once priced, silently under-billing real accepted work. Diagnosed read-only first (no code changed during diagnosis); root cause confirmed via full Stage 10 quantity-derivation audit (Surface M2 → `SURFACE_NET_AREA`; Surface LM/PCS/HOUR/DAY/FLAT → always `MANUAL`/`NULL`/`0.000`; Reveal LM → `REVEAL_LENGTH`; Reveal M2 → `REVEAL_AREA`) and a positive control (`Gruntowanie gruntem penetrującym` correctly shows `1.284 m²` via `SURFACE_NET_AREA`, unaffected).

#### Owner decision:
Unresolved MANUAL quantity (`quantity_source=MANUAL AND source_quantity IS NULL AND quantity_overridden=False`, on a `PLANNED_WORK`-origin line only) is distinct from an explicit, owner-confirmed zero (`quantity_overridden=True`) and must never finalize; it must never be displayed to the owner as a meaningful `0.000`.

#### Added/Changed (backend):
- `EstimateService.finalize()` (`backend/app/domain/services/estimate_service.py`) gains a second, independent FINAL blocker alongside the existing unresolved-price check: any line with `origin=PLANNED_WORK AND quantity_source=MANUAL AND source_quantity IS NULL AND quantity_overridden=False` blocks finalization with `EstimateValidationError`. Explicitly scoped to `origin=PLANNED_WORK`: a freeform MANUAL-origin line (`add_manual_line`) always carries the identical `(quantity_source=MANUAL, source_quantity=NULL, quantity_overridden=False)` fingerprint by construction (the owner already typed its quantity at creation), so it is resolved by definition and must never be misclassified — caught and fixed during focused testing (`test_v2_does_not_copy_v1_manual_lines_or_overrides` initially regressed, then passed once the `origin` guard was added). Both blockers (price, quantity) are independent and both are named in the raised message when both apply; existing price-only message text is unchanged for backward compatibility with the frontend's existing count-extraction regex.

#### Added/Changed (frontend):
- `EstimateShell.tsx`: new `isUnresolvedQuantity(line)` helper (mirrors the backend predicate exactly, including the `origin=PLANNED_WORK` scoping) — a matching line now displays **„Ilość do ustalenia" / mb** instead of the raw `0.000 mb`; an explicit owner-confirmed zero (`quantity_overridden=True`) always displays normally (`0.000 mb`), never as unresolved. New `extractUnresolvedQuantityCount` (mirrors the existing `extractUnresolvedPriceCount`, now un-anchored so both can be detected in one combined message regardless of order) feeds a new localized, actionable finalize-rejection message; when both price and quantity are unresolved, both localized sentences are shown together. No change to the existing manual quantity-edit/reset mechanism (`patch_line`/`EstimateLineUpdate`) — it already supported exactly this (owner enters e.g. `4.5`, `quantity_overridden` becomes `True`; reset restores the exact prior fingerprint) and needed no backend change.
- New PL/RU locale keys: `estimates.quantity_unresolved` ("Ilość do ustalenia" / "Количество не определено"), `estimates.finalize_unresolved_quantity_error` (count-based actionable sentence, mirroring the existing price-error key's style).

#### Explicitly deferred (separate, not addressed here):
- **`UNEVENNESS_PREP_INCREASED` → `CENNIK_SKIM_LOCAL-01` (M2) local-repair quantity policy.** This item mechanically auto-derives the *full* `Surface.net_area` (a legitimate M2 derivation, so it never triggers the new unresolved-quantity blocker), but the PriceItem's own name is "Szpachlowanie lokalne / naprawy punktowe" (**local/point** repairs) — substituting the whole wall's area for a local-patch quantity is a real scope/semantic mismatch, just not a `0.000`-looking one. Not fixed, redesigned, or silently remapped in this pass — recorded as a pending, separate product/domain decision.

#### Manual UX Defect #4 (found during the same manual acceptance, 2026-09-21): main estimate card/list parity
The per-line detail-view fix above was real but incomplete: the Estimate's main "Wersja 2" card/list view (the collapsed multi-line *group* aggregate, `buildGroups`/`group.quantity`) computed a raw `sumDecimalStrings` over `quantity` with no awareness of the unresolved predicate, so a single-line group whose only line was unresolved still summed to the literal string `"0.000"` and rendered numerically — reproducing the exact reported symptom in that one specific, most-visible render path, even though the drilled-down detail view was already correct. A live end-to-end HTTP round-trip (real FastAPI app, real Pydantic serialization, in-process ASGI, reproducing the exact reported DB fingerprint) first confirmed the backend/schema contract was already fully correct at every layer (`origin`/`quantity_source`/`source_quantity`/`quantity_overridden` all serialize exactly as expected) before concluding the defect was frontend-only. Fixed with the smallest coherent addition: `EstimateGroup` gained a `hasUnresolvedQuantity` field (`gLines.some(isUnresolvedQuantity)`), and a new shared `quantityDisplay(quantity, unit, unresolved)` helper now backs *both* the per-line and group-card render sites, so the unresolved-vs-numeric decision is made in exactly one place instead of being duplicated (and one of the two copies silently omitted, as happened here). No backend, schema, or persisted-value change. 6 new `EstimateShell.test.tsx` tests cover the main-card unresolved display, explicit-zero/MANUAL-origin/Surface-M2/Reveal-LM/Reveal-M2 non-regression at the group level.

#### Owner manual acceptance (2026-09-21): **PASS**
Owner verified the complete flow end-to-end: unresolved LM planned work shows "Ilość do ustalenia / mb" in both the main estimate card and the detail view; entering `4.5` saves and displays as `4.500 mb` with the manual-change state visible; reset returns the line to unresolved quantity (main card and detail both revert to "Ilość do ustalenia / mb"); FINAL is blocked while unresolved quantity exists and continues to block unresolved prices independently; the estimate correctly remains DRAFT/Szkic throughout. **Stage 10H.1 is manually accepted.**

#### Tests:
- Backend: new `backend/tests/test_estimate_quantity_hardening.py` (16 tests) — unresolved-quantity blocks FINAL; the exact blocker fingerprint; explicit manual `4.500` allows FINAL; explicit overridden `0.000` is never misclassified as unresolved; Surface M2 / Reveal LM / Reveal M2 auto-derivation never blocks; unresolved price still independently blocks; price-resolved+quantity-unresolved and quantity-resolved+price-unresolved each still block on their own reason only; both-resolved allows FINAL; both-unresolved reports both blockers in one message; a freeform MANUAL-origin line is never misclassified; reset restores the exact unresolved fingerprint (and re-blocks FINAL); DRAFT regeneration preserves both the unresolved fingerprint and a prior manual override. Full backend suite re-run **1081/1081 PASS** (unchanged by the frontend-only defect #4 fix), including the full `test_estimates.py`/`test_estimates_hardening.py`/`test_estimates_api.py`/`test_work_recommendation*.py` families with zero regressions.
- Frontend: `EstimateShell.test.tsx` grew to 335 tests (14 from the original hardening pass + 6 from defect #4) covering the unresolved display at both the line and group-card level, edit/save/reset flows, the M2/Reveal-LM/Reveal-M2 positive controls, the MANUAL-origin non-misclassification (at both levels), and all four finalize-message combinations (PL, RU, combined, price-only-unaffected). Full frontend suite re-run **1016/1016 PASS** (36 files); `RecommendationPanel.test.tsx` (48) and `InspectionFlow.test.tsx` (39) re-verified unaffected; `tsc --noEmit` PASS; production `vite build` PASS (90 modules); `git diff --check` CLEAN.

#### Verification:
- No migration created; Alembic single head unchanged (`0022_work_recommendations`), confirmed via `alembic heads`.
- No `SurfaceWorkPlan`/`WorkRecommendation` mutation introduced anywhere in this change — `EstimateShell.tsx`'s test file imports/mocks only `../api/estimates`, structurally incapable of touching either.
- **Status at the time this hardening pass was implemented (2026-09-21): manual Stage 11D.2 acceptance was still pending, not yet owner-accepted.** Next owner action at that point: reload the Estimate `Wersja 2 / Szkic` view, confirm `Naprawa rys i pęknięć` now shows "Ilość do ustalenia / mb" instead of `0.000 mb`, use the existing quantity-edit control to enter the real measured crack length, then retry finalize. **This was subsequently completed** — see the Stage 11 roadmap entry above and the Stage 10H.1 section below for the final owner-accepted outcome; Stage 11 is now **COMPLETE — OWNER ACCEPTED — INTEGRATED TO MAIN**.

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
