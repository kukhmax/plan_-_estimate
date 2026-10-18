# Репетиция восстановления с ключом (EN-3c) — проверенные блоки команд (рабочая станция W)

Выполнено владельцем 2026-10-18 (PASS), порядок и результат — `docs/CLIENT_ENCRYPTION_RESTORE_REHEARSAL_RU.md`, раздел 6. Блоки ниже — ровно те, что прошли; повторять так же, по одному, присылая вывод. Все секреты вводятся скрытно (`read -rs … < /dev/tty`) и не попадают в историю, список процессов и сам блок.

Ключевые уроки (почему блоки именно такие):
* **`umask 022` при распаковке `git archive`**: с `umask 077` файлы в образе получают права `0600`, а образ работает от пользователя `65534` — `PermissionError: /app/app/__init__.py`.
* **Заглушки `RESTORE_S3_*`**: фаза `--phase database` бакет не трогает, но проверяет форму переменных (бакет с `drill` в имени и не боевой); реальных токенов R2 не нужно.
* **`-e DEBUG=false`**: у приложения `DEBUG=true` по умолчанию, команда иначе печатает сотни строк SQL (без параметров и значений).
* **Запуск от своего пользователя** (`--user "$(id -u):$(id -g)"`): защита требует, чтобы владелец файла age-ключа совпадал с пользователем процесса.
* **Конфиг OCI с проверкой отпечатка**: скрипт считает отпечаток файла ключа и отказывает, если он не равен значению из консоли.
* Бэкап до ротации ключа сервера открывается только вместе со старым ключом (`-e DATA_KEK_PREVIOUS`).

Переменные (`~/pe-rehearsal/env.sh`, пишет шаг 2): `REPO COMMIT WORK RUN BK UP NET PG_IMAGE RESTORE_DB`, позже `OCI_NAMESPACE OCI_CFG_DIR`.

## Шаг 1 — факты (read-only)
На VM: `ls -1t ~/backups/plan-estimate/db-backup/data/encrypted | head -5` (нужен свежий `run_id` с `*.published.json` в `…/evidence`). На W: `docker --version`, права файла age-ключа (`-rw-------`), чекаут репозитория (у владельца: `~/Projects/plan_estimate`), нет остатков `pe-rehearsal*`.

## Шаг 2 — образы из `git archive` (umask 022!)
```bash
bash <<'EOF2'
set -euo pipefail
umask 077
REPO=""
for d in "$HOME/Projects/plan_estimate" "$HOME/apps/plan_-_estimate" "$HOME/plan_-_estimate"; do [ -d "$d/.git" ] && { REPO="$d"; break; }; done
[ -n "$REPO" ] || { echo "FAIL: нет чекаута репозитория"; exit 1; }
cd "$REPO"; git fetch -q origin backlog-client-encryption
COMMIT=$(git rev-parse origin/backlog-client-encryption)
git cat-file -e "$COMMIT:backend/app/cli/restore_key_check.py" || { echo "FAIL: в коммите нет restore_key_check"; exit 1; }
WORK="$HOME/pe-rehearsal"; [ ! -e "$WORK" ] || { echo "FAIL: $WORK уже существует"; exit 1; }
mkdir -m 700 "$WORK" "$WORK/secrets" "$WORK/out"
printf 'export REPO=%q\nexport COMMIT=%s\nexport WORK=%q\nexport RUN=<run_id>\nexport BK=pe-rehearsal-backup:local\nexport UP=pe-rehearsal-upload:local\nexport NET=pe-rehearsal\nexport PG_IMAGE=postgres:16-alpine\nexport RESTORE_DB=pe_restore_scratch_rehearsal\n' "$REPO" "$COMMIT" "$WORK" > "$WORK/env.sh"
B=$(mktemp -d "$WORK/build.XXXXXX")
( umask 022; git archive --format=tar "$COMMIT" backend | tar -x --no-same-owner -C "$B" )
stat -c '%a %n' "$B/backend/app/__init__.py" "$B/backend/app"      # ожидается 644 / 755
docker build -q -f "$B/backend/Dockerfile.backup" -t pe-rehearsal-backup:local "$B/backend"
docker build -q -f "$B/backend/Dockerfile.uploader" --build-arg BACKUP_IMAGE=pe-rehearsal-backup:local -t pe-rehearsal-upload:local "$B/backend"
rm -r "$B"
docker run --rm --entrypoint python pe-rehearsal-upload:local -c "import app.cli.restore_key_check, app.backup.restore_command, oci; print('restore_key_check, restore, oci: OK')"
EOF2
```
(В `env.sh` вместо `<run_id>` подставьте номер запуска.)

## Шаг 3 — scratch-PostgreSQL без внешних секретов
Сеть `pe-rehearsal` без опубликованных портов; контейнер `pe-rehearsal-scratch-pg` (`postgres:16-alpine`, суперпользователь `plan_estimate`, как в P7: чтобы `OWNER TO` из дампа разрешались; имя хоста содержит `scratch`); база `pe_restore_scratch_rehearsal` (`TEMPLATE template0`); в `~/pe-rehearsal/secrets` (0600): `pg_pw` (40 hex из `/dev/urandom`), `pgpass-restore` (`pe-rehearsal-scratch-pg:5432:<db>:plan_estimate:<pw>`), `restore-s3.env` (заглушки `RESTORE_S3_ENDPOINT_URL=https://unused.example.invalid`, `RESTORE_S3_BUCKET=pe-rehearsal-drill-unused`, `RESTORE_S3_REGION=auto`, `RESTORE_S3_ACCESS_KEY_ID=unused`, `RESTORE_S3_SECRET_ACCESS_KEY=unused`), `check.env` (`DATABASE_URL=postgresql+asyncpg://plan_estimate:<pw>@pe-rehearsal-scratch-pg:5432/<db>`, `ENVIRONMENT=development`, `APP_ENV=development`, **`DEBUG=false`**). PASS: `accepting connections`, база есть, 0 таблиц, портов наружу нет.

## Шаг 4 — OCI: конфиг с проверкой отпечатка
В консоли Oracle: `plan-estimate-restore-operator` → API keys → Generate API key pair → приватный ключ (`…pem` без `_public`) → `~/pe-rehearsal/secrets/oci-key.pem` (0600). Скрипт спрашивает через `read … < /dev/tty` user, tenancy, region, fingerprint, namespace (namespace — `BACKUP_OCI_NAMESPACE` из `…/db-backup/secrets/upload.env` на VM), проверяет форму, **считает `openssl rsa -pubout -outform DER | openssl md5 -c` файла ключа и отказывает при расхождении**, переносит ключ в `secrets/oci/key.pem`, пишет `secrets/oci/config` (`[DEFAULT]`, `key_file=/run/oci/key.pem`) и дописывает `OCI_NAMESPACE` / `OCI_CFG_DIR` в `env.sh`.

## Шаг 5 — восстановление
```bash
docker run --rm --network "$NET" --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --read-only --tmpfs /tmp:rw,exec,size=768m -e HOME=/tmp \
  -e PGHOST=pe-rehearsal-scratch-pg -e PGPORT=5432 -e PGDATABASE="$RESTORE_DB" -e PGUSER=plan_estimate -e PGSSLMODE=disable -e PGPASSFILE=/run/secrets/pgpass \
  -e BACKUP_OCI_NAMESPACE="$OCI_NAMESPACE" -e BACKUP_OCI_BUCKET=plan-estimate-backup-prod -e BACKUP_OCI_REGION=eu-frankfurt-1 \
  --env-file "$WORK/secrets/restore-s3.env" \
  -v "$WORK/secrets/pgpass-restore":/run/secrets/pgpass:ro -v ~/.local/share/plan-estimate/age/backup-identity.txt:/run/age/identity.key:ro \
  -v "$OCI_CFG_DIR":/run/oci:ro -v "$WORK/out":/out \
  "$UP" restore --phase database --run-id "$RUN" --identity-file /run/age/identity.key --scratch-dir /tmp \
  --report-file /out/restore-database-report.json --oci-config /run/oci/config \
  --allowed-host pe-rehearsal-scratch-pg --forbidden-bucket plan-estimate-media-prod
```
PASS: `restore ok … phase=database`, `exit=0`, отчёт `ok: true`, `matches_repository_head: true`. Затем read-only SELECT-ы: `alembic_version`, число таблиц, строки основных таблиц, «открытых фамилий 0».

## Шаги 6–8 — проверка ключом
Один и тот же блок; меняется только источник ключа. Ключ вводится `read -rs -p … DATA_KEK < /dev/tty`, пробелы вырезаются (`${DATA_KEK//[[:space:]]/}`), `export DATA_KEK`, затем:
```bash
docker run --rm --network "$NET" --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --read-only --tmpfs /tmp:rw,size=256m -e HOME=/tmp -e DEBUG=false \
  --env-file "$WORK/secrets/check.env" -e DATA_KEK \
  --entrypoint python "$UP" -m app.cli.restore_key_check
unset DATA_KEK
```
* **6 — копия из менеджера паролей:** PASS, отпечаток = боевой.
* **7 — копия с бумаги (набрать вручную):** PASS, отпечаток = боевой. Опечатка при наборе даёт другой отпечаток и `FAIL (DATA_KEYS_DO_NOT_OPEN_WITH_THIS_KEY)`; найти место без показа ключей — блок сравнения двух копий, печатающий только позиции расхождений (длины, номера позиций, «лишний / пропущенный знак», перестановка соседних, пары-двойники `0/O`, `1/l/I`).
* **8 — случайный ключ** (`DATA_KEK=$(openssl rand -base64 32)`, не печатается): FAIL, `open with neither: N`, `exit=3`.

## Шаг 9 — сверка и уборка
* Сверка (read-only) на VM: `docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "set default_transaction_read_only=on; select (select count(*) from users), (select count(*) from clients), (select count(*) from projects), (select count(*) from project_payments), (select count(*) from issued_documents), (select count(*) from contracts), (select count(*) from data_keys), (select count(*) from photo_assets)"'` — сравнить с восстановленной базой; разницу объясняют записи после времени бэкапа.
* **Отозвать API-ключ restore-пользователя в консоли Oracle** и убедиться (пока конфиг не стёрт), что вход не принимается: `oci.object_storage.ObjectStorageClient(cfg).get_namespace()` → `status 401 code NotAuthenticated` (любой другой статус — ключ ещё действует).
* На W: сохранить отчёт `restore-database-report.json` (без секретов), `docker rm -f pe-rehearsal-scratch-pg`, `docker network rm pe-rehearsal`, `docker rmi pe-rehearsal-*:local`, `shred -u` файлов в `secrets/` и `key.pem`, `rm -rf ~/pe-rehearsal`. Проверить: контейнеров и образов `pe-rehearsal*` нет.
