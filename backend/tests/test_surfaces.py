import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.surface import Surface, SurfaceType
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 777777777,
    "username": "surface_owner",
    "first_name": "Surface",
    "last_name": "Owner",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 888888888,
    "username": "other_surface_owner",
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
    name: str = "Projekt powierzchni",
) -> dict:
    response = await async_client.post(
        "/api/projects",
        json={
            "name": name,
            "address": "ul. Płaszczyznowa 10",
            "city": "Warszawa",
            "postal_code": "00-002",
            "description": "Projekt do testów powierzchni",
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
) -> dict:
    response = await async_client.post(
        f"/api/projects/{project_id}/rooms",
        json={"name": name, "description": "Pomieszczenie testowe"},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def surfaces_url(project_id: str, room_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/surfaces"


def surface_url(project_id: str, room_id: str, surface_id: str) -> str:
    return f"{surfaces_url(project_id, room_id)}/{surface_id}"


async def create_surface(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    room_id: str,
    name: str = "Ściana północna",
    surface_type: str = "WALL",
    description: str | None = "Powierzchnia testowa",
) -> dict:
    response = await async_client.post(
        surfaces_url(project_id, room_id),
        json={
            "name": name,
            "surface_type": surface_type,
            "description": description,
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("surface_type", ["WALL", "CEILING", "FLOOR", "OTHER"])
async def test_create_each_supported_surface_type(
    async_client: AsyncClient,
    surface_type: str,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    response = await async_client.post(
        surfaces_url(project["id"], room["id"]),
        json={
            "name": f"Powierzchnia {surface_type}",
            "surface_type": surface_type,
        },
        headers=auth_header(token),
    )

    assert response.status_code == 201
    data = response.json()
    assert set(data) == {
        "id",
        "room_id",
        "name",
        "surface_type",
        "description",
        "width",
        "height",
        "gross_area",
        "is_archived",
        "created_at",
        "updated_at",
    }
    assert data["room_id"] == room["id"]
    assert data["surface_type"] == surface_type
    assert data["description"] is None
    assert data["width"] is None
    assert data["height"] is None
    assert data["gross_area"] is None
    assert data["is_archived"] is False


async def test_surface_relationship_is_persisted(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    surface = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
        name="Sufit główny",
        surface_type="CEILING",
    )

    result = await db_session.execute(
        select(Surface).where(Surface.id == uuid.UUID(surface["id"]))
    )
    persisted = result.scalar_one()
    assert persisted.room_id == uuid.UUID(room["id"])
    assert persisted.name == "Sufit główny"
    assert persisted.surface_type == SurfaceType.CEILING
    assert persisted.description == "Powierzchnia testowa"
    assert persisted.is_archived is False


async def test_list_surfaces_filters_archived_and_scopes_to_room(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"], "Salon")
    other_room = await create_room(async_client, token, project["id"], "Kuchnia")
    first = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
        "Ściana A",
        "WALL",
    )
    second = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
        "Sufit",
        "CEILING",
    )
    archived = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
        "Podłoga",
        "FLOOR",
    )
    unrelated = await create_surface(
        async_client,
        token,
        project["id"],
        other_room["id"],
        "Inne pomieszczenie",
        "OTHER",
    )
    archive_response = await async_client.post(
        f"{surface_url(project['id'], room['id'], archived['id'])}/archive",
        headers=auth_header(token),
    )
    assert archive_response.status_code == 200

    active_response = await async_client.get(
        surfaces_url(project["id"], room["id"]),
        headers=auth_header(token),
    )
    archived_response = await async_client.get(
        f"{surfaces_url(project['id'], room['id'])}?include_archived=true",
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


async def test_read_surface(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    surface = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
    )

    response = await async_client.get(
        surface_url(project["id"], room["id"], surface["id"]),
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json() == surface


async def test_update_surface(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    surface = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
    )

    response = await async_client.patch(
        surface_url(project["id"], room["id"], surface["id"]),
        json={
            "name": "Sufit podwieszany",
            "surface_type": "CEILING",
            "description": None,
        },
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Sufit podwieszany"
    assert response.json()["surface_type"] == "CEILING"
    assert response.json()["description"] is None
    assert response.json()["room_id"] == room["id"]


async def test_archive_surface(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    surface = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
    )

    response = await async_client.post(
        f"{surface_url(project['id'], room['id'], surface['id'])}/archive",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["is_archived"] is True


async def test_restore_surface(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    surface = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
    )
    await async_client.post(
        f"{surface_url(project['id'], room['id'], surface['id'])}/archive",
        headers=auth_header(token),
    )

    response = await async_client.post(
        f"{surface_url(project['id'], room['id'], surface['id'])}/restore",
        headers=auth_header(token),
    )
    list_response = await async_client.get(
        surfaces_url(project["id"], room["id"]),
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["is_archived"] is False
    assert surface["id"] in [item["id"] for item in list_response.json()["items"]]


async def test_surface_cannot_be_accessed_through_another_owned_room(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    first_room = await create_room(async_client, token, project["id"], "Pierwszy")
    second_room = await create_room(async_client, token, project["id"], "Drugi")
    surface = await create_surface(
        async_client,
        token,
        project["id"],
        first_room["id"],
    )
    missing_surface_id = str(uuid.uuid4())

    wrong_room_response = await async_client.get(
        surface_url(project["id"], second_room["id"], surface["id"]),
        headers=auth_header(token),
    )
    missing_response = await async_client.get(
        surface_url(project["id"], second_room["id"], missing_surface_id),
        headers=auth_header(token),
    )

    assert wrong_room_response.status_code == 404
    assert missing_response.status_code == 404
    assert wrong_room_response.json() == missing_response.json() == {
        "detail": "Surface not found"
    }


async def test_foreign_project_is_indistinguishable_from_missing(
    async_client: AsyncClient,
) -> None:
    owner_token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    project = await create_project(async_client, owner_token)
    room = await create_room(async_client, owner_token, project["id"])
    surface = await create_surface(
        async_client,
        owner_token,
        project["id"],
        room["id"],
    )
    missing_project_id = str(uuid.uuid4())

    foreign_responses = [
        await async_client.post(
            surfaces_url(project["id"], room["id"]),
            json={"name": "Niedozwolone", "surface_type": "WALL"},
            headers=auth_header(other_token),
        ),
        await async_client.get(
            surfaces_url(project["id"], room["id"]),
            headers=auth_header(other_token),
        ),
        await async_client.get(
            surface_url(project["id"], room["id"], surface["id"]),
            headers=auth_header(other_token),
        ),
        await async_client.patch(
            surface_url(project["id"], room["id"], surface["id"]),
            json={"name": "Niedozwolona zmiana"},
            headers=auth_header(other_token),
        ),
        await async_client.post(
            f"{surface_url(project['id'], room['id'], surface['id'])}/archive",
            headers=auth_header(other_token),
        ),
        await async_client.post(
            f"{surface_url(project['id'], room['id'], surface['id'])}/restore",
            headers=auth_header(other_token),
        ),
    ]
    missing_responses = [
        await async_client.post(
            surfaces_url(missing_project_id, room["id"]),
            json={"name": "Niedozwolone", "surface_type": "WALL"},
            headers=auth_header(other_token),
        ),
        await async_client.get(
            surfaces_url(missing_project_id, room["id"]),
            headers=auth_header(other_token),
        ),
        await async_client.get(
            surface_url(missing_project_id, room["id"], surface["id"]),
            headers=auth_header(other_token),
        ),
        await async_client.patch(
            surface_url(missing_project_id, room["id"], surface["id"]),
            json={"name": "Niedozwolona zmiana"},
            headers=auth_header(other_token),
        ),
        await async_client.post(
            f"{surface_url(missing_project_id, room['id'], surface['id'])}/archive",
            headers=auth_header(other_token),
        ),
        await async_client.post(
            f"{surface_url(missing_project_id, room['id'], surface['id'])}/restore",
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
    foreign_surface = await create_surface(
        async_client,
        other_token,
        foreign_project["id"],
        foreign_room["id"],
    )
    missing_room_id = str(uuid.uuid4())

    foreign_responses = [
        await async_client.post(
            surfaces_url(project["id"], foreign_room["id"]),
            json={"name": "Niedozwolone", "surface_type": "WALL"},
            headers=auth_header(owner_token),
        ),
        await async_client.get(
            surfaces_url(project["id"], foreign_room["id"]),
            headers=auth_header(owner_token),
        ),
        await async_client.get(
            surface_url(project["id"], foreign_room["id"], foreign_surface["id"]),
            headers=auth_header(owner_token),
        ),
        await async_client.patch(
            surface_url(project["id"], foreign_room["id"], foreign_surface["id"]),
            json={"name": "Niedozwolona zmiana"},
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{surface_url(project['id'], foreign_room['id'], foreign_surface['id'])}/archive",
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{surface_url(project['id'], foreign_room['id'], foreign_surface['id'])}/restore",
            headers=auth_header(owner_token),
        ),
    ]
    missing_responses = [
        await async_client.post(
            surfaces_url(project["id"], missing_room_id),
            json={"name": "Niedozwolone", "surface_type": "WALL"},
            headers=auth_header(owner_token),
        ),
        await async_client.get(
            surfaces_url(project["id"], missing_room_id),
            headers=auth_header(owner_token),
        ),
        await async_client.get(
            surface_url(project["id"], missing_room_id, foreign_surface["id"]),
            headers=auth_header(owner_token),
        ),
        await async_client.patch(
            surface_url(project["id"], missing_room_id, foreign_surface["id"]),
            json={"name": "Niedozwolona zmiana"},
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{surface_url(project['id'], missing_room_id, foreign_surface['id'])}/archive",
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{surface_url(project['id'], missing_room_id, foreign_surface['id'])}/restore",
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


async def test_foreign_surface_is_indistinguishable_from_missing(
    async_client: AsyncClient,
) -> None:
    owner_token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    project = await create_project(async_client, owner_token)
    room = await create_room(async_client, owner_token, project["id"])
    foreign_project = await create_project(async_client, other_token, "Obcy projekt")
    foreign_room = await create_room(
        async_client,
        other_token,
        foreign_project["id"],
    )
    foreign_surface = await create_surface(
        async_client,
        other_token,
        foreign_project["id"],
        foreign_room["id"],
    )
    missing_surface_id = str(uuid.uuid4())

    foreign_responses = [
        await async_client.get(
            surface_url(project["id"], room["id"], foreign_surface["id"]),
            headers=auth_header(owner_token),
        ),
        await async_client.patch(
            surface_url(project["id"], room["id"], foreign_surface["id"]),
            json={"name": "Niedozwolona zmiana"},
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{surface_url(project['id'], room['id'], foreign_surface['id'])}/archive",
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{surface_url(project['id'], room['id'], foreign_surface['id'])}/restore",
            headers=auth_header(owner_token),
        ),
    ]
    missing_responses = [
        await async_client.get(
            surface_url(project["id"], room["id"], missing_surface_id),
            headers=auth_header(owner_token),
        ),
        await async_client.patch(
            surface_url(project["id"], room["id"], missing_surface_id),
            json={"name": "Niedozwolona zmiana"},
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{surface_url(project['id'], room['id'], missing_surface_id)}/archive",
            headers=auth_header(owner_token),
        ),
        await async_client.post(
            f"{surface_url(project['id'], room['id'], missing_surface_id)}/restore",
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
            "detail": "Surface not found"
        }


async def test_invalid_surface_type_is_rejected(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    create_response = await async_client.post(
        surfaces_url(project["id"], room["id"]),
        json={"name": "Nieprawidłowa", "surface_type": "WINDOW"},
        headers=auth_header(token),
    )
    surface = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
    )
    update_response = await async_client.patch(
        surface_url(project["id"], room["id"], surface["id"]),
        json={"surface_type": "CONCRETE"},
        headers=auth_header(token),
    )

    assert create_response.status_code == 422
    assert update_response.status_code == 422
