# Stage 14D — Backup / Restore Drill & Production Media-Readiness Gate (plan and contract)

> **Status:** 14D.1 architecture — **OWNER APPROVED** (2026-10-02, with the mandatory corrections A–D below
> incorporated). 14D.2A (snapshot primitive, §7.1) — COMPLETE / OWNER ACCEPTED (owner runs, 9/9, re-proven after hardening).
> 14D.2B (encrypted DB artifact primitive, §9.1) — COMPLETE / OWNER ACCEPTED (real-age round-trip proven, age 1.3.2).
> 14D.2C (backup execution image / container contract, §16) — COMPLETE, OWNER LOCAL IMAGE / RUNTIME VERIFIED (linux/amd64,
> 2026-10-03), owner accepted. Not yet proven: ARM64 production image, real PostgreSQL topology end-to-end,
> production DB role, production backup execution. 14D.2D (local backup orchestrator, owner decisions D1–D6 / corrections
> C1–C4) — IN PROGRESS: 14D.2D.1 pure contracts (§16.3) and 14D.2D.2 data root / lock / stale work / promotion
> (§16.4), 14D.2D.3 local orchestration + `db-dump` (§16.5) and 14D.2D.4 real PostgreSQL 16 snapshot / role proof
> (§16.6, owner-verified 8/8 on PostgreSQL 16.15; production backup-role policy frozen) and 14D.2D.5 Compose / runtime
> E2E proof (§16.7, owner-verified, FAIL count 0, amd64) complete. Not yet proven: ARM64 production image / bind,
> production backup execution. 14D.3 Oracle Object Storage / IAM provisioning (§16.8,
> `docs/STAGE_14D3_ORACLE_BACKUP_PROVISIONING.md`) — provisioning **COMPLETE / OWNER ACCEPTED** (2026-10-04); 14D.4
> connectivity / semantics smoke and the IMDS gate (`docs/STAGE_14D4_CONNECTIVITY_SEMANTICS_SMOKE.md`) — **COMPLETE /
> OWNER ACCEPTED** (2026-10-04). 14D.2E manifest v1 / COMPLETE.json / provenance core (§16.9) — **OWNER ACCEPTED**,
> pure (no I/O). 14D.2F Oracle backup writer (§16.10) — implemented, **OWNER ACCEPTED**, live drill-bucket smoke on
> the Oracle VM **PASS 9/9** (2026-10-04). 14D.2G media sync R2 → Oracle (§16.11) — implemented and tested on
> in-memory stores and the real S3 adapter, **OWNER ACCEPTED**, live drill smoke R2 → Oracle **PASS 11/11**
> (2026-10-04). 14D.2H verify of a sealed run in the target (§16.12) — implemented, **OWNER ACCEPTED**, live drill smoke
> on the Oracle VM **PASS 11/11** (2026-10-04). 14D.2I restore, slice 2I.1 — the database restore chain (§16.13) — implemented and proven with
> real age and PostgreSQL 16 in a development sandbox; the owner run with the production versions is NOT done yet.
> Slice 2I.2 — media restore into the destination bucket (§16.14) — implemented and tested on in-memory stores and the
> real S3 adapter; no live run yet. Slice 2I.3 — the OCI restore client, the whole restore chain and the media-restore smoke (§16.15) — implemented and
> proven with real tools in a development sandbox, and the owner live media-restore smoke on the Oracle VM
> **PASS 8/8** (2026-10-04, 10/10 synthetic objects removed afterwards); the database half of the restore on real data is
> still proven only by the development sandbox until the 14D.5 drill. 14D.2J — the `upload` and `restore` commands that wire all of this to the operator's environment (§16.16) — implemented
> and tested; not run live yet. 14D.5A — drill tooling and runbook draft (§16.17, `docs/STAGE_14D5_DRILL_RUNBOOK.md`) —
> implemented. 14D.5B — the isolated drill (§16.18) — **EXECUTED by the owner on 2026-10-05: steps 1–6 of §11 PASS** (seed through
> the real upload pipeline, `db-dump`, `upload`, restore of the database and of the media, integrity check before and after,
> serving 8/8; production Oracle backup bucket unchanged). 14D.6A — production-run tooling (`verify` command, uploader image, `backup-upload` service, production runbook draft; §16.19) —
> implemented, nothing run on production. Rest of the plan: 14D.6B–14D.7 — NOT STARTED: no production backup
> upload or media copy has run and no schedule exists yet. Executable procedures stay **DRAFT** until the sub-stage that
> verifies them.
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
| Oracle | `plan-estimate-backup-prod` | production backup target (versioning on) — renamed in 14D.3 (was `plan-estimate-media-backup`) |
| Oracle | `plan-estimate-backup-drill` | drill backup target — renamed in 14D.3 (was `plan-estimate-media-drill-backup`) |
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
assumed here.** 14D.3 design (§16.8): Oracle documents separate `OBJECT_CREATE` / `OBJECT_OVERWRITE` / `OBJECT_DELETE`
permissions, so the backup identity is create + inspect + read only (no overwrite / delete); approved (O1–O7): an
Instance Principal used by a separate uploader, gated on the 14D.4 IMDS-isolation proof; the restore identity stays off
the production VM. The policy statements stay PROPOSED until 14D.4 proves them empirically.

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
  There is **no** fallback to plain `rename`, `replace` or copy. Support on the actual Compose bind mount was proven by
  the owner 14D.2D.5 E2E on the local amd64 host; the ARM64 production host remains to be proven before 14D.6.
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

### 16.7 Compose / runtime E2E proof (Stage 14D.2D.5 — COMPLETE / OWNER VERIFIED)

Proves the **actual operational command** with the **production** `backup` service definition, against scratch
resources only:

    docker compose --env-file <scratch proof env> -p plan-estimate-14d2d5-proof \
      -f docker-compose.prod.yml -f backend/tests/runtime_proof/compose.proof-override.yml \
      run --rm --no-deps backup db-dump

The production Compose file already satisfies the accepted contract (14D.2C + D1 / D6) and is **not** changed. The
scratch override (`backend/tests/runtime_proof/compose.proof-override.yml`) changes no security control; it only adds a
non-secret `PE_PROOF_GUARD` variable whose `${VAR:?}` interpolation makes Compose refuse to run unless every scratch
variable is set, so a missing scratch env cannot fall back to production defaults (step 0 proves the refusal).

**Topology:** project `plan-estimate-14d2d5-proof`; network `plan-estimate-14d2d5-proof_internal` pre-created
`--internal` (no internet egress) with the Compose project / network labels so the service's `internal` network
resolves to it; disposable `postgres:16-alpine` (`pe14d2d5-proof-pg`, password from a mounted file, no published
port) on that network only; fresh `/tmp/pe-14d2d5-proof.*` root with `data/` (→ `/backup`) and `secrets/pgpass`
(→ `/run/secrets/pgpass`, read-only); disposable age identity; scratch database `pe_scratch_test_14d2d5` migrated to the
repository head with 2 READY / 1 PENDING / 1 FAILED assets; scratch backup role created with the **frozen 14D.2D.4
policy** (LOGIN + CONNECT + `pg_read_all_data`, no elevated attributes) — only in the disposable server. Host-side
`docker exec` / tool containers are scaffolding only (C3); the backup itself always runs through the real service.

**Tooling** (`backend/tests/runtime_proof/`): `bind_ops` runs **inside the real `backup` service** (entrypoint override
only; all hardening in force) — `self-inspect` (`/proc/self/status` + `mountinfo`: non-root, all capability sets 0,
NoNewPrivs 1, ro root + write probe, tmpfs `/tmp`, single rw `/backup`, ro pgpass outside `/backup`, no Docker
socket), `egress-check`, `promote-proof` (production `create_run` / `promote` on the real bind: same `st_dev`, atomic
appearance, collision refused, `renameat2(RENAME_NOREPLACE)` refuses an empty destination, no overwrite; removes only
its own synthetic runs), `hold-lock` / `try-lock` (production `RunLock`); `scratch` runs in a separate tool
container (setup, independent decrypt / gunzip / restore / digest verification, a `pe_proof_block` lock holder,
tagged-session check); `check_host` runs on the host with the standard library only (bind layout / persistence,
`docker inspect` of the backup container, postgres and network). `owner_proof.sh` runs all steps in order and prints a
PASS / FAIL summary; it never cleans up automatically.

**Steps / PASS criteria:** 0 missing scratch env refused · 1 image build (PGDG key + age verified), scratch setup ·
K postgres unpublished, network internal with proof containers only, no egress from the backup container · D
`db-dump` exit 0; host shows exactly one `encrypted/<run_id>/` (artifact + `local-run.json`, 0600 / 0700), empty `work/`
and `evidence/`, no plaintext, evidence complete, revision = head, SHA / size match, `run.lock` 0600; independent
decrypt → gunzip → restore → READY digest / revision = source + evidence · F no backup container remains, artifact
hash stable later · E in-container self-inspection and `docker inspect` (non-root user, ReadonlyRootfs, CapDrop ALL,
no-new-privileges, not privileged, no ports, single `/backup` bind, ro pgpass outside it on the host, tmpfs `/tmp`,
512 MiB / 0.5 CPU / 64 pids, StopTimeout 45, init, proof network only) · G promotion proof on the bind, real run
untouched · H lock held by container A → second container and the real `db-dump` get exit 3; after `docker stop`
(SIGTERM) and after `docker kill -s KILL` the lock is acquirable; `run.lock` persists · I synthetic stale entry →
`db-dump` exit 4, entry untouched, nothing promoted, no evidence; operator removes only the synthetic entry · J
`pe_proof_block` held ACCESS EXCLUSIVE so the real `db-dump` waits in pg_dump; `StopTimeout` 45; `docker stop` →
exit 6 well under the grace period, no tagged server session left, lock released, interrupted run left in `work/`,
`CANCELLED` failure evidence, nothing promoted; then the operator clears it and a second normal run succeeds · L no
backup / superuser password and no age identity anywhere under the data root or in the logs.

**Owner command:** from the repository root, `bash backend/tests/runtime_proof/owner_proof.sh`; send back the printed
summary (contains no secret). **Cleanup (proof-only, after review):**

    docker stop pe14d2d5-proof-pg 2>/dev/null           # --rm removes it and its anonymous volume
    docker ps -a --filter label=com.docker.compose.project=plan-estimate-14d2d5-proof -q | xargs -r docker rm -f
    docker network rm plan-estimate-14d2d5-proof_internal
    rm -r /tmp/pe-14d2d5-proof.XXXXXX                   # the workspace printed by the script

Known risk (did not materialise): Compose versions differ in how strictly they accept a pre-created network; the
owner's Compose accepted the labelled internal network.

**Owner-run result (2026-10-03): FAIL count 0** (local amd64 host; workspace `/tmp/pe-14d2d5-proof.3BxTqN`; completed
runs `20261003T213210Z-faa37747`, `20261003T213846Z-158c6649`). The proof used the **real production `backup`
service** of the unchanged `docker-compose.prod.yml` plus only the scratch guard override; `backend/app/` and
`backend/Dockerfile.backup` were not changed in 14D.2D.5.
- **Fail-closed / setup:** missing scratch env refused by the guard; scratch database at the current head, 2 READY;
  frozen backup-role policy used.
- **Network:** PostgreSQL without published port and only on the proof network; network internal and
  Compose-labelled; no internet egress from the backup container.
- **Real command:** `docker compose … run --rm --no-deps backup db-dump` exit 0.
- **Persistence / restore:** one complete run on the host bind; `work/` and `evidence/` empty; artifact SHA-256 /
  size correct; `run.lock` correct; independent decrypt → gunzip → restore with READY digest and revision verified; no
  backup container left after `--rm`; the first artifact unchanged after all later proof operations.
- **Runtime hardening (effective):** non-root; effective capabilities zero; NoNewPrivs; read-only root; tmpfs `/tmp`;
  writable `/backup`; pgpass read-only and outside `/backup`; no Docker socket; one `/backup` bind; resource limits
  effective; StopTimeout 45; proof network only.
- **Promotion on the real bind:** production code; same `st_dev`; atomic; collision refused; no overwrite; real run
  untouched.
- **Lock:** held lock → second container exit 3 and real `db-dump` exit 3; acquirable after normal SIGTERM stop and
  after SIGKILL (exit 0); `run.lock` persisted 0600.
- **Stale work:** real `db-dump` exit 4; entry untouched; nothing promoted; no evidence.
- **SIGTERM:** StopTimeout 45; real `db-dump` interrupted, exit 6 in 1 s (well before the grace period); no tagged
  dump session left; lock released; interrupted run left in `work/`; `CANCELLED` evidence; after operator cleanup a
  second normal backup exited 0 and verified.
- **Secrets:** backup password, superuser password and age identity absent from data and logs.
- **Observed noise:** Compose printed interpolation warnings for unrelated production variables (`APP_DOMAIN`,
  `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `JWT_SECRET_KEY`) because the scratch env
  defines only backup variables; harmless for the backup proof, production Compose intentionally not changed.

### 16.8 Oracle Object Storage / IAM provisioning design (Stage 14D.3 — DESIGN APPROVED, PROVISIONING NOT YET EXECUTED)

Full design and owner Console runbook: `docs/STAGE_14D3_ORACLE_BACKUP_PROVISIONING.md` (nothing executed). Owner
decisions 2026-10-04:

- **O1 APPROVED** — Instance Principal for the future uploader; dedicated API-key IAM user only if Instance Principal
  proves impractical or cannot be safely isolated.
- **O2 APPROVED** — `backup` stays local-only (database, pgpass, writable `/backup`, no Internet, no OCI / R2
  authority); a separate future `backup-upload` service (no database, no pgpass, `/backup` read-only, controlled
  outbound HTTPS, R2 read-only, narrowly scoped OCI backup authority). No runtime change now.
- **O3 APPROVED** — native OCI API via a pinned official OCI SDK in the uploader; Oracle is not forced through the S3
  adapter.
- **O4 APPROVED WITH MANDATORY GATE** — Instance Principal only if 14D.4 proves on the actual production Docker host
  that IMDS access is restricted to the uploader boundary; **no real (production-bucket) uploader authority before that
  proof**; otherwise reconsider the API-key fallback. Hence the uploader policy is phased: drill bucket only in 14D.3,
  production bucket only after 14D.4 PASS and separate owner approval.
- **O5 APPROVED** — create-only IAM + required read / inspect; no `OBJECT_OVERWRITE` / `OBJECT_DELETE` /
  `OBJECT_VERSION_DELETE`; **versioning enabled**; **no retention rule** (Oracle: retention rules cannot be added while
  versioning is enabled, versioning cannot be enabled with active retention rules) — retention lock is not part of
  v1; no lifecycle deletion; immutable keys; `COMPLETE.json` last.
- **O6 APPROVED** — restore authority and age identities never permanently on the production VM.
- **O7 APPROVED** — compartment `plan-estimate-backup` under the `kukhmax` root.
- **O8 DEFERRED HARDENING** (not a 14D readiness gate, not a prerequisite for `PHOTO_UPLOADS_ENABLED`) — a second
  encrypted DB backup outside OCI (offline copy, private R2 DB bucket or another provider) against Oracle account /
  region / administrative failure; nothing provisioned or implemented for it.
- **Buckets renamed (owner):** `plan-estimate-backup-prod` and `plan-estimate-backup-drill` (they hold media **and**
  DB backups); accepted §5 layout unchanged.
- **IAM statements are PROPOSED** until the OCI Console accepts them and 14D.4 proves on the drill bucket: create of a
  new object; HEAD / GET as designed; list only as required; overwrite, object delete, version delete and bucket
  mutation **denied**; native `if-none-match: *` refuses an existing name; restore principal cannot write; IMDS
  reachable from the uploader boundary only.
- **age custody:** recipients only on the VM / uploader; ≥ 2 independently stored owner copies of the identities off
  the VM; the 14D.5 drill decrypts with a copy brought from outside the VM.
- **ARM64 gate before 14D.6** (not performed now): arm64 image build / run; Python 3.12; pg_dump 16; age 1.3.2;
  non-root hardening; actual `/backup` filesystem; `renameat2(RENAME_NOREPLACE)`; fsync; `flock`; encrypted scratch
  backup + independent restore.
- **Gap for the later media / manifest stage:** the uploader needs the READY asset list of the same snapshot; the
  14D.2D.3 metadata hook can read it in the imported snapshot without changing 14D.2A.

### 16.9 Manifest v1, COMPLETE.json and SHA-256 provenance core (Stage 14D.2E — pure)

Implementation: `backend/app/backup/manifest.py`; tests `backend/tests/test_stage14d2e_manifest.py` (153). No I/O, clock,
randomness or network: bytes and plain values in, bytes and plain values out, so the uploader, `verify` and restore
tooling (14D.2F–I) share one definition of "a valid backup run". It implements §6, §7, §8 and §10 exactly:

- **Canonical JSON Lines.** `header`, then one `object` line per required object sorted by key, then `summary`; each
  line sorted-keys / compact / ASCII / `\n`-terminated (the 14D.2D.1 serialization). `parse_manifest` accepts only
  the exact bytes the builder produces (re-serialization must equal the input), so `sha256(manifest bytes)` is well
  defined; duplicate JSON fields, `NaN`, floats, booleans-as-integers, unknown / missing fields, CRLF, blank lines and
  lines over 4 KiB are refused. Golden digests of a reference manifest and COMPLETE.json are pinned in the tests.
- **Self-verifying completeness (§7).** Every READY asset has exactly three object lines (original, display,
  thumbnail) with keys fixed by the 14B key layout and a content type consistent with the key; the object lines
  alone must reproduce the header's `ready_set_sha256` (the 14D.2A digest) and `ready_count`; the summary must equal
  the counts / byte sum of the lines; an object cannot be verified before the run started; source and target bucket
  must differ; `db_dump.key` must be `db/<run_id>/plan-estimate.sql.gz.age`; recipients are 1..32 distinct native
  `age1…` public recipients (private keys and SSH keys are refused). `verify_against_ready_set` compares the manifest
  with a READY set from the snapshot (backup time) or from a restored database (restore time) and reports counts only
  (`not_in_manifest`, `not_in_ready_set`, `changed`).
- **Sealing.** `build_complete` derives `COMPLETE.json` (canonical single line, fields as in §6) from a validated
  manifest; `verify_run(complete_bytes, manifest_bytes)` requires the recorded manifest SHA-256 to equal the stored
  manifest's, re-parses and re-validates the manifest, and compares run id, object / byte / asset counts, READY-set
  digest and encrypted-dump SHA-256; `completed_at` may not precede the run's own timestamps. Only `verify_run`
  yields a `VerifiedRun`, the type that `decide_provenance` accepts as a prior run.
- **Provenance (§8).** `decide_provenance` returns *inherit* only when the prior run is verified, the same key and size
  are recorded there, the target object exists with that size and (for originals) the recorded SHA-256 equals the
  database SHA-256; any other case, `--deep`, or no prior run is a *download* with a machine-readable reason. A fresh
  copy is always `downloaded`; an inherited run id must be strictly earlier than the manifest's own run. Provider
  ETags are never an input.
- **What the internal checks do not cover (by design).** The database stores only the original's SHA-256, so a changed
  *derivative* SHA-256 is internally consistent; it is caught by the COMPLETE.json seal (manifest hash) and by the
  restore-time check of every object against the manifest (§10). A run with any failed object produces no manifest
  and no COMPLETE.json (§15); its error report is a separate artifact (14D.2G).
- **Not in this stage:** reading / writing any storage, building the object list, the transfer loop, selecting the
  prior run, the `verify` and `restore` commands (14D.2F–I).

### 16.10 Oracle backup writer (Stage 14D.2F)

Implementation: `backend/app/backup/target.py` (provider-neutral port, verified puts, run publication, in-memory test
double), `backend/app/backup/oci_target.py` (OCI adapter), `backend/scripts/stage14d2f_oci_writer_smoke.py` (owner live
smoke, drill bucket only). Tests: `test_stage14d2f_target.py` (36), `test_stage14d2f_oci_target.py` (61),
`test_stage14d2f_writer_smoke.py` (8). It builds on the 14D.4 findings (create-only IAM, `If-None-Match: *` → 412, no
overwrite / delete, masked 404, body-less HEAD errors) and on the §16.9 manifest core.

- **Port with no destructive verb.** `BackupTarget` has exactly `put_new` (create-only: `CREATED` | `EXISTS`), `head`
  and `download_to` (new local file). There is no delete, overwrite, multipart or listing, mirroring the uploader
  principal's `OBJECT_CREATE` + read / inspect IAM (14D.3 §6.2). Single `PutObject` only: multipart needs
  `OBJECT_OVERWRITE`; one PutObject carries up to 50 GiB, far above any object written here.
- **`put_verified` (plan §10 "post-copy").** Local SHA-256 and size → create-only put with `Content-MD5` and
  `Content-Length` → HEAD size → full re-download → SHA-256 comparison. If the object already exists (an ambiguous
  earlier put, or a resumed run) it is accepted only when the downloaded bytes equal the local bytes
  (`created=False`); different bytes raise `MediaObjectConflict` and nothing is overwritten. Optional
  `expected_sha256` / `expected_size` guard against the source changing between hashing and upload.
- **Retries.** Only `MediaStorageUnavailable` (HTTP 408 / 429 / ≥ 500, transport errors) is retried: 4 attempts,
  exponential backoff 1 s × 2, capped. Misconfiguration, conflict, verification failure and local errors are final.
  The SDK's own retries are disabled so the policy lives in one place.
- **`publish_run` (order is the safety property).** Validate the dump against the header and build the manifest
  locally → upload the encrypted dump → upload `manifest.jsonl` → HEAD every object the manifest lists
  (`_require_objects_present`) → `build_complete` → upload `COMPLETE.json` **last**. A run that stops anywhere before
  the last step has no seal and is incomplete by definition (§6); no cleanup by deletion exists. Re-publishing the same
  run with a different seal is refused (`MediaObjectConflict`).
- **OCI adapter.** Native OCI API (not the S3 layer) with the VM's instance principal — no key file, no secret on
  disk. Error mapping: 408 / 429 / ≥ 500 / transport → `MediaStorageUnavailable`; 401 / 403 and masked 404
  (`BucketNotFound`, `NamespaceNotFound`, `NotAuthorizedOrNotFound`) → `MediaStorageMisconfigured`; 404 on HEAD / GET →
  absent / `MediaObjectNotFound`. HEAD errors carry no code, so a body-less 404 means "absent". Local I/O errors are
  not mapped as transient. Downloads are streamed into an exclusively created file (`O_EXCL | O_NOFOLLOW`, mode 0600),
  size-checked and removed on failure. Error messages and `repr` never contain the namespace, OCIDs, tokens or
  response bodies. `oci` is imported lazily (`oci==2.187.1` pin); no SDK is needed to import the module or run tests.
- **Test evidence.** In-memory target with fault injection (transient, ambiguous put with / without effect, corrupted
  store, object hidden after put); a real-SDK contract check against `oci==2.187.1` with a stubbed transport (not part
  of the suite; SDK installed in a scratch venv only); mutation check — 10 deliberate defects in the writer each made
  a test fail.
- **Owner live smoke (PASS 9/9, 2026-10-04, Oracle VM, instance principal, drill bucket).**
  `stage14d2f_oci_writer_smoke.py` runs the production write path against the drill bucket with synthetic data only
  (random bytes as the "dump", an empty-READY-set manifest, its COMPLETE.json). 9 checks: put created, identical put
  idempotent, different bytes refused, object unchanged, `publish_run` zero-asset, stored run verifies (`verify_run`),
  stored dump equals local, re-publish with a different seal refused, seal unchanged. Owner result:
  `RESULT: PASS (9/9 checks passed)`, `exit=0`, drill run id `20261004T160719Z-b374f2d1`. Refuses any bucket whose
  name does not contain `drill`. Exit codes: 0 PASS, 1 a check failed, 2 cannot run (including SDK missing or no
  namespace), 3 no instance principal. Objects stay in the drill bucket (`smoke/14d2f/<run_id>/…`, `db/<run_id>/…`,
  `runs/<run_id>/…`); cleanup is a manual administrator step. The namespace comes from `OCI_NAMESPACE` at run time and
  is never stored in the repository.

  Verified command (run in the repository root on the VM; the backend imports need `sqlalchemy`, `pydantic`,
  `pydantic-settings`, `pyjwt`, `asyncpg` besides `oci`):

  ```bash
  IMG='python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f'
  RUN='pip install -q --no-cache-dir --target /tmp/deps "sqlalchemy[asyncio]==2.1.1" greenlet==3.5.6 pydantic==2.13.5 pydantic-settings==2.15.0 pyjwt==2.15.0 asyncpg==0.31.0 oci==2.187.1 && PYTHONPATH=/tmp/deps python /app/scripts/stage14d2f_oci_writer_smoke.py'
  docker run --rm --network pe-upload --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
    -e OCI_NAMESPACE -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$PWD/backend":/app:ro "$IMG" sh -c "$RUN"
  ```

  Run-time notes from the owner run: `--cap-drop ALL` removes root's permission bypass, so the container must run as
  the checkout's owner (`--user`; some source files are mode 0600) and install dependencies into a writable
  `--target`; only `backend/` is mounted, so `.env.production` and other root-level secrets are not visible.
- **Not in this stage:** reading R2, the media transfer loop and prior-run selection (14D.2G), `verify` (14D.2H),
  `restore` (14D.2I), production execution, schedule. Uploads stay OFF.

### 16.11 Media sync R2 → Oracle (Stage 14D.2G)

Implementation: `backend/app/backup/media_sync.py`; live smoke `backend/scripts/stage14d2g_media_sync_smoke.py`. Tests:
`test_stage14d2g_media_sync.py` (60), `test_stage14d2g_smoke.py` (17). It composes the accepted pieces — READY set
(14D.2A), `decide_provenance` / `VerifiedRun` (14D.2E), `put_verified` / `publish_run` (14D.2F) — into the copy loop of
§5 and the failure behaviour of §15. A small manifest helper was added for it: `expected_content_type(role, asset_id,
key)` (the 14B key layout, previously a private table); `target.retrying` is now a public alias of the retry helper.

- **Input and unit of work.** `sync_media(source, target, assets=…, run_id, target_bucket, scratch_dir, prior, deep)`
  takes the snapshot's READY assets and handles their three objects (original, display, thumbnail) one at a time, in
  canonical order (asset id text, then role). Invalid input — duplicate asset, a key that is not valid for its role,
  bad run id — is refused before any storage call.
- **Target object missing → copy.** Download the source object into a fresh 0700 scratch directory, check the size
  (all roles) and — for originals — the SHA-256 against the database row, then `put_verified` (create-only put, HEAD,
  full re-download, SHA-256). Action `copied`, provenance `downloaded`. If an earlier, ambiguous attempt of this tool
  already created the object, the identical bytes are proved and the line is `already_present` / `downloaded`.
- **Target object present → admitted only per §8.** (a) *Inherit*: the prior run is sealed, lists this key with the
  same size and trusted SHA-256, the object exists with that size and (originals) the recorded SHA-256 equals the
  database row → `already_present`, `inherited:<run_id>`, nothing downloaded. (b) Otherwise (no prior run, `deep`,
  key / size not recorded, …): the **source** object is downloaded and checked, the **target** object is downloaded,
  and the two SHA-256 values must be equal; the line is `already_present` / `downloaded`. A target object of a
  different size is refused on the HEAD size alone, without any download. *Why the source comparison:* the target is
  write-once, so a same-size but different object (corruption, an aborted foreign write) would otherwise be recorded
  with its own hash and locked into the backup for good, with the good source copy never written.
- **Failures are per object and machine readable** (`ObjectFailure(asset_id, role, code)`; never a key, hash or
  provider message): `MISSING_SOURCE` (evidence loss), `SOURCE_SIZE_MISMATCH`, `SOURCE_SHA_MISMATCH`,
  `SOURCE_UNAVAILABLE`, `TARGET_CONFLICT` (never overwritten), `TARGET_VERIFICATION_FAILED`, `TARGET_UNAVAILABLE`,
  `SOURCE_LISTING_FAILED`. The run continues so the report is complete (§15), but `MediaSyncResult.complete` is
  False and `objects_for_publication()` raises `MediaSyncIncomplete`: a manifest or COMPLETE.json cannot be built from
  a partial copy. A misconfigured store (any non-transient storage error: permission, bucket, disabled) aborts the
  run at once (`SOURCE_MISCONFIGURED` / `TARGET_MISCONFIGURED`), as do 5 consecutive unavailable-store failures
  (`STORAGE_UNAVAILABLE`; the streak resets on any other outcome). Unexpected exceptions (programming errors, a full
  scratch disk, cancellation) are not translated: they propagate, scratch is removed, and the run has no seal.
- **Source listing.** After the loop the source store is listed under `photos/v1/` once: `source_keys` is the number
  of keys, `orphan_candidates` the number not in the required set (objects of PENDING / FAILED assets and objects
  uploaded after the snapshot are therefore counted as candidates; nothing is copied or deleted). A listing failure
  makes the run incomplete (the summary needs the counts).
- **Prior run.** The prior run is named explicitly (`load_prior_run(target, run_id)`): it downloads
  `runs/<run_id>/COMPLETE.json` and `manifest.jsonl` and applies `verify_run`. A missing, unsealed or inconsistent run
  is a `PriorRunError`, never a silent "no prior run"; a persistent outage propagates as `MediaStorageUnavailable`.
  `sync_media` additionally requires the prior run to be strictly earlier and written to the **same target bucket** (a
  manifest from another bucket proves nothing about this one). Choosing the latest sealed run by listing `runs/` is
  not part of this stage.
- **Error report.** `MediaSyncResult.report_bytes()` is a canonical one-line JSON (`plan-estimate/media-sync-report/v1`):
  run id, completeness, abort reason, counts, source / orphan counts, failures. It contains no key, hash or provider
  text. Persisting it (local evidence directory) and the exit code belong to the command that drives the run; it is
  not uploaded to the target (no new remote layout element).
- **Test evidence.** Engine against in-memory source / target with fault injection (transient and persistent source
  and target errors, an ambiguous put with and without effect, store corruption, objects invisible after the put,
  misconfiguration, streaks, cancellation, scratch hygiene); the production `S3MediaStorage` as the source through a
  fake boto3 client (download, paginated listing, response bodies closed, 404 → missing source); a mutation check —
  20 deliberate defects in the engine, all caught (two initially survived and led to a stronger test and the removal
  of an unreachable check); and a negative property: no key is ever written twice.
- **Owner live smoke (PASS 11/11, 2026-10-04, Oracle VM, R2 drill source → Oracle drill bucket, instance principal).** `stage14d2g_media_sync_smoke.py` runs the production path R2 drill source →
  Oracle drill bucket with synthetic assets (three good assets, three planted problems, two junk source keys): run 1
  copies everything and is published; run 2 inherits everything with zero downloads from either store; run 3 (`deep`)
  verifies all nine objects by download and compares them with the source; run 4 reports exactly the planted failures
  (a missing source object, an original that differs from the database SHA-256, a target object holding other bytes),
  is not publishable and leaves the planted target object untouched; the listing counts and the secret-free report
  are checked. 11 checks, exit codes 0 PASS / 1 FAIL / 2 cannot run / 3 no instance principal. It refuses a bucket
  without "drill" in its name and equal R2 and Oracle buckets. The synthetic R2 objects are deleted at the end; the
  Oracle objects stay (no delete permission by design) and their prefixes are printed for the administrator.
  Owner result: `RESULT: PASS (11/11 checks passed)`, `exit=0`; 9 objects copied (196608 bytes) in run 1, 9 inherited
  with 0 downloads and 0 writes in run 2, 9 verified by download in run 3, exactly the 3 planted failures in run 4
  (9 inherited, 6 copied), `source keys 19 (baseline 0, good 9, planted 8, junk 2)`, `cleanup: 19/19 synthetic R2
  objects removed`. Drill run ids `20261004T172411Z-06f3cfbc` … `-9432291f`; only runs 1 and 2 are published
  (`db/<run_id>/…`, `runs/<run_id>/…`), runs 3 and 4 wrote no run-level objects. The one line
  `media storage error: MediaObjectNotFound (code=NoSuchKey, status=404)` on stderr is the S3 adapter's log of the
  planted missing source object, not a failure. Six `photos/v1/<uuid>/` prefixes stay in the Oracle drill bucket for the
  administrator's cleanup.

  Configuration: the R2 drill-source token in an env file (`R2_*`, as in 14D.4; on the VM
  `~/backups/plan-estimate/drill-secrets/r2-drill-source.env`, chmod 600, outside the repository) and `OCI_NAMESPACE`.
  Verified command (`--env-file` points at that file):

  ```bash
  IMG='python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f'
  RUN='pip install -q --no-cache-dir --target /tmp/deps "sqlalchemy[asyncio]==2.1.1" greenlet==3.5.6 pydantic==2.13.5 pydantic-settings==2.15.0 pyjwt==2.15.0 asyncpg==0.31.0 oci==2.187.1 boto3==1.43.103 botocore==1.43.103 s3transfer==0.19.2 urllib3==2.8.0 anyio==4.15.1 && PYTHONPATH=/tmp/deps python /app/scripts/stage14d2g_media_sync_smoke.py'
  docker run --rm --network pe-upload --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
    --env-file ~/backups/plan-estimate/drill-secrets/r2-drill-source.env -e OCI_NAMESPACE -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$PWD/backend":/app:ro "$IMG" sh -c "$RUN"
  ```
- **Not in this stage:** the command that ties snapshot, dump, encryption, sync and publication together, local
  evidence / exit codes, selecting the latest prior run, concurrency (v1 is strictly sequential), `verify` (14D.2H),
  `restore` (14D.2I), the drill (14D.5), production runs (14D.6). Uploads stay OFF.

### 16.12 Verification of a sealed run in the target (Stage 14D.2H)

Implementation: `backend/app/backup/verify.py`; live smoke `backend/scripts/stage14d2h_verify_smoke.py`. Tests:
`test_stage14d2h_verify.py` (37), `test_stage14d2h_smoke.py` (17). A small refactor supports it: the read side of the
backup target is now its own port, `target.BackupReader` (`head`, `download_to`); `BackupTarget` is unchanged and
`media_sync.load_prior_run` accepts any `BackupReader`.

- **Scope.** `verify_run_in_target(reader, run_id, mode, expected_recipients)` proves from the stored bytes alone that a
  run in the backup target is what its COMPLETE.json says. It needs **no secret and no database**: decrypting the dump
  with a private age identity, restoring it into a scratch PostgreSQL and recomputing the READY-set digest from the
  restored database (§7, §9) are restore concerns and stay in 14D.2I.
- **Checks.** *Seal:* `COMPLETE.json` and `manifest.jsonl` exist and `verify_run` accepts them (manifest SHA-256 equals
  the sealed value, counts and digests agree) and the sealed run id is the one asked for. *Recipients (optional):* every
  public age recipient the caller expects is among the manifest's (a private key or SSH key as "expected" is refused
  before anything is read). *Dump:* exists with the recorded size; FULL also re-hashes it against the manifest. *Objects:*
  every object line exists with the recorded size; FULL also downloads it and compares its SHA-256 with the manifest.
  FULL never trusts provenance: `inherited:<run>` lines are verified by download like any other.
- **Modes.** QUICK = two documents plus one HEAD per object and the dump; it cannot see same-size changes and relies on
  the seal for content (documented, tested). FULL = every byte. Strictly sequential, one scratch directory (0700) per
  download, always removed.
- **Result.** `VerifyReport` with run-level problems (`SEAL_MISSING`, `MANIFEST_MISSING`, `SEAL_INVALID`,
  `RECIPIENTS_MISMATCH`, `DUMP_MISSING`, `DUMP_SIZE_MISMATCH`, `DUMP_SHA_MISMATCH`), per-object problems tied to asset
  id and role (`MISSING_OBJECT`, `SIZE_MISMATCH`, `SHA_MISMATCH`, `UNAVAILABLE`), counts (objects, size checks, SHA checks,
  bytes hashed, lines with inherited vs downloaded provenance) and `ok`. A run whose seal cannot be established
  reports nothing about its objects (an unproven manifest is not trusted). Every problem is collected; the check of
  the remaining objects continues. A misconfigured store (any non-transient storage error) or 5 consecutive
  unavailable-store failures abort the checks (`AbortReason`); a persistent outage while reading the seal or the
  dump also aborts. Transient errors are retried with the §16.10 policy. Unexpected exceptions and cancellation
  propagate and scratch is removed. `report_bytes()` is a canonical one-line JSON (`plan-estimate/verify-report/v1`),
  secret-free: problem codes, asset ids and roles only; at most 200 problems listed, per-code totals always complete.
- **Read-only by construction.** The port has no write verb; the tests assert that a verification issues only `head`
  and `download_to`, and the live smoke wraps the genuine target in a read-only reader.
- **Test evidence.** A published run (real `sync_media` + `publish_run` on in-memory stores) verified in both modes;
  every problem code produced from a deliberately damaged run (deleted / resized / bit-flipped objects and dump,
  tampered or foreign seal, missing documents, recipient mismatch); retries, streak and misconfiguration aborts,
  cancellation and scratch hygiene; mutation check — 21 deliberate defects in the verifier, all caught; the smoke's
  own checks are tested against a blind, a noisy, a greedy and a leaking verifier so that they cannot pass vacuously
  (14 mutations of the smoke, all caught after strengthening).
- **Owner live smoke (PASS 11/11, 2026-10-04, Oracle VM, instance principal, drill bucket).** `stage14d2h_verify_smoke.py` verifies runs that the 14D.2G smoke published in the
  Oracle drill bucket, with the instance principal. **Nothing is written**: negative cases are injected on the client
  side of a genuine stored run (a flipped byte in an object or in the dump, a HEAD size off by one, a HEAD answering
  "absent", a fresh run id, a recipient that is not in the manifest). Checks: full verify passes; quick verify
  downloads only the two documents; the inherited run (`--run-id-2`) is verified by download; unknown run → seal
  missing; recipient mismatch; accepted real recipients (`--expect-recipient`); each injected fault is reported for
  exactly the affected object (or the dump) and nothing else; the report is secret-free. Exit codes 0 PASS / 1 FAIL /
  2 cannot run / 3 no instance principal; drill buckets only. Owner result: `RESULT: PASS (11/11 checks passed)`,
  `exit=0`, on the two runs of the 14D.2G smoke (`20261004T172411Z-06f3cfbc`, `20261004T172412Z-faaf3559`): full verify
  9 objects / 196608 bytes hashed with the dump SHA-256 matching; quick verify 9 sizes by HEAD and exactly 2 documents
  downloaded; the inherited run (9 inherited lines) verified by download; unknown run → `SEAL_MISSING`; foreign
  recipient → `RECIPIENTS_MISMATCH`; the 2 real (synthetic) recipients accepted; flipped bytes → `SHA_MISMATCH`, HEAD
  size off by one → `SIZE_MISMATCH`, HEAD "absent" → `MISSING_OBJECT`, each for the one affected object only; a changed
  dump → `DUMP_SHA_MISMATCH`; the report free of names, hashes and recipients. Verified command (same container recipe
  as §16.10; the 14D.2F dependency set is enough):

  ```bash
  Q="age1$(printf 'q%.0s' {1..58})"; P="age1$(printf 'p%.0s' {1..58})"   # the synthetic recipients of the 14D.2G drill
  RUN='pip install -q --no-cache-dir --target /tmp/deps "sqlalchemy[asyncio]==2.1.1" greenlet==3.5.6 pydantic==2.13.5 pydantic-settings==2.15.0 pyjwt==2.15.0 asyncpg==0.31.0 oci==2.187.1 && PYTHONPATH=/tmp/deps python /app/scripts/stage14d2h_verify_smoke.py --run-id <run 1> --run-id-2 <run 2> --expect-recipient '"$Q"' --expect-recipient '"$P"
  docker run --rm --network pe-upload --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
    -e OCI_NAMESPACE -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$PWD/backend":/app:ro "$IMG" sh -c "$RUN"
  ```
- **Not in this stage:** the OCI API-key (restore principal) client factory, decryption, scratch PostgreSQL, READY-set
  recomputation, media restore and the restore-time integrity checker (all 14D.2I), the command that ties
  backup and verify together, listing `runs/` to find the latest sealed run, a sampling mode. Uploads stay OFF.

### 16.13 Database restore chain (Stage 14D.2I.1)

Implementation: `backend/app/backup/restore_guards.py` (scratch-database and identity-file guards),
`backend/app/backup/restore_db.py` (the chain and its checks). Tests: `test_stage14d2i1_restore_guards.py` (36),
`test_stage14d2i1_restore_db.py` (72; fake `age` / `age-keygen` / `psql` child processes and a fake PostgreSQL
connection), `test_stage14d2i1_real.py` (17, opt-in, real age and real PostgreSQL 16). 14D.2I is delivered in
slices: **2I.1 database restore (this section)**, 2I.2 media restore into the drill-restore bucket, 2I.3 the OCI
API-key client for the restore principal and the live smokes (the full chain on real data is the 14D.5 drill).

`restore_database(reader, run, database=…, identity_file=…, scratch_dir=…)` takes a sealed run (`load_prior_run`), the
read side of the backup target (`BackupReader`) and an age identity, and returns a `DbRestoreReport`. Steps, cheap and
local first; nothing is written anywhere before the guards pass:

1. **Guards.** *Scratch database* (`restore_guards.validate_restore_database`): the name contains `pe_restore_scratch`,
   the host is loopback, contains `scratch`, or is explicitly allowed, and the pgpass file satisfies the 14D.2C
   contract. *Identity file*: absolute, regular, not a symlink, owned by the effective user, no group / other bits,
   at most 64 KiB, holds an `AGE-SECRET-KEY-1…` line; its content is never returned or printed. Then `age-keygen -y`
   derives the public key, which must be one of the manifest's recipients (`IDENTITY_NOT_A_RECIPIENT` otherwise —
   a wrong key is reported before a possibly large download).
2. **Database preflight.** Reachable, `current_database()` equals the configured name, and **empty** (no relation
   outside the system schemas): the last line of defence against a mis-aimed restore, because a production database
   is never empty.
3. **Artifact.** `db/<run_id>/plan-estimate.sql.gz.age` is downloaded into a private (0700) scratch directory; its size
   and SHA-256 must equal the manifest's **before** age sees a byte.
4. **Load.** `age --decrypt -i <identity> <artifact>` → incremental gunzip (one member; CRC32 / ISIZE checked; output
   bounded per call; a cap on the plaintext size) → `psql -X -q -v ON_ERROR_STOP=1 --single-transaction --no-password
   -f -`, with libpq settings from the `PgConnectionConfig` (pgpass only, no password anywhere). The plaintext SQL
   exists only in pipes. **Commit gate:** psql gets EOF — and therefore runs `COMMIT` — only after age exited 0, the gzip
   member ended cleanly with nothing after it, and the plain dump's completion marker
   (`-- PostgreSQL database dump complete`) was seen in its last 4 KiB. On any failure psql is killed before it can
   see EOF, so **nothing is committed**; the children are killed (psql first), their pipes are read to EOF so no
   transport outlives the loop, and the scratch directory is removed, also on timeout and cancellation. age's exit
   status is the root cause when age fails (wrong key, tampered or truncated ciphertext: `DECRYPT_FAILED`) even though
   the gzip layer then sees a short stream; gzip faults seen while age is still healthy are `GZIP_INVALID`.
5. **Checks on the restored database** (read-only transaction): `alembic_version` has exactly one row equal to the
   manifest's `alembic_head` (whether it also equals the running repository's head is reported, not enforced — a newer
   code base upgrades afterwards); the READY set read with the 14D.2A inventory query equals the manifest
   (`verify_against_ready_set`) — the association between backup and database is proved from the restored data, not from
   the tool that wrote the backup; the READY / PENDING / FAILED counts equal the manifest's snapshot count and
   `skipped` counters.

- **Result.** `DbRestoreReport` (`plan-estimate/db-restore-report/v1`, canonical one-line JSON): last step reached,
  `RestoreFailure` code (`SCRATCH_UNSAFE`, `IDENTITY_INVALID`, `IDENTITY_NOT_A_RECIPIENT`, `TOOL_UNUSABLE`,
  `DATABASE_UNREACHABLE`, `DATABASE_NOT_EMPTY`, `DUMP_MISSING`, `DUMP_SIZE_MISMATCH`, `DUMP_SHA_MISMATCH`,
  `STORAGE_UNAVAILABLE`, `STORAGE_MISCONFIGURED`, `DECRYPT_FAILED`, `GZIP_INVALID`, `DUMP_INCOMPLETE`,
  `PLAINTEXT_TOO_LARGE`, `PSQL_FAILED`, `ROLE_MISSING`, `RESTORE_TIMEOUT`, `CHECKS_UNREADABLE`, `ALEMBIC_MISMATCH`,
  `READY_SET_MISMATCH`, `STATUS_COUNTS_MISMATCH`), byte counts, plaintext SHA-256, Alembic revision, READY count and
  status counts. It never contains a host, database, path, key, SQL text, row content or psql's message; the one
  value taken from psql is a role **name** that matches a plain-identifier pattern (`ROLE_MISSING`).
- **Roles.** The plain dump keeps object owners and grants, so the scratch server must already have the roles the dump
  names; `ROLE_MISSING` names the first missing one and nothing is committed. The tool creates and alters nothing
  outside the restored database.
- **Test evidence.** Fake children: every failure above, each asserting that psql never saw EOF; chunked and 12 MiB
  streams; a gzip bomb stopped by the cap; gzip faults (ISIZE, CRC32, no trailer, trailing bytes in the same and in a
  later chunk, a second member, deflate corruption, not gzip); early stop of age at the first bad byte; timeout and
  cancellation (both children really die, no transport outlives a private event loop even when the pipeline was backed
  up); secret-freeness and canonical form of the report; mutation check — 33 deliberate defects in the chain: 29 caught
  (four of them only after adding tests), 3 survivors judged equivalent (the order of the two `kill` calls, a liveness
  test that the broken-pipe handler duplicates, awaiting the stderr drains before cancelling them) and an explicit
  `stdin.close()` that proved redundant and was removed. **Real tools**
  (`test_stage14d2i1_real.py`, gate `TEST_REAL_POSTGRES=1` as in 14D.2D.4, plus `age` / `age-keygen`): a database with
  the real Alembic schema and seeded assets → `pg_dump` → the production `encrypt_dump_artifact` (two recipients) →
  sealed manifest → `restore_database` into a fresh scratch database: identical `photo_assets` content, marker row,
  Alembic head, READY 2 / PENDING 1 / FAILED 1; either recipient restores; a second restore and the source database
  are refused; for a listed-but-wrong identity, tampered (header / middle / tag) and truncated ciphertext, a gzip member
  with a bad CRC wrapped in valid age, a dump without pg_dump's completion marker, a dump of an older schema, a role
  the scratch server lacks, a mismatching manifest, and a cancellation in the middle of a large restore, the report
  names the failure and the target database is **still empty** (no relation) — psql's transaction was never committed;
  no plaintext file is left anywhere. Development-sandbox versions: age 1.1.1, PostgreSQL / pg_dump / psql 16.13.
- **Owner run (not yet done).** The same module run inside the backup image against a disposable `postgres:16` on an
  isolated network, exactly as the 14D.2D.4 proof (§16.6), gives the proof with the production versions (age 1.3.2,
  PostgreSQL 16.15): `TEST_REAL_POSTGRES=1`, `TEST_PG16_*`, `pytest tests/test_stage14d2i1_real.py`. The full chain
  on real data (including the real production dump) remains the 14D.5 drill.
- **Not in this stage:** media restore, the OCI API-key client factory, the restore-time integrity checker run, a
  command that wires fetching the run, restoring the database and restoring media together, any production target.
  Uploads stay OFF.

### 16.14 Media restore (Stage 14D.2I.2)

Implementation: `backend/app/backup/restore_media.py`; the destination-bucket guard `validate_restore_media_target` was
added to `backend/app/backup/restore_guards.py`. Tests: `test_stage14d2i2_restore_media.py` (49).

`restore_media(reader, run, destination, destination_bucket=…, forbidden_buckets=…, ready_assets=…, scratch_dir=…)`
copies every object line of a sealed run from the backup target (`BackupReader`) into the destination
(`MediaStorageAdmin`: the production S3 adapter in a drill, the drill-restore bucket) and proves each copy. It runs
after the database restore (§16.13) whose READY set it requires.

- **Guards (before anything is read or written).** (1) *Destination bucket:* a valid bucket name, not in the caller's
  forbidden list (production, …) and never the run's own source or backup bucket (taken from the manifest header), and —
  unless `allow_non_drill` states a real disaster restore — a name containing `drill`. The adapter cannot be asked which
  bucket it writes to, so the caller states it and the wiring (2I.3) builds both together. (2) *Association:* the
  manifest must describe exactly the READY set read from the **restored database** (`verify_against_ready_set`), which
  is where "originals = DB, sizes = DB" (§10) is enforced at restore time. (3) *No foreign objects:* the destination
  must hold no object under `photos/v1/` that is not part of the run — a production bucket practically always does, a
  fresh or half-restored drill bucket never (`allow_foreign_objects` is an explicit override, not the default).
- **Per object**, strictly sequential in key order: *absent* → download from the backup, size and SHA-256 must equal the
  manifest's, create-only put (an identical re-put is a no-op, any other content is a conflict), HEAD size and — by
  default — a full re-download compared with the manifest's SHA-256 (`verify_destination=False` reduces this to the size
  check; a same-size change is then not visible, which is documented and tested); *present* → the same size and, by
  download, the same SHA-256 count as `already_present` (a resumed run), anything else is `DESTINATION_CONFLICT` and the
  object is never touched. There is no overwrite and no delete: the destination interface has neither.
- **Result.** `MediaRestoreReport` (`plan-estimate/media-restore-report/v1`, canonical one-line JSON): preflight failure
  (`DESTINATION_UNSAFE`, `MANIFEST_DB_MISMATCH`, `FOREIGN_OBJECTS_PRESENT`, `LISTING_FAILED`, `STORAGE_UNAVAILABLE`,
  `STORAGE_MISCONFIGURED`), per-object problems tied to asset id and role (`MISSING_BACKUP_OBJECT`,
  `BACKUP_SIZE_MISMATCH`, `BACKUP_SHA_MISMATCH`, `BACKUP_UNAVAILABLE`, `DESTINATION_CONFLICT`,
  `DESTINATION_VERIFICATION_FAILED`, `DESTINATION_UNAVAILABLE`), counts (restored, already present, failed, bytes), abort
  reason and `ok`. Every problem is collected and the run continues; a misconfigured backup or destination, or 5
  consecutive unavailable-store failures, aborts. Transient errors are retried with the §16.10 policy. No key, hash,
  bucket name or provider message is ever reported; at most 200 problems are listed, the totals cover all.
  Unexpected exceptions and cancellation propagate after the scratch files are removed.
- **After the copy.** Whether the restored database and bucket agree is checked by the existing
  `scripts/media_integrity_check.py --verify-sha256 --strict` (§10, §11 step 5), run by the operator against the
  restored database and the destination bucket: it must report the expected missing objects before the restore and be
  clean after it.
- **Test evidence.** Everything above against an in-memory backup and destination with fault injection (missing /
  resized / bit-flipped backup objects, conflicting, corrupted, truncated and invisible destination objects, a put
  that loses a race, transient and persistent outages on both sides, misconfiguration, streaks, cancellation, scratch
  hygiene, ordering and call-log assertions that the backup is only read and the destination only receives creates and
  reads); the production `S3MediaStorage` as the destination through a fake boto3 client (conditional put, resumed run,
  conflict, foreign object, response bodies closed); mutation check — 27 deliberate defects in the engine and the guard,
  all caught (one only after a malformed-but-"drill" bucket name was added to the tests).
- **Not in this stage:** the restore client for the OCI restore principal (API key), the command that wires fetching
  the sealed run, `restore_database`, reading the READY set from the restored database and `restore_media`, the
  integrity-check run, and the live smokes (2I.3); the full chain on real data is the 14D.5 drill. Uploads stay OFF.

### 16.15 Restore client, the whole restore chain and the media-restore smoke (Stage 14D.2I.3)

Implementation: `backend/app/backup/oci_target.py` (`OciBackupReader`, `validate_api_key_config`),
`backend/app/backup/restore_run.py` (`restore_run`), `backend/app/backup/restore_db.py` (`read_ready_assets`),
`backend/scripts/stage14d2i3_media_restore_smoke.py`. Tests: `test_stage14d2i3_oci_reader.py` (14),
`test_stage14d2i3_oci_sdk.py` (18, real `oci` SDK with a stubbed transport), `test_stage14d2i3_restore_run.py` (16),
`test_stage14d2i3_smoke.py` (33), `test_stage14d2i3_real.py` (5, opt-in, real age + PostgreSQL 16 + real bytes).

- **Restore client (`OciBackupReader`).** The read side of the backup bucket for the restore principal: **`head` and
  `download_to` only** — there is no write verb to call, not even one that IAM would refuse. Authentication is the
  operator's API signing key from a local OCI config file (the private key stays on the workstation, never on the
  production VM); `from_instance_principal` serves verification on the VM. Before the SDK sees them, the config file and
  the private key it names must be absolute, regular, non-symlink files owned by the effective user with no group /
  other bits (`validate_api_key_config`); SDK failures are reduced to the exception type, so neither a path, an OCID,
  a fingerprint nor a provider message reaches an error. The client is built with the SDK's retries off (retry policy
  lives in `app.backup.target`) and explicit timeouts. A missing SDK is reported as such (`error_code` None), not as a
  bad config. The tests run the **real SDK** against a stubbed `requests` transport: signed requests (`Authorization:
  Signature … keyId="<tenancy>/<user>/<fingerprint>"`), endpoint and region (and its override), URL encoding of object
  names, HEAD / GET only, streaming into a new 0600 file with a size check, 404 / 429 / 5xx / masked-denial mapping with
  exactly one request per call, and — over the same real client — the 14D.2F writer's conditional PUT (`If-None-Match:
  *`, `Content-MD5`, `Content-Length`) and 412 → exists. These SDK tests need `oci` and `requests` (an operator /
  development dependency, not a production pin) and skip without them.
- **The whole restore (`restore_run`).** `restore_run(reader, run_id, database=…, identity_file=…, destination=…, …)`:
  (1) seal — `runs/<run_id>/COMPLETE.json` + manifest accepted by `verify_run` (`SEAL_MISSING` / `SEAL_INVALID` /
  storage failures are reported, never guessed); (2) database — `restore_database` (§16.13); (3) the READY set is read
  back from the **restored** database (`read_ready_assets`); (4) media — `restore_media` (§16.14) with that set. It stops
  at the first step that did not succeed: a failed database restore never touches the destination bucket, an unreadable
  READY set never reaches media. A media failure leaves the restored database in place and says so (`step: media`). The
  result is one canonical secret-free report (`plan-estimate/restore-run-report/v1`) embedding the step reports. The
  integrity checker `scripts/media_integrity_check.py --verify-sha256 --strict` stays the operator's final check
  (§10, §11 step 5). `PriorRunError` gained a `missing` flag so that a run that does not exist is told apart from one
  that is inconsistent.
- **Real proof of the whole chain** (`test_stage14d2i3_real.py`, gate `TEST_REAL_POSTGRES=1`, plus `age`): a database
  with the real Alembic schema is given real object bytes (rows' sizes and the original's SHA-256 updated to describe
  them), dumped, encrypted for two recipients and sealed with a manifest of the bytes the backup target really holds;
  `restore_run` with the second recipient's identity restores an identical `photos` table and every object (6 objects,
  bytes equal); a second run is refused by the database step and never reaches media; a tampered artifact leaves the
  destination untouched and the database empty; a damaged backup object is reported while the rest and the database are
  restored; a destination holding other objects is refused after the database restore. Development-sandbox versions:
  age 1.1.1, PostgreSQL / pg_dump / psql 16.13 (together with the 17 tests of §16.13: 22 passed).
- **Media-restore live smoke (owner run 2026-10-04: PASS 8/8, `oci principal: obtained`, `cleanup: 10/10 synthetic
  objects removed`, exit 0).** `stage14d2i3_media_restore_smoke.py` restored a run that the
  14D.2G smoke published in the Oracle drill bucket into the R2 **drill-restore** bucket with the production adapters,
  reading the backup bucket with the VM's instance principal (or, with `--oci-config`, the restore principal's API key
  on the workstation). The database half needs a real encrypted dump and is proved by the 14D.5 drill; here the READY
  set is derived from the manifest. It starts only if the destination holds no object under `photos/v1/`, removes
  exactly what it created, and never deletes anything else. 8 checks: all objects restored and verified; an independent
  comparison of keys, sizes and SHA-256 with the manifest; an idempotent rerun (no backup read, no write); another
  object under a manifest key (reported for it alone, bytes untouched); a foreign object (nothing written); a
  forbidden bucket name (nothing read or written); bytes changed in transit (reported, never written, the rest
  restored); a secret-free report. Exit codes 0 PASS / 1 FAIL / 2 cannot run / 3 no OCI principal. The automated
  tests drive every check against engines that are deliberately blind, lenient or destructive, so none can pass
  vacuously (the first version of the tests let 11 of 15 mutations of the script survive). Configuration: the
  drill-restore R2 token env file (`R2_*` and `R2_FORBIDDEN_BUCKETS`) and `OCI_NAMESPACE`. Command (DRAFT until the owner
  run; dependency set resolved and the script's imports and exit codes checked in a clean environment):

  ```bash
  RUN='pip install -q --no-cache-dir --target /tmp/deps "sqlalchemy[asyncio]==2.1.1" greenlet==3.5.6 pydantic==2.13.5 pydantic-settings==2.15.0 pyjwt==2.15.0 asyncpg==0.31.0 oci==2.187.1 boto3==1.43.103 botocore==1.43.103 s3transfer==0.19.2 urllib3==2.8.0 anyio==4.15.1 && PYTHONPATH=/tmp/deps python /app/scripts/stage14d2i3_media_restore_smoke.py --run-id <run 1>'
  docker run --rm --network pe-upload --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
    --env-file ~/backups/plan-estimate/drill-secrets/r2-drill-restore.env -e OCI_NAMESPACE -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$PWD/backend":/app:ro "$IMG" sh -c "$RUN"
  ```
- **Not in this stage:** a command-line entry point that wires all of this to the operator's environment (data root,
  lock, exit codes — the same gap as for the backup run; delivered in 14D.2J, §16.16), the live run of the database half with a real dump and an
  API-key restore principal (re-creating that key is a 14D.5 step), the integrity-check run, any production target.
  Uploads stay OFF.

### 16.16 Backup and restore commands (Stage 14D.2J)

Implementation: `backend/app/backup/run_sidecars.py`, `upload_run.py`, `upload_command.py`, `restore_command.py`;
`__main__.py` (`upload`, `restore`), `orchestrator.py`, `workspace.py`, `core/pg_snapshot_dump.py` (additions).
Tests: `test_stage14d2j1_sidecars.py` (29), `test_stage14d2j2_upload_run.py` (42), `test_stage14d2j2_upload_command.py`
(44), `test_stage14d2j3_restore_command.py` (38); `test_stage14d2a_exporter_contract.py` and
`test_stage14d2d3_orchestrator.py` extended. This slice only **wires** the accepted pieces (§16.5, §16.10–§16.15) to the
operator's environment: data root, lock, evidence, exit codes, guards. It introduces no new backup or restore logic.

- **Why two commands for the backup run.** `db-dump` runs where the database credentials are; the upload runs where the
  object-storage authority is (§12, O2): two containers that must not share secrets. They meet in the data root.
  `db-dump` therefore leaves, next to the encrypted artifact, the two facts only it knows (the evidence keeps only a
  digest of the READY set and a recipient *count*): `ready-assets.txt` (the canonical READY set v1 bytes of the very
  snapshot that was dumped; `snapshot_bound_dump` now returns the assets it hashed) and `recipients.txt` (the public
  `age1…` recipients). Both are written, fsynced and private before `local-run.json`, and a run whose assets do not hash to
  the snapshot digest stops at the evidence stage (`SNAPSHOT_METADATA_INVALID`). Parsing is strict: a sidecar is accepted
  only if re-serialising it reproduces it byte for byte.
- **`python -m app.backup upload --environment drill|production [--run-id ID] [--prior auto|none|ID] [--deep]`.** Takes
  `run.lock` (never overlaps a `db-dump`), picks the newest promoted run without `evidence/<run_id>.published.json`, builds
  the R2 source (`MEDIA_S3_*`, the application's own names) and the Oracle target (instance principal) from the
  environment, and calls `upload_run`: **local** (files read through the data root: no symlink, private, bounded; READY
  file hashed against `snapshot.ready_set_sha256`, recipient count against the evidence, artifact size and SHA-256
  against the evidence — before a single byte is written anywhere) → **target** (is this very run already sealed there?
  then it is *adopted*: only the local evidence is written; a different run under that id is `TARGET_RUN_CONFLICT`) →
  **prior** (named or the newest published run; a prior that is missing, inconsistent or from another bucket is
  `PRIOR_UNUSABLE`, never silently ignored — `--prior none` is the operator's explicit choice) → **sync** (`sync_media`)
  → **publish** (`publish_run`: dump, manifest, `COMPLETE.json` last) → `evidence/<run_id>.published.json` (counts only).
  A failure writes `evidence/<run_id>.upload-failed-<UTC>.json` (the canonical report) and nothing later runs; the local
  run is never modified. `--environment` is mandatory and checked against the bucket names (drill: both buckets contain
  `drill`; production: neither, and `--allow-production` — production uploads stay off until the owner enables them);
  source and target must differ. Exit codes: 0 published / adopted, 1 failed, 2 usage, 3 lock held, 5 configuration or
  guard, 6 interrupted, 8 nothing to upload (no such run, or already published), 9 the local run is unusable, 10 sealed in
  the target but the local evidence could not be written (repeat the same command: it adopts the sealed run).
- **Repeating after a failure (plan §15).** `SYNC_INCOMPLETE` (a source object missing or unreadable) is repeatable with
  the same run: media objects are create-only or verified-identical and nothing was sealed. A publication that failed
  *after* its manifest was stored cannot be re-published under the same run id — the manifest lines carry per-attempt
  actions and timestamps, so a second manifest would differ, and the target never overwrites. Per §15 the answer is a new
  `db-dump` run (a new `run_id`); the half-written run has no `COMPLETE.json` and is invalid by definition.
- **`python -m app.backup restore --run-id ID --identity-file … --scratch-dir … --report-file … --forbidden-bucket …`.**
  The restore principal's command (workstation, never the production VM). Configuration: the scratch database (`PG*`, name
  must carry `pe_restore_scratch`, loopback / `scratch` host / `--allowed-host`, valid pgpass), the Oracle bucket to read
  (`BACKUP_OCI_*`; `--oci-config` for the API-key principal, else the instance principal) and the destination media bucket
  (`RESTORE_S3_*` — deliberately not the production `MEDIA_S3_*` names). Every guard runs *before* anything is built, read
  or written (identity file, scratch database, destination not forbidden and a drill bucket unless `--allow-non-drill`, at
  least one `--forbidden-bucket`; the Oracle backup bucket is always forbidden; the report file must be creatable). Then
  `restore_run` (seal → database → READY set → media) runs with a per-run private scratch directory that is removed
  afterwards, the canonical secret-free report is written to the new `--report-file` (0600, exclusive, never overwritten)
  and a short summary is printed. Exit codes: 0 restored and verified, 1 restore failed (the report says where), 2 usage,
  5 configuration / guard / principal, 6 interrupted, 7 the restore ran but the report file could not be written.
- **Tests.** The command layer runs end to end on real promoted runs on disk (the real orchestrator's output is uploaded
  unchanged), with in-memory stores for the network sides: success, adoption, conflict, every missing / symlinked /
  group-readable / tampered file of a run, prior handling, unavailable target, incomplete sync, failed publication, lock held,
  interruption by SIGTERM (handler removed, scratch removed, nothing sealed), the guard matrix, run selection, secret-free
  output and reports. Mutation checks: 34 mutations of the new code; 4 survived at first — one equivalent (`<` vs `<=` in
  the prior selection: a run with published evidence is refused earlier), three led to new tests (inconsistent seal in
  the target, schema revision in the local evidence, size limit of a promoted file).
- **Not in this stage:** a live run of `db-dump` → `upload` → `restore` on the Oracle VM / workstation (that is the 14D.5
  drill, with the restore principal's API key created again by the owner), the integrity-check run, any schedule, any
  production target. Uploads stay OFF. **Dependency note:** the OCI SDK (`oci==2.187.1`) is in no requirements file and no
  image (the backup image carries neither `oci` nor, for the uploader, a separate build yet); for the drill the commands run
  the way the smokes do — `pip install --target /tmp/deps` of the pinned set, `PYTHONPATH=/tmp/deps` — and pinning `oci`
  into a dedicated uploader image is a later image / dependency change that needs the owner's approval.

### 16.17 Drill tooling and runbook (Stage 14D.5A)

Implementation: `backend/scripts/stage14d5_drill_tool.py`, `backend/app/backup/restore_run.py` and
`restore_command.py` (`--phase`), runbook `docs/STAGE_14D5_DRILL_RUNBOOK.md`. Tests: `test_stage14d5_drill_tool.py` (46),
`test_stage14d2i3_restore_run.py` (+8) and `test_stage14d2j3_restore_command.py` (+5). 14D.5A prepares the isolated drill
(§11); it executes nothing on any server. The drill itself (14D.5B) is run by the owner phase by phase.

- **Drill tool (`seed`, `verify-serving`, `inventory`, `compare-inventory`).** `seed` generates the §12 fixture — a JPEG,
  a PNG, a WebP and a JPEG with EXIF orientation 6, all generated, deterministic, no real media — and uploads it through
  the **real** `POST /api/projects/{id}/photos` of a *scratch* backend (mock authentication, development environment; the
  tool refuses any backend whose host is not loopback, does not contain `scratch` or is not explicitly allowed). It
  records the project, the assets, the SHA-256 of every uploaded original and the stored dimensions in a new 0600
  fixture file. `verify-serving` is plan §11 step 6: against a scratch backend pointed at the restored database and the
  drill-restore bucket it checks (8 checks) that the list equals the fixture and the sealed manifest, every list item has a
  thumbnail URL, every detail is READY with thumbnail and display URLs, the bytes behind every presigned URL (fetched
  without the API's Authorization header, redirects not followed) hash to the **manifest's** SHA-256, the originals in
  the manifest equal the fixture's, the stored dimensions are unchanged by the restore, the EXIF case is portrait, and no
  original is exposed. `inventory` lists a bucket (R2 `list_objects_v2` or OCI `list_objects`, never anything else) and
  writes object count, bytes and a digest over the sorted "key, size, etag" lines — no key in the file;
  `compare-inventory` names the fields that differ. The tests drive `seed` and `verify-serving` against the **real
  application** (ASGI, in-memory storage), so the tool is proven against the actual upload and read contract; misbehaving
  backends (missing URLs, a not-READY detail, a lost orientation, an exposed original, wrong bytes, an unreachable or
  non-200 URL) are simulated by rewriting the real app's answers. 46 tests, mutation-checked (11 of the first batch of mutations survived and led to 12 added tests; 0 survive now).
- **`restore --phase all|database|media`.** Plan §11 step 5 needs the integrity checker *between* the database and the
  media restore (database restored, destination empty: exactly the expected objects are missing; afterwards: clean). The
  chain therefore gained `RestorePhase`: `database` = seal + database; `media` = seal + READY set read back from the
  already restored database + media (refused when the database is not a scratch database — `DATABASE_UNSAFE` — or does not
  match the manifest — the existing `MANIFEST_DB_MISMATCH`); `all` (default) is unchanged. The report carries `phase`, and
  `ok` means that the phase's own halves succeeded and that a skipped half carries no report. Mutation-checked.
- **Finding on the way.** The first version of the serving check crashed on a detail without a URL instead of failing
  the check; fixed and pinned by a test.
- **Dependency set for the Oracle VM** (python slim, no build): `sqlalchemy[asyncio]==2.1.1 greenlet==3.5.6
  pydantic==2.13.5 pydantic-settings==2.15.0 pyjwt==2.15.0 asyncpg==0.31.0 alembic==1.20.0 oci==2.187.1
  boto3==1.43.103 botocore==1.43.103 s3transfer==0.19.2 urllib3==2.8.0 anyio==4.15.1` — installed and the `upload` /
  `restore` commands imported in a clean Python 3.12 environment (`alembic` is needed because the CLI module imports the
  `db-dump` chain). `oci` is in no image or requirements file.
- **Facts the runbook rests on.** The production R2 bucket holds 0 objects and no production R2 token exists yet (the
  read-only token is created in 14D.6), so the production "no write" evidence is inventory-based and optional (Oracle
  production backup bucket via the restore principal, one read-only count on the production database); every production
  access is the owner's explicit decision. The restore principal's API key must be re-created by the owner.
- **Not in this stage:** executing any phase (14D.5B), step 7 of §11 (the real production dump: 14D.6), a dedicated
  uploader image.

### 16.18 The isolated drill — executed (Stage 14D.5B, 2026-10-05)

Procedure: `docs/STAGE_14D5_DRILL_RUNBOOK.md`; verified command blocks: `docs/STAGE_14D5_DRILL_COMMANDS.md`; tooling: §16.17.
Run id `20261005T052617Z-66a27f56` (taken at schema head `0032_photo_attachments`). **Result: steps 1–6 of §11 PASS.**

**Topology.** Workstation W (Docker, amd64): scratch PostgreSQL 16 (`postgres:16-alpine`, no published port), the scratch backend
(uploads enabled, mock authentication — a throw-away drill service), `db-dump` in the backup image with the production
service's hardening flags (read-only root, `--cap-drop ALL`, `no-new-privileges`, 512 MiB / 0.5 CPU / 64 pids, non-root host
UID), `restore` with the restore principal's API key and the private drill age identity. Oracle VM V: only `upload`, in a
container on `pe-upload` with the instance principal and no restore credentials. Nothing was built, pulled or changed on
the production checkout of V (the source went over as a `git archive` of `backend/app` into a separate directory).

| §11 step | Result (numbers are the observed ones) |
|---|---|
| 1 seed through the real upload pipeline | `seeded … images=4`; 4 `READY`; drill-source bucket 12 objects, 90 667 bytes |
| 2 backup → drill-backup → COMPLETE | `backup complete … ready_count=4` (artifact 12 271 bytes, four files 0600 in `encrypted/<run_id>/`); `upload complete … published objects=12 ready_assets=4 prior=-`; a second `upload` exits 8 (`ALREADY_PUBLISHED`); `published.json` 0600 |
| 3 §9 chain into a fresh scratch database | `restore … phase=database ready_count=4`; Alembic `0032_photo_attachments` = repository head; status counts READY 4 / PENDING 0 / FAILED 0 (plaintext 112 852 bytes) |
| 5 integrity **before** media | `Assets checked: READY=4`, `Findings: MISSING_DERIVATIVE=8, MISSING_ORIGINAL=4`, `Result: 12 error(s)` (exit 1) — exactly the 12 objects of the empty destination |
| 4 media into the empty drill-restore bucket | `restore … phase=media restored=12 already_present=0 total=12` (90 667 bytes) |
| 5 integrity **after** (`--verify-sha256 --strict`) | `Findings: none`, `0 error(s), 0 warning(s)`, exit 0; the drill-restore bucket has the same objects, bytes **and listing digest** (keys, sizes, ETags) as drill-source after seeding |
| 6 the backend on the restored database + bucket | `verify-serving` **8/8**: list = fixture = manifest (4), thumbnail / display URLs for all, 8 presigned URLs fetched without Authorization hash to the manifest's SHA-256, originals equal the fixture, dimensions unchanged, the EXIF case is portrait, no original exposed |
| no write to production | Oracle `plan-estimate-backup-prod`: 0 objects before and after, `inventories identical`. The uploader cannot delete, so 0 objects before the restore phases also covers the earlier phases. |

**Problems met and what they changed** (none changed the system under test; four were defects of the drill's own command blocks):
1. *Secret generator under `pipefail`* — `tr … | head -c N` dies of SIGPIPE and silently ends the script. Fixed (`od`); the block now also checks every secret's size.
2. *R2 drill tokens bound to the VM's IP* — every call from the workstation was `403 AccessDenied` (diagnosed with a read-only three-call script run on both machines). The owner added the workstation's IP to both tokens.
3. *Seeding ran twice* (once earlier, once again) — 8 assets and 24 objects instead of 4 and 12, which would have made the §11 numbers false. Not adjusted around: the scratch database was recreated, the 24 drill-source objects were deleted (drill token, bucket name enforced in code), the mistaken local run removed, and the seed repeated. The seed and `db-dump` blocks now refuse a non-empty bucket, database or `encrypted/`.
4. *`ssh` inside `bash <<EOF`* read the remaining script from stdin and ended the block after its first call (the run was not shipped). Fixed with `ssh -n` where stdin is not given explicitly.
5. *The public key was taken for the private one* when the restore principal's key pair was laid out (the Console offers both downloads). The layout step now checks for `PRIVATE KEY` and the config script verifies that the Console fingerprint belongs to `key.pem`.
6. *`docker run --tmpfs` is `noexec`* — noted and handled up front (`--tmpfs /tmp:rw,exec`) for the `pip --target` installs.
7. *A prediction of mine was wrong:* the Oracle **drill** bucket holds 42 objects, not the 15 this run wrote — it still holds the leftovers of the earlier smoke tests (14D.2F–H, 14D.4) that the create-only uploader cannot delete. This run's objects are proven by `restore` having read and verified them, not by the bucket total. The inventory tool has no prefix filter.

**Deviations from the plan, stated plainly.** (a) The drill is split between the workstation and the VM (restore credentials must not live on the production VM; the instance principal exists only there). (b) Production PostgreSQL and the production R2 bucket were not inventoried: no tool of the drill connects to either (all databases were scratch, every R2 call used a drill-scoped token), and no production R2 token exists before 14D.6. Only the production Oracle bucket was inventoried. (c) Step 7 of §11 (a real production dump) is 14D.6. (d) A sealed run was not separately verified in the target with a stand-alone `verify` command — `restore` verified the seal and every object, but the 14D.2H engine has no command-line entry point yet.

**Cleanup (Phase J) — done after the owner's sign-off (2026-10-05), J1–J4 PASS:** the 12 + 12 objects of the drill-source / drill-restore buckets (drill tokens; each bucket checked empty afterwards), the copied run, source and `drill-upload.env` on V, the three scratch containers with the scratch PostgreSQL volume and the network on W, and `~/pe-drill-14d5` (scratch passwords, run, reports, fixture). **Still open, by hand:** the Oracle drill-bucket objects (administrator only; the create-only uploader cannot delete), revoking the restore principal's API key created for the drill and removing its files from the workstation, removing the workstation's IP from the R2 drill tokens (they expire 2026-11-09), and the two local drill images. A dedicated uploader image with `oci` pinned, a `verify` command and `inventory --prefix` are follow-ups for 14D.6. Uploads stay OFF.

### 16.19 Production-run tooling (Stage 14D.6A)

Implementation: `backend/app/backup/verify_command.py` (+ `__main__.py`), `backend/Dockerfile.uploader`,
`backend/requirements-oci.txt`, the `backup-upload` service and the `pe-upload` network entry in `docker-compose.prod.yml`;
runbook `docs/STAGE_14D6_PRODUCTION_RUNBOOK.md` (DRAFT). Tests: `test_stage14d6a_verify_command.py` (26),
`test_stage14d6a_uploader_contract.py` (14), `test_stage14d2c_image_contract.py` (two assertions widened) and `test_stage14b4_production_templates.py` (one). 14D.6A is the part
of 14D.6 that needs no contact with production: it closes the follow-ups the drill left (§16.18) and drafts the production
procedure. **Nothing was built, started or changed on any server.**

- **`python -m app.backup verify --run-id ID [--mode quick|full]`.** The 14D.2H engine got its command: read-only, no database,
  no age identity, no write authority. QUICK = seal, manifest, dump size, one HEAD per object; FULL (default) re-hashes the dump and
  every object. Reader: the instance principal (inside the uploader on the VM) or, with `--oci-config`, the restore principal's API
  key (the independent reader on the workstation). `--expect-recipient` (repeatable) or the public `BACKUP_AGE_RECIPIENTS` of the
  backup environment: the run must have been encrypted for each of them (`RECIPIENTS_MISMATCH`). A short summary is printed; the
  canonical secret-free report goes to `--report-file` (new file, 0600). Exit codes 0 verified / 1 problems / 2 usage /
  5 configuration or principal / 6 interrupted / 7 report not written.
- **Uploader image (`Dockerfile.uploader`).** A thin layer on top of the accepted backup image — `Dockerfile.backup` stays
  byte-identical (its hash is pinned by a test), so the local-only `db-dump` image does not get the Oracle SDK. The layer
  installs `requirements-oci.txt` with `--no-deps` and `pip check`: `oci==2.187.1` and the 17 packages it adds, every one pinned
  (resolved against `requirements.txt` in a clean Python 3.12 environment, which none of its pins changed). The image also
  carries `age` and `psql`, so it is what the workstation can use for `restore` without a `pip install` at run time.
- **`backup-upload` Compose service.** Profile-gated and one-shot like `backup`, the same hardening (non-root host UID, read-only
  root, `cap_drop: ALL`, `no-new-privileges`, 512 MiB / 0.5 CPU / 64 pids), **no database and no pgpass**, its only network the
  external `pe-upload` bridge (the one behind the IMDS guard), a tmpfs `/tmp` of 256 MiB, and a writable data root (`upload` takes
  `run.lock` and writes `evidence/<run_id>.published.json`; the artifacts there are age-encrypted — this deviates from the
  "read-only `/backup`" sketch of the O2 design and is a stated trade-off). Its R2 settings come from **its own variable names**
  (`BACKUP_UPLOAD_S3_*` → `MEDIA_S3_*` inside the container), so `--env-file .env.production` can never hand it the backend's
  read-write token. Its default command is `upload --help`; the real one needs `--environment production --allow-production`.
  The contract tests pin all of this (mutation-checked: 21 mutations, 1 invalid, 0 survivors). **A finding of the full suite:** the
  14B.4 invariant "MEDIA_* / PHOTO_* settings reach the backend service only" failed on the new service (the uploader's container
  uses the application's names for its R2 *source*). The invariant was widened, narrowly: `backup-upload` may carry exactly the six
  `MEDIA_S3_*` / `MEDIA_STORAGE_NAME` keys and each must be fed from a `BACKUP_UPLOAD_*` host variable; any other service, any other
  key or any value from the backend's variables still fails (mutation-checked).
- **14D.6B, P0 executed (read-only, 2026-10-05):** the VM facts and the production database baseline are in the runbook §4a — `aarch64`, Docker 29.8.0,
  38 GiB free, IMDS guard active, new Compose file valid, Alembic at head, **`photo_assets` empty** (so `ready_count = 0` and the first run puts
  exactly three objects into the target), no `pe_*` role. Finding while preparing P1: `owner_proof.sh` generated its throwaway age identity with
  `age-keygen` **on the host** — the VM has no `age` and the owner's rule is that no private identity is generated on it; the script now generates
  the synthetic identity with the image under test after the build (contract test + mutation checks).
- **Not done here (14D.6B, owner, each step with its own approval):** the ARM64 gate on the production host, the backup role in the
  production PostgreSQL, IAM Phase B, the production read-only R2 token, the first production `db-dump`, `upload`, `verify` and the
  restore of the real dump (plan §11 step 7) — see the runbook. `docker compose` with the new external network was only checked
  statically (`yaml`); the owner runs `docker compose config` as the first read-only step on the host.

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
