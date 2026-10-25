"""The norms, the calculations and the statement of materials (V2-11): thin routes over `MaterialsService`. Online only; owner-scoped."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError

from app.api.deps import get_current_user, get_materials_service
from app.domain.data.material_norms import BY_CODE
from app.domain.exceptions import (
    EstimateNotFoundError,
    EstimateStateError,
    MaterialInvalidError,
    MaterialNotFoundError,
    ProjectNotFoundError,
)
from app.domain.services.materials_service import (
    CalcView,
    MaterialsService,
    NormView,
    Statement,
)
from app.models.user import User
from app.schemas.material import (
    AddMaterialsResponse,
    CalcCreate,
    CalcRead,
    CalcsResponse,
    CalcUpdate,
    MaterialRead,
    NormRead,
    NormsResponse,
    NormUpdate,
    StatementCalc,
    StatementResponse,
    TotalRead,
)
from app.schemas.room_point import PointItemRead

router = APIRouter()

FAILURES = (ProjectNotFoundError, MaterialNotFoundError, MaterialInvalidError, EstimateNotFoundError, EstimateStateError, ValidationError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MaterialNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if isinstance(exc, EstimateNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Estimate not found")
    if isinstance(exc, MaterialInvalidError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, ValidationError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "CALC_INVALID", "message": "the data of the calculation are not valid"})
    if isinstance(exc, EstimateStateError):
        return HTTPException(status.HTTP_409_CONFLICT, detail={"code": "ESTIMATE_NOT_DRAFT", "message": str(exc)})
    return HTTPException(status.HTTP_404_NOT_FOUND, "Room not found")


def _material(view) -> MaterialRead:
    qty = view.qty
    return MaterialRead(
        code=qty.code, name=view.name, quantity=qty.quantity, unit_text=qty.unit_text, pack_size=qty.pack_size, packs=view.packs, pieces=qty.pieces,
        billing_unit=view.billing_unit, billing_quantity=view.billing_quantity,
    )


def _calc(view: CalcView) -> CalcRead:
    row = view.row
    return CalcRead(
        id=row.id, room_id=row.room_id, package=row.package, title=row.title, params=row.params, materials=[_material(m) for m in view.materials],
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _norm(view: NormView) -> NormRead:
    row, item = view.row, view.item
    definition = BY_CODE[row.code]
    return NormRead(
        id=row.id, code=row.code, package=row.package, kind=row.kind, name=row.name, default_name=definition.name, unit_text=definition.unit_text, value=row.value, default_value=definition.default,
        minimum=definition.minimum if definition.default is not None else None, maximum=definition.maximum if definition.default is not None else None,
        billing_unit=definition.billing_unit,
        price_item=PointItemRead(
            id=item.id, code=item.code, name_key=item.name_key, display_name=item.display_name, category=item.category, unit=item.unit, price=item.price, is_archived=item.is_archived
        ) if item is not None else None,
    )


def _statement(found: Statement) -> StatementResponse:
    totals = []
    for entry in found.totals:
        total = entry.total
        totals.append(TotalRead(
            code=total.code, name=entry.name, quantity=total.quantity, unit_text=total.unit_text, pack_size=total.pack_size, packs=total.packs, pieces=total.pieces,
            billing_unit=entry.billing_unit, billing_quantity=total.billing_quantity, package=entry.package, price_item_id=entry.price_item_id, unit_price=entry.unit_price, amount=entry.amount,
        ))
    calcs = []
    for view, room_name in found.calcs:
        base = _calc(view)
        calcs.append(StatementCalc(**base.model_dump(), room_name=room_name))
    return StatementResponse(calcs=calcs, totals=totals, amount=found.amount, unpriced=found.unpriced)


@router.get("/material-norms", response_model=NormsResponse, summary="The owner's consumption norms (made from the starting ones on first use)")
async def list_norms(current_user: User = Depends(get_current_user), service: MaterialsService = Depends(get_materials_service)) -> NormsResponse:
    return NormsResponse(items=[_norm(v) for v in await service.list_norms(current_user.id)])


@router.patch("/material-norms/{norm_id}", response_model=NormRead, summary="Change a norm: a number, or the name and the price item of a material; or return it to the starting one")
async def update_norm(
    norm_id: uuid.UUID,
    payload: NormUpdate,
    current_user: User = Depends(get_current_user),
    service: MaterialsService = Depends(get_materials_service),
) -> NormRead:
    try:
        return _norm(await service.update_norm(current_user.id, norm_id, payload.model_dump(exclude_unset=True)))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.get("/projects/{project_id}/rooms/{room_id}/material-calcs", response_model=CalcsResponse, summary="The calculations of materials of a room, with what each needs")
async def list_calcs(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: MaterialsService = Depends(get_materials_service),
) -> CalcsResponse:
    try:
        return CalcsResponse(items=[_calc(v) for v in await service.list_calcs(current_user.id, project_id, room_id)])
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post("/projects/{project_id}/rooms/{room_id}/material-calcs", response_model=CalcRead, status_code=status.HTTP_201_CREATED, summary="Add a calculation of materials to a room")
async def create_calc(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: CalcCreate,
    current_user: User = Depends(get_current_user),
    service: MaterialsService = Depends(get_materials_service),
) -> CalcRead:
    try:
        view = await service.create_calc(current_user.id, project_id, room_id, payload.package, payload.title, payload.params.model_dump(mode="json"))
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return _calc(view)


@router.patch("/projects/{project_id}/rooms/{room_id}/material-calcs/{calc_id}", response_model=CalcRead, summary="Change a calculation of materials")
async def update_calc(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    calc_id: uuid.UUID,
    payload: CalcUpdate,
    current_user: User = Depends(get_current_user),
    service: MaterialsService = Depends(get_materials_service),
) -> CalcRead:
    try:
        return _calc(await service.change_calc(current_user.id, project_id, room_id, calc_id, payload.model_dump(exclude_unset=True)))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.delete("/projects/{project_id}/rooms/{room_id}/material-calcs/{calc_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a calculation of materials")
async def delete_calc(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    calc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: MaterialsService = Depends(get_materials_service),
) -> Response:
    try:
        await service.delete_calc(current_user.id, project_id, room_id, calc_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/materials", response_model=StatementResponse, summary="The statement of materials of an object: the totals by material (packs over the sum) and the calculations")
async def get_statement(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: MaterialsService = Depends(get_materials_service),
) -> StatementResponse:
    try:
        return _statement(await service.statement(current_user.id, project_id))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post(
    "/projects/{project_id}/estimates/{estimate_id}/add-materials", response_model=AddMaterialsResponse,
    summary="Add the materials of the object to a draft estimate (a snapshot; what is in it already is not added twice)",
)
async def add_materials_to_estimate(
    project_id: uuid.UUID,
    estimate_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: MaterialsService = Depends(get_materials_service),
) -> AddMaterialsResponse:
    try:
        found = await service.add_to_estimate(current_user.id, project_id, estimate_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return AddMaterialsResponse(added=len(found.added), already=found.already, skipped=found.skipped)
