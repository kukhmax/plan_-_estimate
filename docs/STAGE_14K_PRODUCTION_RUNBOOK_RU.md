# Stage 14K — итоговая проверка владельцем на production: runbook

Порядок и правила — как в `STAGE_14H5_PRODUCTION_RUNBOOK_RU.md` и `PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md`. **Каждый шаг ждёт вашего явного «да»**; команды выполняете вы на VM `ubuntu@plan-estimate`, вывод присылаете мне, **секреты и ссылки на фото в чат не вставлять**. Все шаги с `docker compose` — в чистой новой SSH-сессии (`env | grep -c '^MEDIA_S3\|^BACKUP_'` = 0); бэкап — в отдельной сессии после выкладки (раздел 72.5).

```bash
cd ~/apps/plan_-_estimate
PC() { docker compose --env-file .env.production -p plan-estimate -f docker-compose.prod.yml "$@"; }
```

## 1. Что делает 14K

Последний подэтап Stage 14 (архитектура §19, строка 14K): вы сами проходите фото-функции Stage 14 на телефоне в production, и только ваше «PASS» закрывает Stage 14. Перед этим на production выкладывается всё, что накопилось в ветке и ещё не выложено.

## 2. Что выкладывается (состояние: production `333fa8d` → ветка `stage-14`)

| Часть | Изменение | Риск |
|---|---|---|
| Миграция | **нет**; `alembic current` остаётся `0036_photo_annotation_outline` | — |
| Backend, 2 файла приложения | `app/domain/services/photo_report_read_model.py` — новый сервис чтения для Stage 15 (14I): **нигде не подключён**, маршрутов и данных не меняет; `app/models/photo_annotation.py` — очищенный контур метки сохраняется как SQL `NULL`, а не JSON `null` (14J, без изменения схемы) | низкий |
| Frontend | **без изменений** (поэтому шаги A6 «frontend» и A7 «кнопка меню Telegram» не нужны) | — |
| Образы бэкапа | **пересборка не нужна** (голова миграций и код `app/backup` не менялись) | — |

Откат: миграции нет; образ `plan-estimate-backend:pre-14k` возвращается в любой момент (раздел 7).

## 3. Выкладка

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
git fetch origin stage-14
echo "--- что придёт ---"; git log --oneline HEAD..origin/stage-14
echo "--- всё, кроме backend/app, tests и docs (должно быть пусто) ---"
git diff --stat HEAD origin/stage-14 -- . ':(exclude)backend/app' ':(exclude)backend/tests' ':(exclude)docs'
echo "--- файлы backend/app ---"; git diff --name-only HEAD origin/stage-14 -- backend/app
```
**PASS:** `0` лишних переменных; дерево чистое, `stage-14`, коммит `333fa8d`; 4 контейнера `Up`; `alembic current` = `0036_photo_annotation_outline`; health ok; свободно ≥ 5 ГБ; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`; блок «всё, кроме…» пуст; в `backend/app` ровно два файла: `domain/services/photo_report_read_model.py` и `models/photo_annotation.py`.

### A3 — получить код → «да, A3»
```bash
git pull --ff-only origin stage-14
git log --oneline -1
git status --short
```
**PASS:** fast-forward; верхний коммит = `origin/stage-14` (его хеш я назову после A0); дерево чистое.

### A4 — конфигурация и сборка backend (старый production работает) → «да, A4»
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC config --quiet && echo CONFIG-OK
docker tag "$(docker inspect -f '{{.Image}}' plan_estimate_backend)" plan-estimate-backend:pre-14k
docker images --format '{{.Repository}}:{{.Tag}}  {{.ID}}' | grep 'backend:pre-14k'
PC build backend 2>&1 | tail -n 6
PC ps
```
**PASS:** `0` лишних переменных; `CONFIG-OK`; тег `pre-14k`; сборка без ошибок; 4 контейнера `Up`.

### A5 — применить backend → «да, A5» (миграции нет: ВОРОТА M не нужны)
```bash
echo "лишних переменных в оболочке: $(env | grep -c '^MEDIA_S3\|^BACKUP_')"
PC up -d --no-deps backend
sleep 20
docker exec plan_estimate_backend alembic current
docker logs plan_estimate_backend --tail 20
curl -fsS https://plan-estimate.pl/api/health; echo
docker exec plan_estimate_backend python -c "from app.core.config import settings as s; k=s.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(); print('ключ приложения:', k[:6]+'…'+k[-4:]); print('бакет:', s.MEDIA_S3_BUCKET); print('endpoint:', str(s.MEDIA_S3_ENDPOINT_URL).split('//')[-1].split('.')[-3:])"
```
**PASS:** `0` лишних переменных; `current` = `0036_photo_annotation_outline`, без строки `Running upgrade`; в логе нет ошибок; health ok; ключ `97bfe5…6dab`, бакет `plan-estimate-media-prod`, endpoint `r2`, `cloudflarestorage`, `com`.

### P1 — сводка отчёта 14I на настоящих данных (только чтение) → «да, P1»
Сервис 14I ни на что не влияет; этот шаг один раз запускает его на данных production и печатает **только числа** (без названий, подписей и ключей хранилища). Числа сравниваются с тем, что вы отметили «Uwzględnij w raporcie» на телефоне (раздел 4, W6).
```bash
docker exec -i plan_estimate_backend python - <<'PY'
import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.domain.services.photo_report_read_model import PhotoReportReadModel
from app.models.project import Project


def photos_of(report):
    found = list(report.project_photos)
    for room in report.rooms:
        found += room.photos
        for surface in room.surfaces:
            found += surface.photos
            for opening in surface.openings:
                found += opening.photos
            for work in surface.works:
                found += work.photos
        for inspection in room.inspections:
            found += inspection.photos
            for question in inspection.questions:
                found += question.photos
            for finding in inspection.findings:
                found += finding.photos
    return found


def shape(report):
    rooms = report.rooms
    surfaces = [s for r in rooms for s in r.surfaces]
    inspections = [i for r in rooms for i in r.inspections]
    works = [w for s in surfaces for w in s.works]
    return {
        "rooms": len(rooms),
        "surfaces": len(surfaces),
        "openings": sum(len(s.openings) for s in surfaces),
        "works": len(works),
        "works_detached": sum(not w.current for w in works),
        "inspections": len(inspections),
        "questions": sum(len(i.questions) for i in inspections),
        "findings": sum(len(i.findings) for i in inspections),
    }


async def summarize(db):
    """Read-only: numbers only, no names, captions or storage keys."""
    projects = (await db.execute(select(Project.id, Project.owner_id).order_by(Project.created_at))).all()
    for number, (project_id, owner_id) in enumerate(projects, start=1):
        service = PhotoReportReadModel(db)
        selected = await service.build(owner_id, project_id)
        visible = await service.build(owner_id, project_id, only_included=False)
        chosen, every = photos_of(selected), photos_of(visible)
        markers = sum(len(p.markers) for p in chosen)
        contours = sum(1 for p in chosen for m in p.markers if m.outline)
        print(f"project {number}: in report {len(chosen)} of {len(every)} visible photos; markers {markers}, contours {contours}")
        print(f"  tree of the report: {shape(selected)}")


async def main():
    async with async_session_maker() as db:
        await summarize(db)


if __name__ == "__main__":
    asyncio.run(main())
PY
```
**PASS:** скрипт отработал без ошибки; для каждого проекта напечатаны числа (`in report N of M visible photos; markers …, contours …` и строка `tree of the report`). `N` ≤ `M`; `N` = числу фото, отмеченных «в отчёт» и не архивных; комнаты / поверхности / осмотры в дереве — только те, где такие фото есть.

## 4. Проверка владельцем на телефоне (W1–W9)
Полностью закройте Telegram и откройте Mini App заново (кнопка меню прежняя, ссылка `?v=333fa8d` остаётся: frontend не менялся). Пройдите на тестовом объекте; PL, затем несколько экранов в RU.

- **W1. Фото объекта, комнаты, стены, потолка, проёма.** «Zrób zdjęcie» (камера) и «Z galerii» дают фото; миниатюры, счётчики на карточках растут; просмотр, подпись («Opis»), категория; **«Uwzględnij w raporcie»** включается и остаётся после закрытия и повторного открытия; «Archiwizuj» убирает фото из списка, «Przywróć» из архива возвращает (в архиве фото не правится).
- **W2. Осмотр.** На вопросе («Czy występują pęknięcia?») есть «Zrób zdjęcie» / «Z galerii»; фото вопроса видно и на самом вопросе, и в верхней панели осмотра; **в верхней панели кнопок съёмки нет**, фото открывается и правится; у строки «Ustalenia» **камеры нет**. Индикатор (камера и число) на «Badanie ściany» / «Badanie sufitu» растёт после нового фото; общие счётчики объекта / комнаты / стены эти фото не включают.
- **W3. Realizacja.** Фото к работе плана (BEFORE / IN_PROGRESS / AFTER и т. д.); индикатор на строке «Realizacja»; фото работы, убранной из плана, остаётся в «Realizacja» (отвязанная работа).
- **W4. Метки.** Поставить метки на фото (до 10), подпись во всплывающем окне, удалить метку; на 11-й метке — понятное сообщение о лимите; метки видны в полноэкранном режиме с увеличением; значок «Znaczniki: N» на плитке.
- **W5. Контур.** «Obrysuj wadę» → обвести пальцем → контур сохраняется и виден после перезапуска Telegram; «Obrysuj ponownie» заменяет; «Usuń obrys» убирает, **после чего метка остаётся без контура** (исправление 14J).
- **W6. Отбор для отчёта.** Отметьте «Uwzględnij w raporcie» у нескольких фото разных мест (комната, стена, вопрос осмотра, работа) и запомните их число; затем шаг P1 покажет то же число.
- **W7. Мобильный вид.** 390 и 412 px (ваш телефон), PL и RU: ничего не режется, кнопки нажимаются, горизонтальной прокрутки нет (замечания по кнопке «Wstecz» и фильтру «Все» известны и записаны в TODO интерфейса, их не считаем).
- **W8. Ссылки на фото.** Фото открываются; ссылку в чат не присылать. (Проверка ссылки с чужого адреса уже была PASS 2026-10-08; повторять не нужно.)
- **W9. Ничего не пропало.** Фото, метки и контуры, сделанные раньше, на месте.

## 5. Резервная копия после проверки (B) — отдельная SSH-сессия → «да, B»
Раздел 72.3 основного runbook, **шаги 2–4** (`db-dump` → `upload` → `verify`); шаг 1 (пересборка образов) не нужен — голова и код бэкапа не менялись. Команды берите из раздела 72.3 дословно (перед ними `. backup.env; . upload.env`). **Закройте сессию после `verify`.** **PASS:** `backup complete … ready_count=<число READY-фото>`, `upload complete`, `verify ok … mode=full`. `ready_count` должен равняться числу фото в системе (то же число, что сумма «в отчёте» + остальные видимые + архивные READY).

## 6. Необязательно (O) — нормализация контуров → только с отдельным «да, O»
Контуры, очищенные до исправления 14J, лежат как JSON `null` (читаются как «нет контура»). Сначала только счёт:
```bash
docker exec plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from photo_annotations where outline::text = '"'"'null'"'"';"'
```
Если число > 0 и вы хотите привести их к `NULL`: `UPDATE photo_annotations SET outline = NULL WHERE outline::text = 'null'` — только по вашему явному «да, O» (данные меняются; безопасно пропустить).

## 7. Оценка риска и откат
- **Данные:** миграции нет; backend-код читает и пишет те же таблицы; единственное поведение, которое меняется, — очищенный контур теперь `NULL`. Сервис 14I не подключён к маршрутам.
- **Совместимость:** frontend не менялся; старые и новые контуры читаются одинаково.
- **Хранилище:** ключ приложения не меняется.

| Ситуация | Действие |
|---|---|
| Backend не стартует после A5 | `docker logs plan_estimate_backend --tail 100`; `docker tag plan-estimate-backend:pre-14k plan-estimate-backend:latest && PC up -d --no-deps --no-build backend` |
| Любое сомнение с данными | остановиться, прислать вывод; `down -v` — **никогда** |

## 8. Закрытие Stage 14
После PASS по W1–W9, P1 и B вы подтверждаете «принимаем 14K» → я записываю приёмку 14K и закрываю Stage 14 в `docs/development-progress.md` (таблица дорожной карты и статус). Отложенное остаётся в backlog: офлайн-очередь фото 14E.8 (по вашему решению), финальный проход по интерфейсу, необязательная нормализация контуров. Stage 15 (документы / PDF) начинается только по вашему отдельному решению.
