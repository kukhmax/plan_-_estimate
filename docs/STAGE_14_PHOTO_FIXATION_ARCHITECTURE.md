# Stage 14 — Photo Fixation & Defect Annotations: Audit & Architecture (14A)

- **Date**: 2026-09-27
- **Branch / HEAD**: `stage-14` @ `4249ef9` (= `origin/stage-14`; Stage 13 COMPLETE / OWNER ACCEPTED / PRODUCTION
  VERIFIED; production runtime `7b5aaf0`, DB `0030_surface_work_executions`)
- **Sub-stage**: 14A — **audit & architecture only**. No code, no migration, no dependency, no production change.
- **Status**: **Stage 14A — COMPLETE / OWNER ACCEPTED** (2026-09-28). The decisions in §20 are **OWNER APPROVED**
  (final owner decisions recorded in §21). Stage 14 overall remains **IN PROGRESS**; **14B NOT STARTED** — it starts
  only with explicit owner approval.
- **Revision 2 (2026-09-28)**: owner correction pass applied — private object storage (no VM disk as photo store),
  non-atomic backup model with integrity checks, annotation = location evidence only (finding stays the defect source of
  truth), durable finding lineage, report inclusion default false, 8-value category list, HEIC pending verification,
  no original-download UI, explicit attachment CHECK design, explicit storage keys, upload state machine, revised
  substages.
- **Closure (2026-09-28)**: final owner decisions OD-1…OD-12 recorded (Cloudflare R2 Standard primary, Oracle Object
  Storage independent backup target, lineage_id, 300 s configurable signed-URL TTL, 8 GB / 10 GB quota policy); see §21
  and §23 (production state preserved).

Planned scope already recorded in `docs/development-progress.md` (Stage 14 roadmap detail) and honoured here:
Project/Room/WALL/FLOOR/CEILING attachment, camera + gallery, several photos per target, notes and timestamps,
thumbnails, an S3-compatible storage abstraction, metadata separate from binaries; tap-to-place annotations with
normalized x/y, several per photo, each with defect category, comment, severity and status; the defect-category list
must not be frozen prematurely; forward chain Photo/Annotation → Finding → Risk → Recommended work → Estimate → PDF
(Stage 15), none of which Stage 14 automates.

---

## 1. Current-state audit

### 1.1 Candidate parent entities (verified in code)

| Entity | Identity | Ownership path | Archive | Hard delete via API | Recreated? | Durable photo parent? |
|---|---|---|---|---|---|---|
| Project | UUID | `projects.owner_id` | `is_archived` | no | no | **yes** |
| Room | UUID | room → project | `is_archived` | no | no | **yes** |
| Surface (WALL / FLOOR / CEILING / OTHER) | UUID | surface → room → project | `is_archived` (canonical FLOOR/CEILING cannot be archived) | no | no | **yes** (FLOOR/CEILING are canonical Surface rows since 13F-PRE) |
| Opening (incl. reveal data) | UUID | opening → surface → … | `is_archived` | no | no | **yes** |
| Inspection | UUID | `room_id` (+ optional `surface_id` or `plane`) → project | `is_archived` | no | no | **yes** |
| InspectionAnswer | UUID | inspection | — | **deleted + recreated** by `replace_answers` | **yes** | **no** (ephemeral) |
| ChecklistQuestion | UUID | global template catalog | — | no | no | only as an optional *reference* |
| InspectionFinding | UUID | inspection | `is_active` / `resolved_at` (never deleted) | no | UUID stable while continuously active; a finding resolved and later re-confirmed gets a **new** row (reconciliation reuses active rows only) | **yes, with the re-confirmation caveat** (§6) |
| RiskFinding | UUID | risk → room | — | **deleted + recreated** on evaluation | **yes** | **no** |
| WorkRecommendation | UUID | room | status machine (PENDING/ACCEPTED/DISMISSED…) | no | no | not needed in v1 (derived from findings) |
| SurfaceWorkPlan | UUID | surface | — | no (one per surface) | no | not needed (surface is the parent) |
| SurfacePlannedWork | row UUID **ephemeral**; `occurrence_key` durable (Stage 13 D13) | plan → surface | — | rows recreated on every save | **row: yes / key: no** | only by **`occurrence_key`**, never `id` |
| SurfaceWorkExecution | UUID; keyed by `occurrence_key`; lazy (no row = NOT_STARTED) | plan | kept as detached history | no | no | **no** (may not exist before work starts) |
| Estimate / EstimateLine | UUID | project | status DRAFT/FINAL | manual lines only | lines re-matched | no (Stage 15 consumer, not a photo parent) |
| OpeningRevealPlannedWork | row UUID, **no occurrence_key** | opening | — | replaced wholesale | yes | **no** (reveal context = Opening) |

**Dangerous/ephemeral identities (never a photo parent):** `SurfacePlannedWork.id`, `InspectionAnswer.id`,
`RiskFinding.id`, `OpeningRevealPlannedWork.id`, `WorkflowTemplateStep.id`, `EstimateLine.id`.

### 1.2 Defect representation today

`InspectionFinding` is **checklist-derived**: `(question_id, finding_key)` identity, `label_key`, `value_snapshot`,
`is_active/resolved_at`. It has no free description, no location, no severity, no category of its own and cannot be
created by the owner outside a checklist answer. Stage 7 risks and Stage 11 recommendations consume `finding_key`.
It is the **source of truth for a defect/finding** ("the checklist says there are cracks / old paint"); Stage 7
risks and Stage 11 recommendations already consume it. It cannot record *where* on a photo the defect is visible.
Owner correction (Rev. 2): no parallel `Defect` model and no defect data on annotations — an annotation is only
**location evidence** on a photo (§8); severity, lifecycle, category and recommendation state stay with the finding
and its downstream Stage 7/11 records.

### 1.3 Infrastructure

- Production: Oracle A1 VM (1 OCPU, 6 GB RAM, ~47 GB boot volume shared by OS, Docker images and PostgreSQL),
  Docker Compose (`postgres` with named volume `postgres_data`, stateless `backend`, `frontend`, `caddy`), behind
  Cloudflare (origin certificate) → Caddy → backend `/api/*`.
- **No persistent storage for application files exists today**; the backend container filesystem is replaced on
  every deploy. Writing photos inside the container would lose them.
- Backups: manual `pg_dump` to `~/backups` on the same VM; the runbook lists off-server copies (Cloudflare R2 named
  as an option), rotation and a tested restore as future improvements. **A DB backup alone would not protect photos.**
- Backend has no Pillow, `python-multipart`, HEIF or S3 client dependency; the frontend has no file input. FastAPI
  file upload needs `python-multipart`.

---

## 2. Use-case matrix

One asset system; the "where" is a typed **context** on an attachment (§3), the "why" is a **category** (§5).

| # | Use case | v1 | How |
|---|---|---|---|
| A | Project / object photo | direct | context `PROJECT` |
| B | Room photo | direct | context `ROOM` |
| C | Surface photo (wall / floor / ceiling / other) | direct | context `SURFACE` |
| D | Opening / reveal photo | direct | context `OPENING` (reveals belong to the opening) |
| E | Inspection photo | direct | context `INSPECTION`, optional `question_id` reference |
| F | Defect photo | direct | context `FINDING` (the finding is the defect); point markers on that attachment show where it is visible |
| G | Work execution photo (before / during / after) | direct | context `WORK` = surface + `occurrence_key` |
| H | Dispute / damage | derived | category `DAMAGE` (+ report inclusion) on any context |

Eight use cases, **one** asset table, **one** attachment table, **one** annotation table.

---

## 3. Canonical media model — options

| | A: single photo table, nullable FK columns | **B: asset + attachment (typed nullable FKs + context enum + CHECK)** | C: asset + polymorphic `(entity_type, entity_id)` | D: purpose-specific photo tables |
|---|---|---|---|---|
| FK integrity | real FKs | **real FKs**; CHECK enforces exactly the context's FKs | **none** (the DB cannot know what `entity_id` points to; orphans and cross-owner ids undetectable) | real FKs |
| Same image in several contexts | duplicates rows/files | **yes, one stored file, several attachments** | yes | duplicates |
| Ownership/security | FK chain | FK chain + denormalized `project_id` | per-type code only | per table |
| Query complexity | one table | one join | untyped dispatch | UNIONs |
| Migrations | one | additive, three tables | one | many |
| Stage 15 reporting | fine | **one ordered query per project** | type dispatch | UNION of N tables |
| Archive | per row | per asset **and** per attachment | per row | per table |
| Extensibility | column per context | **column + enum value + CHECK branch** | trivial but unsafe | new table |
| Deletion safety | file + context mixed | **file lifecycle separate from context lifecycle** | ok | ok |

**OWNER APPROVED (D14-1, D14-2): Option B**, with the concrete column/CHECK design in §15. It stays manageable: 7 contexts,
8 target columns, one CHECK with one branch per context, and **leaf-only** targets (the ancestor chain is derived by
joins, never duplicated). Rejected alternatives: C (loses referential integrity — a deleted, foreign or invented id
cannot be caught by the database) and D (seven tables, UNION-only reporting). If a future context would need more than
two target columns, the fallback is a **typed attachment table per context** (D-style, each with NOT NULL FKs) behind the
same asset table — never a polymorphic target.

---

## 4. Storage (Rev. 2 — owner correction OD-1/OD-2)

### 4.1 Decision

- **The Oracle VM boot disk (and any Docker volume) is never the durable store for photos** — originals, display
  derivatives and thumbnails live only in **private object storage** from 14B onward.
- The VM/container may hold **bounded temporary files** during upload processing only: a dedicated temp directory,
  per-request size cap (upload limit + derivatives), removal in `finally` on every path, and a startup sweep of leftover
  temp files older than a configured age (deterministic cleanup, no worker).
- The application talks to storage only through a provider-neutral **`MediaStorage` port**:
  `put_object(key, bytes/stream, content_type)`, `head_object(key)`, `open_object(key)` (server-side read),
  `presigned_get(key, ttl)`, `list_prefix(prefix)` (integrity checks). Implementations: `S3CompatibleStorage` (one
  adapter for any S3-API provider) and `InMemoryStorage` for tests. **No provider-specific behaviour in the domain
  model**; provider, endpoint, bucket and credentials are configuration/secrets.

### 4.2 Provider decision (OD-1 — OWNER APPROVED)

**Cloudflare R2 Standard is the primary production media storage**: a private bucket (never public), no public
canonical photo URLs, accessed only through the provider-neutral `MediaStorage` port and its S3-compatible
implementation. The domain model contains no Cloudflare-specific concept; switching provider changes configuration and
`storage_backend`, never asset identity or business relationships. **Oracle Object Storage is the independent secondary
backup target** (§13). Nothing is created by 14A: the R2 bucket, API tokens and any Cloudflare/Oracle account, billing
or tier setting are Stage 14B actions performed explicitly with the owner.

Comparison that informed the decision ("verify" items are confirmed during 14B, not assumptions):

| | Cloudflare R2 | Oracle Object Storage |
|---|---|---|
| API | S3-compatible | native OCI API + S3-compatibility API |
| Private bucket + presigned GET | yes (verify current docs) | yes via S3 compat / pre-authenticated requests (verify) |
| Versioning / lifecycle for backup | verify current support | object versioning + replication/lifecycle (verify) |
| Egress to the Oracle VM / to phones | no egress fees on R2 (verify current pricing) | intra-region/Always-Free terms (verify) |
| Operational fit | already named in the runbook for off-server DB backups; separate provider = off-site by construction | same cloud as the VM; must still plan an off-site copy |
| Secrets | access key + secret (new env secrets) | customer secret keys for S3 compat (new env secrets) |

Both fit the adapter; the choice is an owner decision after verifying price, versioning, presigned URLs and region.

### 4.3 File identity and keys (Rev. 2)

`photo_assets` stores **explicit, immutable variant keys** plus the backend identity, not a URL:

- `storage_backend` — configured backend name (e.g. `r2-primary`), so a later migration between providers is explicit
  per asset;
- `storage_key_original`, `storage_key_display`, `storage_key_thumbnail` — e.g.
  `v1/{owner_id}/{project_id}/{asset_id}/original.{ext}`, `…/display.jpg`, `…/thumb.jpg`.

**Why explicit keys rather than deriving from one prefix:** the key scheme can evolve (a `v2/` layout, different
derivative formats or sizes) without silently re-pointing old rows; integrity checks compare exact keys; restore and
provider migration work from data, not from code conventions. Cost: three short strings per asset. Keys contain only
UUIDs (never names or the original filename); the `owner/project` path segments help organization and cleanup but are
**never** used for authorization (§10). No key segment depends on a mutable value — client name, project name, room
name, surface label or filename are never part of a key; the original filename is metadata only. The provider may change
(objects copied under the same keys) without changing asset ids, attachments, annotations or any business relation. Objects are **write-once**: a key is never overwritten after the asset is
`READY`, and nothing is physically deleted in v1.

### 4.4 Formats, limits, derivatives (Rev. 2 — OD-8, OD-9)

- **Accepted in v1: JPEG, PNG, WebP** — type determined by decoding, never by extension or client MIME.
- **HEIC/HEIF: PENDING TECHNICAL VERIFICATION** (not owner-approved). Before enabling: decoder/library maturity, ARM64
  Ubuntu compatibility, Docker build, memory and CPU cost on 1 OCPU / 6 GB, EXIF orientation handling, derivative
  generation, and actual iOS Telegram Mini App upload behaviour (whether the WebView hands over HEIC or converts to JPEG).
  Until then a HEIC upload is rejected with a clear message. The format enum and the decoder step are pluggable so
  HEIC can be added without a schema redesign. No dependency is added in 14A.
- **Limits (provisionally accepted):** 25 MB encoded upload, 60 MP decoded; longest edge ≤ 12 000 px; SVG, GIF,
  TIFF, RAW, PDF rejected.
- **Stored:** original bytes unchanged (private evidence), **display** (JPEG ≈ q85, longest edge 2048 px, orientation
  applied, all metadata stripped), **thumbnail** (JPEG, longest edge 480 px).
- **Original download:** stored privately; **no "download original" UI in Stage 14 v1**. Backend/report code may read
  the original server-side when authorized (Stage 15 may use it).
- Still to verify (not guessed): Telegram WebView camera/gallery behaviour on iOS/Android, and the Cloudflare
  request-body limit for the current plan.

### 4.5 EXIF and privacy

Originals keep their bytes (including EXIF/GPS) and are never exposed to clients in v1; derivatives are re-encoded
with orientation applied and **all EXIF removed**; `captured_at` is read from EXIF `DateTimeOriginal` when present
(device time); **GPS is not extracted or stored**; `sha256` of the original is stored for integrity/idempotency, never
for silent deduplication.

---

## 5. Metadata, categories, report inclusion (Rev. 2 — OD-6, OD-7)

**File metadata — `photo_assets` (immutable after `READY`):** id, owner, project, upload status, storage backend +
three keys, content type, byte size, width/height (after orientation), sha256, original filename, captured_at,
uploaded_at, archived_at, timestamps.

**Context metadata — `photo_attachments` (editable):** context + target, category, caption, `include_in_report`,
position, archived_at, timestamps.

**Categories — v1 vocabulary on the attachment (never on the immutable asset):**

| Code | Meaning |
|---|---|
| `GENERAL` | overview / reference |
| `BEFORE` | condition before any work |
| `DEFECT` | defect evidence |
| `PREPARATION` | preparation work (intentionally separate from BEFORE) |
| `IN_PROGRESS` | during the work |
| `HIDDEN_WORK` | work before it is covered (roboty zanikające) |
| `AFTER` | completed result |
| `DAMAGE` | damage / disputed condition |

**`include_in_report`** belongs to the **attachment** (the same image can be internal evidence in one context and
customer-facing in another) and **defaults to `false`**: nothing reaches a Stage 15 client document unless explicitly
selected. Before/after is category + context grouping (same surface or same `occurrence_key`), no pair entity.

---

## 6. Findings, annotations and lineage (Rev. 2 — OD-4, OD-5)

### 6.1 Finding stays the source of truth

`InspectionFinding` (and the Stage 7 risks / Stage 11 recommendations derived from it) owns the defect's identity,
category (`finding_key`/`label_key`), lifecycle (`is_active`/`resolved_at`), severity (Stage 7 risk severity) and
recommendation state. **Annotations store none of these.** A photo documents a finding through a `FINDING`-context
attachment; point markers on that attachment show *where* it is visible.

### 6.2 Exact current re-confirmation semantics (audited)

- Findings are materialized only when an inspection is **completed** (`complete_inspection` → `_reconcile_findings`).
- Reconciliation identity is `(question_id, finding_key)` **within one inspection**, matched against **active**
  findings only: a confirmed active finding is reused (same UUID, snapshot refreshed); an active finding no longer
  confirmed is set `is_active=false`, `resolved_at=now`; nothing is deleted.
- An inspection can be reopened (COMPLETED → DRAFT), answers replaced, and completed again. A finding resolved in one
  completion and confirmed again in a later one gets a **new row** (the resolved row is not reactivated).
- A new inspection of the same surface is a new survey with its own findings (not a re-confirmation).
- Downstream identity depends on finding UUIDs: risk/recommendation `source_signature` is SHA-256 over source
  finding UUIDs, and `risk_findings.finding_id` / `work_recommendations.finding_id` reference them (SET NULL).

### 6.3 Lineage options

| | A: stable lineage key on findings | B: `supersedes_finding_id` self-FK | C: attach to inspection + question (+ optional finding) | D: read-time grouping heuristic |
|---|---|---|---|---|
| Durable | **yes** | yes | partly (a multi-option question yields several findings → ambiguous) | no |
| Migration | add `lineage_id UUID NOT NULL` + deterministic backfill (one id per `(inspection, question, finding_key)` group) + index | add nullable self-FK + backfill chains by `created_at` | none on findings; weaker evidence target | none |
| Query for "all evidence of this finding" | one equality join on `lineage_id` | recursive walk of the chain | by question, then guess | heuristic |
| Effect on Stage 7/11 (UUID-based signatures) | **none** (finding UUID semantics unchanged) | none | none | none |
| Historical correctness | each photo stays on the exact row it documented; history grouped durably | same | loses which finding a photo documented | fragile |
| Ownership | unchanged (finding → inspection → room → project) | unchanged | unchanged | unchanged |

**OWNER APPROVED (OD-5/OD-11, D14-26): A — `inspection_findings.lineage_id`.** On creation, reconciliation reuses the `lineage_id` of the most
recent finding with the same `(inspection_id, question_id, finding_key)` (resolved or not), otherwise a new UUID.
Photos keep their concrete `finding_id` (where the evidence was captured); reads and reports group by `lineage_id`,
so earlier evidence stays visible on the re-confirmed finding without reviving UUIDs (which would silently re-match
dismissed/resolved recommendations via their signatures). Rejected: reactivating the resolved row (changes Stage 6/7/11
semantics). This is a small, owner-approved extension of Stage 6 data, delivered before finding evidence UI (§19).

### 6.4 Annotation (point marker) — minimal

`photo_annotations`: `id`, `attachment_id`, `x`, `y` (normalized 0..1), optional `label` (short text, e.g. "1" or
"rysa przy oknie", ≤ 40 chars), `position` (display order), `created_at`, `updated_at`.

**No `finding_id` on the annotation:** the attachment already carries the context. A marker for finding #1 lives on the
`FINDING`-context attachment of finding #1; the same image attached to finding #2 has its own attachment and its own
markers. Adding `finding_id` to the marker would allow a marker on finding #1's attachment to claim finding #2 —
exactly the contradictory double storage the owner wants prevented. Markers on SURFACE/OPENING/INSPECTION photos are
plain location notes; to tie a spot to a finding, the photo is attached to that finding. Annotations are presentation
evidence, so hard delete of a marker is allowed (the photo is untouched).

**Coordinates:** relative to the orientation-corrected image as displayed; origin top-left, `x` → right, `y` → down,
`0 ≤ x, y ≤ 1` (CHECK); independent of screen size, thumbnail, display derivative and PDF.

---

## 7. Execution photos (confirmed Stage 13 invariants)

- Context `WORK` = `surface_id` + **`occurrence_key`** (no FK; `SurfacePlannedWork.id` is never used) +
  `price_item_id` snapshot so detached work stays labelled.
- **BEFORE photos need no `SurfaceWorkExecution` row** (execution rows are lazy; NOT_STARTED has none).
- New WORK attachments are accepted only for a key **current** in that surface's plan (the existing non-leaking 409);
  existing attachments are never touched by WorkPlan edits.
- **APPEND** does not copy photos (new occurrences start with none); **apply-to-all** does not copy photos (like
  execution state); **REPLACE/removal** never deletes photos — they remain as detached-occurrence evidence on the
  surface and stay reportable; **re-adding the same PriceItem** creates a new `occurrence_key` and cannot inherit the
  old occurrence's photos (matching is by key only).
- Completion never requires a photo; Realizacja suggests a category from the status (NOT_STARTED → BEFORE,
  IN_PROGRESS → IN_PROGRESS, COMPLETED → AFTER), editable.

---

## 8. Upload lifecycle — state machine (Rev. 2)

Object storage and PostgreSQL cannot share a transaction, so the asset carries an explicit status:

```
(new upload_id) ──▶ PENDING ──objects stored──▶ READY
                       │                          (listed, attachable, reportable)
                       └──storage/processing error──▶ FAILED ──retry same upload_id──▶ PENDING
```

1. Authorize the target, check size/quota; stream the body into a bounded temp file; decode, validate, build
   derivatives in temp; compute sha256.
2. **Commit** `photo_assets(status=PENDING, keys, sha256, …)` + its first attachment (invisible while the asset is not
   READY).
3. `put_object` original, display, thumbnail (keys deterministic from the asset id, so a retry re-puts the same keys).
4. **Commit** `status=READY`. On any storage error: commit `status=FAILED`, return an error; temp files are removed in
   `finally` in every case.

Properties: incomplete assets are **never exposed** (every read filters `status='READY'`); **idempotent retry** — same
`upload_id` + same sha256: READY → return it, PENDING/FAILED → resume from step 3; same id + different bytes → 409;
**abandoned objects are detectable** — an object is only ever written after its PENDING row is committed, so any object
whose asset is not READY, or any `PENDING` older than a configured age, is listed by a maintenance query/command; a DB
rollback never pretends an object was removed; cleanup is manual/maintenance in v1 (no worker). Intentional re-upload of
identical bytes under a new `upload_id` is allowed.

---

## 9. Signed media access (Rev. 2)

- Bucket is **private**; no public ACL/static website; knowing a key grants nothing.
- The backend verifies ownership (project → owner) for the listing/viewer request, then issues **presigned GET URLs**
  scoped to **one object key (one asset variant)** with a **configurable expiry**: `PHOTO_SIGNED_URL_TTL_SECONDS`,
  default **300** (OD-10, OWNER APPROVED) — a setting, never a constant in domain logic.
- Delivery per variant (OD-12, OWNER APPROVED): **thumbnail** and **display** — short-lived presigned GET after backend
  ownership authorization; **original** — no client presigned URL in Stage 14 v1, backend/report-side authorized
  retrieval only.
- Knowing an asset UUID, filename, storage key or object URL grants nothing by itself.
- **Originals are stricter:** no presigned original URLs to clients in v1; the original is read only server-side
  (report generation) with the backend's credentials.
- Fallback only: if presigned delivery proves incompatible with the Telegram/browser/runtime environment, the backend
  streams thumbnail/display through an authorized endpoint; the domain model is unchanged.
- The frontend must allow the storage domain in `img-src` (CSP) if one is set; responses must not be publicly cached.

---

## 10. Security

Ownership through `projects.owner_id` on every call; attachment targets validated to belong to the same project;
foreign/invented ids → 404 (non-leaking); WORK with a non-current key → existing 409. Upload hardening: size limit
before decode, decode-based type detection (MIME spoofing ignored), pixel-count guard (decompression bombs), SVG/HTML/
executables rejected, derivatives re-encoded, bounded temp storage with deterministic cleanup.

---

## 11. Mobile UX (unchanged from Rev. 1, adjusted)

One reusable photo section ("Zdjęcia (n)") with progressive disclosure; entry points on Project, Room, Surface
(**Zdjęcia** next to *Rodzaje prac i jakość* / *Realizacja*), Opening options, Inspection questions and findings,
Realizacja (under **Opcje**). Picker via `<input type="file" accept="image/jpeg,image/png,image/webp" multiple>`
(camera/gallery behaviour to be verified on devices), upload queue with progress (XHR) and retry with the same
`upload_id`, thumbnail grid (3/row at 390–412 px, 2 at 320 px), full-screen viewer (caption, category, "Uwzględnij w
raporcie" — off by default, archive), marker mode (tap to place a point, optional short label). No "download original"
action. ≥ 44 px targets, PL/RU, Telegram light/dark.

---

## 12. Quotas and performance

25 MB per file. **Storage quota policy (initial operational defaults, OWNER APPROVED as application policy):** warning
threshold **8 GB**, soft upload cap **10 GB** — both configuration (e.g. `PHOTO_STORAGE_WARNING_BYTES`,
`PHOTO_STORAGE_SOFT_CAP_BYTES`), never domain constants, and not configured in Cloudflare. Usage = sum of stored object
bytes of the owner's assets (all variants). At the soft cap: **new uploads are rejected cleanly** (structured error),
existing media keeps being served, metadata/report/annotation operations keep working, no asset is corrupted or
archived, and an actionable storage warning is shown (also from the warning threshold on). Object storage removes the
VM-disk exhaustion risk for photos; temp processing keeps a bounded temp-space check. Lists return metadata + presigned thumbnail URLs only,
paginated (default 30, max 100) by `(position, uploaded_at, id)`, READY only; badge counts via aggregates; display
variant only in the viewer; originals never sent to the client in v1.

---

## 13. Backup / restore (Rev. 2 — OD-3; "DB first, then media" corrected)

"Dump the DB, then copy media" is **not** an atomic snapshot while uploads continue: an upload can commit between the
two steps, or a restore can combine a DB from time T with objects from another time. The model is instead built so that
inconsistency is **bounded, detectable and recoverable**:

1. **Immutable identity:** asset ids and all three variant keys are immutable; objects are write-once and never
   physically deleted in v1 → the object store is append-only, so any later object copy is a superset of what an
   earlier DB references.
2. **Object durability (OD-3, OWNER APPROVED direction):** primary **Cloudflare R2**; **independent secondary backup
   target: Oracle Object Storage**, deliberately outside the R2 storage domain, filled by a periodic export/copy under
   the same immutable keys and retained at least as long as DB backups. R2 versioning/lifecycle protection may
   complement this but is **not** the independent backup. Nothing is configured in 14A.
3. **Integrity manifest/check (command, 14B design, no tooling yet):** from the DB, every `READY` asset's three keys (and
   sha256 of the original) are checked with `head_object`/`list_prefix`:
   - **DB → missing object** (restored DB newer than objects, or lost object): reported per asset; a missing derivative
     is regenerated from the original; a missing original is reported as evidence loss (asset flagged, never silently
     hidden).
   - **Unreferenced objects** (objects under `v1/…` with no READY asset — uploads after the DB backup point, FAILED or
     abandoned PENDING uploads): reported/quarantined, never auto-deleted.
4. **Recovery procedure (runbook):** restore DB to point T → ensure objects are at least as new as T (live bucket or
   versioned/export copy) → run the integrity check → regenerate derivatives where only derivatives are missing →
   resolve the report with the owner.
5. **Gate:** no production photo uploads before the 14D gate passes: documented DB + media backup procedure,
   independent media backup/export procedure (R2 → Oracle Object Storage), integrity verification, restore procedure,
   and at least one restore drill.
6. **Once uploads exist, a PostgreSQL `pg_dump` alone is no longer a complete application backup.** DB + media backup
   is **not** claimed to be an atomic snapshot; recovery is made auditable through immutable asset/storage identity and
   the integrity check.

---

## 14. Stage 15 read contract

A read-only query service per project, READY + non-archived only, filterable by `include_in_report` (false by
default), category and context: project/room/surface/opening photos; inspection photos; findings **grouped by
`lineage_id`** with their evidence; work occurrences (current and detached, by `occurrence_key`) with
BEFORE/PREPARATION/IN_PROGRESS/HIDDEN_WORK/AFTER photos; each attachment with caption, category,
`captured_at`/`uploaded_at`, display key (original available server-side), width/height, point markers (x, y, label,
position). Stable order: context hierarchy (project → room → surface → opening/inspection/finding/work) → `position` →
`captured_at` → `uploaded_at` → `id`. No PDF layout in Stage 14.

---

## 15. Approved schema design (not created — implemented from 14B/14F)

### 15.1 `photo_assets`

| Column | Type | FK / rule |
|---|---|---|
| `id` | UUID PK | = client `upload_id` |
| `owner_id` | UUID NOT NULL | FK `users.id` **RESTRICT** (evidence must not vanish through a cascade; no user deletion flow exists) |
| `project_id` | UUID NOT NULL | FK `projects.id` **RESTRICT** (projects are archive-only; a future hard-delete must handle photos explicitly) |
| `status` | enum `PENDING`, `READY`, `FAILED` | |
| `storage_backend` | varchar(40) NOT NULL | configured backend name |
| `storage_key_original`, `storage_key_display`, `storage_key_thumbnail` | varchar(255) NOT NULL | UNIQUE each; immutable |
| `content_type` | enum `image/jpeg`, `image/png`, `image/webp` (HEIC later) | decoded type |
| `byte_size`, `width`, `height` | int | CHECK > 0 |
| `sha256` | char(64) NOT NULL | not unique |
| `original_filename` | varchar(255) NULL | display only |
| `captured_at` | timestamptz NULL | EXIF device time |
| `uploaded_at`, `created_at`, `updated_at` | timestamptz | server UTC |
| `archived_at` | timestamptz NULL | soft archive |

Indexes: `(project_id, status, archived_at)`, `(status, created_at)` for abandoned-PENDING checks.

### 15.2 `photo_attachments` — actual columns

`id` PK · `asset_id` FK `photo_assets` RESTRICT · `project_id` FK `projects` RESTRICT (NOT NULL, = asset's project,
service-validated) · `context` enum · targets: `room_id`, `surface_id`, `opening_id`, `inspection_id`, `question_id`,
`finding_id`, `occurrence_key`, `price_item_id` · `category` enum · `caption` varchar(1000) · `include_in_report` bool
NOT NULL DEFAULT false · `position` int · `archived_at` · `created_at`, `updated_at`.

| Context | Required | Optional | Forbidden (must be NULL) | Ownership path | ON DELETE of required target |
|---|---|---|---|---|---|
| `PROJECT` | — | — | all 8 targets | project → owner | — |
| `ROOM` | `room_id` | — | surface, opening, inspection, question, finding, occurrence_key, price_item | room → project | RESTRICT |
| `SURFACE` | `surface_id` | — | room, opening, inspection, question, finding, occurrence_key, price_item | surface → room → project | RESTRICT |
| `OPENING` | `opening_id` | — | room, surface, inspection, question, finding, occurrence_key, price_item | opening → surface → room → project | RESTRICT |
| `INSPECTION` | `inspection_id` | `question_id` | room, surface, opening, finding, occurrence_key, price_item | inspection → room → project | RESTRICT (question: SET NULL — catalog pointer only) |
| `FINDING` | `finding_id` | — | room, surface, opening, inspection, question, occurrence_key, price_item | finding → inspection → room → project | RESTRICT (findings are never deleted) |
| `WORK` | `surface_id`, `occurrence_key`, `price_item_id` | — | room, opening, inspection, question, finding | surface → room → project (+ key current in that surface's plan at attach time) | surface RESTRICT; price_item RESTRICT; occurrence_key no FK |

**RESTRICT rather than CASCADE** on all evidence parents: every parent is archive-only through the API, so RESTRICT
never fires in normal use, and any future hard-delete path is forced to deal with photos explicitly instead of silently
dropping evidence rows (which would also orphan objects). `photo_annotations.attachment_id` is CASCADE (markers have no
meaning without their attachment; attachments are archived, not deleted).

### 15.3 CHECK strategy (portable SQL, no `num_nonnulls` so SQLite tests behave like PostgreSQL)

```sql
CONSTRAINT ck_photo_attachments_context_targets CHECK (
  (context = 'PROJECT'    AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL
                          AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)
  OR (context = 'ROOM'    AND room_id IS NOT NULL AND surface_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL
                          AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)
  OR (context = 'SURFACE' AND surface_id IS NOT NULL AND room_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL
                          AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)
  OR (context = 'OPENING' AND opening_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL AND inspection_id IS NULL
                          AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)
  OR (context = 'INSPECTION' AND inspection_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL
                          AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)          -- question_id optional
  OR (context = 'FINDING' AND finding_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL
                          AND inspection_id IS NULL AND question_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)
  OR (context = 'WORK'    AND surface_id IS NOT NULL AND occurrence_key IS NOT NULL AND price_item_id IS NOT NULL
                          AND room_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL
                          AND finding_id IS NULL)
)
```

Plus: partial unique index on `(asset_id, context, <target columns>)` where `archived_at IS NULL` (no double attach to
the same target); indexes on each target column and `(project_id, context, archived_at)`. **Manageability verdict:**
leaf-only targets keep it to one row-local CHECK with 7 branches; adding a context is one enum value, one column at most
and one branch. Cross-row consistency (a room belongs to the project) is service-validated, as everywhere else in the
codebase; optional later hardening: composite FKs (e.g. `(surface_id, project_id)` against a unique
`(id, project_id)` on a view/denormalized column) if multi-tenant teams arrive. If contexts grow beyond this, switch to
typed per-context attachment tables (§3), not a polymorphic target.

### 15.4 `photo_annotations`

`id` PK · `attachment_id` FK `photo_attachments` CASCADE · `kind` enum `POINT` (v1) · `x`, `y` numeric(7,6) CHECK
`0 ≤ v ≤ 1` · `label` varchar(40) NULL · `position` int · `created_at`, `updated_at`. No defect category, severity,
status or finding reference (§6.4).

### 15.5 Finding lineage (Stage 6 extension, for the finding-evidence substage)

`inspection_findings.lineage_id UUID NOT NULL` + index; migration adds nullable → deterministic backfill (one new UUID
per `(inspection_id, question_id, finding_key)` group, shared by all rows of the group) → NOT NULL. Reconciliation sets
it as in §6.3. Finding UUIDs, signatures and Stage 7/11 behaviour unchanged.

No migration is created in 14A.

---

## 16. Approved API design (not implemented — 14C onward)

| Method & path | Purpose |
|---|---|
| `POST /api/projects/{p}/photos` (multipart: `file`, `upload_id`, context + target, `category`, `caption`) | upload + first attachment; state machine §8; idempotent |
| `GET /api/projects/{p}/photos?context=&room_id=&surface_id=&opening_id=&inspection_id=&finding_id=&lineage=&occurrence_key=&category=&include_in_report=&archived=&limit=&cursor=` | READY attachments + asset facts + presigned thumb/display URLs + marker counts |
| `GET /api/projects/{p}/photos/counts?…` | badge counts |
| `POST /api/projects/{p}/photos/{asset_id}/attachments` | attach a READY asset to another context |
| `PATCH /api/projects/{p}/photo-attachments/{id}` | caption, category, include_in_report, position |
| `POST …/photo-attachments/{id}/archive` · `/restore` | detach/restore one context |
| `POST /api/projects/{p}/photos/{asset_id}/archive` · `/restore` | archive/restore the asset everywhere |
| `GET/POST /api/projects/{p}/photo-attachments/{id}/annotations`, `PATCH/DELETE …/annotations/{aid}` | point markers |
| `GET /api/projects/{p}/photo-storage` | usage |

No original-download endpoint for clients in v1. Ownership on every call; foreign/invented ids → 404; WORK with a
non-current key → existing 409; upload of a non-READY/foreign asset into another context → 404/409.

---

## 17. Frontend components (proposal)

Reusable: `PhotoPicker` (input, upload queue, progress, retry with the same `upload_id`), `PhotoThumbGrid`,
`PhotoViewer` (metadata edit incl. report toggle, archive), `PointMarkerLayer` (render/place normalized points with
optional label), `PhotoSection` (badge + collapse + picker + grid, parameterized by context). Context wrappers only:
Project/Room/Surface/Opening, `FindingEvidence` (grouped by lineage), `WorkPhotos` in Realizacja.

---

## 18. Rollout

Additive migrations only; no backfill except the deterministic finding `lineage_id`; existing projects unchanged.
Infrastructure (provider, private bucket, secrets, adapter, pipeline, runbook) is deployed **with uploads disabled**
(feature flag) before any user-facing upload. Rollback: application rollback keeps tables and objects; a DB downgrade is
only acceptable before real use, and objects are never auto-deleted (the integrity check lists them).

---

## 19. Stage 14 sub-stages (final — OWNER APPROVED)

Hard rule: **no production photo uploads are enabled before the 14D backup/restore gate passes.** Every sub-stage
follows the normal stage workflow (verification → owner acceptance → commit → push/deploy only with explicit approval).

| Sub-stage | Scope | Explicit non-scope | Migration | PASS | Production / manual gate |
|---|---|---|---|---|---|
| 14A | audit & architecture | any code, migration, dependency, infrastructure | no | owner approves D14-* | — (**COMPLETE / OWNER ACCEPTED**) |
| 14B | **media infrastructure readiness**: R2 private bucket + scoped API token (created with the owner), secrets via env, `MediaStorage` port + S3-compatible adapter + in-memory test fake, image pipeline (JPEG/PNG/WebP, 25 MB / 60 MP, derivatives, EXIF strip, sha256, bounded temp + cleanup), schema (`photo_assets`, `photo_attachments`, `photo_annotations`), config (TTL, quota), integrity-check design, runbook DB + media backup/restore section draft, uploads feature flag **off** | user uploads, UI, HEIC, Oracle backup configuration beyond design | **yes** (three photo tables) | pytest (pipeline, malicious files, adapter contract vs fake), scratch-PG upgrade/downgrade/upgrade, dev-bucket smoke | owner-approved bucket/token creation; deploy with flag off |
| 14B.H | HEIC/HEIF technical spike (OD-8 checklist) | enabling HEIC in production | no | measured ARM64/Docker/CPU (1 OCPU)/memory (6 GB)/orientation/derivatives/iOS Telegram results | device checks; HEIC only after owner approval |
| 14C | media API & security: upload state machine, list/attach/metadata/archive, presigned thumb/display URLs, quota policy; flag still off in production | UI | no | API + security tests (cross-user 404, spoofed MIME, decompression bombs, idempotent retry, 409 on byte mismatch, PENDING/FAILED never listed, soft-cap rejection) | — |
| 14D | **backup/restore drill & production media-readiness gate**: Oracle Object Storage independent backup target (with owner), export procedure, integrity check (missing / unreferenced objects), restore procedure, runbook finalized | features | no | drill executed once: DB + media restored, integrity report clean or explained | **gate before any production upload**; owner-approved Oracle setup |
| 14E | reusable mobile photo UI + Project/Room/Surface/Opening contexts; first controlled upload enablement | inspection/finding evidence, markers, WORK | no | vitest, tsc, build, 320/390/412 px PL/RU light/dark, touch targets | owner enables flag in production only after 14D PASS |
| 14F | finding `lineage_id` + inspection/finding evidence | markers | **yes** (lineage) | reconcile tests (resolve → re-confirm keeps lineage; Stage 7/11 signatures and matching unchanged) | — |
| 14G | POINT annotations (API + editor) | rectangle/freehand/arrow/text tools | no | tests + browser at 320–412 px | — |
| 14H | WORK execution photos in Realizacja | required photos | no | tests incl. BEFORE without execution row, APPEND/apply-to-all/REPLACE/detach/re-add | — |
| 14I | Stage 15 report read model / report-inclusion boundary | PDF | no | read-model tests (§14 fields, deterministic order, READY/non-archived, include_in_report) | — |
| 14J | adversarial / full verification | features | no | all backend/frontend/PG/object-store/browser gates | — |
| 14K | owner production walkthrough | — | — | owner PASS | **yes** |

---

## 20. Decision register (final — OWNER APPROVED 2026-09-28)

| ID | Decision (OWNER APPROVED) | Rejected / alternative | Deferred |
|---|---|---|---|
| D14-1 | Canonical media entity `photo_assets` (immutable file facts, status, explicit variant keys, no URL) | photo row per context | — |
| D14-2 | `photo_attachments`: leaf-only typed nullable FKs + context enum + one CHECK (§15.3) | polymorphic target (no referential integrity) | typed per-context tables if contexts grow |
| D14-3 | **Primary storage: Cloudflare R2 Standard**, private bucket, via provider-neutral `MediaStorage` S3-compatible adapter; VM/Docker disk only bounded temp (OD-1, OD-2) | VM disk / Docker volume as store | — |
| D14-4 | Explicit immutable `storage_key_original/display/thumbnail` + `storage_backend`; UUID-only keys, no mutable names | derived prefix; name-based paths | — |
| D14-5 | JPEG/PNG/WebP; 25 MB encoded; 60 MP decoded (limits provisional) (OD-8) | SVG/GIF/TIFF/RAW/PDF | **HEIC/HEIF pending 14B.H + owner approval** |
| D14-6 | Derivatives: original + display (2048) + thumbnail (480) | — | on-demand resizing |
| D14-7 | Original private & untouched; derivatives EXIF-stripped; `captured_at` kept; no GPS stored | — | — |
| D14-8 | Categories GENERAL, BEFORE, DEFECT, PREPARATION, IN_PROGRESS, HIDDEN_WORK, AFTER, DAMAGE — on the attachment (OD-7) | category on asset | — |
| D14-9 | InspectionFinding = canonical defect; annotation is not a defect entity; no severity/status/category/recommendation on annotations (OD-4) | Defect model; defect data on markers | markers → risk/recommendation |
| D14-10 | POINT marker: id, attachment_id, x, y, optional short label, position, timestamps; no finding_id | marker finding_id (contradiction risk) | rectangle / freehand / arrow / text tools |
| D14-11 | Normalized 0 ≤ x, y ≤ 1, origin top-left of the correctly oriented display image | pixels | — |
| D14-12 | WORK identity = surface + Stage 13 `occurrence_key` + price_item snapshot; `SurfacePlannedWork.id` never used | planned-work id / execution-row link | — |
| D14-13 | APPEND / apply-to-all never copy; REPLACE / removal never delete; detached evidence reportable; re-added PriceItem = new key, no inheritance; BEFORE needs no execution row | — | — |
| D14-14 | Archive attachment / asset; no physical delete in v1; RESTRICT on evidence parents | hard delete | physical cleanup |
| D14-15 | Annotations belong to the attachment | per image | — |
| D14-16 | Before/after = category + context grouping | pair entity | — |
| D14-17 | Upload lifecycle PENDING → READY / FAILED; only READY visible; DB and object storage never described as one transaction | single transaction | background worker |
| D14-18 | Client `upload_id` = request idempotency; same bytes resume/return, different bytes 409; checksum = integrity metadata, no global dedupe | checksum dedupe | — |
| D14-19 | Private bucket; thumb/display presigned GET after ownership check; original backend-only; streaming only as fallback (OD-12) | public URLs; presigned originals | streaming default |
| D14-20 | `include_in_report` on attachment, default **false** (OD-6) | on asset; default true | — |
| D14-21 | Backup: R2 primary + **Oracle Object Storage independent backup**; R2 versioning complementary only; integrity check; restore procedure + drill before uploads; no atomic-snapshot claim (OD-3) | DB-then-media "snapshot"; R2 versioning as the backup | automation tooling |
| D14-22 | Quota policy: warning 8 GB, soft cap 10 GB (configuration); at cap reject new uploads only | none; hard delete at cap | billing |
| D14-23 | One reusable mobile photo section; viewer + point-marker mode; no original download UI | per-context galleries | desktop UI |
| D14-24 | Execution completion never requires a photo; status-based category default | photo required | — |
| D14-25 | Stage 15 boundary = read-only query service (§14); no PDF in Stage 14 | PDF now | PDF (Stage 15) |
| D14-26 | `inspection_findings.lineage_id` (Option A); attachments keep concrete `finding_id`; Stage 7/11 semantics unchanged; no frontend heuristic (OD-5/OD-11) | supersedes self-FK; inspection+question; heuristic; reviving rows | — |
| D14-27 | Original preserved privately; no download-original UI in v1; authorized backend/report retrieval (OD-9) | UI download | later UI |
| D14-28 | Signed URL TTL `PHOTO_SIGNED_URL_TTL_SECONDS`, default 300 s, configuration only (OD-10) | hard-coded TTL | — |

## 21. Owner decisions (final)

| OD | Decision | Status |
|---|---|---|
| OD-1 | Cloudflare R2 Standard primary; private; S3-compatible provider-neutral adapter; nothing created in 14A | OWNER APPROVED |
| OD-2 | VM/Docker filesystem only bounded temp processing with deterministic cleanup | OWNER APPROVED |
| OD-3 | Oracle Object Storage independent backup; R2 versioning complementary only; backup/integrity/restore/drill before uploads; pg_dump alone insufficient | OWNER APPROVED (direction; configured in 14B/14D) |
| OD-4 | InspectionFinding canonical; annotation not a defect entity | OWNER APPROVED |
| OD-5 / OD-11 | Durable `lineage_id` on InspectionFinding (future migration, 14F) | OWNER APPROVED |
| OD-6 | `include_in_report` on attachment, default false | OWNER APPROVED |
| OD-7 | 8 attachment categories | OWNER APPROVED |
| OD-8 | JPEG/PNG/WebP; 25 MB / 60 MP provisional; HEIC deferred to 14B.H + owner approval | OWNER APPROVED (HEIC DEFERRED) |
| OD-9 | Original private; no download UI in v1 | OWNER APPROVED |
| OD-10 | Signed URL TTL 300 s default, configurable | OWNER APPROVED |
| OD-12 | Thumb/display presigned; original backend-only; streaming fallback | OWNER APPROVED |
| Quota | Warning 8 GB, soft cap 10 GB, configuration; reject new uploads only | OWNER APPROVED (initial operational defaults) |

No open owner decision blocks 14B; 14B itself requires explicit owner approval to start.

## 22. Risks

- **Provider lock-in / pricing drift** → S3 adapter, explicit `storage_backend` per asset, provider-independent keys.
- **Evidence loss** → Oracle independent backup, 14D gate, integrity check.
- **Inconsistent restore** (DB and objects from different times) → append-only objects + integrity report + recovery
  procedure; never auto-delete.
- **Abandoned PENDING/FAILED uploads** → detectable by query; manual cleanup in v1.
- **HEIC and WebView behaviour** differ between iOS/Android → 14B.H; JPEG/PNG/WebP only until then.
- **CPU/RAM** on 1 OCPU / 6 GB during decode → pixel limits, one upload per request, measured in 14B.
- **Cloudflare body-size/timeouts** → 25 MB limit; verify plan limits in 14B.
- **Presigned URL leakage** → 300 s configurable TTL, per-variant scope, no originals, no public caching.
- **Stage 6 change** (lineage) touches accepted code → isolated migration + reconcile tests proving Stage 7/11 unchanged.

## 23. Production state preserved by Stage 14A

- No Stage 14 production code exists yet; no Stage 14 migration exists yet; no dependency was added.
- No R2 bucket or API token has been created by this stage.
- No Oracle Object Storage backup has been configured by this stage.
- No Cloudflare/Oracle billing, tier or plan changes have been made by this stage.
- Production runtime remains the accepted Stage 13 runtime (`7b5aaf0`); production DB remains
  `0030_surface_work_executions`.

- **Status:** Stage 14A — COMPLETE / OWNER ACCEPTED. Stage 14 overall — IN PROGRESS. Stage 14B — NOT STARTED.
