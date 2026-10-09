"""The technological card (Karta technologiczna) as a document (Stage 16C).

For every room and surface of an object the card says: what the substrate is, which finishing standard is agreed, what the
inspection found (the answered checklist and the risks) and which works will be done, in their order, with the technological
break after each. It carries **no prices** (they are the estimate's) and **no wording of obligations** -- it is the technical
basis that the work production plan, the estimate and the contract refer to.

Two forms of one document:

* **issued** (`working=False`): numbered, journalled, without a watermark. It is refused with a stable code while the data are
  not there (a surface with works needs an agreed standard and a finished inspection), so a numbered card is always complete;
* **working** (`working=True`): a draft with the "WERSJA ROBOCZA" watermark, no number, no journal row. It never refuses for
  missing data: every missing value prints as an empty line to write in by hand, so the owner can print it before the
  inspection is done and talk it through with the customer. An object with no rooms yet gets a blank room with blank surfaces.

Read-only and owner scoped; the number of SQL statements does not depend on the number of rooms or surfaces. All words are
Polish labels (`locales/pl.json`); the data (names, answers, risks) come from the database through the same catalogues as the
photo report.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents import formatting
from app.domain.documents.catalog import localize_description
from app.domain.documents.estimate_document import object_lines, party_from_client
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.photo_report_document import InspectionView, inspection_view
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.renderer import DocumentRenderer, RenderedPdf
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.domain.services.inspection_report_read_model import InspectionInfo, InspectionReportReadModel
from app.domain.services.project_service import ProjectService
from app.models.client import Client
from app.models.estimate import Estimate, EstimateLine, EstimateStatus
from app.models.executor_profile import ExecutorProfile
from app.models.price_item import PriceItem
from app.models.project import Project
from app.models.surface import Surface
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan

BLANK_SURFACES = 3  # surfaces of the blank room printed for an object that has no rooms yet
SPARE_ROWS = 4  # empty rows a working version leaves under the works of a surface (and the whole table of a blank one)

# what a surface lacks for a numbered card (`details` of TECH_CARD_INCOMPLETE; the screen has a sentence for each)
MISSING_QUALITY_TARGET = "QUALITY_TARGET"
MISSING_INSPECTION = "INSPECTION"

_CANONICAL_WALL = re.compile(r"^Wall (\d+)$")


@dataclass(frozen=True, slots=True)
class TechCardWork:
    number: int
    name: str
    unit: str | None
    quantity: str | None  # from the current estimate; None = not in an estimate (yet)
    wait_hours: int | None  # the technological break after this work


@dataclass(frozen=True, slots=True)
class TechCardSurface:
    name: str | None  # None = a blank block to fill in by hand
    type_label: str | None
    substrate: str | None
    quality_target: str | None
    inspection: InspectionView | None
    works: tuple[TechCardWork, ...]
    spare_rows: int = 0


@dataclass(frozen=True, slots=True)
class TechCardRoom:
    name: str | None
    surfaces: tuple[TechCardSurface, ...]


@dataclass(frozen=True, slots=True)
class TechCardDocument:
    layout: DocumentLayout
    object_name: str
    object_lines: tuple[str, ...]
    rooms: tuple[TechCardRoom, ...]
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


# --- source data ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlannedWorkRow:
    name: str
    unit: str
    wait_hours: int | None
    quantity: Decimal | None


@dataclass(frozen=True, slots=True)
class SurfaceSource:
    surface_id: uuid.UUID
    room_id: uuid.UUID
    name: str
    surface_type: str
    plan_exists: bool
    substrate: str | None
    quality_target: str | None
    works: tuple[PlannedWorkRow, ...]
    inspection: InspectionInfo | None


@dataclass(frozen=True, slots=True)
class RoomSource:
    room_id: uuid.UUID
    name: str
    surfaces: tuple[SurfaceSource, ...]


def surface_title(name: str) -> str:
    """The canonical language-neutral names ("Wall 1", "Floor", "Ceiling") in Polish; an owner's own name is kept."""
    labels = Labels()
    match = _CANONICAL_WALL.match(name)
    if match:
        return labels("techcard.canonical.wall", n=match.group(1))
    if name == "Floor":
        return labels("techcard.canonical.floor")
    if name == "Ceiling":
        return labels("techcard.canonical.ceiling")
    return name


def _quality_label(code: str) -> str:
    labels = Labels()
    names = {
        "S1": labels("techcard.quality.s1"),
        "S2": labels("techcard.quality.s2"),
        "S3": labels("techcard.quality.s3"),
        "S4": labels("techcard.quality.s4"),
        "Q1": labels("techcard.quality.q1"),
        "Q2": labels("techcard.quality.q2"),
        "Q3": labels("techcard.quality.q3"),
        "Q4": labels("techcard.quality.q4"),
    }
    return f"{code} — {names[code]}"


def _surface_type_label(surface_type: str) -> str:
    labels = Labels()
    names = {
        "WALL": labels("techcard.surface.wall"),
        "CEILING": labels("techcard.surface.ceiling"),
        "FLOOR": labels("techcard.surface.floor"),
        "OTHER": labels("techcard.surface.other"),
    }
    return names[surface_type]


def _unit_label(unit: str) -> str:
    return Labels()(f"unit.{unit.lower()}")


def _work_view(number: int, row: PlannedWorkRow) -> TechCardWork:
    return TechCardWork(
        number=number,
        name=row.name,
        unit=_unit_label(row.unit),
        quantity=formatting.format_quantity(row.quantity) if row.quantity is not None else None,
        wait_hours=row.wait_hours,
    )


def missing_for_issue(source: SurfaceSource) -> tuple[str, ...]:
    missing = []
    if source.quality_target is None:
        missing.append(MISSING_QUALITY_TARGET)
    if source.inspection is None:
        missing.append(MISSING_INSPECTION)
    return tuple(missing)


def _surface_view(source: SurfaceSource, *, working: bool) -> TechCardSurface:
    labels = Labels()
    inspection = inspection_view(source.inspection) if source.inspection is not None else None
    substrate = source.substrate or (source.inspection.substrate if source.inspection is not None else None)
    quality = source.quality_target or (source.inspection.quality_target if source.inspection is not None else None)
    return TechCardSurface(
        name=surface_title(source.name),
        type_label=_surface_type_label(source.surface_type),
        substrate=labels(f"photo_report.substrate_name.{substrate.lower()}") if substrate else None,
        quality_target=_quality_label(quality) if quality else None,
        inspection=inspection,
        works=tuple(_work_view(n, row) for n, row in enumerate(source.works, start=1)),
        spare_rows=max(0, SPARE_ROWS - len(source.works)) if working else 0,
    )


def build_tech_card_document(
    project: Project,
    client: Client | None,
    executor: ExecutorProfile | None,
    rooms: tuple[RoomSource, ...],
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> TechCardDocument:
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    if executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a technological card")
    if working:
        views = tuple(
            TechCardRoom(room.name, tuple(_surface_view(source, working=True) for source in room.surfaces)) for room in rooms
        )
        if not views:
            blank = TechCardSurface(None, None, None, None, None, (), spare_rows=SPARE_ROWS)
            views = (TechCardRoom(None, (blank,) * BLANK_SURFACES),)
    else:
        planned = tuple(
            (room, tuple(s for s in room.surfaces if s.works)) for room in rooms
        )
        planned = tuple((room, surfaces) for room, surfaces in planned if surfaces)
        if not planned:
            raise DocumentDataError("TECH_CARD_EMPTY", "no surface of the object has planned works yet")
        incomplete = [
            {"room": room.name, "surface": source.name, "surface_type": source.surface_type, "missing": list(missing_for_issue(source))}
            for room, surfaces in planned
            for source in surfaces
            if missing_for_issue(source)
        ]
        if incomplete:
            raise DocumentDataError(
                "TECH_CARD_INCOMPLETE",
                "the surfaces with planned works need an agreed standard and a finished inspection",
                {"items": incomplete},
            )
        views = tuple(
            TechCardRoom(room.name, tuple(_surface_view(source, working=False) for source in surfaces)) for room, surfaces in planned
        )
    labels = Labels()
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("techcard.title"),
            issued_on=issued_on,
            number=number,
            place=(executor.city or None) if executor is not None else None,
            sequence=sequence,
        ),
        executor=party_from_executor_profile(executor) if executor is not None else None,
        client=party_from_client(client) if client is not None else None,
        signatures=True,
        draft=working,
        light_watermark=working,
    )
    return TechCardDocument(layout, project.name, object_lines(project), views, working)


# --- loading -------------------------------------------------------------------------------------------------------------------------


def _surface_order(surface: Surface) -> tuple:
    created = surface.created_at if surface.created_at.tzinfo is not None else surface.created_at.replace(tzinfo=UTC)
    return (surface.position is None, surface.position or 0, created, str(surface.id))


def _inspection_of(surface: Surface, inspections: tuple[InspectionInfo, ...]) -> InspectionInfo | None:
    """The latest finished inspection of a surface: a wall's own, or -- for a floor or a ceiling -- the room's inspection of
    that plane (they have no surface of their own)."""
    found = [
        i
        for i in inspections
        if i.status == "COMPLETED"
        and (i.surface_id == surface.id or (i.surface_id is None and i.plane is not None and i.plane == surface.surface_type.value))
    ]
    return found[-1] if found else None  # the read model orders inspections by creation


class TechCardDocumentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def sources(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> tuple[Project, Client | None, tuple[RoomSource, ...]]:
        """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then)."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        project = (
            await self.db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        ).scalar_one()
        client = None
        if project.client_id is not None:
            client = (
                await self.db.execute(select(Client).where(Client.id == project.client_id, Client.owner_user_id == owner_id))
            ).scalar_one_or_none()
        details = await InspectionReportReadModel(self.db).build(owner_id, project_id)
        room_ids = [room.room_id for room in details.rooms]
        surfaces = (
            list(
                (
                    await self.db.execute(
                        select(Surface).where(Surface.room_id.in_(room_ids), Surface.is_archived.is_(False))
                    )
                ).scalars()
            )
            if room_ids
            else []
        )
        surfaces.sort(key=_surface_order)
        plans = (
            {
                plan.surface_id: plan
                for plan in (
                    await self.db.execute(select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id.in_([s.id for s in surfaces])))
                ).scalars()
            }
            if surfaces
            else {}
        )
        works = (
            list(
                (
                    await self.db.execute(
                        select(SurfacePlannedWork)
                        .where(SurfacePlannedWork.work_plan_id.in_([p.id for p in plans.values()]))
                        .order_by(SurfacePlannedWork.work_plan_id, SurfacePlannedWork.position)
                    )
                ).scalars()
            )
            if plans
            else []
        )
        items = (
            {
                item.id: item
                for item in (await self.db.execute(select(PriceItem).where(PriceItem.id.in_({w.price_item_id for w in works})))).scalars()
            }
            if works
            else {}
        )
        quantities = await self._quantities(owner_id, project_id, [w.occurrence_key for w in works])
        by_plan: dict[uuid.UUID, list[PlannedWorkRow]] = {}
        for work in works:
            item = items[work.price_item_id]
            by_plan.setdefault(work.work_plan_id, []).append(
                PlannedWorkRow(
                    name=localize_description(item.display_name or item.name_key or item.code),
                    unit=item.unit.value,
                    wait_hours=work.wait_after_hours,
                    quantity=quantities.get(work.occurrence_key),
                )
            )
        sources: dict[uuid.UUID, list[SurfaceSource]] = {}
        for surface in surfaces:
            plan = plans.get(surface.id)
            sources.setdefault(surface.room_id, []).append(
                SurfaceSource(
                    surface_id=surface.id,
                    room_id=surface.room_id,
                    name=surface.name,
                    surface_type=surface.surface_type.value,
                    plan_exists=plan is not None,
                    substrate=plan.substrate.value if plan is not None else None,
                    quality_target=plan.quality_target.value if plan is not None and plan.quality_target else None,
                    works=tuple(by_plan.get(plan.id, ())) if plan is not None else (),
                    inspection=_inspection_of(surface, details.of_room(surface.room_id)),
                )
            )
        rooms = tuple(RoomSource(room.room_id, room.name, tuple(sources.get(room.room_id, ()))) for room in details.rooms)
        return project, client, rooms

    async def _quantities(self, owner_id: uuid.UUID, project_id: uuid.UUID, keys: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
        """Quantity of each planned work in the current estimate (the latest that is not archived), by the work's stable
        occurrence key; a work that is not in the estimate has none."""
        if not keys:
            return {}
        estimate_id = (
            await self.db.execute(
                select(Estimate.id)
                .where(Estimate.project_id == project_id, Estimate.owner_id == owner_id, Estimate.status != EstimateStatus.ARCHIVED)
                .order_by(Estimate.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if estimate_id is None:
            return {}
        lines = (
            await self.db.execute(
                select(EstimateLine.occurrence_key, EstimateLine.quantity).where(
                    EstimateLine.estimate_id == estimate_id, EstimateLine.occurrence_key.in_(keys)
                )
            )
        ).all()
        return {key: quantity for key, quantity in lines}

    async def build(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        working: bool,
        issued_on: date,
        number: str | None = None,
        sequence: int | None = None,
    ) -> TechCardDocument:
        project, client, rooms = await self.sources(owner_id, project_id)
        executor = await ExecutorProfileService(self.db).get(owner_id)
        return build_tech_card_document(
            project, client, executor, rooms, working=working, issued_on=issued_on, number=number, sequence=sequence
        )

    @staticmethod
    def html(document: TechCardDocument) -> str:
        return render_html(get_template(DocumentKind.TECH_CARD), document.context())

    async def render(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, renderer: DocumentRenderer, **kwargs
    ) -> RenderedPdf:
        document = await self.build(owner_id, project_id, **kwargs)
        return await renderer.render(self.html(document))

