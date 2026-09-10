import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.room import Room
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 555555555,
    "username": "room_owner",
    "first_name": "Room",
    "last_name": "Owner",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 666666666,
    "username": "other_room_owner",
    "first_name": "Other",
    "last_name": "Owner",
    "language_code": "pl",
}


async def get_token(async_client: AsyncClient, user_dict: dict) -> str:
    response = await async_client.post(
        "/api/auth/telegram",
        json={"init_data": make_telegram_init_data(user_dict)},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_project(
    async_client: AsyncClient,
    token: str,
    name: str = "Projekt pomieszczeń",
) -> dict:
    response = await async_client.post(
        "/api/projects",
        json={
            "name": name,
            "address": "ul. Pokojowa 10",
            "city": "Warszawa",
            "postal_code": "00-001",
            "description": "Projekt do testów pomieszczeń",
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_room(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    name: str = "Salon",
    description: str | None = "Pomieszczenie dzienne",
) -> dict:
    response = await async_client.post(
        f"/api/projects/{project_id}/rooms",
        json={"name": name, "description": description},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def room_url(project_id: str, room_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}"


async def test_create_room_persists_minimal_fields(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)

    response = await async_client.post(
        f"/api/projects/{project['id']}/rooms",
        json={"name": "Łazienka", "description": "Strefa mokra"},
        headers=auth_header(token),
    )

    assert response.status_code == 201
    data = response.json()
    assert set(data) == {
        "id",
        "project_id",
        "name",
        "description",
        "length",
        "width",
        "height",
        "calculations",
        "is_archived",
        "created_at",
        "updated_at",
    }
    assert data["project_id"] == project["id"]
    assert data["name"] == "Łazienka"
    assert data["description"] == "Strefa mokra"
    assert data["length"] is None
    assert data["width"] is None
    assert data["height"] is None
    assert data["calculations"] is None
    assert data["is_archived"] is False
    assert data["created_at"]
    assert data["updated_at"]

    result = await db_session.execute(
        select(Room).where(Room.id == uuid.UUID(data["id"]))
    )
    room = result.scalar_one()
    assert room.project_id == uuid.UUID(project["id"])
    assert room.name == "Łazienka"
    assert room.description == "Strefa mokra"
    assert room.is_archived is False


async def test_create_room_without_description(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)

    response = await async_client.post(
        f"/api/projects/{project['id']}/rooms",
        json={"name": "Korytarz"},
        headers=auth_header(token),
    )

    assert response.status_code == 201
    assert response.json()["description"] is None


async def test_list_rooms_filters_archived_and_scopes_to_project(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token, "Pierwszy projekt")
    other_project = await create_project(async_client, token, "Drugi projekt")
    first = await create_room(async_client, token, project["id"], "Salon")
    second = await create_room(async_client, token, project["id"], "Kuchnia")
    archived = await create_room(async_client, token, project["id"], "Garderoba")
    unrelated = await create_room(
        async_client,
        token,
        other_project["id"],
        "Inny projekt",
    )
    archive_response = await async_client.post(
        f"{room_url(project['id'], archived['id'])}/archive",
        headers=auth_header(token),
    )
    assert archive_response.status_code == 200

    active_response = await async_client.get(
        f"/api/projects/{project['id']}/rooms",
        headers=auth_header(token),
    )
    archived_response = await async_client.get(
        f"/api/projects/{project['id']}/rooms?include_archived=true",
        headers=auth_header(token),
    )

    assert active_response.status_code == 200
    assert active_response.json()["total"] == 2
    assert {item["id"] for item in active_response.json()["items"]} == {
        first["id"],
        second["id"],
    }
    assert archived_response.status_code == 200
    assert archived_response.json()["total"] == 3
    assert {item["id"] for item in archived_response.json()["items"]} == {
        first["id"],
        second["id"],
        archived["id"],
    }
    assert unrelated["id"] not in {
        item["id"] for item in archived_response.json()["items"]
    }


async def test_read_room(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    response = await async_client.get(
        room_url(project["id"], room["id"]),
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json() == room


async def test_update_room(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    response = await async_client.patch(
        room_url(project["id"], room["id"]),
        json={"name": "Pokój dzienny", "description": None},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Pokój dzienny"
    assert response.json()["description"] is None
    assert response.json()["project_id"] == project["id"]


async def test_archive_room(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    response = await async_client.post(
        f"{room_url(project['id'], room['id'])}/archive",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["is_archived"] is True


async def test_restore_room(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    await async_client.post(
        f"{room_url(project['id'], room['id'])}/archive",
        headers=auth_header(token),
    )

    response = await async_client.post(
        f"{room_url(project['id'], room['id'])}/restore",
        headers=auth_header(token),
    )
    list_response = await async_client.get(
        f"/api/projects/{project['id']}/rooms",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["is_archived"] is False
    assert room["id"] in [item["id"] for item in list_response.json()["items"]]


async def test_room_cannot_be_accessed_through_another_owned_project(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    first_project = await create_project(async_client, token, "Pierwszy")
    second_project = await create_project(async_client, token, "Drugi")
    room = await create_room(async_client, token, first_project["id"])
    missing_room_id = str(uuid.uuid4())

    wrong_project_response = await async_client.get(
        room_url(second_project["id"], room["id"]),
        headers=auth_header(token),
    )
    missing_response = await async_client.get(
        room_url(second_project["id"], missing_room_id),
        headers=auth_header(token),
    )

    assert wrong_project_response.status_code == 404
    assert missing_response.status_code == 404
    assert wrong_project_response.json() == missing_response.json() == {
        "detail": "Room not found"
    }


async def test_foreign_project_is_indistinguishable_from_missing(
    async_client: AsyncClient,
) -> None:
    owner_token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    project = await create_project(async_client, owner_token)
    room = await create_room(async_client, owner_token, project["id"])
    missing_project_id = str(uuid.uuid4())

    foreign_responses = [
        await async_client.post(
            f"/api/projects/{project['id']}/rooms",
            json={"name": "Niedozwolone"},
            headers=auth_header(other_token),
        ),
        await async_client.get(
            f"/api/projects/{project['id']}/rooms",
            headers=auth_header(other_token),
        ),
        await async_client.get(
            room_url(project["id"], room["id"]),
            headers=auth_header(other_token),
        ),
        await async_client.patch(
            room_url(project["id"], room["id"]),
            json={"name": "Niedozwolona zmiana"},
            headers=auth_header(other_token),
        ),
        await async_client.post(
            f"{room_url(project['id'], room['id'])}/archive",
            headers=auth_header(other_token),
        ),
        await async_client.post(
            f"{room_url(project['id'], room['id'])}/restore",
            headers=auth_header(other_token),
        ),
    ]
    missing_responses = [
        await async_client.post(
            f"/api/projects/{missing_project_id}/rooms",
            json={"name": "Niedozwolone"},
            headers=auth_header(other_token),
        ),
        await async_client.get(
            f"/api/projects/{missing_project_id}/rooms",
            headers=auth_header(other_token),
        ),
        await async_client.get(
            room_url(missing_project_id, room["id"]),
            headers=auth_header(other_token),
        ),
        await async_client.patch(
            room_url(missing_project_id, room["id"]),
            json={"name": "Niedozwolona zmiana"},
            headers=auth_header(other_token),
        ),
        await async_client.post(
            f"{room_url(missing_project_id, room['id'])}/archive",
            headers=auth_header(other_token),
        ),
        await async_client.post(
            f"{room_url(missing_project_id, room['id'])}/restore",
            headers=auth_header(other_token),
        ),
    ]

    for foreign_response, missing_response in zip(
        foreign_responses,
        missing_responses,
        strict=True,
    ):
        assert foreign_response.status_code == 404
        assert missing_response.status_code == 404
        assert foreign_response.json() == missing_response.json() == {
            "detail": "Project not found"
        }


async def test_foreign_room_is_indistinguishable_from_missing(
    async_client: AsyncClient,
) -> None:
    owner_token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    project = await create_project(async_client, owner_token)
    foreign_project = await create_project(async_client, other_token, "Obcy projekt")
    foreign_room = await create_room(
        async_client,
        other_token,
        foreign_project["id"],
        "Obce pomieszczenie",
    )
    missing_room_id = str(uuid.uuid4())

    foreign_responses = [
        await async_client.get(
            room_url(project["id"], foreign_room["id"]),
            headers=auth_header(owner_token),
        ),
        await async_client.patch(
            room_url(project["id"], foreign_room["id"]),
            json={"name": "Niedozwolona zmiana"},
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{room_url(project['id'], foreign_room['id'])}/archive",
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{room_url(project['id'], foreign_room['id'])}/restore",
            headers=auth_header(owner_token),
        ),
    ]
    missing_responses = [
        await async_client.get(
            room_url(project["id"], missing_room_id),
            headers=auth_header(owner_token),
        ),
        await async_client.patch(
            room_url(project["id"], missing_room_id),
            json={"name": "Niedozwolona zmiana"},
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{room_url(project['id'], missing_room_id)}/archive",
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{room_url(project['id'], missing_room_id)}/restore",
            headers=auth_header(owner_token),
        ),
    ]

    for foreign_response, missing_response in zip(
        foreign_responses,
        missing_responses,
        strict=True,
    ):
        assert foreign_response.status_code == 404
        assert missing_response.status_code == 404
        assert foreign_response.json() == missing_response.json() == {
            "detail": "Room not found"
        }


async def test_missing_project_and_room_return_404(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    missing_project_id = str(uuid.uuid4())
    missing_room_id = str(uuid.uuid4())

    project_response = await async_client.get(
        f"/api/projects/{missing_project_id}/rooms",
        headers=auth_header(token),
    )
    room_response = await async_client.get(
        room_url(project["id"], missing_room_id),
        headers=auth_header(token),
    )

    assert project_response.status_code == 404
    assert project_response.json() == {"detail": "Project not found"}
    assert room_response.status_code == 404
    assert room_response.json() == {"detail": "Room not found"}


async def test_invalid_project_and_room_ids_are_rejected(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)

    project_response = await async_client.get(
        "/api/projects/not-a-uuid/rooms",
        headers=auth_header(token),
    )
    room_response = await async_client.get(
        f"/api/projects/{project['id']}/rooms/not-a-uuid",
        headers=auth_header(token),
    )

    assert project_response.status_code == 422
    assert room_response.status_code == 422
