#!/usr/bin/env bash
# V2-14a: кнопка «Przenieś do pomieszczeń» в карточке мастера («Linki dla mistrzów»): ответы электрика / сантехника переносятся в «Punkty i trasy» и в материалы помещений — сначала предпросмотр (ничего не пишется), выбор позиции прайса для каждой типовой позиции, потом запись по вашей кнопке; повтор не дублирует — выкладка С ОДНОЙ МИГРАЦИЕЙ 0086 (две НОВЫЕ необязательные колонки `source` у room_points и material_calcs; существующие строки не меняются, у всех NULL = «ввёл владелец»). Вместе с ней выкладывается доработка V2-13 (если ни одна профессия раздела не включена, в помещении нельзя добавить новый расчёт материалов / точку; уже имеющееся видно и правится).
# Что меняется: в карточке мастера, где уже есть ответы, появляется кнопка переноса; перенесённые строки помечены источником, ваши собственные никогда не трогаются; смета не меняется. Откат миграции просто убирает колонки (строки остаются как ваши).
# Откат образами БЕЗОПАСЕН: прежний образ не знает колонки и не мешает ей; теги pre-v214aa. Останавливается на первом непройденном условии (FAIL). Ворота B: контейнеры пересоздаются только после того, как вы САМИ введёте фразу.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin ver-2 && git show origin/ver-2:docs/V2_14A_DEPLOY_RU.sh > ~/deploy_v214a.sh && bash ~/deploy_v214a.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
BR="${DEPLOYV214A_BRANCH:-ver-2}"
R="$HOME/backups/plan-estimate/db-backup"
COMPOSE="docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml"
PSQL() { docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"$1\""; }

echo "################ G0: проверка перед выкладкой (только чтение) ################"
[ "$(env | grep -c '^MEDIA_S3\|^BACKUP_')" = "0" ] || fail "G0" "В оболочке лишние переменные MEDIA_S3/BACKUP_. Откройте новую SSH-сессию (не ту, где шёл бэкап)."
[ -z "$(git status --short)" ] || fail "G0" "Рабочее дерево не чистое: $(git status --short)"
PREV=$(git branch --show-current); [ -n "$PREV" ] || fail "G0" "VM в состоянии detached HEAD: сначала вернитесь на ветку"
PREV_SHA=$(git rev-parse HEAD)
echo "ветка на VM сейчас: $PREV, коммит $(git rev-parse --short HEAD)"
restore() { git checkout -q -B "$PREV" "$PREV_SHA" 2>/dev/null; }
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "G0" "health недоступен"
has '"status":"ok"' "$H" || fail "G0" "health не ok до выкладки: $H"
AL=$(docker exec plan_estimate_backend alembic current 2>/dev/null)
if has '0086_transfer_source' "$AL"; then FIRST=no; echo "повторный запуск: миграция 0086 уже применена"
elif has '0085_trade_links' "$AL"; then FIRST=yes
else fail "G0" "alembic current не 0085_trade_links и не 0086_transfer_source: $AL (этот выпуск ставится на базу V2-14; сначала выложите V2-14)"; fi
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
STRICT_ENV=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower(), bool(s.DATA_KEK.get_secret_value()) if s.DATA_KEK else False)")
[ "$STRICT_ENV" = "true True" ] || fail "G0" "строгое чтение / ключ шифрования в контейнере: '$STRICT_ENV', ожидалось 'true True' (состояние после EN-2b-2)"
# бэкап (A9) не старше суток: миграция добавляет две новые колонки (бэкап под голову 0085_trade_links делается из ветки ver-2, текущий коммит VM)
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
[ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9 (BACKUP_BRANCH=ver-2 BACKUP_COMMIT=$(git rev-parse --short HEAD) BACKUP_HEAD=0085_trade_links bash ~/backup_a9.sh)"
AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
[ "$AGE_H" -le 24 ] || fail "G0" "последний бэкап $LASTRUN старше суток (${AGE_H} ч). Сделайте свежий: cd ~/apps/plan_-_estimate && git fetch -q origin ver-2 && git show origin/ver-2:docs/STAGE_18_BACKUP_A9_RU.sh > ~/backup_a9.sh && BACKUP_BRANCH=ver-2 BACKUP_COMMIT=$(git rev-parse --short HEAD) BACKUP_HEAD=0085_trade_links bash ~/backup_a9.sh (в НОВОЙ сессии, потом закрыть её)"
echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
KEKTXT=$(grep -E '^DATA_KEK=' .env.production | head -1 | cut -d= -f2-)
[ -n "$KEKTXT" ] && [ "$(printf '%s' "$KEKTXT" | base64 -d 2>/dev/null | wc -c)" = "32" ] || fail "G0" "DATA_KEK в .env.production отсутствует или не base64 из 32 байт (ключ НЕ МЕНЯТЬ и не удалять)"
echo "ключ сервера на месте; отпечаток (8 знаков SHA-256): $(printf '%s' "$KEKTXT" | sha256sum | cut -c1-8)"
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod docker-compose.prod.yml .env.production.example)
[ -z "$INFRA" ] || fail "G0" "Изменились образы/зависимости/compose (этого релиза там быть не должно): $INFRA"
NEWMIG=$(git diff --name-only --diff-filter=A HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
CHGMIG=$(git diff --name-only --diff-filter=MD HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
[ -z "$CHGMIG" ] || fail "G0" "существующие миграции изменены или удалены: $CHGMIG"
[ "$NEWMIG" = "backend/alembic/versions/0086_transfer_source.py" ] || [ "$FIRST" = no -a -z "$NEWMIG" ] || fail "G0" "в релизе должна быть ровно одна новая миграция (0086_transfer_source.py), а здесь: '$NEWMIG'"
OTHERALEMBIC=$(git diff --name-only HEAD "origin/$BR" -- backend/alembic | grep -v '__pycache__' | grep -Ev '^backend/alembic/versions/0086_transfer_source.py$' || true)
[ -z "$OTHERALEMBIC" ] || fail "G0" "в alembic изменено что-то кроме миграции 0086: $OTHERALEMBIC"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(README.md|backend/app/|backend/alembic/versions/0086_transfer_source.py|backend/tests/|frontend/src/|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from photo_annotations; select count(*) from material_calcs; select count(*) from material_norms; select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from contracts; select count(*) from handover_protocols; select count(*) from concealed_works_protocols; select count(*) from acceptance_protocols; select count(*) from decision_protocols; select count(*) from downtime_episodes; select count(*) from data_keys; select count(*) from photo_attachments; select count(*) from photo_assets; select count(*) from estimates; select count(*) from calendar_settings; select count(*) from reminders; select count(*) from project_payments; select count(*) from executor_profiles;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
IDOC_BEFORE=$(PSQL "select count(*) from issued_documents")
echo "данные до: клиенты/объекты/журнал/договоры/передачи/скрытые/приёмки/решения/простои/ключи/привязки фото/файлы фото/сметы/настройки календаря/напоминания = $BEFORE"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
fail1() { restore; fail "$1" "$2 (код на VM возвращён на $PREV, коммит $(echo "$PREV_SHA" | cut -c1-7))"; }
git checkout -q -B "$BR" "origin/$BR" || fail "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
# теги для отката: образ работающего контейнера; если docker не находит его по номеру (бывает с хранилищем образов containerd), берётся образ по имени :latest — он ещё не пересобран
tag_pre() {
  local svc="$1" t="plan-estimate-$1:pre-v214a" cur
  docker image inspect "$t" > /dev/null 2>&1 && return 0
  cur=$(docker inspect -f '{{.Image}}' "plan_estimate_$svc" 2>/dev/null)
  if [ -n "$cur" ] && docker image inspect "$cur" > /dev/null 2>&1; then docker tag "$cur" "$t" && return 0; fi
  if docker image inspect "plan-estimate-$svc:latest" > /dev/null 2>&1; then docker tag "plan-estimate-$svc:latest" "$t" && return 0; fi
  return 1
}
tag_pre backend || fail1 "G1" "нет образа backend для отката (тег pre-v214a)"
if tag_pre frontend; then FRONT_ROLLBACK=yes; else FRONT_ROLLBACK=no; echo "ВНИМАНИЕ: образа frontend для отката нет (frontend — статические файлы; откат при необходимости: git checkout на прежний коммит и docker compose build frontend && up -d --no-deps frontend). Продолжаем: backend откатывается образом."; fi
PC build backend frontend > /tmp/build_v214a.log 2>&1 || { tail -n 30 /tmp/build_v214a.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-v214a)"

echo; echo "################ ВОРОТА B: пересоздание контейнеров и миграция 0086 ################"
echo "Что произойдёт: пересоздаются backend и frontend из собранных образов."
echo "  • Миграция 0086 (при старте backend): у таблиц «Punkty i trasy» и расчётов материалов появляется по одной необязательной колонке «источник» (у всех существующих строк пусто = вы ввели сами). Ни одна существующая строка не меняется. Откат миграции просто убирает колонки."
echo "  • Ключ шифрования и строгое чтение остаются как были. Ничего не удаляется. Вход по паролю остаётся выключенным."
echo "  • Простой API при пересоздании backend: около 30–60 секунд."
echo "  • Откат образами безопасен (прежний образ не знает новых видов и не мешает им): retag pre-v214a и up --no-deps --no-build backend frontend. Команда напечатается при любом отказе."
echo "  • Отказ на этих воротах возвращает код на $PREV; production не меняется."
echo
echo "Чтобы пересоздать backend и frontend, введите ТОЧНО:  ВЫКЛАДКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYV214A_TTY:-/dev/tty}" || { restore; fail "B" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА ДА" ] || { echo; restore; echo "Остановлено на воротах B (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "B (подтверждено вами)"

if [ "$FRONT_ROLLBACK" = yes ]; then
  ROLLALL="Откат (прежний образ работает на новой схеме: он не знает ссылок для мастеров и не показывает их; данные остаются в базе): 1) docker tag plan-estimate-backend:pre-v214a plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-v214a plan-estimate-frontend:latest   2) $COMPOSE up -d --no-deps --no-build backend frontend   3) git checkout -q -B $PREV $PREV_SHA"
else
  ROLLALL="Откат (прежний образ работает на новой схеме): 1) docker tag plan-estimate-backend:pre-v214a plan-estimate-backend:latest   2) $COMPOSE up -d --no-deps --no-build backend   3) git checkout -q -B $PREV $PREV_SHA && $COMPOSE build frontend && $COMPOSE up -d --no-deps frontend"
fi

echo; echo "################ G2: backend ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend 2>&1)
if [ "$FIRST" = yes ]; then has "Running upgrade 0085_trade_links -> 0086_transfer_source" "$LOG" || fail "G2" "в логе нет применения миграции 0086. $ROLLALL"; fi
[ "$(grep -c 'Running upgrade' <<<"$LOG")" -le 1 ] || fail "G2" "в логе применяется больше одной миграции. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0086_transfer_source' "$AL2" || fail "G2" "alembic не 0086: $AL2. $ROLLALL"
STRICT=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")
[ "$STRICT" = "true" ] || fail "G2" "строгое чтение в контейнере: $STRICT, ожидалось true. $ROLLALL"
API=$(docker exec plan_estimate_backend python -c "
from app.main import app
p = app.openapi()['paths']
need = ['/api/projects/{project_id}/rooms/{room_id}/surfaces/merge', '/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/unmerge', '/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/parts/{part_id}', '/api/projects/{project_id}/rooms/{room_id}/work-plan', '/api/auth/telegram', '/api/me']
print(all(n in p for n in need))")
[ "$API" = "True" ] || fail "G2" "в API нет нужных маршрутов: $API. $ROLLALL"
# на настоящей базе (ТОЛЬКО ЧТЕНИЕ): новые таблицы есть и пусты; маршруты ссылки для клиента на месте; вход по паролю выключен
SRC=$(PSQL "select count(*) from information_schema.columns where column_name = 'source' and table_name in ('room_points', 'material_calcs') and is_nullable = 'YES' and data_type = 'character varying'")
SRCSET=$(PSQL "select (select count(*) from room_points where source is not null) + (select count(*) from material_calcs where source is not null)")
echo "новые необязательные колонки source: $SRC из 2; строк с заполненным источником: $SRCSET (при первом запуске 0: перенос ещё не нажимали); строк журнала отправленных: $(PSQL "select count(*) from issued_documents") (было $IDOC_BEFORE)"
[ "$SRC" = "2" ] || fail "G2" "нет двух необязательных колонок source: $SRC. $ROLLALL"
if [ "$FIRST" = yes ]; then [ "$SRCSET" = "0" ] || fail "G2" "после миграции ни у одной строки не должно быть источника: $SRCSET. $ROLLALL"; fi
[ "$(PSQL "select count(*) from issued_documents")" = "$IDOC_BEFORE" ] || fail "G2" "число строк журнала отправленных изменилось. $ROLLALL"
ST=$(PSQL "select count(*) from payment_stages"); WH=$(PSQL "select count(*) from work_hours")
echo "ваших этапов: $ST; записей часов: $WH (эта миграция их не затрагивает)"
CODE=$(docker exec plan_estimate_backend python -c "
from app.core.config import settings
from app.main import app
paths = app.openapi()['paths']
open_ops = sorted(f'{m.upper()} {p}' for p, ops in paths.items() if p.startswith('/api/public/') for m, op in ops.items() if not op.get('security'))
print('/api/material-norms' in paths, '/api/projects/{project_id}/rooms/{room_id}/material-calcs' in paths, '/api/projects/{project_id}/estimates/{estimate_id}/add-materials' in paths, '/api/projects/{project_id}/rooms/{room_id}/route-totals' in paths, '/api/projects/{project_id}/documents/installation-map/preview' in paths, '/api/projects/{project_id}/pressure-tests' in paths, '/api/projects/{project_id}/pressure-tests/{protocol_id}/issue' in paths, '/api/projects/{project_id}/documents/pressure-test/preview' in paths, '/api/trades' in paths, '/api/projects/{project_id}/trade-links' in paths, '/api/projects/{project_id}/trade-links/{trade}/answers' in paths, '/api/public/trade' in paths, '/api/public/trade/submit' in paths, '/api/projects/{project_id}/trade-links/{trade}/transfer' in paths, '/api/projects/{project_id}/trade-links/{trade}/transfer/preview' in paths, len(open_ops) == 6, settings.AUTH_PASSWORD_ENABLED is False)")
[ "$CODE" = "True True True True True True True True True True True True True True True True True" ] || fail "G2" "в контейнере нет маршрутов норм, расчётов материалов, трасс помещения, «Mapa instalacji», протоколов опрессовки, профессий, ссылок для мастеров или их переноса в помещения, открытых операций не шесть (три клиента и три мастера), или вход по паролю включён: $CODE. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "G2" "verify шифрования не прошёл. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ok "G2 (backend: миграция 0086 применена, база на 0086, строгое чтение включено, колонки source есть и ни у кого не заполнены, журнал цел, маршруты переноса на месте, вход по паролю выключен, данные те же)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in show-access login-email login-submit account-sign-out reorder-walls-start merge-walls-start bottom-nav field-help- start-quick-estimate quick-estimate-form room-plan-open room-plan-sheet estimate-vat-select executor-profile-vat language-switch language-list lang- Українська English object-tile-client client-link-create client-estimate-decline X-Client-Link docs-tile documents/measurements/preview Obmiar with_photos payment-stages work-hours margin-card schedule-tab hours-tab stage-form hours-form payment-schedule/preview schedule-pdf 'Harmonogram płatności' voice- stage-due-hint room-points-toggle room-point-form estimate-add-points-action price-items/points-pack 'Punkty i trasy' object-tile-materials room-materials-toggle material-calc-form material-norms-toggle estimate-add-materials-action material-norms 'Normy zużycia' 'Dodaj materiały do kosztorysu' 'Нормы расхода' 'Consumption norms' TILE_WASTE_STRAIGHT material-use-routes route-totals ELEC_CABLE_M_SOCKET PL_PIPE_M_POINT 'Elektryka' 'Hydraulika' 'Электрика' 'Сантехника' 'Electrics' 'Plumbing' docs-tile installation-map/preview marker-utility- marker-legend 'Mapa instalacji ukrytych' 'Карта скрытых коммуникаций' 'Карта прихованих комунікацій' 'Map of hidden utilities' 'Co to jest (instalacja ukryta)' 'Woda zimna' pressure-tests documents/pressure-test/preview pressure-system- pressure-result- 'Protokół próby ciśnieniowej' 'Протокол опрессовки' 'Протокол опресування' 'Pressure test protocol' 'Protokół próby szczelności' pressure-photo-add surface-note- trades-picker trade- pricebook-show-all-trades recommendation-picker-show-all-trades '/api/trades' 'Zawody (pakiety)' 'Профессии (пакеты)' 'Професії (пакети)' 'Trades (packages)' 'Pokaż wszystkie kategorie' trade-transfer-open- trade-transfer-run- trade-transfer-item- 'Przenieś do pomieszczeń' 'Перенести в помещения' 'Перенести в приміщення' 'Carry over into the rooms' object-tile-masters trade-link-create- 'Linki dla mistrzów' 'Ссылки для мастеров' 'Посилання для майстрів' 'Links for craftsmen' X-Trade-Link master-submit master-room-save- 'Elektryk — punkty i trasy' 'Hydraulik — punkty i trasy'; do
  has "$MARK" "$BUNDLE" || fail "G3" "в выданной сборке нет '$MARK'. $ROLLALL"
done
# страница клиента отдаётся по /c, а открытое API без секрета отвечает 404 и не кэшируется (через Caddy, как у клиента)
CPAGE=$(curl -fsS https://plan-estimate.pl/c) && has "assets/index-" "$CPAGE" || fail "G3" "адрес /c не отдаёт страницу приложения. $ROLLALL"
MPAGE=$(curl -fsS https://plan-estimate.pl/m) && has "assets/index-" "$MPAGE" || fail "G3" "адрес /m не отдаёт страницу приложения. $ROLLALL"
for WHO in client trade; do
  HDR=X-Client-Link; [ "$WHO" = trade ] && HDR=X-Trade-Link
  PUB=$(curl -s -D - -o /dev/null -H "$HDR: $(printf 'x%.0s' $(seq 1 43))" "https://plan-estimate.pl/api/public/$WHO")
  has " 404" "$PUB" || fail "G3" "открытое API ($WHO) без настоящего секрета должно отвечать 404: $PUB. $ROLLALL"
  grep -qi '^cache-control: no-store' <<<"$PUB" || fail "G3" "открытое API ($WHO) не говорит no-store: $PUB. $ROLLALL"
  grep -qi '^referrer-policy: no-referrer' <<<"$PUB" || fail "G3" "открытое API ($WHO) не говорит referrer-policy: no-referrer: $PUB. $ROLLALL"
done
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend: прежние разделы, плитка «Linki dla mistrzów» с кнопкой переноса, /c и /m отдаются, открытое API клиента и мастера закрыто секретом и не кэшируется)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена (миграция 0086, база на 0086), данные те же, ничего не удалено ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram и откройте Mini App по кнопке меню: вход как обычно, всё прежнее на месте;"
echo "  2) профессии: в «Konto» → «Profil wykonawcy» оставьте включённой только «Wykończenia»; в помещении, где уже были расчёты материалов или точки, раздел называется просто «Materiały», показывает имеющееся и НЕ предлагает добавить новое;"
echo "  3) объект → «Linki dla mistrzów» → карточка мастера с ответами: кнопка «Przenieś do pomieszczeń» открывает предпросмотр (ничего не записывается): сверху позиции прайса для типовых позиций (по умолчанию подобраны по названию — «Punkt elektryczny - gniazdko / włącznik», «Punkt wodny», «Trasa rurowa»…, можно выбрать другую или «не переносить»), ниже по помещениям: новое / изменить / без изменений / убрать;"
echo "  4) нажмите «Przenieś»: в помещении в «Punkty i trasy» появились строки, в «Materiały» — расчёт «Elektryka» / «Hydraulika» с числами мастера; ваши собственные строки не изменились;"
echo "  5) нажмите «Przenieś» ещё раз: «Wszystko już jest przeniesione — nic się nie zmieniło.» (повтор не дублирует); поправьте ответ мастера (или зайдите по его ссылке и измените число), снова перенесите — строки обновятся;"
echo "  6) смета не меняется сама: новые точки попадут в смету кнопкой «Dodaj punkty i trasy z pomieszczeń»;"
echo "  7) подробная инструкция — в README.md, раздел «Ссылка для мастера: пошаговая инструкция» (пункт про перенос);"
echo "  8) бэкап под новую голову: cd ~/apps/plan_-_estimate && BACKUP_BRANCH=$BR BACKUP_HEAD=0086_transfer_source bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  9) слияние $BR → main — только по отдельному «да»."
)
