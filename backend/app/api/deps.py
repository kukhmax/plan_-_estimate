from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.upload_guard import MAX_CONCURRENT_UPLOAD_REQUESTS, UploadAdmission
from app.core.config import settings
from app.core.database import get_db
from app.core.s3_media_storage import create_media_storage
from app.core.security import decode_access_token
from app.domain.photos.image_processing import ImagePipelineConfig, ImageProcessor
from app.domain.services.area_segment_service import AreaSegmentService
from app.domain.services.auth_service import TelegramAuthService
from app.domain.services.checklist_service import ChecklistService
from app.domain.services.client_service import ClientService
from app.domain.services.communication_service import CommunicationService
from app.domain.services.estimate_service import EstimateService
from app.domain.services.inspection_service import InspectionService
from app.domain.services.media_storage import MediaStorage
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.domain.services.opening_service import OpeningService
from app.domain.services.price_book_service import PriceBookService
from app.domain.services.price_coefficient_service import PriceCoefficientService
from app.domain.services.project_service import ProjectService
from app.domain.services.risk_service import RiskService
from app.domain.services.adjacent_work_service import AdjacentWorkService
from app.domain.services.contract_service import ContractService
from app.domain.services.handover_service import HandoverService
from app.domain.services.project_representative_service import ProjectRepresentativeService
from app.domain.services.room_service import RoomService
from app.domain.services.surface_service import SurfaceService
from app.domain.services.work_execution_service import SurfaceWorkExecutionService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.domain.services.work_recommendation_service import WorkRecommendationService
from app.domain.services.workflow_template_service import WorkflowTemplateService
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "MISSING_TOKEN", "message": "Authentication credentials required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = decode_access_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": str(e)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User not found or deactivated"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_auth_service(
    db: AsyncSession = Depends(get_db),
) -> TelegramAuthService:
    return TelegramAuthService(db)


async def get_client_service(
    db: AsyncSession = Depends(get_db),
) -> ClientService:
    return ClientService(db)


async def get_project_service(
    db: AsyncSession = Depends(get_db),
) -> ProjectService:
    return ProjectService(db)


async def get_room_service(
    db: AsyncSession = Depends(get_db),
) -> RoomService:
    return RoomService(db)


async def get_project_representative_service(
    db: AsyncSession = Depends(get_db),
) -> ProjectRepresentativeService:
    return ProjectRepresentativeService(db)


async def get_adjacent_work_service(
    db: AsyncSession = Depends(get_db),
) -> AdjacentWorkService:
    return AdjacentWorkService(db)


async def get_contract_service(
    db: AsyncSession = Depends(get_db),
) -> ContractService:
    return ContractService(db)


async def get_handover_service(
    db: AsyncSession = Depends(get_db),
) -> HandoverService:
    return HandoverService(db)


async def get_surface_service(
    db: AsyncSession = Depends(get_db),
) -> SurfaceService:
    return SurfaceService(db)


async def get_opening_service(
    db: AsyncSession = Depends(get_db),
) -> OpeningService:
    return OpeningService(db)


async def get_area_segment_service(
    db: AsyncSession = Depends(get_db),
) -> AreaSegmentService:
    return AreaSegmentService(db)


async def get_checklist_service(
    db: AsyncSession = Depends(get_db),
) -> ChecklistService:
    return ChecklistService(db)


async def get_inspection_service(
    db: AsyncSession = Depends(get_db),
) -> InspectionService:
    return InspectionService(db)


async def get_risk_service(
    db: AsyncSession = Depends(get_db),
) -> RiskService:
    return RiskService(db)


async def get_communication_service(
    db: AsyncSession = Depends(get_db),
) -> CommunicationService:
    return CommunicationService(db)


async def get_price_book_service(
    db: AsyncSession = Depends(get_db),
) -> PriceBookService:
    return PriceBookService(db)


async def get_price_coefficient_service(
    db: AsyncSession = Depends(get_db),
) -> PriceCoefficientService:
    return PriceCoefficientService(db)


async def get_work_plan_service(
    db: AsyncSession = Depends(get_db),
) -> SurfaceWorkPlanService:
    return SurfaceWorkPlanService(db)


async def get_work_execution_service(
    db: AsyncSession = Depends(get_db),
) -> SurfaceWorkExecutionService:
    return SurfaceWorkExecutionService(db)


async def get_workflow_template_service(
    db: AsyncSession = Depends(get_db),
) -> WorkflowTemplateService:
    return WorkflowTemplateService(db)


async def get_work_recommendation_service(
    db: AsyncSession = Depends(get_db),
) -> WorkRecommendationService:
    return WorkRecommendationService(db)


async def get_estimate_service(
    db: AsyncSession = Depends(get_db),
) -> EstimateService:
    return EstimateService(db)


async def get_reveal_work_service(
    db: AsyncSession = Depends(get_db),
) -> OpeningRevealWorkService:
    return OpeningRevealWorkService(db)


@dataclass
class PhotoRuntime:
    """Process-wide photo upload resources (Stage 14C.4). One instance per
    process so the processing slot and the upload admission limit are
    shared by every request."""

    processor: ImageProcessor
    storage: MediaStorage
    admission: UploadAdmission


_photo_runtime: PhotoRuntime | None = None


def get_photo_runtime() -> PhotoRuntime:
    """Created on first use from the validated settings; the storage client
    itself connects lazily. Tests override this dependency."""
    global _photo_runtime
    if _photo_runtime is None:
        _photo_runtime = PhotoRuntime(
            processor=ImageProcessor(
                ImagePipelineConfig.from_settings(settings),
                wait_seconds=settings.PHOTO_PROCESSING_WAIT_SECONDS,
            ),
            storage=create_media_storage(settings),
            admission=UploadAdmission(MAX_CONCURRENT_UPLOAD_REQUESTS),
        )
    return _photo_runtime


_document_issuer = None


def get_document_issuer():
    """The process-wide document issuer (Stage 15F): one renderer (one render at a time), one delivery, the photo store.
    Created on first use from the validated settings; tests override this dependency."""
    from app.core.database import async_session_maker
    from app.domain.documents.delivery import delivery_from_settings
    from app.domain.documents.issuer import DocumentIssuer
    from app.domain.documents.renderer import renderer_from_settings

    global _document_issuer
    if _document_issuer is None:
        _document_issuer = DocumentIssuer(
            session_factory=async_session_maker,
            renderer=renderer_from_settings(settings),
            delivery=delivery_from_settings(settings),
            storage=lambda: get_photo_runtime().storage,
            storage_name=settings.MEDIA_STORAGE_NAME,
            max_photos=settings.DOCUMENT_MAX_PHOTOS,
            max_active=settings.DOCUMENT_MAX_ACTIVE,
        )
    return _document_issuer
