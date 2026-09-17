"""Estimate HTTP API (Stage 10E).

Thin owner-scoped controller: auth → input validation → service → typed
response. All domain rules live in EstimateService; this module only maps
domain exceptions to HTTP error shapes (404 for missing/foreign rows, 422 for
domain state/validation failures).

Ownership is always derived from the authenticated user — owner_id is never
trusted from request body or query parameters.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

import dataclasses

from app.api.deps import get_current_user, get_estimate_service
from app.domain.exceptions import (
    EstimateDraftExistsError,
    EstimateNotFoundError,
    EstimateStateError,
    EstimateValidationError,
    ProjectNotFoundError,
)
from app.domain.services.estimate_service import EstimateService
from app.models.user import User
from app.schemas.estimate import (
    EstimateLineRead,
    EstimateLineUpdate,
    EstimateListResponse,
    EstimateRead,
    EstimateSummaryRead,
    LineChangeEntryRead,
    ManualLineCreate,
    RegenerationPreviewResponse,
)

router = APIRouter()

_404_project = "Project not found"
_404_estimate = "Estimate not found"
_404_line = "Line not found"


def _est_prefix(project_id: uuid.UUID) -> str:
    return f"/projects/{project_id}/estimates"


def _regen_response(result) -> RegenerationPreviewResponse:
    """Convert a RegenerationResult dataclass to the HTTP response schema."""
    changes = [
        LineChangeEntryRead(**dataclasses.asdict(c))
        for c in result.changes
    ]
    return RegenerationPreviewResponse(
        added=result.added,
        removed=result.removed,
        updated=result.updated,
        preserved_manual=result.preserved_manual,
        changes=changes,
    )


# ---------------------------------------------------------------------------
# A. List estimates for project
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/estimates",
    response_model=EstimateListResponse,
    status_code=status.HTTP_200_OK,
    summary="List estimates for a project",
)
async def list_estimates(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> EstimateListResponse:
    try:
        estimates = await service.list_estimates(project_id, current_user.id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_project)
    return EstimateListResponse(
        items=[EstimateSummaryRead.model_validate(e) for e in estimates],
        total=len(estimates),
    )


# ---------------------------------------------------------------------------
# B. Get one estimate with ordered lines
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/estimates/{estimate_id}",
    response_model=EstimateRead,
    status_code=status.HTTP_200_OK,
    summary="Get estimate detail with ordered lines",
)
async def get_estimate(
    project_id: uuid.UUID,
    estimate_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> EstimateRead:
    try:
        estimate = await service.get_estimate_detail(
            project_id, estimate_id, current_user.id
        )
    except (EstimateNotFoundError, ProjectNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_estimate)
    return EstimateRead.model_validate(estimate)


# ---------------------------------------------------------------------------
# C. Generate initial DRAFT
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/estimates/generate",
    response_model=EstimateRead,
    status_code=status.HTTP_200_OK,
    summary="Generate or refresh the project DRAFT estimate",
)
async def generate_estimate(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> EstimateRead:
    try:
        estimate = await service.generate_estimate(project_id, current_user.id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_project)
    except EstimateDraftExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    return EstimateRead.model_validate(estimate)


# ---------------------------------------------------------------------------
# D. Regeneration preview (NO mutation)
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/estimates/{estimate_id}/regenerate-preview",
    response_model=RegenerationPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview what regeneration would change (read-only, no mutation)",
)
async def regenerate_preview(
    project_id: uuid.UUID,
    estimate_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> RegenerationPreviewResponse:
    try:
        result = await service.preview_regeneration(
            project_id, estimate_id, current_user.id
        )
    except (EstimateNotFoundError, ProjectNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_estimate)
    except EstimateStateError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return _regen_response(result)


# ---------------------------------------------------------------------------
# E. Confirm draft regeneration (mutates DRAFT)
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/estimates/{estimate_id}/regenerate",
    response_model=RegenerationPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm DRAFT regeneration — re-derives planned lines in-place",
)
async def regenerate_confirm(
    project_id: uuid.UUID,
    estimate_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> RegenerationPreviewResponse:
    try:
        result = await service.regenerate_draft(
            estimate_id, current_user.id, project_id=project_id
        )
    except (EstimateNotFoundError, ProjectNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_estimate)
    except EstimateStateError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return _regen_response(result)


# ---------------------------------------------------------------------------
# F. Add manual line
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/estimates/{estimate_id}/lines",
    response_model=EstimateLineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Append a MANUAL line to a DRAFT estimate",
)
async def add_manual_line(
    project_id: uuid.UUID,
    estimate_id: uuid.UUID,
    payload: ManualLineCreate,
    current_user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> EstimateLineRead:
    try:
        line = await service.add_manual_line(
            estimate_id,
            current_user.id,
            description=payload.description,
            scope=payload.scope,
            unit=payload.unit,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            currency=payload.currency,
            project_id=project_id,
        )
    except (EstimateNotFoundError, ProjectNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_estimate)
    except EstimateStateError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except EstimateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return EstimateLineRead.model_validate(line)


# ---------------------------------------------------------------------------
# G. Update editable draft line (quantity / price overrides, MANUAL description)
# ---------------------------------------------------------------------------

@router.patch(
    "/projects/{project_id}/estimates/{estimate_id}/lines/{line_id}",
    response_model=EstimateLineRead,
    status_code=status.HTTP_200_OK,
    summary="Update owner-controlled fields on a DRAFT estimate line",
)
async def patch_line(
    project_id: uuid.UUID,
    estimate_id: uuid.UUID,
    line_id: uuid.UUID,
    payload: EstimateLineUpdate,
    current_user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> EstimateLineRead:
    try:
        line = await service.patch_line(
            project_id,
            estimate_id,
            current_user.id,
            line_id,
            provided_fields=payload.model_fields_set,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            description=payload.description,
            reset_price_override=payload.reset_price_override,
            reset_quantity_override=payload.reset_quantity_override,
        )
    except (EstimateNotFoundError, ProjectNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_line)
    except EstimateStateError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except EstimateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return EstimateLineRead.model_validate(line)


# ---------------------------------------------------------------------------
# H. Delete manual line
# ---------------------------------------------------------------------------

@router.delete(
    "/projects/{project_id}/estimates/{estimate_id}/lines/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a MANUAL line from a DRAFT estimate",
)
async def delete_line(
    project_id: uuid.UUID,
    estimate_id: uuid.UUID,
    line_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> None:
    try:
        await service.delete_manual_line(
            project_id, estimate_id, current_user.id, line_id
        )
    except (EstimateNotFoundError, ProjectNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_line)
    except EstimateStateError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except EstimateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )


# ---------------------------------------------------------------------------
# I. Finalize — DRAFT → FINAL
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/estimates/{estimate_id}/finalize",
    response_model=EstimateRead,
    status_code=status.HTTP_200_OK,
    summary="Finalize a DRAFT estimate (DRAFT → FINAL)",
)
async def finalize_estimate(
    project_id: uuid.UUID,
    estimate_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> EstimateRead:
    try:
        estimate = await service.finalize(
            estimate_id, current_user.id, project_id=project_id
        )
    except (EstimateNotFoundError, ProjectNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_404_estimate)
    except EstimateStateError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except EstimateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return EstimateRead.model_validate(estimate)
