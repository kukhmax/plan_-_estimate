#!/usr/bin/env bash
# Stage 18 — выкладка календаря и напоминаний (18C + 18D + 18E): миграция 0054, backend, frontend, кнопка Telegram.
# Цикл отправки сообщений остаётся ВЫКЛЮЧЕННЫМ (CALENDAR_DISPATCHER_ENABLED=false): его включает отдельный скрипт STAGE_18_ENABLE_LOOP_RU.sh после вашей проверки.
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Ворота M: миграция применяется только после того, как вы САМИ введёте подтверждение.
# Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому старый код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin stage-18 && git show origin/stage-18:docs/STAGE_18_DEPLOY_RU.sh > ~/deploy18.sh && bash ~/deploy18.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
R="$HOME/backups/plan-estimate/db-backup"

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
has '0053_downtime_episodes' "$AL" || fail "G0" "alembic current не 0053_downtime_episodes: $AL"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
# бэкап (A9) должен быть сделан НЕДАВНО: миграция не применяется без свежей копии
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
[ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9 (docs/STAGE_18_BACKUP_A9_RU.sh)"
AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
[ "$AGE_H" -le 72 ] || fail "G0" "последний бэкап $LASTRUN старше 72 часов (${AGE_H} ч): сначала A9"
echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
git fetch -q origin stage-18 || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD origin/stage-18 || fail "G0" "HEAD не предок origin/stage-18"
INFRA=$(git diff --name-only HEAD origin/stage-18 -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod backend/app/backup)
[ -z "$INFRA" ] || fail "G0" "Изменились образы/зависимости/бэкап (этого релиза там быть не должно): $INFRA"
NEWMIG=$(git diff --name-only --diff-filter=A HEAD origin/stage-18 -- backend/alembic/versions | grep -v '__pycache__' || true)
[ "$NEWMIG" = "backend/alembic/versions/0054_calendar_reminders.py" ] || fail "G0" "ожидается ровно одна новая миграция 0054_calendar_reminders.py, а пришло: $NEWMIG"
CHGMIG=$(git diff --name-only --diff-filter=MD HEAD origin/stage-18 -- backend/alembic/versions | grep -v '__pycache__' || true)
[ -z "$CHGMIG" ] || fail "G0" "существующие миграции изменены или удалены: $CHGMIG"
BADALL=$(git diff --name-only HEAD origin/stage-18 | grep -Ev '^(backend/app/|backend/alembic/versions/0054_calendar_reminders\.py$|backend/tests/|frontend/src/|docs/|docker-compose\.prod\.yml$|\.env\.production\.example$)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
CMP=$(git diff -U0 HEAD origin/stage-18 -- docker-compose.prod.yml | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' | grep -vE 'CALENDAR_|^\+\s*#|^\+\s*$' || true)
[ -z "$CMP" ] || fail "G0" "в docker-compose.prod.yml изменено не только календарное: $CMP"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN (адрес кнопки в сообщениях строится из него)"
echo "домен приложения: $DOMAIN; CALENDAR_DISPATCHER_ENABLED в .env.production: $(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production || echo 'нет (по умолчанию false)')"
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/документы/фото = $BEFORE"
echo "приходит:"; git log --oneline HEAD..origin/stage-18 | head -30
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
git checkout -q -B stage-18 origin/stage-18 || fail "G1" "переключение на stage-18 не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка stage-18)"
PC config --quiet || fail "G1" "docker compose config не прошёл"
CFGURL=$(PC config | grep 'CALENDAR_WEB_APP_URL' | head -1 | sed -E 's/.*CALENDAR_WEB_APP_URL: *//; s/"//g')
[ "$CFGURL" = "https://$DOMAIN" ] || fail "G1" "адрес кнопки в compose: '$CFGURL', ожидалось https://$DOMAIN (вложенная подстановка не сработала: задайте CALENDAR_WEB_APP_URL в .env.production)"
CFGON=$(PC config | grep 'CALENDAR_DISPATCHER_ENABLED' | head -1 | sed -E 's/.*CALENDAR_DISPATCHER_ENABLED: *//; s/"//g')
[ "$CFGON" = "false" ] || fail "G1" "CALENDAR_DISPATCHER_ENABLED в compose = '$CFGON', ожидалось false при выкладке"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-18  || fail "G1" "тег pre-18 backend"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-18 || fail "G1" "тег pre-18 frontend"
PC build backend frontend > /tmp/build18.log 2>&1 || { tail -n 30 /tmp/build18.log; fail "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка, теги pre-18; адрес кнопки https://$DOMAIN, цикл выключен)"

echo; echo "################ ВОРОТА M: миграция базы данных ################"
echo "Миграция 0054_calendar_reminders (проверена на PostgreSQL 16: вверх, вниз, вверх):"
echo "  • СОЗДАЁТ три новые таблицы: work_schedule (плановые даты работ), reminders (очередь напоминаний), calendar_settings (настройки). Существующие таблицы и данные НЕ меняются."
echo "  • Время: миллисекунды (таблицы пустые); одна транзакция: при ошибке откат целиком."
echo "  • Простой API при пересоздании контейнера backend: около 30–60 секунд. Фото и база не затрагиваются."
echo "  • Откат: образ backend откатывается командой из сообщения об ошибке (старый код новых таблиц не знает и не трогает — это безопасно). Откат самой миграции (alembic downgrade) НЕ нужен и отказывает, пока в таблицах есть ваши данные."
echo "  • Бэкап перед миграцией: $LASTRUN (${AGE_H} ч назад)."
echo "  • Отказ на этих воротах возвращает код на ветку $PREV; ничего не меняется."
echo
echo "Чтобы применить миграцию и пересоздать backend, введите ТОЧНО:  МИГРАЦИЯ 0054 ДА"
echo "Любой другой ввод останавливает выкладку; в production ничего не изменено (образы собраны, старая версия работает)."
printf '> '
read -r ANSWER < "${DEPLOY18_TTY:-/dev/tty}" || { git checkout -q "$PREV"; fail "M" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на ветку $PREV)"; }
[ "$ANSWER" = "МИГРАЦИЯ 0054 ДА" ] || { echo; git checkout -q "$PREV"; echo "Остановлено на воротах M (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на ветку $PREV."; exit 1; }
ok "M (подтверждено вами)"

echo; echo "################ G2: backend + миграция ################"
ROLLB="Откат backend:  docker tag plan-estimate-backend:pre-18 plan-estimate-backend:latest && docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps --no-build backend"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLB"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLB"; }
LOG=$(docker logs plan_estimate_backend --tail 120 2>&1)
has "Running upgrade 0053_downtime_episodes -> 0054_calendar_reminders" "$LOG" || fail "G2" "в логе нет применения миграции 0053 -> 0054. $ROLLB"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLB"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLB"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0054_calendar_reminders' "$AL2" || fail "G2" "alembic не 0054. $ROLLB"
TBL=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"select count(*) from information_schema.tables where table_name in ('work_schedule','reminders','calendar_settings')\"")
[ "$TBL" = "3" ] || fail "G2" "новых таблиц $TBL из 3. $ROLLB"
CAT=$(docker exec plan_estimate_backend python -c "from app.domain.knowledge.catalog import load_knowledge_catalog as l; c=l(); print(len(c.sources), len(c.entries), len(c.links), len(c.situations), c.meta.version)")
echo "каталог знаний (источники статьи связи ситуации версия): $CAT"
[ "$CAT" = "13 34 51 8 5" ] || fail "G2" "каталог не 13 34 51 8 5. $ROLLB"
TXT=$(docker exec plan_estimate_backend python -c "from app.domain.calendar.messages import load_texts; print(len(load_texts().titles))")
[ "$TXT" = "17" ] || fail "G2" "тексты календаря: $TXT заголовков вместо 17. $ROLLB"
API=$(docker exec plan_estimate_backend python -c "from app.main import app; p=app.openapi()['paths']; print('/api/calendar' in p, '/api/projects/{project_id}/schedule' in p)")
[ "$API" = "True True" ] || fail "G2" "в API нет маршрутов календаря: $API. $ROLLB"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(s.CALENDAR_DISPATCHER_ENABLED, s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "False https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось 'False https://$DOMAIN'. $ROLLB"
echo "$LOG" | grep -q "calendar loop started" && fail "G2" "цикл отправки запущен, а должен быть выключен. $ROLLB"
KEY=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print(k[:6]+'…'+k[-4:], s.MEDIA_S3_BUCKET, s.DOCUMENT_DELIVERY)")
[ "$KEY" = "97bfe5…6dab plan-estimate-media-prod telegram" ] || fail "G2" "ключ/бакет/доставка не те: $KEY. $ROLLB"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLB"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLB"
ok "G2 (миграция 0054 применена, 3 таблицы, каталог 13/34/51/8/v5, тексты 17, маршруты календаря, цикл выключен, данные те же)"

echo; echo "################ G3: frontend ################"
ROLLF="Откат frontend:  docker tag plan-estimate-frontend:pre-18 plan-estimate-frontend:latest && docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps --no-build frontend"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLF"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLF"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLF"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLF"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
[ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" | grep -q 'show-calendar' || fail "G3" "в выданной сборке нет пункта меню «Календарь». $ROLLF"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLF"
ok "G3 (frontend с пунктом «Календарь»)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена, миграция 0054 применена, цикл сообщений ВЫКЛЮЧЕН ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) закройте Telegram полностью, откройте Mini App, пройдите чек-лист на телефоне (раздел 6 STAGE_18_PRODUCTION_RUNBOOK_RU.md);"
echo "  2) бэкап под новую голову: BACKUP_BRANCH=stage-18 BACKUP_HEAD=0054_calendar_reminders bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  3) включение цикла сообщений: STAGE_18_ENABLE_LOOP_RU.sh (отдельное ваше «да»)."
)
