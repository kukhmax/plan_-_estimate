"""Stage 16D.2 — the production plan: the order of the works, the technological breaks, the works of others, the working version with
empty lines, the journal, the delivery, the HTTP API and the migration."""
import importlib.util
import io
import uuid
from datetime import date
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_document_issuer  # noqa: F401
from app.domain.documents.production_plan_document import BLANK_ADJACENT, BLANK_ROWS, ProductionPlanDocumentService
from app.domain.documents.renderer import DocumentRenderer
from app.domain.documents.tech_card_document import SPARE_ROWS
from app.domain.exceptions import DocumentDataError, ProjectNotFoundError
from app.models.adjacent_work import AdjacentWork
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from tests.test_clients import OTHER_USER, VALID_USER
from tests.test_stage15e_photo_report import seed as seed_photos
from tests.test_stage15f2_api import login, use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer, journal, text_of, user_of
from tests.test_stage16c_tech_card import plan, price_item, world

TODAY = date(2026, 10, 9)
OWNER_TG, STRANGER_TG = VALID_USER["id"], OTHER_USER["id"]
BACKEND = Path(__file__).resolve().parents[1]


async def build(db, w, *, working, number=None):
    return await ProductionPlanDocumentService(db).build(w.owner.id, w.project.id, working=working, issued_on=TODAY, number=number)


async def add_entry(db, w, **kw) -> AdjacentWork:
    row = AdjacentWork(owner_id=w.owner.id, project_id=w.project.id, work_name=kw.pop("work_name", "Instalacja elektryczna"),
                       order_relation=kw.pop("order_relation", "BEFORE_OURS"), position=kw.pop("position", 0), **kw)
    db.add(row)
    await db.commit()
    return row


# --- the numbered plan ----------------------------------------------------------------------------------------------------------------


async def test_an_object_with_no_planned_works_has_no_numbered_plan(db_session):
    w = await world(db_session)
    with pytest.raises(DocumentDataError) as refused:
        await build(db_session, w, working=False)
    assert refused.value.reason == "PRODUCTION_PLAN_EMPTY"


async def test_the_works_of_a_room_are_numbered_through_its_surfaces_and_the_breaks_are_added_up(db_session):
    w = await world(db_session)
    wall2 = Surface(room_id=w.salon.id, name="Wall 1", surface_type=SurfaceType.WALL, position=5)
    db_session.add(wall2)
    await db_session.commit()
    await plan(db_session, w.wall, [w.item_a, w.item_b], waits=(24, None))
    await plan(db_session, wall2, [w.item_a], waits=(12,))
    document = await build(db_session, w, working=False, number="PLAN/2026/10/09/1200")
    assert not document.working and not document.layout.draft and document.layout.meta.number == "PLAN/2026/10/09/1200"
    (room,) = document.rooms  # Kuchnia has nothing planned
    assert room.name == "Salon" and room.spare_rows == 0 and room.total_wait_hours == 36
    # surfaces with a position come first (the owner's order), the rest by creation; the numbers run through the room
    assert [(x.number, x.surface, x.surface_type, x.unit, x.wait_hours) for x in room.works] == [
        (1, "Ściana 1", "ściana", "m²", 12), (2, "Ściana A", "ściana", "m²", 24), (3, "Ściana A", "ściana", "m²", None)]
    html = ProductionPlanDocumentService.html(document)
    assert "Plan produkcji prac" in html and "36 godz." in html and "WERSJA ROBOCZA" not in html
    assert "zł" not in html
    assert html[html.index("<body"):].count("write-line") == 2  # only the two dates of the room are left to write in
    assert "Nie zarejestrowano prac innych wykonawców." in html


async def test_the_plan_needs_the_executor_profile_but_the_working_version_does_not(db_session):
    w = await world(db_session, with_profile=False)
    await plan(db_session, w.wall, [w.item_a])
    with pytest.raises(DocumentDataError) as refused:
        await build(db_session, w, working=False)
    assert refused.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    assert (await build(db_session, w, working=True)).layout.executor is None


async def test_the_adjacent_works_are_printed_with_rooms_by_name_the_period_and_the_order(db_session):
    w = await world(db_session)
    await plan(db_session, w.wall, [w.item_a])
    await add_entry(db_session, w, performer="Firma Prąd", room_ids=[str(w.salon.id), str(w.kuchnia.id)], period_from=date(2026, 10, 12),
                    period_to=date(2026, 10, 14), order_note="elektryka przed tynkiem", responsibility_note="sprząta ekipa",
                    coordination_note="Jan Kowalski")
    await add_entry(db_session, w, work_name="Płytki", order_relation="AFTER_OURS", room_ids=None, period_from=date(2026, 10, 20), position=1)
    document = await build(db_session, w, working=False)
    first, second = document.adjacent
    assert (first.work_name, first.performer, first.rooms, first.period, first.order) == (
        "Instalacja elektryczna", "Firma Prąd", "Salon, Kuchnia", "12.10.2026 – 14.10.2026", "przed naszymi pracami")
    assert (first.order_note, first.responsibility_note, first.coordination_note) == ("elektryka przed tynkiem", "sprząta ekipa", "Jan Kowalski")
    assert (second.rooms, second.period, second.order) == ("cały obiekt", "od 20.10.2026", "po naszych pracach")
    text = ProductionPlanDocumentService.html(document)
    assert "Rodzaj prac" in text and "Firma Prąd" in text and "Nie zarejestrowano" not in text


async def test_an_archived_entry_is_left_out_and_an_archived_room_is_not_named(db_session):
    w = await world(db_session)
    await plan(db_session, w.wall, [w.item_a])
    await add_entry(db_session, w, work_name="Stara", is_archived=True)
    await add_entry(db_session, w, work_name="Tylko kuchnia", room_ids=[str(w.kuchnia.id)], position=1)
    room = (await db_session.execute(select(Room).where(Room.id == w.kuchnia.id))).scalar_one()
    room.is_archived = True
    await db_session.commit()
    (entry,) = (await build(db_session, w, working=False)).adjacent
    assert entry.work_name == "Tylko kuchnia" and entry.rooms == "pomieszczenia nieaktywne"


async def test_a_foreign_project_is_not_found_and_a_foreign_entry_is_never_read(db_session):
    w = await world(db_session)
    other = await seed_photos(db_session, telegram_id=9702)
    await plan(db_session, w.wall, [w.item_a])
    await add_entry(db_session, other, work_name="Cudza")
    with pytest.raises(ProjectNotFoundError):
        await ProductionPlanDocumentService(db_session).build(other.owner.id, w.project.id, working=True, issued_on=TODAY)
    assert (await build(db_session, w, working=False)).adjacent == ()


# --- the working version --------------------------------------------------------------------------------------------------------------


async def test_the_working_version_prints_what_exists_and_empty_lines_for_the_rest(db_session):
    w = await world(db_session)
    await plan(db_session, w.wall, [w.item_a], waits=(6,))
    document = await build(db_session, w, working=True)
    assert document.working and document.layout.draft and document.layout.light_watermark and document.layout.meta.number is None
    assert [r.name for r in document.rooms] == ["Salon", "Kuchnia"]
    assert document.rooms[0].spare_rows == SPARE_ROWS - 1 and document.rooms[1].spare_rows == SPARE_ROWS and document.rooms[1].works == ()
    assert len(document.adjacent) == BLANK_ADJACENT and all(a.work_name is None for a in document.adjacent)
    html = ProductionPlanDocumentService.html(document)
    assert 'class="watermark light"' in html and "write-line" in html and html.count('class="spare"') == SPARE_ROWS - 1 + SPARE_ROWS


async def test_blank_entries_come_after_the_real_ones_in_the_working_version(db_session):
    w = await world(db_session)
    await add_entry(db_session, w)
    document = await build(db_session, w, working=True)
    assert [a.work_name for a in document.adjacent] == ["Instalacja elektryczna", None, None]


async def test_an_object_with_no_rooms_gets_a_blank_form(db_session):
    w = await world(db_session)
    for room in (w.salon, w.kuchnia):
        row = (await db_session.execute(select(Room).where(Room.id == room.id))).scalar_one()
        row.is_archived = True
    await db_session.commit()
    (room,) = (await build(db_session, w, working=True)).rooms
    assert room.name is None and room.works == () and room.spare_rows == BLANK_ROWS


async def test_the_pdf_has_the_headings_and_the_pale_watermark(db_session):
    w = await world(db_session)
    await plan(db_session, w.wall, [w.item_a, w.item_b], waits=(24, None))
    await add_entry(db_session, w, performer="Firma Prąd")
    pdf = (await DocumentRenderer().render(ProductionPlanDocumentService.html(await build(db_session, w, working=True)))).pdf
    text = " ".join(text_of(pdf).split())
    for heading in ("Plan produkcji prac", "Kolejność prac w pomieszczeniach", "Pomieszczenie: Salon", "ermin rozpoczęcia",  # the extractor splits the kerned capital "T"
                    "ermin zakończenia", "Przerwa technologiczna po pracy", "Łączny czas przerw technologicznych w pomieszczeniu: 24 godz.",
                    "Prace innych wykonawców", "Rodzaj prac", "Kolejność względem naszych prac", "Czystość i uszkodzenia", "Koordynacja", "WERSJA ROBOCZA"):
        assert heading in text, heading
    assert len(PdfReader(io.BytesIO(pdf)).pages) >= 1


async def test_the_number_of_queries_does_not_grow_with_rooms_surfaces_and_entries(db_session):
    w = await world(db_session)
    await plan(db_session, w.wall, [w.item_a])
    await add_entry(db_session, w)
    counter = {"n": 0}

    def count(*_):
        counter["n"] += 1

    bind = db_session.bind.sync_engine
    event.listen(bind, "before_cursor_execute", count)
    try:
        await build(db_session, w, working=True)
        small = counter["n"]
        for index in range(5):
            room = Room(project_id=w.project.id, name=f"R{index}")
            db_session.add(room)
            await db_session.flush()
            surface = Surface(room_id=room.id, name="S", surface_type=SurfaceType.WALL)
            db_session.add(surface)
            await db_session.flush()
            await plan(db_session, surface, [w.item_a])
            await add_entry(db_session, w, work_name=f"E{index}", position=index + 1)
        counter["n"] = 0
        await build(db_session, w, working=True)
        assert counter["n"] == small
    finally:
        event.remove(bind, "before_cursor_execute", count)


def test_the_template_has_no_price_or_clause_word():
    from app.domain.documents.labels import load_labels
    from app.domain.documents.templating import TEMPLATES_DIR

    source = (TEMPLATES_DIR / "production_plan.html.j2").read_text(encoding="utf-8").lower()
    for word in ("zł", "pln", "cena", "gwarancj", "kara", "odpowiedzialn", "zobowiązuj"):
        assert word not in source, word
    for key, value in load_labels().items():
        if key.startswith("plan."):
            for word in ("zł", "gwarancj", "kara", "odpowiedzialn", "zobowiązuj"):
                assert word not in value.lower(), (key, word)


# --- issuing --------------------------------------------------------------------------------------------------------------------------


async def test_a_plan_is_numbered_rendered_sent_and_recorded(db_session):
    w = await world(db_session, telegram_id=9750)
    owner_id, project_id, telegram = w.owner.id, w.project.id, w.owner.telegram_user_id
    await plan(db_session, w.wall, [w.item_a])
    sender = Delivery()
    run = issuer(delivery=sender)
    reservation = await run.start_production_plan(db_session, await user_of(db_session, owner_id), project_id)
    assert (reservation.document.status, reservation.document.kind, reservation.document.project_seq) == ("PENDING", "PRODUCTION_PLAN", 1)
    assert reservation.document.number.startswith("PLAN/2026/10/08/")
    await run.drain()
    (done,) = await journal(db_session)
    assert (done.status, done.error_code, done.title) == ("SENT", None, "Plan produkcji prac")
    (message,) = sender.sent
    assert message["chat_id"] == telegram and message["filename"].startswith("PLAN-2026-10-08-")
    assert message["caption"].startswith("Plan produkcji prac — Mokotów\nPLAN/")
    text = text_of(message["pdf"])
    assert done.number in text and "WERSJA ROBOCZA" not in text


async def test_an_empty_plan_takes_no_number(db_session):
    w = await world(db_session, telegram_id=9751)
    owner_id, project_id = w.owner.id, w.project.id
    run = issuer()
    with pytest.raises(DocumentDataError) as refused:
        await run.start_production_plan(db_session, await user_of(db_session, owner_id), project_id)
    assert refused.value.reason == "PRODUCTION_PLAN_EMPTY" and await journal(db_session) == [] and run.active == 0


async def test_the_preview_goes_to_the_chat_without_a_number_or_a_journal_row_even_for_an_empty_object(db_session):
    w = await world(db_session, telegram_id=9752)
    owner_id, project_id = w.owner.id, w.project.id
    sender = Delivery()
    result = await issuer(delivery=sender).preview_production_plan(db_session, await user_of(db_session, owner_id), project_id)
    assert result.pages >= 1
    (message,) = sender.sent
    assert message["filename"] == "Plan-produkcji-prac-wersja-robocza.pdf"
    assert message["caption"] == "WERSJA ROBOCZA — Plan produkcji prac — Mokotów"
    assert "WERSJA ROBOCZA" in text_of(message["pdf"]) and await journal(db_session) == []


# --- HTTP -----------------------------------------------------------------------------------------------------------------------------


async def test_the_routes_need_a_token_and_take_no_other_fields(async_client: AsyncClient, use_issuer):  # noqa: F811
    run = use_issuer(issuer())
    pid = uuid.uuid4()
    assert (await async_client.post(f"/api/projects/{pid}/documents", json={"kind": "PRODUCTION_PLAN"})).status_code == 401
    assert (await async_client.post(f"/api/projects/{pid}/documents/production-plan/preview")).status_code == 401
    headers = await login(async_client)
    for body in ({"kind": "PRODUCTION_PLAN", "estimate_id": str(uuid.uuid4())}, {"kind": "PRODUCTION_PLAN", "room_ids": [str(uuid.uuid4())]},
                 {"kind": "PRODUCTION_PLAN", "include_project_photos": True}):
        assert (await async_client.post(f"/api/projects/{pid}/documents", json=body, headers=headers)).status_code == 422
    assert run.active == 0


async def test_issue_then_journal_then_an_empty_object_is_a_422(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await world(db_session, telegram_id=OWNER_TG)
    project_id = str(w.project.id)
    sender = Delivery()
    run = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    empty = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "PRODUCTION_PLAN"}, headers=headers)
    assert (empty.status_code, empty.json()["detail"]["code"]) == (422, "PRODUCTION_PLAN_EMPTY")
    await plan(db_session, w.wall, [w.item_a])
    response = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "PRODUCTION_PLAN"}, headers=headers)
    assert response.status_code == 202, response.text
    row = response.json()
    assert row["kind"] == "PRODUCTION_PLAN" and row["number"].startswith("PLAN/") and row["source_id"] is None
    await run.drain()
    assert (await async_client.get(f"/api/projects/{project_id}/documents/{row['id']}", headers=headers)).json()["status"] == "SENT"


async def test_the_preview_is_a_200_and_a_stranger_gets_404(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    mine = await world(db_session, telegram_id=OWNER_TG)
    theirs = await seed_photos(db_session, telegram_id=STRANGER_TG)
    sender = Delivery()
    use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    ok = await async_client.post(f"/api/projects/{mine.project.id}/documents/production-plan/preview", headers=headers)
    assert ok.status_code == 200 and ok.json()["sent"] is True and len(sender.sent) == 1
    for response in (
        await async_client.post(f"/api/projects/{theirs.project.id}/documents/production-plan/preview", headers=headers),
        await async_client.post(f"/api/projects/{theirs.project.id}/documents", json={"kind": "PRODUCTION_PLAN"}, headers=headers),
    ):
        assert response.status_code == 404 and response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert len(sender.sent) == 1


# --- migration ------------------------------------------------------------------------------------------------------------------------

INSERT = (
    "INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at) "
    "VALUES (:id, 'u1', 'p1', :kind, 't', :number, :seq, '1', 'SENT', '2026-10-09')"
)


def load_migration(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "alembic" / "versions" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(engine, name: str, direction: str):
    module = load_migration(name)
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        getattr(module, direction)()


def journal_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE projects (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users (id) VALUES ('u1')"))
        conn.execute(text("INSERT INTO projects (id) VALUES ('p1')"))
    run(engine, "0038_issued_documents", "upgrade")
    run(engine, "0041_issued_documents_tech_card", "upgrade")
    return engine


def test_revision_chain():
    module = load_migration("0043_issued_docs_plan")
    assert module.revision == "0043_issued_docs_plan" and module.down_revision == "0042_adjacent_works"


def test_the_database_refuses_a_plan_before_the_migration_and_accepts_it_after():
    engine = journal_engine()
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "a", "kind": "PRODUCTION_PLAN", "number": "PLAN/1", "seq": 1})
    run(engine, "0043_issued_docs_plan", "upgrade")
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "a", "kind": "PRODUCTION_PLAN", "number": "PLAN/1", "seq": 1})
        conn.execute(text(INSERT), {"id": "b", "kind": "TECH_CARD", "number": "KART/1", "seq": 2})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "c", "kind": "CONTRACT", "number": "UMOWA/1", "seq": 3})


def test_downgrade_narrows_the_check_and_refuses_to_lose_a_plan():
    engine = journal_engine()
    run(engine, "0043_issued_docs_plan", "upgrade")
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "a", "kind": "PRODUCTION_PLAN", "number": "PLAN/1", "seq": 1})
        conn.execute(text(INSERT), {"id": "b", "kind": "TECH_CARD", "number": "KART/1", "seq": 2})
    with pytest.raises(RuntimeError, match="1 production plan"):
        run(engine, "0043_issued_docs_plan", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issued_documents WHERE kind = 'PRODUCTION_PLAN'"))
    run(engine, "0043_issued_docs_plan", "downgrade")
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "c", "kind": "PRODUCTION_PLAN", "number": "PLAN/2", "seq": 3})
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM issued_documents")).scalar_one() == 1  # the card survived


def test_every_revision_id_fits_the_alembic_version_column():
    """`alembic_version.version_num` is varchar(32): a longer id passes on SQLite and fails on PostgreSQL at the very end of the
    upgrade (found by the PostgreSQL check of 0043)."""
    ids = []
    for path in sorted((BACKEND / "alembic" / "versions").glob("*.py")):
        module = load_migration(path.stem)
        ids.append(module.revision)
        assert len(module.revision) <= 32, (path.name, len(module.revision))
    assert len(ids) == len(set(ids)) and "0043_issued_docs_plan" in ids
