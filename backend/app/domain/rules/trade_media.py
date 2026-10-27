"""What a craftsman sees of the photos of a room (V2-14b; docs/V2_14B_PLAN_RU.md): the photos of the room itself and the route map of his trade -- the photos of the room (its walls,
openings, works, inspections) whose markers name a hidden utility of his trade. Pure rules over the photo report read model; no database, no storage.

Only what was meant to be shared is picked: no captions (they are the owner's notes), only the markers of the trade of the link, the number of photos is bounded, and the object's own
photos and every other room are not part of a room's pictures.
"""
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

from app.domain.rules.trades import ELECTRIC, PLUMBING
from app.domain.services.photo_report_read_model import (
    ReportInspection,
    ReportMarker,
    ReportPhoto,
    ReportRoom,
)

# The hidden utilities (the types of a marker, `PhotoUtility`) each craftsman works on.
UTILITIES: dict[str, frozenset[str]] = {
    ELECTRIC: frozenset({"CABLE"}),
    PLUMBING: frozenset({"WATER_COLD", "WATER_HOT", "SEWER", "HEATING", "GAS"}),
}
MAX_ROOM_PHOTOS = 8
MAX_MAP_PHOTOS = 12
URL_TTL_SECONDS = 1800  # a craftsman may keep the page open while he works: the links of the photos live half an hour (the page is read again on every save)


@dataclass(frozen=True, slots=True)
class Picked:
    photo: ReportPhoto
    place: str | None  # the name of the wall the photo belongs to (None: the room itself or an inspection)
    markers: tuple[ReportMarker, ...]  # only the markers of the trade of the link


def _inspection_photos(inspection: ReportInspection) -> Iterator[ReportPhoto]:
    yield from inspection.photos
    for question in inspection.questions:
        yield from question.photos
    for finding in inspection.findings:
        yield from finding.photos


def _all(room: ReportRoom) -> Iterator[tuple[ReportPhoto, str | None]]:
    for photo in room.photos:
        yield photo, None
    for surface in room.surfaces:
        for photo in surface.photos:
            yield photo, surface.name
        for opening in surface.openings:
            for photo in opening.photos:
                yield photo, surface.name
        for work in surface.works:
            for photo in work.photos:
                yield photo, surface.name
    for inspection in room.inspections:
        for photo in _inspection_photos(inspection):
            yield photo, None


def pick(room: ReportRoom, trade: str) -> tuple[list[Picked], list[Picked]]:
    """(the photos of the room itself, the route map of the trade) of one room. A photo with markers of the trade is on the map and not among the room's own photos; a photo that is attached
    in several places is taken once."""
    kinds = UTILITIES[trade]
    seen: set[uuid.UUID] = set()
    route_map: list[Picked] = []
    for photo, place in _all(room):
        if photo.attachment_id in seen:
            continue
        mine = tuple(m for m in photo.markers if m.utility in kinds)
        if mine:
            seen.add(photo.attachment_id)
            route_map.append(Picked(photo, place, mine))
    own: list[Picked] = []
    for photo in room.photos:
        if photo.attachment_id not in seen:
            seen.add(photo.attachment_id)
            own.append(Picked(photo, None, ()))
    return own[:MAX_ROOM_PHOTOS], route_map[:MAX_MAP_PHOTOS]
