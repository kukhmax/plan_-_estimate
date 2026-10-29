"""Carrying the answers of a craftsman over into the rooms (V2-14a; docs/V2_14A_PLAN_RU.md): the owner's button. Reads the answers, plans what the pure rules
(`domain/rules/trade_transfer.py`) decide, shows it (preview) and writes it in one transaction (apply). Owner-scoped like every service.

Rows marked `source = TRADE_LINK` are changed or removed freely; a row the owner typed is touched only when it names what the craftsman also gives AND the owner chose
REPLACE (taken over / removed, shown in the preview). The estimate is not touched (it keeps its snapshot).
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ProjectNotFoundError
from app.domain.rules import trade_checklist as checklist
from app.domain.rules import trade_transfer as rules
from app.domain.services.room_service import RoomService
from app.models.material import MaterialCalc
from app.models.price_item import PriceItem, PriceUnit
from app.models.project import Project
from app.models.room_point import RoomPoint
from app.models.trade_link import TradeAnswer
from app.schemas.material import ElectricParams, PlumbingParams
from app.schemas.trade_transfer import (
    MaterialPlan,
    CandidateRead,
    PositionPlan,
    RoomPlan,
    RowPlan,
    TransferPreview,
    TransferResult,
)

POINT_UNITS = (PriceUnit.PCS, PriceUnit.LM)
PARAMS = {"ELECTRIC": ElectricParams, "PLUMBING": PlumbingParams}


class _Plan:
    """What one reading of the answers decided: the preview is made of it and so is the writing, so that they cannot differ."""

    def __init__(self) -> None:
        self.preview: TransferPreview | None = None
        self.rows: dict[uuid.UUID, list[rules.RowAction]] = {}
        self.material: dict[uuid.UUID, tuple[str, dict | None, MaterialCalc | None, list[MaterialCalc]]] = {}


class TradeTransferService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        found = (await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
        if found is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _items(self, owner_id: uuid.UUID) -> list[PriceItem]:
        return list(
            (
                await self.db.execute(
                    select(PriceItem)
                    .where(PriceItem.owner_id == owner_id, PriceItem.is_archived.is_(False), PriceItem.unit.in_(POINT_UNITS))
                    .order_by(PriceItem.category, PriceItem.display_name, PriceItem.code)
                )
            ).scalars()
        )

    @staticmethod
    def _read(item: PriceItem, trade: str) -> CandidateRead:
        return CandidateRead(
            id=item.id, code=item.code, name_key=item.name_key, display_name=item.display_name, category=item.category, unit=item.unit, price=item.price, is_archived=item.is_archived,
            relevant=rules.is_relevant(trade, item.category.value),
        )

    async def _plan(self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str, given: dict[str, uuid.UUID | None], own_mode: str = rules.REPLACE) -> _Plan:
        trade = checklist.clean_trade(trade)
        await self._ensure_project(owner_id, project_id)
        positions = checklist.positions_of(trade)
        keys = tuple(p.key for p in positions)
        items = await self._items(owner_id)
        by_id = {i.id: i for i in items}

        # the choice of the item of the price book for each typical position that has one
        defaults: dict[str, uuid.UUID | None] = {}
        for pos in positions:
            name = rules.default_item_name(pos.key)
            defaults[pos.key] = None
            if name is not None:
                found = [i for i in items if i.unit.value == pos.unit and (i.display_name or "").strip().casefold() == name.casefold()]
                defaults[pos.key] = found[0].id if found else None
        for key, item_id in given.items():
            if key not in keys or rules.default_item_name(key) is None:
                raise checklist.TradeChecklistError("TRANSFER_ITEM_INVALID", f"the position {key!r} does not go to the price book", "mapping")
            pos_unit = next(p.unit for p in positions if p.key == key)
            if item_id is not None and (item_id not in by_id or by_id[item_id].unit.value != pos_unit):
                raise checklist.TradeChecklistError("TRANSFER_ITEM_INVALID", "the item is not an own, live item of the price book in the unit of the position", "mapping")
        chosen = {key: (given[key] if key in given else defaults[key]) for key in keys}

        # the answers
        rooms, _total = await RoomService(self.db).list_rooms(project_id, owner_id)
        rows = list(
            (await self.db.execute(select(TradeAnswer).where(TradeAnswer.project_id == project_id, TradeAnswer.owner_id == owner_id, TradeAnswer.trade == trade))).scalars()
        )
        typical: dict[uuid.UUID, dict[str, rules.Answer]] = {}
        own = 0
        for row in rows:
            if row.position_key is None:
                own += 1
            else:
                typical.setdefault(row.room_id, {})[row.position_key] = rules.Answer(row.quantity, row.note)

        # what an earlier carrying over made
        ours = list(
            (
                await self.db.execute(
                    select(RoomPoint).where(RoomPoint.project_id == project_id, RoomPoint.owner_id == owner_id, RoomPoint.source == rules.SOURCE).order_by(RoomPoint.position, RoomPoint.id)
                )
            ).scalars()
        )
        calcs = list(
            (
                await self.db.execute(
                    select(MaterialCalc)
                    .where(MaterialCalc.project_id == project_id, MaterialCalc.owner_id == owner_id, MaterialCalc.source == rules.SOURCE, MaterialCalc.package == rules.package_of(trade))
                    .order_by(MaterialCalc.position, MaterialCalc.id)
                )
            ).scalars()
        )
        # what the owner typed himself (the same item / package in a room is the same thing counted twice)
        owners = list(
            (
                await self.db.execute(
                    select(RoomPoint).where(RoomPoint.project_id == project_id, RoomPoint.owner_id == owner_id, RoomPoint.source.is_(None)).order_by(RoomPoint.position, RoomPoint.id)
                )
            ).scalars()
        )
        owner_calcs = list(
            (
                await self.db.execute(
                    select(MaterialCalc)
                    .where(MaterialCalc.project_id == project_id, MaterialCalc.owner_id == owner_id, MaterialCalc.source.is_(None), MaterialCalc.package == rules.package_of(trade))
                    .order_by(MaterialCalc.position, MaterialCalc.id)
                )
            ).scalars()
        )
        scope = {i for i in chosen.values() if i is not None}
        conflicts = 0
        plan = _Plan()
        room_plans: list[RoomPlan] = []
        package = rules.package_of(trade)
        for room in rooms:
            answers = typical.get(room.id, {})
            wanted = rules.wanted_rows(answers, chosen, keys)
            existing = [rules.ExistingRow(r.id, r.price_item_id, Decimal(r.quantity), r.note) for r in ours if r.room_id == room.id]
            own_rows = [rules.ExistingRow(r.id, r.price_item_id, Decimal(r.quantity), r.note) for r in owners if r.room_id == room.id]
            actions = rules.plan_rows(wanted, existing, scope, own_rows, own_mode)
            conflicts += sum(1 for a in actions if a.own_quantity is not None)
            plan.rows[room.id] = actions

            numbers = rules.material_numbers(trade, answers)
            mine = [c for c in calcs if c.room_id == room.id]
            first, extra = (mine[0] if mine else None), mine[1:]
            own_calc = next((c for c in owner_calcs if c.room_id == room.id), None)
            kind, params = "NONE", None
            if numbers is not None:
                try:
                    params = PARAMS[package].model_validate(numbers).model_dump(mode="json")
                except ValidationError:
                    kind = "INVALID"
                else:
                    kind = "NEW" if first is None else ("SAME" if rules.same_numbers(first.params, params) else "CHANGE")
                    if kind == "NEW" and own_calc is not None:
                        conflicts += 1
                        if own_mode == rules.REPLACE:
                            kind, first = "TAKE_OVER", own_calc
                        elif own_mode == rules.SKIP:
                            kind = "SKIP"
            elif first is not None:
                kind = "REMOVE"
            plan.material[room.id] = (kind, params, first, extra)
            shown = {k: str(v) for k, v in (numbers or {}).items()}
            room_plans.append(
                RoomPlan(
                    room_id=room.id,
                    room_name=room.name,
                    rows=[
                        RowPlan(kind=a.kind, item_id=a.item_id, quantity=a.quantity, was_quantity=a.was_quantity, note=a.note, own_quantity=a.own_quantity)  # type: ignore[arg-type]
                        for a in actions
                    ],
                    material=MaterialPlan(kind=kind, package=package, numbers=shown, own=own_calc is not None),  # type: ignore[arg-type]
                )
            )

        answered = {pos.key: sum(1 for per in typical.values() if per.get(pos.key) and (per[pos.key].quantity or 0) > 0) for pos in positions}
        position_plans = [
            PositionPlan(
                key=pos.key,
                unit=pos.unit,  # type: ignore[arg-type]
                goes_to_points=rules.default_item_name(pos.key) is not None,
                answered_rooms=answered[pos.key],
                item_id=chosen[pos.key],
                default_item_id=defaults[pos.key],
                candidates=sorted((self._read(i, trade) for i in items if i.unit.value == pos.unit), key=lambda c: not c.relevant) if rules.default_item_name(pos.key) is not None else [],
            )
            for pos in positions
        ]
        idle = all(a.kind in (rules.SAME, rules.SKIP) for acts in plan.rows.values() for a in acts) and all(k in ("NONE", "SAME", "SKIP") for k, *_ in plan.material.values())
        no_answers = not any(answered.values())
        plan.preview = TransferPreview(
            trade=trade,  # type: ignore[arg-type]
            positions=position_plans,
            rooms=room_plans,
            own_not_carried=own,
            nothing=idle and no_answers,
            offer_pack=any(p.goes_to_points and p.answered_rooms > 0 and p.item_id is None for p in position_plans),
            own=own_mode,  # type: ignore[arg-type]
            own_conflicts=conflicts,
        )
        return plan

    async def preview(self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str, mapping: dict[str, uuid.UUID | None], own: str = rules.REPLACE) -> TransferPreview:
        plan = await self._plan(owner_id, project_id, trade, mapping, own)
        assert plan.preview is not None
        return plan.preview

    async def apply(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str, mapping: dict[str, uuid.UUID | None], *, points: bool = True, materials: bool = True,
        own: str = rules.REPLACE,
    ) -> TransferResult:
        plan = await self._plan(owner_id, project_id, trade, mapping, own)
        assert plan.preview is not None
        if plan.preview.nothing:
            raise checklist.TradeChecklistError("TRANSFER_NOTHING", "the craftsman has not answered anything that could be carried over")
        if materials and any(kind == "INVALID" for kind, *_ in plan.material.values()):
            raise checklist.TradeChecklistError("TRANSFER_MATERIALS_INVALID", "a number of the answers is out of the range of a calculation of materials", "materials")
        package = rules.package_of(trade)
        now = datetime.now(UTC)
        result = dict(points_added=0, points_changed=0, points_removed=0, materials_added=0, materials_changed=0, materials_removed=0)

        if points:
            next_position: dict[uuid.UUID, int] = {}
            for room_id, actions in plan.rows.items():
                for act in actions:
                    if act.kind == rules.NEW:
                        if room_id not in next_position:
                            next_position[room_id] = (await self.db.execute(select(func.coalesce(func.max(RoomPoint.position), -1)).where(RoomPoint.room_id == room_id))).scalar_one() + 1
                        self.db.add(
                            RoomPoint(
                                owner_id=owner_id, project_id=project_id, room_id=room_id, price_item_id=act.item_id, quantity=act.quantity, note=act.note,
                                source=rules.SOURCE, position=next_position[room_id], created_at=now, updated_at=now,
                            )
                        )
                        next_position[room_id] += 1
                        result["points_added"] += 1
                    elif act.kind == rules.CHANGE:
                        row = (await self.db.execute(select(RoomPoint).where(RoomPoint.id == act.row_id))).scalar_one()
                        row.quantity = act.quantity
                        row.note = act.note
                        row.updated_at = now
                        result["points_changed"] += 1
                    elif act.kind == rules.REMOVE:
                        await self.db.execute(delete(RoomPoint).where(RoomPoint.id == act.row_id, RoomPoint.source == rules.SOURCE))
                        result["points_removed"] += 1
                    elif act.kind == rules.TAKE_OVER:  # the owner's own row gets the craftsman's number and is carried from now on
                        row = (await self.db.execute(select(RoomPoint).where(RoomPoint.id == act.row_id, RoomPoint.source.is_(None)))).scalar_one()
                        row.quantity = act.quantity
                        row.note = act.note
                        row.source = rules.SOURCE
                        row.updated_at = now
                        result["points_changed"] += 1
                    elif act.kind == rules.REMOVE_OWN:  # a second own row of the same item: the craftsman's number is the whole count
                        await self.db.execute(delete(RoomPoint).where(RoomPoint.id == act.row_id, RoomPoint.source.is_(None)))
                        result["points_removed"] += 1

        if materials:
            for room_id, (kind, params, first, extra) in plan.material.items():
                for dup in extra:  # two carried calculations of one room never stay: the first is the one
                    await self.db.execute(delete(MaterialCalc).where(MaterialCalc.id == dup.id, MaterialCalc.source == rules.SOURCE))
                if kind == "NEW":
                    position = (await self.db.execute(select(func.coalesce(func.max(MaterialCalc.position), -1)).where(MaterialCalc.room_id == room_id))).scalar_one() + 1
                    self.db.add(
                        MaterialCalc(
                            owner_id=owner_id, project_id=project_id, room_id=room_id, package=package, title=None, params=params, source=rules.SOURCE, position=position,
                            created_at=now, updated_at=now,
                        )
                    )
                    result["materials_added"] += 1
                elif kind in ("CHANGE", "TAKE_OVER") and first is not None:
                    first.params = params
                    first.source = rules.SOURCE
                    first.updated_at = now
                    result["materials_changed"] += 1
                elif kind == "REMOVE" and first is not None:
                    await self.db.execute(delete(MaterialCalc).where(MaterialCalc.id == first.id, MaterialCalc.source == rules.SOURCE))
                    result["materials_removed"] += 1
        await self.db.commit()
        return TransferResult(**result)
