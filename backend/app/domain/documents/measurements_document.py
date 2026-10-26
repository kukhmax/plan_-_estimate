"""The measurements of an object (Obmiar obiektu): every size of every room, as the screens of the application show them (V2-8c).

For the client and for the owner's own file: first the summary of the object (the same sums as the screen "Podsumowanie obiektu"), then each room
with its totals and, under them, how they come about: the rectangles of the ceiling (and of the floor), then every wall with its size, its
openings and reveals and its net area. Nothing is calculated here that the application does not already calculate: the sums are those of
`RoomService` (rooms and the summary of the object), the areas of walls come from the surface reads, the openings and reveals from the
opening reads; this module only lays them out. The words are Polish labels (`locales/pl.json`).

Two forms of one document, like the technological card:

* **issued** (`working=False`): numbered (OBM/...), journalled, no watermark. Refused with a stable code while the object has no room
  (`MEASUREMENTS_EMPTY`) or the executor profile is empty (`EXECUTOR_PROFILE_REQUIRED`);
* **working** (`working=True`): the "WERSJA ROBOCZA" watermark, no number, no journal row; it never refuses.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents import formatting
from app.domain.documents.estimate_document import object_lines, party_from_client
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.photo_report_document import (
    MarkerShape,
    OutlineShape,
    PhotoReportDocumentService,
    PrintImage,
    legend_entries,
    marker_shapes,
    outline_shapes,
)
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.renderer import DocumentRenderer, RenderedPdf
from app.domain.documents.surface_names import surface_title
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.rules.room_geometry import calculate_segment_area
from app.domain.services.area_segment_service import AreaSegmentService
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.domain.services.photo_report_read_model import (
    PhotoReportReadModel,
    ReportPhoto,
)
from app.domain.services.project_service import ProjectService
from app.domain.services.room_service import RoomService
from app.domain.services.surface_service import SurfaceService
from app.models.area_segment import AreaOperation, AreaPlane
from app.models.client import Client
from app.models.executor_profile import ExecutorProfile
from app.models.opening import Opening, OpeningType
from app.models.project import Project
from app.models.surface import SurfaceType
from app.schemas.opening import OpeningRead
from app.schemas.room import ProjectSummaryRead, RoomCalculations
from app.schemas.surface import SurfaceRead

NBSP = " "
DASH = "—"

THUMB_WIDTH_MM = 52.0  # three photos side by side on the page
THUMB_MAX_HEIGHT_MM = 62.0  # a portrait photo is narrower, so the rows stay about equally high


# --- what is read ----------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SegmentSource:
    plane: AreaPlane
    operation: AreaOperation
    width: Decimal
    height: Decimal
    label: str | None


@dataclass(frozen=True, slots=True)
class RoomSource:
    name: str
    description: str | None
    length: Decimal | None
    width: Decimal | None
    calculations: RoomCalculations | None
    base_areas: dict[AreaPlane, Decimal | None]  # the rectangle L x W of each plane (None for a room without a rectangle)
    segments: tuple[SegmentSource, ...]
    walls: tuple[tuple[SurfaceRead, tuple[OpeningRead, ...]], ...]
    ceiling_photos: tuple[ReportPhoto, ...] = ()  # the photos attached to the surfaces (only when the owner asked for them)
    floor_photos: tuple[ReportPhoto, ...] = ()
    wall_photos: Mapping[uuid.UUID, tuple[ReportPhoto, ...]] = field(default_factory=dict)  # by the id of the wall


@dataclass(frozen=True, slots=True)
class Sources:
    project: Project
    client: Client | None
    summary: ProjectSummaryRead
    rooms: tuple[RoomSource, ...]
    with_photos: bool = False


# --- what is printed -------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Row:
    """One line of a table of measurements: a label, the sizes as the owner typed them, and the area (or length)."""

    label: str
    sizes: str = ""
    result: str = ""
    note: str = ""
    muted: bool = False


@dataclass(frozen=True, slots=True)
class ThumbView:
    """A photo of a surface as the page prints it: small, with the markers drawn over it."""

    asset_name: str  # file name inside the document's own assets/
    width: int
    height: int
    frame_mm: str
    caption: str | None
    markers: tuple[MarkerShape, ...]
    outlines: tuple[OutlineShape, ...]
    legend: tuple[tuple[int, str | None], ...]


@dataclass(frozen=True, slots=True)
class PlaneBlock:
    title: str
    total: str
    rows: tuple[Row, ...]
    photos: tuple[ThumbView, ...] = ()


@dataclass(frozen=True, slots=True)
class WallBlock:
    name: str
    sizes: str
    gross: str
    parts: tuple[Row, ...]
    openings: tuple[Row, ...]
    reveals: tuple[Row, ...]
    net: str | None  # shown only when something is taken off the wall
    missing: bool
    photos: tuple[ThumbView, ...] = ()


@dataclass(frozen=True, slots=True)
class RoomBlock:
    name: str
    description: str | None
    totals: tuple[Row, ...]
    ceiling: PlaneBlock
    floor: PlaneBlock
    walls_title: str
    walls: tuple[WallBlock, ...]


@dataclass(frozen=True, slots=True)
class MeasurementsDocument:
    layout: DocumentLayout
    object_name: str
    object_lines: tuple[str, ...]
    summary: tuple[Row, ...]
    openings: tuple[Row, ...]
    rooms: tuple[RoomBlock, ...]
    working: bool
    assets: Mapping[str, bytes] = field(default_factory=dict, compare=False, repr=False)  # the photos the page refers to as assets/<name>

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def dim(value: Decimal) -> str:
    """A size as it was typed: `3,45`, `2,50`, but `3,125` -- never rounded away."""
    return formatting.format_quantity_exact(value)


def area(value: Decimal | None) -> str:
    return DASH if value is None else formatting.format_area(value)


def length(value: Decimal | None) -> str:
    return DASH if value is None else f"{formatting.format_decimal(value, 2)}{NBSP}mb"


def _sizes(*values: Decimal, quantity: int | None = None) -> str:
    text = f"{NBSP}×{NBSP}".join(dim(value) for value in values)
    return f"{text}{NBSP}×{NBSP}{quantity}" if quantity is not None and quantity != 1 else text


def photos_of(sources: Sources) -> list[ReportPhoto]:
    """Every photo the document prints, in print order (empty unless the photos were asked for)."""
    if not sources.with_photos:
        return []
    found: list[ReportPhoto] = []
    for room in sources.rooms:
        found += room.ceiling_photos
        found += room.floor_photos
        for wall, _ in room.walls:
            found += room.wall_photos.get(wall.id, ())
    return found


class _Thumbs:
    """Turns the photos of a surface into what the template prints; keeps one file per asset for the whole document."""

    def __init__(self, images: Mapping[uuid.UUID, PrintImage] | None) -> None:
        self.images = images  # None: the photos are not printed (the document is only being checked)
        self.names: dict[uuid.UUID, str] = {}

    def __call__(self, photos: tuple[ReportPhoto, ...]) -> tuple[ThumbView, ...]:
        if self.images is None:
            return ()
        views: list[ThumbView] = []
        for photo in photos:
            image = self.images.get(photo.asset_id)
            if image is None:
                raise DocumentDataError("PHOTO_UNAVAILABLE", "a photo of the measurements has no picture")
            name = self.names.setdefault(photo.asset_id, f"p{len(self.names) + 1}.jpg")
            views.append(
                ThumbView(
                    asset_name=name,
                    width=image.width,
                    height=image.height,
                    frame_mm=f"{min(THUMB_WIDTH_MM, THUMB_MAX_HEIGHT_MM * image.width / image.height):.1f}",
                    caption=photo.caption or None,
                    markers=marker_shapes(photo.markers, image.width, image.height),
                    outlines=outline_shapes(photo.markers, image.width, image.height),
                    legend=legend_entries(photo.markers),
                )
            )
        return tuple(views)

    def files(self) -> dict[str, bytes]:
        if self.images is None:
            return {}
        return {name: self.images[asset_id].data for asset_id, name in self.names.items()}


def _plane(labels: Labels, plane: AreaPlane, room: RoomSource, thumbs: _Thumbs) -> PlaneBlock:
    calc = room.calculations
    total = calc.ceiling_area if calc is not None and plane == AreaPlane.CEILING else (calc.floor_area if calc is not None else None)
    rows: list[Row] = []
    base = room.base_areas.get(plane)
    if base is not None and room.length is not None and room.width is not None:
        rows.append(Row(labels("measurements.room_rectangle"), _sizes(room.length, room.width), f"={NBSP}{area(base)}"))
    for segment in (s for s in room.segments if s.plane == plane):
        sign = "−" if segment.operation == AreaOperation.SUBTRACT else "+"
        segment_area = calculate_segment_area(segment.width, segment.height)
        rows.append(
            Row(
                f"{sign}{NBSP}{segment.label}" if segment.label else sign,
                _sizes(segment.width, segment.height),
                f"={NBSP}{area(segment_area)}",
            )
        )
    title = labels("measurements.ceiling") if plane == AreaPlane.CEILING else labels("measurements.floor")
    photos = thumbs(room.ceiling_photos if plane == AreaPlane.CEILING else room.floor_photos)
    return PlaneBlock(title, area(total), tuple(rows), photos)


def _opening_names(labels: Labels) -> dict[OpeningType, str]:
    return {
        OpeningType.DOOR: labels("measurements.opening.door"),
        OpeningType.WINDOW: labels("measurements.opening.window"),
        OpeningType.OTHER: labels("measurements.opening.other"),
    }


def _wall(labels: Labels, wall: SurfaceRead, openings: tuple[OpeningRead, ...], photos: tuple[ThumbView, ...]) -> WallBlock:
    name = surface_title(wall.name)
    if wall.gross_area is None:
        return WallBlock(name, labels("measurements.no_size"), DASH, (), (), (), None, True, photos)
    parts = (
        tuple(
            Row(labels("measurements.part", n=index), _sizes(part.width, part.height), f"={NBSP}{area((part.width * part.height).quantize(Decimal('0.001')))}")
            for index, part in enumerate(sorted(wall.parts, key=lambda p: p.position), start=1)
        )
        if wall.parts
        else ()
    )
    names = _opening_names(labels)
    opening_rows: list[Row] = []
    reveal_rows: list[Row] = []
    for opening in openings:
        kind = names[opening.opening_type]
        label = f"{kind}{NBSP}„{opening.name}”" if opening.name else kind
        opening_rows.append(Row(f"−{NBSP}{label}", _sizes(opening.width, opening.height, quantity=opening.quantity), f"={NBSP}{area(opening.total_area)}"))
        if opening.reveal_enabled and opening.reveal_depth is not None and opening.reveal_total_length is not None:
            reveal_rows.append(
                Row(
                    f"{labels('measurements.reveals')}{NBSP}({label})",
                    f"{labels('measurements.depth')}{NBSP}{dim(opening.reveal_depth)}{NBSP}m",
                    f"{length(opening.reveal_total_length)}{NBSP}={NBSP}{area(opening.reveal_total_area)}",
                    muted=True,
                )
            )
    deducted = bool(opening_rows)
    return WallBlock(
        name=name,
        sizes=_sizes(wall.width, wall.height) if wall.width is not None and wall.height is not None else "",
        gross=area(wall.gross_area),
        parts=parts,
        openings=tuple(opening_rows),
        reveals=tuple(reveal_rows),
        net=area(wall.net_area) if deducted else None,
        missing=False,
        photos=photos,
    )


def build_measurements_document(
    sources: Sources,
    executor: ExecutorProfile | None,
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
    images: Mapping[uuid.UUID, PrintImage] | None = None,
) -> MeasurementsDocument:
    """`images` (by asset id, one per photo of `sources`) are printed under the surfaces they are attached to; without them no photo is printed."""
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    if executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing the measurements")
    if not sources.rooms and not working:
        raise DocumentDataError("MEASUREMENTS_EMPTY", "the object has no room to measure yet")
    labels = Labels()
    summary = sources.summary
    summary_rows = [
        Row(labels("measurements.rooms_count"), result=str(summary.room_count)),
        Row(labels("measurements.floors"), result=area(summary.floor_area)),
        Row(labels("measurements.ceilings"), result=area(summary.ceiling_area)),
        Row(labels("measurements.walls_gross"), result=area(summary.total_wall_area)),
        Row(labels("measurements.deductions"), result=area(summary.total_deduction_area)),
        Row(labels("measurements.walls_net"), result=area(summary.net_wall_area), note="strong"),
        Row(labels("measurements.reveals_total"), result=f"{length(summary.reveal_total_length)}{NBSP}/{NBSP}{area(summary.reveal_total_area)}"),
    ]
    opening_rows = tuple(
        Row(
            _opening_names(labels)[group.opening_type],
            _sizes(group.width, group.height),
            f"×{NBSP}{group.quantity}",
        )
        for group in summary.opening_groups
    )
    rooms: list[RoomBlock] = []
    thumbs = _Thumbs(images)
    for room in sources.rooms:
        calc = room.calculations
        totals = [
            Row(labels("measurements.walls_net_of_room"), result=area(calc.net_wall_area if calc else None), note="strong"),
        ]
        if calc is not None and calc.total_deduction_area:
            totals.append(
                Row(
                    labels("measurements.walls_gross_of_room"),
                    result=area(calc.total_wall_area),
                    note=labels("measurements.minus_openings", area=area(calc.total_deduction_area)),
                    muted=True,
                )
            )
        totals.append(Row(labels("measurements.ceiling"), result=area(calc.ceiling_area if calc else None), note="strong"))
        totals.append(Row(labels("measurements.floor"), result=area(calc.floor_area if calc else None), note="strong"))
        rooms.append(
            RoomBlock(
                name=room.name,
                description=room.description or None,
                totals=tuple(totals),
                ceiling=_plane(labels, AreaPlane.CEILING, room, thumbs),
                floor=_plane(labels, AreaPlane.FLOOR, room, thumbs),
                walls_title=labels("measurements.walls"),
                walls=tuple(_wall(labels, wall, openings, thumbs(room.wall_photos.get(wall.id, ()))) for wall, openings in room.walls),
            )
        )
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("measurements.title"),
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
    return MeasurementsDocument(
        layout, sources.project.name, object_lines(sources.project), tuple(summary_rows), opening_rows, tuple(rooms), working, thumbs.files()
    )


class MeasurementsDocumentService:
    def __init__(self, db: AsyncSession, photos: PhotoReportDocumentService | None = None) -> None:
        self.db = db
        self.photos = photos  # reads the pictures; needed only for a document with photos

    async def sources(self, owner_id: uuid.UUID, project_id: uuid.UUID, *, with_photos: bool = False) -> Sources:
        """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then). Only active rooms, walls and openings.
        With `with_photos` every photo attached to a wall, a ceiling or a floor is read too (whether or not it is marked for the photo report);
        a document with more of them than one document holds is refused (`MEASUREMENTS_PHOTO_LIMIT_EXCEEDED`) before any picture is read."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        project = (await self.db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one()
        client = None
        if project.client_id is not None:
            client = (
                await self.db.execute(select(Client).where(Client.id == project.client_id, Client.owner_user_id == owner_id))
            ).scalar_one_or_none()
        rooms_service = RoomService(self.db)
        summary = await rooms_service.get_project_summary(project_id, owner_id)
        rooms, _ = await rooms_service.list_rooms(project_id, owner_id, include_archived=False)
        photo_tree = {r.room_id: r for r in (await PhotoReportReadModel(self.db).build(owner_id, project_id, only_included=False)).rooms} if with_photos else {}
        out: list[RoomSource] = []
        for room in rooms:
            surfaces, _ = await SurfaceService(self.db).list_surfaces(project_id, room.id, owner_id)
            reads = [SurfaceRead.model_validate(s) for s in surfaces if s.surface_type == SurfaceType.WALL and getattr(s, "merged_into_id", None) is None]
            opening_rows: dict[uuid.UUID, list[OpeningRead]] = {read.id: [] for read in reads}
            if reads:
                found = (
                    await self.db.execute(
                        select(Opening)
                        .where(Opening.surface_id.in_(list(opening_rows)), Opening.is_archived.is_(False))
                        .order_by(Opening.created_at.asc(), Opening.id.asc())
                    )
                ).scalars()
                for opening in found:
                    opening_rows[opening.surface_id].append(OpeningRead.model_validate(opening))
            segments, _, totals = await AreaSegmentService(self.db).list_area_segments(project_id, room.id, owner_id)
            by_type: dict[str, list[ReportPhoto]] = {"CEILING": [], "FLOOR": []}
            by_wall: dict[uuid.UUID, tuple[ReportPhoto, ...]] = {}
            for node in photo_tree[room.id].surfaces if room.id in photo_tree else ():
                if node.surface_type in by_type:
                    by_type[node.surface_type].extend(node.photos)
                elif node.surface_type == SurfaceType.WALL.value and node.photos:
                    by_wall[node.surface_id] = node.photos
            out.append(
                RoomSource(
                    name=room.name,
                    description=room.description,
                    length=room.length,
                    width=room.width,
                    calculations=room.calculations,
                    base_areas={plane: (totals.get(plane).base_area if totals.get(plane) is not None else None) for plane in AreaPlane},
                    segments=tuple(SegmentSource(s.plane, s.operation, s.width, s.height, s.label) for s in segments),
                    walls=tuple((read, tuple(opening_rows[read.id])) for read in reads),
                    ceiling_photos=tuple(by_type["CEILING"]),
                    floor_photos=tuple(by_type["FLOOR"]),
                    wall_photos={read.id: by_wall[read.id] for read in reads if read.id in by_wall},
                )
            )
        sources = Sources(project, client, summary, tuple(out), with_photos)
        self._check_limit(sources)
        return sources

    def _check_limit(self, sources: Sources) -> None:
        count = len(photos_of(sources))
        limit = self.photos.max_photos if self.photos is not None else None
        if limit is not None and count > limit:
            raise DocumentDataError(
                "MEASUREMENTS_PHOTO_LIMIT_EXCEEDED",
                f"the surfaces have {count} photos; one document holds at most {limit}",
                {"count": count, "limit": limit},
            )

    async def build(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        working: bool,
        issued_on: date,
        number: str | None = None,
        sequence: int | None = None,
        with_photos: bool = False,
        read_photos: bool = True,
    ) -> MeasurementsDocument:
        """`read_photos=False` only checks that a document with photos can be made (limits, data) without reading a single picture:
        what the numbered form does before it takes a number."""
        sources = await self.sources(owner_id, project_id, with_photos=with_photos)
        executor = await ExecutorProfileService(self.db).get(owner_id)
        if executor is None and not working:  # refuse before a single picture is read
            raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing the measurements")
        images = None
        if with_photos and read_photos:
            if self.photos is None:
                raise RuntimeError("a document with photos needs the service that reads them")
            images = await self.photos.images_of(photos_of(sources))
        return build_measurements_document(
            sources, executor, working=working, issued_on=issued_on, number=number, sequence=sequence, images=images
        )

    @staticmethod
    def html(document: MeasurementsDocument) -> str:
        return render_html(get_template(DocumentKind.MEASUREMENTS), document.context())

    async def render(self, owner_id: uuid.UUID, project_id: uuid.UUID, renderer: DocumentRenderer, **kwargs) -> RenderedPdf:
        document = await self.build(owner_id, project_id, **kwargs)
        return await renderer.render(self.html(document), document.assets)
