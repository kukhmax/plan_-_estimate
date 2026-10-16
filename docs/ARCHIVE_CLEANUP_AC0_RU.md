# Удаление архивных материалов — AC-0: проверки перед кодом

Статус: **AC-0 выполнен по коду и по базе production (2026-10-16); остаётся один факт — Bucket Lock в Cloudflare (раздел 3a).** Только чтение: код, миграции, production не менялись. План — `docs/ARCHIVE_CLEANUP_PLAN_RU.md`.

## 1. Что проверено в коде и что из этого следует

| № | Находка | Влияние на план |
|---|---|---|
| F1 | **Ссылки на фото по id (JSON, без внешнего ключа) есть ровно в трёх местах:** `concealed_works_protocols.photo_ids`, `downtime_episodes.photo_ids`, `acceptance_protocols.surfaces[...].remarks[].photo_ids`. В `handover_protocols`, `decision_protocols`, `contracts` ссылок на фото нет. В `issued_documents.scope` хранятся помещения отчёта, не фото. Идентификаторы в JSON — это id **привязок** (`photo_attachments`), не активов. | Обратный поиск для правила «фото из выданного протокола нельзя удалять» (раздел 5 плана) — три источника; один запрос на источник, объём данных мал. Реализация — чистая функция в `domain/rules/purge_rules.py` + тесты на каждый из трёх. |
| F2 | Связь привязок с помещением, поверхностью, проёмом, осмотром, находкой, ценовой позицией — `ON DELETE RESTRICT`; активы и привязки к проекту/владельцу — тоже `RESTRICT`. Метки (`photo_annotations`) — `CASCADE` от привязки. | Порядок удаления фиксирован: метки → привязки → активы → родители; при любом шаге база сама остановит ошибку порядка (хорошая страховка). |
| F3 | Порт хранилища `MediaStorage` **сознательно без удаления**, и это закреплено тестом `test_stage14b_media_storage.py:77` (`assert not hasattr(impl, "delete_object")`). `S3MediaStorage` — только put / head / presign / download / iter_keys. | **Не добавлять `delete_object` в `MediaStorage`.** Завести отдельный узкий порт `MediaPurger` (только `delete_objects(keys)`), подключаемый **только** службе удаления; тест F3 остаётся в силе и продолжает охранять основной порт. Это меняет раздел 9 плана. |
| F4 | Бэкап строится от **READY-набора снимка БД**: после удаления строк фото из БД они не входят в набор следующего запуска и туда не копируются. Файлы старых запусков (манифесты, `COMPLETE.json`, объекты) не изменяются. | Новые бэкапы после удаления чисты сами по себе. |
| F5 | `verify` (`app/backup/verify.py`) требует, чтобы **каждая строка манифеста существовала в целевом бакете с записанным размером**; восстановление медиа (`restore_media.py`) — тоже по манифесту. | После удаления из Oracle все **старые** запуски, где эти фото были, перестанут проходить проверку и восстановление. Нужна поправка: проверка и восстановление принимают объект, **отсутствующий по реестру удалений** (отдельный счётчик «purged», не ошибка). Это единственная правка кода бэкапа; загрузчик и его права не меняются. |
| F6 | Порядок эксплуатации: после удаления в R2 и Oracle **самый свежий** запуск всё ещё перечисляет эти фото → его проверка упадёт без поправки F5. | Обязательный шаг после чистки: **новый запуск бэкапа (A9)**, чтобы последний запуск был чистым; в runbook — после скрипта удаления в Oracle. |
| F7 | Права Oracle (14D.3, §6): `OBJECT_DELETE` и `OBJECT_VERSION_DELETE` — отдельные разрешения; перечисление версий — `OBJECT_INSPECT`; у загрузчика их нет, у группы восстановления `plan-estimate-backup-restore` — только чтение. | Для скрипта удаления нужна **новая** группа только для вас (вне VM), например `plan-estimate-backup-purge`, с узкой политикой (проект политики — раздел 2). Создать её вы сможете сами в консоли OCI в AC-3; ничего не создаётся сейчас. |
| F8 | Версионирование: у Oracle-бакета включено (14D.3); у R2 в документах — «versioning / Bucket Lock не считаются бэкапом, правила блокировки удаления — оценить в 14D». R2 не имеет S3-версий объектов; **не включена ли блокировка удаления на бакете (Bucket Lock)** в документах не зафиксировано. | Нужен факт с production (раздел 3, пункт 3): если блокировка включена, удаление приложением будет отказано; тогда AC-2 включает её настройку владельцем. |

## 2. Проект политики OCI для скрипта удаления (проект, **не создаётся сейчас**; проверить формулировки в консоли OCI в AC-3)

Группа `plan-estimate-backup-purge` (IAM-пользователи, только оператор, не на VM):

```
Allow group plan-estimate-backup-purge to read buckets in compartment plan-estimate-backup where target.bucket.name = 'plan-estimate-backup-prod'
Allow group plan-estimate-backup-purge to manage objects in compartment plan-estimate-backup where all {target.bucket.name = 'plan-estimate-backup-prod', any {request.permission = 'OBJECT_INSPECT', request.permission = 'OBJECT_READ', request.permission = 'OBJECT_DELETE', request.permission = 'OBJECT_VERSION_DELETE'}}
```

Условие на бакет — только боевой бэкап; репетиция AC-3 идёт в тренировочном бакете `plan-estimate-backup-drill` с аналогичной политикой. Идентификатор действует только на время работы (ключ создаётся перед запуском и удаляется после — как для restore).

## 3. Факты с production, которые нужны от вас (только чтение, секреты не печатаются)

Выполните в **новой** SSH-сессии на VM и пришлите вывод целиком:

```bash
cd ~/apps/plan_-_estimate
echo "== 1. фото в базе: статус / в архиве / сколько / МБ =="
docker exec -i plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
select status, (archived_at is not null) as archived, count(*) as n, round(sum(byte_size+display_byte_size+thumbnail_byte_size)/1048576.0,1) as mb from photo_assets group by 1,2 order by 1,2;
select (archived_at is not null) as archived, context, count(*) from photo_attachments group by 1,2 order by 1,2;
select (select count(*) from photo_annotations) as annotations;
SQL
echo "== 2. выданные документы и ссылки на фото в протоколах =="
docker exec -i plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
select 'contracts' as t, status, count(*) from contracts group by 2
union all select 'handover', status, count(*) from handover_protocols group by 2
union all select 'concealed', status, count(*) from concealed_works_protocols group by 2
union all select 'acceptance', status, count(*) from acceptance_protocols group by 2
union all select 'decision', status, count(*) from decision_protocols group by 2
union all select 'downtime', status, count(*) from downtime_episodes group by 2 order by 1,2;
select 'concealed with photos' as t, count(*) from concealed_works_protocols where json_array_length(photo_ids::json) > 0
union all select 'downtime with photos', count(*) from downtime_episodes where json_array_length(photo_ids::json) > 0
union all select 'acceptance with photos', count(*) from acceptance_protocols where surfaces::text ~ '"photo_ids":\s*\["';
select (select count(*) from projects where is_archived) as projects_archived, (select count(*) from clients where is_archived) as clients_archived, (select count(*) from rooms where is_archived) as rooms_archived;
SQL
echo "== 3. R2: блокировка / версии (статус, без ключей) =="
docker exec plan_estimate_backend python -c "
from app.core.config import settings as s
from app.core.s3_media_storage import S3MediaStorage
c = S3MediaStorage.from_settings(s)._get_client()
for name, call in (('versioning', lambda: c.get_bucket_versioning(Bucket=s.MEDIA_S3_BUCKET).get('Status', 'none')),
                   ('object_lock', lambda: c.get_object_lock_configuration(Bucket=s.MEDIA_S3_BUCKET).get('ObjectLockConfiguration', {}).get('ObjectLockEnabled', 'none'))):
    try: print(name, call())
    except Exception as e: print(name, 'unavailable:', getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__))
"
```

Если в Cloudflare Dashboard у бакета включены **Bucket Lock** (правила блокировки) — это тоже нужно знать (R2 → бакет → Settings): ответьте «есть / нет».

## 3a. Факты с production (2026-10-16, вывод владельца)

| Что | Значение | Вывод |
|---|---|---|
| Фото-активы | **36 READY, 64,1 МБ, ни одного в архиве, ни одного PENDING / FAILED** | Согласуется с R2 (в панели Cloudflare 108 объектов = 36 × 3, 67,17 МБ): осиротевших файлов нет. |
| Привязки фото | 36 активных (поверхности 25, осмотры 8, находки 1, работы 2), меток 6 | **Архивных фото нет вообще:** удалять сейчас нечего, AC-1 / AC-2 придётся проверять на отдельном тестовом фото, а не на настоящих данных. |
| Выданные документы | Договор, протоколы передачи / приёмки / простоя — по одному, все **DRAFT**; выданных (`ISSUED` / `SIGNED`) нет | Правила блокировки (раздел 5 плана) сейчас ничего не блокируют; они нужны на будущее. |
| Ссылки на фото в протоколах | 0 / 0 / 0 (скрытые работы, простой, приёмка) | Подтверждает F1. |
| Архив структуры | объектов 2, клиентов 1, помещений 2 | Кандидаты на AC-4 / AC-5. |
| R2: версии / блокировка | токен приложения отвечает `AccessDenied` на оба запроса | Не факт «выключено»: токен «Object Read & Write» не имеет права читать настройки бакета. Нужна проверка в панели Cloudflare. |

**Bucket Lock в панели Cloudflare:** R2 → бакет `plan-estimate-media-prod` → вкладка **Settings** → раздел **Bucket lock rules** (если разделов нет в таком виде — искать слова «Bucket Lock» / «Object lock» на этой вкладке). Нужен ответ «правил нет / есть правило (какое)».

## 4. Что меняется в плане по итогам AC-0

1. Раздел 9 плана: вместо `delete_object` в `MediaStorage` — отдельный порт `MediaPurger` (F3).
2. AC-3 включает поправку проверки и восстановления «объект отсутствует по реестру» (F5) и обязательный новый запуск бэкапа после чистки (F6).
3. AC-1 (корзина фото) можно начинать без решений по бэкапу — он ничего не удаляет физически.
4. Остаются открытыми: результаты раздела 3 (особенно Bucket Lock) и создание группы OCI в AC-3 (вручную вами).

AC-0 PASS по коду: все восемь находок раздела 1 подтверждены чтением; **AC-0 закрывается после ответа про Bucket Lock в панели Cloudflare (раздел 3a).**
