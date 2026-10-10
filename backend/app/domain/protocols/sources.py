"""What the handover protocol is built from besides its own entries (Stage 16F.2): the object, the customer, the executor, the rooms
and the contract whose requirements apply. Loaded once so the gate and the document see the same data."""
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ProjectNotFoundError
from app.domain.protocols.acceptance import SurfaceFacts, WorkLine
from app.domain.protocols.decision import RiskFacts
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.models.client import Client
from app.models.contract import Contract, ContractStatus
from app.models.executor_profile import ExecutorProfile
from app.models.issued_document import IssuedDocument, IssuedDocumentKind
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from app.models.project import Project
from app.models.risk import Risk
from app.models.room import Room
from app.models.surface import Surface


@dataclass(slots=True)
class HandoverSources:
    project: Project
    client: Client | None
    executor: ExecutorProfile | None
    rooms: tuple[tuple[str, str, bool], ...]  # (id, name, archived) in the order they were added
    contract: Contract | None  # the latest issued or signed one
    contract_number: str | None  # its number in the journal of issued documents

    @property
    def required_values(self) -> dict:
        answers = ((self.contract.snapshot or {}).get("answers") or {}) if self.contract else {}
        return answers.get("premises_requirement_values") or {}


async def load_handover_sources(db: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID) -> HandoverSources:
    """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then)."""
    project = (await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
    if project is None:
        raise ProjectNotFoundError(f"Project {project_id} not found")
    client = (
        (await db.execute(select(Client).where(Client.id == project.client_id, Client.owner_user_id == owner_id))).scalar_one_or_none()
        if project.client_id is not None else None
    )
    executor = await ExecutorProfileService(db).get(owner_id)
    rooms = tuple(
        (str(room.id), room.name, bool(room.is_archived))
        for room in (await db.execute(select(Room).where(Room.project_id == project_id).order_by(Room.created_at, Room.id))).scalars()
    )
    contract = (
        await db.execute(
            select(Contract)
            .where(
                Contract.project_id == project_id, Contract.owner_id == owner_id,
                Contract.status.in_([ContractStatus.ISSUED.value, ContractStatus.SIGNED.value]),
            )
            .order_by(Contract.version.desc()).limit(1)
        )
    ).scalar_one_or_none()
    number = None
    if contract is not None:
        number = (
            await db.execute(
                select(IssuedDocument.number)
                .where(
                    IssuedDocument.owner_id == owner_id, IssuedDocument.kind == IssuedDocumentKind.CONTRACT.value,
                    IssuedDocument.source_id == contract.id,
                )
                .order_by(IssuedDocument.issued_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
    return HandoverSources(project, client, executor, rooms, contract, number)


@dataclass(frozen=True, slots=True)
class SurfaceInfo:
    id: str
    name: str
    room_id: str
    room_name: str
    archived: bool


@dataclass(frozen=True, slots=True)
class PhotoInfo:
    id: str
    caption: str | None
    captured_at: datetime | None
    created_at: datetime


@dataclass(slots=True)
class ConcealedSources:
    base: HandoverSources
    surfaces: dict[str, SurfaceInfo]  # every surface of the object, by id
    photos: dict[str, list[PhotoInfo]]  # the evidence photos (category HIDDEN_WORK, active) of each surface, oldest first


async def load_concealed_sources(db: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID) -> ConcealedSources:
    """Raises ProjectNotFoundError for a project that is not this owner's."""
    base = await load_handover_sources(db, owner_id, project_id)
    surfaces = {
        str(surface.id): SurfaceInfo(str(surface.id), surface.name, str(room.id), room.name, bool(surface.is_archived or room.is_archived))
        for surface, room in (
            await db.execute(select(Surface, Room).join(Room, Room.id == Surface.room_id).where(Room.project_id == project_id).order_by(Room.created_at, Surface.position, Surface.id))
        ).all()
    }
    photos: dict[str, list[PhotoInfo]] = {}
    rows = await db.execute(
        select(PhotoAttachment, PhotoAsset.captured_at)
        .join(PhotoAsset, PhotoAsset.id == PhotoAttachment.asset_id)
        .where(
            PhotoAttachment.project_id == project_id,
            PhotoAttachment.context == PhotoAttachmentContext.SURFACE,
            PhotoAttachment.category == PhotoCategory.HIDDEN_WORK,
            PhotoAttachment.archived_at.is_(None),
        )
        .order_by(PhotoAttachment.created_at, PhotoAttachment.id)
    )
    for attachment, captured_at in rows.all():
        photos.setdefault(str(attachment.surface_id), []).append(
            PhotoInfo(str(attachment.id), attachment.caption, captured_at, attachment.created_at)
        )
    return ConcealedSources(base, surfaces, photos)


@dataclass(slots=True)
class AcceptanceSources:
    base: HandoverSources
    facts: dict[str, SurfaceFacts]  # the surfaces with a plan, by id, in the order of the object
    rooms: tuple[tuple[str, str, int], ...]  # (id, name, number of surfaces with planned works) of the rooms that have any
    defect_photos: dict[str, list[PhotoInfo]]  # the photos of the category DEFECT of each surface, oldest first


async def load_acceptance_sources(db: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID) -> AcceptanceSources:
    """The surfaces of the object with their standard, their planned works and the execution state of each work (Stage 13), plus the
    photos of defects. Raises ProjectNotFoundError for a project that is not this owner's."""
    from app.domain.documents.tech_card_document import _surface_order
    from app.models.price_item import PriceItem
    from app.models.work_execution import SurfaceWorkExecution
    from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
    from app.domain.documents.catalog import localize_description

    base = await load_handover_sources(db, owner_id, project_id)
    room_rows = list(
        (await db.execute(select(Room).where(Room.project_id == project_id, Room.is_archived.is_(False)).order_by(Room.created_at, Room.id))).scalars()
    )
    surfaces = (
        list((await db.execute(select(Surface).where(Surface.room_id.in_([r.id for r in room_rows]), Surface.is_archived.is_(False)))).scalars())
        if room_rows else []
    )
    surfaces.sort(key=_surface_order)
    plans = (
        {p.surface_id: p for p in (await db.execute(select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id.in_([s.id for s in surfaces])))).scalars()}
        if surfaces else {}
    )
    works = (
        list((await db.execute(
            select(SurfacePlannedWork).where(SurfacePlannedWork.work_plan_id.in_([p.id for p in plans.values()]))
            .order_by(SurfacePlannedWork.work_plan_id, SurfacePlannedWork.position)
        )).scalars())
        if plans else []
    )
    items = (
        {i.id: i for i in (await db.execute(select(PriceItem).where(PriceItem.id.in_({w.price_item_id for w in works})))).scalars()}
        if works else {}
    )
    executions = (
        {e.occurrence_key: e for e in (await db.execute(select(SurfaceWorkExecution).where(SurfaceWorkExecution.occurrence_key.in_([w.occurrence_key for w in works])))).scalars()}
        if works else {}
    )
    by_plan: dict[uuid.UUID, list[WorkLine]] = {}
    for work in works:
        item = items[work.price_item_id]
        execution = executions.get(work.occurrence_key)
        by_plan.setdefault(work.work_plan_id, []).append(
            WorkLine(localize_description(item.display_name or item.name_key or item.code), execution.status.value if execution else "NOT_STARTED")
        )
    room_names = {r.id: r.name for r in room_rows}
    facts: dict[str, SurfaceFacts] = {}
    for surface in surfaces:
        plan = plans.get(surface.id)
        facts[str(surface.id)] = SurfaceFacts(
            id=str(surface.id), name=surface.name, room_id=str(surface.room_id), room_name=room_names[surface.room_id],
            surface_type=surface.surface_type.value, quality_target=plan.quality_target.value if plan is not None and plan.quality_target else None,
            works=tuple(by_plan.get(plan.id, ())) if plan is not None else (),
        )
    counts: dict[str, int] = {}
    for f in facts.values():
        if f.works:
            counts[f.room_id] = counts.get(f.room_id, 0) + 1
    rooms = tuple((str(r.id), r.name, counts[str(r.id)]) for r in room_rows if str(r.id) in counts)
    photos: dict[str, list[PhotoInfo]] = {}
    rows = await db.execute(
        select(PhotoAttachment, PhotoAsset.captured_at)
        .join(PhotoAsset, PhotoAsset.id == PhotoAttachment.asset_id)
        .where(
            PhotoAttachment.project_id == project_id, PhotoAttachment.context == PhotoAttachmentContext.SURFACE,
            PhotoAttachment.category == PhotoCategory.DEFECT, PhotoAttachment.archived_at.is_(None),
        )
        .order_by(PhotoAttachment.created_at, PhotoAttachment.id)
    )
    for attachment, captured_at in rows.all():
        photos.setdefault(str(attachment.surface_id), []).append(PhotoInfo(str(attachment.id), attachment.caption, captured_at, attachment.created_at))
    return AcceptanceSources(base, facts, rooms, photos)


@dataclass(slots=True)
class DecisionSources:
    base: HandoverSources
    risks: dict[str, RiskFacts]  # the active risks of the object that may feed a refusal of the guarantee, by id, oldest first
    rooms: tuple[tuple[str, str], ...]  # (id, name) of the active rooms: where a recommendation of the contractor's own may point


async def load_decision_sources(db: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID) -> DecisionSources:
    """The risks the application found in the rooms of the object (active ones that are candidates for a refusal of the guarantee, the
    contract's `executor_recommendations`) next to the usual sources. Raises ProjectNotFoundError for a project that is not this owner's."""
    base = await load_handover_sources(db, owner_id, project_id)
    rooms = tuple((room_id, name) for room_id, name, archived in base.rooms if not archived)
    names = dict(rooms)
    risks: dict[str, RiskFacts] = {}
    if names:
        rows = (
            await db.execute(
                select(Risk)
                .where(Risk.room_id.in_([uuid.UUID(r) for r in names]), Risk.is_active.is_(True), Risk.warranty_exclusion_candidate.is_(True))
                .order_by(Risk.created_at, Risk.id)
            )
        ).scalars()
        for risk in rows:
            risks[str(risk.id)] = RiskFacts(
                id=str(risk.id), room_id=str(risk.room_id), room_name=names[str(risk.room_id)], severity=risk.severity.value,
                title_key=risk.title_key, explanation_key=risk.explanation_key, consequence_key=risk.consequence_key,
                communication_key=risk.communication_key, blocks_finishing=risk.blocks_finishing,
            )
    return DecisionSources(base, risks, rooms)


@dataclass(frozen=True, slots=True)
class DowntimePhoto:
    id: str
    room_id: str | None  # None: a photo of the object as a whole
    room_name: str | None
    caption: str | None
    captured_at: datetime | None
    created_at: datetime


@dataclass(slots=True)
class DowntimeSources:
    base: HandoverSources
    rooms: tuple[tuple[str, str], ...]  # (id, name) of the active rooms
    photos: dict[str, DowntimePhoto]  # the active photos of the object (of the object, its rooms and their surfaces), oldest first

    def allowed(self, room_ids: list[str]) -> list[DowntimePhoto]:
        """The photos that may be chosen for a notice about these rooms: those of the object as a whole and of the rooms (or of every room
        when none is named)."""
        return [p for p in self.photos.values() if not room_ids or p.room_id is None or p.room_id in room_ids]


async def load_downtime_sources(db: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID) -> DowntimeSources:
    """The rooms and the photos a notice of downtime may use, next to the usual sources. Raises ProjectNotFoundError for a project that
    is not this owner's."""
    base = await load_handover_sources(db, owner_id, project_id)
    rooms = tuple((room_id, name) for room_id, name, archived in base.rooms if not archived)
    names = dict(rooms)
    surface_room = {
        str(surface.id): str(surface.room_id)
        for surface in (
            (await db.execute(select(Surface).where(Surface.room_id.in_([uuid.UUID(r) for r in names]), Surface.is_archived.is_(False)))).scalars()
            if names else []
        )
    }
    photos: dict[str, DowntimePhoto] = {}
    rows = await db.execute(
        select(PhotoAttachment, PhotoAsset.captured_at)
        .join(PhotoAsset, PhotoAsset.id == PhotoAttachment.asset_id)
        .where(
            PhotoAttachment.project_id == project_id,
            PhotoAttachment.context.in_([PhotoAttachmentContext.PROJECT, PhotoAttachmentContext.ROOM, PhotoAttachmentContext.SURFACE]),
            PhotoAttachment.archived_at.is_(None),
        )
        .order_by(PhotoAttachment.created_at, PhotoAttachment.id)
    )
    for attachment, captured_at in rows.all():
        if attachment.context == PhotoAttachmentContext.PROJECT:
            room_id = None
        elif attachment.context == PhotoAttachmentContext.ROOM:
            room_id = str(attachment.room_id)
        else:
            room_id = surface_room.get(str(attachment.surface_id))
        if attachment.context != PhotoAttachmentContext.PROJECT and room_id not in names:
            continue  # a photo of an archived room or surface
        photos[str(attachment.id)] = DowntimePhoto(
            str(attachment.id), room_id, names.get(room_id) if room_id else None, attachment.caption, captured_at, attachment.created_at,
        )
    return DowntimeSources(base, rooms, photos)
