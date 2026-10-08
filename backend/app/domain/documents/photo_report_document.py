"""The inspection photo report as a document (Stage 15E).

Input: the 14I report tree (`PhotoReportReadModel`: only photos marked for the report, in document order), the objects it
refers to, and the bytes of the photos. Output: blocks the template prints -- headings by room / surface / opening / work /
inspection / question / finding, each followed by its photos two to a row, every photo with its number, caption, date and
the point markers and contours drawn over it.

Rules kept here, not in the template:
- the order is the read model's order, nothing is re-sorted; photo numbers run through the whole document;
- at most `DOCUMENT_MAX_PHOTOS` photos per document (owner decision: 60); a larger report is refused with the counts per
  room so it can be issued in parts by room (`room_ids`);
- the geometry of markers and contours is computed here from the stored fractions of the picture (0..1) and the size of
  the picture that is printed, so a marker sits on the same spot of the print as on the screen;
- a photo that cannot be read is an error, never a silent gap in a client document.
"""

import asyncio
import io
import tempfile
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents import formatting
from app.domain.documents.catalog import localize_checklist_text, localize_description
from app.domain.documents.estimate_document import object_lines, party_from_client
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.renderer import DocumentRenderer, RenderedPdf
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError, MediaStorageError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.domain.services.media_storage import MediaStorage
from app.domain.services.photo_report_read_model import (
    PhotoReport,
    PhotoReportReadModel,
    ReportFinding,
    ReportMarker,
    ReportPhoto,
    ReportRoom,
)
from app.models.client import Client
from app.models.executor_profile import ExecutorProfile
from app.models.project import Project
from app.models.surface import Surface

PRINT_MAX_EDGE = 1000  # px of the longer side: ~300 dpi for a photo 85 mm wide, ~120 KB a photo
PRINT_JPEG_QUALITY = 78
MAX_SOURCE_PIXELS = 60_000_000
PHOTOS_PER_ROW = 2
DOWNLOAD_CONCURRENCY = 4

CELL_WIDTH_MM = 87.0  # a half of the text width of the A4 page
MAX_PHOTO_HEIGHT_MM = 90.0  # a portrait photo is narrower, so two of them still fit under each other on a page
MARKER_RADIUS = 0.032  # of the picture's width: a dot ~5 mm across on a photo 85 mm wide
OUTLINE_UNDER_WIDTH = 0.0045
OUTLINE_WIDTH = 0.002


# --- the picture that is printed ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrintImage:
    data: bytes
    width: int
    height: int


def prepare_print_image(raw: bytes, *, max_pixels: int = MAX_SOURCE_PIXELS) -> PrintImage:
    """The stored display copy as a smaller JPEG for the page. Synchronous CPU work: call it off the event loop."""
    try:
        with Image.open(io.BytesIO(raw)) as source:
            width, height = source.size
            if width * height > max_pixels:
                raise DocumentDataError("PHOTO_UNREADABLE", "a photo has too many pixels to print")
            image = ImageOps.exif_transpose(source).convert("RGB")
    except DocumentDataError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise DocumentDataError("PHOTO_UNREADABLE", "a photo cannot be read as an image") from exc
    image.thumbnail((PRINT_MAX_EDGE, PRINT_MAX_EDGE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=PRINT_JPEG_QUALITY, optimize=True)
    return PrintImage(out.getvalue(), image.width, image.height)


# --- what the template prints ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarkerShape:
    number: int
    cx: str
    cy: str
    ty: str  # baseline of the number, so it sits in the middle of the dot
    r: str
    font: str
    stroke: str


@dataclass(frozen=True, slots=True)
class OutlineShape:
    points: str
    under_width: str
    width: str


@dataclass(frozen=True, slots=True)
class PhotoView:
    number: int
    asset_name: str  # file name inside the document's own assets/
    width: int
    height: int
    frame_mm: str  # printed width of the picture; the markers are drawn in its own units, so they follow it
    category: str  # PhotoCategory value
    show_category: bool
    caption: str | None
    taken_on: datetime
    markers: tuple[MarkerShape, ...]
    outlines: tuple[OutlineShape, ...]
    legend: tuple[tuple[int, str], ...]  # (marker number, label) for the markers that have a label


@dataclass(frozen=True, slots=True)
class Block:
    """One step of the document. `kind` is one of: project, room, surface, opening, work, inspection, question, finding."""

    kind: str
    title: str | None = None  # a name from the data (room, surface, opening, work, question, finding)
    code: str | None = None  # surface type / inspection plane / status
    detail: str | None = None  # a finding's value
    muted: bool = False  # a work removed from the plan, a finding that is no longer current
    rows: tuple[tuple[PhotoView, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class PhotoReportDocument:
    layout: DocumentLayout
    object_name: str
    object_lines: tuple[str, ...]
    blocks: tuple[Block, ...]
    photo_count: int
    scope_rooms: tuple[str, ...] = field(default=())  # names of the rooms of a partial report

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


# --- the plan: which photos, in which order, under which heading ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Step:
    kind: str
    photos: tuple[ReportPhoto, ...]
    title: str | None = None
    code: str | None = None
    detail: str | None = None
    muted: bool = False


def _finding_detail(finding: ReportFinding) -> str | None:
    value = finding.value_snapshot
    if not value:
        return None
    if isinstance(value.get("number"), str):
        return f"{formatting.format_decimal(value['number'], 2)} mm"
    if isinstance(value.get("text"), str):
        return value["text"]
    if "bool" in value:
        return Labels()("photo_report.yes")
    return None


def _room_steps(room: ReportRoom, surface_names: Mapping[uuid.UUID, str]) -> Iterable[_Step]:
    yield _Step("room", room.photos, title=room.name)
    for surface in room.surfaces:
        yield _Step("surface", surface.photos, title=surface.name, code=surface.surface_type)
        for opening in surface.openings:
            yield _Step("opening", opening.photos, title=opening.name)
        for work in surface.works:
            name = work.price_item_display_name or work.price_item_name_key or work.price_item_code
            yield _Step(
                "work",
                work.photos,
                title=localize_description(name) if name else None,
                muted=not work.current,
            )
    for inspection in room.inspections:
        target = surface_names.get(inspection.surface_id) if inspection.surface_id else None
        yield _Step("inspection", inspection.photos, title=target, code=inspection.plane, detail=inspection.status)
        for question in inspection.questions:
            yield _Step("question", question.photos, title=localize_checklist_text(question.text_key))
        for finding in inspection.findings:
            label = localize_checklist_text(finding.label_key) if finding.label_key else None
            yield _Step("finding", finding.photos, title=label, detail=_finding_detail(finding), muted=not finding.is_active)


def plan_photo_report(
    report: PhotoReport,
    surface_names: Mapping[uuid.UUID, str],
    *,
    room_ids: frozenset[uuid.UUID] | None = None,
    include_project_photos: bool = True,
) -> tuple[_Step, ...]:
    """The headings of the document with their photos, in print order. A heading with no photo of its own still stands
    (its children have photos: the read model drops every node that has none below it)."""
    steps: list[_Step] = []
    if include_project_photos and report.project_photos:
        steps.append(_Step("project", report.project_photos))
    for room in report.rooms:
        if room_ids is None or room.room_id in room_ids:
            steps.extend(_room_steps(room, surface_names))
    return tuple(steps)


def photos_of(steps: Iterable[_Step]) -> list[ReportPhoto]:
    return [photo for step in steps for photo in step.photos]


def check_limit(report: PhotoReport, steps: tuple[_Step, ...], limit: int) -> None:
    total = len(photos_of(steps))
    if total == 0:
        raise DocumentDataError("REPORT_EMPTY", "no photo is marked for the report")
    if total > limit:
        per_room = [
            {"room_id": str(room.room_id), "name": room.name, "count": len(photos_of(_room_steps(room, {})))}
            for room in report.rooms
        ]
        raise DocumentDataError(
            "PHOTO_LIMIT_EXCEEDED",
            f"the report has {total} photos; one document holds at most {limit}",
            {"count": total, "limit": limit, "project_photos": len(report.project_photos), "rooms": per_room},
        )


# --- geometry -------------------------------------------------------------------------------------------------------------


def frame_width_mm(width: int, height: int) -> str:
    return f"{min(CELL_WIDTH_MM, MAX_PHOTO_HEIGHT_MM * width / height):.1f}"


def _n(value: float) -> str:
    return f"{value:.1f}"


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def marker_shapes(markers: tuple[ReportMarker, ...], width: int, height: int) -> tuple[MarkerShape, ...]:
    radius = MARKER_RADIUS * width
    return tuple(
        MarkerShape(
            number=index,
            cx=_n(_clamp(marker.x) * width),
            cy=_n(_clamp(marker.y) * height),
            ty=_n(_clamp(marker.y) * height + radius * 0.4),
            r=_n(radius),
            font=_n(radius * 1.15),
            stroke=_n(max(1.0, radius * 0.14)),
        )
        for index, marker in enumerate(markers, start=1)
    )


def outline_shapes(markers: tuple[ReportMarker, ...], width: int, height: int) -> tuple[OutlineShape, ...]:
    return tuple(
        OutlineShape(
            points=" ".join(f"{_n(_clamp(x) * width)},{_n(_clamp(y) * height)}" for x, y in marker.outline),
            under_width=_n(max(1.0, OUTLINE_UNDER_WIDTH * width)),
            width=_n(max(0.6, OUTLINE_WIDTH * width)),
        )
        for marker in markers
        if marker.outline and len(marker.outline) > 1
    )


# --- the document -----------------------------------------------------------------------------------------------------------------


def build_photo_report_document(
    steps: tuple[_Step, ...],
    images: Mapping[uuid.UUID, PrintImage],
    project: Project,
    client: Client | None,
    executor: ExecutorProfile | None,
    *,
    issued_on: date,
    number: str | None = None,
    scope_rooms: tuple[str, ...] = (),
) -> PhotoReportDocument:
    """`images` is keyed by asset id and must hold every photo of `steps`."""
    if executor is None:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a photo report")
    counter = 0
    asset_names: dict[uuid.UUID, str] = {}
    blocks: list[Block] = []
    for step in steps:
        views: list[PhotoView] = []
        for photo in step.photos:
            image = images.get(photo.asset_id)
            if image is None:
                raise DocumentDataError("PHOTO_UNAVAILABLE", "a photo of the report has no picture")
            counter += 1
            name = asset_names.setdefault(photo.asset_id, f"p{len(asset_names) + 1}.jpg")
            views.append(
                PhotoView(
                    number=counter,
                    asset_name=name,
                    width=image.width,
                    height=image.height,
                    frame_mm=frame_width_mm(image.width, image.height),
                    category=photo.category.value,
                    show_category=step.kind == "work",
                    caption=photo.caption or None,
                    taken_on=photo.captured_at or photo.uploaded_at,
                    markers=marker_shapes(photo.markers, image.width, image.height),
                    outlines=outline_shapes(photo.markers, image.width, image.height),
                    legend=tuple((i, m.label) for i, m in enumerate(photo.markers, start=1) if m.label),
                )
            )
        rows = tuple(tuple(views[i : i + PHOTOS_PER_ROW]) for i in range(0, len(views), PHOTOS_PER_ROW))
        blocks.append(Block(step.kind, step.title, step.code, step.detail, step.muted, rows))
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=Labels()("photo_report.title"),
            issued_on=issued_on,
            number=number,
            place=executor.city or None,
        ),
        executor=party_from_executor_profile(executor),
        client=party_from_client(client) if client else None,
    )
    return PhotoReportDocument(
        layout=layout,
        object_name=project.name,
        object_lines=object_lines(project),
        blocks=tuple(blocks),
        photo_count=counter,
        scope_rooms=scope_rooms,
    )


def asset_files(document: PhotoReportDocument, steps: tuple[_Step, ...], images: Mapping[uuid.UUID, PrintImage]) -> dict[str, bytes]:
    """The files the page refers to as `assets/<name>`, named exactly as `build_photo_report_document` named them."""
    files: dict[str, bytes] = {}
    names: dict[uuid.UUID, str] = {}
    for photo in photos_of(steps):
        name = names.setdefault(photo.asset_id, f"p{len(names) + 1}.jpg")
        files[name] = images[photo.asset_id].data
    return files


# --- the service -----------------------------------------------------------------------------------------------------------------


class PhotoReportDocumentService:
    def __init__(self, db: AsyncSession, storage: MediaStorage, *, storage_name: str, max_photos: int) -> None:
        self.db = db
        self.storage = storage
        self.storage_name = storage_name
        self.max_photos = max_photos

    async def prepare(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        room_ids: frozenset[uuid.UUID] | None = None,
        include_project_photos: bool | None = None,
    ) -> tuple[PhotoReport, tuple[_Step, ...]]:
        """The report and its plan; raises `DocumentDataError` for an empty report or one over the photo limit. Nothing
        is downloaded yet: the limit is checked before a single photo is read."""
        report = await PhotoReportReadModel(self.db).build(owner_id, project_id)
        if include_project_photos is None:
            include_project_photos = room_ids is None
        surface_names = await self._surface_names(report)
        steps = plan_photo_report(report, surface_names, room_ids=room_ids, include_project_photos=include_project_photos)
        check_limit(report, steps, self.max_photos)
        return report, steps

    async def build(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        issued_on: date,
        number: str | None = None,
        room_ids: frozenset[uuid.UUID] | None = None,
        include_project_photos: bool | None = None,
    ) -> tuple[PhotoReportDocument, dict[str, bytes]]:
        report, steps = await self.prepare(
            owner_id, project_id, room_ids=room_ids, include_project_photos=include_project_photos
        )
        executor = await ExecutorProfileService(self.db).get(owner_id)
        project = (
            await self.db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        ).scalar_one()
        client = None
        if project.client_id is not None:
            client = (
                await self.db.execute(
                    select(Client).where(Client.id == project.client_id, Client.owner_user_id == owner_id)
                )
            ).scalar_one_or_none()
        images = await self._images(photos_of(steps))
        scope = tuple(room.name for room in report.rooms if room_ids is not None and room.room_id in room_ids)
        document = build_photo_report_document(
            steps, images, project, client, executor, issued_on=issued_on, number=number, scope_rooms=scope
        )
        return document, asset_files(document, steps, images)

    @staticmethod
    def html(document: PhotoReportDocument) -> str:
        return render_html(get_template(DocumentKind.PHOTO_REPORT), document.context())

    async def render(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        renderer: DocumentRenderer,
        *,
        issued_on: date,
        number: str | None = None,
        room_ids: frozenset[uuid.UUID] | None = None,
        include_project_photos: bool | None = None,
    ) -> RenderedPdf:
        document, assets = await self.build(
            owner_id, project_id, issued_on=issued_on, number=number, room_ids=room_ids,
            include_project_photos=include_project_photos,
        )
        return await renderer.render(self.html(document), assets)

    # -- reading ---------------------------------------------------------------------------------------------------------

    async def _surface_names(self, report: PhotoReport) -> dict[uuid.UUID, str]:
        ids = {i.surface_id for room in report.rooms for i in room.inspections if i.surface_id is not None}
        if not ids:
            return {}
        rows = (await self.db.execute(select(Surface.id, Surface.name).where(Surface.id.in_(ids)))).all()
        return {row[0]: row[1] for row in rows}

    async def _images(self, photos: list[ReportPhoto]) -> dict[uuid.UUID, PrintImage]:
        """Download a few at a time, prepare one at a time (one core), keep one picture per asset."""
        unique: dict[uuid.UUID, ReportPhoto] = {}
        for photo in photos:
            if photo.storage_name != self.storage_name:
                raise DocumentDataError("PHOTO_UNAVAILABLE", "a photo is kept in a store this server cannot read")
            unique.setdefault(photo.asset_id, photo)
        images: dict[uuid.UUID, PrintImage] = {}
        gate = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
        with tempfile.TemporaryDirectory(prefix="photo-report-") as tmp:
            async def fetch(index: int, photo: ReportPhoto) -> tuple[uuid.UUID, Path]:
                path = Path(tmp) / f"{index}.jpg"
                async with gate:
                    try:
                        await self.storage.download_to(photo.storage_key_display, path)
                    except MediaStorageError as exc:
                        raise DocumentDataError("PHOTO_UNAVAILABLE", "a photo cannot be read from the store") from exc
                return photo.asset_id, path

            fetched = await asyncio.gather(*(fetch(i, p) for i, p in enumerate(unique.values())))
            for asset_id, path in fetched:
                images[asset_id] = await asyncio.to_thread(self._prepare_file, path)
                path.unlink(missing_ok=True)
        return images

    @staticmethod
    def _prepare_file(path: Path) -> PrintImage:
        return prepare_print_image(path.read_bytes())
