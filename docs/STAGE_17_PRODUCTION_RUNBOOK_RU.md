# Stage 17 — production: база знаний (экран, поиск, «Основание» у рисков, фраз и документов) — без миграции

Порядок и правила — как в `STAGE_16K_PRODUCTION_RUNBOOK_RU.md` (backend + frontend без миграции). Каждый шаг ждёт вашего явного «да»; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне, секреты в чат не вставлять. **Все шаги — в чистой новой SSH-сессии** (первая строка каждого блока проверяет, что лишних переменных 0).

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
```

## 1. Что выкладывается (production `744c3b8` → `origin/stage-17`)

MVP без юриста (решение владельца): **всё содержимое — черновики** (`DRAFT`). Их видите только вы, они помечены «Wersja robocza / Черновик» и **не попадают ни в один документ клиенту** (тест `test_stage17f_knowledge_guards`: ни один модуль документов, договора и протоколов не читает базу знаний).

| Часть | Изменение | Риск |
|---|---|---|
| Миграция | **нет**; `alembic current` остаётся `0053_downtime_episodes` | — |
| Backend | новый **только читающий** `/api/knowledge/*` (7 маршрутов, нужен токен владельца); каталог — файлы `backend/app/domain/knowledge/catalog/*.json` внутри образа; **при старте приложение проверяет каталог и не запускается на неверном файле** (проверено тестами на реальных файлах) | низкий |
| Содержимое | 3 источника (KC, ustawa o prawach konsumenta, RODO), 24 статьи (ключевые моменты на польском, пояснение по-русски, ссылка на источник), 51 связь с рисками, фразами клиенту и документами; ситуаций пока нет | низкий (данные — файлы, не база) |
| Frontend | шестой пункт меню «База знаний»; блок «Основание (n)» у карточки риска, у фразы клиенту и над экранами «Договор и протоколы»; ссылка на источник открывается через Telegram `openLink` | средний: меняются карточки рисков и фраз (добавляется свёрнутая строка), остальное не затронуто |
| Compose / Caddy / Dockerfile / зависимости / `app/backup` / миграции | **без изменений** — проверяется A0 | — |
| Образы бэкапа | пересборка по-прежнему **нужна** (шаг A9 основного runbook Stage 16, голова `0053`); к Stage 17 отношения не имеет | средний при пропуске |

Откат: миграции нет; образы `:pre-17` возвращаются в любой момент (раздел 4).

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
git fetch origin stage-17
git merge-base --is-ancestor HEAD origin/stage-17 && echo "HEAD — предок origin/stage-17: ДА" || echo "HEAD — предок origin/stage-17: НЕТ"
echo "--- что придёт (коммиты) ---"; git log --oneline HEAD..origin/stage-17
echo "--- инфраструктура (должно быть пусто) ---"
git diff --name-only HEAD origin/stage-17 -- docker-compose.prod.yml Caddyfile backend/Dockerfile backend/Dockerfile.backup backend/Dockerfile.uploader backend/entrypoint.sh backend/requirements.txt backend/requirements-oci.txt frontend/package.json frontend/package-lock.json frontend/Dockerfile.prod backend/app/backup backend/alembic
echo "--- файлы backend/app (ожидаем 6 + 5 файлов каталога) ---"
git diff --name-only HEAD origin/stage-17 -- backend/app
```
**PASS:** `0` лишних переменных; дерево чистое, ветка `stage-16`, коммит `744c3b8` или более поздний документальный (`4924ba1`, `2a09212`); 4 контейнера `Up`/healthy; `alembic current` = `0053_downtime_episodes`; health ok; свободно ≥ 5 ГБ; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`; «предок: ДА»; блок «инфраструктура» **пуст**; в `backend/app` ровно: `api/v1/endpoints/knowledge.py`, `domain/knowledge/__init__.py`, `domain/knowledge/catalog.py`, `domain/knowledge/search.py`, `main.py`, `schemas/knowledge.py` и пять файлов `domain/knowledge/catalog/*.json`.

### A1 — получить код → «да, A1»
VM стоит на ветке `stage-16`, а `stage-17` отходит от неё (через `main`), поэтому создаём локальную ветку `stage-17` (рабочее дерево чистое, ничего не теряется):
```bash
git switch -c stage-17 --track origin/stage-17
git log --oneline -1
git status --short
```
**PASS:** ветка `stage-17`; верхний коммит = `origin/stage-17` (хеш назову после A0); дерево чистое.

### A2 — конфигурация и сборка (старый production работает) → «да, A2»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)"  plan-estimate-backend:pre-17
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_frontend)" plan-estimate-frontend:pre-17
PC build backend frontend 2>&1 | tail -n 8
PC ps
df -h / | tail -1
```
**PASS:** `0` лишних переменных; `CONFIG-OK`; обе сборки без ошибок (зависимости из кэша); контейнеры `Up`; свободно ≥ 4 ГБ.

### A3 — применить backend → «да, A3» (миграции нет: ВОРОТА M не нужны)
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps backend
sleep 25
docker exec plan_estimate_backend alembic current
docker logs plan_estimate_backend --tail 20
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_backend python -c "from app.domain.knowledge.catalog import load_knowledge_catalog as l; c=l(); print('каталог:', len(c.sources), 'источников,', len(c.entries), 'статей,', len(c.links), 'связей,', len(c.situations), 'ситуаций; версия', c.meta.version)"
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET); print('доставка документов:', s.DOCUMENT_DELIVERY)"
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from clients; select count(*) from projects; select count(*) from issued_documents; select count(*) from photo_attachments;"'
```
**PASS:** `0` лишних переменных; `current` = `0053_downtime_episodes` (в логе **нет** `Running upgrade`); нет ошибок, видно `Application startup complete`; health ok; **«каталог: 3 источников, 24 статей, 51 связей, 0 ситуаций; версия 2»**; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`; доставка `telegram`; четыре числа (клиенты, объекты, документы, фото) те же, что до выкладки.

Если backend не стартует и в логе `KnowledgeCatalogError` — каталог на сервере не тот, что проверен тестами: **не чинить на месте**, откат по разделу 4 и пришлите вывод лога.

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
1. **Меню.** В меню шесть пунктов: Клиенты, Объекты, Прайс, Архив, Отправленные документы, **База знаний**; «Аккаунт» внизу.
2. **База знаний — список.** Заголовок, оранжевая строка «Wersje robocze … / Черновики …», поле поиска, «Тем: 24» (без блока «Найти по ситуации» — ситуаций нет). Каждая строка: название, источник (`KC, t.j. Dz.U. 2026 poz. 795 · art. …`) и метка «Wersja robocza / Черновик».
3. **Поиск.** `rekoj` → находит статьи о rękojmi (польские буквы без диакритики); `odstap` / `отказ` / `art. 640` → находят нужные; несуществующее слово → «Brak wyników / Ничего не найдено»; очистка поля возвращает 24.
4. **Карточка.** Нажмите «Brak współdziałania zamawiającego» (art. 640): ключевые моменты на польском; в русском интерфейсе — ещё «Пояснение для исполнителя»; «Gdzie w aplikacji» с местами договора; свёрнутая строка «Do sprawdzenia przez prawnika (1)»; **в самом конце — «Otwórz źródło / Открыть источник»**: ссылка открывается в браузере телефона (страница ISAP / EUR-Lex), приложение не закрывается. «← Wróć» и кнопка Telegram «Назад» возвращают к списку.
5. **«Основание» у риска.** Объект → помещение → обследование (завершённое) → риски: у карточки риска свёрнутая строка «Podstawa (2)» (или (1)); раскрывается список статей; нажатие на статью раскрывает ключевые моменты и кнопку источника.
6. **«Основание» у фразы клиенту.** Блок «Co powiedzieć klientowi»: то же у каждой фразы.
7. **«Основание» на экранах документов.** Объект → Договор и протоколы: **Договор** (12), **Протокол решений** (2), **Простой** (3) — строка «Podstawa (n)» над формой; на экранах Стороны, Смежные работы, Передача помещений, Скрытые работы, Приёмка строки нет (связей для них нет — это нормально).
8. **Ничего не сломалось.** Клиенты, объекты, помещения, фото, сметы, договор и протоколы, документы — на месте и работают как раньше; кнопка Telegram «Назад» ведёт по шагам.
9. **320 / 390 / 412 px, PL и RU.** Кнопки ≥ 44 px (кроме маленького переключателя языка), длинные названия не режутся, горизонтальной прокрутки нет.
10. **Документ клиенту.** Выдайте любой PDF (например, смету или договор): в нём **нет** ни слова из базы знаний (черновики не печатаются).

Присылайте результат пунктами «1 — PASS / FAIL (что увидели)».

## 3. Оценка риска
- **Данные:** миграции нет; новое на backend — только чтение файлов каталога и ответы без записи. Данные объектов, документов и фото не меняются.
- **Старт backend:** приложение проверяет каталог при запуске. Файлы проверены тестами (реальный каталог по HTTP, 3 теста охраны, 71 тест базы знаний); ошибка возможна только если на сервере окажется другая версия файлов — A3 печатает счётчики каталога.
- **Совместимость:** новый frontend со старым backend не используется (порядок A3 → A4); блок «Основание» молча не показывается, если backend не отвечает.
- **Содержание:** юридическое содержание — черновик, подготовленный ИИ (`docs/STAGE_17C_AI_LEGAL_RESEARCH_RU.md`); для MVP его видите только вы, с пометкой, и оно не уходит клиентам. Использовать его как основание для решений — на ваш риск до проверки юристом.

## 4. Откат
| Ситуация | Действие |
|---|---|
| Backend не стартует после A3 | `docker logs plan_estimate_backend --tail 100`; `docker tag plan-estimate-backend:pre-17 plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` |
| Сломался или не понравился frontend | `docker tag plan-estimate-frontend:pre-17 plan-estimate-frontend:latest && PC up -d --no-deps --no-build frontend` |
| Любое сомнение с данными | остановиться, прислать вывод; `down -v` — **никогда** |

## 5. После выкладки
Остаются: **A9** Stage 16 (пересборка образов бэкапа под голову `0053` и полный бэкап — пока он не сделан, бэкап останавливается безопасно), переключение VM на `main` (отдельное «да»; `stage-17` сначала сливается в `main` вашим «да»), и работа с юристом (проверка статей и связей, ситуации) — по вашему слову.

## 6. Дополнение 17E.1 + 17C.3 — исправления после первого просмотра и техническое основание рисков (backend + frontend, без миграции)

Что меняется: понятные подписи «Где в приложении» (§ договора и названия документов вместо кодов), один блок «Основание» на весь список рисков и на список фраз, исправленные названия статей (art. 634, 557, 639, 635), у источника — действующая редакция. Плюс 17C.3: у каждой карточки риска — своё «Техническое основание» (нормы, ITB, технические карты производителей), под списком рисков — одно правовое основание. Каталог — версия 4. Шаги — как выше, коротко:
1. **A0** (чтение): `git fetch origin stage-17; git log --oneline HEAD..origin/stage-17`; блок «инфраструктура» из A0 — **пуст**; в `backend/app` меняются только `api/v1/endpoints/knowledge.py`, `schemas/knowledge.py` и файлы каталога.
2. **A1 + A2:** `git pull --ff-only origin stage-17`; теги `pre-17e1` на работающие образы; `PC build backend frontend`.
3. **A3:** `PC up -d --no-deps backend`; проверка из A3 выше, строка каталога: **«13 источников, 34 статей, 51 связей, 0 ситуаций; версия 4»**; числа 2 / 2 / 5 / 11 (или больше, если вы что-то добавили).
4. **A4:** `PC up -d --no-deps frontend`.
5. **A5:** кнопка меню Telegram с новым хешем; полностью закрыть и открыть Telegram.
6. **Проверка:** карточка art. 640 — «Где в приложении»: «Договор § 10 п. 5 — …», «Документ: Уведомление о простое», без кодов; источник: «Kodeks cywilny — ustawa z 23 kwietnia 1964 r. (obowiązuje…)» и «Действующий текст: KC, t.j. Dz.U. 2026 poz. 795»; риски обследования — **один** блок «Правовое основание по этим рискам» под списком (только законы), у каждой карточки риска — «Техническое основание (n)» со своими нормами и картами (например, у влажности — карта Atlas: ниже 3% CM; у неровностей — PN-70/B-10100: 3 мм на рейке 2 м); фразы — один блок «Почему это нужно сказать клиенту»; в базе знаний 34 темы.
7. **Откат:** `docker tag plan-estimate-backend:pre-17e1 plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` (и так же frontend).

### Выкладка одной командой (по просьбе владельца)
Шаги 1–5 выше собраны в скрипт `docs/STAGE_17_DEPLOY_17E1_17C3_RU.sh` с автоматическими остановками (G0 проверка, G1 код и сборка, G2 backend, G3 frontend, G4 кнопка Telegram). Первый же непройденный критерий печатает `FAIL`, точную команду отката и останавливает выкладку. Скрипт проверен на заглушках (успех, неверный каталог, посторонний файл в `backend/app`). Запуск:
```bash
cd ~/apps/plan_-_estimate && git fetch -q origin stage-17 && git show origin/stage-17:docs/STAGE_17_DEPLOY_17E1_17C3_RU.sh > ~/deploy17.sh && bash ~/deploy17.sh
```
