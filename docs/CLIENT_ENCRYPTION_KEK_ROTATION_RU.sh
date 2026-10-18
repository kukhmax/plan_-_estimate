#!/usr/bin/env bash
# Шифрование данных клиентов, EN-3a — РОТАЦИЯ ключа сервера (DATA_KEK): новый ключ, ключи данных перезавёртываются новым ключом, сами данные НЕ перешифровываются и не меняются.
# Нужно: после EN-3a (код ротации выложен), по вашему отдельному «да»; при подозрении на утечку ключа и при плановой смене. Без выкладки EN-3a скрипт остановится.
# Порядок: (1) вы создаёте НОВЫЙ ключ в файле ~/new_data_kek.txt и сохраняете его копии (менеджер паролей + бумага); (2) скрипт ставит в .env.production новый DATA_KEK, версию +1 и СТАРЫЙ ключ как DATA_KEK_PREVIOUS,
# пересоздаёт backend (теперь он читает ключи данных при любом из двух) и проверяет, что все данные читаются; (3) ворота R: перезавёртывание; (4) ворота P: старый ключ убирается из .env.production.
# ВАЖНО: СТАРЫЙ КЛЮЧ НЕ УДАЛЯТЬ из менеджера паролей и с бумаги: старые бэкапы содержат ключи данных, завёрнутые СТАРЫМ ключом; для их восстановления он нужен (пометьте запись «выведен из работы, версия N»). Потеря ключа = потеря данных.
# Откат до ворот R: вернуть сохранённый файл .env.production (команда печатается при любом отказе) и пересоздать backend. После ворот R (ключи завёрнуты новым ключом) откат — тем же путём, но старый ключ нужно вернуть как DATA_KEK_PREVIOUS (печатается).
# Скрипт можно запускать повторно (узнаёт середину ротации по DATA_KEK_PREVIOUS). Секреты и ключи не печатает (только отпечатки, 8 знаков SHA-256).
# Запуск (в НОВОЙ SSH-сессии на VM):
#   cd ~/apps/plan_-_estimate && git fetch -q origin backlog-client-encryption && git show origin/backlog-client-encryption:docs/CLIENT_ENCRYPTION_KEK_ROTATION_RU.sh > ~/rotate_kek.sh && bash ~/rotate_kek.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }
fp()   { printf '%s' "$1" | sha256sum | cut -c1-8; }
R="$HOME/backups/plan-estimate/db-backup"
ENVF=".env.production"
NEWF="${ROTATE_NEWKEY_FILE:-$HOME/new_data_kek.txt}"
SAVED="$HOME/.env.production.before-rotation"
getenvf() { grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2-; }
PSQL() { docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"$1\""; }
wait_healthy() { for i in $(seq 1 36); do [ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend 2>/dev/null)" = "healthy" ] && return 0; sleep 5; done; return 1; }
# переписывает ровно три строки ключей в .env.production (значения берёт из окружения: в списке процессов их нет); остальные строки не трогает
write_keys() { # $1 = DATA_KEK, $2 = DATA_KEK_VERSION, $3 = DATA_KEK_PREVIOUS
  NK="$1" NV="$2" NP="$3" awk 'BEGIN{k=0;v=0;p=0}
    /^DATA_KEK=/{print "DATA_KEK=" ENVIRON["NK"]; k=1; next}
    /^DATA_KEK_VERSION=/{print "DATA_KEK_VERSION=" ENVIRON["NV"]; v=1; next}
    /^DATA_KEK_PREVIOUS=/{print "DATA_KEK_PREVIOUS=" ENVIRON["NP"]; p=1; next}
    {print}
    END{if(!k)print "DATA_KEK=" ENVIRON["NK"]; if(!v)print "DATA_KEK_VERSION=" ENVIRON["NV"]; if(!p)print "DATA_KEK_PREVIOUS=" ENVIRON["NP"]}' "$ENVF" > "$ENVF.tmp" && chmod --reference="$ENVF" "$ENVF.tmp" && mv "$ENVF.tmp" "$ENVF"
}

echo "################ G0: проверка перед ротацией (только чтение) ################"
[ "$(env | grep -c '^MEDIA_S3\|^BACKUP_')" = "0" ] || fail "G0" "В оболочке лишние переменные MEDIA_S3/BACKUP_. Откройте новую SSH-сессию (не ту, где шёл бэкап)."
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "G0" "health недоступен"
has '"status":"ok"' "$H" || fail "G0" "health не ok: $H"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
docker exec plan_estimate_backend python -m app.cli.rotate_keys status > /dev/null 2>&1; RC=$?
[ "$RC" = "0" ] || [ "$RC" = "3" ] || fail "G0" "команда rotate_keys недоступна или не отработала (код $RC): сначала должна быть выложена EN-3a (docs/CLIENT_ENCRYPTION_EN3A_DEPLOY_RU.sh)"
CUR=$(getenvf DATA_KEK); PREVK=$(getenvf DATA_KEK_PREVIOUS); VER=$(getenvf DATA_KEK_VERSION); [ -n "$VER" ] || VER=1
[ "$(printf '%s' "$CUR" | base64 -d 2>/dev/null | wc -c)" = "32" ] || fail "G0" "DATA_KEK в $ENVF отсутствует или не base64 из 32 байт"
[ "$(getenvf DATA_STRICT_READ)" = "true" ] || fail "G0" "DATA_STRICT_READ в $ENVF не true (состояние после EN-2b: строгое чтение включено)"
[ -f "$NEWF" ] || fail "G0" "нет файла нового ключа $NEWF. Создайте его (один раз) и сохраните копии:  docker exec plan_estimate_backend python -m app.cli.rotate_keys new-key > $NEWF && chmod 600 $NEWF  (затем скопируйте ключ в менеджер паролей и на бумагу)"
[ "$(stat -c %a "$NEWF")" = "600" ] || fail "G0" "права файла $NEWF должны быть 600 (chmod 600 $NEWF)"
NEWK=$(tr -d ' \n\r' < "$NEWF")
[ "$(printf '%s' "$NEWK" | base64 -d 2>/dev/null | wc -c)" = "32" ] || fail "G0" "в $NEWF не base64 ровно из 32 байт"
if [ -z "$PREVK" ]; then
  MODE=start
  [ "$NEWK" != "$CUR" ] || fail "G0" "новый ключ в $NEWF совпадает с текущим DATA_KEK: нечего менять (ротация уже выполнена? тогда ничего больше не нужно)"
  LASTRUN=$(ls -1t "$R/data/encrypted" 2>/dev/null | head -1)
  [ -n "$LASTRUN" ] || fail "G0" "нет ни одного запуска бэкапа в $R/data/encrypted: сначала A9"
  AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$R/data/encrypted/$LASTRUN") ) / 3600 ))
  [ "$AGE_H" -le 24 ] || fail "G0" "последний бэкап $LASTRUN старше суток (${AGE_H} ч): сделайте свежий (BACKUP_BRANCH=backlog-client-encryption BACKUP_HEAD=<голова> bash ~/backup_a9.sh)"
  echo "последний бэкап: $LASTRUN (${AGE_H} ч назад)"
  ST=$(docker exec plan_estimate_backend python -m app.cli.rotate_keys status) || { echo "$ST"; fail "G0" "не все ключи данных открываются текущим ключом: ротацию начинать нельзя"; }
  has "ROTATION DONE" "$ST" || fail "G0" "до ротации все ключи данных должны открываться текущим ключом сервера: $ST"
else
  MODE=resume
  [ "$NEWK" = "$CUR" ] || fail "G0" "в $ENVF уже есть DATA_KEK_PREVIOUS (ротация начата), но DATA_KEK не равен ключу из $NEWF: состояние неизвестно. Ничего не меняю"
  [ "$(printf '%s' "$PREVK" | base64 -d 2>/dev/null | wc -c)" = "32" ] || fail "G0" "DATA_KEK_PREVIOUS в $ENVF — не base64 из 32 байт"
  echo "ПРОДОЛЖЕНИЕ ротации: ключ из $NEWF уже установлен как DATA_KEK, старый стоит как DATA_KEK_PREVIOUS"
fi
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "G0" "verify шифрования не прошёл до ротации"
Q="select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from contracts; select count(*) from project_payments; select count(*) from data_keys; select count(*) from photo_attachments; select count(*) from photo_assets;"
BEFORE=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
LOOP_ENV=$(getenvf CALENDAR_DISPATCHER_ENABLED | tr 'A-Z' 'a-z'); [ -n "$LOOP_ENV" ] || LOOP_ENV=false
DOMAIN=$(getenvf APP_DOMAIN); [ -n "$DOMAIN" ] || fail "G0" "в $ENVF нет APP_DOMAIN"
if [ "$MODE" = start ]; then OLDFP=$(fp "$CUR"); NEWFP=$(fp "$NEWK"); else OLDFP=$(fp "$PREVK"); NEWFP=$(fp "$CUR"); fi
echo "режим: $MODE; версия ключа сейчас: $VER; отпечаток СТАРОГО ключа: $OLDFP; отпечаток НОВОГО ключа: $NEWFP; строк (клиенты/объекты/журнал/договоры/расчёты/ключи данных/привязки фото/файлы фото): $BEFORE"
ok "G0"

if [ "$MODE" = start ]; then
echo; echo "################ ВОРОТА K: новый ключ сохранён ################"
echo "  • НОВЫЙ ключ (отпечаток $NEWFP) лежит в $NEWF. Прежде чем идти дальше, сохраните его: менеджер паролей (запись «Plan & Estimate — DATA_KEK, версия $((VER+1))») и бумага в другом месте."
echo "  • Проверка копии: printf '%s' \"<ваша копия>\" | sha256sum | cut -c1-8  — должно быть $NEWFP."
echo "  • СТАРЫЙ ключ (отпечаток $OLDFP) НЕ удаляйте: старые бэкапы восстанавливаются только им. Пометьте его «выведен из работы, версия $VER»."
echo "  • Дальше: .env.production получит новый DATA_KEK, версию $((VER+1)) и старый ключ как DATA_KEK_PREVIOUS; backend пересоздаётся (30–60 секунд). Данные не меняются."
echo
echo "Чтобы подтвердить, что копия нового ключа сохранена и отпечаток совпадает, введите ТОЧНО:  КЛЮЧ СОХРАНЁН $NEWFP"
printf '> '
read -r ANSWER < "${ROTATE_TTY:-/dev/tty}" || fail "K" "нет терминала для подтверждения: запустите скрипт в обычной SSH-сессии"
[ "$ANSWER" = "КЛЮЧ СОХРАНЁН $NEWFP" ] || { echo; echo "Остановлено на воротах K (введено: '$ANSWER'). Ничего не менялось."; exit 1; }
ok "K (новый ключ сохранён, отпечаток $NEWFP подтверждён вами)"

echo; echo "################ S1: .env.production и backend ################"
cp -p "$ENVF" "$SAVED" && chmod 600 "$SAVED" || fail "S1" "не удалось сохранить копию $ENVF"
ROLLB="Откат: cp -p $SAVED $ENVF  и  docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps backend   (старый ключ вернётся как DATA_KEK; ключи данных ещё завёрнуты им)"
write_keys "$NEWK" "$((VER+1))" "$CUR" || { cp -p "$SAVED" "$ENVF"; fail "S1" "не удалось записать ключи в $ENVF (файл возвращён)"; }
[ "$(getenvf DATA_KEK)" = "$NEWK" ] && [ "$(getenvf DATA_KEK_PREVIOUS)" = "$CUR" ] && [ "$(getenvf DATA_KEK_VERSION)" = "$((VER+1))" ] || { cp -p "$SAVED" "$ENVF"; fail "S1" "после записи в $ENVF не те значения (файл возвращён)"; }
[ "$(grep -c '^DATA_KEK=' "$ENVF")" = "1" ] || { cp -p "$SAVED" "$ENVF"; fail "S1" "в $ENVF не ровно одна строка DATA_KEK= (файл возвращён)"; }
PC up -d --no-deps backend || fail "S1" "up backend не удался. $ROLLB"
wait_healthy || { docker logs plan_estimate_backend --tail 40; fail "S1" "backend не стал healthy за 3 минуты. $ROLLB"; }
fi

ROLLB="Откат до ворот R: cp -p $SAVED $ENVF  и  docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps backend"
echo; echo "################ S2: backend читает при обоих ключах ################"
LOG=$(docker logs plan_estimate_backend 2>&1)
grep -qE "Traceback|DATA_KEK" <<<"$LOG" && { tail -30 <<<"$LOG"; fail "S2" "в логе ошибка. $ROLLB"; }
ST=$(docker exec plan_estimate_backend python -m app.cli.rotate_keys status); echo "$ST"
if [ "$MODE" = start ]; then
  TOTALK=$(PSQL "select count(*) from data_keys where wrapped_by = 'SERVER_KEK'")
  has "open only with DATA_KEK_PREVIOUS (still to be re-wrapped): $TOTALK" "$ST" || fail "S2" "не все $TOTALK ключей данных открываются старым ключом как «предыдущим». $ROLLB"
fi
has "open with neither (unreadable): 0" "$ST" || fail "S2" "есть ключи данных, не открывающиеся ни одним ключом. $ROLLB"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "S2" "verify шифрования не прошёл при двух ключах (данные не читаются). $ROLLB"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "S2" "health не ok. $ROLLB"
ok "S2 (все данные читаются при двух ключах; ключи данных ещё завёрнуты старым ключом)"

echo; echo "################ ВОРОТА R: перезавёртывание ключей данных ################"
echo "Что произойдёт: каждый ключ данных (по одному на владельца) перезавёртывается НОВЫМ ключом сервера; сами данные не трогаются; всё или ничего (одна транзакция). Повторяемо."
echo "Чтобы перезавернуть, введите ТОЧНО:  ПЕРЕЗАВОРАЧИВАНИЕ ДА"
printf '> '
read -r ANSWER < "${ROTATE_TTY:-/dev/tty}" || fail "R" "нет терминала для подтверждения"
[ "$ANSWER" = "ПЕРЕЗАВОРАЧИВАНИЕ ДА" ] || { echo; echo "Остановлено на воротах R (введено: '$ANSWER'). Backend работает при двух ключах; повторный запуск скрипта продолжит с этого места."; exit 1; }
ok "R (подтверждено вами)"
RW=$(docker exec plan_estimate_backend python -m app.cli.rotate_keys rewrap) || { echo "$RW"; fail "R" "перезавёртывание не удалось (ничего не изменено: всё или ничего). Backend работает при двух ключах"; }
echo "$RW"
has "ROTATION DONE" "$RW" || fail "R" "после перезавёртывания не все ключи открываются новым ключом: $RW"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "R" "verify шифрования после перезавёртывания не прошёл"
ok "R (ключи данных завёрнуты новым ключом; данные читаются)"

echo; echo "################ ВОРОТА P: убрать старый ключ из .env.production ################"
echo "Что произойдёт: DATA_KEK_PREVIOUS в .env.production становится пустым, backend пересоздаётся (30–60 секунд); скрипт проверяет, что ВСЁ открывается НОВЫМ ключом одним."
echo "  • Старый ключ после этого из сервера исчезает; он остаётся только у вас (менеджер паролей, бумага) — для старых бэкапов."
echo "Чтобы убрать старый ключ, введите ТОЧНО:  СТАРЫЙ КЛЮЧ УБРАТЬ ДА"
printf '> '
read -r ANSWER < "${ROTATE_TTY:-/dev/tty}" || fail "P" "нет терминала для подтверждения"
[ "$ANSWER" = "СТАРЫЙ КЛЮЧ УБРАТЬ ДА" ] || { echo; echo "Остановлено на воротах P (введено: '$ANSWER'). Ключи данных уже завёрнуты новым ключом; DATA_KEK_PREVIOUS ещё в $ENVF; повторный запуск продолжит с этого места."; exit 1; }
ok "P (подтверждено вами)"
CUR=$(getenvf DATA_KEK); VERNOW=$(getenvf DATA_KEK_VERSION); OLDK=$(getenvf DATA_KEK_PREVIOUS)
write_keys "$CUR" "$VERNOW" "" || fail "P" "не удалось записать $ENVF"
[ -z "$(getenvf DATA_KEK_PREVIOUS)" ] && [ "$(getenvf DATA_KEK)" = "$CUR" ] || fail "P" "после записи в $ENVF не те значения"
ROLLP="Вернуть старый ключ как предыдущий: в $ENVF строка DATA_KEK_PREVIOUS=<старый ключ из менеджера паролей, отпечаток $OLDFP>  и  docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml up -d --no-deps backend"
PC up -d --no-deps backend || fail "P" "up backend не удался. $ROLLP"
wait_healthy || { docker logs plan_estimate_backend --tail 40; fail "P" "backend не стал healthy. $ROLLP"; }
docker exec plan_estimate_backend python -m app.cli.rotate_keys verify || fail "P" "не все ключи данных открываются новым ключом ОДНИМ. $ROLLP"
docker exec plan_estimate_backend python -m app.cli.reencode_data verify > /dev/null || fail "P" "verify шифрования не прошёл с одним ключом. $ROLLP"
[ "$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.DATA_STRICT_READ).lower(), bool(s.DATA_KEK_PREVIOUS.get_secret_value()))")" = "true False" ] || fail "P" "в контейнере строгое чтение выключено или DATA_KEK_PREVIOUS не пуст. $ROLLP"
CFG=$(docker exec plan_estimate_backend python -c "from app.core.config import settings as s; print(str(s.CALENDAR_DISPATCHER_ENABLED).lower(), s.CALENDAR_WEB_APP_URL)")
[ "$CFG" = "$LOOP_ENV https://$DOMAIN" ] || fail "P" "настройки календаря в контейнере: '$CFG', ожидалось '$LOOP_ENV https://$DOMAIN'. $ROLLP"
AFTER=$(docker exec plan_estimate_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc '$Q'" | tr '\n' ' ')
[ "$AFTER" = "$BEFORE" ] || fail "P" "число строк изменилось: было $BEFORE стало $AFTER. $ROLLP"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "P" "health не ok. $ROLLP"
ok "P (всё открывается новым ключом одним; число строк то же)"

echo; echo "=============== ВСЁ PASS: ключ сервера заменён (версия $VERNOW, отпечаток $(fp "$CUR")), старый ключ ($OLDFP) убран с сервера ==============="
echo "Дальше (по порядку):"
echo "  1) закройте Telegram полностью, откройте Mini App: клиенты, объекты, «Faktury i zaliczki», документы — как раньше;"
echo "  2) бэкап под текущую голову: cd ~/apps/plan_-_estimate && BACKUP_BRANCH=backlog-client-encryption BACKUP_HEAD=<голова> bash ~/backup_a9.sh  (в НОВОЙ сессии) — он уже содержит ключи данных под НОВЫМ ключом;"
echo "  3) сохраните НОВЫЙ ключ (менеджер паролей + бумага) и ПОМЕТЬТЕ старый «выведен из работы, версия $((VERNOW-1))» — НЕ удаляйте: старые бэкапы открываются только им;"
echo "  4) удалите с VM файлы с ключами:  shred -u $NEWF $SAVED  (в них лежат новый и старый ключи);"
echo "  5) приёмка: «принимаем EN-3a»."
)
