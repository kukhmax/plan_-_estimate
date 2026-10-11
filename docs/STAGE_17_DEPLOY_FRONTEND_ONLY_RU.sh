#!/usr/bin/env bash
# Stage 17F.1 — только frontend (закреплённая шапка): проверка, получение кода, сборка, frontend, кнопка Telegram. Backend и данные не трогаются.
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому старый код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin stage-17 && git show origin/stage-17:docs/STAGE_17_DEPLOY_FRONTEND_ONLY_RU.sh > ~/deploy17f.sh && bash ~/deploy17f.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }

echo "################ G0: проверка перед выкладкой (только чтение) ################"
[ "$(env | grep -c '^MEDIA_S3\|^BACKUP_')" = "0" ] || fail "G0" "В оболочке лишние переменные MEDIA_S3/BACKUP_. Откройте новую SSH-сессию."
[ "$(git branch --show-current)" = "stage-17" ] || fail "G0" "Ветка не stage-17: $(git branch --show-current)"
[ -z "$(git status --short)" ] || fail "G0" "Рабочее дерево не чистое: $(git status --short)"
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "G0" "health недоступен"
has '"status":"ok"' "$H" || fail "G0" "health не ok до выкладки: $H"
AL=$(docker exec plan_estimate_backend alembic current 2>/dev/null)
has '0053_downtime_episodes' "$AL" || fail "G0" "alembic current не 0053_downtime_episodes: $AL"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 4 ] || fail "G0" "Свободно ${FREE} ГБ (< 4)"
git fetch -q origin stage-17 || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD origin/stage-17 || fail "G0" "HEAD не предок origin/stage-17"
INFRA=$(git diff --name-only HEAD origin/stage-17 -- docker-compose.prod.yml Caddyfile backend frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod)
[ -z "$INFRA" ] || fail "G0" "Изменились backend/инфраструктура/зависимости (должен меняться только frontend/src): $INFRA"
BAD=$(git diff --name-only HEAD origin/stage-17 | grep -Ev '^(frontend/src/|docs/)' || true)
[ -z "$BAD" ] || fail "G0" "Неожиданные файлы: $BAD"
echo "приходит:"; git log --oneline HEAD..origin/stage-17
ok "G0"

echo; echo "################ G1: код и сборка frontend (старый production работает) ################"
git pull -q --ff-only origin stage-17 || fail "G1" "git pull --ff-only не удался"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW"
PC config --quiet || fail "G1" "docker compose config не прошёл"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-17f1 || fail "G1" "тег pre-17f1 frontend"
PC build frontend > /tmp/build17f.log 2>&1 || { tail -n 30 /tmp/build17f.log; fail "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка, тег pre-17f1)"

echo; echo "################ G3: frontend ################"
ROLLF="Откат frontend:  docker tag plan-estimate-frontend:pre-17f1 plan-estimate-frontend:latest && docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps --no-build frontend"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLF"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLF"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLF"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLF"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLF"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G3" "backend не healthy (он не менялся): смотрите docker logs plan_estimate_backend"
ok "G3 (frontend, backend не тронут)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена (frontend) ==============="
echo "Теперь: полностью закройте Telegram, откройте Mini App и прокрутите любой длинный список: шапка с меню должна оставаться вверху."
)
