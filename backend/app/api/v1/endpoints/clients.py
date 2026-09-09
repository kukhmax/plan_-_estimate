import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_client_service, get_current_user
from app.domain.exceptions import ClientNotFoundError
from app.domain.services.client_service import ClientService
from app.models.user import User
from app.schemas.client import ClientCreate, ClientListResponse, ClientRead, ClientUpdate

router = APIRouter()


@router.get(
    "/clients",
    response_model=ClientListResponse,
    status_code=status.HTTP_200_OK,
    summary="List clients for the authenticated owner",
)
async def list_clients(
    include_archived: bool = Query(default=False),
    search: Optional[str] = Query(default=None, max_length=255),
    current_user: User = Depends(get_current_user),
    client_service: ClientService = Depends(get_client_service),
) -> ClientListResponse:
    items, total = await client_service.list_clients(
        owner_user_id=current_user.id,
        include_archived=include_archived,
        search=search,
    )
    return ClientListResponse(
        items=[ClientRead.model_validate(c) for c in items],
        total=total,
    )


@router.post(
    "/clients",
    response_model=ClientRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new client",
)
async def create_client(
    payload: ClientCreate,
    current_user: User = Depends(get_current_user),
    client_service: ClientService = Depends(get_client_service),
) -> ClientRead:
    client = await client_service.create_client(payload, owner_user_id=current_user.id)
    return ClientRead.model_validate(client)


@router.get(
    "/clients/{client_id}",
    response_model=ClientRead,
    status_code=status.HTTP_200_OK,
    summary="Get a specific client by ID",
)
async def get_client(
    client_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    client_service: ClientService = Depends(get_client_service),
) -> ClientRead:
    try:
        client = await client_service.get_client(client_id, owner_user_id=current_user.id)
    except ClientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return ClientRead.model_validate(client)


@router.patch(
    "/clients/{client_id}",
    response_model=ClientRead,
    status_code=status.HTTP_200_OK,
    summary="Partially update a client",
)
async def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    current_user: User = Depends(get_current_user),
    client_service: ClientService = Depends(get_client_service),
) -> ClientRead:
    try:
        client = await client_service.update_client(
            client_id, payload, owner_user_id=current_user.id
        )
    except ClientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return ClientRead.model_validate(client)


@router.post(
    "/clients/{client_id}/archive",
    response_model=ClientRead,
    status_code=status.HTTP_200_OK,
    summary="Archive a client (soft delete)",
)
async def archive_client(
    client_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    client_service: ClientService = Depends(get_client_service),
) -> ClientRead:
    try:
        client = await client_service.archive_client(client_id, owner_user_id=current_user.id)
    except ClientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return ClientRead.model_validate(client)


@router.post(
    "/clients/{client_id}/restore",
    response_model=ClientRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived client",
)
async def restore_client(
    client_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    client_service: ClientService = Depends(get_client_service),
) -> ClientRead:
    try:
        client = await client_service.restore_client(client_id, owner_user_id=current_user.id)
    except ClientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return ClientRead.model_validate(client)
