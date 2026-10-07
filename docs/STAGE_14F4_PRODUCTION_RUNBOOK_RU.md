# Stage 14F.4 — production: миграция `0034_finding_lineage`, backend 14F.1–14F.3, frontend

Порядок и правила — как в `STAGE_14E7_PRODUCTION_RUNBOOK_RU.md` и разделе 69b `PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md`. Каждый шаг ждёт вашего явного «да»; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне. «ВОРОТА» = стоп до вашего ответа.

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }   # в каждом новом сеансе SSH
```

## 1. Что выкладывается

| Часть | Изменение | Риск |
|---|---|---|
| **Миграция `0034_finding_lineage`** | `inspection_findings.lineage_id` UUID: добавить NULL → детерминированный backfill (один UUID на группу `(осмотр, вопрос, ключ замечания)`, пустой вопрос — тоже значение) → `SET NOT NULL` → индекс `ix_inspection_findings_lineage_id` | см. «ВОРОТА M» |
| Backend (9 файлов приложения) | 14F.1 сверка замечаний (линия), 14F.2 контексты INSPECTION / FINDING, 14F.3 `site_only` и счётчики по вопросам | низкий: аддитивно, существующие маршруты сохраняют ответ (только добавлены поля) |
| Frontend | кнопки фото в осмотре (шапка, вопросы, замечания), `site_only` в общем списке объекта | низкий |
| Compose / Caddy / Dockerfile / зависимости | **без изменений с прошлой выкладки backend (`4d4707a`)** — проверяется A1 | — |

## 2. Шаги

### A0 — только чтение (состояние production)
```bash
git status --short; git branch --show-current; git log --oneline -1
PC ps
docker inspect -f '{{.Name}}  {{.Image}}  {{.Created}}' plan_estimate_backend plan_estimate_frontend plan_estimate_caddy plan_estimate_postgres
docker exec plan_estimate_backend alembic current
curl -fsS https://plan-estimate.pl/api/health; echo
df -h / | tail -1
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from inspection_findings; select count(distinct (inspection_id, question_id, finding_key)) from inspection_findings;"'
```
**PASS:** дерево чистое, ветка `stage-14`; 4 контейнера `Up`/healthy; `alembic current` = `0033_photo_capture_source`; health ok; свободно ≥ 5 ГБ. Последние две цифры — число замечаний и число будущих линий (ожидается небольшое).

### A1 — что изменилось (только чтение, без `pull`)
```bash
git fetch origin stage-14
git diff --stat HEAD origin/stage-14 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/entrypoint.sh backend/requirements.txt frontend/package.json
git diff --stat HEAD origin/stage-14 -- backend/alembic | tail -3
```
**PASS:** первая команда пуста (деплойные файлы не менялись); во второй только `0034_finding_lineage.py`.

### A2 — бэкап перед выкладкой *(рекомендую)* → ждёт «да, A2»
Миграция меняет схему, фото на production есть (6 штук), поэтому **рекомендую** один прогон `db-dump` + `upload` + `verify` существующими образами (голова `0033` — они собраны на A6b 14E.7): раздел 72.3, шаги 2–3, **перед** ними загрузить **оба** файла (`. backup.env; . upload.env`). **PASS:** `backup complete: run_id=… ready_count=6`, затем `upload complete`, `verify ok`.

### A3 — получить код → ждёт «да, A3»
```bash
git pull --ff-only origin stage-14
git log --oneline -3
```
**PASS:** fast-forward; верхний коммит = `origin/stage-14` (`9ec1704` или новее из-за docs).

### A4 — конфигурация и сборка (старый production работает) → ждёт «да, A4»
```bash
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-14f4
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-14f4
PC build backend frontend 2>&1 | tail -n 15
```
**PASS:** `CONFIG-OK`; обе сборки без ошибок; контейнеры по-прежнему `Up`. *Ничего ещё не применено.*

### M0 — голова нового образа (только чтение) → ждёт «да, M0»
```bash
docker run --rm --entrypoint alembic plan-estimate-backend:latest heads
docker run --rm --entrypoint sh plan-estimate-backend:latest -c 'sed -n 1,40p /app/alembic/versions/0034_finding_lineage.py | head -30'
```
**PASS:** `0034_finding_lineage (head)`; файл миграции из нового образа совпадает с репозиторием. (Голову спрашиваем у **нового** образа; старый контейнер показал бы `0033`.)

### ВОРОТА M — миграция → ждёт вашего «да, миграция»
Перед ответом вы получите письменную оценку (см. раздел 3 ниже).

### A5 — применить backend (entrypoint сам выполнит `alembic upgrade head`)
```bash
PC up -d --no-deps backend
docker exec plan_estimate_backend alembic current
docker exec plan_estimate_backend alembic heads
docker logs plan_estimate_backend --tail 40
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*), count(lineage_id), count(distinct lineage_id) from inspection_findings;"'
```
**PASS:** `current` = `heads` = `0034_finding_lineage`; в логах нет ошибок; health ok; `count` = `count(lineage_id)` (нет NULL), число линий = числу групп из A0.

### A6 — применить frontend → ждёт «да, A6»
```bash
PC up -d --no-deps frontend
PC ps
curl -fsS https://plan-estimate.pl/api/health; echo
```
**PASS:** все контейнеры `Up`/healthy; health ok.

### A6b — пересобрать образы бэкапа под новую голову → ждёт «да, A6b»
Раздел 72.3 **шаг 1** (образы из `git archive` нового коммита), затем обновить `BACKUP_TOOL_COMMIT` в `~/backups/plan-estimate/db-backup/secrets/upload.env` на `git rev-parse origin/stage-14`. До этого шага бэкап падает безопасно (fail-closed, головы не совпадают).
**PASS:** оба образа собрались; `BACKUP_TOOL_COMMIT` = новый хеш; затем один прогон `db-dump` подтверждает работу (`ready_count=6`).

### A7 — cache-busting кнопки меню Telegram (раздел 71) → ждёт «да, A7»
`?v=<короткий хеш>`; токен подставляется внутри команды и не печатается. **PASS:** `getChatMenuButton` отдаёт новый URL.

### A8 — проверка на телефоне (владелец, 5–10 минут)
1. Откройте осмотр: в шапке кнопка фото; сделайте фото в шапке (общие фото осмотра).
2. У одного вопроса нажмите кнопку фото, снимите кадр: счётчик вопроса и шапки +1; подпись называет вопрос.
3. Завершите осмотр: у активных замечаний кнопка фото; снимите кадр на замечание.
4. «Wznów», измените ответ так, чтобы замечание исчезло, завершите; снова подтвердите: на новом замечании видны **и прежние фото** (счётчик линии).
5. Общий список фото объекта и фото помещений не содержат фото осмотров (они только в осмотре).
6. 320–412 px, PL и RU: кнопки не меньше 44 px, подписи не обрезаются.

## 3. Оценка миграции (для ВОРОТ M)

- **Что делает:** одна колонка + индекс на `inspection_findings`; значения создаются из существующих строк (UUID замечаний, флаги, даты не меняются).
- **Блокировки:** `ADD COLUMN` без значения по умолчанию мгновенный; `UPDATE` по строкам таблицы (десятки строк) — миллисекунды; `SET NOT NULL` проверяет таблицу целиком под коротким эксклюзивным замком — на такой таблице незаметно; `CREATE INDEX` — миллисекунды. Всё идёт **одной транзакцией** (DDL в PostgreSQL транзакционный): при любой ошибке откат целиком, `alembic_version` остаётся `0033`.
- **Обратимость:** `downgrade` удаляет индекс и колонку, ничего другого.
- **Совместимость со старым кодом:** старый backend колонку не знает и не может создавать замечания (INSERT без `lineage_id` нарушит NOT NULL). Поэтому **откат образа backend без отката миграции небезопасен для завершения осмотров**; правильный откат — сначала `alembic downgrade 0033_photo_capture_source` на новом образе, затем старый образ (раздел 4).
- **Бэкап:** рекомендую A2; после A5 образы бэкапа надо пересобрать (A6b).

## 4. Откат

| Ситуация | Действие |
|---|---|
| Backend не стартует после A5 | `docker logs plan_estimate_backend --tail 100`; миграция транзакционная — при ошибке версия осталась `0033`; вернуть образ: `docker tag plan-estimate-backend:pre-14f4 plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` |
| Backend работает, нужна отмена фич | **сначала** `docker exec plan_estimate_backend alembic downgrade 0033_photo_capture_source` (согласовать), потом образ `:pre-14f4` как выше. Теряется только `lineage_id` (его можно пересоздать повторным `upgrade`) |
| Сломался frontend | `docker tag plan-estimate-frontend:pre-14f4 plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| Бэкап после отката головы | работает только с образами, чья голова совпадает с БД |
| Любое сомнение с данными | остановиться, прислать вывод; `down -v` — **никогда** |

## 5. После завершения

Записываю в `docs/development-progress.md`: коммит, образы, ревизию БД, результаты A0–A8. Затем приёмка 14F и решение о следующем этапе. Уборка: теги `:pre-14f4` и более старые `:pre-…` — через неделю.
