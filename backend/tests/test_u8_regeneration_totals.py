"""Usability U-8 -- the preview of a regeneration tells the total of the estimate now and the one it would give.

The projected total is computed by the same rules as the regeneration (overrides kept, new works added, works that no longer exist dropped,
manual lines as they are) and is checked here against the total a REAL regeneration leaves on the same data. The preview writes nothing.
"""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import func, select

from app.domain.services.estimate_service import EstimateService
from app.models.estimate import EstimateLine
from app.models.price_item import PriceScope, PriceUnit
from app.schemas.work_plan import OrderedPriceItemSelection
from tests.test_estimate_coefficient_pricing import _generate, _make_work_plan_with_coefficients
from tests.test_estimates import _make_price_item, _make_project, _make_room, _make_surface, _make_user
from tests.test_planned_work_coefficient_assignments import _make_group_with_options

Sel = OrderedPriceItemSelection


async def _world(db, telegram_id, prices=("40.00", "25.00")):
    user = await _make_user(db, telegram_id)
    project = await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)
    items = [await _make_price_item(db, user.id, price=price) for price in prices]
    await _make_work_plan_with_coefficients(db, project.id, room.id, surface.id, user.id, [Sel(price_item_id=i.id, coefficient_option_ids=[]) for i in items])
    estimate = await _generate(db, project.id, user.id)
    return user, project, room, surface, items, estimate


async def _line_amounts(db, estimate_id):
    return (await db.execute(select(func.count()).select_from(EstimateLine).where(EstimateLine.estimate_id == estimate_id))).scalar_one()


async def test_the_preview_tells_the_total_now_and_the_total_after_a_price_change(db_session):
    user, project, _room, _surface, items, estimate = await _world(db_session, 8000001)
    before = estimate.total
    assert before is not None
    items[0].price = Decimal("50.00")  # the price book moved
    await db_session.commit()
    service = EstimateService(db_session)
    preview = await service.preview_regeneration(project.id, estimate.id, user.id)
    assert preview.current_total == before
    assert preview.projected_total is not None and preview.projected_total != before
    # nothing was written: the estimate keeps its total and its lines
    refreshed = await service.get_estimate_detail(project.id, estimate.id, user.id)
    assert refreshed.total == before
    # the real regeneration leaves exactly the projected total
    await service.regenerate_draft(estimate.id, user.id, project_id=project.id)
    after = await service.get_estimate_detail(project.id, estimate.id, user.id)
    assert after.total == preview.projected_total


async def test_the_projected_total_keeps_overrides_manual_lines_and_follows_added_and_removed_works(db_session):
    user, project, room, surface, items, estimate = await _world(db_session, 8000002)
    service = EstimateService(db_session)
    first = next(line for line in estimate.lines if line.item_code == items[0].code)
    await service.patch_line(project.id, estimate.id, user.id, first.id, provided_fields={"unit_price"}, unit_price=Decimal("99.00"))
    await service.add_manual_line(
        estimate.id, user.id, description="Transport", scope=PriceScope.LABOR, unit=PriceUnit.M2, quantity=Decimal("2"), unit_price=Decimal("10.00"),
        project_id=project.id,
    )
    # the plan changes: the second work goes, a new one comes; the price of the kept work changes in the price book too
    new_item = await _make_price_item(db_session, user.id, price="12.00")
    items[0].price = Decimal("45.00")
    await db_session.commit()
    from tests.test_estimate_coefficient_pricing import _current_keys  # noqa: PLC0415

    keys = await _current_keys(db_session, surface.id)
    from app.domain.services.work_plan_service import SurfaceWorkPlanService  # noqa: PLC0415
    from app.models.checklist import Substrate  # noqa: PLC0415

    await SurfaceWorkPlanService(db_session).set_plan(
        project.id, room.id, surface.id, user.id, substrate=Substrate.GYPSUM_PLASTER,
        planned_works=[Sel(price_item_id=items[0].id, occurrence_key=keys[0], coefficient_option_ids=[]), Sel(price_item_id=new_item.id, coefficient_option_ids=[])],
    )
    preview = await service.preview_regeneration(project.id, estimate.id, user.id)
    assert (preview.added, preview.removed, preview.preserved_manual) == (1, 1, 1)
    await service.regenerate_draft(estimate.id, user.id, project_id=project.id)
    after = await service.get_estimate_detail(project.id, estimate.id, user.id)
    assert after.total == preview.projected_total
    # the override of the owner (99.00) and the manual line are in it
    assert any(line.unit_price == Decimal("99.00") for line in after.lines)
    assert any(line.description == "Transport" for line in after.lines)


async def test_nothing_changes_means_the_two_totals_are_equal(db_session):
    user, project, _room, _surface, _items, estimate = await _world(db_session, 8000003)
    preview = await EstimateService(db_session).preview_regeneration(project.id, estimate.id, user.id)
    assert (preview.added, preview.removed, preview.updated) == (0, 0, 0)
    assert preview.current_total == estimate.total == preview.projected_total


async def test_an_estimate_with_no_priced_line_has_no_total_on_either_side(db_session):
    user, project, _room, _surface, _items, estimate = await _world(db_session, 8000004, prices=(None, None))
    preview = await EstimateService(db_session).preview_regeneration(project.id, estimate.id, user.id)
    assert preview.current_total is None and preview.projected_total is None


async def test_the_http_preview_carries_both_totals_as_strings_and_the_applied_regeneration_leaves_them_empty(async_client: AsyncClient, db_session):
    from tests.test_estimates_api import VALID_USER, _est_id, auth, get_token  # noqa: PLC0415
    from app.models.user import User  # noqa: PLC0415

    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(select(User).where(User.telegram_user_id == VALID_USER["id"]))).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price="40.00")
    await _make_work_plan_with_coefficients(db_session, project.id, room.id, surface.id, owner.id, [Sel(price_item_id=item.id, coefficient_option_ids=[])])
    estimate = await _generate(db_session, project.id, owner.id)
    item.price = Decimal("60.00")
    await db_session.commit()

    preview = await async_client.post(f"{_est_id(project.id, estimate.id)}/regenerate-preview", headers=auth(token))
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert isinstance(body["current_total"], str) and isinstance(body["projected_total"], str)  # Decimal as a string, never a float
    assert Decimal(body["projected_total"]) > Decimal(body["current_total"])
    # a stranger cannot read it
    other = await get_token(async_client, {"id": 555555555, "username": "x", "first_name": "X", "language_code": "pl"})
    assert (await async_client.post(f"{_est_id(project.id, estimate.id)}/regenerate-preview", headers=auth(other))).status_code == 404
    # the applied regeneration answers without the totals (they are a part of the preview only)
    applied = await async_client.post(f"{_est_id(project.id, estimate.id)}/regenerate", headers=auth(token))
    assert applied.status_code == 200, applied.text
    assert applied.json()["current_total"] is None and applied.json()["projected_total"] is None
