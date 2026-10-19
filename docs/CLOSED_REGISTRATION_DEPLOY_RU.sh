#!/usr/bin/env bash
# Закрытая регистрация — выкладка С МИГРАЦИЕЙ 0065 (две новые таблицы), backend + frontend, без новых зависимостей.
# Что меняется: в приложение входят только аккаунты Telegram из списка доступа (access_entries, статус ACTIVE); остальные видят «Brak dostępu» с вашим контактом и попадают в «Oczekujące» — вы решаете на экране «Dostęp» (меню, только у администратора).
# Миграция 0065 создаёт таблицы access_entries и access_settings и НИЧЕГО в существующих таблицах не меняет: все нынешние пользователи становятся ACTIVE, САМЫЙ РАННИЙ (первый вошедший, то есть вы) — администратором, регистрация переключается на ЗАКРЫТУЮ.
# Скрипт покажет пользователей и проверит, что администратор — вы. Если это не так, исправление одной командой напечатается в конце (python -m app.cli.access set-admin --telegram-id ...).
# Ключ шифрования, строгое чтение, цикл календаря, фото и данные не трогаются (скрипт проверяет, что они в том же состоянии). Ничего не удаляется.
# Откат БЕЗОПАСЕН образами: прежний образ работает и на новой схеме (новые таблицы ему не мешают); теги pre-access. Откат образа не возвращает регистрацию в «открытую» — для этого есть команда `access open`.
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Скрипт можно запускать повторно (он узнаёт, что миграция уже применена). Ворота B: контейнеры пересоздаются только после того, как вы САМИ введёте фразу. Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-closed-registration && git show origin/backlog-closed-registration:docs/CLOSED_REGISTRATION_DEPLOY_RU.sh > ~/deploy_access.sh && bash ~/deploy_access.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
BR="${DEPLOYACCESS_BRANCH:-backlog-closed-registration}"
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
if has '0065_access_control' "$AL"; then FIRST=no; echo "повторный запуск: миграция 0065 уже применена"
elif has '0064_encrypted_payments' "$AL"; then FIRST=yes
else fail "G0" "alembic current не 0064_encrypted_payments и не 0065_access_control: $AL"; fi
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
STRICT_ENV=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower(), bool(s.DATA_KEK.get_secret_value()) if s.DATA_KEK else False)")
[ "$STRICT_ENV" = "true True" ] || fail "G0" "строгое чтение / ключ шифрования в контейнере: '$STRICT_ENV', ожидалось 'true True' (состояние после EN-2b-2)"
# бэкап (A9) не старше суток: выкладка добавляет таблицы (бэкап под голову 0064 делается из ветки main, пока она на 0064)
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
[ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9 (BACKUP_BRANCH=main BACKUP_HEAD=0064_encrypted_payments bash ~/backup_a9.sh)"
AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
[ "$AGE_H" -le 24 ] || fail "G0" "последний бэкап $LASTRUN старше суток (${AGE_H} ч). Сделайте свежий: cd ~/apps/plan_-_estimate && git fetch -q origin main && git show origin/main:docs/STAGE_18_BACKUP_A9_RU.sh > ~/backup_a9.sh && BACKUP_BRANCH=main BACKUP_HEAD=0064_encrypted_payments bash ~/backup_a9.sh (в НОВОЙ сессии, потом закрыть её)"
echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
KEKTXT=$(grep -E '^DATA_KEK=' .env.production | head -1 | cut -d= -f2-)
[ -n "$KEKTXT" ] && [ "$(printf '%s' "$KEKTXT" | base64 -d 2>/dev/null | wc -c)" = "32" ] || fail "G0" "DATA_KEK в .env.production отсутствует или не base64 из 32 байт (ключ НЕ МЕНЯТЬ и не удалять)"
echo "ключ сервера на месте; отпечаток (8 знаков SHA-256): $(printf '%s' "$KEKTXT" | sha256sum | cut -c1-8)"
echo "пользователи (кто станет администратором — самый ранний):"; PSQL "select row_number() over (order by created_at, id), telegram_user_id, coalesce(username, '-'), to_char(created_at, 'YYYY-MM-DD HH24:MI') from users order by created_at, id" | sed 's/^/  /'
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod docker-compose.prod.yml .env.production.example)
[ -z "$INFRA" ] || fail "G0" "Изменились образы/зависимости/compose (этого релиза там быть не должно): $INFRA"
NEWMIG=$(git diff --name-only --diff-filter=A HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
CHGMIG=$(git diff --name-only --diff-filter=MD HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
[ -z "$CHGMIG" ] || fail "G0" "существующие миграции изменены или удалены: $CHGMIG"
[ "$NEWMIG" = "backend/alembic/versions/0065_access_control.py" ] || [ "$FIRST" = no -a -z "$NEWMIG" ] || fail "G0" "в релизе должна быть ровно одна новая миграция 0065_access_control.py, а здесь: '$NEWMIG'"
OTHERALEMBIC=$(git diff --name-only HEAD "origin/$BR" -- backend/alembic | grep -v '__pycache__' | grep -v '^backend/alembic/versions/0065_access_control.py$' || true)
[ -z "$OTHERALEMBIC" ] || fail "G0" "в alembic изменено что-то кроме миграции 0065: $OTHERALEMBIC"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(README.md|backend/app/|backend/alembic/versions/0065_access_control.py|backend/tests/|frontend/src/|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
USERS_BEFORE=$(PSQL "select count(*) from users")
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
# теги для отката: образ работающего контейнера; если docker не находит его по номеру (бывает с хранилищем образов containerd), берётся образ по имени :latest — он ещё не пересобран
tag_pre() {
  local svc="$1" t="plan-estimate-$1:pre-access" cur
  docker image inspect "$t" > /dev/null 2>&1 && return 0
  cur=$(docker inspect -f '{{.Image}}' "plan_estimate_$svc" 2>/dev/null)
  if [ -n "$cur" ] && docker image inspect "$cur" > /dev/null 2>&1; then docker tag "$cur" "$t" && return 0; fi
  if docker image inspect "plan-estimate-$svc:latest" > /dev/null 2>&1; then docker tag "plan-estimate-$svc:latest" "$t" && return 0; fi
  return 1
}
tag_pre backend || fail1 "G1" "нет образа backend для отката (тег pre-access)"
if tag_pre frontend; then FRONT_ROLLBACK=yes; else FRONT_ROLLBACK=no; echo "ВНИМАНИЕ: образа frontend для отката нет (frontend — статические файлы; откат при необходимости: git checkout на прежний коммит и docker compose build frontend && up -d --no-deps frontend). Продолжаем: backend откатывается образом."; fi
PC build backend frontend > /tmp/build_access.log 2>&1 || { tail -n 30 /tmp/build_access.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-access)"

echo; echo "################ ВОРОТА B: пересоздание контейнеров и миграция 0065 ################"
echo "Что произойдёт: пересоздаются backend и frontend из собранных образов."
echo "  • Миграция 0065 (при старте backend): две новые таблицы; существующие таблицы и данные не меняются. Все нынешние пользователи (их $USERS_BEFORE) становятся допущенными, самый ранний — администратором (см. список выше), регистрация становится ЗАКРЫТОЙ: новый аккаунт Telegram больше сам не регистрируется."
echo "  • Ключ шифрования и строгое чтение остаются как были. Ничего не удаляется."
echo "  • Простой API при пересоздании backend: около 30–60 секунд."
echo "  • Откат безопасен образами (прежний образ работает и на новой схеме): retag pre-access и up --no-deps --no-build backend frontend. Команда напечатается при любом отказе."
echo "  • Отказ на этих воротах возвращает код на $PREV; production не меняется."
echo
echo "Чтобы пересоздать backend и frontend, введите ТОЧНО:  ВЫКЛАДКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYACCESS_TTY:-/dev/tty}" || { restore; fail "B" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА ДА" ] || { echo; restore; echo "Остановлено на воротах B (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "B (подтверждено вами)"

if [ "$FRONT_ROLLBACK" = yes ]; then
  ROLLALL="Откат (новые таблицы прежнему образу не мешают): 1) docker tag plan-estimate-backend:pre-access plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-access plan-estimate-frontend:latest   2) $COMPOSE up -d --no-deps --no-build backend frontend   3) git checkout -q -B $PREV $PREV_SHA"
else
  ROLLALL="Откат (новые таблицы прежнему образу не мешают): 1) docker tag plan-estimate-backend:pre-access plan-estimate-backend:latest   2) $COMPOSE up -d --no-deps --no-build backend   3) git checkout -q -B $PREV $PREV_SHA && $COMPOSE build frontend && $COMPOSE up -d --no-deps frontend"
fi

echo; echo "################ G2: backend ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend 2>&1)
if [ "$FIRST" = yes ]; then has "Running upgrade 0064_encrypted_payments -> 0065_access_control" "$LOG" || fail "G2" "в логе нет применения миграции 0065. $ROLLALL"; fi
[ "$(grep -c 'Running upgrade' <<<"$LOG")" -le 1 ] || fail "G2" "в логе применяется больше одной миграции. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0065_access_control' "$AL2" || fail "G2" "alembic не 0065: $AL2. $ROLLALL"
STRICT=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")
[ "$STRICT" = "true" ] || fail "G2" "строгое чтение в контейнере: $STRICT, ожидалось true. $ROLLALL"
API=$(docker exec plan_estimate_backend python -c "
from app.main import app
p = app.openapi()['paths']
need = ['/api/access', '/api/access/entries/{entry_id}', '/api/access/settings', '/api/auth/telegram', '/api/me']
print(all(n in p for n in need))")
[ "$API" = "True" ] || fail "G2" "в API нет нужных маршрутов: $API. $ROLLALL"
# список доступа на настоящей базе (ТОЛЬКО ЧТЕНИЕ): каждый пользователь допущен, администратор один и это самый ранний пользователь, регистрация закрыта, чужой аккаунт получает отказ
NENT=$(PSQL "select count(*) from access_entries where status = 'ACTIVE'")
NADM=$(PSQL "select count(*) from access_entries where is_admin")
FIRSTUSER=$(PSQL "select telegram_user_id from users order by created_at, id limit 1")
ADMINID=$(PSQL "select telegram_user_id from access_entries where is_admin")
CLOSED=$(PSQL "select value from access_settings where key = 'closed'")
echo "список доступа: допущено $NENT из $USERS_BEFORE пользователей; администраторов $NADM (id $ADMINID, самый ранний пользователь: id $FIRSTUSER); регистрация закрыта = $CLOSED"
[ "$FIRST" = no ] || { [ "$NENT" = "$USERS_BEFORE" ] && [ "$NADM" = "1" ] && [ "$ADMINID" = "$FIRSTUSER" ] && [ "$CLOSED" = "1" ] || fail "G2" "список доступа не такой, каким его должна сделать миграция. $ROLLALL"; }
DEC=$(docker exec plan_estimate_backend python -c "
import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker
from app.models.user import User
from app.domain.exceptions import AccessDeniedError
from app.domain.services.access_service import AccessService
async def main():
    async with async_session_maker() as s:
        service = AccessService(s)
        admitted = 0
        for tid in (await s.execute(select(User.telegram_user_id))).scalars().all():
            await service.ensure_allowed(tid)
            admitted += 1
        refused = 0
        try:
            await service.ensure_allowed(1)
        except AccessDeniedError:
            refused = 1
        print(admitted, refused)
asyncio.run(main())") || fail "G2" "проверка доступа на настоящей базе упала (кто-то из нынешних пользователей не допущен?). $ROLLALL"
echo "проверка правил (допущено нынешних пользователей, чужой аккаунт отклонён): $DEC"
[ "$DEC" = "$USERS_BEFORE 1" ] || [ "$FIRST" = no ] || fail "G2" "правила доступа на настоящей базе работают не так: $DEC. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "G2" "verify шифрования не прошёл. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ok "G2 (backend: миграция 0065 применена, база на 0065, строгое чтение включено, нынешние пользователи допущены, администратор один, чужой аккаунт отклоняется, данные те же)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in show-access access-denied access-closed access-contact 'Dostęp do aplikacji' 'Доступ к приложению' 'Brak dostępu' 'api/access'; do
  has "$MARK" "$BUNDLE" || fail "G3" "в выданной сборке нет '$MARK'. $ROLLALL"
done
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend: пункт меню «Dostęp», экран списка доступа, карточка отказа)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена (миграция 0065, база на 0065), данные те же, ничего не удалено, регистрация ЗАКРЫТА ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram, откройте Mini App по кнопке меню: вы входите как раньше; в меню есть пункт «Dostęp» (только у вас) — откройте его: вы в «Aktywne» с пометкой «Administrator», ваш второй телефон (если он был в приложении) — тоже в «Aktywne»;"
echo "  2) если пункта «Dostęp» НЕТ у вас: администратором стал не тот аккаунт. Исправление (подставьте telegram id нужного аккаунта из списка пользователей выше):"
echo "       docker exec plan_estimate_backend python -m app.cli.access set-admin --telegram-id <id>"
echo "  3) впишите свой контакт на экране «Dostęp» (его видят отклонённые) и проверьте: аккаунт Telegram без доступа открывает бота и видит «Brak dostępu» с вашим контактом; у вас в «Oczekujące» появилась его заявка; нажмите «Dopuść» — он входит;"
echo "  4) аварийно (если вы не можете войти): docker exec plan_estimate_backend python -m app.cli.access open   (регистрация снова открытая) и  ... status  (числа);"
echo "  5) бэкап под новую голову (образы под 0065): cd ~/apps/plan_-_estimate && BACKUP_BRANCH=$BR BACKUP_HEAD=0065_access_control bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  6) приёмка: «принимаем закрытую регистрацию»; слияние $BR → main и переключение VM — только по отдельному «да»."
)
