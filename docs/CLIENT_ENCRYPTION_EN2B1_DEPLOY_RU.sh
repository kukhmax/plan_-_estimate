#!/usr/bin/env bash
# Шифрование данных клиентов, шаг EN-2b-1 — выкладка БЕЗ миграций и БЕЗ новых зависимостей: пересоздаётся только backend (команда перекодировки старых значений и «строгое чтение»).
# Что делает: (1) выкладывает backend с командой `python -m app.cli.reencode_data` (report / verify / apply); (2) по вашей фразе ПЕРЕКОДИРОВКА ДА превращает ВСЕ старые открытые значения (клиенты, объекты, представители, заметки)
# в шифртекст и проверяет, что открытых значений не осталось и всё расшифровывается; (3) по вашей фразе СТРОГОЕ ЧТЕНИЕ ДА включает DATA_STRICT_READ=true в .env.production: открытое значение в зашифрованной колонке с этого момента отклоняется.
# Ничего не удаляется. Перекодировка не меняет «дату изменения» записей и не затирает запись, которую вы сохранили во время её работы (такая пропускается и подхватывается повторным запуском).
# ПОСЛЕ ПЕРЕКОДИРОВКИ образ ДО EN-2a уже не прочитает данные (откат на него невозможен); образ EN-2a (тег pre-en2b1) читает шифртекст и остаётся запасным. Строгое чтение выключается строкой DATA_STRICT_READ=false и пересозданием backend.
# Документы (снимки, HTML, названия в журнале) и расчёты остаются открытыми до шагов EN-2b-2 и EN-2b-3.
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Ворота B (пересоздание), R (перекодировка), S (строгое чтение): вы САМИ вводите фразы. Секреты и значения не печатает (только числа).
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-client-encryption && git show origin/backlog-client-encryption:docs/CLIENT_ENCRYPTION_EN2B1_DEPLOY_RU.sh > ~/deploy_en2b1.sh && bash ~/deploy_en2b1.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
R="$HOME/backups/plan-estimate/db-backup"
BR="${DEPLOYEN_BRANCH:-backlog-client-encryption}"
COMPOSE="docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml"
PSQL() { docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"$1\""; }
echo "################ G0: проверка перед выкладкой (только чтение) ################"
echo "--- ресурсы сервера (справочно) ---"
echo "процессоров: $(nproc); память МБ (всего/занято/свободно): $(free -m | awk '/^Mem:/ {print $2"/"$3"/"$4}'); swap МБ: $(free -m | awk '/^Swap:/ {print $2}'); архитектура: $(uname -m)"
docker stats --no-stream --format '  {{.Name}}: память {{.MemUsage}} ({{.MemPerc}}), процессор {{.CPUPerc}}' 2>/dev/null || true
[ "$(env | grep -c '^MEDIA_S3\|^BACKUP_')" = "0" ] || fail "G0" "В оболочке лишние переменные MEDIA_S3/BACKUP_. Откройте новую SSH-сессию (не ту, где шёл бэкап)."
[ -z "$(git status --short)" ] || fail "G0" "Рабочее дерево не чистое: $(git status --short)"
PREV=$(git branch --show-current); [ -n "$PREV" ] || fail "G0" "VM в состоянии detached HEAD: сначала вернитесь на ветку"
PREV_SHA=$(git rev-parse HEAD)
echo "ветка на VM сейчас: $PREV, коммит $(git rev-parse --short HEAD)"
restore() { git checkout -q -B "$PREV" "$PREV_SHA" 2>/dev/null; }
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "G0" "health недоступен"
has '"status":"ok"' "$H" || fail "G0" "health не ok до выкладки: $H"
AL=$(docker exec plan_estimate_backend alembic current 2>/dev/null)
has '0062_data_keys' "$AL" || fail "G0" "alembic current не 0062_data_keys: $AL (сначала должен быть выложен EN-2a)"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
KEYS=$(PSQL "select count(*) from data_keys")
[ "$KEYS" -ge 1 ] || fail "G0" "в базе нет ни одного ключа данных (data_keys пуст): EN-2a не использовался"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
# бэкап (A9) под ТЕКУЩУЮ голову не старше суток: перекодировка меняет значения в базе
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
[ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9"
AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
[ "$AGE_H" -le 24 ] || fail "G0" "последний бэкап $LASTRUN старше суток (${AGE_H} ч): сначала свежий A9 (cd ~/apps/plan_-_estimate && BACKUP_BRANCH=backlog-client-encryption BACKUP_HEAD=0062_data_keys bash ~/backup_a9.sh, в НОВОЙ сессии)"
echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
KEKTXT=$(grep -E '^DATA_KEK=' .env.production | head -1 | cut -d= -f2-)
[ -n "$KEKTXT" ] && [ "$(printf '%s' "$KEKTXT" | base64 -d 2>/dev/null | wc -c)" = "32" ] || fail "G0" "DATA_KEK в .env.production отсутствует или не base64 из 32 байт (ключ НЕ МЕНЯТЬ и не удалять: без него данные не прочитать)"
echo "ключ сервера на месте; отпечаток (8 знаков SHA-256): $(printf '%s' "$KEKTXT" | sha256sum | cut -c1-8)"
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend)
[ -z "$INFRA" ] || fail "G0" "Изменились образы / зависимости / frontend / Caddy (этого релиза там быть не должно): $INFRA"
MIG=$(git diff --name-only HEAD "origin/$BR" -- backend/alembic | grep -v '__pycache__' || true)
[ -z "$MIG" ] || fail "G0" "в релизе есть изменения миграций (этот скрипт — только для выкладки БЕЗ миграций): $MIG"
COMPDIFF=$(git diff HEAD "origin/$BR" -- docker-compose.prod.yml | grep -E '^[+-][^+-]' | grep -v '^+ *#' || true)
[ "$COMPDIFF" = '+      DATA_STRICT_READ: ${DATA_STRICT_READ:-false}' ] || fail "G0" "docker-compose.prod.yml должен получить ровно одну переменную DATA_STRICT_READ, а изменено: $COMPDIFF"
ENVDIFF=$(git diff HEAD "origin/$BR" -- .env.production.example | grep -E '^-[^-]' || true)
[ -z "$ENVDIFF" ] || fail "G0" ".env.production.example: строки удалены или изменены: $ENVDIFF"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(backend/app/|backend/tests/|docker-compose\.prod\.yml$|\.env\.production\.example$|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from clients; select count(*) from projects; select count(*) from project_representatives; select count(*) from project_notes; select count(*) from issued_documents; select count(*) from photo_attachments; select count(*) from photo_assets; select count(*) from purge_ledger; select count(*) from project_payments; select count(*) from data_keys;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/представители/заметки/документы/привязки фото/файлы фото/реестр удалений/записи расчётов/ключи = $BEFORE"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
fail1() { restore; fail "$1" "$2 (код на VM возвращён на $PREV, коммит $(echo "$PREV_SHA" | cut -c1-7))"; }
git checkout -q -B "$BR" "origin/$BR" || fail1 "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)" plan-estimate-backend:pre-en2b1 || fail1 "G1" "тег pre-en2b1 backend"
PC build backend > /tmp/build_en2b1.log 2>&1 || { tail -n 30 /tmp/build_en2b1.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend, тег pre-en2b1)"

echo; echo "################ ВОРОТА B: пересоздание backend (миграций нет, перекодировки ещё нет) ################"
echo "Что произойдёт: пересоздаётся ТОЛЬКО backend из собранного образа. Миграций НЕТ, данные НЕ меняются, строгое чтение остаётся ВЫКЛЮЧЕННЫМ."
echo "  • Простой API при пересоздании backend: около 30–60 секунд. Перекодировка и строгое чтение — отдельные ворота ниже."
echo "  • Откат безопасен (схема и данные не менялись): retag pre-en2b1 и up --no-deps --no-build backend. Команда напечатается при любом отказе."
echo "  • Отказ на этих воротах возвращает код на $PREV; production не меняется."
echo
echo "Чтобы пересоздать backend, введите ТОЧНО:  ВЫКЛАДКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYEN_TTY:-/dev/tty}" || { restore; fail "B" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА ДА" ] || { echo; restore; echo "Остановлено на воротах B (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "B (подтверждено вами)"

ROLLALL="Откат (схема не менялась; ДО перекодировки): 1) docker tag plan-estimate-backend:pre-en2b1 plan-estimate-backend:latest   2) $COMPOSE up -d --no-deps --no-build backend   3) git checkout -q -B $PREV $PREV_SHA"

echo; echo "################ G2: backend ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend --tail 120 2>&1)
has "Running upgrade" "$LOG" && fail "G2" "в логе применяется миграция, а в этом релизе их быть не должно. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError|DATA_KEK" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0062_data_keys' "$AL2" || fail "G2" "alembic не 0062: $AL2. $ROLLALL"
STRICT=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")
[ "$STRICT" = "false" ] || fail "G2" "строгое чтение уже включено ($STRICT), а на этом шаге оно должно быть выключено. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
KEY=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print(k[:6]+'…'+k[-4:], s.MEDIA_S3_BUCKET, s.DOCUMENT_DELIVERY)")
[ "$KEY" = "97bfe5…6dab plan-estimate-media-prod telegram" ] || fail "G2" "ключ/бакет/доставка не те: $KEY. $ROLLALL"
echo "--- отчёт команды перекодировки (ТОЛЬКО ЧТЕНИЕ; числа, без значений) ---"
docker exec plan_estimate_backend python -m app.cli.reencode_data report || fail "G2" "команда report не отработала. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ok "G2 (backend с командой перекодировки, миграций нет, строгое чтение выключено, цикл календаря как был: $LOOP_ENV, данные те же)"

echo; echo "################ ВОРОТА R: перекодировка старых значений ################"
PLAINNOW=$(docker exec plan_estimate_backend python -m app.cli.reencode_data report | grep '^TOTAL' || true)
echo "Сейчас: $PLAINNOW"
echo "Что произойдёт: каждое ОТКРЫТОЕ значение зашифрованных колонок (клиенты, объекты, представители, заметки) заменяется шифртекстом ключом владельца. Порциями по 200, каждая порция — своя транзакция."
echo "  • Значение, которое вы сохранили во время работы команды, НЕ затирается (такое пропускается и подхватывается повторным запуском). «Дата изменения» записей не меняется. Ничего не удаляется."
echo "  • Команда повторяема и возобновляема: можно остановить (Ctrl+C) и запустить снова."
echo "  • ВАЖНО: после перекодировки образ ДО EN-2a (шифрование) данные не прочитает. Запасной образ — EN-2a (тег pre-en2b1), он читает шифртекст."
echo "  • Бэкап перед перекодировкой: $LASTRUN (${AGE_H} ч назад)."
echo "  • Отказ на этих воротах ничего не меняет (backend уже новый, строгое чтение выключено): повторный запуск скрипта продолжит с этого места."
echo
echo "Чтобы перекодировать, введите ТОЧНО:  ПЕРЕКОДИРОВКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYEN_TTY:-/dev/tty}" || fail "R" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии"
[ "$ANSWER" = "ПЕРЕКОДИРОВКА ДА" ] || { echo; echo "Остановлено на воротах R (введено: '$ANSWER'). Данные не менялись. Backend уже новый (EN-2b-1), строгое чтение выключено."; exit 1; }
ok "R (подтверждено вами)"
ROLLR="Данные могли частично перекодироваться (это безопасно: читается и открытое, и шифртекст). Повторите:  docker exec plan_estimate_backend python -m app.cli.reencode_data apply  и затем  ... verify. Образ ДО EN-2a использовать нельзя."
echo; echo "################ G3: перекодировка и проверка ################"
APPLIED=no
for TRY in 1 2 3; do
  docker exec plan_estimate_backend python -m app.cli.reencode_data apply && { APPLIED=yes; break; }
  echo "(попытка $TRY: часть значений была изменена во время работы или остались открытые; повторяю)"
done
[ "$APPLIED" = "yes" ] || fail "G3" "перекодировка не довела дело до конца за 3 попытки. $ROLLR"
echo "--- проверка: все шифртексты расшифровываются, открытых значений нет ---"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify || fail "G3" "verify нашёл открытые или нерасшифровываемые значения. $ROLLR"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G3" "число строк изменилось: было $BEFORE стало $AFTER. $ROLLR"
ok "G3 (все значения зашифрованы и расшифровываются, число строк то же)"

echo; echo "################ ВОРОТА S: строгое чтение ################"
echo "Что произойдёт: в .env.production добавляется строка DATA_STRICT_READ=true, backend пересоздаётся (30–60 секунд). С этого момента открытое значение в зашифрованной колонке ОТКЛОНЯЕТСЯ (ошибка DATA_PLAIN_VALUE_REFUSED) — защита от пропущенных или записанных мимо приложения значений."
echo "  • Данные не меняются. Выключается строкой DATA_STRICT_READ=false и пересозданием backend (команда напечатается при любом отказе)."
echo
echo "Чтобы включить строгое чтение, введите ТОЧНО:  СТРОГОЕ ЧТЕНИЕ ДА"
printf '> '
read -r ANSWER < "${DEPLOYEN_TTY:-/dev/tty}" || fail "S" "нет терминала для подтверждения"
[ "$ANSWER" = "СТРОГОЕ ЧТЕНИЕ ДА" ] || { echo; echo "Остановлено на воротах S (введено: '$ANSWER'). Данные перекодированы, строгое чтение ВЫКЛЮЧЕНО (можно включить позже повторным запуском скрипта)."; exit 1; }
ok "S (подтверждено вами)"
ROLLS="Выключить строгое чтение: удалите или поменяйте строку DATA_STRICT_READ в .env.production на DATA_STRICT_READ=false и выполните  $COMPOSE up -d --no-deps backend"
if grep -q '^DATA_STRICT_READ=' .env.production; then sed -i 's/^DATA_STRICT_READ=.*/DATA_STRICT_READ=true/' .env.production; else printf 'DATA_STRICT_READ=true\n' >> .env.production; fi
[ "$(grep -c '^DATA_STRICT_READ=true$' .env.production)" = "1" ] || fail "S" "в .env.production не получилась ровно одна строка DATA_STRICT_READ=true. $ROLLS"
PC up -d --no-deps backend || fail "S" "up backend не удался. $ROLLS"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "S" "backend не стал healthy. $ROLLS"; }
STRICT=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")
[ "$STRICT" = "true" ] || fail "S" "в контейнере DATA_STRICT_READ=$STRICT, ожидалось true. $ROLLS"
RD=$(docker exec plan_estimate_backend python -c "
import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker
from app.domain.services.data_key_service import DataKeyService
from app.models import Client, Project, ProjectNote, ProjectRepresentative
async def main():
    async with async_session_maker() as s:
        print(await DataKeyService(s).prepare(), end=' ')
        for model, cols in ((Client, ('first_name','last_name','company_name','phone','email','nip','street','postal_code','city','telegram_username','notes')), (Project, ('name','address','city','postal_code','description')), (ProjectRepresentative, ('name','phone','email')), (ProjectNote, ('body',))):
            rows = (await s.execute(select(model))).scalars().all()
            for row in rows:
                for c in cols: getattr(row, c)
            print(len(rows), end=' ')
asyncio.run(main())") || fail "S" "в строгом режиме чтение строк упало (где-то остались открытые значения). $ROLLS"
SQLRD=$(PSQL "select (select count(*) from clients), (select count(*) from projects), (select count(*) from project_representatives), (select count(*) from project_notes)" | tr '|' ' ')
echo "строки, прочитанные приложением в СТРОГОМ режиме (ключи клиенты объекты представители заметки): $RD; независимый подсчёт: $SQLRD"
[ "$RD" = "True $SQLRD " ] || fail "S" "приложение прочитало не столько строк, сколько в базе. $ROLLS"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "S" "verify после включения не прошёл. $ROLLS"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "S" "число строк изменилось: было $BEFORE стало $AFTER. $ROLLS"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "S" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLS"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "S" "health не ok. $ROLLS"
ok "S (строгое чтение включено, все строки читаются, число строк то же)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена, старые значения перекодированы, строгое чтение включено, данные те же ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram, откройте Mini App: клиенты, поиск, объекты, заметки, представители, календарь, архив — как раньше (чек-лист EN-2a, раздел 4 docs/CLIENT_ENCRYPTION_EN2A_RUNBOOK_RU.md);"
echo "  2) бэкап под текущую голову (теперь в нём ШИФРТЕКСТ): cd ~/apps/plan_-_estimate && BACKUP_BRANCH=$BR BACKUP_HEAD=0062_data_keys bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  3) EN-2b-2 (документы) и EN-2b-3 (расчёты) начинаются только по вашему отдельному «да»."
)
