# Plan & Estimate --- Production Deployment Runbook

> **Project:** `plan_-_estimate`\
> **Production domain:** `https://plan-estimate.pl`\
> **Platform:** Oracle Cloud Always Free (ARM64) + Docker Compose +
> Cloudflare\
> **Application:** React/Vite frontend + FastAPI backend + PostgreSQL +
> Caddy\
> **Repository:** `git@github.com:kukhmax/plan_-_estimate.git`\
> **Production branch during initial deployment:** `stage-9`\
> **Server project directory:** `~/apps/plan_-_estimate`
>
> This document records the initial production deployment performed in
> September 2026 and defines the safe update procedure for subsequent
> deployments.

------------------------------------------------------------------------

## 1. Final architecture

Production traffic follows this path:

``` text
Telegram Mini App / Browser
        |
        | HTTPS
        v
Cloudflare
  - DNS
  - Proxy
  - public TLS
        |
        | HTTPS (Full strict)
        v
Oracle Cloud VM
        |
        v
Caddy :80 / :443
        |
        +---- /api/* ----> FastAPI :8000
        |
        +---- everything -> nginx :80 -> React/Vite production build

FastAPI
   |
   v
PostgreSQL :5432
```

Only Caddy publishes ports `80` and `443` to the host. PostgreSQL,
FastAPI and the frontend nginx container remain on the internal Docker
network.

Production URL:

``` text
https://plan-estimate.pl
```

Health endpoint:

``` text
https://plan-estimate.pl/api/health
```

Expected response:

``` json
{"status":"ok"}
```

------------------------------------------------------------------------

# PART I --- INITIAL INFRASTRUCTURE

## 2. Oracle Cloud account and VM

### 2.1 Account

An Oracle Cloud Free Tier / Free Trial account was created.

Home Region used during this deployment:

``` text
Germany Central (Frankfurt)
```

The goal was to stay inside Oracle Always Free resources.

### 2.2 VM

VM name:

``` text
plan-estimate
```

Configuration used:

``` text
OS: Ubuntu 24.04 LTS
Architecture: aarch64 / ARM64
Shape: VM.Standard.A1.Flex
OCPU: 1
RAM: 6 GB
Boot volume: ~47 GB
```

Network:

``` text
VCN: vcn-20260913-2332
Subnet: subnet-20260913-2332
Private IP: 10.0.0.83
Initial public IP: 158.101.165.162
```

> The public IP was initially ephemeral. If the VM/network configuration
> is recreated, verify that the public IP has not changed and update
> Cloudflare DNS if necessary.

### 2.3 SSH

The local public SSH key was supplied to Oracle while creating the VM.

Connection:

``` bash
ssh ubuntu@158.101.165.162
```

Never share or upload the local private SSH key.

------------------------------------------------------------------------

## 3. Oracle network rules

Oracle has a cloud network firewall in addition to firewall rules inside
the VM.

The VM subnet uses:

``` text
Default Security List for vcn-20260913-2332
```

Path in Oracle Cloud Console is approximately:

``` text
Compute
→ Instances
→ plan-estimate
→ VNIC
→ subnet-20260913-2332
→ Security Lists
→ Default Security List...
→ Security rules
```

### 3.1 HTTP ingress

Add an ingress rule:

``` text
Stateless: OFF
Source Type: CIDR
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Source Port Range: empty / all
Destination Port Range: 80
Description: HTTP
```

### 3.2 HTTPS ingress

Add:

``` text
Stateless: OFF
Source Type: CIDR
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Source Port Range: empty / all
Destination Port Range: 443
Description: HTTPS
```

Do **not** remove the existing SSH port `22` rule.

------------------------------------------------------------------------

## 4. VM firewall checks

On this Oracle Ubuntu image, `ufw` was not installed:

``` bash
sudo ufw status
```

returned:

``` text
sudo: ufw: command not found
```

This is not itself an error requiring UFW installation.

The actual iptables rules were inspected with:

``` bash
sudo iptables -L -n
```

Port listeners were checked with:

``` bash
ss -lntp | grep -E ':80|:443' || echo "80/443 are not listening yet"
```

Before Caddy was started, no process was expected to listen on 80/443.

Do not casually flush or rewrite Oracle-provided iptables rules. They
contain rules for Oracle Instance Services.

------------------------------------------------------------------------

# PART II --- SERVER SOFTWARE

## 5. System preparation

Update Ubuntu:

``` bash
sudo apt update
sudo apt upgrade -y
```

Install common utilities as needed:

``` bash
sudo apt install -y git curl ca-certificates
```

Docker was installed using Docker's official convenience installation
script.

After installation, verify:

``` bash
docker --version
docker compose version
```

ARM64 execution was verified using:

``` bash
docker run --rm hello-world
```

The output identified the ARM64 image variant, confirming that Docker
was functioning on the Ampere A1 VM.

------------------------------------------------------------------------

## 6. Clone the repository

Production directory:

``` bash
mkdir -p ~/apps
cd ~/apps
```

Clone:

``` bash
git clone git@github.com:kukhmax/plan_-_estimate.git
cd plan_-_estimate
```

Checkout the deployment branch:

``` bash
git checkout stage-9
```

Verify:

``` bash
git status
git branch --show-current
git log -5 --oneline
```

------------------------------------------------------------------------

# PART III --- PRODUCTION DOCKER CONFIGURATION

## 7. Why the development Compose file was not used

The original `docker-compose.yml` was intended for development. Among
other things it:

-   exposed PostgreSQL on host port 5432;
-   exposed FastAPI on 8000;
-   ran Vite dev server on 5173;
-   mounted frontend source into the container;
-   enabled mock Telegram authentication;
-   configured the frontend API as `http://localhost:8000`.

Those settings are inappropriate for production.

A separate production configuration was therefore created.

------------------------------------------------------------------------

## 8. `frontend/Dockerfile.prod`

``` dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ENV NODE_ENV=production
ENV VITE_API_URL=""
ENV VITE_DEV_MOCK_AUTH=false

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

Important production behavior:

``` text
VITE_API_URL=""
```

makes the frontend use same-origin API calls:

``` text
/api/...
```

and:

``` text
VITE_DEV_MOCK_AUTH=false
```

prevents development mock authentication from being included in the
production flow.

------------------------------------------------------------------------

## 9. `frontend/nginx.conf`

``` nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|webp|woff|woff2)$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }
}
```

The `try_files` rule is required for React SPA routes.

------------------------------------------------------------------------

## 10. `docker-compose.prod.yml`

``` yaml
name: plan-estimate

services:
  postgres:
    image: postgres:16-alpine
    container_name: plan_estimate_postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10
    networks:
      - internal

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: plan_estimate_backend
    restart: unless-stopped
    environment:
      ENVIRONMENT: production
      APP_ENV: production
      DEBUG: "false"
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      TELEGRAM_AUTH_MAX_AGE_SECONDS: ${TELEGRAM_AUTH_MAX_AGE_SECONDS:-86400}
      MOCK_TELEGRAM_AUTH: "false"
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
      JWT_ALGORITHM: ${JWT_ALGORITHM:-HS256}
      JWT_EXPIRE_MINUTES: ${JWT_EXPIRE_MINUTES:-10080}
    depends_on:
      postgres:
        condition:
          service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8000/api/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s
    networks:
      - internal

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.prod
    container_name: plan_estimate_frontend
    restart: unless-stopped
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - internal

  caddy:
    image: caddy:2-alpine
    container_name: plan_estimate_caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    environment:
      APP_DOMAIN: ${APP_DOMAIN}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./certs:/etc/caddy/certs:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      frontend:
        condition: service_started
      backend:
        condition: service_healthy
    networks:
      - internal

volumes:
  postgres_data:
    driver: local
  caddy_data:
    driver: local
  caddy_config:
    driver: local

networks:
  internal:
    driver: bridge
```

### Compose project-name error

An early build failed with an error similar to:

``` text
invalid tag "plan_-_estimate-frontend": invalid reference format
```

The repository directory contains `_` in its name, which caused an
invalid automatically generated image/project name.

Fix:

``` yaml
name: plan-estimate
```

was added at the top of `docker-compose.prod.yml`.

------------------------------------------------------------------------

## 11. `Caddyfile`

``` caddy
{$APP_DOMAIN} {
    tls /etc/caddy/certs/origin.pem /etc/caddy/certs/origin.key

    encode gzip zstd

    @api path /api/*
    handle @api {
        reverse_proxy backend:8000
    }

    handle {
        reverse_proxy frontend:80
    }

    log {
        output stdout
        format console
    }
}
```

Routing:

``` text
/api/* → backend:8000
everything else → frontend:80
```

Caddy is the only application container with public host ports.

------------------------------------------------------------------------

# PART IV --- SECRETS AND ENVIRONMENT

## 12. `.env.production.example`

The repository contains only a template:

``` env
ENVIRONMENT=production
APP_ENV=production
DEBUG=false

APP_DOMAIN=app.example.com

POSTGRES_USER=plan_estimate
POSTGRES_PASSWORD=CHANGE_ME
POSTGRES_DB=plan_estimate

TELEGRAM_BOT_TOKEN=CHANGE_ME
TELEGRAM_AUTH_MAX_AGE_SECONDS=86400
MOCK_TELEGRAM_AUTH=false

JWT_SECRET_KEY=CHANGE_ME
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080
```

The real server file is:

``` text
.env.production
```

It contains real secrets and must never be committed.

Set restrictive permissions:

``` bash
chmod 600 .env.production
```

For the deployed site:

``` text
APP_DOMAIN=plan-estimate.pl
```

------------------------------------------------------------------------

## 13. `.gitignore`

Production secrets and certificates are excluded:

``` gitignore
.env
.env.*
!.env.example
!.env.production.example

certs/
```

Verify before committing:

``` bash
git check-ignore -v .env.production certs/origin.key certs/origin.pem
```

All three should be reported as ignored.

Never commit:

``` text
.env.production
certs/origin.key
certs/origin.pem
```

In particular, never publish:

-   Telegram bot token;
-   PostgreSQL password;
-   JWT secret;
-   TLS private key.

------------------------------------------------------------------------

# PART V --- INITIAL APPLICATION BUILD

## 14. Validate Compose

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config --quiet
```

No output means the configuration passed validation.

------------------------------------------------------------------------

## 15. Build production images

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  build
```

The initial deployment successfully built the backend and frontend on
ARM64.

The frontend production bundle was also checked to ensure it did not
contain development values such as:

``` text
localhost:8000
VITE_DEV_MOCK_AUTH
```

------------------------------------------------------------------------

## 16. Start PostgreSQL and backend

PostgreSQL and backend were brought up first.

The backend entrypoint performs:

``` text
alembic upgrade head
```

before starting Uvicorn.

The initial empty production database successfully applied all existing
Alembic migrations.

Check containers:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps
```

Check backend health internally:

``` bash
docker exec plan_estimate_backend \
  curl -fsS http://localhost:8000/api/health
```

Expected:

``` json
{"status":"ok"}
```

Check PostgreSQL:

``` bash
docker exec plan_estimate_postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

------------------------------------------------------------------------

## 17. Start frontend

Start the frontend with Compose.

It runs nginx internally on port 80 but has no host port mapping.

Internal connectivity was tested in both directions.

Backend → frontend:

``` bash
docker exec plan_estimate_backend curl -fsS http://frontend/
```

Frontend → backend:

``` bash
docker exec plan_estimate_frontend \
  wget -qO- http://backend:8000/api/health
```

Expected backend result:

``` json
{"status":"ok"}
```

### Localhost IPv6 observation

A request to:

``` text
http://localhost/
```

inside a container initially failed because `localhost` could resolve to
IPv6 `::1`, while nginx was listening on IPv4.

Using:

``` text
http://127.0.0.1/
```

worked.

This was not a production routing problem.

------------------------------------------------------------------------

# PART VI --- DOMAIN

## 18. Domain purchase

Domain purchased:

``` text
plan-estimate.pl
```

At registration it initially used CAL.pl nameservers:

``` text
ns1.cal.pl
ns2.cal.pl
```

No additional registrar hosting, VPS, paid SSL or site builder was
required.

The application itself is hosted on Oracle.

------------------------------------------------------------------------

# PART VII --- CLOUDFLARE

## 19. Add domain to Cloudflare

A Cloudflare account was created and the domain added:

``` text
plan-estimate.pl
```

Cloudflare Free plan is sufficient for this deployment.

An A record was configured for the root domain:

``` text
Type: A
Name: @
IPv4: 158.101.165.162
TTL: Auto
Proxy: Proxied
```

The orange-cloud proxy should be enabled.

Because proxying is enabled, a public DNS lookup returns Cloudflare IP
addresses rather than the Oracle origin IP. That is expected.

------------------------------------------------------------------------

## 20. Change authoritative nameservers

Cloudflare assigned:

``` text
itzel.ns.cloudflare.com
rex.ns.cloudflare.com
```

At CAL.pl, DNSSEC was confirmed to be disabled. The interface displayed
an option such as:

``` text
Włącz DNSSEC
```

which means DNSSEC was not currently enabled.

Under:

``` text
Zmiana DNS
```

the original:

``` text
ns1.cal.pl
ns2.cal.pl
```

were removed and replaced with:

``` text
itzel.ns.cloudflare.com
rex.ns.cloudflare.com
```

------------------------------------------------------------------------

## 21. Verify DNS propagation

On Manjaro, `dig` and `nslookup` were initially unavailable.

Install `dig` with:

``` bash
sudo pacman -S bind
```

Verify authoritative nameservers:

``` bash
dig NS plan-estimate.pl +short
```

Expected:

``` text
itzel.ns.cloudflare.com.
rex.ns.cloudflare.com.
```

Check A lookup:

``` bash
dig A plan-estimate.pl +short
```

Because Cloudflare proxying is enabled, this returns Cloudflare edge IP
addresses rather than `158.101.165.162`.

------------------------------------------------------------------------

# PART VIII --- CLOUDFLARE ORIGIN CERTIFICATE

## 22. Create certificate

Cloudflare path:

``` text
SSL/TLS
→ Origin Server
→ Create Certificate
```

Configuration used:

``` text
Generate private key and CSR with Cloudflare
Private key: RSA 2048
Hostnames:
  *.plan-estimate.pl
  plan-estimate.pl
```

A long-lived Cloudflare Origin Certificate was created.

The deployed certificate validity was:

``` text
notBefore: Sep 14 2026
notAfter:  Sep 10 2041
```

The Cloudflare Origin private key is shown during creation and must be
stored securely.

**Never paste the private key into chat, GitHub, documentation, logs or
tickets.**

------------------------------------------------------------------------

## 23. Store certificate on Oracle

Create directory:

``` bash
cd ~/apps/plan_-_estimate
mkdir -p certs
```

Save the complete Origin Certificate to:

``` text
certs/origin.pem
```

including:

``` text
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
```

Save the complete private key to:

``` text
certs/origin.key
```

including:

``` text
-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
```

Permissions:

``` bash
chmod 600 certs/origin.key
chmod 644 certs/origin.pem
```

Verify only metadata:

``` bash
ls -l certs/
```

Do not use `cat origin.key` for troubleshooting output that may be
copied elsewhere.

------------------------------------------------------------------------

## 24. Validate certificate and key

Inspect certificate metadata:

``` bash
openssl x509 \
  -in certs/origin.pem \
  -noout \
  -subject -issuer -dates
```

Verify that certificate and private key form a pair:

``` bash
openssl x509 \
  -in certs/origin.pem \
  -pubkey -noout | sha256sum

openssl pkey \
  -in certs/origin.key \
  -pubout | sha256sum
```

The two SHA256 hashes must be identical.

During initial deployment they matched.

------------------------------------------------------------------------

# PART IX --- CADDY AND HTTPS

## 25. Configure production domain

Edit:

``` bash
nano .env.production
```

Set:

``` env
APP_DOMAIN=plan-estimate.pl
```

Validate:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config --quiet
```

------------------------------------------------------------------------

## 26. Start Caddy

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d caddy
```

Check:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps
```

Expected public mappings:

``` text
0.0.0.0:80->80/tcp
0.0.0.0:443->443/tcp
```

Inspect logs:

``` bash
docker logs plan_estimate_caddy --tail 100
```

### Non-critical Caddy warnings observed

Warnings included:

-   Caddyfile formatting warning;
-   no OCSP stapling URL for Cloudflare Origin Certificate;
-   HTTP/3 UDP receive buffer size warning;
-   HTTP/2/HTTP/3 skipped on plain HTTP port 80.

These did not prevent HTTPS operation.

------------------------------------------------------------------------

## 27. Test origin before enabling strict mode

Test frontend directly through local Caddy while forcing hostname
resolution:

``` bash
curl -kI \
  --resolve plan-estimate.pl:443:127.0.0.1 \
  https://plan-estimate.pl
```

Expected:

``` text
HTTP/2 200
```

Test API:

``` bash
curl -k \
  --resolve plan-estimate.pl:443:127.0.0.1 \
  https://plan-estimate.pl/api/health
```

Expected:

``` json
{"status":"ok"}
```

`-k` is used here because a Cloudflare Origin Certificate is intended to
be validated by Cloudflare, not directly by a normal browser trust
store.

------------------------------------------------------------------------

## 28. Cloudflare TLS mode

After the origin certificate was installed and tested:

``` text
Cloudflare
→ SSL/TLS
→ Overview
```

Encryption mode was changed from:

``` text
Full
```

to:

``` text
Full (strict)
```

Do **not** use Flexible mode.

Final TLS path:

``` text
Browser/Telegram
   ↓ public HTTPS
Cloudflare
   ↓ HTTPS + Origin Certificate validation
Caddy
```

------------------------------------------------------------------------

# PART X --- PUBLIC VALIDATION

## 29. Browser and API

Open:

``` text
https://plan-estimate.pl
```

Check:

``` text
https://plan-estimate.pl/api/health
```

Expected:

``` json
{"status":"ok"}
```

From a terminal:

``` bash
curl -I https://plan-estimate.pl
curl https://plan-estimate.pl/api/health
```

------------------------------------------------------------------------

## 30. Why normal browser auth initially failed

Opening the production application directly in a normal browser produced
an authentication error similar to:

``` text
Telegram did not provide login data
```

This was **expected**.

Production has:

``` text
MOCK_TELEGRAM_AUTH=false
```

and the frontend only receives Telegram `initData` when launched as a
Telegram Mini App.

This behavior confirmed that development mock authentication was not
accidentally enabled in production.

------------------------------------------------------------------------

# PART XI --- TELEGRAM MINI APP

## 31. Configure BotFather

In Telegram:

``` text
@BotFather
→ /mybots
→ select the project bot
→ Bot Settings
→ Menu Button
```

Configure the web app URL:

``` text
https://plan-estimate.pl
```

A menu-button title such as:

``` text
Plan & Estimate
```

can be used.

Do not create a new bot or rotate the token merely to configure the Mini
App URL.

------------------------------------------------------------------------

## 32. Real Telegram authentication test

Open the bot in Telegram and launch the Mini App through its configured
menu button.

Telegram then supplies WebApp `initData`.

The frontend sends it to:

``` text
/api/auth/telegram
```

FastAPI validates it using the production:

``` text
TELEGRAM_BOT_TOKEN
```

The successful deployment displayed:

``` text
Telegram Verified
```

This validated the complete production path:

``` text
Telegram
→ Cloudflare
→ Caddy
→ React
→ FastAPI
→ Telegram signature verification
→ PostgreSQL
```

------------------------------------------------------------------------

# PART XII --- GIT AND DEPLOYMENT CONFIGURATION

## 33. Production deployment commit

Production infrastructure files were committed without secrets.

Files:

``` text
.env.production.example
.gitignore
Caddyfile
docker-compose.prod.yml
frontend/Dockerfile.prod
frontend/nginx.conf
```

Production commit after rebasing onto the latest Stage 9 work:

``` text
7dd457f deploy(prod): add Oracle Cloud and Cloudflare production stack
```

The server and GitHub `stage-9` branch were synchronized and the working
tree was clean.

------------------------------------------------------------------------

## 34. Git identity error on Oracle

The first commit attempt failed:

``` text
Author identity unknown
fatal: unable to auto-detect email address
```

Existing repository author details were inspected:

``` bash
git log -1 --format='name=%an%nemail=%ae'
```

Then configured:

``` bash
git config --global user.name "kukhmax"
git config --global user.email "kukhmax@gmail.com"
```

------------------------------------------------------------------------

## 35. GitHub SSH authentication on Oracle

`git push` initially requested GitHub username/password.

GitHub password authentication is not used for Git pushes.

The remote should be SSH:

``` bash
git remote -v
```

Expected:

``` text
git@github.com:kukhmax/plan_-_estimate.git
```

The server initially had only:

``` text
~/.ssh/authorized_keys
```

This allows clients to SSH **into** the server; it is not a private key
that lets the server authenticate **to GitHub**.

A dedicated GitHub key was created:

``` bash
ssh-keygen \
  -t ed25519 \
  -C "kukhmax@gmail.com" \
  -f ~/.ssh/id_ed25519_github
```

The public key:

``` bash
cat ~/.ssh/id_ed25519_github.pub
```

was added in GitHub under:

``` text
Settings
→ SSH and GPG keys
→ New SSH key
```

Only the `.pub` key is copied to GitHub.

SSH config:

``` bash
cat > ~/.ssh/config <<'EOF'
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_github
    IdentitiesOnly yes
EOF

chmod 600 ~/.ssh/config
```

Test:

``` bash
ssh -T git@github.com
```

Successful authentication reports that GitHub does not provide shell
access.

------------------------------------------------------------------------

## 36. Push rejected because remote advanced

A push later failed with:

``` text
! [rejected] stage-9 -> stage-9 (fetch first)
```

The server contained one local deployment commit while GitHub had
received two new Stage 9 research commits.

Inspect divergence:

``` bash
git fetch origin

git log \
  --oneline \
  --graph \
  --decorate \
  --left-right \
  HEAD...origin/stage-9
```

The working tree was clean.

Instead of force-pushing or creating an unnecessary merge commit, the
local deployment commit was rebased:

``` bash
git rebase origin/stage-9
```

Then pushed normally:

``` bash
git push origin stage-9
```

Final result:

``` text
7dd457f deploy(prod): add Oracle Cloud and Cloudflare production stack
e82cc26 docs(stage-9): research Krakow reveal prices
92c5ecf docs(stage-9): research Krakow painting and drywall prices
...
```

Never use `git push --force` on the shared deployment branch merely to
resolve this situation.

------------------------------------------------------------------------

# PART XIII --- LOCAL WORKSTATION SYNCHRONIZATION

## 37. Synchronize Manjaro with GitHub

On the local development machine:

``` bash
cd ~/Pr/plan_estimate
```

Inspect:

``` bash
git status
git branch --show-current
```

Fetch:

``` bash
git fetch origin
```

Inspect:

``` bash
git status
git log --oneline --graph --decorate --all -12
```

If the local branch is clean and Git reports that it can be
fast-forwarded:

``` bash
git pull --ff-only origin stage-9
```

Verify:

``` bash
git status
git log -3 --oneline --decorate
```

`--ff-only` prevents Git from unexpectedly creating a merge commit.

------------------------------------------------------------------------

# PART XIV --- SAFE PRODUCTION UPDATE PROCEDURE

## 38. Standard deployment workflow

For every future production update use:

``` text
1. Inspect production repository
2. Fetch GitHub
3. Review incoming commits
4. Backup PostgreSQL
5. Fast-forward production branch
6. Validate Compose
7. Build new images while old containers keep running
8. Apply with docker compose up -d
9. Verify containers
10. Verify backend health
11. Verify public HTTPS
12. Inspect logs if anything fails
```

Do not blindly run `git pull && docker compose up`.

------------------------------------------------------------------------

## 39. Step 1 --- inspect server state

Connect:

``` bash
ssh ubuntu@158.101.165.162
cd ~/apps/plan_-_estimate
```

Check:

``` bash
git status
git branch --show-current
```

Production should normally report:

``` text
On branch stage-9
nothing to commit, working tree clean
```

If the working tree is dirty, **stop** and inspect the changes before
pulling.

------------------------------------------------------------------------

## 40. Step 2 --- fetch without changing files

``` bash
git fetch origin
```

See exactly what will be deployed:

``` bash
git log --oneline HEAD..origin/stage-9
```

If unexpected commits appear, stop and review them.

------------------------------------------------------------------------

## 41. Step 3 --- backup PostgreSQL

Create backup directory:

``` bash
mkdir -p ~/backups/plan-estimate
```

Create compressed SQL dump:

``` bash
docker exec plan_estimate_postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  | gzip > ~/backups/plan-estimate/db-$(date +%Y%m%d-%H%M%S).sql.gz
```

Verify that the backup exists and is not zero bytes:

``` bash
ls -lh ~/backups/plan-estimate/ | tail
```

For important production updates, keeping an off-server backup is
strongly recommended. A future option is Cloudflare R2.

------------------------------------------------------------------------

## 42. Step 4 --- fast-forward production code

``` bash
git pull --ff-only origin stage-9
```

Then:

``` bash
git status
git log -3 --oneline
```

If Git refuses because branches diverged, **do not force anything**.
Inspect:

``` bash
git fetch origin
git log --oneline --graph --decorate --left-right HEAD...origin/stage-9
```

Resolve the situation deliberately before proceeding.

------------------------------------------------------------------------

## 43. Step 5 --- validate production configuration

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config --quiet
```

If this returns an error, stop.

Do not restart the working production application with an invalid
Compose configuration.

------------------------------------------------------------------------

## 44. Step 6 --- build first, while old production keeps running

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  build
```

This is intentionally separate from `up -d`.

If the build fails, stop.

The existing production containers remain running, which avoids
unnecessary downtime caused by a compilation/build failure.

------------------------------------------------------------------------

## 45. Step 7 --- apply the new images

Only after the build succeeds:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d
```

Compose recreates services that require updating.

The backend entrypoint automatically executes:

``` text
alembic upgrade head
```

before starting Uvicorn.

Therefore database migrations contained in the new version are applied
during backend startup.

------------------------------------------------------------------------

## 46. Step 8 --- inspect containers

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps
```

Expected state:

``` text
plan_estimate_postgres   Up ... (healthy)
plan_estimate_backend    Up ... (healthy)
plan_estimate_frontend   Up ...
plan_estimate_caddy      Up ...
```

PostgreSQL and FastAPI should not have public host port mappings.

Caddy should expose `80` and `443`.

------------------------------------------------------------------------

## 47. Step 9 --- internal backend health

``` bash
docker exec plan_estimate_backend \
  curl -fsS http://localhost:8000/api/health
```

Expected:

``` json
{"status":"ok"}
```

------------------------------------------------------------------------

## 48. Step 10 --- public production health

``` bash
curl -fsS https://plan-estimate.pl/api/health
```

Expected:

``` json
{"status":"ok"}
```

Check frontend response:

``` bash
curl -I https://plan-estimate.pl
```

Expected HTTP success, normally:

``` text
HTTP/2 200
```

Finally test the Mini App from Telegram, especially after changes
involving authentication, routing or frontend initialization.

------------------------------------------------------------------------

# PART XV --- TROUBLESHOOTING

## 49. Backend logs

``` bash
docker logs plan_estimate_backend --tail 100
```

Follow live:

``` bash
docker logs -f plan_estimate_backend
```

Use `Ctrl+C` to stop following; it does not stop the container.

------------------------------------------------------------------------

## 50. Frontend logs

``` bash
docker logs plan_estimate_frontend --tail 100
```

------------------------------------------------------------------------

## 51. Caddy logs

``` bash
docker logs plan_estimate_caddy --tail 100
```

------------------------------------------------------------------------

## 52. PostgreSQL logs

``` bash
docker logs plan_estimate_postgres --tail 100
```

------------------------------------------------------------------------

## 53. Complete service status

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps
```

Docker resources:

``` bash
docker ps
docker images
docker volume ls
```

------------------------------------------------------------------------

## 54. Check ports

``` bash
ss -lntp | grep -E ':80|:443'
```

Expected Caddy/Docker listeners on public ports 80 and 443.

------------------------------------------------------------------------

## 55. Check DNS

From Manjaro:

``` bash
dig NS plan-estimate.pl +short
dig A plan-estimate.pl +short
```

Expected NS:

``` text
itzel.ns.cloudflare.com.
rex.ns.cloudflare.com.
```

A lookup normally returns Cloudflare proxy addresses.

------------------------------------------------------------------------

## 56. Cloudflare 5xx errors

If Cloudflare shows an origin-related error:

1.  verify Caddy is running;
2.  verify ports 80/443 are open in Oracle Security List;
3.  inspect Caddy logs;
4.  verify `APP_DOMAIN=plan-estimate.pl`;
5.  verify `certs/origin.pem` and `certs/origin.key` exist;
6.  verify Cloudflare mode is `Full (strict)`;
7.  verify the Cloudflare DNS A record still points to the VM's current
    public IP.

Commands:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps

docker logs plan_estimate_caddy --tail 100
```

Test origin locally:

``` bash
curl -kI \
  --resolve plan-estimate.pl:443:127.0.0.1 \
  https://plan-estimate.pl
```

If local origin works but Cloudflare does not, investigate Cloudflare
DNS/proxy and Oracle network access.

------------------------------------------------------------------------

## 57. Telegram authentication fails

First distinguish normal-browser behavior from Telegram behavior.

A normal browser does not have Telegram WebApp `initData`, so production
authentication may intentionally fail there.

Test through the bot's Mini App menu.

Check:

``` text
BotFather Mini App URL = https://plan-estimate.pl
MOCK_TELEGRAM_AUTH=false
ENVIRONMENT=production
APP_ENV=production
```

Verify backend logs:

``` bash
docker logs plan_estimate_backend --tail 100
```

Do not print or paste `TELEGRAM_BOT_TOKEN`.

------------------------------------------------------------------------

# PART XVI --- COMMANDS THAT REQUIRE SPECIAL CARE

## 58. Never delete production volumes casually

Do **not** run:

``` bash
docker compose down -v
```

on production unless the explicit intention is to destroy persistent
volumes.

`-v` can remove the PostgreSQL volume and therefore production data.

A normal deployment does not require `docker compose down`.

Use:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d
```

------------------------------------------------------------------------

## 59. Avoid force-pushing

Do not use:

``` bash
git push --force
```

on `stage-9` simply because the server is behind or has diverged.

Use:

``` bash
git fetch origin
git status
git log --oneline --graph --decorate --left-right HEAD...origin/stage-9
```

and understand the divergence first.

------------------------------------------------------------------------

## 60. Never commit production secrets

Before committing deployment changes:

``` bash
git status --short
git check-ignore -v .env.production certs/origin.key certs/origin.pem
```

The actual secret files must remain ignored.

------------------------------------------------------------------------

# PART XVII --- QUICK DEPLOYMENT CHECKLIST

## 61. Routine update

Use this compact version only after understanding the detailed procedure
above.

``` bash
ssh ubuntu@158.101.165.162

cd ~/apps/plan_-_estimate

git status
git fetch origin
git log --oneline HEAD..origin/stage-9
```

If clean and expected:

``` bash
mkdir -p ~/backups/plan-estimate

docker exec plan_estimate_postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  | gzip > ~/backups/plan-estimate/db-$(date +%Y%m%d-%H%M%S).sql.gz

ls -lh ~/backups/plan-estimate/ | tail
```

Update:

``` bash
git pull --ff-only origin stage-9
```

Validate:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config --quiet
```

Build without first stopping production:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  build
```

Apply:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d
```

Verify:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps

docker exec plan_estimate_backend \
  curl -fsS http://localhost:8000/api/health

curl -fsS https://plan-estimate.pl/api/health

curl -I https://plan-estimate.pl
```

Expected API result:

``` json
{"status":"ok"}
```

Then launch the application from Telegram and verify real Telegram
authentication.

------------------------------------------------------------------------

# PART XVIII --- CURRENT PRODUCTION REFERENCE

## 62. Production endpoints

``` text
Application:
https://plan-estimate.pl

Health:
https://plan-estimate.pl/api/health
```

## 63. Server

``` text
Oracle VM: plan-estimate
OS: Ubuntu 24.04 LTS
Architecture: ARM64 / aarch64
Production directory: ~/apps/plan_-_estimate
```

## 64. Containers

``` text
plan_estimate_postgres
plan_estimate_backend
plan_estimate_frontend
plan_estimate_caddy
```

## 65. Important production files

Tracked:

``` text
docker-compose.prod.yml
Caddyfile
frontend/Dockerfile.prod
frontend/nginx.conf
.env.production.example
```

Server-only / secret:

``` text
.env.production
certs/origin.pem
certs/origin.key
```

## 66. Cloudflare

``` text
Domain: plan-estimate.pl
Proxy: enabled
SSL/TLS mode: Full (strict)

Nameservers:
itzel.ns.cloudflare.com
rex.ns.cloudflare.com
```

------------------------------------------------------------------------

# PART XIX --- RECOMMENDED NEXT INFRASTRUCTURE IMPROVEMENTS

The initial production deployment is operational. The following
improvements should be treated as future infrastructure tasks rather
than prerequisites for normal operation:

1.  Automate and rotate PostgreSQL backups.
2.  Copy backups off the Oracle VM, e.g. to object storage such as
    Cloudflare R2.
3.  Define and test a documented database restore procedure.
4.  Consider reserving/stabilizing the Oracle public IP or otherwise
    ensuring DNS is updated if the IP changes.
5.  Consider restricting SSH access once a safe recovery method exists.
6.  Add deployment automation only after the manual runbook remains
    reliable.
7.  Add monitoring/alerting for `/api/health`, disk usage and backup
    failures.
8.  Periodically prune unused Docker images after confirming the current
    deployment is healthy.

Do not optimize these at the cost of making the currently working
production deployment harder to recover.

------------------------------------------------------------------------

## 67. Core safety principles

The production workflow is deliberately conservative:

``` text
GitHub is the source of application code
            ↓
fetch and inspect first
            ↓
backup persistent data
            ↓
fast-forward only
            ↓
validate configuration
            ↓
build while current production is still running
            ↓
apply only after successful build
            ↓
health-check internally and publicly
```

The most important rules are:

-   do not expose PostgreSQL publicly;
-   do not enable Telegram mock auth in production;
-   do not commit secrets;
-   do not delete Docker volumes during routine deployment;
-   do not force-push to solve ordinary synchronization problems;
-   do not stop a healthy production stack before verifying that the new
    version can build;
-   always back up the database before an update that may include
    migrations;
-   verify both `/api/health` and the Telegram Mini App after
    deployment.
