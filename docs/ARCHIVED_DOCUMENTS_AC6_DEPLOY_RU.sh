#!/usr/bin/env bash
# Архивная чистка AC-6 — выкладка БЕЗ миграций: backend (список архивных договоров и протоколов и их удаление: GET /api/archive/documents, GET .../purge-preview, POST .../purge),
# frontend (вкладка «Umowy i protokoły» / «Договоры и протоколы» в архиве, у каждой записи «Usuń na zawsze…»), кнопка Telegram.
# Эта выкладка САМА НИЧЕГО НЕ УДАЛЯЕТ: она только добавляет вкладку и возможность удалять (само удаление — отдельно, вашими руками в приложении).
# Миграций нет: база остаётся на 0063_encrypted_documents; ключ шифрования, строгое чтение и цикл календаря не трогаются (скрипт проверяет, что они в том же состоянии).
# Откат БЕЗОПАСЕН образами: схема базы не меняется (теги pre-ac6). Откат образа не возвращает то, что уже удалено через приложение (удаление необратимо).
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Ворота B: контейнеры пересоздаются только после того, как вы САМИ введёте фразу. Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-client-encryption && git show origin/backlog-client-encryption:docs/ARCHIVED_DOCUMENTS_AC6_DEPLOY_RU.sh > ~/deploy_ac6.sh && bash ~/deploy_ac6.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
BR="${DEPLOYAC6_BRANCH:-backlog-client-encryption}"
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
has '0063_encrypted_documents' "$AL" || fail "G0" "alembic current не 0063_encrypted_documents: $AL (эта выкладка — без миграций и рассчитана на базу на 0063)"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
STRICT_ENV=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower(), bool(s.DATA_KEK.get_secret_value()) if s.DATA_KEK else False)")
[ "$STRICT_ENV" = "true True" ] || fail "G0" "строгое чтение / ключ шифрования в контейнере: '$STRICT_ENV', ожидалось 'true True' (состояние после EN-2b-2)"
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
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from contracts; select count(*) from handover_protocols; select count(*) from concealed_works_protocols; select count(*) from acceptance_protocols; select count(*) from decision_protocols; select count(*) from downtime_episodes; select count(*) from data_keys; select count(*) from photo_attachments; select count(*) from photo_assets;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/журнал/договоры/передачи/скрытые/приёмки/решения/простои/ключи/привязки фото/файлы фото = $BEFORE"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
fail1() { restore; fail "$1" "$2 (код на VM возвращён на $PREV, коммит $(echo "$PREV_SHA" | cut -c1-7))"; }
git checkout -q -B "$BR" "origin/$BR" || fail "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
if ! docker image inspect plan-estimate-backend:pre-ac6 > /dev/null 2>&1; then
  docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-ac6  || fail1 "G1" "тег pre-ac6 backend"
  docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-ac6 || fail1 "G1" "тег pre-ac6 frontend"
fi
PC build backend frontend > /tmp/build_ac6.log 2>&1 || { tail -n 30 /tmp/build_ac6.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-ac6)"

echo; echo "################ ВОРОТА B: пересоздание контейнеров (миграций нет) ################"
echo "Что произойдёт: пересоздаются backend и frontend из собранных образов."
echo "  • Миграций НЕТ: схема базы и данные не меняются; ключ шифрования и строгое чтение остаются как были. Выкладка НИЧЕГО не удаляет: в архиве появляется вкладка «Umowy i protokoły»; удаление записи — только когда вы его подтвердите в приложении."
echo "  • Простой API при пересоздании backend: около 30–60 секунд."
echo "  • Откат безопасен образами (схема не менялась): retag pre-ac6 и up --no-deps --no-build backend frontend. Команда напечатается при любом отказе."
echo "  • Отказ на этих воротах возвращает код на $PREV; production не меняется."
echo
echo "Чтобы пересоздать backend и frontend, введите ТОЧНО:  ВЫКЛАДКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYAC6_TTY:-/dev/tty}" || { restore; fail "B" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА ДА" ] || { echo; restore; echo "Остановлено на воротах B (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "B (подтверждено вами)"

ROLLALL="Откат (схема базы не менялась): 1) docker tag plan-estimate-backend:pre-ac6 plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-ac6 plan-estimate-frontend:latest   2) $COMPOSE up -d --no-deps --no-build backend frontend   3) git checkout -q -B $PREV $PREV_SHA"

echo; echo "################ G2: backend ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend 2>&1)
has "Running upgrade" "$LOG" && fail "G2" "в логе применяется миграция, а в этом релизе их быть не должно. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0063_encrypted_documents' "$AL2" || fail "G2" "alembic не 0063: $AL2. $ROLLALL"
STRICT=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")
[ "$STRICT" = "true" ] || fail "G2" "строгое чтение в контейнере: $STRICT, ожидалось true. $ROLLALL"
API=$(docker exec plan_estimate_backend python -c "
from app.main import app
p = app.openapi()['paths']
need = ['/api/archive/documents', '/api/archive/documents/{kind}/{record_id}/purge-preview', '/api/archive/documents/{kind}/{record_id}/purge', '/api/archive/payments', '/api/archive/structure', '/api/photos/archive']
print(all(n in p for n in need))")
[ "$API" = "True" ] || fail "G2" "в API нет нужных маршрутов: $API. $ROLLALL"
# список архива документов (ТОЛЬКО ЧТЕНИЕ, в строгом режиме, с расшифровкой названий объектов) на настоящей базе: число записей сходится с независимым подсчётом
DOCS=$(docker exec plan_estimate_backend python -c "
import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker
from app.models.user import User
from app.domain.services.data_key_service import DataKeyService
from app.domain.services.archived_document_service import ArchivedDocumentService
async def main():
    async with async_session_maker() as s:
        print(await DataKeyService(s).prepare(), end=' ')
        total = shown = 0
        for uid in (await s.execute(select(User.id))).scalars().all():
            await DataKeyService(s).put_in_force(uid)
            found = await ArchivedDocumentService(s).list_archived(uid)
            total += found.total; shown += len(found.items)
            assert all(item.project_name for item in found.items)
        print(total, shown)
asyncio.run(main())") || fail "G2" "список архивных договоров и протоколов упал на настоящей базе. $ROLLALL"
SQLD=$(PSQL "select (select count(*) from contracts c join projects p on p.id = c.project_id where c.status = 'ARCHIVED' and not p.is_archived) + (select count(*) from handover_protocols c join projects p on p.id = c.project_id where c.status = 'ARCHIVED' and not p.is_archived) + (select count(*) from concealed_works_protocols c join projects p on p.id = c.project_id where c.status = 'ARCHIVED' and not p.is_archived) + (select count(*) from acceptance_protocols c join projects p on p.id = c.project_id where c.status = 'ARCHIVED' and not p.is_archived) + (select count(*) from decision_protocols c join projects p on p.id = c.project_id where c.status = 'ARCHIVED' and not p.is_archived) + (select count(*) from downtime_episodes c join projects p on p.id = c.project_id where c.status = 'ARCHIVED' and not p.is_archived)")
echo "архивные договоры и протоколы (ключи, всего, показано): сервис = $DOCS; независимый подсчёт = $SQLD"
[ "$DOCS" = "True $SQLD $SQLD" ] || fail "G2" "число записей сервиса и независимого подсчёта различаются. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "G2" "verify шифрования не прошёл. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ok "G2 (backend: миграций нет, база на 0063, строгое чтение включено, список архивных договоров и протоколов читается в строгом режиме и сходится с независимым подсчётом, данные те же)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in archive-tab- delete-document- document-delete-understood 'Umowy i protokoły' 'Договоры и протоколы' 'Brak zarchiwizowanych umów i protokołów' 'api/archive/documents'; do
  has "$MARK" "$BUNDLE" || fail "G3" "в выданной сборке нет '$MARK'. $ROLLALL"
done
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend: вкладка «Umowy i protokoły» в архиве, окно удаления)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена (миграций нет, база на 0063), данные те же, ничего не удалено ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram, откройте Mini App по кнопке меню: «Архив» → вкладка «Umowy i protokoły» — должен быть виден договор, который вы отправили в архив; «Usuń na zawsze…» — только открыть окно и нажать «Anuluj»;"
echo "  2) бэкап под текущую голову, если ещё не делали: cd ~/apps/plan_-_estimate && BACKUP_BRANCH=$BR BACKUP_HEAD=0063_encrypted_documents bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  3) приёмка: «принимаем AC-6»; слияние $BR → main и переключение VM на main — только по отдельному «да»."
)
