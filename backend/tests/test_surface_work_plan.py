"""Focused Stage 10B.1 tests: per-surface Work Plan backend domain.

Covers model/DB invariants (A), the duplicate-PriceItem allowance decision (B),
deterministic positioning (C), ownership isolation through the Surface chain (D),
S/Q quality-scale compatibility (E, G), NULL quality (F), create/update/atomic
replace (H/I/J), archived PriceItem count-based retention/removal/no-increase
semantics (K/L), all PriceScopes, reference-only semantics with no price snapshot
(M), per-surface plan independence (N), unplanned surfaces (O), cascade deletion
(P), ordered reads (Q), replace-only-works (R/S/T), and the two-coat-row case (U).
"""
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import UniqueConstraint, func, select

from app.domain.exceptions import (
    PriceItemNotFoundError,
    ProjectNotFoundError,
    QualityScaleMismatchError,
    RoomNotFoundError,
    SurfaceNotFoundError,
    SurfaceWorkPlanNotFoundError,
    SurfaceWorkPlanValidationError,
)
from app.domain.services.price_book_service import PriceBookService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import QualityLevel, Substrate
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from app.schemas.work_plan import OrderedPriceItemSelection


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _make_project(
    db, owner_id: uuid.UUID, *, name: str = "Obiekt testowy"
) -> Project:
    project = Project(
        owner_id=owner_id,
        name=name,
        address="ul. Kwiatowa 1",
        city="Kraków",
        postal_code="30-001",
    )
    db.add(project)
    await db.commit()
    return project


async def _make_room(
    db, project_id: uuid.UUID, *, name: str = "Salon"
) -> Room:
    room = Room(project_id=project_id, name=name)
    db.add(room)
    await db.commit()
    return room


async def _make_surface(
    db,
    room_id: uuid.UUID,
    surface_type: SurfaceType = SurfaceType.WALL,
) -> Surface:
    surface = Surface(room_id=room_id, name="Ściana 1", surface_type=surface_type)
    db.add(surface)
    await db.commit()
    return surface


async def _make_price_item(
    db,
    owner_id: uuid.UUID,
    *,
    code: str | None = None,
    price: str | None = "12.50",
    price_scope: PriceScope = PriceScope.LABOR,
    is_archived: bool = False,
) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id,
        code=code or f"ITEM_{uuid.uuid4().hex[:8].upper()}",
        category=PriceCategory.PAINTING,
        unit=PriceUnit.M2,
        price=Decimal(price) if price is not None else None,
        price_scope=price_scope,
        is_archived=is_archived,
    )
    db.add(item)
    await db.commit()
    return item


async def _make_chain(db, owner_id: uuid.UUID) -> dict:
    project = await _make_project(db, owner_id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)
    return {"project_id": project.id, "room_id": room.id, "surface_id": surface.id}


def _selection(*price_item_ids: uuid.UUID) -> list[OrderedPriceItemSelection]:
    return [OrderedPriceItemSelection(price_item_id=item_id) for item_id in price_item_ids]


async def _make_plan_with_archived_item(
    db, telegram_id: int, *, archived_count: int = 1
):
    user = await _make_user(db, telegram_id)
    chain = await _make_chain(db, user.id)
    active_a = await _make_price_item(db, user.id, code="ACTIVE_A")
    archived = await _make_price_item(db, user.id, code="ARCHIVED")
    active_c = await _make_price_item(db, user.id, code="ACTIVE_C")
    service = SurfaceWorkPlanService(db)
    await service.set_plan(
        chain["project_id"],
        chain["room_id"],
        chain["surface_id"],
        user.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S2,
        planned_works=_selection(
            active_a.id, *([archived.id] * archived_count), active_c.id
        ),
    )
    await PriceBookService(db).archive_item(user.id, archived.id)
    return user, chain, service, active_a, archived, active_c


class TestA_ModelInvariants:
    def test_surface_plan_unique_surface(self):
        names = {c.name for c in SurfaceWorkPlan.__table__.constraints}
        assert "uq_surface_work_plans_surface_id" in names

    def test_surface_fk_cascade(self):
        fk = list(SurfaceWorkPlan.__table__.c.surface_id.foreign_keys)[0]
        assert fk.column.table.name == "surfaces"
        assert fk.ondelete == "CASCADE"

    def test_substrate_enum_reused_from_stage6(self):
        col = SurfaceWorkPlan.__table__.c.substrate
        assert col.type.enum_class is Substrate  # not a duplicated Python enum
        assert col.type.name == "substrate"  # DB enum owner is revision 0011

    def test_quality_target_reuses_qualitylevel_enum_and_is_nullable(self):
        col = SurfaceWorkPlan.__table__.c.quality_target
        assert col.type.enum_class is QualityLevel
        assert col.type.name == "qualitylevel"
        assert col.nullable is True

    def test_planned_work_plan_fk_cascade(self):
        fk = list(SurfacePlannedWork.__table__.c.work_plan_id.foreign_keys)[0]
        assert fk.column.table.name == "surface_work_plans"
        assert fk.ondelete == "CASCADE"

    def test_planned_work_price_item_fk_restrict(self):
        fk = list(SurfacePlannedWork.__table__.c.price_item_id.foreign_keys)[0]
        assert fk.column.table.name == "price_items"
        assert fk.ondelete == "RESTRICT"

    def test_position_unique_within_plan(self):
        names = {c.name for c in SurfacePlannedWork.__table__.constraints}
        assert "uq_surface_planned_works_work_plan_position" in names


class TestB_DuplicatePriceItemAllowed:
    def test_no_price_item_unique_constraint(self):
        unique_cols = {
            frozenset(col.name for col in constraint.columns)
            for constraint in SurfacePlannedWork.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        # D: duplicates allowed — the PriceItem union is not unique.
        assert frozenset({"work_plan_id", "price_item_id"}) not in unique_cols
        assert frozenset({"work_plan_id", "position"}) in unique_cols

    async def test_same_item_twice_creates_two_rows(self, db_session):
        user = await _make_user(db_session, 1001)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)

        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(item.id, item.id),
        )
        assert [w.price_item_id for w in plan.planned_works] == [item.id, item.id]
        assert [w.position for w in plan.planned_works] == [0, 1]


class TestB_PriceScopes:
    @pytest.mark.parametrize(
        "price_scope",
        [PriceScope.LABOR, PriceScope.MATERIAL, PriceScope.LABOR_AND_MATERIAL],
    )
    async def test_active_price_scope_is_valid_for_planning(
        self, db_session, price_scope
    ):
        user = await _make_user(db_session, 1002)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(
            db_session, user.id, price_scope=price_scope
        )
        service = SurfaceWorkPlanService(db_session)

        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(item.id),
        )

        assert plan.planned_works[0].price_item.price_scope == price_scope


class TestC_DeterministicPositioning:
    async def test_positions_appended_from_zero_in_list_order(self, db_session):
        user = await _make_user(db_session, 2001)
        chain = await _make_chain(db_session, user.id)
        first = await _make_price_item(db_session, user.id)
        second = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)

        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(first.id, second.id),
        )
        assert [(w.position, w.price_item_id) for w in plan.planned_works] == [
            (0, first.id),
            (1, second.id),
        ]

    async def test_ordering_stable_across_fresh_read(self, db_session):
        user = await _make_user(db_session, 2002)
        chain = await _make_chain(db_session, user.id)
        a = await _make_price_item(db_session, user.id)
        b = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(b.id, a.id),
        )
        refetched = await service.get_work_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id
        )
        assert [w.position for w in refetched.planned_works] == [0, 1]
        assert [w.price_item_id for w in refetched.planned_works] == [b.id, a.id]


class TestD_OwnershipIsolation:
    async def test_foreign_project_rejected(self, db_session):
        owner = await _make_user(db_session, 3001)
        other = await _make_user(db_session, 3002)
        chain = await _make_chain(db_session, other.id)
        item = await _make_price_item(db_session, owner.id)
        service = SurfaceWorkPlanService(db_session)

        with pytest.raises(ProjectNotFoundError):
            await service.set_plan(
                chain["project_id"], chain["room_id"], chain["surface_id"], owner.id,
                substrate=Substrate.GYPSUM_BOARD,
                planned_works=_selection(item.id),
            )
        with pytest.raises(ProjectNotFoundError):
            await service.get_work_plan(
                chain["project_id"], chain["room_id"], chain["surface_id"], owner.id
            )

    async def test_foreign_room_rejected(self, db_session):
        owner = await _make_user(db_session, 3003)
        project_a = await _make_project(db_session, owner.id)
        room_a = await _make_room(db_session, project_a.id)
        surface = await _make_surface(db_session, room_a.id)
        project_b = await _make_project(db_session, owner.id, name="Inny obiekt")
        room_b = await _make_room(db_session, project_b.id)
        service = SurfaceWorkPlanService(db_session)

        with pytest.raises(RoomNotFoundError):
            await service.set_plan(
                project_a.id, room_b.id, surface.id, owner.id,
                substrate=Substrate.GYPSUM_BOARD,
            )
        with pytest.raises(RoomNotFoundError):
            await service.get_work_plan(project_a.id, room_b.id, surface.id, owner.id)

    async def test_foreign_surface_rejected(self, db_session):
        owner = await _make_user(db_session, 3004)
        project = await _make_project(db_session, owner.id)
        room_a = await _make_room(db_session, project.id)
        surface_a = await _make_surface(db_session, room_a.id)
        room_b = await _make_room(db_session, project.id, name="Łazienka")
        surface_b = await _make_surface(db_session, room_b.id)
        service = SurfaceWorkPlanService(db_session)

        with pytest.raises(SurfaceNotFoundError):
            await service.get_work_plan(project.id, room_a.id, surface_b.id, owner.id)

    async def test_foreign_price_item_rejected(self, db_session):
        owner = await _make_user(db_session, 3005)
        other = await _make_user(db_session, 3006)
        chain = await _make_chain(db_session, owner.id)
        foreign_item = await _make_price_item(db_session, other.id)
        service = SurfaceWorkPlanService(db_session)

        with pytest.raises(PriceItemNotFoundError):
            await service.set_plan(
                chain["project_id"], chain["room_id"], chain["surface_id"], owner.id,
                substrate=Substrate.GYPSUM_BOARD,
                planned_works=_selection(foreign_item.id),
            )


class TestE_QualityScaleCompatibility:
    @pytest.mark.parametrize(
        ("substrate", "quality"),
        [
            (Substrate.GYPSUM_BOARD, QualityLevel.Q2),
            (Substrate.CONCRETE, QualityLevel.S3),
            (Substrate.GYPSUM_PLASTER, QualityLevel.S1),
            (Substrate.CEMENT_LIME_PLASTER, QualityLevel.S4),
        ],
    )
    async def test_compatible_level_accepted(self, db_session, substrate, quality):
        user = await _make_user(db_session, 4001)
        chain = await _make_chain(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=substrate,
            quality_target=quality,
        )
        assert plan.substrate == substrate
        assert plan.quality_target == quality

    @pytest.mark.parametrize(
        ("substrate", "quality"),
        [
            (Substrate.GYPSUM_BOARD, QualityLevel.S2),
            (Substrate.CONCRETE, QualityLevel.Q1),
        ],
    )
    async def test_wrong_scale_rejected(self, db_session, substrate, quality):
        user = await _make_user(db_session, 4002)
        chain = await _make_chain(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        with pytest.raises(QualityScaleMismatchError):
            await service.set_plan(
                chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
                substrate=substrate,
                quality_target=quality,
            )

    async def test_painted_unrestricted(self, db_session):
        user = await _make_user(db_session, 4003)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.PAINTED,
            quality_target=QualityLevel.Q4,
            planned_works=_selection(item.id),
        )
        assert plan.quality_target == QualityLevel.Q4


class TestF_NullQualityTarget:
    async def test_null_quality_allowed_and_persisted(self, db_session):
        user = await _make_user(db_session, 5001)
        chain = await _make_chain(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            quality_target=None,
        )
        assert plan.quality_target is None

    async def test_quality_cleared_explicitly(self, db_session):
        user = await _make_user(db_session, 5002)
        chain = await _make_chain(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            quality_target=QualityLevel.S2,
        )
        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            quality_target=None,
        )
        assert plan.quality_target is None


class TestG_SubstrateChangeRequiresExplicitClear:
    async def test_incompatible_quality_on_substrate_change_rejected(self, db_session):
        user = await _make_user(db_session, 6001)
        chain = await _make_chain(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            quality_target=QualityLevel.Q2,
        )
        with pytest.raises(QualityScaleMismatchError):
            await service.set_plan(
                chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
                substrate=Substrate.CONCRETE,  # Q2 is not an S-scale level
                quality_target=QualityLevel.Q2,
            )

    async def test_after_explicit_clear_substrate_change_succeeds(self, db_session):
        user = await _make_user(db_session, 6002)
        chain = await _make_chain(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            quality_target=QualityLevel.Q2,
        )
        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.CONCRETE,
            quality_target=None,
        )
        assert plan.substrate == Substrate.CONCRETE
        assert plan.quality_target is None


class TestH_CreatePlan:
    async def test_set_plan_creates_when_none_exists(self, db_session):
        user = await _make_user(db_session, 7001)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)

        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(item.id),
        )
        assert plan.surface_id == chain["surface_id"]
        assert len(plan.planned_works) == 1

    async def test_one_plan_per_surface(self, db_session):
        user = await _make_user(db_session, 7002)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(item.id),
        )
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(item.id),
        )
        count = (
            await db_session.execute(
                select(func.count())
                .select_from(SurfaceWorkPlan)
                .where(SurfaceWorkPlan.surface_id == chain["surface_id"])
            )
        ).scalar_one()
        assert count == 1


class TestI_UpdateExistingPlan:
    async def test_reapply_updates_fields_not_count(self, db_session):
        user = await _make_user(db_session, 8001)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        first = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            quality_target=QualityLevel.Q3,
            planned_works=_selection(item.id),
        )
        second = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.PAINTED,
            quality_target=QualityLevel.Q1,
            planned_works=_selection(item.id),
        )
        assert second.id == first.id
        assert second.substrate == Substrate.PAINTED
        assert second.quality_target == QualityLevel.Q1
        count = (
            await db_session.execute(
                select(func.count())
                .select_from(SurfaceWorkPlan)
                .where(SurfaceWorkPlan.surface_id == chain["surface_id"])
            )
        ).scalar_one()
        assert count == 1


class TestJ_AtomicReplace:
    async def test_replacing_works_deletes_old_rows(self, db_session):
        user = await _make_user(db_session, 9001)
        chain = await _make_chain(db_session, user.id)
        first = await _make_price_item(db_session, user.id)
        second = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(first.id, second.id),
        )
        old_ids = {w.id for w in plan.planned_works}

        replaced = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(second.id),
        )
        assert [w.price_item_id for w in replaced.planned_works] == [second.id]
        assert not old_ids.intersection({w.id for w in replaced.planned_works})

        rows = (
            await db_session.execute(
                select(SurfacePlannedWork).where(
                    SurfacePlannedWork.work_plan_id == plan.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].position == 0


class TestK_ArchivedItemReplacementCounts:
    async def test_archived_item_rejected_when_no_plan_yet(self, db_session):
        user = await _make_user(db_session, 10001)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(db_session, user.id, is_archived=True)
        service = SurfaceWorkPlanService(db_session)

        with pytest.raises(SurfaceWorkPlanValidationError):
            await service.set_plan(
                chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
                substrate=Substrate.GYPSUM_BOARD,
                planned_works=_selection(item.id),
            )
        assert (
            await service.get_work_plan(
                chain["project_id"], chain["room_id"], chain["surface_id"], user.id
            )
            is None
        )

    async def test_existing_archived_occurrence_can_be_retained(self, db_session):
        user, chain, service, active_a, archived, active_c = (
            await _make_plan_with_archived_item(db_session, 10002)
        )

        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            quality_target=QualityLevel.S2,
            planned_works=_selection(active_a.id, archived.id, active_c.id),
        )

        assert [w.price_item_id for w in plan.planned_works] == [
            active_a.id,
            archived.id,
            active_c.id,
        ]

    async def test_configuration_can_change_while_archived_occurrence_remains(
        self, db_session
    ):
        user, chain, service, active_a, archived, active_c = (
            await _make_plan_with_archived_item(db_session, 10003)
        )

        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.CONCRETE,
            quality_target=QualityLevel.S3,
            planned_works=_selection(active_a.id, archived.id, active_c.id),
        )

        assert plan.substrate == Substrate.CONCRETE
        assert plan.quality_target == QualityLevel.S3
        assert [w.price_item_id for w in plan.planned_works] == [
            active_a.id,
            archived.id,
            active_c.id,
        ]

    async def test_existing_archived_occurrence_can_move(self, db_session):
        user, chain, service, active_a, archived, active_c = (
            await _make_plan_with_archived_item(db_session, 10004)
        )

        plan = await service.replace_planned_works(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            planned_works=_selection(active_c.id, archived.id, active_a.id),
        )

        assert [w.price_item_id for w in plan.planned_works] == [
            active_c.id,
            archived.id,
            active_a.id,
        ]

    async def test_existing_archived_occurrence_can_be_removed(self, db_session):
        user, chain, service, active_a, _, active_c = (
            await _make_plan_with_archived_item(db_session, 10005)
        )

        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            quality_target=QualityLevel.S2,
            planned_works=_selection(active_a.id, active_c.id),
        )

        assert [w.price_item_id for w in plan.planned_works] == [
            active_a.id,
            active_c.id,
        ]

    async def test_removed_archived_occurrence_cannot_be_readded(self, db_session):
        user, chain, service, active_a, archived, active_c = (
            await _make_plan_with_archived_item(db_session, 10006)
        )
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            quality_target=QualityLevel.S2,
            planned_works=_selection(active_a.id, active_c.id),
        )

        with pytest.raises(SurfaceWorkPlanValidationError):
            await service.set_plan(
                chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
                substrate=Substrate.GYPSUM_PLASTER,
                quality_target=QualityLevel.S2,
                planned_works=_selection(active_a.id, archived.id, active_c.id),
            )

        plan = await service.get_work_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id
        )
        assert [w.price_item_id for w in plan.planned_works] == [
            active_a.id,
            active_c.id,
        ]

    async def test_archived_occurrence_count_cannot_increase(self, db_session):
        user, chain, service, active_a, archived, active_c = (
            await _make_plan_with_archived_item(db_session, 10007)
        )

        with pytest.raises(SurfaceWorkPlanValidationError):
            await service.set_plan(
                chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
                substrate=Substrate.GYPSUM_PLASTER,
                quality_target=QualityLevel.S2,
                planned_works=_selection(
                    active_a.id, archived.id, archived.id, active_c.id
                ),
            )

        plan = await service.get_work_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id
        )
        assert [w.price_item_id for w in plan.planned_works] == [
            active_a.id,
            archived.id,
            active_c.id,
        ]

    async def test_two_existing_archived_occurrences_can_be_retained(
        self, db_session
    ):
        user, chain, service, active_a, archived, active_c = (
            await _make_plan_with_archived_item(
                db_session, 10008, archived_count=2
            )
        )

        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            quality_target=QualityLevel.S2,
            planned_works=_selection(
                active_a.id, archived.id, archived.id, active_c.id
            ),
        )

        assert (
            [w.price_item_id for w in plan.planned_works].count(archived.id) == 2
        )

    async def test_two_existing_archived_occurrences_can_reduce_to_one(
        self, db_session
    ):
        user, chain, service, active_a, archived, active_c = (
            await _make_plan_with_archived_item(
                db_session, 10009, archived_count=2
            )
        )

        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            quality_target=QualityLevel.S2,
            planned_works=_selection(active_a.id, archived.id, active_c.id),
        )

        assert (
            [w.price_item_id for w in plan.planned_works].count(archived.id) == 1
        )

    async def test_two_existing_archived_occurrences_cannot_increase_to_three(
        self, db_session
    ):
        user, chain, service, active_a, archived, active_c = (
            await _make_plan_with_archived_item(
                db_session, 10010, archived_count=2
            )
        )

        with pytest.raises(SurfaceWorkPlanValidationError):
            await service.set_plan(
                chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
                substrate=Substrate.GYPSUM_PLASTER,
                quality_target=QualityLevel.S2,
                planned_works=_selection(
                    active_a.id,
                    archived.id,
                    archived.id,
                    archived.id,
                    active_c.id,
                ),
            )

        plan = await service.get_work_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id
        )
        assert (
            [w.price_item_id for w in plan.planned_works].count(archived.id) == 2
        )


class TestL_ArchiveNeverMutatesExistingRows:
    async def test_archiving_item_keeps_existing_work_reference(self, db_session):
        user = await _make_user(db_session, 11001)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(item.id),
        )
        await PriceBookService(db_session).archive_item(user.id, item.id)

        refetched = await service.get_work_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id
        )
        assert [w.price_item_id for w in refetched.planned_works] == [item.id]
        assert refetched.planned_works[0].price_item.is_archived is True


class TestM_ReferenceOnlyNoSnapshot:
    def test_plan_has_no_price_column(self):
        cols = {c.name for c in SurfaceWorkPlan.__table__.columns}
        assert "price" not in cols
        work_cols = {c.name for c in SurfacePlannedWork.__table__.columns}
        assert "price" not in work_cols

    async def test_price_change_does_not_alter_plan(self, db_session):
        user = await _make_user(db_session, 12001)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(db_session, user.id, price="12.50")
        service = SurfaceWorkPlanService(db_session)
        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(item.id),
        )

        refetched_item = await PriceBookService(db_session).get_owned_item(user.id, item.id)
        refetched_item.price = Decimal("44.00")
        await db_session.commit()

        plan = await service.get_work_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id
        )
        # The plan still references the item by id; the price lives only on the item.
        assert plan.planned_works[0].price_item_id == item.id
        assert plan.planned_works[0].price_item.price == Decimal("44.00")


class TestM_NullPriceValidForPlanning:
    async def test_null_price_item_is_valid_for_planning(self, db_session):
        """A NULL (not-yet-set) owner price never blocks planning (D3)."""
        user = await _make_user(db_session, 12002)
        chain = await _make_chain(db_session, user.id)
        item = PriceItem(
            owner_id=user.id,
            code=f"ITEM_{uuid.uuid4().hex[:8].upper()}",
            category=PriceCategory.PAINTING,
            unit=PriceUnit.M2,
            price=None,  # NULL = commercial price not set yet; fine for planning
        )
        db_session.add(item)
        await db_session.commit()
        service = SurfaceWorkPlanService(db_session)
        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.PAINTED,
            planned_works=_selection(item.id),
        )
        assert [w.price_item_id for w in plan.planned_works] == [item.id]
        assert plan.planned_works[0].price_item.price is None


class TestN_PerSurfaceIndependence:
    async def test_two_surfaces_get_distinct_plans(self, db_session):
        user = await _make_user(db_session, 13001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        ceiling = await _make_surface(
            db_session, room.id, SurfaceType.CEILING
        )
        service = SurfaceWorkPlanService(db_session)

        wall_plan = await service.set_plan(
            project.id, room.id, wall.id, user.id,
            substrate=Substrate.GYPSUM_BOARD,
            quality_target=QualityLevel.Q3,
        )
        ceiling_plan = await service.set_plan(
            project.id, room.id, ceiling.id, user.id,
            substrate=Substrate.CONCRETE,
            quality_target=QualityLevel.S1,
        )
        assert wall_plan.id != ceiling_plan.id
        assert wall_plan.substrate == Substrate.GYPSUM_BOARD
        assert ceiling_plan.substrate == Substrate.CONCRETE


class TestO_UnplannedSurface:
    async def test_get_returns_none_for_unplanned_surface(self, db_session):
        user = await _make_user(db_session, 14001)
        chain = await _make_chain(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        plan = await service.get_work_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id
        )
        assert plan is None

    async def test_replace_planned_works_raises_when_unplanned(self, db_session):
        user = await _make_user(db_session, 14002)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        with pytest.raises(SurfaceWorkPlanNotFoundError):
            await service.replace_planned_works(
                chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
                planned_works=_selection(item.id),
            )


class TestP_CascadeDeletion:
    async def test_deleting_surface_deletes_its_plan(self, db_session):
        user = await _make_user(db_session, 15001)
        chain = await _make_chain(db_session, user.id)
        item = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(item.id),
        )

        surface = (
            await db_session.execute(
                select(Surface).where(Surface.id == chain["surface_id"])
            )
        ).scalar_one()
        await db_session.delete(surface)
        await db_session.commit()

        count = (
            await db_session.execute(
                select(func.count())
                .select_from(SurfaceWorkPlan)
                .where(SurfaceWorkPlan.surface_id == chain["surface_id"])
            )
        ).scalar_one()
        assert count == 0


class TestQ_OrderedReads:
    async def test_works_returned_in_position_order(self, db_session):
        user = await _make_user(db_session, 16001)
        chain = await _make_chain(db_session, user.id)
        first = await _make_price_item(db_session, user.id)
        second = await _make_price_item(db_session, user.id)
        third = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_BOARD,
            planned_works=_selection(third.id, first.id, second.id),
        )
        plan = await service.get_work_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id
        )
        assert [w.price_item_id for w in plan.planned_works] == [
            third.id,
            first.id,
            second.id,
        ]
        assert [w.position for w in plan.planned_works] == [0, 1, 2]


class TestR_ReplaceWorksOnExistingPlan:
    async def test_replace_keeps_configuration_and_rewrites_positions(self, db_session):
        user = await _make_user(db_session, 17001)
        chain = await _make_chain(db_session, user.id)
        first = await _make_price_item(db_session, user.id)
        second = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            quality_target=QualityLevel.S3,
            planned_works=_selection(first.id),
        )
        plan = await service.replace_planned_works(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            planned_works=_selection(second.id, first.id),
        )
        assert plan.substrate == Substrate.GYPSUM_PLASTER
        assert plan.quality_target == QualityLevel.S3
        assert [(w.position, w.price_item_id) for w in plan.planned_works] == [
            (0, second.id),
            (1, first.id),
        ]


class TestT_QualityPersistsAcrossWorksReplace:
    async def test_replacing_works_keeps_quality_target(self, db_session):
        user = await _make_user(db_session, 18001)
        chain = await _make_chain(db_session, user.id)
        first = await _make_price_item(db_session, user.id)
        second = await _make_price_item(db_session, user.id)
        service = SurfaceWorkPlanService(db_session)
        await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.CONCRETE,
            quality_target=QualityLevel.S4,
            planned_works=_selection(first.id),
        )
        plan = await service.replace_planned_works(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            planned_works=_selection(second.id),
        )
        assert plan.quality_target == QualityLevel.S4
        assert plan.substrate == Substrate.CONCRETE


class TestU_TwoCoatRows:
    async def test_two_separate_coat_rows_same_item(self, db_session):
        user = await _make_user(db_session, 19001)
        chain = await _make_chain(db_session, user.id)
        coat = await _make_price_item(
            db_session, user.id, code="CENNIK_COAT_01", price="8.00"
        )
        service = SurfaceWorkPlanService(db_session)
        plan = await service.set_plan(
            chain["project_id"], chain["room_id"], chain["surface_id"], user.id,
            substrate=Substrate.PAINTED,
            planned_works=_selection(coat.id, coat.id),
        )
        assert len(plan.planned_works) == 2
        works = plan.planned_works
        assert works[0].id != works[1].id
        assert works[0].price_item_id == works[1].price_item_id == coat.id
        assert (works[0].position, works[1].position) == (0, 1)


class TestV_ApplyToRoomWallsService:
    async def test_apply_batch_atomic_when_source_item_archived(self, db_session):
        """A failed apply-to-all must leave every target plan untouched."""
        user = await _make_user(db_session, 20001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        source = await _make_surface(db_session, room.id)
        target_1 = await _make_surface(db_session, room.id)
        target_2 = await _make_surface(db_session, room.id)
        source_item = await _make_price_item(db_session, user.id, code="SRC")
        target_item = await _make_price_item(db_session, user.id, code="TGT")
        service = SurfaceWorkPlanService(db_session)
        await service.set_plan(
            project.id, room.id, source.id, user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            quality_target=QualityLevel.S3,
            planned_works=_selection(source_item.id),
        )
        await service.set_plan(
            project.id, room.id, target_1.id, user.id,
            substrate=Substrate.CONCRETE,
            quality_target=QualityLevel.S2,
            planned_works=_selection(target_item.id),
        )
        await service.set_plan(
            project.id, room.id, target_2.id, user.id,
            substrate=Substrate.CONCRETE,
            quality_target=QualityLevel.S2,
            planned_works=_selection(target_item.id),
        )
        # The item the source plan references is archived now — propagation to
        # new target rows must be rejected before any mutation happens.
        await PriceBookService(db_session).archive_item(user.id, source_item.id)
        with pytest.raises(SurfaceWorkPlanValidationError):
            await service.apply_to_room_walls(project.id, room.id, source.id, user.id)
        # Neither target was mutated and the source plan is untouched.
        for target in (target_1, target_2):
            plan = await service.get_work_plan(project.id, room.id, target.id, user.id)
            assert plan.substrate == Substrate.CONCRETE
            assert plan.quality_target == QualityLevel.S2
            assert [w.price_item_id for w in plan.planned_works] == [target_item.id]
        source_plan = await service.get_work_plan(
            project.id, room.id, source.id, user.id
        )
        assert [w.price_item_id for w in source_plan.planned_works] == [
            source_item.id
        ]