# Удаление фото из бэкапов — runbook (архивная чистка, AC-3)

Статус: **готов к репетиции (2026-10-16); на production не применялся.** Документ описывает, как после окончательного удаления фото в приложении (AC-2) убрать его копии из бэкапа в Oracle и как после этого проверять бэкапы и восстанавливаться из них. Решение владельца: удалённые фото **удалять и из опубликованных бэкапов**. План: `docs/ARCHIVE_CLEANUP_PLAN_RU.md` §7, находки: `docs/ARCHIVE_CLEANUP_AC0_RU.md`.

## 1. Что именно удаляется и что нет

| Где | Что | Чем |
|---|---|---|
| База (строки фото, метки) | удаляется сразу | приложение, AC-2 |
| R2 (три файла фото) | удаляются сразу после строк | приложение, AC-2 (при сбое — повтор, см. `/api/photo-purge/retry`) |
| **Oracle: все версии трёх файлов** | **удаляются этим runbook** | инструмент владельца `scripts/purge_backup_objects.py`, **не на VM**, с отдельным доступом |
| Манифесты и «печати» `runs/…`, дампы `db/…` в Oracle | **не меняются и не удаляются** | — |
| Старые дампы БД | остаются целиком: в них строки фото и все остальные данные на момент дампа (убрать строку из зашифрованного дампа нельзя) | при восстановлении из старого дампа реестр удалений **повторяется** (раздел 5) |
| Документы, уже отправленные в Telegram | остаются у клиента | — |

Загрузчик бэкапа на VM **по-прежнему не умеет удалять** (его права не меняются). Удаляет только вы, отдельным доступом, который существует на время работы.

## 2. Один раз: доступ для чистки (создаёте вы в консоли OCI)

Отдельная группа **только для вас**, не на VM, по образцу группы восстановления `plan-estimate-backup-restore` (14D.3). **Формулировки политик проверьте в консоли OCI при создании** (названия разрешений указаны по документации 14D.3 §6; если консоль отвергнет формулировку, пришлите текст ошибки, а не меняйте права «пошире»).

Группа `plan-estimate-backup-purge`, один пользователь (вы), политика `plan-estimate-backup-purge-policy` в отсеке `plan-estimate-backup`:

```
Allow group plan-estimate-backup-purge to read buckets in compartment plan-estimate-backup where any {target.bucket.name = 'plan-estimate-backup-prod', target.bucket.name = 'plan-estimate-backup-drill'}
Allow group plan-estimate-backup-purge to manage objects in compartment plan-estimate-backup where all {any {target.bucket.name = 'plan-estimate-backup-prod', target.bucket.name = 'plan-estimate-backup-drill'}, any {request.permission = 'OBJECT_INSPECT', request.permission = 'OBJECT_READ', request.permission = 'OBJECT_DELETE', request.permission = 'OBJECT_VERSION_DELETE'}}
```

* Ключ API этого пользователя создаётся **перед работой** и **удаляется после**; приватная часть живёт только на вашем компьютере (как ключ восстановления). Файл настроек: `~/.oci-purge/config` (права `0600`).
* Инструмент принимает **только** два бакета: `plan-estimate-backup-drill` (репетиция) и `plan-estimate-backup-prod` (боевая чистка); любое другое имя он отвергает.
* Нужны: репозиторий проекта на компьютере и Python-окружение с `backend/requirements.txt` и `backend/requirements-oci.txt` (как для `stage14d4_oci_restore_smoke.py`).

## 3. Репетиция (обязательна перед первой боевой чисткой)

Цель — увидеть, что инструмент удаляет **все версии** выбранных объектов и **ничего больше**, на данных тренировочного бакета.

1. Список полных наборов фото в тренировочном бакете и репетиционный реестр (только чтение):
   ```
   cd backend && python scripts/purge_rehearsal_ledger.py --namespace <ns> --config ~/.oci-purge/config --out /abs/rehearsal-ledger.jsonl --count 1
   ```
2. Сухой прогон — что есть, ничего не удаляется:
   ```
   python scripts/purge_backup_objects.py --ledger /abs/rehearsal-ledger.jsonl --namespace <ns> --bucket plan-estimate-backup-drill --config ~/.oci-purge/config
   ```
   Ожидается: `DRY RUN`, `versions found=…` (число версий трёх файлов), `deleted=0`.
3. Удаление (инструмент потребует ввести фразу, для репетиции — `РЕПЕТИЦИЯ ДА`):
   ```
   python scripts/purge_backup_objects.py --ledger /abs/rehearsal-ledger.jsonl --namespace <ns> --bucket plan-estimate-backup-drill --config ~/.oci-purge/config --execute --report /abs/rehearsal-report.jsonl
   ```
   Ожидается: `removed`, `deleted=N`, строка «report written».
4. Повтор шага 2 на том же реестре: `versions found=0` (чисто). Манифест и дамп запусков тренировочного бакета на месте (`verify` тренировочного запуска покажет `purged_absent=3`, см. раздел 4).
5. Отчёт репетиции **ничего не помечает** на сервере (в нём `bucket_kind=drill`): проверьте — выполните `mark-done` с ним (раздел 4, шаг F): ожидается `marked=0`.

PASS репетиции: п. 3 удалил все версии только выбранных объектов, п. 4 чисто, п. 5 `marked=0`. Результат пришлите — я запишу его в журнал.

## 4. Боевая чистка (после удаления фото в приложении)

Порядок. A, B и F — на VM (новая SSH-сессия), остальное — на вашем компьютере.

| Шаг | Где | Команда / действие |
|---|---|---|
| A | приложение | фото удалено из корзины навсегда (AC-2); `GET /api/photo-purge/status` показывает `backup_pending` > 0 |
| B | VM | `docker exec plan_estimate_backend python -m app.cli.purge_ledger export --pending-only --out /tmp/purge-ledger.jsonl` затем `docker cp plan_estimate_backend:/tmp/purge-ledger.jsonl ~/purge-ledger.jsonl` |
| C | ваш компьютер | скопировать файл (`scp`) в безопасную папку; файл без содержимого и секретов (ключи, суммы, размеры, время) |
| D | ваш компьютер | **сухой прогон по боевому бакету:** `python scripts/purge_backup_objects.py --ledger /abs/purge-ledger.jsonl --namespace <ns> --bucket plan-estimate-backup-prod --config ~/.oci-purge/config` — проверьте число наборов и версий |
| E | ваш компьютер | **удаление:** тот же вызов с `--execute --report /abs/report-<дата>.jsonl`; фраза подтверждения **`УДАЛИТЬ ИЗ БЭКАПА ДА`** (репетиционная фраза боевой бакет не открывает) |
| F | VM | отчёт на VM (`scp`), затем `docker cp` в контейнер и `docker exec plan_estimate_backend python -m app.cli.purge_ledger mark-done --report /tmp/report.jsonl` → `marked=N` (отчёт репетиции помечает 0) |
| G | VM | **новый полный бэкап A9** (иначе последний запуск перечисляет удалённые фото и его проверка без реестра покажет «отсутствует») |
| H | VM / ваш компьютер | проверка старых запусков по реестру: `verify --run-id <id> --mode full --purge-ledger /abs/purge-ledger.jsonl` → `verify ok … purged_absent=…` |

Если инструмент остановился (сеть, права), он пишет, какой набор не очищен; **повтор безопасен**. Отчёт с `failed` помечает на сервере только очищенные наборы.

## 5. Восстановление из бэкапа после чистки

* Из **последнего** запуска (после шага G): ничего особого — в нём уже нет удалённых фото.
* Из **старого** запуска (до чистки) нужен актуальный реестр (`export` без `--pending-only`, шаг B) и параметр `--purge-ledger`:
  ```
  python -m app.backup restore --run-id <id> ... --purge-ledger /abs/purge-ledger.jsonl
  ```
  Что происходит: файлы удалённых фото **не копируются обратно** (даже если ещё лежат в бэкапе); после успешного восстановления медиа реестр **повторяется на восстановленной базе** — строки удалённых фото, их метки и привязки удаляются, реестр записывается в базу; отчёт содержит `replay` и `purged_skipped`. Затем обычная проверка целостности (`scripts/media_integrity_check.py --verify-sha256 --strict`) видит базу без удалённых фото и бакет без их файлов.
* Реестр — единственный способ «вспомнить» удаление при восстановлении из старого дампа: **храните экспорт реестра рядом с отчётами чистки** (он маленький и не содержит секретов).

## 6. Ограничения, которые надо помнить

* Необратимо: удалённая версия объекта в Oracle не восстанавливается. Поэтому: репетиция, сухой прогон, фраза подтверждения, один бакет за раз.
* Старые дампы БД хранят данные удалённых записей (имена, размеры, тексты) до тех пор, пока вы сами не решите удалить дамп целиком; фото из дампов не читаются.
* Чистка бэкапа не затрагивает R2 (его чистит приложение) и Telegram.
* Выкладка кода AC-1…AC-3 на production — отдельным шагом с вашим «да» (миграции `0056`, `0057`, backup A9 до них); до этого инструменты не нужны.
