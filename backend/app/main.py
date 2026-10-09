from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints.area_segments import router as area_segments_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.checklists import router as checklists_router
from app.api.v1.endpoints.clients import router as clients_router
from app.api.v1.endpoints.communications import router as communications_router
from app.api.v1.endpoints.estimates import router as estimates_router
from app.api.v1.endpoints.inspections import router as inspections_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.openings import router as openings_router
from app.api.v1.endpoints.documents import router as documents_router
from app.api.v1.endpoints.executor_profile import router as executor_profile_router
from app.api.v1.endpoints.photos import router as photos_router
from app.api.v1.endpoints.price_coefficients import router as price_coefficients_router
from app.api.v1.endpoints.pricebook import router as pricebook_router
from app.api.v1.endpoints.projects import router as projects_router
from app.api.v1.endpoints.reveal_works import router as reveal_works_router
from app.api.v1.endpoints.risks import router as risks_router
from app.api.v1.endpoints.contract_catalog import router as contract_catalog_router
from app.api.v1.endpoints.adjacent_works import router as adjacent_works_router
from app.api.v1.endpoints.contracts import router as contracts_router
from app.api.v1.endpoints.handovers import router as handovers_router
from app.api.v1.endpoints.project_representatives import router as project_representatives_router
from app.api.v1.endpoints.rooms import router as rooms_router
from app.api.v1.endpoints.surfaces import router as surfaces_router
from app.api.v1.endpoints.work_plans import router as work_plan_router
from app.api.v1.endpoints.work_recommendations import router as work_recommendations_router
from app.api.v1.endpoints.workflow_templates import router as workflow_templates_router
from app.api.upload_guard import sweep_stale_photo_temp
from app.core.config import settings



@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Stage 14C.4: remove photo temp workspaces abandoned by a crash. Never
    # blocks startup (failures are logged inside the sweep).
    sweep_stale_photo_temp(settings.PHOTO_TEMP_DIR, settings.PHOTO_TEMP_STALE_AFTER_SECONDS)
    yield


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

app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(clients_router, prefix="/api", tags=["clients"])
app.include_router(projects_router, prefix="/api", tags=["projects"])
app.include_router(rooms_router, prefix="/api", tags=["rooms"])
app.include_router(project_representatives_router, prefix="/api", tags=["project-representatives"])
app.include_router(adjacent_works_router, prefix="/api", tags=["adjacent-works"])
app.include_router(contracts_router, prefix="/api", tags=["contracts"])
app.include_router(handovers_router, prefix="/api", tags=["handovers"])
app.include_router(contract_catalog_router, prefix="/api", tags=["contract-catalog"])
app.include_router(surfaces_router, prefix="/api", tags=["surfaces"])
app.include_router(openings_router, prefix="/api", tags=["openings"])
app.include_router(area_segments_router, prefix="/api", tags=["area-segments"])
app.include_router(checklists_router, prefix="/api", tags=["checklists"])
app.include_router(inspections_router, prefix="/api", tags=["inspections"])
app.include_router(risks_router, prefix="/api", tags=["risks"])
app.include_router(communications_router, prefix="/api", tags=["communications"])
app.include_router(pricebook_router, prefix="/api", tags=["price-items"])
app.include_router(price_coefficients_router, prefix="/api", tags=["price-coefficients"])
app.include_router(work_plan_router, prefix="/api", tags=["work-plans"])
app.include_router(estimates_router, prefix="/api", tags=["estimates"])
app.include_router(reveal_works_router, prefix="/api", tags=["reveal-works"])
app.include_router(work_recommendations_router, prefix="/api", tags=["work-recommendations"])
app.include_router(workflow_templates_router, prefix="/api", tags=["workflow-templates"])
app.include_router(photos_router, prefix="/api", tags=["photos"])
app.include_router(executor_profile_router, prefix="/api", tags=["executor-profile"])
app.include_router(documents_router, prefix="/api", tags=["documents"])
