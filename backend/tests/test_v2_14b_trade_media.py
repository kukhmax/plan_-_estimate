"""V2-14b -- the photos of a room and the route map of the trade on the craftsman's page (docs/V2_14B_PLAN_RU.md)."""
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api import deps
from app.domain.rules import trade_media as rules
from app.domain.services import trade_media_service
from app.domain.services.media_storage import InMemoryMediaStorage
from app.main import app
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from tests.test_v2_14_trade_links import PUBLIC, make, owner_world

C = PhotoAttachmentContext
SECRET_CAPTION = "uwaga prywatna właściciela"


@pytest.fixture
def storage():
    memory = InMemoryMediaStorage()
    app.dependency_overrides[deps.get_photo_runtime] = lambda: SimpleNamespace(storage=memory, processor=None, admission=None)
    yield memory
    app.dependency_overrides.pop(deps.get_photo_runtime, None)


async def marked(db, w, context, utilities=(), minute=50, **targets):
    """A photo with one marker per given utility (None = an ordinary marker); returns the attachment."""
    asset = await w.attach(context, minute, **targets)
    attachment = (await db.execute(select(PhotoAttachment).where(PhotoAttachment.asset_id == asset.id))).scalar_one()
    for index, utility in enumerate(utilities):
        db.add(PhotoAnnotation(attachment_id=attachment.id, x=0.25 + index / 10, y=0.5, label=f"m{index}", utility=utility, depth_cm=4, from_floor_cm=110, position=index))
    await db.commit()
    return attachment


async def page_of(async_client, w, trade="ELECTRIC"):
    made = await make(async_client, w, trade)
    response = await async_client.get(PUBLIC, headers={"X-Trade-Link": made["token"]})
    assert response.status_code == 200, response.text
    return response.json()


def room_of(page, room_id):
    return next(r for r in page["rooms"] if r["id"] == str(room_id))


# --- the rules --------------------------------------------------------------------------------------------------------------------


def test_the_trades_work_on_their_own_utilities():
    assert rules.UTILITIES["ELECTRIC"] == {"CABLE"}
    assert rules.UTILITIES["PLUMBING"] == {"WATER_COLD", "WATER_HOT", "SEWER", "HEATING", "GAS"}
    assert not rules.UTILITIES["ELECTRIC"] & rules.UTILITIES["PLUMBING"]


# --- the page ---------------------------------------------------------------------------------------------------------------------


async def test_without_a_working_storage_the_page_has_no_photos_and_still_opens(async_client, db_session):
    w = await owner_world(async_client, db_session)  # the default storage of the tests is switched off
    page = await page_of(async_client, w)
    assert all(r["photos"] == [] and r["route_map"] == [] for r in page["rooms"]) and page["photos_expire_at"] is None


async def test_a_room_shows_its_own_photos_and_the_route_map_of_the_trade_with_only_its_markers(async_client, db_session, storage):
    w = await owner_world(async_client, db_session)
    cable = await marked(db_session, w, C.SURFACE, ["CABLE", "WATER_COLD"], surface_id=w.wall.id)
    water = await marked(db_session, w, C.SURFACE, ["WATER_HOT"], surface_id=w.wall.id)
    plain = await marked(db_session, w, C.SURFACE, [None], surface_id=w.wall.id)
    electric = room_of(await page_of(async_client, w, "ELECTRIC"), w.salon.id)
    assert [p["id"] for p in electric["route_map"]] == [str(cable.id)]
    only = electric["route_map"][0]
    assert [m["utility"] for m in only["markers"]] == ["CABLE"] and only["place"] == "Ściana A"
    assert (only["markers"][0]["depth_cm"], only["markers"][0]["from_floor_cm"], only["markers"][0]["label"]) == (4, 110, "m0")
    assert len(electric["photos"]) == 1  # the photo of the room itself (the seed has one); the wall photos are not "the room's"
    plumbing = room_of(await page_of(async_client, w, "PLUMBING"), w.salon.id)
    assert {p["id"] for p in plumbing["route_map"]} == {str(cable.id), str(water.id)}
    by_id = {p["id"]: [m["utility"] for m in p["markers"]] for p in plumbing["route_map"]}
    assert by_id[str(cable.id)] == ["WATER_COLD"] and by_id[str(water.id)] == ["WATER_HOT"]  # the cable marker of the electrician stays out
    assert str(plain.id) not in str(plumbing) and str(plain.id) not in str(electric)  # a marker with no utility is on no map


async def test_a_photo_with_markers_of_the_trade_is_on_the_map_and_not_among_the_room_photos_and_other_rooms_stay_apart(async_client, db_session, storage):
    w = await owner_world(async_client, db_session)
    on_map = await marked(db_session, w, C.ROOM, ["CABLE"], room_id=w.salon.id)
    page = await page_of(async_client, w)
    salon, kuchnia = room_of(page, w.salon.id), room_of(page, w.kuchnia.id)
    assert [p["id"] for p in salon["route_map"]] == [str(on_map.id)]
    assert str(on_map.id) not in [p["id"] for p in salon["photos"]]
    assert str(on_map.id) not in str(kuchnia) and len(kuchnia["photos"]) == 1  # the seed's photo of the kitchen only


async def test_the_links_are_signed_for_the_display_and_the_thumbnail_never_the_original_and_there_is_no_caption(async_client, db_session, storage):
    w = await owner_world(async_client, db_session)
    attachment = await marked(db_session, w, C.SURFACE, ["CABLE"], surface_id=w.wall.id)
    attachment.caption = SECRET_CAPTION
    await db_session.commit()
    page = await page_of(async_client, w)
    photo = room_of(page, w.salon.id)["route_map"][0]
    asset = (await db_session.execute(select(PhotoAsset).where(PhotoAsset.id == attachment.asset_id))).scalar_one()
    assert asset.storage_key_display.replace("/", "%2F") in photo["url"].replace("/", "%2F") or asset.storage_key_display in photo["url"]
    assert asset.storage_key_thumbnail in photo["thumb_url"]
    assert asset.storage_key_original not in str(page)
    assert "expires=1800" in photo["url"]
    assert SECRET_CAPTION not in str(page) and page["photos_expire_at"] is not None
    assert set(photo) == {"id", "thumb_url", "url", "width", "height", "place", "markers"}


async def test_archived_or_trashed_photos_and_the_photos_of_an_archived_room_are_not_shown(async_client, db_session, storage):
    w = await owner_world(async_client, db_session)
    gone = await marked(db_session, w, C.SURFACE, ["CABLE"], surface_id=w.wall.id)
    kept = await marked(db_session, w, C.SURFACE, ["CABLE"], surface_id=w.wall.id, minute=51)
    from datetime import UTC, datetime

    gone.archived_at = datetime.now(UTC)
    await db_session.commit()
    page = await page_of(async_client, w)
    assert [p["id"] for p in room_of(page, w.salon.id)["route_map"]] == [str(kept.id)]
    room = (await db_session.execute(select(Room).where(Room.id == w.salon.id))).scalar_one()
    room.is_archived = True
    await db_session.commit()
    assert w.salon.id not in [uuid.UUID(r["id"]) for r in (await page_of(async_client, w))["rooms"]]


async def test_the_number_of_photos_is_bounded(async_client, db_session, storage):
    w = await owner_world(async_client, db_session)
    for minute in range(10, 22):
        await marked(db_session, w, C.ROOM, [], minute=minute, room_id=w.salon.id)
    for minute in range(30, 46):
        await marked(db_session, w, C.SURFACE, ["CABLE"], minute=minute, surface_id=w.wall.id)
    salon = room_of(await page_of(async_client, w), w.salon.id)
    assert len(salon["photos"]) == rules.MAX_ROOM_PHOTOS and len(salon["route_map"]) == rules.MAX_MAP_PHOTOS


async def test_a_photo_of_another_object_of_the_owner_does_not_come_to_the_page(async_client, db_session, storage):
    w = await owner_world(async_client, db_session)
    from app.models.project import Project

    other = Project(owner_id=w.owner.id, client_id=w.project.client_id, name="Inny", address="x", city="y", postal_code="00-002")
    db_session.add(other)
    await db_session.commit()
    room = Room(project_id=other.id, name="Cudzy salon")
    db_session.add(room)
    await db_session.commit()
    asset = await w.attach(C.ROOM, 60, room_id=room.id)
    assert asset is not None
    page = await page_of(async_client, w)
    assert str(room.id) not in str(page) and "Cudzy" not in str(page)


async def test_the_page_opens_even_when_the_photos_cannot_be_made(async_client, db_session, storage, monkeypatch):
    w = await owner_world(async_client, db_session)

    async def broken(self, *args, **kwargs):
        raise RuntimeError("storage exploded")

    monkeypatch.setattr(trade_media_service.TradeMediaService, "for_trade", broken)
    page = await page_of(async_client, w)
    assert all(r["photos"] == [] and r["route_map"] == [] for r in page["rooms"]) and page["rooms"]


async def test_a_room_save_and_the_submit_answer_with_the_photos_again(async_client, db_session, storage):
    w = await owner_world(async_client, db_session)
    await marked(db_session, w, C.SURFACE, ["CABLE"], surface_id=w.wall.id)
    made = await make(async_client, w, "ELECTRIC")
    headers = {"X-Trade-Link": made["token"]}
    saved = await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json={"typical": [{"key": "SOCKET", "quantity": "2"}], "own": []}, headers=headers)
    assert saved.status_code == 200 and len(room_of(saved.json(), w.salon.id)["route_map"]) == 1
    sent = await async_client.post(f"{PUBLIC}/submit", json={"master_name": "Jan"}, headers=headers)
    assert sent.status_code == 200 and len(room_of(sent.json(), w.salon.id)["route_map"]) == 1
