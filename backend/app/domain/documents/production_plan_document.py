"""The production plan (Plan produkcji prac) as a document (Stage 16D.2).

The second document of the chain "technological card -> production plan -> estimate -> contract". Per room, in the order of the
rooms of the object, it says **in which order the works are done** (the surfaces and their planned works, numbered through the
room) and **how long the technological breaks after them are** (the plan's own `wait_after_hours`, summed per room), and it lists
the **works of other contractors** of the register (16D.1): who, where, when, in which order against ours, who answers for
cleanliness and damage, who coordinates.

It invents no duration: the dates of a room ("od … do …") are empty lines to write in -- the contract questionnaire (16E) holds
the agreed dates. No prices, no clause wording.

Two forms of one builder, exactly as the technological card: **numbered** (`PLAN/…`, journal, refused with
`PRODUCTION_PLAN_EMPTY` while no surface has a planned work) and the **working version** (watermark, pale, no number, no
journal row, never refuses; every missing value is an empty line, free rows are left, an object with no rooms yet gets a blank
room, and two blank entries wait under the adjacent works).
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents import formatting
from app.domain.documents.estimate_document import object_lines, party_from_client
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.renderer import DocumentRenderer, RenderedPdf
from app.domain.documents.tech_card_document import (
    SPARE_ROWS,
    RoomSource,
    TechCardDocumentService,
    _surface_type_label,
    surface_title,
)
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.models.adjacent_work import AdjacentWork
from app.models.client import Client
from app.models.executor_profile import ExecutorProfile
from app.models.project import Project

BLANK_ADJACENT = 2  # empty entries of the adjacent works a working version leaves to write in
BLANK_ROWS = 6  # rows of the works table of a blank room


@dataclass(frozen=True, slots=True)
class PlanWork:
    number: int  # through the whole room
    surface: str
    surface_type: str
    work: str
    unit: str | None
    wait_hours: int | None


@dataclass(frozen=True, slots=True)
class PlanRoom:
    name: str | None  # None = a blank room to fill in by hand
    works: tuple[PlanWork, ...]
    total_wait_hours: int  # the technological breaks of the room, added up
    spare_rows: int = 0


@dataclass(frozen=True, slots=True)
class AdjacentEntry:
    """One entry of the register as printed; every field None = a blank entry to write in."""

    work_name: str | None
    performer: str | None
    rooms: str | None
    period: str | None
    order: str | None
    order_note: str | None
    responsibility_note: str | None
    coordination_note: str | None


@dataclass(frozen=True, slots=True)
class ProductionPlanDocument:
    layout: DocumentLayout
    object_name: str
    object_lines: tuple[str, ...]
    rooms: tuple[PlanRoom, ...]
    adjacent: tuple[AdjacentEntry, ...]
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def _unit(unit: str) -> str:
    labels = Labels()
    names = {
        "M2": labels("unit.m2"),
        "LM": labels("unit.lm"),
        "PCS": labels("unit.pcs"),
        "HOUR": labels("unit.hour"),
        "DAY": labels("unit.day"),
        "FLAT": labels("unit.flat"),
    }
    return names[unit]


def _room_view(room: RoomSource, *, working: bool) -> PlanRoom:
    works: list[PlanWork] = []
    for surface in room.surfaces:
        for row in surface.works:
            works.append(
                PlanWork(
                    number=len(works) + 1,
                    surface=surface_title(surface.name),
                    surface_type=_surface_type_label(surface.surface_type),
                    work=row.name,
                    unit=_unit(row.unit),
                    wait_hours=row.wait_hours,
                )
            )
    return PlanRoom(
        name=room.name,
        works=tuple(works),
        total_wait_hours=sum(w.wait_hours or 0 for w in works),
        spare_rows=max(0, SPARE_ROWS - len(works)) if working else 0,
    )


def _period(entry: AdjacentWork) -> str | None:
    labels = Labels()
    if entry.period_from and entry.period_to:
        return f"{formatting.format_date(entry.period_from)} – {formatting.format_date(entry.period_to)}"
    if entry.period_from:
        return labels("plan.period_from_only", date=formatting.format_date(entry.period_from))
    if entry.period_to:
        return labels("plan.period_to_only", date=formatting.format_date(entry.period_to))
    return None


def _order(relation: str) -> str:
    labels = Labels()
    names = {
        "BEFORE_OURS": labels("plan.order.before"),
        "PARALLEL": labels("plan.order.parallel"),
        "AFTER_OURS": labels("plan.order.after"),
    }
    return names[relation]


def adjacent_entries(entries: tuple[AdjacentWork, ...], room_names: dict[str, str]) -> tuple[AdjacentEntry, ...]:
    labels = Labels()
    views = []
    for entry in entries:
        if entry.room_ids is None:
            rooms = labels("plan.whole_object")
        else:
            live = [room_names[room_id] for room_id in entry.room_ids if room_id in room_names]
            rooms = ", ".join(live) if live else labels("plan.rooms_archived")
        views.append(
            AdjacentEntry(
                work_name=entry.work_name,
                performer=entry.performer,
                rooms=rooms,
                period=_period(entry),
                order=_order(entry.order_relation),
                order_note=entry.order_note,
                responsibility_note=entry.responsibility_note,
                coordination_note=entry.coordination_note,
            )
        )
    return tuple(views)


def build_production_plan_document(
    project: Project,
    client: Client | None,
    executor: ExecutorProfile | None,
    rooms: tuple[RoomSource, ...],
    adjacent: tuple[AdjacentWork, ...],
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> ProductionPlanDocument:
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    if executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a production plan")
    names = {str(room.room_id): room.name for room in rooms}
    entries = adjacent_entries(adjacent, names)
    if working:
        views = tuple(_room_view(room, working=True) for room in rooms)
        if not views:
            views = (PlanRoom(None, (), 0, spare_rows=BLANK_ROWS),)
        entries = entries + (AdjacentEntry(None, None, None, None, None, None, None, None),) * BLANK_ADJACENT
    else:
        views = tuple(view for view in (_room_view(room, working=False) for room in rooms) if view.works)
        if not views:
            raise DocumentDataError("PRODUCTION_PLAN_EMPTY", "no surface of the object has planned works yet")
    labels = Labels()
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("plan.title"),
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
    return ProductionPlanDocument(layout, project.name, object_lines(project), views, entries, working)


class ProductionPlanDocumentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        working: bool,
        issued_on: date,
        number: str | None = None,
        sequence: int | None = None,
    ) -> ProductionPlanDocument:
        """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then)."""
        project, client, rooms = await TechCardDocumentService(self.db).sources(owner_id, project_id)
        adjacent = tuple(
            (
                await self.db.execute(
                    select(AdjacentWork)
                    .where(
                        AdjacentWork.project_id == project_id,
                        AdjacentWork.owner_id == owner_id,
                        AdjacentWork.is_archived.is_(False),
                    )
                    .order_by(AdjacentWork.position, AdjacentWork.created_at, AdjacentWork.id)
                )
            ).scalars()
        )
        executor = await ExecutorProfileService(self.db).get(owner_id)
        return build_production_plan_document(
            project, client, executor, rooms, adjacent, working=working, issued_on=issued_on, number=number, sequence=sequence
        )

    @staticmethod
    def html(document: ProductionPlanDocument) -> str:
        return render_html(get_template(DocumentKind.PRODUCTION_PLAN), document.context())

    async def render(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, renderer: DocumentRenderer, **kwargs
    ) -> RenderedPdf:
        document = await self.build(owner_id, project_id, **kwargs)
        return await renderer.render(self.html(document))
