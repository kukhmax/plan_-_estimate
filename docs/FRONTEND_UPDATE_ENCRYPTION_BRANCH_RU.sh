#!/usr/bin/env bash
# Обновление ТОЛЬКО frontend ветки backlog-client-encryption (без миграций, backend, базы и цикла сообщений не касается): сборка нового образа, замена контейнера frontend,
# обновление кнопки меню Telegram (?v=<коммит>, чтобы Telegram не показывал старый кэш). Останавливается на первом непройденном условии (FAIL).
# Секреты не печатает. Прежний образ frontend сохраняется под тегом pre-<коммит>: откат одной командой (она печатается при любом отказе).
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-client-encryption && git show origin/backlog-client-encryption:docs/FRONTEND_UPDATE_ENCRYPTION_BRANCH_RU.sh > ~/update_front.sh && bash ~/update_front.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }

echo "################ U0: проверка перед обновлением (только чтение) ################"
[ "$(env | grep -c '^MEDIA_S3\|^BACKUP_')" = "0" ] || fail "U0" "В оболочке лишние переменные MEDIA_S3/BACKUP_. Откройте новую SSH-сессию."
[ -z "$(git status --short)" ] || fail "U0" "Рабочее дерево не чистое: $(git status --short)"
BR=$(git branch --show-current)
[ "$BR" = "backlog-client-encryption" ] || fail "U0" "ветка на VM '$BR', а нужна backlog-client-encryption (этот скрипт — для обновления ПОСЛЕ выкладки EN-2b-3)"
OLD=$(git rev-parse --short HEAD)
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "U0" "health недоступен"
has '"status":"ok"' "$H" || fail "U0" "health не ok: $H"
AL=$(docker exec plan_estimate_backend alembic current 2>/dev/null)
has '0064_encrypted_payments' "$AL" || fail "U0" "alembic current не 0064_encrypted_payments (EN-2b-3 ещё не выложен?): $AL"
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "U0" "frontend не запущен"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 3 ] || fail "U0" "Свободно ${FREE} ГБ (< 3)"
git fetch -q origin backlog-client-encryption || fail "U0" "git fetch не удался"
git merge-base --is-ancestor HEAD origin/backlog-client-encryption || fail "U0" "HEAD не предок origin/backlog-client-encryption"
CHANGED=$(git diff --name-only HEAD origin/backlog-client-encryption)
if [ -z "$CHANGED" ]; then echo "На VM уже последняя версия ($OLD): обновлять нечего."; exit 0; fi
BADALL=$(grep -Ev '^(frontend/src/|docs/)' <<<"$CHANGED" || true)
[ -z "$BADALL" ] || fail "U0" "Этот скрипт — только для frontend, а в обновлении есть другие файлы (нужна полная выкладка): $BADALL"
echo "версия на VM: $OLD; приходит:"; git log --oneline HEAD..origin/backlog-client-encryption | head -20
PAGE0=$(curl -fsS https://plan-estimate.pl/) || fail "U0" "главная страница недоступна"
JS0=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE0" | head -1)
echo "сборка сейчас: ${JS0:-неизвестно}"
ok "U0"

echo; echo "################ U1: сборка (старый frontend работает) ################"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" "plan-estimate-frontend:pre-$OLD" || fail "U1" "тег pre-$OLD"
ROLLF="Откат frontend:  docker tag plan-estimate-frontend:pre-$OLD plan-estimate-frontend:latest && docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps --no-build frontend"
git checkout -q --detach origin/backlog-client-encryption || fail "U1" "переключение на origin/backlog-client-encryption не удалось"
NEW=$(git rev-parse --short HEAD)
PC build frontend > /tmp/build-front.log 2>&1 || { tail -n 30 /tmp/build-front.log; git checkout -q backlog-client-encryption; fail "U1" "сборка не удалась (старый frontend продолжает работать; код на VM возвращён на backlog-client-encryption)"; }
git checkout -q backlog-client-encryption || fail "U1" "не удалось вернуться на backlog-client-encryption"   # ветка переедет на $NEW только после успешной замены контейнера (U2)
ok "U1 (сборка $NEW готова, прежний образ сохранён как pre-$OLD)"

echo; echo "################ U2: замена контейнера frontend ################"
PC up -d --no-deps frontend || fail "U2" "up frontend не удался. $ROLLF"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "U2" "frontend не запущен. $ROLLF"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "U2" "не все контейнеры running. $ROLLF"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "U2" "главная страница не отдаёт сборку. $ROLLF"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
[ -n "$JS" ] || fail "U2" "в странице нет файла сборки. $ROLLF"
[ "$JS" != "$JS0" ] || fail "U2" "файл сборки не изменился ($JS): браузер/прокси отдаёт старую версию или сборка та же. $ROLLF"
curl -fsS "https://plan-estimate.pl/$JS" | grep -q 'delete-document-' || fail "U2" "в выданной сборке нет вкладки архива документов (сборка не от этой ветки?). $ROLLF"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "U2" "health не ok. $ROLLF"
git merge -q --ff-only origin/backlog-client-encryption || fail "U2" "frontend уже обновлён, но ветку backlog-client-encryption на VM перевести на $NEW не удалось (git merge --ff-only origin/backlog-client-encryption вручную)"
ok "U2 (сборка $JS; ветка на VM = $NEW)"

echo; echo "################ U3: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "U3" "setChatMenuButton: $R1 (приложение уже обновлено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "U3" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "U3 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: frontend обновлён $OLD -> $NEW; backend, база и цикл сообщений не тронуты ==============="
echo "Дальше: закройте Telegram полностью и откройте Mini App (или по ссылке с ?v=$NEW), проверьте изменения на телефоне."
)
