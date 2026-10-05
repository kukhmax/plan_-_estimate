# Stage 14D.5 — verified command blocks (executed 2026-10-05)

> These are the blocks that **passed** in the owner's 14D.5B drill, in their corrected final form (see
> `docs/STAGE_14D_BACKUP_RESTORE_PLAN.md` §16.18 for what each correction fixed). Each block is run as
> `bash <<'EOF' … EOF` so that it behaves identically in bash and zsh. Blocks marked **W** run on the owner's
> workstation (Docker, amd64); blocks marked **V** are executed on the Oracle VM through `ssh` from W.
> Nothing here contains a secret. Values that depend on the environment live in `env.sh` (block A1) and are
> never typed into a block: `OCI_NAMESPACE` (Object Storage namespace) and `V_HOST` (ssh target).
>
> Rules the blocks rely on (each one was learned the hard way during the drill):
> * `set -o pipefail` plus a `… | head -c N` secret generator kills the script with SIGPIPE — generate with `od`.
> * `ssh` reads the stdin of the surrounding `bash <<EOF`; use `ssh -n` unless stdin is given explicitly.
> * `docker run --tmpfs /tmp` is `noexec` by default; use `--tmpfs /tmp:rw,exec,…` when `pip --target` installs
>   compiled wheels there.
> * Seed once: blocks C and D refuse to run on a non-empty bucket / database / `encrypted/`.

## A1 (W) — variables and a check of the token files

```bash
bash <<'EOF'
set -euo pipefail
mkdir -m 700 -p "$HOME/pe-drill-14d5"
cat > "$HOME/pe-drill-14d5/env.sh" <<'ENVEOF'
export REPO=<absolute path of the repository checkout>
export DRILL=$HOME/pe-drill-14d5
export SECRETS=$HOME/backups/plan-estimate/drill-secrets   # r2-drill-source.env, r2-drill-restore.env, age-drill.key
export AGE_IDENTITY=$SECRETS/age-drill.key                 # the PRIVATE drill identity (W only)
export OCI_CFG_DIR=$SECRETS/oci                            # restore principal: config + key.pem (W only)
export OCI_NAMESPACE=<Object Storage namespace>            # non-secret; Console: Object Storage -> Buckets
export V_HOST=<user>@<vm address>
export BACKUP_BUCKET=plan-estimate-backup-drill
export BK=plan-estimate-backup:drill
export BACKEND_IMG=pe-drill-backend:local
export NET=pe-drill
export PG_IMAGE=postgres:16-alpine
export SRC_DB=pe_drill_source
export RESTORE_DB=pe_restore_scratch_drill
export SRC_BACKEND=pe-drill-scratch-backend
export RESTORED_BACKEND=pe-drill-scratch-backend-restored
ENVEOF
chmod 600 "$HOME/pe-drill-14d5/env.sh"
source "$HOME/pe-drill-14d5/env.sh"
for f in r2-drill-source.env r2-drill-restore.env; do
  echo "-- $f (names only)"; sed -E 's/=.*/=<hidden>/' "$SECRETS/$f"
  grep -E '^(R2_BUCKET|R2_FORBIDDEN_BUCKETS)=' "$SECRETS/$f" || true
done
docker network inspect "$NET" >/dev/null 2>&1 && echo "FAIL: network $NET already exists" || echo "ok: network $NET is free"
docker ps -a --format '{{.Names}}' | grep -E '^pe-drill' && echo "FAIL: pe-drill containers exist" || echo "ok: no pe-drill containers"
EOF
```

The R2 drill tokens may be restricted to the VM's IP address in Cloudflare (this happened): before block C add the
workstation's public IP to both drill tokens, then check them with block A0 below.

## A0 (W) — token check from the workstation (read-only; only response codes are printed)

```bash
bash <<'EOF'
set -euo pipefail
source "$HOME/pe-drill-14d5/env.sh"
umask 077
mkdir -m 700 -p "$DRILL/out"
cat > "$DRILL/out/r2diag.py" <<'PY'
import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

c = boto3.session.Session().client(
    "s3", endpoint_url=os.environ["R2_ENDPOINT_URL"], region_name="auto",
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
b = os.environ["R2_BUCKET"]
print("bucket:", b, "| bucket-name-clean:", b.isascii() and b.strip() == b)

def t(name, fn):
    try:
        r = fn()
        print(f"{name:28} OK   keycount={r.get('KeyCount', '-')}")
    except ClientError as e:
        print(f"{name:28} ERR  {e.response['Error']['Code']} http={e.response['ResponseMetadata']['HTTPStatusCode']}")

t("list, no prefix", lambda: c.list_objects_v2(Bucket=b, MaxKeys=1))
t("list, prefix photos/v1/", lambda: c.list_objects_v2(Bucket=b, Prefix="photos/v1/", MaxKeys=1))
t("head bucket", lambda: c.head_bucket(Bucket=b))
PY
for f in r2-drill-source.env r2-drill-restore.env; do
  echo "===== $f ====="
  docker run --rm -i --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp:size=16m \
    -e HOME=/tmp --env-file "$SECRETS/$f" --entrypoint python "$BK" - < "$DRILL/out/r2diag.py"
done
EOF
```
PASS: `OK` and `keycount=0` in every line for both files (the image `$BK` is built in A2, run A2 first).

## A2 (W) — network, PostgreSQL 16, roles, databases, images

```bash
bash <<'EOF'
set -euo pipefail
source "$HOME/pe-drill-14d5/env.sh"
umask 077
docker network inspect "$NET" >/dev/null 2>&1 && { echo "FAIL: network $NET exists"; exit 1; }
docker ps -a --format '{{.Names}}' | grep -E '^pe-drill' && { echo "FAIL: pe-drill containers exist"; exit 1; } || true
rm -f "$DRILL"/secrets/*
mkdir -m 700 -p "$DRILL/data" "$DRILL/secrets"
for n in pg_super_pw pg_app_pw pg_backup_pw jwt_secret; do
  head -c 20 /dev/urandom | od -An -vtx1 | tr -d ' \n' > "$DRILL/secrets/$n"
  [ "$(wc -c < "$DRILL/secrets/$n")" = 40 ] || { echo "FAIL: secret $n has the wrong size"; exit 1; }
done
printf 'pe-drill-pg:5432:%s:pe_backup:%s\n' "$SRC_DB" "$(cat "$DRILL/secrets/pg_backup_pw")" > "$DRILL/secrets/pgpass"
printf 'pe-drill-pg:5432:%s:postgres:%s\n' "$RESTORE_DB" "$(cat "$DRILL/secrets/pg_super_pw")" > "$DRILL/secrets/pgpass-restore"
chmod 600 "$DRILL"/secrets/*
docker network create "$NET" >/dev/null
docker run -d --name pe-drill-pg --network "$NET" \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/pw -v "$DRILL/secrets/pg_super_pw":/run/secrets/pw:ro "$PG_IMAGE" >/dev/null
for i in $(seq 1 60); do docker exec pe-drill-pg pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1 && break; sleep 1; done
docker exec pe-drill-pg pg_isready -h 127.0.0.1 -U postgres
docker exec -i pe-drill-pg psql -U postgres -v ON_ERROR_STOP=1 -q <<SQL
CREATE ROLE pe_app LOGIN PASSWORD '$(cat "$DRILL/secrets/pg_app_pw")';
CREATE ROLE pe_backup LOGIN PASSWORD '$(cat "$DRILL/secrets/pg_backup_pw")';
CREATE DATABASE $SRC_DB OWNER pe_app;
CREATE DATABASE $RESTORE_DB TEMPLATE template0;
GRANT CONNECT ON DATABASE $SRC_DB TO pe_backup;
GRANT pg_read_all_data TO pe_backup;
SQL
docker exec pe-drill-pg psql -U postgres -Atc "select datname from pg_database where datname like 'pe_%' order by 1"
echo "== building images (several minutes) =="
docker build -q -f "$REPO/backend/Dockerfile.backup" -t "$BK" "$REPO/backend"
docker build -q -t "$BACKEND_IMG" "$REPO/backend"
docker image ls --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep -E "^(plan-estimate-backup:drill|pe-drill-backend:local)"
echo "A2: PASS"
EOF
```

## A3 (W) — the scratch backend (uploads enabled, mock authentication — drill only)

```bash
bash <<'EOF'
set -euo pipefail
source "$HOME/pe-drill-14d5/env.sh"
umask 077
for n in pg_app_pw jwt_secret; do [ -s "$DRILL/secrets/$n" ] || { echo "FAIL: $n missing - run A2 first"; exit 1; }; done
derive() { sed -n -E -e "s/^R2_ENDPOINT_URL=/$2_ENDPOINT_URL=/p" -e "s/^R2_ACCESS_KEY_ID=/$2_ACCESS_KEY_ID=/p" \
  -e "s/^R2_SECRET_ACCESS_KEY=/$2_SECRET_ACCESS_KEY=/p" -e "s/^R2_BUCKET=/$2_BUCKET=/p" "$1"; }
rm -f "$DRILL/secrets/backend-source.env"
{
  derive "$SECRETS/r2-drill-source.env" MEDIA_S3
  echo MEDIA_S3_REGION=auto
  echo MEDIA_STORAGE_BACKEND=s3
  echo MEDIA_STORAGE_NAME=r2-drill
  echo PHOTO_UPLOADS_ENABLED=true
  echo ENVIRONMENT=development
  echo APP_ENV=development
  echo MOCK_TELEGRAM_AUTH=true
  echo TELEGRAM_BOT_TOKEN=drill-not-a-real-token
  echo "JWT_SECRET_KEY=$(cat "$DRILL/secrets/jwt_secret")"
  echo "DATABASE_URL=postgresql+asyncpg://pe_app:$(cat "$DRILL/secrets/pg_app_pw")@pe-drill-pg:5432/$SRC_DB"
} > "$DRILL/secrets/backend-source.env"
chmod 600 "$DRILL/secrets/backend-source.env"
docker run -d --name "$SRC_BACKEND" --network "$NET" --env-file "$DRILL/secrets/backend-source.env" "$BACKEND_IMG" >/dev/null
ok=0
for i in $(seq 1 90); do
  if docker exec "$SRC_BACKEND" curl -fsS http://127.0.0.1:8000/api/health 2>/dev/null; then ok=1; echo; break; fi
  sleep 2
done
[ "$ok" = 1 ] || { echo "FAIL: backend did not become healthy"; docker logs --tail 40 "$SRC_BACKEND" | sed -E 's/(postgresql[^ ]*:\/\/[^:]+:)[^@]+@/\1***@/'; exit 1; }
echo "alembic head (repo):    $(docker exec "$SRC_BACKEND" alembic heads | awk '{print $1}')"
echo "alembic version (DB):   $(docker exec pe-drill-pg psql -U postgres -d "$SRC_DB" -Atc 'select version_num from alembic_version')"
echo "photo_assets rows:      $(docker exec pe-drill-pg psql -U postgres -d "$SRC_DB" -Atc 'select count(*) from photo_assets')"
docker ps --filter name=pe-drill --format '{{.Names}}  {{.Status}}  ports={{.Ports}}'
echo "PHASE A: PASS"
EOF
```
PASS: `{"status":"ok"}`, repo head equals DB version, `photo_assets rows: 0`, no published ports.

## C (W) — seed through the real upload endpoint (run ONCE)

```bash
bash <<'EOF'
set -euo pipefail
source "$HOME/pe-drill-14d5/env.sh"
umask 077
mkdir -m 700 -p "$DRILL/out"
derive() { sed -n -E -e "s/^R2_ENDPOINT_URL=/$2_ENDPOINT_URL=/p" -e "s/^R2_ACCESS_KEY_ID=/$2_ACCESS_KEY_ID=/p" \
  -e "s/^R2_SECRET_ACCESS_KEY=/$2_SECRET_ACCESS_KEY=/p" "$1"; }
derive "$SECRETS/r2-drill-source.env" INVENTORY_S3 > "$DRILL/secrets/inventory-source.env"
chmod 600 "$DRILL/secrets/inventory-source.env"
SRC_BUCKET="$(sed -n 's/^R2_BUCKET=//p' "$SECRETS/r2-drill-source.env")"
base=(docker run --rm --network "$NET" --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges
      --read-only --tmpfs /tmp:size=64m -e HOME=/tmp -v "$DRILL/out":/out -v "$REPO/backend/scripts":/scripts:ro
      --entrypoint python)
T=/scripts/stage14d5_drill_tool.py
[ ! -e "$DRILL/out/fixture.json" ] || { echo "FAIL: fixture.json already exists - this phase was already run"; exit 1; }
rm -f "$DRILL/out/src-before.json" "$DRILL/out/src-after-seed.json"
echo "== drill-source bucket BEFORE seeding =="
"${base[@]}" --env-file "$DRILL/secrets/inventory-source.env" "$BK" $T inventory --provider r2 --bucket "$SRC_BUCKET" --output /out/src-before.json
grep -q '"objects":0,' "$DRILL/out/src-before.json" || { echo "FAIL: the bucket is not empty - nothing was seeded"; exit 1; }
[ "$(docker exec pe-drill-pg psql -U postgres -d "$SRC_DB" -Atc 'select count(*) from photo_assets')" = 0 ] || { echo "FAIL: the database is not empty - nothing was seeded"; exit 1; }
echo "== seed through the real upload endpoint =="
"${base[@]}" "$BK" $T seed --base-url "http://$SRC_BACKEND:8000" --fixture-file /out/fixture.json
echo "== database =="
docker exec pe-drill-pg psql -U postgres -d "$SRC_DB" -Atc "select status || ' ' || count(*) from photo_assets group by status order by status"
echo "== drill-source bucket AFTER seeding =="
"${base[@]}" --env-file "$DRILL/secrets/inventory-source.env" "$BK" $T inventory --provider r2 --bucket "$SRC_BUCKET" --output /out/src-after-seed.json
grep -q '"objects":12,' "$DRILL/out/src-after-seed.json" || { echo "FAIL: expected 12 objects after seeding"; exit 1; }
[ "$(docker exec pe-drill-pg psql -U postgres -d "$SRC_DB" -Atc "select count(*) from photo_assets where status='READY'")" = 4 ] || { echo "FAIL: expected 4 READY assets"; exit 1; }
echo "PHASE C: PASS (4 images, 4 READY, 12 objects)"
EOF
```

## C-reset (W) — only if C was run twice or failed half way (scratch database and the drill-source objects)

Stops the scratch backend, recreates `pe_drill_source`, deletes every object under `photos/v1/` of the drill-source bucket
(the bucket name is enforced in code), removes a mistaken local run, restarts the backend. See §16.18 of the plan for the
incident this block came from; the exact block is the one issued during the drill and consists of the five steps above.

## D (W) — `db-dump` with the production service's hardening flags

```bash
bash <<'EOF'
set -euo pipefail
source "$HOME/pe-drill-14d5/env.sh"
umask 077
RECIP="$(docker run --rm --user "$(id -u):$(id -g)" -v "$AGE_IDENTITY":/id:ro --entrypoint age-keygen "$BK" -y /id)"
case "$RECIP" in age1*) echo "recipient derived (public): $RECIP";; *) echo "FAIL: no public recipient"; exit 1;; esac
[ -z "$(ls -A "$DRILL/data/encrypted")" ] || { echo "FAIL: encrypted/ is not empty - this phase was already run"; exit 1; }
docker run --rm --name pe-drill-dbdump --network "$NET" --user "$(id -u):$(id -g)" --init --read-only \
  --cap-drop ALL --security-opt no-new-privileges --memory 512m --cpus 0.5 --pids-limit 64 --tmpfs /tmp:size=16m \
  -e PGHOST=pe-drill-pg -e PGPORT=5432 -e PGDATABASE="$SRC_DB" -e PGUSER=pe_backup -e PGSSLMODE=disable \
  -e PGPASSFILE=/run/secrets/pgpass -e BACKUP_AGE_RECIPIENTS="$RECIP" \
  -v "$DRILL/data":/backup -v "$DRILL/secrets/pgpass":/run/secrets/pgpass:ro "$BK" db-dump
echo "exit=$?"
find "$DRILL/data" -maxdepth 3 -printf '%m %p\n' | sort -k2
EOF
```

## E1 (W → V) — ship the run and the source to the VM (no `git pull`, no build on the VM)

```bash
bash <<'EOF'
set -euo pipefail
source "$HOME/pe-drill-14d5/env.sh"
RUN="$(ls "$DRILL/data/encrypted")"
case "$RUN" in *[!0-9A-Za-z_-]*|"") echo "FAIL: expected exactly one run id, got: $RUN"; exit 1;; esac
[ "$(ls "$DRILL/data/encrypted" | wc -l)" = 1 ] || { echo "FAIL: more than one run in encrypted/"; exit 1; }
[ -z "$(git -C "$REPO" status --porcelain)" ] || { echo "FAIL: the working tree is not clean"; exit 1; }
COMMIT="$(git -C "$REPO" rev-parse HEAD)"
echo "run: $RUN | source commit: ${COMMIT:0:12}"
VROOT='$HOME/backups/plan-estimate/drill-upload'
echo "== 1. directories on the VM =="
ssh -n "$V_HOST" "umask 077; mkdir -p $VROOT/data/work $VROOT/data/encrypted $VROOT/data/evidence $VROOT/src; ls -ld $VROOT $VROOT/data/*"
echo "== 2. the run =="
tar -C "$DRILL/data/encrypted" -cf - "$RUN" | ssh "$V_HOST" "umask 077; tar -C $VROOT/data/encrypted -xpf -"
echo "== 3. the source (git archive of HEAD, backend/app only) =="
git -C "$REPO" archive --format=tar HEAD backend/app | ssh "$V_HOST" "umask 022; rm -rf $VROOT/src/backend; tar -C $VROOT/src -xf -"
echo "== 4. the upload env file, built on the VM from the drill-source token =="
ssh "$V_HOST" bash -s -- "$COMMIT" <<'REMOTE'
set -euo pipefail
umask 077
S="$HOME/backups/plan-estimate/drill-secrets"
OUT="$S/drill-upload.env"
{
  sed -n -E -e 's/^R2_ENDPOINT_URL=/MEDIA_S3_ENDPOINT_URL=/p' -e 's/^R2_ACCESS_KEY_ID=/MEDIA_S3_ACCESS_KEY_ID=/p' \
           -e 's/^R2_SECRET_ACCESS_KEY=/MEDIA_S3_SECRET_ACCESS_KEY=/p' -e 's/^R2_BUCKET=/MEDIA_S3_BUCKET=/p' "$S/r2-drill-source.env"
  echo MEDIA_S3_REGION=auto
  echo MEDIA_STORAGE_NAME=r2-drill
  echo BACKUP_OCI_BUCKET=plan-estimate-backup-drill
  echo "BACKUP_TOOL_COMMIT=$1"
} > "$OUT"
chmod 600 "$OUT"
echo "-- $OUT (names only)"; sed -E 's/=.*/=<hidden>/' "$OUT" | sort
REMOTE
echo "== 5. verify: modes and artifact SHA-256 on both sides =="
LOCAL_SHA="$(sha256sum "$DRILL/data/encrypted/$RUN/plan-estimate.sql.gz.age" | cut -d' ' -f1)"
REMOTE_SHA="$(ssh -n "$V_HOST" "sha256sum $VROOT/data/encrypted/$RUN/plan-estimate.sql.gz.age" | cut -d' ' -f1)"
[ "$LOCAL_SHA" = "$REMOTE_SHA" ] && echo "artifact SHA-256 equal on both sides" || { echo "FAIL: SHA-256 differs"; exit 1; }
ssh -n "$V_HOST" "find $VROOT/data -maxdepth 3 -printf '%m %u %p\n' | sort -k3; ls $VROOT/src/backend/app | head -3"
echo "E1: PASS"
EOF
```

## E2 (W → V) — `upload` on `pe-upload` with the instance principal (twice: the second must exit 8)

```bash
bash <<'EOF'
set -euo pipefail
source "$HOME/pe-drill-14d5/env.sh"
ssh "$V_HOST" bash -s -- "$OCI_NAMESPACE" <<'REMOTE'
set -euo pipefail
NS="$1"
V="$HOME/backups/plan-estimate/drill-upload"
IMG='python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f'
INSTALL='pip install -q --no-cache-dir --target /tmp/deps "sqlalchemy[asyncio]==2.1.1" greenlet==3.5.6 pydantic==2.13.5 pydantic-settings==2.15.0 pyjwt==2.15.0 asyncpg==0.31.0 alembic==1.20.0 oci==2.187.1 boto3==1.43.103 botocore==1.43.103 s3transfer==0.19.2 urllib3==2.8.0 anyio==4.15.1'
UPLOAD='PYTHONPATH=/tmp/deps:/app python -m app.backup upload --environment drill --scratch-dir /tmp'
CMD="$INSTALL && { $UPLOAD; echo \"first upload exit=\$?\"; $UPLOAD; echo \"second upload exit=\$?\"; }"
set +e
docker run --rm --name pe-drill-upload --network pe-upload --user "$(id -u):$(id -g)" \
  --cap-drop ALL --security-opt no-new-privileges \
  -e HOME=/tmp -e PIP_DISABLE_PIP_VERSION_CHECK=1 -e PYTHONDONTWRITEBYTECODE=1 \
  --env-file "$HOME/backups/plan-estimate/drill-secrets/drill-upload.env" -e BACKUP_OCI_NAMESPACE="$NS" \
  -v "$V/src/backend/app":/app/app:ro -v "$V/data":/backup "$IMG" sh -c "$CMD"
code=$?
set -e
echo "docker exit=$code"
echo "== local evidence on the VM =="
find "$V/data/evidence" -type f -printf '%m %u %f\n'
REMOTE
EOF
```
PASS: `upload complete: … published objects=12 ready_assets=4 prior=-`, `first upload exit=0`, `nothing to upload: every
promoted run already has published evidence`, `second upload exit=8`, one `*.published.json` (0600).

## The restore principal's files (W) — private key, not the public one

The Console offers two downloads; only the **private** key (`…pem` without `_public`, ~1.7 kB, first line contains
`PRIVATE KEY`) goes to `$OCI_CFG_DIR/key.pem`. The config is built by a small script that asks for `user`, `tenancy`,
`region` and `fingerprint`, refuses values of the wrong shape, computes the fingerprint of `key.pem` and refuses a
mismatch, then writes `[DEFAULT]` with `key_file=/run/oci/key.pem` (the path inside the container) — both files 0600.

## F (W) — restore the database, integrity check before the media

```bash
bash <<'EOF'
set -euo pipefail
source "$HOME/pe-drill-14d5/env.sh"
umask 077
NS="$OCI_NAMESPACE"
RUN=<run id printed by block D>
derive() { sed -n -E -e "s/^R2_ENDPOINT_URL=/$2_ENDPOINT_URL=/p" -e "s/^R2_ACCESS_KEY_ID=/$2_ACCESS_KEY_ID=/p" \
  -e "s/^R2_SECRET_ACCESS_KEY=/$2_SECRET_ACCESS_KEY=/p" -e "s/^R2_BUCKET=/$2_BUCKET=/p" "$1"; }
{ derive "$SECRETS/r2-drill-restore.env" RESTORE_S3; echo RESTORE_S3_REGION=auto; } > "$DRILL/secrets/restore-s3.env"
{ derive "$SECRETS/r2-drill-restore.env" MEDIA_S3
  echo MEDIA_S3_REGION=auto; echo MEDIA_STORAGE_BACKEND=s3; echo MEDIA_STORAGE_NAME=r2-drill
  echo PHOTO_UPLOADS_ENABLED=false; echo ENVIRONMENT=development; echo APP_ENV=development; echo PHOTO_TEMP_DIR=/tmp
  echo "DATABASE_URL=postgresql+asyncpg://postgres:$(cat "$DRILL/secrets/pg_super_pw")@pe-drill-pg:5432/$RESTORE_DB"
} > "$DRILL/secrets/integrity-restore.env"
chmod 600 "$DRILL"/secrets/restore-s3.env "$DRILL"/secrets/integrity-restore.env
FORB="$(sed -n 's/^R2_FORBIDDEN_BUCKETS=//p' "$SECRETS/r2-drill-restore.env")"
IFS=, read -r -a FB <<< "$FORB"
FARGS=(); for b in "${FB[@]}"; do FARGS+=(--forbidden-bucket "$b"); done

PIP='pip install -q --no-cache-dir --target /tmp/deps oci==2.187.1'
run_py() {
  docker run --rm --network "$NET" --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
    --read-only --tmpfs /tmp:rw,exec,size=768m -e HOME=/tmp -e PIP_DISABLE_PIP_VERSION_CHECK=1 -e PYTHONPATH=/tmp/deps:/app \
    -e PGHOST=pe-drill-pg -e PGPORT=5432 -e PGDATABASE="$RESTORE_DB" -e PGUSER=postgres -e PGSSLMODE=disable -e PGPASSFILE=/run/secrets/pgpass \
    -e BACKUP_OCI_NAMESPACE="$NS" -e BACKUP_OCI_BUCKET="$BACKUP_BUCKET" -e BACKUP_OCI_REGION=eu-frankfurt-1 \
    --env-file "$DRILL/secrets/restore-s3.env" \
    -v "$DRILL/secrets/pgpass-restore":/run/secrets/pgpass:ro -v "$AGE_IDENTITY":/run/age/identity.key:ro \
    -v "$OCI_CFG_DIR":/run/oci:ro -v "$DRILL/out":/out -v "$REPO/backend/scripts":/scripts:ro \
    --entrypoint sh "$BK" -c "$PIP && exec python \"\$@\"" sh "$@"
}

echo "== 0. production Oracle backup bucket, read-only inventory BEFORE =="
run_py /scripts/stage14d5_drill_tool.py inventory --provider oci --bucket plan-estimate-backup-prod --namespace "$NS" \
  --oci-config /run/oci/config --output /out/prod-oci-before.json || echo "(inventory of the production bucket not possible - recorded as such)"

echo "== 1. restore --phase database =="
set +e
run_py -m app.backup restore --phase database --run-id "$RUN" --identity-file /run/age/identity.key --scratch-dir /tmp \
  --report-file /out/restore-database-report.json --oci-config /run/oci/config --allowed-host pe-drill-pg "${FARGS[@]}"
rc=$?
set -e
echo "restore exit=$rc"
[ -f "$DRILL/out/restore-database-report.json" ] && { echo "-- report:"; cat "$DRILL/out/restore-database-report.json"; }
[ "$rc" = 0 ] || { echo "FAIL: the database restore did not succeed - stopping here"; exit 1; }

echo "== 2. integrity check BEFORE media (restored database, EMPTY drill-restore bucket) =="
set +e
docker run --rm --network "$NET" --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --read-only --tmpfs /tmp:size=256m -e HOME=/tmp --env-file "$DRILL/secrets/integrity-restore.env" \
  -v "$REPO/backend/scripts":/scripts:ro --entrypoint python "$BK" /scripts/media_integrity_check.py --expect-storage-name r2-drill \
  | grep -E '^(Assets checked|READY objects|Originals verified|Findings|Result):'
echo "integrity exit=${PIPESTATUS[0]} (expected 1: exactly the 12 objects of the empty destination are missing)"
set -e
echo "PHASE F: done"
EOF
```

## G (W) — restore the media, integrity check after (`--verify-sha256 --strict`), bucket comparison

Same preamble as block F (the `derive`, `FARGS`, `PIP` and `run_py` definitions, `RUN`, `NS`), refusing to run twice
(`restore-media-report.json` must not exist), then:

```bash
run_py -m app.backup restore --phase media --run-id "$RUN" --identity-file /run/age/identity.key --scratch-dir /tmp \
  --report-file /out/restore-media-report.json --oci-config /run/oci/config --allowed-host pe-drill-pg "${FARGS[@]}"
docker run --rm --network "$NET" --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --read-only --tmpfs /tmp:size=256m -e HOME=/tmp --env-file "$DRILL/secrets/integrity-restore.env" \
  -v "$REPO/backend/scripts":/scripts:ro --entrypoint python "$BK" /scripts/media_integrity_check.py \
  --expect-storage-name r2-drill --verify-sha256 --strict
# then: stage14d5_drill_tool.py inventory --provider r2 (INVENTORY_S3_* derived from the restore token) of the
# drill-restore bucket, and compare objects / bytes / digest with /out/src-after-seed.json
```
PASS: `restored=12 already_present=0 total=12`; integrity `Findings: none`, `Originals verified by sha256: 4`, exit 0; the
two inventories have equal objects, bytes and digest.

## H (W) — a scratch backend on the restored database + drill-restore bucket, then `verify-serving`

A second scratch backend (`$RESTORED_BACKEND`, uploads off, mock authentication, `DATABASE_URL` to `$RESTORE_DB` as
`pe_app`, `MEDIA_S3_*` from the drill-restore token), then:

```bash
run_py /scripts/stage14d5_drill_tool.py verify-serving --base-url "http://$RESTORED_BACKEND:8000" \
  --fixture-file /out/fixture.json --run-id "$RUN" --oci-config /run/oci/config
```
PASS: eight `[PASS]` lines, `RESULT: PASS (8/8 checks passed)`, exit 0.

## I (W) — production "after" inventory and comparison

`stage14d5_drill_tool.py inventory --provider oci --bucket plan-estimate-backup-prod …` into `/out/prod-oci-after.json`, then
`stage14d5_drill_tool.py compare-inventory /out/prod-oci-before.json /out/prod-oci-after.json`. PASS: `inventories
identical`. (The Oracle **drill** bucket also holds leftovers of earlier smoke tests that the create-only uploader cannot
delete — its total is not a measure of one drill.)
