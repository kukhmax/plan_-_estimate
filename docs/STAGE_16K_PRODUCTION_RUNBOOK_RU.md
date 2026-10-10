# Stage 16K — production: навигация приложения (меню, клиенты, объект плитками, архив, общий журнал) — без миграции

Порядок и правила — как в `STAGE_15H2_PRODUCTION_RUNBOOK_RU.md` и `STAGE_16_PRODUCTION_RUNBOOK_RU.md` (выкладка backend + frontend без миграции). Каждый шаг ждёт вашего явного «да»; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне, секреты в чат не вставлять. **Все шаги — в чистой новой SSH-сессии** (первая строка каждого блока проверяет, что лишних переменных 0).

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
```

## 1. Что выкладывается (production `5abb49b` → `origin/stage-16`)

Вы увидели Stage 16 на телефоне и остановили проверку: экран объекта был лентой из десятков карточек, шапка занимала полэкрана. Подэтап 16K (внутри Stage 16, ветка та же) перестроил навигацию.

| Часть | Изменение | Риск |
|---|---|---|
| Миграция | **нет**; `alembic current` остаётся `0053_downtime_episodes` | — |
| Backend (3 файла приложения) | `api/v1/endpoints/documents.py`, `domain/services/issued_document_service.py`, `schemas/issued_document.py`: один новый **только читающий** маршрут `GET /api/documents` (журнал отправленных документов по всем объектам владельца, постранично); завершает зависшие попытки так же, как журнал объекта. Ничего другого не меняется | низкий |
| Frontend | шапка в одну строку и меню слева (Клиенты, Объекты, Прайс, Архив, Отправленные документы, Аккаунт); клиенты — список имён и карточка с объектами и кнопкой «Смета»; объект — пять плиток (Смета, Помещения, Фото, Документы, Договор и протоколы) и отдельные экраны; архив с восстановлением; общий журнал; прайс доработан под телефон; из списков клиентов и объектов убраны переключатели «показать архивные» | средний: меняется весь путь по приложению (данные и расчёты не затронуты) |
| Compose / Caddy / Dockerfile / зависимости / `app/backup` | **без изменений** — проверяется A0 | — |
| Образы бэкапа | пересборка по-прежнему **нужна** (шаг A9 основного runbook Stage 16: голова миграций `0053`; к 16K отношения не имеет) | средний при пропуске |

Откат: миграции нет; образы `:pre-16k` возвращаются в любой момент (раздел 4).

## 2. Шаги

### A0 — только чтение → «да, A0»
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
git fetch origin stage-16
git merge-base --is-ancestor HEAD origin/stage-16 && echo "HEAD — предок origin/stage-16: ДА" || echo "HEAD — предок origin/stage-16: НЕТ"
echo "--- что придёт (коммиты) ---"; git log --oneline HEAD..origin/stage-16
echo "--- инфраструктура (должно быть пусто) ---"
git diff --name-only HEAD origin/stage-16 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile backend/app/backup backend/alembic
echo "--- файлы backend/app (ожидаем 3) ---"
git diff --name-only HEAD origin/stage-16 -- backend/app
```
**PASS:** `0` лишних переменных; дерево чистое, ветка `stage-16`, коммит `5abb49b` (или более поздний документальный); 4 контейнера `Up`/healthy; `alembic current` = `0053_downtime_episodes`; health ok; свободно ≥ 5 ГБ; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`; «предок: ДА»; блок «инфраструктура» **пуст**; в `backend/app` ровно 3 файла: `api/v1/endpoints/documents.py`, `domain/services/issued_document_service.py`, `schemas/issued_document.py`.

### A1 — получить код → «да, A1»
```bash
git pull --ff-only origin stage-16
git log --oneline -1
git status --short
```
**PASS:** fast-forward; верхний коммит = `origin/stage-16` (хеш назову после A0); дерево чистое.

### A2 — конфигурация и сборка (старый production работает) → «да, A2»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-16k
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-16k
PC build backend frontend 2>&1 | tail -n 8
PC ps
df -h / | tail -1
```
**PASS:** `0` лишних переменных; `CONFIG-OK`; обе сборки без ошибок (зависимости из кэша); контейнеры `Up`; свободно ≥ 4 ГБ.

### A3 — применить backend → «да, A3» (миграции нет: ВОРОТА M не нужны)
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps backend
sleep 25
docker exec plan_estimate_backend alembic current
docker logs plan_estimate_backend --tail 20
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET); print('endpoint:', str(s.MEDIA_S3_ENDPOINT_URL).split('//')[-1].split('.')[-3:]); print('доставка документов:', s.DOCUMENT_DELIVERY)"
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments;"'
```
**PASS:** `0` лишних переменных; `current` = `0053_downtime_episodes` (в логе **нет** строки `Running upgrade`); нет ошибок, видно `Application startup complete`; health ok; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`, endpoint `r2`, `cloudflarestorage`, `com`; доставка `telegram`; четыре числа (клиенты, объекты, документы, фото) те же, что до выкладки.

### A4 — применить frontend → «да, A4»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps frontend
PC ps
curl -fsS https://plan-estimate.pl/api/health; echo
```
**PASS:** `0` лишних переменных; все контейнеры `Up`/healthy; health ok.

### A5 — кнопка меню Telegram → «да, A5»
```bash
V=$(git rev-parse --short HEAD); echo "версия кнопки: $V"
set -a; source .env.production; set +a
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${V}\"}}}"; echo
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#'; echo
unset TELEGRAM_BOT_TOKEN V
```
**PASS:** оба ответа `"ok":true`, `?v=` = новый хеш. Затем полностью закройте Telegram и откройте Mini App заново.

### A6 — проверка новой навигации на телефоне (владелец, ~15 минут; PL, затем RU)
1. **Шапка и меню.** Вверху одна строка: слева ☰ и «Plan & Estimate», справа маленький переключатель PL/RU; подписи «Telegram Mini App — …» и ряда из трёх кнопок нет. ☰ открывает меню слева: Клиенты, Объекты, Прайс, Архив, Отправленные документы и внизу «Аккаунт» (профиль исполнителя там же). Закрывается выбором пункта, тапом вне меню, крестиком и кнопкой Telegram «Назад».
2. **Клиенты.** Список — только имена (человек или фирма), строка целиком нажимается. Карточка клиента: данные, «Редактировать», «Архивировать», блок «Объекты клиента» со статусом и кнопкой «Смета» у каждого объекта; «Смета» открывает сметы этого объекта.
3. **Объекты → объект.** Шесть крупных плиток: **Смета**, **Помещения**, **Фото объекта** (с числом), **PDF-документы**, **Договор и протоколы**, **Резюме объекта**. «Помещения» — только список комнат (комнаты и поверхности открываются как раньше). «Фото» — список фото открыт сразу. «PDF-документы» — список из четырёх строк (Технологическая карта, План производства работ, Фотоотчёт, Отправленные документы объекта), каждая открывается отдельно. «Резюме объекта» — итоги по площадям и проёмам.
4. **Договор и протоколы.** Короткий список в три группы (Стороны и подрядчики / Договор / Протоколы); каждая строка открывает одну карточку. Дальше — проверка Stage 16 по пунктам A7 основного runbook (договор, протоколы, простой), но теперь через эти плитки.
5. **Назад.** Кнопка Telegram «Назад» поднимается на шаг: карточка → список «Договор и протоколы» → объект → список объектов. Ссылки «Объекты / название / …» вверху нажимаются.
6. **Прайс.** Три плитки: Позиции прайса, Коэффициенты, Процессы; внутри каждой «Активные / Архив» — как раньше; «Назад» ведёт обратно к трём плиткам.
7. **Архив.** Вкладки «Клиенты» и «Объекты»: архивные записи и кнопка «Восстановить»; после восстановления запись появляется в своём списке. В списках клиентов и объектов переключателя «показать архивные» больше нет.
8. **Отправленные документы.** Все документы по всем объектам, новые сверху: вид, объект, номер, дата, статус; «Показать ещё» и «Обновить».
9. **320 / 390 / 412 px, PL и RU.** Кнопки ≥ 44 px (кроме маленького переключателя языка — по вашей просьбе), длинные русские подписи и названия не режутся и не налезают на кнопки, горизонтальной прокрутки нет.
10. **Ничего не пропало.** Клиенты, объекты, помещения, фото, сметы и ранее выданные документы на месте.

Присылайте результат пунктами «1 — PASS / FAIL (что увидели)».

## 3. Оценка риска
- **Данные:** миграции нет; единственное новое на backend — чтение. Данные объектов, документов и фото не меняются.
- **Совместимость:** новый frontend со старым backend не используется (порядок A3 → A4); старый frontend в кэше WebView работает с новым backend (старые маршруты не менялись).
- **Хранилище:** ключ приложения не меняется.
- **Навигация:** меняются все пути по приложению — главный риск восприятия, не данных; откат — образ frontend `:pre-16k`.

## 4. Откат
| Ситуация | Действие |
|---|---|
| Backend не стартует после A3 | `docker logs plan_estimate_backend --tail 100`; `docker tag plan-estimate-backend:pre-16k plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` |
| Сломался или не понравился frontend | `docker tag plan-estimate-frontend:pre-16k plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| Любое сомнение с данными | остановиться, прислать вывод; `down -v` — **никогда** |

## 5. После выкладки
Остаются шаги основного runbook Stage 16: **A7** (ваша проверка Stage 16 — теперь на новой навигации), **A8** (время и память на самом большом документе) и **A9** (пересборка образов бэкапа под голову `0053` и полный бэкап — пока он не сделан, бэкап останавливается безопасно). После приёмки — слияние `stage-16` в `main` отдельным вашим «да».

## 6. Дополнение 16K.6 — только frontend (замечания владельца после первого просмотра)

Backend не меняется (остаётся `75fd53e`, миграции `0053`). Шаги те же, что A0, A1–A2, A4, A5 выше, **без A3**:
1. **A0** (чтение): блок A0 выше; PASS — коммит на VM `75fd53e`, «предок: ДА», блок «инфраструктура» **пуст**, в `backend/app` **пусто** (изменился только `frontend`).
2. **A1 + A2:** `git pull --ff-only origin stage-16`, `PC build frontend`, перед сборкой тег `plan-estimate-frontend:pre-16k6` на работающий образ.
3. **A4:** `PC up -d --no-deps frontend`; проверка health.
4. **A5:** кнопка меню Telegram с новым хешем, затем полностью закрыть и открыть Telegram.
5. **Проверка на телефоне:** по чек-листу A6 выше (пункты 2, 3, 6, 7 изменились: архивирование клиента возвращает к списку с сообщением; плиток объекта шесть; документы списком; прайс плитками).
6. **Откат:** `docker tag plan-estimate-frontend:pre-16k6 plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend`.

