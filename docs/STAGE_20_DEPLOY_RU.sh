#!/usr/bin/env bash
# Stage 20 (аудит MVP) — выкладка БЕЗ миграций: backend + frontend, без новых зависимостей и без изменений compose.
# Что меняется: (F1) напоминание принимает только комнату и поверхность СВОЕГО объекта; (F3) production не запускается со слабым секретом сессий (JWT_SECRET_KEY),
# неверным токеном бота, включёнными mock-входом или DEBUG — поэтому скрипт ЗАРАНЕЕ проверяет ваш .env.production (значения не печатает); (F4) модели общения известны alembic;
# frontend: цели нажатия не меньше 44 px у кнопок, найденных аудитом на телефоне. База остаётся на 0065_access_control; ключ шифрования, строгое чтение, регистрация, цикл календаря и данные не трогаются.
# Откат БЕЗОПАСЕН образами (схема не менялась): теги pre-s20. Останавливается на первом непройденном условии (FAIL). Ворота B: контейнеры пересоздаются только после того, как вы САМИ введёте фразу. Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin stage-20 && git show origin/stage-20:docs/STAGE_20_DEPLOY_RU.sh > ~/deploy_s20.sh && bash ~/deploy_s20.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
BR="${DEPLOYS20_BRANCH:-stage-20}"
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
has '0065_access_control' "$AL" || fail "G0" "alembic current не 0065_access_control: $AL (эта выкладка — без миграций и рассчитана на базу на 0065)"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
STRICT_ENV=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower(), bool(s.DATA_KEK.get_secret_value()) if s.DATA_KEK else False)")
[ "$STRICT_ENV" = "true True" ] || fail "G0" "строгое чтение / ключ шифрования в контейнере: '$STRICT_ENV', ожидалось 'true True' (состояние после EN-2b-2)"
KEKTXT=$(grep -E '^DATA_KEK=' .env.production | head -1 | cut -d= -f2-)
[ -n "$KEKTXT" ] && [ "$(printf '%s' "$KEKTXT" | base64 -d 2>/dev/null | wc -c)" = "32" ] || fail "G0" "DATA_KEK в .env.production отсутствует или не base64 из 32 байт (ключ НЕ МЕНЯТЬ и не удалять)"
echo "ключ сервера на месте; отпечаток (8 знаков SHA-256): $(printf '%s' "$KEKTXT" | sha256sum | cut -c1-8)"
# F3: production теперь отказывается стартовать со слабым секретом сессий и неверным токеном бота — проверяем ЗАРАНЕЕ, значения не печатаем
envval() { grep -E "^$1=" .env.production | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"; }
JWT=$(envval JWT_SECRET_KEY)
JWTLEN=$(printf '%s' "$JWT" | wc -c)
echo "JWT_SECRET_KEY: длина $JWTLEN (нужно не меньше 32)"
[ "$JWTLEN" -ge 32 ] || fail "G0" "JWT_SECRET_KEY в .env.production короче 32 знаков или отсутствует. Production после этой выкладки не запустится. Исправление (все войдут заново автоматически через Telegram): NEW=\$(openssl rand -hex 32); замените строку JWT_SECRET_KEY=... в .env.production на JWT_SECRET_KEY=\$NEW и запустите скрипт снова"
if printf '%s' "$JWT" | tr 'A-Z' 'a-z' | grep -qE 'change|insecure|example|placeholder|secret-key|your-|xxx|todo'; then
  fail "G0" "JWT_SECRET_KEY похож на заглушку из примера. Замените: NEW=\$(openssl rand -hex 32), строка JWT_SECRET_KEY=\$NEW в .env.production, затем запустите скрипт снова (все войдут заново автоматически)"
fi
BOT=$(envval TELEGRAM_BOT_TOKEN)
printf '%s' "$BOT" | grep -qE '^[0-9]{6,}:[A-Za-z0-9_-]{30,}$' || fail "G0" "TELEGRAM_BOT_TOKEN в .env.production не похож на токен BotFather (число:строка). Исправьте (токен не пересылайте в чат)"
echo "TELEGRAM_BOT_TOKEN: форма верна"
JS_BEFORE=$(curl -fsS https://plan-estimate.pl/ | grep -o 'assets/index-[^"]*\.js' | head -1)
echo "сборка frontend сейчас: $JS_BEFORE"
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod docker-compose.prod.yml .env.production.example)
[ -z "$INFRA" ] || fail "G0" "Изменились образы/зависимости/compose (этого релиза там быть не должно): $INFRA"
MIG=$(git diff --name-only HEAD "origin/$BR" -- backend/alembic | grep -v '__pycache__' || true)
[ -z "$MIG" ] || fail "G0" "в релизе есть изменения миграций (этот скрипт — только для выкладки БЕЗ миграций): $MIG"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(README.md|backend/app/|backend/tests/|frontend/src/|docs/)' || true)
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
# теги для отката: образ работающего контейнера; если docker не находит его по номеру (бывает с хранилищем образов containerd), берётся образ по имени :latest — он ещё не пересобран
tag_pre() {
  local svc="$1" t="plan-estimate-$1:pre-s20" cur
  docker image inspect "$t" > /dev/null 2>&1 && return 0
  cur=$(docker inspect -f '{{.Image}}' "plan_estimate_$svc" 2>/dev/null)
  if [ -n "$cur" ] && docker image inspect "$cur" > /dev/null 2>&1; then docker tag "$cur" "$t" && return 0; fi
  if docker image inspect "plan-estimate-$svc:latest" > /dev/null 2>&1; then docker tag "plan-estimate-$svc:latest" "$t" && return 0; fi
  return 1
}
tag_pre backend || fail1 "G1" "нет образа backend для отката (тег pre-s20)"
if tag_pre frontend; then FRONT_ROLLBACK=yes; else FRONT_ROLLBACK=no; echo "ВНИМАНИЕ: образа frontend для отката нет (frontend — статические файлы; откат при необходимости: git checkout на прежний коммит и docker compose build frontend && up -d --no-deps frontend). Продолжаем: backend откатывается образом."; fi
PC build backend frontend > /tmp/build_s20.log 2>&1 || { tail -n 30 /tmp/build_s20.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-s20)"

echo; echo "################ ВОРОТА B: пересоздание контейнеров (миграций нет) ################"
echo "Что произойдёт: пересоздаются backend и frontend из собранных образов."
echo "  • Миграций НЕТ: схема базы (0065), данные, ключ шифрования, строгое чтение и регистрация остаются как были. Ничего не удаляется."
echo "  • Backend теперь сам проверяет при старте, что секрет сессий и токен бота надёжны (вы это уже проверили выше); при ошибке он не запустится, а скрипт напечатает откат."
echo "  • Простой API при пересоздании backend: около 30–60 секунд."
echo "  • Откат безопасен образами (схема не менялась): retag pre-s20 и up --no-deps --no-build backend frontend. Команда напечатается при любом отказе."
echo "  • Отказ на этих воротах возвращает код на $PREV; production не меняется."
echo
echo "Чтобы пересоздать backend и frontend, введите ТОЧНО:  ВЫКЛАДКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYS20_TTY:-/dev/tty}" || { restore; fail "B" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА ДА" ] || { echo; restore; echo "Остановлено на воротах B (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "B (подтверждено вами)"

if [ "$FRONT_ROLLBACK" = yes ]; then
  ROLLALL="Откат (схема базы не менялась): 1) docker tag plan-estimate-backend:pre-s20 plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-s20 plan-estimate-frontend:latest   2) $COMPOSE up -d --no-deps --no-build backend frontend   3) git checkout -q -B $PREV $PREV_SHA"
else
  ROLLALL="Откат (схема базы не менялась): 1) docker tag plan-estimate-backend:pre-s20 plan-estimate-backend:latest   2) $COMPOSE up -d --no-deps --no-build backend   3) git checkout -q -B $PREV $PREV_SHA && $COMPOSE build frontend && $COMPOSE up -d --no-deps frontend"
fi

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
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0065_access_control' "$AL2" || fail "G2" "alembic не 0065: $AL2. $ROLLALL"
STRICT=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")
[ "$STRICT" = "true" ] || fail "G2" "строгое чтение в контейнере: $STRICT, ожидалось true. $ROLLALL"
PROB=$(docker exec plan_estimate_backend python -c "
from app.core.config import settings
from app.core.startup_checks import production_problems
print(len(production_problems(settings)))") || fail "G2" "проверка настроек production в контейнере упала. $ROLLALL"
[ "$PROB" = "0" ] || fail "G2" "в контейнере production-настройки небезопасны ($PROB). $ROLLALL"
CODE=$(docker exec plan_estimate_backend python -c "
from app.domain.services.calendar_service import CalendarService
import app.models
from app.core.database import Base
print(hasattr(CalendarService, '_place_of_reminder'), len(Base.metadata.tables) >= 60)")
[ "$CODE" = "True True" ] || fail "G2" "в контейнере нет исправлений этой выкладки: $CODE. $ROLLALL"
# список доступа (ТОЛЬКО ЧТЕНИЕ): каждый нынешний пользователь допущен, как и до выкладки
USERS_N=$(PSQL "select count(*) from users"); ENTRIES_N=$(PSQL "select count(*) from access_entries where status = 'ACTIVE'")
[ "$USERS_N" = "$ENTRIES_N" ] || fail "G2" "допущено $ENTRIES_N из $USERS_N пользователей. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "G2" "verify шифрования не прошёл. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ok "G2 (backend: миграций нет, база на 0065, production-настройки безопасны, исправления на месте, строгое чтение включено, пользователи допущены, данные те же)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in show-access access-denied access-closed 'Dostęp do aplikacji' 'Доступ к приложению' archive-tab- show-security; do
  has "$MARK" "$BUNDLE" || fail "G3" "в выданной сборке нет '$MARK'. $ROLLALL"
done
JS_AFTER="$JS"
[ "$JS_AFTER" != "$JS_BEFORE" ] || fail "G3" "выданная сборка не изменилась ($JS_AFTER): frontend не пересобран. $ROLLALL"

H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend: новая сборка $JS_AFTER вместо $JS_BEFORE, прежние разделы на месте)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена (миграций нет, база на 0065), данные те же, ничего не удалено ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram и откройте Mini App по кнопке меню: вход как обычно; пройдитесь по клиентам, объекту, смете, документам;"
echo "  2) кнопки «Открыть / Заметки / Изменить / В архив» в списке объектов, «позвонить» и «копировать e-mail» в карточке клиента и «›» в календаре стали крупнее (не меньше 44 px) — убедитесь, что попадать пальцем стало легче;"
echo "  3) бэкап под текущую голову, если ещё не делали: cd ~/apps/plan_-_estimate && BACKUP_BRANCH=$BR BACKUP_HEAD=0065_access_control bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  4) приёмка: «принимаем Stage 20» после чек-листа 20F; слияние $BR → main и переключение VM — только по отдельному «да»."
)
