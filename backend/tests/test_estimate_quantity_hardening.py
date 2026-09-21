"""Stage 10H.1: unresolved MANUAL quantity FINAL-blocking hardening.

Manual Stage-11 integration acceptance found that a `PLANNED_WORK` line
generated for a non-M2 unit on a plain Surface (e.g. `CENNIK_SKIM_CRACK-01`,
unit LM) gets `quantity_source=MANUAL`, `source_quantity=NULL`, and a
`Decimal("0.000")` storage fallback -- a placeholder, not a resolved
quantity -- yet nothing previously stopped it from finalizing once priced.
The owner decided: unresolved MANUAL quantity must never finalize, exactly
like unresolved price, and must remain distinct from an owner's own
explicit, confirmed zero (`quantity_overridden=True`).

This module tests only `EstimateService.finalize()`'s new second blocker.
Positive controls (Surface M2, Reveal LM, Reveal M2) and the existing
price blocker are re-verified alongside it to prove independence.
"""
from decimal import Decimal
import uuid

import pytest

from app.domain.exceptions import EstimateValidationError
from app.domain.services.estimate_service import EstimateService
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.models.checklist import Substrate
from app.models.estimate import EstimateStatus, LineOrigin, QuantitySource
from app.models.price_item import PriceCategory, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _make_project(db, owner_id: uuid.UUID) -> Project:
    project = Project(
        owner_id=owner_id, name="Obiekt testowy", address="ul. Kwiatowa 1",
        city="Kraków", postal_code="30-001",
    )
    db.add(project)
    await db.commit()
    return project


async def _make_room(db, project_id: uuid.UUID) -> Room:
    room = Room(project_id=project_id, name="Salon")
    db.add(room)
    await db.commit()
    return room


async def _make_surface(
    db, room_id: uuid.UUID, *, width: str = "5.000", height: str = "2.700"
) -> Surface:
    from decimal import Decimal as D

    surface = Surface(
        room_id=room_id, name="Ściana 1", surface_type=SurfaceType.WALL,
        width=D(width), height=D(height),
    )
    db.add(surface)
    await db.commit()
    return surface


async def _make_opening(db, surface_id: uuid.UUID):
    from app.models.opening import Opening, OpeningType

    opening = Opening(
        surface_id=surface_id, opening_type=OpeningType.WINDOW,
        width=Decimal("1.200"), height=Decimal("1.400"), quantity=1,
        reveal_enabled=True, reveal_depth=Decimal("0.250"),
        reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
    )
    db.add(opening)
    await db.commit()
    return opening


async def _make_price_item(
    db, owner_id: uuid.UUID, *, unit: PriceUnit, price: str | None,
    category: PriceCategory = PriceCategory.SKIM_COAT,
):
    from app.models.price_item import PriceItem

    item = PriceItem(
        owner_id=owner_id, code=f"ITEM_{uuid.uuid4().hex[:8].upper()}",
        category=category, unit=unit, price=Decimal(price) if price is not None else None,
        price_scope=PriceScope.LABOR,
    )
    db.add(item)
    await db.commit()
    return item


async def _make_work_plan(db, project_id, room_id, surface_id, owner_id, price_items):
    from app.domain.services.work_plan_service import SurfaceWorkPlanService
    from app.schemas.work_plan import OrderedPriceItemSelection

    service = SurfaceWorkPlanService(db)
    return await service.set_plan(
        project_id, room_id, surface_id, owner_id,
        substrate=Substrate.GYPSUM_PLASTER,
        planned_works=[OrderedPriceItemSelection(price_item_id=item.id) for item in price_items],
    )


async def _setup_lm_surface_line(db, telegram_id: int):
    """A CRACK_SKIM-like Surface PLANNED_WORK line: non-M2 unit, no
    geometry -> the owner's real Stage-11 manual-acceptance scenario."""
    user = await _make_user(db, telegram_id)
    project = await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)
    item = await _make_price_item(db, user.id, unit=PriceUnit.LM, price="60.00")
    await _make_work_plan(db, project.id, room.id, surface.id, user.id, [item])
    svc = EstimateService(db)
    estimate = await svc.generate_estimate(project.id, user.id)
    return user, project, estimate, svc


class TestUnresolvedQuantityBlocksFinal:
    async def test_unresolved_manual_quantity_blocks_finalize(self, db_session):
        user, project, estimate, svc = await _setup_lm_surface_line(db_session, 51001)
        line = estimate.lines[0]
        assert line.quantity_source == QuantitySource.MANUAL
        assert line.source_quantity is None
        assert line.quantity_overridden is False
        assert line.quantity == Decimal("0.000")

        with pytest.raises(EstimateValidationError, match="unresolved quantity"):
            await svc.finalize(estimate.id, user.id, project_id=project.id)

    async def test_blocker_predicate_is_exact(self, db_session):
        """Only MANUAL + source_quantity NULL + not overridden trips the
        blocker -- verified directly against the persisted line fingerprint,
        not merely inferred from a raised exception."""
        _, _, estimate, _ = await _setup_lm_surface_line(db_session, 51002)
        line = estimate.lines[0]
        assert (
            line.origin == LineOrigin.PLANNED_WORK
            and line.quantity_source == QuantitySource.MANUAL
            and line.source_quantity is None
            and not line.quantity_overridden
        )

    async def test_explicit_manual_quantity_allows_finalize(self, db_session):
        user, project, estimate, svc = await _setup_lm_surface_line(db_session, 51003)
        line = estimate.lines[0]
        await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"quantity"}, quantity=Decimal("4.500"),
        )
        final = await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert final.status == EstimateStatus.FINAL
        refreshed = final.lines[0]
        assert refreshed.quantity == Decimal("4.500")
        assert refreshed.quantity_overridden is True

    async def test_explicit_overridden_zero_is_not_unresolved(self, db_session):
        """The owner explicitly saving 0.000 is a resolved, confirmed zero --
        never re-classified as unresolved."""
        user, project, estimate, svc = await _setup_lm_surface_line(db_session, 51004)
        line = estimate.lines[0]
        await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"quantity"}, quantity=Decimal("0.000"),
        )
        final = await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert final.status == EstimateStatus.FINAL
        refreshed = final.lines[0]
        assert refreshed.quantity == Decimal("0.000")
        assert refreshed.quantity_overridden is True

    async def test_surface_m2_auto_derived_does_not_block(self, db_session):
        user = await _make_user(db_session, 51005)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id, width="4.000", height="2.500")
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="20.00",
            category=PriceCategory.PREPARATION,
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.quantity_source == QuantitySource.SURFACE_NET_AREA
        assert line.quantity == Decimal("10.000")

        final = await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert final.status == EstimateStatus.FINAL

    async def test_reveal_lm_auto_derived_does_not_block(self, db_session):
        user = await _make_user(db_session, 51006)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.LM, price="15.00",
            category=PriceCategory.REVEAL,
        )
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.quantity_source == QuantitySource.REVEAL_LENGTH
        assert line.source_quantity == Decimal("4.000")

        final = await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert final.status == EstimateStatus.FINAL

    async def test_reveal_m2_auto_derived_does_not_block(self, db_session):
        user = await _make_user(db_session, 51007)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="25.00",
            category=PriceCategory.REVEAL,
        )
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.quantity_source == QuantitySource.REVEAL_AREA
        assert line.source_quantity == Decimal("1.000")

        final = await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert final.status == EstimateStatus.FINAL

    async def test_unresolved_price_still_independently_blocks(self, db_session):
        user = await _make_user(db_session, 51008)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price=None,
            category=PriceCategory.PREPARATION,
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        with pytest.raises(EstimateValidationError, match="no price set") as exc_info:
            await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert "unresolved quantity" not in str(exc_info.value)

    async def test_price_resolved_quantity_unresolved_still_blocks(self, db_session):
        user, project, estimate, svc = await _setup_lm_surface_line(db_session, 51009)
        line = estimate.lines[0]
        assert line.unit_price is not None  # priced via _setup_lm_surface_line
        with pytest.raises(EstimateValidationError, match="unresolved quantity") as exc_info:
            await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert "no price set" not in str(exc_info.value)

    async def test_quantity_resolved_price_unresolved_still_blocks(self, db_session):
        user = await _make_user(db_session, 51010)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.LM, price=None,
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"quantity"}, quantity=Decimal("4.500"),
        )

        with pytest.raises(EstimateValidationError, match="no price set") as exc_info:
            await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert "unresolved quantity" not in str(exc_info.value)

    async def test_both_unresolved_reports_both_blockers(self, db_session):
        user, project, estimate, svc = await _setup_lm_surface_line(db_session, 51011)
        line = estimate.lines[0]
        # Clear the price this fixture set, to also unresolve price.
        line.unit_price = None
        line.price_override = True
        await db_session.commit()

        with pytest.raises(EstimateValidationError) as exc_info:
            await svc.finalize(estimate.id, user.id, project_id=project.id)
        message = str(exc_info.value)
        assert "no price set" in message
        assert "unresolved quantity" in message

    async def test_both_resolved_allows_finalize(self, db_session):
        user, project, estimate, svc = await _setup_lm_surface_line(db_session, 51012)
        line = estimate.lines[0]
        await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"quantity"}, quantity=Decimal("4.500"),
        )
        final = await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert final.status == EstimateStatus.FINAL

    async def test_manual_origin_line_is_never_misclassified_as_unresolved(self, db_session):
        """A freeform MANUAL line always carries (quantity_source=MANUAL,
        source_quantity=NULL, quantity_overridden=False) by construction --
        the owner already typed its quantity at creation, so it must never
        block finalize."""
        user = await _make_user(db_session, 51013)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        await svc.add_manual_line(
            estimate.id, user.id, description="Transport materiałów",
            scope=PriceScope.LABOR, unit=PriceUnit.FLAT,
            quantity=Decimal("1.000"), unit_price=Decimal("100.00"),
            project_id=project.id,
        )
        line = estimate.lines[0]
        assert line.origin == LineOrigin.MANUAL
        assert line.quantity_source == QuantitySource.MANUAL
        assert line.source_quantity is None
        assert line.quantity_overridden is False

        final = await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert final.status == EstimateStatus.FINAL

    async def test_reset_after_manual_override_restores_unresolved_fingerprint(self, db_session):
        """4.500 -> reset restores the exact unresolved fingerprint (backend
        storage semantics unchanged), which must again block finalize."""
        user, project, estimate, svc = await _setup_lm_surface_line(db_session, 51014)
        line = estimate.lines[0]
        await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"quantity"}, quantity=Decimal("4.500"),
        )
        await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_quantity_override=True,
        )
        refreshed = next(ln for ln in estimate.lines if ln.id == line.id)
        assert refreshed.quantity == Decimal("0.000")
        assert refreshed.quantity_overridden is False
        assert refreshed.quantity_source == QuantitySource.MANUAL
        assert refreshed.source_quantity is None

        with pytest.raises(EstimateValidationError, match="unresolved quantity"):
            await svc.finalize(estimate.id, user.id, project_id=project.id)

    async def test_regeneration_preserves_unresolved_fingerprint(self, db_session):
        """Regenerating a DRAFT re-derives the same LM line the same way --
        still unresolved, never silently resolved by regeneration."""
        user, project, estimate, svc = await _setup_lm_surface_line(db_session, 51015)
        result = await svc.regenerate_draft(estimate.id, user.id, project_id=project.id)
        line = result.lines[0]
        assert line.quantity_source == QuantitySource.MANUAL
        assert line.source_quantity is None
        assert line.quantity_overridden is False
        assert line.quantity == Decimal("0.000")

        with pytest.raises(EstimateValidationError, match="unresolved quantity"):
            await svc.finalize(estimate.id, user.id, project_id=project.id)

    async def test_regeneration_preserves_manual_quantity_override(self, db_session):
        """An owner's manual quantity override on a PLANNED_WORK line survives
        DRAFT regeneration -- existing Stage 10 override-preservation
        contract, unaffected by this hardening."""
        user, project, estimate, svc = await _setup_lm_surface_line(db_session, 51016)
        line = estimate.lines[0]
        await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"quantity"}, quantity=Decimal("4.500"),
        )
        result = await svc.regenerate_draft(estimate.id, user.id, project_id=project.id)
        refreshed = result.lines[0]
        assert refreshed.quantity == Decimal("4.500")
        assert refreshed.quantity_overridden is True

        final = await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert final.status == EstimateStatus.FINAL
