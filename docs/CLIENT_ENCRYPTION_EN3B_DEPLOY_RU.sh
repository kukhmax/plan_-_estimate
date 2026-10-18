#!/usr/bin/env bash
# Шифрование данных клиентов, шаг EN-3b (смена КЛЮЧА ДАННЫХ) — выкладка БЕЗ миграций, только backend: код смены ключа данных владельца (`python -m app.cli.rotate_data_keys`).
# Сама смена этой выкладкой НЕ выполняется: ключи, данные и ключи данных не меняются (смена — отдельный скрипт docs/CLIENT_ENCRYPTION_DEK_ROTATION_RU.sh, только по вашему «да»).
# Миграций нет, docker-compose и зависимости не меняются: база остаётся на 0064_encrypted_payments. Строгое чтение, ключ сервера и цикл календаря не трогаются (скрипт проверяет, что они в том же состоянии).
# Откат БЕЗОПАСЕН образом (схема не менялась): теги pre-en3b. Останавливается на первом непройденном условии (FAIL). Ворота B: контейнер пересоздаётся только после того, как вы САМИ введёте фразу. Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-client-encryption && git show origin/backlog-client-encryption:docs/CLIENT_ENCRYPTION_EN3B_DEPLOY_RU.sh > ~/deploy_en3b.sh && bash ~/deploy_en3b.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
BR="${DEPLOYEN3B_BRANCH:-backlog-client-encryption}"
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
has '0064_encrypted_payments' "$AL" || fail "G0" "alembic current не 0064_encrypted_payments: $AL (эта выкладка — без миграций и рассчитана на базу на 0063)"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
STRICT_ENV=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower(), bool(s.DATA_KEK.get_secret_value()) if s.DATA_KEK else False)")
[ "$STRICT_ENV" = "true True" ] || fail "G0" "строгое чтение / ключ шифрования в контейнере: '$STRICT_ENV', ожидалось 'true True' (состояние после EN-2b-2)"
KEYVER=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(s.DATA_KEK_VERSION)")
echo "версия ключа сервера в контейнере: $KEYVER; отпечаток (8 знаков SHA-256): $(grep -E '^DATA_KEK=' .env.production | head -1 | cut -d= -f2- | tr -d '\n' | sha256sum | cut -c1-8)"
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod docker-compose.prod.yml .env.production.example)
[ -z "$INFRA" ] || fail "G0" "Изменились образы / зависимости / compose (этого релиза там быть не должно): $INFRA"
MIG=$(git diff --name-only HEAD "origin/$BR" -- backend/alembic | grep -v '__pycache__' || true)
[ -z "$MIG" ] || fail "G0" "в релизе есть изменения миграций (этот скрипт — только для выкладки БЕЗ миграций): $MIG"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(backend/app/|backend/tests/|docs/)' || true)
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
if ! docker image inspect plan-estimate-backend:pre-en3b > /dev/null 2>&1; then
  docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-en3b  || fail1 "G1" "тег pre-en3b backend"
fi
PC build backend > /tmp/build_en3b.log 2>&1 || { tail -n 30 /tmp/build_en3b.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend, тег pre-en3b; frontend не меняется)"

echo; echo "################ ВОРОТА B: пересоздание контейнеров (миграций нет) ################"
echo "Что произойдёт: пересоздаётся ТОЛЬКО backend из собранного образа; frontend и кнопка меню не трогаются."
echo "  • Миграций НЕТ: схема базы и данные не меняются; ключ шифрования и строгое чтение остаются как были. Выкладка НИЧЕГО не удаляет и НЕ МЕНЯЕТ ключи: она добавляет только код смены ключа данных (сама смена — отдельным скриптом по вашему «да»)."
echo "  • Простой API при пересоздании backend: около 30–60 секунд."
echo "  • Откат безопасен образами (схема не менялась): retag pre-en3b и up --no-deps --no-build backend. Команда напечатается при любом отказе."
echo "  • Отказ на этих воротах возвращает код на $PREV; production не меняется."
echo
echo "Чтобы пересоздать backend, введите ТОЧНО:  ВЫКЛАДКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYEN3B_TTY:-/dev/tty}" || { restore; fail "B" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА ДА" ] || { echo; restore; echo "Остановлено на воротах B (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "B (подтверждено вами)"

ROLLALL="Откат (схема базы не менялась): 1) docker tag plan-estimate-backend:pre-en3b plan-estimate-backend:latest   2) $COMPOSE up -d --no-deps --no-build backend   3) git checkout -q -B $PREV $PREV_SHA"

echo; echo "################ G2: backend ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend 2>&1)
has "Running upgrade" "$LOG" && fail "G2" "в логе применяется миграция, а в этом релизе их быть не должно. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError|DATA_KEK" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0064_encrypted_payments' "$AL2" || fail "G2" "alembic не 0064: $AL2. $ROLLALL"
STRICT=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")
[ "$STRICT" = "true" ] || fail "G2" "строгое чтение в контейнере: $STRICT, ожидалось true. $ROLLALL"
PKEK=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(bool(s.DATA_KEK_PREVIOUS.get_secret_value()), s.DATA_KEK_VERSION)")
[ "$PKEK" = "False $KEYVER" ] || fail "G2" "DATA_KEK_PREVIOUS / версия ключа в контейнере: '$PKEK', ожидалось 'False $KEYVER' (ротация этой выкладкой не выполняется). $ROLLALL"
echo "--- состояние ключей (ТОЛЬКО ЧТЕНИЕ; числа, без ключей) ---"
ROT=$(docker exec plan_estimate_backend python -m app.cli.rotate_keys status) || { echo "$ROT"; fail "G2" "rotate_keys status не прошёл. $ROLLALL"; }
echo "$ROT"
has "ROTATION DONE" "$ROT" || fail "G2" "не все ключи данных открываются текущим ключом сервера. $ROLLALL"
DEKST=$(docker exec plan_estimate_backend python -m app.cli.rotate_data_keys status) || { echo "$DEKST"; fail "G2" "rotate_data_keys status не прошёл или есть значения под старым ключом данных. $ROLLALL"; }
echo "--- ключи данных (ТОЛЬКО ЧТЕНИЕ; числа, без ключей) ---"; echo "$DEKST"
has "STILL SEALED WITH AN OLD KEY: 0" "$DEKST" || fail "G2" "есть значения под неактивным ключом данных (смена не закончена?). $ROLLALL"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "G2" "verify шифрования не прошёл (открытые или нерасшифровываемые значения). $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G2" "не все контейнеры running. $ROLLALL"; }
ok "G2 (backend: миграций нет, база на 0064, строгое чтение включено, все ключи данных открываются текущим ключом, команда ротации работает, данные те же)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена (миграций нет, база на 0064), ключи не менялись, данные те же ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) откройте Mini App: клиенты, объекты, «Faktury i zaliczki», документы — как раньше (frontend и кнопка меню не менялись);"
echo "  2) приёмка: «принимаем EN-3b»;"
echo "  3) САМА СМЕНА ключа данных (docs/CLIENT_ENCRYPTION_KEYS_RUNBOOK_RU.md, скрипт docs/CLIENT_ENCRYPTION_DEK_ROTATION_RU.sh) — только по вашему отдельному «да»; нужна при подозрении, что утёк именно ключ данных, не обязательна сейчас."
)
