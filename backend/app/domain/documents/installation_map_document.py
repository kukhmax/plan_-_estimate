"""The map of hidden utilities (Mapa instalacji ukrytych, V2-12a): the photos of the object whose markers name a utility, with the markers drawn in the colour of their type, and
under each photo what lies where (the type, the label, the distances from the floor / a corner, the depth). For the client and for the owner's own file.

Nothing is calculated here: the photos, the markers and their distances are what the owner stored; this module only picks the photos with at least one utility marker (whether or not they are
marked for the photo report), groups them by the place they were taken and lays them out. The words are Polish labels (`locales/pl.json`). The geometry of the markers is the one of the
photo report (`photo_report_document.marker_shapes`).

Two forms of one document, like the measurements:

* **issued** (`working=False`): numbered (MAP/...), journalled, no watermark. Refused with a stable code while no photo has a marker with a utility
  (`INSTALLATION_MAP_EMPTY`), when there are more photos than one document holds (`INSTALLATION_MAP_PHOTO_LIMIT_EXCEEDED`) or the executor profile is empty (`EXECUTOR_PROFILE_REQUIRED`);
* **working** (`working=True`): the "WERSJA ROBOCZA" watermark, no number, no journal row; it never refuses for missing photos.
"""

import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.estimate_document import object_lines, party_from_client
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.photo_report_document import (
    PHOTOS_PER_ROW,
    UTILITY_COLORS,
    MarkerShape,
    OutlineShape,
    PhotoReportDocumentService,
    PrintImage,
    frame_width_mm,
    legend_entries,
    marker_shapes,
    outline_shapes,
    utility_names,
)
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.renderer import DocumentRenderer, RenderedPdf
from app.domain.documents.surface_names import surface_title
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.domain.services.photo_report_read_model import (
    PhotoReport,
    PhotoReportReadModel,
    ReportInspection,
    ReportPhoto,
)
from app.domain.services.project_service import ProjectService
from app.models.client import Client
from app.models.executor_profile import ExecutorProfile
from app.models.project import Project


@dataclass(frozen=True, slots=True)
class MapSource:
    """A photo with a utility marker and where it was taken: the room (None: the object itself) and the place inside it."""

    photo: ReportPhoto
    room: str | None
    place: str


@dataclass(frozen=True, slots=True)
class Sources:
    project: Project
    client: Client | None
    photos: tuple[MapSource, ...]


@dataclass(frozen=True, slots=True)
class MapPhoto:
    number: int
    place: str
    asset_name: str
    width: int
    height: int
    frame_mm: str
    caption: str | None
    taken_on: datetime
    markers: tuple[MarkerShape, ...]
    outlines: tuple[OutlineShape, ...]
    legend: tuple[tuple[int, str | None], ...]


@dataclass(frozen=True, slots=True)
class MapGroup:
    title: str
    rows: tuple[tuple[MapPhoto, ...], ...]


@dataclass(frozen=True, slots=True)
class MapKey:
    """A type of utility that is on the map: its name and its colour."""

    name: str
    color: str


@dataclass(frozen=True, slots=True)
class InstallationMapDocument:
    layout: DocumentLayout
    object_name: str
    object_lines: tuple[str, ...]
    groups: tuple[MapGroup, ...]
    keys: tuple[MapKey, ...]
    photo_count: int
    working: bool
    assets: Mapping[str, bytes] = field(default_factory=dict, compare=False, repr=False)

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def has_utility(photo: ReportPhoto) -> bool:
    return any(marker.utility in UTILITY_COLORS for marker in photo.markers)


def _inspection_photos(inspection: ReportInspection) -> Iterator[ReportPhoto]:
    yield from inspection.photos
    for question in inspection.questions:
        yield from question.photos
    for finding in inspection.findings:
        yield from finding.photos


def collect(report: PhotoReport) -> tuple[MapSource, ...]:
    """Every photo of the object with a utility marker, in the order of the photo report: the object's own photos, then each room (its own photos, its surfaces with their openings and works, its
    inspections). One photo attached in several places is listed once (the first place)."""
    labels = Labels()
    found: list[MapSource] = []
    seen: set[uuid.UUID] = set()

    def take(photos, room: str | None, place: str) -> None:
        for photo in photos:
            if photo.attachment_id not in seen and has_utility(photo):
                seen.add(photo.attachment_id)
                found.append(MapSource(photo, room, place))

    take(report.project_photos, None, labels("installation_map.object_place"))
    for room in report.rooms:
        take(room.photos, room.name, room.name)
        for surface in room.surfaces:
            base = f"{room.name} › {surface_title(surface.name)}"
            take(surface.photos, room.name, base)
            for opening in surface.openings:
                take(opening.photos, room.name, f"{base} › {opening.name or labels('photo_report.opening')}")
            for work in surface.works:
                take(work.photos, room.name, base)
        for inspection in room.inspections:
            take(_inspection_photos(inspection), room.name, f"{room.name} › {labels('photo_report.inspection')}")
    return tuple(found)


def build_installation_map_document(
    sources: Sources,
    images: Mapping[uuid.UUID, PrintImage] | None,
    executor: ExecutorProfile | None,
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> InstallationMapDocument:
    """`images` (by asset id, one per photo of `sources`) are printed; without them (the check before a number is given) the photos are only counted."""
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    if executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing the map of installations")
    if not sources.photos and not working:
        raise DocumentDataError("INSTALLATION_MAP_EMPTY", "no photo has a marker with a hidden utility yet")
    labels = Labels()
    asset_names: dict[uuid.UUID, str] = {}
    assets: dict[str, bytes] = {}
    counter = 0
    grouped: dict[str, list[MapPhoto]] = {}
    present: set[str] = set()
    for source in sources.photos:
        photo = source.photo
        for marker in photo.markers:
            if marker.utility in UTILITY_COLORS:
                present.add(marker.utility)
        image = (images or {}).get(photo.asset_id)
        if image is None:
            counter += 1
            continue
        name = asset_names.setdefault(photo.asset_id, f"p{len(asset_names) + 1}.jpg")
        assets[name] = image.data
        counter += 1
        grouped.setdefault(source.room or labels("installation_map.object_group"), []).append(
            MapPhoto(
                number=counter,
                place=source.place,
                asset_name=name,
                width=image.width,
                height=image.height,
                frame_mm=frame_width_mm(image.width, image.height),
                caption=photo.caption or None,
                taken_on=photo.captured_at or photo.uploaded_at,
                markers=marker_shapes(photo.markers, image.width, image.height),
                outlines=outline_shapes(photo.markers, image.width, image.height),
                legend=legend_entries(photo.markers),
            )
        )
    groups = tuple(
        MapGroup(title, tuple(tuple(views[i : i + PHOTOS_PER_ROW]) for i in range(0, len(views), PHOTOS_PER_ROW))) for title, views in grouped.items()
    )
    names = utility_names(labels)
    keys = tuple(MapKey(names[kind], color) for kind, color in UTILITY_COLORS.items() if kind in present)
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("installation_map.title"),
            issued_on=issued_on,
            number=number,
            place=(executor.city or None) if executor is not None else None,
            sequence=sequence,
        ),
        executor=party_from_executor_profile(executor) if executor is not None else None,
        client=party_from_client(sources.client) if sources.client is not None else None,
        signatures=False,
        draft=working,
        light_watermark=False,
    )
    return InstallationMapDocument(layout, sources.project.name, object_lines(sources.project), groups, keys, counter, working, assets)


class InstallationMapDocumentService:
    def __init__(self, db: AsyncSession, photos: PhotoReportDocumentService) -> None:
        self.db = db
        self.photos = photos  # reads the pictures and knows how many a document holds

    async def sources(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> Sources:
        """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then). A document with more photos than one document holds
        is refused (`INSTALLATION_MAP_PHOTO_LIMIT_EXCEEDED`) before any picture is read."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        project = (await self.db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one()
        client = None
        if project.client_id is not None:
            client = (
                await self.db.execute(select(Client).where(Client.id == project.client_id, Client.owner_user_id == owner_id))
            ).scalar_one_or_none()
        report = await PhotoReportReadModel(self.db).build(owner_id, project_id, only_included=False)
        found = collect(report)
        if len(found) > self.photos.max_photos:
            raise DocumentDataError(
                "INSTALLATION_MAP_PHOTO_LIMIT_EXCEEDED",
                f"the object has {len(found)} photos with hidden utilities; one document holds at most {self.photos.max_photos}",
                {"count": len(found), "limit": self.photos.max_photos},
            )
        return Sources(project, client, found)

    async def build(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        working: bool,
        issued_on: date,
        number: str | None = None,
        sequence: int | None = None,
        read_photos: bool = True,
    ) -> InstallationMapDocument:
        """`read_photos=False` only checks that the document can be made (limits, data) without reading a single picture: what the numbered form does before it takes a number."""
        sources = await self.sources(owner_id, project_id)
        executor = await ExecutorProfileService(self.db).get(owner_id)
        if executor is None and not working:  # refuse before a single picture is read
            raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing the map of installations")
        images = await self.photos.images_of([source.photo for source in sources.photos]) if read_photos and sources.photos else None
        return build_installation_map_document(sources, images, executor, working=working, issued_on=issued_on, number=number, sequence=sequence)

    @staticmethod
    def html(document: InstallationMapDocument) -> str:
        return render_html(get_template(DocumentKind.INSTALLATION_MAP), document.context())

    async def render(self, owner_id: uuid.UUID, project_id: uuid.UUID, renderer: DocumentRenderer, **kwargs) -> RenderedPdf:
        document = await self.build(owner_id, project_id, **kwargs)
        return await renderer.render(self.html(document), document.assets)
