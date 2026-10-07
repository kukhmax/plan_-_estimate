# Stage 14H.3 — production: фото выполнения работ (backend 14H.1 + frontend 14H.2), без миграции

Порядок и правила — как в `STAGE_14F4_PRODUCTION_RUNBOOK_RU.md` и разделе 69b `PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md`. Каждый шаг ждёт вашего явного «да»; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне. Секреты в чат не присылайте (ключи только в виде маски, ссылки на фото не пересылайте).

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }   # в каждом новом сеансе SSH
```

## 1. Что выкладывается

| Часть | Изменение | Риск |
|---|---|---|
| **Миграция** | **нет**: схема `0032` уже содержит `WORK`; `alembic current` остаётся `0034_finding_lineage` | — |
| Backend (5 файлов приложения) | `photos.py`, `exceptions.py`, `photo_attachment_service.py`, `photo_query_service.py`, `schemas/photo.py`: контекст `WORK` (поверхность + `occurrence_key`, ключ должен быть текущим, иначе `409 WORK_OCCURRENCE_NOT_CURRENT`), фильтр списка, счётчики `works` / `work_surfaces`; в ответ добавлены поля `occurrence_key` и `price_item_id`; лимит скалярных полей загрузки остаётся 8 | низкий: аддитивно, существующие маршруты сохраняют ответ (добавлены только поля) |
| Frontend | кнопка фото и панель в карточке каждой работы Realizacja, блок «Фото прежних работ», категория по статусу работы | низкий |
| Compose / Caddy / Dockerfile / зависимости / `app/backup` | **без изменений с выкладки 14F.4 (`9ec1704`)** — проверяется A1 | — |
| Образы бэкапа | **пересборка не нужна**: голова миграций не меняется, код `app/backup` не менялся | — |

**Откат безопасен:** миграции нет, поэтому вернуть прежний образ можно в любой момент (раздел 4). Уже сделанные фото выполнения при этом остаются в базе и в R2; прежний backend их не показывает.

## 2. Шаги

### A0 — только чтение (состояние production)
```bash
git status --short; git branch --show-current; git log --oneline -1
PC ps
docker inspect -f '{{.Name}}  {{.Image}}  {{.Created}}' plan_estimate_backend plan_estimate_frontend plan_estimate_caddy plan_estimate_postgres
docker exec plan_estimate_backend alembic current
curl -fsS https://plan-estimate.pl/api/health; echo
df -h / | tail -1
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:], len(k))"
```
**PASS:** дерево чистое, ветка `stage-14`; 4 контейнера `Up`/healthy; `alembic current` = `0034_finding_lineage`; health ok; свободно ≥ 5 ГБ; ключ приложения **`97bfe5…6dab`** (если `ab8171…048b` — это ключ бэкапов, его в приложении быть не должно: остановиться и написать мне, см. раздел 6 runbook 14F.4).

### A1 — что изменилось (только чтение, без `pull`)
```bash
git fetch origin stage-14
git diff --stat HEAD origin/stage-14 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt frontend/package.json frontend/package-lock.json backend/alembic backend/app/backup
git diff --name-only HEAD origin/stage-14 -- backend/app
```
**PASS:** первая команда пуста (деплойные файлы, миграции и инструмент бэкапа не менялись); вторая — ровно 5 файлов: `api/v1/endpoints/photos.py`, `domain/exceptions.py`, `domain/services/photo_attachment_service.py`, `domain/services/photo_query_service.py`, `schemas/photo.py`.

### A2 — бэкап перед выкладкой *(по желанию)* → ждёт «да, A2»
Схема не меняется, поэтому бэкап не обязателен. Последний проверенный запуск: `20261007T203639Z-bfab5242` (`ready_count=26`). Если хотите свежий, раздел 72.3 основного runbook, шаги 2–4 (db-dump → upload → verify).

### A3 — получить код → ждёт «да, A3»
```bash
git pull --ff-only origin stage-14
git log --oneline -3
```
**PASS:** fast-forward; верхний коммит = `origin/stage-14`.

### A4 — конфигурация и сборка (старый production работает) → ждёт «да, A4»
```bash
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-14h
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-14h
PC build backend frontend 2>&1 | tail -n 15
```
**PASS:** `CONFIG-OK`; обе сборки без ошибок; контейнеры по-прежнему `Up`. *Ничего ещё не применено.*

### A5 — применить backend → ждёт «да, A5»
```bash
PC up -d --no-deps backend
sleep 20
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_backend alembic current
docker logs plan_estimate_backend --tail 30
docker exec plan_estimate_backend python -c "from app.api.v1.endpoints import photos as p; print('лимит полей', p.MAX_FIELDS, '| occurrence_key принимается:', 'occurrence_key' in p.SCALAR_FIELDS)"
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:])"
```
**PASS:** health ok (если не сразу — подождать 20 секунд: бывает гонка запуска); `alembic current` = `0034_finding_lineage` (голова не меняется, миграция не применялась); в логах нет ошибок; `лимит полей 8 | occurrence_key принимается: True`; ключ приложения `97bfe5…6dab`.

### A5b — подписанная ссылка с чужого адреса (обязательно, урок 14F.4) → ждёт «да, A5b»
Фото должны открываться не только с сервера. Ссылку получить на VM и **вставить в локальный терминал компьютера** (не в сессию SSH и не в чат):
```bash
docker exec -i plan_estimate_backend python - <<'PY'
from app.core.config import settings
from app.core.s3_media_storage import create_media_storage
s = create_media_storage(settings)
keys = sorted((o["LastModified"], o["Key"]) for o in s._get_client().list_objects_v2(Bucket=s._bucket, Prefix="photos/v1/", MaxKeys=300)["Contents"] if o["Key"].endswith("thumb.jpg"))
print(s._presign_sync(keys[-1][1], 900))
PY
```
На компьютере: `curl -sS -o /dev/null -D - "ССЫЛКА" | head -12`. **PASS:** `HTTP/1.1 200`, `Content-Type: image/jpeg`, в `CF-RAY` не `…-FRA`. Ссылка действует 15 минут.

### A6 — применить frontend → ждёт «да, A6»
```bash
PC up -d --no-deps frontend
PC ps
curl -fsS https://plan-estimate.pl/api/health; echo
```
**PASS:** все контейнеры `Up`/healthy; health ok.

### A7 — cache-busting кнопки меню Telegram (раздел 71) → ждёт «да, A7»
```bash
cd ~/apps/plan_-_estimate
V=$(git rev-parse --short HEAD); echo "версия кнопки: $V"
set -a; source .env.production; set +a
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${V}\"}}}"; echo
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#'; echo
unset TELEGRAM_BOT_TOKEN V
```
Токен бота подставляется внутри команды и не печатается. **PASS:** оба ответа `"ok":true`, во втором `?v=` равен новому короткому хешу.

### A8 — проверка на телефоне (владелец, 10 минут)
Полностью закройте Telegram и откройте Mini App заново. Откройте помещение → стену → **«Realizacja»** (в RU: «Выполнение»; экран выполнения работ) у поверхности с планом работ.
1. У **каждой** работы есть кнопка фото со счётчиком (у ещё не начатой тоже); по нажатию открывается панель с «Zrób zdjęcie / Z galerii».
2. Работа «Zaplanowano»: снимите фото → в плитке метка **«Przed» (RU «До»)**, счётчик +1; статус работы **не изменился** (фото до работы не требует начала).
3. Нажмите «Rozpocznij» → новое фото получает метку **«W trakcie» (RU «В процессе»)**; «Oznacz jako wykonane» → новое фото получает **«Po» (RU «После»)**. Категорию можно сменить в просмотрщике.
4. Фото увеличивается в просмотрщике (зум работает); подпись называет поверхность и операцию.
5. **Общие фото объекта и помещения не выросли** (фото выполнения живут только в Realizacja).
6. Измените план так, чтобы одна работа с фото исчезла (проще всего у работы «Zaplanowano»; для начатой / завершённой появится окно подтверждения) → вернитесь в Realizacja: внизу блок **«Zdjęcia dawnych prac»** с числом фото и подписью прежней операции; добавьте ту же позицию прайса снова — у новой работы **нет** старых фото.
7. 320–412 px, PL и RU: кнопки не меньше 44 px, подписи не обрезаются, нет горизонтальной прокрутки.

## 3. Оценка риска

- **Данные:** схема и существующие строки не меняются; новые строки `photo_attachments` с `context = 'WORK'` создаются только при загрузке из Realizacja.
- **Совместимость:** старый frontend (в кэше WebView) продолжает работать с новым backend (ответ только дополнен полями); новый frontend со старым backend не используется (выкладка по порядку A5 → A6).
- **Хранилище:** ключ приложения не меняется (`97bfe5…6dab`); проверка A5b гарантирует, что фото открываются с любого адреса.

## 4. Откат

| Ситуация | Действие |
|---|---|
| Backend не стартует после A5 | `docker logs plan_estimate_backend --tail 100`; вернуть образ: `docker tag plan-estimate-backend:pre-14h plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` |
| Сломался frontend | `docker tag plan-estimate-frontend:pre-14h plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| Миграция | не применялась, откатывать нечего |
| Фото не открываются у телефона (403) | не откатывать: проверить ключ приложения (A0) и A5b, см. раздел 6 runbook 14F.4 |
| Любое сомнение с данными | остановиться, прислать вывод; `down -v` — **никогда** |

## 5. После завершения

Записываю в `docs/development-progress.md`: коммит, образы, результаты A0–A8. Затем приёмка 14H и решение о следующем этапе. Уборка: теги `:pre-14h`, `:pre-14f4` и более старые `:pre-…` — через неделю (команды дам, выполняете вы).
