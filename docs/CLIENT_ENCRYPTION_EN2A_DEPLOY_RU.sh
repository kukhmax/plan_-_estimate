#!/usr/bin/env bash
# Шифрование данных клиентов, шаг EN-2a (V1: ключ сервера) — выкладка С МИГРАЦИЕЙ 0062, новой зависимостью (cryptography 50.0.2) и новой переменной окружения DATA_KEK.
# Что меняется: таблица data_keys (ключ данных владельца, хранится только ЗАВЁРНУТЫМ ключом сервера), текстовые колонки клиентов / объектов / представителей / заметок объекта становятся TEXT,
# четыре индекса клиентов снимаются (поиск идёт в Python после расшифровки). С этого момента ЗАПИСЫВАЕМЫЕ значения этих полей хранятся шифртекстом (enc1:…); старые значения остаются открытыми, пока
# их не перекодирует команда шага EN-2b (до этого шифрование защищает только новые и изменённые значения). Читается всё: и открытое, и шифртекст.
# БЕЗ КЛЮЧА DATA_KEK backend НЕ ЗАПУСКАЕТСЯ (так задумано: чтобы не писать открытым текстом по забывчивости). Ключ создаёте ВЫ, один раз, на VM; его копию вы кладёте в менеджер паролей и на бумагу ДО выкладки.
# ПОТЕРЯ КЛЮЧА = ПОТЕРЯ ДАННЫХ, КОТОРЫЕ ОН ЗАЩИЩАЕТ: из базы и бэкапов ключ не восстановить.
# Откат: образ backend прежней версии НЕ прочитает записанный шифртекст. Поэтому откат образа безопасен только пока ничего не сохранено шифртекстом (после выкладки и до первого сохранения клиента / объекта / заметки / представителя).
# Дальше — только вперёд (новым выпуском) или из бэкапа A9. Откат миграции отказывает, пока в этих колонках есть шифртекст.
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Ворота K (ключ сохранён) и M (миграция): вы САМИ вводите фразы. Секреты не печатает (о ключе — только его короткий отпечаток).
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-client-encryption && git show origin/backlog-client-encryption:docs/CLIENT_ENCRYPTION_EN2A_DEPLOY_RU.sh > ~/deploy_en2a.sh && bash ~/deploy_en2a.sh
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
has '0061_expense_category' "$AL" || fail "G0" "alembic current не 0061_expense_category: $AL (выкладка рассчитана на базу ровно на 0061)"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
# бэкап (A9) должен быть сделан НЕДАВНО (не старше суток): с этой выкладки в базу начинает попадать шифртекст
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
[ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9 (раздел 2 runbook)"
AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
[ "$AGE_H" -le 24 ] || fail "G0" "последний бэкап $LASTRUN старше суток (${AGE_H} ч): сначала свежий A9 (BACKUP_BRANCH=<ветка> BACKUP_HEAD=0061_expense_category bash ~/backup_a9.sh, в НОВОЙ сессии)"
echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
# ключ сервера: есть в .env.production, это base64 ровно 32 байт; сам ключ НЕ печатается
KEKTXT=$(grep -E '^DATA_KEK=' .env.production | head -1 | cut -d= -f2-)
[ -n "$KEKTXT" ] || fail "G0" "в .env.production нет DATA_KEK. Создайте ключ ОДИН РАЗ:  echo \"DATA_KEK=\$(openssl rand -base64 32)\" >> .env.production  — затем сохраните его копию (раздел «Ключ» в docs/CLIENT_ENCRYPTION_EN2A_RUNBOOK_RU.md) и запустите скрипт снова"
[ "$(printf '%s' "$KEKTXT" | base64 -d 2>/dev/null | wc -c)" = "32" ] || fail "G0" "DATA_KEK в .env.production — не base64 ровно из 32 байт (так backend не запустится). Если ключ ещё ни разу не использовался (шифртекста в базе нет), замените его: удалите строку DATA_KEK и создайте новую командой  echo \"DATA_KEK=\$(openssl rand -base64 32)\" >> .env.production ; если с ним уже записывался шифртекст — НЕ МЕНЯЙТЕ ключ, сообщите мне"
[ "$(grep -cE '^DATA_KEK=' .env.production)" = "1" ] || fail "G0" "в .env.production больше одной строки DATA_KEK"
FPR=$(printf '%s' "$KEKTXT" | sha256sum | cut -c1-8)
echo "ключ сервера найден; его ОТПЕЧАТОК (первые 8 знаков SHA-256; по нему вы сверите свою сохранённую копию): $FPR"
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod)
[ -z "$INFRA" ] || fail "G0" "Изменились образы / зависимости frontend / Caddy (этого релиза там быть не должно): $INFRA"
REQADD=$(git diff HEAD "origin/$BR" -- backend/requirements.txt | grep -E '^[+-][^+-]' | grep -v '^+#' || true)
[ "$REQADD" = "+cryptography==50.0.2" ] || fail "G0" "backend/requirements.txt должен получить ровно одну зависимость cryptography==50.0.2 (и комментарии), а изменено: $REQADD"
OCIDIFF=$(git diff HEAD "origin/$BR" -- backend/requirements-oci.txt | grep -E '^[+-][^+-]' | grep -v '^+#' || true)
[ "$OCIDIFF" = "-cryptography==50.0.2" ] || fail "G0" "backend/requirements-oci.txt должен только потерять строку cryptography==50.0.2 (перенесена в requirements.txt), а изменено: $OCIDIFF"
COMPDIFF=$(git diff HEAD "origin/$BR" -- docker-compose.prod.yml | grep -E '^[+-][^+-]' | grep -v '^+ *#' || true)
[ "$COMPDIFF" = "$(printf '+      DATA_KEK: ${DATA_KEK:-}\n+      DATA_KEK_VERSION: ${DATA_KEK_VERSION:-1}')" ] || fail "G0" "docker-compose.prod.yml должен получить ровно две переменные DATA_KEK и DATA_KEK_VERSION, а изменено: $COMPDIFF"
ENVDIFF=$(git diff HEAD "origin/$BR" -- .env.production.example | grep -E '^-[^-]' || true)
[ -z "$ENVDIFF" ] || fail "G0" ".env.production.example: строки удалены или изменены: $ENVDIFF"
NEWMIG=$(git diff --name-only --diff-filter=A HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
[ "$NEWMIG" = "backend/alembic/versions/0062_data_keys.py" ] || fail "G0" "ожидается ровно одна новая миграция 0062_data_keys.py, а пришло: $NEWMIG"
CHGMIG=$(git diff --name-only --diff-filter=MD HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
[ -z "$CHGMIG" ] || fail "G0" "существующие миграции изменены или удалены: $CHGMIG"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(backend/app/|backend/alembic/versions/0062_data_keys\.py$|backend/tests/|backend/requirements(-oci)?\.txt$|docker-compose\.prod\.yml$|\.env\.production\.example$|frontend/src/|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from clients; select count(*) from projects; select count(*) from project_representatives; select count(*) from project_notes; select count(*) from issued_documents; select count(*) from photo_attachments; select count(*) from photo_assets; select count(*) from purge_ledger; select count(*) from project_payments;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/представители/заметки/документы/привязки фото/файлы фото/реестр удалений/записи расчётов = $BEFORE"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
fail1() { restore; fail "$1" "$2 (код на VM возвращён на $PREV, коммит $(echo "$PREV_SHA" | cut -c1-7))"; }
git checkout -q -B "$BR" "origin/$BR" || fail1 "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-en2a  || fail1 "G1" "тег pre-en2a backend"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-en2a || fail1 "G1" "тег pre-en2a frontend"
PC build backend frontend > /tmp/build_en2a.log 2>&1 || { tail -n 30 /tmp/build_en2a.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-en2a; cryptography 50.0.2 установлена закреплённой)"

echo; echo "################ ВОРОТА K: ключ сервера (DATA_KEK) ################"
echo "Ключ защищает ВСЕ данные клиентов, которые с этого момента пишутся шифртекстом. Он лежит только в $PWD/.env.production на этой VM."
echo "  • Отпечаток ключа (SHA-256, 8 знаков): $FPR. Откройте менеджер паролей: у записи «Plan & Estimate — DATA_KEK» должен быть тот же отпечаток (команда:  printf '%s' \"<ваша копия>\" | sha256sum | cut -c1-8 ),"
echo "    и копия ключа должна быть ещё и на бумаге, в другом месте, чем сервер и бэкапы."
echo "  • Если ключ потерян, данные, записанные шифртекстом, НЕ восстановить ни из базы, ни из бэкапа (бэкап хранит тот же шифртекст)."
echo "  • Кто имеет ключ и базу, читает данные; ключ НЕ в репозитории, НЕ в образе, НЕ в бэкапах."
echo
echo "Чтобы подтвердить, что копия ключа сохранена и её отпечаток совпадает, введите ТОЧНО:  КЛЮЧ СОХРАНЁН $FPR"
printf '> '
read -r ANSWER < "${DEPLOYEN_TTY:-/dev/tty}" || { restore; fail "K" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "КЛЮЧ СОХРАНЁН $FPR" ] || { echo; restore; echo "Остановлено на воротах K (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "K (ключ сохранён, отпечаток $FPR подтверждён вами)"

echo; echo "################ ВОРОТА M: миграция базы данных ################"
echo "Миграция 0062_data_keys (проверена на PostgreSQL 16: вверх, вниз, вверх; отказ отката, пока есть шифртекст; 12 одновременных первых запросов нового владельца создают ровно один ключ):"
echo "  • СОЗДАЁТ пустую таблицу data_keys (ключ данных владельца, только завёрнутый ключом сервера; внешний ключ на users, ON DELETE CASCADE; один активный ключ на владельца)."
echo "  • ПРЕВРАЩАЕТ в TEXT 19 текстовых колонок (клиенты, объекты, представители, заметки: шифртекст длиннее прежнего предела); существующие значения НЕ меняются."
echo "  • СНИМАЕТ четыре индекса клиентов (по имени, фамилии, названию фирмы, телефону): поиск теперь идёт в приложении после расшифровки."
echo "  • Время: миллисекунды (метаданные), в одной транзакции: при ошибке откат целиком. Простой API при пересоздании backend: около 30–60 секунд. Ничего не удаляется."
echo "  • ПЕРВЫЙ ВХОД в приложение после выкладки создаёт ваш ключ данных; каждое СОХРАНЕНИЕ клиента / объекта / представителя / заметки записывает эти поля шифртекстом. Старые значения остаются открытыми до шага EN-2b (команда перекодировки, по вашему «да»)."
echo "  • ОТКАТ ИМЕЕТ ПОРЯДОК и ПРЕДЕЛ: пока вы ничего не сохраняли — миграция откатывается командой из сообщения об ошибке, затем возвращается прежний образ. ПОСЛЕ первого сохранения шифртекстом откат миграции откажется, а прежний образ не прочитает данные: только вперёд новым выпуском или из бэкапа $LASTRUN."
echo "  • Бэкап перед миграцией: $LASTRUN (${AGE_H} ч назад)."
echo "  • Отказ на этих воротах возвращает код на $PREV; ничего не меняется."
echo
echo "Чтобы применить миграцию и пересоздать backend и frontend, введите ТОЧНО:  МИГРАЦИЯ 0062 ДА"
printf '> '
read -r ANSWER < "${DEPLOYEN_TTY:-/dev/tty}" || { restore; fail "M" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "МИГРАЦИЯ 0062 ДА" ] || { echo; restore; echo "Остановлено на воротах M (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "M (подтверждено вами)"

ROLLALL="Откат (ПОРЯДОК ВАЖЕН; возможен, только пока ничего не сохранено шифртекстом): 1) $COMPOSE run --rm --no-deps --entrypoint alembic backend downgrade 0061_expense_category   2) docker tag plan-estimate-backend:pre-en2a plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-en2a plan-estimate-frontend:latest   3) $COMPOSE up -d --no-deps --no-build backend frontend   4) git checkout -q -B $PREV $PREV_SHA"

echo; echo "################ G2: backend + миграция ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты (без DATA_KEK или с неверным ключом он не запускается: смотрите лог выше). $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend --tail 120 2>&1)
has "Running upgrade 0061_expense_category -> 0062_data_keys" "$LOG" || fail "G2" "в логе нет применения миграции 0061 -> 0062. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError|DATA_KEK" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0062_data_keys' "$AL2" || fail "G2" "alembic не 0062: $AL2. $ROLLALL"
DBX=$(PSQL "select (select count(*) from information_schema.tables where table_name='data_keys'), (select count(*) from data_keys), (select count(*) from pg_indexes where indexname in ('ix_clients_company_name','ix_clients_phone','ix_clients_owner_first_name','ix_clients_owner_last_name')), (select count(*) from information_schema.columns where data_type='text' and ((table_name='clients' and column_name in ('first_name','last_name','company_name','phone','email','nip','street','postal_code','city','telegram_username','notes')) or (table_name='projects' and column_name in ('name','address','city','postal_code','description')) or (table_name='project_representatives' and column_name in ('name','phone','email')))), (select count(*) from pg_indexes where indexname='uq_data_keys_one_active_per_owner')")
[ "$DBX" = "1|0|0|19|1" ] || fail "G2" "схема после миграции не та (data_keys|ключей|индексов клиентов|колонок TEXT|уникальный индекс): '$DBX', ожидалось 1|0|0|19|1. $ROLLALL"
CRY=$(docker exec plan_estimate_backend python -c "
import cryptography
from app.core import data_crypto as dc
from app.domain.services.data_key_service import server_kek
kek = server_kek()
dek = dc.new_key()
wrapped = dc.wrap_key(kek, dek, 'smoke')
stored = dc.encrypt_text(dek, 'smoke', 'clients.notes', 'Zażółć gęślą jaźń')
key_id, nonce, body = dc.split_value(stored)
print(cryptography.__version__, kek is not None, dc.unwrap_key(kek, wrapped, 'smoke') == dek, dc.decrypt_text(dek, 'clients.notes', nonce, body) == 'Zażółć gęślą jaźń', 'Zażółć' not in stored)") || fail "G2" "проверка шифрования в контейнере (без базы) упала. $ROLLALL"
[ "$CRY" = "50.0.2 True True True True" ] || fail "G2" "шифрование в контейнере: '$CRY', ожидалось '50.0.2 True True True True'. $ROLLALL"
# ТОЛЬКО ЧТЕНИЕ: каждая строка клиентов / объектов / представителей / заметок читается через приложение (ключи загружены, открытый текст читается мягко), число совпадает с SQL
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
asyncio.run(main())") || fail "G2" "чтение клиентов / объектов / представителей / заметок через приложение упало. $ROLLALL"
SQLRD=$(PSQL "select (select count(*) from clients), (select count(*) from projects), (select count(*) from project_representatives), (select count(*) from project_notes)" | tr '|' ' ')
echo "строки, прочитанные приложением (ключи загружены клиенты объекты представители заметки): $RD; независимый подсчёт: $SQLRD"
[ "$RD" = "True $SQLRD " ] || fail "G2" "приложение прочитало не столько строк, сколько в базе. $ROLLALL"
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
need = ['/api/clients', '/api/projects', '/api/calendar', '/api/projects/{project_id}/notes', '/api/projects/{project_id}/representatives', '/api/archive/structure', '/api/projects/{project_id}/payments']
print(all(n in p for n in need))")
[ "$API" = "True" ] || fail "G2" "в API нет нужных маршрутов: $API. $ROLLALL"
PURGER=$(docker exec plan_estimate_backend python -c "from app.api.deps import get_media_purger; print(type(get_media_purger()).__name__)")
[ "$PURGER" = "S3MediaPurger" ] || fail "G2" "порт удаления файлов не S3MediaPurger: $PURGER. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
if [ "$LOOP_ENV" = "true" ]; then
  has "calendar loop is not started" "$LOG" && fail "G2" "цикл календаря включён, но не запущен (нет токена бота). $ROLLALL"
  TOK=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(bool(s.TELEGRAM_BOT_TOKEN))")
  [ "$TOK" = "True" ] || fail "G2" "цикл календаря включён, а токена бота в контейнере нет: $TOK. $ROLLALL"
fi
KEY=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print(k[:6]+'…'+k[-4:], s.MEDIA_S3_BUCKET, s.DOCUMENT_DELIVERY)")
[ "$KEY" = "97bfe5…6dab plan-estimate-media-prod telegram" ] || fail "G2" "ключ/бакет/доставка не те: $KEY. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ok "G2 (миграция 0062 применена, схема, ключей данных пока 0, шифрование работает в контейнере, все строки читаются, цикл календаря как был: $LOOP_ENV, данные те же)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in plan-estimate-offline CHANGES_WAITING sync-screen show-calendar object-tile-payments data-tone journal-delete-understood security-probe probe-run-all show-security 'after_raw=' argon2id; do
  has "$MARK" "$BUNDLE" || fail "G3" "в выданной сборке нет '$MARK'. $ROLLALL"
done
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend на месте; страница «Test zabezpieczeń» с исправлением ответа \"null\")"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN DATA_KEK
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена, миграция 0062 применена, ключ сервера на месте (отпечаток $FPR), данные те же ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram, откройте Mini App по кнопке меню: клиенты, объекты, поиск клиента, заметки и представители должны выглядеть как раньше;"
echo "  2) проверка ключа и шифртекста (печатает ТОЛЬКО префиксы и числа, не данные):"
echo "       docker exec plan_estimate_postgres sh -c 'psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"select (select count(*) from data_keys), (select count(*) from clients where last_name like '\''enc1:%'\'')\"'"
echo "     после первого входа ключей = 1; клиентов с шифртекстом станет больше нуля после первого сохранения клиента (старые значения остаются открытыми до EN-2b);"
echo "  3) бэкап под новую голову: BACKUP_BRANCH=$BR BACKUP_HEAD=0062_data_keys bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  4) EN-2b (перекодировка старых значений и документы) начинается только по вашему отдельному «да»."
)
