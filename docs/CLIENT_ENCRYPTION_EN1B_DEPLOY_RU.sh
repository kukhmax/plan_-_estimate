#!/usr/bin/env bash
# Шифрование данных клиентов, шаг EN-1b (уточнение spike) — выкладка БЕЗ миграций, БЕЗ изменения backend и БЕЗ изменения зависимостей: только frontend (страница «Test zabezpieczeń» теперь печатает сырой ответ SecureStorage / DeviceStorage после удаления и пробует restoreItem).
# Страница спрашивает ЭТОТ телефон, что умеют Telegram (CloudStorage, SecureStorage, DeviceStorage, BiometricManager) и браузер (WebCrypto, PBKDF2, Argon2), и показывает отчёт. Данных клиентов она не трогает, на сервер ничего не отправляет.
# Контейнер backend НЕ пересоздаётся (скрипт проверяет, что он остался тем же), база остаётся на 0061_expense_category, цикл календаря не трогается.
# Откат БЕЗОПАСЕН образом frontend (тег pre-en1b): backend и база не менялись.
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Ворота B: frontend пересоздаётся только после того, как вы САМИ введёте фразу. Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-client-encryption && git show origin/backlog-client-encryption:docs/CLIENT_ENCRYPTION_EN1B_DEPLOY_RU.sh > ~/deploy_en1b.sh && bash ~/deploy_en1b.sh
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
has '0061_expense_category' "$AL" || fail "G0" "alembic current не 0061_expense_category: $AL (эта выкладка — без миграций и рассчитана на базу на 0061; сначала должны быть выложены IA-1…IA-7 и третья выкладка)"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
if [ -n "$LASTRUN" ]; then echo "последний бэкап (справочно; без миграций он не обязателен): $LASTRUN ($(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 )) ч назад)"; fi
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend frontend/Dockerfile.prod frontend/nginx.conf docker-compose.prod.yml .env.production.example)
[ -z "$INFRA" ] || fail "G0" "Изменились backend / образы / compose / Caddy (этого релиза там быть не должно): $INFRA"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(frontend/src/|frontend/package\.json$|frontend/package-lock\.json$|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DEPS=$(git diff --name-only HEAD "origin/$BR" -- frontend/package.json frontend/package-lock.json)
[ -z "$DEPS" ] || fail "G0" "Эта выкладка не меняет зависимости, а изменились: $DEPS"
BACKEND_ID=$(docker inspect -f '{{.Id}}' plan_estimate_backend)
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments; select count(*) from photo_assets; select count(*) from photo_annotations; select count(*) from purge_ledger; select count(*) from project_payments; select count(*) from project_finance;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/документы/привязки фото/файлы фото/метки/реестр удалений/записи расчётов/договорные суммы = $BEFORE"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
fail1() { restore; fail "$1" "$2 (код на VM возвращён на $PREV, коммит $(echo "$PREV_SHA" | cut -c1-7))"; }
git checkout -q -B "$BR" "origin/$BR" || fail1 "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-en1b || fail1 "G1" "тег pre-en1b frontend"
PC build frontend > /tmp/build_en1b.log 2>&1 || { tail -n 30 /tmp/build_en1b.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка frontend, тег pre-en1b; зависимости прежние)"

echo; echo "################ ВОРОТА B: пересоздание контейнеров (миграций нет) ################"
echo "Что произойдёт: пересоздаётся ТОЛЬКО frontend из собранного образа (backend не трогается)."
echo "  • Миграций НЕТ, backend не меняется, база остаётся на 0061. В меню приложения появляется последний пункт «Test zabezpieczeń» (страница проверки EN-1, теперь с сырым ответом после удаления)."
echo "  • Страница ничего не делает сама: она работает, когда вы нажмёте «Uruchom testy». Данных клиентов она не читает и не пишет; единственное, что она оставляет, — пробные значения en1_* в хранилищах Telegram (и их же она удаляет), метки — только если вы нажмёте «Zapisz znacznik»."
echo "  • Простой интерфейса при пересоздании frontend: несколько секунд. Записи, документы, фото и файлы не затрагиваются; НИЧЕГО не удаляется."
echo "  • Откат безопасен образом (backend и база не менялись): retag pre-en1b и up --no-deps --no-build frontend. Команда напечатается при любом отказе."
echo "  • Отказ на этих воротах возвращает код на $PREV; production не меняется."
echo
echo "Чтобы пересоздать frontend, введите ТОЧНО:  ВЫКЛАДКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYEN_TTY:-/dev/tty}" || { restore; fail "B" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА ДА" ] || { echo; restore; echo "Остановлено на воротах B (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "B (подтверждено вами)"

ROLLALL="Откат (backend и база не менялись): 1) docker tag plan-estimate-frontend:pre-en1b plan-estimate-frontend:latest   2) $COMPOSE up -d --no-deps --no-build frontend   3) git checkout -q -B $PREV $PREV_SHA"

echo; echo "################ G2: frontend ################"
PC up -d --no-deps frontend || fail "G2" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G2" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G2" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G2" "главная страница не отдаёт сборку. $ROLLALL"
grep -q 'bg-gray-50' <<<"$PAGE" && fail "G2" "в выданной странице всё ещё есть класс bg-gray-50 у body (светлый фон в тёмной теме). $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in plan-estimate-offline CHANGES_WAITING sync-screen show-calendar object-tile-payments data-tone journal-delete-understood security-probe probe-run-all show-security 'Test zabezpieczeń' 'Тест защиты' argon2id aes256gcm_roundtrip 'after_raw=' 'after_can_restore='; do
  has "$MARK" "$BUNDLE" || fail "G2" "в выданной сборке нет '$MARK'. $ROLLALL"
done
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ARGON=$(grep -o 'index\.esm-[A-Za-z0-9_-]*\.js' <<<"$BUNDLE" | head -1)
[ -n "$ARGON" ] || fail "G2" "в сборке нет ссылки на кусок с Argon2 (hash-wasm). $ROLLALL"
curl -fsS -o /dev/null "https://plan-estimate.pl/assets/$ARGON" || fail "G2" "кусок с Argon2 ($ARGON) не отдаётся. $ROLLALL"
ok "G2 (frontend: страница «Test zabezpieczeń» в меню, кусок с Argon2 отдаётся, прежние экраны на месте)"

echo; echo "################ G3: backend не тронут ################"
[ "$(docker inspect -f '{{.Id}}' plan_estimate_backend)" = "$BACKEND_ID" ] || fail "G3" "контейнер backend был пересоздан: этого выкладка делать не должна. $ROLLALL"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G3" "backend не healthy. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0061_expense_category' "$AL2" || fail "G3" "alembic не 0061: $AL2. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G3" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G3" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (backend тот же контейнер, healthy, база на 0061, цикл календаря как был: $LOOP_ENV, данные те же)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена (backend и база не менялись, база на 0061), данные те же, ничего не удалено ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram, откройте Mini App по кнопке меню, меню → «Test zabezpieczeń» → «Uruchom testy» (пошаговая инструкция — docs/CLIENT_ENCRYPTION_EN1_RUNBOOK_RU.md);"
echo "  2) нажмите «Kopiuj raport» и пришлите отчёт; затем кнопки биометрии и «Zapisz znacznik» (инструкция там же)."
)
