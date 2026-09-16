# Stage 10A — Surface Work Planning + Estimate Architecture

- **Date**: 2026-09-15
- **Branch / HEAD**: `stage-10` @ `96d0518` (Merge Canonical Stage 9 into main)
- **Stage**: 10A (architecture & domain contract) — **documentation only**
- **Scope guardrails**: no application code, no Alembic migrations, no backend/frontend behavior changes, no Git commit/push/deploy (VCS is performed manually by the owner after acceptance). Stage 10B must not start without explicit owner approval.

> **10A.1 — Canonical Architecture Corrections (applied 2026-09-15, docs only; owner-accepted 2026-09-15 — ZERO open owner decisions remain before 10B)**
> The record below is corrected per owner decision. Corrections: the Work Plan model becomes one
> `SurfaceWorkPlan` per physical `Surface` (1:0..1), the plan-level quantity override is removed, manual
> estimate lines no longer require a `PriceItem`, ROBOCIZNA / MATERIAŁY become the normal estimate
> presentation (mixed = exception bucket), and regeneration refreshes the DRAFT in place (new version only
> for a meaningful commercial revision). Contradictory 10A text has been removed, not duplicated. §24
> (D1–D18), §26, and Appendix A below are the corrected contract.

> **10C.1A — Canonical Floor/Ceiling Surfaces (implemented 2026-09-16, uncommitted; awaiting owner acceptance)**
> Corrective sub-stage discovered during 10C.1 acceptance: the standard room workflow did not provision
> canonical FLOOR/CEILING `Surface` rows, so Stage 10B `SurfaceWorkPlan` had no stable `Surface.id` for the
> floor/ceiling measurement planes (WALLs are real `Surface` rows; FLOOR/CEILING were room-scoped
> `AreaSegment` planes only). 10C.1A makes FLOOR and CEILING canonical physical `Surface` entities for every
> room. Full record: §25A.

---

## 0. Purpose

This record settles the architecture of canonical **Stage 10 — Estimate / Kosztorys**: the contractor's
**Surface Work Planning** model and the **line-item Estimate** it feeds. It is the Stage 10 analogue of the
Stage 9A decision record. It resolves 18 required architecture decisions (§24) and defines the 10A–10I
execution plan, the mobile UX contract, and the acceptance scenario.

**Product question Stage 10 answers**: *"What work are we going to do on each surface (gładź, włóknina,
malowanie, mikrocement…), in what order, at what quality — and, once the owner prices are set in the Price
Book, what is the line-item kosztorys to show the client?"*

**What Stage 10 is NOT** (boundary): it is not the Price Book (Stage 9, done), not the automatic
inspection → recommended-work mapping (Stage 11), not price coefficients (Stage 12), not technological
workflows/drying (Stage 13), not photos/defects (Stage 14), not PDF generation (Stage 15), not contracts
(Stage 16).

---

## 1. Product goal

1. **Plan the scope of work per physical surface**: the owner stands in a room and records, per wall /
   floor / ceiling, which finishing works apply (e.g. *gładź szpachlowa + włóknina szklana + malowanie* on
   walls; *mikrocement* on the floor), in execution order. **Each physical surface owns one
   `SurfaceWorkPlan`** (`Surface 1 → 0..1 SurfaceWorkPlan`), so walls in the same room may plan different
   substrates, qualities, and works.
2. **Anchor each planned work to the Price Book**: every planned work *is an application of an existing
   `PriceItem`* (labor or material). No prices are typed into the plan; the Price Book stays the single
   pricing source.
3. **Declare the commercial substrate + quality tier** once per plan (S1–S4 / Q1–Q4), reusing the Stage 6
   enums and its scale-validity rule. The quality tier selects *which* works are appropriate — it is never
   a silent numeric multiplier (coefficients are Stage 12 / Stage 10A Decision D5).
4. **Generate a line-item Estimate** from the plans. Each line is a real number for the client: quantity
   (from the measured surface / owner entry) × owner unit price (from the Price Book), presented under
   ROBOCIZNA and MATERIAŁY subtotals (mixed = exception bucket, §15).
5. **Freeze commercial history**: an accepted estimate line never changes when the owner later edits the
   Price Book or refreshes market evidence (Stage 9E.1 / Stage 9A §10 snapshot obligation).

---

## 2. UX contract (mobile-first)

The canonical UI is the Telegram Mini App on a smartphone (permanent mobile-first rule in `CLAUDE.md`):

- **Primary viewports**: 320–480 px width; acceptance is verified at 390 px and 412 px.
- **Workflow** (progressive disclosure, minimal taps for a contractor on site):

  ```
  Project (Obiekt)
    └─ Room → "Plan prac" (plan screen)
         ├─ Surface list (Ściana 1–4, Podłoga, Sufit)  →  one SurfaceWorkPlan per surface
         │     ├─ per-surface: substrate + quality picker (pre-filled from completed inspections)
         │     ├─ per-surface: ordered work list → "Dodaj pracę" → Price Book picker
         │     │    (filter by category, unit, substrate hint)
         │     ├─ reorder (↑↓), remove work
         │     └─ "Zapisz dla wszystkich ścian" / "Сохранить для всех стен"
         │        (Stage 10C.3 apply-to-all: copy one wall's plan to the others,
         │        explicit overwrite confirmation)
         └─ "Wygeneruj kosztorys"  →  Estimate editor (DRAFT)
              ├─ grouped lines (per surface → works in position order)
              ├─ per-line: quantity (overridable), price override / "Do ustalenia"
              ├─ "Dodaj pozycję ręcznie" (freeform manual line — no book row required)
              ├─ totals footer: Robocizna / Materiały / [Mieszane] / Razem
              └─ status: Wersja robocza → Zatwierdź (FINAL)
  ```

- **Interaction rules applied**: ≥44 px touch targets, vertical stacking, no horizontal page scrolling,
  labels wrap (RU labels are materially longer than PL), decimal `inputMode="decimal"` for quantity and
  price inputs, Telegram BackButton respected, every string in PL/RU locale dictionaries — no raw strings
  in components, no price/labor rates/coefficients in components (backend Price Book is the only source).
- **Global "Do ustalenia" pattern** (consistent with the Price Book card): a line whose owner price is not
  set renders `Do ustalenia` (PL) / `Уточняется` (RU). Market evidence is never substituted into a price
  (stage 9E contract).

---

## 3. Work Plan domain

Two new entities enter the domain (Stage 9E.7 made `PriceItem.price` nullable precisely so that the stage
10 estimate can distinguish *not-set* from *zero*):

- **`SurfaceWorkPlan`** — **one per physical `Surface`** (`Surface 1 → 0..1 SurfaceWorkPlan`). It carries
  the commercial substrate + quality tier for exactly that surface and its ordered planned works. It is a
  *scope declaration*, not a money document.
- **`SurfacePlannedWork`** — a child line: *"we apply PriceItem X on this surface, in order Z"*. Multiple
  planned works per plan are allowed (including the same PriceItem twice, e.g. two separate coat rows) —
  ordered by `position`.

**Entity diagram (corrected model):**

```
Surface (Ściana / Podłoga / Sufit)  1 → 0..1  SurfaceWorkPlan
SurfaceWorkPlan                     1 → 0..*  SurfacePlannedWork
SurfacePlannedWork                  * → 1     PriceItem

SurfaceWorkPlan    : id · surface_id (UNIQUE NOT NULL) · substrate · quality_target ·
                     created_at / updated_at
SurfacePlannedWork : id · work_plan_id (FK NOT NULL) · price_item_id (FK NOT NULL) · position ·
                     created_at / updated_at
```

- `SurfaceWorkPlan.surface_id` is **UNIQUE NOT NULL** — exactly one plan per physical surface. No
  `name` / `status` / `owner_id` / `project_id` are duplicated on the plan: the surface is the identity,
  and owner/project/room are reached via `Surface → Room → Project → User` (these are sub-entities, not
  tenancy roots).
- `SurfacePlannedWork` carries **no `surface_id`** (its surface is its plan's surface) and **no quantity
  override** (quantity is a commercial estimate-line concern, §12). Two tables, per §24 D1–D2.

**Section 24 D1–D4** fix the exact entities, the `Surface` relationship, the `PriceItem` relationship, and
the ordering rule.

---

## 4. Multiple works per surface

A surface commonly receives several sequential works (*gładź → włóknina → malowanie*), and the same scope
of work differs per surface (*walls get gładź + włóknina + malowanie; the floor gets mikrocement; the
ceiling gets gładź + malowanie only*).

- `SurfacePlannedWork` rows are **per plan** payload; nothing is shared or inferred between surfaces —
  each surface's `SurfaceWorkPlan` is independent.
- A plan's order of works is the execution order and the estimate line order.
- Revising one wall's plan never mutates its neighbours' plans (only the explicit **apply-to-all**
  action copies — §6).

---

## 5. Substrate + quality in the plan

- Reused **verbatim** from Stage 6: the `Substrate` enum
  (`CONCRETE / GYPSUM_PLASTER / CEMENT_LIME_PLASTER / GYPSUM_BOARD / PAINTED / OTHER`) and the
  `QualityLevel` enum (`S1–S4`, `Q1–Q4`).
- `SurfaceWorkPlan.substrate` (NOT NULL) and `SurfaceWorkPlan.quality_target` (nullable) are **the
  commercial decision the owner quotes against, per physical surface**. They are validated by the existing
  `assert_quality_scale_valid(substrate, quality_target)` rule from
  `app/domain/rules/inspection_rules.py` (GYPSUM_BOARD → Q1–Q4; CONCRETE / GYPSUM_PLASTER /
  CEMENT_LIME_PLASTER → S1–S4; PAINTED / OTHER unrestricted).
- **Per-surface, natively**: each wall/floor/ceiling has its own plan header. The four-wall example is
  supported directly — `Wall 1 → GYPSUM_PLASTER → S3`, `Wall 2 → GYPSUM_PLASTER → S3`,
  `Wall 3 → CONCRETE → S3`, `Wall 4 → GYPSUM_BOARD → Q3` — each wall's plan recording its own
  substrate/quality.
- **Ownership**: the plan owns the commercial substrate/quality. A completed Stage 6 `Inspection` on the
  same surface is the *measurement reality* and is used purely as a UI **pre-fill** (the most recent
  COMPLETED inspection for the surface with a substrate). The plan never writes back to an Inspection.
- **Quality selects works, not a multiplier**: the quality tier affects which `PriceItem` rows the UI
  surfaces (e.g. by `PriceItem.quality_level` hint or category filtering) and which coefficient-free
  pricing applies. **Stage 10 applies no numeric quality factor** — that is Stage 12
  (Price coefficients). The roadmap phrase *"by surface, substrate, and quality tier"* is realised as:
  surface → quantity, substrate+quality → selected works, Price Book → unit price.

---

## 6. Apply-to-all walls

A one-tap bulk operation for the on-site workflow: *"this room's walls all get the same planning
configuration"*.

**Current execution ownership**: **Stage 10C.3 — Apply Work Plan to All Walls** implements this
WALL-only action with the final UI labels:

- PL: **„Zapisz dla wszystkich ścian”**
- RU: **„Сохранить для всех стен”**

It uses the existing backend endpoint:
`POST .../surfaces/{source_surface_id}/work-plan/apply-to-room-walls`.

- **WALL-only source and targets**: the selected active WALL is the source; the operation applies to every
  other ACTIVE WALL surface in the same Room. FLOOR, CEILING, and OTHER never expose this action.
- **Semantics** (copy / replace): the source WALL's plan **copies / replaces only the planning
  configuration** in each target wall's `SurfaceWorkPlan` (creating it if absent, replacing its contents
  if present):
  1. `substrate`,
  2. `quality_target`,
  3. the ordered `SurfacePlannedWork` rows.
- **Explicit overwrite confirmation**: if a target wall already has a plan with works, the UI shows a
  confirm dialog with the count of rows that would be replaced (`Zastąpić plan prac na N ścianach?`).
  Overwrite is destructive to those plan rows only and is never silent.
- **Never copied / never changed**: physical `Surface` identity, dimensions, geometry, openings,
  deductions, AreaSegments, inspections, inspection answers, findings, risks, communication, photos /
  defects, archive state, Estimate data, or Price Book data. Apply-to-all is plan-configuration only (D6).
- After the copy each wall's plan is independent; later single-wall edits do not re-propagate.

---

## 7. Floor and ceiling works

- WALL / FLOOR / CEILING are all `Surface` rows today (`SurfaceType`), so **one `SurfacePlannedWork` model
  serves every plane**. Targeted-surface rows on a floor/ceiling are identical in shape to wall rows.
- Quantity defaults: **M2** works take the surface's **net area** (walls: net = gross − opening deduction,
  computed by Stage 5 `surface_service`/`room_geometry`; floors/ceilings: plane totals including composite
  ADD/SUBTRACT segments and openings). **LM / PCS / HOUR / DAY / FLAT** works default to a manual quantity
  at the estimate line (quantity_source = `MANUAL`; §12), since reveal geometry (5F) does not exist yet.
- A room-level non-surface item (a lump cost not tied to any plane) is out of the plan's model — it is
  added directly as a **manual estimate line** (§10).

---

## 8. Price Book relationship

The Price Book is the only pricing source, and Stage 10 never copies money into the plan:

- `SurfacePlannedWork.price_item_id` (FK, NOT NULL) references the exact catalog row — labor or material,
  M2/LM/PCS/HOUR/DAY/FLAT, the owner-editable `PriceItem.price`.
- Planning **prefers atomic `LABOR` work items** where the catalog provides them; material rows are
  planned as separate lines. Mixed `LABOR_AND_MATERIAL` catalog rows remain referenceable for backward
  compatibility (D15).
- **No price snapshot inside the plan** — the plan is scope, not money. Price enters the record only at
  estimate-line creation (§11, D9).
- **No hardcoded prices anywhere**: no unit price, no rate table, no markup in plan/estimate UI. A custom
  work that has no book row is first created as a `CUSTOM_*` PriceItem via the existing Price Book flow,
  then referenced from the plan.
- **Archiving behaviour**: archiving a `PriceItem` (Stage 9 semantics) blocks *new* plan rows referencing
  it; it never deletes or mutates existing `SurfacePlannedWork` rows or existing estimate lines (their
  snapshots stand). Generation refuses plan rows whose item is archived until the owner replaces the item
  in the plan (D3).

---

## 9. Estimate domain

- **`Estimate`** — a versioned, project-level commercial document (D8). Owned (`owner_id`), anchored to a
  project (`project_id`), with a monotonically increasing `version` per project and a lifecycle status
  (`DRAFT → FINAL → ACCEPTED | ARCHIVED`). **A version is a meaningful commercial revision, not a button
  press** (D8).
- **`EstimateLine`** — the materialized, priced, snapshot line (D7–D13). Lines originate from a planned
  work (`PLANNED_WORK`), are picked straight from the Price Book (`PRICE_BOOK`), or are owner-authored
  freeform rows (`MANUAL` — no `PriceItem` required).
- A line is a real number for the client: **quantity × unit price**, presented under ROBOCIZNA /
  MATERIAŁY subtotals (mixed = exception bucket), in PLN (D9, D14–D16).
- The Estimate owns no substrate/quality fields of its own — it inherits the commercial context from the
  plan(s) it was generated from (snapshot of the plan substrate/quality is carried per line for the PDF,
  §11).

---

## 10. Line origin

- **`PLANNED_WORK`** lines: produced by "Wygeneruj kosztorys" from the surface work plans. Provenance refs
  are kept: `plan_id`, `planned_work_id`, `surface_id` (and via the surface, the room). A generated line
  snapshots its PriceItem (§11) and materializes its quantity (§12).
- **`PRICE_BOOK`** lines: an item picked straight from the catalog into the estimate without being planned
  on a surface (a lump material, a subcontractor item). `price_item_id` NOT NULL, snapshotted like a
  generated line, quantity entered manually. Never appears in a plan.
- **`MANUAL`** lines: owner-authored freeform rows inside a DRAFT estimate (a one-off *dojazd*, a
  client-supplied item, a non-surface cost). **`price_item_id = NULL` is allowed.** The manual line
  supplies its own commercial snapshot: `description`, classification (`LABOR` / `MATERIAL`), `unit`,
  `quantity`, `unit_price`, `currency`. Manual lines **never create or modify PriceItems** and never
  appear in a plan (D10).
- `LineOrigin` is sealed into the line at creation.

---

## 11. Snapshot contract

The Stage 9A §10 / 9E.1 obligation, made concrete. At **line-creation time** the estimate line stores:

| Field | Source |
|---|---|
| `item_code` | `PriceItem.code` at creation; **NULL for MANUAL lines** |
| `description` | resolved display name at creation (`display_name` → locale `name_key` → `code`); **owner-entered for MANUAL lines** |
| `unit` | `PriceItem.unit`; **owner-entered for MANUAL lines** |
| `scope` | `PriceItem.price_scope`; **owner-chosen for MANUAL lines — restricted to LABOR / MATERIAL** |
| `currency` | `PriceItem.currency` (PLN); **owner-entered (default PLN) for MANUAL lines** |
| `unit_price` | `PriceItem.price` used, or NULL if not set; owner override allowed (D13); **owner-entered for MANUAL lines** |
| `price_override` | whether `unit_price` came from the owner, not the book (always true for MANUAL lines) |
| `source_quantity` | suggested quantity (surface net area, or NULL when no geometry / manual unit) |
| `quantity`, `quantity_source` | commercial quantity and where `source_quantity` came from (D12); owner-overridable |
| `quantity_overridden` | whether `quantity` was set by the owner, not defaulted from `source_quantity` |
| `amount` | quantized line total, or NULL while unpriced (D11/D16) |

Immutability rules:

- **Freezing is per-document**: the snapshot of a `FINAL`/`ACCEPTED` estimate is immutable. Later
  PriceItem edits, market-reference refreshes, and price-book re-seeds **never rewrite an existing
  estimate line** (tested in 10D).
- **DRAFT lines can be replaced**: editing a still-DRAFT document re-runs generation/editing explicitly;
  nothing is silently recalculated in place.
- No `price_history` table is introduced on the Price Book for this (Stage 9 decision stands). History is
  expressed as estimate **versions** (D8).

---

## 12. Quantity source + override

**One override point — the estimate line. The plan holds no quantity at all.**

**Canonical flow**: `Surface geometry → suggested/source quantity → EstimateLine.source_quantity →
EstimateLine.quantity`.

- **`source_quantity` at generation** (quantity_source = `SURFACE_NET_AREA`): for **M2** works, the
  surface's **net area** (wall: gross − opening deduction; floor/ceiling: plane totals incl. composite
  segments and opening deductions) — using the already-persisted
  `Surface.gross_area / deduction_area / net_area` numbers.
- **Manual** (quantity_source = `MANUAL`): for **LM / PCS / HOUR / DAY / FLAT**, for any surface whose
  geometry is incomplete, and for all `PRICE_BOOK` / `MANUAL` lines — the owner enters `quantity`
  (`Podaj ilość` blocks generation otherwise).
- **`EstimateLine.quantity`** defaults to `source_quantity` at generation and is independently editable
  inside a DRAFT — this is the single quantity-override layer. `quantity_overridden = true` marks an
  owner-set quantity so regeneration preserves it (§13, §20). There is **no plan-level quantity override**
  and no second override layer.
- Quantities are `Numeric(10, 3)` reusing the Stage 5 area precision (`Decimal("0.001")`).

---

## 13. Price override

- An estimate line may carry **`unit_price` different from the book** without touching the Price Book:
  `price_override = true` on the line. The override amount is part of the snapshot.
- Overrides are applied inside the Estimate editor ("Cena własna"), editable while the document is DRAFT,
  locked once FINAL. **Regeneration of a DRAFT preserves owner overrides** — they are never silently
  reset; the regeneration preview shows which lines would take a new book price and which keep an
  override, and the owner confirms (§20).
- **Rule of precedence for the client number**: line `unit_price` (override if set, else the snapshot of
  the book price); NULL book price → NULL line price → "Do ustalenia" and a FINAL block (§11/D11).

---

## 14. NULL owner price (Do ustalenia)

- If the referenced `PriceItem.price` is `NULL` at line-creation (owner commercial price not set yet),
  the generated line is created with **`unit_price = NULL`** — the line displays `Do ustalenia`
  (PL) / `Уточняется` (RU) and its `amount` is NULL.
- Such a line **counts in the line list but not in any subtotal**, and the Estimate **cannot transition to
  FINAL/ACCEPTED** while any line has a NULL unit price (blocked with a clear `Ceny nieustalone: N pozycji`
  message). DRAFT is the only permitted state for unpriced lines.
- The owner resolves it by: (a) setting the price in the Price Book and re-generating (DRAFT refresh,
  §20), or (b) setting a line-level override (D13). A MANUAL line's `unit_price` is owner-entered
  directly; if left NULL it is equally unpriced and equally blocks FINAL. **Market evidence
  (min/max/reference prices) is never auto-substituted** into a NULL price — `PriceItem.price` remains
  the only authoritative quoting number (Stage 9E contract). No price is ever invented.
- `0.00` remains a real, explicitly set zero price (Stage 9E.7 semantics): a `0.00` book price produces a
  priced line of 0.

---

## 15. Labor / materials — the normal estimate model

Owner decision (10A.1): **ROBOCIZNA and MATERIAŁY are the normal Stage 10 estimate presentation.**

- The estimate footer reports: `Robocizna` subtotal · `Materiały` subtotal · *(exception)* `Mieszane` ·
  `Razem` total.
- Every line carries `scope` = the PriceItem's `PriceScope` (`LABOR / MATERIAL / LABOR_AND_MATERIAL`),
  snapshotted at creation. Classification comes from the book row — never derived from category name.
- **Manual estimate lines are `LABOR` or `MATERIAL`** (never mixed).
- **Surface work planning prefers atomic `LABOR` work items** where the catalog provides them; material
  rows are planned/estimated as separate lines.
- **`LABOR_AND_MATERIAL` is an exception/compatibility path**, not the preferred model for new estimate
  data. Existing catalog rows remain supported (Stage 9 `PriceScope` is not altered by Stage 10A); they
  are grouped in the explicit `Mieszane` bucket so that the LABOR and MATERIAL subtotals never count the
  mixed row twice and never silently guess a split (D15).

---

## 16. Materials MVP boundary

- Stage 10 supports **materials exactly like labor**: a material is a `PriceItem` with
  `price_scope = MATERIAL` (or a combined `LABOR_AND_MATERIAL` row), referenced by a planned work or added
  as a `PRICE_BOOK` line with an M2/manual quantity, priced from the book. If the owner maintains material
  rows for *gładź gipsowa*, *włóknina szklana*, *farba*, the estimate shows them as `Materiały` totals.
- **NOT in Stage 10** (deferred): an automatic bill-of-materials / take-off engine that turns
  *"gładź o grubości 1 mm"* into kg of powder, meters of tape, etc. Stage 10 consumes book rows
  wholesale; material *quantification per component* is a Stage 12+ concern.
- `PriceItem` already has a `MATERIAL` category and `PriceScope.MATERIAL`; no new material model is built.

---

## 17. Totals, Decimal, rounding

- **Money is `Decimal` end-to-end**; Pydantic serializes monetary JSON as strings (never floats).
- Per-line `amount = quantize(quantity × unit_price, 0.01, ROUND_HALF_UP)`, computed at line write.
- **Estimate total = Σ of quantized line amounts** (`Numeric(14, 2)`), computed by a domain
  `recalculate_totals` service on every line mutation — the total is always the exact sum of the line
  amounts (invariant covered by tests in 10D). No second rounding of the sum.
- **No unsupported unit conversions**: quantity and price are combined only within the same `PriceUnit`;
  no LM↔M2, PCS↔M2 or cross-unit arithmetic is ever performed or inferred (a mismatch is a validation
  error, never a guess).
- `Numeric` widths in the migration: quantity `Numeric(10,3)`, prices `Numeric(12,2)`, amounts
  `Numeric(14,2)`.
- Currency PLN only, `String(3)` (no currency enum — matches `PriceItem`).

---

## 18. Discounts / VAT / coefficients — deferred

- **No VAT** (the owner quotes net), **no discounts/revisions**, **no difficulty/height/urgency/
  logistics coefficients** — these are Stage 12 (price coefficients) and Stage 16 (contract value with
  VAT) concerns. Stage 10 computes a clean net line-item total from the Price Book and the measured
  scope.

---

## 19. Mobile UX screen map (current Stage 10C execution; original 10E/10F/10G context)

1. **Room card → "Plan prac"** — enters the plan screen; creates one `SurfaceWorkPlan` per surface on
   first touch.
2. **Plan screen** — a collapsible list of surfaces (Ściana 1–4, Podłoga, Sufit); **each surface expands
   to its own plan**: substrate + quality picker (pre-filled from that surface's completed inspections,
   validated with `assert_quality_scale_valid`) and the ordered work chips. Chips show the book display
   name, unit, and current price state (`12,00 zł / m²` or `Do ustalenia`).
3. **"Dodaj pracę"** — Price Book picker (bottom sheet): search + filter by category/unit, shows the
   book price state; selecting appends a `SurfacePlannedWork`. Archived items are excluded.
4. **Work chip actions** — reorder (↑/↓ ≥44 px), remove (with undo or confirm). Quantities are not entered
   here — they belong to the estimate line (§12).
5. **„Zapisz dla wszystkich ścian” / „Сохранить для всех стен”** — Stage 10C.3 WALL-only apply-to-all with explicit overwrite confirmation (§6).
6. **"Wygeneruj kosztorys"** — creates the next `Estimate` version as DRAFT and opens the estimate
   editor.
7. **Estimate editor** — lines grouped by surface in order; per-line controls: quantity (overridable,
   `quantity_overridden`), price override, remove; "Dodaj pozycję ręcznie" (freeform manual line); live
   footer subtotals (§15) with `Do ustalenia` counters.
8. **Status flow** — "Zatwierdź kosztorys" validates no NULL prices → FINAL (locked). Regeneration
   refreshes the DRAFT in place (preview/confirmation); a new version is created only for a meaningful
   commercial revision of an immutable document; the version list is reachable from the estimate screen.

Every string is a PL/RU locale key; no numeric constants in components; 390/412 px and 320 px regression
checks are part of every current frontend sub-stage. The original 10E/10F/10G grouping is historical;
apply-to-all ownership is now exclusively Stage 10C.3.

---

## 20. Sync model (WorkPlan → Estimate) — versioning & regeneration

**One-way, explicit, confirmed — no silent mutation, no background sync.**

- `Wygeneruj kosztorys`:
  1. validates the plans (every row has an active item, computable or owner-provided quantity),
  2. creates / refreshes the estimate document, materializing one `PLANNED_WORK` line per planned work
     (snapshot per §11),
  3. computes totals (§17).
- **No new version per click.** Versioning policy (D8):
  - No DRAFT estimate exists for the project → create **DRAFT v1**.
  - A **DRAFT** already exists → regenerate **that same DRAFT in place** (confirmed preview below). No
    version bump.
  - The latest document is **FINAL / ACCEPTED / ARCHIVED** and commercial changes are needed → create a
    **new DRAFT** `version = max + 1`, either regenerated from the current plans or derived from the
    frozen document.
- **DRAFT regeneration semantics (exact):**
  1. `PLANNED_WORK` lines are re-derived from the current plans, matched by `planned_work_id`.
  2. **Manual lines are never touched** — not removed, not re-derived, not re-priced, never deleted.
  3. A kept line's book snapshot (description / unit / scope / base unit price) is refreshed from the
     book; **owner overrides are preserved** — `quantity_overridden` keeps the owner's quantity,
     `price_override` keeps the owner's price.
  4. Retained `PLANNED_WORK` lines follow the **current `SurfacePlannedWork` ordering** after
     regeneration (surfaces by `Surface.position`, then works by `SurfacePlannedWork.position`) — the
     source planned-work order is **authoritative**. Exact manual-line interleaving / UI positioning is
     an implementation detail that may be done conservatively later.
  5. New planned works → new lines; planned works no longer planned → lines proposed for **removal**;
     a reorder is a re-position preserved across regeneration.
  6. Every add / update / remove / reorder is shown in a **preview** with counts; the owner confirms or
     cancels. Nothing is applied silently or in the background.
- Editing a **DRAFT** estimate (manual lines, overrides, quantity edits) lives on that estimate only and
  never writes back to the plans.
- There is no background job, no auto-sync, no cache.

---

## 21. Stage 11 boundary

- Stage 11 = **Inspection → recommended work → add to estimate**: deterministic mapping from
  `InspectionFinding.finding_key` to a recommended `PriceItem` (by its stable `code`), producing
  recommended plan rows / estimate lines for the owner to accept.
- Stage 10 must not build any mapping table or recommendation service. Stage 10's contribution to
  Stage 11 readiness is already in place: **`PriceItem.code` is immutable** (Stage 9), `InspectionFinding.
  finding_key` exists (Stage 6), and `SurfacePlannedWork` is an append-only list — Stage 11 simply adds
  rows to a plan (or lines to an estimate) via the same APIs.
- No `origin=INSPECTION_MAPPED` column is added now; Stage 11 can store its own traceability at creation.

---

## 22. Stage 14 photo boundary

- Stage 14 photos attach to Project / Room / Surface (and later to defect annotations). Estimates and work
  plan rows **do not own photos** and carry no photo references in Stage 10 — a client-facing estimate
  cites line items, not photo evidence.
- The floor/ceiling/wall surfaces already anchor photos (via `room_id`/`surface_id`); the estimate's
  `surface_id` provenance on generated lines is enough for any future "photos of this line's surface"
  joined view. Nothing more is modeled now.

---

## 23. Execution plan 10A → 10I

| Sub-stage | Deliverable | Gate |
|---|---|---|
| **10A** (this) | Surface Work Planning + Estimate architecture decision record; `development-progress.md` minimal update | Owner acceptance of the 18 decisions before any code |
| **10B** | Backend domain: SQLAlchemy models (`surface_work_plans`, `surface_planned_works`, `estimates`, `estimate_lines`), enums, reversible Alembic migrations, domain services (per-surface plan CRUD with `assert_quality_scale_valid` reuse, generation with snapshots, `recalculate_totals`, version sequencing, DRAFT regeneration preview, null-price FINAL block); unit tests | `pytest` unit PASS; no API yet |
| **10C** | Public owner-scoped API: FastAPI routers (plans, works, estimates, generate, finalize), Pydantic v2 schemas, ownership filtering, integration tests | `pytest` integration PASS (mock-auth pattern from Stage 9) |
| **10D** | Estimate engine hardening: snapshot immutability tests (book edit after line creation → line unchanged), totals invariant, version sequencing, DRAFT regeneration preview (manual lines + overrides preserved), manual lines, price override semantics | `pytest` snapshot/regression suite PASS |
| **10E** | Mobile UI — work planning (plan screen, surface lists, work picker, reorder, substrate/quality picker, PL/RU) | `vitest` + `tsc` + `vite build` PASS; 390/412 px manual |
| **10F** | Mobile UI — estimate (generate, line editor, freeform manual add, subtotal footer, status flow, PL/RU) | `vitest` + `tsc` + `vite build` PASS; 390/412 px manual |
| **10G** (historical placeholder; superseded) | No longer owns apply-to-all-walls UX; the current execution assignment is **Stage 10C.3** | No separate apply-to-all execution under 10G |
| **10H** | Final manual acceptance — full walkthrough as owner (per §26) on 390/412 px and in Telegram; owner sign-off | Owner acceptance |
| **10I** | Final gate — full backend `pytest` + frontend `vitest` + `tsc --noEmit` + `vite build`, `git diff --check`, `docs/development-progress.md` update, one logical commit, push to `origin/stage-10` | Clean tree; Stage 10 CLOSED |

The table above preserves the original 10A architecture phasing. The **current owner-approved Stage 10C
execution order** is authoritative:

1. **10C.2A — Editor Shell + Existing Plan Loading** — implemented; awaiting owner verification.
2. **10C.2B** — next.
3. **10C.2C** — next.
4. **10C.2D** — retained in the current breakdown and follows 10C.2C.
5. **10C.3 — Apply Work Plan to All Walls** — implements the WALL-only **„Zapisz dla wszystkich ścian” /
   „Сохранить для всех стен”** action through the existing `apply-to-room-walls` endpoint.

After completion of **Stage 10C**, execution returns to **Stage 5F — Opening Reveals / Ościeża**. Stage
5F is not moved into or ahead of Stage 10C.

Sub-stages require explicit owner approval; no later sub-stage starts automatically.

---

## 24. The 18 required architecture decisions (D1–D18)

### D1 — `SurfaceWorkPlan` / `SurfacePlannedWork` entities

**Decision**: two tables; **one `SurfaceWorkPlan` per physical surface**, per §3.

`surface_work_plans`: `id` (uuid pk) · `surface_id` (FK surfaces, **UNIQUE not null**, idx) · `substrate`
(enum `substrate`, not null) · `quality_target` (enum `qualitylevel`, nullable) · `created_at` /
`updated_at` (timestamptz).

`surface_planned_works`: `id` (uuid pk) · `work_plan_id` (FK surface_work_plans, not null, ondelete
CASCADE, idx) · `price_item_id` (FK price_items, not null) · `position` (int, not null) · `created_at` /
`updated_at`. Unique `(work_plan_id, position)`.

**Rationale**: the plan is a per-surface configuration (a 1:0..1 child of `Surface`). The surface is the
identity, so no `name` / `status` / `owner_id` / `project_id` are duplicated on the plan (owner /
project / room are reached via `Surface → Room → Project → User`; these are sub-entities, not tenancy
roots). A work row is meaningless without its plan and a book row, so both FKs are NOT NULL; `surface_id`
is **not** repeated on `SurfacePlannedWork` (it is inherited from the plan). `quantity_override` is
removed from the plan entirely (§12).

### D2 — Relationship to `Surface`

**Decision**: `surface_id` **UNIQUE NOT NULL** on `SurfaceWorkPlan` — exactly one plan per physical
surface; one model serves WALL / FLOOR / CEILING (and OTHER, with manual quantity). Every planned work
inherits its target surface from its plan. Geometry/opening/net-area computations are not duplicated into
the plan — quantity is derived from the surface's persisted areas at generation (§12).

**Consequence**: apply-to-all is modeled as *copying one wall's plan configuration into the other walls'
plans* (D6), not as a `NULL = any wall` pseudo-row. The four-wall example is native — `Wall 1
GYPSUM_PLASTER/S3` · `Wall 2 GYPSUM_PLASTER/S3` · `Wall 3 CONCRETE/S3` · `Wall 4 GYPSUM_BOARD/Q3`.
Non-surface scope belongs to manual estimate lines.

### D3 — Relationship to `PriceItem`

**Decision**: `price_item_id` NOT NULL FK; the plan stores **the reference only — no price copy**. The
price state is read from the book at generation. `PriceItem.price = NULL` is valid in the plan and
produces an unpriced line (D11). Archived items are excluded from the picker and from generation; existing
rows and lines are never mutated by archiving.

**Rationale**: preserves "no hardcoded prices" (Stage 9D/GB rule) and Stage 9E.1 snapshot semantics;
keeps the plan as pure scope so it remains cheap to revise. **Planning prefers atomic `LABOR` work items
where the catalog provides them; material rows are planned as separate lines** (D14/D15).

### D4 — Work ordering

**Decision**: an integer **`position`** unique within a `SurfaceWorkPlan`, appended on insert, beginning
at 0. Mirrors the existing `position` ordering precedent on `Surface`, `AreaSegment`, and
`ChecklistSection`. Estimate generation orders surfaces by `Surface.position`, then works by
`SurfacePlannedWork.position`; a reorder is a re-position of integers (10E).

### D5 — Substrate / quality ownership + Stage 6 enum reuse

**Decision**: substrate (NOT NULL) and `quality_target` (nullable) live on the **per-surface
`SurfaceWorkPlan`**; reuses the exact Stage 6 `Substrate` / `QualityLevel` enums and
`assert_quality_scale_valid`. Each physical surface has its own commercial substrate/quality — `Wall 1
gipsowa S3`, `Wall 3 beton S3`, `Wall 4 GK Q3` — natively, no second plan needed. Completed Inspections
only **pre-fill** in the UI and are never written to.

**Field naming (final)**: `quality_target` (NOT `target_quality`), aligned verbatim with Stage 6
`Inspection.quality_target`.

**Owner-visible reading**: substrate+quality select the appropriate works; they are **never** a numeric
coefficient — coefficients are Stage 12.

### D6 — Apply-to-all overwrite semantics

**Decision**: Stage 10C.3's WALL-only **„Zapisz dla wszystkich ścian” / „Сохранить для всех стен”**
action uses the selected active WALL as source and **copies / replaces only its planning configuration** —
`substrate`, `quality_target`, and the ordered `SurfacePlannedWork` rows — in every other ACTIVE WALL in
the same Room (creating a plan if absent, replacing its contents if present). The implementation uses
`POST .../surfaces/{source_surface_id}/work-plan/apply-to-room-walls` and requires explicit overwrite
confirmation when targets already have plan rows (count shown; destructive to those plan rows only, never
silent). It never copies or changes physical `Surface` identity, dimensions, geometry, openings,
deductions, AreaSegments, inspections, inspection answers, findings, risks, communication, photos /
defects, archive state, Estimate data, or Price Book data. After the copy, each wall's plan is independent.

### D7 — `Estimate` / `EstimateLine` entities

**Decision**: two tables.

`estimates`: `id` (uuid pk) · `owner_id` (FK users, not null) · `project_id` (FK projects, not null, idx) ·
`version` (int, not null) · `name` (varchar 120, nullable) · `status` (enum `estimatestatus`, default
DRAFT) · `total` (Numeric(14,2), nullable) · `currency` (String(3), default PLN) · `created_at` /
`updated_at`. Unique `(project_id, version)`. Index `(owner_id, status)`.

`estimate_lines`: `id` (uuid pk) · `estimate_id` (FK, not null, ondelete CASCADE, idx) · `origin` (enum
`lineorigin`: `PLANNED_WORK / PRICE_BOOK / MANUAL`) · `position` (int) · provenance refs `plan_id` /
`planned_work_id` / `surface_id` / `room_id` (all nullable; populated for `PLANNED_WORK`) ·
`price_item_id` (FK price_items, **nullable — NULL only for `MANUAL`**) · snapshot: `item_code` (varchar
120, nullable), `description` (varchar 255), `unit` (enum `priceunit`), `scope` (enum `pricescope`;
`MANUAL` restricted to `LABOR` / `MATERIAL`), `currency` (String(3)) · quantity: `source_quantity`
(Numeric(10,3), nullable), `quantity` (Numeric(10,3)), `quantity_source` (enum `quantitysource`),
`quantity_overridden` (bool, default false) · price: `unit_price` (Numeric(12,2), nullable),
`price_override` (bool, default false) · `amount` (Numeric(14,2), nullable) · `created_at` /
`updated_at`. Index `(estimate_id)`, `(surface_id)`.

### D8 — Version / status strategy

**Decision**: statuses `DRAFT → FINAL → ACCEPTED | ARCHIVED`. Version is an **int sequence per project**
(UNIQUE `(project_id, version)`). **A version is a meaningful commercial revision — not every button
press.** `Wygeneruj kosztorys` creates DRAFT v1 when none exists; regenerating an existing DRAFT refreshes
**the same DRAFT in place** (confirmed preview, §20) without bumping the version. A **new version** is
created only when the latest document is immutable (FINAL / ACCEPTED / ARCHIVED) and commercial changes
are needed — as a new DRAFT derived from it or regenerated explicitly. DRAFT is the only editable state
(manual lines, overrides, quantity edits; ARCHIVED = soft delete). `FINAL` locks every line; `ACCEPTED`
marks client acceptance (Stage 16 owns contracts, not the ACCEPTED stamp itself). No in-place mutation of
non-DRAFT documents; no revision table — history *is* the version list.

**Owner decision recorded**: regeneration is an in-place DRAFT refresh with explicit preview/confirmation,
so manual lines and owner overrides are never silently destroyed. New versions are reserved for meaningful
commercial revisions of immutable documents.

### D9 — Snapshot fields

**Decision**: the §11 table verbatim — `item_code` (nullable), `description` (resolved at creation, or
owner-entered for MANUAL), `unit`, `scope`, `currency`, `unit_price`, `price_override`, `source_quantity`,
`quantity`, `quantity_source`, `quantity_overridden`, `amount`. Provenance refs (`price_item_id`,
`plan_id`, `planned_work_id`, `surface_id`, `room_id`) are stored for traceability but are never re-read
to recompute the line. Snapshot immutability is enforced for FINAL/ACCEPTED and tested (10D).

### D10 — Manual-line strategy

**Decision**: manual lines are EstimateEditor-only rows with `origin = MANUAL`; **`price_item_id` may be
NULL** — the line carries its own `description`, `scope` (`LABOR` / `MATERIAL` only), `unit`, `quantity`,
`unit_price`, and `currency`. Manual lines **never create or modify PriceItems** and never appear in a
plan. Catalog-based lines that are not planned use `origin = PRICE_BOOK` (a `PriceItem` reference + book
snapshot, manual quantity); the freeform lump-sum manual line needs no book row at all.

### D11 — NULL owner price behaviour

**Decision**: NULL price → line `unit_price = NULL`, `amount = NULL`, rendered `Do ustalenia` /
`Уточняется`, excluded from subtotals and total. The document stays DRAFT and **cannot reach FINAL/ACCEPTED
while any line is unpriced** (blocked with a count). Resolved via book price + regeneration or a
line-level override (a MANUAL line's `unit_price` is owner-entered directly; if left NULL it is equally
unpriced). **Market evidence is never substituted**; the Price Book's `PriceItem.price` is the only
quoting authority; `0.00` remains a real zero.

### D12 — Quantity source + override

**Decision**: quantity_source ∈ {`SURFACE_NET_AREA`, `MANUAL`}. M2 planned works default `source_quantity`
to the surface's **net area** from persisted geometry; LM/PCS/HOUR/DAY/FLAT, incomplete-geometry surfaces,
and all `PRICE_BOOK` / `MANUAL` lines default to `MANUAL` and block generation until a quantity is entered.
`EstimateLine.quantity` defaults to `source_quantity` and is the **single override layer**, editable in a
DRAFT; `quantity_overridden` marks an owner-set value so regeneration preserves it. The plan carries **no
quantity and no quantity override**. Quantities `Numeric(10,3)` (Stage 5 area precision).

### D13 — Price override

**Decision**: line-level `unit_price` + `price_override=true` (owner-set, inside the Estimate editor), part
of the snapshot, editable only in DRAFT, locked in FINAL/ACCEPTED. **Regeneration of a DRAFT preserves
owner overrides** (never silently reset); the preview shows which lines would take a new book price.
Overrides never write back to the Price Book.

### D14 — Labor/material classification

**Decision**: **ROBOCIZNA and MATERIAŁY are the normal Stage 10 estimate presentation.** Classification is
a snapshot of the book row's `PriceScope` (`LABOR / MATERIAL / LABOR_AND_MATERIAL`) on every line — never
derived from category names. Footer: `Robocizna` subtotal · `Materiały` subtotal · *(exception)*
`Mieszane` · `Razem` total. Manual lines are `LABOR` or `MATERIAL`; planning prefers atomic `LABOR` items
where the catalog provides them, with material rows as separate lines.

### D15 — `LABOR_AND_MATERIAL` behaviour

**Decision**: a mixed row is an **exception/compatibility path** (existing Stage 9 catalog rows remain
supported; Stage 9 `PriceScope` is not altered by Stage 10A) — **not** the preferred model for new
estimate data. A mixed row is **one line** at the combined unit price; it is grouped in its own `Mieszane`
bucket and contributes its full amount to the total. **It is never split** into invented labor/material
lines (the book stores no ratio to split by). Owners who need the split should maintain separate LABOR and
MATERIAL rows in the book (noted as an owner option).

### D16 — Totals / Decimal / rounding

**Decision**: `Decimal` end-to-end, JSON as strings; per-line `amount = quantize(qty × price, 0.01,
ROUND_HALF_UP)` at write time; **total = Σ quantized line amounts** recomputed by a domain
`recalculate_totals` service on every line mutation (never re-rounded). **No unsupported unit
conversions**: quantity and price are combined only within the same `PriceUnit`; cross-unit arithmetic is
a validation error, never a guess. `Numeric` widths: qty 10,3 · price 12,2 · amount 14,2 · total 14,2.
PLN, `String(3)`. Totals invariant is tested in 10D.

### D17 — WorkPlan → Estimate sync

**Decision**: one-way, explicit, confirmed — `Wygeneruj kosztorys` validates, creates DRAFT v1 (or
refreshes the existing DRAFT after preview/confirmation, or derives a new DRAFT version from an immutable
document), materializes snapshotted lines, computes totals; **no background sync, no silent mutation, no
per-click version**. Plan edits after generation do not touch existing documents. DRAFT-only estimate
edits never write back to the plans.

### D18 — Stage 11 boundary

**Decision**: Stage 11 owns the mapping (`InspectionFinding.finding_key → recommended `PriceItem` code` →
add rows/lines). Stage 10 builds **no** mapping table or recommendation service. Readiness already
satisfied: `PriceItem.code` immutable, `finding_key` present, plan = appendable row list, estimate lines
referenceable. No new column is reserved for Stage 11 in this stage.

---

## 25. Documentation requirements (where this stage lands)

| File | Action |
|---|---|
| `docs/stage-10-architecture.md` | **created** — this record (10A.1 canonical corrections applied 2026-09-15) |
| `docs/development-progress.md` | **minimally updated** — Stage 10 roadmap row status → "In Progress — 10A Completed 2026-09-15 (docs-only, uncommitted); 10A.1 Canonical Architecture Corrections applied 2026-09-15 (docs-only, uncommitted)"; one Stage Log entry appended |

No source code, no migrations, no tests, no build artifacts are changed by 10A / 10A.1.

---

## 25A. 10C.1A — Canonical Floor/Ceiling Surfaces (implementation record)

- **Date**: 2026-09-16
- **Branch / HEAD**: `stage-10` (uncommitted working tree; awaiting owner acceptance)
- **Reason**: discovered during 10C.1 acceptance — WALLs are real `Surface` rows, but FLOOR/CEILING
  measurement data lived only in room-scoped `AreaSegment` rows; the canonical room workflow created no
  FLOOR/CEILING `Surface` rows, so Stage 10B `SurfaceWorkPlan` had no stable `Surface.id` for floor or
  ceiling. 10C.1A adopts canonical physical `Surface` entities for FLOOR and CEILING.

### Scope (canonical invariant)

- **Every Room**: exactly one active canonical **FLOOR** `Surface` and exactly one active canonical
  **CEILING** `Surface`; zero+ WALL surfaces. Real rows in `surfaces` with stable UUID `Surface.id`. No fake
  frontend IDs, no `PlaneSurface` mapping model. WALL behaviour is unchanged.
- Canonical plane names are language-neutral tokens following the "Wall N" convention: **`Floor`** /
  **`Ceiling`**, positions **100** / **101** (kept out of the wall 0..N range).
- **Uniqueness**: the DB invariant is the smallest one that preserves archive/restore — a partial unique
  index `uq_surfaces_active_plane_per_room (room_id, surface_type)` filtered to active
  (`is_archived = false`) FLOOR/CEILING rows. Archived plane rows may therefore exist (restore/archive keep
  working); the domain service rejects creating a second active plane, retyping onto a plane type, archiving
  a canonical plane, or restoring a plane that would collide with an active one — all 409
  `CanonicalPlaneConflictError`.
- **Ambiguity handling**: if a room already has **more than one active** same-plane FLOOR/CEILING surface,
  the system never merges or deletes user rows — provisioning and migration 0018 **abort and report the
  room** (`CanonicalPlaneConflictError` / migration `RuntimeError`) for manual reconciliation.

### Provisioning

- `app/domain/services/canonical_planes.py` — `ensure_canonical_plane_surfaces(db, room_id)` is idempotent:
  **reuse** the single active plane surface if one exists, otherwise **create** it. `room_service.create_room`
  provisions FLOOR+CEILING automatically; `surface_service` guards plane-type create/update/archive/restore.
- Room dimension changes do **not** replace canonical identities — plane `Surface.id` is stable across room
  updates. `generate_walls` is untouched and never creates/removes plane rows.

### Backfill (Alembic migration 0018)

- `0018_canonical_plane_surfaces` (revision `0018_canonical_plane_surfaces`, down_revision
  `0017_create_surface_work_plans`). Staged, transactional, reversible:
  1. provision/reuse canonical Floor/Ceiling per room (aborts with an explicit message on duplicate active
     planes — never merges user rows),
  2. add nullable `area_segments.surface_id`,
  3. backfill **every** existing `AreaSegment` to exactly one canonical surface (aborts if a segment resolves
     to nothing),
  4. add FK `fk_area_segments_surface_id (surface_id → surfaces.id, ON DELETE CASCADE)` + index
     `ix_area_segments_surface_id`, set NOT NULL (safe: every row backfilled),
  5. add the partial unique index `uq_surfaces_active_plane_per_room`.
- Downgrade removes only rows carrying the canonical signature (type + `Floor`/`Ceiling` name + position
  100/101, active); reused user rows are preserved. Verified against real PostgreSQL:
  `0017 → 0018 → 0017 → 0018` plus the duplicate-plane abort path (transaction fully rolled back).

### Area segment association

- `AreaSegment.surface_id → surfaces.id` FK; `room_id` retained. Both columns are kept and the domain
  service (`area_segment_service._resolve_plane_surface`) validates they agree. Backfill + service rejects,
  with `AreaSegmentSurfaceMismatchError` (409): segment→surface from another room, WALL targets, plane/type
  mismatches (FLOOR segment → CEILING surface), and unverifiable `surface_id` (never trusted from the
  client without validation).

### API compatibility & calculations

- Backend resolves canonical planes from `room_id + plane` when `surface_id` is omitted; responses expose
  `surface_id`. Existing measurement clients keep working (schema adds an optional field). Ceiling/floor net
  area math (BASE + ADD − SUBTRACT segments, openings subtracted on walls) is numerically identical before
  and after. `SurfaceWorkPlan` GET/PUT on `.../surfaces/{floor_surface_id}/work-plan` and the ceiling
  counterpart work on the canonical plane IDs; no `FloorWorkPlan`/`CeilingWorkPlan` models; the WorkPlan
  schema is unchanged.

### Verification (all green 2026-09-16)

- Backend suite: **618 passed** (incl. new `tests/test_canonical_planes.py` — 23-tests A–X matrix + lifecycle
  guards, and updated `test_surfaces`, `test_openings`, `test_inspections`, `test_wall_generation`).
- Alembic migration cycle on **real PostgreSQL**: `0017 → 0018` (provision/reuse, backfill, NOT NULL, FK,
  unique index), `0018 → 0017` (user rows preserved, canonical rows removed, column dropped),
  `0017 → 0018` (no duplicates, reused rows keep stable IDs), duplicate-active-plane room → abort + rollback.
- Frontend: 340 passed, `tsc --noEmit` clean, `vite build` clean, `git diff --check` clean.

**Status**: 10C.1A — Canonical Floor/Ceiling Surfaces **IMPLEMENTED — awaiting owner acceptance**.
STOP — no commit, no push, no deploy, no 10C.1B / 10C.2.

---

## 26. Acceptance scenario (used by 10B → 10H, and the owner's 10H walkthrough)

**Setup**: project "Mieszkanie Kraków" → room "Salon" → walls measured (room 6/4/3, window + door
openings) → WALL/FLOOR/CEILING surfaces with persisted net areas → completed inspections (gipsowa, beton,
GK) exist.

1. Owner opens Room "Salon" → "Plan prac". Surface list: Ściana 1–4, Podłoga, Sufit — **each surface a
   distinct `SurfaceWorkPlan`**. Wall 1 pre-fills substrate **gipsowa**, quality **S3** from its
   inspection (`assert_quality_scale_valid(gipsowa, S3)` passes).
2. On Wall 1, adds works *Gładź szpachlowa* (M2, LABOR), *Włóknina szklana* (M2, LABOR), *Malowanie* (M2,
   LABOR); reorders them; taps **"Zapisz dla wszystkich ścian"** → confirmation shows "skopiuj plan prac
   na 3 ściany" → confirm → Walls 2–4 carry the same substrate/quality/works as their own plans.
3. Wall 3 substrate is corrected to **beton / S3**; Wall 4 to **GK / Q3** (their own plans change
   independently). Floor: adds *Mikrocement* (M2) on Podłoga. The four-wall example — gipsowa/S3,
   gipsowa/S3, beton/S3, GK/Q3 — is now native.
4. Taps "Wygeneruj kosztorys" → Estimate DRAFT v1 with generated `PLANNED_WORK` lines; wall lines show
   their net-area m² as `source_quantity` (quantity defaults to it), the floor line shows its plane net
   area; a line whose book price is NULL renders `Do ustalenia`, excluded from the subtotals; footer shows
   Robocizna / Materiały / (Mieszane) / Razem.
5. Owner sets that price in the Price Book, re-generates → the DRAFT is refreshed **in place** (preview
   confirms the change, no new version); the NULL resolves.
6. Owner adds one freeform **manual line** (*Dodatkowy dojazd*, 1 FLAT × 350 PLN — no book row) and
   overrides one generated line's price → subtotals recompute; the manual line and the overrides survive
   any later regeneration.
7. "Zatwierdź kosztorys" → FINAL (validation would block if any NULL price remained). Back in the Price
   Book, owner edits a price 20% up and refreshes market evidence → **v1 FINAL numbers unchanged**
   (snapshot). Commercial change to the FINAL → owner derives a new DRAFT version (v2).
8. Mobile regression at 320 / 390 / 412 px: no horizontal scroll, wrapping PL/RU labels, ≥44 px targets,
   decimal keypads, back navigation intact.

**10A acceptance criteria (this sub-stage)**: this record exists, resolves D1–D18 with a single,
non-ambiguous decision each, and is internally consistent after the 10A.1 corrections (no contradictory
passages); `development-progress.md` updated minimally; `git diff` shows **docs only**; working tree
otherwise clean. STOP — no commit, no push, no 10B without owner approval.

---

## Appendix A — Owner decisions to confirm (judgment calls resolved here)

1. **Substrate + quality are per physical surface** — each wall/floor/ceiling has its own
   `SurfaceWorkPlan`, so different walls may carry different substrate/quality (Wall 1 gipsowa S3,
   Wall 3 beton S3, Wall 4 GK Q3). (D5)
2. **`LABOR_AND_MATERIAL` rows are never split** and are an exception/compatibility bucket; owners that
   need a split maintain separate LABOR and MATERIAL rows in the book. (D15)
3. **Regeneration refreshes the existing DRAFT in place** (confirmed preview); a **new version** is
   created only for a meaningful commercial revision of an immutable (FINAL / ACCEPTED) document. (D8/D17)
4. **Manual estimate lines are freeform** — no `PriceItem` required (`price_item_id = NULL`); they never
   create or modify book rows. Catalog pickups that are not planned use `origin = PRICE_BOOK`. (D10)
5. **Quality tier selects works; it is not a numeric coefficient.** (D5 — coefficients are Stage 12)
6. **`LineOrigin` naming is final**: `PLANNED_WORK` / `PRICE_BOOK` / `MANUAL`. (D7 / §10)
7. **`quality_target` field naming is final** — aligned with Stage 6 `Inspection.quality_target`. (D5)
8. **DRAFT regeneration ordering**: retained `PLANNED_WORK` lines follow the current `SurfacePlannedWork`
   order (planes by `Surface.position`, then works by position); manual lines are never deleted. (D8/D17 / §20)
9. **Apply-to-all is final**: Stage 10C.3 exposes **„Zapisz dla wszystkich ścian” / „Сохранить для всех
   стен”** only for WALL. The selected active WALL is the source; every other ACTIVE WALL in the same Room
   receives replacement `substrate`, `quality_target`, and ordered planned works. It never changes Surface
   identity, dimensions, geometry, openings, deductions, AreaSegments, inspections, inspection answers,
   findings, risks, communication, photos/defects, archive state, or Estimate data. (D6 / §6)

## Appendix B — Reused contracts (unchanged by 10A)

`Project`/`Room`/`Surface`(+`net/deduction/gross` areas) · `Opening` (width/height/quantity) ·
`AreaSegment` (plane ADD/SUBTRACT composite totals) · `Inspection` (substrate, quality_target, status,
pre-fill source) · `PriceItem` (code immutable, price nullable-at-will, price_scope, unit, currency) ·
`Substrate` / `QualityLevel` / `PriceUnit` / `PriceScope` enums · `assert_quality_scale_valid` ·
`room_geometry` AREA_PRECISION `Decimal("0.001")`. No existing table or enum is altered by Stage 10A.