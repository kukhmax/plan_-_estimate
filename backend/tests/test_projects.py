import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectStatus
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 333333333,
    "username": "project_owner",
    "first_name": "Project",
    "last_name": "Owner",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 444444444,
    "username": "other_project_owner",
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


def project_payload(name: str = "Mieszkanie Mokotów") -> dict[str, str]:
    return {
        "name": name,
        "address": "ul. Puławska 10/12",
        "city": "Warszawa",
        "postal_code": "02-566",
        "description": "Kompleksowe wykończenie mieszkania",
    }


async def create_client(
    async_client: AsyncClient,
    token: str,
    first_name: str = "Klient",
) -> dict:
    response = await async_client.post(
        "/api/clients",
        json={"client_type": "PRIVATE_PERSON", "first_name": first_name},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_project(
    async_client: AsyncClient,
    token: str,
    name: str = "Projekt",
    client_id: str | None = None,
) -> dict:
    payload = project_payload(name)
    if client_id is not None:
        payload["client_id"] = client_id

    response = await async_client.post(
        "/api/projects",
        json=payload,
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_project_persists_fields(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    payload = project_payload()
    payload["status"] = "IN_PROGRESS"

    response = await async_client.post(
        "/api/projects",
        json=payload,
        headers=auth_header(token),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["address"] == payload["address"]
    assert data["city"] == payload["city"]
    assert data["postal_code"] == payload["postal_code"]
    assert data["description"] == payload["description"]
    assert data["status"] == "IN_PROGRESS"
    assert data["is_archived"] is False
    assert data["client_id"] is None
    assert data["owner_id"]
    assert data["created_at"]
    assert data["updated_at"]

    result = await db_session.execute(
        select(Project).where(Project.id == uuid.UUID(data["id"]))
    )
    project = result.scalar_one()
    assert project.owner_id == uuid.UUID(data["owner_id"])
    assert project.name == payload["name"]
    assert project.address == payload["address"]
    assert project.city == payload["city"]
    assert project.postal_code == payload["postal_code"]
    assert project.description == payload["description"]
    assert project.status == ProjectStatus.IN_PROGRESS
    assert project.client_id is None


async def test_create_project_defaults_to_planning(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)

    project = await create_project(async_client, token)

    assert project["status"] == "PLANNING"


async def test_list_projects_and_archive_filtering(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    active_project = await create_project(async_client, token, "Aktywny")
    archived_project = await create_project(async_client, token, "Archiwalny")
    archive_response = await async_client.post(
        f"/api/projects/{archived_project['id']}/archive",
        headers=auth_header(token),
    )
    assert archive_response.status_code == 200

    active_response = await async_client.get(
        "/api/projects",
        headers=auth_header(token),
    )
    archived_response = await async_client.get(
        "/api/projects?include_archived=true",
        headers=auth_header(token),
    )

    assert active_response.status_code == 200
    assert active_response.json()["total"] == 1
    assert [item["id"] for item in active_response.json()["items"]] == [
        active_project["id"]
    ]
    assert archived_response.status_code == 200
    assert archived_response.json()["total"] == 2
    assert {item["id"] for item in archived_response.json()["items"]} == {
        active_project["id"],
        archived_project["id"],
    }


async def test_read_project(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    created = await create_project(async_client, token, "Odczyt")

    response = await async_client.get(
        f"/api/projects/{created['id']}",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json() == created


async def test_update_project(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    created = await create_project(async_client, token, "Przed zmianą")

    response = await async_client.patch(
        f"/api/projects/{created['id']}",
        json={
            "name": "Po zmianie",
            "description": None,
            "status": "COMPLETED",
        },
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Po zmianie"
    assert data["description"] is None
    assert data["status"] == "COMPLETED"
    assert data["address"] == created["address"]
    assert data["city"] == created["city"]
    assert data["postal_code"] == created["postal_code"]


async def test_create_project_with_client_persists_relationship(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    client = await create_client(async_client, token)

    project = await create_project(
        async_client,
        token,
        "Projekt z klientem",
        client_id=client["id"],
    )
    read_response = await async_client.get(
        f"/api/projects/{project['id']}",
        headers=auth_header(token),
    )
    list_response = await async_client.get(
        "/api/projects",
        headers=auth_header(token),
    )

    assert project["client_id"] == client["id"]
    assert read_response.json()["client_id"] == client["id"]
    assert list_response.json()["items"][0]["client_id"] == client["id"]

    result = await db_session.execute(
        select(Project).where(Project.id == uuid.UUID(project["id"]))
    )
    assert result.scalar_one().client_id == uuid.UUID(client["id"])


async def test_assign_client_to_existing_project(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    client = await create_client(async_client, token)
    project = await create_project(async_client, token)

    response = await async_client.patch(
        f"/api/projects/{project['id']}",
        json={"client_id": client["id"]},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["client_id"] == client["id"]


async def test_change_assigned_client(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    first_client = await create_client(async_client, token, "Pierwszy")
    second_client = await create_client(async_client, token, "Drugi")
    project = await create_project(
        async_client,
        token,
        client_id=first_client["id"],
    )

    response = await async_client.patch(
        f"/api/projects/{project['id']}",
        json={"client_id": second_client["id"]},
        headers=auth_header(token),
    )
    read_response = await async_client.get(
        f"/api/projects/{project['id']}",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["client_id"] == second_client["id"]
    assert read_response.json()["client_id"] == second_client["id"]


async def test_remove_client_association(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    client = await create_client(async_client, token)
    project = await create_project(
        async_client,
        token,
        client_id=client["id"],
    )

    response = await async_client.patch(
        f"/api/projects/{project['id']}",
        json={"client_id": None},
        headers=auth_header(token),
    )
    read_response = await async_client.get(
        f"/api/projects/{project['id']}",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["client_id"] is None
    assert read_response.json()["client_id"] is None


async def test_missing_client_returns_404(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    missing_client_id = str(uuid.uuid4())
    payload = project_payload("Nieprawidłowy klient")
    payload["client_id"] = missing_client_id

    create_response = await async_client.post(
        "/api/projects",
        json=payload,
        headers=auth_header(token),
    )
    project = await create_project(async_client, token)
    update_response = await async_client.patch(
        f"/api/projects/{project['id']}",
        json={"client_id": missing_client_id},
        headers=auth_header(token),
    )

    assert create_response.status_code == 404
    assert update_response.status_code == 404
    assert create_response.json() == update_response.json() == {
        "detail": "Client not found"
    }


async def test_foreign_client_is_indistinguishable_from_missing(
    async_client: AsyncClient,
) -> None:
    owner_token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    foreign_client = await create_client(async_client, other_token, "Obcy")
    project = await create_project(async_client, owner_token)
    missing_client_id = str(uuid.uuid4())
    foreign_payload = project_payload("Obcy klient")
    foreign_payload["client_id"] = foreign_client["id"]

    foreign_create_response = await async_client.post(
        "/api/projects",
        json=foreign_payload,
        headers=auth_header(owner_token),
    )
    foreign_response = await async_client.patch(
        f"/api/projects/{project['id']}",
        json={"client_id": foreign_client["id"]},
        headers=auth_header(owner_token),
    )
    missing_response = await async_client.patch(
        f"/api/projects/{project['id']}",
        json={"client_id": missing_client_id},
        headers=auth_header(owner_token),
    )

    assert foreign_create_response.status_code == 404
    assert foreign_response.status_code == 404
    assert missing_response.status_code == 404
    assert foreign_create_response.json() == foreign_response.json()
    assert foreign_response.json() == missing_response.json() == {
        "detail": "Client not found"
    }


async def test_foreign_project_relationship_update_returns_404(
    async_client: AsyncClient,
) -> None:
    owner_token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    project = await create_project(async_client, owner_token)
    other_client = await create_client(async_client, other_token)

    foreign_project_response = await async_client.patch(
        f"/api/projects/{project['id']}",
        json={"client_id": other_client["id"]},
        headers=auth_header(other_token),
    )
    missing_project_response = await async_client.patch(
        f"/api/projects/{uuid.uuid4()}",
        json={"client_id": other_client["id"]},
        headers=auth_header(other_token),
    )

    assert foreign_project_response.status_code == 404
    assert missing_project_response.status_code == 404
    assert foreign_project_response.json() == missing_project_response.json() == {
        "detail": "Project not found"
    }


async def test_archived_client_remains_assignable(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    client = await create_client(async_client, token, "Archiwalny klient")
    linked_project = await create_project(
        async_client,
        token,
        "Powiązany przed archiwizacją",
        client_id=client["id"],
    )

    archive_response = await async_client.post(
        f"/api/clients/{client['id']}/archive",
        headers=auth_header(token),
    )
    read_response = await async_client.get(
        f"/api/projects/{linked_project['id']}",
        headers=auth_header(token),
    )
    new_project = await create_project(
        async_client,
        token,
        "Powiązany po archiwizacji",
        client_id=client["id"],
    )

    assert archive_response.status_code == 200
    assert read_response.json()["client_id"] == client["id"]
    assert new_project["client_id"] == client["id"]


async def test_archive_project(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    created = await create_project(async_client, token)

    response = await async_client.post(
        f"/api/projects/{created['id']}/archive",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["is_archived"] is True


async def test_restore_project(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    created = await create_project(async_client, token)
    await async_client.post(
        f"/api/projects/{created['id']}/archive",
        headers=auth_header(token),
    )

    response = await async_client.post(
        f"/api/projects/{created['id']}/restore",
        headers=auth_header(token),
    )
    list_response = await async_client.get(
        "/api/projects",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["is_archived"] is False
    assert created["id"] in [item["id"] for item in list_response.json()["items"]]


async def test_owner_isolation_returns_404(async_client: AsyncClient) -> None:
    owner_token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    created = await create_project(async_client, owner_token, "Prywatny projekt")
    project_url = f"/api/projects/{created['id']}"

    list_response = await async_client.get(
        "/api/projects?include_archived=true",
        headers=auth_header(other_token),
    )
    get_response = await async_client.get(project_url, headers=auth_header(other_token))
    update_response = await async_client.patch(
        project_url,
        json={"name": "Niedozwolona zmiana"},
        headers=auth_header(other_token),
    )
    archive_response = await async_client.post(
        f"{project_url}/archive",
        headers=auth_header(other_token),
    )
    restore_response = await async_client.post(
        f"{project_url}/restore",
        headers=auth_header(other_token),
    )

    assert list_response.status_code == 200
    assert list_response.json() == {"items": [], "total": 0}
    assert get_response.status_code == 404
    assert update_response.status_code == 404
    assert archive_response.status_code == 404
    assert restore_response.status_code == 404


async def test_missing_project_returns_404(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    project_id = uuid.uuid4()

    get_response = await async_client.get(
        f"/api/projects/{project_id}",
        headers=auth_header(token),
    )
    update_response = await async_client.patch(
        f"/api/projects/{project_id}",
        json={"name": "Brak"},
        headers=auth_header(token),
    )
    archive_response = await async_client.post(
        f"/api/projects/{project_id}/archive",
        headers=auth_header(token),
    )
    restore_response = await async_client.post(
        f"/api/projects/{project_id}/restore",
        headers=auth_header(token),
    )

    assert get_response.status_code == 404
    assert update_response.status_code == 404
    assert archive_response.status_code == 404
    assert restore_response.status_code == 404


async def test_invalid_project_id_is_rejected(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)

    response = await async_client.get(
        "/api/projects/not-a-uuid",
        headers=auth_header(token),
    )

    assert response.status_code == 422


async def test_invalid_project_status_is_rejected(async_client: AsyncClient) -> None:
    token = await get_token(async_client, VALID_USER)
    payload = project_payload()
    payload["status"] = "ARCHIVED"

    response = await async_client.post(
        "/api/projects",
        json=payload,
        headers=auth_header(token),
    )

    assert response.status_code == 422


async def test_unauthenticated_project_access_is_rejected(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get("/api/projects")

    assert response.status_code == 401
