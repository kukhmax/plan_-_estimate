# Stage 14H.5 — production: индикаторы фото на строках «Realizacja» и «Badanie …» (backend: поле счётчиков; frontend), без миграции

Порядок и правила — как в `STAGE_14G6_PRODUCTION_RUNBOOK_RU.md`. Каждый шаг ждёт вашего явного «да»; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне. **Все шаги этого runbook — в чистой новой SSH-сессии** (здесь нет бэкапа; первая строка каждого блока проверяет, что лишних переменных 0).

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
```

## 1. Что выкладывается

| Часть | Изменение | Риск |
|---|---|---|
| Миграция | **нет**; `alembic current` остаётся `0036_photo_annotation_outline` | — |
| Backend (3 файла приложения) | `endpoints/photos.py`, `domain/services/photo_query_service.py`, `schemas/photo.py`: поле `inspection_surfaces` в `GET /photos/counts` (только чтение, одна дополнительная выборка по замечаниям и осмотрам) | низкий |
| Frontend | индикатор (камера и число) на строке «Realizacja» и на «Badanie ściany» / «Badanie sufitu» | низкий |
| Образы бэкапа | **пересборка не нужна** (голова миграций и код `app/backup` не меняются) | — |

Откат: миграции нет, образы `:pre-14h5` возвращаются в любой момент (раздел 4).

## 2. Шаги

### A0 — только чтение
```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
git status --short; git branch --show-current; git log --oneline -1
PC ps
docker exec plan_estimate_backend alembic current
curl -fsS https://plan-estimate.pl/api/health; echo
df -h / | tail -1
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET)"
```
**PASS:** `0` лишних переменных; дерево чистое, `stage-14`, коммит `5d36c77`; 4 контейнера `Up`; `alembic current` = `0036_photo_annotation_outline`; health ok; свободно ≥ 5 ГБ; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`.

### A1 — что изменилось (только чтение, без `pull`)
```bash
git fetch origin stage-14
git diff --stat HEAD origin/stage-14 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt frontend/package.json frontend/package-lock.json backend/app/backup backend/alembic
echo "--- файлы backend ---"
git diff --name-only HEAD origin/stage-14 -- backend/app
```
**PASS:** первая команда пуста; вторая — ровно 3 файла: `app/api/v1/endpoints/photos.py`, `app/domain/services/photo_query_service.py`, `app/schemas/photo.py`.

### A3 — получить код → «да, A3»
```bash
git pull --ff-only origin stage-14
git log --oneline -1
```
**PASS:** fast-forward; верхний коммит = `origin/stage-14`.

### A4 — конфигурация и сборка (старый production работает) → «да, A4»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-14h5
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-14h5
PC build backend frontend 2>&1 | tail -n 8
PC ps
```
**PASS:** `0` лишних переменных; `CONFIG-OK`; обе сборки без ошибок; контейнеры `Up`.

### A5 — применить backend → «да, A5» (миграции нет: ВОРОТА M не нужны)
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps backend
sleep 20
docker exec plan_estimate_backend alembic current
docker logs plan_estimate_backend --tail 20
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET); print('endpoint:', str(s.MEDIA_S3_ENDPOINT_URL).split('//')[-1].split('.')[-3:])"
```
**PASS:** `0` лишних переменных; `current` = `0036_photo_annotation_outline` (без строки `Running upgrade`); нет ошибок; health ok; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`, endpoint `r2`, `cloudflarestorage`, `com`.

### A6 — применить frontend → «да, A6»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps frontend
PC ps
curl -fsS https://plan-estimate.pl/api/health; echo
```
**PASS:** `0` лишних переменных; все контейнеры `Up`; health ok.

### A7 — кнопка меню Telegram → «да, A7»
```bash
V=$(git rev-parse --short HEAD); echo "версия кнопки: $V"
set -a; source .env.production; set +a
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${V}\"}}}"; echo
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#'; echo
unset TELEGRAM_BOT_TOKEN V
```
**PASS:** оба ответа `"ok":true`, `?v=` = новый хеш.

### A8 — проверка на телефоне (владелец, 5 минут)
Полностью закройте Telegram и откройте Mini App заново. **Нужны фото:** сделайте по одному фото в Realizacja у любой работы и в осмотре (обычное фото осмотра и/или фото к замечанию) на одной и той же стене.
1. Строка **«Realizacja»** этой стены: справа от подписи камера и число фото выполнения. У стены без таких фото индикатора нет.
2. Кнопка **«Badanie ściany»** (в «Opcje»): камера и число фото осмотра (осмотр + вопросы + замечания). То же у потолка («Badanie sufitu»); у пола кнопки осмотра нет.
3. **Общие счётчики** фото (объект, помещение, стена) эти фото не включают.
4. PL и RU, 320–412 px: на узкой кнопке индикатор уходит под подпись, если не помещается; подпись не режется и не накрывается; горизонтальной прокрутки нет.
5. Число растёт после новых фото (после возврата на экран стены).

## 3. Оценка риска
- **Данные:** миграции нет, записей не меняется; новое поле — только чтение (две дополнительные выборки: замечания и осмотры по найденным фото).
- **Совместимость:** старый frontend (в кэше WebView) игнорирует новое поле; новый frontend со старым backend не используется (порядок A5 → A6); если поле всё же отсутствует, индикатор просто не рисуется.
- **Хранилище:** ключ приложения не меняется; фото сейчас в системе мало, A5b (ссылка с чужого адреса) выполняется после первого нового фото, если не было сделано раньше.

## 4. Откат
| Ситуация | Действие |
|---|---|
| Backend не стартует после A5 | `docker logs plan_estimate_backend --tail 100`; `docker tag plan-estimate-backend:pre-14h5 plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` |
| Сломался frontend | `docker tag plan-estimate-frontend:pre-14h5 plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| Любое сомнение с данными | остановиться, прислать вывод; `down -v` — **никогда** |
