"""The points and routes of a room and their addition to an estimate (V2-10): thin routes over `RoomPointsService`. Online only; owner-scoped."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_user, get_room_points_service
from app.domain.exceptions import (
    EstimateNotFoundError,
    EstimateStateError,
    ProjectNotFoundError,
    RoomPointInvalidError,
    RoomPointNotFoundError,
)
from app.domain.services.room_points_service import PointView, RoomPointsService
from app.models.user import User
from app.schemas.room_point import (
    AddToEstimateResponse,
    PointCountsResponse,
    PointCreate,
    PointItemRead,
    PointRead,
    PointsResponse,
    PointUpdate,
    RoomPointCount,
    SkippedPoint,
)

router = APIRouter()

FAILURES = (ProjectNotFoundError, RoomPointNotFoundError, RoomPointInvalidError, EstimateNotFoundError, EstimateStateError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RoomPointNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Point not found")
    if isinstance(exc, EstimateNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Estimate not found")
    if isinstance(exc, RoomPointInvalidError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, EstimateStateError):
        return HTTPException(status.HTTP_409_CONFLICT, detail={"code": "ESTIMATE_NOT_DRAFT", "message": str(exc)})
    return HTTPException(status.HTTP_404_NOT_FOUND, "Room not found")


def _read(view: PointView) -> PointRead:
    row, item = view.row, view.item
    return PointRead(
        id=row.id, room_id=row.room_id, quantity=row.quantity, note=row.note, source=row.source, created_at=row.created_at, updated_at=row.updated_at,
        item=PointItemRead(
            id=item.id, code=item.code, name_key=item.name_key, display_name=item.display_name, category=item.category, unit=item.unit, price=item.price,
            is_archived=item.is_archived,
        ),
    )


@router.get("/projects/{project_id}/room-points/summary", response_model=PointCountsResponse, summary="How many points and routes each room of an object has")
async def point_counts(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: RoomPointsService = Depends(get_room_points_service),
) -> PointCountsResponse:
    try:
        counts = await service.count_by_room(current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return PointCountsResponse(items=[RoomPointCount(room_id=room_id, count=count) for room_id, count in counts.items()])


@router.get("/projects/{project_id}/rooms/{room_id}/points", response_model=PointsResponse, summary="The points and routes of a room")
async def list_points(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: RoomPointsService = Depends(get_room_points_service),
) -> PointsResponse:
    try:
        views = await service.list_points(current_user.id, project_id, room_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return PointsResponse(items=[_read(v) for v in views])


@router.post("/projects/{project_id}/rooms/{room_id}/points", response_model=PointRead, status_code=status.HTTP_201_CREATED, summary="Add a point or a route to a room")
async def create_point(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: PointCreate,
    current_user: User = Depends(get_current_user),
    service: RoomPointsService = Depends(get_room_points_service),
) -> PointRead:
    try:
        return _read(await service.create(current_user.id, project_id, room_id, payload.model_dump()))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.patch("/projects/{project_id}/rooms/{room_id}/points/{point_id}", response_model=PointRead, summary="Change a point or a route")
async def update_point(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    point_id: uuid.UUID,
    payload: PointUpdate,
    current_user: User = Depends(get_current_user),
    service: RoomPointsService = Depends(get_room_points_service),
) -> PointRead:
    try:
        return _read(await service.change(current_user.id, project_id, room_id, point_id, payload.model_dump(exclude_unset=True)))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.delete("/projects/{project_id}/rooms/{room_id}/points/{point_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a point or a route")
async def delete_point(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    point_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: RoomPointsService = Depends(get_room_points_service),
) -> Response:
    try:
        await service.delete(current_user.id, project_id, room_id, point_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/estimates/{estimate_id}/add-points", response_model=AddToEstimateResponse,
    summary="Add the points and routes of the object to a draft estimate (a snapshot; what is in it already is not added twice)",
)
async def add_points_to_estimate(
    project_id: uuid.UUID,
    estimate_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: RoomPointsService = Depends(get_room_points_service),
) -> AddToEstimateResponse:
    try:
        found = await service.add_to_estimate(current_user.id, project_id, estimate_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return AddToEstimateResponse(added=len(found.added), already=found.already, skipped=[SkippedPoint(point_id=pid, code=code) for pid, code in found.skipped])
