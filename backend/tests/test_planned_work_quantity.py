"""The quantity of a work the area does not measure (owner 2026-10-30): typed on "Dodaj do prac" or in the plan, kept on the
occurrence, taken by the estimate instead of "Ilość do ustalenia"."""
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.domain.services.estimate_service import EstimateService, _resolve_surface_quantity
from app.models.estimate import EstimateLine, QuantitySource
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.schemas.work_plan import OrderedPriceItemSelection
from app.schemas.work_recommendation import WorkRecommendationAcceptRequest
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import Substrate
from tests.test_stage16e2_contract import load_migration
from tests.test_work_recommendation_accept import _plan_works, _setup_actionable


async def _lm_item(db, owner_id, code="CRACK_LM") -> PriceItem:
    item = PriceItem(owner_id=owner_id, code=code, category=PriceCategory.SKIM_COAT, unit=PriceUnit.LM, price=Decimal("50.00"),
                     price_scope=PriceScope.LABOR)
    db.add(item)
    await db.commit()
    return item


def test_the_estimate_takes_the_typed_quantity_of_a_work_the_area_does_not_measure():
    lm = PriceItem(code="X", category=PriceCategory.SKIM_COAT, unit=PriceUnit.LM)
    m2 = PriceItem(code="Y", category=PriceCategory.SKIM_COAT, unit=PriceUnit.M2)
    reveal = PriceItem(code="Z", category=PriceCategory.REVEAL, unit=PriceUnit.LM)
    assert _resolve_surface_quantity(lm, Decimal("12.5"), Decimal("7.5")) == (Decimal("7.5"), QuantitySource.MANUAL)
    assert _resolve_surface_quantity(lm, Decimal("12.5"), None) == (None, QuantitySource.MANUAL)  # still "do ustalenia"
    # an area work keeps the area; the typed quantity only fills in when the area is unknown
    assert _resolve_surface_quantity(m2, Decimal("12.5"), Decimal("3")) == (Decimal("12.5"), QuantitySource.SURFACE_NET_AREA)
    assert _resolve_surface_quantity(m2, None, Decimal("3")) == (Decimal("3"), QuantitySource.MANUAL)
    assert _resolve_surface_quantity(reveal, None, Decimal("3")) == (None, QuantitySource.MANUAL)  # reveals belong under an opening


@pytest.mark.parametrize("bad", ["0", "-1", "1.0001"])
def test_a_quantity_must_be_above_zero_with_at_most_three_places(bad):
    with pytest.raises(ValidationError):
        OrderedPriceItemSelection(price_item_id="00000000-0000-0000-0000-000000000001", quantity=bad)
    with pytest.raises(ValidationError):
        WorkRecommendationAcceptRequest(quantity=bad)


async def test_accepting_with_a_quantity_keeps_it_and_the_estimate_line_is_no_longer_to_be_set(db_session):
    user, project, room, wall, plan, _, rec, service = await _setup_actionable(db_session, 1309001)
    lm = await _lm_item(db_session, user.id)
    rec.recommended_work_code = lm.code
    await db_session.commit()
    await service.accept_recommendation(project.id, rec.id, user.id, quantity=Decimal("6.5"))
    (work,) = await _plan_works(db_session, plan.id)
    assert work.quantity == Decimal("6.5")

    estimate = await EstimateService(db_session).generate_estimate(project.id, user.id)
    (line,) = (await db_session.execute(select(EstimateLine).where(EstimateLine.estimate_id == estimate.id))).scalars().all()
    assert (line.quantity, line.source_quantity, line.quantity_source, line.amount) == (Decimal("6.5"), Decimal("6.5"), QuantitySource.MANUAL, Decimal("325.00"))


async def test_accepting_without_a_quantity_leaves_it_to_be_set(db_session):
    user, project, room, wall, plan, _, rec, service = await _setup_actionable(db_session, 1309002)
    lm = await _lm_item(db_session, user.id)
    rec.recommended_work_code = lm.code
    await db_session.commit()
    await service.accept_recommendation(project.id, rec.id, user.id)
    (work,) = await _plan_works(db_session, plan.id)
    assert work.quantity is None


async def test_the_plan_save_keeps_an_echoed_quantity_and_a_change_reaches_the_estimate(db_session):
    user, project, room, wall, plan, _, rec, _service = await _setup_actionable(db_session, 1309003)
    lm = await _lm_item(db_session, user.id)
    plans = SurfaceWorkPlanService(db_session)
    saved = await plans.set_plan(project.id, room.id, wall.id, user.id, substrate=Substrate.GYPSUM_PLASTER, quality_target=None,
                                 planned_works=[OrderedPriceItemSelection(price_item_id=lm.id, quantity=Decimal("4"))])
    key = saved.planned_works[0].occurrence_key
    estimate_id = (await EstimateService(db_session).generate_estimate(project.id, user.id)).id
    await plans.set_plan(project.id, room.id, wall.id, user.id, substrate=Substrate.GYPSUM_PLASTER, quality_target=None,
                         planned_works=[OrderedPriceItemSelection(price_item_id=lm.id, occurrence_key=key, quantity=Decimal("9"))])
    await EstimateService(db_session).regenerate_draft(estimate_id, user.id, project.id)
    db_session.expire_all()
    (line,) = (await db_session.execute(select(EstimateLine).where(EstimateLine.estimate_id == estimate_id))).scalars().all()
    assert line.quantity == Decimal("9.000")


def test_the_migration_chain():
    module = load_migration("0091_planned_work_quantity")
    assert module.down_revision == "0090_vat_own_rate" and len(module.revision) <= 32
