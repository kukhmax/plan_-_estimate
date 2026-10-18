#!/usr/bin/env bash
# Шифрование данных клиентов, шаг EN-2b-3 (расчёты: «Faktury i zaliczki») — выкладка С МИГРАЦИЕЙ 0064, без новых зависимостей, только backend.
# Что меняется: название записи расчёта (за что), номер, магазин / поставщик и заметка (счета, авансы, платежи, расходы) — 4 колонки таблицы project_payments — будут храниться ШИФРТЕКСТОМ. Суммы, даты, вид и категория остаются открытыми (итоги и сроки считаются по ним).
# Миграция 0064 лишь превращает 3 колонки VARCHAR в TEXT и ничего в строках не меняет; старые значения читаются как есть, пока их не заменит команда перекодировки.
# ПОРЯДОК ВАЖЕН: строгое чтение (включено после EN-2b-1) на время миграции и перекодировки ВРЕМЕННО выключается (иначе старые записи отклонялись бы), затем включается снова. Скрипт делает это сам; при остановке посреди пути строгое чтение остаётся ВЫКЛЮЧЕННЫМ (безопасно).
# Ничего не удаляется. Запасной образ — предыдущий (тег pre-en2b3): он читает данные, пока не выполнена перекодировка; после неё образ до EN-2b-3 записи расчётов НЕ прочитает, откат миграции откажет, пока в этих колонках есть шифртекст.
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Скрипт можно запускать повторно (он узнаёт, что миграция уже применена). Ворота M (миграция), R (перекодировка), S (строгое чтение): вы САМИ вводите фразы. Значения и ключи не печатает (только числа).
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-client-encryption && git show origin/backlog-client-encryption:docs/CLIENT_ENCRYPTION_EN2B3_DEPLOY_RU.sh > ~/deploy_en2b3.sh && bash ~/deploy_en2b3.sh
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
if has '0064_encrypted_payments' "$AL"; then FIRST=no; echo "повторный запуск: миграция 0064 уже применена"
elif has '0063_encrypted_documents' "$AL"; then FIRST=yes
else fail "G0" "alembic current не 0063_encrypted_documents и не 0064_encrypted_payments: $AL"; fi
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
KEYS=$(PSQL "select count(*) from data_keys")
[ "$KEYS" -ge 1 ] || fail "G0" "в базе нет ни одного ключа данных (data_keys пуст)"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
# бэкап (A9) не старше суток: меняется колонка записей расчётов и их значения
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
[ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9"
AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
[ "$AGE_H" -le 24 ] || fail "G0" "последний бэкап $LASTRUN старше суток (${AGE_H} ч). Свежий бэкап ПОД ГОЛОВУ 0063 нельзя сделать из ветки backlog-client-encryption (она уже заканчивается миграцией 0064: образы бэкапа обязаны совпасть с базой). Нужен бэкап под 0063 не старше суток (после выкладки AC-6): сообщите мне, если его нет"
echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
KEKTXT=$(grep -E '^DATA_KEK=' .env.production | head -1 | cut -d= -f2-)
[ -n "$KEKTXT" ] && [ "$(printf '%s' "$KEKTXT" | base64 -d 2>/dev/null | wc -c)" = "32" ] || fail "G0" "DATA_KEK в .env.production отсутствует или не base64 из 32 байт (ключ НЕ МЕНЯТЬ и не удалять)"
echo "ключ сервера на месте; отпечаток (8 знаков SHA-256): $(printf '%s' "$KEKTXT" | sha256sum | cut -c1-8)"
STRICT_WAS=$(grep -E '^DATA_STRICT_READ=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z'); [ -n "$STRICT_WAS" ] || STRICT_WAS=false
echo "строгое чтение в .env.production сейчас: $STRICT_WAS (на время миграции и перекодировки оно выключается, потом включается снова, если было включено)"
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend docker-compose.prod.yml .env.production.example)
[ -z "$INFRA" ] || fail "G0" "Изменились образы / зависимости / frontend / compose / Caddy (этого релиза там быть не должно): $INFRA"
NEWMIG=$(git diff --name-only --diff-filter=A HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
CHGMIG=$(git diff --name-only --diff-filter=MD HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
[ -z "$CHGMIG" ] || fail "G0" "существующие миграции изменены или удалены: $CHGMIG"
if [ "$FIRST" = yes ]; then
  [ "$NEWMIG" = "backend/alembic/versions/0064_encrypted_payments.py" ] || fail "G0" "ожидается ровно одна новая миграция 0064_encrypted_payments.py, а пришло: $NEWMIG"
else
  [ -z "$NEWMIG" ] || fail "G0" "повторный запуск, а в релиз пришли новые миграции: $NEWMIG"
fi
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(backend/app/|backend/alembic/versions/0064_encrypted_payments\.py$|backend/tests/|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from clients; select count(*) from projects; select count(*) from project_representatives; select count(*) from project_notes; select count(*) from issued_documents; select count(*) from contracts; select count(*) from handover_protocols; select count(*) from concealed_works_protocols; select count(*) from acceptance_protocols; select count(*) from decision_protocols; select count(*) from downtime_episodes; select count(*) from photo_attachments; select count(*) from photo_assets; select count(*) from purge_ledger; select count(*) from project_payments;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/представители/заметки/журнал документов/договоры/протоколы (передача, скрытые работы, приёмка, решения)/простои/привязки фото/файлы фото/реестр удалений/записи расчётов = $BEFORE; ключей данных: $KEYS"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
fail1() { restore; fail "$1" "$2 (код на VM возвращён на $PREV, коммит $(echo "$PREV_SHA" | cut -c1-7))"; }
git checkout -q -B "$BR" "origin/$BR" || fail1 "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
if docker image inspect plan-estimate-backend:pre-en2b3 > /dev/null 2>&1; then
  echo "тег pre-en2b3 уже есть (образ ДО этого шага, запасной): не перезаписываю"
else
  docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)" plan-estimate-backend:pre-en2b3 || fail1 "G1" "тег pre-en2b3 backend"
fi
PC build backend > /tmp/build_en2b3.log 2>&1 || { tail -n 30 /tmp/build_en2b3.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend, тег pre-en2b3)"

if [ "$FIRST" = yes ]; then
echo; echo "################ ВОРОТА M: миграция базы данных ################"
echo "Миграция 0064_encrypted_payments (проверена на PostgreSQL 16: вверх, вниз, вверх; отказ отката, пока есть шифртекст):"
echo "  • ПРЕВРАЩАЕТ в TEXT 3 колонки записей расчётов (VARCHAR → TEXT): название (за что), номер, магазин / поставщик; заметка уже TEXT. Значения НЕ меняются (старое значение читается как раньше). Суммы, даты, вид и категория остаются открытыми."
echo "  • Время: миллисекунды (таблицы малы), в одной транзакции: при ошибке откат целиком. Простой API при пересоздании backend: около 30–60 секунд. Ничего не удаляется."
echo "  • На время миграции и перекодировки скрипт ВЫКЛЮЧАЕТ строгое чтение в .env.production (было: $STRICT_WAS) и вернёт его на воротах S."
echo "  • ОТКАТ: пока ничего не перекодировано — миграция откатывается командой из сообщения об ошибке, затем прежний образ pre-en2b3. ПОСЛЕ перекодировки откат миграции откажется, а образ до EN-2b-3 не прочитает записи расчётов: только вперёд."
echo "  • Бэкап перед миграцией: $LASTRUN (${AGE_H} ч назад)."
echo "  • Отказ на этих воротах возвращает код на $PREV; ничего не меняется."
echo
echo "Чтобы применить миграцию и пересоздать backend, введите ТОЧНО:  МИГРАЦИЯ 0064 ДА"
printf '> '
read -r ANSWER < "${DEPLOYEN_TTY:-/dev/tty}" || { restore; fail "M" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "МИГРАЦИЯ 0064 ДА" ] || { echo; restore; echo "Остановлено на воротах M (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "M (подтверждено вами)"
fi

ROLLALL="Откат (ПОРЯДОК ВАЖЕН; возможен, только пока ничего не перекодировано): 1) $COMPOSE run --rm --no-deps --entrypoint alembic backend downgrade 0063_encrypted_documents   2) docker tag plan-estimate-backend:pre-en2b3 plan-estimate-backend:latest   3) $COMPOSE up -d --no-deps --no-build backend   4) git checkout -q -B $PREV $PREV_SHA   (и верните строгое чтение: DATA_STRICT_READ=$STRICT_WAS в .env.production)"

echo; echo "################ G2: строгое чтение выключается, backend, миграция ################"
if [ "$STRICT_WAS" = true ]; then sed -i 's/^DATA_STRICT_READ=.*/DATA_STRICT_READ=false/' .env.production; fi
[ "$(grep -c '^DATA_STRICT_READ=true$' .env.production)" = "0" ] || fail "G2" "не удалось выключить строгое чтение в .env.production. $ROLLALL"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend --tail 120 2>&1)
if [ "$FIRST" = yes ]; then has "Running upgrade 0063_encrypted_documents -> 0064_encrypted_payments" "$LOG" || fail "G2" "в логе нет применения миграции 0063 -> 0064. $ROLLALL"; fi
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError|DATA_KEK" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
STARTED=$(docker logs plan_estimate_backend 2>&1 | grep -c "Application startup complete" || true)
[ "${STARTED:-0}" -ge 1 ] || fail "G2" "в логе контейнера нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0064_encrypted_payments' "$AL2" || fail "G2" "alembic не 0064: $AL2. $ROLLALL"
STRICT=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")
[ "$STRICT" = "false" ] || fail "G2" "строгое чтение в контейнере: $STRICT, ожидалось false (на время перекодировки). $ROLLALL"
TEXTCOLS=$(docker exec plan_estimate_backend python -c "
import asyncio, importlib.util
from sqlalchemy import text
from app.core.database import async_session_maker
spec = importlib.util.spec_from_file_location('m', '/app/alembic/versions/0064_encrypted_payments.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
async def main():
    async with async_session_maker() as s:
        n = total = 0
        for table, cols in m.COLUMNS.items():
            for name, _kind, _nullable in cols:
                total += 1
                kind = (await s.execute(text('select data_type from information_schema.columns where table_name = :t and column_name = :c'), {'t': table, 'c': name})).scalar_one()
                n += kind == 'text'
        print(n, total)
asyncio.run(main())") || fail "G2" "проверка типов колонок упала. $ROLLALL"
[ "$TEXTCOLS" = "4 4" ] || fail "G2" "колонок TEXT среди 4: '$TEXTCOLS', ожидалось '4 4'. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
KEY=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print(k[:6]+'…'+k[-4:], s.MEDIA_S3_BUCKET, s.DOCUMENT_DELIVERY)")
[ "$KEY" = "97bfe5…6dab plan-estimate-media-prod telegram" ] || fail "G2" "ключ/бакет/доставка не те: $KEY. $ROLLALL"
echo "--- отчёт команды перекодировки (ТОЛЬКО ЧТЕНИЕ; числа, без значений) ---"
docker exec plan_estimate_backend python -m app.cli.reencode_data report || fail "G2" "команда report не отработала. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ok "G2 (миграция 0064: 4 колонки TEXT, строгое чтение временно выключено, цикл календаря как был: $LOOP_ENV, данные те же)"

echo; echo "################ ВОРОТА R: перекодировка ################"
PLAINNOW=$(docker exec plan_estimate_backend python -m app.cli.reencode_data report | grep '^TOTAL' || true)
echo "Сейчас: $PLAINNOW"
echo "Что произойдёт: каждое ОТКРЫТОЕ значение зашифрованных колонок (теперь и записей расчётов) заменяется шифртекстом ключом владельца. Порциями по 200, каждая — своя транзакция. Ничего не удаляется; «дата изменения» не меняется; значение, изменённое в это время, не затирается."
echo "  • Повторяема и возобновляема (Ctrl+C и снова)."
echo "  • ВАЖНО: после перекодировки образ ДО EN-2b-3 записи расчётов не прочитает и откат миграции откажет. Запасной образ — pre-en2b3 годится только для задач ДО этого места."
echo "  • Бэкап перед перекодировкой: $LASTRUN (${AGE_H} ч назад)."
echo
echo "Чтобы перекодировать, введите ТОЧНО:  ПЕРЕКОДИРОВКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYEN_TTY:-/dev/tty}" || fail "R" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии"
[ "$ANSWER" = "ПЕРЕКОДИРОВКА ДА" ] || { echo; echo "Остановлено на воротах R (введено: '$ANSWER'). Данные не менялись, строгое чтение сейчас ВЫКЛЮЧЕНО; повторный запуск скрипта продолжит с этого места."; exit 1; }
ok "R (подтверждено вами)"
ROLLR="Данные могли частично перекодироваться (это безопасно: читается и открытое, и шифртекст). Повторите:  docker exec plan_estimate_backend python -m app.cli.reencode_data apply  и затем  ... verify. Образ ДО EN-2b-3 использовать нельзя."
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
KEYS2=$(PSQL "select count(*) from data_keys")
[ "$KEYS2" -ge "$KEYS" ] || fail "G3" "ключей данных стало меньше: было $KEYS стало $KEYS2. $ROLLR"
[ "$KEYS2" = "$KEYS" ] || echo "ключей данных было $KEYS, стало $KEYS2: команда создала ключ владельцу, у которого были записи, но не было ключа (штатно)"
ok "G3 (все значения зашифрованы и расшифровываются, число строк то же, ключей данных: $KEYS2)"

echo; echo "################ ВОРОТА S: строгое чтение ################"
echo "Что произойдёт: в .env.production ставится DATA_STRICT_READ=true, backend пересоздаётся (30–60 секунд); скрипт читает ВСЕ строки всех зашифрованных таблиц (клиенты, объекты, представители, заметки, договоры, протоколы, простои, журнал документов, записи расчётов) в строгом режиме."
echo "  • Данные не меняются. Выключается строкой DATA_STRICT_READ=false и пересозданием backend."
echo
echo "Чтобы включить строгое чтение, введите ТОЧНО:  СТРОГОЕ ЧТЕНИЕ ДА"
printf '> '
read -r ANSWER < "${DEPLOYEN_TTY:-/dev/tty}" || fail "S" "нет терминала для подтверждения"
[ "$ANSWER" = "СТРОГОЕ ЧТЕНИЕ ДА" ] || { echo; echo "Остановлено на воротах S (введено: '$ANSWER'). Данные перекодированы, строгое чтение ВЫКЛЮЧЕНО (можно включить повторным запуском скрипта)."; exit 1; }
ok "S (подтверждено вами)"
ROLLS="Выключить строгое чтение: DATA_STRICT_READ=false в .env.production и  $COMPOSE up -d --no-deps backend"
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
from sqlalchemy import func, select
from app.core.database import async_session_maker, Base
from app.domain.services.data_key_service import DataKeyService
from app.domain.services.data_reencode_service import encrypted_columns
import app.models
async def main():
    wanted = {}
    for c in encrypted_columns():
        wanted.setdefault(c.table, []).append(c.column)
    classes = {m.local_table.name: m.class_ for m in Base.registry.mappers}
    async with async_session_maker() as s:
        print(await DataKeyService(s).prepare(), end=' ')
        total = 0
        for table in sorted(wanted):
            rows = (await s.execute(select(classes[table]))).scalars().all()
            for row in rows:
                for column in wanted[table]:
                    getattr(row, column)
            total += len(rows)
        print(len(wanted), total, end=' ')
asyncio.run(main())") || fail "S" "в строгом режиме чтение строк упало (где-то остались открытые значения). $ROLLS"
SQLRD=$(PSQL "select (select count(*) from clients) + (select count(*) from projects) + (select count(*) from project_representatives) + (select count(*) from project_notes) + (select count(*) from issued_documents) + (select count(*) from contracts) + (select count(*) from handover_protocols) + (select count(*) from concealed_works_protocols) + (select count(*) from acceptance_protocols) + (select count(*) from decision_protocols) + (select count(*) from downtime_episodes) + (select count(*) from project_payments)")
echo "строки, прочитанные приложением в СТРОГОМ режиме (ключи таблиц строк): $RD; независимый подсчёт строк: $SQLRD"
[ "$RD" = "True 12 $SQLRD " ] || fail "S" "приложение прочитало не то число таблиц или строк, что в базе. $ROLLS"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "S" "verify после включения не прошёл. $ROLLS"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "S" "число строк изменилось: было $BEFORE стало $AFTER. $ROLLS"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "S" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLS"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "S" "health не ok. $ROLLS"
ok "S (строгое чтение включено, все строки 12 таблиц читаются, число строк то же)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена, миграция 0064 применена, записи расчётов зашифрованы, строгое чтение включено, данные те же ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram, откройте Mini App: откройте объект → «Faktury i zaliczki»: старые и новые записи читаются, добавьте и измените запись, отправьте «Rozliczenie» (PDF придёт в чат), архив → «Faktury i zaliczki», календарь (срок счёта) — как раньше;"
echo "  2) бэкап под новую голову (теперь в нём шифртекст и записей расчётов): cd ~/apps/plan_-_estimate && BACKUP_BRANCH=$BR BACKUP_HEAD=0064_encrypted_payments bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  3) приёмка: «принимаем EN-2b-3»; слияние в main и переключение VM на main — только по отдельному «да»; дальше EN-3 (ротация, восстановление с ключом) — тоже только по вашему «да»."
)
