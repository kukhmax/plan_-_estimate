"""Stage 10D focused tests: Estimate domain foundation.

Covers:
  A - OpeningRevealPlannedWork model invariants
  B - OpeningRevealWorkService: set/get/clear/replace semantics
  C - OpeningRevealWorkService: REVEAL category guard
  D - OpeningRevealWorkService: reveal_enabled guard
  E - OpeningRevealWorkService: archived-item reduction-only rule
  F - OpeningRevealWorkService: duplicates allowed; per-opening independence
  G - Estimate generation from SurfaceWorkPlan: SURFACE_NET_AREA for M2
  H - Estimate generation from OpeningRevealPlannedWork: REVEAL_LENGTH/AREA
  I - Snapshot immutability: price, area, and reveal-disable changes
  J - Totals invariant
  K - Version sequencing
  L - DRAFT regeneration: preservation and diff semantics
  M - NULL price: line renders NULL, finalize() blocked
  N - FINAL status transition; regeneration refused
"""
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select

from app.domain.exceptions import (
    EstimateDraftExistsError,
    EstimateNotFoundError,
    EstimateStateError,
    EstimateValidationError,
    OpeningRevealWorkValidationError,
    ProjectNotFoundError,
)
from app.domain.services.estimate_service import EstimateService
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.domain.services.price_book_service import PriceBookService
from app.models.checklist import QualityLevel, Substrate
from app.models.estimate import (
    Estimate,
    EstimateLine,
    EstimateStatus,
    LineOrigin,
    QuantitySource,
)
from app.models.opening import Opening, OpeningType
from app.models.opening_reveal_planned_work import OpeningRevealPlannedWork
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _make_project(db, owner_id: uuid.UUID, *, name: str = "Projekt") -> Project:
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


async def _make_room(db, project_id: uuid.UUID, *, name: str = "Salon") -> Room:
    room = Room(project_id=project_id, name=name)
    db.add(room)
    await db.commit()
    return room


async def _make_surface(
    db,
    room_id: uuid.UUID,
    surface_type: SurfaceType = SurfaceType.WALL,
    *,
    width: str = "5.000",
    height: str = "2.700",
) -> Surface:
    surface = Surface(
        room_id=room_id,
        name="Ściana 1",
        surface_type=surface_type,
        width=Decimal(width),
        height=Decimal(height),
    )
    db.add(surface)
    await db.commit()
    return surface


async def _make_opening(
    db,
    surface_id: uuid.UUID,
    *,
    opening_type: OpeningType = OpeningType.WINDOW,
    width: str = "1.200",
    height: str = "1.400",
    quantity: int = 1,
    reveal_enabled: bool = True,
    reveal_depth: str | None = "0.250",
    reveal_left: bool = True,
    reveal_right: bool = True,
    reveal_top: bool = True,
    reveal_bottom: bool = False,
) -> Opening:
    opening = Opening(
        surface_id=surface_id,
        opening_type=opening_type,
        width=Decimal(width),
        height=Decimal(height),
        quantity=quantity,
        reveal_enabled=reveal_enabled,
        reveal_depth=Decimal(reveal_depth) if reveal_depth else None,
        reveal_left=reveal_left,
        reveal_right=reveal_right,
        reveal_top=reveal_top,
        reveal_bottom=reveal_bottom,
    )
    db.add(opening)
    await db.commit()
    return opening


async def _make_price_item(
    db,
    owner_id: uuid.UUID,
    *,
    code: str | None = None,
    category: PriceCategory = PriceCategory.PAINTING,
    unit: PriceUnit = PriceUnit.M2,
    price: str | None = "12.50",
    price_scope: PriceScope = PriceScope.LABOR,
    is_archived: bool = False,
) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id,
        code=code or f"ITEM_{uuid.uuid4().hex[:8].upper()}",
        category=category,
        unit=unit,
        price=Decimal(price) if price is not None else None,
        price_scope=price_scope,
        is_archived=is_archived,
    )
    db.add(item)
    await db.commit()
    return item


async def _make_reveal_item(
    db,
    owner_id: uuid.UUID,
    *,
    unit: PriceUnit = PriceUnit.LM,
    price: str | None = "15.00",
    is_archived: bool = False,
) -> PriceItem:
    return await _make_price_item(
        db,
        owner_id,
        category=PriceCategory.REVEAL,
        unit=unit,
        price=price,
        is_archived=is_archived,
    )


async def _make_work_plan(
    db,
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    owner_id: uuid.UUID,
    price_items: list[PriceItem],
) -> SurfaceWorkPlan:
    from app.domain.services.work_plan_service import SurfaceWorkPlanService
    from app.schemas.work_plan import OrderedPriceItemSelection

    service = SurfaceWorkPlanService(db)
    return await service.set_plan(
        project_id,
        room_id,
        surface_id,
        owner_id,
        substrate=Substrate.GYPSUM_PLASTER,
        planned_works=[
            OrderedPriceItemSelection(price_item_id=item.id) for item in price_items
        ],
    )


# ---------------------------------------------------------------------------
# TestA — OpeningRevealPlannedWork model invariants
# ---------------------------------------------------------------------------


class TestA_ModelInvariants:
    def test_fk_to_openings_cascade(self):
        fk = list(
            OpeningRevealPlannedWork.__table__.c.opening_id.foreign_keys
        )[0]
        assert fk.column.table.name == "openings"
        assert fk.ondelete == "CASCADE"

    def test_fk_to_price_items_restrict(self):
        fk = list(
            OpeningRevealPlannedWork.__table__.c.price_item_id.foreign_keys
        )[0]
        assert fk.column.table.name == "price_items"
        assert fk.ondelete == "RESTRICT"

    def test_position_not_nullable(self):
        col = OpeningRevealPlannedWork.__table__.c.position
        assert col.nullable is False

    def test_opening_position_index_exists(self):
        idx_names = {
            idx.name for idx in OpeningRevealPlannedWork.__table__.indexes
        }
        assert "ix_opening_reveal_planned_works_opening_position" in idx_names


# ---------------------------------------------------------------------------
# TestB — set_works / get_works / clear_works
# ---------------------------------------------------------------------------


class TestB_SetGetClearWorks:
    async def test_set_works_creates_ordered_rows(self, db_session):
        user = await _make_user(db_session, 20001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item1 = await _make_reveal_item(db_session, user.id)
        item2 = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        works = await service.set_works(opening.id, user.id, [item1.id, item2.id])
        assert len(works) == 2
        assert works[0].price_item_id == item1.id
        assert works[1].price_item_id == item2.id
        assert works[0].position == 0
        assert works[1].position == 1

    async def test_get_works_returns_in_order(self, db_session):
        user = await _make_user(db_session, 20002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item_a = await _make_reveal_item(db_session, user.id)
        item_b = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        await service.set_works(opening.id, user.id, [item_b.id, item_a.id])
        works = await service.get_works(opening.id, user.id)
        assert [w.price_item_id for w in works] == [item_b.id, item_a.id]

    async def test_set_works_replaces_existing_atomically(self, db_session):
        user = await _make_user(db_session, 20003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item_a = await _make_reveal_item(db_session, user.id)
        item_b = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        await service.set_works(opening.id, user.id, [item_a.id])
        works = await service.set_works(opening.id, user.id, [item_b.id])
        assert len(works) == 1
        assert works[0].price_item_id == item_b.id

        count = (
            await db_session.execute(
                select(OpeningRevealPlannedWork).where(
                    OpeningRevealPlannedWork.opening_id == opening.id
                )
            )
        ).scalars().all()
        assert len(count) == 1

    async def test_clear_works_removes_all_rows(self, db_session):
        user = await _make_user(db_session, 20004)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        await service.set_works(opening.id, user.id, [item.id, item.id])
        await service.clear_works(opening.id, user.id)
        works = await service.get_works(opening.id, user.id)
        assert works == []


# ---------------------------------------------------------------------------
# TestC — REVEAL category guard
# ---------------------------------------------------------------------------


class TestC_RevealCategoryGuard:
    async def test_non_reveal_item_rejected(self, db_session):
        user = await _make_user(db_session, 21001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        painting_item = await _make_price_item(
            db_session, user.id, category=PriceCategory.PAINTING
        )
        service = OpeningRevealWorkService(db_session)

        with pytest.raises(OpeningRevealWorkValidationError, match="REVEAL"):
            await service.set_works(opening.id, user.id, [painting_item.id])

    async def test_reveal_item_accepted(self, db_session):
        user = await _make_user(db_session, 21002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        works = await service.set_works(opening.id, user.id, [item.id])
        assert len(works) == 1
        assert works[0].price_item.category == PriceCategory.REVEAL


# ---------------------------------------------------------------------------
# TestD — reveal_enabled guard
# ---------------------------------------------------------------------------


class TestD_RevealEnabledGuard:
    async def test_set_works_rejected_when_reveal_disabled(self, db_session):
        user = await _make_user(db_session, 22001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(
            db_session, surface.id, reveal_enabled=False, reveal_depth=None
        )
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        with pytest.raises(OpeningRevealWorkValidationError, match="reveal"):
            await service.set_works(opening.id, user.id, [item.id])

    async def test_get_works_allowed_when_reveal_disabled(self, db_session):
        """get_works does not enforce reveal_enabled (read-only)."""
        user = await _make_user(db_session, 22002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(
            db_session, surface.id, reveal_enabled=False, reveal_depth=None
        )
        service = OpeningRevealWorkService(db_session)
        works = await service.get_works(opening.id, user.id)
        assert works == []


# ---------------------------------------------------------------------------
# TestE — archived item reduction-only rule
# ---------------------------------------------------------------------------


class TestE_ArchivedItemRule:
    async def test_new_archived_item_rejected(self, db_session):
        user = await _make_user(db_session, 23001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_reveal_item(db_session, user.id, is_archived=True)
        service = OpeningRevealWorkService(db_session)

        with pytest.raises(OpeningRevealWorkValidationError):
            await service.set_works(opening.id, user.id, [item.id])

    async def test_existing_archived_occurrence_retained(self, db_session):
        user = await _make_user(db_session, 23002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        await service.set_works(opening.id, user.id, [item.id])
        item.is_archived = True
        await db_session.commit()

        works = await service.set_works(opening.id, user.id, [item.id])
        assert len(works) == 1
        assert works[0].price_item_id == item.id

    async def test_archived_occurrence_cannot_increase(self, db_session):
        user = await _make_user(db_session, 23003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        await service.set_works(opening.id, user.id, [item.id])
        item.is_archived = True
        await db_session.commit()

        with pytest.raises(OpeningRevealWorkValidationError):
            await service.set_works(opening.id, user.id, [item.id, item.id])

    async def test_archived_occurrence_can_be_removed(self, db_session):
        user = await _make_user(db_session, 23004)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        active = await _make_reveal_item(db_session, user.id)
        archived = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        await service.set_works(opening.id, user.id, [active.id, archived.id])
        archived.is_archived = True
        await db_session.commit()

        works = await service.set_works(opening.id, user.id, [active.id])
        assert [w.price_item_id for w in works] == [active.id]


# ---------------------------------------------------------------------------
# TestF — duplicates allowed; per-opening independence
# ---------------------------------------------------------------------------


class TestF_DuplicatesAndIndependence:
    async def test_same_item_twice_creates_two_rows(self, db_session):
        user = await _make_user(db_session, 24001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        works = await service.set_works(opening.id, user.id, [item.id, item.id])
        assert len(works) == 2
        assert works[0].id != works[1].id
        assert works[0].price_item_id == works[1].price_item_id == item.id
        assert (works[0].position, works[1].position) == (0, 1)

    async def test_different_openings_same_surface_have_independent_work_lists(
        self, db_session
    ):
        user = await _make_user(db_session, 24002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening_a = await _make_opening(db_session, surface.id)
        opening_b = await _make_opening(db_session, surface.id)
        item_x = await _make_reveal_item(db_session, user.id)
        item_y = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)

        await service.set_works(opening_a.id, user.id, [item_x.id])
        await service.set_works(opening_b.id, user.id, [item_y.id, item_x.id])

        works_a = await service.get_works(opening_a.id, user.id)
        works_b = await service.get_works(opening_b.id, user.id)
        assert [w.price_item_id for w in works_a] == [item_x.id]
        assert [w.price_item_id for w in works_b] == [item_y.id, item_x.id]


# ---------------------------------------------------------------------------
# TestF2 — apply-to-room-openings bulk reveal work copy (Stage 10G.4)
# ---------------------------------------------------------------------------


class TestF2_ApplyToRoomOpenings:
    async def test_copies_ordered_selection_to_other_reveal_enabled_openings_in_room(
        self, db_session
    ):
        user = await _make_user(db_session, 24101)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id)
        target = await _make_opening(db_session, surface.id)
        item_a = await _make_reveal_item(db_session, user.id)
        item_b = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item_b.id, item_a.id])

        targets = await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        assert [t.id for t in targets] == [target.id]
        target_works = await service.get_works(target.id, user.id)
        assert [w.price_item_id for w in target_works] == [item_b.id, item_a.id]

    async def test_spans_multiple_surfaces_in_the_same_room(self, db_session):
        user = await _make_user(db_session, 24102)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface_a = await _make_surface(db_session, room.id)
        surface_b = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface_a.id)
        target = await _make_opening(db_session, surface_b.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item.id])

        targets = await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        assert [t.id for t in targets] == [target.id]

    async def test_source_is_excluded_from_targets_and_left_unchanged(self, db_session):
        user = await _make_user(db_session, 24103)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item.id])

        targets = await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        assert source.id not in {t.id for t in targets}
        source_works = await service.get_works(source.id, user.id)
        assert [w.price_item_id for w in source_works] == [item.id]

    async def test_excludes_reveal_disabled_openings(self, db_session):
        user = await _make_user(db_session, 24104)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id)
        disabled = await _make_opening(db_session, surface.id, reveal_enabled=False, reveal_depth=None)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item.id])

        targets = await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        assert disabled.id not in {t.id for t in targets}
        disabled_works = await service.get_works(disabled.id, user.id)
        assert disabled_works == []

    async def test_excludes_archived_openings(self, db_session):
        user = await _make_user(db_session, 24105)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id)
        archived_target = await _make_opening(db_session, surface.id)
        archived_target.is_archived = True
        await db_session.commit()
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item.id])

        targets = await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        assert archived_target.id not in {t.id for t in targets}

    async def test_rejects_archived_source_opening(self, db_session):
        user = await _make_user(db_session, 24106)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id)
        source.is_archived = True
        await db_session.commit()
        service = OpeningRevealWorkService(db_session)

        with pytest.raises(OpeningRevealWorkValidationError):
            await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

    async def test_rejects_reveal_disabled_source(self, db_session):
        user = await _make_user(db_session, 24107)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id, reveal_enabled=False, reveal_depth=None)
        service = OpeningRevealWorkService(db_session)

        with pytest.raises(OpeningRevealWorkValidationError, match="reveal"):
            await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

    async def test_window_and_door_both_eligible_as_targets(self, db_session):
        user = await _make_user(db_session, 24108)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id, opening_type=OpeningType.WINDOW)
        door_target = await _make_opening(db_session, surface.id, opening_type=OpeningType.DOOR)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item.id])

        targets = await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        assert door_target.id in {t.id for t in targets}

    async def test_duplicate_selection_is_preserved_on_apply(self, db_session):
        user = await _make_user(db_session, 24109)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id)
        target = await _make_opening(db_session, surface.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item.id, item.id])

        await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        target_works = await service.get_works(target.id, user.id)
        assert [w.price_item_id for w in target_works] == [item.id, item.id]

    async def test_empty_source_clears_target_reveal_works(self, db_session):
        user = await _make_user(db_session, 24110)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id)
        target = await _make_opening(db_session, surface.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(target.id, user.id, [item.id])  # target starts non-empty
        # source has no reveal works at all

        await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        assert await service.get_works(target.id, user.id) == []

    async def test_target_geometry_is_never_touched_by_apply(self, db_session):
        user = await _make_user(db_session, 24111)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id, width="1.200", height="1.400")
        target = await _make_opening(db_session, surface.id, width="0.900", height="2.000")
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item.id])

        await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        await db_session.refresh(target)
        assert target.width == Decimal("0.900")
        assert target.height == Decimal("2.000")

    async def test_archived_price_item_in_source_rejects_whole_batch_atomically(self, db_session):
        user = await _make_user(db_session, 24112)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id)
        target = await _make_opening(db_session, surface.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item.id])
        item.is_archived = True
        await db_session.commit()

        with pytest.raises(OpeningRevealWorkValidationError):
            await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        # No partial mutation — target remains exactly as before the failed apply.
        assert await service.get_works(target.id, user.id) == []

    async def test_excludes_openings_on_archived_surfaces(self, db_session):
        """An opening's own is_archived flag is independent of its parent
        surface's; archiving a surface never cascades to its openings. Bulk
        apply must still exclude such openings, consistent with every other
        "active opening" query in this codebase (estimate_service,
        room_service, surface_service all AND Opening.is_archived and
        Surface.is_archived together)."""
        user = await _make_user(db_session, 24114)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        source_surface = await _make_surface(db_session, room.id)
        archived_surface = await _make_surface(db_session, room.id)
        archived_surface.is_archived = True
        await db_session.commit()
        source = await _make_opening(db_session, source_surface.id)
        target_on_archived_surface = await _make_opening(db_session, archived_surface.id)
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item.id])

        targets = await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        assert target_on_archived_surface.id not in {t.id for t in targets}

    async def test_non_reveal_room_opening_without_reveal_enabled_is_excluded(self, db_session):
        """OTHER-type openings can never have reveal_enabled=True; confirms
        they are naturally excluded without a special-case type filter."""
        user = await _make_user(db_session, 24113)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        source = await _make_opening(db_session, surface.id)
        other = await _make_opening(
            db_session, surface.id, opening_type=OpeningType.OTHER,
            reveal_enabled=False, reveal_depth=None,
        )
        item = await _make_reveal_item(db_session, user.id)
        service = OpeningRevealWorkService(db_session)
        await service.set_works(source.id, user.id, [item.id])

        targets = await service.apply_to_room_openings(project.id, room.id, source.id, user.id)

        assert other.id not in {t.id for t in targets}


# ---------------------------------------------------------------------------
# TestF3 — inline-created NULL-priced custom item flows through to Estimate
# (Stage 10G.4 null-price-creation follow-up)
# ---------------------------------------------------------------------------


class TestF3_NullPricedCustomItemEstimate:
    async def test_null_priced_reveal_item_gets_real_quantity_and_null_money(
        self, db_session
    ):
        """A custom PriceItem created with price=None (the exact contract used
        by inline Price Book creation) must still drive a normal, non-zero
        EstimateLine.quantity from the opening's own reveal geometry — only
        unit_price/amount are NULL. Quantity and price are independent."""
        user = await _make_user(db_session, 25101)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(
            db_session, surface.id,
            reveal_enabled=True, reveal_depth="0.250",
            reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
        )

        price_book = PriceBookService(db_session)
        unresolved_item = await price_book.create_custom_item(
            user.id,
            category=PriceCategory.REVEAL,
            unit=PriceUnit.M2,
            price=None,
            display_name="Szpachlowanie ościeży",
        )
        assert unresolved_item.price is None

        reveal_service = OpeningRevealWorkService(db_session)
        await reveal_service.set_works(opening.id, user.id, [unresolved_item.id])

        estimate = await EstimateService(db_session).generate_estimate(project.id, user.id)
        reveal_lines = [
            ln for ln in estimate.lines if ln.price_item_id == unresolved_item.id
        ]
        assert len(reveal_lines) == 1
        line = reveal_lines[0]
        assert line.quantity > Decimal("0.000")
        assert line.unit_price is None
        assert line.amount is None

        with pytest.raises(EstimateValidationError, match="price"):
            await EstimateService(db_session).finalize(estimate.id, user.id)


# ---------------------------------------------------------------------------
# TestG — Estimate generation from SurfaceWorkPlan
# ---------------------------------------------------------------------------


class TestG_EstimateFromSurfaceWorkPlan:
    async def test_m2_item_gets_surface_net_area_quantity(self, db_session):
        user = await _make_user(db_session, 25001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(
            db_session, room.id, width="4.000", height="2.500"
        )
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="20.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        assert estimate.status == EstimateStatus.DRAFT
        assert len(estimate.lines) == 1
        line = estimate.lines[0]
        assert line.unit == PriceUnit.M2
        assert line.quantity_source == QuantitySource.SURFACE_NET_AREA
        # 4.000 × 2.500 = 10.000 m² (no openings)
        assert line.quantity == Decimal("10.000")
        assert line.source_quantity == Decimal("10.000")

    async def test_non_m2_item_gets_manual_quantity_source(self, db_session):
        user = await _make_user(db_session, 25002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.PCS, price="50.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.unit == PriceUnit.PCS
        assert line.quantity_source == QuantitySource.MANUAL
        assert line.source_quantity is None
        assert line.quantity == Decimal("0.000")

    async def test_opening_deducted_from_surface_net_area(self, db_session):
        user = await _make_user(db_session, 25003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        # 5.0 × 2.7 = 13.5 m², opening 1.2 × 1.4 = 1.68
        surface = await _make_surface(
            db_session, room.id, width="5.000", height="2.700"
        )
        await _make_opening(
            db_session, surface.id,
            width="1.200", height="1.400",
            reveal_enabled=False, reveal_depth=None,
        )
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.quantity == Decimal("11.820")  # 13.5 - 1.68

    async def test_surface_net_area_never_modified(self, db_session):
        """Surface has no net_area column; model width/height are unchanged."""
        user = await _make_user(db_session, 25004)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(
            db_session, room.id, width="4.000", height="2.500"
        )
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2)
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        await svc.generate_estimate(project.id, user.id)

        # Re-fetch surface — dimensions must be unchanged
        refreshed = (
            await db_session.execute(select(Surface).where(Surface.id == surface.id))
        ).scalar_one()
        assert refreshed.width == Decimal("4.000")
        assert refreshed.height == Decimal("2.500")

    async def test_snapshot_captures_item_code_and_description(self, db_session):
        user = await _make_user(db_session, 25005)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, code="CENNIK_TEST_01", unit=PriceUnit.M2
        )
        item.display_name = "Gładź gipsowa"
        await db_session.commit()
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.item_code == "CENNIK_TEST_01"
        assert line.description == "Gładź gipsowa"


# ---------------------------------------------------------------------------
# TestH — Estimate generation from OpeningRevealPlannedWork
# ---------------------------------------------------------------------------


class TestH_EstimateFromRevealWorks:
    async def test_lm_item_gets_reveal_length_quantity_source(self, db_session):
        user = await _make_user(db_session, 26001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        # window: width=1.2, height=1.4, depth=0.25, left+right+top
        # length = (1.4 + 1.4 + 1.2) × 1 = 4.0 lm
        opening = await _make_opening(
            db_session, surface.id,
            width="1.200", height="1.400",
            reveal_depth="0.250",
            reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
            quantity=1,
        )
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM, price="15.00")
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        assert len(estimate.lines) == 1
        line = estimate.lines[0]
        assert line.quantity_source == QuantitySource.REVEAL_LENGTH
        assert line.opening_id == opening.id
        assert line.plan_id is None
        # source_quantity = total_length = (1.4 + 1.4 + 1.2) = 4.000
        assert line.source_quantity == Decimal("4.000")
        assert line.quantity == Decimal("4.000")

    async def test_m2_reveal_item_gets_reveal_area_quantity_source(self, db_session):
        user = await _make_user(db_session, 26002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        # width=1.2, height=1.4, depth=0.25, left+right+top
        # area = (1.4 × 0.25 + 1.4 × 0.25 + 1.2 × 0.25) = (0.35 + 0.35 + 0.30) = 1.000
        opening = await _make_opening(
            db_session, surface.id,
            width="1.200", height="1.400",
            reveal_depth="0.250",
            reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
        )
        item = await _make_reveal_item(
            db_session, user.id, unit=PriceUnit.M2, price="25.00"
        )
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.quantity_source == QuantitySource.REVEAL_AREA
        assert line.source_quantity == Decimal("1.000")

    async def test_one_line_per_reveal_work_row(self, db_session):
        user = await _make_user(db_session, 26003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item1 = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        item2 = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item1.id, item2.id])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        assert len(estimate.lines) == 2

    async def test_opening_with_reveal_enabled_but_zero_works_generates_no_lines(
        self, db_session
    ):
        user = await _make_user(db_session, 26004)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        # Opening has reveal_enabled but no OpeningRevealPlannedWork rows
        await _make_opening(db_session, surface.id, reveal_enabled=True)
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        assert estimate.lines == []

    async def test_reveal_area_never_merged_into_surface_net_area(self, db_session):
        """Surface.net_area = gross - openings; reveal area is never added back."""
        user = await _make_user(db_session, 26005)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(
            db_session, room.id, width="5.000", height="2.700"
        )
        opening = await _make_opening(
            db_session, surface.id,
            width="1.200", height="1.400",
        )
        wall_item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        reveal_item = await _make_reveal_item(
            db_session, user.id, unit=PriceUnit.M2, price="25.00"
        )
        await _make_work_plan(
            db_session, project.id, room.id, surface.id, user.id, [wall_item]
        )
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [reveal_item.id])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        wall_line = next(l for l in estimate.lines if l.price_item_id == wall_item.id)
        reveal_line = next(
            l for l in estimate.lines if l.price_item_id == reveal_item.id
        )
        # Wall net area = 5.0 × 2.7 - 1.2 × 1.4 = 13.5 - 1.68 = 11.820
        assert wall_line.quantity == Decimal("11.820")
        # Reveal area = separate, not added to wall area
        assert reveal_line.quantity_source == QuantitySource.REVEAL_AREA


# ---------------------------------------------------------------------------
# TestI — Snapshot immutability
# ---------------------------------------------------------------------------


class TestI_SnapshotImmutability:
    async def test_price_change_does_not_update_existing_line(self, db_session):
        user = await _make_user(db_session, 27001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]

        original_price = line.unit_price
        item.price = Decimal("99.99")
        await db_session.commit()

        # Re-fetch line directly
        refreshed_line = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed_line.unit_price == original_price

    async def test_surface_dimension_change_does_not_update_existing_line(
        self, db_session
    ):
        user = await _make_user(db_session, 27002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(
            db_session, room.id, width="4.000", height="2.500"
        )
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        original_qty = line.source_quantity  # 4.0 × 2.5 = 10.0

        surface.width = Decimal("10.000")
        await db_session.commit()

        refreshed_line = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed_line.source_quantity == original_qty

    async def test_disabling_reveal_does_not_update_existing_reveal_line(
        self, db_session
    ):
        user = await _make_user(db_session, 27003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(
            db_session, surface.id, reveal_depth="0.250"
        )
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        original_qty = line.source_quantity

        opening.reveal_enabled = False
        await db_session.commit()

        refreshed_line = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed_line.source_quantity == original_qty


# ---------------------------------------------------------------------------
# TestJ — Totals invariant
# ---------------------------------------------------------------------------


class TestJ_TotalsInvariant:
    async def test_total_equals_sum_of_line_amounts(self, db_session):
        user = await _make_user(db_session, 28001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(
            db_session, room.id, width="3.000", height="2.500"
        )
        item1 = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        item2 = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="5.00"
        )
        await _make_work_plan(
            db_session, project.id, room.id, surface.id, user.id, [item1, item2]
        )
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        total_from_lines = sum(
            l.amount for l in estimate.lines if l.amount is not None
        )
        assert estimate.total == total_from_lines

    async def test_total_null_when_all_amounts_null(self, db_session):
        user = await _make_user(db_session, 28002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price=None
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        assert all(l.amount is None for l in estimate.lines)
        assert estimate.total is None

    async def test_amount_computed_as_quantity_times_unit_price(self, db_session):
        user = await _make_user(db_session, 28003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        # 3.000 × 2.500 = 7.500 m²; price = 12.30 → amount = 92.25
        surface = await _make_surface(
            db_session, room.id, width="3.000", height="2.500"
        )
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="12.30"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        line = estimate.lines[0]
        assert line.quantity == Decimal("7.500")
        assert line.unit_price == Decimal("12.30")
        assert line.amount == Decimal("92.25")
        assert estimate.total == Decimal("92.25")


# ---------------------------------------------------------------------------
# TestK — Version sequencing
# ---------------------------------------------------------------------------


class TestK_VersionSequencing:
    async def test_first_generate_creates_draft_v1(self, db_session):
        user = await _make_user(db_session, 29001)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        assert estimate.version == 1
        assert estimate.status == EstimateStatus.DRAFT

    async def test_second_generate_raises_draft_exists(self, db_session):
        """POST /generate must not silently regenerate an existing DRAFT (C1)."""
        user = await _make_user(db_session, 29002)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        first = await svc.generate_estimate(project.id, user.id)
        with pytest.raises(EstimateDraftExistsError):
            await svc.generate_estimate(project.id, user.id)

        # Exactly one estimate remains
        count = (
            await db_session.execute(
                select(Estimate).where(Estimate.project_id == project.id)
            )
        ).scalars().all()
        assert len(count) == 1
        assert count[0].id == first.id

    async def test_new_draft_after_final_gets_version_2(self, db_session):
        user = await _make_user(db_session, 29003)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        draft = await svc.generate_estimate(project.id, user.id)
        draft.status = EstimateStatus.FINAL
        await db_session.commit()

        new_draft = await svc.generate_estimate(project.id, user.id)
        assert new_draft.version == 2
        assert new_draft.id != draft.id
        assert new_draft.status == EstimateStatus.DRAFT

    async def test_unique_constraint_project_version(self):
        names = {
            c.name for c in Estimate.__table__.constraints
        }
        assert "uq_estimates_project_version" in names


# ---------------------------------------------------------------------------
# TestL — DRAFT regeneration
# ---------------------------------------------------------------------------


class TestL_DraftRegeneration:
    async def test_manual_lines_preserved_during_regeneration(self, db_session):
        user = await _make_user(db_session, 30001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2)
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        manual = await svc.add_manual_line(
            estimate.id,
            user.id,
            description="Ręczna pozycja",
            scope=PriceScope.LABOR,
            unit=PriceUnit.FLAT,
            quantity=Decimal("1.000"),
            unit_price=Decimal("500.00"),
        )

        result = await svc.regenerate_draft(estimate.id, user.id)
        assert result.preserved_manual == 1
        manual_ids = {l.id for l in result.lines if l.origin == LineOrigin.MANUAL}
        assert manual.id in manual_ids

    async def test_quantity_overridden_preserved_during_regeneration(self, db_session):
        user = await _make_user(db_session, 30002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(
            db_session, room.id, width="4.000", height="2.500"
        )
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        line.quantity = Decimal("99.000")
        line.quantity_overridden = True
        await db_session.commit()

        await svc.regenerate_draft(estimate.id, user.id)

        refreshed_line = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed_line.quantity_overridden is True
        assert refreshed_line.quantity == Decimal("99.000")

    async def test_price_override_preserved_during_regeneration(self, db_session):
        user = await _make_user(db_session, 30003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        line.unit_price = Decimal("77.00")
        line.price_override = True
        await db_session.commit()

        await svc.regenerate_draft(estimate.id, user.id)

        refreshed_line = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed_line.price_override is True
        assert refreshed_line.unit_price == Decimal("77.00")

    async def test_new_planned_work_creates_new_line(self, db_session):
        user = await _make_user(db_session, 30004)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item_a = await _make_price_item(db_session, user.id, unit=PriceUnit.M2)
        await _make_work_plan(
            db_session, project.id, room.id, surface.id, user.id, [item_a]
        )
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        assert len(estimate.lines) == 1

        item_b = await _make_price_item(db_session, user.id, unit=PriceUnit.M2)
        from app.domain.services.work_plan_service import SurfaceWorkPlanService
        from app.schemas.work_plan import OrderedPriceItemSelection

        await SurfaceWorkPlanService(db_session).set_plan(
            project.id, room.id, surface.id, user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            planned_works=[
                OrderedPriceItemSelection(price_item_id=item_a.id),
                OrderedPriceItemSelection(price_item_id=item_b.id),
            ],
        )

        result = await svc.regenerate_draft(estimate.id, user.id)
        assert result.added >= 1
        assert len(result.lines) == 2

    async def test_removed_planned_work_removes_line(self, db_session):
        user = await _make_user(db_session, 30005)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item_a = await _make_price_item(db_session, user.id, unit=PriceUnit.M2)
        item_b = await _make_price_item(db_session, user.id, unit=PriceUnit.M2)
        await _make_work_plan(
            db_session, project.id, room.id, surface.id, user.id, [item_a, item_b]
        )
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        assert len(estimate.lines) == 2

        from app.domain.services.work_plan_service import SurfaceWorkPlanService
        from app.schemas.work_plan import OrderedPriceItemSelection

        await SurfaceWorkPlanService(db_session).set_plan(
            project.id, room.id, surface.id, user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            planned_works=[OrderedPriceItemSelection(price_item_id=item_a.id)],
        )

        result = await svc.regenerate_draft(estimate.id, user.id)
        assert result.removed >= 1
        assert len(result.lines) == 1


# ---------------------------------------------------------------------------
# TestM — NULL price
# ---------------------------------------------------------------------------


class TestM_NullPrice:
    async def test_null_price_produces_null_unit_price_and_amount(self, db_session):
        user = await _make_user(db_session, 31001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price=None
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.unit_price is None
        assert line.amount is None

    async def test_finalize_blocked_when_any_line_has_null_price(self, db_session):
        user = await _make_user(db_session, 31002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price=None
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        with pytest.raises(EstimateValidationError, match="price"):
            await svc.finalize(estimate.id, user.id)

    async def test_zero_price_is_real_zero_not_null(self, db_session):
        user = await _make_user(db_session, 31003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(
            db_session, room.id, width="2.000", height="2.000"
        )
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="0.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.unit_price == Decimal("0.00")
        assert line.amount == Decimal("0.00")
        assert estimate.total == Decimal("0.00")


# ---------------------------------------------------------------------------
# TestN — FINAL status transition; regeneration refused
# ---------------------------------------------------------------------------


class TestN_FinalStatus:
    async def test_finalize_sets_status_final(self, db_session):
        user = await _make_user(db_session, 32001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        final = await svc.finalize(estimate.id, user.id)
        assert final.status == EstimateStatus.FINAL

    async def test_regenerate_draft_refused_for_final(self, db_session):
        user = await _make_user(db_session, 32002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        await svc.finalize(estimate.id, user.id)

        with pytest.raises(EstimateStateError):
            await svc.regenerate_draft(estimate.id, user.id)

    async def test_regenerate_draft_refused_for_accepted(self, db_session):
        user = await _make_user(db_session, 32003)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        estimate.status = EstimateStatus.ACCEPTED
        await db_session.commit()

        with pytest.raises(EstimateStateError):
            await svc.regenerate_draft(estimate.id, user.id)

    async def test_finalize_empty_estimate_succeeds(self, db_session):
        """No lines → no NULL-priced lines → finalize succeeds."""
        user = await _make_user(db_session, 32004)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        assert estimate.lines == []
        final = await svc.finalize(estimate.id, user.id)
        assert final.status == EstimateStatus.FINAL

    async def test_add_line_to_final_estimate_raises(self, db_session):
        user = await _make_user(db_session, 32005)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        estimate = await svc.generate_estimate(project.id, user.id)
        final = await svc.finalize(estimate.id, user.id)

        with pytest.raises(EstimateStateError):
            await svc.add_manual_line(
                final.id,
                user.id,
                description="Linia ręczna",
                scope=PriceScope.LABOR,
                unit=PriceUnit.FLAT,
                quantity=Decimal("1.000"),
                unit_price=Decimal("100.00"),
            )


# ---------------------------------------------------------------------------
# TestO — regeneration diff provenance enrichment (Stage 10G.3B follow-up)
# ---------------------------------------------------------------------------


class TestO_ChangeProvenanceEnrichment:
    def _entry(self, **overrides) -> "LineChangeEntry":
        from app.domain.services.estimate_service import LineChangeEntry
        defaults = dict(
            change_type="ADDED",
            estimate_line_id=None,
            planned_work_id=uuid.uuid4(),
            surface_id=None,
            opening_id=None,
            item_code=None,
            description="Test",
            unit=PriceUnit.M2,
            old_source_quantity=None,
            new_source_quantity=Decimal("1.000"),
            old_unit_price=None,
            new_unit_price=Decimal("10.00"),
            quantity_overridden=False,
            price_override=False,
        )
        defaults.update(overrides)
        return LineChangeEntry(**defaults)

    async def test_enriches_surface_and_room_for_a_planned_work_entry(self, db_session):
        user = await _make_user(db_session, 33001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id, name="Kuchnia")
        surface = await _make_surface(db_session, room.id)
        svc = EstimateService(db_session)

        entry = self._entry(surface_id=surface.id)
        await svc._enrich_change_provenance([entry])

        assert entry.room_name == "Kuchnia"
        assert entry.surface_name == "Ściana 1"
        assert entry.surface_type_value == "WALL"
        assert entry.opening_name is None
        assert entry.opening_type_value is None

    async def test_enriches_opening_for_a_reveal_entry(self, db_session):
        user = await _make_user(db_session, 33002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id, name="Łazienka")
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(
            db_session, surface.id, opening_type=OpeningType.DOOR,
            reveal_enabled=True, reveal_depth="120.000",
        )
        opening.name = "Drzwi"
        await db_session.commit()
        svc = EstimateService(db_session)

        entry = self._entry(surface_id=surface.id, opening_id=opening.id)
        await svc._enrich_change_provenance([entry])

        assert entry.room_name == "Łazienka"
        assert entry.surface_name == "Ściana 1"
        assert entry.opening_name == "Drzwi"
        assert entry.opening_type_value == "DOOR"

    async def test_nonexistent_surface_and_opening_ids_resolve_to_none_without_crashing(self, db_session):
        svc = EstimateService(db_session)
        entry = self._entry(
            change_type="REMOVED",
            surface_id=uuid.uuid4(),
            opening_id=uuid.uuid4(),
            new_source_quantity=None,
            new_unit_price=None,
            old_source_quantity=Decimal("5.000"),
            old_unit_price=Decimal("10.00"),
        )

        await svc._enrich_change_provenance([entry])

        assert entry.room_name is None
        assert entry.surface_name is None
        assert entry.surface_type_value is None
        assert entry.opening_name is None
        assert entry.opening_type_value is None

    async def test_entries_with_no_surface_or_opening_are_left_fully_null(self, db_session):
        svc = EstimateService(db_session)
        entry = self._entry(surface_id=None, opening_id=None)
        await svc._enrich_change_provenance([entry])
        assert entry.room_name is None
        assert entry.surface_name is None
        assert entry.opening_name is None

    async def test_empty_change_list_is_a_no_op(self, db_session):
        svc = EstimateService(db_session)
        await svc._enrich_change_provenance([])  # must not raise

    async def test_bounded_queries_regardless_of_change_count(self, db_session):
        """Batch-loading must stay bounded (Surface + Room + Opening = 3
        queries max) regardless of how many change entries are enriched —
        never one query per entry.
        """
        from sqlalchemy import event
        from tests.conftest import test_engine

        user = await _make_user(db_session, 33003)
        project = await _make_project(db_session, user.id)
        entries = []
        for i in range(6):
            room = await _make_room(db_session, project.id, name=f"Room {i}")
            surface = await _make_surface(db_session, room.id)
            entries.append(self._entry(surface_id=surface.id))

        svc = EstimateService(db_session)
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(test_engine.sync_engine, "before_cursor_execute", _capture)
        try:
            await svc._enrich_change_provenance(entries)
        finally:
            event.remove(test_engine.sync_engine, "before_cursor_execute", _capture)

        # Surface batch + Room batch (no Opening query — no opening_ids present).
        assert len(statements) <= 2
        for entry in entries:
            assert entry.room_name is not None
            assert entry.surface_name == "Ściana 1"
