# Stage 14D.6 — First production backup run: runbook (EXECUTED 2026-10-05 / 2026-10-06 — P0–P8 PASS; awaiting the owner's acceptance)

> **Status:** written in 14D.6A together with the tooling it needs (`verify` command, uploader image, `backup-upload`
> Compose service; plan §16.19). **Executed in full on 2026-10-05 / 2026-10-06: P0–P8 PASS (results recorded per phase below; closure in §7).**
> Every phase below touches production in some way and is run by the owner only after an explicit decision for *that* phase (`CLAUDE.md`: SSH, `git pull`, Docker build,
> Docker up, any data-modifying operation each need their own approval). Production photo uploads stay **OFF**
> (`PHOTO_UPLOADS_ENABLED=false`); nothing here enables them (that is Stage 14E).
>
> Commands are issued one phase at a time after the previous phase's output has been reviewed, and recorded here in their
> verified form (the pattern of `docs/STAGE_14D5_DRILL_COMMANDS.md`). The drill's lessons apply: run blocks as
> `bash <<'EOF'`, use `ssh -n` unless stdin is given, `--tmpfs … exec` only where needed, never re-run a phase that
> already wrote something.

## 1. What the run proves and what it changes

Plan §17 criterion 5: *"Production non-destructive run: encrypted dump off the VM and verified; media run on the current
inventory COMPLETE; no production change."* Together with §11 step 7: *"the real production dump restores into scratch
PostgreSQL with Alembic current = head and the expected counts."*

| What | Where | Reversible? |
|---|---|---|
| Read the production database in one `REPEATABLE READ READ ONLY` snapshot, dump it, encrypt it with the **public** age recipients | production VM (`backup` service), local data root | local files only |
| Create the backup database role `pe_backup` (LOGIN + CONNECT + `pg_read_all_data`; frozen 14D.2D.4 policy) | production PostgreSQL | **yes** (`DROP ROLE`), but it is a write to production — own approval |
| Upload dump + manifest + `COMPLETE.json` (+ the READY media, currently none) | Oracle `plan-estimate-backup-prod` | **no** — create-only, versioned, the uploader cannot delete; only the administrator can |
| Read the media list of the production bucket | R2 `plan-estimate-media-prod` with a new **Object Read only** token | read-only |
| Restore the real dump into a scratch database | the owner's workstation (private recovery identity needed) | scratch only |

The point of no return is **P5** (the first object in the production backup bucket). Everything before it can be undone or
discarded; everything after it is permanent history. P5 is therefore preceded by a checklist and its own approval.

## 2. Prerequisites that already exist (nothing to build for them)

* Code: backup chain (14D.2), `upload` / `restore` / `verify` commands, the drill-proven procedure (14D.5).
* Oracle: buckets `plan-estimate-backup-prod` / `-drill` (versioning on), compartment, dynamic group
  `plan-estimate-backup-uploader-dg`, restore group and policy; the IMDS guard on the production host
  (`pe-imds-guard.sh status` → `OK`) and the network `pe-upload` (14D.4).
* The private recovery age identities live off the VM (at least two independent copies — the owner's custody).

## 3. What the owner has to create (not in the repository)

1. **IAM Phase B** — policy `plan-estimate-backup-uploader-prod-policy` (exact statements: `docs/STAGE_14D3_ORACLE_BACKUP_PROVISIONING.md`
   §6.2). Without it the uploader can write only to the drill bucket.
2. **R2 read-only token** for `plan-estimate-media-prod` only (Cloudflare → R2 → Manage API tokens → Object Read only).
   Written straight into the upload env file on the VM (`chmod 600`), never pasted into chat.
3. **Restore principal API key** (re-created for P7, deleted afterwards) — and, for P7, the private recovery identity in RAM
   (`/dev/shm`) on the workstation, removed with `shred -u` right after the restore.
4. **Production backup environment** on the VM: `BACKUP_HOST_ROOT` (data root 0700 + `secrets/pgpass` 0600),
   `BACKUP_UID` / `BACKUP_GID`, `BACKUP_PG*`, `BACKUP_AGE_RECIPIENTS` (**public** recipients only), and for the uploader
   `BACKUP_UPLOAD_S3_*`, `BACKUP_OCI_NAMESPACE`, `BACKUP_OCI_BUCKET=plan-estimate-backup-prod`, `BACKUP_TOOL_COMMIT`.

## 4. Phases

Each phase lists **what it touches** and **PASS**. A phase is not started before the previous one passed and the owner said yes.

**P0 — facts (read-only on the VM).** Architecture (`aarch64`), Docker / Compose versions, disk, `docker compose ps`,
`pe-imds-guard.sh status`, existence of `pe-upload` and of the images `plan-estimate-backup:local` /
`plan-estimate-backup-upload:local`, the checkout's commit, and — one `SELECT` — `photo_assets` counts by status and the Alembic
revision of the production database. *Touches:* nothing. *PASS:* all as expected; `photo_assets` counts recorded as the
"before" snapshot of the production database (they are compared again in P8).

### 4a. P0 — executed 2026-10-05 (read-only; the owner's "yes, P0")

Facts (no secrets): the VM is `aarch64`, Ubuntu 24.04.5, kernel 6.17 (Oracle), Docker 29.8.0 `linux/arm64`, Compose 5.5.1; 38 GiB free of
45 GiB, 5.9 GiB RAM (≈5 GiB available); the production stack (`caddy`, `backend` healthy, `frontend`, `postgres` healthy) was up; the
network `pe-upload` (172.30.250.0/24) exists with no attached container; `plan-estimate-imds-guard.service` is `active` and `enabled`
(`/usr/local/sbin/pe-imds-guard.sh`; its `status` needs root and was not run); no `plan-estimate-backup*` image exists; the production
checkout `~/apps/plan_-_estimate` is at `1931e78` on `stage-14`, clean, `.env.production` is 0600; `~/backups/plan-estimate` is 0700 and
holds the older ad-hoc dumps and `drill-secrets` — there is **no** `db-backup` root yet. The new `docker-compose.prod.yml`, fed to the
VM's Compose through stdin (`-f -`), is valid: services `backend, backup, backup-upload, caddy, frontend, postgres`, `pe-upload` external,
`backup-upload` attached to `pe-upload` only. Production database (a `default_transaction_read_only` session): PostgreSQL 16.15, Alembic
`0032_photo_attachments` (= repository head), 11.8 MB, **no `pe_*` role**, `photo_assets` empty (no photo exists: the first run has
`ready_count = 0`, so the target will receive exactly three objects). Baseline row counts, for P8 (differences are expected only from the
owner's own use of the application between P0 and P8; the backup itself changes no row): `users` 1, `clients` 2, `projects` 2, `rooms` 4,
`surfaces` 25, `openings` 8, `inspections` 4, `estimates` 3, `estimate_lines` 43, `surface_planned_works` 41, `photo_assets` 0,
`photo_attachments` 0, `price_items` 50, `workflow_template_steps` 128 (all other tables are listed by the P0 query).

Observation, not a blocker: `~/backups/plan-estimate` holds older plaintext dumps (`before-stage*.sql`, 0664, inside the 0700 directory).
Encrypting or removing them is the owner's decision; 14D.6 does not touch them.

**P1 — ARM64 gate (before 14D.6, plan §16.8).** Three sub-steps, each with its own approval; the running stack is never rebuilt or
restarted and the production checkout is **not** touched (no `git pull`): the verified commit is shipped as a `git archive` of
`backend` and `docker-compose.prod.yml` into the separate directory `~/apps/plan_-_estimate-14d6/`.
*P1a* ship the archive (writes one directory). *P1b* run `bash backend/tests/runtime_proof/owner_proof.sh` there: it builds the backup
image **natively on `aarch64`** (`plan-estimate-backup:local`; PGDG key and `age` release are SHA-256-verified, Python 3.12, `pg_dump` 16,
`age` 1.3.2) and then proves non-root hardening, the actual `/backup` bind, `renameat2(RENAME_NOREPLACE)`, fsync, `flock`, SIGTERM
handling, no egress, an encrypted scratch backup and an independent restore — against **scratch** resources only (its own project
`plan-estimate-14d2d5-proof`, an internal network, a disposable `postgres:16-alpine`, `/tmp/pe-14d2d5-proof.*`). The synthetic proof needs
a throwaway age identity: since 14D.6A the image under test generates it (the host needs no `age`; nothing is installed on the VM). It
exists for the minutes of the proof under `/tmp/pe-14d2d5-proof.*/identity` (0600, synthetic data only) and is `shred`-ed in *P1c*, the
cleanup of the scratch resources (the cleanup block of plan §16.7 plus `shred -u` of the identity). *Touches:* the image store (+ ~0.4 GiB),
build cache, transient scratch containers and CPU load beside the running stack; not the production stack, volumes, networks or
database. *PASS:* `FAIL count 0` and `docker image inspect` shows `arm64`.

*P1 attempts (2026-10-05), recorded as they happened.* **Attempt 1 — FAIL, cause: file modes of the production checkout.** Run from
`~/apps/plan_-_estimate`, the build copied the checkout's file modes into the image; many tracked files there are `0600` (e.g.
`backend/app/core/config.py`) although git stores `100644`, so the non-root process could not read them (`PermissionError`) and every
step after the build failed. The image itself built natively (`arm64`), the PGDG key and `age` checksums verified, the network checks
passed. **Rule from this:** never build from the production checkout — build from a `git archive` directory (git modes), as P1a now does:
`git archive HEAD backend docker-compose.prod.yml | tar -x` into `~/apps/plan_-_estimate-14d6/`, checked for readable files. The same rule
applies to the P5 uploader build. **Attempt 2 — 5 FAIL, all one cause in the proof tooling:** the host checker and the in-container
verifier still expected a run directory of exactly `local-run.json` + the artifact, but `db-dump` has also written `ready-assets.txt` and
`recipients.txt` since 14D.2J. Every security-relevant check passed on `aarch64` (hardening, locks incl. SIGKILL release, SIGTERM exit 6
in 1 s, `CANCELLED` evidence, stale-work refusal, no egress, no secret leak, independent decrypt + READY digest + revision). Fixed in the
tooling (`check_host.py`, `scratch.py`, contract tests pinning the names to `run_sidecars`). **Attempt 3 — PASS (commit `6e3de1a`, built from a
`git archive` directory): `FAIL count: 0`, 33 checks PASS, image `arm64/linux` (537.6 MB), runs `20261005T205035Z-ce42d740` and
`20261005T205530Z-20741fd6`; the production stack was untouched (same containers, same uptime). The production checkout stayed at `68a06d5`.**

**P2 — backup role and data root.** Create `pe_backup` (the frozen policy) in the production PostgreSQL, the data root and the
pgpass, `backup.env`. *Touches:* **production PostgreSQL (a role is created)**. *PASS:* `db-dump`'s `preflight --workspace`
passes inside the `backup` service; `\du pe_backup` shows LOGIN only with `pg_read_all_data`.

*P2 executed 2026-10-05 — PASS.* P2-0 (read-only): PostgreSQL 16.15, `log_statement = none`, `password_encryption = scram-sha-256`, `ssl = off`
(→ `BACKUP_PGSSLMODE=disable` on the internal bridge), no `pe_*` role, `pg_hba` `host all all all scram-sha-256`; Compose project `plan-estimate`,
networks `plan-estimate_internal` and `pe-upload`; VM uid:gid `1001:1001`. P2a: `~/backups/plan-estimate/db-backup/` (0700; `data/{work,encrypted,evidence}`,
`secrets/{pgpass,backup.env}` 0600; password generated on the VM, never printed; recipients A and B, public). P2b: one transaction in the production
database — `CREATE ROLE pe_backup LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`, `GRANT CONNECT`, `GRANT pg_read_all_data`;
verified: member of `pg_read_all_data` only, SELECT yes, INSERT / UPDATE / DELETE / CREATE (schema, database) no. P2c: `preflight --workspace` PASS and
a connection as `pe_backup` from a container with the service's hardening (`docker run`, network `plan-estimate_internal`); `CREATE TABLE` →
`permission denied for schema public`. **Decision:** the production `db-dump` is started with `docker run` mirroring the `backup` service
(not `docker compose -p plan-estimate`): the production network carries a Compose `config-hash` label and a divergence could make Compose recreate it
under the running stack. The uploader (P5) has only the external `pe-upload` network and may use Compose.

**P3 — the first production `db-dump`.** `docker compose … run --rm --no-deps backup db-dump`. *Touches:* reads production in
one read-only snapshot (brief `ACCESS SHARE` locks); writes `encrypted/<run_id>/` locally. *PASS:* `backup complete: run_id=…
ready_count=<n>` with `n` equal to the READY count of P0; four files 0600; `work/` and `evidence/` empty; the artifact is
age-encrypted for exactly the configured recipients.

*P3 executed 2026-10-05 — PASS (first production `db-dump`, local only).* Run `20261005T214112Z-c00c8951`, exit 0, `ready_count = 0` (= P0), snapshot
method `exported-snapshot`, Alembic `0032_photo_attachments` = expected head, PostgreSQL 16.15, plaintext 338 443 B → age artifact 66 534 B
(SHA-256 `62b4443a…5cfe`, equal to the evidence and to the file on disk), 2 recipients (A and B, public), format header `age-encryption.org/v1`.
Layout: `encrypted/<run_id>/` holds exactly `plan-estimate.sql.gz.age`, `local-run.json`, `ready-assets.txt`, `recipients.txt` (all 0600, directory
0700); `work/` and `evidence/` empty; `run.lock` 0600; no plaintext dump anywhere; the production stack unchanged (same uptime). Incident: the first
P3 command block was missing line continuations and ran nothing (`command not found`, exit 127) — no container started, no data written; the
second (array-based) block succeeded. The decryption proof is P7 (private identity on the workstation only).

**P4 — cloud authority.** IAM Phase B and the R2 read-only token (owner, Console / Cloudflare), the upload env file on the VM,
`pe-upload` check. *Touches:* IAM and Cloudflare; no data. *PASS:* a read-only check that the uploader's principal can `HEAD`
the production bucket and that the R2 token can list `plan-estimate-media-prod` and **cannot** write.

*P4 executed 2026-10-05 — PASS.* Owner-created: IAM Phase B policy `plan-estimate-backup-uploader-prod-policy` (compartment `plan-estimate-backup`; the three
§6.2 statements) and the R2 token "Object Read only" for `plan-estimate-media-prod`, restricted to the VM's IP (EU jurisdiction endpoint). On the VM:
`secrets/upload.env` (0600; endpoint, key id and secret entered by hidden prompt, never printed; namespace, `plan-estimate-backup-prod`,
`eu-frankfurt-1`, `BACKUP_TOOL_COMMIT=6e3de1a3…`); uploader image `plan-estimate-backup-upload:local` built from the same `git archive` directory
(`arm64/linux`, oci 2.187.1, boto3 1.43.103) with `docker build` (not Compose). Read-only checks: the R2 token lists the production media bucket
(`KeyCount = 0`) and a write is denied (`AccessDenied`, 403); the uploader's instance principal reaches the Oracle production bucket
(`verify --mode quick` of the P3 run → `SEAL_MISSING`, i.e. readable, nothing sealed yet). The production stack was unchanged throughout.

*Pre-P5 checks (§5), 2026-10-05 — PASS.* IMDS guard `OK` (`PE-IMDS-GUARD at DOCKER-USER #1; uploader bridge br-pe-upload`); the IMDS address
169.254.169.254 is refused from the default bridge and from `plan-estimate_internal` (where the application runs) and reachable only from `pe-upload`.
Recoverability, before the permanent write: the P3 artifact was copied to the workstation's RAM (`/dev/shm`), decrypted with the working identity A and
streamed (no plaintext on disk) through `gunzip`: SHA-256 `5e175b12…be52` and size 338 443 B equal the evidence (`dump.plaintext_sha256` /
`plaintext_size`); the first line is a `pg_dump` comment; the temporary files were removed. The VM holds no private identity (the check that looked for
one there found none).

**P5 — build the uploader and `upload` (the point of no return).** `docker compose --profile backup-upload build backup-upload`,
then `docker compose … run --rm --no-deps backup-upload upload --environment production --allow-production`. *Touches:*
**writes three or more objects to the production backup bucket, permanently** (dump, manifest, `COMPLETE.json`, plus one object
per READY media file). *PASS:* `upload complete: run_id=… published objects=<3·n> ready_assets=<n>`; a second `upload` exits 8.
Before it: the checklist of §5.

*P5 executed 2026-10-05 22:17 UTC — PASS (the permanent write).* `upload --environment production --allow-production` for run
`20261005T214112Z-c00c8951` (uploader image, network `pe-upload`, instance principal): `upload complete … objects=0 ready_assets=0 prior=-`, exit 0
(`objects` counts the **media** objects of the manifest — 0 while no photo exists; the formula `3·n` above is per READY asset, the three run objects are
separate); `evidence/<run_id>.published.json` (0600) written, `work/` empty; a second `upload` printed `nothing to upload: every promoted run already has
published evidence`, exit 8. The production stack was unchanged.
*P6a executed — PASS (VM, instance principal).* `verify --mode full`: `verify ok … dump=sha256 objects_total=0`, exit 0 (expected recipients A and B from
`BACKUP_AGE_RECIPIENTS`). Bucket `plan-estimate-backup-prod` holds exactly three objects: `db/20261005T214112Z-c00c8951/plan-estimate.sql.gz.age` (66 534 B),
`runs/20261005T214112Z-c00c8951/COMPLETE.json` (465 B), `runs/20261005T214112Z-c00c8951/manifest.jsonl` (1 001 B).

**P6 — verify the sealed run.** `verify --mode full` from the VM (instance principal) and from the workstation (restore
principal, an independent reader), with `--expect-recipient` for every public recipient. *Touches:* reads. *PASS:* `verify ok`
in both, `RECIPIENTS` as configured.

*P6b executed 2026-10-06 — PASS (independent reader).* On the workstation, with a **new** API key of the restore user `plan-estimate-restore-operator`
(member of `plan-estimate-backup-restore`; config and key in `~/backups/plan-estimate/prod-restore/oci`, 0600, fingerprint checked against the key before
use; the downloaded copy shredded) and images built on the workstation from a `git archive` of `origin/stage-14` (`:p67` tags):
`verify ok: run_id=20261005T214112Z-c00c8951 mode=full dump=sha256 objects_total=0 …`, exit 0, canonical report `out/verify-prod-report.json` (0600).
Two readers (VM instance principal, workstation API key) therefore agree. Two blocks on the way were wrong and are recorded as such: the first P6b read a
`~/pe-drill-14d5/env.sh` removed by the drill cleanup, and the first OCI-config block used `read` inside `bash <<'EOF'`, which consumed the script itself
(stdin) — fixed with `read … < /dev/tty`; nothing had been written either time.

**P7 — restore the real dump (plan §11 step 7).** On the workstation: `restore --phase database` into a fresh scratch
database with the private recovery identity from RAM, then `--phase media` (nothing to restore if `n = 0`) and the integrity
checker. *Touches:* scratch only; the private identity exists in RAM for the minutes of the restore, then `shred -u`.
*PASS:* `restore ok`; Alembic = head; the restored table counts equal the P0 counts (compared by an owner-run `SELECT` on both
sides, read-only on production).

*P7 executed 2026-10-06 — PASS (the real production dump restored).* On the workstation: a scratch PostgreSQL 16 (`pe-p7-scratch-pg`, no published port, superuser
`plan_estimate` so the dump's `OWNER TO` statements resolve), `restore --phase database --run-id 20261005T214112Z-c00c8951` with the restore principal's API key and
identity A mounted read-only (from its normal 0600 file): `restore ok … phase=database ready_count=0`, exit 0; plaintext SHA-256 `5e175b12…be52` and size 338 443 B
equal the P3 evidence; `alembic_version = 0032_photo_attachments` (= repository head); READY / PENDING / FAILED 0 / 0 / 0; no media phase (manifest has none).
Row counts of **all** 40 tables of schema `public` (+ `alembic_version`), restored vs production (read-only session, over ssh): identical, and equal to the P0
baseline (`users 1`, `clients 2`, `projects 2`, `rooms 4`, `surfaces 25`, `openings 8`, `inspections 4`, `estimates 3`, `estimate_lines 43`, `surface_planned_works 41`,
`photo_assets 0`, `photo_attachments 0`, `price_items 50`, `workflow_template_steps 128`). Therefore the backup is restorable and the backup itself changed no row.

**P8 — "no change" evidence and closure.** The P0 `SELECT` repeated (production counts unchanged), R2 production bucket
inventory (unchanged — 0 objects while uploads are off), Oracle production bucket inventory (exactly the objects of P5),
`docker compose ps` (the production stack unchanged), revoke the temporary restore key, remove the workstation secrets. The
result is recorded in plan §16.x and `docs/development-progress.md`; **uploads remain OFF** — enabling them is Stage 14E.

## 5. Checklist before P5 (the permanent write)

* P3 passed and its `ready_count` equals the P0 count; the encrypted artifact's recipients are exactly the configured public ones.
* P1 passed on `aarch64`; the uploader image was built from the same commit as the backup image (`BACKUP_TOOL_COMMIT`).
* `pe-upload` exists and `pe-imds-guard.sh status` is `OK`; no other container can obtain an instance-principal token.
* The IAM Phase B statements are exactly those of §6.2 (create-only: no `OBJECT_OVERWRITE`, `OBJECT_DELETE`).
* The upload env file is `chmod 600`, outside the repository, and `BACKUP_UPLOAD_S3_*` is the **read-only** token (not the backend's).
* The owner has a way to decrypt: at least one recovery identity is reachable *right now* (otherwise P7 cannot follow).

## 6. If something fails

* Before P5: stop; nothing permanent exists. Fix and repeat the failed phase only.
* P5 fails half way: the target has at most an incomplete run (no `COMPLETE.json`), which restore and `verify` treat as invalid.
  Repeating the **same** local run is safe when only the media sync failed; a failure after the manifest was written needs a new
  `db-dump` run (plan §15). Leftover objects stay (the uploader cannot delete); the administrator may remove them.
* Never "fix" a mismatch by editing evidence, manifests or the bucket by hand.

## 7. Closure (P8, executed 2026-10-06)

**Evidence.** Oracle `plan-estimate-backup-prod` holds exactly the three objects of run `20261005T214112Z-c00c8951` (listed with the VM's instance principal after
P7): `db/…/plan-estimate.sql.gz.age` 66 534 B, `runs/…/COMPLETE.json` 465 B, `runs/…/manifest.jsonl` 1 001 B; no continuation. R2 `plan-estimate-media-prod`
holds **0** objects (the read-only token lists, never writes). The production stack ran unchanged throughout (`caddy`, `backend` healthy, `frontend`, `postgres`
healthy — the same containers with the same uptime from P0 to P8). Row counts of all tables, production vs the restored database, are identical and equal to the
P0 baseline. Local data on the VM: `encrypted/<run>/` (4 files, 0600), `evidence/<run>.published.json` (0600), empty `work/`, `run.lock`; no plaintext dump of this
run anywhere. Station evidence (0600) in `~/backups/plan-estimate/prod-restore/out/`: `verify-prod-report.json`, `restore-prod-database-report.json`,
`p7-counts-prod.txt`, `p7-counts-scratch.txt`.

**Credentials closed.** The restore user's API keys (the new one and the one left from the drill) were deleted in the OCI Console (the list is empty); with the
old key, `verify` now fails `NotAuthenticated` (401, exit 1) — revocation proven — and the key and config were `shred`-ed from the workstation. The scratch
PostgreSQL, its network and its password files on the workstation were removed. No restore credential and no private age identity has ever existed on the VM.

**Left deliberately.** (1) `upload.env` on the VM (0600): the production R2 read-only token and the target names — uploads are OFF and nothing runs it; delete
it if the token should not rest there until Stage 14E. (2) Group `plan-estimate-backup-restore` and user `plan-estimate-restore-operator` (no keys). (3) Images
`plan-estimate-backup:local` and `plan-estimate-backup-upload:local` on the VM, `:p67` images on the workstation.

**Open items (owner).** (a) Drill leftovers: the drill R2 tokens (still IP-restricted to the VM and the workstation) and `~/backups/plan-estimate/drill-secrets/` on the
workstation; the 42 objects in `plan-estimate-backup-drill` (administrator only, the uploader cannot delete). (b) The production checkout on the VM was fast-forwarded to
`68a06d5` by mistake during P1 (working tree only, nothing restarted; harmless — the next deployment pulls anyway). (c) VM leftovers: `~/apps/plan_-_estimate-14d6`
(stale archive), `~/apps/plan_-_estimate-14d6-6e3de1a`, logs `~/p1b*.log`, `~/p4-build.log`, and the older plaintext dumps in `~/backups/plan-estimate`. (d) **There is no
schedule:** the backup is as fresh as its last manual run — automation, retention and lifecycle of the production bucket are decisions for a later step, not part of
14D.6. (e) Production photo uploads remain OFF; enabling them (Stage 14E) needs the owner's approval and a fresh backup run first.

**Lessons recorded.** Never build images from the production checkout (file modes — build from a `git archive` directory); `read` inside `bash <<'EOF'` consumes the
script (use `< /dev/tty`); a pasted multi-line `docker run` needs line continuations or an array; do not reuse paths of cleaned-up drill state; Compose against the
production project is avoided (network `config-hash`), `docker run` mirroring the service is used instead.
