# Stage 13 — Technological Workflows: Audit & Architecture (13A)

- **Date**: 2026-09-25
- **Branch / HEAD**: `stage-13` @ `fb4eb9a` (= `main`; Stage 12 COMPLETE / OWNER ACCEPTED, production release `d60390b`, DB head `0026_coefficient_descriptions`)
- **Sub-stage**: 13A — **architecture/audit only**. No code, no migration, no API change.
- **Status**: **13A COMPLETE — owner decisions D1–D13 approved** (§A). Stage 13 itself is not complete; 13B starts only on explicit owner approval.

---

## A. Owner decisions (recorded)

| # | Decision | Effect on this architecture |
|---|---|---|
| D1 | **APPROVED** — a step references `PriceItem` directly; atomic and bundled items allowed; no separate technological-operation catalog in v1 | `PriceItem` stays the billable operation; the step adds order + technological context (§8) |
| D2 | **APPROVED** — apply modes **APPEND** (default) and **REPLACE**; REPLACE needs explicit confirmation | REPLACE removes existing occurrences **and their Stage 12 coefficient assignments**; never silent (§5) |
| D3 | **DEFERRED** — no default recipes approved in 13A | Concrete/plaster/GK × S1–S4 / Q1–Q4 recipes are defined in 13D; §7 is illustrative only |
| D4 | **APPROVED** — new atomic PriceItems may be added where a real workflow needs them | No mechanical splitting of bundles; existing bundles stay valid |
| D5 | **APPROVED** — no stored `starting_condition` in v1 | Substrate + findings + explicit template choice; revisit only with a concrete 13D proposal |
| D6 | **APPROVED** — templates filterable by `surface_type` | Minimal applicability filter (§4.1) |
| D7 | **APPROVED** — record that a template was applied to a plan and when, as historical metadata, no live coupling | Application-history record on the durable plan header (§14.C) |
| D8 | **APPROVED** — no template-level default coefficients | Coefficients only on materialised occurrences (§12) |
| D9 | **APPROVED** — break information must survive materialisation, on the actual plan; never an intrinsic `PriceItem` property | Break stored on the step and on the materialised occurrence, carried in the save payload (§14.D) |
| D10 | **APPROVED direction, design deferred to 13H** — execution tracking in scope, but not on recreated occurrence ids and not via ordinal matching | Identity foundation = `occurrence_key` from 13B (D13); execution state/history designed in 13H (§4.5, §22) |
| D11 | **APPROVED** — reveals stay manual in v1; do not block a future extension | No reveal templates in v1 (§13) |
| D12 | **APPROVED** — Stage 13 = templates + ordered sequencing + technological/drying breaks + execution stage tracking; calendar/reminders stay in Stage 18; no general project-management engine | Scope of §20 |
| D13 | **APPROVED** — stable logical occurrence identity `occurrence_key` on `SurfacePlannedWork`, introduced **in 13B / migration 0027** (not deferred to 13H) | Identity foundation for tracking (§14.E, §22); Estimate unchanged in 13B |

---

## 0. Scope

Canonical roadmap: **Stage 13 — Technological workflows** — *Work sequencing, technological breaks, drying
times, stage tracking.* Confirmed by D12 as:

1. reusable technological workflow templates;
2. ordered technological sequencing;
3. technological / drying breaks;
4. execution stage tracking.

Out of scope: calendars, reminders and notifications (Stage 18); scheduling/resource planning; a general
project-management engine.

---

## 1. Current-state audit (13A.1)

**A. Where substrate is stored.** Not on `Surface`. It lives on:
- `SurfaceWorkPlan.substrate` (`backend/app/models/work_plan.py`, `SurfaceWorkPlan`) — the planning value;
- `Inspection.substrate` (`backend/app/models/inspection.py`, `Inspection`) — what was inspected.
A new Inspection reuses the saved plan's substrate/quality (Stage 11 UX); they are otherwise independent.

**B. Substrate values.** `Substrate` enum in `backend/app/models/checklist.py`:
`CONCRETE`, `GYPSUM_PLASTER`, `CEMENT_LIME_PLASTER`, `GYPSUM_BOARD`, `PAINTED`, `OTHER`.
Note: `PAINTED` is a *condition* ("existing paint coat"), not a base material — see §6.

**C. Where quality_target is stored.** `SurfaceWorkPlan.quality_target` and `Inspection.quality_target`
(nullable).

**D. Quality values.** `QualityLevel` enum (`checklist.py`): `S1–S4`, `Q1–Q4`. Scale validation
`assert_quality_scale_valid` (`backend/app/domain/rules/inspection_rules.py`):
`GYPSUM_BOARD` → Q only; `CONCRETE` / `GYPSUM_PLASTER` / `CEMENT_LIME_PLASTER` → S only;
`PAINTED` / `OTHER` → unrestricted; `None` always allowed. PSG1–PSG4 are presented as Q1–Q4 equivalents
(no separate enum values).

**E. Surface WorkPlan operations.** `SurfaceWorkPlan` (one per surface) → ordered
`SurfacePlannedWork(work_plan_id, price_item_id, position)` rows; duplicates allowed.
Persisted only by full replace: `SurfaceWorkPlanService.set_plan` / `replace_planned_works` / `_rewrite_works`
(`backend/app/domain/services/work_plan_service.py`); API `PUT …/surfaces/{id}/work-plan`
(`backend/app/api/v1/endpoints/work_plans.py`), payload `planned_works: [OrderedPriceItemSelection]`
(or legacy `price_item_ids`). Apply-to-all-walls: `apply_to_room_walls`.

**F. Opening Reveal operations.** No header table: `OpeningRevealPlannedWork(opening_id, price_item_id, position)`
(`backend/app/models/opening_reveal_planned_work.py`), REVEAL-category items only, full replace via
`OpeningRevealWorkService.set_works` (`opening_reveal_work_service.py`), bulk `apply_to_room_openings`.

**G. PriceItem ↔ planned work.** Each occurrence holds a direct FK `price_item_id` (RESTRICT). The planned
work carries no price/quantity; the Estimate reads the PriceItem at generation time.

**H. PriceUnits.** `PriceUnit` (`backend/app/models/price_item.py`): `M2`, `LM`, `PCS`, `HOUR`, `DAY`, `FLAT`.
Also `PriceCategory` (11 values incl. `REVEAL`) and `PriceScope` (`LABOR`, `MATERIAL`, `LABOR_AND_MATERIAL`).

**I. Estimate quantity resolution** (`backend/app/domain/services/estimate_service.py`):
- Surface occurrence — `_resolve_surface_quantity`: `REVEAL` category → unresolved (legacy); `M2` →
  `SURFACE_NET_AREA` (`_surface_net_area`; FLOOR/CEILING via `_plane_net_area`); anything else → unresolved
  (`MANUAL`, `NULL`).
- Reveal occurrence — `_resolve_reveal_quantity`: `LM` → reveal length, `M2` → reveal area, otherwise or
  underivable geometry → unresolved.
- Unresolved = `quantity_source=MANUAL, source_quantity=NULL, not quantity_overridden`; blocks `finalize`.
- **Consequence for Stage 13:** workflow steps priced in `LM`/`PCS`/`HOUR`/`DAY`/`FLAT` on a surface
  (e.g. crack repair, corners, GK joints) always need an owner-entered quantity.

**J. Stage 11 recommendations.** Findings/risks → `WorkRecommendationRule` (`app/domain/data/work_recommendation_rules.py`,
4 rules: `DUSTY_SUBSTRATE_PRIME→CENNIK_PRIM_STD-01`, `WEAK_ADHESION_PREP→CENNIK_PRIM_ADH-01`,
`UNEVENNESS_PREP_INCREASED→CENNIK_SKIM_LOCAL-01`, `CRACK_RECURRENCE→CENNIK_SKIM_CRACK-01`) →
`WorkRecommendation` (PENDING/ACCEPTED/DISMISSED). Acceptance
(`WorkRecommendationService.accept_recommendation`) locks the plan and calls
`SurfaceWorkPlanService.append_one_planned_work_no_commit` — **additive, one occurrence, never a full
replace**, never touches the Estimate, rejects REVEAL items.

**K. Stage 12 coefficients.** `SurfacePlannedWorkCoefficientAssignment` / `OpeningRevealPlannedWorkCoefficientAssignment`
join rows per occurrence (`work_plan.py`, `opening_reveal_planned_work.py`), sent inside the same PUT
(`coefficient_option_ids` per `OrderedPriceItemSelection`), validated by
`PriceCoefficientService.resolve_assignment_options` (LABOR only, SINGLE_SELECT, non-archived).

**L. Durable vs recreated ids.**
- Durable: `Surface`, `Opening`, `SurfaceWorkPlan` (header, one per surface), `PriceItem`,
  `CoefficientGroup/Option`, `Estimate`, `EstimateLine` (lines are updated in place on regeneration).
- **Recreated on every save**: `SurfacePlannedWork`, `OpeningRevealPlannedWork` and their coefficient
  assignments (full replace). Stage 12 made Estimate regeneration match lines logically
  (`_match_existing_lines`: exact id, then (surface, opening, PriceItem) paired by order).
- Stage 11's append path is the only one that adds an occurrence without recreating the others.

**M. Existing data resembling technological operations.** The seeded Price Book (`app/domain/data/price_book_seed.py`,
44 items) is already largely an operation catalog (see §2). There is **no** existing sequence/recipe entity,
no per-step drying time, and no execution status anywhere in the domain.

---

## 2. Price Book audit (13A.2)

Seeded items grouped by technological role (codes without the `CENNIK_` prefix / `-01` suffix):

| Role | Items | Unit / scope | Usable as workflow step? |
|---|---|---|---|
| Protection | `PREP_PROT`, `PAINT_MASK` | M2, LABOR | Yes (atomic) |
| Removal / stripping | `PREP_WALLP`, `PREP_SCRAPE`, `PREP_FLEECE` | M2, LABOR | Yes — condition-driven |
| Cleaning / dedusting | `PREP_CLEAN`, `PREP_DEGR` | M2, LABOR | Yes |
| Biological treatment | `PREP_MOLD` | M2, L+M | Yes (no coefficients: L+M) |
| Priming | `PRIM_STD`, `PRIM_ADH`, `PRIM_HIGH`, `PRIM_PAINT` | M2, L+M | Yes (no coefficients: L+M) |
| Repairs | `SKIM_LOCAL` (M2), `SKIM_CRACK` (LM) | LABOR | Yes — condition-driven; LM needs manual qty |
| Corners / edges | `SKIM_CORNER` (LM), `GK_CORNER` (LM) | LABOR | Yes; manual qty |
| Reinforcement / fleece / mesh | `GF_FLIZ_L`, `GF_FLIZ_M` (L+M), `GF_MESH` | M2 | Yes |
| GK joints / screws | `GK_JOINT` (LM), `GK_SCREW` (M2) | LABOR | Yes; `GK_JOINT` manual qty |
| Skim coat | `SKIM_1L`, `SKIM_2L` ("pakiet"), `SKIM_SQ` | M2, LABOR | Mostly; `SKIM_2L` is a 2-layer bundle |
| GK full-surface skim | `GK_FULL` (quality Q3), `GK_Q4` (quality Q4) | M2, LABOR | Yes — quality-tied items |
| Sanding | `SKIM_SAND` (incl. dedusting) | M2, LABOR | Yes (mildly bundled) |
| Painting | `PAINT_1K`, `PAINT_2K`, `PAINT_3K`, `PAINT_CEIL`, `PAINT_COL`, `PAINT_MULTI` | M2, LABOR | Yes; layer count is inside the item |
| Reveal | `REV_WORK_LM` | LM, LABOR | Opening domain only |
| Microcement | `MC_WALL_L/S`, `MC_FLOOR_L/S`, `MC_SHOWER`, `MC_STAIRS` (PCS) | mixed | `_S`/shower/stairs are full systems (bundles) |
| Decorative | `DEC_VEN`, `DEC_VEN_MAR`, `DEC_CONC`, `DEC_GENERIC` | M2, LABOR | Finish systems (bundles) |

Findings:
- **Reusable as steps:** almost everything in preparation, priming, repairs, fleece/mesh, GK, skim,
  sanding and painting. The seed is already close to atomic.
- **Bundled / composite:** `SKIM_2L` (two layers), `PAINT_2K/3K/CEIL` (layer counts), `SKIM_SAND`
  (sanding + dedusting), microcement `_S` / `SHOWER` / `STAIRS` and decorative systems, and any
  owner-created bundle (e.g. the walkthrough item "Grunt + Gładź (2 warstwy) + Grunt + Malowanie
  (2 warstwy)").
- **Missing atomic operations** (if the owner wants them as separate billable steps): a second-layer skim
  for Q/S upgrades, separate dedusting, primer between skim and paint is present (`PRIM_PAINT`), a
  "control under side light" step (S4) does not exist as a billable item. These are catalog decisions,
  not architecture (D4).
- **Recommendation:** Stage 13 steps **reference `PriceItem` directly** (§8). A separate
  technological-operation catalog would duplicate the Price Book, split owner edits across two catalogs,
  and give the Estimate nothing it can price.

---

## 3. Domain boundaries & terminology

| Concept | Meaning | Where it lives | Stage |
|---|---|---|---|
| Substrate | Base material (+ `PAINTED`/`OTHER`) | `SurfaceWorkPlan.substrate`, `Inspection.substrate` | 5/6/10 |
| Inspection finding | Observed fact (crack, dust, moisture, JOINT_TAPE_MISSING…) | `InspectionFinding.finding_key` | 6 |
| Risk | Deterministic consequence of findings | `Risk` / `RiskRule` | 7 |
| Starting condition | Summary of the surface state *relevant to choosing a technology* | derived, not stored in v1 (§6) | 13 |
| Quality target | Required finish level | `SurfaceWorkPlan.quality_target` | 6/10 |
| **Technological workflow (template)** | Reusable ordered recipe of operations for a substrate/quality combination | **new**: `WorkflowTemplate` + steps | **13** |
| Price item / operation | Billable operation with unit and price | `PriceItem` | 9 |
| Planned work | Actual project-specific occurrence | `SurfacePlannedWork` / `OpeningRevealPlannedWork` | 10 |
| Price coefficient | LABOR correction for execution conditions | Stage 12 assignments | 12 |
| Surcharge | Order-level/commercial extra | future; v1 = manual `EstimateLine` | future |

Canonical wording kept from Stage 12G:
- **"Standard Wykończenia Powierzchni S1–S4"** — *Wewnętrzna klasyfikacja wykonawcy.* Not a Polish norm, no
  millimetre tolerances, finish quality not geometry, never a coefficient.
- **Q1–Q4 / PSG1–PSG4** — industry gypsum-board finishing levels.
- "Technologia" (PL UI) / "Технология" (RU UI) for a workflow template; "Kroki" for its steps.

---

## 4. Workflow-template concept (13A.3)

### 4.1 What a template is (revised)
An **owner-scoped, reusable recipe**: an ordered list of steps, each pointing to a `PriceItem` (D1), plus
applicability metadata used only to filter/suggest templates in the UI:

```
WorkflowTemplate                       (recipe, not project state)
  name / description                    owner-editable
  applies_to_substrates                 subset of Substrate; empty = any
  applies_to_quality                    subset of QualityLevel; empty = any
  applies_to_surface_types              subset of SurfaceType; empty = any      (D6)
  steps: ordered WorkflowTemplateStep[]
WorkflowTemplateStep
  position
  price_item_id                         billable operation (never REVEAL)        (D1)
  is_optional                           default selection at apply time
  note                                  technological context, owner-editable
  wait_after_hours                      technological/drying break AFTER this step (D9)
```

No branching, no backend-evaluated conditions, no automatic application. Not a workflow engine.

### 4.2 Required capabilities
- Per substrate / quality / surface type → applicability filters and separate templates.
- Ordering → `position`; optional operations → `is_optional`.
- Owner-editable → CRUD + archive/restore (Stage 12 catalog pattern).
- Per-project customisation → after applying, the WorkPlan is edited as today.
- Price Book, WorkPlan, Estimate, coefficients → unchanged semantics; the template only yields ordinary
  occurrences (plus the break value, §4.3).
- Stage 14 photos/defects → surface/occurrence level, never the template.
- Stage 11 → unchanged in v1 (§11).

### 4.3 Technological / drying breaks (D9)
- A break is **"minimum wait after this step before the next step starts"**, in whole hours
  (`wait_after_hours`, nullable = no break).
- It belongs to the **technological step**, never to `PriceItem`: the same item can need different breaks
  in different systems/materials.
- It is **copied** onto the materialised occurrence and then lives on the actual plan independently of the
  template (editable there, survives template edits/archiving).
- It is **not billable** (not a `PriceItem`) and **not a calendar reminder** (Stage 18 may use it later).
- The Estimate ignores it.

### 4.4 Default catalog (D3 deferred)
Program defaults will be seeded lazily per owner (Stage 11/12 pattern), referencing seeded
`PriceItem.code`s resolved to the owner's items, owner-editable and never re-imposed. **Their content is
defined in 13D** after reviewing real technologies for concrete, plaster and gypsum board across
S1–S4 and Q1–Q4 / PSG1–PSG4. New atomic PriceItems may be added there where genuinely needed (D4).

### 4.5 Execution stage tracking (D10)
Stage tracking records execution progress of planned work over time. It **must not** be stored on
`SurfacePlannedWork.id` or kept alive by ordinal matching, because every WorkPlan save recreates those rows.

Why it differs from breaks/coefficients: a break or coefficient is *plan configuration* that the editor owns
and round-trips in the save payload. Execution status changes *outside* the editor (on site, over days);
an editor draft opened before a status change and saved after it would silently overwrite the newer
status if status travelled in the plan payload. Tracking therefore needs a **stable execution identity**
that the full-replace save cannot destroy or overwrite. D13 provides that identity (`occurrence_key`, §22) from 13B;
13H builds execution state/history on it, outside the plan payload, so a stale draft cannot overwrite it.

---

## 5. Template vs actual WorkPlan (13A.4) — decision

- **Template = recipe. SurfaceWorkPlan = the project's source of truth after materialisation.**
- Applying **copies** the selected steps into the plan as ordinary `SurfacePlannedWork` occurrences
  (with their `wait_after_hours`).
- The plan stays independent: reorder, remove, duplicate, coefficients, edit breaks.
- Template edits, archiving or deletion are **non-retroactive**; they never change an existing plan.
- The Estimate reads only the actual plan.

**Mechanism (recommended, unchanged): client-side materialisation into the editor draft, persisted by the
existing atomic `PUT …/work-plan`.** Same semantics as the Stage 12 coefficient modal: choosing a template
changes only the local draft; nothing is saved until "Zapisz plan prac". The existing validation
(archived items, REVEAL guard, coefficients) applies unchanged, and the Stage 12 logical Estimate line
matching keeps overrides for PriceItems that survive.

**Apply modes (D2):**
- **APPEND (default)** — selected steps are appended after the current draft occurrences; existing occurrences
  keep their `occurrence_key`, appended ones get new keys.
- **REPLACE** — the draft's occurrences are replaced by the selected steps. This **removes the existing
  occurrences and therefore their occurrence-specific coefficient assignments** (Stage 12), and any
  per-occurrence break values; Estimate lines for removed PriceItems become REMOVED on the next regeneration.
  The UI must show an explicit confirmation stating this before replacing the draft; nothing is persisted
  until the owner then saves. Removed occurrences' keys disappear; materialised steps get new keys (a
  removed key is never reused because a new step looks similar).

---

## 6. Starting condition (13A.5) — D5

Existing data: `Substrate` (incl. `PAINTED` as a quasi-condition), Stage 6 findings (`CRACK`,
`UNEVENNESS`, `LOOSE_SUBSTRATE`, `DUSTY_SUBSTRATE`, `OILY_SUBSTRATE`, `DELAMINATION`, `BLOW_HOLES`,
`EFFLORESCENCE`, `MOLD`, `HIGH_MOISTURE`, `WEAK_ADHESION`, `JOINT_TAPE_MISSING`, `BOARD_MOVEMENT`,
`FASTENER_CORROSION`, `JOINT_GAP`) and Stage 7 risks.

- Substrate — base material; unchanged.
- Inspection finding / risk — facts and consequences; never duplicated.
- **Starting condition — no stored field in v1 (D5).** Condition-specific work comes from optional template
  steps and Stage 11 recommendations.
- Technological decision — the owner's explicit template choice + ticked steps.
- If 13D shows template selection is materially ambiguous without a discriminator, a concrete proposal
  goes back to the owner.

---

## 7. Quality target → technology examples (13A.6) — illustrative only

**Not normative recipes, not approved defaults (D3).** They only test that the model can express the
cases; real content is defined in 13D. Codes refer to the seeded catalog.

| # | Substrate → target | Illustrative ordered steps |
|---|---|---|
| 1 | Concrete / plaster → S1 | protection · cleaning · priming · local repair (optional) |
| 2 | → S2 | protection · cleaning · priming · skim (bundle or layers) · sanding · primer under paint · painting |
| 3 | → S3 | as S2 + optional fleece + additional skim/sanding pass |
| 4 | → S4 | as S3 with the higher-standard skim item; conditions agreed per project; no generic default |
| 5 | Gypsum board → Q1 | screw masking · joint taping (LM) |
| 6 | → Q2 | Q1 + further joint finishing |
| 7 | → Q3 | Q2 + full-surface skim (`GK_FULL`) · sanding · primer · painting |
| 8 | → Q4 | Q2 + `GK_Q4` · sanding · primer · painting |

S1–S4 remains "Standard Wykończenia Powierzchni" — *Wewnętrzna klasyfikacja wykonawcy*: no normative
claims, no millimetre tolerances.

---

## 8. Operation granularity (13A.7) — D1 / D4

Chosen: **steps reference any `PriceItem`, atomic or bundled.** `PriceItem` remains the billable
operation; the step adds order, optionality, a technological note and the break. A bundle is one step
whose `note` can explain what it contains. New atomic items are added only where they give real
technological, planning or estimating value (D4); existing bundles stay valid.

Rejected for v1: a separate technological-operation catalog mapped to billing items (duplicates the Price
Book and needs Estimate/WorkPlan changes).

## 9. PriceItem relationship
- Step → `PriceItem` FK, same owner, RESTRICT (a used item can only be archived).
- Archived item in a template: shown as unavailable and skipped with a visible warning when applying
  (the WorkPlan save would reject it anyway).
- REVEAL items are invalid in surface templates.
- Templates store no quantities; the Estimate resolves them (§1.I). LM/PCS/… steps stay unresolved until
  the owner enters quantities; the apply preview warns.

## 10. Estimate relationship
No Estimate change. Materialised steps are ordinary occurrences; generation, preview, regeneration,
logical matching, overrides, coefficients, NULL/0.00 and FINAL/ACCEPTED behave exactly as in Stage 12.
The Estimate never reads templates, application history or breaks. The D13 `occurrence_key` does not
change Estimate matching in 13B; a future hardening path is documented in §22.7.

## 11. Stage 11 relationship
v1 unchanged: Finding → Risk → Recommendation → explicit accept → one appended occurrence (no break,
no coefficients). Future: a recommendation may **suggest** a template; materialisation still needs the
owner's explicit apply + save. Nothing applies a workflow automatically.

## 12. Stage 12 relationship — D8
Workflow = **what** is done. Coefficient = **labor price correction** for **how/where** it is done.
No template-level coefficients; materialised occurrences start with none; the owner assigns them via the
existing modal. REPLACE removes coefficients together with the replaced occurrences (§5).

## 13. Reveal relationship — D11
Reveals stay manual in v1. The design does not block a later `target = OPENING_REVEAL` template kind with
REVEAL-only steps. Surface and opening-reveal planning stay separate; no surface-level reveal work. `OpeningRevealPlannedWork` gets no `occurrence_key`
in 13B; a later extension would use the same, uncoupled pattern (§22.7).

---

## 14. Persistence model (revised)

Only what D1, D2, D6, D7, D9 and D13 require. No execution-status table yet (13H).

**A. `workflow_templates`**
```
id uuid pk
owner_id uuid fk users ON DELETE CASCADE
code varchar(120)  (owner_id, code) unique, immutable
name_key varchar(255) null        -- program defaults (13D)
display_name varchar(255) null
description text null
applies_to_substrates json null   -- list of Substrate values; null/empty = any
applies_to_quality json null      -- list of QualityLevel values
applies_to_surface_types json null-- list of SurfaceType values (D6)
position int, is_archived bool, created_at, updated_at
```

**B. `workflow_template_steps`**
```
id uuid pk
template_id uuid fk workflow_templates ON DELETE CASCADE
position int
price_item_id uuid fk price_items ON DELETE RESTRICT
is_optional bool default false
note text null
wait_after_hours int null (>= 1)
created_at, updated_at
```
Steps are replaced as a whole on edit (nothing else references them).

**C. Applied-template provenance (D7)** — options:

| Option | Pros | Cons |
|---|---|---|
| Live nullable `workflow_template_id` on `surface_work_plans` | one column | live coupling; shows the *current* template name, not what was applied; loses history when a second template is appended |
| Snapshot fields on `surface_work_plans` (id, name, applied_at, mode) | no coupling | only the *last* application; APPEND of several templates loses history |
| **Separate application-history record** | full history (several appends), pure snapshot, no coupling | one small table |

**Chosen: separate record `surface_work_plan_template_applications`**, attached to the **durable**
`SurfaceWorkPlan` header (never to recreated occurrence rows):
```
id uuid pk
work_plan_id uuid fk surface_work_plans ON DELETE CASCADE
template_id uuid null fk workflow_templates ON DELETE SET NULL   -- informational only
template_code varchar(120)        -- snapshot
template_name varchar(255)        -- snapshot (resolved display text at save time)
mode varchar(10)                  -- APPEND | REPLACE
steps_applied int                 -- how many steps were materialised
applied_at timestamptz
```
Written atomically inside the existing plan `PUT` when the payload carries an application intent
(§15); the snapshot is taken server-side from the template at save time. It is history, not state: the
plan remains the truth, and a later manual edit or REPLACE does not rewrite past records. Plan-level
only (no link to individual occurrences, which are not durable).

**D. Materialised break (D9)** — options:

| Option | Assessment |
|---|---|
| **Column `wait_after_hours` on `surface_planned_works`, carried in the save payload** | Same proven pattern as Stage 12D coefficients: plan configuration round-tripped explicitly by the editor on every full replace; no ordinal matching; additive |
| Companion technology-step record keyed by occurrence | Same recreation problem, plus a join; no benefit |
| Store only on the template and look it up | Violates D9 (template coupling) |

**Chosen: nullable `surface_planned_works.wait_after_hours int`**, added to
`OrderedPriceItemSelection` as an optional field. Rules:
- the editor always saves with `planned_works` (never the legacy `price_item_ids`) whenever any occurrence
  has a break or coefficient, exactly as Stage 12F does for coefficients;
- apply-to-all-walls copies it; Stage 11 append creates occurrences without it;
- the Estimate ignores it.

With D13 the saved occurrence also carries `occurrence_key`, so an ordinary save preserves both the key and
`wait_after_hours` while the row itself may be recreated.

**E. Stable logical occurrence identity (D13)** — `surface_planned_works.occurrence_key uuid NOT NULL`,
globally unique (unique index). Full semantics, uniqueness and threat model in §22.

## 15. API shape (revised)
- `GET /api/workflow-templates?archived=&substrate=&quality=&surface_type=` (lazy default bootstrap after 13D)
- `POST /api/workflow-templates`, `GET|PATCH /api/workflow-templates/{id}`,
  `POST …/{id}/archive`, `POST …/{id}/restore`
- `PUT /api/workflow-templates/{id}/steps` — full replace of ordered steps
- **Existing** `PUT …/surfaces/{id}/work-plan`, additively extended:
  - `planned_works[].occurrence_key` (optional; see §22 for the rules)
  - `planned_works[].wait_after_hours` (optional)
  - `template_applications: [{template_id, mode, steps_applied}]` (optional; each writes one history record)
- `GET …/work-plan` additively returns `planned_works[].occurrence_key`, `planned_works[].wait_after_hours`
  and the plan's `template_applications` history.
- No separate "apply" endpoint.

## 16. Mobile UX (revised)
- **Cennik → "Technologie"** tab: accordion list (Stage 12 catalog pattern); applicability chips and step
  count collapsed; expanded shows ordered steps with PriceItem, unit, optional flag, note and break
  ("przerwa min. 24 h"). Step editor: non-REVEAL PriceItem picker, reorder, optional toggle, note, break
  hours. 44 px targets, 320–480 px, PL/RU.
- **Rodzaje prac i jakość**: prominent **"Zastosuj technologię"** → bottom sheet:
  1. templates matching the plan's substrate + quality + surface type first, "Pokaż wszystkie" toggle;
  2. preview: ordered steps with unit, price, breaks, optional checkboxes; warnings for archived items and
     LM steps needing manual quantities;
  3. mode: **Dodaj na końcu** (default) / **Zastąp prace**;
  4. **Zastąp prace** opens an explicit confirmation: existing works *and their coefficients* will be removed
     from the draft;
  5. **Zastosuj** changes only the draft; the existing **Zapisz plan prac** persists (plan + breaks +
     application record).
- Breaks are shown on each planned-work card ("po tej pracy: min. 24 h przerwy") and editable there.
- Plan header shows provenance: "Technologia: *name* · data".
- S1–S4 disclaimer wherever the quality is shown.

## 17. Backward compatibility
- Existing plans, estimates, recommendations and coefficient assignments untouched; templates optional.
- WorkPlan `PUT`/`GET` changes are additive and optional; legacy clients keep working (a legacy
  `price_item_ids` save clears breaks exactly as it clears coefficients today, and — see §22 — gives every
  occurrence a new `occurrence_key`).
- Estimate logic unchanged.

## 18. Migration strategy
- **13B**: one migration `0027_workflow_templates`:
  1. create `workflow_templates`;
  2. create `workflow_template_steps`;
  3. create `surface_work_plan_template_applications`;
  4. add `surface_planned_works.wait_after_hours` (nullable);
  5. add `surface_planned_works.occurrence_key` as **nullable**, backfill every existing row with a fresh
     UUID generated in Python per row (`uuid.uuid4()`, matching the app's UUID convention and avoiding a
     dependency on a database UUID function), then set **NOT NULL** and create the **unique index**.
  The backfill touches no other column: no planned work deleted, order, PriceItem references, Stage 12
  coefficient assignments and Estimate data unchanged. Downgrade drops the added columns/tables.
  Reversible, single head, verified up/down/up in a scratch PostgreSQL DB.
- 13D: no migration (lazy bootstrap of defaults).
- 13H: its own migration for the execution-tracking model, keyed by `occurrence_key`.

## 19. Invariants & risks
1. **Template is a recipe, not project state.** The actual WorkPlan is the source of truth after
   materialisation.
2. **The Estimate never reads templates** (or application history, or breaks).
3. **Template edits are non-retroactive**; archiving/deleting a template never invalidates a plan.
4. **Technological break ≠ PriceItem** — not billable, not an item property.
5. **Technological break ≠ calendar reminder** — Stage 13 records the duration; Stage 18 may schedule it.
6. **Quality ≠ workflow ≠ coefficient** — target finish vs operations to reach it vs labor price correction.
7. **Workflow application is always explicit** — no inspection, rule or recommendation applies one.
8. **Stage 11 may suggest, the owner accepts** — suggestion never materialises by itself.
9. REVEAL work never enters a surface plan through templates; reveals stay manual (D11).
10. No automatic coefficients (D8); REPLACE removes coefficients only after explicit confirmation (D2).
11. Execution tracking never lives on recreated occurrence rows or ordinal matching (D10); it keys on
    `occurrence_key` (D13) and is never part of the plan payload.
12. S1–S4 remains an internal classification; no normative claims or mm tolerances.
13. Default recipes are owner-approved business data (13D), never invented.
14. Owner isolation on templates, steps and application history.
15. Risk: many LM/PCS steps create many unresolved quantities — preview warns.
16. `occurrence_key` is the logical identity; `id` is only the row identity and may change on save (D13).
17. A key never moves to another plan, another PriceItem or another occurrence, and a removed key is
    never reused (§22).

---

## 20. Stage 13 sub-stage plan (final)

| Sub-stage | Scope | Likely files | Migration | PASS | Non-goals |
|---|---|---|---|---|---|
| **13A** | Audit & architecture (this doc) | docs | no | owner approves D1–D13 ✅ | code |
| **13B** | Persistence/domain foundation: migration 0027; templates; template steps; provenance (application history); `wait_after_hours`; `occurrence_key` foundation (backfill, uniqueness, preservation across full replace, server-side key rules of §22) | `models/workflow_template.py`, `models/work_plan.py`, `domain/services/workflow_template_service.py`, `work_plan_service.py`, migration, tests | **0027** | pytest + scratch-DB up/down/up; backfill gives every row a unique key with nothing else changed; keys and breaks survive full replace; §22 rejections; Estimate behaviour unchanged | UI, default recipes, execution tracking, Estimate matching changes |
| **13C** | API/contracts: template CRUD/archive/restore; full-replace template steps; WorkPlan `occurrence_key` / `wait_after_hours` metadata; provenance intent | `api/v1/endpoints/workflow_templates.py`, `schemas/workflow_template.py`, `schemas/work_plan.py`, frontend types, tests | no | API tests incl. cross-owner, duplicate/foreign/stale keys, legacy payload compatibility | UI |
| **13D** | Default technological recipes: owner-defined business content (concrete, plaster, GK × S1–S4 / Q1–Q4); any justified atomic PriceItems (D4); lazy bootstrap | `domain/data/workflow_templates.py`, possibly `price_book_seed.py`, tests | no | exact approved content; idempotent; owner edits preserved | invented recipes |
| **13E** | Apply template to WorkPlan draft: matching/filtering; preview; optional-step selection; APPEND/REPLACE (+ confirmation); new occurrence keys; editor round-trips existing keys | `SurfaceWorkPlanEditor.tsx`, new sheet component, api/types, locales, tests | no | draft-only apply; Save persists plan + keys + breaks + history; coefficients removed only after REPLACE confirmation | server apply command |
| **13F** | Template management UI (Cennik → Technologie) | new catalog component, PriceBook tab, locales, tests | no | CRUD, ordering, breaks; mobile 320–480 | reveal templates |
| **13G** | Break editing/presentation polish on planned-work cards + apply-to-all check (new keys, breaks copied) | editor, tests | no | breaks editable and preserved through edits/apply-to-all | reminders |
| **13H** | Execution tracking: durable execution state/history built on `occurrence_key`; separate migration/API as required | new models/services/UI | **yes** (own) | status survives any WorkPlan edit and cannot be overwritten by a stale draft; no ordinal matching; Estimate unaffected | calendar/reminders |
| **13I** | Adversarial/full regression verification | tests | no | full gates, mobile | new features |
| **13J** | Owner walkthrough / production acceptance | — | apply 0027 (+13H) | owner PASS | Stage 14 |

---

## 21. Remaining open owner decisions

**None.** D1–D13 are decided; 13A is closed.

Not owner decisions now, but explicitly handed to later sub-stages:

- **13D** — the concrete default recipe content (D3) is owner-defined business data, agreed in 13D.
- **13H** — the execution-state/history table and API; what happens to execution state when its occurrence
  is removed (kept as history vs. deleted); whether a legacy key-less save (§22.6) should be refused for a
  plan that already has execution state. These are raised with the owner when 13H starts.

---

## 22. D13 — Stable logical occurrence identity (`occurrence_key`)

### 22.1 Two identities

`SurfacePlannedWork` has two distinct identities:

| Identity | Meaning | Durability |
|---|---|---|
| `id` | database row identity | may change on every full-replace WorkPlan save (Stage 10 `_rewrite_works` deletes and re-inserts) |
| `occurrence_key` | logical identity of one actual planned-work occurrence | survives ordinary full-replace saves |

Future execution/project state must key on `occurrence_key`, never on `id`.

### 22.2 Why in 13B (not 13H)

Stage 10's destructive full-replace persistence makes row ids non-durable. Stage 12 already needed logical
Estimate matching (exact id → `(surface, opening, price_item)` → order) to preserve overrides. Stage 13 adds
technological metadata and later execution tracking. Stable occurrence identity is therefore foundational
domain infrastructure and exists **before** tracking is built, so 13H does not discover a second identity
migration on `surface_planned_works`.

### 22.3 Semantics

Representation: UUID (`Uuid` column, application-generated `uuid.uuid4()`, matching the repository's
UUIDv4 convention). The exact SQLAlchemy mapping is confirmed during 13B.

| # | Situation | Key behaviour |
|---|---|---|
| A | Existing occurrence loaded into the editor | `occurrence_key` returned by `GET` |
| B | Existing occurrence edited, plan re-saved | same key sent back and preserved |
| C | Full-replace persistence | row `id` may change; `occurrence_key` stays the same |
| D | New manually-added work (incl. Stage 11 append) | receives a NEW key |
| E | Workflow-template materialisation | every materialised occurrence receives a NEW key; the template step id never becomes the key |
| F | APPEND | existing occurrences keep their keys; appended ones get new keys |
| G | REPLACE | removed occurrences disappear with their keys; materialised ones get new keys; a removed key is never reused because PriceItem/order looks similar |
| H | Apply-to-all | each destination Surface gets a NEW key per copied occurrence; the source key is never copied |
| I | Duplicate PriceItems | each duplicate occurrence has its own unique key |

A key is **never derived** from PriceItem id, ordinal position, substrate, quality target or template step
id. New keys are **generated by the server**; the client only echoes keys it received (a new occurrence is
sent without a key).

### 22.4 Uniqueness invariant

**`occurrence_key` is globally unique across all `SurfacePlannedWork` rows** (unique index; NOT NULL). No
scoped alternative is chosen: repository conventions (UUIDv4 everywhere) do not favour scoped uniqueness,
and global uniqueness lets a future execution table reference the key alone. Preserving a key through full
replace is safe because `_rewrite_works` deletes the old rows before inserting the new ones in the same
transaction.

### 22.5 Threat model — full-replace `PUT`

The payload is client-controlled, so the server validates keys before rewriting (whole save rejected, plan
unchanged, typed error envelope):

| Payload case | Risk | Server rule |
|---|---|---|
| Same key twice in one payload | two occurrences share one identity; tracking ambiguity | reject (422) |
| Key belonging to another plan / surface / owner | identity hijack, cross-owner leakage | reject; treated as unknown, no existence disclosure |
| Unknown / fabricated key | client-chosen identity | reject; new occurrences must omit the key |
| Key that existed but was removed by a later save (stale draft) | resurrecting a removed identity | reject as conflict (409); the editor reloads |
| Known key with a different `price_item_id` | silently re-purposing an occurrence | reject; a different operation is remove + add |
| Key omitted | — | server generates a new key |

The DB unique index is the final guard. Execution state (13H) is never part of this payload, so even a
valid stale save cannot overwrite it.

### 22.6 Legacy data and transition

Migration 0027 backfills every existing row with a unique key (Python `uuid.uuid4()` per row, batched),
then sets NOT NULL and creates the unique index. No planned work deleted; order, PriceItem references,
Stage 12 coefficient assignments, Estimate data and all WorkPlan business semantics unchanged.

Server fallback for legacy API clients/old payloads during transition:

- legacy `price_item_ids` save → every occurrence gets a new key (identity reset — the same model under
  which such a save already clears coefficients);
- `planned_works` entries without keys → treated as new occurrences, new keys;
- from 13C/13E the Mini App always round-trips keys, so the reset path is legacy-only.

### 22.7 Relationships

- **D9** — `wait_after_hours` stays actual planned-work configuration, carried with the occurrence in the
  payload; an ordinary save preserves `occurrence_key` and `wait_after_hours` while the row may be recreated.
  It is never moved onto PriceItem and never billed.
- **D10 / 13H** — `occurrence_key` is only the identity foundation. 13B implements no tracking. 13H adds
  durable execution state/history keyed by `occurrence_key`
  (`SurfacePlannedWork.occurrence_key → execution state/history`), outside WorkPlan editor state so a
  stale draft cannot overwrite it. The exact table/API is a 13H decision.
- **Estimate** — Stage 12 matching is accepted production behaviour and is **not changed in 13B**. Future
  hardening path: when safe and covered by regression tests, matching may prefer `occurrence_key` (e.g. a
  key on `EstimateLine`) before the existing logical fallback, which stays for rows that predate the key.
  Not coupled to 13B.
- **Opening reveals** — `OpeningRevealPlannedWork` gets **no** key in 13B (reveal workflows stay manual,
  D11; reveal tracking undefined). If durable reveal tracking/templates arrive later, it adopts the same
  pattern with its own key; Surface and Reveal identities are never coupled.
- **Provenance (D7)** — unchanged. `surface_work_plan_template_applications` remains the snapshot history
  on the durable `SurfaceWorkPlan`; `occurrence_key` does not replace it, and occurrences keep no live
  template-step FK.

### 22.8 Implementation clarifications (13B)

Factual notes from the 13B implementation; D1–D13 unchanged.

- No tombstones are kept for removed keys, so a stale key, another plan's/owner's key and an invented key
  are indistinguishable by design. All three return the same **409** conflict, which also guarantees no
  existence disclosure. A duplicate key in one payload and a known key sent with a different PriceItem
  return **422**.
- `wait_after_hours` is NULL (no break) or a whole number of hours **>= 1** (as §14.B) on both
  `workflow_template_steps` and `surface_planned_works`: 0 and negatives are rejected by the Pydantic
  schema, the template service and a DB `CHECK` constraint.
- Because the WorkPlan service consumes `OrderedPriceItemSelection`, the optional `occurrence_key` /
  `wait_after_hours` fields are already accepted by `PUT …/work-plan` and returned by `GET` from 13B
  (additive; the current Mini App ignores them, so every current save is the legacy key-less path of
  §22.6). Frontend types, template CRUD API and contract hardening remain 13C.
- **Transitional client behaviour (must be resolved before 13H).** The current pre-13C/pre-13E Mini App
  does not echo `occurrence_key`, so every WorkPlan save from it is treated as sending new occurrences and
  receives new keys. This is intentional backward compatibility, **not** the final Stage 13 identity
  behaviour; the frontend is not changed in 13B. 13C/13E must make the editor round-trip keys, and this
  must be resolved before execution tracking is built in 13H.

### 22.9 Implementation clarifications (13C)

Factual notes from the 13C implementation; D1–D13 unchanged.

- **Template API**:
  - `GET|POST /api/workflow-templates`, `GET|PATCH /api/workflow-templates/{id}`,
    `PUT …/{id}/steps` (full replace), and `POST …/{id}/archive|restore`.
  - There is no hard-delete and no apply endpoint.
  - Foreign and unknown templates or price items return the same 404.
- **Step order**: list order = position (same contract as `planned_works`), so duplicate or gapped positions
  cannot be expressed; an explicit `position` field is rejected.
- **Picker filter** (`substrate`, `quality_target`, `surface_type`, `archived=active|archived|all`):
  - A template matches a requested value when its filter for that dimension is empty ("any") or contains it.
  - There is no ranking.
- **Quality filters**: each quality in a template filter must fit at least one listed substrate under the
  existing S/Q rule (PAINTED/OTHER unrestricted, empty substrate list = any).
- **Provenance intent**: `PUT …/work-plan` takes an optional
  `template_applications: [{application_id, template_id, mode, steps_applied}]`.
  - The server resolves the owner's template and writes the code/name snapshot and `applied_at` itself.
    Client snapshot fields are rejected.
  - Validated before any mutation and recorded in the same commit as the plan.
  - A REPLACE intent may not be combined with echoed `occurrence_key`s.
  - The sum of `steps_applied` may not exceed the payload's new (key-less) occurrences.
  - An archived but owned template may still be recorded. Apply-to-all copies no provenance.
- **Retry idempotency without a new migration**: `application_id` is generated by the client once per
  apply action and becomes the history record's primary key (already globally unique in 0027).
  - Re-sending it for the same plan with the same template, mode and count is a no-op retry.
  - Any other reuse returns 409.
  - `GET …/work-plan` returns the plan's `template_applications` history, oldest first.

### 22.10 Open items carried forward (recorded at 13C acceptance)

- **Transitional frontend (resolve in 13E, required before 13H).** The backend round-trip contract is
  complete in 13C, but the current pre-13E Mini App does not echo `occurrence_key`, so its WorkPlan saves
  still create new logical keys. Stage 13E must make the real editor preserve `occurrence_key`.
- **Concurrency (deferred hardening, review before 13H).** Concurrent WorkPlan PUTs are not serialized today.
  Two truly simultaneous identical provenance retries may race on the unique `application_id`, and one
  request may surface a database uniqueness error. This is not a 13C blocker. Before 13H execution tracking,
  concurrency/stale-save semantics must be reviewed so that execution state is never lost or overwritten
  by an older WorkPlan editor state.

---

## 23. Stage 13D — program-default technological recipes (binding owner decisions)

Implemented in 13D.2 as data (`app/domain/data/workflow_templates.py`, `price_book_seed.py`), materialized
lazily and **insert-only** per owner. No migration (0027 already represents everything); no localization
schema change.

### 23.1 Price Book: 44 → 49 defaults

Five owner-approved OWN_PRICE rows (no market evidence, price NULL, LABOR):

| Code | Name (PL) | Category / unit |
|---|---|---|
| `CENNIK_SKIM_ADD-01` | Gładź szpachlowa — dodatkowa warstwa | SKIM_COAT / M2 |
| `CENNIK_GK_JOINT_Q1-01` | Szpachlowanie konstrukcyjne spoin g-k z taśmą (Q1) | DRYWALL / LM |
| `CENNIK_GK_JOINT_Q2-01` | Szpachlowanie spoin g-k — warstwa wykończeniowa (Q2) | DRYWALL / LM |
| `CENNIK_PREP_CONC-01` | Usuwanie nadlewek i szlifowanie styków betonu | PREPARATION / M2 |
| `CENNIK_SKIM_LEVEL-01` | Szpachlowanie wyrównawcze — korekta płaszczyzny | SKIM_COAT / M2 |

The legacy `CENNIK_GK_JOINT-01` ("…z taśmą (Q1/Q2)") is unchanged (name, meaning, owner price, archive
state) and stays available for manual use, but is **not** used by any default recipe.

### 23.2 Sixteen default templates

`TECH_{BETON|TYNK_GIPSOWY|TYNK_CW}_{S1..S4}-01` and `TECH_GK_{Q1..Q4}-01`:
- one substrate (CONCRETE / GYPSUM_PLASTER / CEMENT_LIME_PLASTER / GYPSUM_BOARD) and one quality target each;
- surface types WALL, CEILING, OTHER (never FLOOR);
- names via `name_key` `workflow_templates.seed.*` (PL/RU locale).

**Recipe rules:**
- **S1–S4** = "Standard Wykończenia Powierzchni", *Wewnętrzna klasyfikacja wykonawcy*.
  - Not normative, not a Q-equivalent, and never defined by a number of layers.
  - S1 = basic technical preparation, no full-surface skim.
  - S2 = paint-ready standard.
  - S3 = higher visual standard.
  - S4 = individually agreed premium standard with agreed viewing/lighting conditions.
- **Q1–Q4 (PSG1–PSG4)** is the separate gypsum-board scale:
  - Q1 = GK_JOINT_Q1;
  - Q2 = Q1 + GK_JOINT_Q2;
  - Q3 = Q2 + (opt) PRIM_STD + GK_FULL + SKIM_SAND;
  - Q4 = Q2 + (opt) PRIM_STD + GK_Q4 + SKIM_SAND. Q4 never uses GK_FULL.
- **Skim and sanding:** SKIM_2L stays the commercial two-layer package, and SKIM_SAND is sanding + dust
  removal. SKIM_ADD is **optional** and appears only in S3/S4. SKIM_SQ is never used.
- **Primers** are optional, condition-dependent alternatives: concrete ADH vs STD; cement-lime STD vs
  HIGH. Notes say "nie oba". There is no "one-of" mechanism.
- **Excluded from all recipes:**
  - fleece and mesh (GF_*);
  - geometry correction (SKIM_LEVEL is seeded but unused);
  - painting and PRIM_PAINT / PAINT_MASK;
  - REVEAL and GK_SCREW.
- **End point:** every recipe ends with a surface ready for the next finishing/painting system.
- **Waits and notes:**
  - All `wait_after_hours` are NULL. Drying guidance is a canonical Polish note: "Kolejny etap po
    całkowitym wyschnięciu, zgodnie z wymaganiami zastosowanego materiału i warunkami na obiekcie."
  - Template descriptions and step notes are canonical Polish text. Once materialized they are owner data.

### 23.3 Bootstrap

`WorkflowTemplateService.ensure_owner_catalog` runs on `GET /api/workflow-templates`. It first bootstraps
the owner's Price Book, then inserts only templates whose code the owner does not have.
- An existing template is never renamed, re-described, re-stepped or un-archived, so owner edits win.
- Steps reference the owner's own PriceItems by code. An item the owner has archived is still referenced
  (and never restored); 13E skips it with a warning (§9).

### 23.4 Invariants for 13E

- Optional recipe steps must start **unselected** in the apply preview.
- Provenance snapshots for an untouched default record `template_name` = its `name_key` (no display name
  is seeded). The UI resolves it through the locale.

---

## 24. Stage 13E.2B — Estimate occurrence identity (migration 0028)

Owner decisions D13E-1 (server-side apply endpoint), D13E-2 (template REPLACE = genuinely new work, no
override migration) and D13E-3 (quality target required before applying) are approved. 13E.2B implements
only the Estimate identity foundation. Template application, preview and the 13E UI are **not** implemented.

### 24.1 Identity rule

- `SurfacePlannedWork.id` is the physical row identity; it changes on every full-replace save.
- `SurfacePlannedWork.occurrence_key` is the stable logical identity of an actual planned-work occurrence.
- `EstimateLine.occurrence_key` (new, nullable, **no foreign key**) is a historical snapshot linking a
  Surface Estimate line to that logical occurrence. It outlives the occurrence.
- **Same key:** an ordinary re-save preserves the line's manual price/quantity overrides.
  **Different key:** different work, so old overrides never migrate automatically.

### 24.2 Migration `0028_estimate_occurrence_key`

The file is `0028_estimate_line_occurrence_key.py`; the revision id is shortened because `version_num` is
VARCHAR(32).

1. Add `estimate_lines.occurrence_key UUID NULL`.
2. Backfill **only** exact pairings: DRAFT estimate, PLANNED_WORK, `opening_id IS NULL`, `planned_work_id`
   resolving to an existing `surface_planned_works` row with the same `price_item_id`, and that
   `planned_work_id` not duplicated inside the estimate.
   - Stale ids, PriceItem mismatch, reveal, MANUAL, PRICE_BOOK, FINAL, ACCEPTED and ambiguous duplicates
     stay NULL.
   - Nothing is inferred from PriceItem, surface or order.
3. Create partial unique index `uq_estimate_lines_estimate_occurrence_key (estimate_id, occurrence_key)
   WHERE occurrence_key IS NOT NULL` (declared identically in the ORM for PostgreSQL and SQLite).

Downgrade drops the index and the column.

### 24.3 Matching

A Surface line is `opening_id IS NULL AND plan_id IS NOT NULL`. Reveal (and any other planned-work) lines
keep the exact Stage 12 pairing in their own pool, so reveal behaviour is unchanged. MANUAL lines stay
outside matching.

Surface precedence:
1. **Exact row id.**
2. **Same `occurrence_key`.** A keyed line never falls back.
3. **Legacy fallback**, only for lines with NULL key, on plans **without** a template REPLACE record in
   `surface_work_plan_template_applications`: Stage 12 logical key (surface, PriceItem), duplicates by
   line position / generation order.
4. **Leftovers:** unmatched lines are REMOVED (deleted on regeneration); unmatched occurrences are ADDED.

**Regeneration** re-points `planned_work_id` and stores `occurrence_key` on every matched Surface line. This
upgrades legacy lines, so the fallback is transitional and self-upgrading. A key write alone is never
reported as a change. New Surface lines snapshot the key.

**Preview** uses the same pairing and persists nothing.

**Reset override** for a Surface line resolves the live occurrence by `planned_work_id`, then by
`occurrence_key` within the line's surface, then falls back to the PriceItem. Reveal lines are unchanged.

FINAL/ACCEPTED estimates are never regenerated. Template application never touches an Estimate.

### 24.4 Release gate (important)

From 13E.2B on, only a **key-preserving** save keeps Estimate overrides. A legacy key-less save — which is
what the current pre-13E Mini App editor sends — creates new occurrences, so the next regeneration drops
the overrides of re-saved lines (REMOVED + ADDED).

Stage 12 tests that modelled "re-save" as key-less now echo the loaded keys, and a test documents the
key-less behaviour.

**13E.2B must not reach production without the 13E editor fix:** the editor must always send
`planned_works` with `occurrence_key`, `wait_after_hours` and `coefficient_option_ids`.

**Status: 13E.2B COMPLETE / OWNER ACCEPTED — NOT SAFE TO DEPLOY ALONE.**

- Stage 13E.2B must ship with the WorkPlan editor identity compatibility fix. Until that fix is present,
  the existing frontend omits `occurrence_key` on ordinary saves. Under the new identity model that
  correctly means "new occurrence", so old Estimate manual overrides can become REMOVED/ADDED on a later
  regeneration.
- A WorkPlan save itself never regenerates an Estimate, so nothing is lost at save time. The commercial
  effect appears only on a later explicit Estimate preview/regeneration.
- Production remains on the pre-13E release. Migration 0028 must not be applied independently.
- Stage 13E overall remains IN PROGRESS. The next substage is **13E.2C — editor identity compatibility**.

## 25. Stage 13E.2C — WorkPlan editor identity compatibility

Frontend-only; no backend production code changed.

- **Save path:** the Surface WorkPlan editor now **always** saves with `planned_works[]`. The legacy
  `price_item_ids` shortcut is gone, even with no coefficients, all waits NULL or a single occurrence.
- **Existing occurrences:** each echoes its server `occurrence_key` exactly.
- **New occurrences:** a manually added row omits the key; the server generates it. The editor never
  generates keys or sends placeholders. Its frontend-only `draftKey` (React/local row identity) is never
  sent.
- **Configuration:** `wait_after_hours` (NULL stays NULL) and `coefficient_option_ids` are sent verbatim per
  occurrence.
- **Duplicates:** occurrences of the same PriceItem keep their own key, wait and coefficients through
  load, reorder, delete and save.
- **Re-hydration:** after a successful save the editor re-hydrates from the server response, so a newly
  added row carries its server key and the next save echoes it.
- **Dirty detection** now follows occurrence identity (server key or local row id), not PriceItem ids.
  Reordering same-PriceItem duplicates is therefore saveable.
- **Stale-key 409** ("…is not a current occurrence of this work plan…") shows a localized message with a
  full-width **Odśwież plan / Обновить план** reload action (≥44 px).
  - The editor never retries without keys and never turns rows into new occurrences.
  - Other errors keep the existing save-error path.

**Status: 13E.2B and 13E.2C COMPLETE / OWNER ACCEPTED. The 13E.2B compatibility release gate is CLEARED BY
13E.2C.**

This means migration 0028 and the editor fix are now compatible with each other at code/branch level. It
does **not** mean:
- deploy production now;
- Stage 13E is complete;
- apply-template is implemented.

Production remains untouched on the pre-13E release. Migration 0028 ships only later, together with a
compatible frontend release, after Stage 13 production approval. Stage 13E remains IN PROGRESS. Next:
**13E.3 — server-side template application** (NOT STARTED).
