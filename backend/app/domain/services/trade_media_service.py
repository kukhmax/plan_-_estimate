"""The photos a craftsman sees on his page (V2-14b): per room, the room's own photos and the route map of his trade, with links that are signed for half an hour.

Reads the photo report read model (so the usual visibility rules hold: ready photos, active attachments, not archived or trashed, not those of an archived room) and signs the
thumbnail and the display copy of each picked photo -- never the original. A storage that is switched off gives no photos. Nothing is written.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rules import trade_media as rules
from app.domain.services.media_storage import MediaStorage, MediaStorageDisabled
from app.domain.services.photo_report_read_model import PhotoReportReadModel
from app.models.photo_asset import PhotoAsset
from app.schemas.trade_link import PortalMarker, PortalPhoto

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RoomMedia:
    photos: list[PortalPhoto] = field(default_factory=list)
    route_map: list[PortalPhoto] = field(default_factory=list)


@dataclass(slots=True)
class TradeMedia:
    rooms: dict[uuid.UUID, RoomMedia] = field(default_factory=dict)
    expires_at: datetime | None = None


class TradeMediaService:
    def __init__(self, db: AsyncSession, storage: MediaStorage | None) -> None:
        self.db = db
        self.storage = storage

    async def for_trade(self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str) -> TradeMedia:
        out = TradeMedia()
        if self.storage is None:
            return out
        report = await PhotoReportReadModel(self.db).build(owner_id, project_id, only_included=False)
        picked = {room.room_id: rules.pick(room, trade) for room in report.rooms}
        asset_ids = {p.photo.asset_id for own, route in picked.values() for p in (*own, *route)}
        if not asset_ids:
            return out
        thumbs = dict(
            (await self.db.execute(select(PhotoAsset.id, PhotoAsset.storage_key_thumbnail).where(PhotoAsset.id.in_(asset_ids), PhotoAsset.project_id == project_id))).all()
        )
        ttl = rules.URL_TTL_SECONDS
        try:
            for room_id, (own, route) in picked.items():
                media = RoomMedia()
                for target, items in ((media.photos, own), (media.route_map, route)):
                    for item in items:
                        thumb_key = thumbs.get(item.photo.asset_id)
                        if thumb_key is None:
                            continue
                        target.append(
                            PortalPhoto(
                                id=item.photo.attachment_id,
                                thumb_url=await self.storage.presign_get(thumb_key, ttl),
                                url=await self.storage.presign_get(item.photo.storage_key_display, ttl),
                                width=item.photo.width,
                                height=item.photo.height,
                                place=item.place,
                                markers=[
                                    PortalMarker(
                                        x=m.x, y=m.y, label=m.label, utility=m.utility, depth_cm=m.depth_cm, from_floor_cm=m.from_floor_cm, from_corner_cm=m.from_corner_cm
                                    )
                                    for m in item.markers
                                ],
                            )
                        )
                if media.photos or media.route_map:
                    out.rooms[room_id] = media
        except MediaStorageDisabled:
            return TradeMedia()
        if out.rooms:
            out.expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
        return out
