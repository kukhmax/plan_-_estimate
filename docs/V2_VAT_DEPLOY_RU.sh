#!/usr/bin/env bash
# Выпуск «НДС внутри цен» + доработки стен + V2-14b: (1) в смете с НДС 8 %/23 % галочка «Ceny zawierają VAT» — сумма позиций считается брутто, нетто и НДС выделяются из неё (а не добавляются сверху); PDF, страница клиента и сумма договора берут нетто; (2) стены нерегулярного помещения: перетаскивание удержанием в «Zmień kolejność», кнопка «＋ Dodaj ścianę» у заголовка открывает окно добавления; (3) перенос ответа мастера без двойного счёта: если в помещении уже есть ваша строка той же позиции, предпросмотр предлагает «заменить числом мастера» (по умолчанию) / «добавить рядом» / «оставить мою»; строки от мастера помечены «od majstra»; (4) в смете плашка «Bez ceny: N» и кнопка «Uzupełnij ceny z cennika» (строки из помещений берут цену, заданную в прайсе позже); (5) V2-14b (фото помещения и карта трасс на странице мастера) и исправление порядка «описание, потом ссылка» / «majster» — выкладка С ОДНОЙ МИГРАЦИЕЙ 0087 (новая колонка `vat_included` у смет, NOT NULL, по умолчанию false: все существующие сметы считаются как раньше).
# Что меняется в данных: миграция 0087 — новая колонка (у всех существующих смет false); миграция 0088 — новая пустая таблица «Мои стандартные условия договора»; миграция 0089 — три новых значения основания пола (стяжка, старая плитка, доски). Откат миграций убирает колонку и таблицу.
# Технология пола (2026-10-30): справочники пола v2 (чек-листы, 40 правил, 14 работ) создаются при первом обращении; после отката образа прежний образ покажет в списке оснований пола и v1, и v2 чек-листа и не оценит риски осмотров v2 (данные не портятся).
# Откат образами БЕЗОПАСЕН: прежний образ не знает колонки и не мешает ей; теги pre-v2vata. Останавливается на первом непройденном условии (FAIL). Ворота B: контейнеры пересоздаются только после того, как вы САМИ введёте фразу.
# Запуск (в НОВОЙ SSH-сессии на VM; файл берётся из origin без pull, поэтому код на VM не меняется до проверок):
#   cd ~/apps/plan_-_estimate && git fetch -q origin ver-2 && git show origin/ver-2:docs/V2_VAT_DEPLOY_RU.sh > ~/deploy_v2vat.sh && bash ~/deploy_v2vat.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }   # без конвейеров: pipefail не даёт ложных срабатываний
BR="${DEPLOYV214A_BRANCH:-ver-2}"
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
M87=backend/alembic/versions/0087_estimate_vat_included.py; M88=backend/alembic/versions/0088_owner_contract_terms.py; M89=backend/alembic/versions/0089_floor_substrates.py; M90=backend/alembic/versions/0090_vat_own_rate.py; M91=backend/alembic/versions/0091_planned_work_quantity.py
if has '0091_planned_work_quantity' "$AL"; then FIRST=no; START=0091; echo "повторный запуск: миграции 0087-0091 уже применены"
elif has '0090_vat_own_rate' "$AL"; then FIRST=yes; START=0090; echo "база на 0090: применится одна миграция 0091"
elif has '0089_floor_substrates' "$AL"; then FIRST=yes; START=0089; echo "база на 0089: применятся две миграции, 0090 и 0091"
elif has '0088_owner_contract_terms' "$AL"; then FIRST=yes; START=0088; echo "база на 0088: применятся три миграции, 0089-0091"
elif has '0087_estimate_vat_included' "$AL"; then FIRST=yes; START=0087; echo "база на 0087: применятся четыре миграции, 0088-0091"
elif has '0086_transfer_source' "$AL"; then FIRST=yes; START=0086; echo "база на 0086: применятся пять миграций, 0087-0091"
else fail "G0" "alembic current не 0086-0091 (0086_transfer_source … 0091_planned_work_quantity): $AL (этот выпуск ставится на базу V2-14a, голова 0086; сначала выложите V2-14a)"; fi
HEAD_NOW=$(grep -oE '00(86_transfer_source|87_estimate_vat_included|88_owner_contract_terms|89_floor_substrates|90_vat_own_rate|91_planned_work_quantity)' <<<"$AL" | head -1)
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "G0" "Свободно ${FREE} ГБ (< 5)"
STRICT_ENV=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower(), bool(s.DATA_KEK.get_secret_value()) if s.DATA_KEK else False)")
[ "$STRICT_ENV" = "true True" ] || fail "G0" "строгое чтение / ключ шифрования в контейнере: '$STRICT_ENV', ожидалось 'true True' (состояние после EN-2b-2)"
# бэкап (A9) не старше суток: миграции добавляют колонку и пустую таблицу (бэкап под текущую голову $HEAD_NOW делается из ветки ver-2, текущий коммит VM)
LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
[ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9 (BACKUP_BRANCH=ver-2 BACKUP_COMMIT=$(git rev-parse --short HEAD) BACKUP_HEAD=$HEAD_NOW bash ~/backup_a9.sh)"
AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
[ "$AGE_H" -le 24 ] || fail "G0" "последний бэкап $LASTRUN старше суток (${AGE_H} ч). Сделайте свежий: cd ~/apps/plan_-_estimate && git fetch -q origin ver-2 && git show origin/ver-2:docs/STAGE_18_BACKUP_A9_RU.sh > ~/backup_a9.sh && BACKUP_BRANCH=ver-2 BACKUP_COMMIT=$(git rev-parse --short HEAD) BACKUP_HEAD=$HEAD_NOW bash ~/backup_a9.sh (в НОВОЙ сессии, потом закрыть её)"
echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
KEKTXT=$(grep -E '^DATA_KEK=' .env.production | head -1 | cut -d= -f2-)
[ -n "$KEKTXT" ] && [ "$(printf '%s' "$KEKTXT" | base64 -d 2>/dev/null | wc -c)" = "32" ] || fail "G0" "DATA_KEK в .env.production отсутствует или не base64 из 32 байт (ключ НЕ МЕНЯТЬ и не удалять)"
echo "ключ сервера на месте; отпечаток (8 знаков SHA-256): $(printf '%s' "$KEKTXT" | sha256sum | cut -c1-8)"
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR"
INFRA=$(git diff --name-only HEAD "origin/$BR" -- Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod docker-compose.prod.yml .env.production.example)
[ -z "$INFRA" ] || fail "G0" "Изменились образы/зависимости/compose (этого релиза там быть не должно): $INFRA"
NEWMIG=$(git diff --name-only --diff-filter=A HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
CHGMIG=$(git diff --name-only --diff-filter=MD HEAD "origin/$BR" -- backend/alembic/versions | grep -v '__pycache__' || true)
[ -z "$CHGMIG" ] || fail "G0" "существующие миграции изменены или удалены: $CHGMIG"
BADMIG=$(grep -vxF -e "$M87" -e "$M88" -e "$M89" -e "$M90" -e "$M91" <<<"$NEWMIG" | grep -v '^$' || true)
[ -z "$BADMIG" ] || fail "G0" "в релизе допустимы только новые миграции 0087_estimate_vat_included.py, 0088_owner_contract_terms.py, 0089_floor_substrates.py, 0090_vat_own_rate.py и 0091_planned_work_quantity.py, а здесь ещё: '$BADMIG'"
NEED=$( case "$START" in 0086) echo "$M87 $M88 $M89 $M90 $M91";; 0087) echo "$M88 $M89 $M90 $M91";; 0088) echo "$M89 $M90 $M91";; 0089) echo "$M90 $M91";; 0090) echo "$M91";; *) echo "";; esac )
if [ -n "$NEWMIG" ]; then for M in $NEED; do has "$M" "$NEWMIG" || fail "G0" "база на $START, а в релизе нет миграции $M: '$NEWMIG'"; done; fi
OTHERALEMBIC=$(git diff --name-only HEAD "origin/$BR" -- backend/alembic | grep -v '__pycache__' | grep -Ev '^backend/alembic/versions/(008[789]_(estimate_vat_included|owner_contract_terms|floor_substrates)|0090_vat_own_rate|0091_planned_work_quantity).py$' || true)
[ -z "$OTHERALEMBIC" ] || fail "G0" "в alembic изменено что-то кроме миграций 0087-0091: $OTHERALEMBIC"
BADALL=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(README.md|backend/app/|backend/alembic/versions/0087_estimate_vat_included.py|backend/alembic/versions/0088_owner_contract_terms.py|backend/alembic/versions/0089_floor_substrates.py|backend/alembic/versions/0090_vat_own_rate.py|backend/alembic/versions/0091_planned_work_quantity.py|backend/tests/|frontend/src/|docs/)' || true)
[ -z "$BADALL" ] || fail "G0" "Неожиданные файлы в выкладке: $BADALL"
DOMAIN=$(grep -E '^APP_DOMAIN=' .env.production | head -1 | cut -d= -f2-)
[ -n "$DOMAIN" ] || fail "G0" "в .env.production нет APP_DOMAIN"
LOOP_ENV=$(grep -E '^CALENDAR_DISPATCHER_ENABLED=' .env.production | head -1 | cut -d= -f2- | tr 'A-Z' 'a-z')
[ -n "$LOOP_ENV" ] || LOOP_ENV=false
echo "домен приложения: $DOMAIN; цикл сообщений календаря в .env.production: $LOOP_ENV (после выкладки должен быть таким же)"
Q="select count(*) from photo_annotations; select count(*) from material_calcs; select count(*) from material_norms; select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from contracts; select count(*) from handover_protocols; select count(*) from concealed_works_protocols; select count(*) from acceptance_protocols; select count(*) from decision_protocols; select count(*) from downtime_episodes; select count(*) from data_keys; select count(*) from photo_attachments; select count(*) from photo_assets; select count(*) from estimates; select count(*) from calendar_settings; select count(*) from reminders; select count(*) from project_payments; select count(*) from executor_profiles;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
IDOC_BEFORE=$(PSQL "select count(*) from issued_documents")
echo "данные до: клиенты/объекты/журнал/договоры/передачи/скрытые/приёмки/решения/простои/ключи/привязки фото/файлы фото/сметы/настройки календаря/напоминания = $BEFORE"
echo "приходит:"; git log --oneline HEAD.."origin/$BR" | head -40
ok "G0"

echo; echo "################ G1: код и сборка (старый production работает) ################"
fail1() { restore; fail "$1" "$2 (код на VM возвращён на $PREV, коммит $(echo "$PREV_SHA" | cut -c1-7))"; }
git checkout -q -B "$BR" "origin/$BR" || fail "G1" "переключение на $BR не удалось"
NEW=$(git rev-parse --short HEAD); echo "HEAD: $NEW (ветка $BR)"
PC config --quiet || fail1 "G1" "docker compose config не прошёл"
# теги для отката: образ работающего контейнера; если docker не находит его по номеру (бывает с хранилищем образов containerd), берётся образ по имени :latest — он ещё не пересобран
tag_pre() {
  local svc="$1" t="plan-estimate-$1:pre-v2vat" cur
  docker image inspect "$t" > /dev/null 2>&1 && return 0
  cur=$(docker inspect -f '{{.Image}}' "plan_estimate_$svc" 2>/dev/null)
  if [ -n "$cur" ] && docker image inspect "$cur" > /dev/null 2>&1; then docker tag "$cur" "$t" && return 0; fi
  if docker image inspect "plan-estimate-$svc:latest" > /dev/null 2>&1; then docker tag "plan-estimate-$svc:latest" "$t" && return 0; fi
  return 1
}
tag_pre backend || fail1 "G1" "нет образа backend для отката (тег pre-v2vat)"
if tag_pre frontend; then FRONT_ROLLBACK=yes; else FRONT_ROLLBACK=no; echo "ВНИМАНИЕ: образа frontend для отката нет (frontend — статические файлы; откат при необходимости: git checkout на прежний коммит и docker compose build frontend && up -d --no-deps frontend). Продолжаем: backend откатывается образом."; fi
PC build backend frontend > /tmp/build_v2vat.log 2>&1 || { tail -n 30 /tmp/build_v2vat.log; fail1 "G1" "сборка не удалась (старая версия продолжает работать)"; }
ok "G1 (сборка backend и frontend, теги pre-v2vat)"

echo; echo "################ ВОРОТА B: пересоздание контейнеров и миграции 0087-0091 ################"
echo "Что произойдёт: пересоздаются backend и frontend из собранных образов."
echo "  • Миграция 0087 (при старте backend): у таблицы смет появляется колонка «цены уже с НДС» (у всех существующих смет — нет, считаются как раньше: НДС сверху). Ни одна существующая строка не меняется. Откат миграции просто убирает колонку."
echo "  • Миграция 0088 (при старте backend): новая пустая таблица «Мои стандартные условия договора» (одна строка на владельца, ответы зашифрованы). Существующие данные не читаются и не меняются."
echo "  • Миграция 0089 (при старте backend): три новых значения основания пола в базе (стяжка, старая плитка, доски). Существующие строки не меняются; чек-листы этих оснований создаются при первом открытии экрана осмотра. Значения остаются в базе и при откате образов: прежний образ не читает строки с этими основаниями, пока их нет (их нет, пока вы не открыли осмотр пола или план пола после выкладки)."
echo "  • Миграция 0090 (при старте backend): ограничение на ставку НДС в сметах и профиле меняется с «только 8 или 23» на «целое число от 0 до 100» (своя ставка). Ни одна строка не меняется. Откат миграции отказывает, пока у сметы или профиля стоит своя ставка (меняйте её на 8 или 23). Прежний образ читает такую строку без ошибки."
echo "  • Проход UX (без миграции): B6 и средние / мелкие замечания — новый маршрут POST …/trade-links/{trade}/transfer/own-items (создаёт позиции прайса без цены только по нажатию владельца); список помещений по порядку ввода."
echo "  • Миграция 0091 (при старте backend): у запланированных работ новая пустая колонка «количество» (мп / шт., вписанное при «Dodaj do prac» или в плане). Ни одна строка не меняется. Откат миграции убирает колонку (вписанные количества теряются, строки смет остаются)."
echo "  • Технология пола (без миграции): при первом обращении создаются чек-листы осмотра пола версии 2, 40 правил риска пола, их фразы и связки рекомендаций; в прайс каждого владельца при первом открытии добавятся 14 работ пола без цены. Существующие осмотры, риски, сметы и цены не меняются."
echo "  • Ключ шифрования и строгое чтение остаются как были. Ничего не удаляется. Вход по паролю остаётся выключенным."
echo "  • Простой API при пересоздании backend: около 30–60 секунд."
echo "  • Откат образами безопасен (прежний образ не знает новых видов и не мешает им): retag pre-v2vat и up --no-deps --no-build backend frontend. Команда напечатается при любом отказе."
echo "  • Отказ на этих воротах возвращает код на $PREV; production не меняется."
echo
echo "Чтобы пересоздать backend и frontend, введите ТОЧНО:  ВЫКЛАДКА ДА"
printf '> '
read -r ANSWER < "${DEPLOYV214A_TTY:-/dev/tty}" || { restore; fail "B" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии (код на VM возвращён на $PREV)"; }
[ "$ANSWER" = "ВЫКЛАДКА ДА" ] || { echo; restore; echo "Остановлено на воротах B (введено: '$ANSWER'). Production не менялся: работает прежняя версия; код на VM возвращён на $PREV."; exit 1; }
ok "B (подтверждено вами)"

if [ "$FRONT_ROLLBACK" = yes ]; then
  ROLLALL="Откат (прежний образ работает на новой схеме: он не знает ссылок для мастеров и не показывает их; данные остаются в базе): 1) docker tag plan-estimate-backend:pre-v2vat plan-estimate-backend:latest && docker tag plan-estimate-frontend:pre-v2vat plan-estimate-frontend:latest   2) $COMPOSE up -d --no-deps --no-build backend frontend   3) git checkout -q -B $PREV $PREV_SHA"
else
  ROLLALL="Откат (прежний образ работает на новой схеме): 1) docker tag plan-estimate-backend:pre-v2vat plan-estimate-backend:latest   2) $COMPOSE up -d --no-deps --no-build backend   3) git checkout -q -B $PREV $PREV_SHA && $COMPOSE build frontend && $COMPOSE up -d --no-deps frontend"
fi

echo; echo "################ G2: backend ################"
PC up -d --no-deps backend || fail "G2" "up backend не удался. $ROLLALL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "G2" "backend не стал healthy за 3 минуты. $ROLLALL"; }
LOG=$(docker logs plan_estimate_backend 2>&1)
if [ "$START" = 0086 ]; then has "Running upgrade 0086_transfer_source -> 0087_estimate_vat_included" "$LOG" || fail "G2" "в логе нет применения миграции 0087. $ROLLALL"; fi
if [ "$START" = 0086 ] || [ "$START" = 0087 ]; then has "Running upgrade 0087_estimate_vat_included -> 0088_owner_contract_terms" "$LOG" || fail "G2" "в логе нет применения миграции 0088. $ROLLALL"; fi
if [ "$START" = 0086 ] || [ "$START" = 0087 ] || [ "$START" = 0088 ]; then has "Running upgrade 0088_owner_contract_terms -> 0089_floor_substrates" "$LOG" || fail "G2" "в логе нет применения миграции 0089. $ROLLALL"; fi
case "$START" in 0086|0087|0088|0089) has "Running upgrade 0089_floor_substrates -> 0090_vat_own_rate" "$LOG" || fail "G2" "в логе нет применения миграции 0090. $ROLLALL";; esac
if [ "$FIRST" = yes ]; then has "Running upgrade 0090_vat_own_rate -> 0091_planned_work_quantity" "$LOG" || fail "G2" "в логе нет применения миграции 0091. $ROLLALL"; fi
EXPECTED_UP=$( case "$START" in 0086) echo 5;; 0087) echo 4;; 0088) echo 3;; 0089) echo 2;; 0090) echo 1;; *) echo 0;; esac )
[ "$(grep -c 'Running upgrade' <<<"$LOG")" -le "$EXPECTED_UP" ] || fail "G2" "в логе применяется больше миграций, чем $EXPECTED_UP. $ROLLALL"
grep -qE "Traceback|KnowledgeCatalogError|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "G2" "в логе ошибка. $ROLLALL"; }
has "Application startup complete" "$LOG" || fail "G2" "нет Application startup complete. $ROLLALL"
AL2=$(docker exec plan_estimate_backend alembic current 2>/dev/null); has '0091_planned_work_quantity' "$AL2" || fail "G2" "alembic не 0091: $AL2. $ROLLALL"
STRICT=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")
[ "$STRICT" = "true" ] || fail "G2" "строгое чтение в контейнере: $STRICT, ожидалось true. $ROLLALL"
API=$(docker exec plan_estimate_backend python -c "
from app.main import app
p = app.openapi()['paths']
need = ['/api/projects/{project_id}/rooms/{room_id}/surfaces/merge', '/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/unmerge', '/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/parts/{part_id}', '/api/projects/{project_id}/rooms/{room_id}/work-plan', '/api/auth/telegram', '/api/me', '/api/contract-terms', '/api/projects/{project_id}/contracts/{contract_id}/prefill', '/api/projects/{project_id}/estimates/{estimate_id}/fill-prices']
print(all(n in p for n in need))")
[ "$API" = "True" ] || fail "G2" "в API нет нужных маршрутов: $API. $ROLLALL"
# на настоящей базе (ТОЛЬКО ЧТЕНИЕ): новые таблицы есть и пусты; маршруты ссылки для клиента на месте; вход по паролю выключен
VI=$(PSQL "select count(*) from information_schema.columns where table_name = 'estimates' and column_name = 'vat_included' and is_nullable = 'NO' and data_type = 'boolean'")
VISET=$(PSQL "select count(*) from estimates where vat_included")
echo "новая колонка vat_included: $VI из 1; смет с «цены уже с НДС»: $VISET (при первом запуске 0); строк журнала отправленных: $(PSQL "select count(*) from issued_documents") (было $IDOC_BEFORE)"
[ "$VI" = "1" ] || fail "G2" "нет колонки vat_included (boolean, not null): $VI. $ROLLALL"
if [ "$START" = 0086 ]; then [ "$VISET" = "0" ] || fail "G2" "после миграции ни у одной сметы не должно быть «цены уже с НДС»: $VISET. $ROLLALL"; fi
SUB=$(PSQL "select count(*) from pg_enum e join pg_type t on t.oid = e.enumtypid where t.typname = 'substrate' and e.enumlabel in ('SCREED','OLD_TILE','WOOD_BOARDS')")
echo "новые основания пола в базе: $SUB из 3"
[ "$SUB" = "3" ] || fail "G2" "в типе substrate нет трёх новых значений: $SUB. $ROLLALL"
VATCK=$(PSQL "select count(*) from pg_constraint where conname in ('ck_estimates_vat','ck_executor_profiles_vat') and pg_get_constraintdef(oid) like '%vat_rate_percent <= 100%'")
echo "ограничения на ставку НДС (смета, профиль) принимают свою ставку: $VATCK из 2"
[ "$VATCK" = "2" ] || fail "G2" "ограничение ставки НДС не обновлено (миграция 0090): $VATCK из 2. $ROLLALL"
PWQ=$(PSQL "select count(*) from information_schema.columns where table_name = 'surface_planned_works' and column_name = 'quantity' and is_nullable = 'YES'")
echo "колонка количества у запланированных работ: $PWQ из 1"
[ "$PWQ" = "1" ] || fail "G2" "нет колонки surface_planned_works.quantity (миграция 0091): $PWQ. $ROLLALL"
CT=$(PSQL "select count(*) from information_schema.columns where table_name = 'owner_contract_terms' and column_name in ('id','owner_id','answers','created_at','updated_at')")
CTROWS=$(PSQL "select count(*) from owner_contract_terms")
echo "новая таблица owner_contract_terms: колонок $CT из 5; строк $CTROWS (при первом запуске 0)"
[ "$CT" = "5" ] || fail "G2" "нет таблицы owner_contract_terms с 5 колонками: $CT. $ROLLALL"
if [ "$FIRST" = yes ]; then [ "$CTROWS" = "0" ] || fail "G2" "новая таблица owner_contract_terms не пуста: $CTROWS. $ROLLALL"; fi
[ "$(PSQL "select count(*) from issued_documents")" = "$IDOC_BEFORE" ] || fail "G2" "число строк журнала отправленных изменилось. $ROLLALL"
ST=$(PSQL "select count(*) from payment_stages"); WH=$(PSQL "select count(*) from work_hours")
echo "ваших этапов: $ST; записей часов: $WH (эта миграция их не затрагивает)"
CODE=$(docker exec plan_estimate_backend python -c "
from app.core.config import settings
from app.main import app
paths = app.openapi()['paths']
open_ops = sorted(f'{m.upper()} {p}' for p, ops in paths.items() if p.startswith('/api/public/') for m, op in ops.items() if not op.get('security'))
print('/api/material-norms' in paths, '/api/projects/{project_id}/rooms/{room_id}/material-calcs' in paths, '/api/projects/{project_id}/estimates/{estimate_id}/add-materials' in paths, '/api/projects/{project_id}/rooms/{room_id}/route-totals' in paths, '/api/projects/{project_id}/documents/installation-map/preview' in paths, '/api/projects/{project_id}/pressure-tests' in paths, '/api/projects/{project_id}/pressure-tests/{protocol_id}/issue' in paths, '/api/projects/{project_id}/documents/pressure-test/preview' in paths, '/api/trades' in paths, '/api/projects/{project_id}/trade-links' in paths, '/api/projects/{project_id}/trade-links/{trade}/answers' in paths, '/api/public/trade' in paths, '/api/public/trade/submit' in paths, '/api/projects/{project_id}/trade-links/{trade}/transfer' in paths, '/api/projects/{project_id}/trade-links/{trade}/transfer/preview' in paths, len(open_ops) == 6, settings.AUTH_PASSWORD_ENABLED is False)")
[ "$CODE" = "True True True True True True True True True True True True True True True True True" ] || fail "G2" "в контейнере нет маршрутов норм, расчётов материалов, трасс помещения, «Mapa instalacji», протоколов опрессовки, профессий, ссылок для мастеров или их переноса в помещения, открытых операций не шесть (три клиента и три мастера), или вход по паролю включён: $CODE. $ROLLALL"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "G2" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLALL"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "G2" "verify шифрования не прошёл. $ROLLALL"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "G2" "данные изменились: было $BEFORE стало $AFTER. $ROLLALL"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G2" "health не ok. $ROLLALL"
ok "G2 (backend: миграции применены, база на 0091, таблица условий договора и основания пола есть, строгое чтение включено, колонка vat_included есть и у всех смет false, журнал цел, маршруты на месте, вход по паролю выключен, данные те же)"

echo; echo "################ G3: frontend ################"
PC up -d --no-deps frontend || fail "G3" "up frontend не удался. $ROLLALL"
sleep 8
[ "$(docker inspect -f '{{.State.Running}}' plan_estimate_frontend)" = "true" ] || fail "G3" "frontend не запущен. $ROLLALL"
NOTRUN=$(PC ps --format '{{.Name}} {{.State}}' | grep -v ' running' || true); [ -z "$NOTRUN" ] || { PC ps; fail "G3" "не все контейнеры running. $ROLLALL"; }
PAGE=$(curl -fsS https://plan-estimate.pl/) && has "assets/index-" "$PAGE" || fail "G3" "главная страница не отдаёт сборку. $ROLLALL"
JS=$(grep -o 'assets/index-[^"]*\.js' <<<"$PAGE" | head -1)
BUNDLE=$( [ -n "$JS" ] && curl -fsS "https://plan-estimate.pl/$JS" || true )
for MARK in show-access login-email login-submit account-sign-out reorder-walls-start merge-walls-start bottom-nav field-help- start-quick-estimate quick-estimate-form room-plan-open room-plan-sheet estimate-vat-select executor-profile-vat language-switch language-list lang- Українська English object-tile-client client-link-create client-estimate-decline X-Client-Link docs-tile documents/measurements/preview Obmiar with_photos payment-stages work-hours margin-card schedule-tab hours-tab stage-form hours-form payment-schedule/preview schedule-pdf 'Harmonogram płatności' voice- stage-due-hint room-points-toggle room-point-form estimate-add-points-action price-items/points-pack 'Punkty i trasy' object-tile-materials room-materials-toggle material-calc-form material-norms-toggle estimate-add-materials-action material-norms 'Normy zużycia' 'Dodaj materiały do kosztorysu' 'Нормы расхода' 'Consumption norms' TILE_WASTE_STRAIGHT material-use-routes route-totals ELEC_CABLE_M_SOCKET PL_PIPE_M_POINT 'Elektryka' 'Hydraulika' 'Электрика' 'Сантехника' 'Electrics' 'Plumbing' docs-tile installation-map/preview marker-utility- marker-legend 'Mapa instalacji ukrytych' 'Карта скрытых коммуникаций' 'Карта прихованих комунікацій' 'Map of hidden utilities' 'Co to jest (instalacja ukryta)' 'Woda zimna' pressure-tests documents/pressure-test/preview pressure-system- pressure-result- 'Protokół próby ciśnieniowej' 'Протокол опрессовки' 'Протокол опресування' 'Pressure test protocol' 'Protokół próby szczelności' pressure-photo-add surface-note- trades-picker trade- pricebook-show-all-trades recommendation-picker-show-all-trades '/api/trades' 'Zawody (pakiety)' 'Профессии (пакеты)' 'Професії (пакети)' 'Trades (packages)' 'Pokaż wszystkie kategorie' trade-transfer-open- trade-transfer-run- trade-transfer-item- master-route-map- master-room-photos- master-map-photo- master-photo-close 'Mapa tras ({count})' 'Zdjęcia pomieszczenia ({count})' 'Карта трасс ({count})' 'Route map ({count})' estimate-vat-included 'Ceny zawierają VAT' 'Цены уже с НДС' 'Ціни вже з ПДВ' 'Prices include VAT' wall-adder-open wall-adder-close wall-drag- 'Przeciągnij ścianę' trade-transfer-own-choice- room-point-from-master- estimate-unpriced estimate-fill-prices 'Uzupełnij ceny z cennika' inspection-autosave recommendations-accept-all 'Odpowiedzi zapisane automatycznie.' 'Dodaj wszystkie do prac ({n})' room-plan-copy-room-pick room-plan-process- 'Z procesu technologicznego' 'Skopiuj plan z innego pomieszczenia' 'Скопировать план из другого помещения' project-use-client-address 'Wstaw adres klienta' agreed-from-estimate 'Przyjmij kwotę netto z kosztorysu' contract-prefill 'Uzupełnij puste pola' 'Заполнить пустые поля' open-contract-terms save-contract-terms 'Moje standardowe warunki umowy' 'Мои стандартные условия договора' save-blocked- 'Aby zapisać plan, wybierz podłoże' 'Badanie jastrychu' 'Badanie starych płytek' 'Badanie podłogi z desek' 'Czy brakuje dylatacji?' 'Осмотр стяжки' estimate-set-prices estimate-fill-check-changes starter-use-all-references price-item-use-reference- 'Wpisz ceny tych pozycji' 'Ustaw jako moją cenę' 'Подставить цены из прайса' 'Zastąp liczbą majstra (zalecane)' 'Twoje wpisy tych samych pozycji' 'od majstra' 'Przenieś do pomieszczeń' 'Перенести в помещения' 'Перенести в приміщення' 'Carry over into the rooms' object-tile-masters trade-link-create- 'Linki dla majstrów' 'Ссылки для мастеров' 'Посилання для майстрів' 'Links for craftsmen' X-Trade-Link master-submit master-room-save- 'Elektryk — punkty i trasy' 'Hydraulik — punkty i trasy' duplicate-segment- segment-order- segment-drag- segment-up- 'Duplikuj' 'Zmień kolejność' 'Jaka okładzina będzie na podłodze?' 'Przytrzymaj pracę i przeciągnij' 'Ilość pracy musi być liczbą większą od zera.' 'Te prace nie liczą się z powierzchni' pe:open-wall-entry estimate-share-pdf 'Udostępnij / pobierz PDF' public/files client-why 'Dlaczego te prace?' object-summary-more 'Dodatkowo: pieniądze, terminy, ryzyka' price-item-toggle- 'Puste pole = nazwa z katalogu.' floor-work-move- 'Przenieś do planu podłogi' room-plan-report-floor floor-works/move inspection-analysing surface-row-risks- 'Liczę ryzyka, zalecane prace' 'Z pomieszczenia: ' client-what-next 'Co dalej?' trade-transfer-own-items- 'Dodaj je do cennika (bez ceny)' room-quick-names quick-opening- client-new-object- materials-copy-list 'Kopiuj listę zakupów' 'Plan zastosowany do: ' 'Dalej: pytania' 'Pytania badania' name_hints 'Точка водоснабжения' -detail 'Podłoże zbyt nierówne pod: ' 'Za wysoka wilgotność jastrychu' 'Wylewka masy samopoziomującej' 'Okładzina: płytki' 'Какое покрытие будет на полу?' for_floor 'Inna stawka…' 'Własna stawka VAT, %' 'Wpisz całą liczbę od 0 do 100.' 'Другая ставка…' room-points-quick-add-open room-qa-typical room-qa-save room-qa-qty- room-point-duplicate 'Dodaj kilka punktów naraz' 'Typowy zestaw: po 1 szt. każdego punktu' 'Добавить сразу несколько точек'; do
  has "$MARK" "$BUNDLE" || fail "G3" "в выданной сборке нет '$MARK'. $ROLLALL"
done
# страница клиента отдаётся по /c, а открытое API без секрета отвечает 404 и не кэшируется (через Caddy, как у клиента)
CPAGE=$(curl -fsS https://plan-estimate.pl/c) && has "assets/index-" "$CPAGE" || fail "G3" "адрес /c не отдаёт страницу приложения. $ROLLALL"
MPAGE=$(curl -fsS https://plan-estimate.pl/m) && has "assets/index-" "$MPAGE" || fail "G3" "адрес /m не отдаёт страницу приложения. $ROLLALL"
for WHO in client trade; do
  HDR=X-Client-Link; [ "$WHO" = trade ] && HDR=X-Trade-Link
  PUB=$(curl -s -D - -o /dev/null -H "$HDR: $(printf 'x%.0s' $(seq 1 43))" "https://plan-estimate.pl/api/public/$WHO")
  has " 404" "$PUB" || fail "G3" "открытое API ($WHO) без настоящего секрета должно отвечать 404: $PUB. $ROLLALL"
  grep -qi '^cache-control: no-store' <<<"$PUB" || fail "G3" "открытое API ($WHO) не говорит no-store: $PUB. $ROLLALL"
  grep -qi '^referrer-policy: no-referrer' <<<"$PUB" || fail "G3" "открытое API ($WHO) не говорит referrer-policy: no-referrer: $PUB. $ROLLALL"
done
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G3" "health не ok. $ROLLALL"
ok "G3 (frontend: прежние разделы, галочка «Ceny zawierają VAT», перетаскивание и окно добавления стен, фото на странице мастера, /c и /m отдаются, открытое API клиента и мастера закрыто секретом и не кэшируется)"

echo; echo "################ G4: кнопка меню Telegram ################"
set -a; source .env.production; set +a
R1=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${NEW}\"}}}")
R2=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#')
unset TELEGRAM_BOT_TOKEN
has '"ok":true' "$R1" || fail "G4" "setChatMenuButton: $R1 (приложение уже выложено и работает; кнопку можно повторить отдельно)"
has "?v=${NEW}" "$R2" || fail "G4" "getChatMenuButton не показывает ?v=${NEW}: $R2"
ok "G4 (кнопка ?v=$NEW)"

echo; echo "=============== ВСЁ PASS: версия $NEW выложена (миграции 0087-0091, база на 0091), данные те же, ничего не удалено ==============="
echo "Дальше (по порядку, каждый шаг — после вашей проверки):"
echo "  1) полностью закройте Telegram и откройте Mini App по кнопке меню: вход как обычно, всё прежнее на месте;"
echo "  2) смета-черновик с НДС 8 %: под выбором НДС галочка «Ceny zawierają VAT». Включите — «Razem brutto» станет равна сумме позиций, «Razem netto» и «VAT 8 %» выделятся из неё; выключите — НДС снова добавляется сверху. PDF-черновик: «Razem brutto», «w tym wartość netto», «w tym VAT 8%»;"
echo "  3) ссылка клиента на эту смету (после фиксации): netto / VAT / brutto те же, что в смете;"
echo "  4) нерегулярное помещение со стенами: справа от «Ściany» кнопка «＋ Dodaj ścianę» открывает окно; добавьте две стены подряд — окно остаётся открытым, закройте ✕ или «Назад»;"
echo "  5) «Zmień kolejność»: удерживайте стену ~0,3 с и тащите её вверх — у края экрана список прокручивается сам; отпустите — порядок сохранится (стрелки ↑ ↓ остались);"
echo "  6a) «Linki dla majstrów» → «Przenieś do pomieszczeń» в помещении, где у вас уже есть своя точка той же позиции: жёлтый блок «Twoje wpisy tych samych pozycji», по умолчанию «Zastąp liczbą majstra»; после переноса в «Punkty i trasy» ОДНА строка с числом мастера и пометкой «od majstra»;"
echo "  6b) смета-черновик со строками из помещений без цены: под суммами «Bez ceny: N poz.»; задайте цену этой позиции в прайсе и нажмите «Uzupełnij ceny z cennika» — строка получит цену, сумма вырастет, плашка исчезнет;"
echo "  6c) осмотр стены: ответьте на 2 вопроса и сразу сверните Telegram/вернитесь назад, не нажимая «Zapisz szkic» — при новом открытии ответы на месте (над кнопками «Odpowiedzi zapisane automatycznie.»);"
echo "  6d) стена без плана работ, завершённый осмотр с 2+ рекомендациями: «Dodaj wszystkie do prac (N)» → «Dodano do planów prac: N.»; план стены создан с основанием и качеством из осмотра;"
echo "  6e) помещение → «Plan pomieszczenia»: основание и класс, у «Ściany» кнопка «Z procesu technologicznego» → процесс → «Wstaw kroki»; в другом помещении «Skopiuj plan z innego pomieszczenia» → «Kopiuj» → списки на месте, затем «Zapisz i zastosuj»;"
echo "  6f) «Obiekty» → «Dodaj obiekt»: первым полем «Klient»; клиент с адресом заполняет пустые адрес, город, индекс (и название);"
echo "  6g) объект с финальной/принятой сметой без договорной суммы → «Faktury i zaliczki»: в сводке «Przyjmij kwotę netto z kosztorysu (wersja N): …» → сумма записана, кнопка исчезла;"
echo "  6h) объект с частным клиентом → «Umowa i protokoły» → «Umowa» → «Skomponuj umowę»: дата, место, НДС, «Konsument» и клиент как принимающий работы уже стоят (метка «uzupełnione»); во втором объекте подтягиваются гарантия/аванс/неустойки из первого договора;"
echo "  6i) меню ☰ → «Moje standardowe warunki umowy»: пока пусто — «Wypełnij z ostatniej umowy»; задайте гарантию/аванс → «Zapisz warunki»; новый договор другого объекта берёт их первыми (под кнопкой «z „Moich standardowych warunków umowy”»), остальное — из последнего договора;"
echo "  6j) план пола/стены без основания: под серой «Zapisz» — «Aby zapisać plan, wybierz podłoże»;"
echo "  6k) смета-черновик с позициями без цены: «Wpisz ceny tych pozycji (N)» → впишите цены → «Zapisz»; если это работы плана — «Sprawdź zmiany — przelicz prace planu» → «Aktualizuj kosztorys»; в прайсе у позиции без цены с ориентиром рынка — «Ustaw jako moją cenę»;"
echo "  6l) помещение → карточка «Podłoga» → «Badanie podłogi» → «Jastrych» / «Stara płytka» / «Podłoga z desek» (без класса качества, без стеновых оснований): влажность, трещины, dylatacje, плоскость, уровень; завершите осмотр — влажность даёт риск «Podwyższona wilgotność podłoża», dylatacje записываются как ustalenie; в «Opcje» пола план работ предлагает те же основания пола и не показывает класс;"
echo "  6m) помещение → «Podłoga» (и «Sufit») → «Opcje» → у прямоугольника «Duplikuj» — копия встаёт сразу за оригиналом; при двух и более прямоугольниках «Zmień kolejność»: удерживайте строку и перетащите (или ⠿), стрелки ↑↓ двигают на одно место, порядок сохраняется сразу, «Gotowe» закрывает режим; после перезагрузки порядок тот же, площадь «Razem» не меняется;"
echo "  6n) помещение → «Punkty i trasy» → «Dodaj kilka punktów naraz»: в списке только электрика / сантехника / «Punkt»-«Trasa» (уголки, швы ГКЛ, микроцемент — под кнопкой «Pokaż pozostałe pozycje»); «Typowy zestaw: po 1 szt. каждого точки» подставляет 1 в точки; впишите количества, одна кнопка «Zapisz (N)»; позиция, уже бывшая в помещении, помечена («Już na liście: …») и её количество прибавляется к той же строке; в одиночной форме «Dodaj punkt lub trasę» выбор уже имеющейся позиции даёт предупреждение;"
echo "  6o) телефон (Android) → внутри объекта, помещения, сметы, осмотра: системная кнопка «Назад» (или стрелка в шапке Telegram вместо ✕) возвращает на шаг назад; на списке объектов приложение сворачивается;"
echo "  6p) помещение → «Podłoga» → «Badanie podłogi» → «Beton» или «Inne»: вопросы пола (измеренная влажность, трещины, dylatacje, плоскость, уровень, состояние поверхности — 8 вопросов), а не стеновые; «Stara farba» в списке оснований пола нет;"
echo "  6q) смета-черновик → «VAT» → «Inna stawka…» → поле «Własna stawka VAT, %»: 5 → «Ustaw» → «VAT 5 %» и сумма брутто; 150 → «Wpisz całą liczbę od 0 do 100.»; то же в профиле исполнителя (меню → профиль → «Stawka VAT w kosztorysach» → «Inna stawka…»);"
echo "  6r) НОВЫЙ осмотр пола (любое основание) → первым вопросом «Jaka okładzina będzie na podłodze?» (плитка / крупный формат / микроцемент / ламинат / паркет / винил / неизвестно), «strefa mokra», «ogrzewanie podłogowe»; Beton + Płytki, влажность 2,5, ровность 4 → «Oceń ryzyka»: «Za wysoka wilgotność jastrychu…» и «Podłoże zbyt nierówne pod: płytki ceramiczne» (не «Zwiększone nierówności» стен), «Podstawa techniczna» — записи пола, «Oceń zalecenia» → «Pomiar wilgotności… CM» и «Wylewka masy samopoziomującej», фразы для клиента — про пол; в «Cennik» 14 новых работ пола без цены; старые осмотры пола остаются как были;"
echo "  6s) помещение нерегулярной формы без стен и без размеров → «+ Rozpocznij pomiar ścian»: страница прокручивается к карточке «Dodawanie ścian», курсор в поле ширины (если стены уже есть — открывается окно «＋ Dodaj ścianę»);"
echo "  6t) осмотр → «Oceń zalecenia» → работа в мп или шт. (например «Pomiar wilgotności… CM», «Zszywanie rys…») → «Dodaj do prac» спрашивает «Ilość» (цифровая клавиатура; пусто = позже) → «Dodaj do prac»; «Dodaj wszystkie do prac» сначала спрашивает количества таких работ; в плане работы поле «Ilość: … mb/szt.» с этим числом; смета после «Sprawdź zmiany» показывает это количество, а не «Ilość do ustalenia»;"
echo "  6u) смета → строка с «Ilość do ustalenia» → «Edytuj»: поле количества пустое (серый 0) и уже в фокусе — сразу печатаете число;"
echo "  6v) план работ (стена / пол / потолок) с 2+ работами: удержите карточку работы ~0,5 с и перетащите (или возьмите ⠿) — порядок меняется, «Zapisz» становится активной; стрелки в меню «⋯» остались;"
echo "  6w) стена → «Badanie ściany» → ответы → «Zakończ badanie»: сначала «Liczę ryzyka…», затем риски, рекомендованные работы и фразы уже посчитаны (без нажатий «Oceń…»); назад в помещение — у стены с высоким риском значок «⚠ N»; шаг класса — кнопка «Dalej: pytania», у «Stara farba» только S1–S4;"
echo "  6x) смета: строки точек помещения — «Z pomieszczenia: Łazienka»; «Podgląd PDF» под строками; «Zabezpieczenie podłóg» на стенах = площадь пола помещения (одна строка с площадью, на других стенах 0);"
echo "  6y) страница клиента: одинаковые работы помещения — одной строкой; «Materiały» отдельно; имя клиента уже в форме; после подтверждения — «Co dalej?» с кнопками связи;"
echo "  6z) мастер: новая ссылка — польский по умолчанию; «Przenieś do pomieszczeń» → «Dodaj je do cennika (bez ceny)» → свои позиции мастера переносятся; на фото «Ściana 1», не «Wall 1»;"
echo "  6za) помещения: быстрые названия в форме, список по порядку ввода, на карточке «Otwórz» + «Opcje»; на стене «＋ Drzwi» / «＋ Okno»; у каждой стены свой цвет; карточка клиента — «Nowy obiekt tego klienta»; плитки объекта показывают «Pomieszczenia: N», версию/сумму/статус сметы, «Klient otworzył link…»;"
echo "  6zb) «Materiały» → «Do zakupu»: галочки «Kupione», «Kopiuj listę zakupów»; на RU-экране под «Klej do płytek (worek)» — «Плиточный клей (мешок)»; вход в браузере на RU-телефоне — по-русски;"
echo "  6zc) «Plan pomieszczenia» с «Zabezpieczenie podłóg» у стен → «Zapisz i zastosuj»: в отчёте «Zabezpieczenie podłóg trafiło do planu podłogi», у стен её нет, в плане «Podłoga» она одна; в плане стены старая защита пола — подсказка и кнопка «Przenieś do planu podłogi»; смета — одна строка по площади пола;"
echo "  6zd) «Cennik» → «Pozycje»: одна строка на позицию «название — цена — ✏️»; нажатие раскрывает детали (рынок, архив); ✏️ у позиции каталога и у своей открывает одну форму под строкой (у каталога пустое название = название каталога, единица фиксирована);"
echo "  6ze) объект → «Podsumowanie obiektu» → «Dodatkowo: pieniądze, terminy, ryzyka»: смета (версия, сумма, статус), договорная сумма, получено, осталось; даты работ и ближайший платёж; высокие риски по помещениям;"
echo "  6zf) объект в «Planowanie»: клиент подтверждает смету по ссылке (или подписан договор) → статус объекта «W realizacji»; выдан протокол окончательной приёмки без отказа → «Zakończony»;"
echo "  6zg) страница клиента → «Dlaczego te prace? Standard i zdjęcia z oględzin»: стандарт помещений с описанием, у работ из осмотра причина, дата и фото (нажатие открывает фото);"
echo "  6zh) смета (черновик) → «Udostępnij / pobierz PDF»: в Telegram открывается окно скачивания PDF; «Wysłane dokumenty» → у отправленного документа та же кнопка; файл открывается и сохраняется;"
echo "  6) страница мастера: под размерами помещения «Mapa tras» (фото с метками его профессии) и «Zdjęcia pomieszczenia»; сообщение со ссылкой: сначала описание, потом адрес; по-польски «majster»;"
echo "  7) подробно — README.md: «Замеры» (стены нерегулярного помещения) и «Смета» (НДС внутри цен);"
echo "  8) бэкап под новую голову: cd ~/apps/plan_-_estimate && BACKUP_BRANCH=$BR BACKUP_HEAD=0091_planned_work_quantity bash ~/backup_a9.sh  (в НОВОЙ сессии, потом закрыть её);"
echo "  9) слияние $BR → main — только по отдельному «да»."
)
