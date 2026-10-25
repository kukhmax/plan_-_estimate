"""The materials of the packages "Płytki" and "GKL" (V2-11): the owner's norms, the calculations of a room, the statement of an object and its addition to an estimate.

Owner-scoped like every service. The arithmetic is `domain/rules/materials.py` (pure); this service reads the owner's norms (made from the starting ones on first use), runs the rules over
the data of a calculation and joins the price of the Price Book item that a material is tied to. The statement is never stored. Adding to an estimate is a **snapshot** of a draft: one line
per material of the object (the packs over the sum of the calculations), a manual one (so the regeneration of the plan of works never touches it), whose identity is made from the object and
the material, so a second addition adds nothing that is already there.
"""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.data.material_norms import BY_CODE, NORMS, PARAM
from app.domain.exceptions import (
    EstimateStateError,
    MaterialInvalidError,
    MaterialNotFoundError,
    ProjectNotFoundError,
)
from app.domain.rules import materials as rules
from app.domain.services.estimate_service import EstimateService, _compute_amount
from app.models.estimate import EstimateLine, EstimateStatus, LineOrigin, QuantitySource
from app.models.material import MaterialCalc, MaterialNorm
from app.models.price_item import PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.schemas.material import DrywallParams, TileParams

CENT = Decimal("0.01")
NAMESPACE = uuid.UUID("5d0c6f0e-6a53-4f0a-9d3b-2f6b0a1c7e11")  # the identity of the lines of the statement: made from the object and the material


@dataclass(frozen=True, slots=True)
class NormView:
    row: MaterialNorm
    item: PriceItem | None


@dataclass(frozen=True, slots=True)
class MaterialView:
    qty: rules.MaterialQty
    name: str
    billing_unit: str
    packs: int | None
    billing_quantity: Decimal


@dataclass(frozen=True, slots=True)
class CalcView:
    row: MaterialCalc
    materials: list[MaterialView]


@dataclass(frozen=True, slots=True)
class TotalView:
    total: rules.MaterialTotal
    package: str
    name: str
    billing_unit: str
    price_item_id: uuid.UUID | None
    unit_price: Decimal | None
    amount: Decimal | None


@dataclass(slots=True)
class Statement:
    calcs: list[tuple[CalcView, str]] = field(default_factory=list)  # with the name of the room
    totals: list[TotalView] = field(default_factory=list)
    amount: Decimal | None = None
    unpriced: int = 0


@dataclass(slots=True)
class AddedMaterials:
    added: list[EstimateLine] = field(default_factory=list)
    already: int = 0
    skipped: list[str] = field(default_factory=list)


def _title(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


class MaterialsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- the norms ---------------------------------------------------------------

    async def ensure_norms(self, owner_id: uuid.UUID) -> dict[str, MaterialNorm]:
        """The owner's norms by code; the missing rows are made from the starting ones (idempotent, committed only when something was made)."""
        rows = {r.code: r for r in (await self.db.execute(select(MaterialNorm).where(MaterialNorm.owner_id == owner_id))).scalars()}
        made = False
        now = datetime.now(UTC)
        for definition in NORMS:
            if definition.code in rows:
                continue
            row = MaterialNorm(
                owner_id=owner_id, code=definition.code, package=definition.package, kind=definition.kind, name=definition.name, value=definition.default,
                created_at=now, updated_at=now,
            )
            self.db.add(row)
            rows[definition.code] = row
            made = True
        if made:
            await self.db.commit()
        return rows

    async def _items(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, PriceItem]:
        if not ids:
            return {}
        return {i.id: i for i in (await self.db.execute(select(PriceItem).where(PriceItem.id.in_(ids)))).scalars()}

    async def list_norms(self, owner_id: uuid.UUID) -> list[NormView]:
        rows = await self.ensure_norms(owner_id)
        items = await self._items({r.price_item_id for r in rows.values() if r.price_item_id})
        order = {d.code: i for i, d in enumerate(NORMS)}
        return [NormView(r, items.get(r.price_item_id) if r.price_item_id else None) for r in sorted(rows.values(), key=lambda r: order.get(r.code, 9999))]

    async def update_norm(self, owner_id: uuid.UUID, norm_id: uuid.UUID, changes: dict[str, Any]) -> NormView:
        await self.ensure_norms(owner_id)
        row = (await self.db.execute(select(MaterialNorm).where(MaterialNorm.id == norm_id, MaterialNorm.owner_id == owner_id))).scalar_one_or_none()
        if row is None:
            raise MaterialNotFoundError(f"Norm {norm_id} not found")
        definition = BY_CODE[row.code]
        if changes.get("reset"):
            row.value, row.name, row.price_item_id = definition.default, definition.name, None
        if definition.kind == PARAM:
            if changes.get("name") is not None or changes.get("price_item_id") is not None:
                raise MaterialInvalidError("NORM_NOT_A_MATERIAL", "a number has no name and no price item")
            if changes.get("value") is not None:
                value = changes["value"]
                if not definition.minimum <= value <= definition.maximum:
                    raise MaterialInvalidError("NORM_OUT_OF_RANGE", f"the number must be between {definition.minimum} and {definition.maximum}")
                row.value = value
        else:
            if changes.get("value") is not None:
                raise MaterialInvalidError("NORM_NOT_A_NUMBER", "a material has no number")
            if changes.get("name") is not None:
                row.name = changes["name"].strip() or definition.name
            if "price_item_id" in changes and not changes.get("reset"):
                row.price_item_id = None if changes["price_item_id"] is None else (await self._item_for(owner_id, changes["price_item_id"], definition.billing_unit)).id
        row.updated_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(row)
        return (await self._norm_views([row]))[0]

    async def _norm_views(self, rows: list[MaterialNorm]) -> list[NormView]:
        items = await self._items({r.price_item_id for r in rows if r.price_item_id})
        return [NormView(r, items.get(r.price_item_id) if r.price_item_id else None) for r in rows]

    async def _item_for(self, owner_id: uuid.UUID, item_id: uuid.UUID, billing_unit: str | None) -> PriceItem:
        item = (await self.db.execute(select(PriceItem).where(PriceItem.id == item_id, PriceItem.owner_id == owner_id))).scalar_one_or_none()
        if item is None:
            raise MaterialInvalidError("NORM_ITEM_UNKNOWN", "the price item is not in your price book")
        if item.is_archived:
            raise MaterialInvalidError("NORM_ITEM_ARCHIVED", "the price item is archived")
        if item.unit.value != billing_unit:
            raise MaterialInvalidError("NORM_ITEM_UNIT_MISMATCH", f"this material is bought in {billing_unit}, the item is in {item.unit.value}")
        return item

    async def _numbers(self, owner_id: uuid.UUID) -> rules.Norms:
        rows = await self.ensure_norms(owner_id)
        return {code: row.value for code, row in rows.items() if BY_CODE[code].kind == PARAM and row.value is not None}

    # -- the calculations of a room ----------------------------------------------

    async def _ensure_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        found = (await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
        if found is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _ensure_room(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID) -> Room:
        await self._ensure_project(owner_id, project_id)
        room = (await self.db.execute(select(Room).where(Room.id == room_id, Room.project_id == project_id))).scalar_one_or_none()
        if room is None:
            raise ProjectNotFoundError(f"Room {room_id} not found")
        return room

    async def _get(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, calc_id: uuid.UUID) -> MaterialCalc:
        await self._ensure_room(owner_id, project_id, room_id)
        row = (await self.db.execute(
            select(MaterialCalc).where(MaterialCalc.id == calc_id, MaterialCalc.room_id == room_id, MaterialCalc.owner_id == owner_id)
        )).scalar_one_or_none()
        if row is None:
            raise MaterialNotFoundError(f"Calculation {calc_id} not found")
        return row

    def _quantities(self, row: MaterialCalc, numbers: rules.Norms) -> list[rules.MaterialQty]:
        if row.package == "TILE":
            p = TileParams.model_validate(row.params)
            return rules.tile_materials(
                rules.TileInput(
                    p.area_m2, p.length_cm, p.width_cm, p.thickness_mm, p.joint_mm, p.layout == "DIAGONAL", p.waterproof, p.waterproof_area_m2, p.tape_m,
                ),
                numbers,
            )
        d = DrywallParams.model_validate(row.params)
        return rules.drywall_materials(rules.DrywallInput(d.kind == "CEILING", d.area_m2, d.layers, d.height_m, d.perimeter_m), numbers)

    def _view(self, row: MaterialCalc, numbers: rules.Norms, names: dict[str, str]) -> CalcView:
        views = []
        for qty in self._quantities(row, numbers):
            count = rules.packs(qty.quantity, qty.pack_size) if qty.pack_size is not None else None
            billing = Decimal(count) if count is not None else rules.ceil_to(qty.quantity, rules.TWO_PLACES)
            views.append(MaterialView(qty, names.get(qty.code, BY_CODE[qty.code].name), BY_CODE[qty.code].billing_unit or "PCS", count, billing))
        return CalcView(row, views)

    async def _names(self, owner_id: uuid.UUID) -> dict[str, str]:
        return {code: row.name for code, row in (await self.ensure_norms(owner_id)).items()}

    async def list_calcs(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID) -> list[CalcView]:
        await self._ensure_room(owner_id, project_id, room_id)
        rows = list((await self.db.execute(
            select(MaterialCalc).where(MaterialCalc.room_id == room_id, MaterialCalc.owner_id == owner_id).order_by(MaterialCalc.position, MaterialCalc.created_at, MaterialCalc.id)
        )).scalars())
        numbers, names = await self._numbers(owner_id), await self._names(owner_id)
        return [self._view(r, numbers, names) for r in rows]

    async def create_calc(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, package: str, title: str | None, params: dict[str, Any]) -> CalcView:
        await self._ensure_room(owner_id, project_id, room_id)
        position = (await self.db.execute(select(func.coalesce(func.max(MaterialCalc.position), -1)).where(MaterialCalc.room_id == room_id))).scalar_one() + 1
        now = datetime.now(UTC)
        row = MaterialCalc(
            owner_id=owner_id, project_id=project_id, room_id=room_id, package=package, title=_title(title), params=params, position=position, created_at=now, updated_at=now,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return self._view(row, await self._numbers(owner_id), await self._names(owner_id))

    async def change_calc(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, calc_id: uuid.UUID, changes: dict[str, Any]) -> CalcView:
        row = await self._get(owner_id, project_id, room_id, calc_id)
        if "title" in changes:
            row.title = _title(changes["title"])
        if changes.get("params") is not None:
            model = TileParams if row.package == "TILE" else DrywallParams
            row.params = model.model_validate(changes["params"]).model_dump(mode="json")  # a ValidationError is the caller's 422
        row.updated_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(row)
        return self._view(row, await self._numbers(owner_id), await self._names(owner_id))

    async def delete_calc(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, calc_id: uuid.UUID) -> None:
        row = await self._get(owner_id, project_id, room_id, calc_id)
        await self.db.execute(delete(MaterialCalc).where(MaterialCalc.id == row.id))
        await self.db.commit()

    # -- the statement -----------------------------------------------------------

    async def statement(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> Statement:
        await self._ensure_project(owner_id, project_id)
        rows = list((await self.db.execute(
            select(MaterialCalc, Room.name).join(Room, Room.id == MaterialCalc.room_id)
            .where(MaterialCalc.project_id == project_id, MaterialCalc.owner_id == owner_id).order_by(Room.created_at, Room.id, MaterialCalc.position, MaterialCalc.id)
        )).all())
        norm_rows = await self.ensure_norms(owner_id)
        numbers = {code: r.value for code, r in norm_rows.items() if BY_CODE[code].kind == PARAM and r.value is not None}
        names = {code: r.name for code, r in norm_rows.items()}
        statement = Statement()
        views = [(self._view(calc, numbers, names), room_name) for calc, room_name in rows]
        statement.calcs = views
        items = await self._items({r.price_item_id for r in norm_rows.values() if r.price_item_id})
        priced = Decimal(0)
        for entry in rules.total([[m.qty for m in view.materials] for view, _ in views]):
            definition = BY_CODE[entry.code]
            norm = norm_rows[entry.code]
            item = items.get(norm.price_item_id) if norm.price_item_id else None
            price = item.price if item is not None and not item.is_archived and item.unit.value == definition.billing_unit else None
            amount = (entry.billing_quantity * price).quantize(CENT) if price is not None else None
            if amount is None:
                statement.unpriced += 1
            else:
                priced += amount
            statement.totals.append(TotalView(entry, definition.package, norm.name, definition.billing_unit or "PCS", item.id if item is not None else None, price, amount))
        statement.amount = priced if statement.totals and statement.unpriced < len(statement.totals) else None
        return statement

    # -- the estimate ------------------------------------------------------------

    async def add_to_estimate(self, owner_id: uuid.UUID, project_id: uuid.UUID, estimate_id: uuid.UUID) -> AddedMaterials:
        """One line per material of the object that is not in the draft estimate yet (the packs over the sum of the calculations). A DRAFT only; a material whose item has gone is skipped and named."""
        estimates = EstimateService(self.db)
        estimate = await estimates._fetch_estimate(estimate_id, owner_id, project_id=project_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise EstimateStateError(f"Lines can only be added to DRAFT estimates; estimate {estimate_id} is {estimate.status.value}")
        statement = await self.statement(owner_id, project_id)
        norm_rows = await self.ensure_norms(owner_id)
        items = await self._items({r.price_item_id for r in norm_rows.values() if r.price_item_id})
        result = AddedMaterials()
        present = {line.occurrence_key for line in estimate.lines if line.occurrence_key is not None}
        position = max((line.position for line in estimate.lines), default=-1) + 1
        for entry in statement.totals:
            identity = uuid.uuid5(NAMESPACE, f"{project_id}:{entry.total.code}")
            if identity in present:
                result.already += 1
                continue
            item = items.get(entry.price_item_id) if entry.price_item_id else None
            if item is not None and (item.is_archived or item.unit.value != entry.billing_unit):
                result.skipped.append(entry.total.code)
                continue
            quantity = entry.total.billing_quantity
            price = item.price if item is not None else None
            line = EstimateLine(
                estimate_id=estimate.id, origin=LineOrigin.MANUAL, position=position, occurrence_key=identity, price_item_id=item.id if item else None,
                item_code=item.code if item else None, description=((item.display_name or item.name_key or item.code) if item else entry.name)[:255], unit=PriceUnit(entry.billing_unit), scope=item.price_scope if item else PriceScope.MATERIAL,
                currency=item.currency if item else estimate.currency, source_quantity=quantity, quantity=quantity, quantity_source=QuantitySource.MANUAL,
                quantity_overridden=False, unit_price=price, price_override=True, amount=_compute_amount(quantity, price),
            )
            self.db.add(line)
            estimate.lines.append(line)
            result.added.append(line)
            position += 1
        if result.added:
            estimates.recalculate_totals(estimate)
        await self.db.commit()
        return result
