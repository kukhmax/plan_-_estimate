"""The points and routes of a room (V2-10): the owner's list of "a price item x a quantity" rows, and their addition to an estimate.

Owner-scoped like every service. A row may name only an own, live Price Book item whose unit is `PCS` (a point) or `LM` (a route). The unit is the item's, read when it is
needed: if the owner changed the unit of the item later, the row no longer goes to an estimate and the answer says so. Adding to an estimate is a **snapshot** (like the
other lines of an estimate): the line carries the name, the unit, the quantity and the price of that moment, the room it is in, and the row's id as its identity, so a
second addition adds nothing that is already there. The line is a manual one (`LineOrigin.MANUAL`), so the regeneration of the plan of works never touches it.
"""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    EstimateStateError,
    ProjectNotFoundError,
    RoomPointInvalidError,
    RoomPointNotFoundError,
)
from app.domain.services.estimate_service import EstimateService, _compute_amount
from app.models.estimate import EstimateLine, EstimateStatus, LineOrigin, QuantitySource
from app.models.price_item import PriceItem, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.room_point import RoomPoint

POINT_UNITS = (PriceUnit.PCS, PriceUnit.LM)


@dataclass(frozen=True, slots=True)
class PointView:
    row: RoomPoint
    item: PriceItem


@dataclass(slots=True)
class AddedToEstimate:
    added: list[EstimateLine] = field(default_factory=list)
    already: int = 0
    skipped: list[tuple[uuid.UUID, str]] = field(default_factory=list)  # (row id, code): POINT_UNIT_INVALID / POINT_ITEM_ARCHIVED


def _note(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


class RoomPointsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        found = (await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
        if found is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _ensure_room(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID) -> Room:
        await self._ensure_project(owner_id, project_id)
        room = (await self.db.execute(select(Room).where(Room.id == room_id, Room.project_id == project_id))).scalar_one_or_none()
        if room is None:
            raise ProjectNotFoundError(f"Room {room_id} not found")  # a room of another object is as good as none: the same 404
        return room

    async def _item(self, owner_id: uuid.UUID, item_id: uuid.UUID) -> PriceItem:
        item = (await self.db.execute(select(PriceItem).where(PriceItem.id == item_id, PriceItem.owner_id == owner_id))).scalar_one_or_none()
        if item is None:
            raise RoomPointInvalidError("POINT_ITEM_UNKNOWN", "the price item is not in your price book")
        if item.is_archived:
            raise RoomPointInvalidError("POINT_ITEM_ARCHIVED", "the price item is archived")
        if item.unit not in POINT_UNITS:
            raise RoomPointInvalidError("POINT_UNIT_INVALID", "only an item in pieces or in running metres can be a point or a route")
        return item

    async def _get(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, point_id: uuid.UUID) -> RoomPoint:
        await self._ensure_room(owner_id, project_id, room_id)
        row = (await self.db.execute(
            select(RoomPoint).where(RoomPoint.id == point_id, RoomPoint.room_id == room_id, RoomPoint.owner_id == owner_id)
        )).scalar_one_or_none()
        if row is None:
            raise RoomPointNotFoundError(f"Point {point_id} not found")
        return row

    async def _views(self, rows: list[RoomPoint]) -> list[PointView]:
        if not rows:
            return []
        items = {i.id: i for i in (await self.db.execute(select(PriceItem).where(PriceItem.id.in_({r.price_item_id for r in rows})))).scalars()}
        return [PointView(r, items[r.price_item_id]) for r in rows]

    # -- reading ------------------------------------------------------------------

    async def list_points(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID) -> list[PointView]:
        await self._ensure_room(owner_id, project_id, room_id)
        rows = list((await self.db.execute(
            select(RoomPoint).where(RoomPoint.room_id == room_id, RoomPoint.owner_id == owner_id).order_by(RoomPoint.position, RoomPoint.created_at, RoomPoint.id)
        )).scalars())
        return await self._views(rows)

    async def count_by_room(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """How many rows each room of the object has (the badge of the room's card)."""
        await self._ensure_project(owner_id, project_id)
        rows = (await self.db.execute(
            select(RoomPoint.room_id, func.count()).where(RoomPoint.project_id == project_id, RoomPoint.owner_id == owner_id).group_by(RoomPoint.room_id)
        )).all()
        return {room_id: count for room_id, count in rows}

    # -- writing ------------------------------------------------------------------

    async def create(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, data: dict[str, Any]) -> PointView:
        await self._ensure_room(owner_id, project_id, room_id)
        item = await self._item(owner_id, data["price_item_id"])
        position = (await self.db.execute(select(func.coalesce(func.max(RoomPoint.position), -1)).where(RoomPoint.room_id == room_id))).scalar_one() + 1
        now = datetime.now(UTC)
        row = RoomPoint(
            owner_id=owner_id, project_id=project_id, room_id=room_id, price_item_id=item.id, quantity=data["quantity"], note=_note(data.get("note")),
            position=position, created_at=now, updated_at=now,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return PointView(row, item)

    async def change(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, point_id: uuid.UUID, changes: dict[str, Any]) -> PointView:
        row = await self._get(owner_id, project_id, room_id, point_id)
        if changes.get("price_item_id") is not None and changes["price_item_id"] != row.price_item_id:
            row.price_item_id = (await self._item(owner_id, changes["price_item_id"])).id
        if changes.get("quantity") is not None:
            row.quantity = changes["quantity"]
        if "note" in changes:
            row.note = _note(changes["note"])
        row.updated_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(row)
        return (await self._views([row]))[0]

    async def delete(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, point_id: uuid.UUID) -> None:
        row = await self._get(owner_id, project_id, room_id, point_id)
        await self.db.execute(delete(RoomPoint).where(RoomPoint.id == row.id))
        await self.db.commit()

    # -- the estimate -------------------------------------------------------------

    async def add_to_estimate(self, owner_id: uuid.UUID, project_id: uuid.UUID, estimate_id: uuid.UUID) -> AddedToEstimate:
        """Add every row of the object that is not in the estimate yet, as one line each. A DRAFT estimate only; a row whose item has gone (archived, another unit) is
        skipped and named in the answer. Nothing is added twice: the identity of the line is the id of the row."""
        estimates = EstimateService(self.db)
        estimate = await estimates._fetch_estimate(estimate_id, owner_id, project_id=project_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise EstimateStateError(f"Lines can only be added to DRAFT estimates; estimate {estimate_id} is {estimate.status.value}")
        rows = list((await self.db.execute(
            select(RoomPoint).join(Room, Room.id == RoomPoint.room_id).where(RoomPoint.project_id == project_id, RoomPoint.owner_id == owner_id)
            .order_by(Room.created_at, Room.id, RoomPoint.position, RoomPoint.id)  # the rooms in the order they were made, the rows in the order of entry
        )).scalars())
        result = AddedToEstimate()
        present = {line.occurrence_key for line in estimate.lines if line.occurrence_key is not None}
        position = max((line.position for line in estimate.lines), default=-1) + 1
        for view in await self._views(rows):
            row, item = view.row, view.item
            if row.id in present:
                result.already += 1
                continue
            if item.is_archived:
                result.skipped.append((row.id, "POINT_ITEM_ARCHIVED"))
                continue
            if item.unit not in POINT_UNITS:
                result.skipped.append((row.id, "POINT_UNIT_INVALID"))
                continue
            quantity = Decimal(row.quantity)
            line = EstimateLine(
                estimate_id=estimate.id, origin=LineOrigin.MANUAL, position=position, occurrence_key=row.id, room_id=row.room_id, price_item_id=item.id,
                item_code=item.code, description=(item.display_name or item.name_key or item.code)[:255], unit=item.unit, scope=item.price_scope,
                currency=item.currency, source_quantity=quantity, quantity=quantity, quantity_source=QuantitySource.MANUAL, quantity_overridden=False,
                unit_price=item.price, price_override=True, amount=_compute_amount(quantity, item.price),
            )
            self.db.add(line)
            estimate.lines.append(line)
            result.added.append(line)
            position += 1
        if result.added:
            estimates.recalculate_totals(estimate)
        await self.db.commit()
        return result
