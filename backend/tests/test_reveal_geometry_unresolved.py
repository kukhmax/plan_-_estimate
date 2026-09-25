"""Reveal geometry guard: an opening-reveal line never silently becomes 0.

An opening could have reveals enabled with no side selected (or otherwise
underivable reveal geometry). `calculate_reveal` then yields nothing, but the
reveal line used to keep a REVEAL_LENGTH / REVEAL_AREA source with a 0.000
placeholder, which the finalize check did not treat as unresolved. It is now
an unresolved quantity (MANUAL, NULL) until the geometry is fixed or the
owner sets the quantity explicitly.
"""
from decimal import Decimal

import pytest

from app.domain.exceptions import EstimateStateError, EstimateValidationError
from app.domain.services.estimate_service import EstimateService
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.models.estimate import EstimateStatus, QuantitySource
from app.models.price_item import PriceCategory, PriceUnit
from tests.test_estimates import (
    _make_opening,
    _make_price_item,
    _make_project,
    _make_room,
    _make_surface,
    _make_user,
)

NO_SIDES = dict(reveal_left=False, reveal_right=False, reveal_top=False, reveal_bottom=False)


async def _scenario(db, telegram_id, *, unit=PriceUnit.LM, **opening_kwargs):
    user = await _make_user(db, telegram_id)
    project = await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)
    opening = await _make_opening(
        db, surface.id, width="1.500", height="2.000", reveal_depth="0.200", **opening_kwargs
    )
    item = await _make_price_item(
        db, user.id, category=PriceCategory.REVEAL, unit=unit, price="20.00"
    )
    await OpeningRevealWorkService(db).set_works(opening.id, user.id, [item.id])
    return user, project, opening, item, EstimateService(db)


def _is_unresolved(line) -> bool:
    return (
        line.quantity_source == QuantitySource.MANUAL
        and line.source_quantity is None
        and not line.quantity_overridden
    )


class TestRevealGeometryUnresolved:
    @pytest.mark.parametrize("unit", [PriceUnit.LM, PriceUnit.M2])
    async def test_no_sides_selected_is_unresolved_and_blocks_finalize(self, db_session, unit):
        user, project, opening, item, service = await _scenario(
            db_session, 1700001 if unit == PriceUnit.LM else 1700002, unit=unit, **NO_SIDES
        )
        estimate = await service.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert _is_unresolved(line)
        assert line.quantity == Decimal("0.000")  # storage placeholder, not a resolved zero
        with pytest.raises(EstimateValidationError):
            await service.finalize(estimate.id, user.id, project.id)

    async def test_missing_depth_on_existing_invalid_data_is_unresolved(self, db_session):
        user, project, opening, item, service = await _scenario(db_session, 1700003)
        opening.reveal_depth = None  # invalid data the API would reject today
        await db_session.commit()
        estimate = await service.generate_estimate(project.id, user.id)
        assert _is_unresolved(estimate.lines[0])

    @pytest.mark.parametrize(
        ("unit", "source", "quantity"),
        [
            (PriceUnit.LM, QuantitySource.REVEAL_LENGTH, Decimal("5.500")),
            (PriceUnit.M2, QuantitySource.REVEAL_AREA, Decimal("1.100")),
        ],
    )
    async def test_valid_geometry_still_derives(self, db_session, unit, source, quantity):
        user, project, opening, item, service = await _scenario(
            db_session, 1700004 if unit == PriceUnit.LM else 1700005, unit=unit,
            reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
        )
        line = (await service.generate_estimate(project.id, user.id)).lines[0]
        assert (line.quantity_source, line.source_quantity, line.quantity) == (source, quantity, quantity)

    async def test_explicit_zero_override_stays_distinct_and_finalizable(self, db_session):
        user, project, opening, item, service = await _scenario(db_session, 1700006, **NO_SIDES)
        estimate = await service.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"quantity"}, quantity=Decimal("0.000"),
        )
        finalized = await service.finalize(estimate.id, user.id, project.id)
        assert finalized.status == EstimateStatus.FINAL

    async def test_preview_and_regenerate_move_to_unresolved_and_keep_quantity_override(self, db_session):
        user, project, opening, item, service = await _scenario(
            db_session, 1700007,
            reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
        )
        estimate = await service.generate_estimate(project.id, user.id)
        assert estimate.lines[0].quantity == Decimal("5.500")

        # Geometry becomes underivable (all sides unticked).
        for side in NO_SIDES:
            setattr(opening, side, False)
        await db_session.commit()

        preview = await service.preview_regeneration(project.id, estimate.id, user.id)
        assert preview.updated == 1
        assert preview.changes[0].old_source_quantity == Decimal("5.500")
        assert preview.changes[0].new_source_quantity is None
        untouched = await service.get_estimate_detail(project.id, estimate.id, user.id)
        assert untouched.lines[0].quantity_source == QuantitySource.REVEAL_LENGTH
        assert untouched.lines[0].quantity == Decimal("5.500")

        await service.regenerate_draft(estimate.id, user.id, project.id)
        fresh = await service.get_estimate_detail(project.id, estimate.id, user.id)
        line = fresh.lines[0]
        assert _is_unresolved(line)
        with pytest.raises(EstimateValidationError):
            await service.finalize(estimate.id, user.id, project.id)

        # A manual quantity resolves it and survives further regeneration.
        await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"quantity"}, quantity=Decimal("4.000"),
        )
        await service.regenerate_draft(estimate.id, user.id, project.id)
        kept = (await service.get_estimate_detail(project.id, estimate.id, user.id)).lines[0]
        assert (kept.quantity, kept.quantity_overridden, kept.amount) == (
            Decimal("4.000"), True, Decimal("80.00"),
        )
        finalized = await service.finalize(estimate.id, user.id, project.id)
        assert finalized.status == EstimateStatus.FINAL

    async def test_final_and_accepted_lines_never_change(self, db_session):
        user, project, opening, item, service = await _scenario(
            db_session, 1700008,
            reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
        )
        estimate = await service.generate_estimate(project.id, user.id)
        await service.finalize(estimate.id, user.id, project.id)
        for side in NO_SIDES:
            setattr(opening, side, False)
        await db_session.commit()
        for status in (EstimateStatus.FINAL, EstimateStatus.ACCEPTED):
            fresh = await service.get_estimate_detail(project.id, estimate.id, user.id)
            fresh.status = status
            await db_session.commit()
            with pytest.raises(EstimateStateError):
                await service.regenerate_draft(estimate.id, user.id, project.id)
            kept = (await service.get_estimate_detail(project.id, estimate.id, user.id)).lines[0]
            assert (kept.quantity_source, kept.quantity) == (QuantitySource.REVEAL_LENGTH, Decimal("5.500"))
