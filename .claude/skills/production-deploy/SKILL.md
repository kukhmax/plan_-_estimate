---
name: production-deploy
description: Deploy only changed components to the Oracle production server, verify health, and handle Telegram frontend cache busting. All production mutations require explicit owner approval.
disable-model-invocation: true
argument-hint: "[stage label and changed components: frontend | backend | both | migration]"
---

# Production deploy

**Every action in this skill modifies production. All steps require explicit owner approval before execution.**

This skill generates exact manual commands for the owner. It does NOT execute SSH or production mutations itself.

## Production server

- Host: `ubuntu@158.101.165.162`
- App directory: `~/apps/plan_-_estimate`
- Health: `https://plan-estimate.pl/api/health` → `{"status":"ok"}`
- Production URL: `https://plan-estimate.pl`

## Canonical Compose command

Every production Docker Compose command MUST use all three flags:

```bash
docker compose \
  --env-file .env.production \
  -p plan-estimate \
  -f docker-compose.prod.yml \
  <subcommand>
```

Never use generic `docker compose` without all three flags on production.

## Output format

State before providing commands:

```
DEPLOY SCOPE:
- frontend: YES/NO
- backend: YES/NO
- migration: YES/NO  (revision id if YES)
- expected migration head: <id>
- Telegram cache-buster: YES/NO
```

Then numbered command blocks. Place an explicit **STOP / OWNER APPROVAL** checkpoint immediately before the step that applies any migration. Do not combine the migration step with surrounding commands into a single copy/paste block.

## Four deployment scopes

### A) Frontend only

```
git pull → build frontend → up -d frontend → ps → health → cache-buster
```

### B) Backend only — no migration

```
git pull → build backend → up -d backend → ps → health
```

### C) Backend + frontend — no migration

```
git pull → build backend frontend → up -d backend frontend → ps → health → cache-buster
```

### D) Backend with new migration (+ frontend if changed)

**CRITICAL: Never run `alembic heads` or `alembic history` inside a running backend container after `git pull` but before rebuilding and recreating the container. The running container was built from the old image and reports the old code head — not the new migration.**

Correct order:

1. `git pull`
2. Inspect the migration file from the **checked-out repository** (`cat backend/alembic/versions/<new_migration>.py` or equivalent)
3. Report: current DB revision, code head, migration path, compatibility assessment, backup recommendation
4. `build backend` [and `frontend` if changed]
5. **STOP — explicit owner approval required** before the next step
6. `up -d backend` — the new backend container starts; the entrypoint auto-applies `alembic upgrade head`
7. `exec backend alembic current` — from the **new** container
8. `exec backend alembic heads` — from the **new** container
9. Verify step 7 == step 8; if not, inspect backend logs before continuing
10. `up -d frontend` if changed
11. `ps` → `health` → inspect logs if health fails
12. Cache-buster URL if frontend changed

**Startup compatibility note**: The current production backend entrypoint auto-applies `alembic upgrade head` before starting Uvicorn. For additive migrations (ADD COLUMN, CREATE TABLE) this is safe. If a future migration removes or renames a column that the old application code reads, starting the new backend against the old schema may fail. In that case, do NOT run `up -d backend` before an explicit owner-approved compatibility plan.

**Build vs. recreate distinction**: A successful `docker compose build backend` builds a new image but does NOT update the running container. `docker compose up -d backend` is required to recreate the service from the new image. Both steps are always required after a code change.

## Migration safety

Before `up -d backend` when a migration is present, always report:

- current DB revision (from old container before rebuild)
- code head (from new migration file in repository)
- migration file path and operation type (additive vs. destructive)
- whether a DB backup is recommended

Never run without explicit special approval:
- `alembic downgrade`
- Destructive migrations (DROP, TRUNCATE, column removal)

Always verify `alembic current` == `alembic heads` after every migration.

## Troubleshooting: `alembic heads` reports old revision after `git pull`

**Cause**: the running container uses the old image. It has no knowledge of migration files added after that image was built.

**Resolution**:
```bash
# Build the new backend image
docker compose \
  --env-file .env.production \
  -p plan-estimate \
  -f docker-compose.prod.yml \
  build backend

# Recreate the container from the new image
docker compose \
  --env-file .env.production \
  -p plan-estimate \
  -f docker-compose.prod.yml \
  up -d backend

# Now verify heads from the NEW container
docker compose \
  --env-file .env.production \
  -p plan-estimate \
  -f docker-compose.prod.yml \
  exec backend alembic heads
```

Do NOT run `alembic upgrade head` manually until the new container reports the expected code head. (In the current production setup the entrypoint already applied the migration on container start — so verify `alembic current` matches `alembic heads` and do not run it again manually.)

## Frontend cache busting (required for every frontend deployment)

```bash
SHA=$(git rev-parse --short HEAD)
# Owner opens this URL inside Telegram to clear the cached Mini App:
https://plan-estimate.pl/?v=${SHA}
```

After any `setChatMenuButton`, always verify with `getChatMenuButton`.

`TELEGRAM_BOT_TOKEN` must come from `.env.production` on the server. Never print it.

## Strictly prohibited without explicit special approval

- `docker compose down -v`
- Volume deletion
- `DROP DATABASE` / `TRUNCATE` on production tables
- `alembic downgrade`
- `git reset --hard` on production
- `git push --force` to production branch
