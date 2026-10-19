"""Stage 20 -- a whole object built through the HTTP API, the way the owner builds one on the phone.

`build_world` returns the ids of every kind of resource under the NAMES THE ROUTES USE for them (`project_id`, `room_id`, ...), so the isolation
sweep can put them into any path, and the figures the scenario must reproduce (areas, the estimate total) worked out here from the inputs.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace

from httpx import AsyncClient

from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from tests.conftest import make_telegram_init_data
from tests.test_stage14b4_photo_asset import raw_asset

# the room: 4.0 x 3.0 m, height 2.5 m; one door 0.9 x 2.1 m in the first wall (4.0 m wide)
LENGTH, WIDTH, HEIGHT = Decimal("4"), Decimal("3"), Decimal("2.5")
DOOR_W, DOOR_H = Decimal("0.9"), Decimal("2.1")
WALL_PRICE, FLOOR_PRICE = Decimal("20.00"), Decimal("35.00")


@dataclass
class World:
    token: dict
    ids: dict = field(default_factory=lambda: defaultdict(list))
    facts: dict = field(default_factory=dict)

    def first(self, name: str):
        return self.ids[name][0]


async def login(client: AsyncClient, telegram_id: int, name: str = "Owner") -> dict:
    user = {"id": telegram_id, "first_name": name, "username": f"u{telegram_id}", "language_code": "pl"}
    response = await client.post("/api/auth/telegram", json={"init_data": make_telegram_init_data(user)})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def build_world(client: AsyncClient, db, telegram_id: int = 20001) -> World:
    world = World(token=await login(client, telegram_id))
    h = world.token

    async def call(method: str, path: str, expect=(200, 201), **kw):
        response = await client.request(method, path, headers=h, **kw)
        assert response.status_code in (expect if isinstance(expect, tuple) else (expect,)), f"{method} {path} -> {response.status_code} {response.text[:400]}"
        return response.json() if response.content else None

    def put(name, value):
        world.ids[name].append(value)
        return value

    await call("PUT", "/api/executor-profile", json={"name": "Jan Wykonawca", "nip": "5252248481", "street": "ul. Robocza 1", "postal_code": "00-001", "city": "Warszawa", "phone": "500600700", "email": "jan@example.pl", "bank_account": "PL61109010140000071219812874"})
    client_row = await call("POST", "/api/clients", json={"client_type": "PRIVATE_PERSON", "first_name": "Anna", "last_name": "Nowak", "phone": "501502503", "email": "anna@example.pl", "street": "ul. Długa 5", "postal_code": "30-001", "city": "Kraków", "notes": "Klucze u sąsiada"})
    put("client_id", client_row["id"])
    project = await call("POST", "/api/projects", json={"name": "Mieszkanie Nowaków", "address": "ul. Długa 5/12", "city": "Kraków", "postal_code": "30-001", "description": "Remont", "client_id": client_row["id"]})
    pid = put("project_id", project["id"])
    P = f"/api/projects/{pid}"
    put("representative_id", (await call("POST", f"{P}/representatives", json={"side": "CUSTOMER", "name": "Anna Nowak", "phone": "501502503", "may_accept_and_sign": True}))["id"])
    put("work_id", (await call("POST", f"{P}/adjacent-works", json={"work_name": "Elektryka", "performer": "Ela-Mont", "order_relation": "BEFORE_OURS"}))["id"])
    put("note_id", (await call("POST", f"{P}/notes", json={"body": "Wejście od podwórza"}))["id"])
    await call("PUT", f"{P}/finance", json={"agreed_amount": "5000.00"})

    room = await call("POST", f"{P}/rooms", json={"name": "Salon", "description": "Pokój dzienny"})
    rid = put("room_id", room["id"])
    R = f"{P}/rooms/{rid}"
    await call("PATCH", R, json={"length": str(LENGTH), "width": str(WIDTH), "height": str(HEIGHT)})
    await call("POST", f"{R}/surfaces/generate")
    surfaces = (await call("GET", f"{R}/surfaces"))["items"]
    walls = [s for s in surfaces if s["surface_type"] == "WALL"]
    floor = next(s for s in surfaces if s["surface_type"] == "FLOOR")
    ceiling = next(s for s in surfaces if s["surface_type"] == "CEILING")
    for s in surfaces:
        put("surface_id", s["id"])
    put("source_surface_id", walls[0]["id"])
    wall = walls[0]
    S = f"{R}/surfaces/{wall['id']}"
    opening = await call("POST", f"{S}/openings", json={"opening_type": "DOOR", "name": "Drzwi", "width": str(DOOR_W), "height": str(DOOR_H), "quantity": 1, "reveal_enabled": True, "reveal_depth": "0.2", "reveal_left": True, "reveal_right": True, "reveal_top": True})
    put("opening_id", opening["id"])
    segment = await call("POST", f"{R}/area-segments", json={"plane": "FLOOR", "operation": "ADD", "width": "1", "height": "1", "label": "Wnęka"}, expect=(200, 201, 422))
    if isinstance(segment, dict) and segment.get("id"):
        put("segment_id", segment["id"])

    # inspection of the first wall
    templates = (await call("GET", "/api/checklist-templates"))["items"]
    template = next(t for t in templates if t["substrate"] == "CONCRETE")
    put("template_id", template["id"])
    inspection = await call("POST", f"{R}/inspections", json={"template_id": template["id"], "substrate": "CONCRETE", "quality_target": "S2", "surface_id": wall["id"], "notes": "Wilgoć przy oknie"})
    iid = put("inspection_id", inspection["id"])
    full = await call("GET", f"/api/checklist-templates/{template['id']}")
    questions = {q["key"]: q for sec in full["sections"] for q in sec["questions"]}
    answers = [{"question_id": questions["cracks_present"]["id"], "value_bool": True}]
    if "unevenness_mm" in questions:
        answers.append({"question_id": questions["unevenness_mm"]["id"], "value_number": "4.5"})
    await call("PUT", f"{R}/inspections/{iid}/answers", json={"answers": answers})
    await call("POST", f"{R}/inspections/{iid}/complete")
    risks = await call("POST", f"{R}/risks/evaluate", json={"inspection_id": iid}, expect=(200, 201))
    for risk in (risks.get("items") if isinstance(risks, dict) else risks or []):
        put("risk_id", risk["id"])
    risk_list = (await call("GET", f"{R}/risks"))
    for risk in risk_list.get("items", []):
        if risk["id"] not in world.ids["risk_id"]:
            put("risk_id", risk["id"])
    comms = await call("POST", f"{R}/inspections/{iid}/communications/evaluate", expect=(200, 201))
    for c in (comms.get("items") if isinstance(comms, dict) else comms or []):
        put("communication_id", c["id"])
    recs = await call("POST", f"{R}/work-recommendations/evaluate", expect=(200, 201))
    for rec in (recs.get("items") if isinstance(recs, dict) else recs or []):
        put("recommendation_id", rec["id"])

    # the price book and the plans of work
    skim = await call("POST", "/api/price-items", json={"display_name": "Gładź na ścianach", "category": "SKIM_COAT", "unit": "M2", "price": str(WALL_PRICE), "price_scope": "LABOR"})
    paint = await call("POST", "/api/price-items", json={"display_name": "Malowanie podłogi", "category": "PAINTING", "unit": "M2", "price": str(FLOOR_PRICE), "price_scope": "LABOR"})
    put("price_item_id", skim["id"]); put("price_item_id", paint["id"])
    for s in walls:
        await call("PUT", f"{P}/rooms/{rid}/surfaces/{s['id']}/work-plan", json={"substrate": "CONCRETE", "quality_target": "S2", "price_item_ids": [skim["id"]]})
    await call("PUT", f"{P}/rooms/{rid}/surfaces/{floor['id']}/work-plan", json={"substrate": "CONCRETE", "quality_target": None, "price_item_ids": [paint["id"]]})
    group = await call("POST", "/api/price-coefficient-groups", json={"display_name": "Własna grupa", "description": "test"})
    put("group_id", group["id"])
    option = await call("POST", f"/api/price-coefficient-groups/{group['id']}/options", json={"display_name": "Utrudnienie", "percentage": "10"}, expect=(200, 201, 422))
    if isinstance(option, dict) and option.get("id"):
        put("option_id", option["id"])
    template_wf = await call("POST", "/api/workflow-templates", json={"display_name": "Mój proces", "applies_to_substrates": ["CONCRETE"], "steps": []}, expect=(200, 201, 422))
    if isinstance(template_wf, dict) and template_wf.get("id"):
        put("template_id", template_wf["id"])

    estimate = await call("POST", f"{P}/estimates/generate")
    eid = put("estimate_id", estimate["id"])
    for line in estimate["lines"]:
        put("line_id", line["id"])
    manual = await call("POST", f"{P}/estimates/{eid}/lines", json={"description": "Dojazd", "scope": "LABOR", "unit": "FLAT", "quantity": "1", "unit_price": "50.00", "currency": "PLN"})
    put("line_id", manual["id"]) if isinstance(manual, dict) and manual.get("id") else None
    world.facts["estimate_generated"] = estimate
    world.facts["manual_line"] = manual

    # settlements, a reminder
    put("payment_id", (await call("POST", f"{P}/payments", json={"kind": "ADVANCE", "title": "Zaliczka", "amount_gross": "1000.00", "occurred_on": "2026-10-10"}))["id"])
    reminder = await call("POST", "/api/calendar/reminders", json={"preset": "TOMORROW", "title": "Zadzwonić do klienta", "project_id": pid})
    put("reminder_id", reminder["id"])

    # the draft documents of the object
    put("contract_id", (await call("POST", f"{P}/contracts"))["id"])
    put("handover_id", (await call("POST", f"{P}/handovers"))["id"])
    put("protocol_id", (await call("POST", f"{P}/concealed-works"))["id"])
    put("protocol_id", (await call("POST", f"{P}/acceptances"))["id"])
    put("protocol_id", (await call("POST", f"{P}/decisions"))["id"])
    put("episode_id", (await call("POST", f"{P}/downtimes"))["id"])

    if db is not None:
        # a photo with an attachment and a marker (the storage is not needed: the rows are what the routes read)
        from sqlalchemy import select
        from app.models.user import User
        owner = (await db.execute(select(User).where(User.telegram_user_id == telegram_id))).scalar_one()
        import uuid as _uuid
        asset = raw_asset(SimpleNamespace(id=owner.id), SimpleNamespace(id=_uuid.UUID(pid)), status=PhotoAssetStatus.READY)
        db.add(asset)
        await db.flush()
        attachment = PhotoAttachment(asset_id=asset.id, project_id=_uuid.UUID(pid), context=PhotoAttachmentContext.PROJECT, category=PhotoCategory.GENERAL, position=0)
        db.add(attachment)
        await db.commit()
        put("asset_id", str(asset.id)); put("attachment_id", str(attachment.id))
        annotation = await call("POST", f"{P}/photo-attachments/{attachment.id}/annotations", json={"x": 0.5, "y": 0.5, "label": "Rysa"})
        put("annotation_id", annotation["id"])

    world.facts.update(walls=walls, floor=floor, ceiling=ceiling, room_id=rid, wall=wall)
    return world
