"""Archive cleanup AC-4a (the archived rooms and surfaces of all objects in one list) and AC-5a (deleting an archived client for good)."""
import pytest
from httpx import AsyncClient

from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_projects import create_client, create_project
from tests.test_rooms import create_room
from tests.test_surfaces import create_surface


async def owner(async_client: AsyncClient) -> str:
    return await get_token(async_client, VALID_USER)


async def other(async_client: AsyncClient) -> str:
    return await get_token(async_client, OTHER_USER)


async def structure(async_client: AsyncClient, token: str) -> dict:
    response = await async_client.get("/api/archive/structure", headers=auth_header(token))
    assert response.status_code == 200, response.text
    return response.json()


async def archive(async_client: AsyncClient, token: str, url: str) -> None:
    response = await async_client.post(f"{url}/archive", headers=auth_header(token))
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------- AC-4a: archived rooms and surfaces in one list

async def test_nothing_archived_gives_empty_lists(async_client):
    token = await owner(async_client)
    body = await structure(async_client, token)
    assert body == {"rooms": [], "surfaces": [], "rooms_total": 0, "surfaces_total": 0}


async def test_an_archived_room_is_listed_with_its_object_and_leaves_when_restored(async_client):
    token = await owner(async_client)
    project = await create_project(async_client, token, name="Dom pod lasem")
    room = await create_room(async_client, token, project["id"], name="Salon")
    await create_room(async_client, token, project["id"], name="Kuchnia")  # active: not listed
    url = f"/api/projects/{project['id']}/rooms/{room['id']}"
    await archive(async_client, token, url)

    body = await structure(async_client, token)
    assert [(r["id"], r["name"], r["project_id"], r["project_name"]) for r in body["rooms"]] == [
        (room["id"], "Salon", project["id"], "Dom pod lasem")
    ]
    assert body["rooms_total"] == 1 and body["surfaces"] == []

    restored = await async_client.post(f"{url}/restore", headers=auth_header(token))
    assert restored.status_code == 200
    assert (await structure(async_client, token))["rooms"] == []


async def test_an_archived_surface_names_its_room_and_object_and_leaves_when_restored(async_client):
    token = await owner(async_client)
    project = await create_project(async_client, token, name="Mieszkanie")
    room = await create_room(async_client, token, project["id"], name="Sypialnia")
    wall = await create_surface(async_client, token, project["id"], room["id"], name="Ściana 1")
    url = f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{wall['id']}"
    await archive(async_client, token, url)

    body = await structure(async_client, token)
    assert len(body["surfaces"]) == 1 and body["surfaces_total"] == 1
    item = body["surfaces"][0]
    assert (item["id"], item["name"], item["surface_type"]) == (wall["id"], "Ściana 1", "WALL")
    assert (item["room_id"], item["room_name"], item["project_id"], item["project_name"]) == (
        room["id"], "Sypialnia", project["id"], "Mieszkanie"
    )
    assert (await async_client.post(f"{url}/restore", headers=auth_header(token))).status_code == 200
    assert (await structure(async_client, token))["surfaces"] == []


async def test_the_surfaces_of_an_archived_room_are_not_listed_apart_and_come_back_with_the_room(async_client):
    token = await owner(async_client)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    wall = await create_surface(async_client, token, project["id"], room["id"])
    await archive(async_client, token, f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{wall['id']}")
    await archive(async_client, token, f"/api/projects/{project['id']}/rooms/{room['id']}")
    body = await structure(async_client, token)
    assert [r["id"] for r in body["rooms"]] == [room["id"]] and body["surfaces"] == []
    await async_client.post(f"/api/projects/{project['id']}/rooms/{room['id']}/restore", headers=auth_header(token))
    assert [s["id"] for s in (await structure(async_client, token))["surfaces"]] == [wall["id"]]


async def test_nothing_of_an_archived_object_is_listed(async_client):
    token = await owner(async_client)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    await archive(async_client, token, f"/api/projects/{project['id']}/rooms/{room['id']}")
    assert len((await structure(async_client, token))["rooms"]) == 1
    await archive(async_client, token, f"/api/projects/{project['id']}")
    assert (await structure(async_client, token))["rooms"] == []


async def test_another_owners_rooms_and_surfaces_are_never_listed(async_client):
    token, stranger = await owner(async_client), await other(async_client)
    project = await create_project(async_client, stranger, name="Cudzy obiekt")
    room = await create_room(async_client, stranger, project["id"])
    wall = await create_surface(async_client, stranger, project["id"], room["id"])
    await archive(async_client, stranger, f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{wall['id']}")
    other_room = await create_room(async_client, stranger, project["id"], name="Inny")
    await archive(async_client, stranger, f"/api/projects/{project['id']}/rooms/{other_room['id']}")
    assert (await structure(async_client, token)) == {"rooms": [], "surfaces": [], "rooms_total": 0, "surfaces_total": 0}
    assert len((await structure(async_client, stranger))["rooms"]) == 1


async def test_the_list_needs_a_signed_in_user(async_client):
    assert (await async_client.get("/api/archive/structure")).status_code in (401, 403)


# ---------------------------------------------------------------- AC-5a: deleting an archived client for good

async def archived_client(async_client: AsyncClient, token: str, name: str = "Anna") -> dict:
    client = await create_client(async_client, token, first_name=name)
    response = await async_client.post(f"/api/clients/{client['id']}/archive", headers=auth_header(token))
    assert response.status_code == 200
    return client


async def test_an_archived_client_without_objects_can_be_deleted(async_client):
    token = await owner(async_client)
    client = await archived_client(async_client, token)
    preview = await async_client.get(f"/api/clients/{client['id']}/delete-preview", headers=auth_header(token))
    assert preview.status_code == 200
    assert preview.json() == {"client_id": client["id"], "archived": True, "projects": 0, "can_delete": True}

    deleted = await async_client.delete(f"/api/clients/{client['id']}", headers=auth_header(token))
    assert deleted.status_code == 204
    assert (await async_client.get(f"/api/clients/{client['id']}", headers=auth_header(token))).status_code == 404
    listing = await async_client.get("/api/clients?include_archived=true", headers=auth_header(token))
    assert client["id"] not in [c["id"] for c in listing.json()["items"]]


async def test_a_client_in_work_cannot_be_deleted(async_client):
    token = await owner(async_client)
    client = await create_client(async_client, token)
    preview = await async_client.get(f"/api/clients/{client['id']}/delete-preview", headers=auth_header(token))
    assert preview.json()["can_delete"] is False and preview.json()["archived"] is False
    response = await async_client.delete(f"/api/clients/{client['id']}", headers=auth_header(token))
    assert response.status_code == 409 and response.json()["detail"]["code"] == "CLIENT_NOT_ARCHIVED"
    assert (await async_client.get(f"/api/clients/{client['id']}", headers=auth_header(token))).status_code == 200


@pytest.mark.parametrize("archive_the_project", [False, True])
async def test_a_client_with_objects_cannot_be_deleted_whether_the_object_is_archived_or_not(async_client, archive_the_project):
    token = await owner(async_client)
    client = await create_client(async_client, token)
    project = await create_project(async_client, token, client_id=client["id"])
    if archive_the_project:
        await archive(async_client, token, f"/api/projects/{project['id']}")
    await async_client.post(f"/api/clients/{client['id']}/archive", headers=auth_header(token))

    preview = (await async_client.get(f"/api/clients/{client['id']}/delete-preview", headers=auth_header(token))).json()
    assert preview["projects"] == 1 and preview["can_delete"] is False
    response = await async_client.delete(f"/api/clients/{client['id']}", headers=auth_header(token))
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "CLIENT_HAS_PROJECTS", "message": "The client still has objects", "projects": 1}
    # nothing was deleted and the object still points to its client
    assert (await async_client.get(f"/api/clients/{client['id']}", headers=auth_header(token))).status_code == 200
    got = await async_client.get(f"/api/projects/{project['id']}", headers=auth_header(token))
    assert got.json()["client_id"] == client["id"]


async def test_another_owners_client_is_not_found_for_the_preview_and_the_deletion(async_client):
    token, stranger = await owner(async_client), await other(async_client)
    client = await archived_client(async_client, stranger)
    assert (await async_client.get(f"/api/clients/{client['id']}/delete-preview", headers=auth_header(token))).status_code == 404
    assert (await async_client.delete(f"/api/clients/{client['id']}", headers=auth_header(token))).status_code == 404
    assert (await async_client.get(f"/api/clients/{client['id']}", headers=auth_header(stranger))).status_code == 200


async def test_deleting_a_missing_client_is_404_and_needs_sign_in(async_client):
    token = await owner(async_client)
    missing = "00000000-0000-4000-8000-000000000000"
    assert (await async_client.delete(f"/api/clients/{missing}", headers=auth_header(token))).status_code == 404
    assert (await async_client.delete(f"/api/clients/{missing}")).status_code in (401, 403)
