# Stage 14D.5 — Isolated backup / restore drill: runbook (EXECUTED 2026-10-05 — PASS)

> **Status:** EXECUTED by the owner on 2026-10-05 (run `20261005T052617Z-66a27f56`): steps 1–6 of plan §11 **PASS**; step 7
> (the real production dump) belongs to 14D.6. Results and the problems met on the way: plan §16.18. The verified
> command blocks, in their corrected final form, are in `docs/STAGE_14D5_DRILL_COMMANDS.md`.
>
> Written in 14D.5A together with the drill tool (`backend/scripts/stage14d5_drill_tool.py`, plan
> §16.17). Every phase was executed by the owner; each ends with an explicit PASS condition and the output to send back.
> Nothing here touches production data: production PostgreSQL, the production R2 bucket and the production Oracle backup
> bucket are neither written nor used as a restore target. The only production contact is the optional read-only
> "before / after" inventory of §6 / §13 — each such command needs your explicit decision to run it.
> Executable commands stay DRAFT until the phase that verifies them.

## 1. What the drill proves (plan §11) and how

| Plan §11 step | Phase | PASS condition |
|---|---|---|
| 1 seed the synthetic fixture through the **real upload pipeline** | C | `seeded: … images=4`; a fixture file with 4 READY assets |
| 2 backup run → `drill-backup` → COMPLETE (encrypted dump included) | D (`db-dump`), E (`upload`) | `backup complete`, `upload complete … published objects=12 ready_assets=4` |
| 3 §9 restore chain into a fresh scratch database | F (`restore --phase database`) | `restore ok … phase=database ready_count=4`; Alembic = head, READY digest and status counts equal the manifest's |
| 5 integrity checker **before** media: exactly the expected missing objects | F | `errors = 12` (4 `MISSING_ORIGINAL` + 8 `MISSING_DERIVATIVE`), `expected_present = 0` |
| 4 restore media from `drill-backup` into the empty `drill-restore` bucket, SHA-256 verified | G (`restore --phase media`) | `restore ok … phase=media restored=12 already_present=0 total=12` |
| 5 integrity checker **after**: clean with `--verify-sha256 --strict` | G | exit 0, `checksum_verified = 4`, no findings |
| 6 the backend on the restored database + `drill-restore` serves list / detail / presigned URLs, bytes equal the manifest | H (`verify-serving`) | `RESULT: PASS (8/8 checks passed)` |
| 7 a real production dump restores into scratch PostgreSQL | **not here — 14D.6** | — |
| "no write to any production resource" | B and I | `inventories identical` for each production resource inspected |

PASS of 14D.5 = every phase above passes. Anything else = FAIL: stop, report, no cleanup, no retry with changes.

## 2. Topology (why it is split)

* **W — the owner's workstation (Docker, amd64).** Scratch PostgreSQL 16, the scratch backend, `db-dump` (the
  hardened backup image — the same flags as the production `backup` service), `restore` with the **restore
  principal's API key** and the private age identity. Restore credentials never go to the production VM.
* **V — the Oracle VM.** Only `upload`: it needs the **instance principal**, which exists only there, and only on the
  `pe-upload` network behind the IMDS guard. It receives one promoted run directory (encrypted dump, sidecars, local
  evidence) and the R2 **drill-source** read token, and nothing else. No `git pull`, no Docker build and no Compose
  change on the production VM: the source is shipped as an archive into a separate directory and mounted read-only.

Flow: `W: seed → db-dump → copy run → V: upload → W: restore (database) → integrity → restore (media) → integrity →
serving check`.

## 3. Resources, secrets and invariants

* Buckets: R2 `plan-estimate-media-drill-source` (seed, read by `upload`), R2 `plan-estimate-media-drill-restore`
  (restore destination, must be empty), Oracle `plan-estimate-backup-drill`.
* Secret files (all `chmod 600`, never printed, never committed): `r2-drill-source.env`, `r2-drill-restore.env`
  (`R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, restore one also
  `R2_FORBIDDEN_BUCKETS`), the **drill age identity** (private, on W only), the **restore principal's OCI config + key**
  (on W only; re-created by the owner — see Phase 0).
* Every container that holds a secret runs with `--cap-drop ALL`, `no-new-privileges`, the host UID:GID, and — where it
  can — `--read-only`. Scratch passwords are random per drill and live only in `$DRILL/secrets` (0700) and in
  scratch-container environments.
* The scratch database names carry the markers the tools require (`pe_restore_scratch…`); the restore destination
  must be a drill bucket and never a forbidden one; the drill tool talks only to a backend whose host is loopback or
  contains `scratch`.

## 4. Variables (`$DRILL/env.sh`, sourced by every phase)

The paths marked `CHECK` depend on where your secret files actually are — Phase 0 prints what exists, and the file is
adjusted before Phase A. Phases are run as `bash <<'EOF' … EOF` blocks so that they behave identically in bash and zsh.

```bash
# --- env.sh (W) ---
export REPO=~/apps/plan_-_estimate                   # CHECK: your checkout (at the 14D.5A commit or later)
export DRILL=~/pe-drill-14d5                         # work directory, created 0700 in Phase A
export SECRETS=~/backups/plan-estimate/drill-secrets # CHECK: r2-drill-source.env, r2-drill-restore.env
export AGE_IDENTITY="$SECRETS/age-drill.key"         # CHECK: the PRIVATE drill identity (never copied to V)
export OCI_CFG_DIR="$SECRETS/oci"                    # CHECK: restore principal: config + key (re-created, Phase 0)
export OCI_NAMESPACE=''                              # CHECK: Object Storage namespace
export BACKUP_BUCKET=plan-estimate-backup-drill
export IMG='python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f'
export BK=plan-estimate-backup-drill:local           # the backup image built in Phase A
export NET=pe-drill
export PG_IMAGE=postgres:16-alpine
export SRC_DB=pe_drill_source
export RESTORE_DB=pe_restore_scratch_drill
export SRC_BACKEND=pe-drill-scratch-backend
export RESTORED_BACKEND=pe-drill-scratch-backend-restored
# --- V (the Oracle VM) ---
export V_HOST=''                                     # CHECK: ssh target, e.g. ubuntu@<ip>
export V_ROOT='~/backups/plan-estimate/drill-upload' # separate from the production backup root
export V_SECRETS='~/backups/plan-estimate/drill-secrets'
```

## 5. Phase 0 — read-only facts (W) · Phase A — scratch infrastructure (W)

Phase 0 lists which of the files above exist (names and modes only), the Docker and Git state, and whether the restore
principal's API key exists. **The restore principal's API key must be re-created in the OCI Console by the owner**
(user `plan-estimate-restore-operator` → API keys → add; save the private key on W only, write a config with
`key_file=/run/oci/key.pem`, both `chmod 600`, both under `$OCI_CFG_DIR`). The key is never pasted into chat.

Phase A creates `$DRILL` (0700) with `data/` (→ `/backup`), `secrets/`, the network `pe-drill` (an ordinary bridge: it
has no route to the IMDS guard's `pe-upload` bridge), a disposable `postgres:16-alpine` (`pe-drill-pg`, no published
port, superuser password from a random file) with roles `pe_app`, `pe_backup` (the frozen 14D.2D.4 policy: LOGIN +
CONNECT on the source database + `pg_read_all_data`, nothing else) and databases `pe_drill_source` (owner `pe_app`)
and `pe_restore_scratch_drill` (`TEMPLATE template0`, empty); the backup image
(`docker build -f backend/Dockerfile.backup -t $BK backend`); the derived env files; and the **scratch backend**
(`backend/Dockerfile` image) on `pe-drill`, started with `ENVIRONMENT=development`, `MOCK_TELEGRAM_AUTH=true`,
`MEDIA_STORAGE_BACKEND=s3`, `MEDIA_STORAGE_NAME=r2-drill`, `MEDIA_S3_*` from the **drill-source** token and
`PHOTO_UPLOADS_ENABLED=true` — uploads are enabled only in this throw-away environment. Its entrypoint applies
`alembic upgrade head` to `pe_drill_source`. PASS: `pe-drill-pg` accepts connections, `GET /api/health` of the scratch
backend returns `{"status":"ok"}`, `alembic_version` is the repository head.

The command blocks were issued one phase at a time (the owner pasted the output of each phase back); the verified, corrected
blocks are in `docs/STAGE_14D5_DRILL_COMMANDS.md`. Operational note from the execution: R2 API tokens can be restricted to a
client IP address (the drill tokens were restricted to the VM): add the workstation's public IP to both drill tokens before
Phase C, otherwise every call from the workstation is `403 AccessDenied`.

## 6. Phase B — production "before" inventories (read-only, optional, owner decision)

Production R2 holds 0 objects by design (uploads OFF) and no production token is used by the drill. Candidates:

* Oracle `plan-estimate-backup-prod`: `stage14d5_drill_tool.py inventory --provider oci --bucket
  plan-estimate-backup-prod --output $DRILL/prod-oci-before.json` with the restore principal (list is read-only; if
  the principal is denied, the denial is the evidence and is recorded as such).
* Production PostgreSQL: one read-only `SELECT count(*) FROM photo_assets` on the VM (needs the owner's explicit decision
  each time, as every production access does).

Phase I repeats the same commands and `compare-inventory` must say `inventories identical`.

## 7. Phases C–H

* **C — seed (step 1).** `stage14d5_drill_tool.py seed --base-url http://pe-drill-scratch-backend:8000 --fixture-file
  /drill/fixture.json` in a container on `pe-drill`: logs in with mock auth, creates a client and a project and uploads the
  four generated images (JPEG, PNG, WebP, EXIF-orientation JPEG) through `POST /api/projects/{id}/photos`. PASS:
  `seeded: … images=4`, the fixture file (0600) lists 4 READY assets, and the drill-source bucket holds 12 objects.
* **D — `db-dump` (step 2a).** The backup image run with the production service's flags against `pe_drill_source`
  as `pe_backup`; the recipient is derived from the drill identity (`age-keygen -y`), so no recipient is typed.
  PASS: `backup complete: run_id=… ready_count=4`; `encrypted/<run_id>/` holds the artifact, `local-run.json`,
  `ready-assets.txt`, `recipients.txt` (0600), `work/` and `evidence/` are empty.
* **E — `upload` (step 2b, on V).** The run directory is copied with `tar` over ssh into `$V_ROOT/data/encrypted/`, the
  source (`backend/app`) is shipped as a `git archive` into `$V_ROOT/src` (no `git pull`, no build), and `upload
  --environment drill` runs in `python:3.12-slim` on `pe-upload` with the pinned dependency set installed by `pip
  --target` (`sqlalchemy[asyncio]==2.1.1 greenlet==3.5.6 pydantic==2.13.5 pydantic-settings==2.15.0 pyjwt==2.15.0
  asyncpg==0.31.0 alembic==1.20.0 oci==2.187.1 boto3==1.43.103 botocore==1.43.103 s3transfer==0.19.2 urllib3==2.8.0
  anyio==4.15.1` — resolved and import-checked in a clean environment). PASS: exit 0 and `upload complete:
  run_id=… published objects=12 ready_assets=4`; `evidence/<run_id>.published.json` exists. A second `upload` run
  must exit 8 (`ALREADY_PUBLISHED`).
* **F — database (steps 3 and 5-before).** `restore --phase database` on W with the restore principal, then the
  integrity checker against the restored database and the **empty** drill-restore bucket. PASS: `restore ok …
  phase=database`; the checker exits 1 with exactly 12 errors (4 `MISSING_ORIGINAL`, 8 `MISSING_DERIVATIVE`).
* **G — media (steps 4 and 5-after).** `restore --phase media`, then the checker with `--verify-sha256 --strict`. PASS:
  `restored=12 already_present=0 total=12`; the checker exits 0 with `checksum_verified = 4`.
* **H — serving (step 6).** A second scratch backend on the restored database and the drill-restore bucket
  (uploads off), then `stage14d5_drill_tool.py verify-serving --run-id <run_id>`. PASS: `RESULT: PASS (8/8 checks passed)`.

## 8. Phase I — production "after" inventories · Phase J — cleanup

Phase I repeats Phase B and runs `compare-inventory`. Cleanup after your sign-off is manual: the three scratch
containers and the network, `$DRILL`, the copied run on V (`$V_ROOT`), the drill-source and drill-restore objects
(`photos/v1/` — the drill tokens can delete there), and — by the Oracle administrator only — the objects in
`plan-estimate-backup-drill` (the uploader principal cannot delete by design). Nothing in production needs cleanup.

## 9. Evidence to send back (contains no secret)

The summary lines named in each PASS condition, `ls -l` of the run directory (names and modes), the integrity checker's
counts, and the final `compare-inventory` lines. Hashes, keys, presigned URLs and object names are never printed by the
tools.
