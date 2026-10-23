"""V2-2 -- demo data of an account (docs/V2_2_PLAN_RU.md)."""
import io
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from app.cli import demo as demo_cli
from app.core.config import settings
from app.core.data_crypto import is_encrypted
from app.domain.data.demo_data import (
    DEMO_PROJECT_NAME,
    DEMO_ROOMS,
    INVENTED_PRICES,
    demo_prices,
)
from app.domain.data.price_book_seed import (
    build_approved_market_references,
    build_approved_price_book_items,
)
from app.domain.services.demo_data_service import DemoDataService
from app.domain.services.media_purger import DisabledMediaPurger
from app.domain.services.password_login_service import PasswordLoginService
from app.domain.services.price_book_service import PriceBookService
from app.domain.services.project_service import ProjectService
from app.models.client import Client
from app.models.price_item import PriceItem
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.schemas.project import ProjectCreate

PASSWORD = "correct horse battery"


async def _owner(db, email="jan@example.pl"):
    user, _ = await PasswordLoginService(db).create_account(email, "Jan", PASSWORD)
    return user


def _service(db) -> DemoDataService:
    return DemoDataService(db, DisabledMediaPurger())


async def _count(db, model, *conditions) -> int:
    return int((await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one())


async def _price_of(db, owner_id, code):
    return (await db.execute(select(PriceItem.price).where(PriceItem.owner_id == owner_id, PriceItem.code == code))).scalar_one()


# --- the prices ----------------------------------------------------------------------------------------------------------------------------


def test_every_row_has_a_demo_price_the_minimum_of_its_window_or_an_invented_one():
    prices = demo_prices()
    assert set(prices) == {seed.code for seed in build_approved_price_book_items()} and len(prices) == 49
    assert all(price > 0 and price == price.quantize(Decimal("0.01")) for price in prices.values())
    references = build_approved_market_references()
    assert prices["CENNIK_SKIM_2L-01"] == Decimal("35.00")  # the window 35-75: its minimum, not the reference 55
    assert prices["CENNIK_PAINT_3K-01"] == Decimal("21.80")
    assert prices["CENNIK_PREP_PROT-01"] == Decimal("3.00")  # no window: invented
    for code, reference in references.items():
        assert prices[code] == Decimal(reference.market_min).quantize(Decimal("0.01"))
    assert set(INVENTED_PRICES) == {seed.code for seed in build_approved_price_book_items()} - set(references) and len(INVENTED_PRICES) == 21


# --- seed ----------------------------------------------------------------------------------------------------------------------------------


async def test_seed_makes_the_client_the_object_the_rooms_with_walls_and_the_prices(db_session):
    owner = await _owner(db_session)
    result = await _service(db_session).seed(owner.id)
    assert result.created_objects and result.rooms == 5 and result.priced_items == 49

    project = (await db_session.execute(select(Project).where(Project.owner_id == owner.id))).scalar_one()
    assert project.name == DEMO_PROJECT_NAME and project.client_id is not None
    client = (await db_session.execute(select(Client).where(Client.owner_user_id == owner.id))).scalar_one()
    assert client.notes.startswith("[DEMO]") and client.id == project.client_id
    rooms = list((await db_session.execute(select(Room).where(Room.project_id == project.id))).scalars())
    assert sorted(room.name for room in rooms) == sorted(room.name for room in DEMO_ROOMS)
    floor = sum(room.length * room.width for room in rooms)
    assert Decimal(49) < floor < Decimal(52)  # "50 m²"
    for room in rooms:
        walls = await _count(db_session, Surface, Surface.room_id == room.id, Surface.surface_type == SurfaceType.WALL)
        assert walls == 4
    prices = demo_prices()
    items = list((await db_session.execute(select(PriceItem).where(PriceItem.owner_id == owner.id))).scalars())
    assert {item.code: item.price for item in items if item.price is not None} == prices


async def test_seed_twice_makes_nothing_twice(db_session):
    owner = await _owner(db_session)
    await _service(db_session).seed(owner.id)
    again = await _service(db_session).seed(owner.id)
    assert not again.created_objects and again.rooms == 0 and again.priced_items == 0
    assert await _count(db_session, Project, Project.owner_id == owner.id) == 1
    assert await _count(db_session, Client, Client.owner_user_id == owner.id) == 1
    assert await _count(db_session, Room, Room.project_id.in_(select(Project.id).where(Project.owner_id == owner.id))) == 5


async def test_seed_without_prices_leaves_the_price_book_alone(db_session):
    owner = await _owner(db_session)
    result = await _service(db_session).seed(owner.id, with_prices=False)
    assert result.created_objects and result.priced_items == 0
    assert await _count(db_session, PriceItem, PriceItem.owner_id == owner.id) == 0  # not even the catalog is made


async def test_a_price_the_owner_has_set_is_never_overwritten(db_session):
    owner = await _owner(db_session)
    await PriceBookService(db_session).ensure_owner_catalog(owner.id)
    item = (await db_session.execute(select(PriceItem).where(PriceItem.owner_id == owner.id, PriceItem.code == "CENNIK_SKIM_2L-01"))).scalar_one()
    item.price = Decimal("99.00")
    await db_session.commit()
    result = await _service(db_session).seed(owner.id)
    assert result.priced_items == 48
    assert await _price_of(db_session, owner.id, "CENNIK_SKIM_2L-01") == Decimal("99.00")


async def test_the_demo_of_one_account_is_not_the_demo_of_another(db_session):
    first, second = await _owner(db_session), await _owner(db_session, "ola@example.pl")
    await _service(db_session).seed(first.id)
    assert (await _service(db_session).status(second.id)).project_id is None
    assert await _count(db_session, Project, Project.owner_id == second.id) == 0


# --- remove --------------------------------------------------------------------------------------------------------------------------------


async def test_remove_takes_the_demo_away_and_nothing_else(db_session):
    owner = await _owner(db_session)
    real = await ProjectService(db_session).create_project(
        ProjectCreate(name="Kowalski — łazienka", address="ul. Długa 1", city="Kraków", postal_code="30-002"), owner.id
    )
    await PriceBookService(db_session).ensure_owner_catalog(owner.id)
    mine = (await db_session.execute(select(PriceItem).where(PriceItem.owner_id == owner.id, PriceItem.code == "CENNIK_SKIM_2L-01"))).scalar_one()
    mine.price = Decimal("99.00")
    await db_session.commit()
    await _service(db_session).seed(owner.id)

    result = await _service(db_session).remove(owner.id)
    assert result.removed_project and result.removed_client and result.client_kept_reason is None and result.prices_reset == 48
    assert [p.id for p in (await db_session.execute(select(Project).where(Project.owner_id == owner.id))).scalars()] == [real.id]
    assert await _count(db_session, Client, Client.owner_user_id == owner.id) == 0
    assert await _count(db_session, Room, Room.project_id.not_in(select(Project.id))) == 0
    assert await _price_of(db_session, owner.id, "CENNIK_SKIM_2L-01") == Decimal("99.00")  # the owner's price stays
    assert await _price_of(db_session, owner.id, "CENNIK_PAINT_2K-01") is None
    status = await _service(db_session).status(owner.id)
    assert status.project_id is None and status.client_id is None and status.demo_priced_items == 0


async def test_remove_can_keep_the_prices(db_session):
    owner = await _owner(db_session)
    await _service(db_session).seed(owner.id)
    result = await _service(db_session).remove(owner.id, reset_prices=False)
    assert result.prices_reset == 0
    assert await _price_of(db_session, owner.id, "CENNIK_PAINT_2K-01") == Decimal("10.00")


async def test_remove_keeps_a_demo_client_that_got_an_object_of_its_own(db_session):
    owner = await _owner(db_session)
    await _service(db_session).seed(owner.id)
    client = (await db_session.execute(select(Client).where(Client.owner_user_id == owner.id))).scalar_one()
    await ProjectService(db_session).create_project(
        ProjectCreate(name="Prawdziwy obiekt", address="ul. Krótka 3", city="Kraków", postal_code="30-003", client_id=client.id), owner.id
    )
    result = await _service(db_session).remove(owner.id)
    assert result.removed_project and not result.removed_client and result.client_kept_reason
    assert await _count(db_session, Client, Client.id == client.id) == 1


async def test_remove_without_a_demo_does_nothing(db_session):
    owner = await _owner(db_session)
    result = await _service(db_session).remove(owner.id)
    assert (result.removed_project, result.removed_client, result.prices_reset) == (False, False, 0)


async def test_status_counts_the_demo_prices(db_session):
    owner = await _owner(db_session)
    assert (await _service(db_session).status(owner.id)).rooms == 0
    await _service(db_session).seed(owner.id)
    status = await _service(db_session).status(owner.id)
    assert status.project_id and status.client_id and status.rooms == 5 and status.demo_priced_items == 49


# --- the command line ----------------------------------------------------------------------------------------------------------------------


async def test_the_command_line_seeds_shows_and_removes(db_session, monkeypatch):
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(demo_cli, "async_session_maker", TestingSessionLocal)
    owner = await _owner(db_session)

    async def run(*argv):
        out = io.StringIO()
        code = await demo_cli.run(list(argv), out=out)
        return code, out.getvalue()

    code, text = await run("seed", "--email", "Jan@Example.pl")
    assert code == 0 and "created (5 rooms made)" in text and "prices set: 49" in text
    code, text = await run("seed", "--email", "jan@example.pl")
    assert code == 0 and "already there" in text and "prices set: 0" in text
    code, text = await run("status", "--telegram-id", str(owner.telegram_user_id))
    assert code == 0 and "rooms: 5" in text and "prices equal to the demo values: 49" in text
    code, text = await run("remove", "--email", "jan@example.pl")
    assert code == 0 and "demo object removed: True" in text and "prices reset: 49" in text


async def test_the_command_line_refuses_an_unknown_account(db_session, monkeypatch):
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(demo_cli, "async_session_maker", TestingSessionLocal)
    out = io.StringIO()
    assert await demo_cli.run(["seed", "--email", "nobody@example.pl"], out=out) == 1
    assert "ACCOUNT_NOT_FOUND" in out.getvalue()
    out = io.StringIO()
    assert await demo_cli.run(["seed", "--telegram-id", "424242"], out=out) == 1


# --- the encrypted client data (EN-2): a command line has no request that puts the owner's key in force -----------------------------------------


@pytest.fixture
def strict(monkeypatch):
    monkeypatch.setattr(settings, "DATA_STRICT_READ", True)


async def test_the_demo_is_written_as_ciphertext_found_again_and_removed(db_session, encryption_on, strict):
    owner = await _owner(db_session)
    first = await _service(db_session).seed(owner.id)
    assert first.created_objects and first.rooms == 5
    raw = (await db_session.execute(text("select name, address from projects"))).one()
    assert all(is_encrypted(value) for value in raw)  # never plain: the application refuses a plain value in strict mode
    assert is_encrypted((await db_session.execute(text("select notes from clients"))).scalar_one())

    again = await _service(db_session).seed(owner.id)
    assert not again.created_objects and await _count(db_session, Project, Project.owner_id == owner.id) == 1  # found by its decrypted name
    status = await _service(db_session).status(owner.id)
    assert status.project_id and status.client_id and status.rooms == 5

    removed = await _service(db_session).remove(owner.id)
    assert removed.removed_project and removed.removed_client and removed.prices_reset == 49
    assert await _count(db_session, Project, Project.owner_id == owner.id) == 0


async def test_the_application_reads_the_demo_in_strict_mode(async_client, db_session, encryption_on, strict, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PASSWORD_ENABLED", True)
    owner = await _owner(db_session)
    await _service(db_session).seed(owner.id)
    token = (await async_client.post("/api/auth/password", json={"email": "jan@example.pl", "password": PASSWORD})).json()["access_token"]
    projects = await async_client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
    assert projects.status_code == 200, projects.text
    assert [item["name"] for item in projects.json()["items"]] == [DEMO_PROJECT_NAME]
    clients = await async_client.get("/api/clients", headers={"Authorization": f"Bearer {token}"})
    assert clients.status_code == 200 and clients.json()["total"] == 1
