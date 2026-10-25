#!/usr/bin/env bash
# V2-9b: напоминания о сроках этапов графика платежей в Telegram (за день до срока и в день срока) — выкладка БЕЗ МИГРАЦИИ (схема остаётся на 0076), backend и frontend, без новых зависимостей.
# Что меняется: новый вид события календаря STAGE_DUE («Срок оплаты этапа: …»). У этапа со сроком, пока он не оплачен полностью, в календаре стоит день срока, а бот присылает напоминание утренней сводкой за день и в день срока (включено по умолчанию, отключается в настройках календаря). Напоминания следуют за изменениями этапа, оплаты и договорной суммы сразу; периодический пересчёт календаря ставит их и для уже существующих этапов. Под полем срока этапа появилась подсказка.
# Откат БЕЗОПАСЕН образами: схема не меняется, прежний образ работает как раньше (в очереди остаются строки STAGE_DUE; прежний код их просто не пересчитывает); теги pre-v29b. Останавливается на первом непройденном условии (FAIL). Ворота B: контейнеры пересоздаются только после того, как вы САМИ введёте фразу.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin ver-2 && git show origin/ver-2:docs/V2_9B_DEPLOY_RU.sh > ~/deploy_v29b.sh && bash ~/deploy_v29b.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
BR="${DEPLOYV29B_BRANCH:-ver-2}"
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
if has '0076_payment_schedule_doc' "$AL"; then FIRST=no
else fail "G0" "alembic current не 0076_payment_schedule_doc: $AL (V2-9b без миграции: сначала V2-9a)"; fi
# V2-9b не меняет схему: FIRST всегда no
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
STRICT_ENV=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower(), bool(s.DATA_KEK.get_secret_value()) if s.DATA_KEK else False)")
[ "$STRICT_ENV" = "true True" ] || fail "G0" "строгое чтение / ключ шифрования в контейнере: '$STRICT_ENV', ожидалось 'true True' (состояние после EN-2b-2)"
# бэкап (A9) не старше суток: выкладка без миграции, но порядок прежний (бэкап под голову 0076 делается из ветки ver-2, текущий коммит VM)
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
[ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9 (BACKUP_BRANCH=ver-2 BACKUP_COMMIT=$(git rev-parse --short HEAD) BACKUP_HEAD=0076_payment_schedule_doc bash ~/backup_a9.sh)"
AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
[ "$AGE_H" -le 24 ] || fail "G0" "последний бэкап $LASTRUN старше суток (${AGE_H} ч). Сделайте свежий: cd ~/apps/plan_-_estimate && git fetch -q origin ver-2 && git show origin/ver-2:docs/STAGE_18_BACKUP_A9_RU.sh > ~/backup_a9.sh && BACKUP_BRANCH=ver-2 BACKUP_COMMIT=$(git rev-parse --short HEAD) BACKUP_HEAD=0076_payment_schedule_doc bash ~/backup_a9.sh (в НОВОЙ сессии, потом закрыть её)"
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
[ -z "$NEWMIG" ] || fail "G0" "в релизе V2-9b не должно быть новых миграций, а здесь: '$NEWMIG'"
OTHERALEMBIC=$(git diff --name-only HEAD "origin/$BR" -- backend/alembic | grep -v '__pycache__' || true)
[ -z "$OTHERALEMBIC" ] || fail "G0" "в alembic изменено что-то (в V2-9b схема не меняется): $OTHERALEMBIC"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(README.md|backend/app/|backend/tests/|frontend/src/|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from contracts; select count(*) from handover_protocols; select count(*) from concealed_works_protocols; select count(*) from acceptance_protocols; select count(*) from decision_protocols; select count(*) from downtime_episodes; select count(*) from data_keys; select count(*) from photo_attachments; select count(*) from photo_assets; select count(*) from estimates; select count(*) from calendar_settings; select count(*) from payment_stages; select count(*) from work_hours;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/журнал/договоры/передачи/скрытые/приёмки/решения/простои/ключи/привязки фото/файлы фото/сметы/настройки календаря/этапы/часы = $BEFORE (очередь напоминаний в сравнение не входит: после выкладки календарь сам ставит напоминания этапов)"
REM_BEFORE=$(PSQL "select count(*) from reminders" 2>/dev/null | tr -d "[:space:]"); echo "напоминаний в очереди до выкладки: ${REM_BEFORE:-?}"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
fail1() { restore; fail "$1" "$2 (код на VM возвращён на $PREV, коммит $(echo "$PREV_SHA" | cut -c1-7))"; }
git checkout -q -B "$BR" "origin/$BR" || fail "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
# теги для отката: образ работающего контейнера; если docker не находит его по номеру (бывает с хранилищем образов containerd), берётся образ по имени :latest — он ещё не пересобран
tag_pre() {
  local svc="$1" t="plan-estimate-$1:pre-v29b" cur
  docker image inspect "$t" > /dev/null 2>&1 && return 0
  cur=$(docker inspect -f '{{.Image}}' "plan_estimate_$svc" 2>/dev/null)
  if [ -n "$cur" ] && docker image inspect "$cur" > /dev/null 2>&1; then docker tag "$cur" "$t" && return 0; fi
  if docker image inspect "plan-estimate-$svc:latest" > /dev/null 2>&1; then docker tag "plan-estimate-$svc:latest" "$t" && return 0; fi
  return 1
}
tag_pre backend || fail1 "G1" "нет образа backend для отката (тег pre-v29b)"
if tag_pre frontend; then FRONT_ROLLBACK=yes; else FRONT_ROLLBACK=no; echo "ВНИМАНИЕ: образа frontend для отката нет (frontend — статические файлы; откат при необходимости: git checkout на прежний коммит и docker compose build frontend && up -d --no-deps frontend). Продолжаем: backend откатывается образом."; fi
PC build backend frontend > /tmp/build_v29b.log 2>&1 || { tail -n 30 /tmp/build_v29b.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-v29b)"

echo; echo "################ ВОРОТА B: пересоздание контейнеров (миграции нет) ################"
echo "Что произойдёт: пересоздаются backend и frontend из собранных образов."
echo "  • Миграции нет: схема остаётся на 0076, существующие таблицы и строки не меняются. Появляется вид события «Срок оплаты этапа»: у неоплаченных этапов со сроком в очередь ставятся напоминания (за день и в день срока); данные этапов, оплат и часов не меняются. Вход по паролю остаётся выключенным."
echo "  • Ключ шифрования и строгое чтение остаются как были. Ничего не удаляется."
echo "  • Простой API при пересоздании backend: около 30–60 секунд."
echo "  • Откат безопасен образами (схема не менялась, прежний образ работает как раньше): retag pre-v29b и up --no-deps --no-build backend frontend. Команда напечатается при любом отказе."
echo "  • Отказ на этих воротах возвращает код на $PREV; production не меняется."
echo
echo "Чтобы пересоздать backend и frontend, введите ТОЧНО:  ВЫКЛАДКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYV29B_TTY:-/dev/tty}" || { restore; fail "B" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА ДА" ] || { echo; restore; echo "Остановлено на воротах B (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "B (подтверждено вами)"

if [ "$FRONT_ROLLBACK" = yes ]; then
  ROLLALL="Откат (схема не менялась): 1) docker tag plan-estimate-backend:pre-v29b plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-v29b plan-estimate-frontend:latest   2) $COMPOSE up -d --no-deps --no-build backend frontend   3) git checkout -q -B $PREV $PREV_SHA"
else
  ROLLALL="Откат (схема не менялась): 1) docker tag plan-estimate-backend:pre-v29b plan-estimate-backend:latest   2) $COMPOSE up -d --no-deps --no-build backend   3) git checkout -q -B $PREV $PREV_SHA && $COMPOSE build frontend && $COMPOSE up -d --no-deps frontend"
fi

echo; echo "################ G2: backend ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend 2>&1)
[ "$(grep -c 'Running upgrade' <<<"$LOG")" = "0" ] || fail "G2" "в логе применяется миграция, а её в этом релизе нет. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0076_payment_schedule_doc' "$AL2" || fail "G2" "alembic не 0074: $AL2. $ROLLALL"
STRICT=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")
[ "$STRICT" = "true" ] || fail "G2" "строгое чтение в контейнере: $STRICT, ожидалось true. $ROLLALL"
API=$(docker exec plan_estimate_backend python -c "
from app.main import app
p = app.openapi()['paths']
need = ['/api/projects/{project_id}/payment-stages', '/api/projects/{project_id}/payment-stages/{stage_id}/receive', '/api/calendar', '/api/calendar/settings', '/api/auth/telegram', '/api/me']
print(all(n in p for n in need))")
[ "$API" = "True" ] || fail "G2" "в API нет нужных маршрутов: $API. $ROLLALL"
# в контейнере: вид события STAGE_DUE есть, шлёт по умолчанию, за день и в день срока, тексты на четырёх языках; вход по паролю выключен
CODE=$(docker exec plan_estimate_backend python -c "
from app.core.config import settings
from app.domain.calendar.events import PUSH_BY_DEFAULT, EventKind, lead_days
from app.domain.calendar.messages import load_texts
entry = load_texts().titles.get('calendar.event.stage_due', {})
print(EventKind.STAGE_DUE in PUSH_BY_DEFAULT and lead_days(EventKind.STAGE_DUE) == (1, 0) and all('{what}' in entry.get(l, '') for l in ('pl', 'ru', 'uk', 'en')), settings.AUTH_PASSWORD_ENABLED is False)")
[ "$CODE" = "True True" ] || fail "G2" "в контейнере нет вида события STAGE_DUE (по умолчанию шлёт, 1 и 0 дней, тексты PL/RU/UK/EN) или вход по паролю включён: $CODE. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "G2" "verify шифрования не прошёл. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
REM_AFTER=$(PSQL "select count(*) from reminders" 2>/dev/null | tr -d "[:space:]"); echo "напоминаний в очереди после запуска: ${REM_AFTER:-?} (было ${REM_BEFORE:-?}; новые — напоминания этапов, их ставит периодический пересчёт)"
ok "G2 (backend: база на 0076 без новых миграций, строгое чтение включено, вид события STAGE_DUE есть, вход по паролю выключен, данные те же)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in show-access login-email login-submit account-sign-out reorder-walls-start merge-walls-start bottom-nav field-help- start-quick-estimate quick-estimate-form room-plan-open room-plan-sheet estimate-vat-select executor-profile-vat language-switch language-list lang- Українська English object-tile-client client-link-create client-estimate-decline X-Client-Link docs-tile documents/measurements/preview Obmiar with_photos payment-stages work-hours margin-card schedule-tab hours-tab stage-form hours-form payment-schedule/preview schedule-pdf 'Harmonogram płatności' 'Marża obiektu' 'Stawka za godzinę' voice- speech_lang stage-due-hint 'Termin płatności etapu' 'Payment stage due' 'Срок оплаты этапа' 'Строк оплати етапу' STAGE_DUE; do
  has "$MARK" "$BUNDLE" || fail "G3" "в выданной сборке нет '$MARK'. $ROLLALL"
done
# страница клиента отдаётся по /c, а открытое API без секрета отвечает 404 и не кэшируется (через Caddy, как у клиента)
CPAGE=$(curl -fsS https://plan-estimate.pl/c) && has "assets/index-" "$CPAGE" || fail "G3" "адрес /c не отдаёт страницу приложения. $ROLLALL"
PUB=$(curl -s -D - -o /dev/null -H "X-Client-Link: $(printf 'x%.0s' $(seq 1 43))" https://plan-estimate.pl/api/public/client)
has " 404" "$PUB" || fail "G3" "открытое API без настоящего секрета должно отвечать 404: $PUB. $ROLLALL"
grep -qi '^cache-control: no-store' <<<"$PUB" || fail "G3" "открытое API не говорит no-store: $PUB. $ROLLALL"
grep -qi '^referrer-policy: no-referrer' <<<"$PUB" || fail "G3" "открытое API не говорит referrer-policy: no-referrer: $PUB. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend: прежние разделы, подсказка у срока этапа и новые тексты в сборке, /c отдаётся, открытое API закрыто секретом и не кэшируется)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена (без миграции, база на 0076), данные те же, ничего не удалено ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram и откройте Mini App по кнопке меню: вход как обычно, всё прежнее на месте;"
echo "  2) объект → «Faktury i zaliczki» → «Etapy» → «Dodaj etap»: под полем «Termin płatności» есть подсказка про напоминание; поставьте срок через 2–3 дня (этап без оплаты) и сохраните;"
echo "  3) меню 📅 «Календарь»: на день срока строка «Termin płatności etapu: …» с пометкой «присылает сообщение»; в «Настройки» есть вид «Termin płatności etapu (Harmonogram)»;"
echo "  4) напоминание придёт в чат с ботом утренней сводкой (08:00) за день до срока и в день срока; нажмите у этапа «Otrzymano» — напоминания этапа отменятся сами;"
echo "  5) пошаговая инструкция — в README.md, раздел «Напоминания о сроках этапов: пошаговая инструкция»;"
echo "  6) бэкап после выкладки не обязателен (схема та же); при желании: cd ~/apps/plan_-_estimate && BACKUP_BRANCH=$BR BACKUP_HEAD=0076_payment_schedule_doc bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  7) слияние $BR → main — только по отдельному «да»."
)
