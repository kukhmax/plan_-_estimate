# Stage 16J — итоговая проверка и production-выкладка Stage 16 (договор и защитные протоколы): runbook

Порядок и правила — как в `STAGE_15H_PRODUCTION_RUNBOOK_RU.md` (выкладка с миграциями), `STAGE_15H2_PRODUCTION_RUNBOOK_RU.md` и `PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md` (раздел 72). **Каждый шаг ждёт вашего явного «да»**; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне. **Секреты, токен бота и ссылки на фото в чат не вставлять** (ключи — только в виде маски). «ВОРОТА» = стоп до вашего ответа. Все шаги с `docker compose` — в чистой новой SSH-сессии (`env | grep -c '^MEDIA_S3\|^BACKUP_'` = 0); бэкап — в отдельных сессиях (раздел 72.5).

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }   # в каждом новом сеансе SSH
```

## 0. Решения, нужные до начала

| № | Вопрос | Моя рекомендация |
|---|---|---|
| D1 | **Какую ветку отслеживает сервер.** Production сейчас на `848d360` (Stage 15 закрыт; `main` и `origin/stage-15` указывают на этот коммит). `origin/stage-16` содержит его как предка и ещё 26+ коммитов Stage 16 (проверено: `main` — предок `stage-16`). | На VM создать ветку `stage-16`, отслеживающую `origin/stage-16` (шаг A2) — как делали на 15H. После вашей приёмки — слияние `stage-16` → `main` (отдельное «да» на push в `main`) и переключение VM на `main`. |
| D2 | **Предварительный бэкап (A1).** Пятнадцать миграций: 8 новых таблиц, 3 столбца в `clients`, 8 расширений CHECK журнала. Данные существующих таблиц не меняются, но миграций много. | Делать (раздел 72.3, шаги 2–4 существующими образами, голова БД сейчас `0038`). |
| D3 | **Юридический текст.** Каталог положений договора (L2–L15) и числовые значения (допуски и т. п.) — **черновик владельца без проверки юристом** (ваше решение «пока без юриста»). | Выкладывать можно: документы остаются на бумаге и подписываются вами лично; перед первым реальным договором с клиентом — проверка юристом (backlog, раздел 6). |
| D4 | **Память backend.** Измерено в песочнице (без ограничений контейнера): приёмка на 60 поверхностей / 120 замечаний — 46 страниц, 97 КБ, 6,0 с; протокол решений на 30 пунктов — 16 страниц, 45 КБ, 3,2 с; простой на 60 дней — 4 страницы, 21 КБ, 1,9 с. Рендер идёт в дочернем процессе с `RLIMIT_AS` 2048 МБ и лимитом 90 с. | Compose не менять; на VM измерить пик на вашем самом большом документе (шаг A8). |

## 1. Что выкладывается (production `848d360` → `origin/stage-16`)

| Часть | Изменение | Риск |
|---|---|---|
| **Миграции `0039` … `0053`** (15 штук) | см. раздел 4 и ВОРОТА M: 8 новых **пустых** таблиц (`project_representatives`, `adjacent_works`, `contracts`, `handover_protocols`, `concealed_works_protocols`, `acceptance_protocols`, `decision_protocols`, `downtime_episodes`); 3 необязательных столбца адреса в `clients`; расширение CHECK `ck_issued_documents_kind` в журнале (новые виды документов); 2 CHECK и частичные индексы на `contracts` | средний: много миграций, но каждая простая и транзакционная |
| Backend (приложение) | адрес клиента и лица объекта; технологическая карта и план производства работ (PDF); реестр работ смежников; договор: анкета, «ворота» готовности, замороженный снимок, документ с приложениями, подписание; протоколы: передачи помещений, скрытых работ, приёмки работ (результат выводится, не вводится), информации и решений, простоя по вине заказчика (zawiadomienie + protokół); каталоги в `domain/contracts/catalog/*.json` и шаблоны документов; порядок замечаний приёмки (`position`, найдено в 16J) | средний: самый большой объём этапа |
| Frontend | карточки в «Объекте»: «Osoby objektu», «Prace innych wykonawców», «Umowa», «Protokół przekazania pomieszczeń», «Protokół odbioru robót zanikających», «Protokół odbioru prac», «Protokół informacji i decyzji», «Przestój po stronie Zamawiającego»; кнопки «Wersja robocza do wydruku (puste pola)» и «Wystaw …» | низкий |
| Compose / Caddy / Dockerfile / entrypoint / зависимости / `app/backup` | **без изменений** — проверено сравнением с `origin/main`: пусто; перепроверяется в A0 | — |
| Каталоги и шаблоны | лежат внутри `backend/app` и попадают в образ командой `COPY . .` — отдельной выкладки не нужно | — |
| Образы бэкапа | **нужна пересборка** (шаг A9): голова миграций меняется на `0053`; до этого бэкап падает безопасно | средний при пропуске |

Журнал «Wysłane dokumenty» уже существует (Stage 15); новые виды документов получают собственные префиксы номеров: `KART`, `PLAN`, `UMOWA`, `PRZEK`, `ZANIK`, `ODBIOR`, `DECYZ`, `ZAWPRZ`, `PROPRZ` (нумерация с первого выданного документа каждого вида).

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
git fetch origin stage-16
git merge-base --is-ancestor HEAD origin/stage-16 && echo "HEAD — предок origin/stage-16: ДА" || echo "HEAD — предок origin/stage-16: НЕТ"
echo "--- что придёт (коммиты) ---"; git log --oneline HEAD..origin/stage-16 | wc -l
echo "--- инфраструктура (ожидаем ТОЛЬКО backend/alembic/versions/0039…0053, 15 файлов) ---"
git diff --name-only HEAD origin/stage-16 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile backend/app/backup backend/alembic
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments;"'
```
**PASS:** `0` лишних переменных; дерево чистое, ветка `main` или `stage-15`, коммит `848d360` (или более поздний документальный); 4 контейнера `Up`/healthy; `alembic current` = `0038_issued_documents`; health ok; свободно ≥ 5 ГБ; ключ приложения **`97bfe5…6dab`**, бакет `plan-estimate-media-prod` (если `ab8171…048b` — остановиться и написать мне); «предок: ДА»; в списке инфраструктуры **только** файлы `backend/alembic/versions/0039_…` … `0053_…` (15 строк, ни `Dockerfile`, ни `requirements`, ни `app/backup`); счётчики клиентов / объектов / документов / фото запишите — после миграции они не должны измениться.

### A1 — бэкап перед миграцией (D2) — отдельная SSH-сессия → «да, A1»
**Закройте эту сессию после `verify` и открывайте новую для A2 и далее.** Раздел 72.3 основного runbook, **шаги 2–4** (`db-dump` → `upload` → `verify`) существующими образами: голова БД сейчас `0038`, образы собраны под неё и подходят. Перед `upload`/`verify` загрузить оба файла (`. backup.env; . upload.env`). **PASS:** `backup complete … ready_count=<число READY-фото>`, `upload complete`, `verify ok … mode=full`. Запишите `run_id` — он нужен для отката данных.

### A2 — получить код (D1) — новая SSH-сессия → «да, A2»
```bash
cd ~/apps/plan_-_estimate
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
git switch -c stage-16 --track origin/stage-16
git log --oneline -3
git status --short; git branch --show-current
```
**PASS:** `0` лишних переменных; создана ветка `stage-16`, отслеживающая `origin/stage-16`; верхний коммит = `origin/stage-16` (его хеш назову после A0); дерево чистое. *Прежняя ветка остаётся на месте; контейнеры не затронуты.* Если `git switch` откажется (локальные изменения) — остановиться и прислать вывод.

### A3 — конфигурация и сборка (production работает) → «да, A3»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-16
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-16
docker images --format '{{.Repository}}:{{.Tag}}  {{.ID}}  {{.Size}}' | grep -E '(backend|frontend):pre-16'
PC build backend frontend 2>&1 | tail -n 12
docker images --format '{{.Repository}}:{{.Tag}}  {{.ID}}  {{.Size}}' | grep -E 'plan-estimate-(backend|frontend):(latest|pre-16)'
PC ps
df -h / | tail -1
```
**PASS:** `0` лишних переменных; `CONFIG-OK`; теги `pre-16` у обоих образов; обе сборки без ошибок (системные библиотеки и зависимости берутся из кэша — Dockerfile и `requirements` не менялись, пересобираются только слои с кодом); размер нового backend-образа почти равен прежнему (отличие в единицы МБ); контейнеры `Up`; свободно ≥ 4 ГБ. *Ничего ещё не применено.*

### A3b — проверка в новом образе, без базы, без сети (только чтение) → «да, A3b»
Настоящий рендерер приложения в только что собранном образе, каталоги и шаблоны на месте, голова миграций.
```bash
docker run --rm -i --network none --entrypoint python plan-estimate-backend:latest - <<'PY'
import asyncio
from app.domain.contracts.catalog import load_contract_catalog
from app.domain.contracts.clauses import load_clause_catalog
from app.domain.documents.renderer import DocumentRenderer

HTML = ('<!doctype html><html><head><meta charset="utf-8"><style>body{font-family:"DejaVu Sans";font-size:12pt}</style></head>'
        '<body><h1>Umowa — test ąćęłńóśźż ĄĆĘŁŃÓŚŹŻ</h1><p>§ 1 ust. 2 pkt 3</p></body></html>')

async def main():
    c = load_contract_catalog(); k = load_clause_catalog()
    print("CATALOG-OK questions=%s downtime_causes=%s clause_sections=%s" % (len(c.questionnaire.items), len(c.downtime_causes.items), len(k.sections)))
    pdf = await DocumentRenderer().render(HTML, {})
    print("SMOKE-OK pages=%s bytes=%s head=%s render=%.1fs" % (pdf.pages, pdf.byte_size, pdf.pdf[:5], pdf.render_seconds))

asyncio.run(main())
PY
docker run --rm --entrypoint alembic plan-estimate-backend:latest heads
docker run --rm --entrypoint sh plan-estimate-backend:latest -c 'ls /app/app/domain/documents/templates | wc -l; ls /app/app/domain/contracts/catalog'
```
**PASS:** `CATALOG-OK questions=31 downtime_causes=8 clause_sections=23`; `SMOKE-OK pages=1 … head=b'%PDF-'`; **`0053_downtime_episodes (head)`** (голову спрашиваем у **нового** образа; работающий контейнер показал бы `0038`); в образе 17 файлов шаблонов и 9 JSON-каталогов (`assessment_instruments`, `clauses`, `concealed_work_kinds`, `defect_classes`, `downtime_causes`, `evaluation_conditions`, `premises_requirements`, `questionnaire`, `tolerances`). Если что-то не находится или не рендерится — backend не применяется, прислать вывод.

### ВОРОТА M — миграции → ждёт вашего «да, миграция»
Перед ответом: проверка файлов миграций из нового образа и письменная оценка — раздел 4.
```bash
docker run --rm --entrypoint sh plan-estimate-backend:latest -c 'ls /app/alembic/versions | sed -n "/^0039/,\$p"; echo ======; for f in /app/alembic/versions/00[3-5]*.py; do grep -q "def downgrade" "$f" || echo "БЕЗ downgrade: $f"; done; echo downgrade-check-done'
```
**PASS:** цепочка `0039 … 0053` (15 файлов, без пропусков); строк «БЕЗ downgrade» нет; в конце `downgrade-check-done`; файлы совпадают с репозиторием (только `CREATE TABLE`/`INDEX`, `ADD COLUMN` nullable, замена CHECK).

### A4 — применить backend (entrypoint сам выполнит `alembic upgrade head`) — новая SSH-сессия → «да, A4»
```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps backend
sleep 30
docker exec plan_estimate_backend alembic current
docker exec plan_estimate_backend alembic heads
docker logs plan_estimate_backend --tail 60
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments; select count(*) from contracts; select count(*) from project_representatives; select count(*) from adjacent_works; select count(*) from handover_protocols; select count(*) from concealed_works_protocols; select count(*) from acceptance_protocols; select count(*) from decision_protocols; select count(*) from downtime_episodes;"'
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET); print('endpoint:', str(s.MEDIA_S3_ENDPOINT_URL).split('//')[-1].split('.')[-3:]); print('доставка документов:', s.DOCUMENT_DELIVERY)"
```
**PASS:** `0` лишних переменных **до** `up`; в логе пятнадцать строк `Running upgrade … → 00NN_…` от `0039_client_address` до `0053_downtime_episodes`; `current` = `heads` = `0053_downtime_episodes`; в логе нет ошибок, видно `Application startup complete`; health ok (если не сразу — подождать 20 секунд); первые четыре счётчика (клиенты / объекты / документы / фото) **равны записанным в A0**; остальные восемь (новые таблицы) = **0**; ключ приложения `97bfe5…6dab`, бакет `plan-estimate-media-prod`, endpoint `r2`, `cloudflarestorage`, `com`; доставка `telegram`.

### A4b — разовая проверка доставки в Telegram из контейнера (токен не печатается) → «да, A4b»
```bash
docker exec -i plan_estimate_backend python - <<'PY'
import httpx
from app.core.config import settings
r = httpx.get(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getMe", timeout=15)
d = r.json()
print("status:", r.status_code, "| ok:", d.get("ok"), "| bot:", (d.get("result") or {}).get("username"))
PY
```
**PASS:** `status: 200 | ok: True | bot: <имя вашего бота>`.

### A5 — применить frontend — новая SSH-сессия → «да, A5»
```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps frontend
PC ps
curl -fsS https://plan-estimate.pl/api/health; echo
```
**PASS:** `0` лишних переменных; 4 контейнера `Up`/healthy; health ok.

### A6 — cache-busting кнопки меню Telegram (раздел 71) → «да, A6»
```bash
V=$(git rev-parse --short HEAD); echo "версия кнопки: $V"
set -a; source .env.production; set +a
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${V}\"}}}"; echo
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#'; echo
unset TELEGRAM_BOT_TOKEN V
```
**PASS:** оба ответа `"ok":true`, `?v=` = новый хеш. Затем полностью закройте и заново откройте Telegram.

### A7 — проверка на телефоне (владелец, ~40 минут; PL, затем ключевые экраны в RU)
**Перед началом:** тестовый объект с клиентом, завершёнными осмотрами, фото с дефектами, планом работ по поверхностям и сметой (лучше FINAL). Кнопки «Wersja robocza…» и «Wystaw …» присылают PDF в чат с ботом. Проверка идёт **на тестовом объекте**: выданный документ получает номер и остаётся в журнале навсегда.

1. **Всё прежнее работает.** Клиенты, объекты, осмотры, фото и метки, сметы, журнал «Wysłane dokumenty» (документы Stage 15) на месте; счётчики не изменились.
2. **«Osoby objektu».** Добавьте представителя заказчика (имя, должность, телефон) с «Może odbierać prace i podpisywać protokoły». Архивирование и «Pokaż zarchiwizowane» работают. Адрес клиента (ulica, kod pocztowy, miasto) сохраняется на карточке клиента.
3. **«Prace innych wykonawców».** Добавить / изменить / архивировать работу смежника (вид, исполнитель, помещения, период, порядок).
4. **Технологическая карта и план производства.** «Wersja robocza do wydruku (puste pola)» → в чате PDF с бледным водяным знаком, **без номера**, с пустыми полями для записи от руки. «Wyślij kartę (PDF)» / «Wyślij plan (PDF)» — выдача с номером `KART/…` / `PLAN/…`.
5. **Договор.** Карточка «Umowa»: анкета (кто принимает, даты, платежи, гарантия, простой, приёмка); «Skomponuj umowę». Блок «Gotowość umowy» показывает, что мешает выдаче (если мешает). «Wersja robocza do wydruku» — в чате черновик с пустыми полями. «Wystaw umowę» (когда ворота открыты) — документ `UMOWA/…` с приложениями; затем «Umowa podpisana» (нажать дважды), смета становится принятой. Положения — из каталога (юридический черновик, D3).
6. **«Protokół przekazania pomieszczeń».** «Rozpocznij…», отметки по помещениям и решение, ворота, черновик на печать, «Wystaw protokół» → `PRZEK/…`.
7. **«Protokół odbioru robót zanikających».** Выбор вида скрытых работ и фото-доказательства, ворота, черновик, «Wystaw protokół» → `ZANIK/…`.
8. **«Protokół odbioru prac».** Результат по поверхностям **выводится сам** (не вводится): невыполненная работа или существенное замечание → «не принято», только устранимые (со сроком) → «с замечаниями»; замечания идут в том порядке, в каком вы их добавляли (на экране, в PDF и после перезагрузки страницы). Заказчик отсутствует → нужны даты уведомлений по порядку. «Wystaw protokół» → `ODBIOR/…`.
9. **«Protokół informacji i decyzji».** Пункты из активных рисков (текст не редактируется) и собственные рекомендации; решение принято / отклонено / настаивает; действие исполнителя (выполнить / отказаться) только при «настаивает»; заявление «понял» или «отказался подписать» (+ заметка). «Wystaw protokół» → `DECYZ/…`.
10. **«Przestój po stronie Zamawiającego».** «Zgłoś przestój» → причина и дни (после даты уведомления, пн–пт), «Wystaw zawiadomienie» → `ZAWPRZ/…`; затем протокол простоя (поля протокола доступны только после уведомления), сумма считается по условиям замороженного договора; «Wystaw protokół» → `PROPRZ/…`.
11. **Журнал.** «Wysłane dokumenty» показывает все выданные документы: номер, «Nr kolejny», статус «Wysłano», дату, число страниц. Рабочие версии (черновики) в журнал **не попадают**.
12. **Мобильный вид 320 / 390 / 412 px, PL и RU.** Все восемь карточек: кнопки ≥ 44 px, длинные русские подписи и названия не режутся и не налезают на кнопки, горизонтальной прокрутки нет, двойные подтверждения работают, Telegram BackButton возвращает на уровень выше.
13. **Ничего не пропало.** Данные Stage 1–15 неизменны (счётчики как в A4).

Присылайте результат пунктами «1 — PASS / FAIL (что увидели)». Скриншоты PDF не пересылайте, если в них данные клиента; достаточно описания. Пункты, которые не удалось проверить (например, нет подходящего риска для протокола решений), помечайте «не проверялось».

### A8 — время и память на самом большом документе (только чтение; во время пунктов 5–10 из A7) → «да, A8»
Во втором SSH-сеансе **до** нажатия «Wystaw …» у самого большого документа:
```bash
for i in $(seq 1 45); do date +%T; docker stats --no-stream --format 'backend: {{.MemUsage}}  cpu {{.CPUPerc}}' plan_estimate_backend; sleep 2; done
free -m | sed -n 1,2p
docker inspect -f 'OOMKilled={{.State.OOMKilled}} Restarts={{.RestartCount}}' plan_estimate_backend
docker logs plan_estimate_backend --since 15m 2>&1 | grep -iE 'error|traceback|killed|render' | tail -n 20
```
**PASS:** пик памяти укладывается в запас VM (`free -m` не уходит в swap, `OOMKilled=false`, `Restarts=0`); нет traceback; время от нажатия до файла в чате — в пределах 90 с (рендер) плюс отправка; в логе нет токена и URL бота. Присылайте строки с максимумом `MemUsage` и временем. Если время приближается к 90 с или пик > 3 ГБ — фиксирую как замечание (D4), выкладка остаётся.

### A9 — бэкап после выкладки: пересборка образов под голову `0053` и полный прогон — отдельная SSH-сессия → «да, A9»
Раздел 72.3 **шаг 1** (образы строятся из `git archive` нового коммита, `<ветка>` = `stage-16`), затем обновить `BACKUP_TOOL_COMMIT` в `~/backups/plan-estimate/db-backup/secrets/upload.env` на `git rev-parse origin/stage-16` (файл содержит секрет — в чат не присылать, печатать только маску/хеш); затем **шаги 2–4** (`db-dump` → `upload` → `verify`). **PASS:** оба образа собрались; `BACKUP_TOOL_COMMIT` = новый хеш; `backup complete … ready_count=<прежнее число>`, `upload complete`, `verify ok … mode=full`. **Закройте сессию** и больше не запускайте в ней compose.

## 3. Условия закрытия 16J

16J закрыт, когда: A0–A6 PASS, A7 пункты 1, 2, 5, 8, 11–13 PASS (остальные — PASS или явно «не проверялось»), A8 без аварийных значений, A9 PASS. Тогда вы пишете «принимаем 16J» → я записываю приёмку в `docs/development-progress.md` и в план и закрываю Stage 16 в таблице дорожной карты. Слияние `stage-16` → `main` и переключение VM на `main` — отдельным вашим «да» (D1). **Следующий этап не начинается без отдельного решения.**

## 4. Оценка миграций (для ВОРОТ M)

| Ревизия | Что делает | Обратимость |
|---|---|---|
| `0039_client_address` | `ADD COLUMN street, postal_code, city` в `clients`, все `NULL` (в PostgreSQL — без перезаписи таблицы) | `downgrade` удаляет столбцы (адреса теряются) |
| `0040_project_representatives` | `CREATE TABLE project_representatives` + индекс | удаляет таблицу |
| `0041`, `0043`, `0045`, `0048`, `0049`, `0051`, `0052`, `0053` | замена CHECK `ck_issued_documents_kind` на более широкий набор видов (`TECH_CARD`, `PRODUCTION_PLAN`, `CONTRACT`, `HANDOVER_PROTOCOL`, `CONCEALED_WORKS_PROTOCOL`, `FINAL_PROTOCOL`, `DECISION_PROTOCOL`, `DOWNTIME_NOTICE`/`DOWNTIME_PROTOCOL`); существующие строки журнала проходят проверку. Короткая блокировка `issued_documents` (десятки строк) | `downgrade` **отказывается**, пока в журнале есть выданные документы нового вида (улики не стираются молча) |
| `0042_adjacent_works`, `0044_contracts`, `0047_handover_protocols`, `0049_concealed_works`, `0050_acceptance_protocols`, `0052_decision_protocols`, `0053_downtime_episodes` | `CREATE TABLE` (внешние ключи с `ON DELETE CASCADE`, CHECK, частичный уникальный индекс «один черновик на объект») | `downgrade` удаляет таблицу; для таблиц с выданными документами — отказ при наличии улик |
| `0045_contract_issue`, `0046_contract_signed` | CHECK «выданный договор заморожен», CHECK «подписанный имеет дату», частичный уникальный индекс «один подписанный на объект» — на пустой `contracts` | удаляет ограничения |

- **Данные существующих таблиц не меняются** (кроме трёх новых пустых столбцов `clients`). Счётчики A0 и A4 должны совпасть.
- **Блокировки:** создание таблиц и индексов на пустых таблицах и замена CHECK на таблице в десятки строк — миллисекунды. Каждая миграция идёт **одной транзакцией** (DDL в PostgreSQL транзакционный): при ошибке откат целиком, `alembic_version` остаётся на предыдущей ревизии.
- **Простой:** `PC up -d --no-deps backend` пересоздаёт контейнер: API недоступно ≈ 30–60 секунд (пятнадцать миграций + старт uvicorn); база и фото не затрагиваются.
- **Проверено до выкладки:** полная цепочка `0038 → 0053 → 0038 → 0053` на настоящем PostgreSQL 16 (15 вверх / 15 вниз / 15 вверх) с «боевой» строкой журнала, которая сохранилась; допустимые виды документов после `0053`: ESTIMATE, PHOTO_REPORT, TECH_CARD, PRODUCTION_PLAN, CONTRACT, HANDOVER_PROTOCOL, CONCEALED_WORKS_PROTOCOL, FINAL_PROTOCOL, DECISION_PROTOCOL, DOWNTIME_NOTICE, DOWNTIME_PROTOCOL; `alembic` autogenerate показывает только различия, существовавшие до Stage 16.
- **Совместимость со старым кодом:** старый backend не знает новых таблиц и не пишет в них; новый CHECK шире прежнего, новые столбцы `clients` необязательны — **откат образа backend без отката миграций безопасен**. Новый frontend со старым backend не используется (порядок A4 → A5).
- **Бэкап:** A1 до миграции; после A4 образы бэкапа надо пересобрать (A9), иначе бэкап остановится безопасно (головы не совпадут).
- **Хранилище:** ключ приложения не меняется; новые таблицы файлов не содержат (PDF каждый раз собирается заново из сохранённой страницы).

## 5. Оценка риска и откат

| Что может пойти не так | Признак | Действие |
|---|---|---|
| Сборка падает | A3 не дошёл до `PC ps` | Production не затронут (образ `latest` не заменён неудачной сборкой). Прислать вывод. |
| В образе нет каталогов / шаблонов или не рендерится | A3b не `CATALOG-OK` / `SMOKE-OK` | Не применять backend; прислать вывод. |
| Миграция упала | в логе A4 ошибка, `alembic current` — одна из `0038…0052` | Миграции транзакционные: контейнер перезапускается и падает снова — вернуть образ: `docker tag plan-estimate-backend:pre-16 plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` (старый код с уже применёнными миграциями работает). |
| Backend не стартует после A4 | `docker logs plan_estimate_backend --tail 100` | Тот же возврат образа `:pre-16`; миграции могут остаться. |
| Нужна отмена фич | — | Образ `:pre-16` как выше. Полный возврат схемы — только по согласованию: `docker exec plan_estimate_backend alembic downgrade 0038_issued_documents` **до** смены образа (теряются профили, договоры и протоколы; при выданных документах нового вида `downgrade` откажется — это защита, не ошибка). |
| Сломался frontend | — | `docker tag plan-estimate-frontend:pre-16 plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| PDF не доходит в чат | статус «Nie wysłano», код в журнале | Нажать Start в чате бота / проверить A4b. |
| Нехватка памяти на большом документе | A8: `OOMKilled=true`, swap | Сообщить мне; решение D4 принимается отдельно (`DOCUMENT_RENDER_MEMORY_MB` или `mem_limit`). |
| Ключ приложения стал `ab8171…048b` | маска в A4 | Остановиться; пересоздать backend в новой SSH-сессии (72.5). |
| Любое сомнение с данными | — | Остановиться, прислать вывод; `down -v` — **никогда**. Данные восстанавливаются из бэкапа A1 (`run_id` записан). |

## 6. Остаётся после Stage 16 (backlog, не часть выкладки)

- **Юрист:** проверка каталога положений L2–L15 и ваших числовых значений (допуски и пр.) до первого реального договора (D3).
- Не реализовано сознательно: календарь государственных праздников (простой считается по дням пн–пт), «требование устранить препятствие с угрозой отказа» (§ 10 ust. 5 договора), проверка срока уведомления о готовности, фото внутри самих документов (фото остаются в журнале осмотров).
- Удаление старых тегов отката (`:pre-14*`, `:pre-15h*`) — командой владельца, отдельным списком. Тег `:pre-16` держим до приёмки следующего этапа.
