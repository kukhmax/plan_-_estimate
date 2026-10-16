#!/usr/bin/env bash
# Stage 19 — выкладка работы без связи (19B–19F): новый backend (id телефона в создающих запросах, момент нажатия у статусов работ) + новый frontend
# (IndexedDB, очередь изменений и фото, экран «Synchronizacja») + кнопка Telegram. МИГРАЦИЙ НЕТ: голова остаётся 0055_project_notes.
# Меняются backend/app, frontend/src и два пакета frontend (idb в dependencies, fake-indexeddb только для тестов) — поэтому скрипт ПОЛНЫЙ (frontend-only скрипт Stage 18 тут не годится).
# Цикл сообщений календаря этим скриптом НЕ трогается: остаётся таким, каким он сейчас в .env.production (скрипт проверяет, что он после выкладки в том же состоянии).
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому старый код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin stage-19 && git show origin/stage-19:docs/STAGE_19_DEPLOY_RU.sh > ~/deploy19.sh && bash ~/deploy19.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
R="$HOME/backups/plan-estimate/db-backup"
BR="${DEPLOY19_BRANCH:-stage-19}"

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
has '0055_project_notes' "$AL" || fail "G0" "alembic current не 0055_project_notes: $AL (в этом релизе миграций нет: база должна быть на 0055 уже сейчас)"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
# бэкап: миграции нет, откат образов не требует копии; но свежая копия перед любой выкладкой — хорошая привычка (только предупреждение)
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
if [ -n "$LASTRUN" ]; then
  AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
  echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
  [ "$AGE_H" -le 168 ] || echo "ВНИМАНИЕ: последний бэкап старше недели. Миграции нет, выкладка не меняет данные, но свежая копия желательна: BACKUP_BRANCH=main BACKUP_HEAD=0055_project_notes bash ~/backup_a9.sh (в НОВОЙ сессии)."
else
  echo "ВНИМАНИЕ: бэкапов в $R/data/encrypted нет (справочно; выкладка данные не меняет)."
fi
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
NEWMIG=$(git diff --name-only --diff-filter=AMD HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
[ -z "$NEWMIG" ] || fail "G0" "в релизе не должно быть изменений в миграциях, а они есть: $NEWMIG"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/Dockerfile.prod backend/app/backup docker-compose.prod.yml .env.production.example)
[ -z "$INFRA" ] || fail "G0" "Изменились образы/зависимости backend/бэкап/compose (этого релиза там быть не должно): $INFRA"
PKG=$(git diff -U0 HEAD "origin/$BR" -- frontend/package.json | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' | sed -E 's/^([+-])\s*/\1/' | sort || true)
[ "$PKG" = "$(printf '+"fake-indexeddb": "6.2.5",\n+"idb": "8.0.4",')" ] || fail "G0" "frontend/package.json изменён не так, как ожидается (только добавлены idb 8.0.4 и fake-indexeddb 6.2.5): $PKG"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(backend/app/|backend/tests/|frontend/src/|frontend/package\.json$|frontend/package-lock\.json$|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/документы/фото = $BEFORE"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
# до ворот M production не меняется: при любом отказе в G1 код на VM возвращается на прежнюю ветку
fail1() { git checkout -q "$PREV" 2>/dev/null; fail "$1" "$2 (код на VM возвращён на ветку $PREV)"; }
git checkout -q -B "$BR" "origin/$BR" || fail1 "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-19  || fail1 "G1" "тег pre-19 backend"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-19 || fail1 "G1" "тег pre-19 frontend"
PC build backend frontend > /tmp/build19.log 2>&1 || { tail -n 30 /tmp/build19.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-19)"

echo; echo "################ ВОРОТА M: пересоздание контейнеров ################"
echo "Релиз Stage 19: миграций НЕТ (база остаётся на 0055_project_notes), данные не меняются."
echo "  • Backend пересоздаётся: простой API около 30–60 секунд; цикл календаря перезапускается сам, если он включён ($LOOP_ENV)."
echo "  • Frontend пересоздаётся: открытое приложение у пользователя подхватит новую сборку при следующем открытии (кнопка Telegram получит новый ?v=$NEW)."
echo "  • Откат — ОБОИХ образов сразу (см. сообщение об ошибке): новый frontend со старым backend не работает с работой без связи (старый backend отвечает 422 на статус работы с recorded_at)."
echo "  • Отказ на этих воротах возвращает код на ветку $PREV; ничего не меняется."
echo
echo "Чтобы пересоздать контейнеры, введите ТОЧНО:  ВЫКЛАДКА STAGE 19 ДА"
echo "Любой другой ввод останавливает выкладку; в production ничего не изменено (образы собраны, старая версия работает)."
printf '> '
read -r ANSWER < "${DEPLOY19_TTY:-/dev/tty}" || { git checkout -q "$PREV"; fail "M" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на ветку $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА STAGE 19 ДА" ] || { echo; git checkout -q "$PREV"; echo "Остановлено на воротах M (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на ветку $PREV."; exit 1; }
ok "M (подтверждено вами)"

ROLLALL="Откат (оба образа): docker tag plan-estimate-backend:pre-19 plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-19 plan-estimate-frontend:latest && docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps --no-build backend frontend"

echo; echo "################ G2: backend (без миграций) ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend --tail 120 2>&1)
has "Running upgrade" "$LOG" && fail "G2" "в логе применяется миграция, а в этом релизе миграций нет. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0055_project_notes' "$AL2" || fail "G2" "alembic не 0055. $ROLLALL"
SCH=$(docker exec plan_estimate_backend python -c "
from app.schemas.inspection import InspectionCreate
from app.schemas.room import RoomCreate
from app.schemas.surface import SurfaceCreate
from app.schemas.opening import OpeningCreate
from app.schemas.area_segment import AreaSegmentCreate
from app.schemas.project_note import ProjectNoteCreate
from app.schemas.work_plan import SurfaceWorkExecutionTransition
print(all('id' in m.model_fields for m in (InspectionCreate, RoomCreate, SurfaceCreate, OpeningCreate, AreaSegmentCreate, ProjectNoteCreate)), 'recorded_at' in SurfaceWorkExecutionTransition.model_fields)")
[ "$SCH" = "True True" ] || fail "G2" "в контейнере нет id телефона в создающих схемах или recorded_at у статуса работы: $SCH. $ROLLALL"
RULE=$(docker exec plan_estimate_backend python -c "
from datetime import datetime, timedelta, timezone
from app.domain.rules.work_execution_rules import resolve_moment
now = datetime.now(timezone.utc)
print(resolve_moment(now - timedelta(hours=3), now, None) == now - timedelta(hours=3), resolve_moment(now + timedelta(hours=3), now, None) == now, resolve_moment(now - timedelta(days=30), now, None) == now)")
[ "$RULE" = "True True True" ] || fail "G2" "правило момента нажатия работает не так: $RULE. $ROLLALL"
CAT=$(docker exec plan_estimate_backend python -c "from app.domain.knowledge.catalog import load_knowledge_catalog as l; c=l(); print(len(c.sources), len(c.entries), len(c.links), len(c.situations), c.meta.version)")
echo "каталог знаний (источники статьи связи ситуации версия): $CAT"
[ "$CAT" = "13 34 51 8 5" ] || fail "G2" "каталог не 13 34 51 8 5. $ROLLALL"
TXT=$(docker exec plan_estimate_backend python -c "from app.domain.calendar.messages import load_texts; print(len(load_texts().titles))")
[ "$TXT" = "17" ] || fail "G2" "тексты календаря: $TXT заголовков вместо 17. $ROLLALL"
API=$(docker exec plan_estimate_backend python -c "from app.main import app; p=app.openapi()['paths']; print('/api/calendar' in p, '/api/projects/{project_id}/schedule' in p, '/api/projects/{project_id}/notes' in p, '/api/projects/{project_id}/rooms/{room_id}/inspections' in p)")
[ "$API" = "True True True True" ] || fail "G2" "в API нет ожидаемых маршрутов: $API. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
if [ "$LOOP_ENV" = "true" ]; then
  # INFO-строки приложения в docker logs не попадают (в приложении нет настройки logging, видны только строки uvicorn и ERROR/WARNING),
  # поэтому «calendar loop started» искать нельзя. Цикл не запускается только в одном случае — нет токена бота — и тогда в лог идёт ERROR.
  has "calendar loop is not started" "$LOG" && fail "G2" "цикл календаря включён, но не запущен (нет токена бота). $ROLLALL"
  TOK=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(bool(s.TELEGRAM_BOT_TOKEN))")
  [ "$TOK" = "True" ] || fail "G2" "цикл календаря включён, а токена бота в контейнере нет: $TOK. $ROLLALL"
fi
KEY=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print(k[:6]+'…'+k[-4:], s.MEDIA_S3_BUCKET, s.DOCUMENT_DELIVERY)")
[ "$KEY" = "97bfe5…6dab plan-estimate-media-prod telegram" ] || fail "G2" "ключ/бакет/доставка не те: $KEY. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ok "G2 (backend: id телефона и recorded_at на месте, правило момента верно, база на 0055, данные те же, цикл календаря как был: $LOOP_ENV)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
has 'plan-estimate-offline' "$BUNDLE" || fail "G3" "в выданной сборке нет базы работы без связи (plan-estimate-offline). $ROLLALL"
has 'CHANGES_WAITING' "$BUNDLE" || fail "G3" "в выданной сборке нет защиты «сначала отправить ожидающие изменения». $ROLLALL"
has 'sync-screen' "$BUNDLE" || fail "G3" "в выданной сборке нет экрана синхронизации. $ROLLALL"
has 'show-calendar' "$BUNDLE" || fail "G3" "в выданной сборке пропал пункт «Календарь». $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend с работой без связи, экраном синхронизации и прежним календарём)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена, миграций не было, база на 0055 ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) ПОЛНОСТЬЮ закройте Telegram (смахнуть из недавних), откройте Mini App по кнопке меню и пройдите сценарий «режим полёта» из раздела 6 STAGE_19_PRODUCTION_RUNBOOK_RU.md;"
echo "  2) бэкап под текущий код (по желанию, но разумно после первой недели): BACKUP_BRANCH=stage-19 BACKUP_HEAD=0055_project_notes bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  3) приёмка: «принимаем Stage 19» — слияние stage-19 → main и переключение VM на main только по отдельному «да»."
)
