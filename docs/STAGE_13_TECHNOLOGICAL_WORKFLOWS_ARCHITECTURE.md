# Stage 13 — Technological Workflows: Audit & Architecture (13A)

- **Date**: 2026-09-25
- **Branch / HEAD**: `stage-13` @ `fb4eb9a` (= `main`; Stage 12 COMPLETE / OWNER ACCEPTED, production release `d60390b`, DB head `0026_coefficient_descriptions`)
- **Sub-stage**: 13A — **architecture/audit only**. No code, no migration, no API change.
- **Status**: **13A COMPLETE — owner decisions D1–D13 approved** (§A). Stage 13 itself is not complete; 13B starts only on explicit owner approval.
- **Final status (2026-09-27)**: **Stage 13 — COMPLETE / OWNER ACCEPTED / PRODUCTION VERIFIED** (see §35). Production runtime `7b5aaf0`, DB `0030_surface_work_executions`.

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

## 26. Stage 13E.3 — server-side template application

### 26.1 Endpoint

`POST /api/projects/{p}/rooms/{r}/surfaces/{s}/work-plan/apply-template`, next to `apply-to-room-walls`.

Request (`extra="forbid"`):

```json
{"application_id": "…", "template_id": "…", "mode": "APPEND|REPLACE",
 "selected_optional_step_ids": [], "expected_step_ids": ["…"],
 "expected_occurrence_keys": ["…"], "replace_confirmed": true}
```

- The last two fields are for REPLACE.
- PriceItems, order, notes, waits, the required-step selection and `steps_applied` are never accepted from
  the client; they come from the server template.
- **Response:** 200 `SurfaceWorkPlanRead` (planned works with keys, waits, coefficients, provenance
  history). An identical retry returns 200 with the unchanged current plan.

### 26.2 Transaction and locking

One transaction:
1. Ownership chain.
2. `lock_plan` (SELECT … FOR UPDATE) — **taken before the application_id is examined**. No plan → 404.
3. `application_id` replay/conflict.
4. Owned template (foreign or unknown → 404); archived → 409.
5. The plan must have `quality_target` (422).
6. Compatibility (422): empty filter = any; otherwise the plan substrate, quality target and the Surface
   type must be included.
7. `expected_step_ids` must equal the current ordered step ids (409).
8. Optional selection: each id must exist in this template and be optional, with no duplicates (422).
9. Materialization list = required + selected optional, **in template order**. Empty → 422 (no zero-step
   provenance).
10. Every chosen item: owner, no REVEAL, not archived (422). An archived optional item is allowed only if
    unselected; required archived items always block.
11. For REPLACE: `replace_confirmed` true and `expected_occurrence_keys` present (422), equal to the
    **exact ordered** current key sequence (409; `[A,B] ≠ [B,A]`). This detects additions, removals,
    replacements and reorders.
12. Materialize.
13. Provenance.
14. One commit.

Any failure before the commit changes nothing. Template edits that touch only metadata don't block
(`expected_step_ids` changes only when steps are replaced).

### 26.3 Semantics

- **APPEND** runs on the current DB state and never rewrites existing rows (ids, keys, positions,
  coefficients, waits unchanged). Selected steps are added at `MAX(position)+1…` in template order. Each
  gets a new server key (never the step id), the step's `wait_after_hours` and no coefficients. No
  de-duplication.
- **REPLACE** removes every current occurrence (coefficients cascade; legacy surface REVEAL rows go too)
  through the established full-replace path. It then materializes the selection at 0..N-1 with new keys,
  step waits and no coefficients. Old keys are never reused; the plan header and history remain.
- **Estimate:** never touched. APPEND keeps existing keyed lines matched and new occurrences appear ADDED;
  REPLACE yields REMOVED + ADDED on the next explicit preview/regeneration, with no override migration
  (13E.2B).

### 26.4 Idempotency (migration 0029)

The provenance row lacked the request content, so an identical retry could not be told apart from a reused
id with a different selection, template version or REPLACE composition.

- **Migration:** `0029_application_fingerprint` (file `0029_template_application_fingerprint.py`) adds
  nullable `surface_work_plan_template_applications.request_fingerprint` (VARCHAR 64). It is NULL for 13C
  PUT-intent rows.
- **Fingerprint:** a server-computed SHA-256 of canonical JSON
  `{v, work_plan_id, template_id, mode, sorted selected_optional_step_ids, ordered expected_step_ids,
  ordered expected_occurrence_keys (REPLACE), replace_confirmed (REPLACE)}`.
- **Same id + same plan + same fingerprint** → replay: 200 with the current plan, nothing materialized, no
  second row. Any other reuse → 409.
- **Concurrency:** under the row lock, concurrent identical requests serialize. The later one sees the
  committed record and replays; this was proven on PostgreSQL.
- **Provenance:** `id = application_id`, template id/code, name snapshot (`display_name`, else the default
  `name_key`), mode, **server-computed** `steps_applied` = rows actually materialized, `applied_at`,
  fingerprint.

**Status: 13E.3 COMPLETE / OWNER ACCEPTED.** Production untouched; migrations 0028/0029 not deployed.

Deferred:
- 13C PUT-intent provenance rows have a NULL fingerprint, so reusing their ids via apply-template returns 409.
- The three apply-template 409 cases (archived template, stale template, stale plan) are distinguished only
  by their messages. 13E.4 may rely on that. **Future API hardening:** machine-readable domain error codes
  instead of frontend branching on human-readable text.
- No automatic merge of stale editor drafts.

Stage 13E remains IN PROGRESS. Next: **13E.4 — frontend template picker / preview / apply UX**.

## 27. Stage 13E.4 — frontend technological workflow picker / preview / apply UX

Frontend-only; no backend change. `WorkflowTemplateApplySheet` (bottom sheet, same pattern as the
coefficient modal) is opened from `SurfaceWorkPlanEditor` by **Zastosuj proces technologiczny / Применить
технологический процесс**.

- **Gates:**
  - The action requires a saved plan with a quality target; otherwise it shows "Najpierw wybierz docelowy
    standard wykończenia." and never lists templates.
  - It is blocked while the editor has unsaved changes ("Najpierw zapisz lub odrzuć niezapisane zmiany planu
    prac."): no auto-save, discard or merge, because apply runs on current server state.
- **Discovery:** `GET /api/workflow-templates?archived=active&substrate=&quality_target=&surface_type=`. The
  server filter is authoritative; the editor now receives `surfaceType` from its three call sites. Built-in
  names come from `name_key` (PL/RU locale), custom names from `display_name`; codes and UUIDs are not
  shown. There is an empty state.
- **Preview** is a read-only snapshot:
  - ordered steps with ordinal, item name, Wymagany/Opcjonalny, note, and "Przerwa technologiczna: N h" only
    when set;
  - archived items marked; a required archived item blocks Apply; an archived optional item cannot be
    selected;
  - optional steps start **OFF** and reset whenever a template is (re)selected; nothing is persisted before a
    successful Apply.
- **Mode:** APPEND by default, each mode with a one-line explanation.
  - REPLACE shows the impact from the loaded plan (occurrence count, coefficient-assignment count) and
    "Kosztorys nie zostanie zmieniony automatycznie.".
  - Apply in REPLACE opens a second destructive confirmation (red, as other destructive actions).
  - REPLACE is blocked if any loaded row lacks an `occurrence_key`.
- **Request:** `application_id`, `template_id`, `mode`, the selected optional ids, the ordered preview
  `expected_step_ids`, and for REPLACE the exact ordered `expected_occurrence_keys` + `replace_confirmed:
  true`.
- **application_id:** one logical command keeps its id. A transport failure or 5xx (uncertain outcome) is
  retried with the same id and payload via "Spróbuj ponownie". Any change of template, optional selection,
  mode or plan composition produces a new id. There are no automatic retries; double submit is blocked.
- **Success:** the editor re-hydrates from the response (13E.2C identity contract), the sheet closes, and
  "Proces technologiczny zastosowany." is shown. There is no extra WorkPlan PUT and no Estimate call.
- **Errors** are classified in one helper (`classifyApplyTemplateError`, by current 13E.3 messages; future
  hardening: machine-readable codes):
  - **stale template 409:** "Odśwież proces" reloads the template and resets optionals; the next Apply is a
    new command;
  - **stale plan 409:** "Odśwież plan" reloads the plan and closes the sheet; never falls back to APPEND;
  - **archived/unknown template:** "nie jest już dostępny" and the list reloads;
  - **other 409 / 422:** a generic message with the server detail and "Odśwież proces".
- **Mobile:** verified headless at 320/390/412/480 px in PL and RU across APPEND, success, REPLACE impact,
  destructive confirmation, stale template, stale plan and long names. No overflow; the sheet fits the
  viewport and scrolls independently; the Apply/confirm action stays visible; all controls ≥44 px.

**Status: 13E.4 COMPLETE / OWNER ACCEPTED.** Production untouched; migrations 0028/0029 not deployed.

Deferred:
- Seeded Polish descriptions/notes appear in the RU UI (13D decision).
- The main chunk is ~535.40 kB; lazy-loading the sheet is a future option.
- 409s are classified by message text; machine-readable codes are future hardening.
- No stale-draft merge.
- The real Telegram walkthrough is required in 13E.5.

Next: **13E.5 — integration/adversarial verification + owner walkthrough**. 13F not started.

## 28. Stage 13E.5A — integration / adversarial verification (automated gate)

No product code changed. One test file was added for genuine cross-boundary gaps
(`backend/tests/test_stage13e_integration.py`, 6 tests). Everything else was already covered by the 13B–13E.4
suites.

### 28.1 Results

- **APPEND with the same PriceItem:**
  - Existing A (P, +15 %, 24 h) and B keep row id, key, coefficient and wait. The appended P rows get new
    keys, template waits and no coefficients. There is one provenance row, and the Estimate is
    byte-identical right after apply.
  - Preview shows exactly the 3 appended rows as ADDED. After regeneration A keeps 30.00 / 9.000; the new P
    rows have normal pricing and no override.
- **Ordinary save after APPEND:** a key-echoing save plus a coefficient change recreates rows but keeps keys
  and waits. Regeneration then gives 0 added / 0 removed, the same line ids and the new +15 % snapshot.
- **REPLACE with same-PriceItem duplicates** (A 30/9, B 40/7): new distinct keys, no old key reused, no
  coefficient rows left, and the Estimate is byte-identical after apply. Preview shows REMOVED = the two old
  lines and ADDED = the two new rows, with no UPDATED pairing. After regeneration neither override
  migrates.
- **Stale template or stale REPLACE composition:** 409 with WorkPlan, provenance and Estimate unchanged. A
  refreshed command succeeds.
- **Legacy key-less line with a REAL REPLACE via the endpoint:** no fallback; REMOVED + ADDED, overrides not
  carried.
- **Reveal isolation:** APPEND and REPLACE on the surface leave `OpeningRevealPlannedWork` untouched; the
  reveal line keeps its override and a NULL key.
- **Already covered elsewhere:** optional-step order, sequential APPEND/REPLACE retry, id-conflict variants,
  PostgreSQL concurrency (13E.3 gate), apply-to-all new keys, Stage 11 append, and frontend identity
  (13E.2C/13E.4).
- **Migration chain (scratch PostgreSQL):**
  - 0026 → 0027 → (seed with 13D code) → 0028 → 0029: 0028 backfill classification PASS.
  - 0029 `request_fingerprint` is nullable VARCHAR(64); the partial index is present with no FK.
  - Down to 0027 and back up passes, as do down to 0026 and back up. There is a single head and metadata
    drift stays at the 94 baseline.

### 28.2 Production deployment requirements (prepare only)

- **Release:** the current `stage-13` HEAD, with frontend and backend shipped together. The editor
  key-round-trip fix (13E.2C) is a hard gate for 0028.
- **Migrations:** 0027, 0028 and 0029. Production is at 0026, so all three are new. They are applied by the
  backend entrypoint (`alembic upgrade head`) on container start.
- **Seed/bootstrap:** no manual action, and no startup seeding.
  - The five new PriceItems and the 16 default templates are inserted lazily and insert-only per owner: on
    the first Price Book list (PriceItems), or on the first template list, which also runs the Price Book
    bootstrap first.
  - Existing owner rows, prices and archives are never changed.
- **Rollback:**
  - **Take a DB backup before migrating.**
  - After 0027 the Stage 12 backend (`d60390b`) **cannot save WorkPlans**:
    `surface_planned_works.occurrence_key` is NOT NULL with no DB default, and the old model omits it. This
    was verified on scratch PostgreSQL.
  - A code-only rollback is therefore not safe. Roll back by running
    `alembic downgrade 0026_coefficient_descriptions` **with the new image** (the old image does not know
    0027+) before starting the old containers, or by restoring the backup.
  - After a full downgrade, the Stage 12 code saves normally (verified). The downgrade discards Stage 13
    data only: templates, provenance, keys, waits and Estimate keys. Pre-Stage-13 data is kept.
  - An old frontend against the new backend would send key-less saves, losing overrides on regeneration
    (13E.2B release gate).

### 28.3 ⚠ CRITICAL — rollback and deployment atomicity

**A CODE-ONLY ROLLBACK AFTER MIGRATION 0027 IS NOT SAFE.** 0027 makes
`SurfacePlannedWork.occurrence_key` required. The pre-Stage-13 production backend does not provide it when
saving WorkPlans, so it cannot operate against a DB migrated through 0027+.

Canonical production rollback after a Stage 13 deployment:
- **Option A — schema downgrade:**
  1. stop or avoid writes;
  2. using the **NEW Stage 13 backend image/code** (which knows 0027–0029), run
     `alembic downgrade 0026_coefficient_descriptions`;
  3. verify the DB revision;
  4. start the old pre-Stage-13 containers/images.
- **Option B:** restore the pre-deployment PostgreSQL backup (take it before deploying).
- **Never** use the old backend image to run 0027–0029 or their downgrade: it does not know those revisions.

**Downgrade consequence:**
- Stage 13-only data is discarded: workflow templates, template application history, occurrence keys,
  technological waits, and Estimate occurrence keys/provenance.
- Pre-Stage-13 business data remains.

**Deployment atomicity:** the Stage 13 frontend and backend **must be deployed together**.
- **Old frontend + new backend:** ordinary WorkPlan saves omit `occurrence_key` and break the identity
  semantics, causing Estimate override mismatches on a later explicit regeneration.
- **New frontend + old backend:** the Stage 13 contracts and endpoints do not exist.

### 28.4 Status

**13E.5A AUTOMATED VERIFICATION PASS / OWNER ACCEPTED.**
- Stage 13E was IN PROGRESS at this point; it is **COMPLETE / OWNER ACCEPTED** as of §29.5.
- **13E.5B:** production deployment of e4e6c1e performed manually by the owner (production DB at
  `0029_application_fingerprint`); the Telegram walkthrough found the defects fixed in §29.
- **13F:** NOT STARTED.

## 29. Stage 13E.5B-FIX — owner walkthrough defects + targeted mobile UX

A patch **inside 13E**, not a new stage. No migration, no backend production code, no change to the
occurrence_key architecture or to Estimate automatic-sync semantics.

### 29.1 APPEND ordering (reported: new works interleaved with existing ones)

**Investigation (read-only first):** reproduced on scratch PostgreSQL (A B C + APPEND of a 3-step template;
then a repeated APPEND). The apply response, the persisted `position` values (0..n-1) and a fresh GET all
return the template block **after** every existing work, in step order. The WorkPlan editor does not sort;
it renders server order. **No WorkPlan ordering defect is reproducible.**

**Most likely explanation of the observation:** the Estimate screen groups lines by
`planned::{price_item_id}::{scope}::{unit}::{surface|reveal}` (Stage 12 grouping), so APPENDed occurrences of
a PriceItem already present in the plan appear inside the existing group, not as a trailing block; and a
repeated APPEND of the same template adds a second identical block whose rows look interleaved with the
first. Neither changes WorkPlan order. Owner confirmation of the exact screen is requested.

**Regression contract:** `TestAppendOrderingContract` (`backend/tests/test_stage13e_integration.py`) —
A B C then APPEND twice → positions 0..8, A B C unchanged, two ordered template blocks, 9 distinct
occurrence keys, 2 provenance rows, Estimate untouched. It passes on current code (a contract test, not a
failing-then-fixed test, because no defect exists in the WorkPlan path).

### 29.2 Repeated-APPEND safety (frontend only)

- Required steps have no checkbox; optional steps are OFF by default (unchanged).
- **Pre-apply summary (FIX.2):** pinned in the sheet footer directly above Apply, updated live on every
  optional toggle: "Zostaną dodane 4 prace" + "3 wymagane + 1 wybrana opcjonalna" / "Будут добавлены 4
  работы" + "3 обязательные + 1 выбранная дополнительная"; REPLACE: "Nowy plan prac będzie zawierał N prac"
  + "Obecne prace (M) zostaną zastąpione.". Plural forms per part via `Intl.PluralRules` (one/few/many).
- **After apply (FIX.2):** "Proces technologiczny zastosowany i zapisany." with an explanation why Save is
  disabled (apply-template already persisted the plan; no extra PUT, no artificial dirty state). The
  notice disappears and Save enables on the next ordinary edit.
- **No history-based repeat warning (FIX.3).** A FIX.1 warning ("Ten proces był już zastosowany…")
  triggered whenever the template id appeared in `template_applications`. The owner walkthrough showed it
  firing after the template's works had been removed manually. Audit: `surface_planned_works` stores no
  application/template relation, and `surface_work_plan_template_applications` stores no occurrence keys
  (only snapshot code/name, mode, `steps_applied`, fingerprint). History therefore proves only that the
  template *was* applied, never that its works are still in the plan, so the warning was removed. PriceItem
  comparison is not a substitute (same PriceItem may be manual, duplicated, or shared by templates;
  occurrence identity is intentionally stronger). A deliberate later APPEND is a normal command (new
  `application_id`) that adds another block, made explicit by the pinned summary. History is never
  deleted or rewritten; the editor PUT sends no `template_applications`. A future occurrence-level
  attribution would require a schema change and is out of scope for Stage 13E.
- **Final APPEND review (FIX.4).** Owner walkthrough: the plan already held "Gładź szpachlowa — 2 warstwy
  (pakiet)" and the S3 template appended the same PriceItem again, because APPEND mutated straight from the
  preview. APPEND now goes preview → Zastosuj → review ("Prace, które zostaną dodane") → "Dodaj wybrane";
  nothing is sent before the last step. The review lists every candidate (all required + selected optional,
  template order, never collapsed) with its required/optional badge, "Już w planie: N" when the CURRENT plan
  holds occurrences with the same PriceItem ("Ta praca jest już w planie. Możesz pominąć jej ponowne
  dodanie."), "Także wyżej na tej liście: N" for an earlier checked candidate with the same PriceItem, and
  "Zostanie dodana" / "Pominięta". Defaults: a candidate whose PriceItem is already in the plan starts
  SKIPPED, every other candidate starts checked (a template-defined repeat with nothing in the plan stays
  checked — the template author asked for two occurrences). Zero selected → "Wybierz co najmniej jedną
  pracę." and the confirm button is disabled. PriceItem equality is used ONLY for this current-state hint;
  it never implies provenance, template membership or occurrence identity, and never touches existing
  occurrences. **Contract:** `ApplyTemplateRequest.selected_step_ids` (optional, APPEND only) is the exact
  set of this template's step ids to materialize, required or optional; the server rejects (422, nothing
  written) unknown/foreign/duplicate ids, a combination with `selected_optional_step_ids`, use with REPLACE
  and an empty selection; PriceItems, order, notes and waits still come from the server template;
  `expected_step_ids` staleness (409) and archived-item checks on the chosen steps are unchanged. The
  fingerprint adds `selected_step_ids` only when sent, so pre-FIX.4 requests keep identical fingerprints.
  REPLACE is unchanged: no review, all required + selected optional, its own confirmation.
  Owner manual verification of FIX.4: PASS (2026-09-26).
- **Runtime dependency (13E.5B).** `sqlalchemy.ext.asyncio` needs `greenlet`. SQLAlchemy 2.0.x installed it
  implicitly; 2.1.x (allowed by `<3.0.0`, resolved by a `--no-cache` image build as 2.1.1) does not, so the
  backend failed at startup. The dependency is now declared explicitly as `sqlalchemy[asyncio]` in
  `backend/requirements.txt` and `backend/pyproject.toml`. No schema change; single Alembic head `0029`.
- Idempotent retry unchanged: the transport/5xx retry reuses the same `application_id` without asking again.
- REPLACE keeps its own separate confirmation.

### 29.3 Other walkthrough UX fixes

- **Object Estimate shortcut:** a compact full-width "Kosztorys" / "Смета" action (≥44 px) under the
  breadcrumb in nested project views (room / surface). It opens the same Estimate route as the overview card;
  hidden on the overview (which already has the large card) and on the Estimate screen.
- **Opening summary on the wall card:** read-only lines such as "Drzwi 0,90 × 2,07 m (2)"; active openings
  only (archived excluded), grouped by type + width + height with SUM(quantity), ordered DOOR → WINDOW →
  OTHER then width/height ascending; hidden when there are no openings; no calculation change (reuses the
  existing per-wall openings fetch).
- **Toggle label:** the wall-card toggle reads "Otwory i opcje" / "Проёмы и опции" (hide: "Ukryj otwory i
  opcje" / "Скрыть проёмы и опции"); label change only. The toggle is capped at 40 % of the header width and
  wraps, so a long wall name is not squeezed at 320 px.

### 29.4 Status

Automated verification PASS; mobile checks PASS at 320/390/412/480 px in PL and RU. FIX..FIX.4 and the
dependency fix were committed and pushed as `d6e126f` (`fix(stage-13): harden workflow application
walkthrough`) after owner approval.

### 29.5 Stage 13E closure — production walkthrough PASS

**STAGE 13E COMPLETE / OWNER ACCEPTED (2026-09-26).**

- **Production release:** `d6e126f2278dfbc464ab78d3fad7a960cb3f9833`, backend and frontend deployed together
  by the owner. Backend healthy; public `/api/health` returned `{"status":"ok"}`. Alembic at
  `0029_application_fingerprint` (head); no new migration in 13E.5B. Async runtime on SQLAlchemy 2.1.1 +
  greenlet 3.5.6 works. Telegram Menu Button cache-busting URL: `https://plan-estimate.pl/?v=d6e126f`.
- **13E.5B production Telegram walkthrough: PASS.** Verified by the owner in the real Mini App:
  - an existing planned work is detected as "already in plan" and skipped by default instead of duplicated;
  - the reviewed APPEND selection shows correct added/skipped counts; an optional work can be deliberately
    selected; only the selected missing works are added; no accidental duplicate of an existing logical work;
  - the applied workflow is persisted immediately; the success state says the process is applied and saved;
    Save stays disabled until another plan edit;
  - wall opening summary / reveals display correctly; "Otwory i opcje" is present; the nested Estimate
    shortcut works;
  - Estimate preview shows added/removed changes; regeneration works; existing manual quantity/price
    overrides and coefficient provenance remain visible; new workflow works appear as separate Estimate
    positions;
  - real Telegram mobile layout usable, no observed horizontal overflow.
- **REPLACE** was not among the items listed for the production walkthrough; its semantics are unchanged in
  13E.5B and remain covered by the automated suites (`TestReplace`, `TestAdversarialReplace`, frontend
  REPLACE tests).
- **Deferred API hardening (known, not blocking):** with `selected_step_ids` a direct API client may omit a
  required template step whose PriceItem is archived, because the archived check covers only the steps
  actually materialized. The Mini App prevents this (the preview blocks a template with an archived
  required item); server-side hardening remains a future task. *(Closed later in 13F.2 — §30.2.)*
- **Stage 13F:** NOT STARTED (requires explicit owner approval). *(Started after owner approval — §30.)*

## 30. Stage 13F — template management

### 30.1 Owner decisions (13F.1 audit PASS, 2026-09-26)

- **D-F1 — defaults stay owner-editable** (preserves D3, §4.4: never re-imposed). A default is identified
  by its immutable seeded code (`DEFAULT_WORKFLOW_TEMPLATE_CODES`, derived from the Stage 13D recipe list)
  and exposed as a derived, read-only `is_default`; no column, no migration. Defaults may be duplicated
  (client-side, via the existing create). No reset-to-default in v1. A default's custom `display_name` can
  be cleared so its localized `name_key` applies again.
- **D-F2 — optimistic concurrency for step replacement** via `expected_step_ids`; metadata PATCH stays
  last-write-wins (the UI sends only changed fields). No general versioning.
- **D-F3 — close the 13E `selected_step_ids` archived-required-step hole now** (13F.2).
- **D-F4 — empty templates stay valid** at API/storage level; applying one stays rejected; the 13F UI will
  prevent saving a zero-step template.
- **D-F5 — UI location:** Cennik → Procesy (Price Book → Processes).
- **D-F6 — no hard delete in v1** (archive / restore only); a deleted default would be re-inserted by the
  insert-only bootstrap.

Invariants restated: templates reference live PriceItems (no price copy); NULL-price items are allowed
(UI warns); repeated PriceItems are independent ordered steps, never deduplicated; template edits never
touch a WorkPlan, an Estimate or application history; applying never sets or changes `quality_target`;
S1–S4 / Q1–Q4 / PSG1–PSG4 semantics unchanged.

### 30.2 Stage 13F.2 — backend hardening (contracts)

- **`WorkflowTemplateRead.is_default: bool`** — `code in DEFAULT_WORKFLOW_TEMPLATE_CODES`. Read-only:
  create/PATCH reject it as an unknown field.
- **`PATCH /workflow-templates/{id}` `display_name`** — omitted = unchanged; string = set; explicit
  `null` (or a blank string) = clear, allowed only when the template has a `name_key` (a default);
  clearing an owner-created template's name is 422. Other PATCH fields keep their semantics.
- **`PUT /workflow-templates/{id}/steps` `expected_step_ids`** (optional) — the exact ordered step-id list
  the client read. The template row is locked (`SELECT … FOR UPDATE`) and compared with the current
  ordered step ids: exact match → replace; missing / extra / unknown id, different order or an empty
  claim → **409** and nothing changes. Omitted → the unchanged 13C behaviour (backwards compatible).
- **Apply hardening (D-F3)** — with `selected_step_ids`, every REQUIRED step is validated even when the
  owner skips it (archived item → 422 "the required step's price item … is archived", REVEAL item → 422,
  missing/foreign item → 404), exactly like the legacy path. Skipping a VALID required step (the FIX.4
  duplicate-aware review) is still allowed. An archived optional step stays unselectable (422 if selected).
- **Bootstrap** — unchanged, insert-only by code: renames, cleared names, descriptions, edited steps (step
  row ids included) and archive state survive; only a missing canonical code is inserted. The bootstrap
  docstring now states the real apply behaviour for archived items (required blocks, optional
  unselectable, nothing skipped silently).
- **No migration**; single Alembic head `0029_application_fingerprint`. Frontend unchanged in 13F.2.

### 30.3 Stage 13F.3 — list + read-only detail (Cennik → Procesy)

- Third Cennik tab "Procesy" (lazy `WorkflowTemplateManager`). Uses only existing contracts:
  `GET /workflow-templates?archived=active|archived&surface_type=…` (server "any" semantics for empty
  filters) with steps, live PriceItem summaries and the derived `is_default`.
- List: Aktywne / Archiwum, surface-type filter, cards (name, default/archived badges, surface types, step
  counts, archived / no-price warnings). Read-only detail: metadata, applicability and ordered steps
  (required/optional, unit, wait, note, no-price and archived/missing states); repeated PriceItems are separate
  steps; empty templates render an empty state.
- Out of scope here: editing (13F.4/13F.5), archive/restore, duplication, applying (stays in 13E).
  No schema change.
- **FIX.1 — built-in description localization:** `WorkflowTemplateRead.description_key` (derived, read-only)
  is set only while the stored description exactly equals the canonical Stage 13D text for the default code;
  the UI localizes it (PL = canonical text, RU translation). Owner-edited and custom descriptions carry no key
  and are shown verbatim (D-F1).
- **FIX.2 — built-in step note localization:** `WorkflowTemplateStepRead.note_key` (derived, read-only, per
  step) is set only while the step's note is exactly one of this default recipe's canonical notes. One key per
  distinct canonical note text (`workflow_templates.step_note.*`), following the note constant rather than the
  PriceItem. Edited, custom and missing notes carry no key; repeated PriceItems are localized independently.
  Shared frontend helper `utils/workflowTemplateText.ts` (description + step note) used by the manager and the
  13E apply sheet.
- **FIX.3 — real-contract regression:** the RU walkthrough failure was a stale local backend container (built
  before FIX.1/FIX.2, so the JSON had no keys); stored data matched canonical exactly. Added a captured,
  anonymized endpoint-serializer response of the seeded TECH_BETON_S4-01 as a frontend fixture, with a backend
  test asserting list/detail JSON keys equal the fixture.
- **Status:** 13F.3 PASS / OWNER ACCEPTED / PRODUCTION VERIFIED (commit `89e3b18`). Next: 13F.4.

### 30.4 Stage 13F.4 — create / edit metadata / duplicate / archive / restore

Frontend only, over the existing contracts (no backend change, no migration):
- **Create** — `POST /workflow-templates` with metadata and `steps: []`; the code is always server-generated
  (`CUSTOM_*`, immutable, unique per owner). The empty template is labelled "Brak kroków" and the detail explains
  that steps are configured in the step editor (13F.5) and that it cannot be applied until then (D-F4).
- **Edit metadata** — `PATCH` with changed fields only (last-write-wins, D-F2); built-in name may be cleared
  (`null`) to restore the localized canonical name (D-F1); custom name required; description clearable; the
  detail is re-fetched after save.
- **Duplicate** — client-side via `POST` (D-F1): new custom template, new id/code, not default; metadata copied
  (stored text, not the localized rendering) and steps copied in order with required/optional, stored note and
  wait; repeated PriceItems preserved; source untouched; no coefficients. Blocked with an explanation when a
  source step references an archived/unavailable PriceItem (the create contract rejects adding one).
- **Archive / restore** — confirmed archive (plans, estimates and application history unchanged); restore
  returns the template to the active list; no hard delete (D-F6).
- **Status:** 13F.4 PASS / OWNER ACCEPTED / PRODUCTION VERIFIED (commit `7db7a14`). Next: 13F.5.

### 30.5 Stage 13F.5 — step editor

Frontend only over `PUT /workflow-templates/{id}/steps` (13C) with the 13F.2 precondition:
- **Explicit draft.** Add / remove / reorder / required-optional / note / wait are local until "Zapisz kroki",
  which sends the complete ordered list (array order = position) plus `expected_step_ids` = the ordered step
  ids the editor was opened with. The server replaces the rows (new step ids every save); the editor then
  re-fetches the canonical template.
- **Concurrency.** Any difference in the stored ordered ids is a 409; the UI keeps the draft, never overwrites
  or retries, and offers an explicit "reload server version" (which discards the draft). No merge in v1.
- **Occurrences.** The same PriceItem may appear any number of times; each row is independent. Template step
  ids are template-management identity only, never WorkPlan `occurrence_key`s.
- **Picker.** Existing Price Book API, active non-REVEAL items, client-side search; NULL-price items allowed and
  labelled; archived items not offered (the backend rejects a new archived occurrence), existing archived steps
  kept and flagged.
- **Notes** are owner text (trimmed, blank = none); untouched canonical built-in notes keep their derived
  localization; edits become verbatim; exact canonical text localizes again.
- **Wait** is `wait_after_hours`: empty = no break, else a whole number of hours ≥ 1; the day hint is display
  only (no calendar/reminder semantics — Stage 18).
- **Reorder** uses "W górę" / "W dół" buttons (no drag-and-drop).
- **No retroactive effects:** WorkPlans, occurrence keys, Estimates, application history and Stage 12
  coefficients are never changed by a template edit.
- **Identity:** `WorkflowTemplateStep.id` ≠ `SurfacePlannedWork.occurrence_key`. Template step rows may receive new
  ids on every replacement; `expected_step_ids` is only optimistic-concurrency state for template editing;
  `occurrence_key` remains the durable identity of a materialized planned-work occurrence.
- **Status:** 13F.5 PASS / OWNER ACCEPTED / COMMITTED / PUSHED / PRODUCTION VERIFIED (commit `31e3ea0`).
  **Stage 13F COMPLETE / OWNER ACCEPTED / PRODUCTION VERIFIED.**

## 32. Stage 13G — technological breaks in the surface work plan

- `SurfacePlannedWork.wait_after_hours` belongs to the planned-work **occurrence**: the minimum technological
  break AFTER that work before the next operation should normally start. It is not work duration, labour time,
  a start/end time or a deadline. Canonical persistence stays whole hours (NULL = no defined break, else ≥ 1;
  schema `ge=1` + DB CHECK, identical to template step waits). Days are only a derived display hint for exact
  24 h multiples. A last work may keep its break.
- Template → WorkPlan copies a **snapshot** (APPEND: existing occurrences keep key and wait, new ones get new
  keys and the step's wait; REPLACE: new keys with step waits). Later template edits never change materialized
  waits.
- Apply-to-all copies the wait **value** to each destination occurrence, which gets a NEW occurrence key.
- Stage 11 recommendation append creates the work with no break (never inferred from PriceItem, risk,
  inspection or another template).
- Coefficients and waits are independent; the Estimate ignores waits (generation and regeneration).
- UI: numbered works, the break shown on the card, edited per occurrence behind "Przerwa po pracy" through the
  existing WorkPlan save (occurrence keys and coefficients preserved). No backend change, no migration.
- Scheduling, calendar and reminders belong to Stage 18; execution state to 13H.
- Duplicate PriceItem occurrences keep independent waits; apply-to-all destination occurrences stay
  independently editable.
- **Status:** 13G COMPLETE / OWNER ACCEPTED / COMMITTED / PUSHED / PRODUCTION VERIFIED (commits `82cb82b`,
  dark-theme FIX.1 `e702d71`: break toggle uses the paired `--tg-control-*` theme tokens). No migration; Alembic head `0029_application_fingerprint`.

## 31. Stage 13F-PRE — room / surface / object corrections (not template management)

Owner Telegram walkthrough fixes made before 13F.3, recorded separately from 13F. No migration, no model change.

- **Wall generation CTA** — shown only when the room has no WALL surface, archived ones included (the
  backend `generate_walls` creates a set whenever no ACTIVE wall exists, so archived walls would otherwise
  invite a duplicate set). Backend generation rules unchanged.
- **Room opening summary** — `RoomRead.opening_groups` (read-only): active openings on active surfaces,
  grouped by type + exact Decimal width/height (`domain/rules/opening_summary.py`), quantities summed,
  DOOR → WINDOW → OTHER.
- **Inspection navigation** — FLOOR / CEILING inspection from the plane card's Opcje. The room-level entry is
  kept: room-level inspections (`surface_id` and `plane` null) are genuinely room-scoped persisted data.
- **FLOOR recommendations** — rules had no target compatibility; the baseline works are wall/ceiling works.
  `RECOMMENDED_WORK_TARGET_KINDS` declares each work's compatible targets (FLOOR only when explicit),
  applied at evaluation; accept refuses to auto-resolve an incompatible pre-fix row (manual choice allowed).
  Missing FLOOR works (e.g. floor primer, self-levelling screed) are a future catalog task.
- **Object summary** — `GET /projects/{id}/summary` (read-only): Decimal sums of active rooms' canonical
  `RoomCalculations` + openings grouped across rooms; rendered after the room list. No frontend geometry.

### 31.1 13F-PRE FIX.2 — inspection UX and wall section (owner walkthrough)

- **No generic room-level inspection** (owner decision): the room workspace no longer offers "Badanie
  pomieszczenia"; the standalone "Badania podłoża" section is removed. Historical room-level records are kept
  in storage untouched; backend support is unchanged; no history UI is added.
- **"Powierzchnie" → "Ściany"** for the wall-only room-workspace section (heading only).
- **Checklist audit:** templates are substrate-keyed, target-agnostic wall/ceiling finishing checklists
  (7 generic questions, +4 drywall for gypsum board). FLOOR and CEILING both receive them; there is no
  floor checklist. Inspection `quality_target` feeds no risk/finding/recommendation (no QUALITY_IN /
  TARGET_IN rule) and never changes WorkPlan quality.
- **Availability:** FLOOR inspection is not offered and the wizard never asks FLOOR for S1–S4/Q1–Q4;
  CEILING keeps its inspection and substrate-scoped S/Q step; WALL unchanged. "Pomiń" now starts the
  inspection without a class (it previously only cleared the selection).
- **Deferred — Floor Inspection & Floor Preparation Catalog:** floor substrates, flatness/level, cracks,
  strength/cohesion, moisture, contamination/adhesion, existing coatings/adhesives, preparation
  recommendations and FLOOR PriceItems, designed separately.

## 33. Stage 13H — execution tracking (COMPLETE / OWNER ACCEPTED; not yet deployed)

13H.1 was architecture only; §33.3 records the owner-approved decisions (with the owner's refinements), §33.7 the
13H.2 implementation, §33.8 the 13H.3 API contract, §33.9 the 13H.4 execution-safe WorkPlan mutations, §33.10 the 13H.5 mobile execution and confirmation UX. Baseline: `stage-13` = `origin/stage-13`
= `e702d71`, Alembic head `0029_application_fingerprint`. D10/D12 (execution tracking in Stage 13, keyed by
`occurrence_key`, outside the plan payload; calendar/reminders Stage 18) stay binding.

### 33.1 Audit findings (code as of `e702d71`)

**Identity (`SurfacePlannedWork.occurrence_key`).**
- NOT NULL, globally unique (`uq_surface_planned_works_occurrence_key`), always server-generated (`uuid4`
  in `_rewrite_works`, `apply_template` APPEND, `append_one_planned_work_no_commit`); never client-generated.
- Validated in `_validate_occurrence_keys` before any mutation: duplicate in one payload → 422; not a CURRENT
  key of this plan (invented / removed / another plan's / another owner's — indistinguishable) → 409; known key
  with a different PriceItem → 422. So a key is bound to one PriceItem for life; "changing the operation" is
  remove + add.
- A removed key is never reused: it is no longer current, so echoing it is a 409, and every creation path mints
  a new key. Duplicate PriceItems are distinguished only by their keys.
- The Estimate snapshots the key (`estimate_lines.occurrence_key`, nullable, **no FK**, unique per estimate) and
  matches id → key → legacy (§24). Coefficient assignments hang off the row (`ON DELETE CASCADE`) and are
  recreated with it.
- **Conclusion:** `occurrence_key` is sufficient as the durable execution identity. No second identity is needed.

**Row replacement.** Mixed behaviour, by path:

| Path | Rows | Keys |
|---|---|---|
| PUT work-plan (`set_plan`, `replace_planned_works`) | ALL rows deleted + recreated (`_rewrite_works`, raw DELETE) | echoed keys preserved; key-less entries get new keys; omitted keys disappear |
| Legacy PUT `price_item_ids` | all rows recreated | **every key is new** (no Surface client sends this any more; `RevealWorkPlanEditor` uses it for reveal works, a different model) |
| apply-template APPEND | existing rows untouched; new rows inserted | existing keys kept; new keys |
| apply-template REPLACE | all rows recreated | all old keys removed; new keys |
| apply-to-all walls | **each target wall's rows are all recreated** | targets' old keys removed; new keys (source keys never copied) |
| Stage 11 recommendation accept | one row inserted | new key, no wait |

Locking: `apply_template` and recommendation acceptance take `lock_plan` (`SELECT … FOR UPDATE`); **`set_plan`,
`replace_planned_works` and `apply_to_room_walls` do not.**

**Other.** Surfaces, rooms and projects are only soft-archived (`is_archived`); there is no API hard delete of
a project/room/surface/plan (the FK cascades exist but are never triggered by the API). The Estimate ignores
archived surfaces. WorkPlan PUT does not check surface archive state. Timestamps are `DateTime(timezone=True)`,
server-generated `datetime.now(timezone.utc)`. Errors are `HTTPException` 404/409/422 with non-leaking ownership
chain checks (project → room → surface). Existing optimistic-concurrency style = "echo what you saw"
(`expected_step_ids`, `expected_occurrence_keys`). Reveal planned works (per opening) have **no**
`occurrence_key`.

### 33.2 Key analysis

- **Execution state must live outside `surface_planned_works`** (§4.5): rows are recreated on every save, and
  status in the save payload would let a stale draft overwrite on-site progress. A server-side carry-over of
  status columns inside `_rewrite_works` would work for kept keys but still deletes state on removal.
- **Removal.** Options: (1) cascade-delete — simple, but an accidental edit or REPLACE silently destroys proof
  that work was done; (2) retain as detached history — auditable, supports a later journal/PDF, tiny data growth
  (one row per executed occurrence); (3) soft-orphan flag — like (2) plus a redundant column, because
  "detached" can be derived as "key not in the current plan". **Recommend (2), without a flag column**, plus an
  explicit confirmation guard (§33.3 D-H7) so removal is never silent. Re-adding a work creates a new key in
  NOT_STARTED; it does not restore the old record.
- **APPEND.** No hidden complication: existing rows are not even rewritten; new occurrences start NOT_STARTED.
  (If an acknowledgement field is ever added to `ApplyTemplateRequest`, include it in the fingerprint only when
  sent, as with `selected_step_ids`, so recorded retries remain idempotent.)
- **REPLACE.** Removes all current keys, including executed ones. Keep REPLACE possible (owner control), keep
  history (detached), and require the confirmation to name the executed works being removed.
- **Apply-to-all.** Source execution is never copied (new keys, no execution rows → NOT_STARTED). Hidden risk:
  it silently deletes the **target walls'** occurrences; if a target wall has executed works, that must be
  confirmed like any other removal.
- **Recommendation accept.** New key, no execution row → NOT_STARTED. Never infers progress.
- **Coefficients / Estimate.** Separate table; no pricing code reads it; row recreation, Estimate generation or
  regeneration, overrides and coefficient edits never touch it. No progress billing in 13H.

### 33.3 Decision matrix — OWNER APPROVED (2026-09-27)

| ID | Approved decision | Alternatives rejected | Consequences |
|---|---|---|---|
| D-H1 Identity | `SurfacePlannedWork.occurrence_key`; no second identity; `SurfacePlannedWork.id` stays ephemeral | new execution identity | Durable, unique, never reused, owner-scoped via its plan |
| D-H2 Persistence | Separate current-state table `surface_work_executions`; nothing on `SurfacePlannedWork`; no event sourcing in v1 | columns on planned work; event log | Survives row recreation while the key survives; history kept on removal |
| D-H3 Status | `NOT_STARTED` / `IN_PROGRESS` / `COMPLETED`; no SKIPPED/CANCELLED/BLOCKED in v1; **no row = NOT_STARTED** | PLANNED/…; derived from timestamps | Simple aggregation; additive later statuses; DB CHECKs tie status to timestamps |
| D-H4 Timestamps | `started_at`, `completed_at`: UTC, server-generated, not editable in v1. **They record when the state was entered in the application, not proof of the physical moment the operation started or ended** | client/manual times | Honest semantics for a journal/PDF later |
| D-H5 Transitions | NOT_STARTED→IN_PROGRESS; IN_PROGRESS→COMPLETED; COMPLETED→IN_PROGRESS (reopen); IN_PROGRESS→NOT_STARTED (reset); shortcut NOT_STARTED→COMPLETED sets `started_at = completed_at = now` atomically. **COMPLETED never has `started_at` NULL** | require START first; COMPLETED with NULL start | Fast "mark done" on site with a complete persisted state |
| D-H6 Reopen/reset | Reopen keeps `started_at`, clears `completed_at`. Reset clears `started_at`. **COMPLETED→NOT_STARTED is not a transition** (reopen first) | direct reset | The overwritten time is not kept in v1 (D-H22) |
| D-H7 Removal/history | Records of started/completed occurrences survive removal as detached history (detached = key not in the current plan; **no flag column**). Never resurrected: re-added work gets a new key, NOT_STARTED. Destructive WorkPlan operations require an exact confirmation set `confirm_execution_detach_keys` = exactly the started/completed current keys the mutation would detach; any difference (concurrent change, new affected occurrence) → 409 and a fresh confirmation. A bare boolean is not accepted | cascade delete; boolean confirmation | No silent loss; stale-safe |
| D-H8 APPEND | Existing occurrences keep key and state; new ones get new keys, NOT_STARTED; nothing copied or inferred | — | Additive path, no confirmation |
| D-H9 REPLACE | Allowed; the D-H7 exact confirmation applies when it would remove started/completed occurrences; detached history retained; new occurrences NOT_STARTED | block REPLACE | Owner control, no silent loss |
| D-H10 Apply-to-all | Never copies execution; destinations get new keys, NOT_STARTED; replacing destination works that are IN_PROGRESS/COMPLETED requires the D-H7 exact confirmation | skip/block walls | Destination progress never silently destroyed |
| D-H11 Recommendations | Accepted recommendation → new key, NOT_STARTED; nothing inferred | — | — |
| D-H12 Readiness | `ready_after = completed_at + current wait_after_hours`, only for COMPLETED with a break; computed on read, never persisted; follows later wait edits. Technological information only; not a scheduled start, calendar event, reminder or appointment (Stage 18) | persist | No duplicated data |
| D-H13 Predecessors | No enforcement and no warning in v1 | warn; hard block | The owner controls real sequencing |
| D-H14 WorkPlan edits | Without confirmation: wait, reorder, add, quality target, substrate, coefficients, APPEND. Exact confirmation: removing current started/completed occurrences (ordinary removal, REPLACE, apply-to-all). Nothing hard-blocked because execution started | warnings on quality/substrate | Minimal friction |
| D-H15 Commercial isolation | Execution never affects PriceItem price, coefficient, Estimate quantity/unit/effective price, overrides or regeneration; no progress billing | — | Verified by tests |
| D-H16 API | Dedicated execution mutation endpoint; never via the WorkPlan save payload; may be embedded read-only in WorkPlan responses; the editor cannot overwrite it | status in the plan payload | 13H.3 |
| D-H17 Concurrency | Transition: lock the plan row, verify the key is current, compare `expected_status`, apply atomically. Destructive WorkPlan paths take the same lock (ordinary save/replace, REPLACE where necessary, apply-to-all); existing template-apply and recommendation locks kept. No version column unless `expected_status` proves insufficient | version column | Guards in 13H.4 |
| D-H18 Idempotency | Current == requested → success, timestamps unchanged; current ≠ expected → 409; invalid transition → 409; unknown/invented/stale/foreign key → existing non-leaking semantics; invalid status syntax → 422 | — | Safe retries |
| D-H19 Archive | Archive preserves state; reads work; mutation on an archived project/room/surface rejected (project convention: 422 validation); restore exposes the state unchanged | allow mutation | — |
| D-H20 Bootstrap | No row = NOT_STARTED; the migration creates no rows; a row is created lazily on the first transition away from NOT_STARTED and **kept** on reset | backfill | Zero data migration; no hook in any creation path |
| D-H21 Mobile UX | Separate **Realizacja / Выполнение** view; the editor shows only a compact read-only badge. Statuses: Zaplanowano / W trakcie / Wykonano (RU Запланировано / В работе / Выполнено). Main actions: Rozpocznij, Oznacz jako wykonane (RU Начать, Отметить выполненной); COMPLETED has no permanent primary action. Secondary under progressive disclosure, explicit: Wznów pracę / Возобновить работу (COMPLETED→IN_PROGRESS), Zresetuj status / Сбросить статус (IN_PROGRESS→NOT_STARTED); no generic "undo" | controls in editor cards | 13H.5 |
| D-H22 Future history | v1 = current state + timestamps; a future append-only `surface_work_execution_events` may be added; today's schema/API must not prevent it | events now | — |
| Scope | v1 = `SurfacePlannedWork` only. `OpeningRevealPlannedWork` has no `occurrence_key`; no reveal execution identity is invented in 13H (later dedicated extension) | — | — |

### 33.4 Model (implemented in 13H.2)

`surface_work_executions` (migration `0030_surface_work_executions`):

| Column | Type | Rule |
|---|---|---|
| `id` | UUID PK | |
| `occurrence_key` | UUID NOT NULL | `uq_surface_work_executions_occurrence_key` UNIQUE; **no FK** (planned-work rows are recreated; precedent `estimate_lines.occurrence_key`) |
| `work_plan_id` | UUID NOT NULL | FK → `surface_work_plans.id` `ON DELETE CASCADE` (ownership chain/lifecycle; the API never deletes plans); indexed |
| `price_item_id` | UUID NOT NULL | FK → `price_items.id` `ON DELETE RESTRICT` (see §33.7 audit); indexed |
| `status` | enum `workexecutionstatus` | NOT_STARTED / IN_PROGRESS / COMPLETED |
| `started_at`, `completed_at` | timestamptz NULL | server UTC |
| `created_at`, `updated_at` | timestamptz | |

CHECK `ck_surface_work_executions_status_timestamps`: NOT_STARTED ⇒ both NULL; IN_PROGRESS ⇒ started NOT NULL,
completed NULL; COMPLETED ⇒ both NOT NULL. CHECK `ck_surface_work_executions_completed_after_started`:
`completed_at IS NULL OR completed_at >= started_at`. No `owner_id` (ownership resolves through the plan). Later
aggregation (surface 3/5, room, object counts) = current planned works LEFT JOIN executions by key; detached rows
drop out naturally, so no schema change is needed.

### 33.5 Test strategy

Backend: state survives PUT reorder/wait/coefficient/quality/substrate edits; duplicate PriceItems stay
independent; every allowed transition plus all disallowed ones (409); idempotent repeats; stale START after
COMPLETE; stale COMPLETE after REOPEN; D-H7 guard on PUT removal / legacy `price_item_ids` save / REPLACE /
apply-to-all targets (409 without, success with exact acknowledgement, 409 on a changed set); detached rows
retained; APPEND keeps state; apply-to-all source state not copied; recommendation append NOT_STARTED;
coefficients, waits, Estimate generate/regenerate/overrides unchanged; invented / removed / other-surface /
other-owner key → identical 409; archived surface/room/project → 422 and read still works; pre-13H plans read
as NOT_STARTED; migration up/down/up on a scratch DB. Frontend: badges and actions per status; pending and
error states; 409 → reload; duplicates independent; the confirmation dialogs; wait and coefficient display
coexistence; PL/RU; 320/390/412/480 px.

### 33.6 Proposed sub-stages

| Sub-stage | Scope | Migration | STOP gate |
|---|---|---|---|
| 13H.2 | Model + enum + CHECKs + migration `0030`; domain service: read (absent = NOT_STARTED), transitions, idempotency, key-current check under lock; readiness derivation | **yes** | pytest + scratch-DB up/down/up |
| 13H.3 | API: PATCH execution endpoint, embedded read on plan responses, error mapping; frontend types only | no | API tests incl. ownership/stale/archived |
| 13H.4 | WorkPlan mutation guards: plan lock in `set_plan` / `replace_planned_works` / `apply_to_room_walls`; D-H7 acknowledgement on PUT, REPLACE, apply-to-all | no | guard + regression suites (13B–13G, Estimate) |
| 13H.5 | Mobile UI: Realizacja view, editor status badge, confirmation dialogs, 409 handling, PL/RU | no | vitest, tsc, build, mobile 320–480 |
| 13H.6 | Integration/adversarial verification | no | full gates |
| 13H.7 | Owner walkthrough → commit/push/deploy (with migration assessment) | apply 0030 | owner PASS, production verification |

### 33.7 Stage 13H.2 — persistence / domain foundation

**PriceItem lifecycle audit (before 0030).** PriceItems are archive-only: `PriceBookService.archive_item` /
`restore_item` toggle `is_archived`; there is no hard-delete service or API route; the only deletion path is
`price_items.owner_id → users.id ON DELETE CASCADE` (whole-account deletion, which also cascades the owner's
projects → … → plans → executions). Existing references: `surface_planned_works`, `workflow_template_steps`,
`opening_reveal_planned_works` RESTRICT; `estimate_lines`, `work_recommendations` SET NULL; market evidence
CASCADE. Conclusion: detached history can safely reference the PriceItem with **RESTRICT, NOT NULL**, mirroring
`surface_planned_works` (every record always identifies its operation; a future hard-delete feature would have
to address planned works and history together). A `price_item_id` reference alone is enough: the plan itself
shows live PriceItem names (never snapshots), archived items remain readable, and execution is not a commercial
document. **No name/code snapshot** is added (Estimate lines snapshot because they are commercial documents).

**Implementation.** `app/models/work_execution.py` (`WorkExecutionStatus`, `SurfaceWorkExecution`),
`alembic/versions/0030_surface_work_executions.py` (empty table, indexes, CHECKs; downgrade drops table and
enum type), `app/domain/services/work_execution_service.py`:
- `transition(project, room, surface, owner, occurrence_key, status, expected_status)`: existing ownership chain
  (404s) → archived project/room/surface → `WorkExecutionValidationError` (422) → `lock_plan` → key must be
  current in that plan, else the existing `SurfaceWorkPlanOccurrenceConflictError` (same message for invented /
  removed / other-surface / other-owner keys, or no plan) → same status → no-op (commit only releases the lock)
  → stale `expected_status` or disallowed pair → `WorkExecutionConflictError` (409, carries the current status)
  → apply (§33.3 D-H5/D-H6) and commit. The row is created lazily with the occurrence's `price_item_id`.
- `get_plan_executions(...)`: views for the CURRENT occurrences in plan order (absent row = NOT_STARTED);
  detached records are not listed; allowed on archived parents.
- `derive_ready_after(status, completed_at, wait_after_hours)`: D-H12, computed on read.
- No API, no WorkPlan guards/locks (13H.4), no UI. Plan saves, APPEND/REPLACE, apply-to-all, recommendation
  accept and the Estimate were not changed.

**Verification.** `tests/test_stage13h_execution.py` 31 passed; WorkPlan / occurrence / apply-template / 13E /
13G / coefficient / Estimate-identity / recommendation-accept regressions 270 passed; full backend 1581 passed.
Scratch PostgreSQL (throwaway DB on the owner's local server, dropped afterwards): seeded at 0029 → `upgrade
head` (existing plans, planned works, PriceItems, coefficient assignments and Estimate lines byte-identical; 0
execution rows) → CHECK / UNIQUE / FK actions / enum verified → service transitions on PostgreSQL → `downgrade
-1` (table and enum type gone, data identical) → `upgrade head`. Alembic head `0030_surface_work_executions`.

### 33.8 Stage 13H.3 — execution API and read contract

**Read (embedded, read-only).** Every `SurfacePlannedWorkRead` in every WorkPlan response (GET/PUT work-plan,
apply-template, apply-to-room-walls targets) carries:

```json
"execution": { "status": "NOT_STARTED", "started_at": null, "completed_at": null, "ready_after": null }
```

`SurfaceWorkPlanService._fetch_plan` (the single read path of all those responses) attaches each CURRENT
occurrence's view from one query over the current keys: no row → NOT_STARTED with null timestamps and **no row
created**; detached records are never reached. `ready_after` = `completed_at + wait_after_hours` only when
COMPLETED with a break (D-H12), else null; never stored. Timestamps use the existing plain `datetime`
serialization (PostgreSQL: UTC, ISO 8601 with `Z`; verified identical for PATCH and read on a scratch PostgreSQL
DB). The pure rules (`ALLOWED_TRANSITIONS`, `derive_ready_after`, `execution_view`) moved unchanged from the 13H.2
service to `app/domain/rules/work_execution_rules.py` so the WorkPlan read path and the execution service share
them without importing each other; the service re-exports them.

**Write (dedicated endpoint only).**
`PATCH /api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/work-plan/occurrences/{occurrence_key}/execution`

- Request `SurfaceWorkExecutionTransition` (`extra="forbid"`): `{"status": <WorkExecutionStatus>, "expected_status":
  <WorkExecutionStatus>}`, both required. Timestamps, `ready_after` and anything else → 422.
- Response 200 `SurfaceWorkExecutionRead`: `{occurrence_key, status, started_at, completed_at, ready_after}`.
- Thin route → `SurfaceWorkExecutionService.transition` (no transition logic in the route).

| Case | Response |
|---|---|
| allowed transition from the expected status | 200, new state |
| requested status == current status (any `expected_status`) | 200, unchanged, timestamps untouched, no row created |
| stale `expected_status` or disallowed transition (e.g. COMPLETED→NOT_STARTED) | **409** `{"detail": {"code": "WORK_EXECUTION_CONFLICT", "message": …, "current_status": "COMPLETED"}}` |
| key not a current occurrence of this surface's plan (invented, removed/detached, other surface/plan, other owner's) or no plan | **409** plain-string detail, identical to the WorkPlan-save occurrence conflict (D13); no execution data, no `current_status` |
| foreign or missing project / room / surface | existing 404 chain |
| archived project / room / surface | 422; reads keep working; restore makes it mutable again with the state unchanged |
| invalid enum / missing field / extra field | 422 |

The `current_status` of a conflict is exposed only after the key is proven current in the caller's own plan (case A);
non-current keys (case B) never reveal anything.

**Write safety.** `OrderedPriceItemSelection` and `SurfaceWorkPlanUpsert` keep `extra="forbid"`: `execution`,
`status`, `started_at`, `completed_at`, `ready_after` sent per planned work or at top level → 422 with nothing
changed; echoing a read-response planned work verbatim into PUT → 422. The frontend editor builds its payload
field by field (unchanged). No frontend change in 13H.3 (the added response field is ignored by the current
types/UI; types come with 13H.5).

**Not changed in 13H.3:** WorkPlan save / REPLACE / apply-to-all confirmation and locking (13H.4), UI (13H.5),
no migration (head `0030_surface_work_executions`).

**Verification.** `tests/test_stage13h_execution_api.py` 31 passed (read matrix incl. APPEND / REPLACE /
apply-to-all / recommendation, mutation matrix, non-leaking keys, archive, write safety, isolation of coefficients,
PriceItems, Estimate lines/regeneration, waits and ordering); `test_surface_work_plan_api` route-family registry
extended by the new route; focused regressions 363 passed; full backend suite (see progress).

### 33.9 Stage 13H.4 — execution-safe destructive WorkPlan mutations

**Destructive-path audit.**

| Path | Class | Guard |
|---|---|---|
| `PUT …/work-plan` → `set_plan` (incl. legacy `price_item_ids`, and a Stage 13C REPLACE intent) | A: detaches every current key not echoed | yes |
| `SurfaceWorkPlanService.replace_planned_works` (service only, no route) | A | yes |
| `POST …/apply-template` REPLACE | A: detaches all current keys | yes |
| `POST …/apply-template` APPEND | C: appends only | exact-set rule with an empty protected set |
| `POST …/apply-to-room-walls` | A for every target wall (all target keys replaced); source untouched | yes |
| Stage 11 recommendation accept (`append_one_planned_work_no_commit`) | C | none needed |
| Project / room / surface archive | soft `is_archived` only; no planned work deleted | none (reads work; execution mutation 422, §33.8) |
| Any other delete of `surface_planned_works` | none exists (only `_rewrite_works`; reveal works are a separate model) | — |

**Protected-detach algorithm** (`SurfaceWorkPlanService._assert_execution_detach_confirmed`, one helper for all
paths): `removed = current occurrence_keys − resulting occurrence_keys` per target plan (by key only — never
PriceItem, row id or position; duplicates stay independent); `protected = removed` whose execution status is
**IN_PROGRESS or COMPLETED** (`PROTECTED_STATUSES`; an explicit NOT_STARTED row is not protected). Proceed only if
`set(confirm_execution_detach_keys) == protected` (`detach_confirmation_matches`): omitted/empty with nothing
protected → proceed; missing, subset, superset, stale, foreign or unrelated keys → 409. Nothing is mutated on
409, and a confirmed detach deletes nothing: the records stay as detached history (omitted from plan responses,
not mutable — non-leaking 409, §33.8).

**Request contract.** Optional `confirm_execution_detach_keys: list[UUID]` on `SurfaceWorkPlanUpsert` (default
`[]`), `ApplyTemplateRequest` (default `null` = not sent) and the new optional body `ApplyToRoomWallsRequest`
(default `[]`; omitting the body stays valid, so the current client is unchanged). Set semantics: duplicates → 422,
invalid UUIDs → 422, order irrelevant; `extra="forbid"` kept everywhere. Apply-to-all uses **one flat set** across
all target walls: keys are globally unique, so a key identifies its wall unambiguously, and each `affected` entry
carries its `surface_id` for display.

**409 contract** (distinct from `WORK_EXECUTION_CONFLICT`, domain error `ExecutionDetachConfirmationRequiredError`):

```json
{"detail": {"code": "WORK_EXECUTION_DETACH_CONFIRMATION_REQUIRED", "message": "...",
  "affected": [{"surface_id": "...", "occurrence_key": "...", "position": 1, "status": "COMPLETED",
                "price_item_id": "...", "price_item_code": "...", "price_item_name_key": null,
                "price_item_display_name": "Gładź"}]}}
```

`affected` = the CURRENT protected records of the caller's own target plan(s), in lock order then position —
enough for the 13H.5 dialog (wall, numbered work, label via name_key/display_name/code, status) without a
race-prone client reconstruction. It is built only from the target plans; confirmation keys are compared, never
resolved, so a foreign key only causes a mismatch and nothing about it is returned. `affected` may be empty (the
request confirmed keys that nothing would detach).

**Locking.** Every path runs lock → read current occurrences → read execution → compute → validate → mutate →
commit in one transaction under the same `SurfaceWorkPlan` row lock (`SELECT … FOR UPDATE`) that execution
transitions take (§33.8): `set_plan` and `replace_planned_works` now call `lock_plan` before reading the plan;
`apply_template` already locked; apply-to-all locks **every existing target plan in ascending plan id**, one at
a time, before reading any of them (targets without a plan are created in the same transaction, as before). Every
other path locks exactly one plan, so ascending order across multi-plan applies is deadlock-free. Consequence: a
work that becomes IN_PROGRESS/COMPLETED before the destructive transaction reads the plan is always in the
protected set; one that tries to transition after it is blocked until commit and then gets the non-leaking 409 if
its key was removed.

**Ordinary save.** Key-preserving saves (reorder, waits, quality target, substrate, coefficients, adding works)
never need confirmation and leave execution untouched. Removing started/completed works needs their exact keys.

**Template apply and idempotency.** APPEND never needs confirmation (a non-empty one is an exact-set mismatch).
REPLACE over started/completed works needs their exact keys. Order inside `apply_template`: plan lock →
recorded-application check (idempotent retry returns 200 before any guard, so a retry after success is never
re-evaluated against the new plan) → template/step/composition checks → detach guard → mutation + one history
record. A refused request records nothing, so the owner may resend the SAME `application_id` with the confirmation.
`confirm_execution_detach_keys` joins the fingerprint **only when sent** (sorted), like `selected_step_ids`: every
pre-13H.4 fingerprint is unchanged; an identical confirmed retry is idempotent; reusing the id with a different
request (e.g. without the keys) is the existing 409 conflict and never a second application.

**Apply-to-all.** Source execution is never copied (targets get new keys, NOT_STARTED). Target walls whose current
works are all NOT_STARTED need no confirmation; started/completed target works across all walls must be confirmed
exactly; the whole batch is all-or-nothing.

**Verification.** `tests/test_stage13h_detach_guard.py` 23 passed (ordinary save incl. the owner's A/B/C example,
subset/superset/stale/foreign keys, schema, key-preserving saves, duplicates, legacy `price_item_ids`, service
`replace_planned_works`; APPEND/REPLACE incl. no history on 409, exactly one on success, idempotent retry,
unchanged pre-13H.4 fingerprint; apply-to-all aggregation/partial/exact/detached/source; ascending lock order;
recommendation). 13H.2/13H.3 tests that removed started/completed works now send the exact confirmation (62
passed). PostgreSQL concurrency harness on a throwaway DB (SQLite has no row locks; not part of the pytest suite):
a transaction holding the plan lock with an uncommitted COMPLETED transition blocks an ordinary destructive save,
a REPLACE and an apply-to-all, each of which then refuses with the affected key (no application recorded); a
transition blocked behind a destructive save gets the non-leaking 409 afterwards; 15 rounds × 4 concurrent
overlapping apply-to-all: 0 deadlocks, 0 errors — 15/15 checks.

### 33.10 Stage 13H.5 — mobile execution UI and detach-confirmation UX (frontend only)

**Entry.** Every surface card (walls and other surfaces in `SurfaceList`, floor/ceiling planes in
`AreaSegmentList`) gets **Realizacja / Выполнение** next to *Rodzaje prac i jakość*, same size/style. The two open
exclusively (one per list at a time), so neither shows stale data after the other mutates. No new navigation.

**Execution view** (`SurfaceExecutionView`). Loads the WorkPlan (GET) and renders every CURRENT occurrence as its own
numbered card (duplicates separate; detached records never appear): name (owner names verbatim, seeded names via
the locale), status badge **below** the name (a badge beside a long name squeezed it into mid-word breaks at
320 px), the 13G break line, *Rozpoczęcie zapisano / Начало отмечено* and *Ukończenie zapisano / Выполнение
отмечено* (recorded-in-app wording, D-H4), and for COMPLETED with a break a *Gotowe do dalszych prac po / Следующие
работы можно выполнять после* block with *Na podstawie ustawionej przerwy technologicznej. / На основании
заданного технологического перерыва.* (informational: no timers, reminders or blocking). Dates: device time
zone, `pl-PL`/`ru-RU` short date+time (`utils/executionFormat.ts`; an offset-less value is read as UTC). Empty
states (no saved plan / no works) explain and offer *Przejdź do planu prac*, which opens the editor. Nothing is
created client-side.

**Actions.** One full-width primary per status: NOT_STARTED *Rozpocznij / Начать*, IN_PROGRESS *Oznacz jako
wykonane / Отметить выполненной*, COMPLETED none. Under *Opcje*: NOT_STARTED *Oznacz od razu jako wykonane /
Сразу отметить выполненной* (the approved direct-complete PATCH), IN_PROGRESS *Zresetuj status / Сбросить
статус*, COMPLETED *Wznów pracę / Возобновить работу*. Each is an immediate `PATCH …/execution` with the displayed
status as `expected_status`; while pending every action of the view is disabled (synchronous in-flight guard +
disabled buttons, *Zapisywanie statusu...*); the card is updated only from the server response (no optimistic
state, no client timestamps). `WORK_EXECUTION_CONFLICT` → *Status tej pracy zmienił się w innym miejscu. Dane
zostały odświeżone.* and a reload of the plan; never retried. Other errors keep the displayed state, show a
localized message on the card and allow retry (archived hierarchy 422 → `errors.execution_archived`).

**Status badge** (`ExecutionStatusBadge`): symbol + word (○ Zaplanowano / ◐ W trakcie / ✓ Wykonano; RU
Запланировано / В работе / Выполнено), never color alone; only Telegram theme tokens (no hardcoded light pairs).

**Editor.** Each saved occurrence shows the read-only badge; a row added in the draft shows *Nowa praca — status po
zapisaniu planu* instead of a fabricated status. The editor has no execution controls and never sends execution
back.

**Typed errors.** `ApiError` now keeps the raw structured `detail` and takes `code` from `detail.code`
(string-detail patterns unchanged). `parseExecutionDetachConfirmation` (code + structured `affected`, never text)
and `isWorkExecutionConflict` distinguish the two 13H conflicts from the stale-plan 409, 422 validation and
unknown errors.

**Detach confirmation** (`ExecutionDetachDialog`): a blocking modal sheet (the draft cannot change underneath)
listing the server's `affected` entries (number + name + status; for apply-to-all also the target wall's name,
supplied by `SurfaceList`, fallback *Inna powierzchnia*). Text: the change removes started/completed works from the
CURRENT plan; their history is kept and the plan will no longer show them as current — never "deleted". Confirm
retries the ORIGINAL request with exactly the returned keys; a further detach 409 re-opens the dialog with the NEW
list and *Stan prac zmienił się od ostatniego potwierdzenia…* (never auto-confirmed); an empty list explains that
nothing is detached any more and retries with `[]`. Cancel retries nothing and keeps the draft.
- Ordinary save: the exact sent payload (all unsaved changes) is retried with `confirm_execution_detach_keys`.
- Template REPLACE: the keys are stored on the current apply attempt, outside its signature, so the retry keeps the
  SAME `application_id` and the same semantic request (13E idempotency); a transport retry resends them; cancel
  clears them (a later Apply asks again). APPEND never shows the dialog.
- Apply-to-all: one dialog for all target walls; the retry sends the flat key set in the optional body.

**Verification.** Vitest: `SurfaceExecutionView.test.tsx` 15, `ExecutionDetachConfirm.test.tsx` 11, Realizacja entry
tests in `SurfaceList.test.tsx` (2) and `AreaSegmentList.test.tsx` (1); full frontend 1281 passed; `tsc` and
`vite build` PASS. Real browser (headless Chromium over CDP; throwaway PostgreSQL DB + real backend with mock auth +
Vite dev server; Telegram WebApp stub pinned so real Telegram light/dark theme params apply): PL/RU × light/dark ×
320/390/412/480 — no horizontal overflow, no clipped text or buttons, every control ≥ 44 px in the execution view,
editor list and both real server-driven detach dialogs (save, apply-to-all); screenshots inspected. Text contrast
follows Telegram's own palette pairs exactly as the existing editor does (hint text on bg, white on `button_color`);
no light-only pairs. End-to-end on the real API: start → complete → reopen → reset → direct complete, a conflict
created by another session (message + refresh, no retry), confirmed ordinary-save detach, confirmed apply-to-all
(targets NOT_STARTED, detached history kept in the DB) — 13/13. No backend change in 13H.5.

- **Status:** 13H.5 PASS / OWNER ACCEPTED (owner walkthrough). All uncommitted.

### 33.11 Stage 13H.5B — bulk execution status across room walls (ARCHITECTURE APPROVED; 13H.5B.1 OWNER ACCEPTED; 13H.5B.2 implemented)

Goal: "I have just done this operation on every wall of this room" — carry the source wall's execution progress
forward to the matching works of the other walls of the same room. Execution status only: no WorkPlan row, key,
wait, coefficient or Estimate change; not the WorkPlan apply-to-all; not a general sync engine.

**Audit facts.** Walls of a room typically hold the same ordered plan (WorkPlan apply-to-all and templates
materialise identical PriceItem sequences), but every wall has its own `occurrence_key`s (D-H10), so keys cannot
match across walls. Occurrences carry no per-occurrence template-step provenance (application history is
plan-level). Deterministic "(PriceItem, k-th duplicate by position)" matching already exists as the Stage 12 /
13E.2B Estimate legacy fallback (`_match_surface_lines`). Scope rules exist in `apply_to_room_walls` (same room,
`WALL`, not archived, not the source). Execution writes go through the 13H.2 transition rules; plans are locked
with `SELECT … FOR UPDATE`, multi-plan locks in ascending plan id (§33.9).

**Matching algorithm (per destination wall).** Group each plan's CURRENT occurrences by `price_item_id` in position
order; the k-th source occurrence of PriceItem P pairs with the k-th destination occurrence of P. Relative order of
different PriceItems is irrelevant. If P occurs a different number of times on the two walls, P is **ambiguous** on
that wall: none of its occurrences are touched and they are reported. A source occurrence with no destination P is
**unmatched** (reported); destination works with no source P are untouched. Keys, timestamps, `ready_after`,
coefficients and waits are never read from the source for writing.

**Transition rule.** Rank NOT_STARTED 0 < IN_PROGRESS 1 < COMPLETED 2. For a matched pair, act only if
destination rank < source rank: NS→IP (`started_at = now`), NS→C (direct complete, `started_at = completed_at =
now`), IP→C (keep destination `started_at`, `completed_at = now`). Equal or further destination → unchanged. One
server `now` for the whole operation. Source NOT_STARTED never acts.

Owner approved BULK-H1…H10 as below, with the BULK-H7 refinement (exact ordered snapshot of ALL source occurrences).

| ID | Decision | Alternatives | Consequences |
|---|---|---|---|
| BULK-H1 matching identity | (price_item_id, ordinal among that PriceItem's occurrences by position) on current occurrences | occurrence_key (differs per wall); position (breaks when one wall has an extra/moved work); plan-level template provenance (not per occurrence) | Deterministic, order-independent across PriceItems, reuses an existing precedent; destination key stays the only execution identity |
| BULK-H2 duplicates | Pair by ordinal only when the PriceItem's count is EQUAL on both walls; otherwise the PriceItem is ambiguous on that wall and skipped (reported) | always pair by ordinal (1st↔1st even when counts differ) | Conservative: never guesses which "Gładź" a lone destination Gładź is; identical plans (the real case) match fully |
| BULK-H3 source NOT_STARTED | No destination mutation | propagate as reset | Nothing is undone |
| BULK-H4 backward | Never: forward-only (NS→IP, NS→C, IP→C) | mirror the source state | Later destination progress is never lost; reopen/reset stay per-wall actions in Realizacja |
| BULK-H5 partial/mismatched | Fewer destination works → unmatched reported; extra destination works untouched; different order fine; different PriceItem = no match; wall without a plan/works → reported, untouched | refuse the whole operation on any mismatch | Safe partial application is explicit in preview and result, never a hidden success |
| BULK-H6 timestamps | Server-generated per destination transition (13H.2 rules); nothing copied | copy source times | D-H4 holds: each wall records when it was marked in the app |
| BULK-H7 concurrency | Lock source + all existing target plans in ascending plan id, then read plans and executions fresh; the request carries `expected_source` = the EXACT ORDERED snapshot of ALL current source occurrences (keys + statuses, NOT_STARTED included; any key/order/count/status difference) → 409 `WORK_EXECUTION_SOURCE_CHANGED` if the locked source differs; destinations are recomputed from locked state (forward-only makes that safe) | no source check; per-destination expected states (heavy) | The confirmation summary can only under-state what happens to destinations, never propagate source progress the owner did not see |
| BULK-H8 archive | Archived source wall / room / project → 422 (execution convention); archived target walls excluded from scope (as WorkPlan apply-to-all) | include archived targets | Archived history untouched |
| BULK-H9 atomicity | One transaction, one commit, all-or-nothing | per-wall commits / N frontend PATCHes | No half-applied room; one ownership check |
| BULK-H10 UI confirmation | Preview first (no mutation) → summary sheet (walls, statuses that will change, unchanged-because-further, unmatched/ambiguous counts, explanation) → confirm; no key lists to confirm; 0 changes → info only, no confirm | confirm per key; no preview | Fast one-tap field flow with honest numbers |

**Endpoints** (repository precedent: `regenerate-preview` / `regenerate`):
- `POST /api/projects/{p}/rooms/{r}/surfaces/{source_surface_id}/work-plan/execution/apply-to-room-walls-preview` —
  no body, no mutation, no locks; returns the summary below.
- `POST …/work-plan/execution/apply-to-room-walls` — body `{"expected_source": [{"occurrence_key", "status"}]}`
  (exact current source list, `extra="forbid"`); returns the same shape as the applied result.
- Result: `{source_surface_id, changed, unchanged, unmatched, ambiguous, walls: [{surface_id, changed, unchanged,
  unmatched, ambiguous, has_plan}]}` — counts only (the source view stays open and unchanged; destination walls are
  refetched when opened). No detached history, no keys of other walls needed by the UI.
- Errors: existing 404 chain; non-WALL source 422; archived source/room/project 422; 409
  `WORK_EXECUTION_SOURCE_CHANGED` (with the current source statuses) — distinct from the transition and detach
  codes. Other rooms, floor/ceiling and other owners' surfaces are never in scope (query by the source's room +
  WALL + active; ownership via the existing chain).

**Locking model.** Lock set = source plan + existing target plans, acquired one by one in ascending plan id, then
`_fetch_plan` + execution rows re-read. Individual transitions, WorkPlan save and template REPLACE lock one plan;
WorkPlan apply-to-all locks its targets ascending; recommendation accept locks its recommendation row then one plan
— no lock cycles. Only `surface_work_executions` rows are written (created lazily as today).

**Proposed UI** (Realizacja, WALL surfaces with other active walls only): a secondary theme-safe full-width button
at the bottom, **"Zastosuj statusy dla pozostałych ścian" / "Применить статусы к остальным стенам"** (more
precise than "wszystkich": the source is excluded). Tap → preview → blocking sheet: "N ścian · M statusów zostanie
zmienionych", unmatched/ambiguous/already-further counts, and four lines: only matching works on the other walls of
this room; progress only moves forward; later progress is not undone; each wall records its own time. Confirm →
apply → "Zaktualizowano 9 prac na 3 ścianach." (+ "Pominięto 2 prace bez odpowiednika." when non-zero; PL/RU plural
forms via `Intl.PluralRules`). 409 source-changed → reload the view and explain. Disabled while a card transition is
pending. Same ≥ 44 px, 320–480 px and dark-theme rules as 13H.5.

**Proposed sub-steps after approval:** 13H.5B.1 backend (matching helper, preview + apply service, endpoints, pytest
incl. PostgreSQL locking/concurrency harness); 13H.5B.2 frontend (button, preview sheet, result, PL/RU, vitest,
real-browser matrix). No migration.

**13H.5B.1 implementation (backend).**
- **One engine:** `calculate_bulk_execution_plan(source, targets)` in `domain/rules/work_execution_rules.py` — pure,
  used by BOTH preview and apply (a test spies it: identical inputs from both paths). Returns per-wall counts and the
  forward transitions; transitions are executed with the same `_apply_transition` helper as the single-occurrence
  PATCH (one timestamp implementation).
- **Counts** are OCCURRENCE counts, one bucket per (source occurrence × target wall), so per wall
  `changed + unchanged + unmatched + ambiguous == number of source occurrences` (no double counting); totals are
  sums over walls. `unchanged` includes pairs whose SOURCE is NOT_STARTED and pairs whose destination is equal or
  further. `unmatched` = PriceItem absent on that wall, or the wall has no plan (`has_plan: false`). `ambiguous` =
  every source occurrence of a PriceItem whose duplicate count differs on that wall. Extra destination works are not
  counted and never touched. Per wall also `unmatched_price_item_ids` / `ambiguous_price_item_ids`.
- **Preview** `POST …/surfaces/{source_surface_id}/work-plan/execution/apply-to-room-walls-preview` (no body; no lock,
  no write) → `BulkExecutionResultRead {source_surface_id, applied: false, expected_source: [{occurrence_key,
  status}] (server-canonical, all current source occurrences in position order), changed, unchanged, unmatched,
  ambiguous, walls: [{surface_id, has_plan, changed, unchanged, unmatched, ambiguous, unmatched_price_item_ids,
  ambiguous_price_item_ids}]}`. Numbers may be stale by apply time.
- **Apply** `POST …/work-plan/execution/apply-to-room-walls`, body `{"expected_source": [...]}` (required,
  `extra="forbid"` on body and items, UUID + enum validated, duplicate key 422, empty list allowed) → same shape with
  `applied: true`, the authoritative result.
- **409** `{"code": "WORK_EXECUTION_SOURCE_CHANGED", "message", "current_source": [...]}` when the locked source
  snapshot differs in any key, order, count or status; nothing is written. Distinct from `WORK_EXECUTION_CONFLICT`
  and the detach code.
- **Scope:** ownership via the existing project → room → surface chain (404 otherwise, nothing disclosed); source must
  be a WALL (else 422) and active with its room and project (else 422, existing archive convention); targets = active
  WALLs of the same room except the source, ordered as WorkPlan apply-to-all. Floor, ceiling, OTHER, other rooms,
  archived walls and other owners are never in scope.
- **Locking / atomicity:** resolve scope → select plan ids of source + targets → lock each in ascending plan id →
  re-read plans (with execution) → validate `expected_source` → engine → write execution rows only → one commit. A
  target plan created after the id selection is treated as "no plan" (never mutated unlocked). All-or-nothing
  (a failure mid-apply leaves nothing written — tested). No detach guard (nothing is removed). Compatible with all
  other lock paths (single-plan locks; multi-plan paths ascending).
- **Never touched:** the source (statuses, timestamps, keys, plan), any plan row / key / position / PriceItem / wait /
  coefficient / substrate / quality target, template history, the Estimate. Timestamps: one server `now` per
  operation, NS→IP `started_at`, NS→C both, IP→C `completed_at` with the destination's own `started_at` kept.

**Verification.** `tests/test_stage13h_bulk_execution.py` 21 passed (forward transitions across two walls, counts,
one-wall idempotent repeat, duplicates/order/missing/extra/ambiguous/no-plan, scope incl. archived target, floor,
ceiling, OTHER, other room, non-WALL and archived source/room/project 422, other user 404, full isolation incl.
Estimate/coefficients/waits/structure/history, preview writes nothing, exact snapshot incl. status/order/set/missing
NOT_STARTED item 409s, malformed and duplicate 422, shared engine, all-or-nothing, ascending lock order incl. source);
focused regressions 454 passed; full backend 1656 passed. PostgreSQL harness on a throwaway DB (not in pytest; SQLite
has no row locks), 15/15: source transition vs apply and source WorkPlan reorder vs apply → apply blocks, then 409, no
destination write; destination transition vs apply → apply blocks, recomputes, never backward, counts from locked
state; destination WorkPlan edit vs apply → recomputed against the new structure, removed key never written; 10 rounds
of 3 overlapping applies + 1 individual transition → 0 deadlocks, only expected 409s, forward-only final state. No
migration (head `0030_surface_work_executions`), no frontend change.

**13H.5B.2 implementation (frontend, no backend change).**
- **Entry:** in Realizacja of a WALL whose room has other active walls (`SurfaceList` passes `isWall`,
  `otherActiveWallCount` and the room's surface names; floor/ceiling/other surfaces never show it) and whose plan has
  works: a secondary theme-safe full-width button at the bottom, **"Zastosuj statusy dla pozostałych ścian" /
  "Применить статусы к остальным стенам"** — deliberately not "wszystkich" and not the editor's "Zapisz dla
  wszystkich ścian" (plan composition vs. execution status).
- **Preview:** tap → `previewExecutionToRoomWalls` (button disabled + "Sprawdzanie pozostałych ścian..."; synchronous
  in-flight guard; also disabled while a card transition is pending) → `ExecutionBulkSheet` (blocking modal sheet)
  built only from the response: other walls in scope, statuses to update, unchanged (same or later stage), no
  counterpart (walls WITH a plan only), ambiguous (+ one plain-language reason), walls without a plan; the three
  rules (only matching works on the other walls of this room; forward only, later progress not undone; each wall
  records its own time) placed right under the counts so they are visible before the scrollable per-wall list;
  per wall: name + non-zero "N do aktualizacji / bez zmian / bez odpowiednika / niejednoznaczne", or "Brak planu
  prac" / "Нет плана работ" for `has_plan: false`. No keys, PriceItem ids or engine terms are shown.
- **Nothing to change** (`changed = 0`): informational sheet without a confirm button, one reason derived from the
  returned data: no other walls / the source has only planned works / matching works already equal or later /
  plans do not match enough.
- **Apply:** "Zastosuj statusy" / "Применить статусы" sends the preview's `expected_source` object verbatim (not
  rebuilt, sorted or filtered; NOT_STARTED entries kept); disabled + "Zapisywanie statusów..." while pending. The
  APPLY response is authoritative (may differ from the preview): "✓ Zaktualizowano {N} prac na {M} ścianach." with
  CLDR plural forms (PL pracę/prace/prac, ścianie/ścianach; RU работа/работы/работ, стене/стенах) where M = walls
  with `changed > 0`; a separate hint line "Nie dopasowano: x. Niejednoznaczne: y. Ściany bez planu prac: z."; with
  `changed = 0` "Nie zaktualizowano żadnej pracy." + the reason (never a success line). The source view is re-read
  from the server (unchanged) and stays open; no navigation.
- **409 `WORK_EXECUTION_SOURCE_CHANGED`:** sheet closed, source re-read, "Stan prac na tej ścianie zmienił się od
  czasu podglądu. Dane zostały odświeżone. Sprawdź je i spróbuj ponownie." — no retry, no automatic new preview.
  Generic apply error: message inside the sheet, nothing changed locally, confirm can be retried (same snapshot).
  Preview error: message under the button, retry by tapping again. The detach dialog is never involved.

**Verification.** `ExecutionBulk.test.tsx` 19 (entry/visibility, preview counts and per-wall lines, no-plan and
ambiguity text, forward-only text, no internal identifiers, double preview/apply guards, the four nothing-to-change
reasons, exact snapshot object sent, apply-response-based result incl. walls-with-changes count and skipped line, PL
plurals, changed=0 after recompute, source-changed 409 without retry, generic error + retry, cancel, RU, theme tokens
and ≥ 44 px) + `SurfaceList` entry assertion; full frontend 1300 passed; `tsc`, `vite build` PASS. Real backend
(throwaway PostgreSQL + real API + Vite + headless Chromium with pinned Telegram theme): PL/RU × light/dark ×
320/390/412/480 — no overflow, no clipped text, controls ≥ 44 px; scenarios on 5 walls: identical plan in a different
order advanced correctly with duplicates independent, an already-further wall never moved backward, a triple-duplicate
wall left its ambiguous group untouched, a wall without a plan shown as "Brak planu prac", a source change between
preview and apply gave the 409 message with refresh and no destination write, the source stayed byte-identical, and
a second preview with nothing left showed the informational sheet (RU dark 320). The explanation block was moved
above the per-wall list after the screenshot review.

**Owner walkthrough FIX.1 (diagnosis).** The owner's local walkthrough (RU) showed "Не удалось проверить остальные
стены" on the bulk button. The live local backend (`plan_estimate_backend`, image built 2026-09-27 16:07 CEST, no
source bind mount) predated 13H.5B.1 (source written 16:41–16:42): its OpenAPI listed no 13H.5B route, the container's
`work_plans.py` had no `apply-to-room-walls-preview`, and the exact frontend request `POST …/surfaces/{source}/work-plan/
execution/apply-to-room-walls-preview` (Bearer, no body) returned FastAPI's unknown-route `404 {"detail": "Not
Found"}` (also in the container access log for the owner's taps). DB migration was current (`0030`). Root cause: stale
local backend image — environment/runtime, not a code defect; no code changed. Fix: `docker compose build backend &&
docker compose up -d backend`.

After rebuilding the local backend the owner re-ran the walkthrough: PASS (3 target walls, 6 to update / 3 unchanged;
apply advanced destinations with independent timestamps; source unchanged; source NOT_STARTED reset nothing; second
preview 0 / 9 with no apply action).

- **Status:** 13H.5B COMPLETE / OWNER ACCEPTED.

### 33.12 Stage 13H.6 — final adversarial / integration verification

Verify-only; no new functionality. Baseline `e702d71` (= `origin/stage-13`); every change since belongs to Stage 13H
(backend execution model/service/rules/migration/API/guards/bulk, frontend execution/detach/bulk UI, PL/RU strings,
tests, these docs). Alembic single head `0030_surface_work_executions`.

- **Cumulative diff review** (all 21 modified + 16 new files): no unrelated change, no debug/TODO/console code, no broad
  exception catch, removed lines are only re-indentation / replaced signatures; the one unused import is a deliberate
  re-export. One style slip fixed (a missing blank line before `class ExecutionSnapshotItem`, no behaviour change).
- **Contract:** every execution/detach/bulk Pydantic schema compared field-by-field (names, required, nullability,
  enum) with the TypeScript types: identical. Deliberate difference: `SurfacePlannedWorkRead.execution` is always sent
  but optional in TS (existing fixtures; the UI renders no badge without it).
- **New gap tests** `tests/test_stage13h_final.py` (15): the full 3 × 3 forward-only bulk matrix plus explicit
  NOT_STARTED rows on either side; the owner-verified 6/3 → 0/9 case; source work added or re-keyed between preview and
  apply → 409, nothing written; Price Book, workflow templates/steps and coefficient catalog byte-identical after a
  bulk apply; a break never blocks starting the next work. Frontend: the owner case in RU (6/3, apply, 0/9 without an
  apply action).
- **Automated:** backend full suite 1671 passed; frontend 1301 passed; `tsc` PASS; `vite build` PASS; PL/RU execution
  key parity (80 keys); `git diff --check` clean.
- **PostgreSQL migration** (scratch DB, data seeded at 0029 with the pre-13H code: plans with duplicate works,
  waits, coefficients, a template + application history, an Estimate with a manual price override): 0029 → 0030 → 0029
  → 0030 with all 14 affected tables byte-identical at every step; execution table empty after each upgrade; UNIQUE,
  all status/timestamp CHECKs, `completed_at >= started_at`, PriceItem RESTRICT (history keeps its PriceItem) and plan
  CASCADE verified; downgrade drops table and enum — 16/16.
- **PostgreSQL concurrency** (scratch DBs, deterministic lock-holding interleavings): 13H.4 harness 15/15 (save /
  REPLACE / apply-to-all vs an in-flight transition, reverse order, 15 × 4 overlapping apply-to-all: 0 deadlocks);
  13H.5B harness 15/15 (source transition / source reorder / destination transition / destination edit vs bulk, 10 × 3
  overlapping bulk + 1 transition: 0 deadlocks); 13H.6 extra 4/4 (8 simultaneous identical START → all 200, one row;
  opposing COMPLETE vs RESET → one wins, the other WORK_EXECUTION_CONFLICT; 10 rounds of 2 bulk applies + 1 WorkPlan
  apply-to-all → 0 deadlocks, only ok / source-changed / detach-required outcomes). Total 34/34.
- **Real browser** (throwaway PostgreSQL + real API + Vite + headless Chromium, Telegram light/dark theme pinned):
  execution view, editor list and both detach dialogs at PL/RU × light/dark × 320/390/412/480 — no overflow, no
  undersized or clipped control; 13H.5 flows 13/13 (all transitions, conflict refresh, confirmed save detach,
  confirmed apply-to-all, detached history in DB); readiness block PL/RU; template REPLACE 9/9 (dialog lists exactly
  the started/completed works, cancel returns to the REPLACE step with nothing applied, confirm applies once, new
  keys NOT_STARTED, history kept); bulk sheet matrix clean and scenarios 14/14 (counts, ambiguity, no-plan wall,
  no-write preview, source-changed refresh without retry, forward-only results, duplicates, source unchanged,
  informational zero-change sheet).
- **Defects found:** none in behaviour. Test-script expectations corrected (not code): the bulk total after the
  source-change scenario is 9, and a cancelled REPLACE detach returns to the REPLACE confirmation step.
- Out of scope, unchanged: execution journal, notes, photos, progress billing, calendar/reminders, reveal execution,
  backward bulk sync. The known app-wide Telegram palette contrast limitation is not a 13H regression.

- **Status:** 13H.5B COMPLETE / OWNER ACCEPTED. 13H.6 VERIFICATION PASS.

### 33.13 Stage 13H — final owner acceptance

**Stage 13H — COMPLETE / OWNER ACCEPTED** (2026-09-27). 13H.1 architecture ACCEPTED; 13H.2 persistence/domain
ACCEPTED; 13H.3 API ACCEPTED; 13H.4 locking + detach protection ACCEPTED; 13H.5 execution UI ACCEPTED; 13H.5B bulk
execution across room walls ACCEPTED; 13H.6 final adversarial/integration verification PASS.

Final verification (13H.6; only documentation changed afterwards): backend 1671 passed; frontend 1301 passed;
TypeScript PASS; production frontend build PASS; Alembic single head `0030_surface_work_executions`; `git diff --check`
clean; PostgreSQL migration verification 16/16; PostgreSQL concurrency verification 34/34 with 0 deadlocks;
real-browser verification PASS; owner walkthrough PASS; bulk owner walkthrough PASS. The PostgreSQL migration and
concurrency harnesses are scratch scripts outside the repository.

Subsequently pushed, deployed and production-verified by the owner (commit `7b5aaf0`, DB `0030_surface_work_executions`, Telegram smoke PASS).

## 34. Stage 13I — final Stage 13 audit & adversarial regression (verify-only)

Baseline `stage-13` = `origin/stage-13` = `7b5aaf0` (production), clean tree, Alembic single head
`0030_surface_work_executions`. No production code, migration or frontend change; one verification test file added.

**Contract matrix (verified against code).**

| Subsystem | Source of truth | Durable identity | Mutation path | Destructive op | Concurrency | Estimate | Execution |
|---|---|---|---|---|---|---|---|
| WorkPlan occurrences | `surface_planned_works` | `occurrence_key` (row id ephemeral) | PUT save (`set_plan`), APPEND, REPLACE, apply-to-all, recommendation accept | save removal, REPLACE, apply-to-all | plan row lock (single / ascending multi) | lines keyed by `occurrence_key` (id → key → legacy) | keyed by `occurrence_key` |
| Coefficients | assignment per occurrence | occurrence | same as works (recreated with the row) | with the occurrence | plan lock | snapshot at generation | none |
| Breaks | `wait_after_hours` per occurrence | occurrence | same as works | with the occurrence | plan lock | ignored | `ready_after` derived on read |
| Templates | `workflow_templates` + steps | template id / step ids (steps ephemeral) | create/update/replace_steps/archive | step replace | template row lock + `expected_step_ids` | never retroactive | never retroactive |
| Application history | `surface_work_plan_template_applications` | `application_id` + fingerprint | apply-template | — | plan lock | none | none |
| Execution | `surface_work_executions` | `occurrence_key` | PATCH transition, bulk apply | none (detach keeps history) | plan lock; bulk ascending incl. source | none | — |

**Lock order (static):** execution transition, save/replace, apply-template → one plan; WorkPlan apply-to-all → target
plans ascending; bulk → source + targets ascending; recommendation accept → recommendation row, then one plan;
Estimate → project row only; template step edit → template row only. No path locks a plan and then another
lockable row, so no inversion exists.

**Evidence.** New `tests/test_stage13i_audit.py` (11): scenarios A–J (duplicate identity through reorder + Estimate
regeneration with a manual override; APPEND into a live plan; REPLACE of a live plan incl. refused → zero mutation,
confirmed → one application, idempotent retry, Estimate 2 added / 3 removed with no inheritance; apply-to-all over
live targets with duplicates then bulk by PriceItem ordinal; template rename/step replace/archive never retroactive;
Price Book archive of an item used in template/plan/Estimate/execution; recommendation into a live plan + re-evaluation
never deletes works; `ready_after` through wait edit and reorder; stale source duplicate-count change and destination
duplicate change recomputed under lock), reveal isolation (no key, reveal Estimate lines keyless, reveal id rejected
as an occurrence), cross-user sweep of every Stage 13 endpoint (404, no leak). Backend 1682 passed (1671 + 11);
frontend 1301 passed; TypeScript and production build PASS; `git diff --check` clean. PostgreSQL (scratch, owner's
local server; no containers): pre-Stage-13 data seeded at 0026 with the `a772e69` code → 0030 → 0026 → 0030, 11/11
(all Stage 10–12 columns identical, every planned work keyed uniquely, DRAFT surface lines back-filled with their own
key, FINAL and reveal lines keyless, Stage 13 schema fully removed on downgrade); the 13H migration check (16/16) and
concurrency harnesses re-run 34/34 with 0 deadlocks. 16 default templates bootstrap with unique codes; all 16 names and
142 canonical description/note keys exist in PL and RU. Browser (headless Chromium, Telegram light/dark theme,
PL/RU × 320/390/412/480): Procesy list/detail/steps editor/form, WorkPlan editor with break editing, coefficient modal,
template sheet APPEND and REPLACE, Estimate — no horizontal overflow and no undersized Stage 13 control; Realizacja,
detach and bulk covered by the 13H.6 matrices on identical code. Contract: every Stage 13 schema matches its TS type.

**Findings (no BLOCKER / HIGH / MEDIUM):**
- LOW (pre-existing, Stage 9, out of scope): app-shell language buttons (24 px) and main navigation (38 px) are
  below 44 px.
- LOW (pre-existing, Stage 12F, out of scope): the coefficient modal header ellipsizes a long work name/title at
  320–390 px (`truncate`), instead of wrapping.
- LOW (theoretical race): execution transition and bulk check the archive flags before taking the plan lock, and
  archiving does not take the plan lock, so a status change can land concurrently with an archive. No data loss (archive
  is soft; restore shows the state); production impact negligible.
- LOW (contract permissiveness): `SurfacePlannedWorkRead.execution` is optional in TS though always sent;
  `SurfaceWorkPlanUpsert.template_applications` (unused 13C intent path) and `WorkflowTemplateUpdate.position` (unused)
  have no TS field.
- TEST-GAP: the PostgreSQL migration/concurrency harnesses live outside the repository; recommendation accept vs bulk
  is covered by the static lock order only.
- DOC-GAP: none beyond this section.

**Owner acceptance (2026-09-27).** Stage 13I — AUDIT PASS / OWNER ACCEPTED. Scenarios A–J PASS; backend 1682 passed;
frontend 1301 passed; TypeScript PASS; production build PASS; Alembic single head `0030_surface_work_executions`;
`git diff --check` clean; PostgreSQL Stage 13 migration chain 11/11; PostgreSQL concurrency 34/34 with 0 deadlocks.
No production-code defect and no data-integrity defect. The four LOW findings above are accepted as non-blocking
technical debt / known limitations and are NOT fixed in 13I. The PostgreSQL harnesses remain outside the repository;
the recommendation-acceptance-vs-bulk live PostgreSQL race remains a test gap covered by static lock-order analysis.
`tests/test_stage13i_audit.py` (11 tests) contains only reproducible SQLite-suite regression tests of the accepted
contracts (no local PostgreSQL, timing or environment assumptions).

- **Status:** Stage 13I — AUDIT PASS / OWNER ACCEPTED. Stage 13 as a whole not yet marked complete; Stage 13J not
  started.

## 35. Stage 13J — owner final walkthrough & Stage 13 closure

The owner performed the final walkthrough against the **real production Telegram Mini App** (production runtime
`7b5aaf0b782e99df9e96fa63873892dd88631cad`, DB `0030_surface_work_executions`), using dedicated test data
(`TEST_STAGE_13_FINAL`), following the 13J checklist:

| Part | Scope | Result |
|---|---|---|
| A | WorkPlan (substrate/quality, works incl. duplicate, break, coefficient, reopen) | PASS |
| B | Procesy (list, built-in vs custom, detail, ordered steps, duplicate) | PASS |
| C | APPEND into an existing plan | PASS |
| D | Estimate | PASS |
| E | Realizacja (start, complete, reopen, timestamps, readiness) | PASS |
| F | Detach protection (cancel, confirm) | PASS |
| G | REPLACE with detach confirmation | PASS |
| H | Apply-to-all (copy, no execution inheritance, confirmation) | PASS |
| I | Bulk execution (preview, apply, forward-only, zero-change preview) | PASS |
| J | Template non-retroactivity | PASS |
| K | Mobile / theme / language | PASS |
| L | Final sanity | PASS |

**Overall: PASS.**

Stage 13J — OWNER WALKTHROUGH PASS / OWNER ACCEPTED. Stage 13I — AUDIT PASS / OWNER ACCEPTED (§34; verification/docs
commit `88047c3c9657e057000d33339c501da6d4964028`). No runtime deployment is needed for 13I/13J: application
runtime code has not changed since the accepted production deployment (`7b5aaf0`).

**Known limitations / technical debt (non-blocking, from §34, unchanged):**
1. Pre-existing app-shell/navigation controls below the 44 px target.
2. Coefficient modal long-name ellipsis at narrow widths.
3. Theoretical archive-vs-status race with no known data-loss consequence.
4. Permissive frontend execution typing and minor unused contract omissions.

- **Status:** **Stage 13 — COMPLETE / OWNER ACCEPTED / PRODUCTION VERIFIED.** Stage 14 NOT STARTED.
