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


async def create_project(async_client: AsyncClient, token: str, name: str = "Projekt") -> dict:
    response = await async_client.post(
        "/api/projects",
        json=project_payload(name),
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
