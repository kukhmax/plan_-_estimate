#!/usr/bin/env bash
# Архивная чистка AC-1…AC-3 + подписи на экране «Synchronizacja» (19H) — выкладка: миграции 0056 и 0057, backend, frontend, кнопка Telegram.
# Что приходит: корзина для фото (AC-1), окончательное удаление фото из корзины (AC-2), инструменты чистки бэкапа и ledger-aware verify / restore (AC-3, образы бэкапа
# перестраивает следующий запуск бэкапа A9), слова вместо кодов на экране «Synchronizacja» (19H). Ничего не УДАЛЯЕТСЯ этой выкладкой: миграции только добавляют колонку, индекс и пустую таблицу.
# Цикл сообщений календаря этим скриптом НЕ трогается: остаётся таким, каким он сейчас в .env.production (скрипт проверяет, что он после выкладки в том же состоянии).
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Ворота M: миграции применяются только после того, как вы САМИ введёте фразу.
# Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому старый код на VM не меняется до проверок), ПОСЛЕ свежего бэкапа A9 (раздел 2 runbook):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-archive-cleanup && git show origin/backlog-archive-cleanup:docs/ARCHIVE_CLEANUP_DEPLOY_RU.sh > ~/deploy_ac.sh && bash ~/deploy_ac.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
R="$HOME/backups/plan-estimate/db-backup"
BR="${DEPLOYAC_BRANCH:-backlog-archive-cleanup}"
COMPOSE="docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml"

echo "################ G0: проверка перед выкладкой (только чтение) ################"
echo "--- ресурсы сервера (справочно) ---"
echo "процессоров: $(nproc); память МБ (всего/занято/свободно): $(free -m | awk '/^Mem:/ {print $2"/"$3"/"$4}'); swap МБ: $(free -m | awk '/^Swap:/ {print $2}'); архитектура: $(uname -m)"
docker stats --no-stream --format '  {{.Name}}: память {{.MemUsage}} ({{.MemPerc}}), процессор {{.CPUPerc}}' 2>/dev/null || true
[ "$(env | grep -c '^MEDIA_S3\|^BACKUP_')" = "0" ] || fail "G0" "В оболочке лишние переменные MEDIA_S3/BACKUP_. Откройте новую SSH-сессию (не ту, где шёл бэкап)."
[ -z "$(git status --short)" ] || fail "G0" "Рабочее дерево не чистое: $(git status --short)"
PREV=$(git branch --show-current); [ -n "$PREV" ] || fail "G0" "VM в состоянии detached HEAD: сначала вернитесь на ветку"
echo "ветка на VM сейчас: $PREV, коммит $(git rev-parse --short HEAD)"
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "G0" "health недоступен"
has '"status":"ok"' "$H" || fail "G0" "health не ok до выкладки: $H"
AL=$(docker exec plan_estimate_backend alembic current 2>/dev/null)
has '0055_project_notes' "$AL" || fail "G0" "alembic current не 0055_project_notes: $AL (выкладка рассчитана на базу ровно на 0055)"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
# бэкап (A9) должен быть сделан НЕДАВНО: миграция не применяется без свежей копии
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
[ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9 (см. раздел 2 runbook)"
AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
[ "$AGE_H" -le 72 ] || fail "G0" "последний бэкап $LASTRUN старше 72 часов (${AGE_H} ч): сначала A9 (раздел 2 runbook)"
echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod docker-compose.prod.yml .env.production.example)
[ -z "$INFRA" ] || fail "G0" "Изменились образы/зависимости/compose (этого релиза там быть не должно): $INFRA"
NEWMIG=$(git diff --name-only --diff-filter=A HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
[ "$NEWMIG" = "$(printf 'backend/alembic/versions/0056_photo_trash.py\nbackend/alembic/versions/0057_purge_ledger.py')" ] || fail "G0" "ожидаются ровно две новые миграции (0056_photo_trash.py, 0057_purge_ledger.py), а пришло: $NEWMIG"
CHGMIG=$(git diff --name-only --diff-filter=MD HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
[ -z "$CHGMIG" ] || fail "G0" "существующие миграции изменены или удалены: $CHGMIG"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(backend/app/|backend/alembic/versions/005[67]_[a-z_]+\.py$|backend/tests/|backend/scripts/|frontend/src/|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments; select count(*) from photo_assets; select count(*) from photo_annotations;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/документы/привязки фото/файлы фото/метки = $BEFORE"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
# до ворот M production не меняется: при любом отказе в G1 код на VM возвращается на прежнюю ветку
fail1() { git checkout -q "$PREV" 2>/dev/null; fail "$1" "$2 (код на VM возвращён на ветку $PREV)"; }
git checkout -q -B "$BR" "origin/$BR" || fail1 "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-ac  || fail1 "G1" "тег pre-ac backend"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-ac || fail1 "G1" "тег pre-ac frontend"
PC build backend frontend > /tmp/build_ac.log 2>&1 || { tail -n 30 /tmp/build_ac.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-ac)"

echo; echo "################ ВОРОТА M: миграции базы данных ################"
echo "Миграции 0056_photo_trash и 0057_purge_ledger (проверены на PostgreSQL 16: вверх, вниз, вверх; настоящее удаление фото с внешними ключами):"
echo "  • 0056: ДОБАВЛЯЕТ в photo_attachments одну пустую колонку trashed_at, проверку «в корзине только архивное» и индекс; существующие строки не меняются."
echo "  • 0057: СОЗДАЁТ новую пустую таблицу purge_ledger (реестр удалённых фото); без внешних ключей."
echo "  • Время: миллисекунды; каждая миграция — в одной транзакции: при ошибке откат целиком."
echo "  • Простой API при пересоздании контейнера backend: около 30–60 секунд. Фото и файлы не затрагиваются; НИЧЕГО не удаляется."
echo "  • ОТКАТ ИМЕЕТ ПОРЯДОК: старый образ backend НЕ запустится на базе с новыми миграциями (alembic не знает версию 0057). Сначала миграции откатываются командой из сообщения об ошибке"
echo "    (без потерь; откат 0057 отказывается, пока в реестре есть записи — то есть пока не было настоящего удаления фото), потом возвращается образ."
echo "  • Бэкап перед миграциями: $LASTRUN (${AGE_H} ч назад)."
echo "  • Отказ на этих воротах возвращает код на ветку $PREV; ничего не меняется."
echo
echo "Чтобы применить миграции и пересоздать backend, введите ТОЧНО:  МИГРАЦИИ 0056 0057 ДА"
echo "Любой другой ввод останавливает выкладку; в production ничего не изменено (образы собраны, старая версия работает)."
printf '> '
read -r ANSWER < "${DEPLOYAC_TTY:-/dev/tty}" || { git checkout -q "$PREV"; fail "M" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на ветку $PREV)"; }
[ "$ANSWER" = "МИГРАЦИИ 0056 0057 ДА" ] || { echo; git checkout -q "$PREV"; echo "Остановлено на воротах M (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на ветку $PREV."; exit 1; }
ok "M (подтверждено вами)"

ROLLALL="Откат (ПОРЯДОК ВАЖЕН): 1) $COMPOSE run --rm --no-deps --entrypoint alembic backend downgrade 0055_project_notes   2) docker tag plan-estimate-backend:pre-ac plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-ac plan-estimate-frontend:latest   3) $COMPOSE up -d --no-deps --no-build backend frontend"

echo; echo "################ G2: backend + миграции ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend --tail 120 2>&1)
has "Running upgrade 0055_project_notes -> 0056_photo_trash" "$LOG" || fail "G2" "в логе нет применения миграции 0055 -> 0056. $ROLLALL"
has "Running upgrade 0056_photo_trash -> 0057_purge_ledger" "$LOG" || fail "G2" "в логе нет применения миграции 0056 -> 0057. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0057_purge_ledger' "$AL2" || fail "G2" "alembic не 0057. $ROLLALL"
DBX=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"select (select count(*) from information_schema.columns where table_name='photo_attachments' and column_name='trashed_at'), (select count(*) from pg_constraint where conname='ck_photo_attachments_trashed_is_archived'), (select count(*) from pg_indexes where indexname='ix_photo_attachments_project_trashed'), (select count(*) from information_schema.tables where table_name='purge_ledger'), (select count(*) from purge_ledger)\"")
[ "$DBX" = "1|1|1|1|0" ] || fail "G2" "схема после миграций не та (колонка|проверка|индекс|таблица|строк в реестре): '$DBX', ожидалось 1|1|1|1|0. $ROLLALL"
SCH=$(docker exec plan_estimate_backend python -c "
from app.schemas.inspection import InspectionCreate
from app.schemas.room import RoomCreate
from app.schemas.surface import SurfaceCreate
from app.schemas.opening import OpeningCreate
from app.schemas.area_segment import AreaSegmentCreate
from app.schemas.project_note import ProjectNoteCreate
from app.schemas.work_plan import SurfaceWorkExecutionTransition
print(all('id' in m.model_fields for m in (InspectionCreate, RoomCreate, SurfaceCreate, OpeningCreate, AreaSegmentCreate, ProjectNoteCreate)), 'recorded_at' in SurfaceWorkExecutionTransition.model_fields)")
[ "$SCH" = "True True" ] || fail "G2" "работа без связи (Stage 19) в backend нарушена: $SCH. $ROLLALL"
CAT=$(docker exec plan_estimate_backend python -c "from app.domain.knowledge.catalog import load_knowledge_catalog as l; c=l(); print(len(c.sources), len(c.entries), len(c.links), len(c.situations), c.meta.version)")
echo "каталог знаний (источники статьи связи ситуации версия): $CAT"
[ "$CAT" = "13 34 51 8 5" ] || fail "G2" "каталог не 13 34 51 8 5. $ROLLALL"
TXT=$(docker exec plan_estimate_backend python -c "from app.domain.calendar.messages import load_texts; print(len(load_texts().titles))")
[ "$TXT" = "17" ] || fail "G2" "тексты календаря: $TXT заголовков вместо 17. $ROLLALL"
API=$(docker exec plan_estimate_backend python -c "
from app.main import app
p = app.openapi()['paths']
need = ['/api/calendar', '/api/projects/{project_id}/notes', '/api/projects/{project_id}/photo-attachments/{attachment_id}/trash', '/api/projects/{project_id}/photo-attachments/{attachment_id}/untrash', '/api/projects/{project_id}/photo-attachments/{attachment_id}/purge-preview', '/api/projects/{project_id}/photo-attachments/{attachment_id}/purge', '/api/photo-purge/status', '/api/photo-purge/retry']
print(all(n in p for n in need))")
[ "$API" = "True" ] || fail "G2" "в API нет маршрутов корзины / удаления / календаря: $API. $ROLLALL"
PURGER=$(docker exec plan_estimate_backend python -c "from app.api.deps import get_media_purger; print(type(get_media_purger()).__name__)")
[ "$PURGER" = "S3MediaPurger" ] || fail "G2" "порт удаления файлов не S3MediaPurger: $PURGER (удаление фото в R2 не заработает). $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
if [ "$LOOP_ENV" = "true" ]; then
  # INFO-строки приложения в docker logs не попадают (нет настройки logging): цикл не запускается только без токена бота, и тогда в лог идёт ERROR
  has "calendar loop is not started" "$LOG" && fail "G2" "цикл календаря включён, но не запущен (нет токена бота). $ROLLALL"
  TOK=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(bool(s.TELEGRAM_BOT_TOKEN))")
  [ "$TOK" = "True" ] || fail "G2" "цикл календаря включён, а токена бота в контейнере нет: $TOK. $ROLLALL"
fi
KEY=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print(k[:6]+'…'+k[-4:], s.MEDIA_S3_BUCKET, s.DOCUMENT_DELIVERY)")
[ "$KEY" = "97bfe5…6dab plan-estimate-media-prod telegram" ] || fail "G2" "ключ/бакет/доставка не те: $KEY. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ok "G2 (миграции 0056 и 0057 применены, схема, реестр пуст, порт удаления S3, маршруты, цикл календаря как был: $LOOP_ENV, данные те же)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in plan-estimate-offline CHANGES_WAITING sync-screen show-calendar photo-purge-confirm photo-untrash 'Co zostanie usunięte'; do
  has "$MARK" "$BUNDLE" || fail "G3" "в выданной сборке нет '$MARK'. $ROLLALL"
done
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend: корзина, окно «что будет удалено», работа без связи, экран синхронизации, календарь)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена, миграции 0056 и 0057 применены, реестр удалений пуст, данные те же ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram, откройте Mini App по кнопке меню и пройдите чек-лист из раздела 5 docs/ARCHIVE_CLEANUP_RUNBOOK_RU.md (корзина, окно «что будет удалено», подписи на экране синхронизации);"
echo "  2) бэкап под новую голову (образы бэкапа теперь знают реестр удалений): BACKUP_BRANCH=$BR BACKUP_HEAD=0057_purge_ledger bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  3) приёмка: «принимаем» — слияние $BR → main и переключение VM на main только по отдельному «да»;"
echo "  4) настоящее удаление фото и чистка копий в бэкапе — только по docs/ARCHIVE_PURGE_RUNBOOK_RU.md, отдельными шагами с вашим «да»."
)
