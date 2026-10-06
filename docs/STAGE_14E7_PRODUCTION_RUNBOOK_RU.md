# Stage 14E.7 — выкладка фото на production и контролируемое включение (runbook владельца)

Документ ведёт владельца по двум фазам. **Фаза A** выкладывает всё сделанное в 14E.2–14E.6 на production, **загрузка фото остаётся выключенной**. **Фаза B** — отдельное решение:
включение загрузки для первых реальных фото и проверка всей цепочки на настоящих данных.

> **Правила (CLAUDE.md, неизменные).** Каждый шаг на production — отдельное явное «да» владельца: SSH, `git pull`, `docker build`, `docker up`, миграция, любое изменение данных.
> Команды выполняете **вы** на VM и присылаете вывод; я его разбираю и говорю PASS/FAIL. Секреты (`.env.production`, ключи R2, токены) **не** присылайте в чат и не печатайте.
> Никогда `docker compose … down -v`. Локальный Docker — только если вы сами решили; production — только через каноническую команду (раздел 1).

## 1. Каноническая команда и исходное состояние

Везде ниже `PC` означает:

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }   # объявить в каждом новом сеансе SSH
```

Исходное состояние production (из журнала; **подтверждается шагом A0**, а не принимается на веру):

| Что | Значение |
|---|---|
| Ветка/каталог | `~/apps/plan_-_estimate`, ветка `stage-14`, чистое дерево; последний известный коммит `68a06d5` (в дерево он попал при 14D.6, **контейнеры собраны раньше**) |
| Backend | образ из 14C.7 (`sha256:33bb27b7…`), БД на `0032_photo_attachments` |
| Фото | `MEDIA_STORAGE_BACKEND=s3` (R2 `r2-primary`, бакет `plan-estimate-media-prod`), **`PHOTO_UPLOADS_ENABLED=false`** |
| Frontend | прежний (интерфейса фото на production ещё нет) |
| Caddy | правило потолка 27 МБ на маршрут загрузки уже выложено в 14C.7 |

## 2. Что именно выкладывается

| Часть | Изменение | Риск |
|---|---|---|
| Backend | 14E.2: счётчики фото, поле `capture_source`; 14E.6: `room_totals`, фильтр `in_room_id` | низкий: читающие маршруты и необязательное поле |
| **Миграция `0033_photo_capture_source`** | одна колонка `photo_assets.capture_source` (nullable, без значения по умолчанию) + CHECK `CAMERA`/`GALLERY`; существующие строки не переписываются, другие таблицы не затрагиваются | **аддитивная, обратимая** (`downgrade` = DROP CONSTRAINT + DROP COLUMN); старый код колонку просто не видит. На `photo_assets` сейчас 0 строк, блокировка мгновенная |
| Frontend | интерфейс фото (кнопки, списки, просмотрщик, очередь); при выключенной загрузке показывает нейтральную заметку без кнопок | низкий |
| Caddy / Compose | **ожидается без изменений** — проверяется шагом A1 | — |

## 3. Фаза A — выкладка с выключенной загрузкой

Порядок следует разделу 69b `PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md` (миграция + сборка до остановки старого). Слово «ВОРОТА» = стоп до вашего ответа.

### A0 — только чтение (состояние production)

Ничего не меняет. Нужен только SSH-доступ; присылайте вывод целиком (секретные значения в нём не печатаются).

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }   # функция нужна в каждом новом сеансе SSH
git status --short; git branch --show-current; git log --oneline -1
PC ps
docker inspect -f '{{.Name}}  {{.Image}}  {{.Created}}' plan_estimate_backend plan_estimate_frontend plan_estimate_caddy plan_estimate_postgres
docker exec plan_estimate_backend alembic current
curl -fsS https://plan-estimate.pl/api/health; echo
df -h / | tail -1
grep -E '^(MEDIA_STORAGE_BACKEND|MEDIA_STORAGE_NAME|PHOTO_UPLOADS_ENABLED)=' .env.production
awk -F= '/^MEDIA_S3_/{print $1"="($2==""?"<empty>":"<set>")}' .env.production
```

**PASS:** дерево чистое; 4 контейнера `Up`/healthy; `alembic current` = `0032_photo_attachments`; health `{"status":"ok"}`; на диске ≥ 5 ГБ свободно;
`MEDIA_STORAGE_BACKEND=s3`, `PHOTO_UPLOADS_ENABLED=false`; все пять `MEDIA_S3_*` — `<set>`.

### A1 — что изменилось с последней выкладки (только чтение, без `pull`)

```bash
git fetch origin stage-14
git log --oneline HEAD..origin/stage-14 | wc -l
git log --oneline -1 origin/stage-14
git diff --stat 8c53e58 origin/stage-14 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/entrypoint.sh backend/requirements.txt frontend/Dockerfile.prod frontend/nginx.conf
git show origin/stage-14:backend/alembic/versions/0033_photo_capture_source.py | sed -n 1,40p
```

(`8c53e58` — коммит, из которого собран текущий production-backend: закрепления зависимостей из 14C.7 и маршрут Caddy уже в нём.)
**PASS:** в списке нет изменений в `backend/Dockerfile`, `backend/entrypoint.sh`, `backend/requirements.txt`, `frontend/Dockerfile.prod`, `frontend/nginx.conf`, `Caddyfile`.
Для `docker-compose.prod.yml` ожидаются **только** добавленные сервисы `backup` / `backup-upload` (profile-сервисы 14D.6a, обычным `up` не запускаются). Любое другое изменение я назову до продолжения.

> **После A0 и A1 я выдаю оценку миграции** (текущая ревизия, ожидаемая голова, характер, рекомендация по бэкапу) — это условие воротам ниже.

### A2 — бэкап перед выкладкой *(рекомендую)*  → ждёт «да, A2»

Миграция аддитивная и обратимая, но данных пока немного, а процедура проверена, поэтому **рекомендую** один прогон `db-dump` + `upload` (раздел 72.3 шаги 2–3; verify по желанию).
Образы бэкапа на VM уже есть; **до A5 их не пересобирать** — они собраны из кода с головой `0032`, а инструмент бэкапа требует точного совпадения ревизии БД с головой своего образа (политика v1, без обхода). **PASS:** `backup complete: run_id=… ready_count=0`, затем `upload complete: …` (оба exit 0). Можно пропустить осознанно: тогда напишите «A2 пропускаем».

### A3 — получить код  → ждёт «да, A3»

```bash
git status --short            # должно быть пусто
git pull --ff-only origin stage-14
git log --oneline -3          # сверить хеш с A1
```

**PASS:** fast-forward без конфликтов, верхний коммит = `origin/stage-14` из A1.

### A4 — проверка конфигурации и сборка (старый production продолжает работать)  → ждёт «да, A4»

```bash
PC config --quiet && echo CONFIG-OK
# точка отката: запомнить образы, которые сейчас работают
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-14e7
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-14e7
PC build backend frontend 2>&1 | tail -n 15
```

**PASS:** `CONFIG-OK`; обе сборки завершились без ошибок; контейнеры по-прежнему `Up` (`PC ps`). *Ничего ещё не применено.*

### ВОРОТА M — миграция  → ждёт вашего явного «да, миграция»

Перед ответом вы получите от меня письменную оценку: текущая ревизия БД (из A0), ожидаемая голова `0033_photo_capture_source`, характер (аддитивная), блокировка, откат, рекомендация по бэкапу (A2).

### A5 — применить backend (entrypoint сам выполнит `alembic upgrade head`)

```bash
PC up -d backend
docker exec plan_estimate_backend alembic current
docker exec plan_estimate_backend alembic heads
docker logs plan_estimate_backend --tail 40
docker exec plan_estimate_backend curl -fsS http://localhost:8000/api/health; echo
```

**PASS:** `current` и `heads` совпадают и равны `0033_photo_capture_source`; в логах нет ошибок; health ok. **Если нет — стоп, ничего дальше, присылайте логи** (откат — раздел 5).

> **Не** запускайте `alembic heads` в *старом* контейнере до пересоздания — он покажет старую голову (раздел 57a runbook).

### A6 — применить frontend  → ждёт «да, A6»

```bash
PC up -d frontend
PC ps
curl -fsS https://plan-estimate.pl/api/health; echo
curl -sI https://plan-estimate.pl | head -n 3
```

Caddy не пересоздаётся, если A1 не показал изменений его файлов (иначе я дам отдельную команду). **PASS:** все контейнеры `Up`/healthy; публичный health ok; главная отвечает 200.

### A6b — пересобрать образы бэкапа под новую голову  → ждёт «да, A6b»

Инструмент бэкапа сверяет ревизию БД с головой Alembic **своего образа** и при расхождении завершается ошибкой (fail-closed). После миграции `0033` старые образы бэкапа работать перестанут — это ожидаемо и безопасно, но бэкап надо вернуть в строй до фазы B.
Выполнить раздел 72.3 **шаг 1** (образы из `git archive` нового коммита), затем обновить `BACKUP_TOOL_COMMIT` в `~/backups/plan-estimate/db-backup/secrets/upload.env` на хеш нового коммита (`git rev-parse origin/stage-14`; значение не секретное, файл остаётся 0600).
**PASS:** оба образа собрались; `grep '^BACKUP_TOOL_COMMIT=' …/upload.env` = новый хеш. Проверка работы самого бэкапа — в B0 (в фазе A отдельный прогон не требуется).

### A7 — cache-busting кнопки меню Telegram (раздел 71 runbook)  → ждёт «да, A7»

Короткий SHA: `git rev-parse --short HEAD`; команда `setChatMenuButton` из раздела 71 с `?v=<sha>` (токен подставляется внутри команды и не печатается), затем `getChatMenuButton`.
**PASS:** в ответе новый URL с `?v=<sha>`.

### A8 — проверка на телефоне в настоящем Telegram (владелец, 5 минут)

Закройте Mini App полностью и откройте заново по кнопке меню. Проверьте:

| № | Проверка | Ожидание |
|---|---|---|
| 1 | Откройте объект | Есть карточка **«Zdjęcia obiektu»** со счётчиком **0** (фото ещё нет) |
| 2 | Нажмите кнопку фото в ней | Список пуст, подсказка про добавление; **кнопок «Zrób zdjęcie» / «Z galerii» нет** |
| 3 | Откройте комнату → «Zdjęcia pomieszczenia»; стену, пол, потолок | У поверхностей есть кнопка фото; при раскрытии — заметка «Dodawanie zdjęć jest obecnie wyłączone», кнопок нет |
| 4 | Обычная работа: помещения, стены, проёмы, расчёты, смета | Всё работает как раньше; цифры не изменились |
| 5 | Светлая и тёмная тема, PL и RU | Тексты читаются, кнопки не обрезаются |
| 6 | Кнопка «Назад» Telegram | Возвращает на уровень выше, как раньше |

**PASS фазы A:** A5 PASS + A6 PASS + A8 1–6 PASS. Тогда фаза A закрыта: на production новый код и `0033`, загрузка выключена. Результат я записываю в журнал.

## 4. Фаза B — контролируемое включение загрузки (отдельное решение)

### ВОРОТА D10 — периодичность бэкапов (решить до B0)

Расписания нет: бэкап свеж настолько, насколько свежий последний ручной запуск. Варианты (в 14E.1 они были записаны как открытые):

| Вариант | Что это | Плюс / минус |
|---|---|---|
| **A. Вручную перед каждым выездом и после рабочего дня** (раздел 72.3, ~5 мин) | пока вы сами запускаете | просто, без новой автоматизации; зависит от дисциплины |
| B. Ночной таймер на VM, N копий | systemd-таймер, отдельный небольшой этап | RPO ≈ сутки без вашего участия; нужен новый код/настройка и ретеншн |
| **C. Сначала A, таймер позже** (рекомендую) | на первую-две недели используем A, по реальному опыту решаем про B | не блокирует включение; не вводит автоматизацию до понимания нагрузки |

### B0 — свежий бэкап непосредственно перед включением  → ждёт «да, B0»

Раздел 72.3 шаги 2–4 (`db-dump` → `upload` → `verify` с VM) на образах из A6b. **PASS:** `backup complete …`, `upload complete …`, `verify ok … mode=full`; `ready_count=0`.

### B1 — проверка настроек хранилища (чтение)

```bash
grep -E '^(MEDIA_STORAGE_BACKEND|MEDIA_STORAGE_NAME|PHOTO_UPLOADS_ENABLED|PHOTO_STORAGE_(WARNING|SOFT_CAP)_BYTES|PHOTO_MAX_)' .env.production
awk -F= '/^MEDIA_S3_/{print $1"="($2==""?"<empty>":"<set>")}' .env.production
```

**PASS:** значения лимитов по умолчанию (25 МБ / 8 ГБ / 10 ГБ) или осознанные; токен приложения для `plan-estimate-media-prod` — **чтение и запись** (это *не* токен бэкапа только для чтения; проверяется реальной загрузкой в B3).

### B2 — включить  → ждёт «да, включаем»

```bash
cp -p .env.production ~/env.production.pre-14e7        # копия с правами 0600; удалить после успешной приёмки
sed -i 's/^PHOTO_UPLOADS_ENABLED=.*/PHOTO_UPLOADS_ENABLED=true/' .env.production
grep -E '^PHOTO_UPLOADS_ENABLED=' .env.production      # = true
PC up -d --no-deps backend                             # пересоздаётся ТОЛЬКО backend
docker logs plan_estimate_backend --tail 30
docker exec plan_estimate_backend curl -fsS http://localhost:8000/api/health; echo
curl -fsS https://plan-estimate.pl/api/health; echo
```

**PASS:** backend пересоздан, health ok, в логах нет ошибок конфигурации (если хранилище настроено неверно, backend не стартует с понятной причиной).

### B3 — первые реальные фото с телефона (владелец)

| № | Действие | Ожидание |
|---|---|---|
| 1 | Откройте карточку **стены** → кнопка фото → **«Z galerii»** (1 JPEG) | Строка очереди с прогрессом → миниатюра; число на кнопке стены +1; подпись `Salon → Ściana 1 → дата (время) · dodane z galerii` |
| 2 | То же с **«Zrób zdjęcie»** (камера) | Открывается камера; фото грузится; подпись `… · zrobione w aplikacji` |
| 3 | **Podłoga** и **Sufit**: по одному фото | Подписи `… → Podłoga → …`, `… → Sufit → …` |
| 4 | «Zdjęcia pomieszczenia» и «Zdjęcia obiektu» | Те же фото с путями; числа на карточке комнаты и объекта выросли и совпадают со списками |
| 5 | Просмотрщик: подпись, категория, «w raporcie», Archiwizuj → Przywróć | Всё сохраняется; числа уменьшаются/растут |
| 6 | Фото 5–12 МБ **по мобильной сети** | Загрузилось без обрыва; прогресс идёт |
| 7 | Свернуть Telegram во время загрузки, вернуться | Фото не потеряно и не задвоено |
| 8 | Тёмная тема, RU | Всё читаемо |

**Что я особенно хочу знать из пунктов 1–2:** какой формат пришёл (JPEG или HEIC) и открылась ли камера на вашем телефоне (iOS/Android) — от этого зависит, нужна ли отдельная работа с HEIC.

### B4 — проверка хранилища и БД (чтение)

В Cloudflare R2 → бакет `plan-estimate-media-prod`: у каждого фото **три** объекта в `photos/v1/<uuid>/` (`original.<ext>`, `display.jpg`, `thumb.jpg`). Затем:

```bash
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select status, capture_source, count(*) from photo_assets group by 1,2 order by 1,2;"'
docker logs plan_estimate_backend --since 30m 2>&1 | grep -iE "error|traceback|PHOTO_" | tail -n 20
```

**PASS:** все загруженные фото `READY`; `capture_source` = `CAMERA`/`GALLERY` как вы выбирали; три объекта на фото; в логах нет ошибок (кроме ожидаемых отказов, если вы их вызывали).

### B5 — второй бэкап: первое доказательство медиа-пути на реальных данных  → ждёт «да, B5»

Раздел 72.3 шаги 2–4. **PASS:** `backup complete: run_id=… ready_count=<n>` (n = число загруженных фото), `upload complete: … objects=<3n> ready_assets=<n>`, `verify ok … mode=full`.
Затем **restore-compare** на рабочей станции по `STAGE_14D6_PRODUCTION_RUNBOOK.md` (фазы P5–P8: ключ restore-пользователя на время проверки, `verify`, восстановление в чистую PostgreSQL, сверка чисел строк с production, удаление ключа и временных файлов).
Для первого запуска с медиа это **рекомендуется**; сокращённый вариант (только `verify` с VM) допустим по вашему решению.

### B6 — проверки на устройствах (контракт 14E §12)

(1) iOS и Android: камера и галерея в Telegram; (2) формат (JPEG/HEIC); (3) миниатюры и просмотр из R2 в WebView; (4) 5–12 МБ по мобильной сети через Cloudflare; (5) фон/возврат во время загрузки;
(6) прокрутка с ~30 миниатюрами; (7) BackButton с открытым просмотрщиком (закрывает просмотрщик, затем — уровень выше); (8) PL/RU, светлая/тёмная. Результаты — в журнал.

**PASS фазы B:** B2–B5 PASS; B6 пункты (1)–(5) и (7) подтверждены хотя бы на одном телефоне.

## 5. Откат

| Ситуация | Действие |
|---|---|
| Отключить загрузку (фото остаются, ничего не удаляется) | в `.env.production` `PHOTO_UPLOADS_ENABLED=false`; `PC up -d --no-deps backend` |
| Backend не стартует после A5 | `docker logs plan_estimate_backend --tail 100`; вернуть образ: `docker tag plan-estimate-backend:pre-14e7 plan-estimate-backend:latest && PC up -d --no-build backend`. Миграция `0033` откатывать **не нужно**: старый код колонку не видит. При необходимости: `docker exec plan_estimate_backend alembic downgrade 0032_photo_attachments` (только после согласования; теряется лишь информационное значение источника) |
| Сломался frontend | `docker tag plan-estimate-frontend:pre-14e7 plan-estimate-frontend:latest && PC up -d --no-build frontend` |
| Бэкап после отката backend на старый образ | пока в БД стоит `0033`, бэкап работает только с образами A6b (голова `0033`); если вы сделали `alembic downgrade 0032`, нужны образы старой головы |
| Любое сомнение с данными | остановиться и прислать вывод; `down -v` — **никогда** |

## 6. После завершения

Записываю в `docs/development-progress.md`: коммит и образы, ревизию БД, результаты A8/B3/B4/B5/B6, решение по D10, найденные проблемы. Затем — приёмка 14E и решение о следующем этапе.
Уборка: удалить `~/env.production.pre-14e7`, теги `:pre-14e7` (после приёмки), временные файлы бэкапа по раздела 72.
