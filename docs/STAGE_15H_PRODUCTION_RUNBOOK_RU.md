# Stage 15H — итоговая проверка и production-выкладка Stage 15 (документы / PDF): runbook

Порядок и правила — как в `STAGE_14K_PRODUCTION_RUNBOOK_RU.md`, `STAGE_14G3_PRODUCTION_RUNBOOK_RU.md` (выкладка с миграцией) и `PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md` (раздел 72). **Каждый шаг ждёт вашего явного «да»**; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне. **Секреты, токен бота и ссылки на фото в чат не вставлять** (ключи — только в виде маски). «ВОРОТА» = стоп до вашего ответа. Все шаги с `docker compose` — в чистой новой SSH-сессии (`env | grep -c '^MEDIA_S3\|^BACKUP_'` = 0); бэкап — в отдельных сессиях (раздел 72.5).

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }   # в каждом новом сеансе SSH
```

## 0. Решения, нужные до начала

| № | Вопрос | Моя рекомендация |
|---|---|---|
| D1 | **Какую ветку отслеживает сервер.** Сейчас на VM локальная ветка `stage-14`. На GitHub `origin/stage-14` уже содержит коммиты 15B–15E (`daca978`, они попали туда до разделения веток), а полный Stage 15 лежит только в `origin/stage-15`. Поэтому **`git pull origin stage-14` на VM делать нельзя** — он принёс бы недоделанный Stage 15 (без 15F/15G и без миграции `0038`, но с кодом, который её ждёт). | На VM создать ветку `stage-15`, отслеживающую `origin/stage-15` (шаг A2). После вашей приёмки 15H — слияние `stage-15` → `main` (отдельное «да» на push в `main`) и переключение VM на `main`. `origin/stage-14` я не трогаю: он — предок `stage-15`, вреда не причиняет. |
| D2 | **Предварительный бэкап (A1).** Миграции только создают две новые таблицы, но так же делали на 14G.3. | Делать (раздел 72.3, шаги 2–4 существующими образами). |
| D3 | **Ограничение памяти backend.** У `backend` в `docker-compose.prod.yml` нет `mem_limit`; рендер PDF живёт в дочернем процессе с `RLIMIT_AS` 2048 МБ. На VM 1 OCPU / 6 ГБ. | Compose **не менять** в 15H; измерить пик на настоящем фотоотчёте (шаг A9). Если пик велик — отдельное решение (например `DOCUMENT_RENDER_MEMORY_MB` в `.env.production` или `mem_limit`). |

## 1. Что выкладывается (production `175f97c` → `origin/stage-15`)

| Часть | Изменение | Риск |
|---|---|---|
| **Миграции `0037_executor_profiles`, `0038_issued_documents`** | две новые **пустые** таблицы: `executor_profiles` (профиль исполнителя, один на владельца) и `issued_documents` (журнал выданных документов; файлы **не хранятся**); существующие таблицы не меняются. Подробности — раздел 4 | см. «ВОРОТА M» |
| **`backend/Dockerfile`** | в образ добавлены системные библиотеки WeasyPrint: `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fontconfig fonts-dejavu-core` (apt). **Первая сборка с ними на ARM64** | средний: сборка может не найти пакет (тогда ничего не применено, шаг A3) |
| **`requirements.txt`** | +16 закреплённых пакетов (Jinja2, MarkupSafe, weasyprint 70.0, pydyf, tinycss2, tinyhtml5, cssselect2, webencodings, fonttools, brotli, zopfli, Pyphen, cffi, pycparser, tzdata, pypdf). Для всех есть wheel под aarch64 / pure для cp312 — **компиляции на сервере нет** (проверено 2026-10-08) | низкий |
| `requirements-oci.txt` | `cffi` и `pycparser` перенесены в `requirements.txt` (версии те же); влияет только на образ бэкапа-загрузчика | низкий |
| Backend (приложение) | движок документов (Jinja2 → WeasyPrint в отдельном ограниченном процессе), профиль исполнителя, смета в PDF, фотоотчёт и отчёт осмотра (с метками и контурами), журнал, отправка файла ботом в чат владельца, заготовки договора и протоколов (без текста — Stage 16); новые маршруты `/executor-profile`, `/projects/{p}/documents`, `…/photo-report/summary`, `…/estimates/{e}/preview-pdf` | средний: самый большой объём нового кода (≈ 6400 строк в `backend/app` и `frontend/src`) |
| Frontend | «Профиль исполнителя», блок «PDF-документы» на смете и на объекте, фотоотчёт с выбором помещений, журнал «Отправленные документы» | низкий |
| Compose / Caddy / entrypoint / `app/backup` | **без изменений** — проверяется A0 | — |
| Новые настройки `DOCUMENT_*` | необязательны, действуют значения по умолчанию (`DOCUMENT_DELIVERY=telegram`, лимит 60 фото, 3 одновременных документа, рендер ≤ 90 с и ≤ 2048 МБ); в `.env.production` ничего добавлять не нужно | — |
| Образы бэкапа | **нужна пересборка** (шаг A10): голова миграций меняется на `0038`; до этого бэкап падает безопасно | средний при пропуске |

Журнал не ретроактивный: документов, выданных до выкладки, в нём нет (их и не было). Нумерация начинается с первого документа.

## 2. Шаги

### A0 — только чтение (состояние production и что придёт) → «да, A0»
```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
git status --short; git branch --show-current; git log --oneline -1
PC ps
docker inspect -f '{{.Name}}  {{.Image}}  {{.Created}}' plan_estimate_backend plan_estimate_frontend plan_estimate_caddy plan_estimate_postgres
docker exec plan_estimate_backend alembic current
curl -fsS https://plan-estimate.pl/api/health; echo
df -h / | tail -1; free -m | sed -n 1,2p
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET)"
git fetch origin stage-15
git merge-base --is-ancestor HEAD origin/stage-15 && echo "HEAD — предок origin/stage-15: ДА" || echo "HEAD — предок origin/stage-15: НЕТ"
echo "--- что придёт (коммиты) ---"; git log --oneline HEAD..origin/stage-15 | wc -l
echo "--- инфраструктура (ожидаем ровно 5 файлов) ---"
git diff --name-only HEAD origin/stage-15 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile backend/app/backup backend/alembic
```
**PASS:** `0` лишних переменных; дерево чистое, ветка `stage-14`, коммит — тот, что выложен 14K (`175f97c` или более поздний документальный); 4 контейнера `Up`/healthy; `alembic current` = `0036_photo_annotation_outline`; health ok; свободно ≥ 5 ГБ; ключ приложения **`97bfe5…6dab`**, бакет `plan-estimate-media-prod` (если `ab8171…048b` — остановиться и написать мне); «предок: ДА»; список инфраструктурных файлов — ровно `backend/Dockerfile`, `backend/requirements.txt`, `backend/requirements-oci.txt`, `backend/alembic/versions/0037_executor_profiles.py`, `backend/alembic/versions/0038_issued_documents.py`.

### A1 — бэкап перед миграцией (D2) — отдельная SSH-сессия → «да, A1»
**Закройте эту сессию после `verify` и открывайте новую для A2 и далее.** Раздел 72.3 основного runbook, **шаги 2–4** (`db-dump` → `upload` → `verify`) существующими образами: голова БД сейчас `0036`, образы собраны под неё и подходят. Перед `upload`/`verify` загрузить оба файла (`. backup.env; . upload.env`). **PASS:** `backup complete … ready_count=<число READY-фото>`, `upload complete`, `verify ok … mode=full`. Запишите `run_id` — он нужен для отката данных.

### A2 — получить код (D1) — новая SSH-сессия → «да, A2»
```bash
cd ~/apps/plan_-_estimate
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
git switch -c stage-15 --track origin/stage-15
git log --oneline -3
git status --short; git branch --show-current
```
**PASS:** `0` лишних переменных; создана ветка `stage-15`, отслеживающая `origin/stage-15`; верхний коммит = `origin/stage-15` (его хеш назову после A0); дерево чистое. *Старая ветка `stage-14` остаётся на месте; контейнеры не затронуты.* Если `git switch` откажется (локальные изменения) — остановиться и прислать вывод.

### A3 — конфигурация, сборка и проверка движка в новом образе (production работает) → «да, A3»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-15h
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-15h
docker images --format '{{.Repository}}:{{.Tag}}  {{.ID}}  {{.Size}}' | grep -E '(backend|frontend):pre-15h'
PC build backend frontend 2>&1 | tail -n 25
docker images --format '{{.Repository}}:{{.Tag}}  {{.ID}}  {{.Size}}' | grep -E 'plan-estimate-(backend|frontend):(latest|pre-15h)'
PC ps
df -h / | tail -1
```
**PASS:** `0` лишних переменных; `CONFIG-OK`; теги `pre-15h` у обоих образов; обе сборки без ошибок (**смотрю вывод apt и pip**: все пять apt-пакетов нашлись, ни одного пакета не собирали из исходников); новый backend-образ больше прежнего примерно на 100–250 МБ (допустимо; заметно больше — написать мне); контейнеры по-прежнему `Up`; свободно ≥ 4 ГБ. *Ничего ещё не применено.*

*Если сборка падает на apt (`Unable to locate package` — пакеты Debian bookworm arm64 мне из песочницы проверить не удалось) — это штатная остановка: production не затронут, образ `latest` не заменён успешной сборкой; пришлите вывод.*

### A3b — проверка движка PDF в новом образе, без базы, без сети (только чтение) → «да, A3b»
Настоящий рендерер приложения (дочерний процесс с лимитами) в только что собранном образе: польские буквы, шрифт, PDF.
```bash
docker run --rm -i --network none --entrypoint python plan-estimate-backend:latest - <<'PY'
import asyncio
from app.domain.documents.renderer import DocumentRenderer

HTML = ('<!doctype html><html><head><meta charset="utf-8"><style>body{font-family:"DejaVu Sans";font-size:12pt}</style></head>'
        '<body><h1>Kosztorys — test ąćęłńóśźż ĄĆĘŁŃÓŚŹŻ</h1><p>Szpachlowanie: 12,50 m² × 38,00 zł</p></body></html>')

async def main():
    pdf = await DocumentRenderer().render(HTML, {})
    print("SMOKE-OK pages=%s bytes=%s head=%s render=%.1fs" % (pdf.pages, pdf.byte_size, pdf.pdf[:5], pdf.render_seconds))

asyncio.run(main())
PY
docker run --rm --entrypoint sh plan-estimate-backend:latest -c 'fc-list | grep -ci dejavu; python -c "import weasyprint; print(weasyprint.__version__)"'
docker run --rm --entrypoint alembic plan-estimate-backend:latest heads
```
**PASS:** `SMOKE-OK pages=1 bytes=<~8 КБ> head=b'%PDF-' render=<секунды>`; число шрифтов DejaVu > 0; версия `70.0`; **`0038_issued_documents (head)`** (голову спрашиваем у **нового** образа; работающий контейнер показал бы `0036`). Если рендер падает (нет библиотеки, нет шрифта) — на этом выкладка **останавливается**, backend не применяется.

### ВОРОТА M — миграции → ждёт вашего «да, миграция»
Перед ответом: проверка файлов миграций из нового образа (ниже) и письменная оценка — раздел 4.
```bash
docker run --rm --entrypoint sh plan-estimate-backend:latest -c 'sed -n 1,80p /app/alembic/versions/0037_executor_profiles.py; echo ======; sed -n 1,90p /app/alembic/versions/0038_issued_documents.py'
```
**PASS:** файлы из образа совпадают с репозиторием (только создание таблиц, CHECK и индекса, `downgrade` удаляет их), цепочка `0036 → 0037 → 0038`.

### A4 — применить backend (entrypoint сам выполнит `alembic upgrade head`) — новая SSH-сессия → «да, A4»
```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps backend
sleep 25
docker exec plan_estimate_backend alembic current
docker exec plan_estimate_backend alembic heads
docker logs plan_estimate_backend --tail 40
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from executor_profiles; select count(*) from issued_documents; select count(*) from photo_attachments;"'
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET); print('endpoint:', str(s.MEDIA_S3_ENDPOINT_URL).split('//')[-1].split('.')[-3:]); print('доставка документов:', s.DOCUMENT_DELIVERY, '| лимит фото:', s.DOCUMENT_MAX_PHOTOS, '| память рендера МБ:', s.DOCUMENT_RENDER_MEMORY_MB)"
```
**PASS:** `0` лишних переменных **до** `up`; в логе две строки `Running upgrade … → 0037_executor_profiles` и `… → 0038_issued_documents`; `current` = `heads` = `0038_issued_documents`; в логе нет ошибок, видно `Starting uvicorn`; health ok (если не сразу — подождать 20 секунд); `executor_profiles` = **0**, `issued_documents` = **0**, `photo_attachments` — прежнее число; ключ приложения `97bfe5…6dab`, бакет `plan-estimate-media-prod`, endpoint `r2`, `cloudflarestorage`, `com`; доставка `telegram`, лимит `60`, память `2048`.

### A4b — разовая проверка доставки в Telegram из контейнера (токен не печатается) → «да, A4b»
Проверяем, что backend достаёт `api.telegram.org` и токен рабочий; выводим только признак `ok` и имя бота.
```bash
docker exec -i plan_estimate_backend python - <<'PY'
import httpx
from app.core.config import settings
r = httpx.get(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getMe", timeout=15)
d = r.json()
print("status:", r.status_code, "| ok:", d.get("ok"), "| bot:", (d.get("result") or {}).get("username"))
PY
```
**PASS:** `status: 200 | ok: True | bot: <имя вашего бота>`. (Если ошибка сети или 401 — отправка документов работать не будет; остановиться, прислать строку вывода без токена.)

### A5 — подписанная ссылка с чужого адреса (урок 14F.4; фото в 15 не менялись, но проверяем хранилище) → «да, A5»
Как в runbook 14G.3 (A5b): ссылку на миниатюру получить на VM и **вставить в локальный терминал компьютера** (не в SSH и не в чат):
```bash
docker exec -i plan_estimate_backend python - <<'PY'
from app.core.config import settings
from app.core.s3_media_storage import create_media_storage
s = create_media_storage(settings)
keys = sorted((o["LastModified"], o["Key"]) for o in s._get_client().list_objects_v2(Bucket=s._bucket, Prefix="photos/v1/", MaxKeys=300)["Contents"] if o["Key"].endswith("thumb.jpg"))
print(s._presign_sync(keys[-1][1], 900))
PY
```
На компьютере: `curl -sS -o /dev/null -D - "ССЫЛКА" | head -12`. **PASS:** `HTTP/1.1 200`, `Content-Type: image/jpeg`, в `CF-RAY` не `…-FRA`. *Это может не пригодиться (проверялось PASS 2026-10-08), можно пропустить по вашему решению — но фотоотчёт читает фото через то же хранилище, поэтому проверка дешёвая страховка.*

### A6 — применить frontend — новая SSH-сессия → «да, A6»
```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps frontend
PC ps
curl -fsS https://plan-estimate.pl/api/health; echo
```
**PASS:** `0` лишних переменных; 4 контейнера `Up`/healthy; health ok.

### A7 — cache-busting кнопки меню Telegram (раздел 71) → «да, A7»
```bash
V=$(git rev-parse --short HEAD); echo "версия кнопки: $V"
set -a; source .env.production; set +a
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${V}\"}}}"; echo
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#'; echo
unset TELEGRAM_BOT_TOKEN V
```
**PASS:** оба ответа `"ok":true`, `?v=` = новый хеш. Затем полностью закройте и заново откройте Telegram.

### A8 — проверка на телефоне (владелец, ~20 минут; PL, затем несколько экранов в RU)
**Перед началом:** на тестовом объекте должны быть смета (лучше FINAL) и несколько фото, отмеченных «Uwzględnij w raporcie»; хотя бы в одном осмотре — рекомендация с ценой из сметы.

1. **Профиль исполнителя.** Меню аккаунта → «Профиль исполнителя» («Profil wykonawcy»). Введите название фирмы, NIP, адрес, телефон, e-mail, счёт. Неверный NIP / счёт — понятная ошибка, ничего не сохраняется; верные данные — «Профиль сохранён». Закройте и откройте — данные на месте.
2. **Смета FINAL → «Wyślij PDF».** Блок «PDF-документы» на экране сметы. После нажатия — «Документ … готовится…», затем «Отправлено в чат с ботом». В чате с ботом приходит PDF: имя файла и номер вида `KOSZ/2026/10/…`, шапка с вашими данными, польские буквы, позиции, итог без НДС, нумерация страниц. Откройте PDF и просмотрите **весь**.
3. **Черновик сметы → «Podgląd PDF (wersja robocza)».** Приходит PDF с водяным знаком «WERSJA ROBOCZA»; **номера у черновика нет**, в журнал он не попадает.
4. **Фотоотчёт.** Блок «Raport fotograficzny» на объекте: сводка «Zdjęć w raporcie: N (limit 60)». «Wyślij PDF» → в чат приходит отчёт: фото с подписями, метки с номерами и описаниями, контуры, чек-лист и риски осмотра, блок **«Rekomendowane prace dodatkowe»** (риск → работа → цена из сметы).
5. **Журнал.** «Wysłane dokumenty» показывает оба документа: номер, «Nr kolejny» (1, 2, … по объекту), статус «Wysłano», дату, число страниц. Повторное нажатие на уже идущий документ не создаёт дубль.
6. **Блокировка «нет цены».** Рекомендация осмотра без цены в смете → отправка отчёта запрещена, показан список «Brak ceny w kosztorysie…»; после принятия рекомендации в смету или отклонения отправка проходит.
7. **Больше 60 фото** (если на объекте столько фото; иначе пропустить и записать «не проверялось»): показан выбор помещений, «Wybrano: N / 60», отправка частями.
8. **Чат бота не запущен** (по желанию, если есть второй аккаунт Telegram): документ получает статус «Nie wysłano» с понятной подсказкой («нажмите Start в чате с ботом»), номер остаётся занятым в журнале.
9. **Мобильный вид 390 и 412 px, PL и RU.** Кнопки ≥ 44 px, подписи и длинные RU-тексты не режутся, горизонтальной прокрутки нет, модалка профиля и блок документов вмещаются.
10. **Ничего не пропало.** Сметы, осмотры, фото, метки и контуры, сделанные раньше, на месте; общие счётчики фото не изменились.

Присылайте результат пунктами «1 — PASS / FAIL (что увидели)». Скриншоты PDF не пересылайте, если в них данные клиента; достаточно описания.

### A9 — время и память на настоящем отчёте (только чтение; во время пункта 4 и 7 из A8) → «да, A9»
Откройте второй SSH-сеанс и запустите **до** нажатия «Wyślij PDF» у самого большого фотоотчёта:
```bash
for i in $(seq 1 45); do date +%T; docker stats --no-stream --format 'backend: {{.MemUsage}}  cpu {{.CPUPerc}}' plan_estimate_backend; sleep 2; done
free -m | sed -n 1,2p
docker inspect -f 'OOMKilled={{.State.OOMKilled}} Restarts={{.RestartCount}}' plan_estimate_backend
docker logs plan_estimate_backend --since 15m 2>&1 | grep -iE 'error|traceback|killed|render' | tail -n 20
```
**PASS:** пик памяти backend укладывается в запас VM (общая `free -m` не уходит в swap, `OOMKilled=false`, `Restarts=0`); нет traceback; время отчёта от нажатия до файла в чате — в пределах 90 с (рендер) плюс отправка; в логе нет токена и URL бота. Присылайте строки с пиком (макс. `MemUsage`) и временем. Если время приближается к 90 с или пик > 3 ГБ — фиксирую как замечание (решение D3), выкладка остаётся.

### A10 — бэкап после выкладки: пересборка образов под голову `0038` и полный прогон — отдельная SSH-сессия → «да, A10»
Раздел 72.3 **шаг 1** (образы строятся из `git archive` нового коммита, `<ветка>` = `stage-15`), затем обновить `BACKUP_TOOL_COMMIT` в `~/backups/plan-estimate/db-backup/secrets/upload.env` на `git rev-parse origin/stage-15` (файл содержит секрет — в чат не присылать, печатать только маску/хеш); затем **шаги 2–4** (`db-dump` → `upload` → `verify`). **PASS:** оба образа собрались (в том числе слой загрузчика с `oci` на новых `requirements.txt` / `requirements-oci.txt`); `BACKUP_TOOL_COMMIT` = новый хеш; `backup complete … ready_count=<прежнее число>`, `upload complete`, `verify ok … mode=full`. **Закройте сессию** и больше не запускайте в ней compose.

## 3. Условия закрытия 15H

15H закрыт, когда: A0–A7 PASS, A8 пункты 1–6, 9, 10 PASS (пункты 7 и 8 — PASS или явно «не проверялось»), A9 без аварийных значений, A10 PASS. Тогда вы пишете «принимаем 15H» → я записываю приёмку в `docs/development-progress.md` и в план, закрываю Stage 15 в таблице дорожной карты. Слияние `stage-15` → `main` и переключение VM на `main` — отдельным вашим «да» (D1). **Stage 16 (договор и протоколы) не начинается без отдельного решения.**

## 4. Оценка миграций (для ВОРОТ M)

- **Что делают:** `0037` — `CREATE TABLE executor_profiles` (12 столбцов, внешний ключ на `users` с `ON DELETE CASCADE`, `UNIQUE(owner_id)`, три CHECK по длинам). `0038` — `CREATE TABLE issued_documents` (21 столбец, внешние ключи на `users` и `projects` с `ON DELETE CASCADE`, четыре CHECK, `UNIQUE(owner_id, number)`, `UNIQUE(owner_id, project_id, project_seq)`) и `CREATE INDEX ix_issued_documents_project_issued`. Существующие таблицы, строки и данные **не меняются**; `client_id` в журнале — простой UUID без внешнего ключа (документ остаётся в журнале при удалении клиента).
- **Блокировки:** создание таблиц и индекса на пустых таблицах — миллисекунды; внешние ключи берут короткие блокировки на `users` / `projects` (десятки строк) — незаметно. Каждая миграция идёт **одной транзакцией** (DDL в PostgreSQL транзакционный): при ошибке откат целиком, `alembic_version` остаётся на предыдущей ревизии.
- **Простой:** `PC up -d --no-deps backend` пересоздаёт контейнер backend: API недоступно примерно 20–40 секунд (миграции + старт uvicorn); база и фото не затрагиваются.
- **Обратимость:** `downgrade 0038` удаляет индекс и `issued_documents` (теряется журнал), `downgrade 0037` удаляет `executor_profiles` (профиль вводится заново). Ничто другое на эти таблицы не ссылается.
- **Совместимость со старым кодом:** старый backend этих таблиц не знает и ничего в них не пишет — **откат образа backend без отката миграций безопасен**. Новый frontend со старым backend не используется (порядок A4 → A6).
- **Бэкап:** рекомендую A1 до миграции; после A4 образы бэкапа надо пересобрать (A10), иначе бэкап остановится безопасно (головы не совпадут).
- **Хранилище:** ключ приложения не меняется; новые таблицы файлов не содержат.

## 5. Оценка риска и откат

| Что может пойти не так | Признак | Действие |
|---|---|---|
| Сборка не находит apt-пакет / pip-пакет | A3 падает до `up` | Production не затронут. Прислать вывод; исправление — мой коммит в `Dockerfile` / `requirements`, затем снова A2–A3. |
| Рендер PDF не работает в образе | A3b не `SMOKE-OK` | Не применять backend; прислать вывод; production не затронут. |
| Миграция упала | в логе A4 ошибка, `alembic current` = `0036` или `0037` | Миграции транзакционные: контейнер перезапускается и падает снова — вернуть образ: `docker tag plan-estimate-backend:pre-15h plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` (старый код с `0037` в БД работает, таблица ему не мешает). |
| Backend не стартует после A4 | `docker logs plan_estimate_backend --tail 100` | Тот же возврат образа `:pre-15h`; миграции могут остаться. |
| Backend работает, нужна отмена фич | — | Образ `:pre-15h` как выше (таблицы старому коду не мешают). Полный возврат схемы — только по согласованию: `docker exec plan_estimate_backend alembic downgrade 0036_photo_annotation_outline` **до** смены образа (теряются профиль и журнал). |
| Сломался frontend | — | `docker tag plan-estimate-frontend:pre-15h plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| PDF не доходит в чат | статус «Nie wysłano», код в журнале (`TELEGRAM_CHAT_UNAVAILABLE` / `TELEGRAM_UNAVAILABLE`) | Нажать Start в чате с бота (A8 п. 8) / проверить A4b; временно отключить доставку можно только по моему отдельному предложению (`DOCUMENT_DELIVERY=disabled`). |
| Нехватка памяти при большом отчёте | A9: `OOMKilled=true`, перезапуск контейнера, swap | Сообщить мне; отчёт можно разбить по помещениям (лимит 60 фото, выбор помещений уже есть); решение D3 принимается отдельно. |
| Ключ приложения стал `ab8171…048b` | маска в A4 | Остановиться; пересоздать backend в новой SSH-сессии (72.5). |
| Любое сомнение с данными | — | Остановиться, прислать вывод; `down -v` — **никогда**. Данные восстанавливаются из бэкапа A1 (`run_id` записан). |

## 6. Остаётся после 15H (backlog, не часть выкладки)

- Удаление старых тегов отката: backend `:pre-14h5`, `:pre-14h6`; frontend `:pre-14h5`, `:pre-14h6`, `:pre-14h8`; `:pre-14k` — примерно с 2026-10-15, командой владельца (пришлю отдельно). Тег `:pre-15h` держим до приёмки следующего этапа.
- Необязательная нормализация контуров «O»; решение об очистке архива — после Stage 16; офлайн-очередь фото 14E.8; финальный проход по интерфейсу.
- Stage 16 добавит в журнал виды «договор» и «протоколы» собственной миграцией.
