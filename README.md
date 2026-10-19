# Plan & Estimate

**Plan & Estimate** — Telegram Mini App для подрядчика, который делает отделочные и ремонтные работы в Польше (*prace wykończeniowe i remontowe*). Приложение рассчитано на работу **с телефона прямо на объекте**: замерил помещение, осмотрел основание, сфотографировал дефекты, собрал смету, оформил договор и акты — не возвращаясь к компьютеру.

Интерфейс — на польском и русском (PL/RU), клиентские документы (смета, договор, протоколы) — по умолчанию на польском.

> **Статус на 2026-10-19.** Дорожная карта **Stage 0–20 выполнена** и работает на боевом сервере; Stage 20 (общий аудит MVP, [план](docs/STAGE_20_MVP_AUDIT_PLAN_RU.md), [отчёт](docs/STAGE_20_AUDIT_REPORT_RU.md)) принят владельцем. Дальше — только бэклог (раздел 6).

---

## Содержание

1. [Что умеет приложение](#1-что-умеет-приложение)
2. [Как это устроено внутри](#2-как-это-устроено-внутри)
3. [Как всё настроить](#3-как-всё-настроить)
4. [Шифрование данных клиентов: как это работает](#4-шифрование-данных-клиентов-как-это-работает)
5. [Фото и резервные копии](#5-фото-и-резервные-копии)
6. [Что запланировано, но не сделано](#6-что-запланировано-но-не-сделано)
7. [Разработка и проверка](#7-разработка-и-проверка)
8. [Правила работы над проектом](#8-правила-работы-над-проектом)
9. [Приложение: модель оценки (Model wyceny, PL)](#model-wyceny-jakość-powierzchni-współczynniki-i-dopłaty)

---

## 1. Что умеет приложение

Центральная сущность — **объект** (*Obiekt*): квартира или дом, где идёт ремонт. К объекту привязано всё остальное: помещения, поверхности, замеры, осмотры, фото, смета, договор, протоколы, расчёты, заметки.

```text
Клиент
  └─ Объект
       ├─ Помещения → Поверхности (стена / пол / потолок) → Проёмы (двери, окна, откосы)
       │     ├─ Осмотр основания → Находки → Риски → Рекомендованные работы
       │     └─ План работ поверхности (основание, класс качества, работы из прайса)
       ├─ Смета (kosztorys)
       ├─ Договор и протоколы
       ├─ Фото, заметки, расчёты (деньги от клиента, расходы на материалы)
       └─ Календарь и напоминания
```

Главное меню приложения: **Клиенты, Объекты, Прайс, Архив, Отправленные документы, База знаний, Календарь**.

### Клиенты и объекты
* Частные лица и фирмы: телефон, e-mail, NIP, адрес, Telegram. Создание, правка, архив и восстановление, поиск.
* Объект (статус, адрес, описание, привязка к клиенту), **представители сторон** (кто от заказчика вправе принимать работы и подписывать протоколы), **заметки объекта**, реестр **смежных работ** (другие подрядчики на объекте).
* Карточка клиента показывает его объекты; карточка объекта — «плитки» разделов.

### Замеры
* Помещения с метрическими размерами (ввод в сантиметрах, прямоугольники на полу и потолке), стены, пол, потолок.
* Проёмы (двери, окна) вычитаются из площади стены; **откосы** (*ościeża*) считаются отдельно и не меняют площадь стены.
* Составные площади пола/потолка (основной прямоугольник ± добавки).

### Осмотр основания, риски и «что сказать клиенту»
* Версионированный чек-лист осмотра основания (влажность, трещины, неровности, состояние основания и т. д.).
* **Детерминированный движок рисков** (без ИИ): по ответам чек-листа выдаёт риск, его серьёзность, объяснение, меры и формулировку для исключения гарантии.
* **Помощник общения с клиентом**: готовые фразы PL/RU, чтобы грамотно объяснить риск, задержку или допработы.
* Из риска получается **рекомендованная работа**; в план она попадает только после вашего явного «Dodaj do prac».

### План работ, прайс и коэффициенты
* **План работ** поверхности: основание, целевое качество (S1–S4 для штукатурки/бетона, Q1–Q4 для гипсокартона) и упорядоченный список работ из прайса.
* **Прайс (Cennik)** — ваш редактируемый каталог цен. Рыночные цены показываются только для справки и никогда сами не подменяют вашу цену. Пустая цена («Уточняется») и ноль — разные вещи.
* **Коэффициенты** — явные поправки к цене труда при нестандартных условиях (высота, доступ, сложность, организация работ). Правила — в [приложении](#model-wyceny-jakość-powierzchni-współczynniki-i-dopłaty).
* **Технологические процессы**: шаблоны последовательности работ с технологическими перерывами (сушка).

### Смета (kosztorys)
* Собирается из планов работ; итоги считает сервер. Можно переопределить количество и цену строки, добавить ручные строки.
* Смета — **снимок**, а не «живой» вид: изменения в планах не переписывают её сами. Чтобы обновить черновик, вы сознательно нажимаете «Sprawdź zmiany» → «Aktualizuj kosztorys».
* «Finalizuj kosztorys» фиксирует неизменяемую версию (`FINAL`); новая редакция — новый черновик.

### Фото
* Съёмка встроенной камерой (серия кадров, зум) или из галереи; фото привязываются к объекту, помещению, поверхности, проёму, находке осмотра или выполненной работе.
* **Маркеры и контуры дефектов** на фото (кроме фото чеков и фактур).
* Фото осмотра попадают в PDF-отчёт.

### Документы (PDF)
* Смета, отчёт об осмотре с фото, **договор** (с приложениями), **протокол передачи помещения**, **протокол приёмки скрытых работ**, **протокол приёмки работ**, **протокол информирования и решений заказчика**, **уведомление и протокол простоя**, технологическая карта, производственный план.
* Каждый документ сначала проходит «ворота» (проверка полноты данных), потом **замораживается** снимком и записывается в журнал; отправляется вам в Telegram-чат. Есть печатные рабочие версии с пустыми полями.
* Профиль исполнителя (ваши реквизиты) подставляется во все документы.

### Расчёты по объекту
* «Деньги от клиента» (авансы и оплаты) и «расходы на материалы» с фото чеков и фактур. Названия, номера, контрагенты и заметки хранятся зашифрованными.

### Доступ
* Закрытая регистрация: список допущенных аккаунтов Telegram, заявки новых людей, блокировка, ваш контакт для отказанных (подробно — [раздел 3.2](#32-telegram-бот)).

### Календарь и напоминания
* Рабочие дни и польские праздники, плановые даты этапов, события, кнопка «Напомнить». Напоминания приходят вам в чат Telegram (цикл доставки внутри backend; включается переменной `CALENDAR_DISPATCHER_ENABLED=true`).

### База знаний
* Справочник по польскому праву и техническим условиям: записи, источники, ситуации. **Содержимое — черновик для ваших глаз**, без проверки юристом; клиентам не показывается.

### Работа без связи
* На стройке часто нет сигнала. Приложение хранит на телефоне кэш чтения и очередь изменений: осмотр, статус работ, заметки и фото можно вносить без связи, они синхронизируются при появлении сети («Synchronizacja»). **Холодный старт без сети не поддерживается** — приложение нужно открыть хотя бы раз при связи, лучше нажать «Przygotuj do pracy offline».

### Архив и удаление
* Вкладки архива: объекты, помещения, фото, записи расчётов, **договоры и протоколы**. Архивное можно восстановить или **удалить окончательно** (с проверкой связей — например, нельзя удалить договор, пока на него ссылаются живые протоколы). Журнал отправленных документов при этом сохраняется.

### Принципы интерфейса
**Сначала телефон** (320–480 px; основной контроль — 390 и 412 px): крупные кнопки, никакой горизонтальной прокрутки, вертикальные списки, длинные русские подписи не ломают вёрстку. Отдельного «десктопного» интерфейса нет.

---

## 2. Как это устроено внутри

| Часть | Технологии | Что делает |
|---|---|---|
| **Frontend** (`frontend/`) | React 18, TypeScript (strict), Vite, Tailwind CSS, Vitest | Мини-приложение внутри Telegram; все тексты в `locales/pl.json` и `ru.json` |
| **Backend** (`backend/`) | Python 3.12, FastAPI, SQLAlchemy 2 (async), Pydantic v2, Alembic | API, расчёты, правила рисков, документы, шифрование |
| **База данных** | PostgreSQL 16 | Все данные; схема — только через миграции Alembic (последняя — `0065_access_control`) |
| **Бот** (`bot/`) | aiogram 3 | Кнопка запуска Mini App в чате |
| **Файлы фото** | Cloudflare R2 (приватный бакет) | Сами фотографии; в базе — только ссылки на них |
| **Резервные копии** | `age` + Oracle Object Storage | Независимая зашифрованная копия базы и фото |
| **Сервер** | Oracle Cloud VM (ARM), Docker Compose, Caddy, Cloudflare перед доменом | Боевой запуск |

Правила, которые держатся во всём коде:
* **Тонкие маршруты**: API только проверяет вход и вызывает сервис; бизнес-логика — в `backend/app/domain`.
* **Никаких цен и юридических текстов во frontend**: цены берутся из прайса на сервере, правовое содержание — из базы знаний.
* **Риски, гарантийные исключения — только по правилам**, без ИИ.
* **Все ключи — UUID, время — UTC**, каждая корневая запись принадлежит владельцу (`owner_id`): система уже готова к нескольким подрядчикам, данные изолированы.
* **Секреты — только переменные окружения**, в репозиторий не попадают.

```text
Telegram (телефон)
   │ HTTPS
   ▼
Cloudflare ──► Caddy ──┬─► frontend (nginx, готовая сборка)
                       └─► backend (FastAPI) ──► PostgreSQL   (внутренняя сеть Docker)
                                    │
                                    ├─► Cloudflare R2: файлы фото
                                    └─► (по команде) бэкап → Oracle Object Storage
```

Наружу публикует порты только Caddy (80/443); PostgreSQL и backend живут во внутренней сети.

---

## 3. Как всё настроить

### 3.1. Локальная разработка

Требуется: Python 3.12, Node 20+, PostgreSQL 16 (или любая доступная вам база). Docker для обычной разработки **не используется** — только нативные инструменты (Docker нужен лишь для боевого сервера и стека `docker-compose.yml`, если вы решите его поднять).

```bash
cp .env.example .env            # локальные значения; настоящие секреты — только в .env, он не попадает в Git

# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head            # применить миграции
uvicorn app.main:app --reload --port 8000

# frontend (в другом терминале)
npm --prefix frontend install
npm --prefix frontend run dev   # http://localhost:5173
```

Документация API: `http://localhost:8000/docs`; проверка здоровья: `http://localhost:8000/api/health`.

Для входа в браузере без Telegram в разработке включено `MOCK_TELEGRAM_AUTH=true` (backend) и `VITE_DEV_MOCK_AUTH=true` (frontend). **В боевой среде эти режимы включать нельзя.**

Без `DATA_KEK` в разработке шифрование выключено (данные пишутся открытым текстом, чтобы тесты были простыми). Проверить шифрованный режим:

```bash
export DATA_KEK=$(openssl rand -base64 32)
EN_TEST_ENCRYPTION=1 backend/.venv/bin/pytest backend/tests
```

### 3.2. Telegram-бот

1. В Telegram у **@BotFather** создайте бота, получите токен (`TELEGRAM_BOT_TOKEN`).
2. Там же настройте кнопку меню / Mini App на адрес вашего сайта (`https://<ваш-домен>`).
3. Токен используется backend'ом для **проверки подписи** `initData` (HMAC-SHA256): без верной подписи в API не войти.

#### Кто может войти (закрытая регистрация)

Приложение можно закрыть: тогда входят только аккаунты Telegram из **списка доступа**.

* Новый человек открывает бота и видит «Brak dostępu» (нет доступа) и **ваш контакт**; его заявка попадает на экран **«Dostęp»** (пункт меню, виден только администратору) в раздел «Oczekujące» (ожидают).
* Вы нажимаете «Dopuść» (допустить) или «Zablokuj» (заблокировать). Блокировка действует **сразу**, даже если у человека уже есть открытая сессия.
* На том же экране — переключатель «Rejestracja zamknięta» (закрыта / открыта) и поле вашего контакта.
* При выкладке этой функции все нынешние пользователи автоматически допускаются, **самый ранний (вы) становится администратором**, регистрация закрывается.
* Если регистрация открыта (переключатель выключен), любой, кто откроет бота, получает собственный изолированный аккаунт и попадает в список как «Aktywne»; заблокированные не входят в любом режиме.
* Администратор меняется **только командой на сервере** (не с экрана) — чтобы доступ нельзя было отобрать у владельца через приложение.

Команды (внутри backend, печатают только числа):

| Команда | Для чего |
|---|---|
| `python -m app.cli.access status` | Закрыта ли регистрация; сколько аккаунтов допущено / ожидает / заблокировано; сколько администраторов |
| `python -m app.cli.access set-admin --telegram-id N` | Назначить администратором другой аккаунт (исправление, если администратором стал не тот) |
| `python -m app.cli.access open` / `close` | Аварийно открыть или снова закрыть регистрацию, если вы не можете войти |

Подробно — [`docs/CLOSED_REGISTRATION_RUNBOOK_RU.md`](docs/CLOSED_REGISTRATION_RUNBOOK_RU.md).

### 3.3. Боевой сервер (кратко)

Полная пошаговая инструкция — [`docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md`](docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md). Суть:

1. **VM** (Oracle Cloud, Ubuntu ARM) с Docker; домен в Cloudflare; сертификат Origin для Caddy.
2. Репозиторий клонируется на сервер; создаётся файл **`.env.production`** (права `600`, **не в Git**) по образцу [`.env.production.example`](.env.production.example).
3. Запуск: `docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build`. Backend при старте сам применяет миграции (`alembic upgrade head`).
4. Проверка: `https://<домен>/api/health`.
5. Обновления выкладываются **скриптами `docs/*_DEPLOY_RU.sh`** — каждый останавливается при любом отклонении и спрашивает явное подтверждение фразой; перед миграциями делается проверенная резервная копия.

Что нужно в `.env.production`:

| Группа | Переменные | Заметка |
|---|---|---|
| Приложение | `ENVIRONMENT=production`, `APP_ENV=production`, `DEBUG=false`, `APP_DOMAIN` | |
| База | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_AUTH_MAX_AGE_SECONDS`, `MOCK_TELEGRAM_AUTH=false` | токен — от @BotFather; **backend в боевой среде не запустится**, если токен не похож на настоящий, а также при `MOCK_TELEGRAM_AUTH=true` или `DEBUG=true` |
| Сессии | `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` | секрет — `openssl rand -hex 32`; **backend в боевой среде не запустится**, если секрет короче 32 знаков или похож на заглушку из примера |
| **Шифрование** | **`DATA_KEK`**, `DATA_KEK_VERSION`, `DATA_KEK_PREVIOUS`, `DATA_STRICT_READ` | **без `DATA_KEK` backend в боевой среде не стартует**; подробно — [раздел 4](#4-шифрование-данных-клиентов-как-это-работает) |
| Фото | `MEDIA_STORAGE_BACKEND`, `MEDIA_S3_*`, `PHOTO_UPLOADS_ENABLED`, `PHOTO_*` | загрузка выключена, пока вы её не включите |
| Календарь | `CALENDAR_DISPATCHER_ENABLED` | отправка напоминаний включается явно |

Ключи R2 и Oracle, пароли и токены хранятся **только на сервере**.

---

## 4. Шифрование данных клиентов: как это работает

### 4.1. Зачем и от чего защищает

В базе лежат персональные данные ваших клиентов: имена, телефоны, адреса, договоры, платежи. По закону (RODO/GDPR) их нужно защищать разумными мерами. Главный риск — **утечка копии**: украденный дамп базы, копия диска, чужие руки на резервной копии в облаке.

Решение (его называют «V1»): **данные клиентов хранятся в базе в зашифрованном виде.** Тот, кто получил дамп или бэкап, видит строки вида `enc1:7f3a…:…` — без ключа это бессмысленный набор символов.

### 4.2. Простая картина: сейф и ключ от сейфа

* У каждого владельца есть **ключ данных** (DEK) — случайное число из 32 байт. Им шифруются значения (алгоритм AES-256-GCM: он ещё и замечает, если зашифрованное значение кто-то испортил).
* Сам ключ данных в базе лежит **только «запертым»** другим ключом — **ключом сервера** (`DATA_KEK`). Это как ключ от сейфа, лежащий внутри второго сейфа.
* `DATA_KEK` хранится **не в базе и не в репозитории**, а в файле `.env.production` на сервере — и ещё в **двух копиях вне сервера**: в вашем менеджере паролей и на бумаге.

Почему двухступенчато: чтобы менять ключ сервера **мгновенно**, не перешифровывая все данные (достаточно «перезапереть» один маленький ключ данных).

```text
 данные клиента  ──(ключ данных)──►  enc1:…   лежит в таблицах базы
 ключ данных     ──(ключ сервера)──► лежит в таблице data_keys «запертым»
 ключ сервера    ──────────────────► .env.production на сервере + менеджер паролей + бумага
```

### 4.3. Что зашифровано, а что нет

| Зашифровано | Не зашифровано |
|---|---|
| Клиент: имя, фамилия, фирма, телефон, e-mail, NIP, адрес, Telegram, заметки | Идентификаторы, статусы, даты |
| Объект: название, адрес, город, индекс, описание; представители (имя, телефон, e-mail); заметки объекта | Структура (помещения, поверхности), размеры и площади |
| Договоры, протоколы и журнал выданных документов (ответы, снимки, HTML) | Суммы смет, цены прайса, коэффициенты (серверу нужно их считать) |
| Расчёты: название, номер, контрагент, заметка | **Фотографии** (лежат в приватном бакете, отдаются по ссылкам на 5 минут) |
| | Пока открытым текстом (см. [бэклог](#6-что-запланировано-но-не-сделано)): заметки в осмотрах, подписи к фото, тексты ваших напоминаний, заметки о смежных работах |

Шифрование и расшифровка происходят **автоматически на уровне модели данных**: остальной код приложения видит обычные строки. Для пользователя ничего не меняется. Поиск клиентов работает по расшифрованному списку.

### 4.4. Что защищено — и что нет (честно)

**Защищает от:** утечки дампа базы, копии диска, чтения облачной резервной копии посторонними.

**Не защищает от:** того, кто получил доступ к **работающему серверу вместе с файлом `.env.production`** — ключ лежит рядом. И от захвата вашего аккаунта Telegram. Именно поэтому описан более строгий вариант «V2» ([раздел 6](#6-что-запланировано-но-не-сделано)); пока он не нужен, потому что вы сами администратор своего сервера.

### 4.5. Главное правило: потеряли ключ — потеряли данные

Ключ сервера **нельзя восстановить** ни из базы, ни из резервной копии. Поэтому:

1. Ключ создаётся **один раз**: `openssl rand -base64 32`.
2. Копии — в менеджере паролей **и на бумаге**, отдельно от резервных копий базы.
3. Копии сверяются по **отпечатку** (первые 8 знаков SHA-256 текста ключа; для боевого — `3c6e3287`). Команда `restore_key_check` печатает отпечаток, не показывая ключ.
4. Проверка прошла **живьём** (2026-10-18): резервная копия восстановлена на рабочей станции, открыта ключом из менеджера паролей и ключом с бумаги (первая попытка набрать бумажный ключ дала опечатку — поэтому бумажную копию проверяют именно набором), а случайный ключ ничего не открыл.

### 4.6. Как это настраивается

Переменные в `.env.production`:

| Переменная | Что это |
|---|---|
| `DATA_KEK` | Ключ сервера: base64 от 32 случайных байт. **Обязателен в боевой среде.** |
| `DATA_KEK_VERSION` | Номер поколения ключа сервера (1, 2, …) — нужен при ротации |
| `DATA_KEK_PREVIOUS` | **Только во время ротации**: старый ключ. Обычно пусто. |
| `DATA_STRICT_READ` | `true` — незашифрованное значение в зашифрованной колонке отклоняется (страховка). Включается после перекодировки старых данных |

Команды (выполняются внутри контейнера backend, печатают **только числа**, никогда значения или ключи):

| Команда | Для чего |
|---|---|
| `python -m app.cli.reencode_data report` / `verify` / `apply` | Перекодировать старые открытые значения в шифртекст; проверить, что открытых не осталось (61 колонка в 12 таблицах) |
| `python -m app.cli.rotate_keys status` / `rewrap` / `verify` / `new-key` | Сменить **ключ сервера** (мгновенно, данные не трогаются) |
| `python -m app.cli.rotate_data_keys start` / `reseal` / `retire` | Сменить **ключ данных** (данные перешифровываются пачками) |
| `python -m app.cli.restore_key_check` | Проверить на **восстановленной тренировочной базе**, что данный ключ открывает бэкап (выход 0 — открывает) |

Готовые сценарии (с проверками и подтверждением фразой): `docs/CLIENT_ENCRYPTION_*_DEPLOY_RU.sh`, `CLIENT_ENCRYPTION_KEK_ROTATION_RU.sh`, `CLIENT_ENCRYPTION_DEK_ROTATION_RU.sh`. Подробно — [`docs/CLIENT_ENCRYPTION_KEYS_RUNBOOK_RU.md`](docs/CLIENT_ENCRYPTION_KEYS_RUNBOOK_RU.md) (ключи и ротации) и [`docs/CLIENT_ENCRYPTION_RESTORE_REHEARSAL_RU.md`](docs/CLIENT_ENCRYPTION_RESTORE_REHEARSAL_RU.md) (репетиция восстановления, проверенные блоки команд — `…_COMMANDS_RU.md`).

**Ограничения, которые нужно знать:**
* Шифртекст привязан к «таблице.колонке», а не к конкретной строке: тот, кто может **записывать** в базу, теоретически способен переставить зашифрованное значение между строками одной колонки одного владельца. Для утечки базы на чтение это несущественно; ограничение записано в runbook.
* Старые бэкапы открываются ключом сервера, который действовал на момент бэкапа: **старый ключ после ротации сохраняется**.
* Откат версии программы безопасен, пока не записан шифртекст; откат миграции шифрования при наличии шифртекста отказывает.

---

## 5. Фото и резервные копии

* **Фото**: принимаются JPEG/PNG/WebP (до 25 МБ), из них делаются оригинал, средний размер (метаданные и GPS удаляются) и миниатюра; файлы лежат в приватном бакете **Cloudflare R2** и показываются по ссылкам, живущим 5 минут. Файлы не перезаписываются: «убрать» фото = архивировать (окончательное удаление — отдельная осознанная операция с проверками). Квота: предупреждение с 8 ГБ, мягкий предел 10 ГБ.
* **Резервные копии**: база выгружается и шифруется (`age`, ключ расшифровки — только на вашей рабочей станции), файлы фото копируются на второго провайдера (**Oracle Object Storage**). Каждый запуск проверяется; восстановление отрепетировано. Копия базы содержит шифртекст — для чтения нужны **и** ключ `age`, **и** `DATA_KEK`.
* Подробно простыми словами: [`docs/STAGE_14_PHOTOS_AND_BACKUP_EXPLAINED_RU.md`](docs/STAGE_14_PHOTOS_AND_BACKUP_EXPLAINED_RU.md).

---

## 6. Что запланировано, но не сделано

Полный список с обоснованиями — [`docs/CLIENT_DATA_ENCRYPTION_PLAN_RU.md`](docs/CLIENT_DATA_ENCRYPTION_PLAN_RU.md), раздел 11. Любой шаг начинается только по явному «да» владельца.

### Шифрование — следующие шаги
| Шаг | Что | Зачем / решение |
|---|---|---|
| **EN-4 («V2»)** | Ключ шифрования хранится **у владельца на телефоне**, а не на сервере; сервер видит данные только пока открыта сессия Mini App; фраза восстановления на бумаге | Защита от «прочитать данные может администратор сервера». **Отложено (решение 2026-10-18)**: пока вы сами администратор и единственный пользователь — выигрыш мал, а цена высока (напоминания бота без названий объектов, нужно открывать приложение после перезапуска сервера, потеря ключа и фразы = потеря данных). **Вернуться, когда на сервере появятся другие подрядчики** — тогда это способ честно сказать им «я не вижу ваших клиентов». V1 устроен так, что V2 — надстройка (ключ данных просто «перезапирается» другим ключом), перешифровка данных не нужна. |
| **EN-5** | Локальный кэш offline-режима на телефоне шифруется ключом устройства | Нужен вместе с V2; при утере телефона сейчас кэш защищён только блокировкой телефона |
| **EN-6** | Решение по шифрованию фото | Сейчас фото защищены приватным бакетом и короткими ссылками |
| Особо защищаемые клиенты | Выбор «шифровать этого клиента отдельным ключом» | Имеет смысл только вместе с V2 (иначе в V1 ключ один и тот же) |
| Шифрование остальных текстов | Заметки в осмотрах, подписи к фото, тексты ваших напоминаний, заметки о смежных работах | Небольшой шаг в духе EN-2b (нужно учесть, что текст напоминаний бот отправляет в чат) |
| Слепой индекс | Точный поиск по телефону/NIP среди тысяч записей | Нужен только при большом числе клиентов |
| Привязка шифртекста к строке | Вариант AAD «таблица.колонка.id» | Защита от подмены записью в базу; сложнее, пока не нужно |

### Мультиарендность и монетизация (на будущее)
Планируется дать доступ другим подрядчикам и, возможно, монетизировать. Основа есть (владелец у каждой корневой записи, изоляция данных, **закрытая регистрация** со списком доступа), но **до публичного запуска** нужно:
* приглашения по ссылке (сейчас администратор допускает людей вручную из списка заявок);
* лимиты и учёт хранилища фото на пользователя; тарифы и оплата;
* V2-шифрование (EN-4) и юридическая проверка (RODO: реестр операций, сроки хранения, договор поручения, политика конфиденциальности);
* отдельная политика восстановления данных пользователей и поддержки.

### Продукт
* **Stage 20** — полный аудит MVP и сквозной сценарий «от клиента до акта».
* Проверка базы знаний юристом (пока — черновик для владельца).
* Полный проход Stage 16 (договоры/протоколы) с полностью заполненными данными.
* Холодный старт приложения без связи (решение Stage 19: не поддерживается).
* Расширенные **доплаты** (ночная/выходная работа, минимальный заказ, леса) — сейчас ручной строкой в смете.
* Формат фото HEIC, при необходимости.
* Повторная отправка PDF из архива; серверный отказ от маркеров на фото чеков (сейчас скрыты только в интерфейсе).

---

## 7. Разработка и проверка

```bash
backend/.venv/bin/pytest backend/tests                       # тесты backend
npm --prefix frontend test -- --run                          # тесты frontend (Vitest)
frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit   # типы
npm --prefix frontend run build                              # сборка
git diff --check
```

Структура репозитория:

```text
.
├── backend/             # FastAPI, SQLAlchemy, Alembic, тесты (app/domain — логика, app/cli — команды обслуживания)
├── frontend/            # React, TypeScript, Vite, Tailwind, Vitest
├── bot/                 # aiogram-бот
├── docs/                # дорожная карта, архитектура этапов, runbook'и, скрипты выкладки
├── ops/                 # служебные файлы сервера
├── .agents/rules/       # правила архитектуры, домена, frontend/backend, Git
├── CLAUDE.md, GEMINI.md # инструкции для ИИ-помощника и постоянные правила проекта
├── docker-compose.yml           # локальный стек (опционально)
├── docker-compose.prod.yml      # боевой стек
└── Caddyfile                    # прокси и TLS
```

Статус по этапам, результаты тестов и история — [`docs/development-progress.md`](docs/development-progress.md).

## 8. Правила работы над проектом

* Работа идёт **этапами**; один логический этап — один коммит. Нумерация Stage 0–20 неизменна; задачи бэклога (шифрование, расчёты, архив) в неё не входят.
* Порядок: реализация → автоматические проверки → отчёт PASS/FAIL → коммит (только при PASS) → push (с одобрения владельца) → выкладка (владельцем, по шагам) → приёмка.
* Следующий этап не начинается без явного «да» владельца. Docker локально для разработки не запускается.

---

## Model wyceny: jakość powierzchni, współczynniki i dopłaty

System rozdziela cztery niezależne elementy wyceny:

1. **Standard jakości powierzchni** (`quality_target`: S1–S4, Q1–Q4 /
   PSG1–PSG4) — jaki efekt końcowy ma zostać osiągnięty.
2. **Operacje technologiczne** (PriceItems w planie prac) — co faktycznie
   trzeba wykonać, żeby ten efekt osiągnąć.
3. **Współczynniki ceny** (dla konkretnego wystąpienia planned work) — w
   jakich warunkach dana operacja jest wykonywana.
4. **Dopłaty i korekty komercyjne** (dla całego zlecenia) — warunki
   handlowe i koszty dotyczące całego zlecenia.

Nie należy zastępować dodatkowej operacji technologicznej współczynnikiem
procentowym.

### 1. Standard Wykończenia Powierzchni S1–S4

**Wewnętrzna klasyfikacja wykonawcy.**

S1–S4 jest wewnętrzną klasyfikacją wykonawcy dla powierzchni ciągłych,
np. tynków i betonu. Nie jest oznaczeniem klasy jakości według Polskiej
Normy ani żadnej innej normy.

S1 — Przygotowanie podstawowe
Powierzchnia przygotowana technicznie do kolejnej przewidzianej operacji.
Nie oznacza pełnego standardu powierzchni gotowej do malowania.

S2 — Standard malarski
Typowy standard powierzchni przygotowanej do zwykłego malowania
wnętrz farbą matową w normalnych warunkach użytkowych i przy świetle
rozproszonym.

S3 — Podwyższony standard wizualny
Podwyższona jednorodność wizualna dla bardziej wymagających wnętrz,
dużych jednolitych powierzchni lub bardziej wymagających warunków
oświetleniowych.

S4 — Indywidualnie uzgodniony standard premium
Standard dla powierzchni o szczególnych wymaganiach wizualnych,
uzgadnianych przed rozpoczęciem prac, w tym warunków oświetleniowych.

S1–S4 określa standard wykończenia powierzchni, a nie jej geometrię.
Nie określa pionu, poziomu, płaszczyzny ani kątów i nie przypisuje
żadnych tolerancji milimetrowych.

Geometria powierzchni jest oceniana i rozliczana oddzielnie.

S1–S4 NIE jest współczynnikiem ceny i nie ma domyślnego procentu.
Docelowo Stage 13 mapuje quality target na wymagane operacje
technologiczne / PriceItems.

Dla zabudowy gipsowo-kartonowej stosowane są oddzielnie poziomy
Q1–Q4 / PSG1–PSG4 — odrębny, branżowy system poziomów jakości. Nie należy
utożsamiać ich z wewnętrzną klasyfikacją S1–S4. Q1–Q4 / PSG1–PSG4 również
nie są współczynnikami ceny.

### 2. Cena bazowa

Cena PriceItem jest ceną bazową dla określonej operacji.

Cena bazowa powinna odpowiadać normalnym warunkom przyjętym przez
właściciela cennika.

Współczynnik służy wyłącznie do korekty ceny bazowej, gdy warunki
wykonania konkretnej pracy odbiegają od warunków założonych w cenie
bazowej.

Nie wolno stosować współczynnika, jeżeli dane utrudnienie zostało już
uwzględnione w cenie bazowej.

### 3. Współczynniki ceny

**Definicja:** współczynnik to korekta ceny bazowej robocizny wynikająca
z warunków wykonania, które odbiegają od warunków założonych przez
właściciela w cenie bazowej PriceItem.

Współczynnik NIE jest dodatkową operacją technologiczną.

Współczynniki dotyczą wyłącznie robocizny.

Nie zmieniają ceny materiałów.

Dla pozycji LABOR_AND_MATERIAL przypisanie współczynników pozostaje
niedozwolone w v1, ponieważ system nie zna wiarygodnego podziału ceny
na robociznę i materiał.

Współczynniki przypisywane są jawnie przez użytkownika do konkretnego
wystąpienia planned work.

Inspection, Risk Rules i Recommendations nie przypisują współczynników
automatycznie.

Domyślny katalog v1 zawiera cztery grupy opisane poniżej. Każda grupa jest
typu SINGLE_SELECT (dla jednego wystąpienia pracy można wybrać najwyżej
jedną opcję z grupy). Opcja 0% w każdej grupie jest opcją bazową
(`is_base=true`). Opcje z różnych grup można łączyć.

#### WYSOKOSC_PRACY

Standardowa — 0%
Podwyższona — +15%
Wysoka — +25%

Koryguje cenę, gdy wysokość powoduje rzeczywisty spadek wydajności
konkretnej pracy.

Koszt rusztowania, podestu, wynajmu sprzętu itp. nie jest częścią tego
współczynnika i powinien być rozliczony oddzielnie.

#### DOSTEP_DO_POWIERZCHNI

Swobodny — 0%
Utrudniony — +10%
Bardzo utrudniony — +20%

Dotyczy ograniczenia dostępu pozostającego podczas wykonywania pracy.

Jednorazowe przesunięcie mebli lub wyposażenia nie jest podstawą do
zastosowania tego współczynnika i powinno być rozliczane jako oddzielna
operacja, jeżeli jest płatne.

#### ZLOZONOSC_POWIERZCHNI

Standardowa — 0%
Złożona — +10%
Bardzo złożona — +20%

Dotyczy spadku wydajności wynikającego z kształtu, rozdrobnienia,
liczby małych fragmentów, dojść, krawędzi lub częstych zmian kierunku
pracy.

Nie należy używać współczynnika do ponownego wyceniania elementów,
które zostały już ujęte jako oddzielne PriceItems, np. ościeży,
narożników lub innych oddzielnie mierzonych prac.

#### ORGANIZACJA_PRACY

Ciągła — 0%
Ograniczona — +10%
Etapowa / przerywana — +20%

Dotyczy spadku wydajności spowodowanego organizacją realizacji,
np. ograniczonymi godzinami dostępu, pracą w czynnym obiekcie,
wielokrotnym udostępnianiem stref lub koniecznością regularnego
przerywania i wznawiania pracy.

Nie obejmuje dodatkowych czynności takich jak zabezpieczenie,
przenoszenie wyposażenia lub dodatkowe sprzątanie, jeśli są one
rozliczane oddzielnie.

#### Czego domyślny katalog celowo NIE zawiera

- grup jakości S1–S4 / Q1–Q4 / PSG1–PSG4 (to quality target, nie
  współczynnik),
- domyślnych ujemnych współczynników,
- współczynnika umeblowania,
- współczynnika sufitu,
- współczynnika koloru,
- współczynnika małego zlecenia,
- współczynnika pilności / pracy nocnej / weekendowej (to dopłaty
  dotyczące zlecenia, patrz punkt 10).

Właściciel może samodzielnie dodawać własne grupy i opcje oraz edytować
lub archiwizować domyślne.

### 4. Poziom bazowy 0%

Opcja 0% jest rzeczywistą opcją katalogu z `is_base=true`.

Wybranie np. "Standardowa 0%" zapisuje świadomą decyzję użytkownika
i jej provenance.

Nie jest to to samo co brak wyboru (`Brak`).

Brak wyboru nie zapisuje CoefficientOption.

### 5. Obliczanie współczynników

Współczynniki z różnych grup sumują się addytywnie.

Nie są kapitalizowane / mnożone jeden przez drugi.

effective_unit_price =
base_unit_price × (1 + suma_procentów)

Przykład:

Cena bazowa: 40,00 zł/m²

Wysokość: +15%
Dostęp: +10%
Złożoność: +10%

Łączna korekta: +35%

40,00 × 1,35 = 54,00 zł/m²

Obliczenia używają Decimal, nigdy float.

Zaokrąglenie ceny następuje zgodnie z zasadami Estimate Engine
do 0,01 zł.

### 6. Wysoka łączna korekta

System nie blokuje wysokiej korekty.

Jeżeli suma współczynników przekracza +50%, UI powinno pokazać
ostrzeżenie:

"Wysoka łączna korekta ceny (+X%).
Sprawdź, czy wybrane współczynniki opisują niezależne utrudnienia oraz
czy ich wpływ nie został już uwzględniony w cenie bazowej lub innych
pozycjach kosztorysu."

Ostrzeżenie jest informacyjne.
Nie jest błędem walidacji i nie wymaga dodatkowego potwierdzenia.

### 7. Opisy współczynników

CoefficientGroup i CoefficientOption mogą posiadać edytowalne pole
`description` (dodawane w Stage 12G).

Dla grup i opcji tworzonych przez właściciela opis jest opcjonalny.
Domyślne grupy i opcje dostarczane przez aplikację muszą mieć
szczegółowe opisy.

Opis powinien wyjaśniać:

- co oznacza współczynnik,
- kiedy go stosować,
- typowe przykłady,
- kiedy go NIE stosować,
- ryzyko podwójnego naliczenia kosztu.

W mobilnym UI obok grupy i opcji, które mają opis, dostępna jest ikona
informacji (obszar dotyku co najmniej 44 px; nie jest to mały tooltip
wyświetlany po najechaniu kursorem).

Po jej naciśnięciu otwierany jest mobilny bottom sheet / modal
z opisem. Strona pod spodem nie reaguje na dotyk, dopóki opis jest
otwarty. Otwarcie opisu nigdy nie zmienia planu prac.

Opis jest pomocą decyzyjną, a nie automatyczną regułą wyceny.

### 8. Ujemne współczynniki

Model danych dopuszcza współczynniki ujemne.

Aplikacja nie dostarcza jednak domyślnych ujemnych współczynników.

Właściciel może utworzyć własny współczynnik, np. dla powtarzalnej,
wysokowydajnej realizacji, jeśli odpowiada to jego modelowi cenowemu.

System nie przyznaje automatycznych rabatów za duży metraż.

### 9. Co NIE jest współczynnikiem

Dodatkowa operacja technologiczna powinna być PriceItem, a nie
współczynnikiem.

Przykłady:

- dodatkowa warstwa gładzi,
- dodatkowa warstwa farby,
- gruntowanie,
- naprawa pęknięcia,
- usuwanie pleśni lub tłustych zabrudzeń,
- włóknina / siatka / fiberglass,
- ościeża,
- dodatkowe narożniki,
- zabezpieczenie,
- przenoszenie wyposażenia.

S1–S4 oraz Q1–Q4 / PSG1–PSG4 również nie są współczynnikami.

### 10. Dopłaty i korekty komercyjne

Współczynnik planned work nie powinien zastępować dopłat dotyczących
całego zlecenia lub warunków handlowych.

Przykłady przyszłych Dopłat:

- minimalna wartość / mały zakres zlecenia,
- praca nocna,
- praca weekendowa,
- dojazd,
- rusztowanie / wynajem sprzętu.

Rabaty handlowe, negocjacje, stały klient lub duży kontrakt również
nie powinny być automatycznie modelowane jako warunki technologiczne
konkretnej pracy.

W v1 fixed surcharge może nadal być reprezentowany przez manual
EstimateLine.

Rozbudowany mechanizm Dopłat pozostaje osobnym przyszłym zakresem.

### 11. Zasada przeciw podwójnemu naliczaniu

Każdy koszt powinien mieć jedno uzasadnienie.

Jeżeli utrudnienie:
- jest już zawarte w cenie bazowej — nie dodawaj współczynnika;
- jest osobną operacją — użyj PriceItem;
- zmniejsza wydajność istniejącej operacji — użyj współczynnika;
- dotyczy całego zlecenia lub warunków handlowych — użyj Dopłaty /
  korekty komercyjnej.

Współczynniki z różnych grup mogą być łączone tylko wtedy, gdy opisują
niezależne przyczyny spadku wydajności.
