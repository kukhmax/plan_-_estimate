"""Stage 13C — workflow template API and WorkPlan contracts.

Template CRUD / archive / restore / ordered step replacement / context
filtering over HTTP with owner isolation; the WorkPlan occurrence_key and
wait_after_hours GET -> PUT -> GET round-trip gate; and the template-
application provenance intent (trusted server snapshot, atomicity,
idempotent retry, owner isolation). No apply endpoint exists.
"""
from decimal import Decimal
import uuid

from httpx import AsyncClient
from sqlalchemy import func, select

from app.domain.services.estimate_service import EstimateService
from app.main import app
from app.models.price_item import PriceCategory
from app.models.user import User
from app.models.work_plan import SurfaceWorkPlan
from app.models.workflow_template import SurfaceWorkPlanTemplateApplication
from tests.test_planned_work_coefficient_assignments import (
    OTHER_USER,
    VALID_USER,
    _make_group_with_options,
    _make_price_item,
    _make_project,
    _make_room,
    _make_surface,
    _wp,
    auth_header,
    get_token,
)

T = "/api/workflow-templates"


async def _login(client, db, user_dict) -> tuple[dict, User]:
    headers = auth_header(await get_token(client, user_dict))
    user = (
        await db.execute(select(User).where(User.telegram_user_id == user_dict["id"]))
    ).scalar_one()
    return headers, user


async def _owner(client, db, user_dict=VALID_USER):
    headers, user = await _login(client, db, user_dict)
    prime = await _make_price_item(db, user.id, category=PriceCategory.PREPARATION)
    skim = await _make_price_item(db, user.id, category=PriceCategory.SKIM_COAT)
    return headers, user, prime, skim


async def _create(client, headers, **body) -> dict:
    body.setdefault("display_name", "Technologia")
    resp = await client.post(T, headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _surface(db, owner_id):
    project = await _make_project(db, owner_id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)
    return project, room, surface


async def _history_count(db) -> int:
    return (
        await db.execute(select(func.count()).select_from(SurfaceWorkPlanTemplateApplication))
    ).scalar_one()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestTemplateCrud:
    async def test_create_read_list_update_archive_restore(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        created = await _create(
            async_client, headers,
            display_name="Tynk → S2", description="opis",
            applies_to_substrates=["GYPSUM_PLASTER"], applies_to_quality=["S2"],
            applies_to_surface_types=["WALL"],
            steps=[
                {"price_item_id": str(prime.id), "wait_after_hours": 4, "note": "grunt"},
                {"price_item_id": str(skim.id), "is_optional": True},
            ],
        )
        assert created["code"].startswith("CUSTOM_")
        assert "owner_id" not in created
        assert [(s["position"], s["price_item_id"], s["is_optional"], s["note"], s["wait_after_hours"]) for s in created["steps"]] == [
            (0, str(prime.id), False, "grunt", 4), (1, str(skim.id), True, None, None),
        ]
        assert created["steps"][0]["price_item"]["is_archived"] is False
        tid = created["id"]

        got = await async_client.get(f"{T}/{tid}", headers=headers)
        assert got.status_code == 200 and got.json() == created

        listed = (await async_client.get(T, headers=headers)).json()
        assert listed["total"] == 1 and listed["items"][0]["id"] == tid

        upd = await async_client.patch(f"{T}/{tid}", headers=headers, json={"display_name": "Nowa", "position": 3})
        assert upd.status_code == 200, upd.text
        assert (upd.json()["display_name"], upd.json()["position"], upd.json()["code"]) == ("Nowa", 3, created["code"])
        assert upd.json()["applies_to_quality"] == ["S2"]  # omitted -> unchanged

        arch = await async_client.post(f"{T}/{tid}/archive", headers=headers)
        assert arch.status_code == 200 and arch.json()["is_archived"] is True
        assert (await async_client.get(T, headers=headers)).json()["total"] == 0
        assert (await async_client.get(T, headers=headers, params={"archived": "archived"})).json()["total"] == 1
        assert (await async_client.get(f"{T}/{tid}", headers=headers)).status_code == 200  # still readable
        rest = await async_client.post(f"{T}/{tid}/restore", headers=headers)
        assert rest.status_code == 200 and rest.json()["is_archived"] is False
        assert len(rest.json()["steps"]) == 2

    async def test_client_cannot_set_code_owner_or_archive(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        for extra in ({"code": "X"}, {"owner_id": str(uuid.uuid4())}, {"is_archived": True}):
            resp = await async_client.post(T, headers=headers, json={"display_name": "T", **extra})
            assert resp.status_code == 422, extra
        tid = (await _create(async_client, headers))["id"]
        for extra in ({"code": "X"}, {"owner_id": str(uuid.uuid4())}):
            assert (await async_client.patch(f"{T}/{tid}", headers=headers, json=extra)).status_code == 422
        # steps carry no explicit position / id / coefficients
        for step in ({"position": 0}, {"id": str(uuid.uuid4())}, {"coefficient_option_ids": []}):
            resp = await async_client.put(f"{T}/{tid}/steps", headers=headers, json={
                "steps": [{"price_item_id": str(prime.id), **step}],
            })
            assert resp.status_code == 422, step

    async def test_no_apply_or_delete_endpoint(self, async_client: AsyncClient, db_session):
        paths = app.openapi()["paths"]
        assert not any("apply" in p for p in paths if p.startswith(T))
        assert "delete" not in paths[f"{T}/{{template_id}}"]
        headers, user, prime, skim = await _owner(async_client, db_session)
        tid = (await _create(async_client, headers))["id"]
        assert (await async_client.post(f"{T}/{tid}/apply", headers=headers, json={})).status_code in (404, 405)
        assert (await async_client.delete(f"{T}/{tid}", headers=headers)).status_code == 405

    async def test_requires_auth(self, async_client: AsyncClient, db_session):
        assert (await async_client.get(T)).status_code in (401, 403)


# ---------------------------------------------------------------------------
# Owner isolation
# ---------------------------------------------------------------------------


class TestOwnerIsolation:
    async def test_other_owner_cannot_read_or_mutate(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        created = await _create(async_client, headers, steps=[{"price_item_id": str(prime.id)}])
        tid = created["id"]
        other_headers, other = await _login(async_client, db_session, OTHER_USER)
        missing = f"{T}/{uuid.uuid4()}"
        for method, suffix, body in (
            ("get", "", None), ("patch", "", {"display_name": "hack"}),
            ("put", "/steps", {"steps": []}), ("post", "/archive", None), ("post", "/restore", None),
        ):
            foreign = await async_client.request(method, f"{T}/{tid}{suffix}", headers=other_headers, json=body)
            unknown = await async_client.request(method, f"{missing}{suffix}", headers=other_headers, json=body)
            assert foreign.status_code == unknown.status_code == 404, (method, suffix)
            assert foreign.json() == unknown.json()  # indistinguishable
        assert (await async_client.get(T, headers=other_headers)).json()["total"] == 0
        after = (await async_client.get(f"{T}/{tid}", headers=headers)).json()
        assert after == created

    async def test_foreign_price_item_rejected(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        other_headers, other = await _login(async_client, db_session, OTHER_USER)
        foreign_item = await _make_price_item(db_session, other.id)
        resp = await async_client.post(T, headers=headers, json={
            "display_name": "T", "steps": [{"price_item_id": str(foreign_item.id)}],
        })
        assert resp.status_code == 404
        resp = await async_client.post(T, headers=headers, json={
            "display_name": "T", "steps": [{"price_item_id": str(uuid.uuid4())}],
        })
        assert resp.status_code == 404
        assert (await async_client.get(T, headers=headers)).json()["total"] == 0


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


class TestFiltering:
    async def test_context_matching_with_generic_templates(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        generic = (await _create(async_client, headers, display_name="Generic"))["id"]
        plaster_s2_wall = (await _create(
            async_client, headers, display_name="Plaster S2 wall",
            applies_to_substrates=["GYPSUM_PLASTER", "CEMENT_LIME_PLASTER"],
            applies_to_quality=["S2", "S3"], applies_to_surface_types=["WALL"],
        ))["id"]
        gk_q4 = (await _create(
            async_client, headers, display_name="GK Q4",
            applies_to_substrates=["GYPSUM_BOARD"], applies_to_quality=["Q4"],
        ))["id"]
        ceiling_only = (await _create(
            async_client, headers, display_name="Ceiling", applies_to_surface_types=["CEILING"],
        ))["id"]

        async def ids(**params):
            resp = await async_client.get(T, headers=headers, params=params)
            assert resp.status_code == 200, resp.text
            return {item["id"] for item in resp.json()["items"]}

        assert await ids() == {generic, plaster_s2_wall, gk_q4, ceiling_only}
        assert await ids(substrate="GYPSUM_PLASTER", quality_target="S2", surface_type="WALL") == {generic, plaster_s2_wall}
        assert await ids(substrate="GYPSUM_BOARD", quality_target="Q4", surface_type="CEILING") == {generic, gk_q4, ceiling_only}
        assert await ids(substrate="CONCRETE") == {generic, ceiling_only}
        assert await ids(quality_target="S3") == {generic, plaster_s2_wall, ceiling_only}
        assert await ids(surface_type="FLOOR") == {generic, gk_q4}
        await async_client.post(f"{T}/{generic}/archive", headers=headers)
        assert await ids(substrate="CONCRETE") == {ceiling_only}
        assert await ids(substrate="CONCRETE", archived="all") == {generic, ceiling_only}
        assert await ids(archived="archived") == {generic}

    async def test_invalid_filter_value_rejected(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        assert (await async_client.get(T, headers=headers, params={"substrate": "MARBLE"})).status_code == 422
        assert (await async_client.get(T, headers=headers, params={"archived": "maybe"})).status_code == 422

    async def test_quality_filter_must_fit_substrate_scale(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        bad = await async_client.post(T, headers=headers, json={
            "display_name": "T", "applies_to_substrates": ["GYPSUM_BOARD"], "applies_to_quality": ["S2"],
        })
        assert bad.status_code == 422
        # mixed template: each quality fits at least one listed substrate
        ok = await async_client.post(T, headers=headers, json={
            "display_name": "T", "applies_to_substrates": ["CONCRETE", "GYPSUM_BOARD"],
            "applies_to_quality": ["S2", "Q2"],
        })
        assert ok.status_code == 201
        # PAINTED / OTHER stay unrestricted; empty substrate = any
        for subs in (["PAINTED"], ["OTHER"], []):
            resp = await async_client.post(T, headers=headers, json={
                "display_name": "T", "applies_to_substrates": subs, "applies_to_quality": ["Q3"],
            })
            assert resp.status_code == 201, subs
        # update is validated against the resulting filters
        tid = ok.json()["id"]
        resp = await async_client.patch(f"{T}/{tid}", headers=headers, json={"applies_to_substrates": ["CONCRETE"], "applies_to_quality": ["Q2"]})
        assert resp.status_code == 422
        # narrowing substrates to GK leaves S2 without a fitting substrate
        resp = await async_client.patch(f"{T}/{tid}", headers=headers, json={"applies_to_substrates": ["GYPSUM_BOARD"]})
        assert resp.status_code == 422
        resp = await async_client.patch(f"{T}/{tid}", headers=headers, json={"applies_to_substrates": ["GYPSUM_BOARD"], "applies_to_quality": ["Q2"]})
        assert resp.status_code == 200
        assert (resp.json()["applies_to_substrates"], resp.json()["applies_to_quality"]) == (["GYPSUM_BOARD"], ["Q2"])


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


class TestSteps:
    async def test_replace_is_ordered_and_failure_keeps_old_steps(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        reveal = await _make_price_item(db_session, user.id, category=PriceCategory.REVEAL)
        created = await _create(async_client, headers, steps=[{"price_item_id": str(prime.id)}])
        tid = created["id"]
        url = f"{T}/{tid}/steps"
        resp = await async_client.put(url, headers=headers, json={"steps": [
            {"price_item_id": str(skim.id), "wait_after_hours": 24},
            {"price_item_id": str(prime.id)},
            {"price_item_id": str(skim.id), "wait_after_hours": 1},
        ]})
        assert resp.status_code == 200, resp.text
        good = resp.json()
        assert [(s["position"], s["price_item_id"], s["wait_after_hours"]) for s in good["steps"]] == [
            (0, str(skim.id), 24), (1, str(prime.id), None), (2, str(skim.id), 1),
        ]
        for bad_steps, code in (
            ([{"price_item_id": str(prime.id)}, {"price_item_id": str(reveal.id)}], 422),
            ([{"price_item_id": str(prime.id), "wait_after_hours": 0}], 422),
            ([{"price_item_id": str(prime.id), "wait_after_hours": -2}], 422),
            ([{"price_item_id": str(prime.id), "wait_after_hours": 1.5}], 422),
            ([{"price_item_id": str(uuid.uuid4())}], 404),
        ):
            resp = await async_client.put(url, headers=headers, json={"steps": bad_steps})
            assert resp.status_code == code, (bad_steps, resp.text)
            db_session.expire_all()
            assert (await async_client.get(f"{T}/{tid}", headers=headers)).json()["steps"] == good["steps"]
        empty = await async_client.put(url, headers=headers, json={"steps": []})
        assert empty.status_code == 200 and empty.json()["steps"] == []

    async def test_archived_price_item_kept_and_exposed(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        tid = (await _create(async_client, headers, steps=[{"price_item_id": str(prime.id)}]))["id"]
        prime.is_archived = True
        await db_session.commit()
        got = (await async_client.get(f"{T}/{tid}", headers=headers)).json()
        assert got["steps"][0]["price_item"]["is_archived"] is True  # not deleted, UI can warn
        # re-saving the same steps keeps it; adding another occurrence does not
        keep = await async_client.put(f"{T}/{tid}/steps", headers=headers, json={"steps": [{"price_item_id": str(prime.id)}]})
        assert keep.status_code == 200
        more = await async_client.put(f"{T}/{tid}/steps", headers=headers, json={"steps": [{"price_item_id": str(prime.id)}] * 2})
        assert more.status_code == 422
        new = await async_client.post(T, headers=headers, json={"display_name": "N", "steps": [{"price_item_id": str(prime.id)}]})
        assert new.status_code == 422


# ---------------------------------------------------------------------------
# WorkPlan occurrence_key / wait_after_hours round-trip gate
# ---------------------------------------------------------------------------


class TestWorkPlanRoundTrip:
    async def test_occurrence_key_and_wait_get_put_get(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        project, room, surface = await _surface(db_session, user.id)
        _, opts = await _make_group_with_options(db_session, user.id, percentages=["0", "15"])
        url = _wp(project.id, room.id, surface.id)
        resp = await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": str(prime.id), "wait_after_hours": 12},
            {"price_item_id": str(skim.id), "coefficient_option_ids": [str(opts[1].id)]},
            {"price_item_id": str(skim.id)},
        ]})
        assert resp.status_code == 200, resp.text

        # A: GET exposes keys and breaks
        first = (await async_client.get(url, headers=headers)).json()["planned_works"]
        keys = [w["occurrence_key"] for w in first]
        assert len(set(keys)) == 3 and all(keys)
        assert [w["wait_after_hours"] for w in first] == [12, None, None]
        ids_before = [w["id"] for w in first]

        # B: PUT echoes keys (editor round-trip), reorders, changes breaks, adds one new work
        resp = await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": w["price_item_id"], "occurrence_key": w["occurrence_key"],
             "wait_after_hours": wait, "coefficient_option_ids": [o["id"] for o in w["coefficient_options"]]}
            for w, wait in ((first[2], 48), (first[0], None), (first[1], 12))
        ] + [{"price_item_id": str(prime.id)}]})
        assert resp.status_code == 200, resp.text
        assert [w["occurrence_key"] for w in resp.json()["planned_works"][:3]] == [keys[2], keys[0], keys[1]]

        # C/D/E: subsequent GET -> same keys, new row ids, new key generated and exposed
        second = (await async_client.get(url, headers=headers)).json()["planned_works"]
        assert [w["occurrence_key"] for w in second[:3]] == [keys[2], keys[0], keys[1]]
        assert [w["wait_after_hours"] for w in second] == [48, None, 12, None]
        assert set(w["id"] for w in second).isdisjoint(ids_before)
        assert second[3]["occurrence_key"] not in keys
        assert [o["id"] for o in second[2]["coefficient_options"]] == [str(opts[1].id)]

        # identical re-save of the full GET result is a no-op for identity
        resp = await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": w["price_item_id"], "occurrence_key": w["occurrence_key"], "wait_after_hours": w["wait_after_hours"],
             "coefficient_option_ids": [o["id"] for o in w["coefficient_options"]]} for w in second
        ]})
        third = (await async_client.get(url, headers=headers)).json()["planned_works"]
        assert [(w["occurrence_key"], w["wait_after_hours"]) for w in third] == [(w["occurrence_key"], w["wait_after_hours"]) for w in second]

    async def test_rejections_keep_13b_semantics(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        project, room, surface = await _surface(db_session, user.id)
        url = _wp(project.id, room.id, surface.id)
        base = (await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": str(prime.id), "wait_after_hours": 6}, {"price_item_id": str(skim.id)},
        ]})).json()
        k0, k1 = [w["occurrence_key"] for w in base["planned_works"]]
        # stale: remove k1 via a normal save
        await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": str(prime.id), "occurrence_key": k0, "wait_after_hours": 6},
        ]})
        snapshot = (await async_client.get(url, headers=headers)).json()
        other_headers, other = await _login(async_client, db_session, OTHER_USER)
        o_project, o_room, o_surface = await _surface(db_session, other.id)
        o_item = await _make_price_item(db_session, other.id)
        o_url = _wp(o_project.id, o_room.id, o_surface.id)
        foreign_key = (await async_client.put(o_url, headers=other_headers, json={
            "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(o_item.id)}],
        })).json()["planned_works"][0]["occurrence_key"]
        cases = [
            ([{"price_item_id": str(prime.id), "occurrence_key": k0}] * 2, 422),        # duplicate
            ([{"price_item_id": str(prime.id), "occurrence_key": str(uuid.uuid4())}], 409),  # invented
            ([{"price_item_id": str(prime.id), "occurrence_key": foreign_key}], 409),   # foreign owner
            ([{"price_item_id": str(skim.id), "occurrence_key": k1}], 409),             # stale
            ([{"price_item_id": str(skim.id), "occurrence_key": k0}], 422),             # mismatched PriceItem
            ([{"price_item_id": str(prime.id), "wait_after_hours": 0}], 422),
            ([{"price_item_id": str(prime.id), "wait_after_hours": -1}], 422),
        ]
        details = {}
        for works, code in cases:
            resp = await async_client.put(url, headers=headers, json={"substrate": "CONCRETE", "planned_works": works})
            assert resp.status_code == code, (works, resp.text)
            if code == 409:
                key = works[0]["occurrence_key"]
                details[key] = resp.json()["detail"].replace(key, "<k>")
            db_session.expire_all()
            assert (await async_client.get(url, headers=headers)).json() == snapshot
        assert len(set(details.values())) == 1  # invented / foreign / stale indistinguishable

    async def test_estimate_ignores_wait_and_provenance(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        prime.price = Decimal("20.00")
        await db_session.commit()
        project, room, surface = await _surface(db_session, user.id)
        url = _wp(project.id, room.id, surface.id)
        first = (await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(prime.id)}],
        })).json()
        estimates = EstimateService(db_session)
        estimate = await estimates.generate_estimate(project.id, user.id)
        before = [(l.id, l.quantity, l.unit_price, l.amount) for l in estimate.lines]
        tid = (await _create(async_client, headers, steps=[{"price_item_id": str(prime.id)}]))["id"]
        resp = await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": str(prime.id), "occurrence_key": first["planned_works"][0]["occurrence_key"], "wait_after_hours": 72},
            {"price_item_id": str(prime.id), "wait_after_hours": 24},
        ], "template_applications": [
            {"application_id": str(uuid.uuid4()), "template_id": tid, "mode": "APPEND", "steps_applied": 1},
        ]})
        assert resp.status_code == 200, resp.text
        await estimates.regenerate_draft(estimate.id, user.id, project.id)
        detail = await estimates.get_estimate_detail(project.id, estimate.id, user.id)
        lines = sorted(detail.lines, key=lambda l: l.id != before[0][0])
        assert (lines[0].id, lines[0].quantity, lines[0].unit_price, lines[0].amount) == before[0]
        assert (lines[1].quantity, lines[1].unit_price, lines[1].amount) == before[0][1:]


# ---------------------------------------------------------------------------
# Template-application provenance intent
# ---------------------------------------------------------------------------


class TestProvenanceIntent:
    async def _setup(self, client, db):
        headers, user, prime, skim = await _owner(client, db)
        project, room, surface = await _surface(db, user.id)
        template = await _create(
            client, headers, display_name="Gładź S2",
            steps=[{"price_item_id": str(prime.id), "wait_after_hours": 4}, {"price_item_id": str(skim.id)}],
        )
        return headers, user, prime, skim, _wp(project.id, room.id, surface.id), template

    @staticmethod
    def _intent(template, mode="APPEND", steps=2, app_id=None, **extra):
        return {"application_id": app_id or str(uuid.uuid4()), "template_id": template["id"],
                "mode": mode, "steps_applied": steps, **extra}

    async def test_append_records_trusted_snapshot_atomically(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, url, template = await self._setup(async_client, db_session)
        existing = (await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(skim.id)}],
        })).json()["planned_works"][0]
        app_id = str(uuid.uuid4())
        resp = await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": str(skim.id), "occurrence_key": existing["occurrence_key"]},
            {"price_item_id": str(prime.id), "wait_after_hours": 4},
            {"price_item_id": str(skim.id)},
        ], "template_applications": [self._intent(template, app_id=app_id)]})
        assert resp.status_code == 200, resp.text
        history = resp.json()["template_applications"]
        assert len(history) == 1
        record = history[0]
        assert (record["id"], record["template_id"], record["template_code"], record["template_name"], record["mode"], record["steps_applied"]) == (
            app_id, template["id"], template["code"], "Gładź S2", "APPEND", 2,
        )
        assert record["applied_at"]
        assert (await async_client.get(url, headers=headers)).json()["template_applications"] == history

    async def test_client_cannot_supply_snapshot_fields(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, url, template = await self._setup(async_client, db_session)
        for forged in ({"template_name": "Fałszywa"}, {"template_code": "X"}, {"applied_at": "2020-01-01T00:00:00Z"}):
            resp = await async_client.put(url, headers=headers, json={
                "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(prime.id)}] * 2,
                "template_applications": [self._intent(template, **forged)],
            })
            assert resp.status_code == 422, forged
        assert await _history_count(db_session) == 0

    async def test_replace_mode(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, url, template = await self._setup(async_client, db_session)
        old = (await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(skim.id)}],
        })).json()["planned_works"][0]
        # REPLACE while still echoing an old occurrence is inconsistent -> rejected, nothing changes
        bad = await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": str(skim.id), "occurrence_key": old["occurrence_key"]},
            {"price_item_id": str(prime.id)}, {"price_item_id": str(skim.id)},
        ], "template_applications": [self._intent(template, mode="REPLACE")]})
        assert bad.status_code == 422
        ok = await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": str(prime.id), "wait_after_hours": 4}, {"price_item_id": str(skim.id)},
        ], "template_applications": [self._intent(template, mode="REPLACE")]})
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert [a["mode"] for a in body["template_applications"]] == ["REPLACE"]
        assert old["occurrence_key"] not in {w["occurrence_key"] for w in body["planned_works"]}

    async def test_retry_is_idempotent(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, url, template = await self._setup(async_client, db_session)
        payload = {"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": str(prime.id), "wait_after_hours": 4}, {"price_item_id": str(skim.id)},
        ], "template_applications": [self._intent(template)]}
        first = await async_client.put(url, headers=headers, json=payload)
        retry = await async_client.put(url, headers=headers, json=payload)
        assert first.status_code == retry.status_code == 200
        assert retry.json()["template_applications"] == first.json()["template_applications"]
        assert await _history_count(db_session) == 1
        # same application_id with different content -> conflict, nothing changes
        changed = dict(payload, template_applications=[dict(payload["template_applications"][0], steps_applied=1)])
        snapshot = (await async_client.get(url, headers=headers)).json()
        assert (await async_client.put(url, headers=headers, json=changed)).status_code == 409
        db_session.expire_all()
        assert (await async_client.get(url, headers=headers)).json() == snapshot
        # a new apply action uses a new id and is recorded
        again = dict(payload, template_applications=[self._intent(template)])
        assert (await async_client.put(url, headers=headers, json=again)).status_code == 200
        assert await _history_count(db_session) == 2

    async def test_application_id_of_another_plan_conflicts(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, url, template = await self._setup(async_client, db_session)
        project2, room2, surface2 = await _surface(db_session, user.id)
        url2 = _wp(project2.id, room2.id, surface2.id)
        intent = self._intent(template)
        works = [{"price_item_id": str(prime.id)}, {"price_item_id": str(skim.id)}]
        assert (await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": works, "template_applications": [intent]})).status_code == 200
        resp = await async_client.put(url2, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": works, "template_applications": [intent]})
        assert resp.status_code == 409
        count = (await db_session.execute(select(func.count()).select_from(SurfaceWorkPlan))).scalar_one()
        assert count == 1  # the second plan was not created

    async def test_foreign_or_unknown_template_rejected_transactionally(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, url, template = await self._setup(async_client, db_session)
        base = (await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(skim.id)}],
        })).json()
        other_headers, other = await _login(async_client, db_session, OTHER_USER)
        foreign = await _create(async_client, other_headers, display_name="Cudza")
        prime_id = str(prime.id)
        for tid in (foreign["id"], str(uuid.uuid4())):
            resp = await async_client.put(url, headers=headers, json={
                "substrate": "CONCRETE", "planned_works": [{"price_item_id": prime_id}] * 2,
                "template_applications": [{"application_id": str(uuid.uuid4()), "template_id": tid, "mode": "APPEND", "steps_applied": 2}],
            })
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Workflow template not found"
            db_session.expire_all()
            assert (await async_client.get(url, headers=headers)).json() == base
        assert await _history_count(db_session) == 0

    async def test_failed_plan_save_records_no_provenance(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, url, template = await self._setup(async_client, db_session)
        reveal = await _make_price_item(db_session, user.id, category=PriceCategory.REVEAL)
        for works in (
            [{"price_item_id": str(reveal.id)}, {"price_item_id": str(prime.id)}],       # REVEAL guard
            [{"price_item_id": str(prime.id), "occurrence_key": str(uuid.uuid4())}, {"price_item_id": str(skim.id)}],  # key conflict
            [{"price_item_id": str(uuid.uuid4())}, {"price_item_id": str(skim.id)}],     # unknown item
        ):
            resp = await async_client.put(url, headers=headers, json={
                "substrate": "GYPSUM_PLASTER", "planned_works": works,
                "template_applications": [self._intent(template, steps=1)],
            })
            assert resp.status_code in (404, 409, 422), resp.text
        assert await _history_count(db_session) == 0

    async def test_step_count_bounded_by_new_occurrences(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, url, template = await self._setup(async_client, db_session)
        resp = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(prime.id)}],
            "template_applications": [self._intent(template, steps=2)],
        })
        assert resp.status_code == 422
        for bad in (0, -1):
            resp = await async_client.put(url, headers=headers, json={
                "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(prime.id)}],
                "template_applications": [self._intent(template, steps=bad)],
            })
            assert resp.status_code == 422
        dup = self._intent(template, steps=1)
        resp = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(prime.id)}] * 2,
            "template_applications": [dup, dup],
        })
        assert resp.status_code == 422
        assert await _history_count(db_session) == 0

    async def test_template_changes_do_not_rewrite_snapshot_or_plan(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, url, template = await self._setup(async_client, db_session)
        saved = (await async_client.put(url, headers=headers, json={"substrate": "GYPSUM_PLASTER", "planned_works": [
            {"price_item_id": str(prime.id), "wait_after_hours": 4}, {"price_item_id": str(skim.id)},
        ], "template_applications": [self._intent(template)]})).json()
        tid = template["id"]
        await async_client.patch(f"{T}/{tid}", headers=headers, json={"display_name": "Zmieniona"})
        await async_client.put(f"{T}/{tid}/steps", headers=headers, json={"steps": [{"price_item_id": str(skim.id), "wait_after_hours": 99}]})
        await async_client.post(f"{T}/{tid}/archive", headers=headers)
        db_session.expire_all()
        after = (await async_client.get(url, headers=headers)).json()
        assert after == saved

    async def test_archived_owned_template_may_still_be_recorded(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, url, template = await self._setup(async_client, db_session)
        await async_client.post(f"{T}/{template['id']}/archive", headers=headers)
        resp = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(prime.id)}, {"price_item_id": str(skim.id)}],
            "template_applications": [self._intent(template)],
        })
        assert resp.status_code == 200
        assert resp.json()["template_applications"][0]["template_name"] == "Gładź S2"

    async def test_apply_to_all_does_not_copy_provenance(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        project, room, surface = await _surface(db_session, user.id)
        await _make_surface(db_session, room.id)
        template = await _create(async_client, headers, steps=[{"price_item_id": str(prime.id)}])
        url = _wp(project.id, room.id, surface.id)
        resp = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(prime.id)}],
            "template_applications": [self._intent(template, steps=1)],
        })
        assert resp.status_code == 200, resp.text
        applied = await async_client.post(f"{url}/apply-to-room-walls", headers=headers)
        assert applied.status_code == 200, applied.text
        target = applied.json()["targets"][0]
        assert target["template_applications"] == []
        assert target["planned_works"][0]["occurrence_key"] != resp.json()["planned_works"][0]["occurrence_key"]
        assert await _history_count(db_session) == 1
