---
name: production-deploy
description: Deploy only changed components to the Oracle production server, verify health, and handle Telegram frontend cache busting. All production mutations require explicit owner approval.
disable-model-invocation: true
argument-hint: "[stage label and changed components: frontend | backend | both]"
---

# Production deploy

**Every action in this skill modifies production. All steps require explicit owner approval before execution.**

## Production server

- Host: `ubuntu@158.101.165.162`
- App directory: `~/apps/plan_-_estimate`
- Health: `https://plan-estimate.pl/api/health` → `{"status":"ok"}`
- Production URL: `https://plan-estimate.pl`

## Canonical Compose command

Always use the full production flags. Never use generic `docker compose up/down`:

```bash
docker compose \
  --env-file .env.production \
  -p plan-estimate \
  -f docker-compose.prod.yml \
  <subcommand>
```

## Deployment decision (run before asking for approval)

Determine which components changed since the last deployed commit:

- **Frontend only**: build + up frontend only
- **Backend only**: build + up backend only
- **Frontend + backend**: build + up both
- **Schema migration**: present the migration diff and require separate approval before `alembic upgrade head`

Do not rebuild services that have no changes.

## Standard deploy sequence (owner approval required for each SSH step)

1. `git pull origin <branch>` — pull the accepted commit
2. If migration exists: show `alembic history -r current:head` and await migration approval
3. `docker compose ... build <services>`
4. `docker compose ... up -d <services>`
5. `docker compose ... ps` — confirm containers running
6. `curl -s https://plan-estimate.pl/api/health` — must return `{"status":"ok"}`
7. If backend/schema change: verify `alembic current` matches `alembic heads`

## Frontend cache busting (required for every frontend deployment)

After a frontend deploy, provide the Telegram WebApp cache-buster URL using the short SHA of the deployed commit:

```
https://plan-estimate.pl/?v=<git-short-sha>
```

Owner must open this URL in Telegram to clear the cached Mini App.

After any Telegram menu button mutation, verify with `getChatMenuButton`.

## TELEGRAM_BOT_TOKEN

Must come from `.env.production` on the server. Never print it.

## Strictly prohibited without explicit special approval

- `docker compose down -v`
- Volume deletion
- `DROP DATABASE`
- `TRUNCATE` on production tables
- Destructive migrations
- `git reset --hard` on production
- `git push --force` to production branch
