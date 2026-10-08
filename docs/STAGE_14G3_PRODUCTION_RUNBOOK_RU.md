# Stage 14G.3 — production: миграция `0035_photo_annotations`, метки на фото (14G.1 + 14G.2) и компактные кнопки (14H.4)

Порядок и правила — как в `STAGE_14F4_PRODUCTION_RUNBOOK_RU.md` и `STAGE_14H3_PRODUCTION_RUNBOOK_RU.md`, раздел 69b `PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md`. Каждый шаг ждёт вашего явного «да»; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне. Секреты в чат не присылайте (ключи только в виде маски, ссылки на фото не пересылайте). «ВОРОТА» = стоп до вашего ответа.

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }   # в каждом новом сеансе SSH
```

## 1. Что выкладывается

| Часть | Изменение | Риск |
|---|---|---|
| **Миграция `0035_photo_annotations`** | новая **пустая** таблица `photo_annotations` (+ тип `photoannotationkind`, CHECK `0 ≤ x, y ≤ 1`, индекс); существующие таблицы не меняются | см. «ВОРОТА M» |
| Backend (6 файлов приложения + миграция) | `photos.py`, `exceptions.py`, `schemas/photo.py`, `models/__init__.py`, новые `models/photo_annotation.py`, `domain/services/photo_annotation_service.py`: API меток, `annotation_count` в списках, `annotations` в деталях фото | низкий: аддитивно, существующие маршруты сохраняют ответ (добавлены поля) |
| Frontend | метки на фото (просмотрщик, полный экран, значок на плитке), 14H.4: компактные кнопки «Сделать фото / Из галереи» | низкий |
| Compose / Caddy / Dockerfile / зависимости / `app/backup` | **без изменений с выкладки 14H.3 (`ee1d086`)** — проверяется A1 | — |
| Образы бэкапа | **нужна пересборка** (шаг A6b): голова миграций меняется на `0035`, инструмент бэкапа требует совпадения головы с БД | средний при пропуске: бэкап останавливается безопасно (fail-closed) |

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
**PASS:** дерево чистое, ветка `stage-14`, коммит `ee1d086`; 4 контейнера `Up`/healthy; `alembic current` = `0034_finding_lineage`; health ok; свободно ≥ 5 ГБ; ключ приложения **`97bfe5…6dab`** (если `ab8171…048b` — остановиться и написать мне).

### A1 — что изменилось (только чтение, без `pull`)
```bash
git fetch origin stage-14
git diff --stat HEAD origin/stage-14 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt frontend/package.json frontend/package-lock.json backend/app/backup
git diff --name-only HEAD origin/stage-14 -- backend/alembic backend/app
```
**PASS:** первая команда пуста; вторая — ровно 7 файлов: `alembic/versions/0035_photo_annotations.py`, `app/api/v1/endpoints/photos.py`, `app/domain/exceptions.py`, `app/domain/services/photo_annotation_service.py`, `app/models/__init__.py`, `app/models/photo_annotation.py`, `app/schemas/photo.py`.

### A2 — бэкап перед миграцией *(рекомендую)* → ждёт «да, A2»
**Выполнять в отдельной SSH-сессии и закрыть её после `verify`.** Шаги `upload` / `verify` экспортируют `MEDIA_S3_*` бэкапа; в той же сессии `docker compose up` подставит их в backend вместо `.env.production` (так случилось на 14G.3: ключ приложения стал `ab8171…048b`; исправлено пересозданием в новой сессии, см. 72.5 основного runbook). Перед каждым `PC up` — новая сессия и `env | grep -c '^MEDIA_S3\|^BACKUP_'` = 0.
Схема меняется (новая таблица), поэтому рекомендую один прогон `db-dump` + `upload` + `verify` **существующими образами** (голова `0034` — они собраны на 14F.4 и до миграции подходят): раздел 72.3 основного runbook, шаги 2–4; перед ними загрузить **оба** файла (`. backup.env; . upload.env`). Последний проверенный запуск: `20261007T203639Z-bfab5242` (`ready_count=26`). **PASS:** `backup complete … ready_count=<число фото>`, `upload complete`, `verify ok`.

### A3 — получить код → ждёт «да, A3»
```bash
git pull --ff-only origin stage-14
git log --oneline -3
```
**PASS:** fast-forward; верхний коммит = `origin/stage-14`.

### A4 — конфигурация и сборка (старый production работает) → ждёт «да, A4»
```bash
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-14g
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-14g
PC build backend frontend 2>&1 | tail -n 15
```
**PASS:** `CONFIG-OK`; обе сборки без ошибок; контейнеры по-прежнему `Up`. *Ничего ещё не применено.*

### M0 — голова нового образа (только чтение) → ждёт «да, M0»
```bash
docker run --rm --entrypoint alembic plan-estimate-backend:latest heads
docker run --rm --entrypoint sh plan-estimate-backend:latest -c 'sed -n 1,60p /app/alembic/versions/0035_photo_annotations.py'
```
**PASS:** `0035_photo_annotations (head)`; файл миграции из нового образа совпадает с репозиторием. (Голову спрашиваем у **нового** образа; старый контейнер показал бы `0034`.)

### ВОРОТА M — миграция → ждёт вашего «да, миграция»
Перед ответом вы получите письменную оценку (раздел 3 ниже).

### A5 — применить backend (entrypoint сам выполнит `alembic upgrade head`)
```bash
PC up -d --no-deps backend
sleep 20
docker exec plan_estimate_backend alembic current
docker exec plan_estimate_backend alembic heads
docker logs plan_estimate_backend --tail 40
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from photo_annotations; select count(*) from photo_attachments;"'
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:])"
```
**PASS:** `env | grep -c '^MEDIA_S3\|^BACKUP_'` = 0 **до** `up` (новая сессия); `current` = `heads` = `0035_photo_annotations`; в логах нет ошибок; health ok (если не сразу — подождать 20 секунд); `photo_annotations` = **0** строк, `photo_attachments` — прежнее число; ключ приложения `97bfe5…6dab`, бакет `plan-estimate-media-prod`, endpoint `r2.cloudflarestorage.com` (команда проверки добавлена в A5: `print('бакет:', s.MEDIA_S3_BUCKET)` и endpoint).

### A5b — подписанная ссылка с чужого адреса (обязательно, урок 14F.4) → ждёт «да, A5b»
Как в runbook 14H.3: ссылку на миниатюру получить на VM и **вставить в локальный терминал компьютера** (не в SSH и не в чат):
```bash
docker exec -i plan_estimate_backend python - <<'PY'
from app.core.config import settings
from app.core.s3_media_storage import create_media_storage
s = create_media_storage(settings)
keys = sorted((o["LastModified"], o["Key"]) for o in s._get_client().list_objects_v2(Bucket=s._bucket, Prefix="photos/v1/", MaxKeys=300)["Contents"] if o["Key"].endswith("thumb.jpg"))
print(s._presign_sync(keys[-1][1], 900))
PY
```
На компьютере: `curl -sS -o /dev/null -D - "ССЫЛКА" | head -12`. **PASS:** `HTTP/1.1 200`, `Content-Type: image/jpeg`, в `CF-RAY` не `…-FRA`.

### A6 — применить frontend → ждёт «да, A6»
```bash
PC up -d --no-deps frontend
PC ps
curl -fsS https://plan-estimate.pl/api/health; echo
```
**PASS:** все контейнеры `Up`/healthy; health ok.

### A6b — пересобрать образы бэкапа под новую голову → ждёт «да, A6b»
Раздел 72.3 **шаг 1** (образы из `git archive` нового коммита), затем обновить `BACKUP_TOOL_COMMIT` в `~/backups/plan-estimate/db-backup/secrets/upload.env` на `git rev-parse origin/stage-14`. До этого шага бэкап падает безопасно (головы не совпадают). **PASS:** оба образа собрались; `BACKUP_TOOL_COMMIT` = новый хеш; затем один полный прогон `db-dump` → `upload` → `verify` подтверждает работу (`ready_count` прежний). Файл `upload.env` содержит секрет — в чат не присылать, печатать только маски.

### A7 — cache-busting кнопки меню Telegram (раздел 71) → ждёт «да, A7»
Команды как в A7 runbook 14H.3 (`V=$(git rev-parse --short HEAD)`, `setChatMenuButton` и `getChatMenuButton`; токен подставляется внутри команды и не печатается). **PASS:** оба ответа `"ok":true`, `?v=` = новый хеш. После этого полностью закройте и заново откройте Telegram.

### A8 — проверка на телефоне (владелец, 10 минут)
Откройте любое фото (например, в «Realizacja» или у стены) в просмотрщике.
1. **Кнопки (14H.4):** «Сделать фото / Из галереи» стоят в одну строку, не меньше 44 px; на 320–412 px текст не обрезается.
2. Под фото кнопка **«Добавить метку»** и «Метки: 0 из 10». Нажмите её (кнопка станет «Закончить добавление»), коснитесь фото: метка с номером 1 появляется **точно под пальцем**, открывается окно с полем подписи.
3. Введите подпись (например, «трещина у окна»), «Сохранить подпись» → окно закрылось; нажмите на метку: в окне видна подпись.
4. Поставьте несколько меток подряд (режим остаётся включённым); после 10-й режим выключается и появляется сообщение о лимите.
5. «Удалить метку» в окне метки: метка исчезает, номера остальных сдвигаются, счётчик уменьшается.
6. **Полный экран** (кнопка в углу фото): метки видны, увеличьте двумя пальцами — метки остаются на своих местах и **не увеличиваются**; кнопка вверху «Добавить метку» включает постановку, касание ставит метку сразу (без ожидания двойного касания).
7. Закройте просмотрщик: на плитке фото значок с числом меток; **общие счётчики фото** (объекта, помещения) не изменились.
8. Архив: заархивируйте фото с метками, откройте в архиве — метки видны, добавить / удалить нельзя; после «Przywróć» метки на месте.
9. То же фото, прикреплённое в другом месте (если есть), имеет **свои** метки.
10. PL и RU: подписи кнопок и окна влезают, горизонтальной прокрутки нет.

## 3. Оценка миграции (для ВОРОТ M)

- **Что делает:** `CREATE TYPE photoannotationkind`, `CREATE TABLE photo_annotations` (11 столбцов, внешний ключ на `photo_attachments` с `ON DELETE CASCADE`, три CHECK), `CREATE INDEX`. Существующие таблицы, строки и данные **не меняются**.
- **Блокировки:** создание таблицы и индекса на пустой таблице — миллисекунды; внешний ключ берёт короткую блокировку на `photo_attachments` (десятки строк) — незаметно. Всё идёт **одной транзакцией** (DDL в PostgreSQL транзакционный): при любой ошибке откат целиком, `alembic_version` остаётся `0034`.
- **Обратимость:** `downgrade` удаляет индекс, таблицу и тип, ничего другого (теряются только метки, фото не затрагиваются).
- **Совместимость со старым кодом:** старый backend таблицу не знает и ничего в неё не пишет; она ему не мешает. **Откат образа backend без отката миграции безопасен** (в отличие от 0034): метки просто не будут показаны. Новый frontend со старым backend не используется (порядок A5 → A6).
- **Бэкап:** рекомендую A2 до миграции; после A5 образы бэкапа надо пересобрать (A6b), иначе бэкап остановится безопасно.
- **Хранилище:** ключ приложения не меняется; A5b проверяет, что фото открываются с любого адреса.

## 4. Откат

| Ситуация | Действие |
|---|---|
| Backend не стартует после A5 | `docker logs plan_estimate_backend --tail 100`; миграция транзакционная — при ошибке версия осталась `0034`; вернуть образ: `docker tag plan-estimate-backend:pre-14g plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` |
| Backend работает, нужна отмена фич | образ `:pre-14g` как выше (миграция может остаться: старый код её не использует); полный возврат схемы — только по согласованию: `docker exec plan_estimate_backend alembic downgrade 0034_finding_lineage` **до** смены образа (теряются метки, если они уже есть) |
| Сломался frontend | `docker tag plan-estimate-frontend:pre-14g plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| Фото не открываются у телефона (403) | не откатывать: проверить ключ приложения (A0) и A5b, раздел 6 runbook 14F.4 |
| Бэкап после отката головы | работает только с образами, чья голова совпадает с БД |
| Любое сомнение с данными | остановиться, прислать вывод; `down -v` — **никогда** |

## 5. После завершения

Записываю в `docs/development-progress.md`: коммит, образы, ревизию БД, результаты A0–A8. Затем приёмка 14G (вместе с 14H.4) и решение о следующем этапе. Уборка: теги `:pre-14h`, `:pre-14h4`, `:pre-14g` и более старые `:pre-…` — через неделю (команды дам, выполняете вы).
