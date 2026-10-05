# Stage 14D.6 — First production backup run: runbook (DRAFT until executed)

> **Status:** DRAFT, written in 14D.6A together with the tooling it needs (`verify` command, uploader image, `backup-upload`
> Compose service; plan §16.19). **Nothing in this document has been executed.** Every phase below touches production in some
> way and is run by the owner only after an explicit decision for *that* phase (`CLAUDE.md`: SSH, `git pull`, Docker build,
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

**P1 — ARM64 gate (before 14D.6, plan §16.8).** On the VM: the checkout is moved to the verified commit (`git pull`; own
approval), `docker compose --profile backup build backup` (Docker build on the production host; CPU and disk contention with
the running stack — own approval), then the 14D.2D.5 runtime proof (`backend/tests/runtime_proof/owner_proof.sh`) against
**scratch** resources only: Python 3.12, `pg_dump` 16, `age` 1.3.2, non-root hardening, `renameat2(RENAME_NOREPLACE)`, fsync,
`flock`, an encrypted scratch backup and an independent restore. *Touches:* the image store and scratch containers; not the
production stack or database. *PASS:* `FAIL count 0` on `aarch64`.

**P2 — backup role and data root.** Create `pe_backup` (the frozen policy) in the production PostgreSQL, the data root and the
pgpass, `backup.env`. *Touches:* **production PostgreSQL (a role is created)**. *PASS:* `db-dump`'s `preflight --workspace`
passes inside the `backup` service; `\du pe_backup` shows LOGIN only with `pg_read_all_data`.

**P3 — the first production `db-dump`.** `docker compose … run --rm --no-deps backup db-dump`. *Touches:* reads production in
one read-only snapshot (brief `ACCESS SHARE` locks); writes `encrypted/<run_id>/` locally. *PASS:* `backup complete: run_id=…
ready_count=<n>` with `n` equal to the READY count of P0; four files 0600; `work/` and `evidence/` empty; the artifact is
age-encrypted for exactly the configured recipients.

**P4 — cloud authority.** IAM Phase B and the R2 read-only token (owner, Console / Cloudflare), the upload env file on the VM,
`pe-upload` check. *Touches:* IAM and Cloudflare; no data. *PASS:* a read-only check that the uploader's principal can `HEAD`
the production bucket and that the R2 token can list `plan-estimate-media-prod` and **cannot** write.

**P5 — build the uploader and `upload` (the point of no return).** `docker compose --profile backup-upload build backup-upload`,
then `docker compose … run --rm --no-deps backup-upload upload --environment production --allow-production`. *Touches:*
**writes three or more objects to the production backup bucket, permanently** (dump, manifest, `COMPLETE.json`, plus one object
per READY media file). *PASS:* `upload complete: run_id=… published objects=<3·n> ready_assets=<n>`; a second `upload` exits 8.
Before it: the checklist of §5.

**P6 — verify the sealed run.** `verify --mode full` from the VM (instance principal) and from the workstation (restore
principal, an independent reader), with `--expect-recipient` for every public recipient. *Touches:* reads. *PASS:* `verify ok`
in both, `RECIPIENTS` as configured.

**P7 — restore the real dump (plan §11 step 7).** On the workstation: `restore --phase database` into a fresh scratch
database with the private recovery identity from RAM, then `--phase media` (nothing to restore if `n = 0`) and the integrity
checker. *Touches:* scratch only; the private identity exists in RAM for the minutes of the restore, then `shred -u`.
*PASS:* `restore ok`; Alembic = head; the restored table counts equal the P0 counts (compared by an owner-run `SELECT` on both
sides, read-only on production).

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
