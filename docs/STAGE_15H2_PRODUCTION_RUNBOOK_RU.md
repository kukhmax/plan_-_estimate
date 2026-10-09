# Stage 15H.2 — production: одна и та же работа для разных дефектов — стена и причина на карточке, предупреждение и подтверждение (без миграции)

Порядок и правила — как в `STAGE_14H5_PRODUCTION_RUNBOOK_RU.md` (выкладка backend + frontend без миграции) и `STAGE_15H_PRODUCTION_RUNBOOK_RU.md`. Каждый шаг ждёт вашего явного «да»; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне, секреты в чат не вставлять. **Все шаги — в чистой новой SSH-сессии** (бэкапа здесь нет; первая строка каждого блока проверяет, что лишних переменных 0).

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
```

## 1. Что выкладывается (production `30ba850` → `origin/stage-15`)

Найдено вами на проверке 15H.1: для разных дефектов предлагается одна и та же работа, карточки выглядят как дубли (не видно ни стены, ни дефекта), а «Dodaj do prac» каждый раз дописывает работу в план ещё раз — в смете она окажется несколько раз. Вариант A (ваше решение): показать стену и причину, предупреждать, что работа уже в плане стены или предлагается другой карточкой, и спрашивать подтверждение перед повторным добавлением. Правило Stage 10 «дубли разрешены» (например, два слоя) не меняется.

| Часть | Изменение | Риск |
|---|---|---|
| Миграция | **нет**; `alembic current` остаётся `0038_issued_documents` | — |
| Backend (3 файла приложения) | `api/v1/endpoints/work_recommendations.py`, `domain/services/work_recommendation_service.py`, `schemas/work_recommendation.py`: каждая карточка получает только для чтения: стену (`surface_name`, `surface_type`), причину (`reason_key`), число вхождений работы в плане стены (`in_plan_count`) и число других живых карточек с той же работой (`same_work_other_cards`). Ничего не записывается; число запросов к БД не зависит от числа карточек (до 5 дополнительных запросов на список) | низкий |
| Frontend | на карточке рекомендации: «Powierzchnia: …» и «Powód: …» на языке интерфейса; жёлтая пометка «уже в плане стены (N×)» или «ту же работу предлагает и другая карточка»; при «Dodaj do prac» для работы, уже стоящей в плане, — подтверждение «Dodać jeszcze raz?» с кнопками «Dodaj jeszcze raz» / «Anuluj»; после добавления список перечитывается, остальные карточки узнают, что работа в плане | низкий |
| Compose / Caddy / Dockerfile / зависимости / `app/backup` | **без изменений** — проверяется A0 | — |
| Образы бэкапа | **пересборка не нужна** (голова `0038` и код бэкапа не меняются) | — |

Откат: миграции нет; образы `:pre-15h2` возвращаются в любой момент (раздел 4).

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
git fetch origin stage-15
git merge-base --is-ancestor HEAD origin/stage-15 && echo "HEAD — предок origin/stage-15: ДА" || echo "HEAD — предок origin/stage-15: НЕТ"
echo "--- инфраструктура (должно быть пусто) ---"
git diff --name-only HEAD origin/stage-15 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile backend/app/backup backend/alembic
echo "--- файлы backend/app (ожидаем 3) ---"
git diff --name-only HEAD origin/stage-15 -- backend/app
```
**PASS:** `0` лишних переменных; дерево чистое, ветка `stage-15`, коммит `30ba850` (или более поздний документальный); 4 контейнера `Up`/healthy; `alembic current` = `0038_issued_documents`; health ok; свободно ≥ 5 ГБ; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`; «предок: ДА»; блок «инфраструктура» **пуст**; в `backend/app` ровно 3 файла: `api/v1/endpoints/work_recommendations.py`, `domain/services/work_recommendation_service.py`, `schemas/work_recommendation.py`.

### A1 — получить код → «да, A1»
```bash
git pull --ff-only origin stage-15
git log --oneline -1
git status --short
```
**PASS:** fast-forward; верхний коммит = `origin/stage-15` (хеш назову после A0); дерево чистое.

### A2 — конфигурация и сборка (старый production работает) → «да, A2»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-15h2
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-15h2
PC build backend frontend 2>&1 | tail -n 8
PC ps
df -h / | tail -1
```
**PASS:** `0` лишних переменных; `CONFIG-OK`; обе сборки без ошибок (слои с системными библиотеками и зависимостями берутся из кэша — сборка заметно быстрее, чем на 15H); контейнеры `Up`; свободно ≥ 4 ГБ.

### A3 — применить backend → «да, A3» (миграции нет: ВОРОТА M не нужны)
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps backend
sleep 25
docker exec plan_estimate_backend alembic current
docker logs plan_estimate_backend --tail 20
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET); print('endpoint:', str(s.MEDIA_S3_ENDPOINT_URL).split('//')[-1].split('.')[-3:]); print('доставка документов:', s.DOCUMENT_DELIVERY)"
```
**PASS:** `0` лишних переменных; `current` = `0038_issued_documents` (в логе **нет** строки `Running upgrade`); нет ошибок, видно `Application startup complete`; health ok; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`, endpoint `r2`, `cloudflarestorage`, `com`; доставка `telegram`.

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

### A6 — проверка на телефоне (владелец, ~10 минут; PL, затем RU)
Нужен завершённый осмотр, у которого **две рекомендации просят одну и ту же работу на одной стене** (разные дефекты) — как на вашем тестовом объекте. Если такого нет, подойдёт любой осмотр с рекомендациями: пункты 1 и 2 проверяются на любых карточках.
1. В осмотре откройте «Zalecane prace» (после «Oceń ponownie»). На **каждой** карточке теперь написано: «Powierzchnia: Ściana 1» (по-русски «Поверхность: Стена 1», без «Wall 1») и «Powód: …» (название дефекта на языке интерфейса).
2. Две карточки с одной работой на одной стене: у каждой жёлтая пометка «Tę samą pracę proponuje też inna karta dla tej powierzchni — dodaj ją tylko raz, chyba że potrzebne są dwie warstwy».
3. Нажмите «Dodaj do prac» на **первой** карточке: работа добавляется, как раньше («Praca dodana do planu…»). Список обновляется, у **второй** карточки пометка меняется на «Ta praca jest już w planie tej powierzchni (1×)».
4. Нажмите «Dodaj do prac» на второй карточке: **сначала** появляется вопрос «Dodać tę pracę jeszcze raz? W kosztorysie pojawi się ona kilka razy.» с кнопками «Dodaj jeszcze raz» и «Anuluj» (во всю ширину, ≥ 44 px). «Anuluj» закрывает вопрос и ничего не добавляет; «Dodaj jeszcze raz» добавляет вторую порцию (на принятых карточках появляется «… (2×)»).
5. «Odrzuć» (в «Opcje») второй карточки вместо добавления: пометка «inna karta» у первой исчезает.
6. Карточка без дубля выглядит и работает как раньше: «Dodaj do prac» добавляет сразу, без вопроса.
7. 320–412 px, PL и RU: стена, причина, пометки и вопрос не режутся, горизонтальной прокрутки нет.

## 3. Оценка риска
- **Данные:** миграции нет, записей не меняется; новые поля карточек — только чтение (до 5 дополнительных запросов на список, не зависят от числа карточек).
- **Совместимость:** старые поля карточек сохранены; новый frontend со старым backend не используется (порядок A3 → A4), а старый frontend (в кэше WebView) игнорирует новые поля.
- **Хранилище:** ключ приложения не меняется.

## 4. Откат
| Ситуация | Действие |
|---|---|
| Backend не стартует после A3 | `docker logs plan_estimate_backend --tail 100`; `docker tag plan-estimate-backend:pre-15h2 plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` |
| Сломался frontend | `docker tag plan-estimate-frontend:pre-15h2 plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| Любое сомнение с данными | остановиться, прислать вывод; `down -v` — **никогда** |

## 5. После выкладки
Stage 15 закрывается после вашей проверки A6: запись приёмки в `docs/development-progress.md`, затем (отдельным вашим «да») слияние `stage-15` в `main` и перевод VM на `main`. После этого по Stage 15 остаётся только очистка старых откатных тегов (раздел 6 основного runbook 15H).
