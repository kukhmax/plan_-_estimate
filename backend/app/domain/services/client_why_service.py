"""Why these works (owner 2026-10-31): what the client's page shows behind "Dlaczego te prace?" -- per room, the agreed standard of the surfaces
and, for each work the owner took from an inspection ("Dodaj do prac"), the finding or the risk it answers, the day of the inspection and
up to four of its photos with links signed for half an hour (the display copy and the thumbnail, never the original).

Only what the owner accepted is shown: a work typed by hand has no reason here. Nothing is written.
"""
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.surface_names import surface_title_or_none
from app.domain.rules.trade_media import URL_TTL_SECONDS
from app.domain.services.media_storage import MediaStorage, MediaStorageDisabled
from app.domain.services.photo_report_read_model import PhotoReportReadModel, ReportPhoto
from app.models.inspection import Inspection, InspectionFinding

from app.models.photo_asset import PhotoAsset
from app.models.price_item import PriceItem
from app.models.risk import Risk
from app.models.room import Room
from app.models.surface import Surface
from app.models.work_plan import SurfaceWorkPlan
from app.models.work_recommendation import WorkRecommendation, WorkRecommendationStatus

PHOTOS_PER_REASON = 4


@dataclass(slots=True)
class WhyPhoto:
    thumb_url: str
    url: str
    width: int
    height: int


@dataclass(slots=True)
class WhyReason:
    surface_name: str | None
    work_name_key: str | None
    work_name: str | None
    reason_key: str
    inspected_on: date | None
    photos: list[WhyPhoto] = field(default_factory=list)


@dataclass(slots=True)
class WhyRoom:
    room_id: uuid.UUID
    room_name: str
    quality_target: str | None
    reasons: list[WhyReason] = field(default_factory=list)


class ClientWhyService:
    def __init__(self, db: AsyncSession, storage: MediaStorage | None) -> None:
        self.db = db
        self.storage = storage

    async def _photos(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> dict[uuid.UUID, list[ReportPhoto]]:
        """The photos of each inspection (its own, its questions', its findings'), in the order of the report."""
        if self.storage is None:
            return {}
        report = await PhotoReportReadModel(self.db).build(owner_id, project_id, only_included=False)
        found: dict[uuid.UUID, list[ReportPhoto]] = defaultdict(list)
        for room in report.rooms:
            for inspection in room.inspections:
                seen: set[uuid.UUID] = set()
                for photo in (*inspection.photos, *(p for q in inspection.questions for p in q.photos), *(p for f in inspection.findings for p in f.photos)):
                    if photo.attachment_id not in seen:
                        seen.add(photo.attachment_id)
                        found[inspection.inspection_id].append(photo)
        return found

    async def _signed(self, photos: list[ReportPhoto]) -> list[WhyPhoto]:
        if self.storage is None or not photos:
            return []
        thumbs = dict(
            (await self.db.execute(select(PhotoAsset.id, PhotoAsset.storage_key_thumbnail).where(PhotoAsset.id.in_([p.asset_id for p in photos])))).all()
        )
        out = []
        for photo in photos:
            thumb = thumbs.get(photo.asset_id)
            if thumb is None:
                continue
            out.append(
                WhyPhoto(
                    thumb_url=await self.storage.presign_get(thumb, URL_TTL_SECONDS),
                    url=await self.storage.presign_get(photo.storage_key_display, URL_TTL_SECONDS),
                    width=photo.width,
                    height=photo.height,
                )
            )
        return out

    async def why(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> list[WhyRoom]:
        rooms = list(
            (await self.db.execute(select(Room).where(Room.project_id == project_id, Room.is_archived.is_(False)).order_by(Room.created_at, Room.id))).scalars()
        )
        if not rooms:
            return []
        room_ids = [room.id for room in rooms]
        # the agreed standard of a room: the quality target most of its surface plans name
        targets: dict[uuid.UUID, Counter] = defaultdict(Counter)
        for room_id, target in (
            await self.db.execute(
                select(Surface.room_id, SurfaceWorkPlan.quality_target)
                .join(SurfaceWorkPlan, SurfaceWorkPlan.surface_id == Surface.id)
                .where(Surface.room_id.in_(room_ids), Surface.is_archived.is_(False), SurfaceWorkPlan.quality_target.is_not(None))
            )
        ).all():
            targets[room_id][target.value if hasattr(target, "value") else str(target)] += 1

        accepted = list(
            (
                await self.db.execute(
                    select(WorkRecommendation)
                    .where(WorkRecommendation.room_id.in_(room_ids), WorkRecommendation.status == WorkRecommendationStatus.ACCEPTED)
                    .order_by(WorkRecommendation.accepted_at, WorkRecommendation.id)
                )
            ).scalars()
        )
        risks = {r.id: r for r in (await self.db.execute(select(Risk).where(Risk.id.in_([a.risk_id for a in accepted if a.risk_id])))).scalars()} if accepted else {}
        findings = (
            {f.id: f for f in (await self.db.execute(select(InspectionFinding).where(InspectionFinding.id.in_([a.finding_id for a in accepted if a.finding_id])))).scalars()}
            if accepted
            else {}
        )
        inspections = (
            {i.id: i for i in (await self.db.execute(select(Inspection).where(Inspection.id.in_({a.inspection_id for a in accepted})))).scalars()} if accepted else {}
        )
        surfaces = (
            {s.id: s for s in (await self.db.execute(select(Surface).where(Surface.id.in_({a.surface_id for a in accepted if a.surface_id})))).scalars()}
            if accepted
            else {}
        )
        items = (
            {
                i.id: i
                for i in (
                    await self.db.execute(select(PriceItem).where(PriceItem.owner_id == owner_id, PriceItem.id.in_({a.resolved_price_item_id for a in accepted if a.resolved_price_item_id})))
                ).scalars()
            }
            if accepted
            else {}
        )
        by_code = {}
        if accepted:
            by_code = {
                i.code: i
                for i in (await self.db.execute(select(PriceItem).where(PriceItem.owner_id == owner_id, PriceItem.code.in_({a.recommended_work_code for a in accepted})))).scalars()
            }
        photos = await self._photos(owner_id, project_id) if accepted else {}

        out = {room.id: WhyRoom(room_id=room.id, room_name=room.name, quality_target=(targets[room.id].most_common(1)[0][0] if targets[room.id] else None)) for room in rooms}
        seen: set[tuple] = set()
        for rec in accepted:
            item = items.get(rec.resolved_price_item_id) if rec.resolved_price_item_id else by_code.get(rec.recommended_work_code)
            risk = risks.get(rec.risk_id) if rec.risk_id else None
            finding = findings.get(rec.finding_id) if rec.finding_id else None
            reason_key = risk.title_key if risk is not None else (finding.label_key if finding is not None and finding.label_key else None)
            if reason_key is None:
                continue
            key = (rec.room_id, rec.surface_id, reason_key, item.id if item else rec.recommended_work_code)
            if key in seen:
                continue
            seen.add(key)
            inspection = inspections.get(rec.inspection_id)
            surface = surfaces.get(rec.surface_id) if rec.surface_id else None
            try:
                signed = await self._signed(photos.get(rec.inspection_id, [])[:PHOTOS_PER_REASON])
            except MediaStorageDisabled:
                signed = []
            out[rec.room_id].reasons.append(
                WhyReason(
                    surface_name=surface_title_or_none(surface.name) if surface else None,
                    work_name_key=item.name_key if item else None,
                    work_name=item.display_name if item else None,
                    reason_key=reason_key,
                    inspected_on=inspection.completed_at.date() if inspection is not None and inspection.completed_at else None,
                    photos=signed,
                )
            )
        return [room for room in out.values() if room.quality_target or room.reasons]
