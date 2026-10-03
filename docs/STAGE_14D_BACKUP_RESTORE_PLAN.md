# Stage 14D — Backup / Restore Drill & Production Media-Readiness Gate (plan and contract)

> **Status:** 14D.1 architecture — **OWNER APPROVED** (2026-10-02, with the mandatory corrections A–D below
> incorporated). 14D.2A (snapshot primitive, §7.1) — COMPLETE / OWNER ACCEPTED (owner runs, 9/9, re-proven after hardening).
> 14D.2B (encrypted DB artifact primitive, §9.1) — COMPLETE / OWNER ACCEPTED (real-age round-trip proven, age 1.3.2). Rest of 14D.2 and 14D.3–14D.7 — NOT STARTED. Apart from the §7.1 and §9.1 primitives, nothing in this
> document is implemented, configured or
> verified yet: no backup tooling, no cloud resources, no credentials, no schedule. Executable procedures stay
> **DRAFT** until the sub-stage that verifies them.
>
> Builds on: `docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md` §13 (consistency model, OD-3),
> `docs/STAGE_14B_MEDIA_INFRASTRUCTURE_PLAN.md` §14 (Oracle concept) and §17 (R9 gate),
> `docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md` §72 (draft runbook). Where this document is more specific, it governs.
>
> Hard rule (unchanged): `PHOTO_UPLOADS_ENABLED` stays `false` in production until Stage 14D passes and the owner
> explicitly approves enablement, which belongs to **Stage 14E**.

---

## 1. Starting point (14D.1 audit, verified from the repository)

- Production (per `docs/development-progress.md`): backend image `sha256:33bb27b7…`, DB `0032_photo_attachments`,
  primary media Cloudflare R2 bucket `plan-estimate-media-prod` (logical store `r2-primary`),
  `PHOTO_UPLOADS_ENABLED=false`, `photo_assets` 0, `photo_attachments` 0. No production upload has ever been enabled.
- Existing capabilities: `MediaStorage` / `MediaStorageAdmin` port (`put_object` write-once, `head_object` size +
  ETag, `download_to`, `presign_get`, `iter_keys`; **no delete**); S3-compatible adapter (boto3, path-style, SigV4,
  `IfNoneMatch: *` conditional PUT, checksums only when required); in-memory test double; immutable keys
  `photos/v1/{asset_uuid}/original.{jpg|png|webp}`, `display.jpg`, `thumb.jpg`; `PhotoAsset` stores the three keys,
  the three byte sizes and the SHA-256 of the **original only**; read-only integrity checker
  (`scripts/media_integrity_check.py`: existence + size for all three objects of READY assets, optional original
  SHA-256, orphan / unknown-key reporting, exit 0/1/2, works against any store via env overrides and
  `--expect-storage-name`).
- Gaps found:
  1. no backup, manifest, verification or restore tooling;
  2. **database dumps exist only on the production VM** (`~/backups/plan-estimate/`) — not off-host;
  3. **no derivative-regeneration tool** exists (§2);
  4. write-once / overwrite / ETag behaviour of Oracle Object Storage through the S3 adapter is **unverified**
     (Oracle ETags are not MD5, so the adapter's conflict check would degrade to size-only);
  5. configuration supports one store (`MEDIA_S3_*`); tooling needs a source and a target store from its own env file;
  6. no read-only R2 token (the only token is the backend's Object Read & Write token), no Oracle identity, no
     restore credential;
  7. no Oracle buckets, no R2 drill buckets (only `plan-estimate-media-prod` was created in 14B.2);
  8. runbook §72 is a draft.

## 2. What must be backed up (authoritative vs reproducible) — OWNER APPROVED

| State | Authoritative | Reproducible | Backup (v1) |
|---|---|---|---|
| PostgreSQL: `photo_assets` (keys, sizes, original SHA-256, status, `storage_name`) | yes | no | **mandatory**, encrypted, off the VM |
| PostgreSQL: `photo_attachments` (context, category, caption, position, report inclusion, archive) | yes | no | **mandatory** (in the same dump) |
| Original objects | yes (evidence) | no | **mandatory** |
| Display derivatives | treated as authoritative | **not safely in v1** | **mandatory** |
| Thumbnails | treated as authoritative | **not safely in v1** | **mandatory** |
| Object keys | derived from asset id + format, stored in DB | yes | via DB dump + manifest |
| Original SHA-256 | yes (DB) | recomputable from the original | DB dump + manifest |
| Derivative SHA-256 | not stored anywhere today | — | recorded in the manifest at first verified backup |
| Orphan objects (no row) | no | — | not backed up; counted only |
| PENDING / FAILED objects | no (incomplete) | — | not backed up in v1; counted; backed up once READY |

**Derivatives are not classified as safely regenerable in v1.** The repository has no operator tool that rebuilds a
derivative from a stored original. The upload pipeline re-derives derivatives only during an upload resume, from
SHA-verified client retry bytes, and accepts them only if format, dimensions and byte size equal the row (14C
contract); byte-identical output across Pillow / libjpeg versions is not guaranteed and the DB holds no derivative
hash. Therefore all three objects of every READY asset are backed up.

## 3. Independence requirement

"Independent" means all of:
- a **different provider** (Oracle Cloud, not Cloudflare);
- **own buckets** and **own credentials**, not shared with the backend application;
- R2 versioning / Bucket Lock are **never** counted as the backup;
- a restore must be possible with R2 entirely unavailable or objects lost;
- nothing deleted or missing in R2 is ever propagated into the backup.

## 4. Resources (operational configuration, not domain constants)

Region: the tenancy's current Frankfurt EU region, if supported as expected (verified in 14D.3). Bucket names are
provisional and live only in operator env files / runbook — **never hard-coded in application logic**.

| Provider | Bucket (provisional) | Purpose |
|---|---|---|
| Oracle | `plan-estimate-media-backup` | production backup target (versioning on) |
| Oracle | `plan-estimate-media-drill-backup` | drill backup target |
| R2 | `plan-estimate-media-drill-source` | drill source (synthetic fixture only) |
| R2 | `plan-estimate-media-drill-restore` | drill restore target |

A drill never uses a prefix inside the production R2 bucket or the production Oracle backup bucket.

## 5. Backup layout

```
<backup bucket>/
  photos/v1/{asset_uuid}/original.{ext}        same immutable keys as R2
  photos/v1/{asset_uuid}/display.jpg
  photos/v1/{asset_uuid}/thumb.jpg
  db/{run_id}/plan-estimate.sql.gz.age          encrypted DB dump (canonical remote DB artifact)
  runs/{run_id}/manifest.jsonl
  runs/{run_id}/COMPLETE.json                   written last, only when every invariant holds
```

- `run_id` = UTC timestamp + random suffix (e.g. `20261003T081500Z-3f9a1c2e`); a rerun always gets a new `run_id`.
- Object set per run = **full** (every READY asset of the DB snapshot); transfer = **incremental** (an existing
  target object is admitted only per §8, never copied over).
- Copy unit: one object at a time — R2 → bounded temp → hash/verify → Oracle PUT → post-copy verify.

## 6. Manifest v1

JSON Lines. No filenames, captions or other personal data (those exist only inside the encrypted DB dump).

Header:
```json
{"type":"header","manifest_version":1,"run_id":"…","started_at":"…Z","tool_commit":"<git sha>",
 "source":{"storage_name":"r2-primary","bucket":"<source bucket>"},
 "target":{"bucket":"<target bucket>"},
 "db_dump":{"key":"db/<run_id>/plan-estimate.sql.gz.age","encryption":"age","recipients":["age1…"],
            "encrypted_sha256":"…","encrypted_size":0,"alembic_head":"0032_photo_attachments","dumped_at":"…Z"},
 "snapshot":{"method":"exported-snapshot","ready_count":0,"ready_set_sha256":"…"}}
```
Object line (one per required object):
```json
{"type":"object","asset_id":"…","role":"original|display|thumbnail","key":"photos/v1/…","size":0,"sha256":"…",
 "content_type":"image/jpeg","action":"copied|already_present","sha_provenance":"downloaded|inherited:<run_id>",
 "target_etag":"…|null","verified_at":"…Z"}
```
Summary line:
```json
{"type":"summary","ready_assets":0,"objects":0,"bytes":0,"skipped":{"pending":0,"failed":0},
 "source_listing":{"keys":0,"orphan_candidates":0}}
```
`COMPLETE.json`:
```json
{"run_id":"…","manifest_version":1,"manifest_key":"runs/<run_id>/manifest.jsonl","manifest_sha256":"…",
 "objects":0,"bytes":0,"ready_assets":0,"ready_set_sha256":"…","db_dump_encrypted_sha256":"…","completed_at":"…Z"}
```
A run without a `COMPLETE.json` whose `manifest_sha256` equals the stored manifest's SHA-256 is **incomplete by
definition** and is never used as a restore source or as SHA provenance.

## 7. DB / media completeness invariant (correction A — MANDATORY)

The manifest must be **provably complete for the DB backup it is associated with**; a later live READY inventory is
not assumed to represent the dump.

- **Same snapshot.** The tool opens a `REPEATABLE READ, READ ONLY` transaction, calls `pg_export_snapshot()`, reads
  the READY asset set in that transaction, and the DB dump is taken with `pg_dump --snapshot=<id>` while the
  transaction is held open. The dump and the inventory are therefore the same database state. (The backend image has
  no `pg_dump`; the dump runs through the postgres container's own `pg_dump`, so client and server versions match.
  The exact orchestration — host wrapper vs tool-driven — is fixed in 14D.2 and verified on scratch PostgreSQL.)
- **Ready-set digest.** `ready_set_sha256` = SHA-256 over the sorted canonical lines
  `asset_id|key_original|key_display|key_thumbnail|byte_size|display_byte_size|thumbnail_byte_size|sha256` of every
  READY asset in that snapshot; `ready_count` = their number. Both go into the header and `COMPLETE.json`.
  Exact v1 serialization: §7.1.
- **Invariant (checked before `COMPLETE.json` is written):** for every READY asset in the snapshot there are exactly
  three object lines (original, display, thumbnail) with the asset's keys, sizes equal to the row, the original's
  SHA-256 equal to the row, every object admitted per §8; and the digest recomputed from the manifest's object lines
  equals `ready_set_sha256`. Any shortfall → no `COMPLETE.json`, non-zero exit.
- **Independent verification:** `verify` (and every restore drill) decrypts the dump, restores it into scratch
  PostgreSQL, recomputes the ready-set digest from the restored DB and requires equality with the manifest — proving
  the association without trusting the tool that wrote it.
- PENDING / FAILED assets in the snapshot are counted (`skipped`), not backed up; a restored DB containing them is
  reported by the integrity checker as `PENDING_INCOMPLETE` / `FAILED_RELATED` (bounded, detectable).
- Objects uploaded after the snapshot are not part of the run; restoring an older dump against a newer bucket shows
  them as orphan candidates, never deleted (14A §13).

### 7.1 Snapshot primitive and READY-set v1 (Stage 14D.2A — complete, owner accepted)

Implementation: `backend/app/core/pg_snapshot_dump.py` (`snapshot_bound_dump`) and
`backend/app/domain/services/media_backup_ready_set.py` (`ready_set_digest`).

**Exporter lifecycle (exact order):**
1. dedicated asyncpg connection (application name `<tag>-exp`), never a pooled application connection, opened with
   `idle_in_transaction_session_timeout=0` as a session setting (the connection exists only for this snapshot), so a
   non-zero server default cannot end the exporter while pg_dump uses the snapshot;
2. `SHOW server_version_num` and `pg_dump --version` (through the same tool prefix as the dump): the **major versions
   must be equal**, otherwise the run stops before any snapshot exists;
3. `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`; the **first** statement is `SELECT pg_export_snapshot()`, which
   fixes the transaction snapshot; isolation, read-only state and the disabled idle timeout are then asserted (fail
   closed);
4. READY inventory (`SELECT … FROM photo_assets WHERE status = 'READY'`) in the same transaction → `ready_count`,
   `ready_set_sha256`;
5. `pg_dump --format=plain --no-password --snapshot=<id>` with `PGAPPNAME=<tag>-dump`, run where the server-matching
   toolchain lives (production: `docker exec -i <postgres container>`); stdout → `<output>.partial`, created
   exclusively with mode **0600** independent of the umask (the renamed dump keeps 0600);
6. the exporter is released only **after pg_dump has exited**: `ROLLBACK`, then close.

**Lifetime rule (PostgreSQL semantics):** an exported snapshot can be imported only while the exporting transaction
is open; a transaction that already imported it keeps it after the exporter ends. `pg_dump` imports it during its
own setup (each parallel worker would import it again) and that moment is not observable from outside, so the
earliest safe release point the primitive relies on is **pg_dump's exit**. `BEGIN → export → COMMIT/close → later
pg_dump --snapshot` is invalid and is never used.

**Success / failure contract:** the dump is accepted only on exit status 0 **and** the plain-format completion marker
(`-- PostgreSQL database dump complete`) within the last 4 KiB; only then is `<output>.partial` renamed. On a
non-zero exit, a missing marker, a timeout or cancellation: the local process is killed and reaped (no zombie), the
server-side backends tagged `<tag>-dump` are terminated with `pg_terminate_backend` (a killed `docker exec` client
does not stop the process inside the container), the exporter is rolled back and closed, the partial file is
removed, and a typed error (`PgDumpFailedError` / `PgDumpTimeoutError` / `PgDumpVersionMismatchError`, all
`SnapshotDumpError`) propagates; stderr is kept only as a bounded tail. Existing output or partial files are never
overwritten. No credential is logged (the DSN goes only to asyncpg; the tool authenticates through its own
environment, never a password in argv).

**READY-set serialization v1 (byte-exact; refines the 14D.1 line list by a version header):**

```
"plan-estimate/ready-set/v1\n"
+ sorted lines (byte order; the fixed-width asset id leads every line):
  asset_id|key_original|key_display|key_thumbnail|byte_size|display_byte_size|thumbnail_byte_size|sha256\n
```

- `asset_id`: canonical lowercase hyphenated UUID text (Python `str(UUID)`, PostgreSQL `id::text`);
- keys: printable ASCII `0x21–0x7E`, non-empty, never `|`;
- sizes: positive base-10 integers, no sign / padding / leading zeros (`str(int)`, `bigint::text`);
- `sha256`: 64 lowercase hex characters;
- encoding ASCII, separator `|`, terminator `\n`, nothing else;
- `ready_set_sha256` = lowercase hex SHA-256 of the bytes; the empty set is the header alone
  (`sha256("plan-estimate/ready-set/v1\n")`), a fixed digest;
- any non-canonical value or duplicate asset id raises `ReadySetFormatError`; nothing is normalized or skipped.

The same digest is computable in plain SQL (`string_agg(… ORDER BY id::text COLLATE "C")` + `sha256()`), which the
PostgreSQL proof uses as an independent implementation.

**Evidence:** local unit tests (canonical bytes, order independence, per-field sensitivity, rejection rules, exit /
marker / timeout / cancellation / overwrite / child-reaping) pass; the real PostgreSQL proof
(`backend/tests/test_stage14d2a_postgres.py`, opt-in) passed 9/9 in an owner-run disposable `postgres:16-alpine`
container (server and pg_dump 16.15): same-snapshot dump / inventory, concurrent-commit isolation, PostgreSQL's own
rejection of a snapshot after its exporter ended (SQLSTATE 22023), pg_dump failure / timeout / cancellation cleanup
with the exporter alive during the dump, zero-READY digest
`6e2b1178c1af4635f75bd0c77e7cce463e0e7055c120984e99ccf2d5a4922240`, SQL = Python digest, version-mismatch refusal.
After the hardening (0600 private dump file, exporter session `idle_in_transaction_session_timeout=0`) the proof was
re-run by the owner: 9 passed in 55.48 s on PostgreSQL 16.15 / pg_dump 16.15, confirming the setting is accepted by
real PostgreSQL 16 without invalidating the snapshot lifecycle.
Details: `docs/development-progress.md` (Stage 14D.2A).

**Plaintext file:** the primitive writes a plain dump (owner-only, 0600) to a local file in a private work directory.
It exists only on the VM and only until the §9.1 primitive has produced the durable encrypted artifact, which then
unlinks it. Removing the plaintext file altogether (`pg_dump` stdout streamed straight into gzip + age) would change
this proven primitive and is a possible later hardening, not current work.

## 8. SHA-256 provenance for target objects (correction B — MANDATORY)

The backup is **SHA-256 based and provider-neutral**. Equal size alone is **never** proof of identical bytes, and no
provider ETag is part of the integrity model. Every object admitted into a COMPLETE backup set has a trusted SHA-256
established by exactly one of:

1. **`downloaded`** — the target object is downloaded and its SHA-256 recomputed in this run (always done after a
   fresh copy, and whenever provenance cannot be established); or
2. **`inherited:<run_id>`** — permitted only if **all** of the following hold:
   1. the prior run has a valid `COMPLETE.json`;
   2. the manifest SHA-256 recorded in that `COMPLETE.json` matches the prior manifest (recomputed in this run);
   3. the prior manifest contains the same object key, the same size and a trusted SHA-256 for it;
   4. the target object currently exists;
   5. the target object's current size matches the recorded size.

If these conditions cannot establish trusted provenance → download the target object and recompute SHA-256.
Originals must additionally equal the DB SHA-256. `--deep` forces mechanism 1 for every object. A mismatch → ERROR,
no overwrite, no `COMPLETE.json`.

**ETag (diagnostic only).** An ETag MAY be recorded when the provider returns one (`target_etag`, nullable), MAY be
compared as diagnostic / provider metadata, and a changed ETag MAY trigger a conservative deep SHA-256 verification.
An ETag MUST NOT be treated as a content hash, MUST NOT be required for a valid backup, MUST NOT replace SHA-256, and
the architecture MUST NOT depend on provider-specific ETag stability. Oracle ETag semantics are unverified until
14D.4; if 14D.4 establishes useful semantics they may serve only as an optimization / suspicion signal — SHA-256
remains authoritative.

## 9. Encrypted DB backup chain (correction C / owner decision 5 — MANDATORY)

- Dumps are **encrypted with `age` before leaving the production VM**: verified private 0600 SQL dump (§7.1) →
  streaming gzip → streaming `age` to public recipients (§9.1). No unencrypted artifact leaves the VM and no gzip
  intermediate file exists. (The earlier wording "`pg_dump | gzip | age`" described the intent; the approved model
  keeps the §7.1 local plaintext file, private and transient, as the stream source.)
- The canonical remote artifact is `db/<run_id>/plan-estimate.sql.gz.age`; the manifest and `COMPLETE.json` record
  its SHA-256 and size, so the COMPLETE chain covers the encrypted artifact.
- The decryption (private) key **must not exist only on the production VM**; no private key or secret is ever
  committed to Git. Key custody (recipients, offline copies) is decided in 14D.3; 14D.1 implements no key management.
- **Restore PASS requires, in order:** encrypted artifact SHA-256 equals the manifest → `age` decryption succeeds →
  gzip integrity PASS → restore into an **isolated** PostgreSQL (never production) → expected DB / Alembic state
  (current = head, expected row counts) → ready-set digest equals the manifest (§7).

### 9.1 Encrypted artifact primitive (Stage 14D.2B — complete, owner accepted)

Implementation: `backend/app/core/db_dump_encryption.py` (`encrypt_dump_artifact`). Input: the `SnapshotDumpResult`
of §7.1. Output: `<work dir>/plan-estimate.sql.gz.age` (future remote key `db/<run_id>/plan-estimate.sql.gz.age`;
no upload in 14D.2B).

**Pipeline (exact order):** validate recipients → work directory private (absolute, not root, not a symlink, a
directory owned by the effective uid, mode no broader than 0700) → neither `plan-estimate.sql.gz.age` nor its
`.partial` exists (never overwritten, never removed when pre-existing; names only in errors) → plaintext opened
`O_NOFOLLOW | O_NONBLOCK`: regular file, owned by the effective uid, no group / other bits, size equal to the
`SnapshotDumpResult` → free-space check → `age --version` (recorded as diagnostic evidence; missing binary or
non-understood output fails; no compatibility range is claimed — the production version is fixed by the later
owner ARM64 image verification) → `.partial` created `O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC` + `fchmod 0600`
(no umask change) → `age --encrypt --recipient …` with stdout = the partial descriptor → 1 MiB chunks read in a
worker thread, plaintext SHA-256 / byte count updated, compressed with in-process zlib (gzip wrapper, level 6) and
written to age's stdin with backpressure, stderr drained concurrently into a bounded tail → plaintext SHA-256 and
size must equal the `SnapshotDumpResult` → stdin closed → age exit 0 → fsync partial → SHA-256 + size re-read
from disk in a worker thread, size > 0 → rename to the final name → directory fsync → unlink plaintext →
directory fsync → `EncryptedDumpResult` (artifact path / size / SHA-256, plaintext size / SHA-256, recipients,
age version).

**gzip:** one member; zlib's documented gzip wrapper header (no file name, no extra field, no comment, MTIME 0);
the source path / name never enters the stream. Byte-identical output across zlib versions is not promised and not
needed — the encrypted artifact SHA-256 is the integrity anchor. No production round-trip inflate (CPU); the
end-to-end check (decrypt → gunzip with CRC32 / ISIZE → exact bytes) is done by the tests.

**age:** official CLI, encryption only (`--encrypt` + `--recipient` per public recipient; never decrypt, identity,
passphrase, armor or output options). Only native X25519 `age1…` recipients; empty, malformed, SSH, plugin and
`AGE-SECRET-KEY-1…` values are refused with the position only, never the value. The child environment is fixed
(`PATH`, `LC_ALL=C`); backup / cloud secrets are not inherited. **Backup uses public recipients only; the private
identity is a restore / drill concern and never present in the backup path.**

**What backup-time success proves — and what not:** the complete verified plaintext was streamed into age, age
exited 0, and a non-empty artifact is durably stored under its final name with an independently re-read SHA-256 and
size. It does **not** prove that the artifact decrypts; that is proven only with a private identity — the opt-in
real-age round-trip test (`backend/tests/test_stage14d2b_age_roundtrip.py`, disposable identities) and the 14D.5
drill with the independently held recovery identity. No age-format parsing is done by the application.

**Real-age proof (owner-run, 2026-10-03) — PASS:** Manjaro Linux, CPython 3.12.14, age 1.3.2 / age-keygen 1.3.2.
`TEST_REAL_AGE=1 tests/test_stage14d2b_age_roundtrip.py`: 3 passed in 0.91 s; combined 14D.2B suite
(`test_stage14d2b_encryption.py` + `test_stage14d2b_age_roundtrip.py`): 64 passed in 7.56 s, 0 failed, 0 skipped.
Real decryptability of the primitive's output was proven with disposable identities: single recipient → `age
--decrypt` → gunzip → exact original bytes; with two recipients identity A and identity B each decrypt independently
and an unrelated identity C fails. This is a property of the tested code path with test identities; the production
recovery identity is proven only in the 14D.5 drill.

**Integrity values:** the authoritative manifest value is SHA-256 of the final encrypted bytes (+ size). The
plaintext SHA-256 is returned for the cross-check with §7.1 only and is not written to the public / remote manifest
without a separate decision. No gzip-intermediate hash exists.

**Cleanup:** the plaintext is unlinked only after every step up to the post-rename directory fsync has succeeded.
Any earlier failure, timeout or cancellation keeps the plaintext byte-identical, kills and reaps age, removes only
the partial created by this call, leaves no final artifact (a final name whose directory fsync failed is removed
again) and propagates (cancellation after the protected cleanup). If unlinking the plaintext or its directory fsync
fails, the valid artifact stays and `PlaintextCleanupError` carries its result. Deletion is unlink only — not secure
or forensic erasure. Stale files from an earlier run are never removed automatically; they cause a collision error.

**Not decided here (later 14D.2 sub-stages):** production execution topology (the planned one-shot backend container
cannot use `docker exec` without the Docker socket, and mounting the socket is not approved), PostgreSQL client and
`age` in the production image, Oracle upload, credentials, manifest / `COMPLETE.json` writer, `alembic_head` capture
(eventually from the same exported snapshot), restore, scheduling, 14D.3 key generation / custody.

## 10. Integrity verification model

- **Backup time:** download each source object into bounded temp; original SHA-256 + size must equal the DB row;
  derivative size must equal the DB row and its SHA-256 is computed; any mismatch → ERROR, object not copied.
- **Post-copy:** HEAD size + full re-download and SHA-256 comparison (`downloaded` provenance).
- **Existing target objects:** §8.
- **Manifest:** SHA-256 of `manifest.jsonl` = `COMPLETE.json.manifest_sha256`; counts and digest consistent;
  encrypted dump SHA-256 consistent.
- **Restore time:** each restored object's SHA-256 = manifest; originals = DB; sizes = DB; then
  `scripts/media_integrity_check.py --verify-sha256 --strict` against the restore target → exit 0.
- **Never relied on or required:** S3 ETags as content hashes or as a validity condition (diagnostic only, §8);
  R2 ETags are MD5 only for single-part uploads and Oracle ETags are opaque.

## 11. Restore drill (real, isolated)

Target topology: on the Oracle VM where practical, using isolated scratch containers / databases and the drill
buckets (§4). Production PostgreSQL is **never** a restore target; production R2 and the production Oracle backup
bucket are never written.

1. Seed the synthetic fixture (§12) through the **real upload pipeline** into `drill-source` + a scratch database
   (uploads enabled only in that isolated environment).
2. Backup run → `drill-backup` → COMPLETE (encrypted dump included).
3. Fresh scratch database: run the §9 restore chain from the drill run.
4. Restore media from `drill-backup` into the empty `drill-restore` bucket, verifying every SHA-256 against the
   manifest and the DB.
5. Before step 4, the integrity checker against the empty `drill-restore` must report exactly the expected missing
   objects; after step 4 it must be clean with `--verify-sha256 --strict`.
6. The backend, pointed at the restored scratch DB and `drill-restore`, serves list / detail and presigned thumbnail
   / display URLs (HTTP 200, bytes equal the manifest SHA-256).
7. The real production dump (encrypted, from the 14D.6 run or a dedicated drill run) restores into scratch
   PostgreSQL with Alembic current = head and the expected counts.

PASS = all steps succeed and before/after inventories show no write to any production resource. Anything else = FAIL.

## 12. Synthetic drill fixture (correction D)

Mandatory: a small JPEG, a small PNG, a small WebP, and an EXIF-orientation case (supported by the existing
pipeline). Generated images only — **no real customer / user media**, no production rows. A near-60 MP image is
**optional** (extended resource test only; the processing boundary was exercised in 14C.6).

Isolation: separate buckets and tokens; tools refuse a restore / drill target equal to a configured production
bucket and refuse a non-scratch database (same pattern as `tests/pg_scratch_guard.py`); drill `run_id`s and buckets
are labelled. Cleanup after owner sign-off is a manual owner step (drill buckets, scratch databases, local files);
nothing in production needs cleanup because nothing there is touched.

## 13. Credentials (least privilege) — OWNER APPROVED in principle

| Purpose | Credential | Intended permission |
|---|---|---|
| Backend app | existing R2 token | Object Read & Write, production bucket (unchanged) |
| Backup reads R2 | new R2 token | Object Read only, production bucket |
| Backup writes Oracle | dedicated Oracle identity (`media-backup`) | create / read / list in the backup bucket; no delete; no overwrite if enforceable |
| Restore reads Oracle | separate Oracle identity (`media-restore`) | read / list only |
| Restore target | restore-target token | drill: `drill-restore` only; a real disaster restore uses a new token created then |
| Drill | separate R2 / Oracle drill tokens | drill buckets only |

Backup and restore credentials are separate. Secrets live only in a dedicated `chmod 600` env file on the VM, never
in `.env.production` or the backend container environment, never printed. **The exact Oracle IAM permissions
(overwrite / delete restriction, conditional PUT behaviour) are verified empirically in 14D.3 / 14D.4 and are not
assumed here.**

## 14. Retention / deletion (v1) — OWNER APPROVED

Media objects, manifests and `COMPLETE.json` markers: append-only, no automatic deletion. DB dumps: no automatic
deletion initially. No irreversible retention lock initially. Oracle object versioning on. The tooling has no delete
code path. Retention / deletion automation is deferred until real storage growth is known.

## 15. Failure / resume / idempotency

| Case | Behaviour |
|---|---|
| Duplicate invocation | host `flock`; the second run exits non-zero immediately |
| Network interruption | bounded retries, then the object fails; the run continues for a complete report but ends with no `COMPLETE.json`, exit non-zero |
| Process crash | no marker → incomplete; rerun with a new `run_id`; admitted objects follow §8 |
| Target object exists | admitted only per §8; different bytes → ERROR, never overwritten |
| Source object missing (READY in DB) | ERROR (`MISSING_SOURCE`, evidence loss), run incomplete |
| SHA-256 mismatch (source vs DB, or post-copy) | ERROR, not admitted, run incomplete |
| Partial manifest | manifest uploaded first, marker last; manifest without a valid marker = invalid |
| Restore | reads only runs with a valid marker; refuses production targets; idempotent per object |

## 16. Operational model

A standalone CLI shipped in the backend image, run as a one-shot container with its own env file (pinned dependency
set; no host Python), e.g.
`docker run --rm --network plan-estimate_internal --env-file <backup env> --cpus 0.5 --memory 512m <pinned image>
python scripts/media_backup.py …`; one object in flight (≈75 MB temp maximum); suitable for later systemd-timer
execution. **No timer is enabled in 14D.1 / 14D.2**; scheduling is decided later in the 14D readiness process,
before 14E. Recurring production backups should use a **dedicated read-only PostgreSQL role**, created as an
explicit manual operational step (not an application migration).

## 17. Stage 14D PASS criteria

1. Tooling (backup, verify, restore, guards, encrypted dump chain) implemented with automated tests; full backend,
   focused suites, mypy, Ruff green.
2. Oracle / R2 resources and least-privilege credentials created by the owner and recorded without secrets.
3. Connectivity / semantics smoke: PUT / HEAD / GET / list; observed overwrite, delete and conditional-PUT behaviour
   documented; backup identity cannot delete; restore identity read-only.
4. Isolated drill (§11) fully PASS, including the §7 invariant and the §9 chain.
5. Production non-destructive run: encrypted dump off the VM and verified; media run on the current inventory
   COMPLETE; no production change.
6. Runbook §72 finalized with exact verified commands; progress document updated.
7. Owner sign-off. Enabling uploads remains the Stage 14E decision.

## 18. Sub-stages (OWNER APPROVED)

| Sub-stage | Scope | Cloud / production |
|---|---|---|
| 14D.1 | architecture / readiness audit (this document) | none |
| 14D.2 | tooling + tests: manifest v1, snapshot-bound inventory + digest, backup engine, §8 provenance, verify, restore, encrypted-dump handling, dual-store config, production-target / scratch guards, runbook draft | none |
| 14D.3 | owner manual setup: Oracle buckets / IAM / keys / versioning; R2 read-only token; R2 drill buckets + tokens; `age` key custody; env files | owner only |
| 14D.4 | controlled connectivity / semantics smoke on drill resources | drill only |
| 14D.5 | isolated drill (§11) with the synthetic fixture | drill / scratch only |
| 14D.6 | first production non-destructive backup run (encrypted dump + media run), verification, runbook final | read-only on production |
| 14D.7 | readiness audit + gate record, owner sign-off (enablement stays 14E) | — |

## 19. Deferred to later 14D sub-stages

- `pg_dump --snapshot` orchestration detail (host wrapper vs tool-driven) and its scratch-PostgreSQL verification
  (14D.2).
- Dual-store configuration names / env-file template (14D.2).
- Integrity-checker wording for `MISSING_DERIVATIVE` (code text still says "regenerable from the original"; to be
  corrected in 14D.2, since code is out of scope for 14D.1).
- `age` recipients, key custody and offline copies; whether the private key may be present temporarily on the VM
  during a drill (14D.3).
- Exact Oracle IAM policy, overwrite / delete / conditional-PUT and ETag behaviour (14D.3 / 14D.4).
- Dedicated read-only PostgreSQL role creation (manual operational step; before recurring backups).
- Recurring schedule (systemd timer) and RPO (before 14E).
