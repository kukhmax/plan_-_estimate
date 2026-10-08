# Stage 14G.6 — production: миграция `0036_photo_annotation_outline`, обводка дефекта на фото (14G.4 + 14G.5)

Порядок и правила — как в `STAGE_14G3_PRODUCTION_RUNBOOK_RU.md` (там же разбор ошибки с сессиями) и разделе 69b `PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md`. Каждый шаг ждёт вашего явного «да»; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне. Секреты в чат не присылайте. «ВОРОТА» = стоп до вашего ответа.

> **Главное правило (урок 14G.3):** бэкап (шаги A2 и A6b) — в **одной** SSH-сессии, `docker compose` (A5, A6) — в **другой, новой** и до любого бэкапа. Переменные `MEDIA_S3_*` бэкапа в оболочке подменяют настройки приложения при `PC up`.

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }   # в каждом новом сеансе SSH
```

## 1. Что выкладывается

| Часть | Изменение | Риск |
|---|---|---|
| **Миграция `0036_photo_annotation_outline`** | одна **nullable** колонка `photo_annotations.outline` (JSON); существующие строки получают `NULL`, другие таблицы не меняются | см. «ВОРОТА M» |
| Backend (4 файла приложения + миграция) | `api/v1/endpoints/photos.py`, `domain/services/photo_annotation_service.py`, `models/photo_annotation.py`, `schemas/photo.py`: поле `outline` у метки, `PATCH` метки принимает `label` и/или `outline`, `outline_max_points` в деталях фото | низкий: аддитивно, существующие ответы сохраняют поля (добавлено `outline`) |
| Frontend | в окне метки «Obrysuj wadę / Обвести дефект»: рисование контура пальцем на полном экране, контур виден во всех видах, «Usuń obrys / Удалить контур» | низкий |
| Compose / Caddy / Dockerfile / зависимости / `app/backup` | **без изменений с выкладки 14G.3 (`063b868`)** — проверяется A1 | — |
| Образы бэкапа | **нужна пересборка** (A6b): голова меняется на `0036` | средний при пропуске: бэкап остановится безопасно |

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
**PASS:** дерево чистое, ветка `stage-14`, коммит `063b868`; 4 контейнера `Up`/healthy; `alembic current` = `0035_photo_annotations`; health ok; свободно ≥ 5 ГБ; ключ приложения **`97bfe5…6dab`** (если `ab8171…048b` — остановиться и написать мне).

### A1 — что изменилось (только чтение, без `pull`)
```bash
git fetch origin stage-14
git diff --stat HEAD origin/stage-14 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt frontend/package.json frontend/package-lock.json backend/app/backup
git diff --name-only HEAD origin/stage-14 -- backend/alembic backend/app
```
**PASS:** первая команда пуста; вторая — ровно 5 файлов: `alembic/versions/0036_photo_annotation_outline.py`, `app/api/v1/endpoints/photos.py`, `app/domain/services/photo_annotation_service.py`, `app/models/photo_annotation.py`, `app/schemas/photo.py`.

### A2 — бэкап перед миграцией *(рекомендую)* → ждёт «да, A2»
**Выполнять в отдельной SSH-сессии и закрыть её после `verify`.** Шаги `upload` / `verify` экспортируют `MEDIA_S3_*` бэкапа; в той же сессии `docker compose up` подставит их в backend вместо `.env.production` (так случилось на 14G.3: ключ приложения стал `ab8171…048b`; исправлено пересозданием в новой сессии, см. 72.5 основного runbook). Перед каждым `PC up` — новая сессия и `env | grep -c '^MEDIA_S3\|^BACKUP_'` = 0.
Схема меняется (новая колонка), поэтому рекомендую один прогон `db-dump` + `upload` + `verify` **существующими образами** (голова `0035` — они собраны на A6b 14G.3 и до миграции подходят): раздел 72.3 основного runbook, шаги 2–4; перед ними загрузить **оба** файла (`. backup.env; . upload.env`). Последний проверенный запуск: `20261008T081841Z-588362c2` (`ready_count=31`). **PASS:** `backup complete … ready_count=<число фото>`, `upload complete`, `verify ok`.

### A3 — получить код → ждёт «да, A3»
```bash
git pull --ff-only origin stage-14
git log --oneline -3
```
**PASS:** fast-forward; верхний коммит = `origin/stage-14`.

### A4 — конфигурация и сборка (старый production работает) → ждёт «да, A4»
```bash
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-14g6
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-14g6
PC build backend frontend 2>&1 | tail -n 15
```
**PASS:** `CONFIG-OK`; обе сборки без ошибок; контейнеры по-прежнему `Up`. *Ничего ещё не применено.*

### M0 — голова нового образа (только чтение) → ждёт «да, M0»
```bash
docker run --rm --entrypoint alembic plan-estimate-backend:latest heads
docker run --rm --entrypoint sh plan-estimate-backend:latest -c 'sed -n 1,60p /app/alembic/versions/0036_photo_annotation_outline.py'
```
**PASS:** `0036_photo_annotation_outline (head)`; файл миграции из нового образа совпадает с репозиторием (колонка `outline` JSON nullable, `downgrade` удаляет её). (Голову спрашиваем у **нового** образа; старый контейнер показал бы `0035`.)

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
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*), count(outline) from photo_annotations; select count(*) from photo_attachments;"'
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:])"
```
**PASS:** `env | grep -c '^MEDIA_S3\|^BACKUP_'` = 0 **до** `up` (новая сессия); `current` = `heads` = `0036_photo_annotation_outline`; в логах нет ошибок; health ok (если не сразу — подождать 20 секунд); число меток `photo_annotations` прежнее (после проверки 14G.3 это метки владельца, как были), `count(outline)` = **0** (контуров ещё нет); ключ приложения `97bfe5…6dab`, бакет `plan-estimate-media-prod`, endpoint `r2.cloudflarestorage.com` (команда проверки добавлена в A5: `print('бакет:', s.MEDIA_S3_BUCKET)` и endpoint).

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
Полностью закройте Telegram и откройте Mini App заново. Откройте фото с меткой (или поставьте метку).
1. Нажмите на метку → окно метки. Внизу кнопка **«Obrysuj wadę» («Обвести дефект»)**.
2. Нажмите её: окно закрывается, открывается **полный экран** с подсказкой «Obrysuj wadę palcem…» и кнопкой «Anuluj». Метка подсвечена.
3. **Обведите дефект пальцем** одним движением. Пока палец на экране, линия рисуется под пальцем; отпустили — контур сохранён, режим рисования выключился, контур остаётся на фото.
4. Закройте полный экран: контур виден и в обычном просмотре, **точно на том же месте** относительно фото. Линия тонкая, красная с белой подложкой.
5. Увеличьте двумя пальцами на полном экране: контур остаётся на месте и **не утолщается**. Двумя пальцами рисование не начинается (только масштаб).
6. Попробуйте «Obrysuj wadę» и просто коснитесь фото (без движения): сообщение «Obrys jest za krótki», режим рисования остаётся; «Anuluj» выходит без сохранения.
7. Откройте окно метки снова: теперь кнопки **«Obrysuj ponownie»** (нарисовать заново, прежний контур заменяется) и **«Usuń obrys»** (контур исчезает, метка и её подпись остаются).
8. У метки с контуром подпись по-прежнему показывается в окне по нажатию; «Usuń znacznik» удаляет метку вместе с контуром.
9. Закройте и заново откройте приложение: контур на месте. Общие счётчики фото не изменились.
10. Архив: у архивного фото контуры видны, кнопок рисования нет; после «Przywróć» контур на месте.
11. PL и RU: кнопки окна влезают, не меньше 44 px, горизонтальной прокрутки нет (окно метки с пятью кнопками на 320 px прокручивается внутри).

## 3. Оценка миграции (для ВОРОТ M)

- **Что делает:** `ALTER TABLE photo_annotations ADD COLUMN outline JSON NULL`. Без значения по умолчанию, поэтому PostgreSQL не переписывает таблицу: операция метаданных, миллисекунды даже на большой таблице; сейчас в таблице только метки владельца. Все существующие метки получают `NULL` (= «контура нет»). Другие таблицы, фото и данные не меняются.
- **Блокировки:** короткая эксклюзивная блокировка таблицы `photo_annotations` на время `ALTER`; одна транзакция (DDL в PostgreSQL транзакционный) — при ошибке откат целиком, `alembic_version` остаётся `0035`.
- **Обратимость:** `downgrade` удаляет колонку и больше ничего (теряются только контуры; метки, подписи и фото остаются).
- **Совместимость со старым кодом:** старый backend колонки не знает и при чтении метки просто не отдаёт `outline`; запись метки (INSERT без `outline`) работает (колонка nullable). Откат образа backend без отката миграции безопасен.
- **Бэкап:** рекомендую A2 до миграции (образы бэкапа на голове `0035` до миграции подходят); после A5 образы бэкапа надо пересобрать (A6b), иначе бэкап остановится безопасно.
- **Хранилище:** ключ приложения не меняется; A5b проверяет, что фото открываются с любого адреса.

## 4. Откат

| Ситуация | Действие |
|---|---|
| Backend не стартует после A5 | `docker logs plan_estimate_backend --tail 100`; миграция транзакционная — при ошибке версия осталась `0035`; вернуть образ: `docker tag plan-estimate-backend:pre-14g6 plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` |
| Backend работает, нужна отмена фич | образ `:pre-14g6` как выше (миграция может остаться: старый код её не использует); полный возврат схемы — только по согласованию: `docker exec plan_estimate_backend alembic downgrade 0035_photo_annotations` **до** смены образа (теряются метки, если они уже есть) |
| Сломался frontend | `docker tag plan-estimate-frontend:pre-14g6 plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| Фото не открываются у телефона (403) | не откатывать: проверить ключ приложения (A0) и A5b, раздел 6 runbook 14F.4 |
| Бэкап после отката головы | работает только с образами, чья голова совпадает с БД |
| Любое сомнение с данными | остановиться, прислать вывод; `down -v` — **никогда** |

## 5. После завершения

Записываю в `docs/development-progress.md`: коммит, образы, ревизию БД, результаты A0–A8. Затем приёмка 14G (метки и обводка) и 14H и решение о следующем этапе. Уборка: теги `:pre-14h`, `:pre-14g`, `:pre-14g6` и более старые `:pre-…` — через неделю (команды дам, выполняете вы).
