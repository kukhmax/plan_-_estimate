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

------------------------------------------------------------------------

## 45. Шаг 7 --- применить новые images

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

------------------------------------------------------------------------

## 46. Шаг 8 --- проверить контейнеры

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

## 69. Безопасный порядок обновления (проверен)

``` bash
# 1. Код: только fast-forward на целевой ветке
git fetch origin
git status                 # дерево должно быть чистым
git pull --ff-only origin stage-9

# 2. Проверка конфигурации (до любых изменений)
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml config --quiet

# 3. Собрать, пока текущий production продолжает работать
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml build

# 4. Применить
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --build

# 5. Состояние контейнеров
docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml ps

# 6. Внутренний health backend
docker exec plan_estimate_backend curl -fsS http://localhost:8000/api/health
#    Ожидается: {"status":"ok"}

# 7. Текущая миграция (backend entrypoint применяет alembic upgrade head при старте)
docker exec plan_estimate_backend alembic current

# 8. Публичная проверка frontend
curl -fsS https://plan-estimate.pl
curl -I https://plan-estimate.pl
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
