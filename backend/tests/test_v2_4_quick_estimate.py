"""V2-4 -- the quick estimate (docs/V2_4_PLAN_RU.md)."""
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.config import settings
from app.domain.data.quick_estimate_data import QUICK_WORK_CODES
from app.domain.services.password_login_service import PasswordLoginService
from app.models.client import Client
from app.models.estimate import Estimate
from app.models.price_item import PriceItem
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan

PASSWORD = "correct horse battery"
PRICES = {  # the owner's prices for the tests
    "CENNIK_PRIM_STD-01": "7.00",
    "CENNIK_SKIM_2L-01": "35.00",
    "CENNIK_SKIM_SAND-01": "10.00",
    "CENNIK_PAINT_2K-01": "10.00",
    "CENNIK_PAINT_CEIL-01": "16.00",
}
SALON = {"name": "Salon", "length": "5.200", "width": "3.600", "height": "2.600"}  # walls 45.76 m2, ceiling 18.72 m2
DEFAULT_WORKS = ["CENNIK_PRIM_STD-01", "CENNIK_SKIM_2L-01", "CENNIK_SKIM_SAND-01", "CENNIK_PAINT_2K-01"]


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PASSWORD_ENABLED", True)


async def _signed_in(client: AsyncClient, db, email="jan@example.pl") -> dict:
    await PasswordLoginService(db).create_account(email, "Jan", PASSWORD)
    token = (await client.post("/api/auth/password", json={"email": email, "password": PASSWORD})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _price(client: AsyncClient, headers, prices=PRICES) -> None:
    options = (await client.get("/api/quick-estimate/options", headers=headers)).json()
    for item in options["items"]:
        if item["code"] in prices:
            assert (await client.patch(f"/api/price-items/{item['id']}", json={"price": prices[item["code"]]}, headers=headers)).status_code == 200


def _body(**over) -> dict:
    body = {
        "client_name": "Jan Kowalski", "client_phone": "600 100 200", "address": "ul. Długa 5/7", "city": "Kraków",
        "rooms": [SALON], "work_codes": DEFAULT_WORKS, "include_ceiling": False, "substrate": "GYPSUM_PLASTER", "quality_target": "S2",
    }
    body.update(over)
    return body


async def _count(db, model, *conditions) -> int:
    return int((await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one())


async def _nothing_made(db) -> bool:
    counts = [await _count(db, model) for model in (Client, Project, Room, Estimate)]
    return counts == [0, 0, 0, 0]


async def test_the_options_list_the_works_in_order_with_their_rows_and_the_defaults(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    body = (await async_client.get("/api/quick-estimate/options", headers=headers)).json()
    assert [w["code"] for w in body["works"]] == list(QUICK_WORK_CODES)
    assert [w["default_on"] for w in body["works"]] == [False, True, True, True, True]
    assert {item["code"] for item in body["items"]} == set(QUICK_WORK_CODES) | {"CENNIK_PAINT_CEIL-01"}
    assert all(item["price"] is None for item in body["items"])
    assert body["default_substrate"] == "GYPSUM_PLASTER" and body["default_quality"] == "S2"
    assert body["substrates"] == ["GYPSUM_PLASTER", "CEMENT_LIME_PLASTER", "CONCRETE", "GYPSUM_BOARD"]


async def test_one_request_makes_the_client_the_object_the_rooms_the_plans_and_the_estimate(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    response = await async_client.post("/api/quick-estimate", json=_body(), headers=headers)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["rooms"] == 1 and result["lines"] == 16 and result["unpriced_lines"] == 0  # 4 walls x 4 works
    assert Decimal(result["total"]) == Decimal("2837.12")  # 45.76 m2 x (7 + 35 + 10 + 10), no openings deducted

    client = (await db_session.execute(select(Client))).scalar_one()
    assert (client.first_name, client.last_name, client.phone) == ("Jan", "Kowalski", "600 100 200")
    project = (await db_session.execute(select(Project))).scalar_one()
    assert project.name == "ul. Długa 5/7" and project.client_id == client.id and str(project.id) == result["project_id"]
    assert await _count(db_session, Room) == 1
    walls = list((await db_session.execute(select(Surface).where(Surface.surface_type == SurfaceType.WALL))).scalars())
    assert len(walls) == 4
    for wall in walls:  # the same works in the order of the screen, the agreed class on the plan
        plan = (await db_session.execute(select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == wall.id))).scalar_one()
        assert plan.substrate.value == "GYPSUM_PLASTER" and plan.quality_target.value == "S2"
        codes = [
            code for (code,) in (
                await db_session.execute(
                    select(PriceItem.code).join(SurfacePlannedWork, SurfacePlannedWork.price_item_id == PriceItem.id)
                    .where(SurfacePlannedWork.work_plan_id == plan.id).order_by(SurfacePlannedWork.position)
                )
            ).all()
        ]
        assert codes == DEFAULT_WORKS
    ceiling = (await db_session.execute(select(Surface).where(Surface.surface_type == SurfaceType.CEILING))).scalar_one()
    assert (await db_session.execute(select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == ceiling.id))).scalar_one_or_none() is None

    estimate = await async_client.get(f"/api/projects/{result['project_id']}/estimates", headers=headers)
    assert estimate.status_code == 200, estimate.text


async def test_the_ceiling_is_planned_with_its_own_painting_row(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    result = (await async_client.post("/api/quick-estimate", json=_body(include_ceiling=True), headers=headers)).json()
    assert result["lines"] == 20 and result["unpriced_lines"] == 0
    assert Decimal(result["total"]) == Decimal("4110.08")  # + 18.72 m2 x (7 + 35 + 10 + 16)
    ceiling = (await db_session.execute(select(Surface).where(Surface.surface_type == SurfaceType.CEILING))).scalar_one()
    plan = (await db_session.execute(select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == ceiling.id))).scalar_one()
    codes = [
        code for (code,) in (
            await db_session.execute(
                select(PriceItem.code).join(SurfacePlannedWork, SurfacePlannedWork.price_item_id == PriceItem.id)
                .where(SurfacePlannedWork.work_plan_id == plan.id).order_by(SurfacePlannedWork.position)
            )
        ).all()
    ]
    assert codes == ["CENNIK_PRIM_STD-01", "CENNIK_SKIM_2L-01", "CENNIK_SKIM_SAND-01", "CENNIK_PAINT_CEIL-01"]


async def test_works_without_a_price_stay_to_be_agreed_and_make_no_total(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    result = (await async_client.post("/api/quick-estimate", json=_body(rooms=[SALON, {**SALON, "name": "Sypialnia"}]), headers=headers)).json()
    assert result["rooms"] == 2 and result["lines"] == 32 and result["unpriced_lines"] == 32 and result["total"] is None


async def test_the_order_of_the_request_never_changes_the_order_of_the_works(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    result = await async_client.post("/api/quick-estimate", json=_body(work_codes=list(reversed(DEFAULT_WORKS))), headers=headers)
    assert result.status_code == 201 and Decimal(result.json()["total"]) == Decimal("2837.12")


async def test_an_existing_client_is_used_and_another_owners_is_refused(async_client: AsyncClient, db_session, web):
    first = await _signed_in(async_client, db_session)
    second = await _signed_in(async_client, db_session, "ola@example.pl")
    mine = (await async_client.post("/api/clients", json={"client_type": "PRIVATE_PERSON", "first_name": "Anna", "last_name": "Nowak"}, headers=first)).json()
    body = _body()
    body.pop("client_name"), body.pop("client_phone")
    made = await async_client.post("/api/quick-estimate", json={**body, "client_id": mine["id"]}, headers=first)
    assert made.status_code == 201 and made.json()["client_id"] == mine["id"]
    assert await _count(db_session, Client) == 1
    foreign = await async_client.post("/api/quick-estimate", json={**body, "client_id": mine["id"]}, headers=second)
    assert foreign.status_code == 404 and foreign.json()["detail"]["code"] == "CLIENT_NOT_FOUND"
    assert await _count(db_session, Project) == 1  # nothing for the other owner


@pytest.mark.parametrize(
    "change,code",
    [
        ({"substrate": "GYPSUM_BOARD", "quality_target": "S2"}, "QUALITY_SCALE_MISMATCH"),
        ({"substrate": "PAINTED"}, None),
        ({"work_codes": ["CENNIK_GK_Q4-01"]}, "QUICK_WORK_UNKNOWN"),
    ],
)
async def test_a_wrong_request_is_refused_before_anything_is_made(async_client: AsyncClient, db_session, web, change, code):
    headers = await _signed_in(async_client, db_session)
    response = await async_client.post("/api/quick-estimate", json=_body(**change), headers=headers)
    assert response.status_code == 422
    if code:
        assert response.json()["detail"]["code"] == code
    assert await _nothing_made(db_session)


@pytest.mark.parametrize(
    "change",
    [
        {"rooms": []},
        {"rooms": [{**SALON, "length": "0"}]},
        {"rooms": [{**SALON, "height": "101"}]},
        {"rooms": [{**SALON, "name": "  "}]},
        {"work_codes": []},
        {"address": ""},
        {"client_name": "  "},
        {"surprise": 1},
    ],
)
async def test_the_shape_of_the_request_is_validated(async_client: AsyncClient, db_session, web, change):
    headers = await _signed_in(async_client, db_session)
    body = _body()
    if "client_name" in change:
        body.pop("client_phone", None)
    response = await async_client.post("/api/quick-estimate", json={**body, **change}, headers=headers)
    assert response.status_code == 422, response.text
    assert await _nothing_made(db_session)


async def test_an_archived_price_row_refuses_the_estimate_before_anything_is_made(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    item = next(i for i in (await async_client.get("/api/quick-estimate/options", headers=headers)).json()["items"] if i["code"] == "CENNIK_SKIM_2L-01")
    assert (await async_client.post(f"/api/price-items/{item['id']}/archive", headers=headers)).status_code == 200
    response = await async_client.post("/api/quick-estimate", json=_body(), headers=headers)
    assert response.status_code == 422 and response.json()["detail"]["code"] == "QUICK_WORK_UNAVAILABLE"
    assert await _nothing_made(db_session)


async def test_a_drywall_estimate_takes_a_q_class(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    response = await async_client.post("/api/quick-estimate", json=_body(substrate="GYPSUM_BOARD", quality_target="Q3"), headers=headers)
    assert response.status_code == 201, response.text
    plan = (await db_session.execute(select(SurfaceWorkPlan).limit(1))).scalar_one()
    assert plan.substrate.value == "GYPSUM_BOARD" and plan.quality_target.value == "Q3"


async def test_the_data_is_ciphertext_and_readable_in_strict_mode(async_client: AsyncClient, db_session, web, encryption_on, monkeypatch):
    monkeypatch.setattr(settings, "DATA_STRICT_READ", True)
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    made = await async_client.post("/api/quick-estimate", json=_body(), headers=headers)
    assert made.status_code == 201, made.text
    assert (await async_client.get("/api/projects", headers=headers)).status_code == 200
    assert (await async_client.get("/api/clients", headers=headers)).status_code == 200
    assert (await async_client.get(f"/api/projects/{made.json()['project_id']}/estimates", headers=headers)).status_code == 200


@pytest.mark.parametrize("method,path", [("get", "/api/quick-estimate/options"), ("post", "/api/quick-estimate")])
async def test_every_quick_estimate_route_needs_a_token(async_client: AsyncClient, method, path):
    assert (await getattr(async_client, method)(path)).status_code == 401
