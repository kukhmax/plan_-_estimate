#!/usr/bin/env bash
# Stage 17C.4 + 17F.1 — стартовые ситуации (каталог, backend) и закреплённая шапка (frontend): проверка, сборка, backend, frontend, кнопка Telegram.
# Останавливается на первом непройденном условии (FAIL) и пишет, что делать. Секреты не печатает.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому старый код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin stage-17 && git show origin/stage-17:docs/STAGE_17_DEPLOY_17C4_RU.sh > ~/deploy17c4.sh && bash ~/deploy17c4.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний

echo "################ G0: проверка перед выкладкой (только чтение) ################"
echo "--- ресурсы сервера (справочно, не критерий; нужны для решений по инфраструктуре) ---"
echo "процессоров: $(nproc); память МБ (всего/занято/свободно): $(free -m | awk '/^Mem:/ {print $2"/"$3"/"$4}'); swap МБ: $(free -m | awk '/^Swap:/ {print $2}'); архитектура: $(uname -m)"
docker stats --no-stream --format '  {{.Name}}: память {{.MemUsage}} ({{.MemPerc}}), процессор {{.CPUPerc}}' 2>/dev/null || true
[ "$(env | grep -c '^MEDIA_S3\|^BACKUP_')" = "0" ] || fail "G0" "В оболочке лишние переменные MEDIA_S3/BACKUP_. Откройте новую SSH-сессию."
[ "$(git branch --show-current)" = "stage-17" ] || fail "G0" "Ветка не stage-17: $(git branch --show-current)"
[ -z "$(git status --short)" ] || fail "G0" "Рабочее дерево не чистое: $(git status --short)"
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "G0" "health недоступен"
has '"status":"ok"' "$H" || fail "G0" "health не ok до выкладки: $H"
AL=$(docker exec plan_estimate_backend alembic current 2>/dev/null)
has '0053_downtime_episodes' "$AL" || fail "G0" "alembic current не 0053_downtime_episodes: $AL"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
git fetch -q origin stage-17 || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD origin/stage-17 || fail "G0" "HEAD не предок origin/stage-17"
INFRA=$(git diff --name-only HEAD origin/stage-17 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod backend/app/backup backend/alembic)
[ -z "$INFRA" ] || fail "G0" "Изменилась инфраструктура/зависимости/миграции: $INFRA"
BAD=$(git diff --name-only HEAD origin/stage-17 -- backend/app | grep -Ev '^backend/app/domain/knowledge/catalog/(situations|meta)\.json$' || true)
[ -z "$BAD" ] || fail "G0" "В backend/app неожиданные файлы (ожидаются только situations.json и meta.json): $BAD"
BADALL=$(git diff --name-only HEAD origin/stage-17 | grep -Ev '^(backend/app/domain/knowledge/catalog/|frontend/src/|docs/|backend/tests/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
echo "данные до: клиенты/объекты/документы/фото = $BEFORE"
echo "приходит:"; git log --oneline HEAD..origin/stage-17
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
git pull -q --ff-only origin stage-17 || fail "G1" "git pull --ff-only не удался"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW"
PC config --quiet || fail "G1" "docker compose config не прошёл"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-17c4  || fail "G1" "тег pre-17c4 backend"
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-17c4 || fail "G1" "тег pre-17c4 frontend"
PC build backend frontend > /tmp/build17.log 2>&1 || { tail -n 30 /tmp/build17.log; fail "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка, теги pre-17c4)"

echo; echo "################ G2: backend ################"
ROLLB="Откат backend:  docker tag plan-estimate-backend:pre-17c4 plan-estimate-backend:latest && docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps --no-build backend"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLB"
for i in $(seq 1 24); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 2 минуты. $ROLLB"; }
LOG=$(docker logs plan_estimate_backend --tail 80 2>&1)
has "Running upgrade" "$LOG" && fail "G2" "в логе Running upgrade — миграция, которой не должно быть. $ROLLB"
grep -qE "Traceback|KnowledgeCatalogError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLB"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLB"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0053_downtime_episodes' "$AL2" || fail "G2" "alembic не 0053. $ROLLB"
CAT=$(docker exec plan_estimate_backend python -c "from app.domain.knowledge.catalog import load_knowledge_catalog as l; c=l(); print(len(c.sources), len(c.entries), len(c.links), len(c.situations), c.meta.version)")
echo "каталог (источники статьи связи ситуации версия): $CAT"
[ "$CAT" = "13 34 51 8 5" ] || fail "G2" "каталог не 13 34 51 8 5. $ROLLB"
KEY=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print(k[:6]+'…'+k[-4:], s.MEDIA_S3_BUCKET, s.DOCUMENT_DELIVERY)")
[ "$KEY" = "97bfe5…6dab plan-estimate-media-prod telegram" ] || fail "G2" "ключ/бакет/доставка не те: $KEY. $ROLLB"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLB"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLB"
ok "G2 (backend, каталог 13/34/51/8/v5, данные те же)"

echo; echo "################ G3: frontend ################"
ROLLF="Откат frontend:  docker tag plan-estimate-frontend:pre-17c4 plan-estimate-frontend:latest && docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps --no-build frontend"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLF"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLF"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLF"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLF"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLF"
ok "G3 (frontend)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена ==============="
echo "Теперь: полностью закройте Telegram, откройте Mini App и пройдите проверку на телефоне (чек-лист в ответе)."
)
