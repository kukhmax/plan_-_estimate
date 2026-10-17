#!/usr/bin/env bash
# «Faktury i zaliczki» IA-1…IA-6 — выкладка: миграции 0058, 0059, 0060 и 0061, backend, frontend, кнопка Telegram.
# Что приходит: расчёты по объекту (счета, авансы и платежи клиента, расходы на материалы, договорная сумма; IA-1/IA-2), фото чеков и счетов (IA-3), работа без связи (IA-4),
# напоминание календаря о сроке оплаты счёта (IA-5; рассылается по умолчанию, отключается в настройках календаря), PDF «Rozliczenie» для клиента (IA-6a), категории расходов (IA-6b).
# Миграции только ДОБАВЛЯЮТ: две новые таблицы (project_payments, project_finance), колонку payment_id в photo_attachments, колонку category в project_payments, одно слово SETTLEMENT в проверке видов документов.
# Существующие строки не меняются, ничего не удаляется. Цикл сообщений календаря этим скриптом НЕ трогается: остаётся таким, каким он в .env.production (скрипт проверяет, что он после выкладки в том же состоянии).
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Ворота M: миграции применяются только после того, как вы САМИ введёте фразу. Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому старый код на VM не меняется до проверок), ПОСЛЕ свежего бэкапа A9 (раздел 2 runbook):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-finance-encryption && git show origin/backlog-finance-encryption:docs/INVOICES_ADVANCES_DEPLOY_RU.sh > ~/deploy_ia.sh && bash ~/deploy_ia.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
R="$HOME/backups/plan-estimate/db-backup"
BR="${DEPLOYIA_BRANCH:-backlog-finance-encryption}"
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
has '0057_purge_ledger' "$AL" || fail "G0" "alembic current не 0057_purge_ledger: $AL (выкладка рассчитана на базу ровно на 0057)"
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
[ "$NEWMIG" = "$(printf 'backend/alembic/versions/0058_project_payments.py\nbackend/alembic/versions/0059_payment_photos.py\nbackend/alembic/versions/0060_settlement_document.py\nbackend/alembic/versions/0061_expense_category.py')" ] || fail "G0" "ожидаются ровно четыре новые миграции (0058…0061), а пришло: $NEWMIG"
CHGMIG=$(git diff --name-only --diff-filter=MD HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
[ -z "$CHGMIG" ] || fail "G0" "существующие миграции изменены или удалены: $CHGMIG"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(backend/app/|backend/alembic/versions/00(5[89]|6[01])_[a-z_]+\.py$|backend/tests/|backend/scripts/|frontend/src/|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments; select count(*) from photo_assets; select count(*) from photo_annotations;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/документы/привязки фото/файлы фото/метки = $BEFORE (таблиц расчётов ещё нет)"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
# до ворот M production не меняется: при любом отказе в G1 код на VM возвращается на прежнюю ветку
fail1() { git checkout -q "$PREV" 2>/dev/null; fail "$1" "$2 (код на VM возвращён на ветку $PREV)"; }
git checkout -q -B "$BR" "origin/$BR" || fail1 "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-ia  || fail1 "G1" "тег pre-ia backend"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-ia || fail1 "G1" "тег pre-ia frontend"
PC build backend frontend > /tmp/build_ia.log 2>&1 || { tail -n 30 /tmp/build_ia.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-ia)"

echo; echo "################ ВОРОТА M: миграции базы данных ################"
echo "Миграции 0058_project_payments, 0059_payment_photos, 0060_settlement_document, 0061_expense_category (проверены на PostgreSQL 16: вверх, вниз, вверх; отказ отката при записанных данных):"
echo "  • 0058: СОЗДАЁТ две новые пустые таблицы project_payments (расчёты по объекту) и project_finance (договорная сумма), внешние ключи на users и projects (ON DELETE CASCADE)."
echo "  • 0059: ДОБАВЛЯЕТ в photo_attachments пустую колонку payment_id (внешний ключ RESTRICT), расширяет проверку «к чему привязано фото» словом PAYMENT и добавляет уникальный индекс; существующие строки не меняются."
echo "  • 0060: РАСШИРЯЕТ проверку видов документов журнала словом SETTLEMENT; строки не меняются."
echo "  • 0061: ДОБАВЛЯЕТ в project_payments пустую колонку category и две проверки."
echo "  • Время: миллисекунды; каждая миграция — в одной транзакции: при ошибке откат целиком. Простой API при пересоздании контейнера backend: около 30–60 секунд. Ничего не удаляется."
echo "  • ОТКАТ ИМЕЕТ ПОРЯДОК: старый образ backend НЕ запустится на базе с новыми миграциями (alembic не знает версию 0061). Сначала миграции откатываются командой из сообщения об ошибке"
echo "    (без потерь, пока вы не ввели ни одной записи расчётов; после первой записи откат отказывается — назад пути нет, только вперёд новым выпуском), потом возвращается образ."
echo "  • ВАЖНО для календаря: напоминания «Termin zapłaty faktury» по умолчанию отправляются в Telegram (за 3 дня и в день срока); отключаются в настройках календаря. Пока счетов нет, ничего не придёт."
echo "  • Бэкап перед миграциями: $LASTRUN (${AGE_H} ч назад)."
echo "  • Отказ на этих воротах возвращает код на ветку $PREV; ничего не меняется."
echo
echo "Чтобы применить миграции и пересоздать backend, введите ТОЧНО:  МИГРАЦИИ 0058 0059 0060 0061 ДА"
echo "Любой другой ввод останавливает выкладку; в production ничего не изменено (образы собраны, старая версия работает)."
printf '> '
read -r ANSWER < "${DEPLOYIA_TTY:-/dev/tty}" || { git checkout -q "$PREV"; fail "M" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на ветку $PREV)"; }
[ "$ANSWER" = "МИГРАЦИИ 0058 0059 0060 0061 ДА" ] || { echo; git checkout -q "$PREV"; echo "Остановлено на воротах M (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на ветку $PREV."; exit 1; }
ok "M (подтверждено вами)"

ROLLALL="Откат (ПОРЯДОК ВАЖЕН): 1) $COMPOSE run --rm --no-deps --entrypoint alembic backend downgrade 0057_purge_ledger   2) docker tag plan-estimate-backend:pre-ia plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-ia plan-estimate-frontend:latest   3) $COMPOSE up -d --no-deps --no-build backend frontend"

echo; echo "################ G2: backend + миграции ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend --tail 120 2>&1)
for PAIR in "0057_purge_ledger -> 0058_project_payments" "0058_project_payments -> 0059_payment_photos" "0059_payment_photos -> 0060_settlement_document" "0060_settlement_document -> 0061_expense_category"; do
  has "Running upgrade $PAIR" "$LOG" || fail "G2" "в логе нет применения миграции $PAIR. $ROLLALL"
done
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0061_expense_category' "$AL2" || fail "G2" "alembic не 0061. $ROLLALL"
DBX=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"select (select count(*) from information_schema.tables where table_name in ('project_payments','project_finance')), (select count(*) from information_schema.columns where table_name='photo_attachments' and column_name='payment_id'), (select count(*) from information_schema.columns where table_name='project_payments' and column_name='category'), (select count(*) from pg_constraint where conname in ('ck_project_payments_category','ck_project_payments_category_only_expense') or conname='ck_issued_documents_kind' and pg_get_constraintdef(oid) like '%SETTLEMENT%'), (select count(*) from project_payments), (select count(*) from project_finance)\"")
[ "$DBX" = "2|1|1|3|0|0" ] || fail "G2" "схема после миграций не та (таблицы|payment_id|category|проверки|строк расчётов|строк договорных сумм): '$DBX', ожидалось 2|1|1|3|0|0. $ROLLALL"
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
[ "$TXT" = "18" ] || fail "G2" "тексты календаря: $TXT заголовков вместо 18. $ROLLALL"
API=$(docker exec plan_estimate_backend python -c "
from app.main import app
p = app.openapi()['paths']
need = ['/api/calendar', '/api/projects/{project_id}/notes', '/api/photo-purge/status', '/api/projects/{project_id}/payments', '/api/projects/{project_id}/payments/{payment_id}', '/api/projects/{project_id}/finance', '/api/projects/{project_id}/documents/settlement/preview']
print(all(n in p for n in need))")
[ "$API" = "True" ] || fail "G2" "в API нет маршрутов расчётов / договорной суммы / «Rozliczenie» / календаря: $API. $ROLLALL"
IA=$(docker exec plan_estimate_backend python -c "
from app.schemas.payment import PaymentCreate, PaymentSummary
from app.domain.documents.registry import DocumentKind
from app.domain.calendar.events import EventKind, PUSH_BY_DEFAULT
from app.models.photo_attachment import PhotoAttachmentContext as C
print('category' in PaymentCreate.model_fields, 'expenses_by_category' in PaymentSummary.model_fields, DocumentKind.SETTLEMENT.value, EventKind.INVOICE_DUE in PUSH_BY_DEFAULT, C.PAYMENT.value)")
[ "$IA" = "True True SETTLEMENT True PAYMENT" ] || fail "G2" "код расчётов в backend не тот: '$IA'. $ROLLALL"
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
ok "G2 (миграции 0058…0061 применены, схема, таблицы расчётов пусты, порт удаления S3, маршруты, цикл календаря как был: $LOOP_ENV, данные те же)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in plan-estimate-offline CHANGES_WAITING sync-screen show-calendar photo-purge-confirm photo-untrash object-tile-payments payments-statement payment-category- payments-pending-note 'Rozliczenie dla klienta' 'Na co wydano'; do
  has "$MARK" "$BUNDLE" || fail "G3" "в выданной сборке нет '$MARK'. $ROLLALL"
done
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend: расчёты по объекту, «Rozliczenie» для клиента, категории расходов, работа без связи, корзина)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена, миграции 0058…0061 применены, таблицы расчётов пусты, данные те же ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram, откройте Mini App по кнопке меню и пройдите чек-лист из раздела 5 docs/INVOICES_ADVANCES_RUNBOOK_RU.md;"
echo "  2) бэкап под новую голову: BACKUP_BRANCH=$BR BACKUP_HEAD=0061_expense_category bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  3) приёмка: «принимаем» — слияние $BR → main и переключение VM на main только по отдельному «да»."
)
