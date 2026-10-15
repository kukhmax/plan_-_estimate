"""Notes of the owner on an object (Stage 18): migration 0055 and the owner-scoped API."""
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.models.project_note import ProjectNote
from tests.test_stage16e2_contract import contract_engine, load_migration, run
from tests.test_wall_generation import OWNER_USER, FOREIGN_USER, auth_header, create_project, get_token

NAME = "0055_project_notes"
NOTE = "INSERT INTO project_notes (id, owner_id, project_id, body, created_at, updated_at) VALUES (:id, 'u1', 'p1', :body, '2026-10-15', '2026-10-15')"


def engine_0055():
    engine = contract_engine()
    run(engine, "0054_calendar_reminders", "upgrade")
    run(engine, NAME, "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0054_calendar_reminders" and len(module.revision) <= 32


def test_the_table_has_the_columns_of_the_model_and_refuses_a_blank_note():
    engine = engine_0055()
    inspector = inspect(engine)
    assert {c["name"] for c in inspector.get_columns("project_notes")} == {c.name for c in ProjectNote.__table__.columns}
    assert "ix_project_notes_project_created" in {i["name"] for i in inspector.get_indexes("project_notes")}
    with engine.begin() as conn:
        conn.execute(text(NOTE), {"id": "n1", "body": "Zadzwonić do klienta"})
    for blank in ("", "   "):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(NOTE), {"id": "n2", "body": blank})


def test_deleting_an_object_takes_its_notes_with_it():
    engine = engine_0055()
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text(NOTE), {"id": "n1", "body": "x"})
        conn.execute(text("DELETE FROM projects WHERE id = 'p1'"))
        assert conn.execute(text("SELECT count(*) FROM project_notes")).scalar_one() == 0


def test_downgrade_refuses_while_a_note_exists_and_then_works():
    engine = engine_0055()
    with engine.begin() as conn:
        conn.execute(text(NOTE), {"id": "n1", "body": "x"})
    with pytest.raises(RuntimeError, match="1 note"):
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM project_notes"))
    run(engine, NAME, "downgrade")
    assert "project_notes" not in inspect(engine).get_table_names()
    run(engine, NAME, "upgrade")
    assert "project_notes" in inspect(engine).get_table_names()


def url(project: dict, note_id: str | None = None) -> str:
    return f"/api/projects/{project['id']}/notes" + (f"/{note_id}" if note_id else "")


async def _setup(async_client: AsyncClient) -> tuple[str, dict]:
    token = await get_token(async_client, OWNER_USER)
    return token, await create_project(async_client, token)


async def _write(async_client: AsyncClient, token: str, project: dict, body: str) -> dict:
    response = await async_client.post(url(project), json={"body": body}, headers=auth_header(token))
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_note_is_written_with_the_time_and_listed_newest_first(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    empty = await async_client.get(url(project), headers=auth_header(token))
    assert empty.status_code == 200 and empty.json() == {"items": [], "total": 0}

    first = await _write(async_client, token, project, "  Klient prosi o inny kolor  ")
    second = await _write(async_client, token, project, "Zamówić gładź")

    assert first["body"] == "Klient prosi o inny kolor"  # trimmed
    assert first["project_id"] == project["id"]
    assert first["created_at"] and first["updated_at"]
    listed = (await async_client.get(url(project), headers=auth_header(token))).json()
    assert listed["total"] == 2
    assert [n["id"] for n in listed["items"]] == [second["id"], first["id"]]
    assert datetime.fromisoformat(listed["items"][1]["created_at"]) <= datetime.fromisoformat(listed["items"][0]["created_at"])


async def test_changing_a_note_keeps_its_time_of_writing(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    note = await _write(async_client, token, project, "Stare słowa")

    response = await async_client.patch(url(project, note["id"]), json={"body": "Nowe słowa"}, headers=auth_header(token))

    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["body"] == "Nowe słowa" and changed["id"] == note["id"]
    assert changed["created_at"] == note["created_at"]
    assert datetime.fromisoformat(changed["updated_at"]) >= datetime.fromisoformat(note["updated_at"])


async def test_a_note_is_removed(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    keep = await _write(async_client, token, project, "zostaje")
    gone = await _write(async_client, token, project, "znika")

    response = await async_client.delete(url(project, gone["id"]), headers=auth_header(token))

    assert response.status_code == 204 and response.content == b""
    listed = (await async_client.get(url(project), headers=auth_header(token))).json()
    assert [n["id"] for n in listed["items"]] == [keep["id"]]
    assert (await async_client.delete(url(project, gone["id"]), headers=auth_header(token))).status_code == 404


@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
async def test_an_empty_note_is_refused(async_client: AsyncClient, body: str) -> None:
    token, project = await _setup(async_client)

    created = await async_client.post(url(project), json={"body": body}, headers=auth_header(token))
    assert created.status_code == 422
    note = await _write(async_client, token, project, "ok")
    changed = await async_client.patch(url(project, note["id"]), json={"body": body}, headers=auth_header(token))
    assert changed.status_code == 422
    assert (await async_client.get(url(project), headers=auth_header(token))).json()["items"][0]["body"] == "ok"


async def test_a_too_long_note_and_unknown_fields_are_refused(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)

    assert (await async_client.post(url(project), json={"body": "x" * 4001}, headers=auth_header(token))).status_code == 422
    assert (await async_client.post(url(project), json={"body": "x" * 4000}, headers=auth_header(token))).status_code == 201
    assert (await async_client.post(url(project), json={"body": "ok", "owner_id": "x"}, headers=auth_header(token))).status_code == 422


async def test_a_blank_body_that_passes_the_schema_is_still_refused_by_the_service(async_client: AsyncClient) -> None:
    from app.domain.exceptions import ProjectNoteInvalidError
    from app.domain.services.project_note_service import _clean

    for body in ("", "  \n", "x" * 4001):
        with pytest.raises(ProjectNoteInvalidError):
            _clean(body)
    assert _clean("  a  ") == "a"


async def test_notes_are_private_to_their_owner(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    note = await _write(async_client, token, project, "tajne")
    foreign = await get_token(async_client, FOREIGN_USER)

    assert (await async_client.get(url(project), headers=auth_header(foreign))).status_code == 404
    assert (await async_client.post(url(project), json={"body": "x"}, headers=auth_header(foreign))).status_code == 404
    assert (await async_client.patch(url(project, note["id"]), json={"body": "x"}, headers=auth_header(foreign))).status_code == 404
    assert (await async_client.delete(url(project, note["id"]), headers=auth_header(foreign))).status_code == 404
    assert (await async_client.get(url(project), headers=auth_header(token))).json()["items"][0]["body"] == "tajne"


async def test_a_note_cannot_be_reached_through_another_object(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    other = await create_project(async_client, token)
    note = await _write(async_client, token, project, "tylko tu")

    assert (await async_client.patch(url(other, note["id"]), json={"body": "x"}, headers=auth_header(token))).status_code == 404
    assert (await async_client.delete(url(other, note["id"]), headers=auth_header(token))).status_code == 404
    assert (await async_client.get(url(other), headers=auth_header(token))).json()["total"] == 0
    assert (await async_client.get(url(project), headers=auth_header(token))).json()["total"] == 1


async def test_notes_require_authentication(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    assert (await async_client.get(url(project))).status_code in (401, 403)
