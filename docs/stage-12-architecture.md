# Stage 12 — Price Coefficients

- **Date**: 2026-09-21
- **Branch / HEAD**: `main` @ `e0a73d5` (Stage 11 COMPLETE / OWNER ACCEPTED / INTEGRATED TO MAIN)
- **Sub-stage**: 12B (architecture specification) — **documentation only**
- **Scope guardrails**: no application code, no Alembic migration, no `stage-12` branch, no runtime behavior change in this sub-stage. 12C must not start without explicit owner approval of this document.

## 0. Purpose

This record settles the architecture of **Stage 12 — Price Coefficients**: letting the owner adjust the
**labor** unit price of a specific planned-work occurrence for explicitly selected job conditions (quality
tier, height, access, room condition, geometry, and similar), without duplicating the Price Book, without
mutating `SurfaceWorkPlan`/`OpeningRevealPlannedWork` price data (which Stage 10 explicitly forbids), and
without breaking the Estimate's snapshot/explicit-regeneration contract that Stages 10 and 11 already
established and the owner already accepted in production.

**Product question Stage 12 answers**: *"This particular wall's plastering is genuinely harder than my
catalog price assumes — quality is higher, the ceiling is high, the room is furnished — how much extra
should THIS line cost, and let me see exactly why before it goes into the Estimate?"*

**What Stage 12 is NOT** (boundary): a second Price Book (Stage 9 remains the sole base-price authority), a
condition-detection rules engine (Stage 7 remains the sole deterministic risk/condition authority; nothing
here evaluates a condition automatically), an automatic-proposal engine (reserved, at earliest, for a future
Stage 13 extension — Stage 12 is 100% explicit owner selection), a fixed-surcharge catalog (Stage 12 reuses
the existing MANUAL `EstimateLine` mechanism unchanged), or a redefinition of the Q/S/PSG quality-level
business meaning (deferred to a dedicated follow-up, §21).

This document supersedes the Stage 12A read-only audit's provisional model comparison, resolving it against
the owner-approved D1–D11 decisions below.

---

## 1. Owner architecture decisions (canonical)

### D1 — User representation: percentages

Coefficients are presented to the owner as **percentages** (`0%`, `+10%`, `+20%`, `-10%`, …), never as
multiplier notation (`1.20`). Internally, a percentage is stored as an exact `Decimal` (e.g. `Numeric(6,3)`
holding `10.000` for `+10%`), never a binary float, and the percentage→multiplier conversion happens only at
calculation time (§10), deterministically, in one place.

### D2 — Application scope: single planned-work occurrence, organized into groups/levels

A coefficient selection belongs to **one specific planned-work occurrence** — never automatically to a whole
Project, Room, or Surface merely because a condition exists there. Coefficient *options* are organized into
**groups** (e.g. `QUALITY`, `HEIGHT`, `ROOM_CONDITION`, `GEOMETRY`, `ACCESS`, `COLOUR_COMPLEXITY`,
`PROTECTION_COMPLEXITY`); a group is `SINGLE_SELECT` for Stage 12's first cut — at most one option from a
given group may be selected per occurrence, but different groups combine freely on the same occurrence (see
§5, §10).

### D3 — Price scope: labor only

Coefficients adjust **labor** cost only. `PriceScope.MATERIAL` items are never eligible. `PriceScope.
LABOR_AND_MATERIAL` items have no existing labor/material split in the data model (`PriceItem.price` is one
blended number) — per the owner's own instruction to prefer rejection over an invented split, Stage 12
**rejects** coefficient assignment on `LABOR_AND_MATERIAL` items in the first cut (§9).

### D4 — Multiple coefficients: additive, relative to base

Selected percentages **sum**, then apply once: `E = B × (1 + ΣpᵢDecimal)`. Never compounding
(`B × 1.10 × 1.20 × …` is explicitly rejected). One deterministic Decimal rounding point, consistent with
`_compute_amount`'s existing `ROUND_HALF_UP` convention (§10).

### D5 — Manual price override remains authoritative

The existing `EstimateLine.price_override`/`unit_price` mechanism is unchanged and wins over any calculated
value. Once overridden, the base-price/coefficient snapshot becomes pure provenance — informational only,
never re-entering arithmetic. `reset_price_override` must recompute the effective price from the **current**
`PriceItem.price` and **current** coefficient assignment (never a stale Estimate snapshot value) — see §13.

### D6 — Separate, owner-editable coefficient catalog

Coefficient groups/options live in their **own** catalog — not part of `PriceItem`, not a second Price Book.
The application ships a **default** catalog (structurally, not with final percentages — see §21/§25); the
owner may edit percentages/labels, archive/disable entries, and add their own groups/options, or use the
defaults unchanged. Groups and options carry stable semantic `code`s (mirroring `PriceItem.code`) so a future
Stage 13 can reference a factor without depending on translated display text.

### D7 — Assignment UX location

Coefficient assignment happens **inside** the existing "Rodzaje prac i jakość" (`SurfaceWorkPlanEditor`)
context, directly on the planned-work row/card, via a control such as **"Współczynnik"**. The owner never
leaves the WorkPlan screen to apply a factor to a specific work. Catalog management (creating/editing
groups/options) may live on its own settings screen (§16).

### D8 — Legacy Estimate snapshot: honest NULL, never fabricated 0%

Pre-Stage-12 `EstimateLine` rows are **not** backfilled with a fabricated `0%`/`1.00` coefficient. New
provenance fields are nullable; `NULL` means *"this historical line predates the coefficient provenance
model"*, never *"the historical coefficient was definitely 0%."* `unit_price` on those rows remains their
historical effective price, untouched (§8, §12).

### D9 — Fixed surcharges are not coefficients

A flat amount (e.g. "+300 PLN small-job surcharge") is architecturally distinct from a percentage adjustment
and must never be folded into the coefficient calculation. Stage 12's first cut reuses the existing MANUAL
`EstimateLine` mechanism unchanged for this (§9, §17). No new "Adjustment" entity is introduced in Stage 12.

### D10 — Explicit application only

No Inspection/Risk condition, and no Stage 11 Recommendation, ever silently selects or applies a coefficient.
No WorkPlan mutation happens merely because a condition is detected. A future stage may *propose* a
coefficient by stable code; Stage 12 implements no such proposal path (§20).

### D11 — Base level / 0% is catalog-relative, never a universal hardcode

A group's `0%` option represents *"the condition already assumed by this owner's current Price Book base
price"* — it is a **per-owner catalog configuration fact**, not a permanent universal statement that
`S2`/`Q2` always means zero. If an owner's pricing already assumes `S3` as the baseline, their own catalog
may configure `S2` as negative and `S3` as `0%`. The architecture must never hardcode which option is "the"
base beyond what the owner's own catalog row says (§6, §21).

---

## 2. Boundary: Q/S/PSG business definitions are explicitly deferred

Stage 12B does **not** define the finished-result meaning, substrate prerequisites, preparation requirements,
acceptance criteria, or final percentage adjustments for `S1–S4`, `Q1–Q4`, or `PSG1–PSG4`. Every percentage
appearing anywhere in this document (`+10%`, `+20%`, `40.00 PLN`, etc.) is an **illustrative example only**,
never a canonical default. A dedicated follow-up (§21) will define each class's business meaning and propose
default coefficients for explicit owner approval before any such value is ever seeded. Stage 12's
architecture must *support* quality-tied groups/options generically — it must not *bake in* any unverified
business percentage.

---

## 3. Conceptual calculation model

```
Price Book base labor unit price (PriceItem.price, LABOR or LABOR_AND_MATERIAL-eligible-if-any)
  +  selected coefficient option percentages (summed, D4)
  =  effective labor unit price

effective labor unit price × quantity  =  EstimateLine.amount   (unchanged Stage 10 arithmetic)
```

Worked example (**illustrative only — not canonical**):

```
base = 40.00 PLN/m²
QUALITY:   S3            +10%
HEIGHT:    high ceiling  +20%
ROOM_CONDITION: furnished +10%
total adjustment = 10 + 20 + 10 = +40%
effective = 40.00 × (1 + 0.40) = 56.00 PLN/m²
quantity  = 100 m²
amount    = 5600.00 PLN
```

---

## 4. Factor group / option model

Two new catalog concepts, deliberately mirroring `PriceItem`'s already-proven shape rather than inventing new
conventions:

### `CoefficientGroup` (conceptual)

| Field | Notes |
|---|---|
| `id` | UUID PK |
| `owner_id` | FK, owner-scoped — mirrors `PriceItem.owner_id` |
| `code` | Stable semantic code, immutable after creation, `(owner_id, code)` unique — mirrors `PriceItem.code` exactly |
| `name_key` / `display_name` | Localized seed name vs. owner-authored name — mirrors `PriceItem` naming precedence |
| `selection_mode` | `SINGLE_SELECT` for Stage 12 (only mode implemented; the field exists so a future mode is additive, not a breaking migration) |
| `position` | Owner-controlled display ordering |
| `is_archived` | Archive-not-delete, mirrors `PriceItem.is_archived` |

### `CoefficientOption` (conceptual)

| Field | Notes |
|---|---|
| `id` | UUID PK |
| `group_id` | FK to `CoefficientGroup`, `ON DELETE CASCADE` |
| `code` | Stable semantic code, immutable, unique **within its group** — e.g. `HEIGHT_NORMAL`, `HEIGHT_MEDIUM`, `HEIGHT_HIGH` |
| `name_key` / `display_name` | Same precedence pattern as `PriceItem`/`CoefficientGroup` |
| `percentage` | `Decimal`, signed, e.g. `Numeric(6,3)` — `0.000` for a base option, positive for a surcharge tier, negative for a discount tier |
| `is_base` | **Explicit boolean**, not inferred from `percentage == 0` — see rationale below |
| `position` | Owner-controlled ordering within the group |
| `is_archived` | Archive-not-delete |

**Why an explicit `is_base` flag, not `percentage == 0`**: D11 establishes that "base" is a *catalog
configuration fact* about which option corresponds to the owner's already-priced assumption, not a
mathematical coincidence. Two different reasons an option could show `0%` must remain distinguishable:
"this is the owner's declared base assumption" (`is_base = true`) vs. "this condition happens to carry no
adjustment right now, but isn't the conceptual base" (`is_base = false`, `percentage = 0`) — e.g., a
`PROTECTION_COMPLEXITY` group's "standard" option could be priced at `0%` without being semantically "the
Price Book's own quality assumption" the way a `QUALITY` group's base level is. Collapsing this into
`percentage == 0` would silently lose that distinction and make future UI/reporting ("show the base level
distinctly from a merely-zero level") impossible without a schema change later. `is_base` costs one boolean
column now; recovering the distinction later would cost a migration and a data-backfill guess.

A `SINGLE_SELECT` group is expected to have **at most one** `is_base = true` option (validated at the service
layer, not a DB constraint, mirroring how this codebase generally prefers service-level domain validation for
cross-row invariants — see e.g. `assert_quality_scale_valid`).

---

## 5. Default catalog vs. owner customization — bootstrap strategy

**Lesson from Stage 9 (Price Book)**: the 44-row approved catalog was seeded via an idempotent Alembic-adjacent
data-loading path keyed by stable `code`, safe to re-run, and the owner can freely edit/archive rows
afterward without the seed ever reasserting itself over an edit.

**Lesson from Stage 11 (`WorkRecommendationRule` bootstrap)**: a **lazy, idempotent, application-level**
bootstrap (`_ensure_bootstrapped`, called from the service's own read/evaluate entry points) that inserts
only rows whose `(natural key)` doesn't already exist — never re-inserts, never overwrites, and requires no
manual seed command, no Docker, and no separate migration data step. Production received it automatically
the first time the feature was used.

**Recommendation for Stage 12**: reuse the **Stage 11 lazy-bootstrap pattern**, not a migration-data seed —
for two reasons specific to this feature: (1) the default catalog's *content* (percentages, exact groups) is
explicitly **not yet approved** (§2/§21), so baking anything into an Alembic migration now would either be
empty (pointless) or premature (risks encoding unapproved business data into schema history); (2) the owner
must be able to freely edit/archive every default row afterward, and the lazy-bootstrap idiom already
guarantees "insert only what's missing, by stable code, never touch what exists" — exactly the required
non-destructive-customization property, proven correct in production by Stage 11.

Concretely (design intent, not implementation): `CoefficientGroup`/`CoefficientOption` rows for the
**structure only** (group codes like `QUALITY`, `HEIGHT`, …, with placeholder-safe or genuinely-approved
percentages once §21 concludes) are defined in a `app/domain/data/price_coefficients.py`-style module
(mirroring `risk_rules.py`/`work_recommendation_rules.py`), and a `_ensure_bootstrapped()` method on the new
service inserts any `(owner_id, code)` combination not yet present. Archived owner choices are never silently
reactivated (the bootstrap only *inserts missing rows*; it never flips `is_archived` back to `false` on an
existing row). Display names remain editable (`display_name` overrides `name_key`, same precedence as
`PriceItem`); percentages remain owner-editable at all times, including on seeded rows.

**Do not seed final Q/S percentages** in 12C. If a structural bootstrap ships before §21 concludes, it must
ship with a **clearly non-production-implying** structure (e.g. an empty/minimal default set, or explicitly
owner-opt-in) rather than guessed numbers presented as if approved — this exact concern is why §21 exists as
a separate, gated follow-up.

---

## 6. Assignment model — the durable-identity problem (critical)

### 6.1 The problem, restated precisely

Stage 11B.0 already proved, by direct code inspection (`docs/stage-11-architecture.md` §2), that
`SurfacePlannedWork.id` and `OpeningRevealPlannedWork.id` are **not durable**: `SurfaceWorkPlanService.
set_plan`/`OpeningRevealWorkService.set_works` unconditionally **delete and recreate every child row** on
every save, even for an edit unrelated to a specific occurrence (e.g. reordering, or adding one unrelated
work). Re-confirmed in this audit by direct re-read of `work_plan_service.py`. A coefficient assignment keyed
by a raw FK to that row's `id` would silently orphan the very first time the owner made *any* other edit to
that surface's plan — an unacceptable, silently-destructive UX (the owner would see their coefficient
selection vanish for no apparent reason).

### 6.2 Options evaluated

**A — Make planned-work child identity durable** (change `set_plan`/`set_works` to diff/upsert instead of
delete-recreate). *Rejected.* This re-opens an already-verified, owner-accepted, production-proven Stage 10
core contract purely to serve a Stage 12 convenience. Blast radius includes Stage 10's own full-replace
semantics (apply-to-all-walls, reorder, archived-item handling) and Stage 11's accept-flow (`append_one_
planned_work_no_commit`), all of which are currently correct *because* of full-replace, not despite it.
Re-litigating a closed, tested architectural decision for an unrelated feature is out of proportion to the
problem.

**B — A stable occurrence key independent of the DB row ID** (e.g. an owner/client-generated UUID that
travels with a selection across saves). *Rejected as effectively redundant with C.* It would still require
the WorkPlan save payload to accept and echo back a per-selection key — which is exactly what C already does,
without inventing a new key concept the rest of the codebase has no precedent for.

**C — Recommended: include coefficient selections in the *same* authoritative WorkPlan replace payload, and
recreate the assignment rows atomically together with the `SurfacePlannedWork`/`OpeningRevealPlannedWork`
rows they belong to, in the *same* delete-recreate operation.** Concretely: extend the existing
`OrderedPriceItemSelection` payload item (today: `price_item_id` only) with an optional list of selected
`CoefficientOption` ids for that specific slot. `set_plan` continues to delete-and-recreate `SurfacePlannedWork`
rows exactly as today, and — in the *same* transaction, keyed to the *freshly created* row's own new `id` —
creates its coefficient-assignment child rows. There is nothing that needs to "survive" an edit
independently, because the assignment is never treated as an entity with a lifecycle separate from the work
selection it belongs to: both are written together, every time, by construction. This requires **zero**
change to Stage 10's existing delete-recreate contract — a coefficient assignment is architecturally just one
more attribute of a planned-work *selection* (alongside `price_item_id` and `position`), not a foreign entity
referencing a row that might disappear.

**D — Best-effort matching of old assignments to new rows by `(price_item_id, position)` on every save.**
*Rejected.* Introduces silent ambiguity the moment duplicate `PriceItem` occurrences exist (which Stage 10
explicitly permits) — e.g. reordering two identical duplicate rows makes "which one keeps its coefficient"
undefined. Strictly worse than C for no benefit.

### 6.3 Recommended solution: **Option C**

Coefficient selection is **part of the same atomic WorkPlan save operation** as the work selection itself,
never a separately-persisted reference to a row that might later disappear. This directly satisfies the
task's own explicit constraint — *"DO NOT build architecture that relies on a child row ID remaining
stable"* — by construction: nothing ever needs the old ID to remain stable, because nothing is ever read back
by that ID across saves. The owner experience is also the most natural fit for D7's UX direction: coefficient
assignment already only happens *from inside* the WorkPlan editor, on the *same* screen where the work
selection itself is edited and saved — so "save both together, atomically" is not a UX compromise, it is
simply what the screen already does today for the work list itself.

This applies identically to `OpeningRevealPlannedWork` (§7) if/when Reveal coefficient support ships,
mirroring `OpeningRevealWorkService.set_works`'s own identical delete-recreate contract.

---

## 7. Reveal support

The calculation architecture (base × Σpercentages, snapshot, NULL/zero handling) is **fully reusable** for
`OpeningRevealPlannedWork` — nothing about §10–§13 is Surface-specific. The durable-assignment solution (§6.3)
applies identically, since `OpeningRevealWorkService.set_works` has the exact same delete-recreate shape as
`SurfaceWorkPlanService.set_plan`.

**Scope recommendation**: ship the **backend/data-model** support generically for both `SurfacePlannedWork`
and `OpeningRevealPlannedWork` from 12D onward (so the calculation/snapshot code in 12E never has a Surface-
only assumption baked in), but the **first frontend substage (12F)** may reasonably ship Surface-only UI
first and defer the Reveal-editor "Współczynnik" control to a follow-up polish substage if it would otherwise
materially inflate 12F's scope. This is a UI-sequencing choice, not a backend limitation — documented
separately so 12E's schema/service work is never revisited for Reveal support later.

---

## 8. Labor-only eligibility (D3)

| `PriceScope` | Coefficient-eligible? |
|---|---|
| `LABOR` | **Yes** |
| `MATERIAL` | **No** — never eligible, no exception |
| `LABOR_AND_MATERIAL` | **No, in Stage 12's first cut** — `PriceItem.price` for this scope is one blended number with no stored labor/material split anywhere in the current schema (confirmed: `PriceItem` has exactly one `price` column regardless of `price_scope`). Inventing a split ratio now would be exactly the kind of unverified business assumption both D3 and this audit are instructed to avoid. **Recommendation: reject assignment at the service layer** (a domain validation error, not a 500) when the target `PriceItem.price_scope != LABOR`. Revisit only if/when the Price Book itself gains an explicit labor/material price decomposition — that would be a Stage 9-scoped change, out of bounds for Stage 12. |

This check happens against the **target `SurfacePlannedWork`/`OpeningRevealPlannedWork`'s resolved
`PriceItem.price_scope` at assignment time** (and is re-validated at Estimate-generation time too, since the
owner could theoretically swap which `PriceItem` a slot points to between assignment and generation — though
under the Option C atomic-save model this is unlikely to ever be inconsistent in practice, re-validation costs
nothing and removes any doubt).

---

## 9. Fixed surcharges (D9) — explicitly not coefficients

A flat surcharge (e.g. "+300 PLN small-job surcharge") is quantity-independent and structurally incompatible
with the `quantity × effective_unit_price` model — folding it into a percentage would require back-solving a
fake per-unit delta from a target total, which is fragile and conceptually backwards.

**Stage 12 first-cut recommendation**: reuse the **existing, already fully-tested MANUAL `EstimateLine`
mechanism** (`add_manual_line`, `unit=FLAT`, `quantity=1.000`, owner-typed `unit_price`) — **zero schema
change**. A future, explicitly-approved UX layer (§17) may offer the owner a convenient *list* of common
named surcharges to reduce typing, but that is a frontend convenience over the same underlying MANUAL-line
mechanism, not a new backend entity, unless a later explicit owner decision changes this.

---

## 10. Calculation contract

Let `B` = base labor unit price (`PriceItem.price` at generation/regeneration time), and `pᵢ` = each selected
option's `percentage` (a signed `Decimal`, e.g. `10.000` for `+10%`).

```
P = Σ pᵢ                          (sum of selected percentages, Decimal, exact)
E = B × (1 + P / 100)             (single multiplication, single rounding point)
A = quantity × E                  (unchanged _compute_amount contract)
```

**Decimal precision**: percentages stored as `Numeric(6,3)` (matches this codebase's existing "3 decimal
places" convention for quantities, `Surface`/`Opening` dimensions, and `RiskRuleCondition` thresholds — never
introduces a new precision convention). `E` is computed at full Decimal precision and quantized to the
existing `unit_price` column's own `Numeric(12,2)` scale using the *same* `ROUND_HALF_UP` rounding already
used by `_compute_amount`, at the single point where `E` is finally assigned — never rounded per-option,
never rounded twice. No binary float anywhere in the chain (this codebase already treats "no
Number/parseFloat/toFixed/Math.round on money or quantity" as an enforced, repeatedly-tested invariant on the
frontend; the backend equivalent is `Decimal` end-to-end, already true today and unchanged by Stage 12).

**Validation boundaries** (service-layer, not left to arithmetic):

| Case | Recommended behavior |
|---|---|
| `+0%` total adjustment | Valid; `E = B` exactly (a `SINGLE_SELECT` group's base option, or no groups selected at all) |
| Positive percentage | Valid (surcharge tier) |
| Negative percentage | Valid (discount tier) — symmetrical with this codebase's existing "an explicit `0.00` price / a coefficient `< 1.0` multiplier is a legitimate owner decision, never blocked" philosophy |
| Total adjustment `= -100%` | **Recommend rejecting at the *option* level, not only at the total**: an individual option's percentage should be validated `> -100%` at catalog-save time, so a `-100%` total can only be reached by *summing* multiple legitimate discounts — if it is reached, the resulting `E = 0.00` is a legitimate resolved zero (same as an explicit `0.00` `PriceItem.price` today), not an error. |
| Total adjustment `< -100%` | **Reject at Estimate-generation/calculation time** (would imply a negative effective price, which is not a real commercial price) — recommend a domain validation error surfaced the same way `EstimateValidationError` surfaces today, not a silently clamped `0.00` (clamping would hide the owner's own catalog-configuration mistake instead of surfacing it) |
| Extremely large positive adjustment | **Recommend a soft per-option maximum** (e.g. reject `percentage > 500` at catalog save time) as a fat-finger guard — exact ceiling is an owner product decision, not decided here |
| Duplicate option selected twice | Reject — the assignment payload should de-duplicate by `option_id`, or the service should reject a duplicate id in the same selection |
| Two options from the same `SINGLE_SELECT` group | Reject at the service layer (domain validation error) — mirrors how this codebase already validates other mutually-exclusive domain rules in the service, not the DB, layer |
| Archived option/group selected | Reject **new** assignment (mirrors `PriceItem.is_archived` exactly: blocks new selection, never mutates an already-snapshotted historical `EstimateLine`) |
| Cross-owner option | Reject with the same `NotFoundError`-style 404 convention used everywhere in this codebase (never a distinguishing 403) |

---

## 11. NULL and zero contract

Directly inherited from Stage 9/10's already-established, owner-accepted semantics — Stage 12 introduces no
new exception to them:

- `PriceItem.price IS NULL` ⇒ effective unit price **stays `NULL`**, regardless of any selected coefficient.
  It remains "Do ustalenia" / "Уточняется" and continues to block FINAL exactly as today (Stage 10H.1's
  unresolved-quantity precedent already treats "unresolved" as contagious, never silently resolved by an
  unrelated calculation — the same discipline applies here: `NULL × anything` must stay `NULL`, enforced by an
  explicit `if base_price is None: effective = None` branch, never left to arithmetic, which would raise in
  Python on `None * Decimal` anyway).
- `PriceItem.price == 0.00` ⇒ effective unit price is **`0.00` exactly**, regardless of a positive percentage
  adjustment (`0.00 × 1.40 = 0.00`) — a real, resolved, finalize-eligible zero, never re-classified as
  unresolved and never silently inflated.

---

## 12. Estimate snapshot contract

**Requirement**: an already-generated `EstimateLine` must remain fully self-explanatory (base price,
selected coefficients, resulting percentage, effective price) **without depending on any live catalog row**
— exactly the same non-negotiable property `unit_price`/`item_code`/`description` already have today
("snapshot fields are written once and never re-read from the Price Book or geometry post-creation").

**Representation options evaluated**:

- **Structured columns per possible group** — rejected: the group set is owner-editable and open-ended
  (§6/§25); a fixed column per group cannot represent an owner-added custom group without a migration per
  group, which defeats the entire "owner-extensible catalog" premise of D6.
- **Normalized child snapshot rows** (one row per applied option, FK-free, pure denormalized copy: code,
  display text, percentage, at generation time) — technically sound and fully queryable, but adds a whole new
  child table + join for what is, per line, typically 0–3 small facts; heavier than the problem needs.
- **A single structured JSON/JSONB column on `EstimateLine`** (e.g. `coefficient_snapshot`: a list of
  `{code, display_text, percentage}` objects, denormalized at generation time) — **recommended**. It requires
  no join to read/render a line (matches how `EstimateLineRead` is already a single flat row the frontend
  renders directly), scales to any number of applied options without a schema change, and is trivially
  `NULL`/absent for legacy and coefficient-free lines (D8). The *sum* (`P`) does not need its own column
  either — it is always re-derivable from the snapshot array at render time, avoiding a second source of
  truth that could drift from the array.

**Recommended new `EstimateLine` fields** (naming illustrative, final naming deferred to 12E):

| Field | Type | Meaning |
|---|---|---|
| `base_unit_price` | `Numeric(12,2)`, nullable | `PriceItem.price` at generation/regeneration time, before any coefficient — mirrors `unit_price`'s own nullability exactly (NULL means unresolved base, same meaning as today's `unit_price IS NULL`) |
| `coefficient_snapshot` | `JSON`/`JSONB`, nullable | `[{code, display_text, percentage}, …]` applied at generation time; `NULL`/`[]` for a line with no coefficient selected, and always `NULL` for pre-Stage-12 legacy rows (D8) — never fabricated |

`unit_price` **itself keeps its exact current meaning and column** — "the number multiplied by quantity" —
so `_compute_amount`, `finalize()`'s price-unresolved check, every existing price-override test, and the
frontend's existing rendering of `unit_price` need **zero** conceptual change. Stage 12 is additive to the
existing snapshot, not a redefinition of it.

If the owner later changes the Price Book base price, or edits/archives a `CoefficientOption`'s percentage,
an already-generated `EstimateLine` (DRAFT or FINAL) is **untouched** — exactly like today's PriceBook-price-
change behavior. Only an explicit "Sprawdź zmiany" → regenerate cycle brings a **DRAFT** up to date (§19);
FINAL/ACCEPTED remain permanently immutable (§14 of the Stage 12A audit, unaffected by this specification).

---

## 13. Price override contract

Unchanged mechanism, now with a wider recompute surface:

- **Calculated state**: `base_unit_price` + `coefficient_snapshot` → `unit_price` (computed, `price_override
  = false`).
- **Override state**: owner explicitly types a final `unit_price` (or explicit `null` for "Do ustalenia") via
  the existing `PATCH .../lines/{id}` endpoint → `price_override = true`, `unit_price` authoritative,
  `base_unit_price`/`coefficient_snapshot` remain frozen provenance, never re-entering arithmetic while
  overridden — identical in kind to how a `price_override` line already ignores PriceBook changes today.
- **Reset** (`reset_price_override = true`): must recompute the **current** effective price from the
  **current** `PriceItem.price` **and** the **current** coefficient assignment for that occurrence (via the
  Option-C-persisted assignment, §6.3) — never merely restore the raw base price and silently drop the
  coefficient, and never reuse a stale value already sitting in the `EstimateLine`'s own snapshot columns
  (those describe what was true at *generation* time, not necessarily what's true *now*). This is the one
  concrete backend behavior change 12E must implement: today's `reset_price_override` only re-reads
  `PriceItem.price`; it must be extended to also re-resolve and re-apply the occurrence's current coefficient
  selection.
- **Preview/regeneration of an overridden line**: unchanged from today — a `price_override = true` line is
  already skipped by `_reconcile_planned_work_lines` for price purposes (only `source_quantity`/description/
  unit/scope/currency drift is tracked for it); Stage 12 must **not** start recomputing an overridden line's
  price during regeneration just because its coefficient assignment changed — that would silently discard an
  explicit owner override, exactly the class of bug Stage 10H.1 hardened against for quantity.

---

## 14. WorkPlan UI contract (12F scope, documented now for continuity)

Each planned-work row/card inside `SurfaceWorkPlanEditor` gains a **"Współczynnik"** control (final wording
localized later). Tapping it opens a **modal / mobile bottom sheet** overlaying the current WorkPlan screen:

```
--------------------------------
Współczynnik ceny

Szpachlowanie S3
Cena bazowa: 40.00 zł/m²

JAKOŚĆ
○ S2 / Q2        0%
● S3 / Q3      +10%
○ S4 / Q4      +20%

WYSOKOŚĆ
● normalna        0%
○ średnia       +10%
○ wysoka        +20%

POMIESZCZENIE
● puste           0%
○ umeblowane    +20%

+ Dodaj współczynnik

Łączna korekta: +30%
Cena po korekcie: 52.00 zł/m²

[Anuluj]              [Zastosuj]
--------------------------------
```

*(All percentages/labels above are illustrative examples only — not approved catalog values, §2/§21.)*

**Mobile constraints** (standing project rule, unchanged): optimized for 390/412px, functional 320–480px, no
horizontal scrolling, touch targets ≥ 44px, the overlay must not let the underlying WorkPlan screen receive
accidental input while open, long option lists scroll *inside* the overlay (not the page), and `[Anuluj]`/
`[Zastosuj]` stay reachable regardless of scroll position (sticky footer, mirroring how `EstimateShell`'s own
finalize-confirmation and reveal-editor already keep primary actions reachable on long content).

---

## 15. Explicit apply/cancel semantics

Opening the overlay **never** mutates persisted state. Every selection change inside it is **local UI state
only**. Only **"Zastosuj"** commits (via the same atomic WorkPlan save described in §6.3). **"Anuluj"**
discards local changes and closes without any request.

**Recommended close/back policy**: if the local selection differs from what was last loaded (dirty), treat
back/swipe-close the same as `[Anuluj]` — **discard immediately**, without a confirmation dialog. Rationale:
this mirrors the existing project-wide mobile philosophy of minimizing taps and avoiding extra confirmation
friction (`.agents/rules` "Field-usage principle": minimal taps, avoid unnecessary screens) *and* the
coefficient selection is inherently low-stakes/quickly-redone compared to, say, deleting a manual line (which
*does* already require confirmation elsewhere in this codebase) — losing an un-applied coefficient tweak by
an accidental back-tap is a minor, instantly-recoverable annoyance, not data loss of real work. If the owner
disagrees, a confirm-on-dirty-close step can be added later without any backend change.

---

## 16. Add-custom-coefficient UX (12F scope)

**"+ Dodaj współczynnik"** inside the overlay should, at minimum, let the owner select an existing group/
option they haven't already picked (for a group not yet represented, or a different `SINGLE_SELECT` group
entirely). **Creating a brand-new custom group/option from inside the modal** is a UX convenience the owner
explicitly requested — recommend supporting a **minimal inline creation path** (just `display_name` +
`percentage`, defaulting to a sensible new group or "General"/"Inne" catch-all group) directly in the modal,
while **full catalog management** (editing existing groups' structure, reordering, archiving, renaming
codes) stays on the separate settings screen (D6/D7). This keeps the WorkPlan card itself uncluttered while
still honoring "the owner doesn't need to leave the WorkPlan context" for the common case of adding one more
factor on the fly.

---

## 17. Fixed surcharge UX (backlog, not Stage 12 scope)

Keep architecturally separate from percentage coefficients (D9). Document, as a **future** UX/product
backlog extension of the existing MANUAL `EstimateLine` mechanism, a convenience concept such as a
**"Dopłaty"** picker offering owner-defined/common named entries (e.g. *Małe zlecenie*, *Dojazd*, *Praca
ekspresowa*) that simply pre-fill the existing "add manual line" form. **Not implemented in Stage 12** unless
a later, explicit owner decision approves a dedicated surcharge catalog.

---

## 18. Estimate UI contract (12F scope)

A coefficient-adjusted line must let the owner understand, without guessing: base price, each selected
adjustment, the total adjustment, the effective price, quantity, and the resulting amount — but the
**collapsed** card should stay compact (progressive disclosure, matching this codebase's existing
`quantity_overridden`/`price_override` amber-annotation-row pattern):

```
Collapsed:            52.00 zł/m²   ·   +30% korekta
Expanded/detail:
  Cena bazowa:             40.00 zł/m²
  Wysokość:                  +20%
  Umeblowanie:               +10%
  Łączna korekta:            +30%
  Cena po korekcie:        52.00 zł/m²
  Ilość:                    100 m²
  Razem:                  5200.00 zł
```

*(Percentages/values illustrative only.)*

A **manually overridden** effective price must remain visually distinguishable from a **calculated** one,
reusing the existing manual-change annotation pattern (`t.estimates.price_overridden`/the amber row already
used for `quantity_overridden`) rather than inventing new visual language.

---

## 19. Preview / regeneration semantics

Unchanged Stage 10 explicit-workflow contract, extended to cover coefficients: changing a coefficient
assignment, or editing a `CoefficientOption`'s percentage in the catalog, **never** mutates an existing
Estimate. The DRAFT (if any) remains a stale snapshot until the owner explicitly presses **"Sprawdź zmiany"**
— the existing regeneration-preview pipeline (`LineChangeEntry`, `old_unit_price`/`new_unit_price`) is
extended with an equivalent effective-price-breakdown diff, reusing the *same* mechanism rather than building
a second preview system. Only an explicit **"Aktualizuj kosztorys"** brings a DRAFT's lines up to the current
base price + current coefficient assignment. FINAL/ACCEPTED remain permanently immutable, unaffected by any
later catalog/assignment/Price-Book change, exactly as already established.

---

## 20. Stage 11 compatibility

`WorkRecommendationService.accept_recommendation` is **unchanged**: it appends a bare
`(price_item_id, position)` `SurfacePlannedWork` row exactly as today, with **no** new parameter, **no**
coefficient selection, and **no** Estimate mutation. After acceptance, the owner may separately open
"Współczynnik" for that newly-planned work through the ordinary WorkPlan-editor path — coefficient assignment
is always a distinct, subsequent, explicit owner action, never something Stage 11 acceptance triggers or
knows about. A future Stage 13 may propose a coefficient option by its stable `code` (D6 anticipates this);
Stage 12 implements no such proposal path (D10).

---

## 21. Q/S/PSG quality-level definition — explicit follow-up (backlog, gated)

Before any production default percentage for a quality-tied coefficient group ships, a **separate,
explicitly-approved** specification task must define, for each of `S1–S4` (concrete/plaster) and `Q1–Q4`/
`PSG1–PSG4` (gypsum-board):

- the intended finished result;
- substrate prerequisites;
- required preparation steps;
- typical work sequence;
- acceptance criteria;
- typical defects/tolerances, where a supported concept exists;
- which `PriceItem`/work categories the tier actually affects;
- its relationship to the owner's declared base level (D11);
- a **proposed** default percentage adjustment — proposed, not pre-approved.

This work is explicitly out of scope for Stage 12B and must not be shortcut by seeding guessed numbers into
any 12C/12D/12E bootstrap. It is tracked as its own gated sub-stage (12G, §26) requiring explicit owner
approval of the resulting percentages before they are ever seeded as defaults for any real owner.

---

## 22. Proposed data model (summary)

| Entity | Purpose | Key fields (illustrative) |
|---|---|---|
| `CoefficientGroup` | Owner-scoped catalog group | `id, owner_id, code, name_key, display_name, selection_mode, position, is_archived` |
| `CoefficientOption` | One selectable level within a group | `id, group_id, code, name_key, display_name, percentage, is_base, position, is_archived` |
| `SurfacePlannedWorkCoefficient` (or reveal equivalent) | Assignment of option(s) to one planned-work occurrence, created/replaced **atomically together with** its parent occurrence row (§6.3) | `id, surface_planned_work_id (or opening_reveal_planned_work_id), coefficient_option_id` |
| `EstimateLine` additions | Immutable generation-time snapshot | `base_unit_price` (nullable Decimal), `coefficient_snapshot` (nullable JSON) |

No change to `PriceItem`, `SurfaceWorkPlan`, `SurfacePlannedWork`'s existing columns, `OpeningRevealPlannedWork`'s
existing columns, or `unit_price`'s meaning/type.

---

## 23. API contract (summary)

- **Coefficient catalog CRUD** — new endpoints mirroring the existing `/api/price-items` shape (list/create/
  update/archive), owner-scoped.
- **WorkPlan read/write** — extend the existing `SurfaceWorkPlanRead`/`OrderedPriceItemSelection` (and the
  Reveal equivalents) with the per-slot coefficient-option-id list, persisted atomically inside the *existing*
  `PUT` endpoint (§6.3) — **no new dedicated assignment endpoint**, to avoid a second, independently-
  concurrent mutation path around the same `SurfacePlannedWork` rows the existing PUT already atomically
  owns.
- **Estimate read / preview** — `EstimateLineRead` and `LineChangeEntry` gain the additive, optional base/
  coefficient/effective fields described in §12/§19.

Reusing the existing WorkPlan PUT for assignment (rather than a separate endpoint) is preferred specifically
*because* concurrency/atomicity matters here (§6.3) — a second endpoint touching the same rows outside the
existing full-replace transaction would reintroduce exactly the "stale reference" risk §6 solves.

---

## 24. Validation contract (summary)

| Concern | Recommended handling |
|---|---|
| Owner isolation | Every `CoefficientGroup`/`CoefficientOption` query filtered by `owner_id`, mirroring `PriceItem` exactly |
| Archived group/option | Reject new selection (404/422-style domain error); never mutates existing snapshots |
| Wrong group / cross-group option id | Reject — validate the option actually belongs to the group the client claims |
| Duplicate option in one selection | Reject / de-duplicate before persistence |
| Two options from one `SINGLE_SELECT` group | Reject — domain validation error, service layer |
| `MATERIAL` target | Reject — never eligible (§8) |
| `LABOR_AND_MATERIAL` target | Reject in Stage 12's first cut (§8) |
| Invalid percentage (see §10 boundaries) | Reject at catalog-save time (per-option ceiling/floor) or at calculation time (total `< -100%`) |
| Cross-project / cross-owner planned work | Reject via the existing owned-resource-graph pattern (`Surface → Room → Project → Owner`), identical to every other Stage 10/11 mutation |
| Stale WorkPlan edit / deleted-and-recreated occurrence | Not applicable under the recommended model — assignment is created *atomically with* the occurrence it belongs to (§6.3), so there is no independent "staleness" state to detect |
| `NULL` base price | Effective price stays `NULL` (§11) |
| Explicit zero base price | Effective price stays `0.00 `(§11) |
| Negative total adjustment reaching exactly `0.00` | Valid, resolved zero |
| Effective price below zero | Reject at calculation time (§10) |

---

## 25. Default catalog categories (structure only — not final values)

The following **categories** are expected to be researched/approved later (§21 for `QUALITY` specifically;
the others may be simpler and approved sooner, but no percentage in any of them is approved yet):

`QUALITY` · `HEIGHT` · `FURNITURE_OCCUPANCY` · `ACCESS` · `GEOMETRY` · `COLOUR_COMPLEXITY` ·
`PROTECTION_COMPLEXITY`

Additional categories may be added to this list as backlog without architectural impact — the group/option
model (§4) places no limit on the number or kind of groups. **No percentage value for any category above is
approved by this document.**

---

## 26. Proposed Stage 12 sub-stages

| Sub-stage | Scope |
|---|---|
| **12A** | Architecture audit — **COMPLETE** |
| **12B** | Architecture specification (this document) — **COMPLETE** upon owner approval of this commit |
| **12C** | `CoefficientGroup`/`CoefficientOption` persistence, idempotent structural bootstrap (§5), owner-scoped CRUD service + API. No assignment, no Estimate integration yet — mirrors how Stage 9 shipped `PriceItem` before anything consumed it. |
| **12D** | Durable planned-work coefficient assignment (§6.3): extend `OrderedPriceItemSelection`/WorkPlan PUT (and the Reveal equivalent per §7's backend-first scope) to persist assignments atomically with their occurrence. Backend + ownership/validation (§24) only, no Estimate integration yet. |
| **12E** | Estimate coefficient snapshot/calculation: `base_unit_price`/`coefficient_snapshot` columns + migration, generation/regeneration computation with NULL/zero-safety (§11), `reset_price_override` extended (§13), preview-diff extension (§19). No frontend yet. |
| **12F** | Frontend: coefficient catalog settings screen, WorkPlan-editor "Współczynnik" modal/bottom-sheet (§14–§16), Estimate line/group/preview presentation (§18), PL/RU, mobile acceptance (320–480px, 390/412px primary). |
| **12G** | Quality-level/default catalog definition (§21): `S1–S4`/`Q1–Q4`/`PSG1–PSG4` business specification and proposed default percentages, submitted for explicit owner approval before any seed ships. |
| **12H** | Adversarial/hardening tests (mirrors Stage 10F's own precedent) + full mobile acceptance + real Telegram owner walkthrough + production deployment, only after explicit owner approval. |

Every implementation sub-stage (12C onward) follows the standing gate exactly: Implementation → focused
tests → full relevant tests → PASS/FAIL → commit → **owner approval** → push. No sub-stage is combined merely
for convenience. Production deployment occurs only after 12H and explicit owner approval, mirroring Stage
11's own closure sequence.
