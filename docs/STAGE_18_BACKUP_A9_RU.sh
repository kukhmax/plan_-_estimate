#!/usr/bin/env bash
# Stage 18 — A9: полный бэкап ПЕРЕД релизом Stage 18 (миграции 0054 и 0055): образы бэкапа под голову 0053, db-dump → upload → verify (раздел 72.3 runbook).
# Останавливается на первом непройденном условии и пишет, что делать. Секреты не печатает (upload.env — только хеш BACKUP_TOOL_COMMIT).
# Запуск (в НОВОЙ SSH-сессии на VM; после него сессию ЗАКРЫТЬ и не запускать в ней docker compose, раздел 72.5):
#   cd ~/apps/plan_-_estimate && git fetch -q origin stage-17 && git show origin/stage-17:docs/STAGE_18_BACKUP_A9_RU.sh > ~/backup_a9.sh && bash ~/backup_a9.sh
# Файл лежит в stage-18: git fetch -q origin stage-18 && git show origin/stage-18:docs/STAGE_18_BACKUP_A9_RU.sh > ~/backup_a9.sh && bash ~/backup_a9.sh
#
# ДО выкладки Stage 18 (по умолчанию): код stage-17, голова миграций 0053 — бэкап перед миграциями 0054 и 0055.
# ПОСЛЕ выкладки Stage 18 (образы бэкапа под новую голову, иначе бэкап остановится безопасно):
#   BACKUP_BRANCH=stage-18 BACKUP_HEAD=0055_project_notes bash ~/backup_a9.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
BRANCH="${BACKUP_BRANCH:-stage-17}"          # код, из которого строятся образы бэкапа
HEAD_NAME="${BACKUP_HEAD:-0053_downtime_episodes}"   # голова миграций: образы бэкапа обязаны совпасть с базой
R="$HOME/backups/plan-estimate/db-backup"
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше (без содержимого secrets/)."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }

echo "################ B0: проверка перед бэкапом (только чтение) ################"
# BACKUP_BRANCH, BACKUP_HEAD и (необязательно) BACKUP_COMMIT — параметры самого скрипта (их передают в команде запуска): они не считаются «лишними»; любые другие MEDIA_S3* / BACKUP_* — считаются
[ "$(env | grep '^MEDIA_S3\|^BACKUP_' | grep -vc '^BACKUP_BRANCH=\|^BACKUP_HEAD=\|^BACKUP_COMMIT=')" = "0" ] || fail "B0" "В оболочке лишние переменные MEDIA_S3/BACKUP_. Откройте НОВУЮ SSH-сессию."
for f in backup.env upload.env pgpass; do [ -r "$R/secrets/$f" ] || fail "B0" "нет файла $R/secrets/$f"; done
for f in backup.env upload.env pgpass; do
  [ "$(stat -c %a "$R/secrets/$f")" = "600" ] || fail "B0" "права $R/secrets/$f не 600"
done
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "B0" "health недоступен"
has '"status":"ok"' "$H" || fail "B0" "health не ok: $H"
AL=$(docker exec plan_estimate_backend alembic current 2>/dev/null)
has "$HEAD_NAME" "$AL" || fail "B0" "alembic current не $HEAD_NAME: $AL (до выкладки Stage 18 нужен 0053_downtime_episodes, после — BACKUP_BRANCH=stage-18 BACKUP_HEAD=0055_project_notes)"
git fetch -q origin "$BRANCH" || fail "B0" "git fetch origin $BRANCH не удался"
if [ -n "${BACKUP_COMMIT:-}" ]; then
  # необязательно (V2-5): ветка уже ушла вперёд по миграциям, а база ещё нет (бэкап ПЕРЕД выкладкой миграции): образы строятся из указанного коммита ИЗ ИСТОРИИ ветки
  COMMIT=$(git rev-parse --verify "${BACKUP_COMMIT}^{commit}" 2>/dev/null) || fail "B0" "нет такого коммита: $BACKUP_COMMIT"
  git merge-base --is-ancestor "$COMMIT" "origin/$BRANCH" || fail "B0" "коммит $BACKUP_COMMIT не из истории origin/$BRANCH"
else
  COMMIT=$(git rev-parse "origin/$BRANCH")
fi
VERS=$(git ls-tree -r --name-only "$COMMIT" backend/alembic/versions | grep -E 'versions/[0-9]{4}_.*\.py$' | sort)
LAST=$(tail -n 1 <<<"$VERS" | sed -E 's#.*/([^/]+)\.py#\1#')
[ "$LAST" = "$HEAD_NAME" ] || fail "B0" "последняя миграция в ${BACKUP_COMMIT:-origin/$BRANCH} — $LAST, а база на $HEAD_NAME: образы будут под другую голову (если ветка ушла вперёд по миграциям: BACKUP_COMMIT=<коммит с головой $HEAD_NAME>)"
docker network inspect plan-estimate_internal >/dev/null 2>&1 || fail "B0" "нет сети plan-estimate_internal"
docker network inspect pe-upload >/dev/null 2>&1 || fail "B0" "нет сети pe-upload"
LEFT=$(docker ps -a --format '{{.Names}}' | grep '^pe-backup-prod-' || true)
[ -z "$LEFT" ] || fail "B0" "остались контейнеры бэкапа: $LEFT (docker rm -f их и повторить)"
[ -z "$(ls -A "$R/data/work" 2>/dev/null)" ] || fail "B0" "каталог $R/data/work не пуст (остатки прошлого запуска): $(ls -A "$R/data/work" | head -5)"
# evidence/ хранит <run_id>.published.json прошлых опубликованных запусков: по ним загрузчик находит предыдущий запуск — они должны быть. Чужое там быть не должно.
EV_OK='^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\.(published|upload-failed-[0-9]{8}T[0-9]{6}Z)\.json$'
STRAY=$(ls -A "$R/data/evidence" 2>/dev/null | grep -Ev "$EV_OK" || true)
[ -z "$STRAY" ] || fail "B0" "в $R/data/evidence лежит файл не того вида (ожидаются только <run_id>.published.json и <run_id>.upload-failed-<UTC>.json — записи самого загрузчика): $(head -5 <<<"$STRAY")"
NFAILED=$(ls -A "$R/data/evidence" 2>/dev/null | grep -c 'upload-failed' || true)
echo "evidence/: опубликованных запусков $(ls -A "$R/data/evidence" 2>/dev/null | grep -c 'published' || true), записей о прежних неудачных загрузках: ${NFAILED} (справочно, не мешают)"
FREE=$(df --output=avail -BG / | tail -1 | tr -dc '0-9'); [ "$FREE" -ge 5 ] || fail "B0" "Свободно ${FREE} ГБ (< 5)"
PREV=$(ls -1 "$R/data/encrypted" 2>/dev/null | tail -1 || true)
echo "коммит инструмента бэкапа: ${COMMIT:0:12} (origin/$BRANCH); последний прежний запуск: ${PREV:-нет}"
ok "B0"

echo; echo "################ B1: образы бэкапа из git archive коммита ${COMMIT:0:12} ################"
D=$(mktemp -d "$HOME/pe-build.XXXXXX")
git archive --format=tar "$COMMIT" backend docker-compose.prod.yml | tar -x --no-same-owner -C "$D" || { rm -r "$D"; fail "B1" "git archive не удался"; }
docker build -q -f "$D/backend/Dockerfile.backup" -t plan-estimate-backup:local "$D/backend" > /tmp/backup-build.log 2>&1 || { tail -n 20 /tmp/backup-build.log; rm -r "$D"; fail "B1" "сборка plan-estimate-backup:local не удалась"; }
docker build -q -f "$D/backend/Dockerfile.uploader" --build-arg BACKUP_IMAGE=plan-estimate-backup:local -t plan-estimate-backup-upload:local "$D/backend" >> /tmp/backup-build.log 2>&1 || { tail -n 20 /tmp/backup-build.log; rm -r "$D"; fail "B1" "сборка plan-estimate-backup-upload:local не удалась"; }
rm -r "$D"
if grep -q '^BACKUP_TOOL_COMMIT=' "$R/secrets/upload.env"; then
  sed -i "s/^BACKUP_TOOL_COMMIT=.*/BACKUP_TOOL_COMMIT=$COMMIT/" "$R/secrets/upload.env" || fail "B1" "не удалось обновить BACKUP_TOOL_COMMIT"
else
  fail "B1" "в upload.env нет строки BACKUP_TOOL_COMMIT= (формат файла другой): впишите её вручную, значение $COMMIT"
fi
[ "$(grep '^BACKUP_TOOL_COMMIT=' "$R/secrets/upload.env")" = "BACKUP_TOOL_COMMIT=$COMMIT" ] || fail "B1" "BACKUP_TOOL_COMMIT не совпал с коммитом"
ok "B1 (образы собраны, BACKUP_TOOL_COMMIT=${COMMIT:0:12})"

echo; echo "################ B2: db-dump (локальный зашифрованный бэкап) ################"
set -a; . "$R/secrets/backup.env"; set +a
OUT=$(docker run --name pe-backup-prod-dump --rm --init --stop-timeout 45 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 512m --cpus 0.5 --pids-limit 64 \
  --user "$BACKUP_UID:$BACKUP_GID" --network plan-estimate_internal --tmpfs /tmp:size=16m \
  -v "$R/data:/backup" -v "$R/secrets/pgpass:/run/secrets/pgpass:ro" \
  -e PGHOST="$BACKUP_PGHOST" -e PGPORT="$BACKUP_PGPORT" -e PGDATABASE="$BACKUP_PGDATABASE" \
  -e PGUSER="$BACKUP_PGUSER" -e PGSSLMODE="$BACKUP_PGSSLMODE" -e PGPASSFILE=/run/secrets/pgpass \
  -e BACKUP_AGE_RECIPIENTS="$BACKUP_AGE_RECIPIENTS" plan-estimate-backup:local db-dump 2>&1); RC=$?
tail -n 6 <<<"$OUT"
[ "$RC" = "0" ] || fail "B2" "db-dump завершился кодом $RC (0 = успех; 3 = блокировка занята; 4 = остатки в work/)"
RUN=$(sed -n 's/.*backup complete: run_id=\([^ ]*\) ready_count=\([0-9]*\).*/\1/p' <<<"$OUT" | tail -1)
READY=$(sed -n 's/.*backup complete: run_id=\([^ ]*\) ready_count=\([0-9]*\).*/\2/p' <<<"$OUT" | tail -1)
[ -n "$RUN" ] || fail "B2" "в выводе нет строки «backup complete: run_id=… ready_count=…»"
[ "$(ls -1 "$R/data/encrypted/$RUN" | wc -l)" = "4" ] || fail "B2" "в encrypted/$RUN не четыре файла: $(ls -1 "$R/data/encrypted/$RUN")"
[ "$(find "$R/data/encrypted/$RUN" -type f ! -perm 600 | wc -l)" = "0" ] || fail "B2" "у файлов в encrypted/$RUN права не 0600"
[ -z "$(ls -A "$R/data/work")" ] || fail "B2" "после db-dump не пуст work/"
STRAY=$(ls -A "$R/data/evidence" | grep -Ev "$EV_OK" || true); [ -z "$STRAY" ] || fail "B2" "после db-dump в evidence/ появился файл не того вида: $(head -5 <<<"$STRAY")"
ok "B2 (run_id=$RUN, ready_count=$READY)"

echo; echo "################ B3: upload в Oracle (необратимо: загрузчик не перезаписывает и не удаляет) ################"
set -a; . "$R/secrets/backup.env"; . "$R/secrets/upload.env"; set +a
export MEDIA_S3_ENDPOINT_URL="$BACKUP_UPLOAD_S3_ENDPOINT_URL" MEDIA_S3_BUCKET="$BACKUP_UPLOAD_S3_BUCKET" MEDIA_S3_REGION="$BACKUP_UPLOAD_S3_REGION" \
  MEDIA_S3_ACCESS_KEY_ID="$BACKUP_UPLOAD_S3_ACCESS_KEY_ID" MEDIA_S3_SECRET_ACCESS_KEY="$BACKUP_UPLOAD_S3_SECRET_ACCESS_KEY" MEDIA_STORAGE_NAME="$BACKUP_UPLOAD_SOURCE_NAME"
OUT=$(docker run --name pe-backup-prod-upload --rm --init --stop-timeout 45 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 512m --cpus 0.5 --pids-limit 64 \
  --user "$BACKUP_UID:$BACKUP_GID" --network pe-upload --tmpfs /tmp:size=256m -v "$R/data:/backup" \
  -e MEDIA_S3_ENDPOINT_URL -e MEDIA_S3_BUCKET -e MEDIA_S3_REGION -e MEDIA_S3_ACCESS_KEY_ID -e MEDIA_S3_SECRET_ACCESS_KEY -e MEDIA_STORAGE_NAME \
  -e BACKUP_OCI_NAMESPACE -e BACKUP_OCI_BUCKET -e BACKUP_OCI_REGION -e BACKUP_TOOL_COMMIT -e BACKUP_AGE_RECIPIENTS \
  plan-estimate-backup-upload:local upload --environment production --allow-production 2>&1); RC=$?
tail -n 4 <<<"$OUT"
[ "$RC" = "0" ] || fail "B3" "upload завершился кодом $RC (8 = нечего загружать; 10 = запуск запечатан, evidence не записано — повторить ТУ ЖЕ команду)"
has 'upload complete' "$OUT" || fail "B3" "нет строки «upload complete»"
ok "B3"

echo; echo "################ B4: verify (полная проверка опубликованного запуска) ################"
OUT=$(docker run --rm --init --read-only --cap-drop ALL --security-opt no-new-privileges:true --user "$BACKUP_UID:$BACKUP_GID" \
  --network pe-upload --tmpfs /tmp:size=256m -e BACKUP_OCI_NAMESPACE -e BACKUP_OCI_BUCKET -e BACKUP_OCI_REGION -e BACKUP_AGE_RECIPIENTS \
  plan-estimate-backup-upload:local verify --run-id "$RUN" --mode full 2>&1); RC=$?
tail -n 4 <<<"$OUT"
[ "$RC" = "0" ] || fail "B4" "verify завершился кодом $RC"
has 'verify ok' "$OUT" || fail "B4" "нет строки «verify ok»"
has 'mode=full' "$OUT" || fail "B4" "verify не в режиме full"
ok "B4"

echo
echo "################ ИТОГ ################"
echo "A9 PASS: run_id=$RUN ready_count=$READY, upload и verify full — ok. Голова: $HEAD_NAME. Коммит инструмента: ${COMMIT:0:12}."
echo "ВАЖНО: ЗАКРОЙТЕ эту SSH-сессию и больше не запускайте в ней docker compose (раздел 72.5)."
echo "После выкладки Stage 18 (миграции 0054 и 0055) бэкап надо повторить с BACKUP_BRANCH=stage-18 BACKUP_HEAD=0055_project_notes (образы под новую голову)."
)
