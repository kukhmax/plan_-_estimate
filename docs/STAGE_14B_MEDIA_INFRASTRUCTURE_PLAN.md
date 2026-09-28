# Stage 14B — Media Infrastructure Readiness: Audit & Implementation Plan (14B.1)

- **Date**: 2026-09-28
- **Branch / HEAD**: `stage-14` @ `9ed5976` (= `origin/stage-14`)
- **Sub-stage**: 14B.1 — **audit + implementation plan only**. No runtime code, migration, dependency, Docker, `.env`,
  Cloudflare or Oracle change.
- **Status**: **Stage 14B.1 — COMPLETE / OWNER ACCEPTED** (2026-09-28). **Stage 14B.2 — COMPLETE / OWNER ACCEPTED**
  (2026-09-28; manual R2 setup recorded in §22). **Stage 14B.3 — COMPLETE / OWNER ACCEPTED** (2026-09-28; record
  in §23; ARM64 benchmark and final defaults in §23.12–§23.13). **Stage 14B.4 — COMPLETE / OWNER ACCEPTED**
  (2026-09-28; commit `e57e037`; PostgreSQL 16 result in §24.8). **Stage 14B.5 — COMPLETE / OWNER VERIFIED** (2026-09-28;
  production runtime `e57e037`, DB `0031_photo_assets`, media disabled, uploads off; §25). **Stage 14B.6 — NOT STARTED**
  (R2 connectivity & credential readiness, §26). 14B.1 and 14B.2 create **no runtime functionality**; 14B.3 adds library
  code only (no endpoint, no DB, no deployment).
- **Revision 2 (2026-09-28)**: owner review applied — R1, R2, R4–R9 **OWNER APPROVED** (R1 with correction); R3 open at that revision
  (multipart vs raw body, §6); decimal quota bytes; EU jurisdiction; age-based temp cleanup; original immutability;
  memory figures are estimates + benchmark requirement; Caddy defence in depth; cache policy separated from signed-URL
  TTL; R2 conditional-PUT note.
- **Revision 3 / closure (2026-09-28)**: R3 **OWNER APPROVED** (multipart baseline, `python-multipart` approved as a
  future dependency); `PHOTO_MAX_UPLOAD_BYTES=25_000_000` approved; image-processing concurrency 1 approved; the
  proposed "upload concurrency 3" removed; R1–R9 all OWNER APPROVED (§18).
- **Parent contract**: `docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md` (Stage 14A, OWNER ACCEPTED). Where this plan
  refines 14A, the owner decision is recorded in §18.

---

## 1. Stage 14A contract verified (committed text, unchanged)

| Decision | 14A location | Verified |
|---|---|---|
| Cloudflare R2 Standard = primary media storage; private bucket; no public canonical URLs | §4.2, D14-3, OD-1 | yes |
| Oracle Object Storage = independent secondary backup; R2 versioning complementary only | §13.2, D14-21, OD-3 | yes |
| Provider-neutral `MediaStorage`, S3-compatible primary adapter, no Cloudflare concepts in the domain | §4.1, §4.2 | yes |
| VM/Docker disk = bounded temporary processing only, deterministic cleanup | §4.1, OD-2 | yes |
| JPEG/PNG/WebP; 25 MB encoded; 60 MP decoded (limits provisional) | §4.4, D14-5, OD-8 | yes |
| HEIC/HEIF deferred to 14B.H + owner approval | §4.4, §19, OD-8 | yes |
| Immutable explicit original/display/thumbnail keys + `storage_backend`; UUID-only; no mutable names | §4.3, D14-4 | yes |
| PENDING / READY / FAILED; only READY visible; no atomic DB+object claim | §8, D14-17 | yes |
| `upload_id` idempotency; same bytes resume, different bytes 409; checksum = integrity metadata, no global dedupe | §8, D14-18 | yes |
| Thumbnail/display via short-lived presigned GET after ownership check; original backend/report-only | §9, D14-19, OD-12 | yes |
| `PHOTO_SIGNED_URL_TTL_SECONDS`, default 300, configurable | §9, D14-28, OD-10 | yes |
| Warning 8 GB, soft upload cap 10 GB, configuration | §12, D14-22 | yes |
| No production uploads before the 14D backup/restore gate | §13.5, §19 | yes |

No discrepancy. Refinements decided in this review: key layout (R1), schema split (R2), GB units (R6); the upload
transport (R3) is decided as the 14A §16 multipart baseline.

---

## 2. Current backend configuration (audited)

| Aspect | Current state |
|---|---|
| File | `backend/app/core/config.py` — one `Settings(BaseSettings)` class, module singleton `settings = Settings()` |
| Mechanism | `pydantic-settings` (`env_file=".env"`, `extra="ignore"`); typed fields with defaults |
| Env loading | process environment, then `.env` in the working directory (dev) |
| Production | `docker-compose.prod.yml` maps each variable explicitly under `backend.environment` from `--env-file .env.production`; a variable not listed there **never reaches the container** |
| Examples | `.env.example` (dev), `.env.production.example` (placeholders `CHANGE_ME`); `.env.production` is `chmod 600`, git-ignored (runbook §12) |
| Tests | `tests/conftest.py::setup_test_settings` mutates the singleton; no dependency override for settings |
| Secrets | plain `str` fields (`TELEGRAM_BOT_TOKEN`, `JWT_SECRET_KEY`); no `SecretStr` |
| Startup validation | **none** — no validators, no lifespan hook |
| Feature-flag pattern | none (only `MOCK_TELEGRAM_AUTH`, `DEBUG`); naming `UPPER_SNAKE` with a domain prefix (`TELEGRAM_*`, `JWT_*`) |
| Process model | `entrypoint.sh` → `alembic upgrade head` → `uvicorn app.main:app` **single worker**; image `python:3.12-slim` (production ARM64); local venv Python 3.14 |
| Upload/file code | none; `python-multipart`, Pillow, boto3 absent; Starlette 1.6 / FastAPI 0.141 / anyio 4 installed |
| Edge | Cloudflare → Caddy (`reverse_proxy backend:8000`) → backend. **Audit finding: production Caddy has no Stage 14-specific request-body limit.** Frontend nginx sets no CSP |
| Ownership | `get_current_user` (`app/api/deps.py`) + `ProjectService.get_project(project_id, owner_id)` → 404 for foreign ids |

---

## 3. Python S3 client — boto3 (R5 OWNER APPROVED for future implementation)

| | **A. boto3 / botocore** | B. already present: `httpx` + hand-written SigV4 | C. aiobotocore / aioboto3 |
|---|---|---|---|
| R2 compatibility | documented by Cloudflare; `endpoint_url`, `region_name="auto"`, SigV4 | possible, but we would own signing | same as A |
| Presigned GET | `generate_presigned_url` (offline) | hand-written | yes |
| Put/Get/Head/Delete/List | yes | hand-written each | yes |
| Multipart | available (not needed: 25 MB single PUT) | hand-written | yes |
| Size/complexity | pure Python (boto3, botocore, s3transfer, jmespath, python-dateutil, urllib3) | 0 deps, security-critical code in-house | A + aiohttp; tight version pinning |
| Sync/async | synchronous → off the event loop | async | async |
| Testability | `botocore.stub.Stubber` (no moto) | custom | fiddly |
| ARM64 | pure Python | n/a | native aiohttp wheels |

boto3 serves both R2 and Oracle's S3-compatibility endpoint (14D backup) with one adapter. Every boto3 network call runs
through `anyio.to_thread.run_sync` inside the adapter, so the event loop is never blocked; presigning is local CPU work.
Client: `signature_version="s3v4"`, `region_name="auto"`, connect/read timeouts, standard retries (3), and
`request_checksum_calculation="when_required"` / `response_checksum_validation="when_required"` (recent botocore
defaults add CRC checksums; **verify against the real bucket in the smoke test**). One lazily created client per process,
only when storage is enabled. Not added in 14B.1.

---

## 4. Image processing — Pillow (R5 OWNER APPROVED for future implementation)

Pillow wheels bundle libjpeg-turbo, libpng, libwebp, zlib and LittleCMS for aarch64 (CPython 3.12 production, 3.14
local); no suitable library is already present; pyvips would add a system library for no benefit at one upload at a
time. **HEIC/HEIF: DEFERRED TO 14B.H** — no `pillow-heif`/libheif.

### 4.1 Original immutability (rule)

- The **canonical original** is the exact byte sequence of the uploaded image (the file part in multipart, or the body
  in raw mode). It is stored **byte-for-byte unchanged** after validation.
- Validation reads/decodes from a read-only handle; it **never rewrites** the canonical original (no re-encode, no EXIF
  rotation, no metadata removal on the original).
- **SHA-256 is computed over exactly those canonical bytes** (while receiving, no second pass needed).
- The private original may retain EXIF/metadata (never served to clients in v1).
- The client filename and declared MIME type are untrusted: they never determine format, extension, key or storage
  identity (the filename is kept only as display metadata).

### 4.2 Validation and derivative pipeline

1. Receive into bounded temporary storage (§5, §6), counting bytes against `PHOTO_MAX_UPLOAD_BYTES`; sha256 in the same pass.
2. `Image.open` (lazy header read): format must be `JPEG`, `PNG` or `WEBP`; animated PNG/WebP rejected.
3. Pixel guard **before decoding**: header `width × height ≤ PHOTO_MAX_DECODED_PIXELS`, longest edge ≤ 12 000 px;
   `Image.MAX_IMAGE_PIXELS` set to the same limit and `DecompressionBombWarning` escalated to an error.
4. Decode (JPEG may use `draft()` reduced decoding for derivatives — the full stream is still parsed, so truncation is
   detected); any decoder error → `PHOTO_INVALID_IMAGE`.
5. `ImageOps.exif_transpose` on the **decoded copy** only; stored `width`/`height` = oriented dimensions.
6. Colour: ICC profile present → convert to sRGB; transparency → **flattened onto opaque white `#FFFFFF`** (deterministic
   background for JPEG derivatives).
7. Derivatives (R8 OWNER APPROVED as initial defaults): **display** longest edge **2048 px**, **thumbnail** longest edge
   **480 px**, **never upscaled**; **JPEG**, **sRGB**, **all metadata stripped** (no EXIF, ICC, XMP, comments). Proposed
   encoder settings: quality 85 / 80, `subsampling="4:2:0"`, `progressive=True`, `optimize=False`, LANCZOS resampling.
   These values are **not performance-proven**; they are verified in the 14B image-pipeline tests and benchmark (§5.3).
8. `captured_at` from EXIF `DateTimeOriginal` when present; GPS is not extracted or stored.

---

## 5. Temporary storage, memory and concurrency (1 OCPU / 6 GB)

### 5.1 Temporary files

- Dedicated directory `PHOTO_TEMP_DIR` (default `<system tmp>/plan-estimate-photos`), never a shared root.
- Every Stage 14 temp file the application creates is named with a fixed prefix (e.g. `pe-photo-`), so it is positively
  identifiable.
- **Per request**: temporary files are removed in `finally` on success and on every failure path.
- **Abandoned-temp cleanup (age-based)**: at startup, and opportunistically at the start of an upload, delete only files
  in `PHOTO_TEMP_DIR` that match the Stage 14 prefix **and** are older than `PHOTO_TEMP_STALE_AFTER_SECONDS` (proposed
  default `86400`, implementation-reviewable). Nothing else is touched; the directory is never blindly emptied.
- Unnamed spooled temp files created by Starlette's multipart parser (if multipart is kept, §6) are unlinked by the OS
  on creation and cannot be left behind after a crash; they are bounded by the request-size guards (§6, §7).

### 5.2 Memory and concurrency

- Current request model: one uvicorn worker, async event loop, anyio thread pool — so in-process limits are global.
- **OWNER APPROVED initial policy: maximum concurrent image-processing operations = 1** (decode/derive serialized, run
  in a worker thread) for the current target (ARM64, 1 OCPU, 6 GB RAM). No second concurrency number is introduced:
  network receive of concurrent requests is bounded per request by the size guards (§7), not by an extra cap.
  Concurrency is revisited only after benchmark results (§5.3).
- **Memory is an estimate, not a bound.** A 60 MP image is ~180 MB as RGB and ~240 MB as RGBA for a single buffer, but
  real peak can be substantially higher: RGBA vs RGB conversion, `exif_transpose` producing a rotated copy, intermediate
  copies (colour conversion, alpha flattening), resize buffers, encoder buffers and Pillow/native allocator behaviour.
- Waiting for the processing slot: if an acquire timeout is kept, it is **configurable**
  (`PHOTO_PROCESSING_WAIT_SECONDS`, default **PROPOSED 30**, pending measurements) and not an API contract; on timeout
  the client receives a retryable "busy" error and retries with the same `upload_id` (idempotent).
- If the uvicorn worker count is ever raised, in-process limits become per-process and must be revisited.

### 5.3 Benchmark requirement (before production uploads)

Stage 14B must measure **peak RSS and processing duration** of the pipeline on a production-equivalent **ARM64**
environment where practical (the Oracle VM itself, outside the serving container, with owner approval; otherwise an
ARM64 equivalent, recorded as such), for representative:

- JPEG (typical phone photo, 12 MP and 48 MP),
- PNG (large, with alpha),
- WebP,
- a large image near the decoded-pixel limit (~60 MP),
- an EXIF-rotated image (orientation 6/8).

Results (peak RSS, wall time, derivative sizes) are recorded in the Stage 14 docs and decide whether processing
concurrency can be revisited, the wait timeout and whether 60 MP stays. Production uploads are not enabled before these numbers exist.

---

## 6. Upload transport — multipart vs raw body (R3 — OWNER APPROVED: multipart)

Verified in the installed versions (FastAPI 0.141, Starlette 1.6): Starlette's multipart parser spools **file parts**
into `SpooledTemporaryFile(max_size=1 MB)` (memory, then an unnamed temp file in the default temp dir) with **no size
limit on file parts** (`max_part_size` applies only to non-file fields); `max_files`/`max_fields` limit counts. When an
endpoint declares `File()`/`Form()` parameters, FastAPI calls `request.form()` **before any dependency runs**, so an
oversized file is fully spooled before application code can reject it. Form parsing requires `python-multipart`.

| Criterion | A. multipart/form-data (14A baseline) | B. raw request body streaming |
|---|---|---|
| Enforce 25 MB before excessive resource use | Only with extra guards: proxy limit + `Content-Length` pre-check + a byte-counting `receive` wrapper on the upload route, and the endpoint takes `Request` and calls `request.form(max_files=1, max_fields=…)` itself (no `File()` params). With those, bounded at limit + multipart overhead | Native: the handler counts bytes from `request.stream()` and aborts at the limit; plus proxy limit + `Content-Length` pre-check |
| Temporary disk | Unnamed spooled temp file in the system temp dir (not `PHOTO_TEMP_DIR`); auto-reclaimed by the OS even after a crash; bounded by the guards | Named file in `PHOTO_TEMP_DIR`; removed in `finally`; stale files cleaned by age (§5.1) |
| Metadata (`upload_id`, context + target, category, caption) | Form fields in the same request, validated with Pydantic; caption stays in the body | Query parameters/headers (caption in the URL → length/encoding limits and access-log exposure), or a two-step API (JSON create + `PUT` bytes), which changes the 14A state-machine order (a row before bytes exist) |
| Telegram Mini App / browser | `FormData` + XHR with upload progress; standard | `XHR.send(file)` with progress; equally simple for one file |
| API clarity | One self-describing request; matches 14A §16 | Clear only as two-step; one-step mixes body and query semantics |
| Caddy protection | `request_body max_size` = image limit + small documented overhead (proposed 1 MB) | `request_body max_size` = image limit + ~0 |
| FastAPI/Starlette behaviour | Must avoid `File()` params on this route (parse-before-check); parser attack surface in `python-multipart` (past DoS advisories, patched — pin a current version) | No parser; plain stream |
| Cleanup | Starlette closes form files after the response; OS reclaims unnamed files | Our `finally` + age-based sweep |
| Testability | `httpx` `files=`/`data=`; oversized/chunked cases via the counting wrapper | `httpx` `content=`; straightforward |
| Dependency | **new: `python-multipart`** (not in R5) | none |

**Decision (R3 — OWNER APPROVED): multipart/form-data is the Stage 14 upload protocol baseline;
`python-multipart` is approved as a future Stage 14 dependency** (pinned, current patched version; not installed in
14B.1). Accepted reasons: one request carries image + metadata; `upload_id` stays part of the same operation;
context/category/caption need no URL/query transport; the 14A state-machine/API model is preserved; FormData support in
browsers/Telegram is straightforward. Raw-body / two-step upload is **not** part of Stage 14 v1 unless later evidence
requires reconsideration.

Implementation constraint: the upload route must **not** use FastAPI `File()`/`Form()` parameters in a way that parses
the whole multipart request before the guards act. Required defence in depth (details verified in 14C):

1. reverse-proxy request-size limit;
2. `Content-Length` early rejection when present;
3. bounded request handling / encoded-byte enforcement (byte-counting receive guard, also for chunked bodies);
4. controlled multipart parsing (route takes `Request`, calls `request.form(max_files=1, max_fields=…)` itself);
5. decoded-pixel validation.

---

## 7. Defence in depth for request size (audit finding)

Production Caddy has **no Stage 14-specific request-body limit** today. The future upload implementation must layer:

1. **Reverse proxy**: Caddy `request_body { max_size … }` on the upload route only — image limit plus a small documented
   multipart overhead (exact allowance PROPOSED, e.g. +1 MB — not approved); Cloudflare's own body limit (100 MB on Free — verify plan)
   is an outer bound, not the control.
2. **Backend encoded-byte limit**: `Content-Length` pre-check + streaming byte counter; the canonical image bytes are
   limited to `PHOTO_MAX_UPLOAD_BYTES=25_000_000`. Proxy/multipart request limits may be slightly larger for protocol
   overhead, which never raises the 25,000,000-byte image limit.
3. **Decoded-pixel limit**: header check before decode + Pillow bomb guard (`PHOTO_MAX_DECODED_PIXELS`).

Caddy is **not** modified in 14B.1; the change ships with the upload endpoint (14C) and needs owner-approved deployment.

---

## 8. `MediaStorage` port (smallest interface)

Runtime (14B/14C):

| Method | Input → output | Used by |
|---|---|---|
| `put_object(key, source, content_type)` | local file/stream → `None` | upload |
| `head_object(key)` | → `ObjectInfo(size, etag)` or `None` | idempotent resume, integrity |
| `presign_get(key, ttl_seconds)` | → URL string | thumbnail/display delivery |
| `download_to(key, path)` | → local temp file | Stage 15 original retrieval, derivative regeneration |

Tooling only (integrity/backup) — separate `MediaStorageAdmin` protocol, not injected into API code: `iter_keys(prefix)`.
No `delete_object` in v1 (14A D14-14). Copy/export is not a port method (backup = `download_to` from one adapter +
`put_object` to another).

**Write-once:** correctness does not depend on the provider: each key contains a fresh asset UUID, keys are written only
after the PENDING row is committed, and a retry re-PUTs identical bytes (sha256 verified). Conditional PUT is an
additional guard: current Cloudflare R2 S3-compatibility documentation reports `PutObject` conditional headers
(`If-None-Match`) as supported; the adapter sends `If-None-Match: *` and treats 412 as "already stored" after a
`head_object` size check. The actual boto3 request behaviour **must still be verified in the real R2 smoke test**; if it
fails, the adapter falls back to head-before-put and the application stays correct.

Errors (adapter maps all `botocore` exceptions; nothing provider-specific escapes):

| Error | Cause | API mapping (14C) |
|---|---|---|
| `MediaStorageUnavailable` | timeouts, connection errors, 5xx, throttling | 503, retryable (asset → FAILED, retry same `upload_id`) |
| `MediaStorageMisconfigured` | 401/403, missing bucket, bad endpoint | 500 + log; no details leaked |
| `MediaObjectNotFound` | 404 on head/download | domain decides (integrity: "missing object") |
| `MediaStorageDisabled` | port used while storage disabled | feature-off response, never 500 |
| `MediaObjectConflict` | write-once key already holds **different** content (412 on conditional PUT and the stored object does not match) — an integrity/conflict condition, never an overwrite (OWNER APPROVED, 14B.3 review) | 409-class integrity error; logged; the existing object is never overwritten |

Implementations: `S3MediaStorage` (boto3), `InMemoryMediaStorage` (tests), `DisabledMediaStorage`; selected once at
startup, injected through a FastAPI dependency (`get_media_storage`) so tests use `app.dependency_overrides`.

---

## 9. Object keys (R1 — OWNER APPROVED with correction)

```
photos/v1/{asset_uuid}/original.{validated_extension}
photos/v1/{asset_uuid}/display.jpg
photos/v1/{asset_uuid}/thumb.jpg
```

- `validated_extension` is determined **only after decoding/validation**: JPEG → `jpg`, PNG → `png`, WebP → `webp`.
  It never comes from the client filename; the filename and declared MIME type are never used for storage identity.
- `asset_uuid` = UUIDv4 (= client `upload_id`), lowercase canonical form. Keys contain immutable IDs only — no
  owner/project/client/room/surface identifiers or labels, no filename.
- All three keys are computed at asset creation and stored verbatim in `storage_key_*`; integrity tooling compares exact
  keys; the same keys are used in R2, in the Oracle backup and after any provider migration.
- `Content-Type` is set on PUT from the validated format (`image/jpeg|png|webp`).

---

## 10. Cache policy (correction)

`PHOTO_SIGNED_URL_TTL_SECONDS` (how long a presigned URL is valid) and object/response `Cache-Control` (how long a
browser may reuse fetched bytes) are **separate policies**. No `Cache-Control` value is approved by this plan; the
earlier "`private, max-age=300`" suggestion is withdrawn. Delivery/cache policy (object metadata, presign
response-header overrides, public-cache prevention) is decided in **14C** unless a later owner decision fixes it earlier.

---

## 11. Configuration (R4 — OWNER APPROVED gates; names proposed)

| Variable | Default | Secret | Notes |
|---|---|---|---|
| `MEDIA_STORAGE_BACKEND` | `disabled` | no | `disabled` \| `s3` (approved) |
| `PHOTO_UPLOADS_ENABLED` | `false` | no | approved |
| `MEDIA_STORAGE_NAME` | `r2-primary` | no | label stored in `photo_assets.storage_backend` |
| `MEDIA_S3_ENDPOINT_URL` | — | no | EU jurisdiction endpoint (§13); **HTTPS only** (OWNER APPROVED, no HTTP escape hatch) |
| `MEDIA_S3_BUCKET` | — | no | |
| `MEDIA_S3_REGION` | `auto` | no | |
| `MEDIA_S3_ACCESS_KEY_ID` | — | no — **identifier**, operationally sensitive | `SecretStr` (masked in repr/logs as hygiene); not committed without reason; visible in SigV4 presigned URLs (§23.3) |
| `MEDIA_S3_SECRET_ACCESS_KEY` | — | **yes** — the only secret credential | `SecretStr`; never logged, printed, documented or exposed |
| `PHOTO_SIGNED_URL_TTL_SECONDS` | `300` | no | 14A-approved; validated 60–3600 |
| `PHOTO_MAX_UPLOAD_BYTES` | **`25_000_000`** (OWNER APPROVED, decimal 25 MB) | no | canonical image bytes only |
| `PHOTO_MAX_DECODED_PIXELS` | `60_000_000` | no | |
| `PHOTO_STORAGE_WARNING_BYTES` | **`8_000_000_000`** | no | R6: decimal GB |
| `PHOTO_STORAGE_SOFT_CAP_BYTES` | **`10_000_000_000`** | no | R6: decimal GB; must be ≥ warning |
| `PHOTO_TEMP_DIR` | `<tmp>/plan-estimate-photos` | no | dedicated dir |
| `PHOTO_TEMP_STALE_AFTER_SECONDS` | `86400` (OWNER APPROVED initial default, §23.13) | no | age-based cleanup (§5.1) |
| `PHOTO_PROCESSING_WAIT_SECONDS` | `30` (OWNER APPROVED initial default, §23.13) | no | acquire timeout for the processing slot |

Quota values are exact byte counts (decimal GB, matching R2 GB-month terminology); 8 GiB/10 GiB are **not** used.
`MEDIA_S3_*` rather than `R2_*` because the adapter is generic S3. Processing concurrency (1), derivative parameters and
the file prefix are code constants. Backup credentials are **not** backend settings.

Validation (new `model_validator`, fails at startup so a misconfigured container fails its healthcheck visibly):
`MEDIA_STORAGE_BACKEND=disabled` → all `MEDIA_S3_*` ignored, app starts normally; `s3` with any missing endpoint/bucket/
key → **fail fast**; `PHOTO_UPLOADS_ENABLED=true` requires `s3`; numeric bounds. Production wiring later: explicit
entries in `docker-compose.prod.yml` and `.env.production.example` (placeholders only); real values only in the
server's `.env.production`.

---

## 12. Feature gates (R4 — OWNER APPROVED)

| Environment | `MEDIA_STORAGE_BACKEND` | `PHOTO_UPLOADS_ENABLED` | Behaviour |
|---|---|---|---|
| Local/tests | `disabled` (default) or in-memory override | per test | starts with no S3 config |
| Production before 14D | `disabled` or `s3` | `false` | app unchanged; uploads unavailable; storage may be configured for smoke/backup/integrity tooling |
| Production after 14D PASS | `s3` | `true` (owner action) | uploads available |
| Emergency upload stop | `s3` | `false` | uploads off; **existing media stays readable** (reads depend only on storage) |
| Partial config | `s3` incomplete, or uploads on with `disabled` | — | **startup fails** — never half-enabled |

The frontend learns the state from the backend (capability field in a 14C endpoint), never from a build-time flag.

---

## 13. Future manual R2 setup (14B.2 — owner performs, not done now)

1. Cloudflare dashboard → **R2 Object Storage**. If R2 was never enabled on the account, Cloudflare asks to activate it
   (typically a payment method is requested even within the free allowance — verify then; owner decision). No other
   plan/billing change is required.
2. **Create the production bucket in the EU jurisdiction** (R7 OWNER APPROVED). The **jurisdiction** is a data-residency
   restriction chosen at creation and cannot be changed later; it is **not** a location hint (WEUR/EEUR hints only
   suggest placement and give no guarantee) — do not use a hint instead. Storage class **Standard**. Proposed names
   (final at setup): `plan-estimate-media-prod`; a separate `plan-estimate-media-dev` for development smoke tests (also
   EU jurisdiction, recommended, so the smoke test exercises the same endpoint form).
3. Bucket settings: `r2.dev` public access **disabled**, **no custom domain**, no CORS rule (images load via `<img src>`
   presigned URLs without credentials).
4. Note the **Account ID**. S3 endpoint for EU-jurisdiction buckets: `https://<ACCOUNT_ID>.eu.r2.cloudflarestorage.com`
   (the default endpoint without `.eu` does not address EU-jurisdiction buckets).
5. **Manage R2 API Tokens → Create API token**: permission **Object Read & Write**, **specific bucket only**
   (the production bucket, selected under the EU jurisdiction), optional client-IP filter to the Oracle VM public IP.
   A separate token for the dev bucket. Admin tokens are never used by the app. (Object tokens cannot exclude delete;
   the app has no delete path and the independent backup covers loss.)
6. Store the Access Key ID and Secret Access Key (shown once) in the owner's password manager only — never in Git, docs,
   tests, chat or tickets.
7. Later, with the owner-approved 14B deploy: values into the server `.env.production` (`chmod 600`).
8. The 14D backup job gets its **own** token: **Object Read only**, production bucket only.
9. Non-production smoke test (dev bucket): PUT a generated image, HEAD it, presign GET → 200, after expiry → 403,
   unsigned URL → denied; conditional PUT (`If-None-Match: *` twice → second 412); botocore checksum settings accepted.
   Results recorded without secrets.

Optional complement (never the backup): R2 bucket lock rules against deletion/overwrite — evaluated in 14D.

---

## 14. Oracle Object Storage backup (concept for 14D — not configured)

- **Bucket** `plan-estimate-media-backup` (name proposed), private, Standard tier, **object versioning on**; region
  chosen with the owner (EU, consistent with R7).
- **Identity**: dedicated IAM group `media-backup`, policy limited to that bucket (e.g.
  `Allow group media-backup to manage objects in compartment <c> where target.bucket.name = 'plan-estimate-media-backup'`),
  **Customer Secret Key** for the S3-compatibility API; not used by the backend app.
- **API**: S3 compatibility (`https://<namespace>.compat.objectstorage.<region>.oraclecloud.com`) — same boto3 adapter,
  same keys on both sides.
- **Job** (runs on the VM as a one-off/cron command with its own env file, never in the backend service environment):
  DB → READY assets → for each key missing in the backup bucket, `download_to` from R2 (read-only token) and `put_object`
  to OCI (immutable objects → incremental by existence) → verify sha256 of the original → write manifest.
- **Manifest** (JSON Lines, `manifests/{run_timestamp}.jsonl` in the backup bucket and next to the matching `pg_dump`):
  header `{run_id, created_at, db_dump_file, source_bucket, target_bucket, asset_count}`; one line per asset
  `{asset_id, status, storage_backend, key_original, key_display, key_thumbnail, sha256_original, byte_size_original,
  content_type, backed_up_at}`.
- **Restore verification**: restored DB → every READY asset present in the restore target → original sha256 equals the
  DB value; derivatives present (or regenerated from the original); unreferenced objects reported.

---

## 15. Test strategy (no cloud credentials in CI)

| Area | Tests | Tooling |
|---|---|---|
| Storage contract | put/head/download/presign/not-found/disabled identical across adapters | `InMemoryMediaStorage`; same suite vs `S3MediaStorage` with `botocore.stub.Stubber` |
| S3 adapter | request shapes (bucket, key, ContentType, IfNoneMatch), offline presign with fake creds (`X-Amz-Expires=300`), error mapping (timeout → Unavailable, 403 → Misconfigured, 404 → NotFound, 412 → exists) | Stubber (no moto) |
| Keys | layout; extension from decoded format; filename/MIME ignored | unit |
| Config | disabled starts without S3 config; partial `s3` fails; uploads on + disabled fails; bounds; decimal quota defaults; `SecretStr` hidden | `Settings(_env_file=None, **kw)` |
| Disabled startup | app imports, health OK | `async_client` |
| Checksum / immutability | sha256 over received bytes; stored original byte-identical to upload (EXIF intact) | unit |
| Formats | JPEG/PNG/WebP accepted; disguised text/HTML/SVG/PDF/GIF named `.jpg` rejected; truncated JPEG rejected; animated rejected | images generated with Pillow in-test |
| Limits | oversized encoded body aborted (incl. chunked without Content-Length); header > 60 MP rejected before decode; lying header → bomb error | small limits via config |
| EXIF | orientation 6/8 → derivatives rotated; derivatives carry no EXIF/ICC/XMP/GPS | Pillow `Exif()` |
| Derivatives | exact dimensions (landscape/portrait/small, no upscale); RGB JPEG; alpha → white | unit |
| Temp | removed on success and each failure path; age sweep deletes only prefixed files older than threshold, keeps fresh and foreign files | `tmp_path`, controlled mtimes |
| Concurrency | processing serialized; configurable wait → busy error | fake pipeline |
| Benchmark (§5.3) | peak RSS + duration per representative image | script, ARM64, results recorded (not a CI test) |

Manual only: the R2 smoke test (§13.9) with dev credentials. Later: 14C API tests with the in-memory adapter; 14D drill
with real buckets.

---

## 16. Migration ownership (R2 — OWNER APPROVED; none created now)

| Sub-stage | Migration | Content | Depends on |
|---|---|---|---|
| 14B | `photo_assets` | status, keys, file facts, owner/project FKs RESTRICT | Stage 13 head `0030` |
| 14C | `photo_attachments` | all seven contexts + full CHECK (API enables contexts progressively) | photo_assets |
| 14F | `inspection_findings.lineage_id` | column + deterministic backfill + index (group key treats nullable `question_id` NULL as a value) | independent; evidence UI needs photo_attachments |
| 14G | `photo_annotations` | POINT markers | photo_attachments |
| 14H | none | no new media identity table unless implementation proves necessary | photo_attachments |

---

## 17. 14D backup/restore gate (R9 — OWNER APPROVED)

Isolated drill environment and bucket; **no real production object is ever intentionally deleted.**

1. Drill DB (restored from a real production `pg_dump`) + drill R2 bucket + drill OCI target; seeded with assets of each
   format created through the real pipeline (backend run natively; no local Docker).
2. Primary write/read in the drill bucket; presigned thumbnail/display → 200.
3. DB metadata backup (`pg_dump` of the drill DB).
4. Independent OCI media backup; manifest written; manifest count = READY count.
5. Loss simulation in the **drill bucket only** (one original, one derivative) + DB restored into a fresh database.
6. Integrity check reports exactly the missing objects.
7. Media restored from OCI; original sha256 = DB value; derivative restored or regenerated.
8. Integrity clean; the application reads restored media.
9. Production, non-destructive: production backup job runs, manifest generated, OCI copy checksum verified; no
   production data changed.
10. Runbook updated with the exact commands; benchmark results (§5.3) present; owner sign-off → only then
    `PHOTO_UPLOADS_ENABLED=true` in production (14E).

---

## 18. Owner decisions (14B.1 review)

| ID | Topic | Status |
|---|---|---|
| R1 | Keys `photos/v1/{asset_uuid}/original.{validated_extension}`, `display.jpg`, `thumb.jpg`; extension only from decoded format | **OWNER APPROVED (with correction)** |
| R2 | Migrations: 14B assets, 14C attachments, 14F lineage, 14G annotations, 14H none | **OWNER APPROVED** |
| R3 | multipart/form-data baseline; `python-multipart` approved as future dependency; guarded, controlled parsing (§6) | **OWNER APPROVED** |
| R4 | `MEDIA_STORAGE_BACKEND=disabled\|s3` + `PHOTO_UPLOADS_ENABLED` | **OWNER APPROVED** |
| R5 | boto3 + Pillow for future implementation (not added now); HEIC excluded | **OWNER APPROVED** |
| R6 | Decimal GB: warning `8_000_000_000`, soft cap `10_000_000_000` bytes | **OWNER APPROVED** |
| R7 | R2 **EU jurisdiction** for the production bucket (not a location hint); bucket names proposed until 14B.2 | **OWNER APPROVED** |
| R8 | Display 2048 / thumbnail 480, never upscale, JPEG, sRGB, metadata stripped, alpha on white `#FFFFFF`; not yet performance-proven | **OWNER APPROVED (initial defaults)** |
| R9 | Isolated drill; never delete real production objects; DB + OCI media restore + manifest/integrity + app readability before uploads | **OWNER APPROVED** |

Also OWNER APPROVED in the closure: `PHOTO_MAX_UPLOAD_BYTES=25_000_000`; maximum concurrent image-processing
operations = 1.

**Still PROPOSED / NOT YET OWNER APPROVED** (must not become architecture constants silently):
`PHOTO_TEMP_STALE_AFTER_SECONDS=86400`, `PHOTO_PROCESSING_WAIT_SECONDS=30`, display JPEG quality (85), thumbnail JPEG
quality (80), exact Caddy multipart-overhead allowance, Cache-Control / delivery caching policy (14C).

> **Update (14B.3 closure, 2026-09-28):** stale age 86400 s, processing wait 30 s and JPEG qualities 85/80 are now
> **OWNER APPROVED initial production defaults** after the ARM64 benchmark (§23.13). The Caddy multipart allowance and
> the Cache-Control / delivery caching policy remain PROPOSED for 14C.

---

## 19. Revised 14B execution sequence (within the approved 14A boundaries)

| Step | Scope | Non-scope | Migration | PASS | Gate |
|---|---|---|---|---|---|
| 14B.1 | this audit/plan | code | no | owner review | **COMPLETE / OWNER ACCEPTED** |
| 14B.2 | owner creates EU-jurisdiction R2 prod/dev buckets + tokens (§13); dev smoke | code, production env | no | smoke results recorded (no secrets) | **COMPLETE / OWNER ACCEPTED** — production bucket + token only; connectivity smoke moved after 14B.3 (§22) |
| 14B.3 | boto3 + Pillow (pinned; `python-multipart` only when the upload route is built in 14C) + config/validation + lifespan age-based temp sweep + `MediaStorage` port/S3/in-memory/disabled + key scheme + image pipeline + tests + **ARM64 benchmark (§5.3)** | endpoints, DB, Caddy | no | §15 tests, full regressions, dev-bucket smoke, benchmark recorded | **COMPLETE / OWNER ACCEPTED** — ARM64 benchmark recorded (§23.12); R2 connectivity smoke **not yet performed** (after secret injection, §22.4) |
| 14B.4 | `photo_assets` migration + model + read-only integrity-check command + runbook media backup/restore draft + placeholders in `.env.production.example`/compose | upload API, state-machine endpoint, Caddy | **yes** (`photo_assets`) | PG upgrade/downgrade/upgrade on scratch DB; command tests | **COMPLETE / OWNER ACCEPTED** — commit `e57e037`; owner-run scratch PostgreSQL 16 up/down/up PASS (§24.8) |
| 14B.5 | verification + commit; production deploy with uploads **off** | enabling uploads | — | health OK, app unchanged | **COMPLETE / OWNER VERIFIED** — production `e57e037` / DB `0031_photo_assets`, media disabled, uploads off (§25) |
| 14B.6 | R2 connectivity & credential readiness: owner injects the existing production R2 credentials; controlled smoke test of PUT/HEAD/GET/presigned GET, private/unsigned denial, write-once conflict; uploads stay off (§26) | upload endpoint, user uploads, Oracle backup/restore (14D) | no | smoke results recorded without secrets | **NOT STARTED** — owner approval required |
| 14B.H | HEIC spike | enabling HEIC | no | measured results | owner approval |

The upload state-machine logic and endpoints, the multipart upload route with its guards (R3), the Caddy limit and the cache policy stay in
**14C**; the Oracle backup job, drill and final runbook stay in **14D**. 14C–14K are otherwise unchanged.

## 20. Not changed by 14B.1

No runtime code, migration, dependency, Docker/Caddy/nginx file, `.env*` file, Cloudflare or Oracle resource or setting.
Production runtime remains Stage 13 (`7b5aaf0`), DB `0030_surface_work_executions`.

## 21. Implementation gates (reaffirmed)

- Stage 14B.1 creates no runtime functionality.
- Stage 14B.2 is the manual Cloudflare R2 setup, performed by the owner.
- Stage 14B.3 implements the media infrastructure foundation.
- Real production photo uploads remain **OFF**: `PHOTO_UPLOADS_ENABLED` stays `false` in production until the Stage 14D
  backup/restore gate has passed **and** the owner explicitly approves enabling uploads.

---

## 22. Stage 14B.2 — manual Cloudflare R2 setup (completion record)

- **Date**: 2026-09-28
- **Status**: **Stage 14B.2 — COMPLETE / OWNER ACCEPTED.** Documentation-only record of infrastructure the owner
  created manually in the Cloudflare dashboard. No runtime code, dependency, migration, Docker/Caddy, `.env*` or
  production change in this sub-stage.

### 22.1 Cloudflare R2 (OWNER VERIFIED MANUAL INFRASTRUCTURE)

| Setting | Value |
|---|---|
| Cloudflare R2 | ACTIVE |
| Production bucket | `plan-estimate-media-prod` |
| Jurisdiction | European Union (EU) — data-residency jurisdiction (R7), not a location hint |
| Default storage class | Standard |
| Public Access | Disabled |
| Public Development URL / `r2.dev` | Disabled |
| Custom Domain | None |
| CORS | None |
| Object Lifecycle | Cloudflare default incomplete-multipart-upload abort rule remains enabled; no other rule |
| Event Notifications | Not enabled |
| On Demand Migration | Not enabled |
| Bucket Lock | Not configured (optional complement, evaluated in 14D per §13) |
| Billing | No Workers Paid feature purchased for Stage 14 |

### 22.2 Production application credential (non-secret metadata only)

| Attribute | Value |
|---|---|
| Credential type | Cloudflare R2 Account API Token / S3 credential |
| Purpose | plan-estimate production application media access |
| Permission | Object Read & Write |
| Scope | Specific bucket only: `plan-estimate-media-prod` |
| TTL | Forever |
| Client IP filtering | Not configured — normal S3 connectivity is verified first; IP restriction may be considered later as a separate hardening decision |

The Access Key ID and Secret Access Key are held by the owner in secure storage only. **Neither value is present in
Git, in project documentation, in tests or in any environment file of this repository**, and neither was requested,
printed or handled during 14B.2.

S3 endpoint pattern (EU jurisdiction): `https://<ACCOUNT_ID>.eu.r2.cloudflarestorage.com`. The actual Account ID is
intentionally not recorded in version-controlled documentation; the adapter receives the real endpoint through
configuration (`MEDIA_S3_ENDPOINT_URL`, §11) later.

### 22.3 Differences from the §13 / §19 plan (owner refinement at 14B.2 closure)

- Only the **production** bucket and its application token are recorded as created. A development bucket
  (`plan-estimate-media-dev`) and a dev token were proposed in §13 but are **not** reported as created; this record does
  not claim they exist.
- The connectivity smoke test (§13.9) was **not** performed in 14B.2. It is moved to after 14B.3, per the injection
  order in §22.4.
- The separate read-only backup token (§13.8) belongs to 14D and has not been created.

### 22.4 Secret-injection order (OWNER APPROVED)

1. **14B.2 (done)**: R2 infrastructure and credentials exist, but are **not** injected into the production application.
2. **14B.3**: implement and test the configuration model, `MediaStorage` abstraction, S3 adapter, image-processing
   foundation, disabled-storage behaviour and automated tests.
3. Only after 14B.3 passes owner review: add the required **non-secret** config names to the production templates;
   the owner manually injects the real credentials into the server's `.env.production`; `PHOTO_UPLOADS_ENABLED`
   stays `false`; the explicit R2 connectivity smoke test is performed and its results recorded without secrets.
   *(Clarified 2026-09-28: the template part was delivered in 14B.4; credential injection and the smoke test are
   Stage **14B.6**, §26.)*

This prevents unused production secrets from being installed before the application can validate and use them.

### 22.5 Feature state after 14B.2

| Item | State |
|---|---|
| Media storage code | not implemented yet |
| Production R2 credentials in application env | not configured yet |
| `PHOTO_UPLOADS_ENABLED` | conceptually OFF / not implemented yet |
| Production photo uploads | **OFF** |
| Production media objects written by plan-estimate | none |
| Stage 14 application code deployed | none — production remains `7b5aaf0`, DB `0030_surface_work_executions` |

---

## 23. Stage 14B.3 — MediaStorage + image-processing foundation (implementation record)

- **Date**: 2026-09-28
- **Status**: **COMPLETE / OWNER ACCEPTED** (2026-09-28) after review round 1 (§23.11), the ARM64 benchmark (§23.12)
  and the final owner decisions (§23.13). Library code only: **not deployed**; production media, R2 connectivity and
  photo uploads are **not** verified or enabled.
- **Scope delivered**: library code + tests only. No endpoint, no DB model/migration, no Caddy/Docker/compose/`.env*`
  change, no real credentials, no R2 connection.

### 23.1 Files

| File | Content |
|---|---|
| `backend/app/core/config.py` | media/photo settings (§11 names), cross-field validation, `hide_input_in_errors`, `MediaConfigurationError` |
| `backend/app/domain/exceptions.py` | `MediaStorageError` family (+ `MediaObjectConflict`), `Photo*Error` family with stable codes, `PhotoProcessingBusyError` |
| `backend/app/domain/services/media_storage.py` | `MediaStorage` / `MediaStorageAdmin` protocols, `ObjectInfo`, `DisabledMediaStorage`, `InMemoryMediaStorage`, key/TTL guards |
| `backend/app/core/s3_media_storage.py` | `S3MediaStorage` (boto3), error mapping, `create_media_storage(settings)` |
| `backend/app/domain/photos/keys.py` | the single key builder (R1) |
| `backend/app/domain/photos/image_processing.py` | validation + derivative pipeline, `ImagePipelineConfig`, `ImageProcessor` concurrency guard |
| `backend/app/domain/photos/temp.py` | per-operation workspace, stale sweep |
| `backend/app/domain/photos/__init__.py` | isolated package: imports only Pillow, anyio and `app.domain.exceptions` (not `app.domain.services`, whose `__init__` eagerly loads config/database/models), so tooling can use the pipeline without application startup code |
| `backend/scripts/photo_benchmark.py` | manual benchmark (not part of the test suite) |
| `backend/tests/test_stage14b_*.py` | 135 focused tests (config, storage, keys, image, temp, concurrency, benchmark smoke) |
| `backend/requirements.txt`, `backend/pyproject.toml` | `boto3>=1.40.0,<2.0.0`, `Pillow>=12.0.0,<13.0.0` |

`python-multipart` is **not** added (no upload route in 14B.3). No other dependency was added. Production templates
(`.env.production.example`, `docker-compose.prod.yml`) are **unchanged**: per §19 and §22.4 the non-secret
placeholders are added after owner review of this foundation (14B.4).

### 23.2 Configuration

Names exactly as §11. `MEDIA_S3_ACCESS_KEY_ID` and `MEDIA_S3_SECRET_ACCESS_KEY` are `SecretStr`. Cross-field rules:
`disabled` accepts missing S3 values; `s3` requires non-empty endpoint (https), bucket, region, key id and secret;
`PHOTO_UPLOADS_ENABLED=true` requires `s3`; soft cap ≥ warning; TTL 60–3600. Cross-field failures raise
`MediaConfigurationError`, deliberately not a `ValueError`: pydantic would otherwise wrap it into a `ValidationError`
whose `errors()` carries the raw input, including the secret (found by a test and fixed). An invalid combination still
fails at import/startup; with defaults the application starts unchanged.

### 23.3 Storage port and S3 adapter

- Port: async `put_object(key, source_path, content_type)`, `head_object(key) -> ObjectInfo | None`,
  `presign_get(key, ttl_seconds)`, `download_to(key, path)`; tooling-only `iter_keys(prefix)`. No delete method.
- `S3MediaStorage`: generic S3 (`endpoint_url`, `region_name`, SigV4, path-style addressing, connect 5 s / read 60 s
  timeouts, standard retries 3, checksum calculation/validation `when_required`); boto3 client created lazily; every
  call runs in a worker thread (`anyio.to_thread`); botocore/urllib3 exceptions mapped to
  `MediaStorageUnavailable` / `MediaStorageMisconfigured` / `MediaObjectNotFound` with the cause suppressed (only the
  provider code and HTTP status are kept); credentials excluded from `repr`.
- Write-once: `IfNoneMatch="*"` on PUT. A 412 is accepted as "already stored" only if the existing object matches
  (ETag = MD5 when MD5-shaped, else size); otherwise `MediaObjectConflict`. No head-before-put (race-prone, not a
  guarantee). Whether R2 honours the header through boto3 is **not assumed**: it is part of the post-review smoke test;
  `conditional_put=False` disables the guard if needed.
- Presigned GET is local signing (no network); URLs carry `X-Amz-Expires` = requested TTL. As with any SigV4
  presigned URL, the URL contains the Access Key **ID** in `X-Amz-Credential`. The Access Key ID is an identifier, not
  the secret credential, so this is **not** a secret leak (OWNER APPROVED classification); the Secret Access Key is
  never exposed. Presigned URL query strings are not logged by the adapter and must not be logged unnecessarily by
  later callers (14C).

### 23.4 Keys

`build_photo_object_keys(asset_id: UUID, validated_format: PhotoFormat)` accepts only a UUIDv4 instance and the
decoded format; no filename/MIME/label parameter exists. Output exactly as §9.

### 23.5 Image pipeline

`process_image_file(source, workspace, config) -> ProcessedImage`: size check (≤ 25 000 000 bytes) → bounded SHA-256
over the exact bytes → `Image.open` restricted to JPEG/PNG/WebP (anything else, incl. HEIC/HEIF, GIF, TIFF, BMP, SVG,
PDF, text → `PHOTO_UNSUPPORTED_FORMAT`) → header pixel check (≤ `PHOTO_MAX_DECODED_PIXELS`, edge ≤ 12 000) before
decoding → animated PNG/WebP rejected → full decode (truncated/corrupt → `PHOTO_INVALID_IMAGE`) → EXIF orientation on
the decoded copy → ICC → sRGB → alpha flattened on `#FFFFFF` → display (2048) and thumbnail (480) JPEG, never
upscaled, all metadata stripped. The source file is never written. Pillow's global `MAX_IMAGE_PIXELS` is untouched;
Pillow's `DecompressionBombError` maps to `PHOTO_TOO_MANY_PIXELS`. Phone JPEGs that Pillow reports as MPO are accepted
as JPEG (first frame; the original stays byte-identical) — see §23.11 for the approved rationale.

Returned metadata: format, extension, original content type, byte size, sha256, stored and oriented dimensions, EXIF
orientation, `captured_at` (EXIF DateTimeOriginal, camera-local, no timezone), derivative path/dimensions/byte
size/content type. Nothing is persisted.

### 23.6 Temporary files

`photo_workspace(PHOTO_TEMP_DIR)` creates a `pe-photo-*` directory (base dir 0700, must be absolute, not a symlink and
not a filesystem root) and removes it in `finally`. `cleanup_stale_photo_temp(dir, older_than_seconds)` deletes only
direct `pe-photo-*` entries older than the threshold, never follows symlinks (prefixed symlinks are skipped), never
touches unprefixed entries and reports per-entry errors. It is a standalone utility, **not yet wired** to startup or
uploads (the 14C upload flow calls it).

### 23.7 Concurrency

`ImageProcessor.process` holds one slot (`MAX_CONCURRENT_PROCESSING = 1`, OWNER APPROVED) across the worker-thread run
(cancellation cannot release it early); waiting longer than `PHOTO_PROCESSING_WAIT_SECONDS` raises
`PhotoProcessingBusyError` (`PHOTO_PROCESSING_BUSY`, retryable). No other concurrency value exists.

### 23.8 Tunable defaults

`PHOTO_TEMP_STALE_AFTER_SECONDS=86400` and `PHOTO_PROCESSING_WAIT_SECONDS=30` (configurable settings);
`DEFAULT_DISPLAY_JPEG_QUALITY=85` and `DEFAULT_THUMBNAIL_JPEG_QUALITY=80` (named defaults, overridable through
`ImagePipelineConfig`). PROPOSED during implementation, **OWNER APPROVED** as initial production defaults at closure
(§23.13). The other §18 items (Caddy allowance, Cache-Control) remain PROPOSED for 14C.

### 23.9 Benchmark

`python scripts/photo_benchmark.py [--cases …] [--input FILE …] [--json] [--scale F]`: synthetic inputs are generated
into a temp dir (no fixtures in Git); one subprocess per case; peak RSS via `/proc/self/status` VmHWM on Linux
(`ru_maxrss` elsewhere). Development-machine run (**x86_64, 4 CPUs, Python 3.14.7, Pillow 12.3.0 — NOT
production-equivalent**):

| Case | Source | Source MB | Time s | Baseline MB | Peak MB | Display | Thumb |
|---|---|---|---|---|---|---|---|
| jpeg_12mp | 4000×3000 JPEG | 1.60 | 0.92 | 75 | 203 | 2048×1536, 449 KB | 480×360, 25 KB |
| jpeg_48mp | 8000×6000 JPEG | 6.39 | 2.45 | 75 | 502 | 2048×1536, 614 KB | 480×360, 15 KB |
| png_alpha | 4000×3000 PNG RGBA | 8.25 | 1.54 | 75 | 227 | 2048×1536, 310 KB | 480×360, 15 KB |
| webp_12mp | 4000×3000 WebP | 0.87 | 1.20 | 78 | 300 | 2048×1536, 423 KB | 480×360, 24 KB |
| near_60mp | 10000×5990 JPEG | 7.90 | 2.93 | 75 | 576 | 2048×1227, 509 KB | 480×288, 10 KB |
| exif_rotated | 4000×3000 JPEG, orientation 6 | 1.60 | 0.87 | 75 | 203 | 1536×2048, 448 KB | 360×480, 25 KB |

Synthetic inputs are smoother than real photos (smaller encoded sizes). The §5.3 ARM64 requirement is met by the
production-hardware run in §23.12.

### 23.10 Verification

Focused tests 135/135 PASS; full backend suite PASS (final numbers in §23.13); ruff (E,F,W,B,UP) and mypy clean on the new modules (run ad hoc
via `uvx`, not added to the project). Tests need no network (botocore `Stubber`, no moto).

### 23.11 Owner review round 1 (2026-09-28)

| Topic | Decision |
|---|---|
| `MediaObjectConflict` | **OWNER APPROVED** as a distinct error (integrity/conflict, not unavailable/misconfigured/missing/disabled); the existing object is never overwritten (§8) |
| HTTPS-only `MEDIA_S3_ENDPOINT_URL` | **OWNER APPROVED**; no HTTP escape hatch; R2 and future OCI endpoints use HTTPS; tests mock the SDK |
| Access Key ID | **OWNER APPROVED classification**: identifier, operationally sensitive, not a secret; appears in SigV4 presigned URLs by design. Secret Access Key handling unchanged (§11, §23.3) |
| MPO phone JPEG | **OWNER APPROVED** compatibility path (below) |
| Stale age 86400 s, wait 30 s, JPEG quality 85/80 | **Still PROPOSED** — awaiting the ARM64 benchmark review; not changed |

**MPO compatibility path.** Many phone cameras write JPEG files with an embedded second image (depth map or preview)
using the CIPA Multi-Picture Format; Pillow reports such files as `MPO`. The file is a standard JPEG whose first image
is the photo. Rules: only frame 0 is validated and used for derivatives; the canonical format is `JPEG`, extension
`.jpg`, content type `image/jpeg`; no MPO domain format exists; the canonical original stays byte-for-byte unchanged;
derivatives are single-frame JPEGs without MPO metadata; animated PNG/WebP remain rejected. Covered by tests.

**Code changes in round 1.** The three pure photo modules moved from `app/domain/services/` to the isolated package
`app/domain/photos/` (`keys.py`, `image_processing.py`, `temp.py`), because importing anything under
`app.domain.services` runs its `__init__`, which loads `auth_service` → config (`.env`), database engine and all ORM
models. The benchmark was hardened for a shared production VM (§23.12). Tests added: MPO first frame, benchmark import
isolation, sequential single-input execution, memory guard, scale envelope.

### 23.12 ARM64 benchmark (owner-approved manual run — DONE 2026-09-28)

Target: the existing Oracle VM (Ubuntu 24.04, ARM64, VM.Standard.A1.Flex, 1 OCPU, 6 GB), **outside** the serving
containers. Planned as a temporary virtualenv; the owner ran it in an **isolated temporary ARM64 Docker container**
(the approved fallback): Python 3.12.14, 1 CPU, `nice +10`, 2 GiB memory limit, network disabled. Not a deployment:
no production container restarted or modified, no database operation, no R2 credential or connection, production
checkout unchanged.

Benchmark safety properties (verified in code and tests): parent imports only the stdlib; children import only
Pillow, anyio and `app.domain.photos` (test asserts no `app.core`, `app.models`, `app.api`, `app.domain.services`,
SQLAlchemy, asyncpg, boto3/botocore, httpx, FastAPI, pydantic-settings); no network; no credentials; strictly
sequential; per case one subprocess generates the input and a second processes it; the input is deleted before the
next case, so at most one synthetic image (≤ 60 MP, `--scale` may only shrink) exists at a time and the parent never
holds image data; MemAvailable guard (default ≥ 1536 MB before each case, otherwise remaining cases are skipped);
children run at `nice +10`; one `pe-photo-bench-*` temp directory, removed at the end.

Results (owner-reported, aarch64; production services running throughout; MemAvailable 4965.8 MB before,
4868.2 MB after, host `free -h` ≈ 4.9 GiB available after; **0 failures**):

| Case | Source | Source bytes | Time s | Baseline MB | Peak RSS MB | Display | Thumbnail |
|---|---|---|---|---|---|---|---|
| jpeg_12mp | 4000×3000 JPEG | 1,602,986 | 0.456 | 29.6 | 157.3 | 2048×1536, 449,124 B | 480×360, 25,409 B |
| jpeg_48mp | 8000×6000 JPEG | 6,395,883 | 1.115 | 26.9 | 453.5 | 2048×1536, 614,979 B | 480×360, 15,539 B |
| png_alpha | 4000×3000 PNG RGBA | 8,248,499 | 0.717 | 27.4 | 180.6 | 2048×1536, 310,984 B | 480×360, 15,749 B |
| webp_12mp | 4000×3000 WebP | 857,960 | 0.584 | 28.7 | 253.0 | 2048×1536, 423,798 B | 480×360, 24,884 B |
| near_60mp | 10000×5990 JPEG | 7,907,382 | 1.295 | 26.9 | 541.8 | 2048×1227, 509,423 B | 480×288, 10,489 B |
| exif_rotated | 4000×3000 JPEG, orientation 6 | 1,603,022 | 0.423 | 27.6 | 155.5 | 1536×2048, 449,051 B | 360×480, 25,547 B |

Post-benchmark production check: all production containers running; backend healthy; postgres healthy; public
`/api/health` → `{"status":"ok"}`; no production checkout changes.

Interpretation (recorded with the owner decision): highest peak RSS **541.8 MB** and longest duration **1.295 s**, both
for the near-60 MP JPEG. On the current 1 OCPU / 6 GB VM this supports keeping the 60 MP decoded limit, processing
concurrency 1, the 30 s processing wait, and no worker/Celery architecture for Stage 14 v1. The benchmark measures one
operation at a time and must **not** be extrapolated to unlimited concurrent processing: the concurrency = 1 guard
remains required.

### 23.13 Final owner decisions (14B.3 closure, 2026-09-28)

**OWNER APPROVED initial production defaults** for Stage 14 (configuration values where appropriate, not permanent
domain invariants; JPEG quality may be tuned later on real construction-site photos without a schema/domain change):

| Setting / policy | Value |
|---|---|
| `PHOTO_MAX_UPLOAD_BYTES` | `25_000_000` |
| `PHOTO_MAX_DECODED_PIXELS` | `60_000_000` |
| image-processing concurrency | `1` |
| `PHOTO_PROCESSING_WAIT_SECONDS` | `30` |
| `PHOTO_TEMP_STALE_AFTER_SECONDS` | `86400` |
| display longest edge | 2048 px |
| thumbnail longest edge | 480 px |
| display JPEG quality | 85 |
| thumbnail JPEG quality | 80 |
| transparency background | `#FFFFFF` |

Code aligned: the "PROPOSED" markers were replaced (`DEFAULT_DISPLAY_JPEG_QUALITY` / `DEFAULT_THUMBNAIL_JPEG_QUALITY`);
values unchanged. Not verified by 14B.3 and not claimed: production media, R2 connectivity, photo uploads. No Stage 14
application runtime is deployed.

---

## 24. Stage 14B.4 — PhotoAsset persistence, integrity tooling, production templates (implementation record)

- **Date**: 2026-09-28
- **Status**: **COMPLETE / OWNER ACCEPTED** — committed and pushed as `e57e037`; deployed to production in 14B.5 (§25).
  The owner-run scratch PostgreSQL 16 verification PASSED (§24.8). R2 connectivity is not verified (14B.6) and backup /
  restore is **not** ready (that gate is 14D).
- **Owner decisions (schema reconciliation)**: `project_id` kept per 14A §15.1; `id` = client upload UUID (no separate
  `upload_id` column); `display_byte_size` + `thumbnail_byte_size` added; `captured_at` is TIMESTAMP WITHOUT TIME ZONE;
  `storage_backend` renamed to `storage_name` (logical store). The 14A §15.1 note records the same clarification.

### 24.1 Final `photo_assets` schema (migration `0031_photo_assets`, down_revision `0030_surface_work_executions`)

| Column | Type | Rule |
|---|---|---|
| `id` | UUID PK | client upload UUIDv4 = idempotency identity = storage-key `{asset_uuid}` |
| `owner_id` | UUID NOT NULL | FK `users.id` ON DELETE RESTRICT |
| `project_id` | UUID NOT NULL | FK `projects.id` ON DELETE RESTRICT; creation verifies the project belongs to the owner |
| `status` | enum `photoassetstatus` (`PENDING`, `READY`, `FAILED`) | NOT NULL |
| `storage_name` | VARCHAR(40) NOT NULL | CHECK `length(trim(storage_name)) > 0` |
| `storage_key_original` / `_display` / `_thumbnail` | VARCHAR(255) NOT NULL | UNIQUE each; CHECK non-empty; write-once |
| `content_type` | enum `photocontenttype` (`image/jpeg`, `image/png`, `image/webp`) | NOT NULL, decoded format |
| `byte_size` | BIGINT NOT NULL | original object size, CHECK > 0 |
| `display_byte_size` | BIGINT NOT NULL | CHECK > 0 |
| `thumbnail_byte_size` | BIGINT NOT NULL | CHECK > 0 |
| `width`, `height` | INTEGER NOT NULL | after EXIF orientation, CHECK > 0 |
| `sha256` | CHAR(64) NOT NULL | CHECK `length = 64 AND = lower(...)` (portable) + PostgreSQL `~ '^[0-9a-f]{64}$'`; not unique |
| `original_filename` | VARCHAR(255) NULL | display only; sanitized (last path segment, no control characters) |
| `captured_at` | TIMESTAMP WITHOUT TIME ZONE NULL | camera-local capture time, timezone unknown, never converted |
| `uploaded_at`, `created_at`, `updated_at` | TIMESTAMPTZ NOT NULL | server UTC (`DEFAULT now()` in DDL, UTC defaults in the model) |
| `archived_at` | TIMESTAMPTZ NULL | soft archive |

Indexes: `uq_photo_assets_storage_key_original|display|thumbnail` (unique), `ix_photo_assets_project_status_archived`
(`project_id, status, archived_at`), `ix_photo_assets_status_created` (`status, created_at`), `ix_photo_assets_owner_status`
(`owner_id, status`). Storage bytes per asset = `byte_size + display_byte_size + thumbnail_byte_size` (derived; no cached
total, no quota table). No attachment/context columns, no URL, no credential. Downgrade drops only the table, its
indexes and the two enum types.

**Timestamp semantics.** `captured_at` is the EXIF DateTimeOriginal wall-clock time exactly as the camera wrote it; it
carries no offset, and none is invented (the persistence layer rejects a timezone-aware value). All server-generated
timestamps are timezone-aware UTC.

**`storage_name` semantics.** The logical storage identity from `MEDIA_STORAGE_NAME` (e.g. `r2-primary`) used later to
resolve an asset to its configured store. It is never the adapter type (`MEDIA_STORAGE_BACKEND=s3`): several logical
stores (primary, backup, restore drill) may share the same S3-compatible adapter.

**State semantics.** Every row carries complete media metadata (NOT NULL in every status): decode, validation,
derivatives and SHA-256 precede the PENDING insert (14A §8). PENDING = processed locally, durable storage not yet
finalized; READY = all three objects stored; FAILED = storage finalization failed. Allowed transitions: PENDING → READY,
PENDING → FAILED, FAILED → PENDING (retry with the same id); READY is terminal. Object existence cannot be enforced by
the DB; the integrity check reports it.

### 24.2 Persistence boundary

`app/models/photo_asset.py` (`PhotoAsset`, `PhotoAssetStatus`, `PhotoContentType`) and
`app/domain/services/photo_asset_service.py` (`PhotoAssetService`): `create_pending` (verifies project ownership,
builds keys only via `build_photo_object_keys(asset_id, processed.format)`, validates metadata, refuses an existing id
without revealing its owner), `get_for_owner`, `transition` (state machine), `list_for_integrity` (all owners, optional
`storage_name` filter; returns read-only `PhotoAssetSnapshot`s). No object-storage call and no adapter coupling in the
persistence layer; the upload workflow is 14C. New exceptions: `PhotoAssetNotFoundError`,
`PhotoAssetAlreadyExistsError`, `PhotoAssetStateError`, `PhotoAssetValidationError`.

### 24.3 Read-only integrity check

Engine `app/domain/services/media_integrity.py` (provider-neutral, uses only `iter_keys`, `head_object` and — with
`--verify-sha256` — `download_to` into a removed temp workspace); CLI `backend/scripts/media_integrity_check.py`
(PostgreSQL session in a `READ ONLY` transaction, rolled back). Never writes, deletes, repairs, changes states,
presigns or prints credentials. `MEDIA_STORAGE_BACKEND=disabled` → exit 2 ("state unknown, not assumed empty"); storage
unavailable/misconfigured → exit 2 ("result incomplete"); integrity errors → exit 1; warnings fail only with
`--strict`. `--expect-storage-name` lets a later run check an independent backup/drill target against the rows of the
logical store it mirrors.

| Classification | Severity | Meaning |
|---|---|---|
| (expected present) | — | READY object present with the persisted size (counted) |
| `MISSING_ORIGINAL` | ERROR | READY original missing — evidence loss |
| `MISSING_DERIVATIVE` | ERROR | READY display/thumbnail missing — regenerable from the original |
| `SIZE_MISMATCH` | ERROR | stored size ≠ persisted size (each of the three objects) |
| `CHECKSUM_MISMATCH` | ERROR | READY original sha256 ≠ persisted (only with `--verify-sha256`) |
| `PENDING_INCOMPLETE` | INFO / WARNING if older than `--pending-stale-after-seconds` (86400) | upload in progress or abandoned; its objects are not orphans |
| `FAILED_RELATED` | INFO / WARNING if objects exist | objects of a FAILED asset |
| `ORPHAN_CANDIDATE` | WARNING | key in the known layout with no asset row — a candidate only, never "safe to delete" |
| `UNKNOWN_KEY` | WARNING | under `photos/v1/` but an unrecognized layout |
| `OTHER_STORAGE` | INFO | rows of another logical store, not checked against this target |

### 24.4 Production templates and compose

`.env.production.example`: all 17 media/photo settings with safe values — `MEDIA_STORAGE_BACKEND=disabled`,
`PHOTO_UPLOADS_ENABLED=false`, empty endpoint/bucket/key id/secret, endpoint pattern only as a comment
(`https://<ACCOUNT_ID>.eu.r2.cloudflarestorage.com`), approved numeric defaults. `docker-compose.prod.yml`: the same 17
names wired into the **backend service only** as `${NAME:-safe-default}`, so a server `.env.production` without media
entries keeps media disabled. No new port, service, volume or build arg; frontend, Caddy and Postgres receive nothing.
The real `.env.production` is untouched.

### 24.5 Runbook

`docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md` §72 — **DRAFT** media backup/restore: R2 (EU, Standard) primary, Oracle
Object Storage independent backup (R2 versioning is not the backup), flow R2 → export/copy → Oracle → integrity
verification → isolated restore target → restore verification, integrity-command usage, restore-drill rules (isolated
bucket/prefix, never delete a real production object, inventory + sha256 comparison, primary untouched). No backup or
restore readiness claimed; Oracle is not configured.

### 24.6 Tests (focused)

`test_stage14b4_photo_asset.py` (49), `test_stage14b4_migration.py` (4: revision chain / single head; real
`upgrade`/`downgrade`/`upgrade` on SQLite compared with model metadata; existing tables untouched; rendered PostgreSQL
DDL), `test_stage14b4_integrity.py` (16), `test_stage14b4_production_templates.py` (4).

### 24.7 Verification done locally

Focused 14B.4 tests and the full backend suite pass (counts in the report); ruff (E,F,W,B,UP) and mypy clean on the new
modules; offline `alembic upgrade 0030:0031 --sql` / `downgrade --sql` rendered and asserted; `alembic heads` =
`0031_photo_assets` (single head). SQLite is **not** the final migration proof.

### 24.7a Owner decisions (14B.4 review, 2026-09-28)

| Topic | Decision |
|---|---|
| Index `ix_photo_assets_owner_status` (`owner_id, status`) | **OWNER APPROVED** — owner-scoped media accounting/querying |
| Integrity stale-PENDING default `--pending-stale-after-seconds=86400` | **OWNER APPROVED** — operational integrity-tool default, not a PhotoAsset domain invariant |
| `ORPHAN_CANDIDATE` / `UNKNOWN_KEY` severity | **OWNER APPROVED** = WARNING; default exit 0 for warnings; `--strict` makes warnings fail; nothing orphan/unknown is ever automatically deletable |
| `--verify-sha256` | **OWNER APPROVED** as opt-in (downloads READY originals); normal runs use inventory + HEAD metadata only |

### 24.8 Owner-run PostgreSQL 16 verification — PASS (2026-09-28)

Run manually by the owner on the Oracle ARM64 VM in a fully isolated scratch environment: standalone
`postgres:16-alpine` container `pe-14b4-scratch-pg`, dedicated network `pe-14b4-scratch-net`, data in tmpfs, no
published port, no production volume or credentials, not part of the `plan-estimate` Compose project. The production
database was **not** migrated and **not** used.

| Check | Result |
|---|---|
| Full chain 0001 → `0031_photo_assets` on an empty database | PASS — `0031_photo_assets (head)` |
| Probes (rolled-back transaction) | PASS: valid PENDING row accepted; non-hex sha256 rejected (regex CHECK); invalid status rejected (enum); `image/gif` rejected (enum); zero `display_byte_size` rejected; blank `storage_name` rejected; duplicate original key rejected; project delete restricted |
| Timestamp types | `captured_at` = timestamp without time zone; `uploaded_at`, `created_at`, `updated_at`, `archived_at` = timestamp with time zone |
| Downgrade 0031 → 0030 | PASS — `photo_assets`, `photoassetstatus`, `photocontenttype` absent; current `0030_surface_work_executions` |
| Re-upgrade 0030 → 0031 | PASS — current and heads `0031_photo_assets (head)`; table present; 11 constraints (8 CHECK + PK + 2 FK; key uniqueness is via unique indexes) |
| Production isolation | PASS — all production containers running; backend and Postgres healthy; `/api/health` → `{"status":"ok"}`; production checkout clean |
| Cleanup | scratch container, network, workspace, archive and probe SQL removed; nothing in production removed or modified |

The real PostgreSQL 16 verification gate for 14B.4 is **PASSED** (owner decision).

### 24.9 Scratch verification procedure (reference)

Temporary standalone `postgres:16-alpine` container on its own network with tmpfs data, no published port, no
production credentials, compose project, volume or network; migration code transferred as a tarball (never via a
production deployment); executed manually by the owner, never by Claude. Results in §24.8.

---

## 25. Stage 14B.5 — production deployment with uploads off (owner-verified record)

- **Date**: 2026-09-28
- **Status**: **COMPLETE / OWNER VERIFIED.** Deployed manually by the owner following the 14B.5 readiness audit
  (runbook §69b order: backup → fast-forward → build → owner stop → recreate backend only).
- **Deployed**: `e57e037d42815fa5e837e7629d0cb3d74c53ad76` (`feat(stage-14): add photo asset persistence and integrity
  tooling`), backend only. Frontend unchanged since `7b5aaf0`, so the frontend, Caddy and Postgres containers were not
  recreated.

### 25.1 Pre-deployment safety

| Check | Result |
|---|---|
| Backend / PostgreSQL / public `/api/health` | healthy / healthy / `{"status":"ok"}` |
| Database revision | `0030_surface_work_executions` |
| `.env.production` media entries | none (`MEDIA_*` / `PHOTO_*` absent) |
| Production working tree | clean |
| Rollback state | previous head `7b5aaf0b782e99df9e96fa63873892dd88631cad`; previous backend image `sha256:4ca75f47452991bdc6f764bdb44ba8ae5476872d706557bf21285efff1273753`, tagged `plan-estimate-backend:rollback-pre-14b5` |
| Database backup | `db-pre-14b5-0030-20260928T143642Z.sql.gz` in `~/backups/plan-estimate/`: non-empty, gzip integrity PASS, contains `0030_surface_work_executions`; SHA256 `543fa2b5c36e7fd2f3c8142499ed5d17a2d626132c4325325a14764bad10ff7e` (saved and recalculated values match) |

### 25.2 Deployment and verification

| Check | Result |
|---|---|
| Migration | entrypoint applied `0030_surface_work_executions → 0031_photo_assets` before uvicorn started |
| Alembic | current `0031_photo_assets (head)`; heads `0031_photo_assets (head)`; `alembic_version` = `0031_photo_assets` |
| `photo_assets` rows | 0 |
| Health | internal and public `{"status":"ok"}`; backend healthy; PostgreSQL healthy |
| Unchanged containers | frontend and Caddy not recreated; PostgreSQL not recreated (`StartedAt` unchanged: `2026-09-14T14:12:48.587182093Z`) |
| Media configuration | `MEDIA_STORAGE_BACKEND=disabled`, `PHOTO_UPLOADS_ENABLED=False`, `MEDIA_STORAGE_NAME=r2-primary`; endpoint / bucket / access key id / secret all **not set** |
| Upload safety | no photo/media/upload routes; image check `multipart: None None` (no upload parser) |
| Integrity tool | `python scripts/media_integrity_check.py` → "cannot run: MEDIA_STORAGE_BACKEND=disabled. Storage state is unknown (not assumed empty)", exit 2 (expected safe behaviour) |
| Images | running = latest backend image `sha256:454e3b2f5673b90fb9be28cf5146c9841c90ccb4689c2969fd406815ae540dfe`; rollback image `sha256:4ca75f47…3753` retained |
| Git | production checkout `e57e037d42815fa5e837e7629d0cb3d74c53ad76`, clean |
| Telegram Menu Button | intentionally **not** changed (backend-only deployment, frontend unchanged; no cache-busting needed) |

### 25.3 State after 14B.5

- Production runtime `e57e037`, database `0031_photo_assets` (empty `photo_assets` table).
- Media storage **disabled**; photo uploads **OFF**; no upload endpoint or parser exists.
- No R2 credential configured or used; **R2 connectivity NOT tested**; no media object created.
- Backup / restore readiness is **not** claimed (14D).
- Rollback note (from the readiness audit): the previous image cannot start against 0031 (its entrypoint's
  `alembic upgrade head` fails on the unknown revision), so an application rollback requires
  `alembic downgrade 0030_surface_work_executions` with the current image first (safe while `photo_assets` is empty),
  then the `rollback-pre-14b5` image.

---

## 26. Stage 14B.6 — R2 Connectivity & Credential Readiness (roadmap clarification, NOT STARTED)

**Why a numbered sub-stage:** §22.4 step 3 (credential injection + explicit R2 connectivity smoke test, uploads kept
off) and the smoke test named in 14A §19 / the §19 14B.3 row were approved but never assigned to a numbered
sub-stage; 14B.5 deliberately excluded them. 14B.6 assigns them within Stage 14B. It does not renumber or reorder any
existing sub-stage and does not change 14C–14K. Defined by the owner on 2026-09-28; starts only with explicit owner
approval.

**Scope:**
- the owner manually injects the already-created production R2 credentials (14B.2 §22.2) into the server's
  `.env.production` — never into Git, docs, tests or chat;
- `PHOTO_UPLOADS_ENABLED` stays `false`;
- storage is switched/tested only under an explicitly controlled smoke-test procedure;
- verify the media storage contract against the real bucket: authenticated PUT / HEAD / GET (download) and presigned
  GET;
- verify unsigned/private access remains denied (and an expired presigned URL is denied);
- verify write-once conflict behaviour (conditional PUT / `MediaObjectConflict`, §23.3);
- results recorded without secrets.

**Explicit non-scope:** no application upload endpoint, no user photo uploads, no Oracle Object Storage backup or
restore (those remain **14D**: independent Oracle backup, restore drill, media-readiness gate).

- **Status:** Stage 14B.1 — COMPLETE / OWNER ACCEPTED. Stage 14B.2 — COMPLETE / OWNER ACCEPTED. Stage 14B.3 —
  COMPLETE / OWNER ACCEPTED. Stage 14B.4 — COMPLETE / OWNER ACCEPTED (§24). Stage 14B.5 — COMPLETE / OWNER VERIFIED
  (§25). Stage 14B.6 — NOT STARTED (§26). Stage 14B — IN PROGRESS. Stage 14 — IN PROGRESS.
