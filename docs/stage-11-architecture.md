# Stage 11 — Inspection → Recommended Work → Estimate

- **Date**: 2026-09-20
- **Branch / HEAD**: `stage-11` @ `a8360f1` (Stage 10 COMPLETE / OWNER ACCEPTED, merged to `main`)
- **Sub-stage**: 11B.0 (contract verification + architecture specification) — **documentation only**
- **Scope guardrails**: no application code, no Alembic migration, no runtime behavior change in this sub-stage. 11B.1 must not start without explicit owner approval of this document.

## 0. Purpose

This record settles the architecture of **Stage 11 — Inspection → recommended work → Estimate**: turning an
already-completed Stage 6 inspection and its Stage 7 risk/finding results into *actionable, priced,
explicitly-accepted* work on an existing Stage 10 `SurfaceWorkPlan`, without duplicating any of Stages 6, 7,
9, or 10.

**Product question Stage 11 answers**: *"Given what the inspection already found, what work should I
consider adding to this wall's/floor's/ceiling's plan — and let me pick which of those I actually want,
without anything happening automatically."*

**What Stage 11 is NOT** (boundary, reaffirmed from the Stage 11A audit): a second Rules Engine (Stage 7
remains the sole authority on technical risk/condition evaluation), a price engine (Stage 9 remains the sole
price authority), a workflow/sequencing engine (Stage 13), a photo/defect annotation system (Stage 14), a
document generator (Stage 15), or a redesign of Estimate generation (Stage 10 stays unchanged).

This document supersedes the Stage 11A read-only audit's tentative design (which had provisionally suggested
extending `RiskRule` directly and referencing a planned-work row by FK). Both of those are corrected below
based on owner decisions D1–D5 and a direct code/test verification performed in 11B.0 (§2).

---

## 1. Owner architecture decisions (canonical)

### D1 — Reveal / Opening: deferred

Stage 11's first implementation supports **WALL Surface, canonical FLOOR Surface, canonical CEILING
Surface** only. `Inspection` has no `opening_id` today (verified in Stage 11A) and none is added. Opening/
reveal recommendations, and any change to `OpeningRevealPlannedWork`, are out of scope for this cut. This is
a scope decision, not a permanent prohibition — a future sub-stage may reopen it explicitly.

### D2 — Room-level results: advisory only

A ROOM-level result (`Inspection.surface_id` and `plane` both null) may be **displayed** as a recommendation
but has **no accept action** in the first cut. No automatic target guessing, no automatic apply-to-all-walls,
no surface picker. A future sub-stage may add explicit target selection.

### D3 — PriceItem resolution: hybrid, `PriceItem.code` primary

Primary mapping: **stable recommended-work code → owner's PriceBook → `PriceItem.code` → current
`PriceItem`**, resolved fresh at every use (never cached, never treated as a permanent identifier — a
`price_item_id` is not durable across owners/time; `code` is the stable key, exactly as `PriceItem.code`'s
own doc comment already states). Market/reference prices are never read as a fallback owner price — the
Stage 9 audit confirmed `PriceMarketReference` is never joined by `WorkPlanService`/`EstimateService`, and
Stage 11 must preserve that isolation. If a code fails to resolve to an eligible current `PriceItem`, the
contract has an explicit unresolved state; a later UI sub-stage may let the owner pick a `PriceItem`
manually instead.

### D4 — Recommendation catalog: separate from Risk

`WorkRecommendationRule` is a **small, separate mapping catalog** — not a synonym for `RiskRule`. It maps an
already-known inspection/rule/finding result to one or more suggested semantic work codes. It is not a
second Rules Engine, workflow engine, price engine, or technology sequencing engine; Stage 7 remains
authoritative for condition/risk evaluation. Its exact shape is derived in §3.

### D5 — Acceptance mutation: explicit backend command

Recommendation acceptance is **one atomic backend command**, never a frontend
GET-WorkPlan → locally-append → PUT-WorkPlan sequence. The command validates recommendation state, resolves
the target and the `PriceItem`, applies the existing Stage 10 WorkPlan invariants (archived-item guard, no
category restriction for WALL/FLOOR/CEILING), appends exactly one intentional occurrence, records
acceptance, and commits atomically. It never regenerates the Estimate, never navigates the user, and never
deduplicates existing WorkPlan occurrences — Stage 10 duplicate semantics remain fully valid. Full contract
in §6.

---

## 2. Verified Stage 10 contract: planned-work row identity is **not durable**

Direct code and test verification (not inferred from Stage 11A's audit, which had flagged this as an open
question):

- `SurfaceWorkPlanService._rewrite_works` (`work_plan_service.py:110-135`) — every call to `set_plan`,
  `replace_planned_works`, or `apply_to_room_walls` executes an **unconditional
  `DELETE FROM surface_planned_works WHERE work_plan_id = ...`**, then re-inserts a brand-new
  `SurfacePlannedWork` row (fresh UUID) for every item in the submitted list, `position` = its index.
- `OpeningRevealWorkService._rewrite_works` (`opening_reveal_work_service.py:125-143`) — identical
  unconditional delete-all-then-recreate-all pattern.
- **Existing regression test proves this is deliberate, tested behavior**:
  `backend/tests/test_surface_work_plan.py::TestJ_AtomicReplace::test_replacing_works_deletes_old_rows`
  (lines 512-532) — asserts `old_ids.intersection({w.id for w in replaced.planned_works})` is **empty** even
  though the same `PriceItem` (`second`) survives the replace semantically.

**Answers to the Stage 11A verification questions:**

| # | Question | Answer |
|---|---|---|
| A | Is an existing row reused if the item remains in the list? | **No.** |
| B | Are child rows deleted and recreated? | **Yes, unconditionally, on every write.** |
| C | Duplicate `price_item_id`s? | Each occurrence becomes its own row at its list index; only aggregate counts (existing vs. requested) are checked, for the archived-item guard. |
| D | Can the service identify which duplicate occurrence survives reordering? | **No** — there is no per-occurrence identity; every row is destroyed and rebuilt from scratch every time. |
| E | Does a position change preserve row ID? | **No.** |
| F | Is `SurfacePlannedWork.id` a durable provenance anchor across ordinary edits? | **No.** |
| G | Same, for `OpeningRevealPlannedWork.id`? | **No** (same code shape). |

**Consequence:** any Stage 11 design that stores a long-lived FK to a specific `SurfacePlannedWork.id` /
`OpeningRevealPlannedWork.id` row would silently go stale the very next time the owner (or Stage 11 itself)
saves that plan through the normal editor — even for an unrelated edit. This rules out "Option A" from the
Stage 11A candidates (`recommendation_id` FK on the planned-work row) outright: the row it would point to is
guaranteed to be replaced by a new one on the next ordinary save.

This does **not** affect `EstimateLine.planned_work_id` — that field is itself a snapshot captured at
Estimate-generation time and is never expected to remain valid past the next WorkPlan edit; Stage 10 already
accepts this (a DRAFT simply goes stale until "Sprawdź zmiany"). No change to `EstimateLine` is implied or
needed.

---

## 3. `WorkRecommendationRule` — the recommendation catalog

A pure lookup table: **existing, already-known result → suggested work code(s)**. It never evaluates a
condition itself (that is Stage 7's job, already done by the time this table is consulted).

**Trigger key — both, not either/or** (per D4, "not every useful recommended work is necessarily a risk"):

- `trigger_type`: `RISK_RULE` | `FINDING`
- `trigger_code`: `RiskRule.code` (when `trigger_type = RISK_RULE`) or `InspectionFinding.finding_key` (when
  `trigger_type = FINDING`)

Both are already-stable, already-versioned/keyed identifiers in the repository — `RiskRule.code`+`version`
uniquely identifies a fired technical risk; `finding_key` uniquely identifies a recorded fact per question.
No new condition language is introduced; `WorkRecommendationRule` only maps a code that already exists to a
suggested work code that already exists (`PriceItem.code`).

Fields:

- `id`, `trigger_type`, `trigger_code`
- `recommended_work_code` (a `PriceItem.code` string — not a `price_item_id`)
- `active` (bool) — mirrors `RiskRule.active`, lets a mapping be retired without deleting history
- `created_at` / `updated_at`

No `substrate`/`target_type` restriction field is added in this cut — `RiskRule` and `InspectionFinding`
already encode that context on the *trigger* side (a `RiskRule.code` is already substrate-restricted where
relevant); duplicating that restriction on the mapping row would be a redundant condition, which D4
explicitly forbids this table from evaluating.

---

## 4. `WorkRecommendation` — the materialized, actionable record

Reuses the **materialize-once, reconcile-by-identity, resolve-never-delete** idiom already used twice in
this codebase (`Risk`, `CommunicationApplication`) — a third instance of an established pattern, not a new
one.

**Identity**: `(trigger_code, source_signature)`, unique — exactly `Risk`'s own identity shape.
`source_signature` is computed with the *existing* `compute_source_signature()` utility
(`risk_rules.py:45-51`, already generic over a finding-ID sequence): when `trigger_type = RISK_RULE`, reuse
the parent `Risk.source_signature` directly; when `trigger_type = FINDING`, compute it fresh over the single
triggering `InspectionFinding.id`.

**Target (denormalized, captured at materialization time — §7 rationale)**:

- `room_id` (always present, mirrors `Risk.room_id`)
- `surface_id` (nullable — present for WALL/FLOOR/CEILING, null for ROOM)
- `target_kind`: `WALL` | `FLOOR` | `CEILING` | `ROOM` (reuses `derive_target_type`'s output verbatim)

**Source (audit only, never used for target resolution)**:

- `inspection_id`
- `risk_id` (nullable — set only when `trigger_type = RISK_RULE`)
- `finding_id` (nullable — set only when `trigger_type = FINDING`)
- `rule_id` (FK to `WorkRecommendationRule`, so a later catalog edit is traceable per row)

**Suggested work**:

- `recommended_work_code` (copied from the rule at materialization time — a snapshot, so a later catalog
  edit never silently changes an already-materialized recommendation's meaning)

**Lifecycle**:

- `status`: `PENDING` | `ACCEPTED` | `DISMISSED`
- `is_active` / `resolved_at` — **yes, needed in addition to `status`** (mirrors `Risk`): `status` is the
  owner's decision; `is_active`/`resolved_at` is whether the *underlying condition still holds* on the most
  recent re-evaluation. A `PENDING` row can become inactive (source resolved) without the owner ever having
  acted — exactly like an unresolved `Risk` can later resolve. `ACCEPTED` and `DISMISSED` are owner
  decisions and are never reverted by re-evaluation alone (§5).
- `accepted_at` (nullable)
- `dismissed_at` (nullable)
- `resolved_price_item_id` (nullable — the actual `PriceItem` used at acceptance time, captured for audit;
  see §6 for why this is a snapshot, not a live-resolved value after the fact)

**No FK to a specific `SurfacePlannedWork` row** — per §2, that row is not durable. Provenance from an
accepted recommendation to "the resulting planned work" is **semantic, not row-level**:
`(surface_id, resolved_price_item_id, accepted_at)`. This is sufficient to answer "did this recommendation
result in this PriceItem being added to this surface's plan, and when" for auditability and future
reporting (Stage 15), without a fragile FK. It also correctly satisfies "manually-created identical work
must remain distinguishable from recommendation-created work where provenance matters": any `WorkPlan`
occurrence of that PriceItem *without* a corresponding `ACCEPTED WorkRecommendation` row is, by definition,
not recommendation-provenanced — no extra marker on `SurfacePlannedWork` itself is needed.

No fields are added for hypothetical future use (e.g., no quantity, no coefficient, no scheduling field) —
those remain Stage 12/13 concerns entirely outside this table.

---

## 5. Materialization contract

**Trigger point: a separate, explicit endpoint** — not folded into `POST .../risks/evaluate`, and not
triggered on GET.

Rationale: Stage 7's risk evaluation stays untouched (single responsibility; D4 explicitly keeps Stage 7
authoritative and separate); the frontend retains full explicit control over when recommendations are
(re-)computed, exactly like every other Stage 10/11 "nothing happens automatically" boundary; and evaluating
strictly on an explicit call (never on GET) keeps a plain list-read side-effect-free and cacheable.

Proposed shape: `POST /api/projects/{project_id}/rooms/{room_id}/work-recommendations/evaluate` — the
canonical API prefix in this repository is `/api` (verified in `backend/app/main.py`'s router
registration; there is no `/api/v1` prefix anywhere in the actual routes, only in the `api/v1/` *package*
path used for organizing endpoint modules), and this exact `projects/{project_id}/rooms/{room_id}/...`
shape mirrors the existing `POST /api/projects/{project_id}/rooms/{room_id}/risks/evaluate` route
verbatim (`backend/app/api/v1/endpoints/risks.py:92-93`) — room-scoped, since `Risk` itself
is room-anchored and a room can have WALL/FLOOR/CEILING/ROOM results simultaneously). It:

1. Loads all currently **active** `Risk` and `InspectionFinding` rows for the room (same source data Risk
   evaluation already loads — no new query pattern).
2. For each `WorkRecommendationRule` whose `trigger_code` matches an active `Risk.rule_code` or
   `InspectionFinding.finding_key` present in that set, computes the identity signature and reconciles:
   - Existing `PENDING` or previously-inactive-now-active-again row with the same identity → reused,
     `is_active = True`, `resolved_at = None`.
   - No existing row with that identity → new row materialized, `status = PENDING`.
   - Existing row **not** matched by this evaluation → `is_active = False`, `resolved_at = now()` — **but
     only if its `status` is still `PENDING`**. `ACCEPTED` rows are never touched by re-evaluation (§4, §6).
     `DISMISSED` rows keep their status; `is_active` may still update for informational purposes, but the
     dismissal itself only clears if the *signature* changes (a genuinely new/changed condition) — never
     merely because the same condition recurred (§6).
3. Single atomic commit for the whole room's reconciliation, mirroring `RiskService._reconcile_risks`
   exactly.

Deterministic, idempotent (calling it twice with unchanged inspection state changes nothing), testable in
isolation from Stage 7, and introduces no hidden WorkPlan mutation — this endpoint only ever writes to
`WorkRecommendation` rows.

---

## 6. Accept command

```
POST /api/projects/{project_id}/work-recommendations/{recommendation_id}/accept
```

(Canonical `/api` prefix, verified against `backend/app/main.py`'s router registration — this repository
does not use an `/api/v1` URL prefix; `api/v1/` is only the Python package path under which endpoint
modules are organized. Flat under `project_id` — the target `room_id`/`surface_id` needed for ownership
validation is already denormalized on the `WorkRecommendation` row itself, per §4; no need to nest the
route under room/surface, unlike the room-scoped evaluate endpoint in §5.)

**Request** (all fields optional): `{ "price_item_id": "<uuid>" }` — an explicit manual override, used only
when the semantic code failed to resolve, or the owner deliberately wants a different `PriceItem`
(supporting D3's manual-fallback clause from day one at the contract level, even before a manual-picker UI
exists).

**Response**: the updated `WorkRecommendation` (status, `resolved_price_item_id`, `accepted_at`). The
frontend re-fetches the Surface/WorkPlan separately (existing "always authoritative refetch" pattern) —
this endpoint does not return the WorkPlan itself.

**Ownership checks**: resolve `project_id → room_id → surface_id` via the exact same chain-ownership query
already used by `SurfaceWorkPlanService._ensure_surface_owned` — never trust a client-supplied ID beyond the
authenticated owner's own resource graph.

**Target validation**: `target_kind` must be `WALL`, `FLOOR`, or `CEILING`. A `ROOM`-kind recommendation
accepted here is rejected — **422** — defense-in-depth for D2, even though the UI never exposes an accept
action for ROOM cards.

**State validation**:
- `status = ACCEPTED` already → **idempotent no-op**: return the current row unchanged, 200. No second
  WorkPlan append, ever, on retry.
- `status = DISMISSED` → **409** — a dismissed recommendation cannot be accepted directly; the owner must
  call reconsider (§7) first. This is a deliberate two-step requirement, not an oversight — it keeps
  "the owner changed their mind" an explicit, auditable action distinct from "the owner is re-clicking
  accept without realizing it was dismissed."
- `is_active = False` (source resolved since materialization, but never re-evaluated as inactive at the
  `status` level because it's still `PENDING`) → accept is still **allowed** — this is an accepted narrow
  staleness window (the owner is looking at a snapshot UI), not a correctness issue; the next explicit
  re-evaluation naturally reconciles state going forward. This exactly mirrors Stage 10's own accepted
  "DRAFT Estimate can go stale until Sprawdź zmiany" staleness tolerance.

**PriceItem resolution** (§ per D3):
1. If the request supplies `price_item_id` explicitly, use it (still subject to the checks below).
2. Otherwise, resolve `owner_id + recommended_work_code` against `PriceItem.code` (unique per owner).
3. No matching `PriceItem` (missing semantic code, or a supplied `price_item_id` that doesn't exist or
   belongs to another owner) → **404**, reusing the existing `PriceItemNotFoundError` verbatim (corrected
   here from an earlier, invented `422 RECOMMENDATION_UNRESOLVED` draft that didn't reuse an existing
   exception) — no silent substitution, no fallback to a market/reference price under any circumstances.
4. Matching `PriceItem` is `is_archived = True` → **422** — the existing Stage 10 "archived item cannot be a
   *new* addition" guard applies unchanged; the response signals this distinctly from "unresolved" so a
   future UI can offer "restore it" vs. "pick a different item."
5. `price = NULL` (unresolved/"Do ustalenia") → **does not block** — Stage 10's own rule (NULL only blocks
   `finalize()`, never adding to a WorkPlan) applies unchanged.
6. `price = 0.00` → treated as any other valid explicit price; no special handling.

**Target existence**: the target Surface must already have a `SurfaceWorkPlan` (i.e., the owner has already
set a substrate). If none exists yet, accept fails with **404** (reusing the existing `SurfaceWorkPlanNotFoundError`
verbatim — the same exception and HTTP mapping `work_plans.py`'s own `apply_to_room_walls` endpoint already
uses for an identical "no plan yet" case; corrected here from an earlier, factually mismatched **409** draft)
— the command never invents a `substrate`, since that is a required, owner-declared field Stage 11 has no
authority to guess (matches D5's "must not... apply automatically").

**Mutation (as implemented, 11C.1)**: exactly one new planned-work occurrence is appended via a new,
additive-only primitive — `SurfaceWorkPlanService.append_one_planned_work_no_commit(plan, price_item)` —
which never calls `_rewrite_works` and never deletes/renumbers any existing row (unlike `set_plan`/
`replace_planned_works`/`apply_to_room_walls`, which all still fully replace the child rows exactly as
before — that full-replace behavior is completely unchanged by 11C). The new primitive reuses only the
archived-item check's *outcome* (an item being newly added can never be archived), not `_resolve_owned_items`
itself (that helper is list/Counter-oriented for a full replacement batch; a single additive append needed
its own equally strict but simpler check). No global deduplication, ever (Stage 10 duplicate semantics stay
fully valid, per D5) — two different recommendations may each append the same `PriceItem` independently.

**Transaction boundary and locking (as implemented, 11C.1)**: `set_plan`/`replace_planned_works`/
`apply_to_room_walls` still each call `await self.db.commit()` internally, exactly as before — the accept
command never calls any of them. Instead, `WorkRecommendationService.accept_recommendation` performs the
entire flow (lock recommendation → validate status/target → lock plan → resolve/validate PriceItem → append
one work, flush-only → update recommendation snapshot) and calls `await self.db.commit()` **exactly once**,
at the very end. Two `SELECT ... FOR UPDATE` row locks are acquired, in this fixed, never-inverted order:
1. **`WorkRecommendation` row** (`SELECT ... FOR UPDATE OF work_recommendations`) — acquired first, and only
   on that one table even though the ownership query joins `Room`/`Project`. Protects same-recommendation
   idempotency: two simultaneous accept requests for the same recommendation cannot both observe `PENDING`
   and both append: the loser blocks until the winner commits, then re-reads `status = ACCEPTED` and takes
   the idempotent no-op path. Verified against the real local PostgreSQL instance with two genuinely
   concurrent connections (not just reasoned about) — the second request's lock acquisition measurably
   blocked until the first committed, and exactly one `SurfacePlannedWork` row resulted.
2. **`SurfaceWorkPlan` row** (`SELECT ... FOR UPDATE`, via the new `SurfaceWorkPlanService.lock_plan`) —
   acquired second, only after the recommendation is confirmed actionable. Protects a *different* invariant:
   two *different* recommendations targeting the *same* plan, accepted concurrently, must never compute the
   same next `position` (the DB's `UniqueConstraint(work_plan_id, position)` is the last-resort backstop;
   this lock prevents the race from ever reaching it in the normal case).
Both locks mirror the exact, already-accepted `EstimateService._lock_project` precedent (`SELECT ...
FOR UPDATE` to serialize a specific row's concurrent writers) rather than inventing a new mechanism.

**REVEAL-category guard (Stage-11-acceptance-specific, not a Stage 10 invariant)**: if the resolved (semantic
or manual-fallback) `PriceItem.category == REVEAL`, acceptance is rejected — **422**. This check lives
entirely inside `WorkRecommendationService._resolve_accept_price_item`, never inside
`SurfaceWorkPlanService`. The existing, deliberately permissive Stage 10 manual Work Plan picker
(`set_plan`/`replace_planned_works`, used by `SurfaceWorkPlanEditor.tsx`) has no category restriction at
all and is **unchanged** — an owner can still manually add a REVEAL item to a Surface plan through the
existing picker exactly as before; only the *automated, recommendation-driven* acceptance path introduced
by Stage 11 rejects it, because Opening/reveal recommendation acceptance is explicitly deferred (D1) and a
REVEAL item's pricing/quantity semantics do not match a Surface's area-based quantity derivation.

**No Estimate interaction of any kind** (§8) — the accept command never touches `Estimate`/`EstimateLine`.

**No navigation** — this is a backend contract; the frontend decides what to show next (§9), but the command
itself has no navigation side effect to specify.

---

## 7. Dismiss / reconsider contract

- `PENDING → DISMISSED`: explicit owner action, sets `status = DISMISSED`, `dismissed_at = now()`.
- `DISMISSED → PENDING` ("reconsider"): two ways this happens, both legitimate:
  - **Automatic**, only when the *identity signature changes* on the next materialization pass (§5) — a
    genuinely different underlying condition is a new fact, not the same dismissed one recurring.
  - **Explicit**, via a dedicated reconsider action the owner can invoke at any time regardless of whether
    the signature changed — "I changed my mind" is always available.
  - Critically: the *same, unchanged* signature recurring on re-evaluation must **not** silently flip
    `DISMISSED` back to `PENDING` — a dismissal is sticky for the condition it was made against.
- `PENDING → ACCEPTED`: the accept command (§6).
- `ACCEPTED → (terminal)`: **no further status transition exists.** Once accepted, the `WorkRecommendation`
  row is a historical record; the resulting WorkPlan occurrence is, from that point on, ordinary
  owner-controlled planned work, editable/removable only through the normal Surface Work Plan editor — never
  through the recommendation lifecycle again. If the source `Risk`/`Finding` later resolves,
  **the accepted WorkPlan item is never touched** — this is an explicit Stage 11 invariant, matching D5's
  requirement not to silently remove accepted work.

---

## 8. Estimate interaction — explicit non-interference invariant

No new Estimate integration is required or added. After an accepted recommendation changes a
`SurfaceWorkPlan`:

- An existing DRAFT Estimate's numbers **remain exactly as they were** — this already-existing Stage 10
  behavior (no staleness flag, no auto-sync, verified in Stage 11A) needs no change.
- The owner uses the existing, unmodified "Sprawdź zmiany" (`preview_regeneration`, verified read-only —
  no `db.add`/`commit`/`delete` in its body) to see the impact, then the existing, unmodified explicit
  "Aktualizuj kosztorys" (`regenerate_draft`) to apply it.
- Stage 11 introduces **zero coupling** from `WorkRecommendationService`/the accept command to
  `EstimateService` — this must remain true through implementation, not just in this document.

---

## 9. Mobile interaction contract (architecture only — no UI implemented in 11B.0)

`RiskPanel.tsx` gains, per risk/finding card that has at least one matching `WorkRecommendation`, a
collapsed "Zalecane prace (N)" progressive-disclosure section:

- Actionable targets (WALL/FLOOR/CEILING): a checkbox per recommendation, **default unchecked**; a primary
  "Dodaj wybrane do planu prac" action, disabled until ≥1 selected, calling the accept command once per
  selected recommendation; a self-clearing confirmation ("N prac dodano do planu") on success, reusing the
  existing self-clearing-status pattern already used elsewhere in this codebase.
- ROOM-level (advisory, D2): the recommendation is shown with the same card styling, but **no checkbox, no
  accept action** — purely informational, same as `RiskPanel`'s existing risk-only display today.
- Unresolved code (§6, PriceItem resolution failed or archived): shown as an explicit "no matching PriceBook
  item — select manually" state, never silently substituted with a different item and never hidden.
- **Never** auto-navigates to the Surface editor or the Estimate screen, and never triggers regeneration —
  matching §8.

---

## 10. Stage boundaries (explicit non-goals, reaffirmed)

Stage 11 does not implement: material/quantity coefficients (Stage 12), technological sequencing or drying
breaks (Stage 13), photo/defect annotation (Stage 14), PDF generation (Stage 15), or contracts (Stage 16). It
does not redesign Estimate generation, does not add Opening/reveal targeting (D1, deferred), and does not add
ROOM-level target selection (D2, deferred).

---

## 11. Proposed implementation substages

| Substage | Goal | Migration | Non-goals |
|---|---|---|---|
| **11B.0** | This document + Stage 10 contract verification (this sub-stage) | No | No models, no runtime code |
| **11B.1** | `WorkRecommendationRule` + `WorkRecommendation` models, migration, seed a handful of rule mappings | Yes | No evaluate/accept endpoints yet |
| **11B.2** | Materialization endpoint (§5) + list/dismiss/reconsider endpoints | No | No accept-to-WorkPlan mutation yet |
| **11C** | Accept command (§6) — recommendation → `SurfaceWorkPlan` for WALL/FLOOR/CEILING | No | No Opening support, no UI yet |
| **11D** | Mobile UI (§9) — `RiskPanel.tsx` extension | No | No visual redesign beyond the new section |
| **11E** | Hardening + real Telegram owner acceptance (Stage-10H-style closure gate) | No | No new functionality |

Opening/reveal support (D1) and ROOM-level target selection (D2) remain deferred unless the owner explicitly
reopens either.
