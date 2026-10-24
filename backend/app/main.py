from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.upload_guard import sweep_stale_photo_temp
from app.api.v1.endpoints.acceptances import router as acceptances_router
from app.api.v1.endpoints.access import router as access_router
from app.api.v1.endpoints.adjacent_works import router as adjacent_works_router
from app.api.v1.endpoints.archive_structure import router as archive_structure_router
from app.api.v1.endpoints.archived_documents import router as archived_documents_router
from app.api.v1.endpoints.area_segments import router as area_segments_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.calendar import router as calendar_router
from app.api.v1.endpoints.checklists import router as checklists_router
from app.api.v1.endpoints.clients import router as clients_router
from app.api.v1.endpoints.communications import router as communications_router
from app.api.v1.endpoints.concealed_works import router as concealed_works_router
from app.api.v1.endpoints.contract_catalog import router as contract_catalog_router
from app.api.v1.endpoints.contracts import router as contracts_router
from app.api.v1.endpoints.decisions import router as decisions_router
from app.api.v1.endpoints.documents import router as documents_router
from app.api.v1.endpoints.downtimes import router as downtimes_router
from app.api.v1.endpoints.estimates import router as estimates_router
from app.api.v1.endpoints.executor_profile import router as executor_profile_router
from app.api.v1.endpoints.handovers import router as handovers_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.inspections import router as inspections_router
from app.api.v1.endpoints.knowledge import router as knowledge_router
from app.api.v1.endpoints.onboarding import router as onboarding_router
from app.api.v1.endpoints.openings import router as openings_router
from app.api.v1.endpoints.payment_purge import router as payment_purge_router
from app.api.v1.endpoints.payments import router as payments_router
from app.api.v1.endpoints.photo_archive import router as photo_archive_router
from app.api.v1.endpoints.photo_purge import router as photo_purge_router
from app.api.v1.endpoints.photos import router as photos_router
from app.api.v1.endpoints.price_coefficients import router as price_coefficients_router
from app.api.v1.endpoints.pricebook import router as pricebook_router
from app.api.v1.endpoints.project_notes import router as project_notes_router
from app.api.v1.endpoints.project_purge import router as project_purge_router
from app.api.v1.endpoints.project_representatives import (
    router as project_representatives_router,
)
from app.api.v1.endpoints.projects import router as projects_router
from app.api.v1.endpoints.reveal_works import router as reveal_works_router
from app.api.v1.endpoints.risks import router as risks_router
from app.api.v1.endpoints.rooms import router as rooms_router
from app.api.v1.endpoints.structure_purge import router as structure_purge_router
from app.api.v1.endpoints.surfaces import router as surfaces_router
from app.api.v1.endpoints.work_plans import router as work_plan_router
from app.api.v1.endpoints.work_recommendations import (
    router as work_recommendations_router,
)
from app.api.v1.endpoints.workflow_templates import router as workflow_templates_router
from app.core.config import settings
from app.core.data_crypto import DataCryptoError
from app.core.database import async_session_maker
from app.core.startup_checks import ensure_production_configuration
from app.domain.calendar.messages import load_texts
from app.domain.exceptions import ClientIdConflictError
from app.domain.knowledge.catalog import load_knowledge_catalog
from app.domain.services.calendar_dispatcher import start_dispatcher
from app.domain.services.data_key_service import DataKeyService


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Stage 14C.4: remove photo temp workspaces abandoned by a crash. Never
    # blocks startup (failures are logged inside the sweep).
    sweep_stale_photo_temp(settings.PHOTO_TEMP_DIR, settings.PHOTO_TEMP_STALE_AFTER_SECONDS)
    # Stage 17B: a wrong file of the knowledge base stops the start instead of serving guessed content.
    load_knowledge_catalog()
    # Stage 18D: the texts of the reminders are a file like the knowledge base: a wrong one stops the start.
    load_texts()
    # EN-2a: the personal data of the clients is encrypted; production does not start without the key of the server, and a wrong key stops
    # the start at once (the keys already in the database are unwrapped here) instead of failing at the first request.
    if settings.is_production and not settings.DATA_KEK.get_secret_value().strip():
        raise RuntimeError("DATA_KEK is not set: production does not start without the key that protects the data of the clients")
    # Stage 20E: production does not start with a weak session secret, a wrong bot token, mock sign-in or debug on.
    ensure_production_configuration(settings)
    async with async_session_maker() as db:
        await DataKeyService(db).prepare()
    # Stage 18D: the loop that sends the reminders; off unless CALENDAR_DISPATCHER_ENABLED, and not started without a bot token.
    loop = start_dispatcher(settings, async_session_maker)
    try:
        yield
    finally:
        if loop is not None:
            await loop.stop()


app = FastAPI(
    title="Plan & Estimate API",
    description="Backend API for Telegram Mini App - Renovation & Finishing Management",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.exception_handler(ClientIdConflictError)
async def client_id_conflict_handler(_request: Request, exc: ClientIdConflictError) -> JSONResponse:
    """An id chosen by the phone (Stage 19C) is taken by another record: the phone moves the operation to "needs attention"."""
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": {"code": exc.code, "message": str(exc)}})


@app.exception_handler(DataCryptoError)
async def data_crypto_error_handler(_request: Request, exc: DataCryptoError) -> JSONResponse:
    """EN-2a: a value that does not decrypt, or a key that is not loaded, is a structured error with a code and never a value or a key."""
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": {"code": exc.code, "message": exc.code}})


app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(access_router, prefix="/api", tags=["access"])
app.include_router(clients_router, prefix="/api", tags=["clients"])
app.include_router(projects_router, prefix="/api", tags=["projects"])
app.include_router(rooms_router, prefix="/api", tags=["rooms"])
app.include_router(project_representatives_router, prefix="/api", tags=["project-representatives"])
app.include_router(adjacent_works_router, prefix="/api", tags=["adjacent-works"])
app.include_router(contracts_router, prefix="/api", tags=["contracts"])
app.include_router(handovers_router, prefix="/api", tags=["handovers"])
app.include_router(concealed_works_router, prefix="/api", tags=["concealed-works"])
app.include_router(acceptances_router, prefix="/api", tags=["acceptances"])
app.include_router(decisions_router, prefix="/api", tags=["decisions"])
app.include_router(downtimes_router, prefix="/api", tags=["downtimes"])
app.include_router(contract_catalog_router, prefix="/api", tags=["contract-catalog"])
app.include_router(surfaces_router, prefix="/api", tags=["surfaces"])
app.include_router(openings_router, prefix="/api", tags=["openings"])
app.include_router(area_segments_router, prefix="/api", tags=["area-segments"])
app.include_router(checklists_router, prefix="/api", tags=["checklists"])
app.include_router(inspections_router, prefix="/api", tags=["inspections"])
app.include_router(risks_router, prefix="/api", tags=["risks"])
app.include_router(communications_router, prefix="/api", tags=["communications"])
app.include_router(pricebook_router, prefix="/api", tags=["price-items"])
app.include_router(onboarding_router, prefix="/api", tags=["onboarding"])
app.include_router(price_coefficients_router, prefix="/api", tags=["price-coefficients"])
app.include_router(work_plan_router, prefix="/api", tags=["work-plans"])
app.include_router(estimates_router, prefix="/api", tags=["estimates"])
app.include_router(reveal_works_router, prefix="/api", tags=["reveal-works"])
app.include_router(work_recommendations_router, prefix="/api", tags=["work-recommendations"])
app.include_router(workflow_templates_router, prefix="/api", tags=["workflow-templates"])
app.include_router(photos_router, prefix="/api", tags=["photos"])
app.include_router(archive_structure_router, prefix="/api", tags=["archive"])
app.include_router(payments_router, prefix="/api", tags=["payments"])
app.include_router(payment_purge_router, prefix="/api", tags=["archive"])
app.include_router(archived_documents_router, prefix="/api", tags=["archive"])
app.include_router(photo_archive_router, prefix="/api", tags=["photo-archive"])
app.include_router(photo_purge_router, prefix="/api", tags=["photo-purge"])
app.include_router(project_purge_router, prefix="/api", tags=["project-purge"])
app.include_router(structure_purge_router, prefix="/api", tags=["structure-purge"])
app.include_router(executor_profile_router, prefix="/api", tags=["executor-profile"])
app.include_router(documents_router, prefix="/api", tags=["documents"])
app.include_router(knowledge_router, prefix="/api", tags=["knowledge"])
app.include_router(calendar_router, prefix="/api", tags=["calendar"])
app.include_router(project_notes_router, prefix="/api", tags=["project-notes"])
