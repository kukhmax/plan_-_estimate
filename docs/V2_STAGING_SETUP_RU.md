# Стенд версии 2: `v2.plan-estimate.pl` без Telegram-входа

Статус: **черновик, ждёт «да» владельца (2026-10-19)**. Общий план: `docs/POST_MVP_PLAN_RU.md`, раздел 2.
Это шаг **V2-0** (инфраструктура) и описание того, как стенд живёт рядом с продом, не трогая его данные.

---

## 1. Что получится

```text
Интернет ── Cloudflare (DNS, прокси, Access) ── VM Oracle
                                                 │
                         ┌───────────────────────┴───────────────────────┐
                         │  Caddy прода (один на VM, порты 80/443)       │
                         └───────┬──────────────────────────┬────────────┘
             plan-estimate.pl    │                          │   v2.plan-estimate.pl
                  сеть internal  │                          │   сеть pe-v2-edge
     ┌───────────────────────────┴───┐        ┌─────────────┴─────────────────────┐
     │ прод: frontend, backend,      │        │ стенд (проект pe-v2): frontend,   │
     │ postgres (том postgres_data)  │        │ backend ── сеть pe-v2-internal ── │
     │ ветка main, ~/plan-estimate   │        │ postgres (свой том), ветка v2,    │
     └───────────────────────────────┘        │ ~/plan-estimate-v2                │
                                              └───────────────────────────────────┘
```

* **Отдельная папка на VM** `~/plan-estimate-v2` с веткой `v2`: папка прода `~/plan-estimate` никогда не переключается на `v2`.
* **Отдельный проект Compose** `pe-v2`: свои имена контейнеров, свои тома, своя внутренняя сеть. Стенд **не видит** базу прода: его backend не подключён к сети `internal` прода.
* **Общий только Caddy**: он подключается ещё к одной сети `pe-v2-edge`, где видит только frontend и backend стенда.
* **IMDS-guard** (`ops/imds-guard`) закрывает доступ к метаданным VM для всех мостов Docker, поэтому новые сети стенда защищены автоматически. После создания сетей проверить: `sudo ops/imds-guard/pe-imds-guard.sh status`.

## 2. Почему поддомен, а не `plan-estimate.pl/ver-2`

| | Поддомен `v2.plan-estimate.pl` | Путь `plan-estimate.pl/ver-2` |
| --- | --- | --- |
| Офлайн-кэш и очередь изменений (IndexedDB, Stage 19) | свои у стенда | **общие с продом**: V2 может прочитать или отправить очередь прода |
| `localStorage`, токен входа | свои | общие с продом |
| `/api` | как есть | нужен префикс `/ver-2/api` во всём фронтенде |
| Сборка Vite | как есть | `base: '/ver-2/'`, переделка путей ресурсов |
| Cloudflare Access | на весь поддомен | только на путь, сложнее |

Поэтому — поддомен.

---

## 3. Что делает владелец (один раз)

Каждый пункт с изменением на сервере — по отдельному «да», как при выкладке.

### 3.1. Cloudflare: DNS

1. Cloudflare → домен `plan-estimate.pl` → **DNS → Records → Add record**.
2. Тип `CNAME`, имя `v2`, цель `plan-estimate.pl`, **Proxy status: Proxied** (оранжевое облако). Сохранить.

### 3.2. Сертификат origin

Caddy прода использует сертификат Cloudflare Origin из `~/plan-estimate/certs/origin.pem`. Проверить, покрывает ли он поддомены:

```bash
openssl x509 -in ~/plan-estimate/certs/origin.pem -noout -ext subjectAltName
```

* Есть `*.plan-estimate.pl` → ничего делать не нужно (стандартный сертификат Cloudflare обычно включает оба имени).
* Нет → Cloudflare → **SSL/TLS → Origin Server → Create Certificate**, имена `plan-estimate.pl, *.plan-estimate.pl`, срок 15 лет; положить как `certs/origin-v2.pem` и `certs/origin-v2.key` (права `600`) и указать их в блоке стенда (п. 4.3).

### 3.3. Cloudflare Access (внешний замок)

Без него страница входа стенда открыта всему интернету. Access бесплатен до 50 пользователей.

1. Cloudflare → **Zero Trust** → **Access → Applications → Add an application → Self-hosted**.
2. Application domain: `v2.plan-estimate.pl`. Session duration: 1 месяц.
3. Policy: **Allow**, Include → **Emails** → твой e-mail и e-mail мастеров-тестировщиков.
4. Login method: **One-time PIN** (код на e-mail).
5. Проверка: открыть `https://v2.plan-estimate.pl` в окне инкогнито → должна появиться страница Cloudflare с запросом e-mail.

### 3.4. Хранилище фото для стенда (R2)

Рекомендуется **отдельный бакет** `plan-estimate-v2` и отдельный API-токен с доступом **только к нему** (Cloudflare → R2 → Manage API tokens → Object Read & Write → Specify bucket). Тогда ошибка в V2 физически не может удалить фото прода.

### 3.5. Ресурсы VM

```bash
free -h; df -h /; docker system df
```

Стенду нужно около 1 ГБ памяти и 5 ГБ диска. Если свободно меньше — сначала очистить старые образы (`docker image prune` — по отдельному «да»).

---

## 4. Что делает Claude Code (шаг V2-0, ветка `v2`)

### 4.1. Ветка

```bash
git checkout main && git pull --ff-only
git checkout -b v2
```

### 4.2. `docker-compose.v2.yml`

Новый файл на основе `docker-compose.prod.yml`, отличия:

* `name: pe-v2`; контейнеры `pe_v2_postgres`, `pe_v2_backend`, `pe_v2_frontend`; **без** `caddy`, `backup`, `backup-upload`.
* Тома: `pe_v2_postgres_data`.
* Сети: `pe-v2-internal` (postgres + backend + frontend) и внешняя `pe-v2-edge` (только backend и frontend):

```yaml
networks:
  pe-v2-internal:
    driver: bridge
  pe-v2-edge:
    external: true
    name: pe-v2-edge
```

* Backend: `ENVIRONMENT: staging`, `APP_ENV: staging`, `DEBUG: "false"`, `MOCK_TELEGRAM_AUTH: "false"`, `CALENDAR_DISPATCHER_ENABLED: "false"`, `AUTH_PROVIDER: ${AUTH_PROVIDER:-password}` (появится в V2-1), переменные из `.env.staging`.
* Frontend: аргумент сборки `VITE_AUTH_MODE=password` (используется с V2-1).

### 4.3. Caddy: подключение блока стенда

В `Caddyfile` (прод) добавить **одну строку** в конец:

```caddyfile
import /etc/caddy/sites/*.caddy
```

Новый файл `caddy-sites/v2.caddy` (в репозитории — как пример `caddy-sites/v2.caddy.example`; на сервере — настоящий):

```caddyfile
v2.plan-estimate.pl {
    tls /etc/caddy/certs/origin.pem /etc/caddy/certs/origin.key
    encode gzip zstd

    @photo_upload {
        method POST
        path_regexp ^/api/projects/[^/]+/photos$
    }
    handle @photo_upload {
        request_body {
            max_size 27000000
        }
        reverse_proxy pe_v2_backend:8000
    }

    @api path /api/*
    handle @api {
        reverse_proxy pe_v2_backend:8000
    }

    handle {
        reverse_proxy pe_v2_frontend:80
    }

    header X-Robots-Tag "noindex, nofollow"
}
```

В `docker-compose.prod.yml` у сервиса `caddy` — том `./caddy-sites:/etc/caddy/sites:ro` и вторая сеть `pe-v2-edge` (внешняя). Это **единственное изменение прода** в V2-0.

Проверка до перезапуска Caddy:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production -p plan-estimate \
  run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile
```

### 4.4. Проверки старта для staging

`backend/app/core/startup_checks.py` сейчас строг только для `production`. Сделать:

* `staging` проверяется так же строго: `JWT_SECRET_KEY` ≥ 32 знаков, не заглушка; `MOCK_TELEGRAM_AUTH` и `DEBUG` выключены; `DATA_KEK` задан.
* Токен бота обязателен, только если `AUTH_PROVIDER=telegram`.
* `staging` не стартует, если `DATA_KEK` совпадает с ключом прода — защита от копирования `.env.production`: стенд сравнивает отпечаток SHA-256 ключа с переменной `PROD_KEK_FINGERPRINT`, если она задана (заполнить в `.env.staging` отпечатком ключа прода, сам ключ туда не копировать).

Тесты: по образцу существующих тестов startup checks; мутации проверок.

### 4.5. `.env.staging.example`

По образцу `.env.production.example`: `ENVIRONMENT=staging`, `APP_DOMAIN=v2.plan-estimate.pl`, свои `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `DATA_KEK` (новые, сгенерировать `openssl rand -base64 32`), `AUTH_PROVIDER=password`, R2 бакет `plan-estimate-v2`, `PHOTO_UPLOADS_ENABLED=true`, `CALENDAR_DISPATCHER_ENABLED=false`, пустой `TELEGRAM_BOT_TOKEN`.

### 4.6. Скрипт выкладки стенда `docs/V2_STAGING_DEPLOY_RU.sh`

По образцу `docs/AC7_DEPLOY_RU.sh`, но проще (данные стенда — демо):

* G0: папка `~/plan-estimate-v2` на ветке `v2`; `.env.staging` с правами `600`, без заглушек (значения не печатать); сеть `pe-v2-edge` существует; Caddy прода здоров.
* G1: `docker compose -f docker-compose.v2.yml --env-file .env.staging -p pe-v2 build`.
* G2: `up -d`; `https://v2.plan-estimate.pl/api/health` через Cloudflare отвечает (с сервисным токеном Access или из VM напрямую `curl -H 'Host: v2.plan-estimate.pl' https://localhost/api/health -k`).
* G3: **прод не изменился**: `https://plan-estimate.pl/api/health` здоров, контейнеры прода не пересоздавались (сравнить `StartedAt` до и после).

---

## 5. Первый запуск (владелец на VM, по шагам, каждый — по «да»)

```bash
# 1. Папка стенда (прод не трогаем)
cd ~ && git clone <адрес репозитория> plan-estimate-v2
cd ~/plan-estimate-v2 && git checkout v2

# 2. Настройки стенда
cp .env.staging.example .env.staging && chmod 600 .env.staging
nano .env.staging            # новые пароли и ключи, R2 стенда

# 3. Сеть между Caddy прода и стендом
docker network create pe-v2-edge
sudo ~/plan-estimate/ops/imds-guard/pe-imds-guard.sh status

# 4. Стенд
docker compose -f docker-compose.v2.yml --env-file .env.staging -p pe-v2 up -d --build

# 5. Прод: Caddy с блоком стенда (только Caddy, остальное не пересоздаётся)
cd ~/plan-estimate && git pull --ff-only     # после слияния изменений V2-0 в main
mkdir -p caddy-sites && cp ~/plan-estimate-v2/caddy-sites/v2.caddy.example caddy-sites/v2.caddy
docker compose -f docker-compose.prod.yml --env-file .env.production -p plan-estimate up -d --no-deps caddy

# 6. Проверки
curl -fsS https://plan-estimate.pl/api/health
# v2 — из браузера после входа через Cloudflare Access
```

## 6. Как откатить

* Стенд целиком: `docker compose -f docker-compose.v2.yml -p pe-v2 down` (данные стенда остаются в томе; `down -v` удалит их — только по отдельному «да»).
* Caddy прода: удалить `caddy-sites/v2.caddy` и перезапустить только Caddy — строка `import` без файлов ничего не делает (проверить `caddy validate` до перезапуска).
* DNS: удалить запись `v2` в Cloudflare.

## 7. Правила стенда

1. **Никаких настоящих данных клиентов** (RODO). Только `seed-demo` и тестовые клиенты. Исключение — репетиция R-1…R-3 в отдельной базе, удаляется сразу после.
2. Ключи и пароли стенда **никогда не совпадают** с продом.
3. Стенд можно пересоздать в любой момент; бэкапы стенда не нужны.
4. `noindex` в заголовках и Cloudflare Access — стенд не попадает в поиск и не открыт чужим.
