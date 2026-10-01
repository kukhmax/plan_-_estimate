# Stage 14C — Media API & Security Contract (14C.1)

- **Date**: 2026-09-28
- **Branch / base**: `stage-14` @ `88ccbaa`
- **Status**: **Stage 14C.1 — COMPLETE / OWNER APPROVED** (contract only). Stage 14C — IN PROGRESS; **next: 14C.2**
  (PhotoAttachment schema/domain foundation), which starts only with explicit owner approval.
- **Nature**: audit / design. No runtime code, migration, dependency, configuration, Caddy or production change.
- **Parent contracts**: `docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md` (14A, OWNER ACCEPTED) and
  `docs/STAGE_14B_MEDIA_INFRASTRUCTURE_PLAN.md` (14B, COMPLETE). Where this contract refines them, the refinement is
  owner-approved and recorded here (§3, §27).
- **Production state (unchanged by 14C.1)**: runtime `e57e037`, DB `0031_photo_assets`, `MEDIA_STORAGE_BACKEND=s3`,
  `MEDIA_STORAGE_NAME=r2-primary`, `PHOTO_UPLOADS_ENABLED=false`, HEIC not implemented, formats JPEG / PNG / WebP.

---

## 1. Stage 14C boundary

**In scope (backend only):** multipart upload, image processing through the existing 14B pipeline, the PhotoAsset
upload lifecycle, the `photo_attachments` table and domain service, list / read metadata, attaching an existing asset
to another context, attachment metadata edits, archive / restore, short-lived presigned thumbnail / display URLs,
ownership and security, logical quota, retry / idempotency, the upload feature gate, the Caddy upload-route limit.

**Out of scope:** any UI, frontend API client or TypeScript types (14E); inspection / finding evidence (14F); point
annotations (14G); work-execution photos (14H); report read model / PDF (14I / Stage 15); HEIC/HEIF (deferred,
14B plan §27); enabling production uploads; hard delete; `MediaStorage` delete; a user-facing original download;
`/photos/counts` (deferred to 14E, C14).

**Explicit rules:**
- The `0032_photo_attachments` schema contains the INSPECTION / FINDING / WORK columns, enum values, CHECK branches and
  unique indexes **for forward compatibility** (14B R2).
- Their presence in the schema does **not** enable those contexts: the Stage 14C API supports only **PROJECT, ROOM,
  SURFACE, OPENING**. INSPECTION and FINDING remain **Stage 14F**; WORK remains **Stage 14H**.
- **HEIC remains deferred.** No user-facing original download endpoint. No hard delete. No `MediaStorage` delete.
- **`PHOTO_UPLOADS_ENABLED` remains `false` in production throughout Stage 14C.**
- **The Stage 14D independent backup / restore / integrity gate remains mandatory before production photo uploads.**

---

## 2. Fixed decisions inherited from Stage 14A / 14B (not reopened)

| Topic | Decision | Source |
|---|---|---|
| Asset identity | `photo_assets.id` = client `upload_id` UUIDv4 = storage-key `{asset_uuid}`; global primary key | 14B.4 §24, owner R-1 |
| Asset schema | `photo_assets` as migrated in `0031` (status, logical `storage_name`, three immutable keys, sizes, dimensions after orientation, `sha256`, `captured_at` TIMESTAMP WITHOUT TIME ZONE) | 14B §24.1 |
| States | PENDING / READY / FAILED; PENDING → READY, PENDING → FAILED, FAILED → PENDING; READY terminal; processing precedes the PENDING insert | 14A §8, 14B §24.1 |
| Keys | `photos/v1/{asset_uuid}/original.{jpg\|png\|webp}`, `display.jpg`, `thumb.jpg`; extension from the decoded format only | 14B R1 |
| Storage | Private Cloudflare R2 bucket via the provider-neutral `MediaStorage` port; write-once conditional PUT; no delete method | 14A D14-3/D14-14, 14B §8/§23.3 |
| Transport | multipart/form-data; `python-multipart` approved (pinned current version); controlled parsing | 14B R3 §6 |
| Image limits | JPEG / PNG / WebP; 25 000 000 bytes; 60 MP; 12 000 px edge; animated PNG/WebP rejected; MPO = JPEG first frame | 14A OD-8, 14B §23.5 |
| Processing | Concurrency 1; `PHOTO_PROCESSING_WAIT_SECONDS=30`; derivatives display 2048 / thumbnail 480, JPEG q85 / q80, sRGB, alpha on `#FFFFFF`, metadata stripped, never upscaled | 14B §23.13 |
| Temp | `PHOTO_TEMP_DIR`, `pe-photo-` workspaces (0700), `finally` cleanup, age-based sweep `PHOTO_TEMP_STALE_AFTER_SECONDS=86400` | 14B §5.1, §23.6 |
| Categories | GENERAL, BEFORE, DEFECT, PREPARATION, IN_PROGRESS, HIDDEN_WORK, AFTER, DAMAGE — on the attachment | 14A OD-7 |
| Report flag | `include_in_report` on the attachment, default `false` | 14A OD-6 |
| Attachment model | Leaf-only typed nullable FKs + context enum + one row-local CHECK; all seven contexts created in 14C | 14A D14-2, 14B R2 |
| Delivery | Thumbnail / display via presigned GET after ownership check; original backend-only; streaming only as fallback | 14A OD-12 |
| TTL | `PHOTO_SIGNED_URL_TTL_SECONDS`, default 300, configuration | 14A OD-10 |
| Quota | Per owner; warning `8_000_000_000`, soft cap `10_000_000_000` bytes; at the cap only new uploads are rejected | 14A §12, 14B R6 |
| Gates | `MEDIA_STORAGE_BACKEND=disabled\|s3`, `PHOTO_UPLOADS_ENABLED`; uploads-on requires `s3` (startup validation) | 14B R4 |
| EXIF / GPS | Original byte-identical (EXIF/GPS kept only inside it); GPS never extracted or stored; derivatives stripped | 14A D14-7 |
| Integrity | Read-only integrity engine/CLI and its classifications (§24.3 of 14B) are unchanged | 14B §24.3 |

---

## 3. Final C1–C16 decisions (OWNER APPROVED)

| # | Decision |
|---|---|
| C1 | The 14C API enables only PROJECT / ROOM / SURFACE / OPENING. INSPECTION / FINDING / WORK are rejected with 422 `PHOTO_CONTEXT_NOT_SUPPORTED` until 14F / 14H. |
| C2 | Per-context partial unique indexes (active rows only), with two INSPECTION indexes (question-less and question-level) — §6. `question_id` FK is **ON DELETE RESTRICT** (R-2, replaces the 14A §15.2 SET NULL). |
| C3 | `PHOTO_MAX_UPLOAD_BYTES = 25_000_000` (canonical image bytes, unchanged). New setting `PHOTO_MAX_REQUEST_BYTES = 27_000_000` (whole multipart request). Caddy upload-route limit = 27 000 000. |
| C4 | No client-provided `captured_at` in v1; only validated EXIF `DateTimeOriginal`. |
| C5 | Short-lived presigned **derivative** URLs returned in JSON after ownership checks (thumbnail in lists, thumbnail + display in detail). |
| C6 | 300 s default TTL; presigned with private cache semantics and inline delivery (§17). |
| C7 | Uploads unavailable → **503 `PHOTO_UPLOADS_DISABLED`**, no `Retry-After` (operational capability gate, not an ownership denial; no retry time implied). |
| C8 | Quota = **logical / reserved storage accounting** (declared original + display + thumbnail sizes of READY, PENDING and FAILED assets, archived included) — **not exact physical R2 usage**. No bucket HEAD scan. Resumes are never rejected by quota; therefore no pre-body quota rejection (§15). |
| C9 | Resume may HEAD individual expected keys: missing → conditional PUT; existing with wrong size → conflict; existing with expected size → resumable existing object. Size equality is **not** cryptographic identity. Retry original bytes are identity-verified by **SHA-256** against the stored `sha256`. A generic S3 ETag is **not** treated as SHA-256 or content identity. No derivative SHA columns (§13). |
| C10 | Compare-and-set state transitions; non-committing `create_pending` path so the asset and its first attachment commit in one transaction. |
| C11 | With `PHOTO_UPLOADS_ENABLED=false`: read / list / link and attachment metadata / archive / restore operations may work; **no operation may create a PhotoAsset or write a media object** (§19). |
| C12 | No new archived-parent prohibition in 14C; current project semantics apply. |
| C13 | Owner-scoped `GET /api/photo-storage` (replaces the project-scoped 14A §16 path). |
| C14 | `/photos/counts` **deferred** to 14E; not part of 14C. |
| C15 | The proposed fixed 256 MB free-space threshold is **rejected**. Existing controls stay; temp usage is measured in 14C.6; any future disk-space threshold requires measured evidence (§20.3). |
| C16 | A replay of an already READY upload ignores new request metadata; changes use PATCH / attachment APIs. |
| R-1 | Keep `PhotoAsset.id = upload_id`; uniform `409 PHOTO_UPLOAD_ID_CONFLICT` semantics (§14). |
| R-2 | `question_id → checklist_questions ON DELETE RESTRICT`; corrected INSPECTION uniqueness (§6). |

---

## 4. `photo_attachments` schema

| Column | Type | Nullability / default | FK / rule |
|---|---|---|---|
| `id` | UUID | PK | server-generated `uuid4` |
| `asset_id` | UUID | NOT NULL | → `photo_assets.id` ON DELETE **RESTRICT** |
| `project_id` | UUID | NOT NULL | → `projects.id` ON DELETE **RESTRICT**; service-validated = asset's `project_id` |
| `context` | enum `photoattachmentcontext` (`PROJECT`, `ROOM`, `SURFACE`, `OPENING`, `INSPECTION`, `FINDING`, `WORK`) | NOT NULL | |
| `room_id` | UUID | NULL | → `rooms.id` RESTRICT |
| `surface_id` | UUID | NULL | → `surfaces.id` RESTRICT |
| `opening_id` | UUID | NULL | → `openings.id` RESTRICT |
| `inspection_id` | UUID | NULL | → `inspections.id` RESTRICT (14F) |
| `question_id` | UUID | NULL | → `checklist_questions.id` **RESTRICT** (14F; R-2) |
| `finding_id` | UUID | NULL | → `inspection_findings.id` RESTRICT (14F) |
| `occurrence_key` | UUID | NULL | **no FK** — Stage 13 durable key, never `SurfacePlannedWork.id` (14H) |
| `price_item_id` | UUID | NULL | → `price_items.id` RESTRICT (14H label snapshot) |
| `category` | enum `photocategory` (the 8 approved values) | NOT NULL | API default `GENERAL` |
| `caption` | VARCHAR(1000) | NULL | trimmed; empty → NULL |
| `include_in_report` | BOOLEAN | NOT NULL DEFAULT false | |
| `position` | INTEGER | NOT NULL DEFAULT 0 | CHECK ≥ 0 |
| `archived_at` | TIMESTAMPTZ | NULL | soft archive |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL | server UTC |

No `owner_id` column: ownership is `project → owner`, with `asset.owner_id` as a second, independent check. No URL,
credential or storage key is stored on the attachment. `photo_assets` is **not** changed.

---

## 5. CHECK constraints

`ck_photo_attachments_context_targets` — exactly the 14A §15.3 seven-branch, row-local, portable (SQLite + PostgreSQL)
expression; no `num_nonnulls`:

```sql
CHECK (
  (context = 'PROJECT'    AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL
                          AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)
  OR (context = 'ROOM'    AND room_id IS NOT NULL AND surface_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL
                          AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)
  OR (context = 'SURFACE' AND surface_id IS NOT NULL AND room_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL
                          AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)
  OR (context = 'OPENING' AND opening_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL AND inspection_id IS NULL
                          AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)
  OR (context = 'INSPECTION' AND inspection_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL
                          AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)   -- question_id optional
  OR (context = 'FINDING' AND finding_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL
                          AND inspection_id IS NULL AND question_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)
  OR (context = 'WORK'    AND surface_id IS NOT NULL AND occurrence_key IS NOT NULL AND price_item_id IS NOT NULL
                          AND room_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL
                          AND finding_id IS NULL)
)
```

`ck_photo_attachments_position_nonneg` — `position >= 0`.

Cross-row consistency (target belongs to the attachment's project; asset and attachment share the project) is
service-validated, as everywhere else in the codebase (14A §15.3).

---

## 6. Partial unique indexes (active attachments only)

Every index includes `archived_at IS NULL`, so an archived duplicate never blocks a new active attachment. Partial
indexes are supported by both SQLite and PostgreSQL. Every indexed column is non-NULL within its branch (guaranteed by
the CHECK or by the index predicate), so PostgreSQL's "NULLs are distinct" rule leaves no duplicate hole.

| Index | Columns | Predicate (plus `archived_at IS NULL`) |
|---|---|---|
| `uq_photo_att_project_active` | `(asset_id)` | `context = 'PROJECT'` |
| `uq_photo_att_room_active` | `(asset_id, room_id)` | `context = 'ROOM'` |
| `uq_photo_att_surface_active` | `(asset_id, surface_id)` | `context = 'SURFACE'` |
| `uq_photo_att_opening_active` | `(asset_id, opening_id)` | `context = 'OPENING'` |
| `uq_photo_att_inspection_active` | `(asset_id, inspection_id)` | `context = 'INSPECTION' AND question_id IS NULL` |
| `uq_photo_att_inspection_question_active` | `(asset_id, inspection_id, question_id)` | `context = 'INSPECTION' AND question_id IS NOT NULL` |
| `uq_photo_att_finding_active` | `(asset_id, finding_id)` | `context = 'FINDING'` |
| `uq_photo_att_work_active` | `(asset_id, surface_id, occurrence_key)` | `context = 'WORK'` |

The same asset may simultaneously have one inspection-level and separate question-level attachments (different
evidence semantics). The 14A §15.3 single index over nullable target columns is superseded (it would allow duplicate
PROJECT attachments because all targets are NULL).

**Lookup indexes:** `ix_photo_attachments_project_context_archived (project_id, context, archived_at)`,
`ix_photo_attachments_asset_id`, `ix_photo_attachments_room_id`, `ix_photo_attachments_surface_id`,
`ix_photo_attachments_opening_id`, `ix_photo_attachments_inspection_id`, `ix_photo_attachments_finding_id`,
`ix_photo_attachments_surface_occurrence (surface_id, occurrence_key)`.

---

## 7. Foreign-key behaviour

All evidence parents are **RESTRICT**: every parent is archive-only through the API, so RESTRICT never fires in normal
use, and any future hard-delete path is forced to handle photos explicitly instead of silently dropping or re-meaning
evidence (14A §15.2).

**`question_id` — ON DELETE RESTRICT (R-2, replaces 14A SET NULL).** Photo attachments are evidence; deleting a
question must not silently turn question-level evidence into inspection-level evidence (SET NULL would still satisfy the
CHECK). Audited lifecycle: `checklist_questions` is an insert-only, versioned catalog materialized once per
`(code, version)` by `ChecklistService._ensure_bootstrapped`; the checklist API is read-only (GET); no service, script or
migration after `0011` deletes or updates question rows. RESTRICT therefore costs nothing in normal operation. SET NULL
would additionally collide with the question-less INSPECTION unique index when two question-level attachments of the same
asset/inspection were nulled. `occurrence_key` has no FK by design (Stage 13 D13).

---

## 8. Migration plan

- **Revision**: `0032_photo_attachments`, **down_revision `0031_photo_assets`** (single head).
- **Upgrade**: create enums `photoattachmentcontext` (7 values) and `photocategory` (8 values); create
  `photo_attachments` with the §4 columns, §5 CHECKs, §7 FKs, §6 unique and lookup indexes.
- **No change** to `photo_assets`; no data backfill. HEIC is **not** part of this migration.
- **PostgreSQL enums**: all seven contexts are created now, so 14F / 14H need no `ALTER TYPE … ADD VALUE`.
- **Downgrade**: drop indexes, table, both enum types. Acceptable only before real use (14A §18); production has zero
  rows.
- **Verification**: SQLite `upgrade`/`downgrade`/`upgrade` compared with model metadata; offline `--sql` rendering;
  owner-run **scratch PostgreSQL 16** verification (isolated procedure of 14B §24.9): 0001 → 0032 on an empty DB,
  downgrade → 0031, re-upgrade; probes: every CHECK branch valid/invalid, each per-context duplicate rejected while
  active and allowed when archived (both INSPECTION variants), RESTRICT on asset / project / room / surface / opening /
  inspection / finding / price item / **question** deletion.

---

## 9. Multipart upload contract

**Endpoint**: `POST /api/projects/{project_id}/photos`, `Content-Type: multipart/form-data`, `Authorization: Bearer`.

| Field | Required | Rule |
|---|---|---|
| `upload_id` | yes | UUIDv4 string (canonical lowercase) = asset id |
| `context` | yes | `PROJECT` \| `ROOM` \| `SURFACE` \| `OPENING` (others → 422 `PHOTO_CONTEXT_NOT_SUPPORTED`) |
| `room_id` / `surface_id` / `opening_id` | exactly the one required by `context`; the others absent | leaf-only target; the server validates the chain to the project |
| `category` | no | one of the 8 values; default `GENERAL` |
| `caption` | no | ≤ 1000 characters; trimmed; empty → NULL |
| `include_in_report` | no | boolean; default `false` |
| `file` | yes | exactly one file part |

- **Controlled parsing**: the route takes `Request` and declares no `File()`/`Form()` parameters, so authentication,
  the upload gate, `Content-Length` and project ownership run **before any body byte is read**. It then calls
  `request.form(max_files=1, max_fields=6, max_part_size=8 KiB)`. Unknown, duplicated or missing fields and malformed
  multipart → 422 `PHOTO_UPLOAD_MALFORMED`.
- **Filename**: the multipart filename passes `sanitize_original_filename` (last path segment, no control characters,
  ≤ 255) and is stored as `original_filename` metadata only; never used in keys or paths; never logged.
- **`captured_at`**: from validated EXIF `DateTimeOriginal` only (C4); camera-local, no timezone; never client-supplied.
- **Response**: `201` (new asset READY) or `200` (replay of a READY asset):
  `{asset, attachment, thumbnail_url, display_url, urls_expire_at, storage: {state}}`. On replay, `attachment` is the
  asset's first attachment (earliest `created_at`, `id`), whatever its archive state; request metadata is ignored (C16).
- **Client retry protocol**: after a timeout, the client first calls `GET /api/projects/{p}/photos/{upload_id}`
  (200 → done; 404 → re-POST with the same `upload_id` and the same file).

---

## 10. Request and image byte limits

| Limit | Value | Enforced by |
|---|---|---|
| `PHOTO_MAX_UPLOAD_BYTES` | **25 000 000** (canonical image bytes, OWNER APPROVED 14B) | byte count while copying the file part into the workspace; the pipeline again (`hash_file_bounded`) |
| `PHOTO_MAX_REQUEST_BYTES` | **27 000 000** (whole multipart request; new setting, C3) | `Content-Length` early rejection when present; byte-counting ASGI `receive` guard for every body (chunked included) — `Content-Length` is never relied on alone |
| Caddy `request_body max_size` | **27 000 000**, upload route only (`POST` matching `^/api/projects/[^/]+/photos$`) | reverse proxy |
| Cloudflare plan body limit | outer bound only | edge (verified on devices in 14E) |

Configuration (14C.4): `PHOTO_MAX_REQUEST_BYTES` added to `Settings` with validation `PHOTO_MAX_REQUEST_BYTES >
PHOTO_MAX_UPLOAD_BYTES`, to `docker-compose.prod.yml` (`${PHOTO_MAX_REQUEST_BYTES:-27000000}`) and
`.env.production.example`. The request allowance never raises the 25 000 000-byte image limit. Exceeding either limit →
413 `PHOTO_TOO_LARGE` (a Caddy 413 is treated identically by the client).

---

## 11. Upload state machine and algorithm

The database and R2 are **not** atomic; no distributed-transaction guarantee is claimed. An object is only ever
written after its PENDING row is committed.

**Stage A — before reading the body**
1. Authenticate → 401.
2. Upload gate (§19): `PHOTO_UPLOADS_ENABLED=false` or storage not `s3` → **503 `PHOTO_UPLOADS_DISABLED`**.
3. `Content-Length` > 27 000 000 → 413.
4. Project owned by the caller → else 404 `PROJECT_NOT_FOUND`.
5. No quota rejection here: the `upload_id` is not yet known, so a pre-body check could not exempt resumes (C8).
   Quota is enforced for new uploads only, in step 9 (§15).
6. Opportunistic stale-temp sweep (`cleanup_stale_photo_temp`).

**Stage B — receive and identify**
7. Parse under the 27 000 000-byte guard (413); validate fields (422) and the target chain (404); copy the file part
   into a `pe-photo-` workspace (> 25 000 000 → 413); compute SHA-256 of those exact bytes.
8. Look up `photo_assets` by `id = upload_id` and branch:
   - no row → **new upload** (Stage C);
   - row of another owner → **409 `PHOTO_UPLOAD_ID_CONFLICT`** (§14; no SHA comparison);
   - own row, different project, or different SHA-256 → **409 `PHOTO_UPLOAD_ID_CONFLICT`**;
   - own row, same project and SHA-256, READY → **200 replay** (C16), whether or not the asset is archived;
   - own row, same project and SHA-256, PENDING or FAILED → **resume** (Stage D).

**Stage C — new upload**
9. Acquire the processing slot (> 30 s → 503 `PHOTO_PROCESSING_BUSY` with `Retry-After`, §11b); run the full pipeline
   (rejections 413 / 415 / 422 create **no row**); still inside the slot, logical quota check (usage + the three new
   sizes > soft cap → 409 `PHOTO_STORAGE_QUOTA_EXCEEDED`, no row).
10. In **one transaction** insert `photo_assets(status=PENDING, …)` and the first `photo_attachments` row, then commit
    (non-committing `create_pending`, C10). A primary-key collision (concurrent request) → re-read and return to step 8.
11. Conditional PUT: original, then display, then thumbnail. Continue with Stage E.

**Stage D — resume (retry bytes already SHA-256-verified in step 8)**
12. FAILED → PENDING by compare-and-set; a lost race → re-read and return to step 8.
13. HEAD each expected key (C9): missing → needs conditional PUT; present with a size different from the recorded
    size → `MediaObjectConflict` → compare-and-set to FAILED → 409 `PHOTO_OBJECT_CONFLICT` (logged as integrity error);
    present with the expected size → resumable existing object.
14. Original missing → PUT the retry bytes (permitted only because their SHA-256 equals the stored `sha256`).
15. A derivative missing → acquire the slot and **re-validate / reprocess the newly supplied retry bytes** through the
    full pipeline (the retry bytes were SHA-verified in step 8). The regenerated format, dimensions and derivative byte
    size must equal the recorded values; otherwise compare-and-set to FAILED → 409 `PHOTO_UPLOAD_RESUME_MISMATCH`
    (logged; the asset stays FAILED for operator action). **A derivative is never regenerated from unverified bytes.**
16. PUT the missing objects (conditional). Continue with Stage E.

**Stage E — finalize**
17. Compare-and-set PENDING → READY, commit → 201 (or 200 when a concurrent request already finalized).
    Storage errors: `MediaStorageUnavailable` → compare-and-set to FAILED → 503 `PHOTO_STORAGE_UNAVAILABLE` (no
    `Retry-After`, §11b); `MediaStorageMisconfigured` → FAILED → 500 `PHOTO_STORAGE_ERROR` (generic message, details only in
    logs); `MediaObjectConflict` → FAILED → 409 `PHOTO_OBJECT_CONFLICT`. Workspaces are removed in `finally` always.

**Compare-and-set transitions (C10)**: `UPDATE photo_assets SET status=:to, updated_at=now() WHERE id=:id AND
status=:from`, row count checked. READY never regresses; a request that loses a race re-reads and returns the current
outcome.

### Failure matrix

| Failure point | DB state | Possible objects | Retry with same `upload_id` | Integrity checker |
|---|---|---|---|---|
| Before PENDING insert: request / validation / processing / quota / busy | no row | none | fresh upload | — |
| Step 10 commit fails | no row (rolled back) | none | fresh upload | — |
| Original PUT fails | FAILED | none or original | resume | `FAILED_RELATED` |
| Display / thumbnail PUT fails | FAILED | original, maybe display | resume | `FAILED_RELATED` |
| FAILED commit fails, or process crash | PENDING | any subset | resume from PENDING | `PENDING_INCOMPLETE` (WARNING after 86 400 s) |
| READY commit fails | PENDING | all three | resume: all present with expected sizes → READY | `PENDING_INCOMPLETE` until then |
| Wrong-size existing object / resume mismatch | FAILED | untouched | 409 until operator action | `FAILED_RELATED` |

Because objects follow the PENDING commit, an upload failure never produces `ORPHAN_CANDIDATE`; such keys indicate a
manual/external write.

### 11a. Refinements (OWNER APPROVED, 14C.3 review, 2026-10-01)

1. **Lost step-17 CAS**: a request whose PENDING → READY compare-and-set loses re-reads the row. READY → it returns
   the concurrently finalized asset (200). Any other state (FAILED written by a parallel request) → it returns to
   step 8 and follows the normal FAILED resume path.
2. **Resume regeneration rejected by the pipeline**: if the SHA-verified retry bytes no longer pass the current
   processing pipeline (e.g. limits changed between attempts), the recorded derivatives cannot be regenerated →
   compare-and-set to FAILED → 409 `PHOTO_UPLOAD_RESUME_MISMATCH` (as in step 15).
3. **Resume and metadata**: a resume never creates or changes an attachment. Request metadata is ignored and the
   response carries the asset's existing first attachment (as for a READY replay, C16).
4. **Storage reads during resume**: a storage error while HEADing the expected keys (step 13) is a storage-phase
   failure handled like Stage E: compare-and-set to FAILED and re-raise the provider-neutral error
   (`MediaStorageUnavailable` → 503, `MediaStorageMisconfigured` → 500). If that compare-and-set loses to READY, the
   READY outcome stands (200).

**Convergence (no retry count).** Step 8 is re-entered only after observing, in a fresh transaction, a transition
committed by another request: a primary-key collision on the step-10 insert (the row now exists; rows are never deleted,
so the new-upload branch is not re-entered), a lost FAILED → PENDING claim, or a lost PENDING → READY to a parallel
PENDING → FAILED. The loser of a FAILED → PENDING claim never recovers from the stale FAILED: it re-reads and resumes
from PENDING without claiming, replays READY, or claims again only after a new FAILED. A request that records FAILED
ends with its error, so each concurrent request can make the row FAILED at most once; re-identification is bounded by
the number of concurrent requests for the same `upload_id`, and no artificial retry limit exists. Concurrent resumes of
the same asset may both HEAD, regenerate and conditionally PUT: identical bytes are a write-once no-op, different bytes
raise `MediaObjectConflict` and are never written over; nothing is deleted; compare-and-set keeps READY terminal.


### 11b. HTTP boundary refinements (OWNER APPROVED, 14C.4 review, 2026-10-01)

1. **Error envelope**: the project convention `{"detail": {"code": "…", "message": "…"}}` (FastAPI `HTTPException`)
   is used for every upload error; it replaces the bare `{"code", "message"}` shown in earlier drafts. Messages are
   fixed per code and never carry storage keys, sha256, paths, provider codes or tracebacks.
2. **`Retry-After`**: `PHOTO_PROCESSING_BUSY` (503) carries `Retry-After` = ⌈`PHOTO_PROCESSING_WAIT_SECONDS`⌉
   (30 s by default; no separate retry constant). `PHOTO_STORAGE_UNAVAILABLE` (503) carries **no** `Retry-After`
   (no reliable recovery interval). `PHOTO_UPLOADS_DISABLED` carries none (C7).
3. **Upload admission (new pre-body step, after project ownership)**: a process-wide limit of
   `MAX_CONCURRENT_UPLOAD_REQUESTS = 2` in-flight upload requests (reception + processing; code constant),
   independent of the processing slot. Acquisition is non-blocking: when full → 503 `PHOTO_PROCESSING_BUSY` with
   `Retry-After` **before any body byte is read**; no queue, no timeout; released on every exit. This bounds temp disk
   use (≈ 2 × (27 MB spool + 25 MB workspace copy) + derivatives). **The admission limiter never waits**: the
   `Retry-After` value (⌈`PHOTO_PROCESSING_WAIT_SECONDS`⌉) is only a retry hint to the client. The only component that
   waits up to `PHOTO_PROCESSING_WAIT_SECONDS` is the separate Stage 14B image-processing slot (§11 step 9), which an
   admitted request may then still find busy (same 503 code and hint).
4. **Request-byte guard**: `Content-Length` is advisory (declared > `PHOTO_MAX_REQUEST_BYTES` → 413 before the body;
   malformed → 422 `PHOTO_UPLOAD_MALFORMED`). The limit itself is enforced on the **actual** `http.request` body
   bytes by a route-scoped ASGI `receive` wrapper; a missing, false or chunked length cannot bypass it. The file part
   is copied into the workspace in ≤ 1 MiB chunks reading at most `PHOTO_MAX_UPLOAD_BYTES + 1` bytes (> limit → 413).
   Starlette's `max_part_size` bounds scalar parts only; non-multipart / unparsable bodies (python-multipart
   `FormParserError`, not converted by Starlette) → 422 `PHOTO_UPLOAD_MALFORMED`. The multipart spool is closed before
   the domain call.
5. **Caddy boundary**: the route-scoped `request_body { max_size 27000000 }` was syntax/provision-validated with the
   official Caddy 2.11.4 and 2.11.6 binaries; the production `caddy:2-alpine` image/version and its runtime behaviour
   remain **unverified** and are a mandatory 14C.7 check. The application request guard (item 4) is authoritative
   regardless of Caddy.
6. **Presign failure after READY**: the upload has already succeeded; a presign failure changes nothing in the
   database or storage (no compare-and-set, no deletion, no retry of the orchestration) and maps to 503
   `PHOTO_STORAGE_UNAVAILABLE` (no `Retry-After`) or 500 `PHOTO_STORAGE_ERROR`. The client's retry with the same
   `upload_id` is a READY replay (200) with fresh URLs.
7. **Upload response URLs**: the upload response (§9) carries presigned `thumbnail_url` / `display_url` and
   `urls_expire_at`, produced with `MediaStorage.presign_get` and `PHOTO_SIGNED_URL_TTL_SECONDS` only after the domain
   result is READY. Standalone read / list / link / archive routes remain 14C.5.

### 11c. Read / archive / storage-status refinements (OWNER APPROVED, 14C.5, 2026-10-01)

1. **Presign response overrides (D-1, §17) implemented**: the S3 adapter signs every derivative URL with
   `ResponseCacheControl: private, max-age=<PHOTO_SIGNED_URL_TTL_SECONDS>` and `ResponseContentDisposition: inline`
   (local signing, no network). This also applies to the 14C.4 upload response URLs. Only derivative keys (thumbnail,
   display) are ever signed.
2. **List** (`GET /projects/{p}/photos`): context filters are validated with the same shape / ownership chain as
   attach and upload — a target id without a context, or a context without its target id → 422
   `PHOTO_ATTACHMENT_INVALID`; INSPECTION / FINDING / WORK → 422 `PHOTO_CONTEXT_NOT_SUPPORTED`; a foreign or missing
   target → 404 `ROOM_NOT_FOUND` / `SURFACE_NOT_FOUND` / `OPENING_NOT_FOUND`. Query type errors (unknown enum, `limit`
   outside 1–100) are the standard FastAPI 422. Every query also requires `attachment.project_id = asset.project_id =
   project`, `asset.owner_id = owner` and READY, independently of the foreign keys.
3. **Cursor**: the cursor is opaque and strictly validated. It is bound to the owner, project and list filters. It
   is not an authorization token. Authorization and filtering are independently enforced by the database query. A
   syntactically valid client-crafted continuation tuple cannot weaken those predicates.
   - Encoding (not part of the API contract): base64url JSON `{v, p, u, i, f}` — version 1, the last row's
     `(position, uploaded_at, attachment id)` and `f` = a plain (unkeyed) truncated SHA-256 of (owner, project,
     every filter, `archived`). It is **not** cryptographically authenticated (no MAC; owner decision for v1).
   - 422 `PHOTO_CURSOR_INVALID` for: a **malformed** cursor (not base64url / JSON), a **schema-invalid** cursor
     (wrong keys, version or types, negative position, unparsable timestamp / id) and a **filter-mismatched** cursor
     (fingerprint of another owner / project / filter set / view).
   - A **valid but client-crafted continuation tuple** is accepted: it only selects where to continue inside the
     already-authorized, already-filtered result set (it is AND-ed after every owner / project / READY / view /
     context / target / category / report predicate), so it can skip or repeat the owner's own visible rows but never
     reveal anything else. Proven by tests.
4. **Detail** (`GET /projects/{p}/photos/{asset_id}`): READY asset of this owner and project (archived included);
   `attachments` = all of its attachments in this project, archived included, in creation order `(created_at, id)`.
5. **Asset archive / restore** set / clear `photo_assets.archived_at` only (no attachment cascade, no status or storage
   change); both idempotent; PENDING / FAILED → 404 `PHOTO_NOT_FOUND`. Attachment archive state is untouched by either.
6. **Attach existing** (`POST /projects/{p}/photos/{asset_id}/attachments`) is a DB-only operation (no media write)
   and works with uploads disabled; the request has no `position` (new attachments start at 0).
7. **`GET /api/photo-storage`** is a **logical application quota / status** endpoint, not provider usage:
   `used_bytes` = the §15 accounting (recorded original + display + thumbnail sizes of READY, PENDING and FAILED assets,
   archived included); no bucket listing, HEAD or network call. `uploads_enabled` = the effective upload gate
   (`PHOTO_UPLOADS_ENABLED` and `MEDIA_STORAGE_BACKEND=s3`); `media_available` = `MEDIA_STORAGE_BACKEND=s3` (configured
   for delivery; no live health check); `state` = OK / WARNING / FULL with the configured thresholds.
8. **Storage on reads**: `MEDIA_STORAGE_BACKEND=disabled` → metadata with `null` URLs and `urls_expire_at`; a presign
   failure → 503 `PHOTO_STORAGE_UNAVAILABLE` (no `Retry-After`) or 500 `PHOTO_STORAGE_ERROR`; reads never write.
---

## 12. Retry and idempotency semantics

| Case | Result |
|---|---|
| Same id + same bytes, READY | 200 replay; new metadata ignored (C16) |
| Same id + same bytes, READY but archived | 200 replay (archive does not affect upload identification) |
| Same id + same bytes, PENDING | resume (no transition needed) |
| Same id + same bytes, FAILED | FAILED → PENDING (CAS), resume |
| Same id + different bytes | 409 `PHOTO_UPLOAD_ID_CONFLICT` |
| Same id + different project | 409 `PHOTO_UPLOAD_ID_CONFLICT` |
| Id belongs to another owner | 409 `PHOTO_UPLOAD_ID_CONFLICT` (identical, §14) |
| Client timeout | `GET …/photos/{id}` first; 404 → re-POST (resume or fresh) |
| Concurrent identical requests | both may process; the second insert hits the PK → re-read → resume; identical conditional PUTs are safe (write-once, 412 = matching object); CAS keeps READY final; the loser returns 200 |
| Same bytes, new `upload_id` | a new independent asset (no global deduplication, 14A D14-18) |
| Uploads disabled | 503 `PHOTO_UPLOADS_DISABLED` for new, replay and resume alike (§19) |
| At the soft cap | new uploads 409 (step 9); replay and resume are never quota-rejected (§15) |


**Archive visibility is independent of upload idempotency.** Replay/resume identification (step 8) uses only owner,
project, SHA-256 and status; `archived_at` of the asset or its attachments is not consulted. An owned, archived READY
asset with matching project and SHA-256 is a valid 200 replay (its response carries `archived_at`). Archive visibility
affects the normal read/list surfaces (§18, §21) only.

---

## 13. Resume verification levels (C9)

| Object | Verification | What it proves |
|---|---|---|
| Retry **original bytes** (from the client) | **SHA-256** of the exact bytes = stored `photo_assets.sha256` | content identity of the retry bytes with the originally processed upload |
| Existing **original** object in storage | HEAD size = `byte_size` | size-level consistency only — **not** content identity |
| Existing **derivative** objects | HEAD size = `display_byte_size` / `thumbnail_byte_size` | size-level resume validation only |
| Regenerated derivative | produced only from SHA-verified retry bytes; format, dimensions and byte size must equal the row | deterministic-regeneration check, not a hash |
| Generic S3 **ETag** | **not** treated as SHA-256 or as content identity (the adapter's existing 412 handling is unchanged) | — |

Full content verification of stored originals remains the integrity tool's opt-in `--verify-sha256` (downloads and
hashes). No derivative SHA columns are added.

---

## 14. Uniform `PHOTO_UPLOAD_ID_CONFLICT` semantics (R-1)

Under the approved global-primary-key identity (`PhotoAsset.id = upload_id`), an unused id succeeds and a used one
cannot; one bit — **"this UUID is unavailable"** — is therefore unavoidable. Nothing beyond that bit is disclosed.

- **One response** for a foreign `upload_id`, an own `upload_id` with different bytes, and an own `upload_id` belonging
  to a different project: `409` with body
  `{"detail": {"code": "PHOTO_UPLOAD_ID_CONFLICT", "message": "upload_id cannot be used for this upload; generate a new one"}}` —
  no owner, project, status, size, timestamp or content information, no hint which condition matched.
- **Same code path**: the body is fully received and hashed in every case and the decision is taken at the same step
  (step 8), before the processing slot.
- **Never compare the retry SHA-256 against a foreign asset** (that would confirm "these exact bytes are stored under
  this id"). The SHA comparison happens only after the owner matches.
- **Foreign assets never reach processing, storage or state transitions.**
- **Read side**: foreign, missing, PENDING and FAILED assets are indistinguishable — the same 404 `PHOTO_NOT_FOUND`.
- The client's correct reaction is identical in all cases: generate a new `upload_id` and upload again.

---

## 15. Quota — logical / reserved storage accounting (C8)

- **Definition**: per owner, `SUM(byte_size + display_byte_size + thumbnail_byte_size)` over the owner's
  `photo_assets` in **READY, PENDING and FAILED**, **archived included** (uses `ix_photo_assets_owner_status`).
- This is **logical / reserved storage accounting, not exact physical R2 usage**: a FAILED or PENDING asset may hold
  none or only some of its objects; archive deletes nothing. The bucket is **never** HEAD-scanned to compute usage; no
  cached total, no quota table.
- **Check**: only for **new** uploads, inside the processing slot immediately before the PENDING insert (usage + new
  sizes > soft cap → 409 `PHOTO_STORAGE_QUOTA_EXCEEDED`, no row). There is deliberately **no pre-body quota
  rejection**: before the body is parsed the `upload_id` is unknown, so such a check would also reject resumes. Cost:
  at `FULL`, a new upload's body is received before rejection (bandwidth only; the client can read `state=FULL` from
  `GET /api/photo-storage` first). With one uvicorn process the check is exact; with several processes the overshoot is
  bounded by one in-flight upload per process (soft cap).
- **Replays and resumes** of an existing own asset are **never** quota-rejected (the asset is already counted).
- **States**: `OK` < `PHOTO_STORAGE_WARNING_BYTES` (8 000 000 000) ≤ `WARNING` < `PHOTO_STORAGE_SOFT_CAP_BYTES`
  (10 000 000 000) ≤ `FULL`. At `FULL` only new uploads are rejected; reads, links, metadata and archive keep working.

---

## 16. Authorization and ownership

- Every route requires Bearer authentication (`get_current_user`) and, when project-scoped, starts with
  `ProjectService.get_project(project_id, owner_id)` → 404 `PROJECT_NOT_FOUND` for foreign or missing projects.
- **Asset**: `id = :asset_id AND owner_id = :me AND project_id = :project_id`; read / attach / archive require READY →
  otherwise 404 `PHOTO_NOT_FOUND` (foreign, missing, other project, PENDING, FAILED identical).
- **Attachment**: `attachment.project_id = :project_id` and its asset's `owner_id = :me` → otherwise 404
  `PHOTO_ATTACHMENT_NOT_FOUND`.
- **Targets (nested ownership)**: room → project; surface → room → project; opening → surface → room → project.
  A mismatch or foreign target → 404 `ROOM_NOT_FOUND` / `SURFACE_NOT_FOUND` / `OPENING_NOT_FOUND` (identical for
  foreign and missing).
- **Attachment project** = asset project; cross-project attachment is impossible (404).
- Presigned URLs are issued only after these checks. **403 is never used for ownership** (consistent with the app);
  the upload gate is 503 (C7).

---

## 17. Media delivery and presigned URLs

- **Option A**: presigned derivative URLs in JSON. Reasons: the frontend authenticates with a Bearer token from
  `localStorage`, which an `<img src>` cannot send, so redirect or backend streaming would require the 7-day JWT in a URL
  or fetch→blob loading; streaming would also push image bytes through the 1-OCPU backend.
- **Scope**: one object key (one variant) per URL; TTL `PHOTO_SIGNED_URL_TTL_SECONDS` (default 300); presigning is
  local (no network). Presign overrides: `ResponseCacheControl: private, max-age=<TTL>`, `ResponseContentDisposition:
  inline`. No `Cache-Control` is set on PUT.
- **Placement**: lists return `thumbnail_url`; asset detail returns `thumbnail_url` + `display_url`; every response
  carries `urls_expire_at`.
- **Original**: **no user-facing endpoint and no presigned original URL** in 14C; backend/report-side authorized
  retrieval only (Stage 15).
- Private bucket, no public URLs (verified in 14B.6). Delivered bytes are always derivative JPEGs.
- URLs contain the Access Key **ID** (approved non-secret classification, 14B §23.3); they are never logged.
- `MEDIA_STORAGE_BACKEND=disabled` → URL fields `null`, metadata still returned.
- Backend streaming remains the OD-12 fallback only if 14E device tests show presigned delivery is incompatible.

---

## 18. Archive / restore

- **Attachment archive** sets `archived_at`; asset and objects untouched. **Restore** clears it; 409
  `PHOTO_ATTACHMENT_DUPLICATE` if an equivalent active attachment now exists (§6). Both idempotent.
- **Asset archive** (READY only) sets `photo_assets.archived_at`; the asset disappears from every default list;
  attachment rows are untouched, so **restore** returns everything exactly as before. Idempotent.
- An asset whose attachments are all archived stays READY and retained; it is reachable through `archived=true` lists.
- **List filter semantics**: `archived=false` (default) = active attachment **AND** non-archived asset;
  `archived=true` = **archive view**: archived attachment **OR** archived asset. `archived=true` is an archive-view
  filter, **not** a direct equality test against `photo_attachments.archived_at` (an active attachment of an archived
  asset appears in the archive view).
- Archive visibility does not affect upload idempotency: an archived READY asset remains a valid upload replay (§12).
  No unattached-asset gallery in 14C.
- **Archive never changes quota** (nothing is deleted). No hard delete; no `MediaStorage` delete (14A D14-14).
- No new archived-parent prohibition (C12): uploads/attachments to archived targets follow current project semantics.

---

## 19. Feature-flag semantics (C11)

| Operation | `disabled` / `false` (local default) | **`s3` / `false` (production throughout 14C)** | `s3` / `true` (after 14D PASS + owner action in 14E) |
|---|---|---|---|
| `POST …/photos` — new upload, replay **and** resume | 503 `PHOTO_UPLOADS_DISABLED` before any body byte (after 401) | **503 `PHOTO_UPLOADS_DISABLED`: no PhotoAsset, no processing, no object write** | enabled |
| List / detail / `GET /photo-storage` | work; URL fields `null`; `media_available=false` | work, with presigned URLs | work |
| Attach READY asset / PATCH / archive / restore | work (DB rows only) | work (DB rows only) | work |
| `disabled` + `true` | startup fails (existing validator) | — | — |

**Boundary**: the upload POST is the only code path that can create a PhotoAsset or call `put_object`, and the gate
covers it entirely. No `Retry-After` is sent with `PHOTO_UPLOADS_DISABLED`. The frontend learns the state from
`GET /api/photo-storage` (`uploads_enabled`), never from a build flag.

---

## 20. Security controls

### 20.1 Upload defence in depth
1. Caddy `request_body max_size 27000000` on the upload route only.
2. Pre-body checks: authentication, upload gate, `Content-Length`, project ownership (quota is checked after
   identification, §15).
3. Byte-counting request guard (27 000 000; chunked bodies included).
4. Controlled multipart parsing (`max_files=1`, `max_fields=6`, `max_part_size=8 KiB`); `python-multipart` pinned to a
   current patched version (≥ 0.0.32 at the time of writing).
5. Image bytes ≤ 25 000 000.
6. Decoded format validation — JPEG / PNG / WebP only; disguised / corrupt / truncated rejected; animated PNG/WebP
   rejected; MPO accepted as JPEG first frame; HEIC/HEIF rejected (`PHOTO_UNSUPPORTED_FORMAT`).
7. Header pixel checks before decode: ≤ 60 000 000 pixels, ≤ 12 000 px edge; Pillow bomb error → `PHOTO_TOO_MANY_PIXELS`.
8. Processing concurrency 1, wait 30 s → 503 `PHOTO_PROCESSING_BUSY`.

### 20.2 Temp files, delivery, logging, EXIF
- Workspaces `pe-photo-*` under `PHOTO_TEMP_DIR` (0700), removed in `finally`; stale sweep at startup (lifespan) and at
  the start of each upload; Starlette spooled parts are unnamed files reclaimed by the OS.
- Filename sanitized, metadata only. Presigned TTL 300 s; no public R2 URLs; no original URLs.
- **Logging**: asset / owner ids, sizes, status, error codes. **Never** credentials, presigned URLs, filenames,
  captions or EXIF content.
- **EXIF GPS**: preserved only inside the immutable original; **not** extracted or stored; derivatives stripped.

### 20.3 Temp-space measurement (C15)
The rejected arbitrary 256 MB free-space threshold is **not** added. Existing controls stay (bounded upload, stale
cleanup, `finally` cleanup, processing concurrency 1). **14C.6 measures** peak bytes in `PHOTO_TEMP_DIR` and in the
system temp directory (Starlette spooling) for: a maximum-size request (27 000 000 bytes / 25 000 000-byte image), a
worst-case high-entropy image (largest derivatives), and N concurrent uploads (receipt is not serialized). Expected
per-request order: spooled request + workspace original + two derivatives. Results are recorded in the 14C.6 report;
**any future disk-space threshold requires that measured evidence** and owner approval.

---

## 21. Final API route set (all under `/api`; errors `{"detail": {"code", "message"}}`, §11b)

| Method & path | Request → success | Key errors |
|---|---|---|
| `POST /projects/{project_id}/photos` | multipart (§9) → 201 / 200 `{asset, attachment, thumbnail_url, display_url, urls_expire_at, storage}` | 401; 503 `PHOTO_UPLOADS_DISABLED`; 404 `PROJECT_NOT_FOUND` / `ROOM_NOT_FOUND` / `SURFACE_NOT_FOUND` / `OPENING_NOT_FOUND`; 409 `PHOTO_UPLOAD_ID_CONFLICT` / `PHOTO_STORAGE_QUOTA_EXCEEDED` / `PHOTO_OBJECT_CONFLICT` / `PHOTO_UPLOAD_RESUME_MISMATCH`; 413 `PHOTO_TOO_LARGE`; 415 `PHOTO_UNSUPPORTED_FORMAT`; 422 `PHOTO_UPLOAD_MALFORMED` / `PHOTO_CONTEXT_NOT_SUPPORTED` / `PHOTO_INVALID_IMAGE` / `PHOTO_TOO_MANY_PIXELS` / `PHOTO_ANIMATED_NOT_SUPPORTED`; 503 `PHOTO_PROCESSING_BUSY` (`Retry-After`) / `PHOTO_STORAGE_UNAVAILABLE` (no `Retry-After`); 500 `PHOTO_STORAGE_ERROR` |
| `GET /projects/{project_id}/photos?context=&room_id=&surface_id=&opening_id=&category=&include_in_report=&archived=false&limit=30&cursor=` | → `{items: [{attachment, asset, thumbnail_url}], next_cursor, urls_expire_at}`; READY only; `limit` ≤ 100; order `(position, uploaded_at, id)`; `archived=false` = active attachment **AND** non-archived asset; `archived=true` = archive view: archived attachment **OR** archived asset (§18) | 404; 422 |
| `GET /projects/{project_id}/photos/{asset_id}` | → `{asset, attachments (each with archived_at), thumbnail_url, display_url, urls_expire_at}` | 404 `PHOTO_NOT_FOUND` |
| `POST /projects/{project_id}/photos/{asset_id}/attachments` | JSON `{context, room_id\|surface_id\|opening_id, category?, caption?, include_in_report?}` → 201 | 404; 409 `PHOTO_ATTACHMENT_DUPLICATE`; 422 (incl. `PHOTO_CONTEXT_NOT_SUPPORTED`) |
| `PATCH /projects/{project_id}/photo-attachments/{attachment_id}` | `{caption?, category?, include_in_report?, position?}` → 200 | 404 `PHOTO_ATTACHMENT_NOT_FOUND`; 422 |
| `POST /projects/{project_id}/photo-attachments/{attachment_id}/archive` · `/restore` | → 200 (idempotent) | 404; 409 duplicate on restore |
| `POST /projects/{project_id}/photos/{asset_id}/archive` · `/restore` | → 200 (idempotent) | 404 |
| `GET /photo-storage` | → `{uploads_enabled, media_available, used_bytes (logical/reserved), warning_bytes, soft_cap_bytes, state}` | 401 |

**Not in 14C**: `/photos/counts` (C14, 14E), original download, delete, annotations, INSPECTION / FINDING / WORK
contexts. Attach is not idempotent (a duplicate returns 409); PATCH, archive and restore are idempotent; upload is
idempotent by `upload_id` (§12).

---

## 22. Automated test plan

Routine tests use `InMemoryMediaStorage` (write-once semantics) plus a fault-injecting wrapper; no real R2.

| File | Coverage |
|---|---|
| `test_stage14c_attachment_schema.py` | each CHECK branch valid/invalid; every partial unique index incl. all-NULL PROJECT case and **both INSPECTION variants**; archived duplicates allowed; RESTRICT on all parents incl. **question**; migration chain / single head; SQLite up/down/up vs metadata; rendered PostgreSQL DDL |
| `test_stage14c_attachment_service.py` | target chain per context incl. foreign / cross-project targets; INSPECTION/FINDING/WORK rejected; duplicate; PATCH; attachment archive/restore (idempotent, duplicate on restore); asset archive/restore |
| `test_stage14c_asset_transitions.py` | CAS transitions; READY never regresses under concurrent updates; non-committing `create_pending` + attachment in one transaction |
| `test_stage14c_upload_service.py` | happy path JPEG / PNG / WebP / MPO; oversize; > 60 MP / > 12 000 px; corrupt, disguised, animated, HEIC → no row; PUT failure at original / display / thumbnail; misconfigured; conflict; DB failure before/after PUTs; READY commit failure → resume; replay READY (metadata ignored); resume PENDING/FAILED; resume with missing original (SHA-verified PUT), missing derivative (reprocess verified bytes), wrong-size object, regeneration mismatch; concurrent identical requests (`asyncio.gather`) → one asset, READY; quota warning / in-slot check for new uploads / replay and resume never quota-rejected at FULL; integrity engine classification after each scenario (never `ORPHAN_CANDIDATE`) |
| `test_stage14c_upload_id_conflict.py` | foreign id, own different bytes, own different project → **byte-identical** 409 bodies; foreign path never calls the SHA comparison, processing, storage or transitions (spies) |
| `test_stage14c_upload_guard.py` | byte-counting guard; `Content-Length` early 413; chunked over-limit 413; image > 25 000 000 within a 27 000 000 request → 413 |
| `test_stage14c_photos_api.py` | gate: 503 `PHOTO_UPLOADS_DISABLED` with **zero body reads, zero `put_object`, zero inserts** (storage `s3` and `disabled`), for new / replay / resume; 401; malformed multipart, extra/duplicate fields, 2 files, oversized field → 422; cross-user matrix on every route (identical 404 bodies for foreign / missing / PENDING / FAILED); URLs only after ownership; thumbnail-only in lists, both in detail; **no original route**; pagination / filters; `/photo-storage` states; error envelope per code; presigned URLs absent from captured logs |
| `test_stage14c_config.py` | `PHOTO_MAX_REQUEST_BYTES` default 27 000 000 and `> PHOTO_MAX_UPLOAD_BYTES` validation |
| `test_stage14c_production_templates.py` | Caddy upload-route matcher with `max_size 27000000`; compose `PHOTO_MAX_REQUEST_BYTES` default; `PHOTO_UPLOADS_ENABLED` default `false` |
| 14C.6 measurement | temp-space peaks (§20.3) recorded, not asserted as a threshold |
| Regression | full backend suite, all 14B tests unchanged, ruff, mypy; frontend vitest / tsc / build (frontend unchanged) |

---

## 23. Implementation sequence (14C.2 – 14C.7)

Each step follows the normal workflow (verification → PASS/FAIL → owner acceptance → commit; push / deploy only with
explicit approval).

| Step | Scope | Likely files | Migration | PASS | Owner manual |
|---|---|---|---|---|---|
| **14C.2** PhotoAttachment schema/domain foundation | `0032`, model, attachment service (targets, patch, archive/restore, duplicates), CAS transitions, non-committing `create_pending` | `app/models/photo_attachment.py`, `app/models/__init__.py`, `alembic/versions/0032_photo_attachments.py`, `app/domain/services/photo_attachment_service.py`, `photo_asset_service.py`, `app/domain/exceptions.py`, tests | **yes** | schema / service / transition tests, full suite | **scratch PostgreSQL 16 up/down/up + probes** |
| **14C.3** Upload orchestration | state machine, replay / resume, uniform conflict, logical quota — no HTTP | `app/domain/services/photo_upload_service.py`, `photo_quota.py`, tests | no | upload-service + conflict tests incl. fault injection and concurrency | — |
| **14C.4** Upload HTTP + guards | `python-multipart`, request guard, upload route, gate, error mapping, lifespan temp sweep, `PHOTO_MAX_REQUEST_BYTES`, Caddy file | `app/api/v1/endpoints/photos.py`, `app/api/upload_guard.py`, `app/api/deps.py`, `app/main.py`, `app/schemas/photo.py`, `app/core/config.py`, `requirements.txt`, `pyproject.toml`, `Caddyfile`, `docker-compose.prod.yml`, `.env.production.example`, tests | no | API / guard / config / template tests; gate proof | — |
| **14C.5** Read / delivery / attachments / archive | list, detail, presign, attach, PATCH, archive/restore, `/photo-storage` | `photos.py`, `schemas/photo.py`, tests | no | API matrix | — |
| **14C.6** Adversarial / regression verification | full suites, ruff / mypy, cross-user, malformed multipart, concurrency, temp-space measurement (§20.3), diff review | tests, report | no | all green; measurements recorded | review |
| **14C.7** Production deploy with uploads **OFF** | backend image with 0032, new Caddy config | — | applies `0032` | health OK; authenticated POST → 503 `PHOTO_UPLOADS_DISABLED` (JSON body passes Cloudflare); unauthenticated → 401; `photo_attachments` empty; integrity check clean; `PHOTO_UPLOADS_ENABLED=false` | **yes — every step owner-approved** (runbook migration procedure) |

---

## 24. Production safety and the Stage 14D gate

- `PHOTO_UPLOADS_ENABLED` stays `false` in production throughout Stage 14C (compose default `false`; the server
  `.env.production` is not changed by 14C).
- The upload POST is the only path that can create a PhotoAsset or write an object; with the gate off it returns 503
  before reading the body, proven by tests (no body read, no PUT, no insert).
- All other 14C routes only read, presign, or change attachment/archive metadata; none can create assets or objects.
- The 14C.7 deployment adds an empty table (`0032`) and a stricter Caddy limit; every deployment step requires explicit
  owner approval.
- **Stage 14D (independent Oracle backup, restore drill, integrity verification, media-readiness gate) remains
  mandatory before any production photo upload.** Enabling uploads is a separate owner action in 14E after 14D PASS.

---

## 25. Deferred work

| Item | Deferred to |
|---|---|
| Mobile photo UI, frontend client/types, `/photos/counts` re-evaluation, device checks (Telegram WebView presigned delivery, Cloudflare body/timeout behaviour, HEIC arrival) | 14E |
| INSPECTION / FINDING contexts, finding `lineage_id` | 14F |
| POINT annotations (`photo_annotations`) | 14G |
| WORK context (occurrence_key evidence) | 14H |
| Report read model / original retrieval for documents | 14I / Stage 15 |
| HEIC/HEIF implementation | 14B.H device gate (14B plan §27) |
| Disk-space guard threshold | only after 14C.6 measurements + owner approval |
| Hard delete, physical object cleanup, `MediaStorage` delete | future stage, not planned |
| Backend streaming delivery | only if 14E shows presigned delivery incompatible (OD-12 fallback) |

---

## 26. Superseded 14A / 14B details (for traceability)

| Earlier text | Superseded by |
|---|---|
| 14A §15.2 `question_id` ON DELETE SET NULL | §7 RESTRICT (R-2) |
| 14A §15.3 single partial unique index over nullable targets | §6 per-context indexes |
| 14A §16 `GET /api/projects/{p}/photo-storage` | §21 `GET /api/photo-storage` (C13) |
| 14A §16 `GET /api/projects/{p}/photos/counts` | deferred to 14E (C14) |
| 14A §8 "PENDING/FAILED → resume from step 3" | §11 Stage D (HEAD per key, SHA-verified retry bytes, reprocessing for missing derivatives) |
| 14B §7 Caddy allowance "+1 MB (PROPOSED)" | §10 `PHOTO_MAX_REQUEST_BYTES = 27_000_000` (C3) |
| 14B §8 `MediaStorageDisabled` → "feature-off response" | §19 503 `PHOTO_UPLOADS_DISABLED` (C7) |
| 14B §10 Cache-Control "PROPOSED for 14C" | §17 presign overrides `private, max-age=<TTL>`, `inline` (C6) |

## 27. Owner approval record

- 2026-09-28: 14C.1 audit/design reviewed; corrections C1–C16 applied; R-1 and R-2 approved; **14C.1 — COMPLETE /
  OWNER APPROVED**. No implementation, migration, dependency, configuration, Caddy or production change was made.
