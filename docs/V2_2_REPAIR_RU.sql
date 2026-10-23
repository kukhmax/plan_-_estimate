-- V2-2: убрать демо-объект и демо-клиента, записанные первой версией команды demo открытым текстом (приложение их не читает: DATA_PLAIN_VALUE_REFUSED).
-- Затрагивает ТОЛЬКО объекты с именем на «DEMO » и клиентов с notes на «[DEMO]» аккаунта 7676184233; настоящие данные в базе — шифртекст (enc1:…) и под условие не попадают.
-- Одна транзакция; до и после печатаются счётчики. Комнаты и стены демо-объекта удаляются каскадом.
-- Запуск (прочитайте счётчики «before»: ожидается clients=4 projects=4 rooms=5 или больше, если у вас уже есть комнаты; после — clients и projects меньше на 1, rooms на 5, surfaces на 30):
--   cd ~/apps/plan_-_estimate && git fetch -q origin ver-2 && git show origin/ver-2:docs/V2_2_REPAIR_RU.sql | docker exec -i plan_estimate_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
begin;
select 'before' as step, (select count(*) from clients) as clients, (select count(*) from projects) as projects, (select count(*) from rooms) as rooms, (select count(*) from surfaces) as surfaces;
delete from projects where name like 'DEMO %' and owner_id = (select id from users where telegram_user_id = 7676184233);
delete from clients where notes like '[DEMO]%' and owner_user_id = (select id from users where telegram_user_id = 7676184233);
select 'after' as step, (select count(*) from clients) as clients, (select count(*) from projects) as projects, (select count(*) from rooms) as rooms, (select count(*) from surfaces) as surfaces;
commit;
