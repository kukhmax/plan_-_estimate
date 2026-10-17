#!/usr/bin/env bash
# Архивная чистка AC-4b — выкладка БЕЗ миграций: backend (просмотр и само удаление архивного помещения и архивной поверхности: GET .../purge-preview и POST .../purge), frontend («Usuń na zawsze…» у архивных помещений и поверхностей),
# кнопка Telegram. Эта выкладка САМА НИЧЕГО НЕ УДАЛЯЕТ: она только добавляет возможность удалять (само удаление — отдельно, вашими руками в приложении).
# Миграций нет: база остаётся на 0057_purge_ledger. Цикл сообщений календаря не трогается (скрипт проверяет, что он в том же состоянии).
# Откат БЕЗОПАСЕН образами: схема базы не меняется, прежний образ (теги pre-ac4b) знает версию 0057. ВАЖНО: откат образа не возвращает то, что уже удалено через приложение (удаление необратимо).
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Ворота B: контейнеры пересоздаются только после того, как вы САМИ введёте фразу. Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-archive-cleanup && git show origin/backlog-archive-cleanup:docs/ARCHIVE_CLEANUP_DEPLOY4_RU.sh > ~/deploy_ac4.sh && bash ~/deploy_ac4.sh
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
has '0057_purge_ledger' "$AL" || fail "G0" "alembic current не 0057_purge_ledger: $AL (эта выкладка — без миграций и рассчитана на базу на 0057; сначала должна быть выложена архивная чистка AC-1…AC-3)"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
if [ -n "$LASTRUN" ]; then echo "последний бэкап (справочно; без миграций он не обязателен): $LASTRUN ($(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 )) ч назад)"; fi
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod docker-compose.prod.yml .env.production.example)
[ -z "$INFRA" ] || fail "G0" "Изменились образы/зависимости/compose (этого релиза там быть не должно): $INFRA"
MIG=$(git diff --name-only HEAD "origin/$BR" -- backend/alembic | grep -v '__pycache__' || true)
[ -z "$MIG" ] || fail "G0" "в релизе есть изменения миграций (этот скрипт — только для выкладки БЕЗ миграций): $MIG"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(backend/app/|backend/tests/|frontend/src/|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments; select count(*) from photo_assets; select count(*) from photo_annotations; select count(*) from purge_ledger;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/документы/привязки фото/файлы фото/метки/реестр удалений = $BEFORE"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
fail1() { restore; fail "$1" "$2 (код на VM возвращён на $PREV, коммит $(echo "$PREV_SHA" | cut -c1-7))"; }
git checkout -q -B "$BR" "origin/$BR" || fail1 "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-ac4b  || fail1 "G1" "тег pre-ac4b backend"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-ac4b || fail1 "G1" "тег pre-ac4b frontend"
PC build backend frontend > /tmp/build_ac4.log 2>&1 || { tail -n 30 /tmp/build_ac4.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-ac4b)"

echo; echo "################ ВОРОТА B: пересоздание контейнеров (миграций нет) ################"
echo "Что произойдёт: пересоздаются backend и frontend из собранных образов."
echo "  • Миграций НЕТ: схема базы и данные не меняются. Эта выкладка НИЧЕГО не удаляет: она добавляет в приложение удаление архивного помещения и архивной поверхности (само удаление — только когда вы его подтвердите в приложении)."
echo "  • Простой API при пересоздании backend: около 30–60 секунд. Фото и файлы не затрагиваются; НИЧЕГО не удаляется."
echo "  • Откат безопасен образами (схема не менялась): retag pre-ac4b и up --no-deps --no-build backend frontend. Команда напечатается при любом отказе."
echo "  • Отказ на этих воротах возвращает код на $PREV; production не меняется."
echo
echo "Чтобы пересоздать backend и frontend, введите ТОЧНО:  ВЫКЛАДКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYAC_TTY:-/dev/tty}" || { restore; fail "B" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА ДА" ] || { echo; restore; echo "Остановлено на воротах B (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "B (подтверждено вами)"

ROLLALL="Откат (схема базы не менялась): 1) docker tag plan-estimate-backend:pre-ac4b plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-ac4b plan-estimate-frontend:latest   2) $COMPOSE up -d --no-deps --no-build backend frontend   3) git checkout -q -B $PREV $PREV_SHA"

echo; echo "################ G2: backend ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend --tail 120 2>&1)
has "Running upgrade" "$LOG" && fail "G2" "в логе применяется миграция, а в этом релизе их быть не должно. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0057_purge_ledger' "$AL2" || fail "G2" "alembic не 0057: $AL2. $ROLLALL"
DBX=$(PSQL "select (select count(*) from information_schema.columns where table_name='photo_attachments' and column_name='trashed_at'), (select count(*) from pg_constraint where conname='ck_photo_attachments_trashed_is_archived'), (select count(*) from pg_indexes where indexname='ix_photo_attachments_project_trashed'), (select count(*) from information_schema.tables where table_name='purge_ledger')")
[ "$DBX" = "1|1|1|1" ] || fail "G2" "схема не та (колонка|проверка|индекс|таблица): '$DBX', ожидалось 1|1|1|1. $ROLLALL"
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
need = ['/api/calendar', '/api/projects/{project_id}/notes', '/api/photos/archive', '/api/archive/structure', '/api/clients/{client_id}/delete-preview', '/api/projects/{project_id}/purge-preview', '/api/projects/{project_id}/purge', '/api/projects/{project_id}/rooms/{room_id}/purge-preview', '/api/projects/{project_id}/rooms/{room_id}/purge', '/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/purge-preview', '/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/purge', '/api/projects/{project_id}/photo-attachments/{attachment_id}/trash', '/api/projects/{project_id}/photo-attachments/{attachment_id}/untrash', '/api/projects/{project_id}/photo-attachments/{attachment_id}/purge-preview', '/api/projects/{project_id}/photo-attachments/{attachment_id}/purge', '/api/photo-purge/status', '/api/photo-purge/retry']
print(all(n in p for n in need))")
[ "$API" = "True" ] || fail "G2" "в API нет нужных маршрутов (в том числе /api/photos/archive): $API. $ROLLALL"
PURGER=$(docker exec plan_estimate_backend python -c "from app.api.deps import get_media_purger; print(type(get_media_purger()).__name__)")
[ "$PURGER" = "S3MediaPurger" ] || fail "G2" "порт удаления файлов не S3MediaPurger: $PURGER. $ROLLALL"
# новый запрос архива работает на настоящей базе и согласуется с независимым подсчётом: фото в архиве / в корзине по всем владельцам
SMOKE=$(docker exec plan_estimate_backend python -c "
import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker
from app.models.user import User
from app.domain.services.photo_archive_service import PhotoArchiveService
async def main():
    async with async_session_maker() as s:
        a = t = 0
        for uid in (await s.execute(select(User.id))).scalars().all():
            page = await PhotoArchiveService(s).list_archive(uid, trashed=False, limit=5)
            a += page.archived_total; t += page.trashed_total
        print(a, t)
asyncio.run(main())") || fail "G2" "запрос архива фото упал на настоящей базе. $ROLLALL"
SQLA=$(PSQL "select count(*) from photo_attachments pa join photo_assets a on a.id = pa.asset_id where a.status = 'READY' and pa.trashed_at is null and (pa.archived_at is not null or a.archived_at is not null)")
SQLT=$(PSQL "select count(*) from photo_attachments pa join photo_assets a on a.id = pa.asset_id where a.status = 'READY' and pa.trashed_at is not null")
echo "фото в архиве / в корзине: сервис = $SMOKE; независимый подсчёт = $SQLA $SQLT"
[ "$SMOKE" = "$SQLA $SQLT" ] || fail "G2" "числа сервиса и независимого подсчёта различаются. $ROLLALL"
# архивные помещения / поверхности: запрос работает на настоящей базе и сходится с независимым подсчётом (объекты в работе, помещение в работе для поверхности)
STR=$(docker exec plan_estimate_backend python -c "
import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker
from app.models.user import User
from app.domain.services.archive_structure_service import ArchiveStructureService
async def main():
    async with async_session_maker() as s:
        r = u = 0
        for uid in (await s.execute(select(User.id))).scalars().all():
            found = await ArchiveStructureService(s).list_archived(uid)
            r += found.rooms_total; u += found.surfaces_total
        print(r, u)
asyncio.run(main())") || fail "G2" "запрос архивных помещений и поверхностей упал на настоящей базе. $ROLLALL"
SQLR=$(PSQL "select count(*) from rooms r join projects p on p.id = r.project_id where r.is_archived and not p.is_archived")
SQLS=$(PSQL "select count(*) from surfaces s join rooms r on r.id = s.room_id join projects p on p.id = r.project_id where s.is_archived and not r.is_archived and not p.is_archived")
echo "архивные помещения / поверхности: сервис = $STR; независимый подсчёт = $SQLR $SQLS"
[ "$STR" = "$SQLR $SQLS" ] || fail "G2" "числа сервиса и независимого подсчёта различаются (помещения / поверхности). $ROLLALL"
# просмотр удаления объекта (ТОЛЬКО ЧТЕНИЕ, ничего не удаляется): для каждого архивного объекта числа сервиса совпадают с независимым подсчётом
PRV=$(docker exec plan_estimate_backend python -c "
import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker
from app.models.project import Project
from app.domain.services.project_purge_service import ProjectPurgeService
async def main():
    async with async_session_maker() as s:
        n = rooms = surfaces = openings = photos = files = 0
        for pid, oid in (await s.execute(select(Project.id, Project.owner_id).where(Project.is_archived.is_(True)))).all():
            p = await ProjectPurgeService(s, None).preview(oid, pid)
            n += 1; rooms += p.rooms; surfaces += p.surfaces; openings += p.openings; photos += p.photos; files += p.photo_files
        print(n, rooms, surfaces, openings, photos, files)
asyncio.run(main())") || fail "G2" "просмотр удаления архивного объекта упал на настоящей базе. $ROLLALL"
SQLP=$(PSQL "select (select count(*) from projects where is_archived), (select count(*) from rooms r join projects p on p.id = r.project_id where p.is_archived), (select count(*) from surfaces s join rooms r on r.id = s.room_id join projects p on p.id = r.project_id where p.is_archived), (select count(*) from openings o join surfaces s on s.id = o.surface_id join rooms r on r.id = s.room_id join projects p on p.id = r.project_id where p.is_archived), (select count(*) from photo_attachments a join projects p on p.id = a.project_id where p.is_archived), (select count(*) from photo_assets a join projects p on p.id = a.project_id where p.is_archived)" | tr '|' ' ')
echo "архивные объекты (шт. помещения поверхности проёмы фото-привязки файлы): сервис = $PRV; независимый подсчёт = $SQLP"
[ "$PRV" = "$SQLP" ] || fail "G2" "числа просмотра удаления объекта и независимого подсчёта различаются. $ROLLALL"
# просмотр удаления архивных помещений и поверхностей (ТОЛЬКО ЧТЕНИЕ, ничего не удаляется) на настоящей базе: числа сервиса совпадают с независимым SQL-подсчётом
STRUCT=$(docker exec plan_estimate_backend python -c "
import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface
from app.domain.services.structure_purge_service import StructurePurgeService
async def main():
    async with async_session_maker() as s:
        service = StructurePurgeService(s, None)
        n = su = op = ins = ph = 0
        for rid, pid, oid in (await s.execute(select(Room.id, Room.project_id, Project.owner_id).join(Project, Room.project_id == Project.id).where(Room.is_archived.is_(True)))).all():
            p = await service.preview_room(oid, pid, rid)
            n += 1; su += p.surfaces; op += p.openings; ins += p.inspections; ph += p.photos
        m = sop = sph = 0
        for sid, rid, pid, oid in (await s.execute(select(Surface.id, Surface.room_id, Room.project_id, Project.owner_id).join(Room, Surface.room_id == Room.id).join(Project, Room.project_id == Project.id).where(Surface.is_archived.is_(True)))).all():
            p = await service.preview_surface(oid, pid, rid, sid)
            m += 1; sop += p.openings; sph += p.photos
        print(n, su, op, ins, ph, m, sop, sph)
asyncio.run(main())") || fail "G2" "просмотр удаления архивных помещений и поверхностей упал на настоящей базе. $ROLLALL"
SQLROOM=$(PSQL "with r as (select id from rooms where is_archived), s as (select id from surfaces where room_id in (select id from r)), o as (select id from openings where surface_id in (select id from s)), i as (select id from inspections where room_id in (select id from r)), f as (select id from inspection_findings where inspection_id in (select id from i)) select (select count(*) from r), (select count(*) from s), (select count(*) from o), (select count(*) from i), (select count(*) from photo_attachments a where a.room_id in (select id from r) or a.surface_id in (select id from s) or a.opening_id in (select id from o) or a.inspection_id in (select id from i) or a.finding_id in (select id from f))" | tr '|' ' ')
SQLSURF=$(PSQL "with s as (select id from surfaces where is_archived), o as (select id from openings where surface_id in (select id from s)), i as (select id from inspections where surface_id in (select id from s)), f as (select id from inspection_findings where inspection_id in (select id from i)) select (select count(*) from s), (select count(*) from o), (select count(*) from photo_attachments a where a.surface_id in (select id from s) or a.opening_id in (select id from o) or a.inspection_id in (select id from i) or a.finding_id in (select id from f))" | tr '|' ' ')
echo "архивные помещения (шт. поверхности проёмы осмотры фото) и поверхности (шт. проёмы фото): сервис = $STRUCT; независимый подсчёт = $SQLROOM $SQLSURF"
[ "$STRUCT" = "$SQLROOM $SQLSURF" ] || fail "G2" "числа просмотра удаления помещений / поверхностей и независимого подсчёта различаются. $ROLLALL"
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
ok "G2 (backend: миграций нет, база на 0057, запросы архива (фото, помещения, поверхности) и просмотр удаления объекта, помещений и поверхностей работают на настоящей базе и сходятся с независимым подсчётом, цикл календаря как был: $LOOP_ENV, данные те же)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in plan-estimate-offline CHANGES_WAITING sync-screen show-calendar photo-purge-confirm photo-untrash archive-photos archive-tab- delete-client- delete-project- project-delete-understood delete-room- delete-surface- structure-delete-understood 'Usunąć pomieszczenie na zawsze' 'Usunąć powierzchnię na zawsze' 'Usunąć obiekt na zawsze' 'Usunąć klienta na zawsze' 'Co zostanie usunięte' 'Pokazano najnowsze' 'Otwórz zdjęcie, aby je przywrócić albo przenieść do kosza'; do
  has "$MARK" "$BUNDLE" || fail "G3" "в выданной сборке нет '$MARK'. $ROLLALL"
done
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend: вкладки архива, удаление клиента, объекта, помещения и поверхности, корзина фото, окно «что будет удалено», работа без связи, экран синхронизации, календарь)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена (миграций нет, база на 0057), данные те же, ничего не удалено ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram, откройте Mini App по кнопке меню и пройдите чек-лист «Выкладка 4» в docs/ARCHIVE_CLEANUP_RUNBOOK_RU.md (окна «Usuń na zawsze…» у помещения и у поверхности — только открыть и нажать «Anuluj»);"
echo "  2) бэкап под новую голову, если ещё не делали: BACKUP_BRANCH=$BR BACKUP_HEAD=0057_purge_ledger bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  3) приёмка: «принимаем» — слияние $BR → main и переключение VM на main только по отдельному «да»;"
echo "  4) настоящее удаление фото и чистка копий в бэкапе — только по docs/ARCHIVE_PURGE_RUNBOOK_RU.md, отдельными шагами с вашим «да»."
)
