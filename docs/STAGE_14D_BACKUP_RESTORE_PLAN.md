# Stage 14D — Backup / Restore Drill & Production Media-Readiness Gate (plan and contract)

> **Status:** 14D.1 architecture — **OWNER APPROVED** (2026-10-02, with the mandatory corrections A–D below
> incorporated). 14D.2A (snapshot primitive, §7.1) — COMPLETE / OWNER ACCEPTED (owner runs, 9/9, re-proven after hardening).
> 14D.2B (encrypted DB artifact primitive, §9.1) — COMPLETE / OWNER ACCEPTED (real-age round-trip proven, age 1.3.2).
> 14D.2C (backup execution image / container contract, §16) — COMPLETE, OWNER LOCAL IMAGE / RUNTIME VERIFIED (linux/amd64,
> 2026-10-03), owner accepted. Not yet proven: ARM64 production image, real PostgreSQL topology end-to-end,
> production DB role, production backup execution. 14D.2D (local backup orchestrator, owner decisions D1–D6 / corrections
> C1–C4) — IN PROGRESS: 14D.2D.1 pure contracts (§16.3) and 14D.2D.2 data root / lock / stale work / promotion
> (§16.4), 14D.2D.3 local orchestration + `db-dump` (§16.5) and 14D.2D.4 real PostgreSQL 16 snapshot / role proof
> (§16.6, owner-verified 8/8 on PostgreSQL 16.15; production backup-role policy frozen) complete. Rest of 14D.2 and 14D.3–14D.7 — NOT STARTED. Apart from the §7.1 / §9.1 primitives and the
> §16 image / container contract, nothing in this document is implemented, configured or
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
  transaction is held open. The dump and the inventory are therefore the same database state. (Superseded detail:
  `pg_dump` does **not** run through `docker exec` in the postgres container — it runs inside the dedicated backup
  execution image, which carries pg_dump major 16 and reaches `postgres:5432` over the Compose network; the 14D.2A
  major-version equality check stays in force. §16.)
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

**`after_export(snapshot_id)` — production lifecycle hook (since 14D.2D.3; not a test-only seam):** it is awaited
after a successful `pg_export_snapshot()` and the transaction-mode assertions, **while the exporter transaction is
open**, **before** the READY inventory and **before** pg_dump. Work that must see the exported snapshot runs here —
14D.2D.3 imports the snapshot on a second connection to read the Alembic revision and metadata and enforces the
schema revision (§16.5). If the hook raises, the snapshot-bound dump aborts before pg_dump starts and the normal
exporter rollback / close cleanup runs. A future refactor must keep this hook and its position.

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

**Not decided here (later 14D.2 sub-stages):** ~~production execution topology and PostgreSQL client / `age` in the
image~~ (decided in 14D.2C, §16: dedicated backup image, no Docker socket), Oracle upload, credentials, manifest / `COMPLETE.json` writer, `alembic_head` capture
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

## 16. Operational model — backup execution image and container (Stage 14D.2C)

The backup runs as a one-shot container of a **dedicated backup image**, not the web backend image (which stays
unchanged), invoked by `docker compose run --rm --no-deps backup …` (no host application Python; a host `flock`
around it is added with the 14D.2D orchestrator). One media object in flight (≈75 MB temp maximum) once the media
engine exists; suitable for later systemd-timer execution. **No timer is enabled in 14D.1 / 14D.2**; scheduling is
decided later in the 14D readiness process, before 14E.

**Image (`backend/Dockerfile.backup`):** base `python:3.12.14-slim-trixie` pinned by multi-arch index digest; the
same pinned `requirements.txt` as the web image (one `pip install`, no second dependency set; the in-image pin guard
`tests/test_dependency_pins.py` applies); only `app/`, `tests/`, `requirements.txt`, `pyproject.toml` copied; no
`entrypoint.sh`, no migrations, no web server; `ENTRYPOINT python -m app.backup`, default `CMD preflight`; default
`USER 65534:65534`.
- **pg_dump 16 — why PGDG:** Debian trixie ships only PostgreSQL 17 clients (`postgresql-client` = `17+278`) and has
  no `postgresql-client-16`. The image installs PGDG `postgresql-client-16`, configured as in PostgreSQL's official
  "Manual Repository Configuration" (deb822 `.sources`, dedicated `Signed-By` key file, no `apt-key`). **PGDG trust
  anchor:** the key is downloaded over HTTPS from the official URL `https://www.postgresql.org/media/keys/ACCC4CF8.asc`
  in a separate build stage and accepted only if (1) its SHA-256 equals the pinned
  `0144068502a1eddd2a0280ede10ef607d1ec592ce819940991203941564e8e76` — checked first, before the key is parsed —
  and (2) it is exactly one OpenPGP primary key with the pinned fingerprint
  `B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8` ("PostgreSQL Debian Repository"); the runtime stage re-checks the SHA-256
  after the copy, before apt trusts it. The expected SHA-256 was established (2026-10-03) from two independently
  distributed copies with identical bytes: the official URL and the Debian archive's `postgresql-common` 278
  **source** package (`pgdg/apt.postgresql.org.asc`). PostgreSQL's pages publish the key URL but not the fingerprint
  as text. (Correction: the Debian `postgresql-common` **binary** package does **not** ship the PGDG key — owner
  build proof #2.) The package name pins the major;
  the build fails unless `command -v pg_dump` is `/usr/lib/postgresql/16/bin/pg_dump` and it reports
  `(PostgreSQL) 16.x`; the minor is recorded by the image proof (PGDG retention makes an exact-minor pin fragile).
  14D.2A's runtime server / client major-equality check remains.
- **age 1.3.2 — why not Debian:** trixie ships `age` 1.2.1. The image downloads the official
  `age-v1.3.2-linux-<arch>.tar.gz` (amd64 for local proofs, arm64 for production), verifies it with
  `sha256sum -c` against digests pinned in the Dockerfile **before extraction** (the GitHub release asset digests of
  `FiloSottile/age` v1.3.2, read from the GitHub release API on 2026-10-03; upstream also publishes `.proof`
  transparency files that the owner may verify additionally), installs only `age` and `age-keygen`, and fails
  unless `age --version` is 1.3.2. No identity is in the image; only public recipients are supplied at runtime.
- **Builders / architecture:** BuildKit / buildx is **not** required. `<arch>` is the Debian architecture of the
  build stage (`dpkg --print-architecture`), i.e. the architecture the binary runs on. When BuildKit supplies
  `TARGETARCH` it is validated and must equal that architecture (never silently overridden); the classic builder
  supplies none and builds only for the native architecture. Only `amd64` and `arm64` are accepted (anything else
  fails before any download), each with its own pinned SHA-256. Native amd64 / arm64 classic builds are supported;
  BuildKit / buildx is needed only for cross-platform builds. The real ARM64 production image still requires its
  later owner proof.

**Compose service `backup` (`docker-compose.prod.yml`):** `profiles: ["backup"]` (never started by `up -d`); **no
`depends_on`** and always run with **`--no-deps`** (a `compose run` with dependencies could start or recreate the
production postgres container); no ports; existing `internal` network only to reach `postgres:5432` without
publishing PostgreSQL (that network is a plain bridge with egress — not a security isolation boundary);
`restart: "no"`; `init: true`; `read_only: true` with a 16 MiB `/tmp` tmpfs (to be confirmed by the owner proof);
`cap_drop: [ALL]`; `no-new-privileges`; non-root `user: ${BACKUP_UID}:${BACKUP_GID}`; `mem_limit 512m`, `cpus 0.5`,
`pids_limit 64` (to be validated with `docker compose config`); **no Docker socket**, no postgres data volume, no
repository, frontend or Caddy mounts; environment limited to `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`,
`PGSSLMODE`, `PGPASSFILE`, `BACKUP_AGE_RECIPIENTS` (no `env_file`, no application secrets). Variables use
fail-closed defaults instead of `${VAR:?}` because Compose interpolates the whole file and a required variable would
break normal deployments: unset `BACKUP_UID` runs as `65534`, unset `BACKUP_HOST_ROOT` points at a non-existent path
and the bind mounts (`create_host_path: false`) are refused. `stop_grace_period: 45s` (14D.2D.2, D6) leaves room for
the protected 14D.2A / 14D.2B cleanup after SIGTERM. Settings come from a separate backup env file
(`backup.env.example`, placeholders only), passed as an additional `--env-file`.

**Workspace / mounts (host root recommended `/home/ubuntu/backups/plan-estimate/db-backup/`, 0700) — corrected in
14D.2D.2:** **one** data mount `data/` → `/backup` (rw; contains `work/`, `encrypted/`, `evidence/`, `run.lock`;
completed artifacts survive `--rm`) and `secrets/pgpass` → `/run/secrets/pgpass` (**read-only**), secrets outside the
data root. The 14D.2C layout (three separate bind mounts for work / encrypted / evidence) was replaced because
`rename(2)` across mount points fails with `EXDEV` even on one host filesystem, so a run could not be promoted
atomically (§16.4). Container paths are unchanged and do not depend on the host user name.

### 16.1 Database connection contract (`backend/app/backup/pg_connection.py`)

One non-secret `PgConnectionConfig` (host, port, database, user, passfile path, **explicit** SSL mode — configurable,
`disable` only expected for the current local bridge, not an invariant) from which both the asyncpg exporter DSN
(no password; `passfile` / `sslmode` parameters) and the libpq environment of `pg_dump` are derived;
`check_process_env` verifies that the inherited process environment (14D.2A's pg_dump inherits it) carries exactly
that connection; `PGPASSWORD`, `PGSERVICE`, `PGSERVICEFILE` are refused. `pg_dump_command()` yields the 14D.2A command
with **no tool prefix** (local pg_dump over the network). The password exists only in the pgpass file — never in
argv, DSN, `DATABASE_URL`, `PGPASSWORD`, logs or evidence.

**pgpass validation:** absolute, regular, not a symlink, owned by the effective UID, no group / other bits, at most
64 KiB, UTF-8, exactly one entry (empty lines and `#` comments at column 1 allowed), no wildcard field, host / port /
database / user equal to the configuration, non-empty password; errors name the line / field, never the content.
**Credential-format constraint (option B):** asyncpg 0.31.0 and libpq parse pgpass differently — libpq de-escapes
`\` and ends the password at the first unescaped `:`, asyncpg keeps backslashes, keeps everything after the fourth
`:` and strips surrounding whitespace. The validator therefore accepts only the common subset (no `\`, no `:` inside
values, no surrounding whitespace), so both clients always use the same password. The production password must
satisfy this; generating it is an owner action (14D.3).

**Database role:** frozen as the intended production policy in 14D.2D.4 after the scratch PostgreSQL 16 experiment
(§16.6): dedicated `LOGIN` role + `CONNECT` on the application database + membership in `pg_read_all_data`;
`NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`; no write, schema CREATE or DDL grants. No production
role or credential is created in 14D.2C or 14D.2D.

### 16.2 Owner local image / runtime proof (Stage 14D.2C, 2026-10-03, linux/amd64)

Three owner builds on the development machine (Manjaro, Docker without buildx → classic builder), scratch paths and
fake values only, no database connection:
1. Compose profile contract PASS (`config --services` without the profile: postgres / backend / frontend / caddy;
   with `--profile backup`: backup listed). Build failed closed: no `TARGETARCH` under the classic builder → fixed
   (native `dpkg --print-architecture`, validated `TARGETARCH`, amd64 / arm64 only).
2. age architecture selection and pinned age SHA-256 PASS. Build failed closed: the Debian `postgresql-common` 278
   binary package does not contain the PGDG key → fixed (official key URL, pinned SHA-256 + fingerprint, §16).
3. **Full build PASS**: `/tmp/pgdg.asc: OK`, fingerprint `B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8`, runtime key
   re-check OK, `postgresql-client-16 16.15-1.pgdg13+2`, `pg_dump (PostgreSQL) 16.15 (Debian 16.15-1.pgdg13+2)`,
   age / age-keygen v1.3.2, Python 3.12.14; image `plan-estimate-backup:local`
   `sha256:7b98dd7605dea6b4dce751632bbd7bd1a646c3ddb635376c0824f00cfc21bc26`; `USER 65534:65534`,
   `ENTRYPOINT ["python","-m","app.backup"]`, `CMD ["preflight"]`.

Runtime (via `docker compose run --rm --no-deps backup`): `preflight` PASS (Python 3.12.14, pg_dump 16, age 1.3.2,
uid / gid 1000); `preflight --workspace` PASS (three private writable mounts; connection host=postgres port=5432
database=plan_estimate user=pe_backup sslmode=disable; pgpass exactly one matching entry; one public recipient).
Security: uid / gid 1000, CapInh / CapPrm / CapEff / CapBnd / CapAmb all 0, NoNewPrivs 1, no Docker socket,
read-only root filesystem, writable `/tmp` tmpfs, pgpass 0600 / uid 1000 regular file and read-only in the container.
A file written to `/backup/encrypted` by a `--rm` container persisted on the host (uid / gid 1000; it was a
shell-created probe with mode 0644 — the backup artifacts' 0600 mode is enforced separately by the 14D.2A / 14D.2B
primitives). In-image tests: selected 14D.2A / 2B / 2C suites 219 passed, 53 skipped (opt-in / repository-only
tests; one warning: pytest cache under the read-only `/app`); `TEST_REAL_AGE=1` round-trip in the image: 3 passed,
0 skipped.

**Not proven by 14D.2C** (later sub-stages): the ARM64 production image (owner-approved smoke before 14D.6), the
real PostgreSQL snapshot → network pg_dump → age chain from this container (14D.2D scratch proof), the production
DB role and its minimum privileges, any production backup execution, the backup / restore gate (14D), and upload
enablement (14E).

**Preflight (`python -m app.backup preflight [--workspace]`):** reports Python (3.12 expected), pg_dump (major 16),
age (1.3.2) and effective UID / GID (non-root required); `--workspace` also checks the data root and its `work/`,
`encrypted/`, `evidence/` directories (private, writable, owned by the effective UID), the connection settings, the pgpass file (validated, never printed) and the
age recipients (count only). Exit 0 / 1. It never prints the environment and never connects to a database.

### 16.3 Local backup run contracts (Stage 14D.2D.1 — pure, no I/O)

Owner decisions for 14D.2D: **D1** one data bind mount `<host data root> → /backup` (`work/`, `encrypted/`,
`evidence/`, `run.lock`; secrets outside, pgpass read-only at `/run/secrets/pgpass`) so a completed run directory is
promoted by an atomic rename inside one mount (separate bind mounts would fail with `EXDEV`); **D2** the backup image
carries `alembic.ini` + `alembic/` and resolves the expected head offline; **D3** observed revision must equal the
expected head, fatal before pg_dump, no override; **D4** same-snapshot metadata through a second connection that
imports the exported snapshot (`SET TRANSACTION SNAPSHOT`, strictly validated id), 14D.2A unchanged; **D5** plaintext
SHA-256 kept in local evidence only; **D6** `stop_grace_period: 45s`. Corrections: **C1** no `tool.source_sha256`;
**C2** `pg_database_size()` is not a required role privilege and the disk-space rule is a local policy, not frozen;
**C3** host `docker exec` / `psql` is scaffolding only (fixture, roles, seed, independent verification), never part
of the backup execution topology; **C4** failure evidence is allowlisted structure only. D1 / D2 / D6 change the 14D.2C
Compose / Dockerfile contract in a later slice (14D.2D.2+); 14D.2D.1 implements only:

- **`run_id`** (`backend/app/backup/run_id.py`): `YYYYMMDDTHHMMSSZ-<8 lowercase hex>`, generated internally from a
  timezone-aware UTC time + `secrets.token_hex(4)`; strict validation (ASCII-only classes — `\d` would also match
  non-ASCII digits that `strptime` accepts — and a real calendar timestamp); never taken from user input.
- **Revision contract** (`backend/app/backup/schema_revision.py`): `observed_revision_from_rows` accepts exactly one
  `alembic_version` row with one valid id (`[A-Za-z0-9_]{1,32}`, matching `VARCHAR(32)`); `resolve_expected_head`
  reads the repository scripts with Alembic `ScriptDirectory` only (no database, `env.py` never run) and requires
  exactly one head; unreadable / cyclic / broken scripts raise a typed error; `check_revision(observed, expected)` —
  exact equality, no override parameter.
- **Local evidence v1** (`backend/app/backup/evidence.py`): `CompleteRunEvidence` (format
  `plan-estimate/local-db-backup/v1`: run_id; UTC timestamps started / snapshot exported / dump completed / completed,
  non-decreasing; database name, server version + number, observed revision, expected head — equal, status counts
  exactly FAILED / PENDING / READY; snapshot method, READY-set format, `ready_count`, `ready_set_sha256` — consistent
  with the fixed empty-set digest and with the READY status count of the same snapshot; pg_dump version line;
  plaintext SHA-256 / size (local only, D5); artifact name, `age`, age version, recipient **count** 1–32, SHA-256,
  size; diagnostics: snapshot id and session tag, diagnostic only) and `FailedRunEvidence` (format
  `plan-estimate/local-db-backup-failure/v1`: run_id, started / failed timestamps, stage enum, stable error code enum,
  `plaintext_retained`, `artifact_valid`, `partials_present` — no message, stderr, path, DSN or environment field can
  exist). Error codes are derived from the exception **type** only. Canonical JSON: sorted keys, compact separators,
  ASCII, `allow_nan=False`, integers only (bool rejected), one trailing `\n`; every string is pattern-checked and
  length-capped.

### 16.4 Data root, run lock, stale work, atomic promotion (Stage 14D.2D.2)

Implementation: `backend/app/backup/workspace.py` (`BackupDataRoot`, `RunLock`, `RunWorkspace`). The data root is a
parameter (container `/backup`, tests a temporary directory); no host path is hard-coded.

- **Data root**: absolute, not `/`, opened with `O_NOFOLLOW | O_DIRECTORY`, checked with `fstat` (directory, owned by
  the effective UID, no group / other bits). `prepare()` opens `work/`, `encrypted/`, `evidence/` relative to the
  root fd the same way; a **missing** one is created with `mkdir` + `fchmod 0700` (umask-independent), an existing
  unsafe one (symlink, file, broader mode, foreign owner) is **refused, never chmod-ed**. `evidence/` is only
  reserved here; failure-evidence writing is a later slice.
- **Run lock**: `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on `run.lock` (created `O_EXCL` 0600 + `fchmod`, otherwise opened
  `O_NOFOLLOW`, must be a regular private file owned by the effective UID). The fd stays open for the run; release is
  idempotent; contention raises `LockHeldError` immediately. The **file persists**, the **kernel lock does not**: it
  ends when the fd is closed or the process / container dies, so there is no stale lock and no cleanup mechanism.
  No container-name or PostgreSQL advisory locking.
- **Stale work (fail closed)**: any entry in `work/` → `StaleWorkError` (entry count + up to five canonical run ids;
  no contents, no host paths). Names are only enumerated: nothing is traversed, followed, inspected, renamed or
  deleted — the operator inspects stale work manually. There is no automatic cleanup or recovery.
- **Run workspace**: `create_run(run_id)` validates the id (14D.2D.1), creates `work/<run_id>/` with `mkdir`
  (fails if anything exists there — never reused, overwritten, deleted or retried) + `fchmod 0700`, fsyncs it and
  `work/`. `RunWorkspace` derives the fixed names `plan-estimate.sql`, `plan-estimate.sql.gz.age`, `local-run.json`.
- **Promotion**: `promote(run_id)` — source must be a real private directory, destination must not exist, `work/`,
  `encrypted/` and the source must share `st_dev` (otherwise `CrossFilesystemError`, no copy). Sequence: files were
  fsynced by their writers → `fsync(work/<run_id>)` → `renameat2(RENAME_NOREPLACE)` (atomic, refuses any existing
  destination; plain `rename(2)` would silently replace an empty directory) → `fsync(work/)` → `fsync(encrypted/)`.
  A failed rename leaves the run in `work/`; an fsync failure is surfaced (`DurabilityError.promoted`). There is no
  copy and no plain-rename fallback. Promotion does not inspect content: only the orchestrator decides a run is
  complete (after the encrypted artifact and `local-run.json` are durable) and calls it.
- **Linux runtime requirement (intentional):** local atomic promotion v1 requires Linux `renameat2` with
  `RENAME_NOREPLACE` (glibc, via `ctypes`); the backup runtime is deliberately Linux / glibc based. `ENOSYS`,
  `EINVAL` or any filesystem that does not support the flag is **fatal** (`PromotionError`, run stays in `work/`).
  There is **no** fallback to plain `rename`, `replace` or copy. Support on the actual Compose bind mount is **not
  claimed yet**; it is proven by the 14D.2D.5 E2E (amd64 locally, ARM64 later).
- **Post-rename durability invariant:** `DurabilityError(promoted=True)` means the rename succeeded — the run may
  already exist as `encrypted/<run_id>/` — but `fsync(work/)` or `fsync(encrypted/)` failed, so durable promotion is
  unconfirmed. Future orchestration MUST NOT treat this as "nothing was promoted" and MUST NOT retry, re-promote or
  overwrite; it is a failed run requiring operator inspection. (`promoted=False`: the run is still in `work/`.)
- Compose runtime behaviour of the new mount is **not** proven by YAML parsing; it is part of the owner E2E
  (14D.2D.5).

### 16.5 Local backup orchestration and `db-dump` (Stage 14D.2D.3)

Implementation: `backend/app/backup/orchestrator.py` (`BackupOrchestrator`), `backend/app/backup/snapshot_metadata.py`,
`backend/app/backup/db_dump_command.py`; command `python -m app.backup db-dump` (`preflight` unchanged). It sequences
the accepted primitives and reimplements none of them; 14D.2A and 14D.2B are unchanged.

**Order:** A preflight (inherited process environment equals the `PgConnectionConfig` libpq environment, passfile
valid, `pg_dump --version` probe) → B lock (`RunLock.acquire` validates the data root before opening `run.lock` in
it) → C `prepare()` under the lock → D stale-work check → E expected head (offline) → F `run_id` + `work/<run_id>/`
→ G 14D.2A `snapshot_bound_dump` with the metadata hook → H 14D.2B `encrypt_dump_artifact` → I complete
`local-run.json` (exclusive, 0600, fsync file + run directory) → J promotion (last). Failures before F have no
`run_id` and write no evidence.

**Same-snapshot metadata (D4):** the 14D.2A `after_export` hook runs while the exporter transaction is open, before
the READY inventory and before pg_dump. It opens a second asyncpg connection (same passfile DSN, application name
`<tag>-meta`), runs `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`, then — as the first statement —
`SET TRANSACTION SNAPSHOT '<id>'` (the only interpolated SQL; the id must match the strict 14D.2D.1 pattern), asserts
the transaction mode, and reads exactly one `alembic_version` row, `photo_assets` counts per status (FAILED / PENDING /
READY only; unknown or duplicate statuses, negative or non-integer counts are refused), `current_database()`,
`server_version`, `server_version_num`; then `ROLLBACK` and close on every path (timeout / cancellation included).
The hook records `snapshot_exported_at` and enforces **observed revision == expected head inside the hook**, so a
mismatch aborts before the READY inventory and before pg_dump starts; 14D.2A then releases the exporter. After the
dump the metadata server major must equal 14D.2A's server major.

**Evidence:** `local-run.json` (CompleteRunEvidence v1) is built only from actual values — metadata, 14D.2A READY and
dump results, 14D.2B result, the pg_dump version probe — and written only after encryption succeeded, before
promotion. From F on, every failure — cancellation included — writes best-effort
`evidence/<run_id>.failed.json` (FailedRunEvidence v1: stage, stable code by exception type, `plaintext_retained`,
`artifact_valid`, `partials_present` derived from the run directory's names); exception text is never serialized;
if writing it fails, only the error type is logged and the original failure stays primary. Additive error codes:
`LOCK_HELD`, `STALE_WORK`, `PG_DUMP_TOOL_UNUSABLE`, `SNAPSHOT_METADATA_INVALID`, `WORKSPACE_UNSAFE`,
`RUN_DIRECTORY_EXISTS`, `CROSS_FILESYSTEM`, `PROMOTION_FAILED`, `PROMOTION_NOT_DURABLE`,
`PROMOTION_DURABILITY_UNCONFIRMED`, `EVIDENCE_WRITE_FAILED`, `EVIDENCE_INVALID`.

**Failure semantics:** nothing is retried, cleaned up or moved back; a remaining `work/<run_id>/` is stale work for
the operator. `PlaintextCleanupError` (artifact valid, plaintext present) fails the run without promotion
(`plaintext_retained=true`, `artifact_valid=true`). `DurabilityError(promoted=False)` → `PROMOTION_NOT_DURABLE`,
run stays in `work/`; `DurabilityError(promoted=True)` → `PROMOTION_DURABILITY_UNCONFIRMED`, exit 7, operator
inspection — never re-promoted or overwritten.

**Signals:** SIGTERM / SIGINT cancel the top-level task (`loop.add_signal_handler`, removed afterwards; no
`os._exit`), so the 14D.2A / 14D.2B protected cleanup runs (child kill + reap, tagged-session termination, exporter
rollback), `CANCELLED` failure evidence is written when a run exists, the lock is released by its context manager,
nothing is promoted. Compose `stop_grace_period: 45s` covers the cleanup timeouts.

**Exit codes:** 0 success · 1 backup failed · 2 usage · 3 lock held · 4 stale work · 5 preflight / configuration (no
run) · 6 interrupted · 7 promotion durability unconfirmed. Output is a one-line structured summary (run id, stage,
code, counts, artifact SHA-256 / size) — never environment, DSN, password, recipients or exception text.

**Not in 14D.2D.3:** disk-space sizing policy (deferred; `pg_database_size()` is not used); PostgreSQL role /
privilege proof and real PostgreSQL proof of the orchestrated path (14D.2D.4); Compose topology E2E, incl.
`renameat2` on the real bind mount (14D.2D.5); cloud, restore, scheduling, production.

### 16.6 Real PostgreSQL 16 snapshot + backup-role proof (Stage 14D.2D.4 — COMPLETE / OWNER VERIFIED)

Opt-in harness (`TEST_REAL_POSTGRES=1`): `backend/tests/pg16_proof_support.py` (gate, scratch-only guards, passfiles,
report), `backend/tests/pg16_proof_fixtures.py` (session template database migrated to the repository head; per-test
clones; synthetic marker table `pe_proof_marker` and photo assets 2 READY / 1 PENDING / 1 FAILED; scratch roles),
registered through `tests/conftest.py` (`pytest_plugins`, inert unless requested). Runs **inside the backup image**
(its own pg_dump 16 / psql / age 1.3.2) on an isolated internal Docker network next to a disposable
`postgres:16-alpine`; no published port, no production project, network or volume. Every database is
`pe_scratch_test_14d2d4_*`, every role `pe_scratch_role_*`; role passwords are random hex in 0600 passfiles (SQL sent
on psql stdin, never argv); databases are dropped first, then roles. The proof requires server major 16 **and**
pg_dump major 16 and fails (not skips) otherwise; it also fails if the gate is on but the configuration is missing
or unsafe (host must contain `proof`).

- **A — snapshot import / isolation:** exporter T1 (`REPEATABLE READ READ ONLY`, `pg_export_snapshot()`), importer T2
  (`SET TRANSACTION SNAPSHOT`), writer T3 commits marker A→B, a new READY asset and a changed `alembic_version`; T2,
  T1 and the production metadata reader (importing S only after T3) still see A / 2 READY / head; a new ordinary
  transaction sees B / 3 READY / the mutated revision.
- **B — pg_dump content:** the 14D.2A primitive with T3 committed inside its hook; the dump is **restored into a
  fresh database and queried**: marker A, 2 READY with the exporter's digest, head revision — while the live source
  shows B.
- **C — exporter lifetime:** after the exporter rolls back, importing S fails with SQLSTATE 22023 (raw and via the
  production reader) and `pg_dump --snapshot=S` exits non-zero.
- **D — real orchestration:** `run_db_dump` (exit 0) per candidate role (`explicit_tables_sequences`,
  `pg_read_all_data`) with real age: `work/` and `evidence/` empty, `encrypted/<run_id>/` holds exactly the artifact
  and `local-run.json`, no plaintext, observed == expected head, READY count / digest equal the source, artifact
  SHA-256 / size equal the evidence; then decrypt (disposable identity) → gunzip → plaintext SHA-256 equals the
  evidence → restore → READY digest and revision equal. Reusable by 14D.2D.5.
- **E — role matrix (recorded, not assumed):** `login_only`, `explicit_tables`, `explicit_tables_sequences`,
  `pg_read_all_data` — connect, RR RO, export, same-role import, alembic / status counts / READY inventory, raw
  `pg_dump --snapshot` (and whether a sequence grant was required), termination of the role's own tagged session,
  the full 14D.2A + metadata pipeline, `pg_database_size()` (diagnostic only, never a requirement); RLS tables /
  policies and public sequences are reported; a table created **after** the grants shows the schema-evolution
  behaviour of each candidate. Negative checks for both candidates: INSERT / UPDATE / DELETE / TRUNCATE / CREATE TABLE
  / ALTER / DROP / CREATE DATABASE / CREATE ROLE must all be denied (42501) and no dangerous role attribute set.
- **What only this proof can show** (unit tests cannot): real PostgreSQL snapshot export / import semantics, real
  pg_dump content, exporter-lifetime dependence, actual privilege requirements, the orchestrated path against a real
  server. Default backend runs never require PostgreSQL / Docker (the modules skip).
- **D2 implemented here:** `backend/Dockerfile.backup` now copies `alembic.ini` + `alembic/` (offline head resolution;
  the image never runs migrations — the proof's own scratch migration runs the test harness, not the image
  entrypoint). Without it the orchestrator cannot resolve the expected head inside the image.

**Owner-run result (2026-10-03): 8 passed in 27.77 s** — PostgreSQL server 16.15, pg_dump 16.15, psql 16.15, age /
age-keygen 1.3.2, inside the backup image on the isolated proof network.

- **A PASS:** the imported snapshot kept marker `PE_PROOF_VALUE_A` / READY 2 while a new transaction saw
  `PE_PROOF_VALUE_B` / READY 3 / revision `zz_proof_mutation`; the production metadata reader importing the snapshot
  after the commit still saw `0032_photo_attachments` / READY 2.
- **B PASS:** the `pg_dump --snapshot` dump restored into a fresh database showed marker A, READY 2, revision
  `0032_photo_attachments`, READY digest equal to the exporter's — while the live source already had B / READY 3.
- **C PASS:** after exporter rollback / close, `SET TRANSACTION SNAPSHOT` and the production metadata reader failed
  with SQLSTATE 22023 and `pg_dump --snapshot` exited 1 — the exporter-lifetime requirement is empirically confirmed.
- **D PASS** for `explicit_tables_sequences` and `pg_read_all_data`: exit 0; artifact present, SHA-256 / size equal
  the evidence; observed = expected = `0032_photo_attachments`; READY 2 with the source digest; decrypt + gunzip +
  restore PASS with matching READY digest and revision; `work/` empty; no failure evidence.
- **E role matrix:** `login_only` — connect, RR RO, `pg_export_snapshot()` and same-role import all ok (no elevated
  attribute needed for snapshot export / import in this PostgreSQL 16 environment), but `alembic_version`,
  `photo_assets`, the READY inventory and `pg_dump` denied (42501) and the full pipeline failed
  (`InsufficientPrivilegeError`); `explicit_tables`, `explicit_tables_sequences` and `pg_read_all_data` — full
  pipeline and `pg_dump --snapshot` PASS. **Schema evolution:** for a table created after the grants,
  `explicit_tables_sequences` was **denied** (not covered by the earlier grants) and `pg_read_all_data` **passed**.
  **Negative checks** (both candidates, part of 8/8; values recorded for `pg_read_all_data`): INSERT, UPDATE, DELETE,
  TRUNCATE, CREATE TABLE, ALTER TABLE, DROP TABLE, CREATE DATABASE, CREATE ROLE all denied (42501); `rolsuper`,
  `rolcreatedb`, `rolcreaterole`, `rolreplication`, `rolbypassrls` all false. RLS: 0 tables with RLS, 0 forcing it,
  0 policies. Public sequences: 0.

**Production backup-role policy (owner decision, frozen; NOT created yet):** dedicated `LOGIN` role + `CONNECT` on
the application database + membership in the predefined role `pg_read_all_data`, explicitly `NOSUPERUSER NOCREATEDB
NOCREATEROLE NOREPLICATION NOBYPASSRLS`; no application write grants, no schema CREATE / DDL grants. Rationale: both
explicit SELECT grants and `pg_read_all_data` run the current pipeline, but explicit grants go stale when a future
Alembic migration creates a table, while `pg_read_all_data` kept working and still could not write, run application
DDL, create databases / roles, replicate, bypass RLS or become superuser. Creating the role and wiring credentials is
a later, controlled operational step (14D.3 / 14D.6). Notes:
- `pg_database_size()` was diagnostic only and stays outside the required contract;
- the schema currently has **zero** public sequences, so this proof does not show that sequence SELECT is
  unnecessary for schemas that use sequences (`pg_read_all_data` covers sequences regardless);
- there is currently no RLS; if RLS is introduced, backup behaviour must be re-audited — `BYPASSRLS` is never added
  automatically.

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

- ~~`pg_dump --snapshot` orchestration detail (host wrapper vs tool-driven)~~ — decided in 14D.2C (§16: pg_dump
  inside the dedicated backup image over the Compose network); end-to-end scratch-PostgreSQL verification in 14D.2D.
- Dual-store configuration names / env-file template (14D.2).
- Integrity-checker wording for `MISSING_DERIVATIVE` (code text still says "regenerable from the original"; to be
  corrected in 14D.2, since code is out of scope for 14D.1).
- `age` recipients, key custody and offline copies; whether the private key may be present temporarily on the VM
  during a drill (14D.3).
- Exact Oracle IAM policy, overwrite / delete / conditional-PUT and ETag behaviour (14D.3 / 14D.4).
- Dedicated PostgreSQL backup role: policy frozen by the 14D.2D.4 proof (§16.6: LOGIN + CONNECT +
  `pg_read_all_data`, no elevated attributes); creation as a manual operational step before the first production
  backup (14D.3 / 14D.6). Production `age`
  recovery identities remain an owner action (14D.3).
- Recurring schedule (systemd timer) and RPO (before 14E).
