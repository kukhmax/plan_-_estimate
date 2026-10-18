#!/usr/bin/env bash
# Шифрование данных клиентов, EN-3b — СМЕНА КЛЮЧА ДАННЫХ: каждому владельцу создаётся новый ключ данных, все его значения (зашифрованные колонки) перешифровываются новым ключом, затем старый ключ удаляется.
# Нужно: после выкладки EN-3b, по вашему отдельному «да»; при подозрении, что утёк именно КЛЮЧ ДАННЫХ владельца (а не ключ сервера: его меняет скрипт docs/CLIENT_ENCRYPTION_KEK_ROTATION_RU.sh).
# Порядок: ворота S — новый ключ + пересоздание backend (иначе он продолжал бы писать старым ключом, который держит в памяти); ворота R — перешифровка значений (порциями, повторяемо, «дата изменения» не меняется);
# ворота P — удаление старого ключа (только когда им не зашифровано ни одно значение; необратимо, кроме как из бэкапов) и пересоздание backend (старый ключ уходит и из памяти).
# Данные не удаляются и не меняются по смыслу. Бэкапы, сделанные ДО смены, содержат старый ключ данных (завёрнутый ключом сервера): они по-прежнему открываются ключом сервера; значит ключ сервера (и его копии) хранить, как и раньше.
# Скрипт можно запускать повторно (середину смены узнаёт по тому, что часть значений ещё под старым ключом). Секреты и ключи не печатает (только числа и первые 8 знаков идентификаторов).
# Запуск (в НОВОЙ SSH-сессии на VM):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-client-encryption && git show origin/backlog-client-encryption:docs/CLIENT_ENCRYPTION_DEK_ROTATION_RU.sh > ~/rotate_dek.sh && bash ~/rotate_dek.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }
R="$HOME/backups/plan-estimate/db-backup"
ENVF=".env.production"
getenvf() { grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2-; }
DEK() { docker exec plan_estimate_backend python -m app.cli.rotate_data_keys "$@"; }
wait_healthy() { for i in $(seq 1 36); do [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && return 0; sleep 5; done; return 1; }
recreate_backend() { PC up -d --no-deps --force-recreate backend && wait_healthy; }

echo "################ G0: проверка перед сменой ключа данных (только чтение) ################"
[ "$(env | grep -c '^MEDIA_S3\|^BACKUP_')" = "0" ] || fail "G0" "В оболочке лишние переменные MEDIA_S3/BACKUP_. Откройте новую SSH-сессию (не ту, где шёл бэкап)."
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "G0" "health недоступен"
has '"status":"ok"' "$H" || fail "G0" "health не ok: $H"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
ST=$(DEK status 2>&1); RC=$?
[ "$RC" = "0" ] || [ "$RC" = "3" ] || { echo "$ST"; fail "G0" "команда rotate_data_keys недоступна (код $RC): сначала должна быть выложена EN-3b (docs/CLIENT_ENCRYPTION_EN3B_DEPLOY_RU.sh)"; }
echo "$ST"
[ "$(getenvf DATA_STRICT_READ)" = "true" ] || fail "G0" "DATA_STRICT_READ в $ENVF не true (состояние после EN-2b: строгое чтение включено)"
[ -z "$(getenvf DATA_KEK_PREVIOUS)" ] || fail "G0" "в $ENVF стоит DATA_KEK_PREVIOUS: идёт ротация ключа СЕРВЕРА; сначала закончите её (docs/CLIENT_ENCRYPTION_KEK_ROTATION_RU.sh)"
docker exec plan_estimate_backend python -m app.cli.rotate_keys verify > /dev/null || fail "G0" "не все ключи данных открываются текущим ключом сервера (ротация ключа сервера не закончена?)"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "G0" "verify шифрования не прошёл до смены (открытые или нерасшифровываемые значения)"
PENDING=$(grep -o 'STILL SEALED WITH AN OLD KEY: [0-9]*' <<<"$ST" | grep -o '[0-9]*$')
[ -n "$PENDING" ] || fail "G0" "не удалось прочитать число значений под старым ключом данных"
if [ "$PENDING" = "0" ]; then MODE=start; else MODE=resume; fi
if [ "$MODE" = start ]; then
  LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
  [ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9"
  AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
  [ "$AGE_H" -le 24 ] || fail "G0" "последний бэкап $LASTRUN старше суток (${AGE_H} ч): сделайте свежий (BACKUP_BRANCH=backlog-client-encryption BACKUP_HEAD=<голова> bash ~/backup_a9.sh)"
  echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
else
  echo "ПРОДОЛЖЕНИЕ смены: под неактивным ключом данных ещё $PENDING значений"
fi
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from contracts; select count(*) from project_payments; select count(*) from photo_attachments; select count(*) from photo_assets;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
KEYSBEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc 'select count(*) from data_keys'")
LOOP_ENV=$(getenvf CALENDAR_DISPATCHER_ENABLED | tr 'A-Z' 'a-z'); [ -n "$LOOP_ENV" ] || LOOP_ENV=false
DOMAIN=$(getenvf APP_DOMAIN); [ -n "$DOMAIN" ] || fail "G0" "в $ENVF нет APP_DOMAIN"
echo "режим: $MODE; строк (клиенты/объекты/журнал/договоры/расчёты/привязки фото/файлы фото): $BEFORE; ключей данных: $KEYSBEFORE"
ok "G0"

if [ "$MODE" = start ]; then
echo; echo "################ ВОРОТА S: новый ключ данных ################"
echo "Что произойдёт: каждому владельцу создаётся НОВЫЙ активный ключ данных (старый остаётся, неактивный, чтобы читать то, что им зашифровано); затем backend пересоздаётся (30–60 секунд), чтобы он не писал старым ключом из памяти."
echo "  • Данные не меняются и продолжают читаться. Откат на этом шаге не нужен: старые значения читаются старым ключом, новые пишутся новым."
echo "  • Бэкап перед сменой: $LASTRUN (${AGE_H} ч назад)."
echo
echo "Чтобы создать новый ключ данных и пересоздать backend, введите ТОЧНО:  НОВЫЙ КЛЮЧ ДАННЫХ ДА"
printf '> '
read -r ANSWER < "${ROTATE_TTY:-/dev/tty}" || fail "S" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии"
[ "$ANSWER" = "НОВЫЙ КЛЮЧ ДАННЫХ ДА" ] || { echo; echo "Остановлено на воротах S (введено: '$ANSWER'). Ничего не менялось."; exit 1; }
ok "S (подтверждено вами)"
SO=$(DEK start --all) || { echo "$SO"; fail "S" "создание нового ключа данных не удалось (если часть владельцев уже получила ключ, повторный запуск скрипта продолжит)"; }
echo "$SO"
recreate_backend || { docker logs plan_estimate_backend --tail 40; fail "S" "backend не стал healthy после пересоздания"; }
LOG=$(docker logs plan_estimate_backend 2>&1)
grep -qE "Traceback|DATA_KEK" <<<"$LOG" && { tail -30 <<<"$LOG"; fail "S" "в логе ошибка после пересоздания backend"; }
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "S" "verify шифрования не прошёл после создания нового ключа (данные не читаются)"
ok "S (новый ключ данных создан, backend пересоздан, данные читаются)"
else
echo; echo "--- продолжение: backend пересоздаётся (чтобы он точно писал активным ключом, а не старым из памяти) ---"
recreate_backend || { docker logs plan_estimate_backend --tail 40; fail "S" "backend не стал healthy после пересоздания"; }
ok "S (продолжение: backend пересоздан)"
fi

echo; echo "################ ВОРОТА R: перешифровка значений новым ключом ################"
echo "Что произойдёт: каждое значение владельца, зашифрованное не активным ключом, расшифровывается старым и шифруется новым ключом. Порциями по 200, каждая — своя транзакция; «дата изменения» не меняется; значение, изменённое в это время, не затирается (найдётся следующим проходом). Повторяемо."
echo "Чтобы перешифровать, введите ТОЧНО:  ПЕРЕШИФРОВКА ДА"
printf '> '
read -r ANSWER < "${ROTATE_TTY:-/dev/tty}" || fail "R" "нет терминала для подтверждения"
[ "$ANSWER" = "ПЕРЕШИФРОВКА ДА" ] || { echo; echo "Остановлено на воротах R (введено: '$ANSWER'). Данные читаются при обоих ключах; повторный запуск скрипта продолжит с этого места."; exit 1; }
ok "R (подтверждено вами)"
DONE=no
for TRY in 1 2 3; do
  RS=$(DEK reseal) && { DONE=yes; echo "$RS" | tail -n 3; break; }
  echo "$RS" | tail -n 4; echo "(попытка $TRY: часть значений изменилась во время работы или не расшифровалась; повторяю)"
done
[ "$DONE" = yes ] || fail "R" "перешифровка не довела дело до конца за 3 попытки (значения НЕ потеряны: читаются при обоих ключах). Пришлите вывод"
STR=$(DEK status) || { echo "$STR"; fail "R" "после перешифровки остались значения под старым ключом"; }
has "STILL SEALED WITH AN OLD KEY: 0" "$STR" || fail "R" "после перешифровки остались значения под старым ключом: $STR"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "R" "verify шифрования после перешифровки не прошёл"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "R" "число строк изменилось: было $BEFORE стало $AFTER"
ok "R (все значения под активным ключом данных; число строк то же)"

echo; echo "################ ВОРОТА P: удалить старый ключ данных ################"
echo "Что произойдёт: неактивные ключи данных, которыми не зашифровано ни одно значение, удаляются из базы (команда откажется, если хоть одно значение ещё под ними); backend пересоздаётся (старый ключ уходит и из памяти)."
echo "  • НЕОБРАТИМО для живой базы: старый ключ данных останется только в бэкапах, сделанных до смены (завёрнутый ключом сервера)."
echo "Чтобы удалить старый ключ данных, введите ТОЧНО:  СТАРЫЙ КЛЮЧ ДАННЫХ УДАЛИТЬ ДА"
printf '> '
read -r ANSWER < "${ROTATE_TTY:-/dev/tty}" || fail "P" "нет терминала для подтверждения"
[ "$ANSWER" = "СТАРЫЙ КЛЮЧ ДАННЫХ УДАЛИТЬ ДА" ] || { echo; echo "Остановлено на воротах P (введено: '$ANSWER'). Все значения уже под новым ключом; старый ключ ещё в базе; повторный запуск продолжит с этого места."; exit 1; }
ok "P (подтверждено вами)"
RT=$(DEK retire) || { echo "$RT"; fail "P" "удаление старого ключа отказало (ничего не удалено)"; }
echo "$RT"
recreate_backend || { docker logs plan_estimate_backend --tail 40; fail "P" "backend не стал healthy после пересоздания"; }
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "P" "verify шифрования с одним ключом не прошёл"
FIN=$(DEK status) || { echo "$FIN"; fail "P" "статус после удаления не чистый"; }
echo "$FIN"
KEYSAFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc 'select count(*) from data_keys'")
OWNERS=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc 'select count(distinct owner_id) from data_keys'")
[ "$KEYSAFTER" = "$OWNERS" ] || fail "P" "после удаления ключей данных ($KEYSAFTER) не по одному на владельца ($OWNERS)"
[ "$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower())")" = "true" ] || fail "P" "строгое чтение в контейнере выключено"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "P" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "P" "число строк изменилось: было $BEFORE стало $AFTER"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "P" "health не ok"
ok "P (ключей данных: $KEYSAFTER, по одному на владельца; всё читается; число строк то же)"

echo; echo "=============== ВСЁ PASS: ключ данных заменён (ключей данных было $KEYSBEFORE, стало $KEYSAFTER), все значения под новым ключом ==============="
echo "Дальше (по порядку):"
echo "  1) закройте Telegram полностью, откройте Mini App: клиенты, объекты, «Faktury i zaliczki», документы — как раньше;"
echo "  2) бэкап под текущую голову: cd ~/apps/plan_-_estimate && BACKUP_BRANCH=backlog-client-encryption BACKUP_HEAD=<голова> bash ~/backup_a9.sh  (в НОВОЙ сессии) — он уже содержит значения под НОВЫМ ключом данных;"
echo "  3) приёмка: «принимаем EN-3b»."
)
