# Plan & Estimate --- Руководство по Production-развёртыванию

> **Проект:** `plan_-_estimate`\
> **Production-домен:** `https://plan-estimate.pl`\
> **Платформа:** Oracle Cloud Always Free (ARM64) + Docker Compose +
> Cloudflare\
> **Приложение:** React/Vite frontend + FastAPI backend + PostgreSQL +
> Caddy\
> **Репозиторий:** `git@github.com:kukhmax/plan_-_estimate.git`\
> **Production-ветка во время первоначального развёртывания:**
> `stage-9`\
> **Каталог проекта на сервере:** `~/apps/plan_-_estimate`
>
> Этот документ фиксирует первоначальное production-развёртывание,
> выполненное в сентябре 2026 года, и определяет безопасную процедуру
> последующих обновлений.

------------------------------------------------------------------------

## 1. Итоговая архитектура

Production-трафик проходит по следующей цепочке:

``` text
Telegram Mini App / Браузер
        |
        | HTTPS
        v
Cloudflare
  - DNS
  - Proxy
  - публичный TLS
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
        +---- всё остальное -> nginx :80 -> production-сборка React/Vite

FastAPI
   |
   v
PostgreSQL :5432
```

Только Caddy публикует порты `80` и `443` на хосте. PostgreSQL, FastAPI
и frontend-контейнер nginx остаются во внутренней Docker-сети.

Production URL:

``` text
https://plan-estimate.pl
```

Health endpoint:

``` text
https://plan-estimate.pl/api/health
```

Ожидаемый ответ:

``` json
{"status":"ok"}
```

------------------------------------------------------------------------

# ЧАСТЬ I --- ПЕРВОНАЧАЛЬНАЯ ИНФРАСТРУКТУРА

## 2. Oracle Cloud: аккаунт и VM

### 2.1 Аккаунт

Был создан аккаунт Oracle Cloud Free Tier / Free Trial.

Home Region, использованный при развёртывании:

``` text
Germany Central (Frankfurt)
```

Цель --- оставаться в пределах ресурсов Oracle Always Free.

### 2.2 Виртуальная машина

Имя VM:

``` text
plan-estimate
```

Использованная конфигурация:

``` text
OS: Ubuntu 24.04 LTS
Архитектура: aarch64 / ARM64
Shape: VM.Standard.A1.Flex
OCPU: 1
RAM: 6 GB
Boot volume: ~47 GB
```

Сеть:

``` text
VCN: vcn-20260913-2332
Subnet: subnet-20260913-2332
Private IP: 10.0.0.83
Первоначальный public IP: 158.101.165.162
```

> Public IP изначально был ephemeral. Если VM или сетевую конфигурацию
> пересоздать, необходимо проверить, не изменился ли public IP, и при
> необходимости обновить DNS в Cloudflare.

### 2.3 SSH

При создании VM в Oracle был добавлен локальный публичный SSH-ключ.

Подключение:

``` bash
ssh ubuntu@158.101.165.162
```

Никогда не передавайте и не загружайте приватный SSH-ключ.

------------------------------------------------------------------------

## 3. Сетевые правила Oracle

В Oracle есть облачный сетевой firewall в дополнение к firewall-правилам
внутри VM.

Подсеть VM использует:

``` text
Default Security List for vcn-20260913-2332
```

Примерный путь в Oracle Cloud Console:

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

### 3.1 Входящий HTTP

Добавить ingress rule:

``` text
Stateless: OFF
Source Type: CIDR
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Source Port Range: пусто / all
Destination Port Range: 80
Description: HTTP
```

### 3.2 Входящий HTTPS

Добавить:

``` text
Stateless: OFF
Source Type: CIDR
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Source Port Range: пусто / all
Destination Port Range: 443
Description: HTTPS
```

**Не удалять** существующее правило SSH для порта `22`.

------------------------------------------------------------------------

## 4. Проверка firewall внутри VM

На используемом Oracle Ubuntu image `ufw` не был установлен:

``` bash
sudo ufw status
```

Ответ:

``` text
sudo: ufw: command not found
```

Сам по себе этот результат не является ошибкой и не требует обязательной
установки UFW.

Фактические правила iptables были проверены командой:

``` bash
sudo iptables -L -n
```

Проверка слушающих портов:

``` bash
ss -lntp | grep -E ':80|:443' || echo "80/443 пока не слушаются"
```

До запуска Caddy отсутствие процессов на `80/443` было ожидаемым.

Не следует без необходимости очищать или переписывать правила iptables,
предоставленные Oracle. В них есть правила для Oracle Instance Services.

------------------------------------------------------------------------

# ЧАСТЬ II --- ПРОГРАММНОЕ ОБЕСПЕЧЕНИЕ СЕРВЕРА

## 5. Подготовка системы

Обновление Ubuntu:

``` bash
sudo apt update
sudo apt upgrade -y
```

Установка базовых утилит:

``` bash
sudo apt install -y git curl ca-certificates
```

Docker был установлен с помощью официального convenience script Docker.

После установки проверить:

``` bash
docker --version
docker compose version
```

Работа ARM64 была проверена:

``` bash
docker run --rm hello-world
```

В выводе использовался ARM64-вариант image, что подтвердило корректную
работу Docker на Ampere A1 VM.

------------------------------------------------------------------------

## 6. Клонирование репозитория

Production-каталог:

``` bash
mkdir -p ~/apps
cd ~/apps
```

Клонирование:

``` bash
git clone git@github.com:kukhmax/plan_-_estimate.git
cd plan_-_estimate
```

Переключение на ветку развёртывания:

``` bash
git checkout stage-9
```

Проверка:

``` bash
git status
git branch --show-current
git log -5 --oneline
```

------------------------------------------------------------------------

# ЧАСТЬ III --- PRODUCTION-КОНФИГУРАЦИЯ DOCKER

## 7. Почему не использовался development Compose

Исходный `docker-compose.yml` предназначен для разработки. В частности,
он:

-   публиковал PostgreSQL на host-порту 5432;
-   публиковал FastAPI на 8000;
-   запускал Vite dev server на 5173;
-   монтировал исходники frontend внутрь контейнера;
-   включал mock Telegram authentication;
-   задавал frontend API как `http://localhost:8000`.

Для production эти настройки не подходят.

Поэтому была создана отдельная production-конфигурация.

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

Важное production-поведение:

``` text
VITE_API_URL=""
```

заставляет frontend использовать same-origin API:

``` text
/api/...
```

а:

``` text
VITE_DEV_MOCK_AUTH=false
```

не позволяет использовать development mock authentication в
production-потоке.

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

Правило `try_files` необходимо для маршрутов React SPA.

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
        condition: service_healthy
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

### Ошибка имени проекта Compose

Первая сборка завершилась ошибкой примерно такого вида:

``` text
invalid tag "plan_-_estimate-frontend": invalid reference format
```

В имени каталога репозитория есть `_`, из-за чего автоматически
сформированное имя проекта/image оказалось недопустимым.

Исправление --- добавить в начало `docker-compose.prod.yml`:

``` yaml
name: plan-estimate
```

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

Маршрутизация:

``` text
/api/* → backend:8000
всё остальное → frontend:80
```

Caddy --- единственный контейнер приложения с публичными host-портами.

------------------------------------------------------------------------

# ЧАСТЬ IV --- СЕКРЕТЫ И ENVIRONMENT

## 12. `.env.production.example`

В репозитории хранится только шаблон:

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

Реальный файл на сервере:

``` text
.env.production
```

Он содержит реальные секреты и никогда не должен попадать в Git.

Ограничить права:

``` bash
chmod 600 .env.production
```

Для развёрнутого сайта:

``` text
APP_DOMAIN=plan-estimate.pl
```

------------------------------------------------------------------------

## 13. `.gitignore`

Production-секреты и сертификаты исключены:

``` gitignore
.env
.env.*
!.env.example
!.env.production.example

certs/
```

Проверка перед commit:

``` bash
git check-ignore -v .env.production certs/origin.key certs/origin.pem
```

Все три файла должны отображаться как ignored.

Никогда не коммитить:

``` text
.env.production
certs/origin.key
certs/origin.pem
```

В частности, никогда не публиковать:

-   Telegram bot token;
-   пароль PostgreSQL;
-   JWT secret;
-   TLS private key.

------------------------------------------------------------------------

# ЧАСТЬ V --- ПЕРВОНАЧАЛЬНАЯ СБОРКА ПРИЛОЖЕНИЯ

## 14. Проверка Compose

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config --quiet
```

Отсутствие вывода означает успешную проверку конфигурации.

------------------------------------------------------------------------

## 15. Production build

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  build
```

Первоначальная сборка backend и frontend успешно прошла на ARM64.

Production bundle frontend также проверялся на отсутствие
development-значений:

``` text
localhost:8000
VITE_DEV_MOCK_AUTH
```

------------------------------------------------------------------------

## 16. Запуск PostgreSQL и backend

Сначала были запущены PostgreSQL и backend.

Backend entrypoint выполняет:

``` text
alembic upgrade head
```

перед запуском Uvicorn.

На первоначально пустой production-БД успешно применились все
существовавшие Alembic migrations.

Проверка контейнеров:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps
```

Внутренняя проверка backend:

``` bash
docker exec plan_estimate_backend \
  curl -fsS http://localhost:8000/api/health
```

Ожидается:

``` json
{"status":"ok"}
```

Проверка PostgreSQL:

``` bash
docker exec plan_estimate_postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

------------------------------------------------------------------------

## 17. Запуск frontend

Frontend запускается через Compose.

nginx работает внутри контейнера на порту 80, но host port для него не
публикуется.

Проверялась внутренняя связность в обе стороны.

Backend → frontend:

``` bash
docker exec plan_estimate_backend curl -fsS http://frontend/
```

Frontend → backend:

``` bash
docker exec plan_estimate_frontend \
  wget -qO- http://backend:8000/api/health
```

Ожидаемый ответ backend:

``` json
{"status":"ok"}
```

### Нюанс с localhost и IPv6

Запрос к:

``` text
http://localhost/
```

внутри контейнера сначала не прошёл, поскольку `localhost` мог
резолвиться в IPv6 `::1`, а nginx слушал IPv4.

Использование:

``` text
http://127.0.0.1/
```

сработало.

Это не являлось проблемой production-маршрутизации.

------------------------------------------------------------------------

# ЧАСТЬ VI --- ДОМЕН

## 18. Покупка домена

Куплен домен:

``` text
plan-estimate.pl
```

Сразу после регистрации использовались nameservers CAL.pl:

``` text
ns1.cal.pl
ns2.cal.pl
```

Дополнительный хостинг, VPS, платный SSL или конструктор сайта у
регистратора не требовались.

Само приложение размещено в Oracle.

------------------------------------------------------------------------

# ЧАСТЬ VII --- CLOUDFLARE

## 19. Добавление домена в Cloudflare

Был создан аккаунт Cloudflare и добавлен домен:

``` text
plan-estimate.pl
```

Для этого развёртывания достаточно Cloudflare Free.

Для корневого домена была настроена A-запись:

``` text
Type: A
Name: @
IPv4: 158.101.165.162
TTL: Auto
Proxy: Proxied
```

Proxy должен быть включён --- оранжевое облако.

Поскольку proxy включён, публичный DNS lookup возвращает IP Cloudflare,
а не IP Oracle origin. Это нормально.

------------------------------------------------------------------------

## 20. Смена authoritative nameservers

Cloudflare назначил:

``` text
itzel.ns.cloudflare.com
rex.ns.cloudflare.com
```

В CAL.pl было подтверждено, что DNSSEC выключен. Интерфейс показывал:

``` text
Włącz DNSSEC
```

то есть DNSSEC в тот момент не был включён.

В разделе:

``` text
Zmiana DNS
```

старые:

``` text
ns1.cal.pl
ns2.cal.pl
```

были удалены и заменены на:

``` text
itzel.ns.cloudflare.com
rex.ns.cloudflare.com
```

------------------------------------------------------------------------

## 21. Проверка распространения DNS

На Manjaro команды `dig` и `nslookup` сначала отсутствовали.

Установка `dig`:

``` bash
sudo pacman -S bind
```

Проверка authoritative nameservers:

``` bash
dig NS plan-estimate.pl +short
```

Ожидается:

``` text
itzel.ns.cloudflare.com.
rex.ns.cloudflare.com.
```

Проверка A-записи:

``` bash
dig A plan-estimate.pl +short
```

При включённом Cloudflare Proxy здесь обычно будут IP Cloudflare, а не
`158.101.165.162`.

------------------------------------------------------------------------

# ЧАСТЬ VIII --- CLOUDFLARE ORIGIN CERTIFICATE

## 22. Создание сертификата

Путь в Cloudflare:

``` text
SSL/TLS
→ Origin Server
→ Create Certificate
```

Использованные параметры:

``` text
Generate private key and CSR with Cloudflare
Private key: RSA 2048
Hostnames:
  *.plan-estimate.pl
  plan-estimate.pl
```

Был создан долгосрочный Cloudflare Origin Certificate.

Срок действия установленного сертификата:

``` text
notBefore: Sep 14 2026
notAfter:  Sep 10 2041
```

Cloudflare показывает Origin private key при создании --- его необходимо
безопасно сохранить.

**Никогда не вставлять private key в чат, GitHub, документацию, логи или
тикеты.**

------------------------------------------------------------------------

## 23. Сохранение сертификата на Oracle

Создать каталог:

``` bash
cd ~/apps/plan_-_estimate
mkdir -p certs
```

Полный Origin Certificate сохранить в:

``` text
certs/origin.pem
```

включая:

``` text
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
```

Полный private key сохранить в:

``` text
certs/origin.key
```

включая:

``` text
-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
```

Права:

``` bash
chmod 600 certs/origin.key
chmod 644 certs/origin.pem
```

Проверять только метаданные:

``` bash
ls -l certs/
```

Не использовать `cat origin.key` для диагностического вывода, который
может случайно попасть куда-либо ещё.

------------------------------------------------------------------------

## 24. Проверка сертификата и ключа

Метаданные сертификата:

``` bash
openssl x509 \
  -in certs/origin.pem \
  -noout \
  -subject -issuer -dates
```

Проверка соответствия сертификата и private key:

``` bash
openssl x509 \
  -in certs/origin.pem \
  -pubkey -noout | sha256sum

openssl pkey \
  -in certs/origin.key \
  -pubout | sha256sum
```

Оба SHA256-хэша должны быть одинаковыми.

При первоначальном развёртывании они совпали.

------------------------------------------------------------------------

# ЧАСТЬ IX --- CADDY И HTTPS

## 25. Настройка production-домена

Открыть:

``` bash
nano .env.production
```

Установить:

``` env
APP_DOMAIN=plan-estimate.pl
```

Проверить:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config --quiet
```

------------------------------------------------------------------------

## 26. Запуск Caddy

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d caddy
```

Проверить:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps
```

Ожидаемые публичные mappings:

``` text
0.0.0.0:80->80/tcp
0.0.0.0:443->443/tcp
```

Логи:

``` bash
docker logs plan_estimate_caddy --tail 100
```

### Некритичные предупреждения Caddy, которые наблюдались

В логах встречались предупреждения:

-   о форматировании Caddyfile;
-   об отсутствии URL для OCSP stapling у Cloudflare Origin Certificate;
-   о размере UDP receive buffer для HTTP/3;
-   о том, что HTTP/2/HTTP/3 пропускаются на обычном HTTP-порту 80.

Они не мешали работе HTTPS.

------------------------------------------------------------------------

## 27. Проверка origin перед включением strict mode

Проверка frontend через локальный Caddy с принудительным hostname:

``` bash
curl -kI \
  --resolve plan-estimate.pl:443:127.0.0.1 \
  https://plan-estimate.pl
```

Ожидается:

``` text
HTTP/2 200
```

Проверка API:

``` bash
curl -k \
  --resolve plan-estimate.pl:443:127.0.0.1 \
  https://plan-estimate.pl/api/health
```

Ожидается:

``` json
{"status":"ok"}
```

`-k` используется здесь потому, что Cloudflare Origin Certificate
предназначен для проверки Cloudflare, а не обычным browser trust store
напрямую.

------------------------------------------------------------------------

## 28. Режим TLS в Cloudflare

После установки и проверки Origin Certificate:

``` text
Cloudflare
→ SSL/TLS
→ Overview
```

режим шифрования был изменён с:

``` text
Full
```

на:

``` text
Full (strict)
```

**Не использовать Flexible.**

Итоговый TLS-путь:

``` text
Браузер/Telegram
   ↓ публичный HTTPS
Cloudflare
   ↓ HTTPS + проверка Origin Certificate
Caddy
```

------------------------------------------------------------------------

# ЧАСТЬ X --- ПУБЛИЧНАЯ ПРОВЕРКА

## 29. Browser и API

Открыть:

``` text
https://plan-estimate.pl
```

Проверить:

``` text
https://plan-estimate.pl/api/health
```

Ожидается:

``` json
{"status":"ok"}
```

Из терминала:

``` bash
curl -I https://plan-estimate.pl
curl https://plan-estimate.pl/api/health
```

------------------------------------------------------------------------

## 30. Почему авторизация в обычном браузере сначала не прошла

При открытии production-приложения напрямую в обычном браузере
появлялась ошибка авторизации вида:

``` text
Telegram не передал данные авторизации
```

Это **ожидаемое поведение**.

В production установлено:

``` text
MOCK_TELEGRAM_AUTH=false
```

а Telegram `initData` frontend получает только при запуске как Telegram
Mini App.

Такое поведение подтвердило, что development mock authentication
случайно не включён в production.

------------------------------------------------------------------------

# ЧАСТЬ XI --- TELEGRAM MINI APP

## 31. Настройка BotFather

В Telegram:

``` text
@BotFather
→ /mybots
→ выбрать бота проекта
→ Bot Settings
→ Menu Button
```

URL Web App:

``` text
https://plan-estimate.pl
```

Название кнопки, например:

``` text
Plan & Estimate
```

Не нужно создавать нового бота или менять токен только ради настройки
URL Mini App.

------------------------------------------------------------------------

## 32. Проверка реальной Telegram-авторизации

Открыть бота в Telegram и запустить Mini App через настроенную кнопку
меню.

Telegram передаёт WebApp `initData`.

Frontend отправляет его на:

``` text
/api/auth/telegram
```

FastAPI проверяет подпись с использованием production:

``` text
TELEGRAM_BOT_TOKEN
```

При успешном развёртывании приложение показало:

``` text
Telegram Verified
```

Таким образом была проверена вся production-цепочка:

``` text
Telegram
→ Cloudflare
→ Caddy
→ React
→ FastAPI
→ проверка Telegram-подписи
→ PostgreSQL
```

------------------------------------------------------------------------

# ЧАСТЬ XII --- GIT И КОНФИГУРАЦИЯ DEPLOYMENT

## 33. Production deployment commit

Infrastructure-файлы были закоммичены без секретов.

Файлы:

``` text
.env.production.example
.gitignore
Caddyfile
docker-compose.prod.yml
frontend/Dockerfile.prod
frontend/nginx.conf
```

Production commit после rebase поверх актуального Stage 9:

``` text
7dd457f deploy(prod): add Oracle Cloud and Cloudflare production stack
```

Ветка `stage-9` на сервере и GitHub была синхронизирована, working tree
--- clean.

------------------------------------------------------------------------

## 34. Ошибка Git identity на Oracle

Первая попытка commit завершилась:

``` text
Author identity unknown
fatal: unable to auto-detect email address
```

Данные автора существующих commits были проверены:

``` bash
git log -1 --format='name=%an%nemail=%ae'
```

Затем настроены:

``` bash
git config --global user.name "kukhmax"
git config --global user.email "kukhmax@gmail.com"
```

------------------------------------------------------------------------

## 35. SSH-аутентификация GitHub с Oracle

При первом `git push` GitHub запросил username/password.

Для Git push пароль GitHub не используется.

Remote должен быть SSH:

``` bash
git remote -v
```

Ожидается:

``` text
git@github.com:kukhmax/plan_-_estimate.git
```

Изначально на сервере был только:

``` text
~/.ssh/authorized_keys
```

Он разрешает клиентам входить **на сервер**, но не является private key
для аутентификации **сервера в GitHub**.

Был создан отдельный GitHub key:

``` bash
ssh-keygen \
  -t ed25519 \
  -C "kukhmax@gmail.com" \
  -f ~/.ssh/id_ed25519_github
```

Публичный ключ:

``` bash
cat ~/.ssh/id_ed25519_github.pub
```

был добавлен в GitHub:

``` text
Settings
→ SSH and GPG keys
→ New SSH key
```

В GitHub копируется только `.pub`.

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

Проверка:

``` bash
ssh -T git@github.com
```

При успешной аутентификации GitHub сообщает, что shell access не
предоставляется.

------------------------------------------------------------------------

## 36. Push отклонён, потому что remote ушёл вперёд

Позже push завершился:

``` text
! [rejected] stage-9 -> stage-9 (fetch first)
```

На сервере был один локальный deployment commit, а в GitHub уже
появились два новых Stage 9 research commits.

Расхождение было проверено:

``` bash
git fetch origin

git log \
  --oneline \
  --graph \
  --decorate \
  --left-right \
  HEAD...origin/stage-9
```

Working tree был clean.

Вместо force push или лишнего merge локальный deployment commit был
перенесён поверх актуальной remote-ветки:

``` bash
git rebase origin/stage-9
```

После этого обычный push:

``` bash
git push origin stage-9
```

Итог:

``` text
7dd457f deploy(prod): add Oracle Cloud and Cloudflare production stack
e82cc26 docs(stage-9): research Krakow reveal prices
92c5ecf docs(stage-9): research Krakow painting and drywall prices
...
```

Не использовать `git push --force` на общей deployment-ветке только для
решения подобной ситуации.

------------------------------------------------------------------------

# ЧАСТЬ XIII --- СИНХРОНИЗАЦИЯ ЛОКАЛЬНОЙ МАШИНЫ

## 37. Синхронизация Manjaro с GitHub

На локальном компьютере:

``` bash
cd ~/Pr/plan_estimate
```

Проверить:

``` bash
git status
git branch --show-current
```

Получить remote-состояние:

``` bash
git fetch origin
```

Проверить:

``` bash
git status
git log --oneline --graph --decorate --all -12
```

Если локальная ветка clean и Git сообщает, что возможен fast-forward:

``` bash
git pull --ff-only origin stage-9
```

Проверить:

``` bash
git status
git log -3 --oneline --decorate
```

`--ff-only` не позволяет Git неожиданно создать merge commit.

------------------------------------------------------------------------

# ЧАСТЬ XIV --- БЕЗОПАСНОЕ ОБНОВЛЕНИЕ PRODUCTION

## 38. Стандартный deployment workflow

Для каждого будущего обновления production использовать
последовательность:

``` text
1. Проверить состояние production-репозитория
2. Fetch из GitHub
3. Просмотреть входящие commits
4. Сделать backup PostgreSQL
5. Fast-forward production-ветки
6. Проверить Compose
7. Собрать новые images, пока старые контейнеры продолжают работать
8. Применить через docker compose up -d
9. Проверить контейнеры
10. Проверить backend health
11. Проверить публичный HTTPS
12. При ошибках посмотреть логи
```

Не запускать вслепую `git pull && docker compose up`.

------------------------------------------------------------------------

## 39. Шаг 1 --- проверить состояние сервера

Подключиться:

``` bash
ssh ubuntu@158.101.165.162
cd ~/apps/plan_-_estimate
```

Проверить:

``` bash
git status
git branch --show-current
```

В нормальном состоянии production должен показывать:

``` text
On branch stage-9
nothing to commit, working tree clean
```

Если working tree содержит изменения --- **остановиться** и сначала
разобраться с ними.

------------------------------------------------------------------------

## 40. Шаг 2 --- fetch без изменения файлов

``` bash
git fetch origin
```

Посмотреть, что именно будет развёрнуто:

``` bash
git log --oneline HEAD..origin/stage-9
```

Если появились неожиданные commits --- остановиться и проверить их.

------------------------------------------------------------------------

## 41. Шаг 3 --- backup PostgreSQL

Создать каталог:

``` bash
mkdir -p ~/backups/plan-estimate
```

Создать сжатый SQL dump:

``` bash
docker exec plan_estimate_postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  | gzip > ~/backups/plan-estimate/db-$(date +%Y%m%d-%H%M%S).sql.gz
```

Проверить, что backup существует и не имеет нулевой размер:

``` bash
ls -lh ~/backups/plan-estimate/ | tail
```

Для важных production-обновлений рекомендуется иметь копию backup вне
Oracle VM. В будущем для этого можно использовать Cloudflare R2.

------------------------------------------------------------------------

## 42. Шаг 4 --- fast-forward production-кода

``` bash
git pull --ff-only origin stage-9
```

После этого:

``` bash
git status
git log -3 --oneline
```

Если Git отказывается из-за divergence, **ничего не форсировать**.
Проверить:

``` bash
git fetch origin
git log --oneline --graph --decorate --left-right HEAD...origin/stage-9
```

Сначала осознанно разрешить расхождение, и только затем продолжать
deployment.

------------------------------------------------------------------------

## 43. Шаг 5 --- проверить production-конфигурацию

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config --quiet
```

Если команда возвращает ошибку --- остановиться.

Не перезапускать рабочий production с некорректной
Compose-конфигурацией.

------------------------------------------------------------------------

## 44. Шаг 6 --- сначала build, пока старый production продолжает работать

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  build
```

Этот шаг намеренно отделён от `up -d`.

Если build завершился ошибкой --- остановиться.

Существующие production-контейнеры при этом продолжают работать, что
позволяет избежать ненужного downtime из-за ошибки компиляции или
сборки.

> **Важно: отличие build от пересоздания контейнера.** Успешный
> `docker compose build backend` создаёт новый image, но НЕ обновляет
> уже работающий контейнер. Команда `docker compose up -d backend`
> (следующий шаг) необходима для пересоздания контейнера из нового image.
> Оба шага обязательны при любом изменении кода backend.

> **Критично при наличии новой Alembic-миграции.** Если в коде появилась
> новая миграция, не выполнять `exec backend alembic heads` или
> `alembic history` против работающего контейнера после `git pull` но до
> пересоздания — работающий контейнер использует старый image и показывает
> старую версию кода. Проверить файл миграции напрямую из репозитория, а
> состояние базы данных — только из НОВОГО контейнера после `up -d backend`.

------------------------------------------------------------------------

## 45. Шаг 7 --- применить новые images

> **Если в обновлении присутствует новая Alembic-миграция:** этот шаг
> применяет её к базе данных (backend entrypoint запускает
> `alembic upgrade head` автоматически). Перед выполнением необходимо
> явное подтверждение владельца. Для определения пути миграции
> использовать файл из репозитория, а не запрос к работающему контейнеру.

Только после успешного build:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d
```

Compose пересоздаст сервисы, которым требуется обновление.

Backend entrypoint автоматически выполняет:

``` text
alembic upgrade head
```

до запуска Uvicorn.

Поэтому migrations новой версии применяются при запуске backend.

После `up -d backend` обязательно проверить, что текущая миграция
совпадает с head (следующий раздел §46).

------------------------------------------------------------------------

## 46. Шаг 8 --- проверить контейнеры и состояние миграции

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps
```

Ожидаемое состояние:

``` text
plan_estimate_postgres   Up ... (healthy)
plan_estimate_backend    Up ... (healthy)
plan_estimate_frontend   Up ...
plan_estimate_caddy      Up ...
```

PostgreSQL и FastAPI не должны иметь публичных host-port mappings.

Caddy должен публиковать `80` и `443`.

Если в обновлении присутствовала новая Alembic-миграция, проверить
её применение из НОВОГО контейнера:

``` bash
docker exec plan_estimate_backend alembic current
docker exec plan_estimate_backend alembic heads
```

Оба вывода должны совпадать (указывать на один и тот же revision).
Если не совпадают --- остановиться, проверить логи backend, не
продолжать до выяснения причины.

------------------------------------------------------------------------

## 47. Шаг 9 --- внутренняя проверка backend

``` bash
docker exec plan_estimate_backend \
  curl -fsS http://localhost:8000/api/health
```

Ожидается:

``` json
{"status":"ok"}
```

------------------------------------------------------------------------

## 48. Шаг 10 --- публичная проверка production

``` bash
curl -fsS https://plan-estimate.pl/api/health
```

Ожидается:

``` json
{"status":"ok"}
```

Проверить frontend:

``` bash
curl -I https://plan-estimate.pl
```

Ожидается успешный HTTP-ответ, обычно:

``` text
HTTP/2 200
```

После этого проверить Mini App непосредственно из Telegram, особенно
после изменений authentication, routing или frontend initialization.

------------------------------------------------------------------------

# ЧАСТЬ XV --- ДИАГНОСТИКА

## 49. Логи backend

``` bash
docker logs plan_estimate_backend --tail 100
```

Следить в реальном времени:

``` bash
docker logs -f plan_estimate_backend
```

`Ctrl+C` прекращает просмотр логов, но не останавливает контейнер.

------------------------------------------------------------------------

## 50. Логи frontend

``` bash
docker logs plan_estimate_frontend --tail 100
```

------------------------------------------------------------------------

## 51. Логи Caddy

``` bash
docker logs plan_estimate_caddy --tail 100
```

------------------------------------------------------------------------

## 52. Логи PostgreSQL

``` bash
docker logs plan_estimate_postgres --tail 100
```

------------------------------------------------------------------------

## 53. Полный статус сервисов

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

## 54. Проверка портов

``` bash
ss -lntp | grep -E ':80|:443'
```

Ожидаются Caddy/Docker listeners на публичных портах 80 и 443.

------------------------------------------------------------------------

## 55. Проверка DNS

С Manjaro:

``` bash
dig NS plan-estimate.pl +short
dig A plan-estimate.pl +short
```

Ожидаемые NS:

``` text
itzel.ns.cloudflare.com.
rex.ns.cloudflare.com.
```

A lookup обычно возвращает proxy-адреса Cloudflare.

------------------------------------------------------------------------

## 56. Ошибки Cloudflare 5xx

Если Cloudflare показывает ошибку, связанную с origin:

1.  проверить, что Caddy работает;
2.  проверить, что `80/443` открыты в Oracle Security List;
3.  посмотреть логи Caddy;
4.  проверить `APP_DOMAIN=plan-estimate.pl`;
5.  проверить наличие `certs/origin.pem` и `certs/origin.key`;
6.  проверить, что Cloudflare работает в режиме `Full (strict)`;
7.  проверить, что A-запись Cloudflare всё ещё указывает на текущий
    public IP VM.

Команды:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps

docker logs plan_estimate_caddy --tail 100
```

Локальная проверка origin:

``` bash
curl -kI \
  --resolve plan-estimate.pl:443:127.0.0.1 \
  https://plan-estimate.pl
```

Если локальный origin работает, а Cloudflare --- нет, проверять
DNS/proxy Cloudflare и сетевой доступ Oracle.

------------------------------------------------------------------------

## 57. Не работает Telegram authentication

Сначала различить поведение обычного браузера и Telegram.

Обычный браузер не имеет Telegram WebApp `initData`, поэтому production
authentication там может намеренно завершаться ошибкой.

Проверять через Mini App меню бота.

Проверить:

``` text
BotFather Mini App URL = https://plan-estimate.pl
MOCK_TELEGRAM_AUTH=false
ENVIRONMENT=production
APP_ENV=production
```

Проверить backend logs:

``` bash
docker logs plan_estimate_backend --tail 100
```

Не выводить и не передавать `TELEGRAM_BOT_TOKEN`.

------------------------------------------------------------------------

## 57a. В репозитории есть миграция N+1, но `alembic heads` показывает N

**Причина**: работающий backend-контейнер был собран из старого image — до
того, как был выполнен `git pull`. Этот контейнер не знает о новых файлах
миграций, добавленных в репозиторий после сборки его image.

Запрос `docker compose exec backend alembic heads` обращается к коду
внутри работающего контейнера, а не к файловой системе хоста. Поэтому
он вернёт head из старого image независимо от того, что находится в
`backend/alembic/versions/` на хосте.

**Диагностика**:

``` bash
# Убедиться, что git pull уже выполнен
git log --oneline -3

# Проверить, какой файл миграции есть в репозитории
ls backend/alembic/versions/

# Проверить, что показывает работающий контейнер
docker exec plan_estimate_backend alembic heads
# Если отличается от ожидаемого — контейнер использует старый image
```

**Решение**: сначала собрать новый image, затем пересоздать контейнер,
и только после этого проверять `alembic heads`.

``` bash
# 1. Собрать новый image
docker compose \
  --env-file .env.production \
  -p plan-estimate \
  -f docker-compose.prod.yml \
  build backend

# 2. Пересоздать контейнер из нового image
docker compose \
  --env-file .env.production \
  -p plan-estimate \
  -f docker-compose.prod.yml \
  up -d backend

# 3. Теперь проверить heads из НОВОГО контейнера
docker compose \
  --env-file .env.production \
  -p plan-estimate \
  -f docker-compose.prod.yml \
  exec backend alembic heads
# Теперь должен отображаться ожидаемый head из нового кода
```

> **Внимание**: в текущей production-конфигурации backend entrypoint
> автоматически запускает `alembic upgrade head` при старте контейнера.
> Это означает, что шаг 2 уже применит миграцию. Не запускать
> `alembic upgrade head` вручную повторно — убедиться через
> `alembic current`, что текущая ревизия совпадает с `alembic heads`.

------------------------------------------------------------------------

# ЧАСТЬ XVI --- КОМАНДЫ, ТРЕБУЮЩИЕ ОСОБОЙ ОСТОРОЖНОСТИ

## 58. Не удалять production volumes при обычном обновлении

**Не выполнять:**

``` bash
docker compose down -v
```

на production, если только намеренно не требуется удалить persistent
volumes.

`-v` может удалить PostgreSQL volume и вместе с ним production-данные.

Для обычного deployment `docker compose down` вообще не требуется.

Использовать:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d
```

------------------------------------------------------------------------

## 59. Избегать force push

Не использовать:

``` bash
git push --force
```

на `stage-9` только потому, что сервер отстал или ветки разошлись.

Сначала:

``` bash
git fetch origin
git status
git log --oneline --graph --decorate --left-right HEAD...origin/stage-9
```

и разобраться в причине divergence.

------------------------------------------------------------------------

## 60. Никогда не коммитить production-секреты

Перед commit deployment-изменений:

``` bash
git status --short
git check-ignore -v .env.production certs/origin.key certs/origin.pem
```

Реальные secret-файлы должны оставаться ignored.

------------------------------------------------------------------------

# ЧАСТЬ XVII --- БЫСТРЫЙ ЧЕКЛИСТ ОБНОВЛЕНИЯ

## 61. Обычное обновление

Использовать этот сокращённый вариант только после понимания полной
процедуры выше.

``` bash
ssh ubuntu@158.101.165.162

cd ~/apps/plan_-_estimate

git status
git fetch origin
git log --oneline HEAD..origin/stage-9
```

Если состояние clean и commits ожидаемые:

``` bash
mkdir -p ~/backups/plan-estimate

docker exec plan_estimate_postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  | gzip > ~/backups/plan-estimate/db-$(date +%Y%m%d-%H%M%S).sql.gz

ls -lh ~/backups/plan-estimate/ | tail
```

Обновить код:

``` bash
git pull --ff-only origin stage-9
```

Проверить:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config --quiet
```

Собрать, не останавливая сначала текущий production:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  build
```

Применить:

``` bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d
```

Проверить:

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

Ожидаемый API-ответ:

``` json
{"status":"ok"}
```

После этого открыть приложение из Telegram и проверить реальную Telegram
authentication.

------------------------------------------------------------------------

# ЧАСТЬ XVIII --- ТЕКУЩАЯ PRODUCTION-КОНФИГУРАЦИЯ

## 62. Production endpoints

``` text
Приложение:
https://plan-estimate.pl

Health:
https://plan-estimate.pl/api/health
```

## 63. Сервер

``` text
Oracle VM: plan-estimate
OS: Ubuntu 24.04 LTS
Архитектура: ARM64 / aarch64
Production-каталог: ~/apps/plan_-_estimate
```

## 64. Контейнеры

``` text
plan_estimate_postgres
plan_estimate_backend
plan_estimate_frontend
plan_estimate_caddy
```

## 65. Важные production-файлы

Отслеживаются Git:

``` text
docker-compose.prod.yml
Caddyfile
frontend/Dockerfile.prod
frontend/nginx.conf
.env.production.example
```

Только на сервере / секретные:

``` text
.env.production
certs/origin.pem
certs/origin.key
```

## 66. Cloudflare

``` text
Домен: plan-estimate.pl
Proxy: включён
SSL/TLS mode: Full (strict)

Nameservers:
itzel.ns.cloudflare.com
rex.ns.cloudflare.com
```

------------------------------------------------------------------------

# ЧАСТЬ XIX --- РЕКОМЕНДУЕМЫЕ СЛЕДУЮЩИЕ УЛУЧШЕНИЯ ИНФРАСТРУКТУРЫ

Первоначальный production deployment работает. Следующие пункты следует
рассматривать как будущие инфраструктурные задачи, а не как обязательные
условия для текущей работы:

1.  Автоматизировать PostgreSQL backups и их ротацию.
2.  Хранить копии backups вне Oracle VM, например в Cloudflare R2.
3.  Описать и протестировать процедуру восстановления БД.
4.  Рассмотреть резервирование/стабилизацию Oracle public IP или
    обеспечить обновление DNS при его изменении.
5.  Рассмотреть ограничение SSH-доступа после появления безопасного
    способа восстановления доступа.
6.  Автоматизировать deployment только после того, как ручной runbook
    доказал свою надёжность.
7.  Добавить monitoring/alerts для `/api/health`, дискового пространства
    и ошибок backup.
8.  Периодически удалять неиспользуемые Docker images после
    подтверждения, что текущий deployment исправен.

Не следует усложнять работающий production ради этих оптимизаций, если
это ухудшает возможность быстрого восстановления.

------------------------------------------------------------------------

## 67. Основные принципы безопасности

Production workflow намеренно консервативный:

``` text
GitHub — источник кода приложения
            ↓
сначала fetch и проверка
            ↓
backup постоянных данных
            ↓
только fast-forward
            ↓
проверка конфигурации
            ↓
build, пока текущий production продолжает работать
            ↓
применение только после успешного build
            ↓
внутренний и публичный health-check
```

Самые важные правила:

-   не публиковать PostgreSQL наружу;
-   не включать Telegram mock auth в production;
-   не коммитить секреты;
-   не удалять Docker volumes при обычном deployment;
-   не использовать force push для обычных проблем синхронизации;
-   не останавливать исправный production до проверки возможности
    собрать новую версию;
-   перед обновлением, которое может содержать migrations, всегда делать
    backup БД;
-   после deployment проверять и `/api/health`, и Telegram Mini App.

------------------------------------------------------------------------

# ЧАСТЬ XX --- ПРОВЕРЕННАЯ PRODUCTION-ПРОЦЕДУРА (использованная в практике)

## 68. Каноническая команда Compose

На production всегда использовать **одну** каноническую форму с явным
именем проекта (`name: plan-estimate` из `docker-compose.prod.yml`):

``` bash
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml <command>
```

Имя проекта `-p plan-estimate` фиксирует одинаковый контекст Compose в
любой директории и исключает конфликт имён с dev-стеком.

## 69. Безопасный порядок обновления

### 69a. Обновление БЕЗ новой Alembic-миграции (frontend или backend)

``` bash
# 1. Код: только fast-forward на целевой ветке
git fetch origin
git status                 # дерево должно быть чистым
git pull --ff-only origin <branch>

# 2. Проверка конфигурации
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml config --quiet

# 3. Собрать, пока текущий production продолжает работать
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml build

# 4. Применить
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d

# 5. Состояние контейнеров
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml ps

# 6. Внутренний health backend
docker exec plan_estimate_backend curl -fsS http://localhost:8000/api/health
#    Ожидается: {"status":"ok"}

# 7. Публичная проверка
curl -fsS https://plan-estimate.pl/api/health
curl -I https://plan-estimate.pl
```

### 69b. Обновление С новой Alembic-миграцией (обязательный порядок)

> **Критичное правило**: не выполнять `alembic heads` или `alembic history`
> внутри работающего backend-контейнера после `git pull` но до пересоздания
> контейнера. Работающий контейнер использует старый image и возвращает
> старый head кода. Файл миграции нужно проверять напрямую из репозитория.

``` bash
# 1. Код: только fast-forward
git fetch origin
git status
git pull --ff-only origin <branch>
git log --oneline -3      # убедиться, что ожидаемый commit в HEAD

# 2. Проверить файл миграции из РЕПОЗИТОРИЯ (не из работающего контейнера)
cat backend/alembic/versions/<new_migration_file>.py
# Убедиться: является ли миграция аддитивной/обратно-совместимой?
# Определить текущую ревизию из СТАРОГО контейнера:
docker exec plan_estimate_backend alembic current

# 3. Проверка конфигурации Compose
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml config --quiet

# 4. Собрать новый backend image (пока старые контейнеры продолжают работать)
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml build backend
# (также собрать frontend, если он изменился)

# ─────────────────────────────────────────────────────────────────────────
# СТОП — ОЖИДАНИЕ ЯВНОГО ПОДТВЕРЖДЕНИЯ ВЛАДЕЛЬЦА
# Перед этим шагом сообщить:
#   - текущая ревизия БД (из шага 2)
#   - ожидаемый head (из файла миграции в репозитории)
#   - характер миграции (аддитивная / деструктивная)
#   - рекомендация по backup
# ─────────────────────────────────────────────────────────────────────────

# 5. Пересоздать backend из НОВОГО image
#    (entrypoint автоматически применит alembic upgrade head при старте)
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d backend

# 6. Проверить применение миграции из НОВОГО контейнера
docker exec plan_estimate_backend alembic current
docker exec plan_estimate_backend alembic heads
#    Оба вывода должны совпадать. Если нет --- остановиться, смотреть логи.

# 7. Применить frontend (если изменился)
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d frontend

# 8. Состояние контейнеров
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml ps

# 9. Внутренний health
docker exec plan_estimate_backend curl -fsS http://localhost:8000/api/health

# 10. Публичная проверка
curl -fsS https://plan-estimate.pl/api/health
curl -I https://plan-estimate.pl

# 11. При ошибке health — посмотреть логи
docker logs plan_estimate_backend --tail 100
```

## 70. НИКОГДА не выполнять при обычном развёртывании

``` bash
docker compose ... down -v        # НЕ выПОЛНЯТЬ
```

`down -v` удаляет persistent volumes (PostgreSQL). При обычном обновлении
это категорически запрещено (см. Часть XVI §58).

## 71. Обновление Telegram Menu Button + cache-busting после каждого frontend deployment

Vite собирает assets с хешированными именами, но Telegram WebView может
удерживать **старый launch document** (Javascript-слой `index.html`) между
запусками Mini App. Поэтому после каждого production-обновления frontend
следует сменить версию WebApp URL в кнопке меню бота:

``` bash
# 1. Получить короткий SHA текущего деплоя
git rev-parse --short HEAD

# 2. Загрузить TELEGRAM_BOT_TOKEN из .env.production (НЕ печатать токен)
set -a; source .env.production; set +a

# 3. Установить Menu Button с cache-busting URL (версия = короткий SHA)
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" \
  -H "Content-Type: application/json" \
  -d '{"menu_button": {"type": "web_app", "text": "Plan & Estimate", "web_app": {"url": "https://plan-estimate.pl/?v=<git-short-sha>"}}}'

# 4. Проверить установленное значение
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton"
```

Пояснение: команда выше задаёт **глобальный (default) Menu Button** для
всех чатов; опциональный параметр `chat_id` применяет кнопку только к
одному пользователю. После `setChatMenuButton` с новый `?v=...` WebView
Telegram перезагружает Mini App по новому launch URL, что и обновляет
интерфейс. `TELEGRAM_BOT_TOKEN` подставляется только внутри команды curl и
не выводится на экран. Проверка выполняется командой `getChatMenuButton`.

## 72. Stage 14 — MEDIA BACKUP / RESTORE (ФИНАЛЬНАЯ ПРОЦЕДУРА, проверена в 14D)

> **СТАТУС: ФИНАЛЬНЫЙ (Stage 14D.7, 2026-10-06).** Процедура выполнена на
> production 2026-10-05/06 (Stage 14D.6, фазы P0–P8) и принята владельцем
> 2026-10-06: первый production-бэкап опубликован в Oracle, проверен двумя
> независимыми читателями, **восстановлен** в чистую PostgreSQL на рабочей
> станции и сверен с production (число строк во всех таблицах совпало).
> Изолированный restore-drill (14D.5) пройден 2026-10-05.
> **Загрузка фото в production остаётся ВЫКЛЮЧЕННОЙ**
> (`PHOTO_UPLOADS_ENABLED=false`): включение — отдельное решение владельца в
> Stage 14E. Расписания бэкапов **нет**: бэкап запускается вручную (см. 72.7).
> Каноничные документы: `docs/STAGE_14D_BACKUP_RESTORE_PLAN.md` (контракт и
> §17.1 запись ворот), `docs/STAGE_14D6_PRODUCTION_RUNBOOK.md` (фазы P0–P8 с
> результатами), `docs/STAGE_14D5_DRILL_COMMANDS.md` (проверенные блоки дрилла).

### 72.1 Модель хранения

- **Primary:** Cloudflare R2, класс Standard, юрисдикция **EU**, приватный
  bucket `plan-estimate-media-prod` (без публичного доступа, без r2.dev,
  без custom domain). Токен для бэкапа — **только чтение**, ограничен по IP VM.
- **Независимая резервная копия:** Oracle Object Storage, bucket
  `plan-estimate-backup-prod` (compartment `plan-estimate-backup`, регион
  `eu-frankfurt-1`, versioning включён). Загрузчик работает по **instance
  principal** VM с политикой «только создание объектов» (`OBJECT_CREATE`,
  без перезаписи и удаления); читать бэкап вне VM может только пользователь
  `plan-estimate-restore-operator` (группа `plan-estimate-backup-restore`,
  политика только чтения) по API-ключу, который создаётся на время проверки
  и **удаляется** после.
- **Версионирование R2 НЕ является независимым backup.**
- Объекты **write-once**: ключи `photos/v1/{asset_uuid}/original.{ext}`,
  `display.jpg`, `thumb.jpg` никогда не перезаписываются и в v1 не
  удаляются; более поздняя копия объектов — надмножество того, на что
  ссылается более ранний dump БД.
- После появления фотографий `pg_dump` сам по себе **не** полный backup:
  нужны БД и объекты; БД + медиа — не атомарный снимок, согласованность
  проверяется integrity-проверкой и `verify`.
- Структура бакета: `db/<run_id>/plan-estimate.sql.gz.age`,
  `runs/<run_id>/manifest.jsonl`, `runs/<run_id>/COMPLETE.json` (печать,
  пишется последней), `media/…` для READY assets.

### 72.2 Где что лежит

| Что | Где | Права |
|---|---|---|
| Данные бэкапа (локально) | VM `~/backups/plan-estimate/db-backup/data/{work,encrypted,evidence}`, `run.lock` | 0700 / файлы 0600 |
| Пароль роли `pe_backup` | VM `…/db-backup/secrets/pgpass` | 0600, монтируется read-only, не попадает в env/argv |
| Настройки бэкапа и загрузчика | VM `…/secrets/backup.env`, `…/secrets/upload.env` (R2-токен только чтение, имена целей, `BACKUP_TOOL_COMMIT`) | 0600 |
| Образы | VM `plan-estimate-backup:local`, `plan-estimate-backup-upload:local` | — |
| Закрытый ключ age A | рабочая станция `~/.local/share/plan-estimate/age/backup-identity.txt` (+ копия под парольной фразой на флешке); ключ B — только на бумаге | 0600 |
| Роль БД | `pe_backup` (`LOGIN`, `CONNECT`, `pg_read_all_data`, без других атрибутов) | — |

На VM **никогда** не существует закрытого ключа age и учётных данных
restore-пользователя.

### 72.3 Порядок backup (проверено в 14D.6)

Образы собирать **только из `git archive` нужного коммита**, не из рабочей
копии (права файлов рабочей копии попадают в образ). Запуск — командами
`docker run` по определению сервисов `backup` / `backup-upload` (не
`docker compose -p plan-estimate`: у production-сети метка `config-hash`,
расхождение может привести к её пересозданию под работающим стеком).

```bash
# 1. Образы (на VM, один раз на версию кода)
cd ~/apps/plan_-_estimate && git fetch origin <ветка>
COMMIT=$(git rev-parse origin/<ветка>)                 # его же записать в BACKUP_TOOL_COMMIT (upload.env)
D=$(mktemp -d "$HOME/pe-build.XXXXXX")
git archive --format=tar "$COMMIT" backend docker-compose.prod.yml | tar -x --no-same-owner -C "$D"
docker build -f "$D/backend/Dockerfile.backup" -t plan-estimate-backup:local "$D/backend"
docker build -f "$D/backend/Dockerfile.uploader" --build-arg BACKUP_IMAGE=plan-estimate-backup:local \
  -t plan-estimate-backup-upload:local "$D/backend"
rm -r "$D"

# 2. db-dump: локальный зашифрованный бэкап (читает БД одним снимком REPEATABLE READ)
R="$HOME/backups/plan-estimate/db-backup"; set -a; . "$R/secrets/backup.env"; set +a
docker run --name pe-backup-prod-dump --rm --init --stop-timeout 45 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 512m --cpus 0.5 --pids-limit 64 \
  --user "$BACKUP_UID:$BACKUP_GID" --network plan-estimate_internal --tmpfs /tmp:size=16m \
  -v "$R/data:/backup" -v "$R/secrets/pgpass:/run/secrets/pgpass:ro" \
  -e PGHOST="$BACKUP_PGHOST" -e PGPORT="$BACKUP_PGPORT" -e PGDATABASE="$BACKUP_PGDATABASE" \
  -e PGUSER="$BACKUP_PGUSER" -e PGSSLMODE="$BACKUP_PGSSLMODE" -e PGPASSFILE=/run/secrets/pgpass \
  -e BACKUP_AGE_RECIPIENTS="$BACKUP_AGE_RECIPIENTS" plan-estimate-backup:local db-dump
# PASS: «backup complete: run_id=… ready_count=…», exit 0; в encrypted/<run_id>/ четыре файла 0600; work/ и evidence/ пусты

# 3. upload: публикация запуска в Oracle (необратимо: загрузчик не умеет перезаписывать и удалять)
set -a; . "$R/secrets/backup.env"; . "$R/secrets/upload.env"; set +a   # BACKUP_UID/GID и BACKUP_AGE_RECIPIENTS живут только в backup.env
export MEDIA_S3_ENDPOINT_URL="$BACKUP_UPLOAD_S3_ENDPOINT_URL" MEDIA_S3_BUCKET="$BACKUP_UPLOAD_S3_BUCKET" MEDIA_S3_REGION="$BACKUP_UPLOAD_S3_REGION" \
  MEDIA_S3_ACCESS_KEY_ID="$BACKUP_UPLOAD_S3_ACCESS_KEY_ID" MEDIA_S3_SECRET_ACCESS_KEY="$BACKUP_UPLOAD_S3_SECRET_ACCESS_KEY" MEDIA_STORAGE_NAME="$BACKUP_UPLOAD_SOURCE_NAME"
docker run --name pe-backup-prod-upload --rm --init --stop-timeout 45 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 512m --cpus 0.5 --pids-limit 64 \
  --user "$BACKUP_UID:$BACKUP_GID" --network pe-upload --tmpfs /tmp:size=256m -v "$R/data:/backup" \
  -e MEDIA_S3_ENDPOINT_URL -e MEDIA_S3_BUCKET -e MEDIA_S3_REGION -e MEDIA_S3_ACCESS_KEY_ID -e MEDIA_S3_SECRET_ACCESS_KEY -e MEDIA_STORAGE_NAME \
  -e BACKUP_OCI_NAMESPACE -e BACKUP_OCI_BUCKET -e BACKUP_OCI_REGION -e BACKUP_TOOL_COMMIT -e BACKUP_AGE_RECIPIENTS \
  plan-estimate-backup-upload:local upload --environment production --allow-production
# PASS: «upload complete: run_id=… objects=<медиа-объекты> ready_assets=<n>», exit 0, evidence/<run_id>.published.json;
# повторный upload того же запуска → «nothing to upload», exit 8

# 4. verify с VM (instance principal), получатели A и B из BACKUP_AGE_RECIPIENTS
set -a; . "$R/secrets/backup.env"; . "$R/secrets/upload.env"; set +a   # нужен и в новом сеансе: переменные из шагов 2–3 не сохраняются
docker run --rm --init --read-only --cap-drop ALL --security-opt no-new-privileges:true --user "$BACKUP_UID:$BACKUP_GID" \
  --network pe-upload --tmpfs /tmp:size=256m -e BACKUP_OCI_NAMESPACE -e BACKUP_OCI_BUCKET -e BACKUP_OCI_REGION -e BACKUP_AGE_RECIPIENTS \
  plan-estimate-backup-upload:local verify --run-id <run_id> --mode full
# PASS: «verify ok: run_id=… mode=full …», exit 0
```

Коды выхода: `db-dump` 0, 1, 3 (блокировка занята), 4 (остатки в `work/`), 5, 6,
7; `upload` 0, 1, 3, 5, 6, 8 (нечего загружать), 9, 10 (запуск запечатан, но
локальное evidence не записано — повторить **ту же** команду); `verify` 0, 1,
5, 6, 7. Если `upload` упал после записи манифеста — нужен **новый** `db-dump`
(план 14D §15). Загрузчик не удаляет: лишние объекты убирает администратор.

### 72.4 Порядок restore (проверено в 14D.5 и 14D.6, рабочая станция)

1. Restore-пользователь `plan-estimate-restore-operator`: владелец создаёт
   **новый** API-ключ в консоли Oracle, конфиг собирается с проверкой
   fingerprint (ключ и `config` — 0600, `key_file=/run/oci/key.pem`).
2. Образы (`backup` + слой `Dockerfile.uploader` с `oci`) собираются на
   станции из `git archive`; временная PostgreSQL 16 в отдельной сети без
   опубликованных портов; суперпользователь — владелец дампа
   (`plan_estimate`), база `pe_restore_scratch_<…>` (имя и хост должны
   содержать маркер scratch), пустая.
3. `docker run … plan-estimate-backup-upload:<тег> restore --phase database
   --run-id <run_id> --identity-file /run/age/identity.key --scratch-dir /tmp
   --report-file /out/<новый файл>.json --oci-config /run/oci/config
   --allowed-host <хост scratch-БД> --forbidden-bucket plan-estimate-media-prod …`
   (ключ A монтируется только на чтение; дрилловый целевой бакет R2 требуется
   командой даже без медиа). Затем `--phase media`, если в запуске есть READY
   assets, и `scripts/media_integrity_check.py --verify-sha256 --strict`.
4. Сверка: число строк во всех таблицах схемы `public` в восстановленной и
   боевой базе (`SELECT` в сессии `default_transaction_read_only=on`);
   `alembic_version` = head репозитория.
5. Уборка: контейнер и сеть scratch, файлы паролей (`shred`); API-ключ
   restore-пользователя **удалить** в консоли и убедиться, что старый ключ
   даёт `NotAuthenticated` (401); `shred` ключа и конфига на станции.

### 72.5 Чего НЕ делать

- Не собирать образы из рабочей копии на сервере; не использовать
  `docker compose -p plan-estimate` для сервиса `backup`.
- Не создавать и не хранить закрытый ключ age на VM; не хранить на VM
  учётные данные restore-пользователя.
- Не вставлять секреты в чат/Git; `read` внутри `bash <<'EOF'` читает сам
  скрипт — вводить значения только `read … < /dev/tty`.
- Не «исправлять» несоответствие правкой evidence, манифеста или бакета
  вручную; не удалять production-объекты как тест.
- Не включать `PHOTO_UPLOADS_ENABLED` без явного решения владельца (14E).

### 72.6 Read-only integrity-проверка (реализована в 14B.4)

Команда только читает: никаких записей, удалений, исправлений строк БД,
presigned URL и вывода секретов. При `MEDIA_STORAGE_BACKEND=disabled`
завершается с кодом 2 («состояние хранилища неизвестно»), а не сообщает
«пусто».

``` bash
cd ~/apps/plan_-_estimate
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml \
  exec backend python scripts/media_integrity_check.py
# опционально: --verify-sha256 (скачивает READY оригиналы во временный каталог
# и сравнивает sha256), --strict, --json, --expect-storage-name r2-primary
```

Коды выхода: `0` — чисто (предупреждения допустимы), `1` — ошибки
целостности (или предупреждения при `--strict`), `2` — проверка не
выполнена (хранилище отключено/недоступно/неверно настроено).

Классификация: `MISSING_ORIGINAL` (потеря доказательства),
`MISSING_DERIVATIVE` (восстанавливается из независимого backup; инструмента
регенерации из оригинала нет — 14D.1), `SIZE_MISMATCH`,
`CHECKSUM_MISMATCH` (только с `--verify-sha256`), `PENDING_INCOMPLETE`,
`FAILED_RELATED`, `ORPHAN_CANDIDATE`, `UNKNOWN_KEY`, `OTHER_STORAGE`.
**`ORPHAN_CANDIDATE` — только кандидат** (например, загрузка после точки
dump БД или брошенная загрузка). Инструмент ничего не считает «безопасным
для удаления» и ничего не удаляет.

### 72.7 Состояние на 2026-10-06 и что остаётся открытым

- Первый production-запуск `20261005T214112Z-c00c8951` (БД на момент
  2026-10-05 21:41 UTC, `ready_count = 0`): три объекта в
  `plan-estimate-backup-prod`, `verify --mode full` с VM и со станции — ok,
  восстановление и сверка таблиц — ok. R2 `plan-estimate-media-prod` пуст.
- **Расписания и политики хранения нет.** Бэкап актуален на момент
  последнего ручного запуска. Частота (RPO), таймер, хранение и очистка
  бакета — решение владельца **до включения загрузки фото** (14E).
- Старые ручные дампы (до 14D) зашифрованы для A и B и лежат в
  `~/backups/plan-estimate/legacy-encrypted/` (только на VM).
- Включение загрузки фото (`PHOTO_UPLOADS_ENABLED=true`) — Stage 14E, после
  подписи 14D.7 и свежего бэкапа.
