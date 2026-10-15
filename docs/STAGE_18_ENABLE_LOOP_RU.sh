#!/usr/bin/env bash
# Stage 18 — включение (или выключение) цикла, который присылает напоминания в Telegram. Отдельный шаг после выкладки и вашей проверки.
# Включает CALENDAR_DISPATCHER_ENABLED=true в .env.production (копия файла сохраняется), пересоздаёт только backend, проверяет, что цикл запустился.
# Выключение:  bash ~/enable_loop.sh off
# Запуск (в НОВОЙ SSH-сессии на VM):
#   cd ~/apps/plan_-_estimate && git fetch -q origin stage-18 && git show origin/stage-18:docs/STAGE_18_ENABLE_LOOP_RU.sh > ~/enable_loop.sh && bash ~/enable_loop.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }
MODE="${1:-on}"

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }
case "$MODE" in on) WANT=true; WANTPY=True;; off) WANT=false; WANTPY=False;; *) fail "args" "режим: on или off";; esac

echo "################ E0: проверка (только чтение) ################"
[ "$(env | grep -c '^MEDIA_S3\|^BACKUP_')" = "0" ] || fail "E0" "В оболочке лишние переменные MEDIA_S3/BACKUP_. Откройте новую SSH-сессию (не ту, где шёл бэкап)."
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "E0" "health недоступен"
has '"status":"ok"' "$H" || fail "E0" "health не ok: $H"
AL=$(docker exec plan_estimate_backend alembic current 2>/dev/null)
has '0054_calendar_reminders' "$AL" || fail "E0" "alembic current не 0054_calendar_reminders (сначала выкладка Stage 18): $AL"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "E0" "backend не healthy"
TOKEN_SET=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(bool(s.TELEGRAM_BOT_TOKEN))")
[ "$TOKEN_SET" = "True" ] || fail "E0" "в backend нет токена бота: сообщения слать нечем"
NOW=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(s.CALENDAR_DISPATCHER_ENABLED)")
echo "сейчас в контейнере CALENDAR_DISPATCHER_ENABLED = $NOW; нужно $WANTPY"
[ "$NOW" != "$WANTPY" ] || { echo "Уже так. Ничего не меняю."; exit 0; }
ok "E0"

echo; echo "################ E1: .env.production и пересоздание backend ################"
cp -p .env.production ".env.production.pre-calendar-$(date +%Y%m%d%H%M%S)" || fail "E1" "не удалось сохранить копию .env.production"
chmod 600 .env.production.pre-calendar-* 2>/dev/null
if grep -q '^CALENDAR_DISPATCHER_ENABLED=' .env.production; then
  sed -i "s/^CALENDAR_DISPATCHER_ENABLED=.*/CALENDAR_DISPATCHER_ENABLED=$WANT/" .env.production || fail "E1" "sed не удался"
else
  printf '\nCALENDAR_DISPATCHER_ENABLED=%s\n' "$WANT" >> .env.production || fail "E1" "не удалось дописать .env.production"
fi
[ "$(grep -c '^CALENDAR_DISPATCHER_ENABLED=' .env.production)" = "1" ] || fail "E1" "в .env.production не одна строка CALENDAR_DISPATCHER_ENABLED"
ROLL="Откат: вернуть копию .env.production.pre-calendar-* и docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps backend"
PC up -d --no-deps backend || fail "E1" "up backend не удался. $ROLL"
for i in $(seq 1 36); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && break; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || { docker logs plan_estimate_backend --tail 40; fail "E1" "backend не стал healthy. $ROLL"; }
LOG=$(docker logs plan_estimate_backend --tail 120 2>&1)
grep -qE "Traceback|CalendarTextsError" <<<"$LOG" && { tail -40 <<<"$LOG"; fail "E1" "в логе ошибка. $ROLL"; }
has "Application startup complete" "$LOG" || fail "E1" "нет Application startup complete. $ROLL"
NOW2=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(s.CALENDAR_DISPATCHER_ENABLED)")
[ "$NOW2" = "$WANTPY" ] || fail "E1" "в контейнере CALENDAR_DISPATCHER_ENABLED = $NOW2. $ROLL"
if [ "$MODE" = "on" ]; then
  has "calendar loop started" "$LOG" || fail "E1" "в логе нет «calendar loop started» (цикл не запустился). $ROLL"
  sleep 75
  LOG2=$(docker logs plan_estimate_backend --since 2m 2>&1)
  grep -qE "calendar loop pass failed|calendar delivery failed|calendar reconciliation failed" <<<"$LOG2" && { grep -E "calendar" <<<"$LOG2" | tail -10; fail "E1" "цикл работает с ошибками (см. выше). Выключить: bash ~/enable_loop.sh off"; }
  ok "E1 (цикл запущен, за первые минуты ошибок нет)"
else
  has "calendar loop started" "$LOG" && fail "E1" "цикл всё ещё запущен. $ROLL"
  ok "E1 (цикл выключен)"
fi
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "E1" "health не ok. $ROLL"
if [ "$MODE" = "on" ]; then
  echo
  echo "=============== ЦИКЛ ВКЛЮЧЁН ==============="
  echo "Первая настоящая проверка (вручную, на телефоне):"
  echo "  1) Mini App → Календарь → «+ Своё напоминание» → «Своё время…» → дата сегодня, время через 3–4 минуты, заметка «проверка» → Сохранить."
  echo "  2) Через 3–4 минуты в чате с ботом приходит сообщение «🔔 проверка» с кнопкой «Открыть»; кнопка открывает календарь."
  echo "  3) Если не пришло за 6 минут: docker logs plan_estimate_backend --since 10m | grep -i calendar  и пришлите вывод; выключить: bash ~/enable_loop.sh off"
fi
)
