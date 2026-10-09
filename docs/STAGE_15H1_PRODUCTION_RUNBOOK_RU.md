# Stage 15H.1 — production: понятная блокировка фотоотчёта и переходы к месту исправления (без миграции)

Порядок и правила — как в `STAGE_14H5_PRODUCTION_RUNBOOK_RU.md` (выкладка backend + frontend без миграции) и `STAGE_15H_PRODUCTION_RUNBOOK_RU.md`. Каждый шаг ждёт вашего явного «да»; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне, секреты в чат не вставлять. **Все шаги — в чистой новой SSH-сессии** (бэкапа здесь нет; первая строка каждого блока проверяет, что лишних переменных 0).

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
```

## 1. Что выкладывается (production `aad9e67` → `origin/stage-15`)

Найдено вами при проверке 15H на телефоне: фотоотчёт отказывал с «Brak ceny w kosztorysie», а экран не говорил, что делать; после «Dodaj do prac» предупреждение оставалось. **Причина:** принятие рекомендации (контракт Stage 11) только дописывает работу в план стены и **не меняет смету**, а цена берётся из текущей сметы. Чтобы работа получила цену, смету нужно обновить (черновик) или создать её новую версию (утверждённая).

| Часть | Изменение | Риск |
|---|---|---|
| Миграция | **нет**; `alembic current` остаётся `0038_issued_documents` | — |
| Backend (4 файла приложения) | `api/v1/endpoints/documents.py`, `domain/documents/photo_report_document.py`, `domain/services/recommended_work_read_model.py`, `schemas/issued_document.py`: сводка фотоотчёта дополнительно отдаёт структурированный список работ без цены с причиной (`unpriced_items`) и текущую смету (`estimate_id`, `estimate_status`). Только чтение; старые поля сохранены | низкий |
| Frontend | карточки работ без цены на языке интерфейса, нажатие ведёт в осмотр с рекомендацией или в текущую смету; понятная подсказка по каждой причине; карточка «PDF-документы» остаётся открытой при возврате | низкий |
| Compose / Caddy / Dockerfile / зависимости / `app/backup` | **без изменений** — проверяется A0 | — |
| Образы бэкапа | **пересборка не нужна** (голова миграций `0038` и код бэкапа не меняются) | — |

Откат: миграции нет; образы `:pre-15h1` возвращаются в любой момент (раздел 4).

## 2. Шаги

### A0 — только чтение → «да, A0»
```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
git status --short; git branch --show-current; git log --oneline -1
PC ps
docker exec plan_estimate_backend alembic current
curl -fsS https://plan-estimate.pl/api/health; echo
df -h / | tail -1
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET)"
git fetch origin stage-15
git merge-base --is-ancestor HEAD origin/stage-15 && echo "HEAD — предок origin/stage-15: ДА" || echo "HEAD — предок origin/stage-15: НЕТ"
echo "--- инфраструктура (должно быть пусто) ---"
git diff --name-only HEAD origin/stage-15 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile backend/app/backup backend/alembic
echo "--- файлы backend/app (ожидаем 4) ---"
git diff --name-only HEAD origin/stage-15 -- backend/app
```
**PASS:** `0` лишних переменных; дерево чистое, ветка `stage-15`, коммит `aad9e67` (или более поздний документальный); 4 контейнера `Up`/healthy; `alembic current` = `0038_issued_documents`; health ok; свободно ≥ 5 ГБ; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`; «предок: ДА»; блок «инфраструктура» **пуст**; в `backend/app` ровно 4 файла: `api/v1/endpoints/documents.py`, `domain/documents/photo_report_document.py`, `domain/services/recommended_work_read_model.py`, `schemas/issued_document.py`.

### A1 — получить код → «да, A1»
```bash
git pull --ff-only origin stage-15
git log --oneline -1
git status --short
```
**PASS:** fast-forward; верхний коммит = `origin/stage-15` (хеш назову после A0); дерево чистое.

### A2 — конфигурация и сборка (старый production работает) → «да, A2»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-15h1
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-15h1
PC build backend frontend 2>&1 | tail -n 8
PC ps
df -h / | tail -1
```
**PASS:** `0` лишних переменных; `CONFIG-OK`; обе сборки без ошибок (слои с системными библиотеками и зависимостями берутся из кэша — сборка заметно быстрее, чем на 15H); контейнеры `Up`; свободно ≥ 4 ГБ.

### A3 — применить backend → «да, A3» (миграции нет: ВОРОТА M не нужны)
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps backend
sleep 25
docker exec plan_estimate_backend alembic current
docker logs plan_estimate_backend --tail 20
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET); print('endpoint:', str(s.MEDIA_S3_ENDPOINT_URL).split('//')[-1].split('.')[-3:]); print('доставка документов:', s.DOCUMENT_DELIVERY)"
```
**PASS:** `0` лишних переменных; `current` = `0038_issued_documents` (в логе **нет** строки `Running upgrade`); нет ошибок, видно `Application startup complete`; health ok; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`, endpoint `r2`, `cloudflarestorage`, `com`; доставка `telegram`.

### A4 — применить frontend → «да, A4»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps frontend
PC ps
curl -fsS https://plan-estimate.pl/api/health; echo
```
**PASS:** `0` лишних переменных; все контейнеры `Up`/healthy; health ok.

### A5 — кнопка меню Telegram → «да, A5»
```bash
V=$(git rev-parse --short HEAD); echo "версия кнопки: $V"
set -a; source .env.production; set +a
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setChatMenuButton" -H "Content-Type: application/json" \
  -d "{\"menu_button\": {\"type\": \"web_app\", \"text\": \"Plan & Estimate\", \"web_app\": {\"url\": \"https://plan-estimate.pl/?v=${V}\"}}}"; echo
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChatMenuButton" | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1…#'; echo
unset TELEGRAM_BOT_TOKEN V
```
**PASS:** оба ответа `"ok":true`, `?v=` = новый хеш. Затем полностью закройте Telegram и откройте Mini App заново.

### A6 — проверка на телефоне (владелец, ~10 минут; PL, затем RU)
На объекте с рекомендациями осмотра, у которых нет цены в смете (как на вашем тестовом объекте):
1. Откройте «Dokumenty PDF» → «Pokaż». Предупреждение **читаемо и на языке интерфейса**: заголовок «Raport nie zostanie wysłany…», у каждой работы — название (например, «Naprawa rys i pęknięć…» / по-русски «Ремонт трещин…»), место («Salon › Ściana 1» / «… › Стена 1», без «Wall 1»), одно предложение, что делать, и строка действия.
2. Работа, **ждущая решения**: нажмите на карточку — откроется её осмотр (Back возвращает в список осмотров, затем в комнату). Добавьте рекомендацию в работы («Dodaj do prac», в приложении сразу пишет «Kosztorys nie został jeszcze zaktualizowany»), вернитесь на объект: карточка «PDF-документы» **осталась открытой**, а у этой работы теперь написано, что она добавлена в работы, но её нет в смете, и подсказка: смета в черновике — «zaktualizuj kosztorys», смета утверждена — «utwórz jego nową wersję».
3. Нажмите на такую карточку — откроется **текущая смета**. Если она утверждена: создайте новую версию («Utwórz nową wersję»); если черновик: «Aktualizuj kosztorys». Убедитесь, что строка работы появилась с ценой; для отчёта достаточно черновика (в отчёте помечено «wersja robocza»), но на документ для клиента смету лучше утвердить.
4. Вернитесь на объект: карточки этой работы больше нет; когда не осталось ни одной, красного предупреждения нет и «Wyślij PDF» активна.
5. «Wyślij PDF»: отчёт приходит в чат с ботом, в нём блок «Rekomendowane prace dodatkowe» с ценой из сметы; в «Wysłane dokumenty» новая запись.
6. Отклонение («Odrzuć») по-прежнему убирает работу из предупреждения.
7. 320–412 px, PL и RU: карточки не режутся, нажимаются целиком (≥ 44 px), горизонтальной прокрутки нет.

## 3. Оценка риска
- **Данные:** миграции нет, записей не меняется; новые поля сводки — только чтение (те же выборки, что и раньше; число запросов не растёт).
- **Совместимость:** старые поля сводки сохранены; новый frontend со старым backend не используется (порядок A3 → A4); старый frontend (в кэше WebView) игнорирует новые поля.
- **Хранилище:** ключ приложения не меняется.

## 4. Откат
| Ситуация | Действие |
|---|---|
| Backend не стартует после A3 | `docker logs plan_estimate_backend --tail 100`; `docker tag plan-estimate-backend:pre-15h1 plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` |
| Сломался frontend | `docker tag plan-estimate-frontend:pre-15h1 plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| Любое сомнение с данными | остановиться, прислать вывод; `down -v` — **никогда** |

## 5. После выкладки
Остаются шаги 15H, которые ещё не выполнены: замер памяти и времени на настоящем отчёте (A9) и бэкап под голову `0038` с пересборкой образов (A10) — по `STAGE_15H_PRODUCTION_RUNBOOK_RU.md`.
