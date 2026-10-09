"""Recommended extra works with their prices, for a client document (Stage 15E.3).

Stage 11 turns the risks of a finished inspection into recommendations: "this risk -> this work of the price book, on this
surface". A client report shows them as a separate block so the client sees *risk -> work -> price*. The price is never made
up here: it is the price of the same work on the same surface in the **current estimate** of the object (the latest estimate
that is not archived), exactly as printed there -- quantity, unit, unit price and amount.

What is listed: active recommendations that are PENDING or ACCEPTED (a dismissed one is the owner's "no") of a live inspection
of a live room, aimed at a wall, a ceiling or a floor; a recommendation for a whole room is advisory only and has no surface
to price, so it is left out. Each work on each surface is listed once, with every reason that asks for it. A listed work
without a price in the estimate is `priced = False`; the document layer refuses to issue a report with one ("no unknown
prices in the final version"), and says which.

Read-only; the number of SQL statements does not depend on the number of recommendations.
"""
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.project_service import ProjectService
from app.models.estimate import Estimate, EstimateLine, EstimateStatus
from app.models.inspection import Inspection, InspectionFinding
from app.models.price_item import PriceItem
from app.models.risk import Risk
from app.models.room import Room
from app.models.surface import Surface
from app.models.work_recommendation import (
    WorkRecommendation,
    WorkRecommendationStatus,
    WorkRecommendationTargetKind,
)


@dataclass(frozen=True, slots=True)
class EstimatePrice:
    """One line of the current estimate, as printed there."""

    quantity: Decimal
    unit: str
    unit_price: Decimal | None
    amount: Decimal | None
    currency: str


@dataclass(frozen=True, slots=True)
class RecommendedWork:
    room_id: uuid.UUID
    room_name: str
    surface_id: uuid.UUID
    surface_name: str
    work_code: str
    work_display_name: str | None  # the owner's own name for the work, else None
    work_name_key: str | None  # the built-in key of the work, else None
    risk_title_keys: tuple[str, ...]  # why: the title keys of the risks that ask for it
    finding_label_keys: tuple[str, ...]  # why: the labels of the findings that ask for it
    accepted: bool
    prices: tuple[EstimatePrice, ...]  # empty = the work has no line in the current estimate
    # Where to go to fix a missing price (Stage 15H.1): the surface kind and the inspection that holds the recommendation
    surface_type: str = "WALL"
    inspection_id: uuid.UUID | None = None
    inspection_surface_id: uuid.UUID | None = None  # the inspection's own carrier: a wall ...
    inspection_plane: str | None = None  # ... or a FLOOR / CEILING plane (both None = a room inspection)
    estimate_exists: bool = True

    @property
    def priced(self) -> bool:
        return bool(self.prices) and all(p.unit_price is not None and p.amount is not None for p in self.prices)

    @property
    def block_reason(self) -> str | None:
        """Why the work has no price, in the order the owner has to act: decide the recommendation (PENDING), have an
        estimate (NO_ESTIMATE), bring the accepted work into it (NOT_IN_ESTIMATE: accepting never touches an estimate),
        or fix a line that has no price (NO_PRICE). None = priced."""
        if self.priced:
            return None
        if not self.accepted:
            return "PENDING"
        if not self.estimate_exists:
            return "NO_ESTIMATE"
        return "NOT_IN_ESTIMATE" if not self.prices else "NO_PRICE"


@dataclass(frozen=True, slots=True)
class RecommendedWorks:
    estimate_version: int | None  # the current estimate whose prices are used; None = the object has no estimate
    estimate_status: str | None
    items: tuple[RecommendedWork, ...]
    estimate_id: uuid.UUID | None = None

    def in_rooms(self, room_ids: frozenset[uuid.UUID] | None) -> "RecommendedWorks":
        if room_ids is None:
            return self
        return RecommendedWorks(
            self.estimate_version,
            self.estimate_status,
            tuple(i for i in self.items if i.room_id in room_ids),
            self.estimate_id,
        )

    @property
    def unpriced(self) -> tuple[RecommendedWork, ...]:
        return tuple(item for item in self.items if not item.priced)


class RecommendedWorkReadModel:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> RecommendedWorks:
        """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then)."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        estimate = (
            await self.db.execute(
                select(Estimate)
                .where(
                    Estimate.project_id == project_id,
                    Estimate.owner_id == owner_id,
                    Estimate.status != EstimateStatus.ARCHIVED,
                )
                .order_by(Estimate.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        rooms = {r.id: r for r in await self._rows(Room, Room.project_id, [project_id]) if not r.is_archived}
        recommendations = [
            r
            for r in await self._rows(WorkRecommendation, WorkRecommendation.room_id, list(rooms))
            if r.is_active
            and r.status in (WorkRecommendationStatus.PENDING, WorkRecommendationStatus.ACCEPTED)
            and r.target_kind is not WorkRecommendationTargetKind.ROOM
            and r.surface_id is not None
        ]
        inspections = {i.id: i for i in await self._rows(Inspection, Inspection.id, list({r.inspection_id for r in recommendations}))}
        surfaces = {s.id: s for s in await self._rows(Surface, Surface.id, list({r.surface_id for r in recommendations}))}
        recommendations = [
            r
            for r in recommendations
            if r.inspection_id in inspections
            and not inspections[r.inspection_id].is_archived
            and r.surface_id in surfaces
            and not surfaces[r.surface_id].is_archived
        ]
        risks = {r.id: r for r in await self._rows(Risk, Risk.id, [r.risk_id for r in recommendations if r.risk_id])}
        findings = {
            f.id: f
            for f in await self._rows(InspectionFinding, InspectionFinding.id, [r.finding_id for r in recommendations if r.finding_id])
        }
        codes = {r.recommended_work_code for r in recommendations}
        by_code: dict[str, PriceItem] = {}
        if codes:
            by_code = {
                p.code: p
                for p in (
                    await self.db.execute(select(PriceItem).where(PriceItem.owner_id == owner_id, PriceItem.code.in_(codes)))
                ).scalars()
            }
        resolved = {p.id: p for p in await self._rows(PriceItem, PriceItem.id, [r.resolved_price_item_id for r in recommendations if r.resolved_price_item_id])}

        lines: list[EstimateLine] = []
        if estimate is not None and recommendations:
            lines = list(
                (
                    await self.db.execute(
                        select(EstimateLine)
                        .where(EstimateLine.estimate_id == estimate.id, EstimateLine.surface_id.in_(list(surfaces)))
                        .order_by(EstimateLine.position)
                    )
                ).scalars()
            )

        # one entry per (surface, price item): several risks may ask for the same work
        merged: dict[tuple[uuid.UUID, str], dict] = {}
        for rec in sorted(recommendations, key=lambda r: (str(r.surface_id), r.recommended_work_code, str(r.id))):
            item = resolved.get(rec.resolved_price_item_id) if rec.resolved_price_item_id else by_code.get(rec.recommended_work_code)
            key = (rec.surface_id, str(item.id) if item else f"code:{rec.recommended_work_code}")
            entry = merged.setdefault(
                key,
                {"rec": rec, "item": item, "risk_keys": [], "finding_keys": [], "accepted": False},
            )
            risk = risks.get(rec.risk_id) if rec.risk_id else None
            if risk is not None and risk.title_key not in entry["risk_keys"]:
                entry["risk_keys"].append(risk.title_key)
            finding = findings.get(rec.finding_id) if rec.finding_id else None
            if finding is not None and finding.label_key and finding.label_key not in entry["finding_keys"]:
                entry["finding_keys"].append(finding.label_key)
            entry["accepted"] = entry["accepted"] or rec.status is WorkRecommendationStatus.ACCEPTED

        items: list[RecommendedWork] = []
        for (surface_id, _), entry in merged.items():
            rec, item = entry["rec"], entry["item"]
            surface = surfaces[surface_id]
            room = rooms[rec.room_id]
            matched = tuple(
                EstimatePrice(line.quantity, line.unit.value, line.unit_price, line.amount, line.currency)
                for line in lines
                if item is not None and line.surface_id == surface_id and line.opening_id is None and line.price_item_id == item.id
            )
            items.append(
                RecommendedWork(
                    room_id=room.id,
                    room_name=room.name,
                    surface_id=surface_id,
                    surface_name=surface.name,
                    work_code=rec.recommended_work_code,
                    work_display_name=item.display_name if item else None,
                    work_name_key=item.name_key if item else None,
                    risk_title_keys=tuple(entry["risk_keys"]),
                    finding_label_keys=tuple(entry["finding_keys"]),
                    accepted=entry["accepted"],
                    prices=matched,
                    surface_type=surface.surface_type.value,
                    inspection_id=rec.inspection_id,
                    inspection_surface_id=inspections[rec.inspection_id].surface_id,
                    inspection_plane=inspections[rec.inspection_id].plane.value if inspections[rec.inspection_id].plane else None,
                    estimate_exists=estimate is not None,
                )
            )
        room_order = {rid: n for n, rid in enumerate(sorted(rooms, key=lambda i: (rooms[i].created_at, i)))}
        items.sort(key=lambda w: (room_order[w.room_id], w.surface_name, w.work_code, str(w.surface_id)))
        return RecommendedWorks(
            estimate_version=estimate.version if estimate else None,
            estimate_status=estimate.status.value if estimate else None,
            items=tuple(items),
            estimate_id=estimate.id if estimate else None,
        )

    async def _rows(self, model, column, ids: list) -> list:
        if not ids:
            return []
        return list((await self.db.execute(select(model).where(column.in_(ids)))).scalars().all())
